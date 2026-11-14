"""Paging helpers for large outputs."""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence, Tuple


def page(items: Sequence[Any], offset: int = 0, limit: int = 100) -> Tuple[List[Any], dict]:
    """Return a slice of *items* plus a small pagination envelope."""
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = 100
    total = len(items)
    start = min(offset, total)
    end = min(start + limit, total)
    sliced = list(items[start:end])
    envelope = {
        "total": total,
        "offset": start,
        "limit": limit,
        "returned": len(sliced),
        "has_more": end < total,
        "next_offset": end if end < total else None,
    }
    return sliced, envelope


def require_paging(offset: int, limit: int, max_limit: int = 4096) -> tuple[int, int]:
    """Normalize paging args; raise ValueError on invalid input."""
    if not isinstance(offset, int) or isinstance(offset, bool):
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            raise ValueError("offset must be an integer >= 0")
    if not isinstance(limit, int) or isinstance(limit, bool):
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise ValueError("limit must be an integer > 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if limit > max_limit:
        limit = max_limit
    return offset, limit


def chunk_bytes(data: bytes, offset: int, limit: int) -> bytes:
    if offset < 0 or offset > len(data):
        raise ValueError("offset out of range")
    if limit < 0:
        raise ValueError("limit must be >= 0")
    end = min(offset + limit, len(data))
    return data[offset:end]