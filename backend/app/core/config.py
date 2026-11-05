from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'sqlite:///./data/autorca.db'
    migrate_on_startup: bool = True
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1-mini'
    llm_provider: Literal['openai', 'gemini'] = 'openai'
    gemini_api_key: str = ''
    gemini_model: str = 'gemini-3.5-flash-lite'
    repository_root: str = ''
    github_token: str = ''
    github_repository: str = ''
    github_base_branch: str = 'main'
    autorca_api_token: str = ''
    sandbox_enabled: bool = False
    sandbox_provider: Literal['docker', 'vercel'] = 'docker'
    sandbox_vercel_image: str = ''
    # Immutable local Docker image ID, never a repository-provided image/tag.
    sandbox_image: str = ''
    sandbox_timeout_seconds: int = 30
    sandbox_docker_context: str = ''
    auth_enabled: bool = True
    secure_cookies: bool = False
    session_hours: int = 12
    public_origin: str = 'http://127.0.0.1:3000'
    job_execution: Literal['embedded', 'external', 'inline', 'vercel'] = 'embedded'


settings = Settings()


def validate_hosted_settings(config):
    if not config.database_url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')):
        raise ValueError('Vercel requires a PostgreSQL DATABASE_URL.')
    if config.job_execution != 'vercel' or config.migrate_on_startup:
        raise ValueError('Vercel requires JOB_EXECUTION=vercel and MIGRATE_ON_STARTUP=false. Run migrations before deployment.')
    if not config.auth_enabled or not config.secure_cookies or len(config.autorca_api_token) < 32:
        raise ValueError('Vercel requires authentication, secure cookies, and an API token of at least 32 characters.')
    from urllib.parse import urlparse
    origin = urlparse(config.public_origin)
    if origin.scheme != 'https' or not origin.netloc or origin.path or origin.query or origin.fragment or origin.username:
        raise ValueError('PUBLIC_ORIGIN must be the exact HTTPS frontend origin, without a trailing slash.')
    if config.repository_root or (config.sandbox_enabled and config.sandbox_provider != 'vercel'):
        raise ValueError('Vercel uses GitHub source and Vercel Sandbox; local repository paths and Docker runners are unavailable.')


if os.environ.get('VERCEL') == '1':
    validate_hosted_settings(settings)
