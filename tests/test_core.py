import os, tempfile, shutil, hashlib
import pytest

from forge_mcp.core.workspace import WorkspaceManager
from forge_mcp.core.snapshot import take_snapshot, restore_snapshot, list_snapshots
from forge_mcp.core.job_log import append, read, changelog
from forge_mcp.core.paging import require_paging


def test_workspace_import_and_path_safety(tmp_path):
    wm = WorkspaceManager(root=str(tmp_path / "wsroot"))
    ws = wm.create("g1")
    src = tmp_path / "a.bin"
    src.write_bytes(b"hello")
    wp = wm.import_file(ws, str(src), logical="main")
    assert os.path.isfile(wp)
    assert wm.work_path(ws) == wp
    # original read-only
    op = wm.original_path(ws)
    assert op and os.path.isfile(op)
    # path traversal
    try:
        from forge_mcp.core.workspace import safe_path
        safe_path(ws.dir, "..", "etc", "passwd")
        assert False
    except Exception:
        pass


def test_snapshot_undo_hash(tmp_path):
    wm = WorkspaceManager(root=str(tmp_path / "wsroot"))
    ws = wm.create("g2")
    src = tmp_path / "a.bin"
    src.write_bytes(b"hello world")
    wp = wm.import_file(ws, str(src))
    h0 = hashlib.sha256(open(wp, "rb").read()).hexdigest()
    sid = take_snapshot(ws.dir, wp, reason="test")
    # modify
    with open(wp, "wb") as f:
        f.write(b"changed")
    assert hashlib.sha256(open(wp, "rb").read()).hexdigest() != h0
    restore_snapshot(ws.dir, sid)
    h1 = hashlib.sha256(open(wp, "rb").read()).hexdigest()
    assert h0 == h1


def test_job_log(tmp_path):
    d = tmp_path / "ws"
    d.mkdir()
    append(str(d), {"action": "x", "target": "f"})
    rows = read(str(d))
    assert len(rows) == 1
    assert rows[0]["action"] == "x"
    cl = changelog(str(d))
    assert "x" in cl