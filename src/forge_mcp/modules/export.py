"""Export helpers: patches and Cheat Engine tables."""

from __future__ import annotations

import os
import struct
from typing import Any, Dict, List, Optional

from forge_mcp.core.external import find_executable, run_tool
from forge_mcp.core.platform import read_file, write_file, ensure_dir


def export_patch(original: bytes, modified: bytes, out_path: str, fmt: str = "ips") -> Dict[str, Any]:
    if fmt == "ips":
        out = bytearray(b"PATCH")
        n = max(len(original), len(modified))
        runs = []
        start = None
        for idx in range(n):
            a = original[idx] if idx < len(original) else None
            b = modified[idx] if idx < len(modified) else None
            if a != b:
                if start is None:
                    start = idx
            else:
                if start is not None:
                    runs.append((start, idx))
                    start = None
        if start is not None:
            runs.append((start, n))
        for s, e in runs:
            off = s
            size = e - s
            if size == 0:
                continue
            if off > 0xFFFFFF:
                return {"error": "offset too large for IPS"}
            out += struct.pack(">I", off)[1:]
            out += struct.pack(">H", size)
            out += modified[s:e]
        out += b"EOF"
        ensure_dir(os.path.dirname(out_path) or ".")
        write_file(out_path, out, binary=True)
        return {"ok": True, "format": "ips", "path": out_path, "hunks": len(runs), "bytes": len(out)}
    if fmt == "xdelta":
        import tempfile
        d = tempfile.mkdtemp()
        a = os.path.join(d, "orig.bin"); b = os.path.join(d, "mod.bin")
        write_file(a, original, binary=True)
        write_file(b, modified, binary=True)
        xdelta = find_executable("xdelta3") or find_executable("xdelta")
        if not xdelta:
            return {"error": "xdelta3 not found. https://github.com/jmacd/xdelta"}
        tr = run_tool(os.path.basename(xdelta), ["-e", "-s", a, b, out_path], timeout=300)
        return {"ok": tr.ok, "format": "xdelta", "path": out_path, "stderr": tr.stderr[-1000:]}
    return {"error": f"unsupported format {fmt}"}


def make_trainer_table(addresses: List[Dict[str, Any]], out_path: str) -> Dict[str, Any]:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<CheatTable>", "  <CheatEntries>"]
    for a in addresses:
        addr = a.get("address", "0")
        desc = a.get("description", "value")
        typ = a.get("type", "4 Bytes")
        lines.append("    <CheatEntry>")
        lines.append(f"      <Description>{desc}</Description>")
        lines.append(f"      <VariableType>{typ}</VariableType>")
        lines.append(f"      <Address>{addr}</Address>")
        lines.append("    </CheatEntry>")
    lines.append("  </CheatEntries>")
    lines.append("</CheatTable>")
    content = "\n".join(lines)
    ensure_dir(os.path.dirname(out_path) or ".")
    write_file(out_path, content)
    return {"ok": True, "path": out_path, "entries": len(addresses)}