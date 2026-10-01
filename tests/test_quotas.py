from datetime import datetime, timezone

import pytest

from app.models import Plan, PlanName, UsageType
from app.services import quotas


def make_plan(
    *,
    overage_enabled: bool = False,
) -> Plan:
    return Plan(
        name=PlanName.FREE,
        api_calls_limit=10,
        ai_tokens_limit=100,
        overage_enabled=overage_enabled,
        stripe_price_id=None,
    )


def test_current_utc_month() -> None:
    window = quotas.current_utc_month(
        datetime(2026, 9, 15, 12, 30, tzinfo=timezone.utc)
    )

    assert window.start == datetime(
        2026, 9, 1, tzinfo=timezone.utc
    )
    assert window.end == datetime(
        2026, 10, 1, tzinfo=timezone.utc
    )


def test_december_rolls_into_next_year() -> None:
    window = quotas.current_utc_month(
        datetime(2026, 12, 31, tzinfo=timezone.utc)
    )

    assert window.start == datetime(
        2026, 12, 1, tzinfo=timezone.utc
    )
    assert window.end == datetime(
        2027, 1, 1, tzinfo=timezone.utc
    )


def test_exact_quota_limit_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(
        quotas.usage_events_repository,
        "get_usage_total",
        lambda *args, **kwargs: 90,
    )

    result = quotas.check_quota(
        object(),
        tenant_id=1,
        plan=make_plan(),
        usage_type=UsageType.AI_TOKENS,
        requested=10,
    )

    assert result.used == 100
    assert result.limit == 100
    assert result.remaining == 0
    assert result.overage == 0
    assert result.new_overage == 0

def test_request_past_quota_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        quotas.usage_events_repository,
        "get_usage_total",
        lambda *args, **kwargs: 90,
    )

    with pytest.raises(quotas.QuotaExceededError) as error:
        quotas.check_quota(
            object(),
            tenant_id=1,
            plan=make_plan(),
            usage_type=UsageType.AI_TOKENS,
            requested=11,
        )

    assert error.value.used == 90
    assert error.value.requested == 11
    assert error.value.limit == 100


def test_api_calls_use_api_call_limit(monkeypatch) -> None:
    monkeypatch.setattr(
        quotas.usage_events_repository,
        "get_usage_total",
        lambda *args, **kwargs: 7,
    )

    result = quotas.check_quota(
        object(),
        tenant_id=1,
        plan=make_plan(),
        usage_type=UsageType.API_CALL,
        requested=2,
    )

    assert result.used == 9
    assert result.limit == 10
    assert result.remaining == 1
    assert result.overage == 0
    assert result.new_overage == 0

def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="timezone information",
    ):
        quotas.current_utc_month(datetime(2026, 9, 15))

def test_overage_enabled_plan_accepts_usage_past_limit(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        quotas.usage_events_repository,
        "get_usage_total",
        lambda *args, **kwargs: 90,
    )

    result = quotas.check_quota(
        object(),
        tenant_id=1,
        plan=make_plan(overage_enabled=True),
        usage_type=UsageType.AI_TOKENS,
        requested=25,
    )

    assert result.used == 115
    assert result.limit == 100
    assert result.remaining == 0
    assert result.overage == 15
    assert result.new_overage == 15


def test_existing_overage_charges_only_new_units(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        quotas.usage_events_repository,
        "get_usage_total",
        lambda *args, **kwargs: 110,
    )

    result = quotas.check_quota(
        object(),
        tenant_id=1,
        plan=make_plan(overage_enabled=True),
        usage_type=UsageType.AI_TOKENS,
        requested=5,
    )

    assert result.used == 115
    assert result.overage == 15
    assert result.new_overage == 5