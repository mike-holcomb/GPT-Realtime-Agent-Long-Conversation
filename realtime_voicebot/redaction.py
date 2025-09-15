"""Simple PII redaction utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

# Basic patterns for emails and US phone numbers
EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+")
PHONE_RE = re.compile(r"\b(?:\d{3}[ -]?){2}\d{4}\b")


@dataclass
class Redactor:
    """Redact configured PII patterns from text."""

    enabled: bool = True
    patterns: Iterable[re.Pattern[str]] = (EMAIL_RE, PHONE_RE)
    replacement: str = "[REDACTED]"

    def redact(self, text: str) -> str:
        """Return ``text`` with any PII patterns removed."""
        if not self.enabled:
            return text
        redacted = text
        for pattern in self.patterns:
            redacted = pattern.sub(self.replacement, redacted)
        return redacted
