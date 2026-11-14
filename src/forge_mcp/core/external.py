"""Wrappers for external tools (Ghidra, apktool, jadx, ...).

Every external invocation goes through subprocess with a timeout and an
argument list (never a shell string). Missing tools produce a helpful
error message with an install hint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

from forge_mcp.core.platform_utils import find_executable, run_cmd, IS_WINDOWS, EXE_EXT


@dataclass
class ToolResult:
    ok: bool
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    missing: Optional[str] = None  # name of missing tool if any


INSTALL_HINTS = {
    "ghidra": "Set GHIDRA_HOME to your Ghidra install (contains support/analyzeHeadless). Download: https://github.com/NationalSecurityAgency/ghidra/releases",
    "apktool": "Install apktool: https://apktool.org/docs/install",
    "jadx": "Install jadx: https://github.com/skylot/jadx/releases",
    "il2cppdumper": "Il2CppDumper: https://github.com/Perfare/Il2CppDumper/releases",
    "frida": "pip install frida frida-tools",
    "unrealpak": "UnrealPak ships with Unreal Engine; or use https://github.com/panzi/u4pak",
    "xdelta3": "Install xdelta3: https://github.com/jmacd/xdelta",
    "bsdiff": "Install bsdiff/bspatch.",
    "aapt2": "Android SDK build-tools (aapt2).",
    "apksigner": "Android SDK build-tools (apksigner).",
    "zipalign": "Android SDK build-tools (zipalign).",
}


def missing_message(name: str) -> str:
    hint = INSTALL_HINTS.get(name, "Install the tool and ensure it is on PATH.")
    return f"{name} not found. {hint}"


def run_tool(name: str, args: Sequence[str], timeout: int = 300,
             cwd: Optional[str] = None) -> ToolResult:
    """Run an external tool by logical name."""
    exe = find_executable(name)
    if not exe:
        return ToolResult(ok=False, command=[name, *args], returncode=127,
                          stdout="", stderr=missing_message(name), missing=name)
    cmd = [exe, *args]
    rc, out, err, timed_out = run_cmd(cmd, timeout=timeout, cwd=cwd)
    return ToolResult(ok=rc == 0, command=cmd,
                      returncode=rc,
                      stdout=out, stderr=err,
                      timed_out=timed_out)


def run_executable(path: str, args: Sequence[str], timeout: int = 300,
                   cwd: Optional[str] = None) -> ToolResult:
    if not os.path.isfile(path):
        return ToolResult(ok=False, command=[path, *args], returncode=127,
                          stdout="", stderr=f"executable not found: {path}")
    cmd = [path, *args]
    rc, out, err, timed_out = run_cmd(cmd, timeout=timeout, cwd=cwd)
    return ToolResult(ok=rc == 0, command=cmd,
                      returncode=rc,
                      stdout=out, stderr=err,
                      timed_out=timed_out)


def java_available() -> bool:
    return shutil.which("java") is not None


def run_jar(jar_path: str, args: Sequence[str], timeout: int = 300,
            cwd: Optional[str] = None) -> ToolResult:
    if not java_available():
        return ToolResult(ok=False, command=["java", "-jar", jar_path, *args],
                          returncode=127, stdout="", stderr="java not found on PATH")
    return run_executable("java", ["-jar", jar_path, *args], timeout=timeout, cwd=cwd)


def get_apktool_jar() -> Optional[str]:
    """Find apktool.jar if apktool is a wrapper script."""
    exe = find_executable("apktool")
    if not exe:
        return None
    if exe.endswith(".jar"):
        return exe
    # if it's a shell script / batch, look next to it
    base = os.path.dirname(exe)
    for cand in ("apktool.jar", "apktool_2.9.3.jar"):
        p = os.path.join(base, cand)
        if os.path.isfile(p):
            return p
    return None