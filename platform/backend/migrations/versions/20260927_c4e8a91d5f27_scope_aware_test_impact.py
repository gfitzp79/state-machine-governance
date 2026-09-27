"""scope aware test impact

Adds what a control test needs to say where its consequences stop.

  * control_tests.failure_type: Design or Operating (CINV-16). DL-1 now
    propagates a design failure to the objective and keeps an operating failure
    on the deployment, so the record has to say which it was.
  * control_tests.impact: the downstream effect, computed in the transaction
    that recorded the test and kept with it, as lineage.
  * control_test_campaigns: a round of testing read against its population.

The one data change is a backfill, and it is a statement of fact rather than a
guess: until this revision every failed test propagated to its objective, which
is exactly the design-failure behaviour. Recording those rows as Design says
what the platform did with them. It is the only UPDATE ever run against this
append-only table, so the trigger is suspended for that statement alone and
restored before the migration returns.

Revision ID: c4e8a91d5f27
Revises: b71c04e98d12
Created: 2026-09-27 10:05:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c4e8a91d5f27'
down_revision: str | None = 'b71c04e98d12'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'control_test_campaigns',
        sa.Column('reference', sa.String(length=32), nullable=False),
        sa.Column('objective_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('tested_by', sa.String(length=36), nullable=True),
        sa.Column(
            'tested_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('impact', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ['objective_id'], ['control_objectives.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference'),
    )
    op.create_index(
        op.f('ix_control_test_campaigns_objective_id'),
        'control_test_campaigns',
        ['objective_id'],
        unique=False,
    )

    op.add_column('control_tests', sa.Column('failure_type', sa.String(length=16), nullable=True))
    op.add_column('control_tests', sa.Column('campaign_id', sa.String(length=36), nullable=True))
    op.add_column(
        'control_tests',
        sa.Column(
            'impact',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column('control_tests', 'impact', server_default=None)
    op.create_index(
        op.f('ix_control_tests_campaign_id'), 'control_tests', ['campaign_id'], unique=False
    )
    op.create_foreign_key(
        'control_tests_campaign_id_fkey',
        'control_tests',
        'control_test_campaigns',
        ['campaign_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # The backfill described above. DISABLE TRIGGER USER rather than naming the
    # trigger, because a database that has not yet booted this version may not
    # carry it, and naming a trigger that is absent is an error.
    op.execute("ALTER TABLE control_tests DISABLE TRIGGER USER")
    op.execute("UPDATE control_tests SET failure_type = 'Design' WHERE result = 'Fail'")
    op.execute("ALTER TABLE control_tests ENABLE TRIGGER USER")

    op.create_check_constraint(
        'ck_control_tests_failure_type',
        'control_tests',
        "failure_type IS NULL OR failure_type IN ('Design', 'Operating')",
    )
    op.create_check_constraint(
        'ck_control_tests_failure_classified',
        'control_tests',
        "result <> 'Fail' OR failure_type IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint('ck_control_tests_failure_classified', 'control_tests', type_='check')
    op.drop_constraint('ck_control_tests_failure_type', 'control_tests', type_='check')
    op.drop_constraint('control_tests_campaign_id_fkey', 'control_tests', type_='foreignkey')
    op.drop_index(op.f('ix_control_tests_campaign_id'), table_name='control_tests')
    op.drop_column('control_tests', 'impact')
    op.drop_column('control_tests', 'campaign_id')
    op.drop_column('control_tests', 'failure_type')
    op.drop_index(
        op.f('ix_control_test_campaigns_objective_id'), table_name='control_test_campaigns'
    )
    op.drop_table('control_test_campaigns')
