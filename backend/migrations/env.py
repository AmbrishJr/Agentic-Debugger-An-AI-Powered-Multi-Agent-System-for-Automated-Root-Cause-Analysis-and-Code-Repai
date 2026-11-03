from alembic import context
from sqlalchemy import create_engine
from app.db.session import Base
from app.models import records

engine = create_engine(context.config.get_main_option('sqlalchemy.url'))
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
