from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
CRAFTSMAN_ROOT = REPO_ROOT / "craftsman"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / "craftsman" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8800
    craftsman_base_url: str = "http://127.0.0.1:8791"
    craftsman_api_token: str | None = None  # env: API_TOKEN from craftsman/.env
    craftsman_contract_version: str = "1.0"
    pipeline_runs_dir: Path = REPO_ROOT / "pipeline_runs"
    workspace_root: Path = CRAFTSMAN_ROOT / "workspace"
    static_dir: Path = Path(__file__).resolve().parent / "static"


settings = Settings()
