from __future__ import annotations

import logging
from typing import Any

from ..config import Settings, get_settings
from ..metrics import Timer
from ..state.conversation import Turn
from .base import Summarizer

_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
}


class NullSummarizer(Summarizer):
    """No-op summarizer used when summarization is disabled."""

    disabled = True

    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:
        return ""


class OpenAISummarizer(Summarizer):
    """Summarizer backed by the OpenAI Responses API."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.log = logging.getLogger(__name__)
        self.settings = settings or self._load_settings()
        self._client = client or self._build_client(self.settings)

    async def summarize(self, turns: list[Turn], language: str | None = None) -> str:
        timer = Timer()
        timer.start()
        language_code = (language or "en").lower()
        transcript = self._format_transcript(turns)

        self.log.info(
            "summarization_start",
            extra={
                "event_type": "summarization_start",
                "turn_id": None,
                "response_id": None,
                "latency_ms": None,
                "tokens_total": None,
                "dropped_frames": None,
                "language": language_code,
            },
        )

        if not transcript.strip():
            timer.stop()
            self.log.info(
                "summarization_end",
                extra={
                    "event_type": "summarization_end",
                    "turn_id": None,
                    "response_id": None,
                    "latency_ms": timer.last_ms,
                    "tokens_total": None,
                    "dropped_frames": None,
                    "language": language_code,
                },
            )
            return "Synopsis: conversation context not yet available.\nFacts: none."

        system_prompt = self._system_prompt(language_code)
        payload = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": transcript}],
            },
        ]

        summary_text = ""
        try:
            response = await self._client.responses.create(
                model=self.settings.summary_model,
                input=payload,
                temperature=0,
            )
            summary_text = self._extract_text(response).strip()
        finally:
            timer.stop()

        if not summary_text:
            summary_text = "Synopsis: conversation summary unavailable.\nFacts: none."

        self.log.info(
            "summarization_end",
            extra={
                "event_type": "summarization_end",
                "turn_id": None,
                "response_id": None,
                "latency_ms": timer.last_ms,
                "tokens_total": None,
                "dropped_frames": None,
                "language": language_code,
            },
        )
        return summary_text

    @staticmethod
    def _load_settings() -> Settings:
        try:  # pragma: no cover - trivial configuration path
            return get_settings()
        except Exception:  # pragma: no cover - fallback when pydantic missing
            return type(
                "_FallbackSettings",
                (),
                {
                    "summary_model": "gpt-4o-mini",
                    "provider": "openai",
                    "openai_api_key": "",
                    "openai_base_url": None,
                    "azure_openai_api_key": "",
                    "azure_openai_endpoint": None,
                    "azure_openai_api_version": "2024-07-01-preview",
                    "azure_openai_deployment": "",
                },
            )()

    def _build_client(self, settings: Settings) -> Any:
        provider = getattr(settings, "provider", "openai")
        if provider == "azure":
            from openai import AsyncAzureOpenAI

            if not getattr(settings, "azure_openai_api_key", ""):
                raise RuntimeError("AZURE_OPENAI_API_KEY is required for summarization")
            azure_endpoint = settings.azure_openai_endpoint
            if not azure_endpoint:
                raise RuntimeError("AZURE_OPENAI_ENDPOINT is required for summarization")
            return AsyncAzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=azure_endpoint,
            )

        from openai import AsyncOpenAI

        api_key = getattr(settings, "openai_api_key", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for summarization")

        base_url = getattr(settings, "openai_base_url", None)
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        return AsyncOpenAI(**client_kwargs)

    def _system_prompt(self, language: str) -> str:
        instruction = self._language_instruction(language)
        return (
            "You maintain a rolling summary of a voice assistant conversation. "
            "Write a concise update that future assistant turns can rely on. "
            "Always respond with exactly two lines using this template:\n"
            "Synopsis: <one sentence overview>\n"
            "Facts: <semicolon-separated enduring facts or 'none'>. "
            "Do not invent details or include speaker markers. "
            f"{instruction}"
        )

    def _language_instruction(self, language: str) -> str:
        normalized = language.lower()
        if normalized in {"", "en"}:
            return "Respond in English."
        name = _LANGUAGE_NAMES.get(normalized)
        if name:
            return f"Respond entirely in {name} ({normalized}) without mixing other languages."
        return (
            "Respond entirely in the language identified by the ISO code "
            f"'{normalized}' without mixing other languages."
        )

    def _format_transcript(self, turns: list[Turn]) -> str:
        role_labels = {"user": "User", "assistant": "Assistant", "system": "System"}
        lines: list[str] = []
        for turn in turns:
            if not turn.text:
                continue
            label = role_labels.get(turn.role, turn.role)
            lines.append(f"{label}: {turn.text.strip()}")
        return "\n".join(lines)

    def _extract_text(self, response: Any) -> str:
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        outputs = getattr(response, "output", None)
        if outputs is None and isinstance(response, dict):
            outputs = response.get("output")

        collected: list[str] = []
        for item in outputs or []:
            content = getattr(item, "content", None)
            if content is None and isinstance(item, dict):
                content = item.get("content")
            for block in content or []:
                block_text = getattr(block, "text", None)
                if block_text is None and isinstance(block, dict):
                    block_text = block.get("text")
                if isinstance(block_text, str) and block_text.strip():
                    collected.append(block_text.strip())

        if collected:
            return "\n".join(collected)

        # Fallback for chat-completions style responses if returned.
        choices = getattr(response, "choices", None)
        if choices is None and isinstance(response, dict):
            choices = response.get("choices")
        if choices:
            for choice in choices:
                message = getattr(choice, "message", None)
                if message is None and isinstance(choice, dict):
                    message = choice.get("message")
                if not message:
                    continue
                content = getattr(message, "content", None)
                if content is None and isinstance(message, dict):
                    content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

        return ""
