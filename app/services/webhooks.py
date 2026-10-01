from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import time
import stripe
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    PlanName,
    SubscriptionStatus,
    TenantStatus,
)
from app.repositories import subscriptions as subscriptions_repository
from app.repositories import tenants, webhook_events
from app.services.billing import BillingConfigurationError


class InvalidWebhookSignatureError(Exception):
    pass


class InvalidWebhookPayloadError(Exception):
    pass


@dataclass(frozen=True)
class WebhookResult:
    event_type: str
    duplicate: bool


def _parse_tenant_id(value: Any) -> int:
    try:
        tenant_id = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidWebhookPayloadError(
            "The Stripe event does not contain a valid tenant ID"
        ) from error

    if tenant_id <= 0:
        raise InvalidWebhookPayloadError(
            "The Stripe event does not contain a valid tenant ID"
        )

    return tenant_id

def _parse_event_created(value: Any) -> int:
    try:
        event_created = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidWebhookPayloadError(
            "The Stripe event has an invalid created timestamp"
        ) from error

    if event_created < 0:
        raise InvalidWebhookPayloadError(
            "The Stripe event has an invalid created timestamp"
        )

    return event_created

def _handle_checkout_completed(
    db: Session,
    session: dict[str, Any],
    *,
    stripe_event_created: int,
) -> None:
    if session.get("mode") != "subscription":
        return

    metadata = session.get("metadata") or {}

    tenant_id = _parse_tenant_id(
        metadata.get("tenant_id")
        or session.get("client_reference_id")
    )

    tenant = tenants.get_tenant_for_update(
        db,
        tenant_id,
    )

    if tenant is None:
        raise InvalidWebhookPayloadError(
            f"Tenant {tenant_id} was not found"
        )

    stripe_customer_id = session.get("customer")
    stripe_subscription_id = session.get("subscription")

    if not isinstance(stripe_customer_id, str):
        raise InvalidWebhookPayloadError(
            "The Checkout Session does not contain a customer ID"
        )

    if not isinstance(stripe_subscription_id, str):
        raise InvalidWebhookPayloadError(
            "The Checkout Session does not contain a subscription ID"
        )

    existing = subscriptions_repository.get_by_stripe_id(
        db,
        stripe_subscription_id,
    )

    if existing is not None:
        if existing.tenant_id != tenant.id:
            raise InvalidWebhookPayloadError(
                "The subscription belongs to another tenant"
            )

        if (
            existing.stripe_customer_id
            != stripe_customer_id
        ):
            raise InvalidWebhookPayloadError(
                "The subscription customer does not match"
            )

        # Subscription events carry more authoritative status.
        return

    subscriptions_repository.upsert_subscription(
        db,
        tenant_id=tenant.id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        plan_name=PlanName.PRO,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=None,
        current_period_end=None,
        cancel_at_period_end=False,
        last_stripe_event_created=stripe_event_created,
    )

    tenant.stripe_customer_id = stripe_customer_id
    tenant.plan = PlanName.PRO
    tenant.status = TenantStatus.ACTIVE


def _dispatch_event(
    db: Session,
    *,
    event_type: str,
    event_object: dict[str, Any],
    stripe_event_created: int,
) -> None:
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(
            db,
            event_object,
            stripe_event_created=stripe_event_created,
        )
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        synchronize_subscription(
            db,
            event_object,
            stripe_event_created=stripe_event_created,
        )
    elif event_type == "customer.subscription.deleted":
        synchronize_subscription(
            db,
            event_object,
            stripe_event_created=stripe_event_created,
            deleted=True,
        )

def _timestamp_to_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    try:
        timestamp = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidWebhookPayloadError(
            "The subscription contains an invalid billing period"
        ) from error

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


def _billing_period(
    subscription: dict[str, Any],
) -> tuple[datetime | None, datetime | None]:
    items = subscription.get("items") or {}
    item_data = items.get("data") or []

    first_item = (
        item_data[0]
        if item_data
        else {}
    )

    period_start = (
        first_item.get("current_period_start")
        or subscription.get("current_period_start")
    )
    period_end = (
        first_item.get("current_period_end")
        or subscription.get("current_period_end")
    )

    return (
        _timestamp_to_datetime(period_start),
        _timestamp_to_datetime(period_end),
    )


def synchronize_subscription(
    db: Session,
    subscription: dict[str, Any],
    *,
    stripe_event_created: int | None = None,
    deleted: bool = False,
) -> bool:
    stripe_subscription_id = subscription.get("id")
    stripe_customer_id = subscription.get("customer")

    if not isinstance(stripe_subscription_id, str):
        raise InvalidWebhookPayloadError(
            "The subscription does not contain an ID"
        )

    if not isinstance(stripe_customer_id, str):
        raise InvalidWebhookPayloadError(
            "The subscription does not contain a customer ID"
        )

    metadata = subscription.get("metadata") or {}
    tenant_id_value = metadata.get("tenant_id")

    tenant = None

    if tenant_id_value is not None:
        tenant_id = _parse_tenant_id(tenant_id_value)
        tenant = tenants.get_tenant_for_update(
            db,
            tenant_id,
        )

    if tenant is None:
        tenant = tenants.get_tenant_by_customer_for_update(
            db,
            stripe_customer_id,
        )

    if tenant is None:
        raise InvalidWebhookPayloadError(
            "The subscription does not match a tenant"
        )

    applied_event_created = (
        int(time.time())
        if stripe_event_created is None
        else stripe_event_created
    )

    existing = subscriptions_repository.get_by_stripe_id(
        db,
        stripe_subscription_id,
    )

    if (
        existing is not None
        and applied_event_created
        < existing.last_stripe_event_created
    ):
        return False

    stripe_status = (
        "canceled"
        if deleted
        else subscription.get("status")
    )

    status_pair = SUBSCRIPTION_STATUS_MAP.get(
        stripe_status
    )

    if status_pair is None:
        raise InvalidWebhookPayloadError(
            f"Unsupported subscription status: {stripe_status}"
        )

    subscription_status, tenant_status = status_pair
    period_start, period_end = _billing_period(
        subscription
    )

    subscriptions_repository.upsert_subscription(
        db,
        tenant_id=tenant.id,
        stripe_subscription_id=stripe_subscription_id,
        stripe_customer_id=stripe_customer_id,
        plan_name=PlanName.PRO,
        status=subscription_status,
        current_period_start=period_start,
        current_period_end=period_end,
        cancel_at_period_end=bool(
            subscription.get("cancel_at_period_end", False)
        ),
        last_stripe_event_created=applied_event_created,
    )

    tenant.stripe_customer_id = stripe_customer_id
    tenant.status = tenant_status

    if subscription_status == SubscriptionStatus.CANCELED:
        tenant.plan = PlanName.FREE
    else:
        tenant.plan = PlanName.PRO
    return True


def process_webhook(
    db: Session,
    *,
    payload: bytes,
    signature: str,
) -> WebhookResult:
    settings = get_settings()

    if not settings.stripe_webhook_secret:
        raise BillingConfigurationError(
            "STRIPE_WEBHOOK_SECRET is not configured"
        )

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret,
        )
    except (ValueError, stripe.SignatureVerificationError) as error:
        raise InvalidWebhookSignatureError(
            "The Stripe webhook signature is invalid"
        ) from error

    event_id = event["id"]
    event_type = event["type"]
    event_created = _parse_event_created(
        event["created"]
    )

    claimed = webhook_events.claim_event(
        db,
        stripe_event_id=event_id,
        event_type=event_type,
    )

    if not claimed:
        return WebhookResult(
            event_type=event_type,
            duplicate=True,
        )

    try:
        event_object = event["data"]["object"].to_dict()

        _dispatch_event(
            db,
            event_type=event_type,
            event_object=event_object,
            stripe_event_created=event_created,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return WebhookResult(
        event_type=event_type,
        duplicate=False,
    )

SUBSCRIPTION_STATUS_MAP = {
    "active": (
        SubscriptionStatus.ACTIVE,
        TenantStatus.ACTIVE,
    ),
    "trialing": (
        SubscriptionStatus.TRIALING,
        TenantStatus.ACTIVE,
    ),
    "past_due": (
        SubscriptionStatus.PAST_DUE,
        TenantStatus.PAST_DUE,
    ),
    "unpaid": (
        SubscriptionStatus.PAST_DUE,
        TenantStatus.PAST_DUE,
    ),
    "paused": (
        SubscriptionStatus.PAST_DUE,
        TenantStatus.PAST_DUE,
    ),
    "incomplete": (
        SubscriptionStatus.INCOMPLETE,
        TenantStatus.INCOMPLETE,
    ),
    "incomplete_expired": (
        SubscriptionStatus.CANCELED,
        TenantStatus.CANCELED,
    ),
    "canceled": (
        SubscriptionStatus.CANCELED,
        TenantStatus.CANCELED,
    ),
}
