from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.main import app
from app.models import (
    Plan,
    PlanName,
    Tenant,
    TenantStatus,
    UsageEvent,
)


ACTIVE_TENANT_ID = 900_001
PAST_DUE_TENANT_ID = 900_002

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
    ]

    with SessionLocal() as db:
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
                    stripe_price_id=None,
                )
            )
            db.flush()

        db.add_all(
            [
                Tenant(
                    id=ACTIVE_TENANT_ID,
                    email="integration-active@example.com",
                    plan=PlanName.FREE,
                    status=TenantStatus.ACTIVE,
                ),
                Tenant(
                    id=PAST_DUE_TENANT_ID,
                    email="integration-past-due@example.com",
                    plan=PlanName.FREE,
                    status=TenantStatus.PAST_DUE,
                ),
            ]
        )
        db.commit()

    with TestClient(app) as test_client:
        yield test_client

    clean_test_data()


def idempotency_headers() -> dict[str, str]:
    return {
        "Idempotency-Key": str(uuid4()),
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

    usage = client.get(f"/usage/{ACTIVE_TENANT_ID}")

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
        headers=idempotency_headers(),
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


def test_unknown_tenant_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/usage/999999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "tenant_not_found"