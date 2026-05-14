"""baseline

Revision ID: 9ae5293c81a8
Revises: 
Create Date: 2026-05-13 18:48:12.687126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ae5293c81a8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentional no-op. The full schema is defined in backend/sql/01_schema.sql
    # and was applied to the database before Alembic was introduced.
    # Run `alembic stamp head` on an existing DB to mark it at this revision.
    pass


def downgrade() -> None:
    # No-op — cannot roll back the baseline. To reset, drop and recreate the DB
    # using 01_schema.sql, then stamp head again.
    pass
