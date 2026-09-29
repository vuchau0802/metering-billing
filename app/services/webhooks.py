from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

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


def _handle_checkout_completed(
    db: Session,
    session: Any,
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

    if not isinstance(stripe_customer_id, str):
        raise InvalidWebhookPayloadError(
            "The Checkout Session does not contain a customer ID"
        )

    stripe_subscription_id = session.get("subscription")

    if not isinstance(stripe_subscription_id, str):
        raise InvalidWebhookPayloadError(
            "The Checkout Session does not contain a subscription ID"
        )

    tenant.stripe_customer_id = stripe_customer_id
    tenant.plan = PlanName.PRO
    tenant.status = TenantStatus.ACTIVE


def _dispatch_event(
    db: Session,
    *,
    event_type: str,
    event_object: dict[str, Any],
) -> None:
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(
            db,
            event_object,
        )
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        _handle_subscription_event(
            db,
            event_object,
        )
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_event(
            db,
            event_object,
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


def _handle_subscription_event(
    db: Session,
    subscription: dict[str, Any],
    *,
    deleted: bool = False,
) -> None:
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
    )

    tenant.stripe_customer_id = stripe_customer_id
    tenant.status = tenant_status

    if subscription_status == SubscriptionStatus.CANCELED:
        tenant.plan = PlanName.FREE
    else:
        tenant.plan = PlanName.PRO


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