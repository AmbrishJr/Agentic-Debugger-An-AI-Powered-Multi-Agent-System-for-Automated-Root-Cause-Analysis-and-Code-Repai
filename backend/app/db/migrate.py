from pathlib import Path
from alembic import command
from alembic.config import Config
from app.core.config import settings


def migrate():
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / 'alembic.ini'))
    config.set_main_option('script_location', str(root / 'migrations'))
    config.set_main_option('sqlalchemy.url', settings.database_url.replace('%', '%%'))
    command.upgrade(config, 'head')


if __name__ == '__main__':
    migrate()
