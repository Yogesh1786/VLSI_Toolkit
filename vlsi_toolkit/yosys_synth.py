"""Run real logic synthesis with Yosys and summarize the result.

Uses a native `yosys` from PATH when installed (OSS CAD Suite), otherwise the
WebAssembly build from PyPI (`pip install yowasp-yosys`), which runs anywhere Python does,
including the hosted server.

    synthesize(files, top=None, flatten=False) -> {
        top, modules: [{name, cells, seq, comb, nand2_eq, cell_types}], totals, logic_depth,
        warnings, latches, black_boxes, netlist, engine, abc, seconds }

Modules that are instantiated but not defined (memories, IP, library cells) are kept as black boxes.

Technology mapping uses Yosys's generic gate library ($_AND_, $_OR_, $_MUX_, $_DFF_* ...).
"NAND2 equivalents" are a rough, library-independent size estimate.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
TIMEOUT = 120                     # seconds per Yosys run
MAX_SOURCE_BYTES = 2 * 1024 * 1024

# rough NAND2-equivalent size of each generic Yosys cell
NAND2_EQ = {
    "$_NOT_": 0.67, "$_BUF_": 0.67, "$_AND_": 1.33, "$_NAND_": 1.0, "$_OR_": 1.33, "$_NOR_": 1.0,
    "$_XOR_": 2.33, "$_XNOR_": 2.33, "$_ANDNOT_": 1.33, "$_ORNOT_": 1.33, "$_MUX_": 2.33, "$_NMUX_": 2.33,
    "$_AOI3_": 1.33, "$_OAI3_": 1.33, "$_AOI4_": 1.67, "$_OAI4_": 1.67, "$_MUX4_": 5.0, "$_MUX8_": 10.0,
}
SEQ_RE = re.compile(r"^\$_(S?DFF|DFFE|SDFFE|SDFFCE|ALDFF|DFFSR|DFFSRE|DLATCH|SR)")
LATCH_RE = re.compile(r"^\$_(DLATCH|SR)")


class SynthError(Exception):
    pass


def engine():
    """('native', path) if yosys is installed, ('wasm', None) if yowasp-yosys is, else (None, None)."""
    native = shutil.which("yosys")
    if native:
        return "native", native
    try:
        import yowasp_yosys  # noqa: F401
        return "wasm", None
    except ImportError:
        return None, None


def _cmd(kind, native):
    if kind == "native":
        return [native]
    return [sys.executable, "-c", "import sys, yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))"]


def _env():
    env = dict(os.environ)
    env.setdefault("YOWASP_CACHE_DIR", str(PROJECT_DIR / ".yowasp-cache"))
    return env


def warm_up():
    """Compile the WebAssembly Yosys once (slow the first time, then cached). Used at deploy time."""
    kind, native = engine()
    if kind is None:
        raise SynthError("Yosys is not installed: pip install yowasp-yosys")
    subprocess.run(_cmd(kind, native) + ["-q", "-p", "help"], env=_env(), capture_output=True, timeout=900)
    return kind


def _safe_name(name, used):
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).name) or "design.v"
    if not base.lower().endswith((".v", ".sv", ".vh", ".svh")):
        base += ".v"
    stem, n = base, 1
    while base in used:
        base = f"{n}_{stem}"
        n += 1
    used.add(base)
    return base


def _clean_name(raw):
    """'\\uart_tx' -> 'uart_tx'; '$paramod$3f2a...\\sync_fifo' -> 'sync_fifo' (a parameterized copy)."""
    raw = raw.lstrip("\\")
    return raw.split("\\")[-1] if raw.startswith("$paramod") else raw


def _clean_message(msg):
    msg = re.sub(r":\s*\$auto\$\S+$", "", msg)          # trailing Yosys-internal cell names
    msg = re.sub(r"\$paramod\$[0-9a-f]+\\", "", msg)
    msg = msg.replace("`\\", "`").replace(".\\", ".")
    # "$or$lint_demo.v:38$6_Y" -> "or at lint_demo.v:38";  "$proc$x.v:21$3" -> "proc at x.v:21"
    msg = re.sub(r"\$(\w+)\$([\w./-]+):(\d+)\$\d+(?:_\w+)?", r"\1 at \2:\3", msg)
    return msg.strip().rstrip(":")


def _parse_warnings(log):
    warnings, latches = [], []
    for line in log.splitlines():
        line = line.strip()
        if not line.startswith("Warning:"):
            continue
        msg = _clean_message(line[len("Warning:"):].strip())
        msg = re.sub(r" \[\d+\]$", " (bus)", msg)        # one warning per bus, not per bit
        m = re.search(r"Latch inferred for signal `([^']+)'", msg)
        if m and m.group(1) not in latches:
            latches.append(m.group(1))
        if msg not in warnings:
            warnings.append(msg)
    return warnings, latches


def _is_primitive(cell_type):
    return cell_type.startswith("$_") or cell_type.startswith("$mem")


def _is_instance(cell_type):
    """An instance of a user module or black box (not a Yosys gate or marker such as $scopeinfo)."""
    return not cell_type.startswith("$") or cell_type.startswith("$paramod")


def _module_summary(name, mod, display):
    types = {k: v for k, v in (mod.get("num_cells_by_type") or {}).items() if v}
    prim = {k: v for k, v in types.items() if _is_primitive(k)}
    seq = sum(v for k, v in prim.items() if SEQ_RE.match(k))
    nand2 = sum(NAND2_EQ.get(k, 0) * v for k, v in prim.items()) + seq * 4.5
    subs = {}
    for k, v in types.items():
        if _is_instance(k):                           # an instance of another module (or a black box)
            subs[display.get(k, _clean_name(k))] = subs.get(display.get(k, _clean_name(k)), 0) + v
    return {
        "name": display.get(name, _clean_name(name)),
        "parameterized": name.startswith("$paramod"),
        "cells": sum(prim.values()),
        "seq": seq,
        "comb": sum(prim.values()) - seq,
        "latches": sum(v for k, v in prim.items() if LATCH_RE.match(k)),
        "memories": mod.get("num_memories", 0),
        "nand2_eq": round(nand2, 1),
        "submodules": subs,
        "cell_types": sorted(({"cell": k, "count": v} for k, v in prim.items()), key=lambda c: -c["count"]),
        "wires": mod.get("num_wires", 0),
        "ports": mod.get("num_ports", 0),
    }


def _display_names(raw_names):
    """Readable, unique module names (two parameterizations of one module get #2, #3...)."""
    out, used = {}, {}
    for raw in raw_names:
        base = _clean_name(raw)
        used[base] = used.get(base, 0) + 1
        out[raw] = base if used[base] == 1 else f"{base}#{used[base]}"
    return out


def synthesize(files, top=None, flatten=False):
    """files: [(name, text)]. Returns the summary dict, raises SynthError with Yosys's message."""
    kind, native = engine()
    if kind is None:
        raise SynthError("Yosys is not available on this server (pip install yowasp-yosys).")
    if not files:
        raise SynthError("No Verilog files given.")
    if sum(len(t) for _, t in files) > MAX_SOURCE_BYTES:
        raise SynthError("The design is too large for online synthesis (2 MB of source max).")
    if top and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", top):
        raise SynthError(f"'{top}' is not a valid module name.")

    started = time.time()
    with tempfile.TemporaryDirectory(prefix="vt_yosys_") as tmp:
        tmp = Path(tmp)
        used = set()
        names = []
        for name, text in files:
            n = _safe_name(name, used)
            (tmp / n).write_text(text, encoding="utf-8")
            names.append(n)
        # undefined modules (memories, IP, library cells) become black boxes; port directions guessed from names
        gen = "-generate * o:*out* o:*dout* o:*rdata* o:*_o o:q o:Q o:y o:Y o:z o:Z i:*"
        top_cmd = f"hierarchy {gen} -top {top}" if top else f"hierarchy {gen} -auto-top"

        def run(abc):
            script = "; ".join([
                "read_verilog -sv " + " ".join(names),
                top_cmd,
                "synth " + ("-top " + top + " " if top else "-auto-top ") + ("-flatten " if flatten else "") + ("" if abc else "-noabc"),
                "tee -q -o stat.json stat -json",
                "write_verilog -noattr netlist.v",
                "flatten", "tee -q -o ltp.txt ltp -noff",
            ])
            p = subprocess.run(_cmd(kind, native) + ["-p", script], cwd=tmp, env=_env(),
                               capture_output=True, text=True, timeout=TIMEOUT)
            return p.returncode, (p.stdout or "") + (p.stderr or "")

        try:
            code, log = run(abc=True)
            abc_ok = code == 0 and (tmp / "stat.json").exists()
            if not abc_ok and "ERROR:" not in log:
                # the WebAssembly build cannot always run ABC (technology mapping): synthesize without it
                for f in ("stat.json", "netlist.v", "ltp.txt"):
                    (tmp / f).unlink(missing_ok=True)
                code, log = run(abc=False)
        except subprocess.TimeoutExpired:
            raise SynthError(f"Synthesis took longer than {TIMEOUT} s and was stopped.")

        errors = [l.strip() for l in log.splitlines() if l.strip().startswith("ERROR:")]
        if errors or code != 0 or not (tmp / "stat.json").exists():
            msg = errors[0][6:].strip() if errors else (log.strip().splitlines() or ["Yosys failed"])[-1]
            # show file names as the user uploaded them
            for (orig, _), n in zip(files, names):
                msg = msg.replace(n, orig)
            raise SynthError(msg)

        stat = json.loads((tmp / "stat.json").read_text(encoding="utf-8"))
        netlist = (tmp / "netlist.v").read_text(encoding="utf-8", errors="replace") if (tmp / "netlist.v").exists() else ""
        ltp = (tmp / "ltp.txt").read_text(encoding="utf-8", errors="replace") if (tmp / "ltp.txt").exists() else ""

    raw_modules = stat.get("modules", {})
    display = _display_names(raw_modules)
    modules = [_module_summary(n, m, display) for n, m in raw_modules.items()]
    top_name = (top or next((m["name"] for m in modules if not any(m["name"] in o["submodules"] for o in modules)), None))
    # design totals: expand instance counts down the hierarchy
    by_name = {m["name"]: m for m in modules}

    def expand(name, seen=()):
        m = by_name.get(name)
        if not m or name in seen:
            return {"cells": 0, "seq": 0, "comb": 0, "latches": 0, "nand2_eq": 0.0}
        t = {k: m[k] for k in ("cells", "seq", "comb", "latches", "nand2_eq")}
        for sub, count in m["submodules"].items():
            s = expand(sub, seen + (name,))
            for k in t:
                t[k] += s[k] * count
        return t

    totals = expand(top_name) if top_name in by_name else {
        k: sum(m[k] for m in modules) for k in ("cells", "seq", "comb", "latches", "nand2_eq")}
    totals["nand2_eq"] = round(totals["nand2_eq"], 1)
    black_boxes = sorted(set(re.findall(r"Generate module for cell type \\?(\S+):", log))
                         | {sub for m in modules for sub in m["submodules"] if sub not in by_name})
    depth = re.search(r"length=(\d+)", ltp)
    warnings, latches = _parse_warnings(log)
    for (orig, _), n in zip(files, names):
        warnings = [w.replace(n, orig) for w in warnings]
    top_name = top_name and _clean_name(top_name)
    return {
        "top": top_name,
        "modules": sorted(modules, key=lambda m: (m["name"] != top_name, -m["nand2_eq"])),
        "totals": totals,
        "logic_depth": int(depth.group(1)) if depth else None,
        "warnings": warnings[:50],
        "latches": latches,
        "black_boxes": black_boxes,
        "netlist": netlist,
        "engine": kind,
        "abc": abc_ok,
        "flatten": flatten,
        "seconds": round(time.time() - started, 2),
    }


if __name__ == "__main__":
    if "--warm" in sys.argv:
        print("Yosys engine:", warm_up())
