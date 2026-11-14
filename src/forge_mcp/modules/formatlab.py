"""Format lab: entropy, decoding, field guessing, templates."""

from __future__ import annotations

import json
import math
import os
import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple

from forge_mcp.core.platform_utils import read_file, write_file, ensure_dir


def entropy_map(data: bytes, block_size: int = 256) -> List[Dict[str, Any]]:
    out = []
    for off in range(0, len(data), block_size):
        chunk = data[off:off + block_size]
        if not chunk:
            break
        from collections import Counter
        c = Counter(chunk)
        total = len(chunk)
        ent = 0.0
        for n in c.values():
            p = n / total
            if p > 0:
                ent -= p * math.log2(p)
        kind = "plain"
        if ent > 7.5:
            kind = "compressed/encrypted"
        elif ent > 6.0:
            kind = "mixed"
        elif ent < 1.0:
            kind = "sparse"
        out.append({"offset": off, "size": len(chunk), "entropy": round(ent, 3), "kind": kind})
    return out


def try_decode(data: bytes, methods: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    methods = methods or ["zlib", "gzip", "lzma", "xor_single", "base64"]
    results = []
    for m in methods:
        try:
            if m == "zlib":
                d = zlib.decompress(data)
                results.append({"method": m, "ok": True, "size": len(d), "preview": d[:64].hex()})
            elif m == "gzip":
                import gzip
                d = gzip.decompress(data)
                results.append({"method": m, "ok": True, "size": len(d), "preview": d[:64].hex()})
            elif m == "lzma":
                import lzma
                d = lzma.decompress(data)
                results.append({"method": m, "ok": True, "size": len(d), "preview": d[:64].hex()})
            elif m == "xor_single":
                best = None
                for k in range(256):
                    dec = bytes(b ^ k for b in data)
                    printable = sum(1 for b in dec if 32 <= b < 127 or b in (9, 10, 13))
                    score = printable / max(1, len(dec))
                    if score > 0.85:
                        best = (k, dec)
                        break
                if best:
                    k, dec = best
                    results.append({"method": f"xor_single (key={k})", "ok": True,
                                    "size": len(dec), "preview": dec[:64].hex()})
            elif m == "base64":
                import base64
                d = base64.b64decode(data, validate=False)
                results.append({"method": m, "ok": True, "size": len(d), "preview": d[:64].hex()})
            else:
                results.append({"method": m, "ok": False, "error": "unknown method"})
        except Exception as e:
            results.append({"method": m, "ok": False, "error": str(e)[:120]})
    return results


def guess_fields(data: bytes, max_fields: int = 20) -> List[Dict[str, Any]]:
    cands = []
    cur = bytearray(); start = None
    for i, b in enumerate(data):
        if 32 <= b < 127:
            if start is None:
                start = i
            cur.append(b)
        else:
            if len(cur) >= 4 and start is not None:
                cands.append({"kind": "string", "offset": start, "length": len(cur),
                              "value": cur.decode("ascii", "replace")})
            cur = bytearray(); start = None
    if len(cur) >= 4 and start is not None:
        cands.append({"kind": "string", "offset": start, "length": len(cur),
                      "value": cur.decode("ascii", "replace")})
    for off in range(0, len(data) - 3, 1):
        try:
            f = struct.unpack_from("<f", data, off)[0]
            if f != 0 and math.isfinite(f) and abs(f) < 1e9 and abs(f) > 1e-6:
                cands.append({"kind": "float", "offset": off, "value": f})
        except Exception:
            pass
    for off in range(0, len(data) - 3, 4):
        try:
            v = struct.unpack_from("<I", data, off)[0]
            if 1_000_000_000 < v < 2_000_000_000:
                cands.append({"kind": "timestamp", "offset": off, "value": v})
        except Exception:
            pass
    for off in range(0, len(data) - 4, 1):
        try:
            n = struct.unpack_from("<I", data, off)[0]
            if 0 < n < 256 and off + 4 + n <= len(data):
                cands.append({"kind": "length_prefix_u32", "offset": off, "count": n})
        except Exception:
            pass
    return cands[:max_fields * 10]


def write_template(format: str, schema: Dict[str, Any], out_path: str) -> Dict[str, Any]:
    if format == "ksy":
        lines = ["meta:", f"  id: {schema.get('id', 'generated')}", "  endian: le", "seq:"]
        for f in schema.get("fields", []):
            lines.append(f"  - id: {f['name']}")
            t = f.get("type", "u4")
            ksy_type = {"uint8": "u1", "uint16": "u2", "uint32": "u4", "uint64": "u8",
                        "int8": "s1", "int16": "s2", "int32": "s4", "int64": "s8",
                        "float": "f4", "double": "f8", "string": "str"}.get(t, "u1")
            lines.append(f"    type: {ksy_type}")
        content = "\n".join(lines) + "\n"
    elif format == "hexpat":
        lines = []
        for f in schema.get("fields", []):
            t = f.get("type", "u32")
            hexpat_type = {"uint8": "u8", "uint16": "u16", "uint32": "u32", "uint64": "u64",
                           "int8": "s8", "int16": "s16", "int32": "s32", "int64": "s64",
                           "float": "float", "double": "double"}.get(t, "u8")
            lines.append(f"{hexpat_type} {f['name']} @ {f.get('offset', 0)};")
        content = "\n".join(lines) + "\n"
    else:
        return {"error": f"unknown format {format}"}
    ensure_dir(os.path.dirname(out_path) or ".")
    write_file(out_path, content)
    return {"ok": True, "path": out_path, "bytes": len(content)}


def validate_template(template_path: str, sample_files: List[str]) -> Dict[str, Any]:
    if not os.path.isfile(template_path):
        return {"ok": False, "error": "template not found"}
    results = []
    for sf in sample_files:
        if not os.path.isfile(sf):
            results.append({"file": sf, "error": "not found"})
            continue
        size = os.path.getsize(sf)
        results.append({"file": sf, "size": size, "covered": 0, "uncovered": size,
                        "note": "Full validation requires kaitaistruct runtime; template syntax not executed here."})
    return {"template": template_path, "results": results}