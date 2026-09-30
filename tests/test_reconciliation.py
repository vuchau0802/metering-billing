import logging
from types import SimpleNamespace
from typing import Any

import pytest

import app.jobs.reconcile_subscriptions as reconciliation


class FakeSession:
    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(
        self,
        exception_type: Any,
        exception: Any,
        traceback: Any,
    ) -> None:
        pass

    def commit(self) -> None:
        pass


class FakeStripeSubscription:
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": "sub_test_reconciliation",
            "object": "subscription",
            "customer": "cus_test_reconciliation",
            "status": "active",
            "metadata": {
                "tenant_id": "1",
            },
            "items": {
                "data": [],
            },
            "cancel_at_period_end": False,
        }


class FakeSubscriptionsService:
    def __init__(
        self,
        outcomes: list[Any],
    ) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def retrieve(
        self,
        stripe_subscription_id: str,
    ) -> Any:
        outcome = self.outcomes[self.calls]
        self.calls += 1

        if isinstance(outcome, Exception):
            raise outcome

        return outcome


def build_client(
    service: FakeSubscriptionsService,
) -> Any:
    return SimpleNamespace(
        v1=SimpleNamespace(
            subscriptions=service,
        )
    )


def prepare_job(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    synchronized: list[dict[str, Any]] = []

    monkeypatch.setattr(
        reconciliation,
        "SessionLocal",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        reconciliation.subscriptions,
        "list_reconcilable_ids",
        lambda db: ["sub_test_reconciliation"],
    )
    monkeypatch.setattr(
        reconciliation,
        "synchronize_subscription",
        lambda db, payload: synchronized.append(
            payload
        ),
    )

    return synchronized


def test_transient_failure_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synchronized = prepare_job(monkeypatch)
    service = FakeSubscriptionsService(
        [
            RuntimeError("temporary Stripe failure"),
            FakeStripeSubscription(),
        ]
    )
    delays: list[float] = []

    result = reconciliation.run_reconciliation(
        client=build_client(service),
        max_attempts=3,
        base_delay_seconds=0.25,
        sleep=delays.append,
    )

    assert result == reconciliation.ReconciliationResult(
        checked=1,
        succeeded=1,
        failed=0,
    )
    assert service.calls == 2
    assert delays == [0.25]
    assert len(synchronized) == 1


def test_persistent_failure_stops_after_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synchronized = prepare_job(monkeypatch)
    service = FakeSubscriptionsService(
        [
            RuntimeError("Stripe unavailable"),
            RuntimeError("Stripe unavailable"),
            RuntimeError("Stripe unavailable"),
        ]
    )
    delays: list[float] = []

    result = reconciliation.run_reconciliation(
        client=build_client(service),
        max_attempts=3,
        base_delay_seconds=0.5,
        sleep=delays.append,
    )

    assert result == reconciliation.ReconciliationResult(
        checked=1,
        succeeded=0,
        failed=1,
    )
    assert service.calls == 3
    assert delays == [0.5, 1.0]
    assert synchronized == []


def test_main_emits_alert_and_returns_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        reconciliation,
        "run_reconciliation",
        lambda: reconciliation.ReconciliationResult(
            checked=2,
            succeeded=1,
            failed=1,
        ),
    )
    caplog.set_level(
        logging.CRITICAL,
        logger=reconciliation.__name__,
    )

    exit_code = reconciliation.main()

    assert exit_code == 1
    assert "RECONCILIATION_ALERT" in caplog.text