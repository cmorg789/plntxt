"""Shared cursor-based pagination helpers."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException


def encode_cursor(ts: datetime, id: UUID) -> str:
    """Build a cursor string from a timestamp and UUID."""
    return f"{ts.isoformat()}_{id}"


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Parse a cursor string of the form '{created_at_iso}_{id}'.

    Raises HTTPException(400) on invalid format.
    """
    sep = cursor.rfind("_")
    if sep == -1:
        raise HTTPException(status_code=400, detail="Invalid cursor format")
    ts_part = cursor[:sep]
    id_part = cursor[sep + 1:]
    try:
        ts = datetime.fromisoformat(ts_part)
        uid = UUID(id_part)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor format") from exc
    return ts, uid
