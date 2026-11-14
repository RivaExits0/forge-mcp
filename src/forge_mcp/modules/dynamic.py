"""Dynamic analysis helpers (Frida scripts). Static generation only; execution requires user consent."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from forge_mcp.core.platform import read_file, write_file, ensure_dir


def frida_script(target: str, hook: str, output_path: Optional[str] = None) -> Dict[str, Any]:
    script = f"""// Forge-Mcp generated Frida script
// Target: {target}
// Hook: {hook}
// Run manually with: frida -n {target} -l <this_file>
Interceptor.attach(Module.findExportByName(null, "{hook}"), {{
    onEnter(args) {{
        console.log("[+] {hook} called");
        for (let i = 0; i < 6; i++) {{
            console.log("    arg" + i + " = " + args[i]);
        }}
    }},
    onLeave(retval) {{
        console.log("    retval = " + retval);
    }}
}});
"""
    if output_path:
        ensure_dir(os.path.dirname(output_path) or ".")
        write_file(output_path, script)
    return {"script": script, "output_path": output_path,
            "run_hint": f"frida -n {target} -l script.js  (requires frida installed)"}


def trace_diff(trace_a: str, trace_b: str) -> Dict[str, Any]:
    a = read_file(trace_a).splitlines()
    b = read_file(trace_b).splitlines()
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return {"divergence_line": i + 1, "a": a[i], "b": b[i],
                    "context_a": a[max(0, i - 3):i + 3],
                    "context_b": b[max(0, i - 3):i + 3]}
    if len(a) != len(b):
        return {"divergence_line": n + 1, "reason": "length differs",
                "len_a": len(a), "len_b": len(b)}
    return {"divergence_line": None, "message": "traces identical"}