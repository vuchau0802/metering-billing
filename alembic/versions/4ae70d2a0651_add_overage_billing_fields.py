"""add overage billing fields

Revision ID: 4ae70d2a0651
Revises: c91b2f6e4a7d
Create Date: 2026-10-01 13:04:52.287795

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4ae70d2a0651'
down_revision: Union[str, None] = 'c91b2f6e4a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "overage_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "usage_events",
        sa.Column(
            "overage_quantity",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "usage_events",
        sa.Column(
            "overage_cost_microusd",
            sa.BigInteger(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "usage_events",
        "overage_cost_microusd",
    )
    op.drop_column(
        "usage_events",
        "overage_quantity",
    )
    op.drop_column(
        "plans",
        "overage_enabled",
    )