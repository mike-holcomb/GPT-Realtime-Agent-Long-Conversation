from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the voicebot.

    Values are loaded from environment variables by default and may be
    overridden via CLI flags by the application entrypoint.
    """

    # Provider selection
    provider: Literal["openai", "azure"] = "openai"

    # OpenAI / API configuration
    # Note: allow empty by default so CLI/tests can run without a key.
    # Connection layers should validate presence when contacting the API.
    openai_api_key: str = ""
    openai_base_url: str | None = None

    # Azure OpenAI configuration
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-07-01-preview"
    azure_openai_deployment: str = "realtime"

    # Models & voice
    realtime_model: str = "gpt-4o-realtime-preview"
    transcribe_model: str = "gpt-4o-transcribe"
    voice_name: str = "shimmer"

    # Audio
    sample_rate_hz: PositiveInt = 24_000
    chunk_ms: PositiveInt = 40
    bytes_per_sample: PositiveInt = 2
    input_device_id: int | None = None
    output_device_id: int | None = None

    # Summarization
    summary_model: str = "gpt-4o-mini"
    summary_trigger_tokens: PositiveInt = 2_000
    keep_last_turns: PositiveInt = 2
    language_policy: Literal["auto", "en", "force"] = "auto"

    # Privacy
    redact_pii: bool = True

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
