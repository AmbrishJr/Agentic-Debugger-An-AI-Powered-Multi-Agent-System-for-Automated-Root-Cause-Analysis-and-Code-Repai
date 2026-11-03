from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'sqlite:///./data/autorca.db'
    openai_api_key: str = ''
    openai_model: str = 'gpt-4.1-mini'
    repository_root: str = ''
    github_token: str = ''
    github_repository: str = ''
    github_base_branch: str = 'main'
    autorca_api_token: str = ''
    sandbox_enabled: bool = False
    # Immutable local Docker image ID, never a repository-provided image/tag.
    sandbox_image: str = ''
    sandbox_timeout_seconds: int = 30
    sandbox_docker_context: str = ''


settings = Settings()
