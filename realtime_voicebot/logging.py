from __future__ import annotations

import logging
import os


def configure_logging(level: str | int | None = None) -> None:
    """Configure basic structured-ish logging.

    Uses a concise, single-line format suitable for terminals. For production,
    consider structlog or JSON logging.
    """

    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

