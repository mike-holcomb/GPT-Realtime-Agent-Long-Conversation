from __future__ import annotations

import base64
import logging

from ..audio.output import AudioPlayer
from ..state.conversation import ConversationState, SummaryPolicy, Turn
from ..summarization.base import Summarizer
from ..transport.client import RealtimeClient

logger = logging.getLogger(__name__)


async def handle_response_created(event: dict, client: RealtimeClient) -> None:
    """Record the currently active response when it's created."""

    response = event.get("response", {})
    response_id = response.get("id") or event.get("response_id")
    if response_id:
        client.active_response_id = response_id


async def handle_response_audio_delta(
    event: dict, client: RealtimeClient, player: AudioPlayer
) -> None:
    response_id = event.get("response_id")
    if response_id is None or client.is_canceled(response_id):
        return
    client.active_response_id = response_id
    audio_b64 = event.get("audio")
    if audio_b64:
        await player.feed(base64.b64decode(audio_b64))


async def handle_conversation_item_created(
    event: dict,
    client: RealtimeClient,
    player: AudioPlayer,
    state: ConversationState | None = None,
) -> None:
    item = event.get("item", {})
    if item.get("role") != "user":
        return

    item_id = item.get("id")
    transcript: str | None = None
    for content in item.get("content", []):
        transcript = content.get("transcript") or content.get("text")
        if transcript:
            break

    if state is not None and item_id:
        existing = next((turn for turn in state.history if turn.item_id == item_id), None)
        if existing is None:
            state.append(Turn(role="user", item_id=item_id, text=transcript))
        elif transcript:
            existing.text = state.redact(transcript) if state.redact else transcript

    response_id = client.active_response_id
    if response_id:
        await player.flush()
        await client.cancel_active_response()
        logger.info("barge_in", extra={"response_id": response_id, "turn_id": item_id})


async def handle_response_done(
    event: dict,
    client: RealtimeClient,
    state: ConversationState,
    summarizer: Summarizer,
    policy: SummaryPolicy,
) -> None:
    """Handle ``response.done`` by recording assistant text and summarizing."""

    resp = event.get("response", {})
    response_id = resp.get("id") or event.get("response_id")
    if client.active_response_id == response_id:
        client.active_response_id = None
    if response_id:
        client.clear_canceled(response_id)
    for item in resp.get("output", []):
        if item.get("role") == "assistant":
            txt = item.get("content", [{}])[0].get("transcript")
            state.append(Turn(role="assistant", item_id=item.get("id", ""), text=txt))

    usage = resp.get("usage", {})
    state.latest_tokens = usage.get("total_tokens", 0)

    if policy.should_summarize(state):
        language = policy.determine_language(state.history)
        await state.summarize_and_prune(
            summarizer,
            keep_last_turns=policy.keep_last_turns,
            language=language,
            client=client,
        )


async def handle_response_error(event: dict, client: RealtimeClient) -> None:
    response_id = event.get("response_id") or event.get("response", {}).get("id")
    if client.active_response_id == response_id:
        client.active_response_id = None
    if response_id:
        client.clear_canceled(response_id)


async def handle_conversation_item_retrieved(
    event: dict,
    client: RealtimeClient | None,
    state: ConversationState,
    summarizer: Summarizer,
    policy: SummaryPolicy,
) -> None:
    """Backfill transcripts and retry summarization if conditions are met."""

    item = event.get("item", {})
    item_id = item.get("id") or event.get("item_id")
    if not item_id:
        return

    transcript: str | None = None
    for content in item.get("content", []):
        transcript = content.get("transcript") or content.get("text")
        if transcript:
            break

    if not transcript:
        return

    updated = False
    redacted = state.redact(transcript) if state.redact and transcript else transcript
    for turn in state.history:
        if turn.item_id == item_id:
            turn.text = redacted
            updated = True
            break

    if not updated:
        role = item.get("role") or "user"
        state.append(Turn(role=role, item_id=item_id, text=transcript))
        updated = True

    if policy.should_summarize(state):
        language = policy.determine_language(state.history)
        await state.summarize_and_prune(
            summarizer,
            keep_last_turns=policy.keep_last_turns,
            language=language,
            client=client,
        )
