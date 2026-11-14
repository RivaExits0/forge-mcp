"""End-to-end tests for the high-level MCP tools."""

import json
import os
import shutil

import pytest

from forge_mcp import server
from forge_mcp.core.workspace import WorkspaceManager

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SAMPLE_EXE = os.path.join(FIX, "sample.exe")


def _ensure_fixtures():
    if not os.path.isfile(SAMPLE_EXE):
        import make_fixtures
        make_fixtures.main()


@pytest.fixture(autouse=True)
def ws_tmp(tmp_path, monkeypatch):
    root = str(tmp_path / "workspaces")
    server.MANAGER = WorkspaceManager(root=root)
    server.STATE["game"] = None
    server.STATE["profile"] = None
    yield root


def _open(sample):
    return json.loads(server.open_game("testgame", source_path=sample))


def test_open_game_imports_file(ws_tmp):
    _ensure_fixtures()
    res = _open(SAMPLE_EXE)
    assert res["game"] == "testgame"
    assert os.path.isfile(res["work_file"])
    assert os.path.isfile(res["original"])
    # original is read-only
    assert not os.access(res["original"], os.W_OK) or os.stat(res["original"]).st_mode & 0o222 == 0


def test_edit_hex_patch_dry_run_then_apply_and_undo(ws_tmp):
    _ensure_fixtures()
    res = _open(SAMPLE_EXE)
    path = res["work_file"]
    data = open(path, "rb").read()
    target = 0x200
    original_bytes = data[target:target + 4]

    dry = json.loads(server.edit("hex", "hex_patch", {
        "path": path, "offset": target, "bytes_hex": "90 90 90 90", "dry_run": True}))
    assert dry["dry_run"] is True
    assert open(path, "rb").read()[target:target + 4] == original_bytes

    applied = json.loads(server.edit("hex", "hex_patch", {
        "path": path, "offset": target, "bytes_hex": "90 90 90 90", "dry_run": False}))
    assert applied["applied"] is True
    assert open(path, "rb").read()[target:target + 4] == b"\x90\x90\x90\x90"

    undone = json.loads(server.undo())
    assert "restored" in undone
    assert open(path, "rb").read()[target:target + 4] == original_bytes


def test_search_hex_and_inspect_pe(ws_tmp):
    _ensure_fixtures()
    res = _open(SAMPLE_EXE)
    path = res["work_file"]
    sr = json.loads(server.search("hex", "hex_search", {"path": path, "query": "48 8B", "mode": "aob"}))
    assert sr["hits"]
    assert sr["pagination"]["total"] >= 1

    ir = json.loads(server.inspect("pe", "pe_info", {"path": path}))
    assert ir["machine"] == "x64"

    patch_code = json.loads(server.patch_code("pe", "verify_signature",
                                             {"path": path, "signature": "48 8B 05 ?? ?? ?? ?? 90 CC"}))
    assert patch_code["unique"] is True


def test_inspect_hex_view_paged(ws_tmp):
    _ensure_fixtures()
    res = _open(SAMPLE_EXE)
    path = res["work_file"]
    out = json.loads(server.inspect("hex", "hex_view", {"path": path, "offset": 0, "limit": 64}))
    assert "dump" in out
    assert len(out["dump"].splitlines()) == 4


def test_diagnose_external_check(ws_tmp):
    out = json.loads(server.diagnose("external", "check_dependencies", {}))
    assert "ghidra" in out
    assert "apktool" in out


def test_export_changelog(ws_tmp):
    _ensure_fixtures()
    res = _open(SAMPLE_EXE)
    path = res["work_file"]
    server.edit("hex", "hex_patch", {"path": path, "offset": 0x200,
                                     "bytes_hex": "90", "dry_run": False})
    cl = server.export("diagnose", "changelog", {})
    assert "hex_patch" in cl
