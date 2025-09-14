from __future__ import annotations

import sys
import types

from typer.testing import CliRunner

from realtime_voicebot import cli


def test_run_overrides(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run(settings):
        captured["settings"] = settings

    monkeypatch.setattr("realtime_voicebot.app.run", fake_run)
    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "run",
            "--model",
            "foo",
            "--voice",
            "bar",
            "--input-device",
            "1",
            "--output-device",
            "2",
            "--summary-threshold",
            "123",
            "--verbose",
        ],
    )
    assert result.exit_code == 0
    settings = captured["settings"]
    assert settings.realtime_model == "foo"
    assert settings.voice_name == "bar"
    assert settings.input_device_id == 1
    assert "foo" in result.stdout


def test_devices_list(monkeypatch):
    fake_sd = types.SimpleNamespace(
        query_devices=lambda: [
            {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Spk", "max_input_channels": 0, "max_output_channels": 2},
        ]
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    runner = CliRunner()
    result = runner.invoke(cli.app, ["devices", "list"])
    assert result.exit_code == 0
    assert "Mic" in result.stdout
    assert "Spk" in result.stdout


def test_fake_server(monkeypatch):
    runner = CliRunner()
    result = runner.invoke(cli.app, ["test", "--fake-server"])
    assert result.exit_code == 0
    assert "Fake server exchange completed" in result.stdout
