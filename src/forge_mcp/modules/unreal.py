"""Unreal Engine .pak helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from forge_mcp.core.external import find_executable, run_tool
from forge_mcp.core.platform import ensure_dir


def unreal_pak(pak_path: str, action: str = "list", out_dir: Optional[str] = None,
               aes_key: Optional[str] = None, src_dir: Optional[str] = None,
               out_pak: Optional[str] = None) -> Dict[str, Any]:
    up = find_executable("UnrealPak") or find_executable("unrealpak")
    if action in ("list", "extract"):
        if not os.path.isfile(pak_path):
            return {"error": f"file not found: {pak_path}"}
        if up:
            args = [pak_path]
            if action == "list":
                args += ["-List"]
            else:
                d = out_dir or (os.path.dirname(pak_path) + "_extracted")
                ensure_dir(d)
                args += ["-Extract", d]
            if aes_key:
                args += [f"-aes={aes_key}"]
            tr = run_tool(os.path.basename(up), args, timeout=600)
            return {"ok": tr.ok, "stdout": tr.stdout[-4000:], "stderr": tr.stderr[-2000:]}
        try:
            with open(pak_path, "rb") as f:
                magic = f.read(4)
            return {"note": "UnrealPak not found; only header inspected.",
                    "magic": magic.hex(), "size": os.path.getsize(pak_path),
                    "hint": "Install Unreal Engine (UnrealPak) or ue4pak."}
        except Exception as e:
            return {"error": str(e)}
    if action == "pack":
        if not src_dir or not out_pak:
            return {"error": "src_dir and out_pak required for pack"}
        if up:
            tr = run_tool(os.path.basename(up), [out_pak, "-Create=" + src_dir], timeout=600)
            return {"ok": tr.ok, "stdout": tr.stdout[-2000:], "stderr": tr.stderr[-2000:]}
        return {"error": "UnrealPak not found."}
    return {"error": f"unknown action {action}"}