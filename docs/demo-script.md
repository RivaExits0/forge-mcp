# Demo Recording Script

This document describes the exact MCP tool calls to demonstrate Forge-Mcp's capabilities. Run these in sequence via Claude Desktop or an MCP test client.

## Prerequisites

```bash
# Ensure fixtures exist (run from repo root)
python tests/make_fixtures.py
```

## Recording Steps

### 1. Open Game Workspace
```json
{
  "tool": "open_game",
  "args": {
    "game_name": "example_game",
    "source_path": "tests/fixtures/sample.exe"
  }
}
```
**Expected:** Returns workspace path, work_file, original file path.

### 2. Inspect PE Info
```json
{
  "tool": "inspect",
  "args": {
    "module": "pe",
    "action": "pe_info",
    "params": {}
  }
}
```
**Expected:** Shows machine=x64, sections, imports, exports, compiler guess.

### 3. Value Scan (Find Gold Offset)
```json
{
  "tool": "search",
  "args": {
    "module": "hex",
    "action": "value_scan",
    "params": {
      "before_path": "tests/fixtures/save_before.bin",
      "after_path": "tests/fixtures/save_after.bin",
      "value_type": "int32",
      "limit": 20
    }
  }
}
```
**Expected:** Returns hits with offset, before/after values. Look for offset where value changed from 100 to 150.

### 4. Hex View Around Offset
```json
{
  "tool": "inspect",
  "args": {
    "module": "hex",
    "action": "hex_view",
    "params": {
      "path": "work/example.exe",
      "offset": 0x3A10,
      "limit": 32
    }
  }
}
```
**Expected:** Shows hex dump with ASCII sidebar around the found offset.

### 5. Make Signature
```json
{
  "tool": "patch_code",
  "args": {
    "module": "pe",
    "action": "make_signature",
    "params": {
      "path": "work/example.exe",
      "address": 0x3A20,
      "length": 32
    }
  }
}
```
**Expected:** Returns AOB signature with `unique: true`.

### 6. Verify Signature (Cross-Build)
```json
{
  "tool": "patch_code",
  "args": {
    "module": "pe",
    "action": "verify_signature",
    "params": {
      "path": "work/example.exe",
      "signature": "<signature_from_step_5>"
    }
  }
}
```
**Expected:** Returns `matches: 1, unique: true`.

### 7. Export IPS Patch
```json
{
  "tool": "export",
  "args": {
    "module": "patch",
    "action": "export_patch",
    "params": {
      "original_path": "original/example.exe",
      "modified_path": "work/example.exe",
      "out_path": "/tmp/gold_patch.ips",
      "fmt": "ips"
    }
  }
}
```
**Expected:** Returns patch file info with hunks count.

### 8. Demonstrate Undo
```json
{
  "tool": "edit",
  "args": {
    "module": "hex",
    "action": "hex_patch",
    "params": {
      "path": "work/example.exe",
      "offset": 0x200,
      "bytes_hex": "90 90 90 90",
      "dry_run": false
    }
  }
}
```
Then:
```json
{
  "tool": "undo",
  "args": {}
}
```
**Expected:** File restored to original state, SHA-256 matches.

---

## Optional: Show Other Modules

### APK Manifest
```json
{
  "tool": "inspect",
  "args": {
    "module": "apk",
    "action": "apk_manifest",
    "params": { "apk_path": "tests/fixtures/fixture.apk" }
  }
}
```

### Table Operations
```json
{
  "tool": "inspect",
  "args": {
    "module": "tables",
    "action": "list_entries",
    "params": {
      "path": "tests/fixtures/table.bin",
      "schema": {
        "count_offset": 0,
        "offset_table": { "offset": 8, "count": 3 },
        "entry_size": 16,
        "fields": [
          { "name": "id", "offset": 0, "type": "uint32", "size": 4 },
          { "name": "hp", "offset": 4, "type": "float", "size": 4 },
          { "name": "mp", "offset": 8, "type": "int32", "size": 4 }
        ]
      }
    }
  }
}
```

### Format Lab
```json
{
  "tool": "inspect",
  "args": {
    "module": "format",
    "action": "entropy_map",
    "params": { "path": "work/example.exe", "block_size": 256, "limit": 10 }
  }
}
```

---

## Recording Tips

- Use `asciinema rec demo.cast` for terminal recording
- Or use `vhs` (video) with a `.tape` file
- Keep each step visible for 2-3 seconds
- Show JSON responses expanded in the terminal
- Total demo target: ~60-90 seconds