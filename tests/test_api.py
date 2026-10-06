from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import hash_tenant_api_key
from app.db import SessionLocal
from app.main import app
from app.models import (
    Plan,
    PlanName,
    Tenant,
    TenantStatus,
    UsageAlert,
    UsageEvent,
    UsageType,
)


ACTIVE_TENANT_ID = 900_001
PAST_DUE_TENANT_ID = 900_002
PRO_TENANT_ID = 900_003
ACTIVE_TENANT_KEY = "test-active-tenant-key"
PAST_DUE_TENANT_KEY = "test-past-due-tenant-key"
PRO_TENANT_KEY = "test-pro-tenant-key"

VALID_BODY = {
    "tenant_id": ACTIVE_TENANT_ID,
    "input_tokens": 10,
    "cached_input_tokens": 0,
    "output_tokens": 5,
    "reasoning_tokens": 1,
}


def clean_test_data() -> None:
    tenant_ids = [
        ACTIVE_TENANT_ID,
        PAST_DUE_TENANT_ID,
        PRO_TENANT_ID,
    ]

    with SessionLocal() as db:
        db.execute(
            delete(UsageAlert).where(
                UsageAlert.tenant_id.in_(tenant_ids)
            )
        )
        db.execute(
            delete(UsageEvent).where(
                UsageEvent.tenant_id.in_(tenant_ids)
            )
        )
        db.execute(
            delete(Tenant).where(
                Tenant.id.in_(tenant_ids)
            )
        )
        db.commit()


@pytest.fixture
def client() -> TestClient:
    clean_test_data()

    with SessionLocal() as db:
        free_plan = db.get(Plan, PlanName.FREE)

        if free_plan is None:
            db.add(
                Plan(
                    name=PlanName.FREE,
                    api_calls_limit=1_000,
                    ai_tokens_limit=100_000,
                    overage_enabled=False,
                    stripe_price_id=None,
                )
            )
            db.flush()

        pro_plan = db.get(Plan, PlanName.PRO)

        if pro_plan is None:
            db.add(
                Plan(
                    name=PlanName.PRO,
                    api_calls_limit=50_000,
                    ai_tokens_limit=5_000_000,
                    overage_enabled=True,
                    stripe_price_id=None,
                )
            )
            db.flush()
        else:
            pro_plan.overage_enabled = True

        db.add_all(
            [
                Tenant(
                    id=ACTIVE_TENANT_ID,
                    email="integration-active@example.com",
                    plan=PlanName.FREE,
                    status=TenantStatus.ACTIVE,
                    api_key_hash=hash_tenant_api_key(
                        ACTIVE_TENANT_KEY
                    ),
                ),
                Tenant(
                    id=PAST_DUE_TENANT_ID,
                    email="integration-past-due@example.com",
                    plan=PlanName.FREE,
                    status=TenantStatus.PAST_DUE,
                    api_key_hash=hash_tenant_api_key(
                        PAST_DUE_TENANT_KEY
                    ),
                ),
                Tenant(
                    id=PRO_TENANT_ID,
                    email="integration-pro@example.com",
                    plan=PlanName.PRO,
                    status=TenantStatus.ACTIVE,
                    api_key_hash=hash_tenant_api_key(
                        PRO_TENANT_KEY
                    ),
                ),
            ]
        )
        db.commit()

    with TestClient(app) as test_client:
        yield test_client

    clean_test_data()


def tenant_headers(
    tenant_key: str = ACTIVE_TENANT_KEY,
) -> dict[str, str]:
    return {
        "X-Tenant-Key": tenant_key,
    }


def idempotency_headers(
    tenant_key: str = ACTIVE_TENANT_KEY,
) -> dict[str, str]:
    return {
        "Idempotency-Key": str(uuid4()),
        **tenant_headers(tenant_key),
    }


def test_duplicate_request_creates_one_event(
    client: TestClient,
) -> None:
    headers = idempotency_headers()

    first = client.post(
        "/generate",
        headers=headers,
        json=VALID_BODY,
    )
    second = client.post(
        "/generate",
        headers=headers,
        json=VALID_BODY,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert "Idempotent-Replay" not in first.headers
    assert second.headers["Idempotent-Replay"] == "true"

    key = headers["Idempotency-Key"]

    with SessionLocal() as db:
        event_count = db.scalar(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.idempotency_key == key
            )
        )

    assert event_count == 1


def test_exact_quota_then_next_request_is_rejected(
    client: TestClient,
) -> None:
    exact_limit = {
        "tenant_id": ACTIVE_TENANT_ID,
        "input_tokens": 100_000,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
    }

    accepted = client.post(
        "/generate",
        headers=idempotency_headers(),
        json=exact_limit,
    )

    assert accepted.status_code == 200
    assert accepted.json()["usage"] == {
        "used": 100_000,
        "limit": 100_000,
        "remaining": 0,
        "overage": 0,
    }

    rejected = client.post(
        "/generate",
        headers=idempotency_headers(),
        json={
            **exact_limit,
            "input_tokens": 1,
        },
    )

    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "quota_exceeded"
    assert rejected.json()["error"]["used"] == 100_000
    assert rejected.json()["error"]["requested"] == 1
    assert "Retry-After" in rejected.headers

    usage = client.get(
        f"/usage/{ACTIVE_TENANT_ID}",
        headers=tenant_headers(),
    )

    assert usage.status_code == 200
    assert (
        usage.json()["usage"]["ai_tokens"]["used"]
        == 100_000
    )


def test_past_due_tenant_returns_402(
    client: TestClient,
) -> None:
    body = {
        **VALID_BODY,
        "tenant_id": PAST_DUE_TENANT_ID,
    }

    response = client.post(
        "/generate",
        headers=idempotency_headers(PAST_DUE_TENANT_KEY),
        json=body,
    )

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "payment_required"
    assert response.json()["error"]["tenant_status"] == "past_due"


def test_reused_key_with_different_body_returns_409(
    client: TestClient,
) -> None:
    headers = idempotency_headers()

    first = client.post(
        "/generate",
        headers=headers,
        json=VALID_BODY,
    )

    changed_body = {
        **VALID_BODY,
        "output_tokens": 6,
    }

    conflict = client.post(
        "/generate",
        headers=headers,
        json=changed_body,
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert (
        conflict.json()["error"]["code"]
        == "idempotency_conflict"
    )


def test_invalid_input_returns_400(
    client: TestClient,
) -> None:
    invalid_body = {
        **VALID_BODY,
        "input_tokens": -1,
    }

    response = client.post(
        "/generate",
        headers=idempotency_headers(),
        json=invalid_body,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"


def test_unknown_tenant_returns_401(
    client: TestClient,
) -> None:
    response = client.get("/usage/999999999")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_tenant_key_cannot_access_another_tenant(
    client: TestClient,
) -> None:
    response = client.get(
        f"/usage/{PAST_DUE_TENANT_ID}",
        headers=tenant_headers(ACTIVE_TENANT_KEY),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

def test_billing_success_redirect() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/billing/success",
            params={"session_id": "cs_test_example"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Checkout completed successfully.",
        "session_id": "cs_test_example",
    }


def test_billing_cancel_redirect() -> None:
    with TestClient(app) as client:
        response = client.get("/billing/cancel")

    assert response.status_code == 200
    assert response.json() == {
        "status": "canceled",
        "message": "Checkout was canceled.",
        "session_id": None,
    }


def test_api_call_is_idempotent_and_updates_rollup(
    client: TestClient,
) -> None:
    headers = idempotency_headers()
    body = {
        "tenant_id": ACTIVE_TENANT_ID,
    }

    first = client.post(
        "/api-call",
        headers=headers,
        json=body,
    )
    replay = client.post(
        "/api-call",
        headers=headers,
        json=body,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert "Idempotent-Replay" not in first.headers
    assert replay.headers["Idempotent-Replay"] == "true"

    assert first.json()["quantity"] == 1
    assert first.json()["cost_microusd"] == 2
    assert first.json()["usage"] == {
        "used": 1,
        "limit": 1_000,
        "remaining": 999,
        "overage": 0,
    }

    key = headers["Idempotency-Key"]

    with SessionLocal() as db:
        event_count = db.scalar(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.idempotency_key == key
            )
        )
        event = db.scalar(
            select(UsageEvent).where(
                UsageEvent.idempotency_key == key
            )
        )

    assert event_count == 1
    assert event is not None
    assert event.usage_type == UsageType.API_CALL
    assert event.token_breakdown is None

    usage = client.get(
        f"/usage/{ACTIVE_TENANT_ID}",
        headers=tenant_headers(),
    )

    assert usage.status_code == 200
    assert usage.json()["usage"]["api_calls"] == {
        "used": 1,
        "limit": 1_000,
        "remaining": 999,
        "overage": 0,
    }
    assert usage.json()["cost_microusd"] == 2


def test_api_call_exact_quota_then_next_is_rejected(
    client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.add(
            UsageEvent(
                tenant_id=ACTIVE_TENANT_ID,
                idempotency_key="api-call-boundary-seed",
                usage_type=UsageType.API_CALL,
                quantity=999,
                token_breakdown=None,
                cost_microusd=1_998,
                response_snapshot={},
            )
        )
        db.commit()

    accepted = client.post(
        "/api-call",
        headers=idempotency_headers(),
        json={
            "tenant_id": ACTIVE_TENANT_ID,
        },
    )

    assert accepted.status_code == 200
    assert accepted.json()["usage"] == {
        "used": 1_000,
        "limit": 1_000,
        "remaining": 0,
        "overage": 0,
    }

    rejected = client.post(
        "/api-call",
        headers=idempotency_headers(),
        json={
            "tenant_id": ACTIVE_TENANT_ID,
        },
    )

    assert rejected.status_code == 429
    assert rejected.json()["error"]["usage_type"] == "api_call"
    assert rejected.json()["error"]["used"] == 1_000
    assert rejected.json()["error"]["requested"] == 1
    assert (
        rejected.json()["error"]["message"]
        == "api call quota exceeded for the current UTC month."
    )
    assert "Retry-After" in rejected.headers

    usage = client.get(
        f"/usage/{ACTIVE_TENANT_ID}",
        headers=tenant_headers(),
    )

    assert usage.status_code == 200
    assert usage.json()["usage"]["api_calls"] == {
        "used": 1_000,
        "limit": 1_000,
        "remaining": 0,
        "overage": 0,
    }
    assert usage.json()["cost_microusd"] == 2_000


def test_idempotency_key_cannot_cross_usage_types(
    client: TestClient,
) -> None:
    headers = idempotency_headers()

    generated = client.post(
        "/generate",
        headers=headers,
        json=VALID_BODY,
    )
    conflicted = client.post(
        "/api-call",
        headers=headers,
        json={
            "tenant_id": ACTIVE_TENANT_ID,
        },
    )

    assert generated.status_code == 200
    assert conflicted.status_code == 409
    assert (
        conflicted.json()["error"]["code"]
        == "idempotency_conflict"
    )


def test_zero_token_request_is_rejected_without_event(
    client: TestClient,
) -> None:
    headers = idempotency_headers()
    response = client.post(
        "/generate",
        headers=headers,
        json={
            "tenant_id": ACTIVE_TENANT_ID,
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_request"

    with SessionLocal() as db:
        event_count = db.scalar(
            select(func.count(UsageEvent.id)).where(
                UsageEvent.idempotency_key
                == headers["Idempotency-Key"]
            )
        )

    assert event_count == 0

def test_pro_overage_is_charged_persisted_and_idempotent(
    client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.add(
            UsageEvent(
                tenant_id=PRO_TENANT_ID,
                idempotency_key="pro-overage-boundary-seed",
                usage_type=UsageType.AI_TOKENS,
                quantity=4_999_900,
                token_breakdown={
                    "input": 4_999_900,
                    "cached_input": 0,
                    "output": 0,
                    "reasoning": 0,
                },
                overage_quantity=0,
                overage_cost_microusd=0,
                cost_microusd=749_985_000,
                response_snapshot={},
            )
        )
        db.commit()

    headers = idempotency_headers(PRO_TENANT_KEY)
    body = {
        "tenant_id": PRO_TENANT_ID,
        "input_tokens": 200,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
    }

    first = client.post(
        "/generate",
        headers=headers,
        json=body,
    )
    replay = client.post(
        "/generate",
        headers=headers,
        json=body,
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["Idempotent-Replay"] == "true"

    result = first.json()

    assert result["quantity"] == 200
    assert result["overage_quantity"] == 100
    assert result["overage_cost_microusd"] == 75_000
    assert result["cost_microusd"] == 105_000
    assert result["usage"] == {
        "used": 5_000_100,
        "limit": 5_000_000,
        "remaining": 0,
        "overage": 100,
    }

    with SessionLocal() as db:
        events = db.scalars(
            select(UsageEvent).where(
                UsageEvent.idempotency_key
                == headers["Idempotency-Key"]
            )
        ).all()

    assert len(events) == 1
    assert events[0].overage_quantity == 100
    assert events[0].overage_cost_microusd == 75_000
    assert events[0].cost_microusd == 105_000

    usage = client.get(
        f"/usage/{PRO_TENANT_ID}",
        headers=tenant_headers(PRO_TENANT_KEY),
    )

    assert usage.status_code == 200

    report = usage.json()

    assert report["overage_enabled"] is True
    assert report["usage"]["ai_tokens"] == {
        "used": 5_000_100,
        "limit": 5_000_000,
        "remaining": 0,
        "overage": 100,
    }
    assert report["overage_cost_microusd"] == 75_000
    assert report["cost_microusd"] == 750_090_000
    assert (
        report["projected_cost_microusd"]
        >= report["cost_microusd"]
    )
