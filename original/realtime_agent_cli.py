#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Realtime Voice Bot with Automatic Context Summarization
------------------------------------------------------
Builds an end-to-end voice assistant using OpenAI's Realtime API. It:
  • Streams microphone audio to the Realtime endpoint (voice-to-voice)
  • Prints transcripts and plays assistant audio in real time
  • Maintains a conversation log (user/assistant turns)
  • Automatically summarizes older turns when the context window grows

Prerequisites
-------------
  • Python >= 3.10
  • OPENAI_API_KEY in your environment
  • Microphone and speakers (grant OS permissions when prompted)

Install (run once):
  pip install --upgrade openai websockets sounddevice simpleaudio numpy

Run:
  python realtime_context_summarizer.py

Notes:
  • Default summary threshold is low for demo (2k tokens). Raise for production.
  • Summary is inserted as a SYSTEM message to avoid modality drift.
  • Extracted from [OpenAI Cookbook: Context Summarization with Realtime API](https://github.com/openai/openai-cookbook/blob/main/examples/Context_summarization_with_realtime_api.ipynb)
"""

from __future__ import annotations

# --------------------------- Standard library --------------------------- #
import asyncio
import base64
import json
import os
import sys
from dataclasses import dataclass, field
from typing import List, Literal

# ----------------------------- Third-party ------------------------------ #
import numpy as np  # noqa: F401  # (used by sounddevice buffers; keep import)
import sounddevice as sd          # microphone capture
import simpleaudio                # speaker playback
import websockets                 # WebSocket client
import openai                     # OpenAI Python SDK >= 1.14.0

# ------------------------------ Safety key ------------------------------ #
openai.api_key = os.getenv("OPENAI_API_KEY", "")
if not openai.api_key:
    raise ValueError(
        "OPENAI_API_KEY not found – set it in your environment before running."
    )

# ---------------------------- Tunable config ---------------------------- #
SAMPLE_RATE_HZ: int    = 24_000   # Required for pcm16
CHUNK_DURATION_MS: int = 40       # ~40ms chunks from the mic
BYTES_PER_SAMPLE: int  = 2        # pcm16 = 2 bytes/sample
SUMMARY_TRIGGER: int   = 2_000    # Summarize when context >= this (demo value)
KEEP_LAST_TURNS: int   = 2        # Keep these most-recent turns verbatim
SUMMARY_MODEL: str     = "gpt-4o-mini"  # Lightweight, fast summarizer
REALTIME_MODEL: str    = "gpt-4o-realtime-preview"  # Realtime voice model
VOICE_NAME: str        = "shimmer"

# --------------------------- Conversation state ------------------------- #
@dataclass
class Turn:
    """One utterance in the dialogue (user or assistant)."""
    role: Literal["user", "assistant"]
    item_id: str                     # Server-assigned identifier
    text: str | None = None          # Filled once transcript is ready


@dataclass
class ConversationState:
    """All mutable data the session needs – nothing more, nothing less."""
    history: List[Turn] = field(default_factory=list)                 # Ordered log
    waiting: dict[str, asyncio.Future] = field(default_factory=dict)  # Pending fetches
    summary_count: int = 0

    latest_tokens: int = 0     # Window size after last reply
    pending_summary_tokens: int = 0
    summarising: bool = False  # Guard to prevent concurrent summaries

    def record_usage(self, total_tokens: int | None) -> None:
        tokens = int(total_tokens or 0)
        self.latest_tokens = tokens
        if tokens > self.pending_summary_tokens:
            self.pending_summary_tokens = tokens

    def should_summarize(self, threshold_tokens: int, keep_last_turns: int) -> bool:
        effective_tokens = max(self.latest_tokens, self.pending_summary_tokens)
        return (
            effective_tokens >= threshold_tokens
            and len(self.history) > keep_last_turns
            and not self.summarising
        )


def print_history(state: ConversationState) -> None:
    """Pretty-print the running transcript so far."""
    print("—— Conversation so far ———————————————")
    for turn in state.history:
        text_preview = (turn.text or "").strip().replace("\n", " ")
        print(f"[{turn.role:<9}] {text_preview}  ({turn.item_id})")
    print("——————————————————————————————————————————")


# ----------------------------- Audio → Queue ---------------------------- #
async def mic_to_queue(pcm_queue: asyncio.Queue[bytes]) -> None:
    """Capture raw PCM-16 mic audio and push ~CHUNK_DURATION_MS chunks to queue.

    Parameters
    ----------
    pcm_queue: asyncio.Queue[bytes]
        Destination queue for PCM-16 frames (little-endian int16).
    """
    blocksize = int(SAMPLE_RATE_HZ * CHUNK_DURATION_MS / 1000)

    def _callback(indata, _frames, _time, status):
        if status:
            print("⚠️", status, file=sys.stderr)
        try:
            pcm_queue.put_nowait(bytes(indata))
        except asyncio.QueueFull:
            # Drop if upstream can't keep up.
            pass

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE_HZ,
        blocksize=blocksize,
        dtype="int16",
        channels=1,
        callback=_callback,
    ):
        try:
            # Keep task alive until cancelled by caller
            await asyncio.Event().wait()
        finally:
            print("⏹️  Mic stream closed.")


# --------------------------- Queue → WebSocket -------------------------- #
b64 = lambda blob: base64.b64encode(blob).decode()


async def queue_to_websocket(pcm_queue: asyncio.Queue[bytes], ws) -> None:
    """Read audio chunks from queue and send as JSON events."""
    try:
        while (chunk := await pcm_queue.get()) is not None:
            await ws.send(
                json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": b64(chunk),
                })
            )
    except websockets.ConnectionClosed:
        print("WebSocket closed – stopping uploader")


# -------------------------- Summarization LLM --------------------------- #
async def run_summary_llm(text: str) -> str:
    """Call a lightweight model to summarize `text` into one French paragraph."""
    def _call():
        return openai.chat.completions.create(
            model=SUMMARY_MODEL,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarise in French the following conversation in one "
                        "concise paragraph so it can be used as context for future dialogue."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )

    resp = await asyncio.to_thread(_call)
    return resp.choices[0].message.content.strip()


async def summarise_and_prune(ws, state: ConversationState) -> None:
    """Summarize old turns, insert summary (SYSTEM), delete old items server-side."""
    state.summarising = True
    window_tokens = max(state.latest_tokens, state.pending_summary_tokens)
    print(f"⚠️  Token window ≈{window_tokens} ≥ {SUMMARY_TRIGGER}. Summarising…")

    old_turns = state.history[:-KEEP_LAST_TURNS]
    recent_turns = state.history[-KEEP_LAST_TURNS:]
    convo_text = "\n".join(f"{t.role}: {t.text}" for t in old_turns if t.text)

    if not convo_text:
        print("Nothing to summarise (transcripts still pending).")
        state.summarising = False
        return

    summary_text = await run_summary_llm(convo_text)
    state.summary_count += 1
    summary_id = f"sum_{state.summary_count:03d}"

    # Replace local history with summary + recent
    state.history[:] = [Turn("assistant", summary_id, summary_text)] + recent_turns
    print_history(state)

    # Create SYSTEM summary on server at the root
    await ws.send(
        json.dumps(
            {
                "type": "conversation.item.create",
                "previous_item_id": "root",
                "item": {
                    "id": summary_id,
                    "type": "message",
                    "role": "system",
                    "content": [{"type": "input_text", "text": summary_text}],
                },
            }
        )
    )

    # Delete old items that were summarized
    for turn in old_turns:
        await ws.send(json.dumps({"type": "conversation.item.delete", "item_id": turn.item_id}))

    print(f"✅ Summary inserted ({summary_id})")
    state.latest_tokens = 0
    state.pending_summary_tokens = 0
    state.summarising = False


# ------------------------ Fetch full item (retry) ----------------------- #
async def fetch_full_item(ws, item_id: str, state: ConversationState, attempts: int = 1):
    """Ask server for a full conversation item; retry up to 5x if transcript is null."""
    if item_id in state.waiting:
        return await state.waiting[item_id]

    fut = asyncio.get_running_loop().create_future()
    state.waiting[item_id] = fut

    await ws.send(json.dumps({"type": "conversation.item.retrieve", "item_id": item_id}))
    item = await fut

    # If transcript still missing, retry (max 5×)
    content = item.get("content", [{}])[0]
    if attempts < 5 and not content.get("transcript"):
        await asyncio.sleep(0.4 * attempts)
        return await fetch_full_item(ws, item_id, state, attempts + 1)

    state.waiting.pop(item_id, None)
    return item


# --------------------------- Realtime session --------------------------- #
async def realtime_session(model: str = REALTIME_MODEL, voice: str = VOICE_NAME, enable_playback: bool = True) -> None:
    """Connect to Realtime, spawn audio tasks, and process incoming events."""
    state = ConversationState()

    pcm_queue: asyncio.Queue[bytes] = asyncio.Queue()
    assistant_audio: List[bytes] = []

    url = f"wss://api.openai.com/v1/realtime?model={model}"
    headers = {"Authorization": f"Bearer {openai.api_key}", "OpenAI-Beta": "realtime=v1"}

    async with websockets.connect(url, extra_headers=headers, max_size=1 << 24) as ws:
        # Wait for session.created
        while json.loads(await ws.recv())["type"] != "session.created":
            pass
        print("session.created ✅")

        # Configure session
        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "voice": voice,
                        "modalities": ["audio", "text"],
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "input_audio_transcription": {"model": "gpt-4o-transcribe"},
                    },
                }
            )
        )

        # Launch background tasks: mic capture → queue → websocket
        mic_task = asyncio.create_task(mic_to_queue(pcm_queue))
        upl_task = asyncio.create_task(queue_to_websocket(pcm_queue, ws))

        print("🎙️ Speak now (Ctrl-C to quit)…")

        try:
            async for event_raw in ws:
                event = json.loads(event_raw)
                etype = event["type"]

                # User turn placeholder (created by VAD)
                if etype == "conversation.item.created" and event["item"]["role"] == "user":
                    item = event["item"]
                    text = None
                    if item.get("content"):
                        text = item["content"][0].get("transcript")
                    state.history.append(Turn("user", item["id"], text))
                    if text is None:
                        asyncio.create_task(fetch_full_item(ws, item["id"], state))

                # Transcript retrieved
                elif etype == "conversation.item.retrieved":
                    content = event["item"]["content"][0]
                    for t in state.history:
                        if t.item_id == event["item"]["id"]:
                            t.text = content.get("transcript")
                            break

                # Assistant audio chunk
                elif etype == "response.audio.delta":
                    assistant_audio.append(base64.b64decode(event["delta"]))

                # Assistant finished reply
                elif etype == "response.done":
                    for item in event["response"].get("output", []):
                        if item.get("role") == "assistant":
                            txt = item["content"][0].get("transcript")
                            state.history.append(Turn("assistant", item["id"], txt))
                    usage = event["response"].get("usage", {})
                    state.record_usage(usage.get("total_tokens"))
                    window_tokens = max(state.latest_tokens, state.pending_summary_tokens)
                    print(f"—— response.done  (window ≈{window_tokens} tokens) ——")
                    print_history(state)

                    # Backfill any missing user transcripts
                    for turn in state.history:
                        if turn.role == "user" and turn.text is None and turn.item_id not in state.waiting:
                            asyncio.create_task(fetch_full_item(ws, turn.item_id, state))

                    # Playback buffered audio once reply completes
                    if enable_playback and assistant_audio:
                        simpleaudio.play_buffer(
                            b"".join(assistant_audio),
                            1,
                            BYTES_PER_SAMPLE,
                            SAMPLE_RATE_HZ,
                        )
                        assistant_audio.clear()

                    # Summarize if context too large
                    if state.should_summarize(SUMMARY_TRIGGER, KEEP_LAST_TURNS):
                        asyncio.create_task(summarise_and_prune(ws, state))

                # Resolve any pending fetch futures when server responds
                elif etype == "conversation.item" and event.get("event") == "retrieved":
                    # (Some SDKs emit this pattern; kept for compatibility.)
                    item = event.get("item", {})
                    fut = state.waiting.get(item.get("id"))
                    if fut and not fut.done():
                        fut.set_result(item)

        except KeyboardInterrupt:
            print("\nStopping…")
        finally:
            mic_task.cancel()
            await pcm_queue.put(None)
            await upl_task


# ------------------------------- Entrypoint ------------------------------ #
if __name__ == "__main__":
    asyncio.run(realtime_session())
