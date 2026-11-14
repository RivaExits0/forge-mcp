"""APK / Android helpers."""

from __future__ import annotations

import os
import re
import zipfile
from typing import Any, Dict, List, Optional

from forge_mcp.core.external import find_executable, run_tool, get_apktool_jar, run_jar
from forge_mcp.core.platform import read_file, ensure_dir, IS_WINDOWS


def apk_unpack(apk_path: str, out_dir: str, framework: Optional[str] = None) -> Dict[str, Any]:
    apktool_exe = find_executable("apktool")
    if apktool_exe:
        ensure_dir(out_dir)
        args = ["d", apk_path, "-o", out_dir, "-f"]
        if framework:
            args += ["-p", framework]
        tr = run_tool("apktool", args, timeout=600)
        return {"ok": tr.ok, "out_dir": out_dir, "stdout": tr.stdout[-2000:],
                "stderr": tr.stderr[-2000:], "returncode": tr.returncode}

    # fallback: use apktool.jar if available
    jar = get_apktool_jar()
    if jar:
        ensure_dir(out_dir)
        args = ["d", apk_path, "-o", out_dir, "-f"]
        if framework:
            args += ["-p", framework]
        tr = run_jar(jar, args, timeout=600)
        return {"ok": tr.ok, "out_dir": out_dir, "stdout": tr.stdout[-2000:],
                "stderr": tr.stderr[-2000:], "returncode": tr.returncode}

    return {"error": "apktool not found. Install: https://apktool.org/docs/install"}


def apk_repack(src_dir: str, out_apk: str, sign: bool = True,
               keystore: Optional[str] = None, keypass: Optional[str] = None,
               storepass: Optional[str] = None, alias: Optional[str] = None) -> Dict[str, Any]:
    apktool_exe = find_executable("apktool")
    if apktool_exe:
        tr = run_tool("apktool", ["b", src_dir, "-o", out_apk, "-f"], timeout=600)
    else:
        jar = get_apktool_jar()
        if not jar:
            return {"error": "apktool not found."}
        tr = run_jar(jar, ["b", src_dir, "-o", out_apk, "-f"], timeout=600)
    if not tr.ok:
        return {"ok": False, "stage": "build", "stderr": tr.stderr[-2000:]}

    if sign:
        # try apksigner
        apksigner = find_executable("apksigner")
        if apksigner:
            args = ["sign"]
            if keystore:
                args += ["--ks", keystore]
            if storepass:
                args += ["--ks-pass", f"pass:{storepass}"]
            if keypass:
                args += ["--key-pass", f"pass:{keypass}"]
            args += [out_apk]
            tr2 = run_tool("apksigner", args, timeout=300)
            return {"ok": tr2.ok, "apk": out_apk, "stderr": tr2.stderr[-1000:]}

        # fallback: jarsigner
        jarsigner = find_executable("jarsigner")
        if jarsigner:
            args = ["-sigalg", "SHA256withRSA", "-digestalg", "SHA-256"]
            if keystore:
                args += ["-keystore", keystore]
            if storepass:
                args += ["-storepass", storepass]
            if keypass:
                args += ["-keypass", keypass]
            args += [out_apk, alias or "alias"]
            tr2 = run_tool("jarsigner", args, timeout=300)
            return {"ok": tr2.ok, "apk": out_apk, "stderr": tr2.stderr[-1000:]}

        return {"ok": True, "apk": out_apk, "note": "built but not signed (no signer found)"}
    return {"ok": True, "apk": out_apk}


def apk_manifest(apk_path: str) -> Dict[str, Any]:
    sources = []
    text = ""
    for tool in ("aapt2", "aapt"):
        exe = find_executable(tool)
        if not exe:
            continue
        tr = run_tool(tool, ["dump", "badging", apk_path], timeout=120)
        if tr.ok and tr.stdout.strip():
            text = tr.stdout
            sources.append(tool)
            break
        if tr.stdout.strip():
            text = tr.stdout
            sources.append(tool + "(partial)")
    if not text:
        try:
            z = zipfile.ZipFile(apk_path)
            raw = z.read("AndroidManifest.xml")
            if raw[:5] == b"<?xml" or b"<manifest" in raw[:200]:
                text = raw.decode("utf-8", "replace")
                sources.append("zip(plain-xml)")
            else:
                strings = re.findall(rb"[\x20-\x7e]{4,}", raw)
                text = "\n".join(s.decode("ascii", "replace") for s in strings)
                sources.append("zip(binary-axml-strings)")
        except Exception as e:
            text = ""
            sources.append(f"zip(error: {e})")

    perms = re.findall(r"android\.permission\.[A-Z_]+", text)
    activities = re.findall(r"[A-Za-z0-9_.$]+Activity", text)
    services = re.findall(r"[A-Za-z0-9_.$]+Service", text)
    receivers = re.findall(r"[A-Za-z0-9_.$]+Receiver", text)
    pkg = None
    m = re.search(r"package=['\"]([^'\"]+)['\"]", text)
    if m:
        pkg = m.group(1)
    exported = len(re.findall(r"exported[\"']?\s*[:=]\s*[\"']?true", text, re.I))
    native_libs = []
    try:
        z = zipfile.ZipFile(apk_path)
        native_libs = [n for n in z.namelist() if n.endswith(".so")][:100]
    except Exception:
        pass
    return {
        "sources": sources,
        "package": pkg,
        "permissions": sorted(set(perms)),
        "activities": sorted(set(activities))[:100],
        "services": sorted(set(services))[:100],
        "receivers": sorted(set(receivers))[:100],
        "exported_components_count": exported,
        "native_libs": native_libs,
        "raw_excerpt": text[:4000],
    }


def smali_search(src_dir: str, query: str, limit: int = 100) -> List[Dict[str, Any]]:
    hits = []
    for root, _, files in os.walk(src_dir):
        for fn in files:
            if not fn.endswith(".smali"):
                continue
            p = os.path.join(root, fn)
            try:
                content = read_file(p)
                for i, line in enumerate(content.splitlines(), 1):
                    if query in line:
                        hits.append({"file": os.path.relpath(p, src_dir),
                                     "line": i, "text": line.rstrip()})
                        if len(hits) >= limit:
                            return hits
            except OSError:
                continue
    return hits


def smali_patch(src_dir: str, file_rel: str, old: str, new: str, dry_run: bool = True) -> Dict[str, Any]:
    p = os.path.join(src_dir, file_rel)
    if not os.path.isfile(p):
        return {"error": f"file not found: {p}"}
    content = read_file(p)
    count = content.count(old)
    if count == 0:
        return {"error": "pattern not found", "matches": 0}
    if dry_run:
        return {"dry_run": True, "matches": count, "preview": content.replace(old, new, 1)[:2000]}
    new_content = content.replace(old, new)
    from forge_mcp.core.platform import write_file
    write_file(p, new_content)
    return {"dry_run": False, "matches": count, "written": p}


def native_lib_info(so_path: str) -> Dict[str, Any]:
    try:
        import lief
        binf = lief.parse(so_path)
        exports = [e.name for e in binf.exported_functions][:200]
        imports = [i.name for i in binf.imported_functions][:200]
        return {"path": so_path, "format": str(binf.format) if hasattr(binf, "format") else "ELF",
                "arch": str(binf.header.machine_type) if hasattr(binf, "header") else None,
                "exports": exports, "imports": imports}
    except Exception as e:
        readelf = find_executable("readelf")
        if readelf:
            tr = run_tool("readelf", ["-Ws", so_path], timeout=120)
            return {"error": None if tr.ok else tr.stderr, "readelf_excerpt": tr.stdout[:4000]}
        return {"error": str(e)}


def resource_extract(apk_path: str, out_dir: str, pattern: Optional[str] = None) -> Dict[str, Any]:
    ensure_dir(out_dir)
    z = zipfile.ZipFile(apk_path)
    extracted = []
    import fnmatch
    for info in z.infolist():
        if pattern and not fnmatch.fnmatch(info.filename, pattern):
            continue
        if info.is_dir():
            continue
        target = os.path.join(out_dir, info.filename)
        ensure_dir(os.path.dirname(target))
        with z.open(info) as src:
            from forge_mcp.core.platform import write_file
            write_file(target, src.read(), binary=True)
        extracted.append(info.filename)
    return {"count": len(extracted), "files": extracted[:200]}


def il2cpp_dump(global_metadata: str, binary: Optional[str] = None,
                out_dir: Optional[str] = None) -> Dict[str, Any]:
    if not os.path.isfile(global_metadata):
        return {"error": f"file not found: {global_metadata}"}
    data = read_file(global_metadata, binary=True)
    import struct
    magic = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0
    strs = []
    cur = bytearray()
    for b in data:
        if 32 <= b < 127:
            cur.append(b)
        else:
            if len(cur) >= 4:
                s = cur.decode("ascii", "replace")
                if any(c.isalpha() for c in s):
                    strs.append(s)
            cur = bytearray()
    if len(cur) >= 4:
        s = cur.decode("ascii", "replace")
        if any(c.isalpha() for c in s):
            strs.append(s)
    seen = set()
    uniq = []
    for s in strs:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    dumper = find_executable("Il2CppDumper") or find_executable("il2cppdumper")
    dumper_result = None
    if dumper and binary:
        out = out_dir or os.path.join(os.path.dirname(global_metadata), "il2cpp_dump")
        ensure_dir(out)
        if IS_WINDOWS and dumper.endswith(".exe"):
            tr = run_tool("il2cppdumper", [binary, global_metadata, out], timeout=600)
        else:
            tr = run_jar(dumper, [binary, global_metadata, out], timeout=600)
        dumper_result = {"ok": tr.ok, "out_dir": out, "stderr": tr.stderr[-1000:]}
    return {
        "magic": hex(magic),
        "size": len(data),
        "string_count": len(uniq),
        "sample_strings": uniq[:200],
        "il2cppdumper": dumper_result,
        "note": "For full type/method/field names use Il2CppDumper; set IL2CPP env or place on PATH.",
    }