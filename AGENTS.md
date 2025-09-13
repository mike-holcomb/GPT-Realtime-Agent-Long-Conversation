# Agents Guide

A practical guide to evolve the simple tutorial script (`original/realtime_agent_cli.py`) into the robust, extensible architecture proposed in the README. Use this as a living document for design decisions, migration steps, and conventions as the codebase grows.

## Goals

- Maintain a realtime voice-to-voice assistant with low latency, resilience, and clear separation of concerns.
- Keep long conversations usable by summarizing and pruning context without losing critical information.
- Enable extension points for tools/function-calling, redaction, memory, and analytics.
- Provide strong developer ergonomics: typing, tests, structured logging, and simple CLI.

## Scope: What is an "Agent" here?

An agent is the orchestrated combination of:
- Transport client to the OpenAI Realtime API (WebSocket),
- Audio I/O pipeline (mic input, streaming speaker output, barge-in),
- Conversation state and summarization policy,
- Event handlers (user/assistant/tool/errors),
- Optional tools/memory/filters,
- CLI entry that wires configuration and lifecycle management.

## Architecture Overview

A minimal but layered package layout (adapt as needed):

```
realtime_voicebot/
  pyproject.toml
  realtime_voicebot/
    __init__.py
    app.py                 # Orchestrates everything
    config.py              # Pydantic settings (env/CLI overrides)
    logging.py             # Structured logging config
    metrics.py             # Basic counters & timers
    transport/
      client.py            # RealtimeClient: connect, send, receive, reconnect
      events.py            # Typed event models; dispatcher helpers
    audio/
      input.py             # MicStreamer (bounded queue)
      output.py            # AudioPlayer (streaming playback, barge-in)
    state/
      conversation.py      # Turn, ConversationState, summarization policies
      memory.py            # Optional vector store/preferences
    summarization/
      base.py              # Summarizer interface
      openai_impl.py       # OpenAI-backed summarizer
    handlers/
      dispatcher.py        # Map event type -> handler
      tools.py             # Tool/function-call handlers
```

Why layering:
- Swap components independently (e.g., different audio backend or summarizer).
- Test each piece in isolation with fakes.
- Contain complexity and keep the main loop readable.

## Migration Plan (from `original/realtime_agent_cli.py`)

Use these steps as an incremental, verifiable path. You do not need to finish all steps to gain value—ship in slices.

1) Extract configuration
- Move constants (sample rate, chunk size, thresholds, model names, voice) into `config.py` using `pydantic.BaseSettings`.
- Support env vars and CLI flags (later via Typer). Keep sensible defaults.

2) Carve out transport client
- Create `transport/client.py` with `RealtimeClient` that encapsulates:
  - connect/handshake (`session.update`),
  - send helpers: `append_audio(bytes)`, `commit_input()`, `create_response()`, `cancel_response()`,
  - receive loop that dispatches events to callbacks,
  - keepalive, reconnect with backoff (preserve session config on resume),
  - bounded outbound audio queue with drop metrics.
- Move `queue_to_websocket` responsibilities into `append_audio` + background sender.

3) Split audio pipeline
- `audio/input.py`: `MicStreamer` that pushes PCM16 chunks into a bounded `asyncio.Queue` (device selection, level meters for debugging).
- `audio/output.py`: `AudioPlayer` that consumes audio deltas and plays immediately (not just after `response.done`). Add a small jitter buffer and barge-in support (stop/flush on new user speech or cancel).

4) Formalize state + summarization
- `state/conversation.py`: `Turn` (including `system`), `ConversationState` (history, pending futures, latest usage), and a `SummaryPolicy` strategy (when/how to summarize: token/turn thresholds, language policy, progressive summary).
- `summarization/base.py`: a `Summarizer` Protocol with `async def summarize(turns, language) -> str`.
- `summarization/openai_impl.py`: implementation backed by a small LLM. Make language configurable (avoid hard-coded French); optionally detect language from recent turns.
- Ensure summaries are stored as `system` both locally and on the server for consistency.

5) Add event dispatching
- `handlers/dispatcher.py`: central mapper of `event["type"]` -> handler function. Keep handlers small and pure when possible.
- Move logic from `realtime_session` into typed handlers:
  - `conversation.item.created` (user VAD): append placeholder, schedule retrieval if transcript missing.
  - `conversation.item.retrieved`: backfill transcripts.
  - `response.audio.delta`: stream to `AudioPlayer`.
  - `response.done`: record assistant message, update usage, maybe summarize.
  - errors: log and classify.

6) Introduce CLI
- Use Typer for commands: `run`, `devices list`, `test --fake-server`, etc.
- Wire settings from `config.py` (env > .env > CLI flags).

7) Add tests and fakes
- Fake Realtime server that feeds canned events to handlers to verify state transitions.
- Audio tests using synthetic PCM (sine, silence) to validate buffer and jitter behavior.
- Summarization tests: ensure pruning keeps last K turns, summary is inserted as `system`, and language policy holds.

## Mapping: Script → Modules

- `mic_to_queue` → `audio/input.py: MicStreamer`
- `queue_to_websocket` → `transport/client.py: append_audio` + sender loop
- `response.audio.delta` buffering → `audio/output.py: AudioPlayer` (streaming)
- `run_summary_llm` → `summarization/openai_impl.py`
- `summarise_and_prune` → `state/conversation.py` (policy) + `summarization/*`
- `fetch_full_item` → `transport/client.py` (retrieve helper) or event-driven backfill
- `realtime_session` → `app.py` (orchestrator) + `handlers/dispatcher.py`

## Realtime Event Flow (reference)

- Outbound:
  - `session.update` (configure voice, modalities, audio formats, transcription model)
  - `input_audio_buffer.append` (base64 PCM16)
  - `input_audio_buffer.commit` (optional, to delineate turns)
  - `response.create` (optional prompt/tooling)
- Inbound (examples):
  - `session.created` – handshake complete
  - `conversation.item.created` – server VAD recognized a user item
  - `conversation.item.retrieved` – full item with transcript
  - `response.audio.delta` – audio bytes for assistant speech
  - `response.done` – assistant’s reply finished, includes usage tokens
  - `response.error` – failures; handle with clear messages

## Configuration Guidelines

- Use `pydantic.BaseSettings` with env aliases:
  - `OPENAI_API_KEY` (required), `OPENAI_BASE_URL` (optional),
  - `VOICE_NAME`, `REALTIME_MODEL`, `TRANSCRIBE_MODEL`,
  - `SAMPLE_RATE_HZ`, `CHUNK_MS`, `SUMMARY_TRIGGER_TOKENS`, `KEEP_LAST_TURNS`,
  - `LANGUAGE_POLICY` (force/en/auto), `INPUT_DEVICE_ID`, `OUTPUT_DEVICE_ID`.
- Allow CLI overrides for common toggles (voice, models, devices, thresholds).

## Summarization Policy

- Trigger: by token usage and/or turn count; debounce to avoid repeated summaries.
- Language: auto-detect from recent turns, or force a configured language.
- Form: short synopsis + stable facts sheet (name, preferences) for continuity.
- Consistency: store as `system` locally and server-side; prune old item IDs on server to reduce context.

## Audio Pipeline

- Input: `sounddevice.RawInputStream` with bounded queue, RMS levels for diagnostics, device selection.
- Output: `sounddevice.RawOutputStream` that starts playback on first `response.audio.delta`. Keep 100–150 ms jitter buffer to avoid underruns.
- Barge-in: pause/cancel current TTS when a new `user` item appears; consider `response.cancel` for a smooth UX.

## Reliability & Observability

- Reconnect with exponential backoff, resume session config on reconnect.
- Keepalive via ping/pong or periodic `session.update` noop.
- Backpressure metrics: dropped audio frames, queue depth.
- Structured logs (JSON) with fields: `event_type`, `turn_id`, `response_id`, `latency_ms`, `tokens_total`, `dropped_frames`.
- Counters (turns, reconnections, tool calls) and timers (EoS→first delta, first delta→playback start, end-to-end).

## Tools and Function-Calling (optional)

- Advertise tools in session config or via response requests.
- Define a minimal tool registry and dispatcher in `handlers/tools.py`.
- Return tool results as items; ensure they’re incorporated into state and can influence subsequent responses.

## Security & Privacy

- Never hard-code secrets; read from env or secret manager.
- Redact PII in logs; allow opt-out logging for transcripts.
- Fail fast on missing audio devices or mic permissions with actionable messages.

## Developer Workflow

- Local run (tutorial): `python original/realtime_agent_cli.py`.
- As the package emerges:
  - `voicebot run --model gpt-4o-realtime-preview --voice shimmer`
  - `voicebot devices list`
- Testing: `pytest -q` (add `pytest-asyncio` for async tests).
- Linting/typing: ruff + mypy (recommend pre-commit hooks).

## Pitfalls & Tips

- Playing audio only after `response.done` increases latency—prefer streaming deltas.
- Summarize only when transcripts are available; otherwise retry retrieval.
- Ensure summaries don’t erase recently referenced facts; keep a fact sheet.
- Bound all queues; measure and surface drops instead of silently ignoring.
- Classify errors (network vs protocol vs audio) to guide user remediation.

## FAQ

- Q: Why store summaries as `system`?
  - A: System role helps keep the assistant on-task and prevents modality drift.
- Q: Do I need a separate summarizer model?
  - A: Not strictly, but a smaller, faster model keeps latency low and cost predictable.
- Q: Can I disable summarization?
  - A: Yes—set the threshold very high or provide a `NullSummarizer` implementation.

## Contributing

- Keep modules focused and typed; prefer small, testable units.
- Add or update tests alongside behavior changes.
- Update this guide when introducing new patterns (e.g., new tool contract).

---

This guide complements the README and should evolve with the code. If something here drifts from reality, update the guide or open an issue so others don’t trip on the same edge cases.

