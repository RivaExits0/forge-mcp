"""Schema-driven table editing.

Supported schema shape (JSON or TOML-loaded dict):

    {
      "count": 3,                         # optional; else read from count_offset
      "count_offset": 0,                  # u32 holding the entry count
      "entry_size": 16,
      "base_offset": 0,                   # where contiguous entries start
      "offset_table": {"offset": 8, "count": 3},   # optional u32 offset array
      "fields": [
        {"name": "id", "offset": 0, "type": "uint32", "size": 4},
        {"name": "hp", "offset": 4, "type": "float",   "size": 4}
      ]
    }
"""

from __future__ import annotations

import json
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

from forge_mcp.core.platform import read_file


_TYPE_FMT = {
    "int8": ("<b", 1), "uint8": ("<B", 1),
    "int16": ("<h", 2), "uint16": ("<H", 2),
    "int32": ("<i", 4), "uint32": ("<I", 4),
    "int64": ("<q", 8), "uint64": ("<Q", 8),
    "float": ("<f", 4), "double": ("<d", 8),
    "string": (None, 0),
}


def load_schema(path: Optional[str]) -> Dict[str, Any]:
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _entry_size(schema: Dict[str, Any]) -> int:
    if schema.get("entry_size"):
        return int(schema["entry_size"])
    fields = schema.get("fields", [])
    return max((f["offset"] + f.get("size", 4) for f in fields), default=0)


def _entry_offsets(data: bytes, schema: Dict[str, Any]) -> Tuple[List[int], int]:
    esize = _entry_size(schema)
    if esize <= 0:
        return [], 0
    ot = schema.get("offset_table")
    count = schema.get("count")
    if count is None and schema.get("count_offset") is not None:
        co = int(schema["count_offset"])
        if co + 4 <= len(data):
            count = struct.unpack_from("<I", data, co)[0]
    if ot:
        toff = int(ot.get("offset", 0))
        tcount = int(ot.get("count", count or 0))
        offsets = []
        for i in range(tcount):
            p = toff + i * 4
            if p + 4 > len(data):
                break
            offsets.append(struct.unpack_from("<I", data, p)[0])
        return offsets, len(offsets)
    base = int(schema.get("base_offset", 0))
    if count is None:
        count = max(0, (len(data) - base) // esize)
    return [base + i * esize for i in range(count)], count


def _decode_field(raw: bytes, typ: str) -> Any:
    if typ == "string":
        return raw.split(b"\x00")[0].decode("utf-8", "replace")
    fmt = _TYPE_FMT.get(typ)
    if fmt and fmt[0]:
        if len(raw) < fmt[1]:
            return None
        return struct.unpack(fmt[0], raw[:fmt[1]])[0]
    return raw.hex()


def _encode_field(val: Any, typ: str, size: int) -> bytes:
    if typ == "string":
        b = str(val).encode("utf-8")[:size - 1] + b"\x00"
        return b.ljust(size, b"\x00")
    fmt = _TYPE_FMT.get(typ)
    if fmt and fmt[0]:
        try:
            return struct.pack(fmt[0], val)
        except (struct.error, TypeError, ValueError):
            raise ValueError(f"value {val!r} does not fit type {typ}")
    if isinstance(val, str):
        b = bytes.fromhex(val.replace(" ", ""))
        return b.ljust(size, b"\x00")[:size]
    if isinstance(val, (bytes, bytearray)):
        return bytes(val).ljust(size, b"\x00")[:size]
    raise ValueError(f"cannot encode {val!r} as {typ}")


def list_entries(data: bytes, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    offsets, count = _entry_offsets(data, schema)
    fields = schema.get("fields", [])
    out = []
    for i, off in enumerate(offsets):
        entry: Dict[str, Any] = {"index": i, "offset": off}
        for fld in fields:
            fo = off + fld.get("offset", 0)
            sz = fld.get("size", 4)
            entry[fld["name"]] = _decode_field(bytes(data[fo:fo + sz]), fld.get("type", "bytes"))
        out.append(entry)
    return out


def clone_entry(data: bytearray, schema: Dict[str, Any], index: int) -> Dict[str, Any]:
    esize = _entry_size(schema)
    offsets, count = _entry_offsets(bytes(data), schema)
    if index < 0 or index >= count:
        return {"error": f"index out of range (0..{count - 1})"}
    src = offsets[index]
    if src + esize > len(data):
        return {"error": "entry extends past end of file"}
    chunk = bytes(data[src:src + esize])

    ot = schema.get("offset_table")
    if ot:
        toff = int(ot.get("offset", 0))
        insert_at = toff + count * 4
        data[insert_at:insert_at] = b"\x00" * 4
        for i in range(count):
            old_off = offsets[i]
            new_off = old_off + 4 if old_off >= insert_at else old_off
            struct.pack_into("<I", data, toff + i * 4, new_off)
        new_entry_off = len(data)
        if new_entry_off + esize > len(data):
            data.extend(b"\x00" * (new_entry_off + esize - len(data)))
        data[new_entry_off:new_entry_off + esize] = chunk
        struct.pack_into("<I", data, insert_at, new_entry_off)
        new_off = new_entry_off
    else:
        base = int(schema.get("base_offset", 0))
        new_off = base + count * esize
        if new_off + esize > len(data):
            data.extend(b"\x00" * (new_off + esize - len(data)))
        data[new_off:new_off + esize] = chunk

    if schema.get("count_offset") is not None:
        struct.pack_into("<I", data, int(schema["count_offset"]), count + 1)
    if ot and "count" in ot:
        ot["count"] = count + 1

    return {"ok": True, "new_index": count, "offset": new_off, "size": esize,
            "count": count + 1}


def edit_fields(data: bytearray, schema: Dict[str, Any], index: int,
                changes: Dict[str, Any]) -> Dict[str, Any]:
    offsets, count = _entry_offsets(bytes(data), schema)
    if index < 0 or index >= count:
        return {"error": f"index out of range (0..{count - 1})"}
    base = offsets[index]
    field_map = {f["name"]: f for f in schema.get("fields", [])}
    applied = []
    for name, val in changes.items():
        f = field_map.get(name)
        if not f:
            applied.append({"field": name, "error": "unknown field"})
            continue
        off = base + f.get("offset", 0)
        sz = f.get("size", 4)
        raw = _encode_field(val, f.get("type", "bytes"), sz)
        old = bytes(data[off:off + sz])
        data[off:off + sz] = raw
        applied.append({"field": name, "old": old.hex(), "new": raw.hex(),
                        "offset": off})
    return {"ok": True, "index": index, "offset": base, "applied": applied}


def find_references(data: bytes, index: int, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs = []
    for e in list_entries(data, schema):
        for k, v in e.items():
            if k in ("index", "offset"):
                continue
            if v == index:
                refs.append({"index": e["index"], "field": k, "value": v,
                             "offset": e["offset"]})
    return refs


def rebuild_offsets(data: bytearray, schema: Dict[str, Any]) -> Dict[str, Any]:
    esize = _entry_size(schema)
    offsets, count = _entry_offsets(bytes(data), schema)
    ot = schema.get("offset_table")
    if not ot:
        return {"ok": False, "error": "schema has no offset_table; nothing to rebuild",
                "entry_size": esize, "count": count}
    toff = int(ot.get("offset", 0))
    new_offsets = []
    cursor = toff + count * 4
    for off in offsets:
        chunk = bytes(data[off:off + esize])
        if cursor + esize > len(data):
            data.extend(b"\x00" * (cursor + esize - len(data)))
        data[cursor:cursor + esize] = chunk
        new_offsets.append(cursor)
        cursor += esize
    for i, no in enumerate(new_offsets):
        struct.pack_into("<I", data, toff + i * 4, no)
    return {"ok": True, "entry_size": esize, "count": count, "new_offsets": new_offsets,
            "data_end": cursor}


def validate_table(data: bytes, schema: Dict[str, Any]) -> Dict[str, Any]:
    esize = _entry_size(schema)
    issues: List[str] = []
    if esize <= 0:
        return {"ok": False, "error": "entry_size unknown", "issues": ["entry_size unknown"]}
    offsets, count = _entry_offsets(data, schema)
    for f in schema.get("fields", []):
        if f["offset"] + f.get("size", 4) > esize:
            issues.append(f"field {f['name']} exceeds entry_size")
    for i, off in enumerate(offsets):
        if off + esize > len(data):
            issues.append(f"entry {i} at {off} exceeds file size {len(data)}")
    ot = schema.get("offset_table")
    if ot:
        toff = int(ot.get("offset", 0))
        if toff + count * 4 > len(data):
            issues.append("offset table exceeds file size")
        if offsets != sorted(offsets):
            issues.append("offset table is not sorted")
        seen = set()
        for i, off in enumerate(offsets):
            if off in seen:
                issues.append(f"duplicate offset for entry {i}")
            seen.add(off)
    return {"ok": not issues, "entry_size": esize, "count": count,
            "offsets": offsets[:100], "file_size": len(data), "issues": issues}