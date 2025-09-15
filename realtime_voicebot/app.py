from __future__ import annotations

import asyncio
import logging

from .config import Settings, get_settings
from .logging import configure_logging


async def run(settings: Settings | None = None) -> None:
    """Run the voicebot orchestrator."""

    configure_logging()
    settings = settings or get_settings()

    # Lazy imports to avoid heavy dependencies during module import.
    from .audio.input import MicConfig, MicStreamer
    from .audio.output import AudioPlayer, PlayerConfig
    from .handlers.core import (
        handle_conversation_item_created,
        handle_conversation_item_retrieved,
        handle_response_audio_delta,
        handle_response_created,
        handle_response_done,
        handle_response_error,
    )
    from .handlers.tools import ToolRegistry, clock_tool, handle_tool_call, http_tool
    from .redaction import Redactor
    from .state.conversation import ConversationState, SummaryPolicy
    from .summarization.openai_impl import NullSummarizer, OpenAISummarizer
    from .transport.client import RealtimeClient, build_ws_url_headers
    from .transport.events import Dispatcher

    log = logging.getLogger(__name__)

    state = ConversationState(redact=Redactor(enabled=settings.redact_pii).redact)
    summary_model = (settings.summary_model or "").strip()
    if not summary_model or summary_model.lower() in {"none", "null", "off", "disabled"}:
        summarizer = NullSummarizer()
    else:
        summarizer = OpenAISummarizer(settings=settings)
    policy = SummaryPolicy(
        threshold_tokens=settings.summary_trigger_tokens,
        keep_last_turns=settings.keep_last_turns,
        language_policy=settings.language_policy,
    )

    # Advertise sample tools.
    registry = ToolRegistry()
    registry.register(clock_tool)
    registry.register(http_tool)

    # Build transport client.
    url, headers = build_ws_url_headers(settings)
    session_config = {
        "voice": settings.voice_name,
        "modalities": ["text", "audio"],
        "input_audio_format": {
            "type": "pcm16",
            "sample_rate": settings.sample_rate_hz,
        },
        "output_audio_format": {
            "type": "pcm16",
            "sample_rate": settings.sample_rate_hz,
        },
        "transcription": {"model": settings.transcribe_model},
        "tools": registry.specs(),
    }

    dispatcher: Dispatcher[dict] = Dispatcher()

    player = AudioPlayer(
        PlayerConfig(sample_rate_hz=settings.sample_rate_hz, device_id=settings.output_device_id)
    )

    client = RealtimeClient(url, headers, dispatcher.dispatch, session_config=session_config)

    # Register event handlers -------------------------------------------------
    dispatcher.on("response.created", lambda ev: handle_response_created(ev, client))
    dispatcher.on(
        "response.audio.delta",
        lambda ev: handle_response_audio_delta(ev, client, player),
    )
    dispatcher.on(
        "conversation.item.created",
        lambda ev: handle_conversation_item_created(ev, client, player, state),
    )
    dispatcher.on(
        "conversation.item.retrieved",
        lambda ev: handle_conversation_item_retrieved(ev, client, state, summarizer, policy),
    )
    dispatcher.on(
        "response.done",
        lambda ev: handle_response_done(ev, client, state, summarizer, policy),
    )
    dispatcher.on(
        "response.output_item.create",
        lambda ev: handle_tool_call(ev, client, registry),
    )
    dispatcher.on("response.error", lambda ev: handle_response_error(ev, client))

    # Mic input queue ---------------------------------------------------------
    audio_q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=32)
    mic = MicStreamer(
        MicConfig(
            sample_rate_hz=settings.sample_rate_hz,
            chunk_ms=settings.chunk_ms,
            device_id=settings.input_device_id,
        ),
        audio_q,
    )

    async def forward_audio() -> None:
        while True:
            chunk = await audio_q.get()
            if chunk is None:
                break
            await client.append_audio(chunk)

    log.info(
        "voicebot starting",
        extra={
            "model": settings.realtime_model,
            "voice": settings.voice_name,
            "sample_rate": settings.sample_rate_hz,
            "summary_trigger": settings.summary_trigger_tokens,
        },
    )

    # Run workers -------------------------------------------------------------
    await mic.start()
    audio_task = asyncio.create_task(forward_audio())
    client_task = asyncio.create_task(client.connect())

    try:
        await client_task
    except asyncio.CancelledError:  # Propagate cancellation after cleanup
        pass
    finally:
        await client.close()
        await mic.stop()
        await player.stop()
        await audio_task


def main() -> None:
    asyncio.run(run())
