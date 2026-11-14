# Forge-Mcp

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-orange)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-23%20passing-brightgreen)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)]()

> **MCP (Model Context Protocol) server for game modding helpers.**
> Run hex/offset/PE/APK/Unity/Unreal operations from inside **Claude Desktop** or any MCP client.

---

## 🎯 What can it do?

| Domain | Key Operations |
|--------|----------------|
| **Hex / Offset** | View, search (AOB/wildcard/string), diff saves, value-scan, patch (dry-run), pointer chains, RVA↔VA↔file-offset, checksum fix (CRC32/Adler/sum) |
| **PE (EXE/DLL)** | Sections, imports/exports, entropy, compiler/packer guess, find by name/string-ref, make/verify AOB signatures, cross-build matching, Unicorn emulation, Ghidra headless decompile |
| **APK / Android** | apktool unpack/repack+sign, manifest (aapt2 fallback), smali search/patch, native `.so` exports, Il2Cpp global-metadata dump (parser + Il2CppDumper) |
| **Unity** | AssetBundle / `.assets` list/extract/replace (UnityPy) |
| **Unreal** | `.pak` list/extract/pack (UnrealPak + AES key) |
| **Tables** | Schema-driven list/clone/edit/rebuild/validate/references |
| **Archives** | zip/tar/7z/unrar unpack & repack (plugin system) |
| **Format Lab** | Entropy map, try_decode (zlib/gzip/lzma/xor/base64), guess fields, write `.ksy`/`.hexpat` templates, validate |
| **Dynamic** | Frida hook script generation, trace diff (two text logs) |
| **Diagnose** | Crash log parse, dependency check, mod conflict detection, bisect plan, load-order suggestion |
| **Export** | IPS / xdelta patches, Cheat Engine `.CT` tables, changelog from job log |
| **Undo** | Automatic snapshot before every write, single-command rollback |

---

## 🚀 Quick Start

### 1. Install
```bash
# From GitHub (recommended)
pip install git+https://github.com/RivaExits0/forge-mcp.git[full]

# Or from source
git clone https://github.com/RivaExits0/forge-mcp.git
cd forge-mcp
pip install -e .[full]          # optional: keystone, UnityPy, kaitaistruct, androguard, lz4
```

### 2. External Tools (Optional but Recommended)
| Tool | Purpose | Setup |
|------|---------|-------|
| **Ghidra** (`analyzeHeadless`) | Decompile functions | `GHIDRA_HOME=/opt/ghidra_12.2` |
| **apktool** | APK unpack/repack | PATH or `APKTOOL_HOME` |
| **jadx** | Dex decompile | `JADX_HOME` |
| **Il2CppDumper** | Full Il2Cpp dump | PATH |
| **UnrealPak** / **u4pak** | `.pak` operations | PATH |
| **xdelta3** | Binary delta patches | PATH |
| **Frida** (`frida`, `frida-trace`) | Runtime hooks | `pip install frida frida-tools` |
| **aapt2** | APK manifest (better than zip fallback) | Android SDK `build-tools/XX/aapt2` |

> Missing tools produce **actionable errors with install links** — core functionality never crashes.

### 3. Configure Claude Desktop
Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "forge-mcp": {
      "command": "python",
      "args": ["-m", "forge_mcp.server"],
      "cwd": "/absolute/path/to/forge-mcp",
      "env": {
        "FORGE_WORKSPACE_ROOT": "/absolute/path/to/forge-workspaces",
        "GHIDRA_HOME": "/opt/ghidra_12.2"
      }
    }
  }
}
```

> **Windows:** Use `C:\\path\\to\\forge-mcp` and `C:\\path\\to\\forge-workspaces` with double backslashes or forward slashes.

### 4. Restart Claude Desktop → You're ready! 🎉

---

## 🛠 10 Top-Level Tools

All tools use a **module/action** pattern with built-in **pagination** (`offset`/`limit`, max 4096) and **dry-run** support for writes.

| Tool | Purpose | Example |
|------|---------|---------|
| `open_game` | Create/open per-game workspace; import file (exe/apk/save) | `{"game_name": "elden_ring", "source_path": "/games/ER/eldenring.exe"}` |
| `inspect` | Read-only queries (pe_info, hex_view, apk_manifest, entropy_map…) | `{"module": "pe", "action": "pe_info", "params": {}}` |
| `search` | Searches (hex_search, diff_files, value_scan, find_function, guess_fields) | `{"module": "hex", "action": "hex_search", "params": {"query": "48 8B ?? ?? ?? 90", "mode": "aob"}}` |
| `edit` | Write ops with `dry_run` (hex_patch, smali_patch, table edit, checksum_fix) | `{"module": "hex", "action": "hex_patch", "params": {"offset": 0x1234, "bytes_hex": "90 90", "dry_run": false}}` |
| `patch_code` | Signature/emulation/code-gen (make_signature, verify_signature, emulate_function, frida_script) | `{"module": "pe", "action": "make_signature", "params": {"address": 0x140001000, "length": 32}}` |
| `rebuild` | Rebuild/repack (tables, archives, apk_repack, unreal_pak) | `{"module": "tables", "action": "rebuild_offsets", "params": {"schema": {...}}}` |
| `validate` | Validate artifacts (verify_signature, validate_table, validate_template) | `{"module": "pe", "action": "verify_signature", "params": {"signature": "..."}}` |
| `export` | Distributable artifacts (IPS/xdelta, Cheat Engine .CT, changelog) | `{"module": "patch", "action": "export_patch", "params": {"original_path": "...", "modified_path": "...", "out_path": "patch.ips"}}` |
| `diagnose` | Crash logs, deps, conflicts, bisect, load order, trace diff | `{"module": "diagnose", "action": "parse_crash_log", "params": {"path": "crash.dmp"}}` |
| `undo` | Restore latest (or named) snapshot | `{"snapshot_id": "20240615T123456Z_abc123"}` |

---

## 📖 Example Workflow

> **User:** *"Open Elden Ring, find the gold value (I had 100 then 150), and give me a signature that survives updates."*

```text
1. open_game({"game_name": "elden_ring", "source_path": "C:/Games/ER/eldenring.exe"})

2. search({"module": "hex", "action": "value_scan",
          "params": {"before_path": "save_100.bin", "after_path": "save_150.bin",
                     "value_type": "int32", "limit": 20}})
   → hits: [{"offset": 0x3A20, "before": 100, "after": 150, "type": "int32"}, ...]

3. inspect({"module": "hex", "action": "hex_view",
            "params": {"path": "work/eldenring.exe", "offset": 0x3A10, "limit": 32}})

4. patch_code({"module": "pe", "action": "make_signature",
               "params": {"path": "work/eldenring.exe", "address": 0x3A20, "length": 32}})
   → {"signature": "8B 45 ?? 3D 96 00 00 00 75 ?? 48 8B 0D ...", "unique": true}

5. validate({"module": "pe", "action": "verify_signature",
             "params": {"path": "work/eldenring_v1.02.exe", "signature": "..."}})
   → {"matches": 1, "unique": true}  # survives the patch!

6. export({"module": "patch", "action": "export_patch",
           "params": {"original_path": "original/eldenring.exe", "modified_path": "work/eldenring.exe",
                      "out_path": "gold_patch.ips", "fmt": "ips"}})
```

---

## 🎮 Game Profiles (Adapters)

Drop a folder under `profiles/<game>/`:

```
profiles/
  elden_ring/
    profile.toml        # metadata + config
    schema.ksy          # Kaitai struct for save/table files
    signatures.json     # known AOBs { "gold_offset": "8B 45 ?? ..." }
```

```python
open_game({"game_name": "elden_ring", "profile_dir": "profiles/elden_ring"})
```

Community adapters are **just folders — no code needed**.

### Example: `profiles/example_game/profile.toml`
```toml
name = "example_game"
version = "1.0"
author = "forge-mcp"
description = "Example game profile template"
```

---

## 🛡 Safety & Ethics

- ✅ **Never writes to originals** — workspace keeps a read-only copy + working copy
- ✅ **Snapshots before every write** — `undo` restores byte-for-byte (SHA-256 verified)
- ✅ **No binary execution** — static analysis only; Unicorn emulation is fully isolated (no syscalls, no FS, no network)
- ✅ **Frida only when explicitly asked** — script generation + run hint; you run it on your own machine
- ✅ **Path traversal blocked** — all paths resolved inside workspace root
- ✅ **Single-player / owned copies only** — no anti-cheat bypass, no DRM removal, no multiplayer advantage tools

---

## 🏗 Architecture

```
forge-mcp/
├── src/forge_mcp/
│   ├── server.py           # FastMCP entry, 10 tools (module/action dispatch)
│   ├── core/
│   │   ├── platform.py     # Cross-platform paths, subprocess, file I/O
│   │   ├── workspace.py    # Per-game dirs, read-only originals + work copy
│   │   ├── snapshot.py     # Copy-on-write + undo (SHA-256 verified)
│   │   ├── job_log.py      # JSONL log → patches + changelog
│   │   ├── paging.py       # offset/limit helper (max 4096)
│   │   ├── profiles.py     # Adapter loader (profile.toml, signatures.json, schema.ksy)
│   │   └── external.py     # Subprocess wrappers (Ghidra, apktool, jadx, Frida…)
│   └── modules/
│       ├── hexops.py       # Hex view/search/diff/scan/patch/pointer/offset/calc/checksum
│       ├── pe.py           # PE info, signatures, emulate, ghidra decompile, cross-build
│       ├── apk.py          # Unpack/repack, manifest, smali, il2cpp, native libs
│       ├── unity.py        # UnityPy asset list/extract/replace
│       ├── unreal.py       # UnrealPak list/extract/pack (AES)
│       ├── tables.py       # Schema-driven CRUD + validate/rebuild/refs
│       ├── archives.py     # zip/tar/7z plugin unpack/repack
│       ├── formatlab.py    # Entropy, try_decode, guess, write_template, validate_template
│       ├── dynamic.py      # Frida script gen, trace diff
│       ├── diagnose.py     # Crash, deps, conflicts, bisect, load order
│       └── export.py       # IPS/xdelta, Cheat Engine .CT
├── profiles/               # Community game adapters
└── tests/                  # 23 tests (core, hexops, modules, server E2E)
    ├── fixtures/           # Synthetic PE/APK/table files (no copyrighted content)
    └── make_fixtures.py    # Regenerates fixtures
```

---

## 🧪 Development

```bash
pip install -e .[full]
pytest -q                    # 23 tests passing
python -m forge_mcp.server   # Stdio server (for MCP clients)
```

### Run Tests
```bash
PYTHONPATH=src:tests python -m pytest -v
```

---

## 📦 Release

- **Latest:** [v0.1.0](https://github.com/RivaExits0/forge-mcp/releases/tag/v0.1.0)
- **Install from release:** `pip install git+https://github.com/RivaExits0/forge-mcp.git@v0.1.0[full]`

---

## 🔧 Troubleshooting

| Issue | Fix |
|-------|-----|
| `Ghidra not found` | Set `GHIDRA_HOME` to your Ghidra install (folder containing `support/analyzeHeadless`) |
| `apktool not found` | Install from https://apktool.org/docs/install or set `APKTOOL_HOME` |
| `aapt2 not found` | Install Android SDK build-tools, add to PATH |
| `Frida not found` | `pip install frida frida-tools` |
| `Permission denied` on Windows | Run terminal as Administrator or check file permissions |
| `ModuleNotFoundError` | Run `pip install -e .[full]` |

---

## 📄 License

**MIT** — use freely for your own single-player modding.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch
3. Add tests for new functionality
4. Ensure `pytest -q` passes
5. Open a PR

---

## 🔗 Links

- **Repository:** https://github.com/RivaExits0/forge-mcp
- **Issues:** https://github.com/RivaExits0/forge-mcp/issues
- **MCP Spec:** https://modelcontextprotocol.io/
- **Ghidra:** https://github.com/NationalSecurityAgency/ghidra
- **apktool:** https://apktool.org/
- **UnityPy:** https://github.com/K0lb3/UnityPy