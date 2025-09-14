from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from contextlib import asynccontextmanager

import typer

from .app import run as app_run
from .config import Settings
from .transport.client import RealtimeClient

app = typer.Typer(help="Realtime voicebot utility")

devices_app = typer.Typer(help="Inspect audio devices")
app.add_typer(devices_app, name="devices")


@app.command()
def run(
    model: str | None = typer.Option(None, help="Realtime model to use"),
    voice: str | None = typer.Option(None, help="Voice name"),
    input_device: int | None = typer.Option(None, help="Input device ID"),
    output_device: int | None = typer.Option(None, help="Output device ID"),
    summary_threshold: int | None = typer.Option(
        None, help="Token threshold to trigger summarization"
    ),
    verbose: bool = typer.Option(False, help="Print effective settings"),
) -> None:
    """Run the voicebot orchestrator."""
    overrides: dict[str, object] = {}
    if model is not None:
        overrides["realtime_model"] = model
    if voice is not None:
        overrides["voice_name"] = voice
    if input_device is not None:
        overrides["input_device_id"] = input_device
    if output_device is not None:
        overrides["output_device_id"] = output_device
    if summary_threshold is not None:
        overrides["summary_trigger_tokens"] = summary_threshold
    settings = Settings(**overrides)
    if verbose:
        typer.echo(settings.model_dump_json(indent=2))
    asyncio.run(app_run(settings=settings))


@devices_app.command("list")
def list_devices() -> None:
    """Print available audio devices."""
    sd = importlib.import_module("sounddevice")
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        inp = dev["max_input_channels"]
        out = dev["max_output_channels"]
        typer.echo(f"{idx}: {dev['name']} (in={inp} out={out})")


@app.command()
def test(fake_server: bool = typer.Option(False, help="Run against a fake server")) -> None:
    """Run a short scripted exchange for testing."""

    if not fake_server:
        typer.echo("No tests specified")
        return

    events = [
        {"type": "session.created"},
        {"type": "response.done", "response_id": "1"},
    ]

    class _FakeWebSocket:
        def __init__(self, queued: list[dict]):
            self._queue = asyncio.Queue[str | None]()
            for ev in queued:
                self._queue.put_nowait(json.dumps(ev))
            self._queue.put_nowait(None)

        def __aiter__(self) -> _FakeWebSocket:
            return self

        async def __anext__(self) -> str:
            msg = await self._queue.get()
            if msg is None:
                raise StopAsyncIteration
            return msg

        async def send(self, msg: str) -> None:
            # For the fake exchange we simply ignore messages sent by the client.
            return None

        async def close(self) -> None:  # pragma: no cover - no-op
            return None

    @asynccontextmanager
    async def _fake_connect(*args, **kwargs):  # pragma: no cover - helper wrapper
        ws = _FakeWebSocket(events)
        try:
            yield ws
        finally:
            await ws.close()

    async def main() -> None:
        fake_ws = types.SimpleNamespace(connect=_fake_connect)
        sys.modules["websockets"] = fake_ws
        received: list[dict] = []

        async def on_event(ev: dict) -> None:
            received.append(ev)
            if ev.get("type") == "response.done":
                await client.close()

        client = RealtimeClient("ws://fake", {}, on_event)
        await client.connect()
        typer.echo("Fake server exchange completed")

    asyncio.run(main())


if __name__ == "__main__":  # pragma: no cover
    app()
