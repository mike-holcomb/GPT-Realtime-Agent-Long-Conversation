import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from realtime_voicebot.logging import configure_logging
from realtime_voicebot.metrics import Timer, audio_frames_dropped_total


def test_json_logging_structure(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging()
    logging.getLogger(__name__).info(
        "sample",
        extra={
            "event_type": "test_event",
            "turn_id": "t1",
            "response_id": "r1",
            "latency_ms": 1.2,
            "tokens_total": 3,
            "dropped_frames": 4,
        },
    )
    captured = capsys.readouterr().err.strip().splitlines()[-1]
    data = json.loads(captured)
    for key in [
        "event_type",
        "turn_id",
        "response_id",
        "latency_ms",
        "tokens_total",
        "dropped_frames",
    ]:
        assert key in data


def test_counter_and_timer_update():
    audio_frames_dropped_total.value = 0
    audio_frames_dropped_total.inc()
    assert audio_frames_dropped_total.value == 1
    timer = Timer()
    timer.start()
    time.sleep(0.001)
    timer.stop()
    assert timer.last_ms is not None and timer.last_ms > 0
