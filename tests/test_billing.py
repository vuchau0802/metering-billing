from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import Settings
from app.models import PlanName, TenantStatus
from app.services import billing
from app.services.quotas import QuotaWindow


def test_checkout_aligns_subscription_to_utc_month(
    monkeypatch,
) -> None:
    settings = Settings(
        _env_file=None,
        stripe_secret_key="sk_test_example",
        app_base_url="http://localhost:8004",
    )
    tenant = SimpleNamespace(
        id=123,
        status=TenantStatus.ACTIVE,
        plan=PlanName.FREE,
        stripe_customer_id=None,
        email="billing@example.com",
    )
    pro_plan = SimpleNamespace(
        stripe_price_id="price_test_pro",
    )
    period = QuotaWindow(
        start=datetime(2026, 10, 1, tzinfo=UTC),
        end=datetime(2026, 11, 1, tzinfo=UTC),
    )
    stripe_client = MagicMock()
    stripe_client.v1.checkout.sessions.create.return_value = (
        SimpleNamespace(
            id="cs_test_proration",
            url="https://checkout.stripe.test/session",
        )
    )
    stripe_client_class = MagicMock(
        return_value=stripe_client
    )

    monkeypatch.setattr(
        billing,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(
        billing.tenants_repository,
        "get_tenant_with_plan",
        lambda db, tenant_id: (tenant, pro_plan),
    )
    monkeypatch.setattr(
        billing.tenants_repository,
        "get_plan",
        lambda db, plan_name: pro_plan,
    )
    monkeypatch.setattr(
        billing,
        "current_utc_month",
        lambda: period,
    )
    monkeypatch.setattr(
        billing,
        "StripeClient",
        stripe_client_class,
    )

    response = billing.create_checkout_session(
        MagicMock(),
        tenant.id,
    )

    stripe_client_class.assert_called_once_with(
        "sk_test_example"
    )
    parameters = (
        stripe_client.v1.checkout.sessions.create
        .call_args.args[0]
    )

    assert parameters["subscription_data"] == {
        "billing_cycle_anchor": int(
            period.end.timestamp()
        ),
        "proration_behavior": "create_prorations",
        "metadata": {
            "tenant_id": "123",
            "plan": "pro",
        },
    }
    assert parameters["customer_email"] == (
        "billing@example.com"
    )
    assert response.session_id == "cs_test_proration"
