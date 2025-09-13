from __future__ import annotations

import json
import logging
import os


class JsonFormatter(logging.Formatter):
    """Very small JSON formatter for structured logs."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - short
        payload = {
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "event_type": getattr(record, "event_type", record.getMessage()),
            "turn_id": getattr(record, "turn_id", None),
            "response_id": getattr(record, "response_id", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "tokens_total": getattr(record, "tokens_total", None),
            "dropped_frames": getattr(record, "dropped_frames", None),
        }
        return json.dumps(payload, default=str)


def configure_logging(level: str | int | None = None) -> None:
    """Configure logging.

    Default format is human friendly, but when ``LOG_FORMAT=json`` is set the
    output becomes structured JSON containing common observability fields.
    """

    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    fmt = os.getenv("LOG_FORMAT", "plain").lower()
    if fmt == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.basicConfig(level=level, handlers=[handler], force=True)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )
