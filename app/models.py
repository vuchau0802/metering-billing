from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
