"""add usage alert outbox

Revision ID: 7c3f4a9e2b10
Revises: 4ae70d2a0651
Create Date: 2026-10-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7c3f4a9e2b10"
down_revision: Union[str, None] = "4ae70d2a0651"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "usage_type",
            postgresql.ENUM(
                "api_call",
                "ai_tokens",
                name="usage_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "window_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("threshold_percent", sa.Integer(), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "usage_type",
            "window_start",
            "threshold_percent",
            name="uq_usage_alert_threshold",
        ),
    )
    op.create_index(
        "ix_usage_alerts_dispatch",
        "usage_alerts",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_usage_alerts_tenant_id"),
        "usage_alerts",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_usage_alerts_tenant_id"),
        table_name="usage_alerts",
    )
    op.drop_index(
        "ix_usage_alerts_dispatch",
        table_name="usage_alerts",
    )
    op.drop_table("usage_alerts")
