"""Cross-platform path & process helpers."""

from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

IS_WINDOWS = sys.platform.startswith("win")
EXE_EXT = ".exe" if IS_WINDOWS else ""


def normalize_path(path: str) -> str:
    """Normalize path for current platform."""
    return os.path.normpath(path)


def join_paths(*parts: str) -> str:
    return os.path.join(*parts)


def is_executable(path: str) -> bool:
    if IS_WINDOWS:
        return os.path.isfile(path) and path.lower().endswith((".exe", ".bat", ".cmd", ".ps1"))
    return os.path.isfile(path) and os.access(path, os.X_OK)


def which_ex(name: str) -> Optional[str]:
    """shutil.which that also tries with .exe on Windows."""
    path = shutil.which(name)
    if path:
        return path
    if IS_WINDOWS and not name.lower().endswith(".exe"):
        return shutil.which(name + ".exe")
    return None


def find_executable(name: str, extra_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Find an executable in PATH, env vars, or common install dirs."""
    env_map = {
        "ghidra": "GHIDRA_HOME",
        "apktool": "APKTOOL_HOME",
        "jadx": "JADX_HOME",
    }
    if name in env_map:
        base = os.environ.get(env_map[name])
        if base:
            candidates = _candidate_paths(base, name)
            for c in candidates:
                if is_executable(c):
                    return c

    path = which_ex(name)
    if path:
        return path

    common_dirs = _common_install_dirs()
    if extra_dirs:
        common_dirs.extend(extra_dirs)
    for d in common_dirs:
        c = os.path.join(d, name + EXE_EXT)
        if is_executable(c):
            return c

    if name == "ghidra":
        for root in _search_roots():
            for dirpath, _, files in os.walk(root):
                if f"analyzeHeadless{EXE_EXT}" in files:
                    return os.path.join(dirpath, f"analyzeHeadless{EXE_EXT}")
    return None


def _candidate_paths(base: str, name: str) -> List[str]:
    if name == "ghidra":
        return [
            os.path.join(base, "support", f"analyzeHeadless{EXE_EXT}"),
            os.path.join(base, f"analyzeHeadless{EXE_EXT}"),
        ]
    return [
        os.path.join(base, "bin", name + EXE_EXT),
        os.path.join(base, name + EXE_EXT),
    ]


def _common_install_dirs() -> List[str]:
    dirs = [
        "/opt", "/usr/local/bin", "/usr/bin",
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/bin"),
    ]
    if IS_WINDOWS:
        pf = os.environ.get("ProgramFiles", "C:\\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        localapp = os.environ.get("LOCALAPPDATA", "")
        appdata = os.environ.get("APPDATA", "")
        dirs.extend([
            pf, pf86,
            os.path.join(localapp, "Programs") if localapp else "",
            os.path.join(appdata, "npm") if appdata else "",
            "C:\\Tools", "C:\\Bin",
        ])
    return [d for d in dirs if d]


def _search_roots() -> List[str]:
    if IS_WINDOWS:
        return [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.path.expanduser("~"),
        ]
    return ["/opt", "/usr/local", "/usr/share", os.path.expanduser("~")]


def run_cmd(cmd: Sequence[str], timeout: int = 300, cwd: Optional[str] = None,
            env: Optional[dict] = None) -> Tuple[int, str, str, bool]:
    """Run command with timeout; returns (rc, stdout, stderr, timed_out)."""
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env={**os.environ, **(env or {})}
        )
        return proc.returncode, proc.stdout or "", proc.stderr or "", False
    except subprocess.TimeoutExpired as e:
        return -1, (e.stdout or "" if isinstance(e.stdout, str) else ""), \
               f"timed out after {timeout}s", True
    except Exception as e:
        return -1, "", str(e), False


def make_executable(path: str) -> None:
    """Best-effort chmod +x on Unix."""
    if not IS_WINDOWS:
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass


def read_file(path: str, binary: bool = False) -> str | bytes:
    mode = "rb" if binary else "r"
    with open(path, mode, encoding=None if binary else "utf-8") as f:
        return f.read()


def write_file(path: str, data: str | bytes, binary: bool = False) -> None:
    mode = "wb" if binary else "w"
    with open(path, mode, encoding=None if binary else "utf-8") as f:
        f.write(data)


def sha256_file(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def copy_file(src: str, dst: str) -> None:
    shutil.copy2(src, dst)


def safe_relpath(workspace: str, target: str) -> str:
    """Resolve target inside workspace; raise ValueError on traversal."""
    base = os.path.realpath(workspace)
    tgt = os.path.realpath(target)
    if tgt != base and not tgt.startswith(base + os.sep):
        raise ValueError(f"path escapes workspace: {target}")
    return os.path.relpath(tgt, base)