"""add monthly invoices

Revision ID: a8d4e6f1c2b3
Revises: 7c3f4a9e2b10
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a8d4e6f1c2b3"
down_revision: str | None = "7c3f4a9e2b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


usage_type = postgresql.ENUM(
    "api_call",
    "ai_tokens",
    name="usage_type",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column(
            "period_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "period_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="finalized",
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default="usd",
            nullable=False,
        ),
        sa.Column(
            "subtotal_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "overage_cost_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "total_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "period_start",
            "period_end",
            name="uq_invoice_tenant_period",
        ),
    )
    op.create_index(
        "ix_invoices_tenant_period",
        "invoices",
        ["tenant_id", "period_start"],
        unique=False,
    )

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column(
            "usage_type",
            usage_type,
            nullable=False,
        ),
        sa.Column(
            "description",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "overage_quantity",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "subtotal_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "overage_cost_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "total_microusd",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["invoice_id"],
            ["invoices.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invoice_id",
            "usage_type",
            name="uq_invoice_line_usage_type",
        ),
    )
    op.create_index(
        op.f("ix_invoice_lines_invoice_id"),
        "invoice_lines",
        ["invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_invoice_lines_invoice_id"),
        table_name="invoice_lines",
    )
    op.drop_table("invoice_lines")
    op.drop_index(
        "ix_invoices_tenant_period",
        table_name="invoices",
    )
    op.drop_table("invoices")
