from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UsageAlert, UsageType


def create_threshold_alerts(
    db: Session,
    *,
    tenant_id: int,
    usage_type: UsageType,
    window_start: datetime,
    window_end: datetime,
    used: int,
    limit: int,
    thresholds: list[int],
) -> list[UsageAlert]:
    alerts = [
        UsageAlert(
            tenant_id=tenant_id,
            usage_type=usage_type,
            window_start=window_start,
            window_end=window_end,
            threshold_percent=threshold,
            used=used,
            limit=limit,
        )
        for threshold in thresholds
    ]

    db.add_all(alerts)

    return alerts

def get_next_pending_alert(
    db: Session,
    *,
    exclude_ids: set[int] | None = None,
) -> UsageAlert | None:
    statement = select(UsageAlert).where(
        UsageAlert.status == "pending"
    )

    if exclude_ids:
        statement = statement.where(
            UsageAlert.id.not_in(exclude_ids)
        )

    statement = (
        statement
        .order_by(
            UsageAlert.created_at,
            UsageAlert.id,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    return db.scalar(statement)


def mark_alert_delivered(
    alert: UsageAlert,
) -> None:
    alert.attempts += 1
    alert.status = "delivered"
    alert.delivered_at = datetime.now(UTC)
    alert.last_error = None


def record_alert_failure(
    alert: UsageAlert,
    error: Exception,
    *,
    max_attempts: int,
) -> None:
    alert.attempts += 1
    alert.last_error = str(error)[:2_000]

    if alert.attempts >= max_attempts:
        alert.status = "failed"