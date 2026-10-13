"""add database integrity constraints

Revision ID: 3951f5f996c7
Revises: 6f5d232a275d
Create Date: 2026-10-12 22:05:24.555741

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3951f5f996c7"
down_revision: Union[str, None] = "6f5d232a275d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECK_CONSTRAINTS = [
    (
        "plans",
        "ck_plans_api_calls_limit_positive",
        "api_calls_limit > 0",
    ),
    (
        "plans",
        "ck_plans_ai_tokens_limit_positive",
        "ai_tokens_limit > 0",
    ),
    (
        "subscriptions",
        "ck_subscriptions_valid_period",
        """
        (
            current_period_start IS NULL
            AND current_period_end IS NULL
        )
        OR
        (
            current_period_start IS NOT NULL
            AND current_period_end IS NOT NULL
            AND current_period_end > current_period_start
        )
        """,
    ),
    (
        "subscriptions",
        "ck_subscriptions_event_created_nonnegative",
        "last_stripe_event_created >= 0",
    ),
    (
        "usage_events",
        "ck_usage_events_quantity_positive",
        "quantity > 0",
    ),
    (
        "usage_events",
        "ck_usage_events_valid_overage_quantity",
        "overage_quantity >= 0 AND overage_quantity <= quantity",
    ),
    (
        "usage_events",
        "ck_usage_events_overage_cost_nonnegative",
        "overage_cost_microusd >= 0",
    ),
    (
        "usage_events",
        "ck_usage_events_valid_cost",
        "cost_microusd >= overage_cost_microusd",
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_valid_window",
        "window_end > window_start",
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_supported_threshold",
        "threshold_percent IN (80, 100)",
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_used_nonnegative",
        "used >= 0",
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_limit_positive",
        '"limit" > 0',
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_attempts_nonnegative",
        "attempts >= 0",
    ),
    (
        "usage_alerts",
        "ck_usage_alerts_supported_status",
        "status IN ('pending', 'delivered', 'failed')",
    ),
    (
        "invoices",
        "ck_invoices_valid_period",
        "period_end > period_start",
    ),
    (
        "invoices",
        "ck_invoices_supported_currency",
        "currency = 'usd'",
    ),
    (
        "invoices",
        "ck_invoices_subtotal_nonnegative",
        "subtotal_microusd >= 0",
    ),
    (
        "invoices",
        "ck_invoices_overage_cost_nonnegative",
        "overage_cost_microusd >= 0",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_event_count_positive",
        "event_count > 0",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_quantity_positive",
        "quantity > 0",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_valid_overage_quantity",
        "overage_quantity >= 0 AND overage_quantity <= quantity",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_subtotal_nonnegative",
        "subtotal_microusd >= 0",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_overage_cost_nonnegative",
        "overage_cost_microusd >= 0",
    ),
    (
        "invoice_lines",
        "ck_invoice_lines_valid_total",
        "total_microusd = subtotal_microusd + overage_cost_microusd",
    ),
    (
        "billing_adjustments",
        "ck_billing_adjustments_valid_period",
        "period_end > period_start",
    ),
    (
        "billing_adjustments",
        "ck_billing_adjustments_effective_in_period",
        "effective_at >= period_start AND effective_at < period_end",
    ),
    (
        "billing_adjustments",
        "ck_billing_adjustments_old_price_nonnegative",
        "old_monthly_price_microusd >= 0",
    ),
    (
        "billing_adjustments",
        "ck_billing_adjustments_new_price_nonnegative",
        "new_monthly_price_microusd >= 0",
    ),
    (
        "billing_adjustments",
        "ck_billing_adjustments_supported_currency",
        "currency = 'usd'",
    ),
]


def upgrade() -> None:
    for table_name, constraint_name, condition in CHECK_CONSTRAINTS:
        op.create_check_constraint(
            constraint_name,
            table_name,
            condition,
        )


def downgrade() -> None:
    for table_name, constraint_name, _ in reversed(CHECK_CONSTRAINTS):
        op.drop_constraint(
            constraint_name,
            table_name,
            type_="check",
        )
