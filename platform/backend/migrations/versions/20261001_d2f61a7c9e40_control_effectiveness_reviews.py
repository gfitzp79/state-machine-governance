"""control effectiveness reviews

Adds the record a repaired control goes through before anything that depends on
it is told it works again (codified-rules 10.3, REV-1 to REV-5).

A deployment returning to Active used to be silent. The risk it held up stayed
at its inherent score, the threat scenario it mitigated stayed open, and the
compliance requirement it evidenced stayed in Gap, with nothing prompting anyone
to look. A review now opens on the repair, is closed only by a passing retest,
and its completion is what prompts the dependants.

No data migration: a deployment repaired before this release has no review, and
inventing one for it would assert a repair date nobody recorded.

Revision ID: d2f61a7c9e40
Revises: b71c04e98d12
Created: 2026-10-01 18:20:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'd2f61a7c9e40'
down_revision: str | None = 'b71c04e98d12'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'control_reviews',
        sa.Column('reference', sa.String(length=32), nullable=False),
        sa.Column('deployment_id', sa.String(length=36), nullable=False),
        sa.Column('objective_id', sa.String(length=36), nullable=False),
        sa.Column('trigger', sa.String(length=64), nullable=False),
        sa.Column('lifecycle_state', sa.String(length=16), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('completed_by', sa.String(length=36), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completion_test_id', sa.String(length=36), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('Open', 'Completed', 'Cancelled')", name='ck_control_reviews_state'
        ),
        sa.CheckConstraint(
            "lifecycle_state <> 'Completed' OR (completed_by IS NOT NULL AND completion_test_id IS NOT NULL)",
            name='ck_control_reviews_completion_evidenced',
        ),
        sa.ForeignKeyConstraint(['deployment_id'], ['control_deployments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['objective_id'], ['control_objectives.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['completion_test_id'], ['control_tests.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference'),
    )
    op.create_index(op.f('ix_control_reviews_deployment_id'), 'control_reviews', ['deployment_id'], unique=False)
    op.create_index(op.f('ix_control_reviews_objective_id'), 'control_reviews', ['objective_id'], unique=False)
    op.create_index(
        'uq_control_reviews_one_open', 'control_reviews', ['deployment_id'], unique=True,
        postgresql_where=sa.text("lifecycle_state = 'Open'"),
    )


def downgrade() -> None:
    op.drop_index('uq_control_reviews_one_open', table_name='control_reviews')
    op.drop_index(op.f('ix_control_reviews_objective_id'), table_name='control_reviews')
    op.drop_index(op.f('ix_control_reviews_deployment_id'), table_name='control_reviews')
    op.drop_table('control_reviews')
