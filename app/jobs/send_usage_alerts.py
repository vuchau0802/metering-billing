import logging
from dataclasses import dataclass

from app.db import SessionLocal
from app.models import Tenant
from app.repositories import usage_alerts
from app.services.notifications import (
    UsageAlertNotifier,
    build_usage_alert_notifier,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertDeliveryResult:
    checked: int
    delivered: int
    retrying: int
    failed: int


def run_alert_delivery(
    *,
    notifier: UsageAlertNotifier | None = None,
    max_alerts: int = 100,
    max_attempts: int = 3,
) -> AlertDeliveryResult:
    if max_alerts < 1:
        raise ValueError("max_alerts must be at least 1")

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    if notifier is None:
        notifier = build_usage_alert_notifier()

    processed_ids: set[int] = set()
    delivered = 0
    retrying = 0
    failed = 0

    with SessionLocal() as db:
        while len(processed_ids) < max_alerts:
            alert = usage_alerts.get_next_pending_alert(
                db,
                exclude_ids=processed_ids,
            )

            if alert is None:
                break

            processed_ids.add(alert.id)
            tenant = db.get(Tenant, alert.tenant_id)

            try:
                if tenant is None:
                    raise ValueError(
                        f"Tenant {alert.tenant_id} was not found"
                    )

                if not tenant.email:
                    raise ValueError(
                        f"Tenant {tenant.id} has no email address"
                    )

                notifier.send(
                    recipient=tenant.email,
                    alert=alert,
                )
                usage_alerts.mark_alert_delivered(alert)
                delivered += 1
            except Exception as error:
                usage_alerts.record_alert_failure(
                    alert,
                    error,
                    max_attempts=max_attempts,
                )

                if alert.status == "failed":
                    failed += 1
                else:
                    retrying += 1

                logger.exception(
                    "Usage alert delivery failed: alert_id=%s",
                    alert.id,
                )

            db.commit()

    return AlertDeliveryResult(
        checked=len(processed_ids),
        delivered=delivered,
        retrying=retrying,
        failed=failed,
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s "
            "%(name)s %(message)s"
        ),
    )

    try:
        result = run_alert_delivery()
    except Exception:
        logger.exception(
            "USAGE_ALERT_JOB_FAILED before completion"
        )
        return 1

    logger.info(
        "Usage alert delivery complete: checked=%s "
        "delivered=%s retrying=%s failed=%s",
        result.checked,
        result.delivered,
        result.retrying,
        result.failed,
    )

    return 1 if result.retrying or result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
