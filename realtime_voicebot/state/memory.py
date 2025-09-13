from __future__ import annotations


class MemoryStore:
    """Placeholder for a preferences/facts store.

    In future iterations, this might be a simple dict, SQLite, or a vector DB
    with embeddings for semantic recall.
    """

    def __init__(self) -> None:
        self.facts: dict[str, str] = {}

    def set(self, key: str, value: str) -> None:
        self.facts[key] = value

    def get(self, key: str) -> str | None:
        return self.facts.get(key)
