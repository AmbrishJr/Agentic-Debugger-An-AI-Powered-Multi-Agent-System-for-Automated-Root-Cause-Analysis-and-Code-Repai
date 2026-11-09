"""Add content-pinned repository snapshots; preserve legacy incident records."""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'


def upgrade():
    op.add_column('incidents', sa.Column('repository_snapshot', sa.JSON(), nullable=False, server_default='{}'))


def downgrade():
    with op.batch_alter_table('incidents') as batch:
        batch.drop_column('repository_snapshot')
