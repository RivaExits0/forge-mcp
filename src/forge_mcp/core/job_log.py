"""Job log: records every change; drives patch/changelog generation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform import ensure_dir, read_file, write_file


def _log_path(ws_dir: str) -> str:
    ensure_dir(ws_dir)
    return os.path.join(ws_dir, "job_log.jsonl")


def append(ws_dir: str, entry: Dict[str, Any]) -> Dict[str, Any]:
    e = dict(entry)
    e.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    write_file(_log_path(ws_dir), json.dumps(e, ensure_ascii=False) + "\n", binary=False)
    return e


def read(ws_dir: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    path = _log_path(ws_dir)
    if not os.path.isfile(path):
        return []
    rows = []
    for line in read_file(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    if offset < 0:
        offset = 0
    if limit <= 0:
        limit = len(rows)
    return rows[offset:offset + limit]


def count(ws_dir: str) -> int:
    return len(read(ws_dir, limit=10**9, offset=0))


def changelog(ws_dir: str) -> str:
    rows = read(ws_dir, limit=10**9, offset=0)
    lines = ["# Changelog", ""]
    for r in rows:
        ts = r.get("timestamp", "")
        action = r.get("action", r.get("op", "change"))
        target = r.get("target", r.get("file", ""))
        desc = r.get("description", "")
        lines.append(f"- {ts} **{action}** {target} {desc}".rstrip())
    return "\n".join(lines) + "\n"