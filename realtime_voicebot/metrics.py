from __future__ import annotations

import time
from contextlib import contextmanager


class Counter:
    def __init__(self) -> None:
        self.value = 0

    def inc(self, n: int = 1) -> None:
        self.value += n


class Gauge:
    def __init__(self) -> None:
        self.value = 0

    def set(self, v: int) -> None:
        self.value = v


class Timer:
    def __init__(self) -> None:
        self.last_ms: float | None = None
        self._start: float | None = None

    def start(self) -> None:
        self._start = time.perf_counter()

    def stop(self) -> float | None:
        if self._start is None:
            return None
        end = time.perf_counter()
        self.last_ms = (end - self._start) * 1000
        self._start = None
        return self.last_ms

    @contextmanager
    def time(self):  # noqa: ANN201 (to keep it lightweight)
        self.start()
        yield
        self.stop()


# Example metrics placeholders
turns_total = Counter()
reconnections_total = Counter()
audio_frames_dropped_total = Counter()
eos_to_first_delta_ms = Timer()
first_delta_to_playback_ms = Timer()
audio_input_queue_depth = Gauge()
audio_output_queue_depth = Gauge()
