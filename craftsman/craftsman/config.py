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
    api_token: str | None = None
    webhook_url: str | None = None
    webhook_secret: str | None = None
    webhook_mandatory: bool = False
    secret_provider: str = "env_file_fallback"
    secret_store_dir: Path = ROOT / "secrets"

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
    skip_gradle_build: bool = False

    android_build_backend: str = "auto"
    docker_android_image: str = "hunter-craftsman/android-builder"
    docker_gradle_timeout_seconds: float = 1800.0
    android_smoke_test: str = "auto"
    android_smoke_timeout_seconds: float = 600.0
    android_smoke_max_rounds: int = 2

    privacy_deploy_dry_run: bool = True
    privacy_contact_email: str = "privacy@example.com"
    cloudflare_api_token: str | None = None
    cloudflare_account_id: str | None = None

    gate_mode: str = "soft"
    gate_auto_accept: bool = True

    poll_interval_seconds: float = 2.0
    job_retry_limit: int = 2
    job_lease_seconds: int = 300
    contract_default_version: str = "1.0"
    contract_supported_versions: str = "1.0"
    artifact_uri_mode: str = "object"
    artifact_object_prefix: str = "object://local"
    llm_price_chat_input_per_1k: float = 0.0
    llm_price_chat_output_per_1k: float = 0.0
    llm_price_pro_input_per_1k: float = 0.0
    llm_price_pro_output_per_1k: float = 0.0
    alert_window_size: int = 20
    alert_min_samples: int = 5
    alert_failure_rate_threshold: float = 0.5
    alert_timeout_rate_threshold: float = 0.3
    alert_duration_threshold_ratio: float = 0.9
    release_require_human_approval: bool = True
    release_require_policy_checks: bool = True
    audit_retention_days: int = 14
    audit_replay_limit: int = 500
    native_backend_pool: str = "local-macos"
    native_backend_pool_strategy: str = "round_robin"
    execution_image_ref: str = "ghcr.io/hunter-craftsman/craftsman:py312-latest"

    # Agent C (Publisher) — Android release automation
    publisher_dry_run: bool = True
    android_release_track: str = "internal"
    google_play_package_name: str | None = None
    google_play_service_account_file: str | None = None
    android_keystore_path: str | None = None
    android_keystore_password: str | None = None
    android_key_alias: str | None = None
    android_key_password: str | None = None
    publisher_require_signing: bool = False
    publisher_submit_timeout_seconds: float = 1800.0
    webhook_url: str | None = None  # POSTed on publish completion
    auto_promote_to_production: bool = False  # 发布 internal 成功后自动推到 production（触发 Google 审核）

    job_worker_count: int = 1
    llm_request_timeout_seconds: float = 120.0
    min_free_disk_bytes: int = 8 * 1024 * 1024 * 1024

    def resolved_api_key(self) -> str | None:
        from craftsman.secrets import resolve_secret_value

        key = resolve_secret_value("DEEPSEEK_API_KEY", self.deepseek_api_key)
        if key:
            return key
        return resolve_secret_value("OPENAI_API_KEY", self.openai_api_key)

    def resolved_api_base(self) -> str:
        return self.deepseek_api_base.rstrip("/")

    def resolved_api_token(self) -> str | None:
        from craftsman.secrets import resolve_secret_value

        return resolve_secret_value("API_TOKEN", self.api_token)

    def resolved_webhook_secret(self) -> str | None:
        from craftsman.secrets import resolve_secret_value

        return resolve_secret_value("WEBHOOK_SECRET", self.webhook_secret)


settings = Settings()
