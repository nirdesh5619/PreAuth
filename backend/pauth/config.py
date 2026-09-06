"""Runtime settings loaded from the repo-root `.env` and process environment."""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
ENV_FILE = REPO_ROOT / ".env"


def load_env_file() -> Path | None:
    """Push non-empty keys from the root `.env` into `os.environ` if unset."""
    if not ENV_FILE.is_file():
        return None
    for key, value in dotenv_values(ENV_FILE).items():
        if not value:
            continue
        current = os.environ.get(key, "")
        if not current.strip():
            os.environ[key] = value
    return ENV_FILE


load_env_file()


class Settings(BaseSettings):
    """Typed config. Empty `OPENAI_API_KEY` means specialist stubs, not OpenAI."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    openai_api_key: str = ""
    llm_model: str = "gpt-4o"
    pauth_force_stubs: bool = False
    data_dir: Path = BACKEND_ROOT / "data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def use_llm(self) -> bool:
        """True when a non-blank key is set and stubs are not forced."""
        return bool(self.openai_api_key.strip()) and not self.pauth_force_stubs

    @property
    def app_db_path(self) -> Path:
        """SQLite file for cases, runs, events, and artifacts."""
        return self.data_dir / "pauth.db"

    @property
    def checkpoint_db_path(self) -> Path:
        """SQLite file for LangGraph thread state (HITL resume)."""
        return self.data_dir / "checkpoints.db"

    @property
    def uploads_dir(self) -> Path:
        """Directory for uploaded chart files, grouped by case id."""
        return self.data_dir / "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        """Split `cors_origins` into stripped origin URLs."""
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
