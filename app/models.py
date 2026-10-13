from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PlanName(str, Enum):
    FREE = "free"
    PRO = "pro"


class TenantStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"
    TRIALING = "trialing"


class UsageType(str, Enum):
    API_CALL = "api_call"
    AI_TOKENS = "ai_tokens"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [item.value for item in enum_class]

plan_name_type = SqlEnum(
    PlanName,
    name="plan_name",
    values_callable=enum_values,
)

tenant_status_type = SqlEnum(
    TenantStatus,
    name="tenant_status",
    values_callable=enum_values,
)

subscription_status_type = SqlEnum(
    SubscriptionStatus,
    name="subscription_status",
    values_callable=enum_values,
)

usage_type_enum = SqlEnum(
    UsageType,
    name="usage_type",
    values_callable=enum_values,
)

class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint(
            "api_calls_limit > 0",
            name="ck_plans_api_calls_limit_positive",
        ),
        CheckConstraint(
            "ai_tokens_limit > 0",
            name="ck_plans_ai_tokens_limit_positive",
        ),
    )

    name: Mapped[PlanName] = mapped_column(plan_name_type, primary_key=True)
    api_calls_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_tokens_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    overage_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    stripe_price_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    supabase_user_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    plan: Mapped[PlanName] = mapped_column(
        plan_name_type,
        ForeignKey("plans.name"),
        nullable=False,
    )
    status: Mapped[TenantStatus] = mapped_column(
        tenant_status_type,
        nullable=False,
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
    )
    api_key_hash: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
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
            name="ck_subscriptions_valid_period",
        ),
        CheckConstraint(
            "last_stripe_event_created >= 0",
            name="ck_subscriptions_event_created_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    stripe_subscription_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    stripe_customer_id: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )
    plan_name: Mapped[PlanName] = mapped_column(
        plan_name_type,
        ForeignKey("plans.name"),
        nullable=False,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        subscription_status_type,
        nullable=False,
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    last_stripe_event_created: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index(
            "ix_usage_events_quota_lookup",
            "tenant_id",
            "usage_type",
            "created_at",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_usage_events_quantity_positive",
        ),
        CheckConstraint(
            """
            overage_quantity >= 0
            AND overage_quantity <= quantity
            """,
            name="ck_usage_events_valid_overage_quantity",
        ),
        CheckConstraint(
            "overage_cost_microusd >= 0",
            name="ck_usage_events_overage_cost_nonnegative",
        ),
        CheckConstraint(
            "cost_microusd >= overage_cost_microusd",
            name="ck_usage_events_valid_cost",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    usage_type: Mapped[UsageType] = mapped_column(
        usage_type_enum,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    token_breakdown: Mapped[dict[str, int] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    overage_quantity: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    overage_cost_microusd: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    cost_microusd: Mapped[int] = mapped_column(BigInteger, nullable=False)
    response_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
        nullable=False,
    )

class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_event_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

class UsageAlert(Base):
    __tablename__ = "usage_alerts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "usage_type",
            "window_start",
            "threshold_percent",
            name="uq_usage_alert_threshold",
        ),
        Index(
            "ix_usage_alerts_dispatch",
            "status",
            "created_at",
        ),
        CheckConstraint(
            "window_end > window_start",
            name="ck_usage_alerts_valid_window",
        ),
        CheckConstraint(
            "threshold_percent IN (80, 100)",
            name="ck_usage_alerts_supported_threshold",
        ),
        CheckConstraint(
            "used >= 0",
            name="ck_usage_alerts_used_nonnegative",
        ),
        CheckConstraint(
            '"limit" > 0',
            name="ck_usage_alerts_limit_positive",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_usage_alerts_attempts_nonnegative",
        ),
        CheckConstraint(
            "status IN ('pending', 'delivered', 'failed')",
            name="ck_usage_alerts_supported_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        index=True,
        nullable=False,
    )
    usage_type: Mapped[UsageType] = mapped_column(
        usage_type_enum,
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    threshold_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    used: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "period_start",
            "period_end",
            name="uq_invoice_tenant_period",
        ),
        Index(
            "ix_invoices_tenant_period",
            "tenant_id",
            "period_start",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_invoices_valid_period",
        ),
        CheckConstraint(
            "currency = 'usd'",
            name="ck_invoices_supported_currency",
        ),
        CheckConstraint(
            "subtotal_microusd >= 0",
            name="ck_invoices_subtotal_nonnegative",
        ),
        CheckConstraint(
            "overage_cost_microusd >= 0",
            name="ck_invoices_overage_cost_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="finalized",
        server_default="finalized",
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="usd",
        server_default="usd",
        nullable=False,
    )
    subtotal_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    overage_cost_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    total_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint(
            "invoice_id",
            "usage_type",
            name="uq_invoice_line_usage_type",
        ),
        CheckConstraint(
            "event_count > 0",
            name="ck_invoice_lines_event_count_positive",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_invoice_lines_quantity_positive",
        ),
        CheckConstraint(
            """
            overage_quantity >= 0
            AND overage_quantity <= quantity
            """,
            name="ck_invoice_lines_valid_overage_quantity",
        ),
        CheckConstraint(
            "subtotal_microusd >= 0",
            name="ck_invoice_lines_subtotal_nonnegative",
        ),
        CheckConstraint(
            "overage_cost_microusd >= 0",
            name="ck_invoice_lines_overage_cost_nonnegative",
        ),
        CheckConstraint(
            """
            total_microusd
            = subtotal_microusd + overage_cost_microusd
            """,
            name="ck_invoice_lines_valid_total",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    usage_type: Mapped[UsageType] = mapped_column(
        usage_type_enum,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    overage_quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    subtotal_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    overage_cost_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    total_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )


class BillingAdjustment(Base):
    __tablename__ = "billing_adjustments"
    __table_args__ = (
        Index(
            "ix_billing_adjustments_tenant_period",
            "tenant_id",
            "period_start",
        ),
        CheckConstraint(
            "period_end > period_start",
            name="ck_billing_adjustments_valid_period",
        ),
        CheckConstraint(
            """
            effective_at >= period_start
            AND effective_at < period_end
            """,
            name="ck_billing_adjustments_effective_in_period",
        ),
        CheckConstraint(
            "old_monthly_price_microusd >= 0",
            name="ck_billing_adjustments_old_price_nonnegative",
        ),
        CheckConstraint(
            "new_monthly_price_microusd >= 0",
            name="ck_billing_adjustments_new_price_nonnegative",
        ),
        CheckConstraint(
            "currency = 'usd'",
            name="ck_billing_adjustments_supported_currency",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
    )
    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        index=True,
        nullable=True,
    )
    source_event_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
    )
    old_plan: Mapped[PlanName] = mapped_column(
        plan_name_type,
        nullable=False,
    )
    new_plan: Mapped[PlanName] = mapped_column(
        plan_name_type,
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    old_monthly_price_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    new_monthly_price_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    amount_microusd: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="usd",
        server_default="usd",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
