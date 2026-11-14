"""Hex / offset operations."""

from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

from forge_mcp.core.platform import read_file


def hex_view(data: bytes, offset: int = 0, limit: int = 256) -> str:
    chunk = chunk_bytes(data, offset, limit)
    lines = []
    base = offset
    for i in range(0, len(chunk), 16):
        row = chunk[i:i + 16]
        hexpart = " ".join(f"{b:02x}" for b in row)
        hexpart = hexpart.ljust(16 * 3 - 1)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{base + i:08x}  {hexpart}  |{asc}|")
    return "\n".join(lines)


def chunk_bytes(data: bytes, offset: int, limit: int) -> bytes:
    if offset < 0 or offset > len(data):
        raise ValueError("offset out of range")
    if limit < 0:
        raise ValueError("limit must be >= 0")
    end = min(offset + limit, len(data))
    return data[offset:end]


def parse_pattern(pat: str) -> Tuple[bytes, bytes]:
    pat = pat.strip()
    if " " in pat:
        toks = pat.split()
    else:
        toks = []
        i = 0
        while i < len(pat):
            if pat[i] == "?":
                toks.append("??")
                i += 2
            else:
                toks.append(pat[i:i + 2])
                i += 2
    needle = bytearray()
    mask = bytearray()
    for t in toks:
        t = t.strip()
        if t in ("?", "??", "??"):
            needle.append(0)
            mask.append(0)
        elif len(t) == 1:
            needle.append(0)
            mask.append(0)
        else:
            needle.append(int(t, 16))
            mask.append(0xFF)
    return bytes(needle), bytes(mask)


def search_bytes(data: bytes, needle: bytes, mask: Optional[bytes] = None,
                 start: int = 0) -> List[int]:
    if mask is None:
        mask = bytes([0xFF] * len(needle))
    if len(needle) == 0:
        return []
    res = []
    n = len(data)
    m = len(needle)
    i = start
    while i <= n - m:
        ok = True
        for j in range(m):
            if mask[j] and (data[i + j] & mask[j]) != (needle[j] & mask[j]):
                ok = False
                break
        if ok:
            res.append(i)
        i += 1
    return res


def hex_search(data: bytes, query: str, mode: str = "auto",
               offset: int = 0, limit: int = 1000) -> Dict[str, Any]:
    if mode == "auto":
        q = query.strip()
        if all(c in "0123456789abcdefABCDEF ?" for c in q) and len(q.replace(" ", "")) >= 2:
            mode = "aob"
        else:
            mode = "string"
    if mode in ("bytes", "aob", "wildcard"):
        needle, mask = parse_pattern(query)
        hits = search_bytes(data, needle, mask, start=offset)
    elif mode == "string":
        nb = query.encode("utf-8", errors="surrogateescape")
        hits = search_bytes(data, nb, None, start=offset)
    else:
        raise ValueError(f"unknown mode {mode}")
    sliced, env = page_list(hits, offset=offset, limit=limit)
    return {"mode": mode, "query": query, "hits": sliced, "pagination": env}


def page_list(items, offset: int, limit: int):
    total = len(items)
    start = min(offset, total)
    end = min(start + limit, total)
    return list(items[start:end]), {
        "total": total, "offset": start, "limit": limit,
        "returned": end - start, "has_more": end < total,
        "next_offset": end if end < total else None,
    }


def diff_files(a: bytes, b: bytes) -> List[Dict[str, Any]]:
    out = []
    n = max(len(a), len(b))
    runs = []
    start = None
    for i in range(n):
        va = a[i] if i < len(a) else None
        vb = b[i] if i < len(b) else None
        diff = va != vb
        if diff and start is None:
            start = i
        if (not diff or i == n - 1) and start is not None:
            end = i if not diff else i + 1
            runs.append((start, end))
            start = None
    for s, e in runs:
        out.append({
            "offset": s,
            "length": e - s,
            "a": a[s:e].hex(),
            "b": b[s:e].hex(),
        })
    return out


def value_scan(data_before: bytes, data_after: bytes, value_type: str = "int32") -> List[Dict[str, Any]]:
    fmts = {
        "int8": ("<b", 1), "uint8": ("<B", 1),
        "int16": ("<h", 2), "uint16": ("<H", 2),
        "int32": ("<i", 4), "uint32": ("<I", 4),
        "int64": ("<q", 8), "uint64": ("<Q", 8),
        "float": ("<f", 4), "double": ("<d", 8),
    }
    if value_type not in fmts:
        raise ValueError(f"unknown value_type {value_type}")
    fmt, size = fmts[value_type]
    n = min(len(data_before), len(data_after))
    hits = []
    off = 0
    while off + size <= n:
        try:
            vb = struct.unpack(fmt, data_before[off:off + size])[0]
            va = struct.unpack(fmt, data_after[off:off + size])[0]
        except struct.error:
            off += 1
            continue
        if vb != va:
            hits.append({"offset": off, "before": vb, "after": va, "type": value_type})
        off += size
    return hits


def offset_calc(rva: Optional[int] = None, va: Optional[int] = None,
                file_offset: Optional[int] = None, image_base: int = 0,
                sections: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    sections = sections or []
    def rva_to_file(rva_val):
        for s in sections:
            va_s = s["virtual_address"]
            vs = s.get("virtual_size", s.get("size", 0))
            if va_s <= rva_val < va_s + vs:
                return rva_val - va_s + s["raw_offset"]
        return None
    def file_to_rva(fo):
        for s in sections:
            ro = s["raw_offset"]
            rs = s.get("raw_size", s.get("size", 0))
            if ro <= fo < ro + rs:
                return fo - ro + s["virtual_address"]
        return None
    out: Dict[str, Any] = {}
    if va is not None:
        rva = va - image_base
        out["rva"] = rva
    if rva is not None:
        out["rva"] = rva
        out["va"] = rva + image_base
        fo = rva_to_file(rva)
        out["file_offset"] = fo
    if file_offset is not None:
        out["file_offset"] = file_offset
        r = file_to_rva(file_offset)
        out["rva_from_file"] = r
        if r is not None:
            out["va_from_file"] = r + image_base
    return out


def hex_patch(data: bytearray, offset: int, new_bytes: bytes, dry_run: bool = True) -> Dict[str, Any]:
    if offset < 0 or offset + len(new_bytes) > len(data):
        return {"error": "offset/length out of range", "size": len(data)}
    old = bytes(data[offset:offset + len(new_bytes)])
    preview = {"offset": offset, "old": old.hex(), "new": new_bytes.hex(), "length": len(new_bytes)}
    if dry_run:
        return {"dry_run": True, **preview}
    data[offset:offset + len(new_bytes)] = new_bytes
    return {"dry_run": False, "applied": True, **preview}


def pointer_chain(data: bytes, base_addr: int, chain: List[int],
                  is_64: bool = True) -> Dict[str, Any]:
    import struct
    fmt = "<Q" if is_64 else "<I"
    size = 8 if is_64 else 4
    cur = base_addr
    steps = []
    for off in chain:
        addr = cur + off
        steps.append({"at": hex(addr), "offset": off})
    return {"base": hex(base_addr), "chain": chain, "steps": steps,
            "note": "Static resolution requires a memory map; use runtime/Frida for live deref."}


def checksum_fix(data: bytearray, algo: str = "crc32", field_offset: int = 0,
                 field_size: int = 4, region: Optional[Tuple[int, int]] = None,
                 endian: str = "little") -> Dict[str, Any]:
    import zlib
    if region is None:
        region = (0, len(data))
    s, e = region
    region_bytes = bytes(data[s:e])
    if algo == "crc32":
        val = zlib.crc32(region_bytes) & 0xFFFFFFFF
    elif algo == "adler32":
        val = zlib.adler32(region_bytes) & 0xFFFFFFFF
    elif algo == "sum8":
        val = sum(region_bytes) & 0xFF
    elif algo == "sum16":
        val = sum(region_bytes) & 0xFFFF
    elif algo == "sum32":
        val = sum(region_bytes) & 0xFFFFFFFF
    else:
        raise ValueError(f"unknown algo {algo}")
    size = field_size
    packed = val.to_bytes(size, "little" if endian == "little" else "big")
    old = bytes(data[field_offset:field_offset + size])
    data[field_offset:field_offset + size] = packed
    return {"algo": algo, "value": val, "old": old.hex(), "new": packed.hex(),
            "field_offset": field_offset}