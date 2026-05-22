from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8791
    database_path: Path = ROOT / "craftsman.db"
    workspace_root: Path = ROOT / "workspace"
    callback_dir: Path = ROOT / "callbacks"
    webhook_url: str | None = None
    webhook_secret: str | None = None

    # DeepSeek（OpenAI 兼容接口）
    deepseek_api_key: str | None = None
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    # 反馈 Agent A：Gate 语义评审
    deepseek_chat_model: str = "deepseek-chat"
    # 写码 / Reflexion 修错
    deepseek_pro_model: str = "deepseek-v4-pro"

    # 兼容旧配置名（未设 DEEPSEEK_* 时可回落）
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    max_reflexion_rounds: int = 5
    max_implementation_seconds: float = 7200.0
    max_features: int = 8

    xcode_scheme: str | None = None
    simulator_name: str = "iPhone 16"
    skip_xcodebuild: bool = False
    skip_fastlane: bool = False

    poll_interval_seconds: float = 2.0

    def resolved_api_key(self) -> str | None:
        return self.deepseek_api_key or self.openai_api_key

    def resolved_api_base(self) -> str:
        return self.deepseek_api_base.rstrip("/")


settings = Settings()
