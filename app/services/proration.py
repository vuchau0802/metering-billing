from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import (
    FREE_MONTHLY_PRICE_MICROUSD,
    PRO_MONTHLY_PRICE_MICROUSD,
)
from app.models import BillingAdjustment, PlanName
from app.repositories import (
    billing_adjustments as adjustments_repository,
)
from app.services.quotas import current_utc_month

def _require_aware(
    value: datetime,
    *,
    name: str,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")

    return value.astimezone(timezone.utc)


def _whole_seconds(
    start: datetime,
    end: datetime,
) -> int:
    difference = end - start

    if difference.microseconds:
        raise ValueError("proration timestamps must use whole seconds")

    return difference.days * 86_400 + difference.seconds


def calculate_proration(
    *,
    old_monthly_price_microusd: int,
    new_monthly_price_microusd: int,
    period_start: datetime,
    period_end: datetime,
    effective_at: datetime,
) -> int:
    if old_monthly_price_microusd < 0:
        raise ValueError("old monthly price cannot be negative")

    if new_monthly_price_microusd < 0:
        raise ValueError("new monthly price cannot be negative")

    if new_monthly_price_microusd < old_monthly_price_microusd:
        raise ValueError("downgrade proration is not supported")

    start = _require_aware(
        period_start,
        name="period_start",
    )
    end = _require_aware(
        period_end,
        name="period_end",
    )
    effective = _require_aware(
        effective_at,
        name="effective_at",
    )

    period_seconds = _whole_seconds(start, end)

    if period_seconds <= 0:
        raise ValueError("period_end must be after period_start")

    if effective < start or effective > end:
        raise ValueError(
            "effective_at must be inside the billing period"
        )

    remaining_seconds = _whole_seconds(effective, end)
    price_difference = (
        new_monthly_price_microusd
        - old_monthly_price_microusd
    )
    numerator = price_difference * remaining_seconds

    return (
        numerator + period_seconds // 2
    ) // period_seconds

@dataclass(frozen=True)
class ProrationResult:
    adjustment: BillingAdjustment
    created: bool


def record_upgrade_proration(
    db: Session,
    *,
    tenant_id: int,
    source_event_id: str,
    old_plan: PlanName,
    new_plan: PlanName,
    effective_at: datetime,
) -> ProrationResult:
    if not source_event_id.strip():
        raise ValueError("source_event_id cannot be empty")

    if (
        old_plan != PlanName.FREE
        or new_plan != PlanName.PRO
    ):
        raise ValueError(
            "only Free-to-Pro proration is supported"
        )

    existing = adjustments_repository.get_by_source_event_id(
        db,
        source_event_id,
    )

    if existing is not None:
        return ProrationResult(
            adjustment=existing,
            created=False,
        )

    period = current_utc_month(effective_at)
    amount = calculate_proration(
        old_monthly_price_microusd=(
            FREE_MONTHLY_PRICE_MICROUSD
        ),
        new_monthly_price_microusd=(
            PRO_MONTHLY_PRICE_MICROUSD
        ),
        period_start=period.start,
        period_end=period.end,
        effective_at=effective_at,
    )

    adjustment = adjustments_repository.create_adjustment(
        db,
        tenant_id=tenant_id,
        source_event_id=source_event_id,
        old_plan=old_plan,
        new_plan=new_plan,
        period_start=period.start,
        period_end=period.end,
        effective_at=effective_at,
        old_monthly_price_microusd=(
            FREE_MONTHLY_PRICE_MICROUSD
        ),
        new_monthly_price_microusd=(
            PRO_MONTHLY_PRICE_MICROUSD
        ),
        amount_microusd=amount,
    )

    return ProrationResult(
        adjustment=adjustment,
        created=True,
    )