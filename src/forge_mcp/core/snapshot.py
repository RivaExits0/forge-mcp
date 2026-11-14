"""Snapshot / undo support."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform_utils import ensure_dir, copy_file, read_file, write_file, sha256_file


def _snap_dir(ws_dir: str) -> str:
    d = os.path.join(ws_dir, "snapshots")
    ensure_dir(d)
    return d


def take_snapshot(ws_dir: str, target_path: str, reason: str = "") -> str:
    """Copy *target_path* into a snapshot; return snapshot id."""
    snap_dir = _snap_dir(ws_dir)
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    h = hashlib.sha1(target_path.encode()).hexdigest()[:6]
    sid = f"{sid}_{h}"
    dest = os.path.join(snap_dir, sid)
    ensure_dir(dest)
    base = os.path.basename(target_path)
    copy_file(target_path, os.path.join(dest, base))
    meta = {
        "id": sid,
        "target": target_path,
        "basename": base,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256_file(target_path),
    }
    write_file(os.path.join(dest, "meta.json"), json.dumps(meta, indent=2))
    return sid


def list_snapshots(ws_dir: str) -> List[Dict[str, Any]]:
    snap_dir = _snap_dir(ws_dir)
    out = []
    for name in sorted(os.listdir(snap_dir)):
        p = os.path.join(snap_dir, name)
        if not os.path.isdir(p):
            continue
        mp = os.path.join(p, "meta.json")
        if os.path.isfile(mp):
            out.append(json.loads(read_file(mp)))
        else:
            out.append({"id": name})
    return out


def restore_snapshot(ws_dir: str, snapshot_id: str) -> str:
    """Restore a snapshot over its original target path. Returns target path."""
    snap_dir = _snap_dir(ws_dir)
    dest = os.path.join(snap_dir, snapshot_id)
    if not os.path.isdir(dest):
        raise FileNotFoundError(f"snapshot not found: {snapshot_id}")
    meta = json.loads(read_file(os.path.join(dest, "meta.json")))
    target = meta["target"]
    base = meta["basename"]
    src = os.path.join(dest, base)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    ensure_dir(os.path.dirname(target))
    copy_file(src, target)
    return target


def latest_snapshot_for(ws_dir: str, target_path: str) -> Optional[str]:
    snaps = list_snapshots(ws_dir)
    matches = [s for s in snaps if s.get("target") == target_path]
    if not matches:
        return None
    matches.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return matches[0].get("id")