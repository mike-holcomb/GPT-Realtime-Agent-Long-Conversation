from __future__ import annotations

import asyncio
import logging

from .config import get_settings
from .logging import configure_logging


async def run() -> None:
    """Application orchestrator stub.

    This currently only validates configuration and sets up logging. In the
    next iterations it will:
      - Initialize transport client and connect to Realtime API,
      - Start MicStreamer and AudioPlayer,
      - Dispatch events to handlers,
      - Apply summarization policy.
    """
    configure_logging()
    settings = get_settings()
    logging.getLogger(__name__).info(
        "voicebot starting",
        extra={
            "model": settings.realtime_model,
            "voice": settings.voice_name,
            "sample_rate": settings.sample_rate_hz,
            "summary_trigger": settings.summary_trigger_tokens,
        },
    )
    # Placeholder until transport is wired
    await asyncio.sleep(0)


def main() -> None:
    asyncio.run(run())
