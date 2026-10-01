"""add tenant api key hash

Revision ID: c91b2f6e4a7d
Revises: baa2a53554f2
Create Date: 2026-09-30 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91b2f6e4a7d"
down_revision: Union[str, None] = "baa2a53554f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "api_key_hash",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_tenants_api_key_hash",
        "tenants",
        ["api_key_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tenants_api_key_hash",
        "tenants",
        type_="unique",
    )
    op.drop_column("tenants", "api_key_hash")
