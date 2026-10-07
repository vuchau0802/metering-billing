from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice, InvoiceLine, UsageEvent, UsageType


@dataclass(frozen=True)
class UsageLineAggregate:
    usage_type: UsageType
    event_count: int
    quantity: int
    overage_quantity: int
    subtotal_microusd: int
    overage_cost_microusd: int
    total_microusd: int


def get_for_period(
    db: Session,
    *,
    tenant_id: int,
    period_start: datetime,
    period_end: datetime,
) -> Invoice | None:
    statement = select(Invoice).where(
        Invoice.tenant_id == tenant_id,
        Invoice.period_start == period_start,
        Invoice.period_end == period_end,
    )

    return db.scalar(statement)


def aggregate_usage_lines(
    db: Session,
    *,
    tenant_id: int,
    period_start: datetime,
    period_end: datetime,
) -> list[UsageLineAggregate]:
    statement = (
        select(
            UsageEvent.usage_type,
            func.count(UsageEvent.id),
            func.sum(UsageEvent.quantity),
            func.sum(UsageEvent.overage_quantity),
            func.sum(
                UsageEvent.cost_microusd
                - UsageEvent.overage_cost_microusd
            ),
            func.sum(UsageEvent.overage_cost_microusd),
            func.sum(UsageEvent.cost_microusd),
        )
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= period_start,
            UsageEvent.created_at < period_end,
        )
        .group_by(UsageEvent.usage_type)
        .order_by(UsageEvent.usage_type)
    )

    return [
        UsageLineAggregate(
            usage_type=usage_type,
            event_count=int(event_count),
            quantity=int(quantity),
            overage_quantity=int(overage_quantity),
            subtotal_microusd=int(subtotal),
            overage_cost_microusd=int(overage_cost),
            total_microusd=int(total),
        )
        for (
            usage_type,
            event_count,
            quantity,
            overage_quantity,
            subtotal,
            overage_cost,
            total,
        ) in db.execute(statement)
    ]


def create_finalized_invoice(
    db: Session,
    *,
    tenant_id: int,
    period_start: datetime,
    period_end: datetime,
    aggregates: list[UsageLineAggregate],
) -> Invoice:
    subtotal = sum(
        item.subtotal_microusd for item in aggregates
    )
    overage_cost = sum(
        item.overage_cost_microusd for item in aggregates
    )
    total = sum(item.total_microusd for item in aggregates)

    invoice = Invoice(
        tenant_id=tenant_id,
        period_start=period_start,
        period_end=period_end,
        status="finalized",
        currency="usd",
        subtotal_microusd=subtotal,
        overage_cost_microusd=overage_cost,
        total_microusd=total,
    )
    db.add(invoice)
    db.flush()

    descriptions = {
        UsageType.API_CALL: "API calls",
        UsageType.AI_TOKENS: "AI tokens",
    }

    db.add_all(
        [
            InvoiceLine(
                invoice_id=invoice.id,
                usage_type=item.usage_type,
                description=descriptions[item.usage_type],
                event_count=item.event_count,
                quantity=item.quantity,
                overage_quantity=item.overage_quantity,
                subtotal_microusd=item.subtotal_microusd,
                overage_cost_microusd=(
                    item.overage_cost_microusd
                ),
                total_microusd=item.total_microusd,
            )
            for item in aggregates
        ]
    )
    db.flush()

    return invoice


def list_for_tenant(
    db: Session,
    tenant_id: int,
) -> list[Invoice]:
    statement = (
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.period_start.desc())
    )

    return list(db.scalars(statement))


def get_for_tenant(
    db: Session,
    *,
    invoice_id: int,
    tenant_id: int,
) -> Invoice | None:
    statement = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.tenant_id == tenant_id,
    )

    return db.scalar(statement)


def list_lines(
    db: Session,
    invoice_id: int,
) -> list[InvoiceLine]:
    statement = (
        select(InvoiceLine)
        .where(InvoiceLine.invoice_id == invoice_id)
        .order_by(InvoiceLine.usage_type)
    )

    return list(db.scalars(statement))
