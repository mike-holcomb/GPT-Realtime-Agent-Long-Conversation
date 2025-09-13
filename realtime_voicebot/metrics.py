from __future__ import annotations

import time
from contextlib import contextmanager


class Counter:
    def __init__(self) -> None:
        self.value = 0

    def inc(self, n: int = 1) -> None:
        self.value += n


class Timer:
    def __init__(self) -> None:
        self.last_ms: float | None = None

    @contextmanager
    def time(self):  # noqa: ANN201 (to keep it lightweight)
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self.last_ms = (end - start) * 1000


# Example metrics placeholders
turns_total = Counter()
reconnections_total = Counter()
audio_frames_dropped_total = Counter()
eos_to_first_delta_ms = Timer()
