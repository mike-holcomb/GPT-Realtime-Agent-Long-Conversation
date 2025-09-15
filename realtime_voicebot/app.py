from __future__ import annotations

import asyncio
import logging

from .config import Settings, get_settings
from .logging import configure_logging


async def run(settings: Settings | None = None) -> None:
    """Application orchestrator stub.

    Parameters
    ----------
    settings:
        Optional :class:`Settings` instance to run with. If omitted, values are
        loaded from the environment using :func:`get_settings`.

    This currently only validates configuration and sets up logging. In the
    next iterations it will:
      - Initialize transport client and connect to Realtime API,
      - Start MicStreamer and AudioPlayer,
      - Dispatch events to handlers,
      - Apply summarization policy.
    """
    configure_logging()
    settings = settings or get_settings()
    # Wire default PII redaction into conversation state based on settings.
    # This ensures transcripts are scrubbed before logging or storage.
    from .redaction import Redactor
    from .state.conversation import ConversationState

    state = ConversationState(redact=Redactor(enabled=settings.redact_pii).redact)
    logging.getLogger(__name__).info(
        "voicebot starting",
        extra={
            "model": settings.realtime_model,
            "voice": settings.voice_name,
            "sample_rate": settings.sample_rate_hz,
            "summary_trigger": settings.summary_trigger_tokens,
        },
    )
    # Placeholder until transport is wired; keep state referenced
    _ = state
    await asyncio.sleep(0)


def main() -> None:
    asyncio.run(run())
