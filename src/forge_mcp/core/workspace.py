"""Workspace management: per-game folders, backups, path safety."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform_utils import (
    safe_relpath as _safe_relpath,
    ensure_dir,
    copy_file,
    sha256_file as _sha256_file,
    read_file,
    write_file,
    normalize_path,
)


class PathTraversalError(ValueError):
    pass


def safe_path(workspace: str, *parts: str) -> str:
    """Resolve a path inside workspace; reject traversal."""
    base = os.path.realpath(workspace)
    target = os.path.realpath(os.path.join(base, *parts))
    if target != base and not target.startswith(base + os.sep):
        raise PathTraversalError(f"path escapes workspace: {os.path.join(*parts)}")
    return target


@dataclass
class Workspace:
    root: str
    name: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    files: Dict[str, str] = field(default_factory=dict)  # logical name -> relative path
    versions: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def dir(self) -> str:
        return os.path.join(self.root, self.name)

    def ensure(self) -> None:
        ensure_dir(self.dir)
        ensure_dir(os.path.join(self.dir, "originals"))
        ensure_dir(os.path.join(self.dir, "work"))
        ensure_dir(os.path.join(self.dir, "snapshots"))
        ensure_dir(os.path.join(self.dir, "profiles"))

    def save_meta(self) -> None:
        self.ensure()
        p = os.path.join(self.dir, "workspace.json")
        write_file(p, json.dumps({
            "name": self.name,
            "created_at": self.created_at,
            "files": self.files,
            "versions": self.versions,
            "meta": self.meta,
        }, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, root: str, name: str) -> "Workspace":
        ws = cls(root=root, name=name)
        ws.ensure()
        p = os.path.join(ws.dir, "workspace.json")
        if os.path.isfile(p):
            d = json.loads(read_file(p))
            ws.created_at = d.get("created_at", ws.created_at)
            ws.files = d.get("files", {})
            ws.versions = d.get("versions", [])
            ws.meta = d.get("meta", {})
        return ws


class WorkspaceManager:
    def __init__(self, root: Optional[str] = None):
        self.root = root or os.path.join(os.getcwd(), "forge-workspaces")
        ensure_dir(self.root)

    def create(self, name: str) -> Workspace:
        ws = Workspace(root=self.root, name=name)
        ws.ensure()
        ws.save_meta()
        return ws

    def open(self, name: str) -> Workspace:
        return Workspace.load(self.root, name)

    def list(self) -> List[str]:
        out = []
        for n in sorted(os.listdir(self.root)):
            if os.path.isdir(os.path.join(self.root, n)) and os.path.isfile(os.path.join(self.root, n, "workspace.json")):
                out.append(n)
        return out

    def import_file(self, ws: Workspace, src_path: str, logical: str = "main") -> str:
        """Copy a file into workspace as read-only original + working copy."""
        if not os.path.isfile(src_path):
            raise FileNotFoundError(src_path)
        ws.ensure()
        safe = os.path.basename(src_path)
        orig_dir = os.path.join(ws.dir, "originals")
        work_dir = os.path.join(ws.dir, "work")
        orig_path = os.path.join(orig_dir, safe)
        work_path = os.path.join(work_dir, safe)
        copy_file(src_path, orig_path)
        copy_file(src_path, work_path)
        # mark original read-only
        try:
            if hasattr(os, "chmod"):
                os.chmod(orig_path, 0o444)
        except OSError:
            pass
        ws.files[logical] = os.path.relpath(work_path, ws.dir)
        ws.save_meta()
        return work_path

    def work_path(self, ws: Workspace, logical: str = "main") -> str:
        rel = ws.files.get(logical)
        if not rel:
            raise KeyError(f"no file registered under logical name {logical!r}")
        p = os.path.join(ws.dir, rel)
        if not os.path.isfile(p):
            raise FileNotFoundError(p)
        return p

    def original_path(self, ws: Workspace, logical: str = "main") -> Optional[str]:
        rel = ws.files.get(logical)
        if not rel:
            return None
        name = os.path.basename(rel)
        p = os.path.join(ws.dir, "originals", name)
        return p if os.path.isfile(p) else None


def sha256_file(path: str) -> str:
    return _sha256_file(path)