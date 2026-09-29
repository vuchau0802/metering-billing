from typing import Any

import stripe
from sqlalchemy.orm import Session
from stripe import StripeClient

from app.config import get_settings
from app.models import PlanName, TenantStatus
from app.repositories import tenants as tenants_repository
from app.schemas import CheckoutResponse
from app.services.metering import (
    PaymentRequiredError,
    TenantNotFoundError,
)


class BillingConfigurationError(Exception):
    pass


class AlreadySubscribedError(Exception):
    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        super().__init__(f"Tenant {tenant_id} already has the Pro plan")


class CheckoutCreationError(Exception):
    pass


def create_checkout_session(
    db: Session,
    tenant_id: int,
) -> CheckoutResponse:
    settings = get_settings()

    if not settings.stripe_secret_key:
        raise BillingConfigurationError(
            "STRIPE_SECRET_KEY is not configured"
        )

    tenant_record = tenants_repository.get_tenant_with_plan(
        db,
        tenant_id,
    )

    if tenant_record is None:
        raise TenantNotFoundError(tenant_id)

    tenant, _current_plan = tenant_record

    if tenant.status != TenantStatus.ACTIVE:
        raise PaymentRequiredError(
            tenant_id=tenant.id,
            status=tenant.status,
        )

    if tenant.plan == PlanName.PRO:
        raise AlreadySubscribedError(tenant.id)

    pro_plan = tenants_repository.get_plan(
        db,
        PlanName.PRO,
    )

    if pro_plan is None or not pro_plan.stripe_price_id:
        raise BillingConfigurationError(
            "The Pro Stripe Price ID is not configured"
        )

    parameters: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [
            {
                "price": pro_plan.stripe_price_id,
                "quantity": 1,
            }
        ],
        "client_reference_id": str(tenant.id),
        "metadata": {
            "tenant_id": str(tenant.id),
            "plan": PlanName.PRO.value,
        },
        "subscription_data": {
            "metadata": {
                "tenant_id": str(tenant.id),
                "plan": PlanName.PRO.value,
            }
        },
        "success_url": (
            f"{settings.app_base_url}/billing/success"
            "?session_id={CHECKOUT_SESSION_ID}"
        ),
        "cancel_url": (
            f"{settings.app_base_url}/billing/cancel"
        ),
    }

    if tenant.stripe_customer_id:
        parameters["customer"] = tenant.stripe_customer_id
    elif tenant.email:
        parameters["customer_email"] = tenant.email

    client = StripeClient(settings.stripe_secret_key)

    try:
        session = client.v1.checkout.sessions.create(parameters)
    except stripe.StripeError as error:
        raise CheckoutCreationError(
            "Stripe could not create the Checkout Session"
        ) from error

    if not session.url:
        raise CheckoutCreationError(
            "Stripe returned a Checkout Session without a URL"
        )

    return CheckoutResponse(
        session_id=session.id,
        checkout_url=session.url,
    )