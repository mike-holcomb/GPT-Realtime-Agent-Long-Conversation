from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Classification for error logging."""

    NETWORK = "network"
    PROTOCOL = "protocol"
    AUDIO = "audio"
    API = "api"
