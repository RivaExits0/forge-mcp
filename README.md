# Forge-Mcp

MCP (Model Context Protocol) server for game modding helpers.
Designed to let modders run hex/offset/PE/APK/Unity/Unreal operations from inside Claude Desktop or any MCP client.

## Features

| Domain | Operations |
|--------|------------|
| **Hex / Offset** | View, search (AOB/wildcard/string), diff two saves, value-scan, patch (dry-run), pointer chains, RVA/VA/file-offset conversion, checksum fix (CRC32/Adler/sum) |
| **PE (EXE/DLL)** | Section/import/export/entropy, compiler/packer guess, find by name/string-ref, make/verify AOB signatures, cross-build matching, Unicorn emulation, Ghidra headless decompile |
| **APK / Android** | apktool unpack/repack+sign, manifest parsing (aapt2 fallback), smali search/patch, native `.so` exports, Il2Cpp global-metadata dump (parser + Il2CppDumper wrapper) |
| **Unity** | AssetBundle / `.assets` list/extract/replace (UnityPy) |
| **Unreal** | `.pak` list/extract/pack (UnrealPak + AES key) |
| **Tables** | Schema-driven list/clone/edit/rebuild/validate/references |
| **Archives** | zip/tar/7z/unrar unpack & repack (plugin system) |
| **Format lab** | Entropy map, try_decode (zlib/gzip/lzma/xor/base64), guess fields, write .ksy/.hexpat templates, validate |
| **Dynamic** | Frida hook script generation, trace diff (two text logs) |
| **Diagnose** | Crash log parse, dependency check, mod conflict detection, bisect plan, load-order suggestion |
| **Export** | IPS / xdelta patches, Cheat Engine .CT tables, changelog from job log |
| **Undo** | Automatic snapshot before every write, single-command rollback |

## Installation

```bash
git clone <this-repo>
cd forge-mcp
pip install -e .[full]   # optional deps: keystone, UnityPy, kaitaistruct, androguard, lz4
```

### External tools (optional but recommended)

| Tool | Purpose | Env / PATH hint |
|------|---------|-----------------|
| Ghidra (`analyzeHeadless`) | Decompile functions | `GHIDRA_HOME=/opt/ghidra_12.2` |
| apktool | APK unpack/repack | on PATH or `APKTOOL_HOME` |
| jadx | Dex decompile | `JADX_HOME` |
| Il2CppDumper | Full Il2Cpp dump | on PATH |
| UnrealPak / u4pak | `.pak` operations | on PATH |
| xdelta3 | Binary delta patches | on PATH |
| Frida (`frida`, `frida-trace`) | Runtime hooks | `pip install frida frida-tools` |
| aapt2 | APK manifest (better than zip fallback) | Android SDK `build-tools/XX/aapt2` |

Missing tools produce actionable errors with install links; core functionality never crashes.

## Quick start (Claude Desktop)

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

Restart Claude Desktop. You now have these **10 top-level tools**:

| Tool | Purpose | Example |
|------|---------|---------|
| `open_game` | Create/open a per-game workspace; import a file (exe/apk/save) | `{"game_name": "elden_ring", "source_path": "/games/ER/eldenring.exe"}` |
| `inspect` | Read-only queries (pe_info, hex_view, apk_manifest, entropy_map…) | `{"module": "pe", "action": "pe_info", "params": {}}` |
| `search` | Searches (hex_search, diff_files, value_scan, find_function, guess_fields) | `{"module": "hex", "action": "hex_search", "params": {"query": "48 8B ?? ?? ?? 90", "mode": "aob"}}` |
| `edit` | Write operations with `dry_run` (hex_patch, smali_patch, table edit, checksum_fix) | `{"module": "hex", "action": "hex_patch", "params": {"offset": 0x1234, "bytes_hex": "90 90", "dry_run": false}}` |
| `patch_code` | Signature/emulation/code-gen (make_signature, verify_signature, emulate_function, frida_script) | `{"module": "pe", "action": "make_signature", "params": {"address": 0x140001000, "length": 32}}` |
| `rebuild` | Rebuild/repack (tables, archives, apk_repack, unreal_pak) | `{"module": "tables", "action": "rebuild_offsets", "params": {"schema": {...}}}` |
| `validate` | Validate artifacts (verify_signature, validate_table, validate_template) | `{"module": "pe", "action": "verify_signature", "params": {"signature": "..."}}` |
| `export` | Produce distributable artifacts (IPS/xdelta, Cheat Engine .CT, changelog) | `{"module": "patch", "action": "export_patch", "params": {"original_path": "...", "modified_path": "...", "out_path": "patch.ips"}}` |
| `diagnose` | Crash logs, deps, conflicts, bisect, load order, trace diff | `{"module": "diagnose", "action": "parse_crash_log", "params": {"path": "crash.dmp"}}` |
| `undo` | Restore latest (or named) snapshot | `{"snapshot_id": "20240615T123456Z_abc123"}` |

All list-returning tools require `offset` and `limit` (max 4096); large hex dumps, decompilation, and search results are **always paginated**.

## Example workflow

> **User**: "Open Elden Ring, find the gold value (I had 100 then 150), and give me a signature that survives updates."

```text
1. open_game({"game_name": "elden_ring", "source_path": "C:/Games/ER/eldenring.exe"})
2. search({"module": "hex", "action": "value_scan",
          "params": {"before_path": "save_100.bin", "after_path": "save_150.bin",
                     "value_type": "int32", "limit": 20}})
   -> hits: [{"offset": 0x3A20, "before": 100, "after": 150, "type": "int32"}, ...]
3. inspect({"module": "hex", "action": "hex_view",
           "params": {"path": "work/eldenring.exe", "offset": 0x3A10, "limit": 32}})
4. patch_code({"module": "pe", "action": "make_signature",
              "params": {"path": "work/eldenring.exe", "address": 0x3A20, "length": 32}})
   -> {"signature": "8B 45 ?? 3D 96 00 00 00 75 ?? 48 8B 0D ...", "unique": true}
5. validate({"module": "pe", "action": "verify_signature",
            "params": {"path": "work/eldenring_v1.02.exe", "signature": "..."}})
   -> {"matches": 1, "unique": true}  # survives the patch
6. export({"module": "patch", "action": "export_patch",
          "params": {"original_path": "original/eldenring.exe", "modified_path": "work/eldenring.exe",
                     "out_path": "gold_patch.ips", "fmt": "ips"}})
```

## Game profiles (adapters)

Drop a folder under `profiles/<game>/` with:

```
profiles/
  elden_ring/
    profile.toml        # metadata + config
    schema.ksy          # Kaitai struct for save / table files
    signatures.json     # known AOBs { "gold_offset": "8B 45 ?? ..." }
```

`open_game(..., profile_dir="profiles/elden_ring")` loads it; `inspect/module=profile` exposes signatures.

Community adapters are just folders — no code needed.

## Safety & Ethics

* **Never writes to originals** — workspace keeps a read-only copy + working copy.
* **Snapshots before every write** — `undo` restores byte-for-byte.
* **No binary execution** — static analysis only; Unicorn emulation is fully isolated (no syscalls, no FS, no network).
* **Frida only when you explicitly ask** — script generation + run hint; you run it on your own machine.
* **Path traversal blocked** — all paths resolved inside the workspace root.
* **Single-player / owned copies only** — no anti-cheat bypass, no DRM removal, no multiplayer advantage tools.

## Architecture

```
forge-mcp/
  src/forge_mcp/
    server.py           # FastMCP entry, 10 top-level tools (module/action dispatch)
    core/
      workspace.py      # per-game dirs, import, read-only originals
      snapshot.py       # copy-on-write + undo
      job_log.py        # JSONL log -> patches + changelog
      paging.py         # offset/limit helper
      profiles.py       # adapter loader (profile.toml, signatures.json, schema.ksy)
      external.py       # subprocess wrappers for Ghidra/apktool/...
    modules/
      hexops.py         # hex view/search/diff/scan/patch/pointer/offset/calc/checksum
      pe.py             # PE info, signatures, emulate, ghidra decompile, cross-build match
      apk.py            # unpack/repack, manifest, smali, il2cpp, native libs
      unity.py          # UnityPy asset list/extract/replace
      unreal.py         # UnrealPak list/extract/pack
      tables.py         # schema-driven table CRUD + validate/rebuild
      archives.py       # zip/tar/7z plugin unpack/repack
      formatlab.py      # entropy, try_decode, guess, write_template, validate_template
      dynamic.py        # frida script gen, trace diff
      diagnose.py       # crash, deps, conflicts, bisect, load order
      export.py         # IPS/xdelta, Cheat Engine .CT
  profiles/             # community game adapters
  tests/
    fixtures/           # synthetic PE/APK/table files (no copyrighted content)
    make_fixtures.py    # regenerates fixtures
```

## Development

```bash
pip install -e .[full]
pytest -q            # runs core + module + server tests
python -m forge_mcp.server   # stdio server (for MCP clients)
```

## License

MIT — use freely for your own single-player modding.