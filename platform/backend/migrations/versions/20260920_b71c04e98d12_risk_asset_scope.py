"""risk asset scope

Adds the table that lets a risk say which assets it concerns.

Without it, a control deployed on the identity provider reduced the likelihood
of a risk about the support console, because nothing in the model connected a
risk to a place. Threat models have had this since TINV-4 and compliance since
AINV-2. Risk, the oldest domain, had neither.

No data migration, and deliberately so. Every existing risk starts with an empty
scope, which RINV-14 reads as undeclared rather than as a scope of nothing, so
scores do not move when this runs. Declaring a scope is what turns the filter
on, and it can only ever remove controls from a resolution, never add them.

Revision ID: b71c04e98d12
Revises: aaa34e5fc638
Created: 2026-09-20 14:12:03.417882

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = 'b71c04e98d12'
down_revision: str | None = 'aaa34e5fc638'
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        'risk_assets',
        sa.Column('risk_id', sa.String(length=36), nullable=False),
        sa.Column('attack_surface_id', sa.String(length=36), nullable=False),
        sa.Column('linked_by', sa.String(length=36), nullable=True),
        sa.Column(
            'linked_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['attack_surface_id'], ['attack_surfaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['risk_id'], ['risks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('risk_id', 'attack_surface_id', name='uq_risk_assets'),
    )
    op.create_index(op.f('ix_risk_assets_risk_id'), 'risk_assets', ['risk_id'], unique=False)


def downgrade() -> None:
    # Dropping this widens every scoped risk back to unfiltered CE, so residual
    # scores that RINV-14 would now refuse become reachable again. That is the
    # honest consequence of removing the rule, not a defect in the downgrade.
    op.drop_index(op.f('ix_risk_assets_risk_id'), table_name='risk_assets')
    op.drop_table('risk_assets')
