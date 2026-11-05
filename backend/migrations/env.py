from alembic import context
from app.db.session import Base, make_engine
from app.models import records

engine = make_engine(context.config.get_main_option('sqlalchemy.url'))
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata,
                      render_as_batch=connection.dialect.name == 'sqlite')
    with context.begin_transaction():
        context.run_migrations()
