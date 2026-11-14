# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-11-14

### Added
- Initial release of Forge-Mcp MCP server for game modding helpers
- 10 top-level MCP tools: `open_game`, `inspect`, `search`, `edit`, `patch_code`, `rebuild`, `validate`, `export`, `diagnose`, `undo`
- Cross-platform support (Windows/Linux) via `platform_utils.py`
- Per-game workspace management with read-only originals and working copies
- Automatic snapshots before every write with SHA-256 verified undo
- Hex operations: view, search (AOB/wildcard/string), diff, value-scan, patch, pointer chains, offset calculation, checksum fix
- PE analysis: sections, imports/exports, compiler/packer detection, signature generation/verification, cross-build matching, Unicorn emulation, Ghidra headless decompile
- APK support: unpack/repack with signing, manifest parsing, smali search/patch, native library info, Il2Cpp dump
- Unity asset handling (AssetBundle, .assets) via UnityPy
- Unreal .pak operations via UnrealPak with AES key support
- Schema-driven table editing (list, clone, edit, rebuild, validate, references)
- Archive operations (zip, tar, 7z, unrar)
- Format lab: entropy mapping, decoding attempts, field guessing, template generation (.ksy/.hexpat)
- Dynamic analysis: Frida script generation, trace diff
- Diagnostics: crash log parsing, dependency checking, mod conflict detection, bisect planning, load order suggestions
- Export: IPS/xdelta patches, Cheat Engine .CT tables, changelog generation
- Game profile/adapter system (profile.toml, signatures.json, schema.ksy)
- Comprehensive test suite (23 tests passing)
- CI pipeline (GitHub Actions: ubuntu-latest + windows-latest, Python 3.11/3.12)

### Security
- Read-only originals enforced
- Path traversal protection
- No binary execution (static analysis only)
- Frida scripts generated but never executed by server
- Single-player/owned copies only; no anti-cheat bypass or DRM removal

[0.1.0]: https://github.com/RivaExits0/forge-mcp/releases/tag/v0.1.0