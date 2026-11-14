"""Archive unpack/repack with plugin system."""

from __future__ import annotations

import os
import tarfile
import zipfile
from typing import Any, Dict, List, Optional

from forge_mcp.core.external import find_executable, run_tool
from forge_mcp.core.platform import ensure_dir


def unpack_archive(archive_path: str, out_dir: str, password: Optional[str] = None) -> Dict[str, Any]:
    ensure_dir(out_dir)
    if archive_path.lower().endswith(".zip"):
        z = zipfile.ZipFile(archive_path)
        if password:
            z.setpassword(password.encode())
        z.extractall(out_dir)
        return {"ok": True, "format": "zip", "count": len(z.namelist()), "files": z.namelist()[:200]}
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path) as t:
            t.extractall(out_dir)
            return {"ok": True, "format": "tar", "count": len(t.getnames()), "files": t.getnames()[:200]}
    for tool in ("7z", "7zz", "7za", "unrar", "bsdtar"):
        exe = find_executable(tool)
        if exe:
            args = ["x", f"-o{out_dir}", archive_path, "-y"]
            if tool == "unrar":
                args = ["x", "-y", archive_path, out_dir]
            tr = run_tool(tool, args, timeout=600)
            return {"ok": tr.ok, "tool": tool, "stdout": tr.stdout[-2000:], "stderr": tr.stderr[-2000:]}
    return {"error": "unsupported archive or no tool found (install 7z / unrar / bsdtar)"}


def repack_archive(src_dir: str, out_path: str, format: str = "zip") -> Dict[str, Any]:
    if format == "zip":
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(src_dir):
                for fn in files:
                    full = os.path.join(root, fn)
                    arc = os.path.relpath(full, src_dir)
                    z.write(full, arc)
        return {"ok": True, "format": "zip", "path": out_path}
    if format == "tar":
        with tarfile.open(out_path, "w") as t:
            t.add(src_dir, arcname=".")
        return {"ok": True, "format": "tar", "path": out_path}
    exe = find_executable("7z") or find_executable("7zz") or find_executable("7za")
    if exe:
        tr = run_tool(os.path.basename(exe), ["a", out_path, f"{src_dir}/*"], timeout=600)
        return {"ok": tr.ok, "tool": os.path.basename(exe), "path": out_path,
                "stderr": tr.stderr[-2000:]}
    return {"error": f"unsupported format {format} (install 7z for more formats)"}