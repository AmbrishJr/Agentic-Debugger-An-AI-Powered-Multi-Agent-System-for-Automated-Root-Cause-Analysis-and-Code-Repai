"""Persist immutable validation plans, authorization, and measured runner outcomes."""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'


def upgrade():
    op.create_table('validation_runs',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('incident_id', sa.String(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('fix_id', sa.String(), sa.ForeignKey('proposed_fixes.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('plan_hash', sa.String(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('policy', sa.JSON(), nullable=False),
        sa.Column('proposed_sha256', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('expires_at', sa.String(), nullable=False),
        sa.Column('authorized_at', sa.String(), nullable=True),
        sa.Column('finished_at', sa.String(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=False),
    )
    for column in ('incident_id', 'fix_id', 'status'):
        op.create_index('ix_validation_runs_' + column, 'validation_runs', [column])


def downgrade():
    op.drop_table('validation_runs')
