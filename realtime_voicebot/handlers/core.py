from __future__ import annotations

import base64
import logging

from ..audio.output import AudioPlayer
from ..transport.client import RealtimeClient

logger = logging.getLogger(__name__)


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
    event: dict, client: RealtimeClient, player: AudioPlayer
) -> None:
    item = event.get("item", {})
    if item.get("role") != "user":
        return
    response_id = client.active_response_id
    if response_id:
        await player.flush()
        await client.cancel_active_response()
        logger.info("barge_in", extra={"response_id": response_id, "turn_id": item.get("id")})
