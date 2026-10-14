"""Project workspace: find and classify the design files in a folder, and analyze them all at once.

    scan(root)              -> every relevant file with its kind (rtl, log, timing, vcd, ...)
    analyze(root, files)    -> runs the matching tools and returns a health summary plus
                               flat metrics that can be stored in the run history

Files are classified by extension, and ambiguous text files (.rpt, .txt, .log,
.json) by a quick look at their content.
"""

import os
import re
import time
from pathlib import Path

SKIP_DIRS = {".git", ".svn", "node_modules", "__pycache__", "dist", "build", ".venv", "venv", ".idea", ".vscode",
             ".vt_data", ".pytest_cache"}
MAX_FILES = 3000
MAX_READ = 50 * 1024 * 1024  # files bigger than this are listed but not analyzed

KINDS = {
    "rtl": "RTL source", "log": "Simulation log", "timing": "Timing report", "vcd": "Waveform (VCD)",
    "def": "DEF layout", "lef": "LEF library", "liberty": "Liberty library", "spice": "SPICE netlist",
    "regmap": "Register spec", "waveform": "Waveform data (CSV)", "sdc": "Timing constraints (SDC)",
    "synth": "Synthesis report", "power": "Power report",
}
_EXT = {
    ".v": "rtl", ".sv": "rtl", ".vh": "rtl", ".svh": "rtl", ".vcd": "vcd", ".def": "def", ".lef": "lef",
    ".lib": "liberty", ".sp": "spice", ".cir": "spice", ".spice": "spice", ".ckt": "spice", ".sdc": "sdc",
    ".csv": "waveform",
}
_SNIFF_EXT = {".rpt", ".txt", ".log", ".out", ".timing", ".sta", ".json", ".yaml", ".yml", ".area", ".power"}
_SNIFF = [  # (kind, pattern) checked in this order on the first 64 KB
    ("timing", re.compile(r"^\s*Startpoint:|^\s*Slack\s*\((?:MET|VIOLATED)\)", re.M)),
    ("synth", re.compile(r"Number of cells:|Total cell area|Chip area for (?:top )?module|Combinational area:", re.I)),
    ("power", re.compile(r"Total\s+Power|Switching\s+Power|Leakage\s+Power|Total Dynamic Power", re.I)),
    ("regmap", re.compile(r'"registers"\s*:|^registers\s*:', re.M)),
    ("log", re.compile(r"UVM_(INFO|ERROR|FATAL)|\$finish|TEST\s+(PASSED|FAILED)|\*\* (Error|Note)|Simulation complete", re.I)),
]

# which tool page opens which kind of file (used by the web app)
TOOLS_FOR_KIND = {
    "rtl": ["/lint", "/modules", "/hierarchy", "/sva"], "log": ["/regression"], "timing": ["/timing"],
    "vcd": ["/vcd", "/axi"], "def": ["/floorplan"], "lef": ["/floorplan"], "liberty": ["/liberty"],
    "spice": ["/netlist", "/sweep"], "regmap": ["/regmap"], "waveform": ["/measure"], "sdc": ["/sdc"],
    "synth": ["/synthesis"], "power": ["/power"],
}


def classify(path):
    ext = path.suffix.lower()
    if ext in _EXT:
        return _EXT[ext]
    if ext in _SNIFF_EXT:
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                head = f.read(65536)
        except OSError:
            return None
        for kind, rx in _SNIFF:
            if rx.search(head):
                return kind
    return None


def scan(root):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Folder not found: {root}")
    files, truncated = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            kind = classify(p)
            if not kind:
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            files.append({"path": p.relative_to(root).as_posix(), "kind": kind, "size": st.st_size,
                          "modified": st.st_mtime})
            if len(files) >= MAX_FILES:
                truncated = True
                break
        if truncated:
            break
    counts = {}
    for f in files:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {"root": str(root), "name": root.name, "files": files, "counts": counts, "truncated": truncated,
            "kinds": KINDS, "tools": TOOLS_FOR_KIND, "scanned_at": time.time()}


def read_file(root, rel):
    """Text of a workspace file; refuses paths outside the workspace."""
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if root not in target.parents or not target.is_file():
        raise ValueError(f"'{rel}' is not a file inside the workspace")
    if target.stat().st_size > MAX_READ:
        raise ValueError(f"'{rel}' is larger than {MAX_READ // (1024 * 1024)} MB")
    return target.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Analyze everything
# ---------------------------------------------------------------------------


def _check(name, status, value, detail, tool=None):
    return {"name": name, "status": status, "value": value, "detail": detail, "tool": tool}


def analyze(root, files=None):
    """Run every relevant tool on the workspace. Returns {checks, sections, metrics, errors}."""
    from . import (axi, hierarchy, lint, pd_analyzer, power_report, regress, sdc_check, spice, synth_report,
                   timing_report)

    started = time.time()
    root = Path(root).resolve()
    files = files if files is not None else scan(root)["files"]
    by_kind = {}
    for f in files:
        if f["size"] <= MAX_READ:
            by_kind.setdefault(f["kind"], []).append(f)

    def text(f):
        return (root / f["path"]).read_text(encoding="utf-8", errors="replace")

    checks, sections, metrics, errors = [], {}, {}, []

    def guarded(label, fn):
        try:
            fn()
        except Exception as exc:  # one broken file must not stop the whole analysis
            errors.append(f"{label}: {type(exc).__name__}: {exc}")

    # ---- RTL: lint + hierarchy
    def do_rtl():
        rtl = by_kind.get("rtl", [])
        if not rtl:
            return
        sources = [(f["path"], text(f)) for f in rtl]
        issues = [i for name, src in sources for i in lint.lint_text(src, name)]
        e = sum(i.severity == "ERROR" for i in issues)
        w = sum(i.severity == "WARNING" for i in issues)
        h = hierarchy.analyze_project(sources)
        unreachable = sum(len(f["unreachable"]) for f in h["fsms"])
        metrics.update(lint_errors=e, lint_warnings=w, rtl_files=len(rtl), rtl_modules=len(h["modules"]),
                       fsms=len(h["fsms"]), undefined_modules=len(h["undefined"]))
        sections["rtl"] = {"files": len(rtl), "lint_errors": e, "lint_warnings": w, "top": h["main_top"],
                           "modules": len(h["modules"]), "fsms": len(h["fsms"]), "undefined": h["undefined"],
                           "unused": h["unused"], "unreachable_states": unreachable,
                           "worst_files": sorted(({"path": n, "errors": sum(1 for i in issues if i.file == n and i.severity == "ERROR"),
                                                   "warnings": sum(1 for i in issues if i.file == n and i.severity == "WARNING")}
                                                  for n, _ in sources), key=lambda x: (-x["errors"], -x["warnings"]))[:8]}
        checks.append(_check("RTL lint", "fail" if e else "warn" if w else "pass", f"{e} errors, {w} warnings",
                             f"{len(rtl)} files checked", "/lint"))
        checks.append(_check("Design hierarchy", "warn" if h["undefined"] or unreachable else "pass",
                             h["main_top"] or "no top", f"{len(h['modules'])} modules, {len(h['fsms'])} FSMs"
                             + (f", {len(h['undefined'])} undefined" if h["undefined"] else "")
                             + (f", {unreachable} unreachable states" if unreachable else ""), "/hierarchy"))

    # ---- Regression logs
    def do_logs():
        logs = by_kind.get("log", [])
        if not logs:
            return
        results = [regress.analyze_text(text(f), f["path"]) for f in logs]
        n = len(results)
        passed = sum(r.status == "PASS" for r in results)
        fail = sum(r.status == "FAIL" for r in results)
        inc = n - passed - fail
        sigs = regress.signatures(results)
        metrics.update(reg_tests=n, reg_pass_rate=round(passed / n, 4), reg_failures=fail, reg_incomplete=inc,
                       reg_signatures=len(sigs))
        sections["regression"] = {"tests": n, "passed": passed, "failed": fail, "incomplete": inc,
                                  "signatures": [{"signature": s, "count": len(rs)} for s, rs in list(sigs.items())[:5]]}
        checks.append(_check("Regression", "pass" if passed == n else "fail", f"{passed / n:.0%} pass",
                             f"{n} tests, {fail} failed, {inc} incomplete, {len(sigs)} unique failures", "/regression"))

    # ---- Timing: newest report is the current state
    def do_timing():
        reps = sorted(by_kind.get("timing", []), key=lambda f: f["modified"], reverse=True)
        if not reps:
            return
        paths = timing_report.parse_report(text(reps[0]))
        s = timing_report.summarize(paths)
        st, ho = s.get("setup", {}), s.get("hold", {})
        for k, v in (("setup_wns", st.get("wns")), ("setup_tns", st.get("tns")), ("hold_wns", ho.get("wns")),
                     ("hold_tns", ho.get("tns"))):
            if v is not None:
                metrics[k] = v
        metrics["timing_violations"] = sum(x["violations"] for x in s.values())
        sections["timing"] = {"report": reps[0]["path"], "reports": len(reps), "summary": s}
        viol = metrics["timing_violations"]
        checks.append(_check("Timing", "fail" if viol else "pass",
                             f"WNS {st.get('wns', 0):.3f} ns" if st else "no setup paths",
                             f"{viol} violating paths in {reps[0]['path']}", "/timing"))

    # ---- AXI checks on every VCD that has AXI signals
    def do_axi():
        vcds = by_kind.get("vcd", [])
        if not vcds:
            return
        per, total_e, total_w = [], 0, 0
        for f in vcds:
            r = axi.analyze_vcd_text(text(f))
            for itf in r["interfaces"]:
                if "error" in itf:
                    continue
                e = sum(v["severity"] == "ERROR" for v in itf["violations"])
                w = len(itf["violations"]) - e
                total_e += e
                total_w += w
                per.append({"path": f["path"], "interface": itf["interface"], "errors": e, "warnings": w,
                            "transactions": len(itf["transactions"])})
        if not per:
            return
        metrics.update(axi_errors=total_e, axi_warnings=total_w)
        sections["axi"] = {"interfaces": per}
        checks.append(_check("AXI protocol", "fail" if total_e else "warn" if total_w else "pass",
                             f"{total_e} errors, {total_w} warnings", f"{len(per)} interface(s) in {len(vcds)} VCD(s)", "/axi"))

    # ---- Floorplan
    def do_pd():
        defs = sorted(by_kind.get("def", []), key=lambda f: f["modified"], reverse=True)
        if not defs:
            return
        d = pd_analyzer.parse_def(text(defs[0]))
        lef = pd_analyzer.Lef()
        for f in by_kind.get("lef", []):
            pd_analyzer.parse_lef(text(f), lef)
        a = pd_analyzer.analyze(d, lef)
        unplaced = sum(1 for c in d.components if c.status == "UNPLACED")
        if a["utilization"] is not None:
            metrics["utilization"] = round(a["utilization"], 4)
        metrics.update(instances=len(d.components), unplaced=unplaced)
        sections["floorplan"] = {"def": defs[0]["path"], "design": d.design, "utilization": a["utilization"],
                                 "instances": len(d.components), "unplaced": unplaced}
        util = a["utilization"]
        checks.append(_check("Floorplan", "fail" if unplaced else "warn" if util and util > 0.8 else "pass",
                             f"{util:.1%} util" if util is not None else d.design or "DEF",
                             f"{len(d.components)} instances, {unplaced} unplaced", "/floorplan"))

    # ---- SPICE connectivity
    def do_spice():
        nets = by_kind.get("spice", [])
        if not nets:
            return
        per = [{"path": f["path"], "issues": len(spice.connectivity_issues(spice.parse_netlist(text(f))))} for f in nets]
        total = sum(p["issues"] for p in per)
        metrics["spice_issues"] = total
        sections["spice"] = {"netlists": per}
        checks.append(_check("SPICE netlists", "warn" if total else "pass", f"{total} issues",
                             f"{len(nets)} netlist(s) checked", "/netlist"))

    # ---- Sign-off reports: newest synthesis / power report, every SDC file
    def do_synth():
        reps = sorted(by_kind.get("synth", []), key=lambda f: f["modified"], reverse=True)
        if not reps:
            return
        r = synth_report.parse_report(text(reps[0]))
        metrics.update({k: v for k, v in (("synth_area", r["total_area"]), ("synth_cells", r["total_cells"])) if v is not None})
        sections["synthesis"] = {"report": reps[0]["path"], "format": r["format"], "top": r["top"], "total_area": r["total_area"],
                                 "total_cells": r["total_cells"], "seq_cells": r["seq_cells"],
                                 "largest": [{"name": m["name"], "percent": m["percent"]} for m in
                                             sorted(r["modules"], key=lambda m: -m["total_area"]) if m["name"] != r["top"]][:3]}
        checks.append(_check("Synthesis area", "pass", f"{r['total_area']:,.0f} area",
                             f"{r['total_cells'] or '?'} cells in {reps[0]['path']}", "/synthesis"))

    def do_power():
        reps = sorted(by_kind.get("power", []), key=lambda f: f["modified"], reverse=True)
        if not reps:
            return
        r = power_report.parse_report(text(reps[0]))
        t = r["totals"]
        metrics["power_total_mw"] = round(t["total"], 6)
        if t["leakage"] is not None:
            metrics["power_leakage_mw"] = round(t["leakage"], 6)
        sections["power"] = {"report": reps[0]["path"], "design": r["design"], "totals": t,
                             "top_instances": [{"name": h["name"], "percent": h["percent"]} for h in
                                               sorted((h for h in r["hierarchy"] if h["depth"] == 1), key=lambda h: -h["total"])][:3]}
        checks.append(_check("Power", "pass", f"{t['total']:.3f} mW",
                             f"dynamic {t['dynamic'] or 0:.3f} mW, leakage {t['leakage'] or 0:.4f} mW", "/power"))

    def do_sdc():
        sdcs = by_kind.get("sdc", [])
        if not sdcs:
            return
        ports = None
        rtl = by_kind.get("rtl", [])
        top = sections.get("rtl", {}).get("top")
        if rtl and top:
            # the top module's ports allow the typo / I-O coverage checks
            for f in rtl:
                src = text(f)
                if re.search(rf"\bmodule\s+{re.escape(top)}\b", src):
                    _, ports = sdc_check.ports_from_rtl(src, top)
                    break
        per, e_total, w_total = [], 0, 0
        for f in sdcs:
            r = sdc_check.check(text(f), ports)
            e_total += r["counts"]["ERROR"]
            w_total += r["counts"]["WARNING"]
            per.append({"path": f["path"], "errors": r["counts"]["ERROR"], "warnings": r["counts"]["WARNING"],
                        "clocks": [c["name"] for c in r["clocks"]]})
        metrics.update(sdc_errors=e_total, sdc_warnings=w_total)
        sections["sdc"] = {"files": per, "rtl_top": top if ports else None}
        checks.append(_check("Timing constraints", "fail" if e_total else "warn" if w_total else "pass",
                             f"{e_total} errors, {w_total} warnings",
                             f"{len(sdcs)} SDC file(s)" + (f", checked against {top}" if ports else ""), "/sdc"))

    for label, fn in (("RTL", do_rtl), ("Regression", do_logs), ("Timing", do_timing), ("AXI", do_axi),
                      ("Floorplan", do_pd), ("SPICE", do_spice), ("Synthesis", do_synth), ("Power", do_power),
                      ("SDC", do_sdc)):
        guarded(label, fn)

    order = {"fail": 0, "warn": 1, "pass": 2}
    checks.sort(key=lambda c: order[c["status"]])
    score = round(100 * sum({"pass": 1, "warn": 0.5, "fail": 0}[c["status"]] for c in checks) / len(checks)) if checks else None
    if score is not None:
        metrics["health_score"] = score
    return {"root": str(root), "checks": checks, "sections": sections, "metrics": metrics, "errors": errors,
            "health_score": score, "files_analyzed": sum(len(v) for v in by_kind.values()),
            "seconds": round(time.time() - started, 2)}
