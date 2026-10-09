from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingAdjustment, PlanName


def get_by_source_event_id(
    db: Session,
    source_event_id: str,
) -> BillingAdjustment | None:
    statement = select(BillingAdjustment).where(
        BillingAdjustment.source_event_id == source_event_id
    )

    return db.scalar(statement)


def create_adjustment(
    db: Session,
    *,
    tenant_id: int,
    source_event_id: str,
    old_plan: PlanName,
    new_plan: PlanName,
    period_start: datetime,
    period_end: datetime,
    effective_at: datetime,
    old_monthly_price_microusd: int,
    new_monthly_price_microusd: int,
    amount_microusd: int,
) -> BillingAdjustment:
    adjustment = BillingAdjustment(
        tenant_id=tenant_id,
        source_event_id=source_event_id,
        old_plan=old_plan,
        new_plan=new_plan,
        period_start=period_start,
        period_end=period_end,
        effective_at=effective_at,
        old_monthly_price_microusd=(
            old_monthly_price_microusd
        ),
        new_monthly_price_microusd=(
            new_monthly_price_microusd
        ),
        amount_microusd=amount_microusd,
        currency="usd",
    )

    db.add(adjustment)
    db.flush()

    return adjustment

def list_uninvoiced_for_statement(
    db: Session,
    *,
    tenant_id: int,
    period_end: datetime,
) -> list[BillingAdjustment]:
    statement = (
        select(BillingAdjustment)
        .where(
            BillingAdjustment.tenant_id == tenant_id,
            BillingAdjustment.invoice_id.is_(None),
            BillingAdjustment.effective_at < period_end,
        )
        .order_by(
            BillingAdjustment.effective_at,
            BillingAdjustment.id,
        )
        .with_for_update()
    )

    return list(db.scalars(statement))


def attach_to_invoice(
    adjustments: list[BillingAdjustment],
    *,
    invoice_id: int,
) -> None:
    for adjustment in adjustments:
        adjustment.invoice_id = invoice_id


def list_for_invoice(
    db: Session,
    invoice_id: int,
) -> list[BillingAdjustment]:
    statement = (
        select(BillingAdjustment)
        .where(
            BillingAdjustment.invoice_id == invoice_id
        )
        .order_by(
            BillingAdjustment.effective_at,
            BillingAdjustment.id,
        )
    )

    return list(db.scalars(statement))