from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the voicebot.

    Values are loaded from environment variables by default and may be
    overridden via CLI flags by the application entrypoint.
    """

    # OpenAI / API configuration
    openai_api_key: Annotated[str, Field(min_length=1)] = ""
    openai_base_url: str | None = None

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

    # pydantic-settings v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
