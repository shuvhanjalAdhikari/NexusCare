"""add lab_tests.price column

Revision ID: b1c2d3e4f5a6
Revises: 245cc2858f27
Create Date: 2026-05-17 10:00:00.000000

Phase 11 (Billing) needs a price on each lab-test catalogue entry so a
lab order can be auto-aggregated into an invoice. lab_tests had no
price column; this adds one. It is nullable — existing rows keep NULL,
and the billing auto-aggregator treats a NULL price as 0.

Hand-written per MIGRATIONS.md: a single op.add_column, no autogenerate
naming-drift noise.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '245cc2858f27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable price column to lab_tests."""
    op.add_column(
        'lab_tests',
        sa.Column('price', sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('lab_tests', 'price')
