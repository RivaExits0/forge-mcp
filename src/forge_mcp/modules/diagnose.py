"""Diagnosis helpers: crash logs, deps, conflicts, bisect, load order."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform_utils import read_file


def parse_crash_log(path: str) -> Dict[str, Any]:
    text = read_file(path)
    exc = re.findall(r"(?:Exception|Error)[: ].*", text)[:20]
    modules = re.findall(r"([A-Za-z0-9_.-]+\.(?:dll|so|dylib))", text)
    stacks = re.findall(r"at .+", text)[:40]
    return {"size": len(text), "exceptions": exc, "modules": sorted(set(modules)),
            "stack_lines": stacks, "hint": "Look for first non-system module in stack."}


def check_dependencies(game_dir: str) -> Dict[str, Any]:
    import shutil
    deps = ["vcruntime140.dll", "msvcp140.dll", "d3d11.dll", "xinput1_3.dll",
            "libc.so.6", "libstdc++.so.6", "libm.so.6"]
    found = {}
    for d in deps:
        found[d] = shutil.which(d) is not None
    files = []
    for root, _, fs in os.walk(game_dir):
        for fn in fs:
            files.append(os.path.relpath(os.path.join(root, fn), game_dir))
    return {"dependency_hints": found, "file_count": len(files)}


def find_conflicts(mods: List[str]) -> Dict[str, Any]:
    from collections import Counter
    names = [os.path.basename(m) for m in mods]
    c = Counter(names)
    collisions = {k: v for k, v in c.items() if v > 1}
    return {"mods": mods, "filename_collisions": collisions,
            "note": "Also check overlapping asset paths inside mods."}


def bisect_plan(items: List[str]) -> List[Dict[str, Any]]:
    plan = []
    n = len(items)
    lo, hi = 0, n
    while hi - lo > 1:
        mid = (lo + hi) // 2
        plan.append({"step": len(plan) + 1, "test_subset": items[lo:mid],
                     "action": "disable these and re-test"})
        hi = mid
    plan.append({"step": len(plan) + 1, "test_subset": [items[-1]] if items else [],
                 "action": "single item"})
    return plan


def suggest_load_order(mods: List[str]) -> List[str]:
    priority = {"core": 0, "framework": 1, "library": 2, "content": 3, "patch": 4}
    def key(m):
        low = m.lower()
        for k, v in priority.items():
            if k in low:
                return (v, m)
        return (3, m)
    return sorted(mods, key=key)