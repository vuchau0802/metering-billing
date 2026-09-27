from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import UsageEvent, UsageType
from typing import Any

def get_usage_total(
    db: Session,
    *,
    tenant_id: int,
    usage_type: UsageType,
    window_start: datetime,
    window_end: datetime,
) -> int:
    statement = select(
        func.coalesce(func.sum(UsageEvent.quantity), 0)
    ).where(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.usage_type == usage_type,
        UsageEvent.created_at >= window_start,
        UsageEvent.created_at < window_end,
    )

    total = db.scalar(statement)

    return int(total or 0)

def get_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> UsageEvent | None:
    statement = select(UsageEvent).where(
        UsageEvent.idempotency_key == idempotency_key
    )

    return db.scalar(statement)


def create_usage_event(
    db: Session,
    *,
    tenant_id: int,
    idempotency_key: str,
    usage_type: UsageType,
    quantity: int,
    token_breakdown: dict[str, int] | None,
    cost_microusd: int,
    response_snapshot: dict[str, Any],
) -> UsageEvent:
    event = UsageEvent(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        usage_type=usage_type,
        quantity=quantity,
        token_breakdown=token_breakdown,
        cost_microusd=cost_microusd,
        response_snapshot=response_snapshot,
    )

    db.add(event)
    db.flush()

    return event

def get_usage_rollup(
    db: Session,
    *,
    tenant_id: int,
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict[UsageType, int], int]:
    statement = (
        select(
            UsageEvent.usage_type,
            func.sum(UsageEvent.quantity),
            func.sum(UsageEvent.cost_microusd),
        )
        .where(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.created_at >= window_start,
            UsageEvent.created_at < window_end,
        )
        .group_by(UsageEvent.usage_type)
    )

    totals = {
        UsageType.API_CALL: 0,
        UsageType.AI_TOKENS: 0,
    }
    total_cost_microusd = 0

    for usage_type, quantity, cost in db.execute(statement):
        totals[usage_type] = int(quantity or 0)
        total_cost_microusd += int(cost or 0)

    return totals, total_cost_microusd