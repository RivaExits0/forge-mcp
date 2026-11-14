import os
from forge_mcp.modules import hexops

DATA = b"\x48\x8b\x05\x12\x34\x56\x78\x90\xcc" * 4 + b"Hello\x00World"


def test_hex_search_bytes_and_string():
    r = hexops.hex_search(DATA, "48 8B ? ? 34", mode="aob")
    assert r["mode"] == "aob"
    assert len(r["hits"]) >= 1
    r2 = hexops.hex_search(DATA, "Hello", mode="string")
    assert len(r2["hits"]) == 1


def test_diff_files():
    a = b"abcXXXdef"
    b = b"abcYYYdef"
    d = hexops.diff_files(a, b)
    assert len(d) == 1
    assert d[0]["offset"] == 3
    assert d[0]["length"] == 3


def test_value_scan():
    import struct
    before = bytearray(64)
    after = bytearray(64)
    struct.pack_into("<i", before, 8, 100)
    struct.pack_into("<i", after, 8, 150)
    hits = hexops.value_scan(bytes(before), bytes(after), "int32")
    assert any(h["offset"] == 8 for h in hits)


def test_hex_patch_dryrun():
    buf = bytearray(b"AAAA")
    res = hexops.hex_patch(buf, 1, b"BB", dry_run=True)
    assert res["dry_run"] is True
    assert bytes(buf) == b"AAAA"
    res2 = hexops.hex_patch(buf, 1, b"BB", dry_run=False)
    assert res2["applied"] is True
    assert bytes(buf) == b"ABBA"


def test_checksum_fix():
    import zlib
    data = bytearray(b"hello")
    # append crc placeholder
    data += b"\x00\x00\x00\x00"
    res = hexops.checksum_fix(data, algo="crc32", field_offset=5, field_size=4, region=(0, 5))
    assert data[5:9] == (zlib.crc32(b"hello") & 0xffffffff).to_bytes(4, "little")