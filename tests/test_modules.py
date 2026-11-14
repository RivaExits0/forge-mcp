import os
import struct

import pytest

from forge_mcp.modules import pe, apk, tables

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SAMPLE_EXE = os.path.join(FIX, "sample.exe")
FIXTURE_APK = os.path.join(FIX, "fixture.apk")
TABLE_BIN = os.path.join(FIX, "table.bin")


def _ensure_fixtures():
    if not os.path.isfile(SAMPLE_EXE):
        import make_fixtures
        make_fixtures.main()


def test_pe_info():
    _ensure_fixtures()
    info = pe.pe_info(SAMPLE_EXE)
    assert info["machine"] == "x64"
    assert info["sections"]
    assert info["sections"][0]["name"] == ".text"
    assert info["image_base"] == 0x140000000
    assert isinstance(info["compiler_guess"], list)


def test_make_and_verify_signature():
    _ensure_fixtures()
    data = open(SAMPLE_EXE, "rb").read()
    # .text raw starts at 0x200
    sig = pe.make_signature(data, 0x200, length=12)
    assert "matches" in sig
    assert sig["matches"] >= 1
    v = pe.verify_signature(data, sig["signature"])
    assert v["matches"] == sig["matches"]
    assert v["unique"] == (v["matches"] == 1)


def test_signature_wildcard_matches():
    _ensure_fixtures()
    data = open(SAMPLE_EXE, "rb").read()
    # 48 8B 05 ? ? ? ? 90 CC  -> should match
    res = pe.verify_signature(data, "48 8B 05 ?? ?? ?? ?? 90 CC")
    assert res["matches"] >= 1
    assert res["unique"] is True


def test_offset_calc_roundtrip():
    _ensure_fixtures()
    info = pe.pe_info(SAMPLE_EXE)
    secs = info["sections"]
    r = hexops_offset(0x1000, info["image_base"], secs)
    assert r["file_offset"] == 0x200


def hexops_offset(rva, image_base, sections):
    from forge_mcp.modules import hexops
    return hexops.offset_calc(rva=rva, image_base=image_base, sections=sections)


def test_emulate_function_x64():
    # mov eax, 0x2a; ret
    code = bytes.fromhex("B82A000000C3")
    res = pe.emulate_function(code, arch="x64")
    assert "return_value" in res
    assert res["return_value"] == 0x2A


def test_apk_manifest():
    _ensure_fixtures()
    res = apk.apk_manifest(FIXTURE_APK)
    assert "INTERNET" in " ".join(res["permissions"])
    assert res["raw_excerpt"]


def test_smali_search_and_patch(tmp_path):
    src = tmp_path / "smali"
    src.mkdir()
    f = src / "MainActivity.smali"
    f.write_text(".class public LMainActivity;\nconst/4 v0, 0x1\nconst/4 v0, 0x2\n")
    hits = apk.smali_search(str(src), "const/4 v0, 0x1")
    assert len(hits) == 1
    res = apk.smali_patch(str(src), "MainActivity.smali", "0x1", "0x9", dry_run=True)
    assert res["dry_run"] is True
    assert "0x9" not in f.read_text()
    res2 = apk.smali_patch(str(src), "MainActivity.smali", "0x1", "0x9", dry_run=False)
    assert res2["dry_run"] is False
    assert "0x9" in f.read_text()


def test_tables_list_clone_edit_validate():
    _ensure_fixtures()
    data = bytearray(open(TABLE_BIN, "rb").read())
    schema = {
        "count_offset": 0,
        "offset_table": {"offset": 8, "count": 3},
        "entry_size": 16,
        "fields": [
            {"name": "id", "offset": 0, "type": "uint32", "size": 4},
            {"name": "hp", "offset": 4, "type": "float", "size": 4},
            {"name": "mp", "offset": 8, "type": "int32", "size": 4},
        ],
    }
    entries = tables.list_entries(bytes(data), schema)
    assert len(entries) == 3
    assert entries[0]["hp"] == 100.0
    assert entries[0]["id"] == 1
    res = tables.clone_entry(data, schema, 0)
    assert res["ok"]
    entries2 = tables.list_entries(bytes(data), schema)
    assert len(entries2) == 4
    assert entries2[3]["hp"] == entries2[0]["hp"]
    ed = tables.edit_fields(data, schema, 3, {"hp": 999.0})
    assert ed["ok"]
    assert tables.list_entries(bytes(data), schema)[3]["hp"] == 999.0
    val = tables.validate_table(bytes(data), schema)
    assert val["ok"] is True, val["issues"]
    # failing scenario: bad schema
    bad = {"entry_size": 4, "fields": [{"name": "x", "offset": 2, "type": "uint32", "size": 8}]}
    val2 = tables.validate_table(bytes(data), bad)
    assert val2["ok"] is False
    assert val2["issues"]


def test_find_references():
    _ensure_fixtures()
    data = open(TABLE_BIN, "rb").read()
    schema = {
        "entry_size": 16,
        "fields": [{"name": "id", "offset": 0, "type": "uint32", "size": 4}],
    }
    refs = tables.find_references(data, 1, schema)
    assert isinstance(refs, list)
