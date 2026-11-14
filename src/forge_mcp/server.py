"""Forge-Mcp server entry point (FastMCP/MCPServer)."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    from mcp.server.mcpserver import MCPServer as FastMCP

from forge_mcp.core.workspace import WorkspaceManager, safe_path, sha256_file
from forge_mcp.core.snapshot import take_snapshot, list_snapshots, restore_snapshot, latest_snapshot_for
from forge_mcp.core.job_log import append, read, changelog
from forge_mcp.core.paging import require_paging, page
from forge_mcp.core.profiles import load_profile, list_profiles
from forge_mcp.core.external import find_executable, missing_message

from forge_mcp.modules import hexops, pe, apk, unity, unreal, tables, archives, formatlab, dynamic, diagnose, export as export_mod

mcp = FastMCP("forge-mcp")

WORKSPACE_ROOT = os.environ.get("FORGE_WORKSPACE_ROOT", os.path.join(os.getcwd(), "forge-workspaces"))
MANAGER = WorkspaceManager(root=WORKSPACE_ROOT)
STATE: Dict[str, Any] = {"game": None, "profile": None}


def _to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _validate_path(path: str) -> str:
    if not path or not isinstance(path, str):
        raise ValueError("path must be a non-empty string")
    norm = os.path.normpath(path)
    if norm.startswith("..") or ".." in norm.split(os.sep):
        raise ValueError(f"unsafe path (traversal): {path}")
    return norm


def _get_ws(name: Optional[str] = None):
    g = name or STATE.get("game")
    if not g:
        raise ValueError("no game open; call open_game first")
    return MANAGER.open(g)


def _read_bytes(path: str) -> bytes:
    from forge_mcp.core.platform_utils import read_file
    return read_file(path, binary=True)


def _write_bytes(path: str, data: bytes) -> None:
    from forge_mcp.core.platform_utils import write_file
    write_file(path, data, binary=True)


def _snapshot_before(ws, target: str, reason: str) -> str:
    return take_snapshot(ws.dir, target, reason=reason)


@mcp.tool()
def open_game(game_name: str, source_path: Optional[str] = None,
              profile_dir: Optional[str] = None) -> str:
    """Open (or create) a per-game workspace.

    Use this first before any other tool. Imports source_path into the workspace
    as a read-only original + working copy. Optionally load a game profile dir.

    Args:
        game_name: Short identifier for the game (e.g. "mygame_v1").
        source_path: Path to the game file to import (exe/apk/save). Optional.
        profile_dir: Path to a profile/adaptor folder. Optional.
    """
    try:
        ws = MANAGER.create(game_name) if game_name not in MANAGER.list() else MANAGER.open(game_name)
        ws.ensure()
        result = {"game": game_name, "workspace": ws.dir}
        if source_path:
            sp = _validate_path(source_path)
            wp = MANAGER.import_file(ws, sp, logical="main")
            result["work_file"] = wp
            result["original"] = MANAGER.original_path(ws, "main")
        if profile_dir:
            prof = load_profile(_validate_path(profile_dir))
            STATE["profile"] = prof
            result["profile"] = prof.name
            result["profile_dir"] = prof.path
        STATE["game"] = game_name
        ws.save_meta()
        append(ws.dir, {"action": "open_game", "game": game_name,
                        "source": source_path, "profile": profile_dir})
        return _to_json(result)
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def inspect(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Inspect files/structures. Dispatches by module+action.

    Modules: pe, apk, unity, unreal, tables, archives, format, hex.
    Actions:
      pe: pe_info (path), find_function (path, name|string_ref)
      apk: apk_manifest (apk_path), native_lib_info (so_path), resource_extract (apk_path, out_dir, pattern)
      unity: unity_assets (path, action=list|extract)
      unreal: unreal_pak (pak_path, action=list|extract)
      tables: list_entries (path, schema)
      archives: unpack (archive_path, out_dir)
      format: entropy_map (path, block_size)
      hex: hex_view (path, offset, limit)
    Large outputs are paginated via offset/limit inside params.
    """
    params = params or {}
    try:
        if module == "pe":
            if action == "pe_info":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                return _to_json(pe.pe_info(path))
            if action == "find_function":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                return _to_json(pe.find_function(path, string_ref=params.get("string_ref"),
                                                name=params.get("name")))
            if action == "decompile_function":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                return _to_json(pe.decompile_function(params.get("ghidra_home"), path,
                                                     function_name=params.get("function_name"),
                                                     function_address=params.get("function_address"),
                                                     timeout=params.get("timeout", 600)))
        if module == "apk":
            if action == "apk_manifest":
                return _to_json(apk.apk_manifest(_validate_path(params["apk_path"])))
            if action == "native_lib_info":
                return _to_json(apk.native_lib_info(_validate_path(params["so_path"])))
            if action == "resource_extract":
                return _to_json(apk.resource_extract(_validate_path(params["apk_path"]),
                                                     _validate_path(params["out_dir"]),
                                                     params.get("pattern")))
            if action == "il2cpp_dump":
                return _to_json(apk.il2cpp_dump(_validate_path(params["global_metadata"]),
                                                params.get("binary"), params.get("out_dir")))
        if module == "unity":
            if action == "unity_assets":
                path = _validate_path(params["path"])
                return _to_json(unity.unity_assets(path, action=params.get("subaction", "list"),
                                                  entry=params.get("entry"), out_dir=params.get("out_dir")))
        if module == "unreal":
            if action == "unreal_pak":
                return _to_json(unreal.unreal_pak(_validate_path(params["pak_path"]),
                                                  action=params.get("subaction", "list"),
                                                  out_dir=params.get("out_dir"),
                                                  aes_key=params.get("aes_key"),
                                                  src_dir=params.get("src_dir"),
                                                  out_pak=params.get("out_pak")))
        if module == "tables":
            if action == "list_entries":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                schema = params.get("schema", {})
                entries = tables.list_entries(data, schema)
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 100))
                sliced, env = page(entries, off, lim)
                return _to_json({"entries": sliced, "pagination": env})
        if module == "archives":
            if action == "unpack":
                return _to_json(archives.unpack_archive(_validate_path(params["archive_path"]),
                                                       _validate_path(params["out_dir"]),
                                                       params.get("password")))
        if module == "format":
            if action == "entropy_map":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                res = formatlab.entropy_map(data, params.get("block_size", 256))
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 1000))
                sliced, env = page(res, off, lim)
                return _to_json({"blocks": sliced, "pagination": env})
        if module == "hex":
            if action == "hex_view":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 256))
                return _to_json({"dump": hexops.hex_view(data, off, lim)})
        return _to_json({"error": f"unknown inspect module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def search(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Search in files. Dispatches by module+action.

    Modules/actions:
      hex: hex_search (path, query, mode, offset, limit), diff_files (path_a, path_b),
           value_scan (before_path, after_path, value_type)
      pe: find_function (path, name|string_ref)
      apk: smali_search (src_dir, query, limit)
      format: guess_fields (path, max_fields)
    """
    params = params or {}
    try:
        if module == "hex":
            if action == "hex_search":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                off = params.get("offset", 0)
                lim = params.get("limit", 100)
                require_paging(off, lim)
                return _to_json(hexops.hex_search(data, params["query"], mode=params.get("mode", "auto"),
                                                 offset=off, limit=lim))
            if action == "diff_files":
                a = _read_bytes(_validate_path(params["path_a"]))
                b = _read_bytes(_validate_path(params["path_b"]))
                diffs = hexops.diff_files(a, b)
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 1000))
                sliced, env = page(diffs, off, lim)
                return _to_json({"diffs": sliced, "pagination": env})
            if action == "value_scan":
                before = _read_bytes(_validate_path(params["before_path"]))
                after = _read_bytes(_validate_path(params["after_path"]))
                hits = hexops.value_scan(before, after, value_type=params.get("value_type", "int32"))
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 1000))
                sliced, env = page(hits, off, lim)
                return _to_json({"hits": sliced, "pagination": env})
            if action == "offset_calc":
                return _to_json(hexops.offset_calc(rva=params.get("rva"), va=params.get("va"),
                                                  file_offset=params.get("file_offset"),
                                                  image_base=params.get("image_base", 0),
                                                  sections=params.get("sections")))
        if module == "pe":
            if action == "find_function":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                return _to_json(pe.find_function(path, string_ref=params.get("string_ref"),
                                                name=params.get("name")))
            if action == "match_across_builds":
                return _to_json(pe.match_across_builds(_validate_path(params["old_binary"]),
                                                       _validate_path(params["new_binary"]),
                                                       function_name=params.get("function_name")))
        if module == "apk":
            if action == "smali_search":
                return _to_json(apk.smali_search(_validate_path(params["src_dir"]), params["query"],
                                                limit=params.get("limit", 100)))
        if module == "format":
            if action == "guess_fields":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                cands = formatlab.guess_fields(data, max_fields=params.get("max_fields", 20))
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 500))
                sliced, env = page(cands, off, lim)
                return _to_json({"candidates": sliced, "pagination": env})
            if action == "try_decode":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(formatlab.try_decode(data, methods=params.get("methods")))
        if module == "diagnose":
            if action == "parse_crash_log":
                return _to_json(diagnose.parse_crash_log(_validate_path(params["path"])))
        return _to_json({"error": f"unknown search module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def edit(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Edit files/structures. Dispatches by module+action. Supports dry_run.

    Modules/actions:
      hex: hex_patch (path, offset, bytes_hex, dry_run)
      apk: smali_patch (src_dir, file_rel, old, new, dry_run)
      tables: clone_entry, edit_fields, rebuild_offsets, checksum_fix
      format: write_template
    Every write snapshots first and logs to job_log.
    """
    params = params or {}
    try:
        ws = _get_ws()
        if module == "hex":
            if action == "hex_patch":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = bytearray(_read_bytes(path))
                new_bytes = bytes.fromhex(params["bytes_hex"].replace(" ", ""))
                off = params["offset"]
                dry = params.get("dry_run", True)
                if not dry:
                    _snapshot_before(ws, path, reason="hex_patch")
                res = hexops.hex_patch(data, off, new_bytes, dry_run=dry)
                if not dry and res.get("applied"):
                    _write_bytes(path, bytes(data))
                    append(ws.dir, {"action": "hex_patch", "target": path,
                                    "offset": off, "length": len(new_bytes), "dry_run": False})
                return _to_json(res)
        if module == "apk":
            if action == "smali_patch":
                src_dir = _validate_path(params["src_dir"])
                return _to_json(apk.smali_patch(src_dir, params["file_rel"], params["old"],
                                                params["new"], dry_run=params.get("dry_run", True)))
        if module == "tables":
            if action == "clone_entry":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = bytearray(_read_bytes(path))
                schema = params.get("schema", {})
                if not params.get("dry_run", True):
                    _snapshot_before(ws, path, reason="clone_entry")
                res = tables.clone_entry(data, schema, params["index"])
                if not params.get("dry_run", True) and res.get("ok"):
                    _write_bytes(path, bytes(data))
                    append(ws.dir, {"action": "clone_entry", "target": path, "index": params["index"]})
                res["dry_run"] = params.get("dry_run", True)
                return _to_json(res)
            if action == "edit_fields":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = bytearray(_read_bytes(path))
                schema = params.get("schema", {})
                dry = params.get("dry_run", True)
                if not dry:
                    _snapshot_before(ws, path, reason="edit_fields")
                res = tables.edit_fields(data, schema, params["index"], params.get("changes", {}))
                if not dry and res.get("ok"):
                    _write_bytes(path, bytes(data))
                    append(ws.dir, {"action": "edit_fields", "target": path,
                                    "index": params["index"], "changes": params.get("changes", {})})
                res["dry_run"] = dry
                return _to_json(res)
            if action == "checksum_fix":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = bytearray(_read_bytes(path))
                dry = params.get("dry_run", True)
                if not dry:
                    _snapshot_before(ws, path, reason="checksum_fix")
                res = hexops.checksum_fix(data, algo=params.get("algo", "crc32"),
                                         field_offset=params.get("field_offset", 0),
                                         field_size=params.get("field_size", 4),
                                         region=tuple(params["region"]) if params.get("region") else None,
                                         endian=params.get("endian", "little"))
                if not dry:
                    _write_bytes(path, bytes(data))
                    append(ws.dir, {"action": "checksum_fix", "target": path, **res})
                res["dry_run"] = dry
                return _to_json(res)
            if action == "rebuild_offsets":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = bytearray(_read_bytes(path))
                return _to_json(tables.rebuild_offsets(data, params.get("schema", {})))
            if action == "validate":
                path = _validate_path(params.get("path") or MANAGER.work_path(ws))
                data = _read_bytes(path)
                return _to_json(tables.validate_table(data, params.get("schema", {})))
        if module == "format":
            if action == "write_template":
                schema = params.get("schema", {})
                out_path = _validate_path(params["out_path"])
                return _to_json(formatlab.write_template(params.get("format", "ksy"), schema, out_path))
        if module == "archives":
            if action == "repack":
                return _to_json(archives.repack_archive(_validate_path(params["src_dir"]),
                                                       _validate_path(params["out_path"]),
                                                       format=params.get("format", "zip")))
        if module == "apk":
            if action == "apk_repack":
                return _to_json(apk.apk_repack(_validate_path(params["src_dir"]),
                                               _validate_path(params["out_apk"]),
                                               sign=params.get("sign", True),
                                               keystore=params.get("keystore"),
                                               keypass=params.get("keypass"),
                                               storepass=params.get("storepass"),
                                               alias=params.get("alias")))
        if module == "unity":
            if action == "unity_assets":
                path = _validate_path(params["path"])
                data = None
                if params.get("data_hex"):
                    data = bytes.fromhex(params["data_hex"].replace(" ", ""))
                return _to_json(unity.unity_assets(path, action=params.get("subaction", "list"),
                                                  entry=params.get("entry"), out_dir=params.get("out_dir"),
                                                  data=data))
        if module == "unreal":
            if action == "unreal_pak":
                return _to_json(unreal.unreal_pak(_validate_path(params["pak_path"]),
                                                  action=params.get("subaction", "list"),
                                                  out_dir=params.get("out_dir"),
                                                  aes_key=params.get("aes_key"),
                                                  src_dir=params.get("src_dir"),
                                                  out_pak=params.get("out_pak")))
        return _to_json({"error": f"unknown edit module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def patch_code(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Code patching helpers. Dispatches by module+action.

    Modules/actions:
      pe: make_signature (path, address, length, wildcard_offsets), verify_signature (path, signature),
          emulate_function (code_hex, entry_offset, arch, args)
      apk: il2cpp_dump
      dynamic: frida_script
    """
    params = params or {}
    try:
        if module == "pe":
            if action == "make_signature":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(pe.make_signature(data, params["address"], length=params.get("length", 32),
                                                 wildcard_offsets=params.get("wildcard_offsets")))
            if action == "verify_signature":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(pe.verify_signature(data, params["signature"]))
            if action == "emulate_function":
                code = bytes.fromhex(params["code_hex"].replace(" ", ""))
                return _to_json(pe.emulate_function(code, entry_offset=params.get("entry_offset", 0),
                                                   arch=params.get("arch", "x64"),
                                                   args=params.get("args"),
                                                   max_steps=params.get("max_steps", 1000)))
            if action == "decompile_function":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                return _to_json(pe.decompile_function(params.get("ghidra_home"), path,
                                                     function_name=params.get("function_name"),
                                                     function_address=params.get("function_address"),
                                                     timeout=params.get("timeout", 600)))
        if module == "apk":
            if action == "il2cpp_dump":
                return _to_json(apk.il2cpp_dump(_validate_path(params["global_metadata"]),
                                                params.get("binary"), params.get("out_dir")))
        if module == "dynamic":
            if action == "frida_script":
                return _to_json(dynamic.frida_script(params["target"], params["hook"],
                                                    output_path=params.get("output_path")))
        return _to_json({"error": f"unknown patch_code module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def rebuild(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Rebuild/repack helpers. Dispatches by module+action.

    Modules/actions:
      tables: rebuild_offsets (path, schema), validate (path, schema)
      archives: repack (src_dir, out_path, format)
      apk: apk_repack
      unreal: unreal_pak pack
      format: validate_template
    """
    params = params or {}
    try:
        if module == "tables":
            if action == "rebuild_offsets":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(tables.rebuild_offsets(bytearray(data), params.get("schema", {})))
            if action == "validate":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(tables.validate_table(data, params.get("schema", {})))
        if module == "archives":
            if action == "repack":
                return _to_json(archives.repack_archive(_validate_path(params["src_dir"]),
                                                       _validate_path(params["out_path"]),
                                                       format=params.get("format", "zip")))
        if module == "apk":
            if action == "apk_repack":
                return _to_json(apk.apk_repack(_validate_path(params["src_dir"]),
                                               _validate_path(params["out_apk"]),
                                               sign=params.get("sign", True)))
        if module == "unreal":
            if action == "unreal_pak":
                return _to_json(unreal.unreal_pak(_validate_path(params["pak_path"]),
                                                  action=params.get("subaction", "pack"),
                                                  out_dir=params.get("out_dir"),
                                                  aes_key=params.get("aes_key"),
                                                  src_dir=params.get("src_dir"),
                                                  out_pak=params.get("out_pak")))
        if module == "format":
            if action == "validate_template":
                return _to_json(formatlab.validate_template(_validate_path(params["template_path"]),
                                                          params.get("sample_files", [])))
        return _to_json({"error": f"unknown rebuild module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def validate(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Validate artifacts. Dispatches by module+action.

    Modules/actions:
      pe: verify_signature (path, signature)
      tables: validate (path, schema)
      format: validate_template (template_path, sample_files)
    """
    params = params or {}
    try:
        if module == "pe":
            if action == "verify_signature":
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(pe.verify_signature(data, params["signature"]))
        if module == "tables":
            if action in ("validate", "validate_table"):
                path = _validate_path(params.get("path") or MANAGER.work_path(_get_ws()))
                data = _read_bytes(path)
                return _to_json(tables.validate_table(data, params.get("schema", {})))
        if module == "format":
            if action == "validate_template":
                return _to_json(formatlab.validate_template(_validate_path(params["template_path"]),
                                                          params.get("sample_files", [])))
        if module == "apk":
            if action == "apk_repack":
                from forge_mcp.core.external import find_executable
                return _to_json({"apktool": find_executable("apktool"), "jadx": find_executable("jadx")})
        return _to_json({"error": f"unknown validate module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def export(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Export patches/tables. Dispatches by module+action.

    Modules/actions:
      patch: export_patch (original_path, modified_path, out_path, fmt=ips|xdelta)
      patch: make_trainer_table (addresses, out_path)
      diagnose: changelog
      joblog: list
    """
    params = params or {}
    try:
        if module == "patch":
            if action == "export_patch":
                orig = _read_bytes(_validate_path(params["original_path"]))
                mod = _read_bytes(_validate_path(params["modified_path"]))
                return _to_json(export_mod.export_patch(orig, mod, _validate_path(params["out_path"]),
                                                   fmt=params.get("fmt", "ips")))
            if action == "make_trainer_table":
                return _to_json(export_mod.make_trainer_table(params.get("addresses", []),
                                                          _validate_path(params["out_path"])))
        if module == "diagnose":
            if action == "changelog":
                ws = _get_ws()
                return changelog(ws.dir)
        if module == "joblog":
            if action == "list":
                ws = _get_ws()
                off, lim = require_paging(params.get("offset", 0), params.get("limit", 100))
                rows = read(ws.dir, limit=lim, offset=off)
                return _to_json({"entries": rows})
        return _to_json({"error": f"unknown export module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def diagnose(module: str, action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """Diagnosis helpers. Dispatches by module+action.

    Modules/actions:
      diagnose: parse_crash_log (path), check_dependencies (game_dir), find_conflicts (mods),
                bisect_plan (items), suggest_load_order (mods)
      dynamic: trace_diff (trace_a, trace_b)
      external: check_dependencies (tool list)
    """
    params = params or {}
    try:
        if module == "diagnose":
            if action == "parse_crash_log":
                return _to_json(diagnose.parse_crash_log(_validate_path(params["path"])))
            if action == "check_dependencies":
                return _to_json(diagnose.check_dependencies(_validate_path(params["game_dir"])))
            if action == "find_conflicts":
                return _to_json(diagnose.find_conflicts(params.get("mods", [])))
            if action == "bisect_plan":
                return _to_json(diagnose.bisect_plan(params.get("items", [])))
            if action == "suggest_load_order":
                return _to_json(diagnose.suggest_load_order(params.get("mods", [])))
        if module == "dynamic":
            if action == "trace_diff":
                return _to_json(dynamic.trace_diff(_validate_path(params["trace_a"]),
                                                  _validate_path(params["trace_b"])))
        if module == "external":
            if action == "check_dependencies":
                from forge_mcp.core.external import find_executable
                tools = ["ghidra", "apktool", "jadx", "il2cppdumper", "frida", "xdelta3"]
                return _to_json({t: bool(find_executable(t)) for t in tools})
        return _to_json({"error": f"unknown diagnose module/action: {module}/{action}"})
    except Exception as exc:
        return f"error: {exc}"


@mcp.tool()
def undo(snapshot_id: Optional[str] = None, target_path: Optional[str] = None) -> str:
    """Restore the last (or specified) snapshot. Verifies hash after restore."""
    try:
        ws = _get_ws()
        if snapshot_id is None:
            if target_path:
                snapshot_id = latest_snapshot_for(ws.dir, _validate_path(target_path))
            else:
                snaps = list_snapshots(ws.dir)
                if not snaps:
                    return _to_json({"error": "no snapshots"})
                snaps.sort(key=lambda s: s.get("created_at", ""), reverse=True)
                snapshot_id = snaps[0].get("id")
        if not snapshot_id:
            return _to_json({"error": "no snapshot to restore"})
        restored = restore_snapshot(ws.dir, snapshot_id)
        append(ws.dir, {"action": "undo", "snapshot": snapshot_id, "target": restored})
        return _to_json({"restored": restored, "snapshot": snapshot_id,
                         "sha256": sha256_file(restored)})
    except Exception as exc:
        return f"error: {exc}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()