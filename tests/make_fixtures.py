"""Generate synthetic fixtures for Forge-Mcp tests.

Everything here is self-produced synthetic data - no game files are used.

Usage:
    python tests/make_fixtures.py
"""

from __future__ import annotations

import os
import struct
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")


def build_pe(path: str, code: bytes = b"\x48\x8b\x05\x11\x22\x33\x44\x90\xcc\x90\x90\x90",
             extra_strings=(b"HelloForge\x00",)) -> str:
    """Build a tiny but structurally valid PE64 executable."""
    file_align = 0x200
    sect_align = 0x1000
    image_base = 0x140000000

    dos = bytearray(b"\x00" * 0x80)
    dos[0:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 0x80)

    pe_off = 0x80
    coff = struct.pack("<HHIIIHH",
                       0x8664,      # Machine x64
                       1,           # NumberOfSections
                       0x66000000,  # TimeDateStamp (fixed)
                       0, 0,        # symbol table
                       0xF0,        # SizeOfOptionalHeader
                       0x0022)      # Characteristics: EXECUTABLE_IMAGE

    # Optional header PE32+
    opt = bytearray(0xF0)
    struct.pack_into("<H", opt, 0, 0x20B)      # Magic PE32+
    opt[2] = 14                                 # MajorLinkerVersion
    opt[3] = 0
    struct.pack_into("<I", opt, 16, 0x1000)     # AddressOfEntryPoint
    struct.pack_into("<I", opt, 20, 0x1000)     # BaseOfCode
    struct.pack_into("<Q", opt, 24, image_base)  # ImageBase
    struct.pack_into("<I", opt, 32, sect_align)  # SectionAlignment
    struct.pack_into("<I", opt, 36, file_align)  # FileAlignment
    struct.pack_into("<H", opt, 40, 6)           # MajorOperatingSystemVersion
    struct.pack_into("<H", opt, 44, 6)           # MajorSubsystemVersion
    struct.pack_into("<I", opt, 56, 0x100000)    # SizeOfImage
    struct.pack_into("<I", opt, 60, 0x200)       # SizeOfHeaders
    struct.pack_into("<H", opt, 68, 3)           # Subsystem: console
    struct.pack_into("<I", opt, 108, 16)         # NumberOfRvaAndSizes

    body = bytearray(code)
    for s in extra_strings:
        body += s
    raw_size = (len(body) + file_align - 1) // file_align * file_align
    raw = bytes(body).ljust(raw_size, b"\x00")

    sect = struct.pack("<8sIIIIIIHHI",
                       b".text\0\0\0", len(body), 0x1000, raw_size, file_align,
                       0, 0, 0, 0, 0x60000020)

    headers = bytes(dos) + b"PE\x00\x00" + coff + bytes(opt) + sect
    headers = headers.ljust(file_align, b"\x00")
    with open(path, "wb") as f:
        f.write(headers + raw)
    return path


def build_zip_apk(path: str) -> str:
    manifest = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.fixture">\n'
        '  <uses-permission android:name="android.permission.INTERNET"/>\n'
        '  <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE"/>\n'
        '  <application android:label="Fixture">\n'
        '    <activity android:name="com.example.fixture.MainActivity" android:exported="true"/>\n'
        '    <service android:name="com.example.fixture.SyncService" android:exported="false"/>\n'
        '  </application>\n'
        '</manifest>\n'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("AndroidManifest.xml", manifest)
        z.writestr("classes.dex", b"dex\n035\x00" + b"\x00" * 32)
        z.writestr("lib/arm64-v8a/libgame.so", b"\x7fELF" + b"\x00" * 60)
        z.writestr("resources.arsc", b"\x02\x00\x0c\x00" + b"\x00" * 64)
    return path


def build_table(path: str) -> str:
    """Simple table: uint32 count, uint32 offset table, then entries of 16 bytes."""
    entries = [
        (1, 100, 2.5),
        (2, 200, 3.5),
        (3, 300, 4.5),
    ]
    entry_size = 16
    header = struct.pack("<II", len(entries), 0)
    offsets = b""
    body = b""
    off = len(header) + 4 * len(entries)
    for eid, hp, mp in entries:
        offsets += struct.pack("<I", off + len(body))
        body += struct.pack("<Ifi", eid, hp, int(mp))
        body = body.ljust(entry_size, b"\x00")
    with open(path, "wb") as f:
        f.write(header + offsets + body)
    return path


def main():
    os.makedirs(FIX, exist_ok=True)
    build_pe(os.path.join(FIX, "sample.exe"))
    build_zip_apk(os.path.join(FIX, "fixture.apk"))
    build_table(os.path.join(FIX, "table.bin"))
    print(f"fixtures written to {FIX}")


if __name__ == "__main__":
    main()
