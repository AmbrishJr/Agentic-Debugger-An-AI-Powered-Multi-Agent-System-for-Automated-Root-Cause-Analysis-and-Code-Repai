"""PostgreSQL search, pinned GitHub revisions, and durable workflow ownership."""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'


def upgrade():
    op.add_column('incidents', sa.Column('repository_commit', sa.String(), nullable=False, server_default=''))
    op.add_column('incidents', sa.Column('repository_name', sa.String(), nullable=False, server_default=''))
    op.add_column('jobs', sa.Column('dispatch_token', sa.String(), nullable=False, server_default=''))
    op.add_column('jobs', sa.Column('workflow_run_id', sa.String(), nullable=True))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("CREATE INDEX ix_memory_search ON incident_memory USING gin (to_tsvector('simple', error_signature || ' ' || root_cause || ' ' || resolution_summary))")


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.drop_index('ix_memory_search', table_name='incident_memory')
    with op.batch_alter_table('jobs') as batch:
        batch.drop_column('workflow_run_id')
        batch.drop_column('dispatch_token')
    with op.batch_alter_table('incidents') as batch:
        batch.drop_column('repository_name')
        batch.drop_column('repository_commit')
