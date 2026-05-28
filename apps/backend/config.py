"""Application configuration.

Centralizes runtime settings for the Whetstone backend: the SQLite
database location, the loopback ports of the three local services the
backend orchestrates (Psirver for code execution, llama-server for the
LLM, whisper-server for speech-to-text), and the model names used for
inference and transcription.

Settings are read from environment variables (prefixed ``WHETSTONE_``)
or an optional ``.env`` file, falling back to the defaults defined here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="WHETSTONE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Storage -------------------------------------------------------
    database_url: str = Field(
        default="sqlite:///./whetstone.db",
        description="SQLAlchemy/SQLModel database URL.",
    )
    data_dir: Path = Field(
        default=Path("./data"),
        description="Directory for app-managed files (uploads, exports).",
    )

    # --- Backend bind --------------------------------------------------
    host: str = Field(default="127.0.0.1", description="Backend bind host.")
    port: int = Field(default=8000, description="Backend bind port.")

    # --- Psirver (C++ code execution) ---------------------------------
    psirver_host: str = Field(default="127.0.0.1")
    psirver_port: int = Field(default=8080)

    # --- llama-server (LLM) -------------------------------------------
    llm_host: str = Field(default="127.0.0.1")
    llm_port: int = Field(default=8081)
    llm_model: str = Field(
        default="gemma-4-e4b",
        description="Model name/alias served by llama-server.",
    )

    # --- whisper-server (speech-to-text) ------------------------------
    stt_host: str = Field(default="127.0.0.1")
    stt_port: int = Field(default=8082)
    stt_model: str = Field(
        default="whisper-base",
        description="Model name/alias served by whisper-server.",
    )

    @property
    def psirver_base_url(self) -> str:
        return f"http://{self.psirver_host}:{self.psirver_port}"

    @property
    def llm_base_url(self) -> str:
        return f"http://{self.llm_host}:{self.llm_port}"

    @property
    def stt_base_url(self) -> str:
        return f"http://{self.stt_host}:{self.stt_port}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""

    return Settings()
