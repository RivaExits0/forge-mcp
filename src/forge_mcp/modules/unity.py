"""Unity helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform_utils import read_file, write_file, ensure_dir


def unity_assets(path: str, action: str = "list", entry: Optional[str] = None,
                 out_dir: Optional[str] = None, data: Optional[bytes] = None) -> Dict[str, Any]:
    try:
        import UnityPy
    except Exception as e:
        return {"error": f"UnityPy not installed: {e}. pip install UnityPy",
                "hint": "https://github.com/K0lb3/UnityPy"}
    if not os.path.isfile(path):
        return {"error": f"file not found: {path}"}
    env = UnityPy.load(path)
    objects = []
    for obj in env.objects:
        try:
            objects.append({"path_id": obj.path_id, "type": str(obj.type.name) if hasattr(obj.type, "name") else str(obj.type)})
        except Exception:
            objects.append({"path_id": getattr(obj, "path_id", None), "type": str(type(obj))})
    if action == "list":
        return {"count": len(objects), "objects": objects[:500]}
    if action == "extract":
        out = out_dir or os.path.join(os.path.dirname(path), "extracted")
        ensure_dir(out)
        n = 0
        for obj in env.objects:
            try:
                d = obj.read()
                name = getattr(d, "name", None) or f"obj_{obj.path_id}"
                raw = obj.get_raw_data() if hasattr(obj, "get_raw_data") else b""
                write_file(os.path.join(out, f"{name}.bin"), raw, binary=True)
                n += 1
            except Exception:
                continue
        return {"extracted": n, "out_dir": out}
    if action == "replace" and entry and data is not None:
        for obj in env.objects:
            try:
                d = obj.read()
                if getattr(d, "name", None) == entry:
                    obj.save(data)
                    env.save(path + ".modified")
                    return {"ok": True, "saved": path + ".modified"}
            except Exception:
                continue
        return {"error": f"entry not found: {entry}"}
    return {"error": f"unknown action {action}"}