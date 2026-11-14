"""PE (EXE/DLL) analysis."""

from __future__ import annotations

import math
import os
import struct
import tempfile
from typing import Any, Dict, List, Optional

import pefile

from forge_mcp.core.external import find_executable, run_tool
from forge_mcp.core.platform import read_file, ensure_dir, IS_WINDOWS


def detect_compiler(pe: "pefile.PE", data: bytes, section_names: List[str]) -> List[Dict[str, Any]]:
    low = [s.lower() for s in section_names]
    guesses = []
    if pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress:
        guesses.append({"tool": "dotnet", "confidence": "high"})
    if b"Rich" in data[:0x400] and b"DanS" in data[:0x400]:
        guesses.append({"tool": "msvc", "confidence": "high"})
    if any(".text" in s for s in low) and any(".rdata" in s for s in low):
        guesses.append({"tool": "msvc-like", "confidence": "medium"})
    if any(s.startswith(".idata") or s == ".idata" for s in low) or any(
            n.lower() in (".edata",) for n in section_names):
        guesses.append({"tool": "mingw/gnu", "confidence": "medium"})
    if any(s in ("code", "data", "idata", "tls", "rdata", "reloc", "bss") for s in low):
        guesses.append({"tool": "delphi/borland", "confidence": "medium"})
    if ".gopclntab" in low or b"Go build" in data[:0x1000]:
        guesses.append({"tool": "go", "confidence": "high"})
    if ".rsrc" in low and b"UPX!" in data:
        guesses.append({"tool": "upx", "confidence": "high"})
    if b"UPX!" in data:
        guesses.append({"tool": "upx", "confidence": "medium"})
    if b".themida" in data.lower() or b"WinLicense" in data:
        guesses.append({"tool": "themida", "confidence": "medium"})
    if not guesses:
        guesses.append({"tool": "unknown", "confidence": "low"})
    return guesses


def _entropy(data: bytes) -> float:
    from collections import Counter
    if not data:
        return 0.0
    c = Counter(data)
    total = len(data)
    ent = 0.0
    for n in c.values():
        p = n / total
        ent -= p * math.log2(p)
    return ent


def pe_info(path: str) -> Dict[str, Any]:
    pe = pefile.PE(path, fast_load=False)
    raw = read_file(path, binary=True)
    sections = []
    for s in pe.sections:
        name = s.Name.split(b"\x00")[0].decode("latin-1", "replace")
        sections.append({
            "name": name,
            "virtual_address": s.VirtualAddress,
            "virtual_size": s.Misc_VirtualSize,
            "raw_offset": s.PointerToRawData,
            "raw_size": s.SizeOfRawData,
            "entropy": round(s.get_entropy(), 4),
            "characteristics": hex(s.Characteristics),
        })
    imports = []
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            dll = entry.dll.decode("latin-1", "replace")
            for imp in entry.imports:
                imports.append({"dll": dll, "name": (imp.name or b"").decode("latin-1", "replace"),
                                "address": imp.address})
    exports = []
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            exports.append({"name": (e.name or b"").decode("latin-1", "replace"),
                            "address": e.address, "ordinal": e.ordinal})
    section_names = [s["name"] for s in sections]
    machine = pe.FILE_HEADER.Machine
    arch = {0x14c: "x86", 0x8664: "x64", 0x1c0: "ARM", 0xaa64: "ARM64"}.get(machine, hex(machine))
    info = {
        "path": path,
        "machine": arch,
        "image_base": pe.OPTIONAL_HEADER.ImageBase,
        "entry_point": pe.OPTIONAL_HEADER.AddressOfEntryPoint,
        "entry_point_va": pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.AddressOfEntryPoint,
        "sections": sections,
        "imports_count": len(imports),
        "exports_count": len(exports),
        "imports": imports[:200],
        "exports": exports[:200],
        "timestamp": pe.FILE_HEADER.TimeDateStamp,
        "subsystem": pe.OPTIONAL_HEADER.Subsystem,
        "dll_characteristics": hex(pe.OPTIONAL_HEADER.DllCharacteristics),
        "compiler_guess": detect_compiler(pe, raw, section_names),
        "file_entropy": round(_entropy(raw), 4),
    }
    pe.close()
    return info


def find_function(pe_path: str, string_ref: Optional[str] = None,
                  name: Optional[str] = None) -> List[Dict[str, Any]]:
    pe = pefile.PE(pe_path)
    res = []
    if name:
        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                n = (e.name or b"").decode("latin-1", "replace")
                if name.lower() in n.lower():
                    res.append({"name": n, "rva": e.address, "va": pe.OPTIONAL_HEADER.ImageBase + e.address})
    if string_ref:
        data = read_file(pe_path, binary=True)
        needle = string_ref.encode("utf-8")
        offs = []
        i = 0
        while True:
            j = data.find(needle, i)
            if j < 0:
                break
            offs.append(j)
            i = j + 1
        for fo in offs:
            rva = None
            for s in pe.sections:
                if s.PointerToRawData <= fo < s.PointerToRawData + s.SizeOfRawData:
                    rva = s.VirtualAddress + (fo - s.PointerToRawData)
                    break
            res.append({"string": string_ref, "file_offset": fo, "rva": rva,
                        "va": (pe.OPTIONAL_HEADER.ImageBase + rva) if rva is not None else None})
    pe.close()
    return res


def make_signature(data: bytes, address: int, length: int = 32,
                   wildcard_offsets: Optional[List[int]] = None) -> Dict[str, Any]:
    wildcard_offsets = wildcard_offsets or []
    chunk = data[address:address + length]
    toks = []
    for i, b in enumerate(chunk):
        if i in wildcard_offsets:
            toks.append("??")
        else:
            toks.append(f"{b:02X}")
    sig = " ".join(toks)
    from forge_mcp.modules.hexops import parse_pattern, search_bytes
    needle, mask = parse_pattern(sig)
    hits = search_bytes(data, needle, mask)
    return {"signature": sig, "address": address, "length": length,
            "matches": len(hits), "unique": len(hits) == 1, "hit_offsets": hits[:10]}


def verify_signature(data: bytes, signature: str) -> Dict[str, Any]:
    from forge_mcp.modules.hexops import parse_pattern, search_bytes
    needle, mask = parse_pattern(signature)
    hits = search_bytes(data, needle, mask)
    return {"signature": signature, "matches": len(hits), "unique": len(hits) == 1,
            "hit_offsets": hits[:20]}


def match_across_builds(old_binary: str, new_binary: str, function_name: Optional[str] = None) -> Dict[str, Any]:
    old_funcs = find_function(old_binary, name=function_name) if function_name else []
    if not old_funcs:
        return {"error": "function not found in old binary"}
    f = old_funcs[0]
    pe = pefile.PE(old_binary)
    rva = f.get("rva")
    fo = None
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            fo = s.PointerToRawData + (rva - s.VirtualAddress)
            break
    pe.close()
    if fo is None:
        return {"error": "could not map rva to file offset"}
    data = read_file(old_binary, binary=True)
    sig = make_signature(data, fo, length=32)
    newdata = read_file(new_binary, binary=True)
    vr = verify_signature(newdata, sig["signature"])
    return {"old": f, "signature": sig["signature"], "new_matches": vr["matches"],
            "new_offsets": vr["hit_offsets"], "unique": vr["unique"]}


def emulate_function(code: bytes, entry_offset: int = 0, arch: str = "x64",
                     args: Optional[List[int]] = None, max_steps: int = 1000) -> Dict[str, Any]:
    try:
        import unicorn
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_RIP, UC_X86_REG_RSP, UC_X86_REG_RAX
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EAX
        from unicorn.x86_const import UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX
        from unicorn.x86_const import UC_X86_REG_RCX, UC_X86_REG_R8, UC_X86_REG_R9
    except Exception as e:
        return {"error": f"unicorn not available: {e}"}

    args = args or []
    if arch not in ("x64", "x86"):
        return {"error": f"unsupported arch {arch}"}

    CODE_BASE = 0x10000
    STACK_BASE = 0x20000
    RET_BASE = 0x30000
    PAGE = 0x10000

    uc = Uc(UC_ARCH_X86, UC_MODE_64 if arch == "x64" else UC_MODE_32)
    uc.mem_map(CODE_BASE, PAGE)
    uc.mem_map(STACK_BASE, PAGE)
    uc.mem_map(RET_BASE, PAGE)
    uc.mem_write(CODE_BASE, code)
    uc.mem_write(RET_BASE, b"\xcc")

    if arch == "x64":
        sp = STACK_BASE + PAGE // 2 - 8
        uc.mem_write(sp, struct.pack("<Q", RET_BASE))
        uc.reg_write(UC_X86_REG_RSP, sp)
        regs = [UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX,
                UC_X86_REG_RCX, UC_X86_REG_R8, UC_X86_REG_R9]
        for i, a in enumerate(args[:6]):
            uc.reg_write(regs[i], a & 0xFFFFFFFFFFFFFFFF)
    else:
        sp = STACK_BASE + PAGE // 2
        for a in reversed(args[:8]):
            sp -= 4
            uc.mem_write(sp, struct.pack("<I", a & 0xFFFFFFFF))
        sp -= 4
        uc.mem_write(sp, struct.pack("<I", RET_BASE))
        uc.reg_write(UC_X86_REG_ESP, sp)

    steps = {"count": 0}

    def hook_code(uc_, address, size, user_data):
        steps["count"] += 1
        if steps["count"] > max_steps or address == RET_BASE:
            uc_.emu_stop()

    uc.hook_add(unicorn.UC_HOOK_CODE, hook_code)

    entry = CODE_BASE + entry_offset
    try:
        uc.emu_start(entry, RET_BASE, count=max_steps)
    except Exception as e:
        pc = uc.reg_read(UC_X86_REG_RIP if arch == "x64" else UC_X86_REG_EIP)
        return {"error": str(e), "steps": steps["count"], "pc": hex(pc),
                "hint": "Function may call outside the mapped block or need more setup."}

    rax = uc.reg_read(UC_X86_REG_RAX if arch == "x64" else UC_X86_REG_EAX)
    return {"return_value": rax, "steps": steps["count"], "arch": arch,
            "entry": hex(entry), "ok": True}


def decompile_function(ghidra_home: Optional[str], binary: str, function_name: Optional[str] = None,
                       function_address: Optional[str] = None, timeout: int = 600) -> Dict[str, Any]:
    ah = find_executable("ghidra")
    if not ah:
        return {"error": "Ghidra not found. Set GHIDRA_HOME. https://github.com/NationalSecurityAgency/ghidra/releases"}
    outdir = tempfile.mkdtemp(prefix="forge_ghidra_")
    proj = os.path.join(outdir, "proj")
    ensure_dir(proj)
    script = os.path.join(outdir, "Decompile.java")
    script_content = f'''// Decompile
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.address.*;
public class Decompile extends GhidraScript {{
    public void run() throws Exception {{
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        FunctionManager fm = currentProgram.getFunctionManager();
        Function f = null;
        String name = "{function_name or ''}";
        if (!name.isEmpty()) {{
            for (Function fn : fm.getFunctions(true)) {{
                if (fn.getName().equals(name)) {{ f = fn; break; }}
            }}
        }}
        if (f == null) {{
            Address a = currentProgram.getAddressFactory().getAddress("{function_address or ''}");
            f = fm.getFunctionAt(a);
        }}
        if (f == null) {{ println("FUNCTION_NOT_FOUND"); return; }}
        DecompileResults r = di.decompileFunction(f, 60, monitor);
        println("===DECOMPILE_START===");
        println(r.getDecompiledFunction().getC());
        println("===DECOMPILE_END===");
    }}
}}
'''
    from forge_mcp.core.platform import write_file
    write_file(script, script_content)
    args = [proj, "forgeproj", "-import", binary, "-postScript", script, "-deleteProject"]
    tr = run_tool("ghidra", args, timeout=timeout, cwd=outdir)
    text = tr.stdout + "\n" + tr.stderr
    start = text.find("===DECOMPILE_START===")
    end = text.find("===DECOMPILE_END===")
    code = text[start + len("===DECOMPILE_START==="):end].strip() if start >= 0 and end >= 0 else ""
    return {"ok": tr.ok, "code": code, "stdout_tail": text[-2000:], "outdir": outdir}