"""audit log hardening

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-17 12:00:00.000000

Phase 13 (Audit Logging) starts writing to the previously-empty
audit_logs table. Two schema changes are required before that is safe:

1. hospital_id DROP NOT NULL.
   login / login_failed / account_locked events are recorded in
   services/auth.py:authenticate_user, which runs BEFORE workspace
   selection. At that point there is no hospital context, so those rows
   must store hospital_id = NULL. The original schema declared the
   column NOT NULL, which would reject every login audit insert.

2. Three indexes for the common audit-query patterns.
   01_schema.sql ships only idx_audit_logs_resource
   (resource_type, resource_id). The Phase 13 read endpoints also
   filter by hospital_id, by user_id, and order/range by created_at.
   audit_logs grows on every dispense, payment, and login, so these
   indexes matter for query performance as the table fills up.

Hand-written per MIGRATIONS.md: no autogenerate. The body is explicit.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop NOT NULL on hospital_id and add the three query indexes."""
    op.alter_column(
        'audit_logs',
        'hospital_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.create_index(
        'idx_audit_logs_hospital', 'audit_logs', ['hospital_id']
    )
    op.create_index(
        'idx_audit_logs_user', 'audit_logs', ['user_id']
    )
    op.create_index(
        'idx_audit_logs_created', 'audit_logs', ['created_at']
    )


def downgrade() -> None:
    """Drop the three indexes and restore NOT NULL on hospital_id.

    NOTE: restoring NOT NULL fails if any login-era rows with
    hospital_id = NULL exist. Such rows must be purged before a
    downgrade — by design, since v1 never deletes audit rows, a
    downgrade past this revision is not expected.
    """
    op.drop_index('idx_audit_logs_created', table_name='audit_logs')
    op.drop_index('idx_audit_logs_user', table_name='audit_logs')
    op.drop_index('idx_audit_logs_hospital', table_name='audit_logs')
    op.alter_column(
        'audit_logs',
        'hospital_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
