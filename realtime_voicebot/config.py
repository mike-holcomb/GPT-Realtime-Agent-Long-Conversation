from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseSettings, Field, PositiveInt


class Settings(BaseSettings):
    """Runtime configuration for the voicebot.

    Values are loaded from environment variables by default and may be
    overridden via CLI flags by the application entrypoint.
    """

    # OpenAI / API configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_base_url: str | None = Field(None, env="OPENAI_BASE_URL")

    # Models & voice
    realtime_model: str = Field("gpt-4o-realtime-preview", env="REALTIME_MODEL")
    transcribe_model: str = Field("gpt-4o-transcribe", env="TRANSCRIBE_MODEL")
    voice_name: str = Field("shimmer", env="VOICE_NAME")

    # Audio
    sample_rate_hz: PositiveInt = Field(24_000, env="SAMPLE_RATE_HZ")
    chunk_ms: PositiveInt = Field(40, env="CHUNK_MS")
    input_device_id: int | None = Field(None, env="INPUT_DEVICE_ID")
    output_device_id: int | None = Field(None, env="OUTPUT_DEVICE_ID")

    # Summarization
    summary_model: str = Field("gpt-4o-mini", env="SUMMARY_MODEL")
    summary_trigger_tokens: PositiveInt = Field(2_000, env="SUMMARY_TRIGGER_TOKENS")
    keep_last_turns: PositiveInt = Field(2, env="KEEP_LAST_TURNS")
    language_policy: Literal["auto", "en", "force"] = Field("auto", env="LANGUAGE_POLICY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
