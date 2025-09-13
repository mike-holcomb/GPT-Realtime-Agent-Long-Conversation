from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Event:
    type: str
    payload: dict


def get_type(ev: dict) -> str:
    return ev.get("type", "")
