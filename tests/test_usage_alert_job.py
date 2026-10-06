from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.jobs.send_usage_alerts import (
    AlertDeliveryResult,
    run_alert_delivery,
)
from app.models import (
    Plan,
    PlanName,
    Tenant,
    TenantStatus,
    UsageAlert,
    UsageType,
)


TENANT_ID = 910_001
TENANT_EMAIL = "alerts@example.com"
WINDOW_START = datetime(2026, 10, 1, tzinfo=UTC)
WINDOW_END = datetime(2026, 11, 1, tzinfo=UTC)


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, int]] = []

    def send(
        self,
        *,
        recipient: str,
        alert: UsageAlert,
    ) -> None:
        self.sent.append((recipient, alert.id))


class FailingNotifier:
    def send(
        self,
        *,
        recipient: str,
        alert: UsageAlert,
    ) -> None:
        raise RuntimeError("email provider unavailable")


def clean_test_data() -> None:
    with SessionLocal() as db:
        db.execute(
            delete(UsageAlert).where(
                UsageAlert.tenant_id == TENANT_ID
            )
        )
        db.execute(
            delete(Tenant).where(Tenant.id == TENANT_ID)
        )
        db.commit()


@pytest.fixture(autouse=True)
def clean_alert_job_data():
    clean_test_data()
    yield
    clean_test_data()


def seed_alerts(
    *,
    email: str | None = TENANT_EMAIL,
    thresholds: tuple[int, ...] = (80,),
    attempts: int = 0,
) -> list[int]:
    with SessionLocal() as db:
        plan = db.get(Plan, PlanName.FREE)

        if plan is None:
            plan = Plan(
                name=PlanName.FREE,
                api_calls_limit=1_000,
                ai_tokens_limit=100_000,
                overage_enabled=False,
                stripe_price_id=None,
            )
            db.add(plan)
            db.flush()

        db.add(
            Tenant(
                id=TENANT_ID,
                email=email,
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.flush()

        alerts = [
            UsageAlert(
                tenant_id=TENANT_ID,
                usage_type=UsageType.AI_TOKENS,
                window_start=WINDOW_START,
                window_end=WINDOW_END,
                threshold_percent=threshold,
                used=threshold * 1_000,
                limit=100_000,
                status="pending",
                attempts=attempts,
            )
            for threshold in thresholds
        ]

        db.add_all(alerts)
        db.commit()

        return [alert.id for alert in alerts]


def test_worker_delivers_pending_alert() -> None:
    alert_id = seed_alerts()[0]
    notifier = RecordingNotifier()

    result = run_alert_delivery(notifier=notifier)

    assert result == AlertDeliveryResult(
        checked=1,
        delivered=1,
        retrying=0,
        failed=0,
    )
    assert notifier.sent == [(TENANT_EMAIL, alert_id)]

    with SessionLocal() as db:
        alert = db.get(UsageAlert, alert_id)

        assert alert is not None
        assert alert.status == "delivered"
        assert alert.attempts == 1
        assert alert.delivered_at is not None
        assert alert.last_error is None


def test_worker_keeps_retryable_failure_pending() -> None:
    alert_id = seed_alerts()[0]

    result = run_alert_delivery(
        notifier=FailingNotifier(),
        max_attempts=3,
    )

    assert result == AlertDeliveryResult(
        checked=1,
        delivered=0,
        retrying=1,
        failed=0,
    )

    with SessionLocal() as db:
        alert = db.get(UsageAlert, alert_id)

        assert alert is not None
        assert alert.status == "pending"
        assert alert.attempts == 1
        assert alert.last_error == "email provider unavailable"


def test_worker_marks_terminal_failure() -> None:
    alert_id = seed_alerts(attempts=2)[0]

    result = run_alert_delivery(
        notifier=FailingNotifier(),
        max_attempts=3,
    )

    assert result.failed == 1
    assert result.retrying == 0

    with SessionLocal() as db:
        alert = db.get(UsageAlert, alert_id)

        assert alert is not None
        assert alert.status == "failed"
        assert alert.attempts == 3


def test_worker_handles_missing_email() -> None:
    alert_id = seed_alerts(email=None)[0]
    notifier = RecordingNotifier()

    result = run_alert_delivery(
        notifier=notifier,
        max_attempts=3,
    )

    assert result.retrying == 1
    assert notifier.sent == []

    with SessionLocal() as db:
        alert = db.get(UsageAlert, alert_id)

        assert alert is not None
        assert alert.status == "pending"
        assert alert.attempts == 1
        assert alert.last_error == (
            f"Tenant {TENANT_ID} has no email address"
        )


def test_worker_respects_batch_limit() -> None:
    seed_alerts(thresholds=(80, 100))
    notifier = RecordingNotifier()

    result = run_alert_delivery(
        notifier=notifier,
        max_alerts=1,
    )

    assert result.checked == 1
    assert result.delivered == 1

    with SessionLocal() as db:
        statuses = list(
            db.scalars(
                select(UsageAlert.status).where(
                    UsageAlert.tenant_id == TENANT_ID
                )
            )
        )

    assert statuses.count("delivered") == 1
    assert statuses.count("pending") == 1