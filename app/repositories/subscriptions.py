from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanName,
    Subscription,
    SubscriptionStatus,
)


def get_by_stripe_id(
    db: Session,
    stripe_subscription_id: str,
) -> Subscription | None:
    statement = select(Subscription).where(
        Subscription.stripe_subscription_id
        == stripe_subscription_id
    )

    return db.scalar(statement)


def upsert_subscription(
    db: Session,
    *,
    tenant_id: int,
    stripe_subscription_id: str,
    stripe_customer_id: str,
    plan_name: PlanName,
    status: SubscriptionStatus,
    current_period_start: datetime | None,
    current_period_end: datetime | None,
    cancel_at_period_end: bool,
) -> Subscription:
    subscription = get_by_stripe_id(
        db,
        stripe_subscription_id,
    )

    if subscription is None:
        subscription = Subscription(
            tenant_id=tenant_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_customer_id=stripe_customer_id,
            plan_name=plan_name,
            status=status,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        db.add(subscription)
    else:
        subscription.tenant_id = tenant_id
        subscription.stripe_customer_id = stripe_customer_id
        subscription.plan_name = plan_name
        subscription.status = status
        subscription.current_period_start = current_period_start
        subscription.current_period_end = current_period_end
        subscription.cancel_at_period_end = cancel_at_period_end

    return subscription

def list_reconcilable_ids(
    db: Session,
) -> list[str]:
    statement = (
        select(Subscription.stripe_subscription_id)
        .where(
            Subscription.status
            != SubscriptionStatus.CANCELED
        )
        .order_by(Subscription.id)
    )

    return list(db.scalars(statement))