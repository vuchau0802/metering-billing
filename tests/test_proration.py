from datetime import UTC, datetime

import pytest

from app.services.proration import calculate_proration
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import (
    BillingAdjustment,
    PlanName,
    Tenant,
    TenantStatus,
)
from app.services.proration import (
    calculate_proration,
    record_upgrade_proration,
)


START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)
PRO_PRICE = 10_000_000
TENANT_ID = 940_001

@pytest.mark.parametrize(
    ("effective_at", "expected"),
    [
        (START, 10_000_000),
        (datetime(2026, 10, 16, 12, tzinfo=UTC), 5_000_000),
        (datetime(2026, 10, 31, 23, 59, 59, tzinfo=UTC), 4),
        (END, 0),
    ],
)
def test_proration_boundaries(
    effective_at: datetime,
    expected: int,
) -> None:
    assert calculate_proration(
        old_monthly_price_microusd=0,
        new_monthly_price_microusd=PRO_PRICE,
        period_start=START,
        period_end=END,
        effective_at=effective_at,
    ) == expected


def test_proration_rejects_downgrade() -> None:
    with pytest.raises(
        ValueError,
        match="downgrade proration is not supported",
    ):
        calculate_proration(
            old_monthly_price_microusd=PRO_PRICE,
            new_monthly_price_microusd=0,
            period_start=START,
            period_end=END,
            effective_at=START,
        )


def test_proration_rejects_outside_period() -> None:
    with pytest.raises(
        ValueError,
        match="effective_at must be inside",
    ):
        calculate_proration(
            old_monthly_price_microusd=0,
            new_monthly_price_microusd=PRO_PRICE,
            period_start=START,
            period_end=END,
            effective_at=datetime(2026, 11, 2, tzinfo=UTC),
        )

def clean_adjustment_test_data() -> None:
    with SessionLocal() as db:
        db.execute(
            delete(BillingAdjustment).where(
                BillingAdjustment.tenant_id == TENANT_ID
            )
        )
        db.execute(
            delete(Tenant).where(Tenant.id == TENANT_ID)
        )
        db.commit()


@pytest.fixture
def adjustment_tenant():
    clean_adjustment_test_data()

    with SessionLocal() as db:
        db.add(
            Tenant(
                id=TENANT_ID,
                email="proration@example.com",
                plan=PlanName.FREE,
                status=TenantStatus.ACTIVE,
            )
        )
        db.commit()

    yield
    clean_adjustment_test_data()


def test_midpoint_upgrade_creates_adjustment(
    adjustment_tenant,
) -> None:
    effective_at = datetime(
        2026,
        10,
        16,
        12,
        tzinfo=UTC,
    )

    with SessionLocal() as db:
        result = record_upgrade_proration(
            db,
            tenant_id=TENANT_ID,
            source_event_id="evt_proration_midpoint",
            old_plan=PlanName.FREE,
            new_plan=PlanName.PRO,
            effective_at=effective_at,
        )
        db.commit()
        adjustment_id = result.adjustment.id

    with SessionLocal() as db:
        adjustment = db.get(
            BillingAdjustment,
            adjustment_id,
        )

        assert adjustment is not None
        assert adjustment.old_plan == PlanName.FREE
        assert adjustment.new_plan == PlanName.PRO
        assert adjustment.period_start == START
        assert adjustment.period_end == END
        assert adjustment.effective_at == effective_at
        assert adjustment.old_monthly_price_microusd == 0
        assert (
            adjustment.new_monthly_price_microusd
            == 10_000_000
        )
        assert adjustment.amount_microusd == 5_000_000
        assert adjustment.invoice_id is None
        assert result.created is True


def test_replayed_event_returns_original_adjustment(
    adjustment_tenant,
) -> None:
    with SessionLocal() as db:
        first = record_upgrade_proration(
            db,
            tenant_id=TENANT_ID,
            source_event_id="evt_proration_replay",
            old_plan=PlanName.FREE,
            new_plan=PlanName.PRO,
            effective_at=START,
        )
        second = record_upgrade_proration(
            db,
            tenant_id=TENANT_ID,
            source_event_id="evt_proration_replay",
            old_plan=PlanName.FREE,
            new_plan=PlanName.PRO,
            effective_at=START,
        )
        db.commit()

        count = db.scalar(
            select(func.count())
            .select_from(BillingAdjustment)
            .where(
                BillingAdjustment.source_event_id
                == "evt_proration_replay"
            )
        )

    assert first.created is True
    assert second.created is False
    assert first.adjustment.id == second.adjustment.id
    assert count == 1


def test_unsupported_transition_creates_nothing(
    adjustment_tenant,
) -> None:
    with SessionLocal() as db:
        with pytest.raises(
            ValueError,
            match="only Free-to-Pro proration",
        ):
            record_upgrade_proration(
                db,
                tenant_id=TENANT_ID,
                source_event_id="evt_proration_downgrade",
                old_plan=PlanName.PRO,
                new_plan=PlanName.FREE,
                effective_at=START,
            )

        count = db.scalar(
            select(func.count())
            .select_from(BillingAdjustment)
            .where(
                BillingAdjustment.tenant_id == TENANT_ID
            )
        )

    assert count == 0