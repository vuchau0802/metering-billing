import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import (
    PlanName,
    ProcessedWebhookEvent,
    Subscription,
    SubscriptionStatus,
    Tenant,
    TenantStatus,
)


WEBHOOK_SECRET = "whsec_automated_test_secret"
EVENT_ID = "evt_test_webhook_dedup"
CHECKOUT_EVENT_ID = "evt_test_checkout_completed"
CHECKOUT_TENANT_ID = 9001
CHECKOUT_CUSTOMER_ID = "cus_test_phase3"
CHECKOUT_SUBSCRIPTION_ID = "sub_test_phase3"
SUBSCRIPTION_TENANT_ID = 9002
SUBSCRIPTION_CUSTOMER_ID = "cus_test_lifecycle"
SUBSCRIPTION_ID = "sub_test_lifecycle"
ORDERING_TENANT_ID = 9003
ORDERING_CUSTOMER_ID = "cus_test_ordering"
ORDERING_SUBSCRIPTION_ID = "sub_test_ordering"

SUBSCRIPTION_EVENT_IDS = [
    "evt_test_subscription_created",
    "evt_test_subscription_updated",
    "evt_test_subscription_deleted",
]
ORDERING_EVENT_IDS = [
    "evt_test_ordering_created",
    "evt_test_ordering_deleted",
    "evt_test_ordering_stale_updated",
]

def clean_webhook_test_data() -> None:
    with SessionLocal() as db:
        db.execute(
            delete(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.stripe_event_id
                == EVENT_ID
            )
        )
        db.commit()


def build_payload() -> bytes:
    event = {
        "id": EVENT_ID,
        "object": "event",
        "type": "payment_intent.succeeded",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "pi_test_webhook",
                "object": "payment_intent",
            }
        },
    }

    return json.dumps(
        event,
        separators=(",", ":"),
    ).encode("utf-8")

def build_checkout_payload() -> bytes:
    event = {
        "id": CHECKOUT_EVENT_ID,
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_test_phase3",
                "object": "checkout.session",
                "mode": "subscription",
                "client_reference_id": str(
                    CHECKOUT_TENANT_ID
                ),
                "customer": CHECKOUT_CUSTOMER_ID,
                "subscription": CHECKOUT_SUBSCRIPTION_ID,
                "metadata": {
                    "tenant_id": str(
                        CHECKOUT_TENANT_ID
                    ),
                    "plan": "pro",
                },
            }
        },
    }

    return json.dumps(
        event,
        separators=(",", ":"),
    ).encode("utf-8")

def build_subscription_payload(
    *,
    event_id: str,
    event_type: str,
    status: str,
    created: int | None = None,
    tenant_id: int = SUBSCRIPTION_TENANT_ID,
    customer_id: str = SUBSCRIPTION_CUSTOMER_ID,
    subscription_id: str = SUBSCRIPTION_ID,
) -> bytes:
    event = {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "created": (
            int(time.time())
            if created is None
            else created
        ),
        "livemode": False,
        "data": {
            "object": {
                "id": subscription_id,
                "object": "subscription",
                "customer": customer_id,
                "status": status,
                "cancel_at_period_end": False,
                "metadata": {
                    "tenant_id": str(
                        tenant_id
                    ),
                    "plan": "pro",
                },
                "items": {
                    "object": "list",
                    "data": [
                        {
                            "id": "si_test_lifecycle",
                            "object": "subscription_item",
                            "current_period_start": 1_700_000_000,
                            "current_period_end": 1_702_592_000,
                        }
                    ],
                },
            }
        },
    }

    return json.dumps(
        event,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(payload: bytes) -> str:
    timestamp = int(time.time())
    signed_payload = (
        f"{timestamp}.{payload.decode('utf-8')}"
        .encode("utf-8")
    )
    signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    return f"t={timestamp},v1={signature}"


@pytest.fixture
def webhook_client(
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    clean_webhook_test_data()

    monkeypatch.setenv(
        "STRIPE_WEBHOOK_SECRET",
        WEBHOOK_SECRET,
    )
    get_settings.cache_clear()

    with TestClient(app) as client:
        yield client

    clean_webhook_test_data()
    get_settings.cache_clear()


def test_forged_signature_returns_400(
    webhook_client: TestClient,
) -> None:
    response = webhook_client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={
            "Stripe-Signature": "forged",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["error"]["code"]
        == "invalid_webhook_signature"
    )


def test_replayed_event_is_processed_once(
    webhook_client: TestClient,
) -> None:
    payload = build_payload()
    headers = {
        "Stripe-Signature": sign_payload(payload),
        "Content-Type": "application/json",
    }

    first = webhook_client.post(
        "/webhooks/stripe",
        content=payload,
        headers=headers,
    )
    second = webhook_client.post(
        "/webhooks/stripe",
        content=payload,
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["duplicate"] is False

    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert first.json()["event_type"] == "payment_intent.succeeded"

    with SessionLocal() as db:
        count = db.scalar(
            select(
                func.count(ProcessedWebhookEvent.id)
            ).where(
                ProcessedWebhookEvent.stripe_event_id
                == EVENT_ID
            )
        )

    assert count == 1

def test_checkout_completed_upgrades_tenant_to_pro(
    webhook_client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.execute(
            delete(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.stripe_event_id
                == CHECKOUT_EVENT_ID
            )
        )
        db.execute(
            delete(Subscription).where(
                Subscription.stripe_subscription_id
                == CHECKOUT_SUBSCRIPTION_ID
            )
        )
        db.execute(
            delete(Tenant).where(
                Tenant.id == CHECKOUT_TENANT_ID
            )
        )
        db.add(
            Tenant(
                id=CHECKOUT_TENANT_ID,
                email="checkout-test@example.com",
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.commit()

    try:
        payload = build_checkout_payload()
        headers = {
            "Stripe-Signature": sign_payload(payload),
            "Content-Type": "application/json",
        }

        first = webhook_client.post(
            "/webhooks/stripe",
            content=payload,
            headers=headers,
        )
        replay = webhook_client.post(
            "/webhooks/stripe",
            content=payload,
            headers=headers,
        )

        assert first.status_code == 200
        assert first.json()["duplicate"] is False

        assert replay.status_code == 200
        assert replay.json()["duplicate"] is True

        with SessionLocal() as db:
            tenant = db.get(
                Tenant,
                CHECKOUT_TENANT_ID,
            )
            subscription = db.scalar(
                select(Subscription).where(
                    Subscription.stripe_subscription_id
                    == CHECKOUT_SUBSCRIPTION_ID
                )
            )

            assert tenant is not None
            assert tenant.plan == PlanName.PRO
            assert tenant.status == TenantStatus.ACTIVE
            assert (
                tenant.stripe_customer_id
                == CHECKOUT_CUSTOMER_ID
            )

            assert subscription is not None
            assert subscription.tenant_id == CHECKOUT_TENANT_ID
            assert subscription.status == SubscriptionStatus.ACTIVE
            assert subscription.plan_name == PlanName.PRO
            assert subscription.last_stripe_event_created > 0
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ProcessedWebhookEvent).where(
                    ProcessedWebhookEvent.stripe_event_id
                    == CHECKOUT_EVENT_ID
                )
            )
            db.execute(
                delete(Subscription).where(
                    Subscription.stripe_subscription_id
                    == CHECKOUT_SUBSCRIPTION_ID
                )
            )
            db.execute(
                delete(Tenant).where(
                    Tenant.id == CHECKOUT_TENANT_ID
                )
            )
            db.commit()

def test_subscription_lifecycle_updates_tenant_and_record(
    webhook_client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.execute(
            delete(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.stripe_event_id.in_(
                    SUBSCRIPTION_EVENT_IDS
                )
            )
        )
        db.execute(
            delete(Subscription).where(
                Subscription.stripe_subscription_id
                == SUBSCRIPTION_ID
            )
        )
        db.execute(
            delete(Tenant).where(
                Tenant.id == SUBSCRIPTION_TENANT_ID
            )
        )
        db.add(
            Tenant(
                id=SUBSCRIPTION_TENANT_ID,
                email="subscription-test@example.com",
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.commit()

    try:
        events = [
            (
                SUBSCRIPTION_EVENT_IDS[0],
                "customer.subscription.created",
                "active",
            ),
            (
                SUBSCRIPTION_EVENT_IDS[1],
                "customer.subscription.updated",
                "past_due",
            ),
            (
                SUBSCRIPTION_EVENT_IDS[2],
                "customer.subscription.deleted",
                "active",
            ),
        ]

        for event_id, event_type, status in events:
            payload = build_subscription_payload(
                event_id=event_id,
                event_type=event_type,
                status=status,
            )

            response = webhook_client.post(
                "/webhooks/stripe",
                content=payload,
                headers={
                    "Stripe-Signature": sign_payload(
                        payload
                    ),
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            assert response.json()["duplicate"] is False

        with SessionLocal() as db:
            tenant = db.get(
                Tenant,
                SUBSCRIPTION_TENANT_ID,
            )
            subscription = db.scalar(
                select(Subscription).where(
                    Subscription.stripe_subscription_id
                    == SUBSCRIPTION_ID
                )
            )
            subscription_count = db.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.stripe_subscription_id
                    == SUBSCRIPTION_ID
                )
            )

            assert tenant is not None
            assert tenant.plan == PlanName.FREE
            assert tenant.status == TenantStatus.CANCELED
            assert (
                tenant.stripe_customer_id
                == SUBSCRIPTION_CUSTOMER_ID
            )

            assert subscription is not None
            assert (
                subscription.status
                == SubscriptionStatus.CANCELED
            )
            assert subscription.plan_name == PlanName.PRO
            assert subscription_count == 1
            assert subscription.current_period_start is not None
            assert subscription.current_period_end is not None
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ProcessedWebhookEvent).where(
                    ProcessedWebhookEvent.stripe_event_id.in_(
                        SUBSCRIPTION_EVENT_IDS
                    )
                )
            )
            db.execute(
                delete(Subscription).where(
                    Subscription.stripe_subscription_id
                    == SUBSCRIPTION_ID
                )
            )
            db.execute(
                delete(Tenant).where(
                    Tenant.id == SUBSCRIPTION_TENANT_ID
                )
            )
            db.commit()


def test_stale_subscription_event_cannot_resurrect_canceled_tenant(
    webhook_client: TestClient,
) -> None:
    with SessionLocal() as db:
        db.execute(
            delete(ProcessedWebhookEvent).where(
                ProcessedWebhookEvent.stripe_event_id.in_(
                    ORDERING_EVENT_IDS
                )
            )
        )
        db.execute(
            delete(Subscription).where(
                Subscription.stripe_subscription_id
                == ORDERING_SUBSCRIPTION_ID
            )
        )
        db.execute(
            delete(Tenant).where(
                Tenant.id == ORDERING_TENANT_ID
            )
        )
        db.add(
            Tenant(
                id=ORDERING_TENANT_ID,
                email="ordering-test@example.com",
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.commit()

    try:
        events = [
            (
                ORDERING_EVENT_IDS[0],
                "customer.subscription.created",
                "active",
                2_000_000_000,
            ),
            (
                ORDERING_EVENT_IDS[1],
                "customer.subscription.deleted",
                "active",
                2_000_000_200,
            ),
            (
                ORDERING_EVENT_IDS[2],
                "customer.subscription.updated",
                "active",
                2_000_000_100,
            ),
        ]

        for event_id, event_type, status, created in events:
            payload = build_subscription_payload(
                event_id=event_id,
                event_type=event_type,
                status=status,
                created=created,
                tenant_id=ORDERING_TENANT_ID,
                customer_id=ORDERING_CUSTOMER_ID,
                subscription_id=ORDERING_SUBSCRIPTION_ID,
            )

            response = webhook_client.post(
                "/webhooks/stripe",
                content=payload,
                headers={
                    "Stripe-Signature": sign_payload(payload),
                    "Content-Type": "application/json",
                },
            )

            assert response.status_code == 200
            assert response.json()["duplicate"] is False

        with SessionLocal() as db:
            tenant = db.get(
                Tenant,
                ORDERING_TENANT_ID,
            )
            subscription = db.scalar(
                select(Subscription).where(
                    Subscription.stripe_subscription_id
                    == ORDERING_SUBSCRIPTION_ID
                )
            )
            processed_count = db.scalar(
                select(
                    func.count(ProcessedWebhookEvent.id)
                ).where(
                    ProcessedWebhookEvent.stripe_event_id.in_(
                        ORDERING_EVENT_IDS
                    )
                )
            )

            assert tenant is not None
            assert tenant.plan == PlanName.FREE
            assert tenant.status == TenantStatus.CANCELED

            assert subscription is not None
            assert (
                subscription.status
                == SubscriptionStatus.CANCELED
            )
            assert (
                subscription.last_stripe_event_created
                == 2_000_000_200
            )
            assert processed_count == 3
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ProcessedWebhookEvent).where(
                    ProcessedWebhookEvent.stripe_event_id.in_(
                        ORDERING_EVENT_IDS
                    )
                )
            )
            db.execute(
                delete(Subscription).where(
                    Subscription.stripe_subscription_id
                    == ORDERING_SUBSCRIPTION_ID
                )
            )
            db.execute(
                delete(Tenant).where(
                    Tenant.id == ORDERING_TENANT_ID
                )
            )
            db.commit()
