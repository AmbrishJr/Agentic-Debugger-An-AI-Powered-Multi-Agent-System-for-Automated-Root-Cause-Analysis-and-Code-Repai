"""Workspace accounts, durable jobs, resolution audit, and multi-file patches."""
from alembic import op
import sqlalchemy as sa
revision = '003'
down_revision = '002'


def upgrade():
    op.add_column('incidents', sa.Column('resolution_note',sa.Text(),nullable=False,server_default=''))
    op.add_column('incidents', sa.Column('resolution_evidence',sa.Text(),nullable=False,server_default=''))
    op.add_column('incidents', sa.Column('resolved_at',sa.String(),nullable=True))
    op.add_column('incidents', sa.Column('resolved_by',sa.String(),nullable=True))
    op.add_column('proposed_fixes',sa.Column('files',sa.JSON(),nullable=False,server_default='[]'))
    op.create_table('users',sa.Column('id',sa.String(),primary_key=True),sa.Column('username',sa.String(),nullable=False,unique=True),sa.Column('password_hash',sa.Text(),nullable=False),sa.Column('role',sa.String(),nullable=False),sa.Column('active',sa.Boolean(),nullable=False),sa.Column('created_at',sa.String(),nullable=False))
    op.create_table('auth_sessions',sa.Column('id',sa.String(),primary_key=True),sa.Column('user_id',sa.String(),sa.ForeignKey('users.id'),nullable=False,index=True),sa.Column('csrf_token',sa.String(),nullable=False),sa.Column('expires_at',sa.String(),nullable=False,index=True))
    op.create_table('login_throttles',sa.Column('key',sa.String(),primary_key=True),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('expires_at',sa.String(),nullable=False))
    op.create_table('incident_events',sa.Column('id',sa.String(),primary_key=True),sa.Column('incident_id',sa.String(),sa.ForeignKey('incidents.id'),nullable=False,index=True),sa.Column('action',sa.String(),nullable=False),sa.Column('actor',sa.String(),nullable=False),sa.Column('note',sa.Text(),nullable=False),sa.Column('evidence',sa.Text(),nullable=False),sa.Column('created_at',sa.String(),nullable=False))
    op.create_table('jobs',sa.Column('id',sa.String(),primary_key=True),sa.Column('kind',sa.String(),nullable=False),sa.Column('target_id',sa.String(),nullable=False),sa.Column('incident_id',sa.String(),sa.ForeignKey('incidents.id'),nullable=False,index=True),sa.Column('status',sa.String(),nullable=False,index=True),sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('cancel_requested',sa.Boolean(),nullable=False),sa.Column('error',sa.Text(),nullable=True),sa.Column('created_at',sa.String(),nullable=False),sa.Column('updated_at',sa.String(),nullable=False),sa.UniqueConstraint('kind','target_id'))
    op.create_table('worker_state',sa.Column('id',sa.String(),primary_key=True),sa.Column('heartbeat_at',sa.String(),nullable=False))


def downgrade():
    for name in ('worker_state','jobs','incident_events','login_throttles','auth_sessions','users'):
        op.drop_table(name)
    with op.batch_alter_table('proposed_fixes') as batch:
        batch.drop_column('files')
    with op.batch_alter_table('incidents') as batch:
        for name in ('resolution_note','resolution_evidence','resolved_at','resolved_by'):
            batch.drop_column(name)
