# GPT Realtime Agent - Long Conversation

Based on the tutorial [OpenAI Cookbook: Context Summarization with Realtime API](https://github.com/openai/openai-cookbook/blob/main/examples/Context_summarization_with_realtime_api.ipynb)

This repo is intended to serve as a more robust example of a long conversation agent that extends the tutorial example to a more maintainable base repo for further adaptation.

The original script that was converted can be found here: `original/realtime_agent_cli.py`

## Development

Create a virtual environment with Python 3.11 or newer and install the development
dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pre-commit install
```

Run the full suite of checks before committing:

```bash
pre-commit run --all-files
mypy realtime_voicebot
pytest -q
```

## What Works Today

The repository now contains a layered, testable implementation of a realtime voice assistant that goes beyond the original tutorial script. Highlights:

- Streaming playback: Assistant audio is played as `response.audio.delta` arrives using a jitter-buffered `AudioPlayer`.
- Barge-in: On a new `user` item, playback is flushed and the active `response` is canceled for a responsive UX.
- Transport client: `RealtimeClient` encapsulates connect/session.update, send helpers, a receive loop with dispatcher, keepalive, and reconnect with backoff; it resends configuration on resume.
- State and summarization policy: `ConversationState` tracks history; summaries are inserted locally and on the server as `system` messages with pruning of old item IDs. Summarization is language-policy aware (auto/en/force) and defers until transcripts are available.
- Tools/function-calling: Minimal tool registry (`clock`, `http_get`) with advertising in session config and `tool_call` → `tool_result` round‑trip.
- Privacy: PII redaction of emails and US phone numbers before logging or storing transcripts.
- Observability: Structured JSON logging (optional) and basic metrics/timers (queue depths, dropped frames, reconnections, timing).
- CLI and DX: Typer CLI (`voicebot`) with `run`, `devices list`, and `test --fake-server`; ruff + mypy + pytest; pre‑commit hooks; CI for Python 3.11/3.12.

See the Architecture section below for module layout. The original tutorial script remains available under `original/` for reference.

---

## What the script does (at a glance)

* **Goal:** Build an end‑to‑end *voice‑to‑voice* assistant on OpenAI's Realtime API that streams microphone audio in, receives the assistant's audio out, keeps a rolling conversation log, and automatically **summarizes** older turns when the context grows past a threshold.
* **Realtime flow:**

  * Opens a WebSocket to the Realtime endpoint, configures the session (`session.update`), and streams **PCM16** mic frames via `input_audio_buffer.append`.
  * Lets the server's VAD create "user" items. It collects **assistant** audio deltas and plays them once the reply finishes.
  * Manages a local `ConversationState` and, when token usage crosses a threshold, calls a lightweight summarizer model and inserts the summary as a **system** message, pruning old items on the server.
    (Event names and client/server roles mirror the official Realtime docs, e.g., `input_audio_buffer.append`, `response.create`, `response.audio.delta`.) ([OpenAI Platform][1])

### High‑level code structure

* **Config constants:** audio format, thresholds, model names.
* **Data model:** `Turn` dataclass + `ConversationState` (history, pending fetches, summary counters).
* **Audio I/O coroutines:**

  * `mic_to_queue`: captures PCM16 from the mic into an asyncio queue.
  * `queue_to_websocket`: base64‑encodes chunks and sends them as Realtime input events.
* **Realtime loop (`realtime_session`)**:

  * Connects, sets session parameters (voice, modalities, transcription model).
  * Spawns audio tasks and consumes the WebSocket event stream:

    * Tracks user/assistant items and text transcripts.
    * Buffers assistant audio (`response.audio.delta`), plays it on `response.done`.
    * Triggers summarization when `usage.total_tokens` exceeds the threshold.
* **Summarization path:** `run_summary_llm` (calls a small model) + `summarise_and_prune` (create `system` summary, delete old item IDs server‑side).
* **Utilities:** retry fetch of full items, pretty‑print history, simple cleanup on `KeyboardInterrupt`.

---

## Remaining Gaps (to address)

1. **App orchestration**: `app.run` is a stub. It should wire `RealtimeClient`, `MicStreamer → append_audio`, `AudioPlayer`, handler registration, and graceful lifecycle.
2. **Summarizer backend**: `OpenAISummarizer` is a stub; replace with a real OpenAI‑backed implementation that honors the language policy. Keep tests hermetic via mocking.
3. **Transcript backfill**: Implement `conversation.item.retrieved` handler to backfill missing transcripts; ensure summarization defers until backfill completes.
4. **Latency timers wiring**: Wire EoS→first‑delta and first‑delta→playback timers at appropriate events (e.g., `response.created`/first `response.audio.delta`), and add tests.
5. **Error handling**: Add explicit handlers for `response.error` and related failure paths with error taxonomy.
6. **Progressive summary + memory**: Evolve summarization to maintain a short synopsis plus a stable "facts" sheet; integrate `MemoryStore` where useful.

---

## A professional, extensible architecture

A small but deliberate split into layers keeps responsibilities clear:

```bash
realtime_voicebot/
  pyproject.toml
  realtime_voicebot/
    __init__.py
    config.py              # Pydantic settings (env/CLI overrides)
    logging.py             # Structured logging config (stdlog/structlog)
    metrics.py             # Basic counters & timers (Prometheus/OpenTelemetry)
    app.py                 # Orchestrates everything
    transport/
      client.py            # RealtimeClient: connect, send, receive, reconnect
      events.py            # Typed event models; dispatcher
    audio/
      input.py             # MicStreamer (bounded queue, levels, device select)
      output.py            # AudioPlayer (streaming playback, barge-in)
    state/
      conversation.py      # Turn, ConversationState, summarization policies
      memory.py            # Vector memory / preferences store (optional)
    summarization/
      base.py              # Summarizer protocol/interface
      openai_summarizer.py # OpenAI impl; language-aware
    handlers/
      dispatcher.py        # Map 'type' -> handler fn (user/assistant/tool/errors)
      tools.py             # Tool/function-call handlers (calendar, http, etc.)
  tests/
    test_transport.py
    test_state.py
    test_audio_player.py
    test_audio.py
    test_summarization.py
    test_barge_in.py
    test_tools.py
    test_logging_metrics.py
    test_redaction.py
```

### Tool contract

`handlers/tools.py` contains a tiny tool registry. Tools expose a name,
description, JSON schema for arguments, and a Python callable. The registry's
specification is advertised to the Realtime session via ``session.update`` under
the ``tools`` field. When the server emits a ``response.output_item.create``
event with ``item.type == "tool_call"``, the client executes the tool and sends
back a ``tool_result`` item.

Two sample tools are provided:

* ``clock`` – returns the current UTC time.
* ``http_get`` – performs a simple HTTP GET and returns the response text.

### PII redaction

Basic email and US phone number redaction is handled by ``redaction.Redactor``.
When enabled (``Settings.redact_pii``), transcripts are filtered before being
logged or stored in conversation state.

### 1) Configuration & typing

* **Pydantic `BaseSettings`** for all tunables (models, sample rate, VAD mode, thresholds, language policy, device IDs). Environment variables > `.env` > CLI flags.
* Strict **ruff** (via pre‑commit). Add docstrings and `Literal`/`TypedDict`/`Protocol` where appropriate.

### 2) Transport: a real Realtime client

Create a `RealtimeClient` that encapsulates:

* **Connect / handshake / configure** (session.update).
* **Send helpers**: `append_audio(bytes)`, `commit_input()`, `request_response()`, `cancel_response()`.
* **Receive loop** with a **dispatcher** mapping `event["type"]` to handlers (e.g., `response.audio.delta`, `conversation.item.created`, errors).
* **Keepalive & reconnect**: ping/pong, exponential backoff, idempotent resend of config after resume.
* **Backpressure**: a bounded channel for outbound audio; measure drop rate.

> Tip: keep references to current response IDs so you can `response.cancel` when barge‑in is detected (user starts speaking again), a common UX improvement. Event names/flow are defined in the Realtime API docs. ([OpenAI Platform][2])

### 3) Audio pipeline: low latency, barge‑in

* **Input**: use `sounddevice.RawInputStream` with a bounded `asyncio.Queue(maxsize=N)`. Track RMS levels for debugging. Device selection via config.
* **Output (streaming)**: swap `simpleaudio` for a persistent `sounddevice.RawOutputStream`. Feed it from a queue that you fill on each `response.audio.delta` to **start playback immediately**, not at `response.done`. Add a small *jitter buffer* (e.g., 100-150 ms) to avoid underruns.
* **Barge‑in**: when you see a new `conversation.item.created` with role `"user"`, stop/flush playback and optionally `response.cancel` the current TTS. ([OpenAI Platform][3])

### 4) State & summarization

* Make `Turn.role` include `"system"` and store the summary as `"system"` locally for consistency.
* **Policy object** (strategy pattern) for when/how to summarize:

  * Thresholds by *tokens* and/or *turn count*.
  * **Language aware**: detect the dominant language from recent turns and summarize **in that language** (or force English)—no hard‑coded French.
  * **Progressive summarization**: keep a short synopsis + a fact sheet of stable details ("user name", preferences).
* **Summarizer interface**:

```python
class Summarizer(Protocol):
    async def summarize(self, turns: list[Turn], language: str | None) -> str: ...
```

Back it with an OpenAI implementation; keep the model name and prompt in config so you can swap in a local or offline summarizer during tests.

### 5) Event handling & tools

* Central **dispatcher**:

```python
HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {
    "conversation.item.created": on_item_created,
    "conversation.item.retrieved": on_item_retrieved,
    "response.audio.delta": on_audio_delta,
    "response.error": on_response_error,
    "response.done": on_response_done,
}
```

* Add **function/tool calling** support to let the assistant call local "tools" during a Realtime session (e.g., clock, web fetch, calendar). Advertise tools during `session.update`; route tool calls to `handlers.tools`.

### 6) Observability & ops

* **Structured logging** (JSON) with fields: `event_type`, `turn_id`, `response_id`, `latency_ms`, `dropped_frames`, `tokens_total`.
* **Metrics**:

  * Counters: turns, tool calls, reconnections.
  * Timers: *end‑of‑speech → first audio delta*, *first audio delta → playback start*, end‑to‑end turn time.
* **Tracing** (optional): OpenTelemetry spans around the Realtime turn.

### 7) Reliability & safety

* **Error taxonomy**: network vs. protocol vs. audio vs. API. Convert to actionable log messages and user prompts (e.g., "Mic not available").
* **Secrets**: never read API keys directly in code; use env or secret managers.
* **Content filters/redaction plugins** (PII, profanity) before logging or persisting transcripts.

### 8) Developer experience

* **Typer‑based CLI** (CLI flags > environment > `.env`):

```bash
voicebot run --model gpt-4o-realtime-preview --voice shimmer --summary-threshold 4000 --verbose
voicebot devices list
voicebot test --fake-server
```

Use `--verbose` to print the effective settings.

* **Tests**:

  * `pytest-asyncio` unit tests with a **fake Realtime server** (feed canned events; assert state transitions).
  * Audio tests with synthetic PCM (sine waves / silence).
  * Summarization tests verify that pruning keeps the last *K* turns and that the summary lands as a system message.

* **Packaging**: `pyproject.toml`, pinned deps, optional extras (`[extra] audio`), pre‑commit hooks (ruff). GitHub Actions CI: lint, type‑check, test.

---

## Representative code slices

> **Dispatcher + client shell** (clear separation of concerns)

```python
# transport/client.py
class RealtimeClient:
    def __init__(self, url: str, headers: dict[str, str], on_event: Callable[[dict], Awaitable[None]]):
        self.url, self.headers, self.on_event = url, headers, on_event
        self.ws = None
        self._stop = asyncio.Event()

    async def connect(self):
        backoff = 0.5
        while not self._stop.is_set():
            try:
                async with websockets.connect(self.url, extra_headers=self.headers, max_size=1 << 24) as ws:
                    self.ws = ws
                    await self._configure_session()
                    await self._recv_loop(ws)
            except Exception as e:
                logger.exception("ws_error", err=str(e))
                await asyncio.sleep(min(backoff, 10.0))
                backoff *= 1.8

    async def _configure_session(self):
        await self.send({"type": "session.update", "session": {/* voice, modalities, formats, tools */}})

    async def _recv_loop(self, ws):
        async for raw in ws:
            try:
                await self.on_event(json.loads(raw))
            except Exception:
                logger.exception("event_handler_error")

    async def send(self, event: dict):  # add rate limiting/backpressure if needed
        await self.ws.send(json.dumps(event))

    async def close(self):
        self._stop.set()
        if self.ws: await self.ws.close()
```

> **Streaming playback** (low latency)

```python
# audio/output.py
class AudioPlayer:
    def __init__(self, sample_rate=24_000, bytes_per_sample=2):
        self.q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=256)
        self.stream = sd.RawOutputStream(samplerate=sample_rate, channels=1, dtype="int16")
        self._task: asyncio.Task | None = None

    async def start(self):
        self.stream.start()
        self._task = asyncio.create_task(self._pump())

    async def _pump(self):
        # optional warmup jitter buffer
        buf = await self.q.get()
        self.stream.write(buf)
        while True:
            chunk = await self.q.get()
            if chunk is None: break
            self.stream.write(chunk)

    async def write(self, pcm16: bytes):
        try:
            self.q.put_nowait(pcm16)
        except asyncio.QueueFull:
            metrics.audio_dropped_frames.inc()
            logger.warning("audio_drop")

    async def stop(self):
        await self.q.put(None)
        if self._task: await self._task
        self.stream.stop(); self.stream.close()
```

Now, in your event handler:

```python
async def on_audio_delta(ev: dict):
    pcm = base64.b64decode(ev["delta"])
    await player.write(pcm)  # play as it streams
```

> **Summarizer interface** (language‑aware, replaceable)

```python
# summarization/base.py
class Summarizer(Protocol):
    async def summarize(self, turns: list[Turn], language: str | None) -> str: ...
```

```python
# summarization/openai_summarizer.py
class OpenAISummarizer:
    def __init__(self, model: str, temperature: float = 0.2):
        self.model, self.temperature = model, temperature

    async def summarize(self, turns, language):
        text = "\n".join(f"{t.role}: {t.text}" for t in turns if t.text)
        prompt = f"Résumé en {language}" if language else "Summarize"
        # call OpenAI chat completions/responses API; return compact summary string
```

---

## Rollout checklist (status)

Completed:

- [x] Extract layers (transport, audio, state, summarization, handlers)
- [x] Streaming playback + barge‑in + `response.cancel` ([OpenAI Platform][2])
- [x] Language‑aware summarization policy (backend currently stubbed)
- [x] Structured logging, basic metrics; initial latency probes
- [x] Pydantic settings + Typer CLI
- [x] Tests (fake server; audio, barge‑in, summarization, tools, logging)
- [x] Pre‑commit (ruff), CI
- [x] Reliability: reconnect/backoff, keepalive, error taxonomy (initial)
- [x] Tool/function‑calling integration + registry

Remaining (tracked as issues):

- [ ] Wire `app.run` orchestrator (end‑to‑end runtime)
- [ ] Replace `OpenAISummarizer` stub with real client (mock in tests)
- [ ] Transcript backfill: `conversation.item.retrieved` handler + tests
- [ ] Wire latency timers: EoS→first‑delta, first‑delta→playback + tests
- [ ] Expand error handling for `response.error` and edge cases
- [ ] Progressive summary + memory integration

### Roadmap milestones (status)

- M1: Core UX (Streaming + Barge‑in)
  - Status: Completed (streaming playback, barge‑in, response.cancel, basic metrics)
- M2: Summarization + State
  - Status: Partially completed (policy + server‑side system summary + pruning); OpenAI summarizer backend pending; transcript backfill pending
- M3: DX + CI
  - Status: Completed (Typer CLI, pre‑commit, CI, mypy, pytest, fakes)
- M4: Reliability + Tools
  - Status: Partially completed (reconnect/backoff/keepalive, error taxonomy, tools); expand error handling

Optional next: vector memory, richer tool ecosystem, additional redaction strategies.

With this plan, you keep the excellent "straight‑line" demo ergonomics while gaining the pieces that make it robust in production: *abstraction boundaries, observability, and low‑latency UX*.

[1]: https://platform.openai.com/docs/api-reference/realtime-client-events/input_audio_buffer/append?utm_source=chatgpt.com "OpenAI Platform"
[2]: https://platform.openai.com/docs/api-reference/realtime-client-events/response/create?utm_source=chatgpt.com "OpenAI Platform"
[3]: https://platform.openai.com/docs/api-reference/realtime-server-events/response/audio/delta?utm_source=chatgpt.com "OpenAI Platform"
