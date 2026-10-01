from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Plan, UsageType
from app.repositories import usage_events as usage_events_repository


@dataclass(frozen=True)
class QuotaWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class QuotaResult:
    used: int
    limit: int
    remaining: int
    overage: int
    new_overage: int
    window: QuotaWindow


class QuotaExceededError(Exception):
    def __init__(
        self,
        *,
        usage_type: UsageType,
        used: int,
        limit: int,
        requested: int,
        resets_at: datetime,
    ) -> None:
        self.usage_type = usage_type
        self.used = used
        self.limit = limit
        self.requested = requested
        self.resets_at = resets_at

        super().__init__(
            f"{usage_type.value} quota exceeded: "
            f"used={used}, requested={requested}, limit={limit}"
        )


def current_utc_month(
    now: datetime | None = None,
) -> QuotaWindow:
    current = now or datetime.now(timezone.utc)

    if current.tzinfo is None:
        raise ValueError("now must include timezone information")

    current = current.astimezone(timezone.utc)

    start = datetime(
        current.year,
        current.month,
        1,
        tzinfo=timezone.utc,
    )

    if current.month == 12:
        end = datetime(
            current.year + 1,
            1,
            1,
            tzinfo=timezone.utc,
        )
    else:
        end = datetime(
            current.year,
            current.month + 1,
            1,
            tzinfo=timezone.utc,
        )

    return QuotaWindow(start=start, end=end)


def get_usage_limit(
    plan: Plan,
    usage_type: UsageType,
) -> int:
    if usage_type == UsageType.API_CALL:
        return plan.api_calls_limit

    if usage_type == UsageType.AI_TOKENS:
        return plan.ai_tokens_limit

    raise ValueError(f"Unsupported usage type: {usage_type}")


def check_quota(
    db: Session,
    *,
    tenant_id: int,
    plan: Plan,
    usage_type: UsageType,
    requested: int,
    now: datetime | None = None,
) -> QuotaResult:
    if requested < 0:
        raise ValueError("requested usage must be non-negative")

    window = current_utc_month(now)
    limit = get_usage_limit(plan, usage_type)

    used = usage_events_repository.get_usage_total(
        db,
        tenant_id=tenant_id,
        usage_type=usage_type,
        window_start=window.start,
        window_end=window.end,
    )

    new_used = used + requested
    overage_before = max(0, used - limit)
    overage_after = max(0, new_used - limit)
    new_overage = overage_after - overage_before

    if new_overage > 0 and not plan.overage_enabled:
        raise QuotaExceededError(
            usage_type=usage_type,
            used=used,
            limit=limit,
            requested=requested,
            resets_at=window.end,
        )

    return QuotaResult(
        used=new_used,
        limit=limit,
        remaining=max(0, limit - new_used),
        overage=overage_after,
        new_overage=new_overage,
        window=window,
    )