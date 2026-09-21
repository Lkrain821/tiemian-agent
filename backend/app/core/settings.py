"""Application settings loaded from environment and the repository .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    """Validated runtime configuration.

    Canonical DeepSeek variables use the DEEPSEEK_ prefix. BASE_URL and MODEL
    remain accepted so the existing local .env file does not need to be edited.
    """

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_version: str = "1.1.0"

    deepseek_api_key: SecretStr = Field(validation_alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "BASE_URL"),
    )
    deepseek_model: str = Field(
        default="deepseek-v4-pro",
        validation_alias=AliasChoices("DEEPSEEK_MODEL", "MODEL"),
    )
    deepseek_timeout_seconds: float = Field(default=60, gt=0, le=300)
    deepseek_max_retries: int = Field(default=2, ge=0, le=5)
    deepseek_thinking_mode: Literal["enabled", "disabled"] = "disabled"

    decision_provider: Literal["deepseek", "jev"] = "deepseek"
    jev_api_key: SecretStr = SecretStr("")
    jev_base_url: str = "https://api.typesafe.ai"
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = Field(default=3, gt=0, le=60)
    jev_followup_threshold: float = Field(default=0.70, ge=0, le=1)
    jev_score_threshold: float = Field(default=0.30, ge=0, le=1)
    jev_min_confidence: float = Field(default=0.60, ge=0, le=1)
    jev_fallback_enabled: bool = True
    jev_shadow_mode: bool = False

    app_db_path: Path = REPOSITORY_ROOT / "data" / "tiemian.sqlite3"
    checkpoint_db_path: Path = REPOSITORY_ROOT / "data" / "checkpoints.sqlite3"
    question_bank_path: Path = REPOSITORY_ROOT / "data" / "questions.json"
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100, le=60000)

    target_question_count: int = 5
    max_followups_per_question: int = 2
    answer_max_length: int = 1200
    partial_score_min_questions: int = Field(default=3, ge=1, le=5)
    cors_origins: list[str] = ["http://127.0.0.1:4173", "http://localhost:4173"]

    @model_validator(mode="after")
    def normalize(self) -> "Settings":
        self.jev_base_url = self.jev_base_url.rstrip("/")
        if not self.jev_base_url.startswith("https://") or not self.jev_model.strip():
            raise ValueError("JEV_BASE_URL must use HTTPS and JEV_MODEL must not be empty")
        if self.jev_score_threshold >= self.jev_followup_threshold:
            raise ValueError("JEV_SCORE_THRESHOLD must be lower than JEV_FOLLOWUP_THRESHOLD")
        self.deepseek_base_url = self.deepseek_base_url.rstrip("/")
        if not self.deepseek_model.strip():
            raise ValueError("DEEPSEEK_MODEL must not be empty")
        self.app_db_path = self._resolve_path(self.app_db_path)
        self.checkpoint_db_path = self._resolve_path(self.checkpoint_db_path)
        self.question_bank_path = self._resolve_path(self.question_bank_path)
        return self

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        if path.is_absolute():
            return path.resolve()
        return (BACKEND_ROOT / path).resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
