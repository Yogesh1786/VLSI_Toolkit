"""Command-line interface:  python vlsi.py <command> [options]

RTL design
  parse   <file.v>          show modules, parameters and ports
  inst    <file.v>          print an instantiation template
  lint    <files/folders>   check RTL for common coding bugs
  hier    <files/folders>   design hierarchy tree + state machines (FSMs)
  regmap  <spec.json>       generate register RTL + C header + HTML docs
Verification
  tb      <file.v>          generate a Verilog testbench (+ optional cocotb test)
  regress <log folder>      summarize simulation logs, group failures by signature
  vcd     <dump.vcd>        analyze a waveform dump (toggles, clocks, glitches, X)
  axi     <dump.vcd>        AXI protocol checker + transaction list
  sva     <file.v>          generate SystemVerilog assertions (AXI, FSM, one-hot, outputs)
Physical design
  timing  <report.rpt>      analyze an STA timing report (WNS/TNS/worst paths)
  pd      <file.def>        DEF/LEF analysis: utilization, cell mix, density map
  lib     <file.lib>        Liberty library: cells, area, leakage, delay tables
  synth   <area.rpt>        synthesis area report (Yosys stat / DC report_area)
  power   <power.rpt>       power report: totals, power groups, hierarchy
  sdc     <file.sdc>        check timing constraints (--rtl top.v for port checks)
Workspace
  workspace <folder>        find all design files in a project and analyze them at once
  history   <folder>        saved workspace snapshots (trend over time)
Tracking
  compare regress OLD NEW   what changed between two regression runs (log folders)
  compare timing  OLD NEW   what changed between two timing reports (e.g. ECO)
Analog
  spice info    <netlist>   device summary, MOSFET W/L, connectivity checks
  spice sweep   <netlist>   generate (and run) .param sweeps with ngspice
  spice measure <waves>     rise/fall time, delay, frequency from waveform data
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import (__version__, axi, compare, history, sva, workspace, hierarchy, liberty, lint, pd_analyzer, power_report, regmap_gen,
               regress, sdc_check, spice, synth_report, tb_generator, timing_report, vcd_analyzer, verilog_parser)
from .common import format_table


def _load_module(args):
    modules = verilog_parser.parse_file(args.file)
    return verilog_parser.pick_module(modules, args.module), modules


def cmd_parse(args):
    modules = verilog_parser.parse_file(args.file)
    if not modules:
        print("No modules found.")
        return 1
    if args.json:
        print(verilog_parser.to_json(modules))
    else:
        print("\n\n".join(verilog_parser.describe(m) for m in modules))
    return 0


def cmd_inst(args):
    module, _ = _load_module(args)
    print(tb_generator.instantiation(module, args.name))
    return 0


def cmd_tb(args):
    module, _ = _load_module(args)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tb_path = out_dir / f"tb_{module.name}.v"
    tb_path.write_text(
        tb_generator.verilog_tb(module, args.cycles, args.period, source=Path(args.file).name), encoding="utf-8"
    )
    print(f"Wrote {tb_path}")
    if args.cocotb:
        py_path = out_dir / f"test_{module.name}.py"
        py_path.write_text(
            tb_generator.cocotb_test(module, Path(args.file).resolve(), args.cycles, args.period), encoding="utf-8"
        )
        print(f"Wrote {py_path}")
    clocks, resets, _ = tb_generator.classify(module)
    print(f"Detected clock(s): {', '.join(c.name for c in clocks) or 'none'}   "
          f"reset(s): {', '.join(r.name for r in resets) or 'none'}")
    print("\nSimulate with Icarus Verilog:")
    print(f"  iverilog -g2012 -o sim.out {tb_path} {args.file}")
    print("  vvp sim.out")
    print(f"  gtkwave tb_{module.name}.vcd")
    return 0


def cmd_timing(args):
    paths = timing_report.parse_file(args.file)
    if args.json:
        print(json.dumps(timing_report.to_dicts(paths), indent=2))
    else:
        print(timing_report.report_text(paths, args.top))
    if args.csv:
        timing_report.write_csv(paths, args.csv)
        print(f"\nWrote {args.csv}")
    if args.plot:
        try:
            timing_report.plot_histogram(paths, args.plot)
            print(f"Wrote {args.plot}")
        except ImportError:
            print("Plotting needs matplotlib:  pip install matplotlib", file=sys.stderr)
            return 1
    # non-zero exit when timing fails -> handy in scripts / CI
    return 2 if args.fail_on_violation and any(p.violated for p in paths) else 0


def cmd_regmap(args):
    try:
        rm, files = regmap_gen.generate_all(args.file, args.out)
    except regmap_gen.RegMapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Block '{rm.block}': {len(rm.registers)} registers, {rm.data_width}-bit data, {rm.addr_width}-bit address")
    for f in files:
        print(f"Wrote {f}")
    return 0


def cmd_vcd(args):
    vcd = vcd_analyzer.parse_file(args.file)
    stats = vcd_analyzer.analyze(vcd, args.glitch, args.x_after)
    if args.filter:
        stats = [s for s in stats if args.filter.lower() in s.name.lower()]
    print(vcd_analyzer.report_text(vcd, stats))
    return 0


def cmd_lint(args):
    files = lint.collect_files(args.paths)
    if not files:
        print("No .v/.sv files found.")
        return 1
    issues = lint.lint_files(args.paths)
    print(f"Checked {len(files)} file(s)")
    print(lint.report_text(issues, args.severity.upper()))
    return 1 if any(i.severity == "ERROR" for i in issues) else 0


def cmd_regress(args):
    results = regress.analyze_folder(args.folder, args.pattern)
    print(regress.report_text(results))
    if args.csv:
        regress.write_csv(results, args.csv)
        print(f"\nWrote {args.csv}")
    if args.html:
        regress.write_html(results, args.html)
        print(f"Wrote {args.html}")
    return 0 if all(r.status == "PASS" for r in results) else 2


def cmd_pd(args):
    d, lef = pd_analyzer.parse_files(args.file, args.lef or [])
    print(pd_analyzer.report_text(d, lef, args.top))
    return 0


def cmd_spice_info(args):
    print(spice.netlist_report(spice.parse_netlist_file(args.file)))
    return 0


def cmd_spice_sweep(args):
    name, _, values = args.param.partition("=")
    if not values:
        print("ERROR: use --param NAME=start:stop:step  or  --param NAME=v1,v2,v3", file=sys.stderr)
        return 1
    if args.run and not spice.find_ngspice():
        print("ERROR: ngspice not found. Install it from https://ngspice.sourceforge.io and add it to PATH,\n"
              "or run without --run to only generate the netlists.", file=sys.stderr)
        return 1
    nl, results = spice.run_sweep(args.file, name, values, args.out, run=args.run)
    cols = ["value"] + (nl.measures if args.run else []) + ["netlist"]
    rows = [[r.get(c) if c in ("value", "netlist") else spice.eng(r.get(c)) for c in cols] for r in results]
    print(f"Sweep of {name}: {len(results)} netlists")
    print(format_table([name if c == "value" else c for c in cols], rows))
    if args.run:
        csv_path = Path(args.out) / f"sweep_{name}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows([[r.get(c) for c in cols] for r in results])
        print(f"Wrote {csv_path}")
    else:
        print("Add --run to simulate each netlist with ngspice and collect the .meas results.")
    return 0


def cmd_spice_measure(args):
    waves = spice.load_waveforms(args.file)
    print(f"Signals in file: {', '.join(list(waves)[1:])}")
    for sig in args.signal:
        res = spice.measure(waves, sig, args.ref, args.vdd)
        print(spice.measure_report(res, sig, args.ref))
    return 0


def cmd_hier(args):
    files = lint.collect_files(args.paths)
    if not files:
        print("No .v/.sv files found.")
        return 1
    r = hierarchy.analyze_project([(str(f), f.read_text(encoding="utf-8", errors="replace")) for f in files])
    print(f"{len(files)} file(s), {len(r['modules'])} module(s), {r['total_instances']} instance(s)\n")
    for t in r["trees"]:
        if t["module"] in r["unused"]:
            continue
        print(hierarchy.tree_text(t))
        print()
    if r["undefined"]:
        print("NOT DEFINED (black boxes / library cells?): " + ", ".join(r["undefined"]))
    if r["unused"]:
        print("UNUSED (defined but never instantiated): " + ", ".join(r["unused"]))
    for f in r["fsms"]:
        print(f"\nFSM in {f['module']} (state register '{f['state_var']}', reset: {f['reset_state'] or '?'})")
        print(format_table(["From", "To", "Condition"], [[t["src"], t["dst"], t["condition"]] for t in f["transitions"]]))
        if f["unreachable"]:
            print("  WARNING unreachable states: " + ", ".join(f["unreachable"]))
        if f["dead_ends"]:
            print("  WARNING states with no way out: " + ", ".join(f["dead_ends"]))
    return 0


def cmd_axi(args):
    r = axi.analyze_file(args.file, args.timeout)
    if not r["interfaces"]:
        print("No AXI interface found (expected <prefix>awvalid, <prefix>awready, ... signals).")
        return 1
    worst = 0
    for i in r["interfaces"]:
        if "error" in i:
            print(f"ERROR: {i['error']}")
            continue
        print(f"Interface {i['interface']}*  ({i['kind']}, {i['data_width']}-bit data, clock {i['clock']}, "
              f"{i['cycles']} cycles)")
        for k in ("write", "read"):
            st = i[k]
            print(f"  {k.upper():5s} {st['count']} transaction(s), {st['completed']} completed, {st['bytes']} bytes, "
                  f"latency avg {st['latency_avg']} / max {st['latency_max']} cycles, {st['bandwidth_MBps']} MB/s")
        v = i["violations"]
        errors = sum(x["severity"] == "ERROR" for x in v)
        worst = max(worst, 2 if errors else 1 if v else 0)
        print(f"\nPROTOCOL CHECK: {errors} error(s), {len(v) - errors} warning(s)")
        if v:
            print(format_table(["Cycle", "Time", "Severity", "Rule", "Channel", "Message"],
                               [[x["cycle"], x["time"], x["severity"], x["rule"], x["channel"], x["message"]] for x in v]))
        if not args.no_transactions:
            print("\nTRANSACTIONS")
            print(format_table(["#", "Kind", "ID", "Address", "Beats", "Data", "Resp", "Start", "Latency"],
                               [[n + 1, t["kind"], "-" if t["id"] is None else t["id"], t["addr"], f"{t['beats']}/{t['length']}",
                                 " ".join(t["data"][:3]) + (" ..." if len(t["data"]) > 3 else ""), t["status"],
                                 t["start_cycle"], "-" if t["latency"] is None else t["latency"]]
                                for n, t in enumerate(i["transactions"])]))
        print()
    return worst


def cmd_workspace(args):
    scan = workspace.scan(args.folder)
    print(f"Workspace {scan['root']}: {len(scan['files'])} design files")
    print("  " + ", ".join(f"{n} {workspace.KINDS[k]}" for k, n in sorted(scan["counts"].items())))
    result = workspace.analyze(scan["root"], scan["files"])
    print(f"\nHEALTH SCORE: {result['health_score']} / 100   ({result['files_analyzed']} files in {result['seconds']} s)")
    icon = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
    print(format_table(["Status", "Check", "Result", "Details"],
                       [[icon[c["status"]], c["name"], c["value"], c["detail"]] for c in result["checks"]]))
    for e in result["errors"]:
        print(f"  could not analyze: {e}")
    if args.save:
        sid = history.save_snapshot(scan["root"], result["metrics"], {"checks": result["checks"]}, args.label or "")
        print(f"\nSaved snapshot #{sid} to {history.data_dir() / 'history.db'}")
    return 2 if any(c["status"] == "fail" for c in result["checks"]) else 0


def cmd_history(args):
    root = str(Path(args.folder).resolve())
    snaps = history.list_snapshots(root, limit=args.limit)
    if not snaps:
        print(f"No saved snapshots for {root}. Run: python vlsi.py workspace {args.folder} --save")
        return 0
    import datetime as dt
    keys = ["health_score", "lint_errors", "reg_pass_rate", "reg_failures", "setup_wns", "axi_errors", "utilization"]
    rows = []
    for s_ in snaps:
        m = s_["metrics"]
        rows.append([s_["id"], dt.datetime.fromtimestamp(s_["ts"]).strftime("%Y-%m-%d %H:%M"), s_["label"]]
                    + [("-" if m.get(k) is None else f"{m[k]:.1%}" if k in ("reg_pass_rate", "utilization") else m[k]) for k in keys])
    print(format_table(["#", "When", "Label", "Health", "Lint err", "Pass rate", "Fails", "Setup WNS", "AXI err", "Util"], rows))
    return 0


def cmd_sva(args):
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    r = sva.generate(text, args.module, Path(args.file).name)
    out = Path(args.out) / r["filename"] if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(r["code"], encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(r["code"])
    summary = ", ".join(f"{n} {k}" for k, n in r["counts"].items())
    print(f"Module {r['module']} (clock {r['clock']}, reset {r['reset'] or 'none'}): {len(r['assertions'])} properties: {summary}")
    return 0


def cmd_lib(args):
    lib = liberty.parse_file(args.file)
    if not lib["cells"]:
        print("No cells found.")
        return 1
    if args.cell:
        cell = next((c for c in lib["cells"] if c["name"] == args.cell), None)
        if not cell:
            print(f"ERROR: cell {args.cell} not found", file=sys.stderr)
            return 1
        print(f"{cell['name']}  area {cell['area']}  leakage {cell['leakage']}  {cell['kind']}  function {cell['function']}")
        print(format_table(["Pin", "Direction", "Capacitance", "Function"],
                           [[p["name"], p["direction"], p["capacitance"], p["function"]] for p in cell["pins"]]))
        for a in cell["arcs"]:
            for name, t in a["tables"].items():
                print(f"\n{a['from']} -> {a['to']}  {a['timing_type']}  {name}   rows: {t['variable_1']}  cols: {t['variable_2']}")
                print(format_table(["slew \\ load"] + [f"{v:g}" for v in t["index_2"]],
                                   [[f"{s:g}"] + [f"{v:.4f}" for v in row] for s, row in zip(t["index_1"], t["values"])]))
        return 0
    u, oc = lib["units"], lib["operating_conditions"]
    print(f"Library {lib['name']}: {len(lib['cells'])} cells   corner {oc['name']} "
          f"({oc['voltage']} V, {oc['temperature']} C)   units: time {u['time']}, cap {u['capacitive_load']}, "
          f"leakage {u['leakage_power']}")
    print(format_table(["Cell", "Kind", "Area", "Leakage", "Inputs", "Function", "Typ. delay"],
                       [[c["name"], c["kind"], f"{c['area']:.3f}", c["leakage"], " ".join(c["inputs"]), c["function"],
                         f"{c['typical_delay']:.4f}" if c["typical_delay"] else "-"] for c in lib["cells"]]))
    return 0


def cmd_synth(args):
    r = synth_report.parse_file(args.file)
    print(f"Synthesis report ({r['format']}): top {r['top'] or '?'}   total area {r['total_area']:.2f}   cells {r['total_cells']}")
    parts = [("combinational", r["comb_area"]), ("sequential", r["seq_area"]), ("buf/inv", r["buf_inv_area"]),
             ("macro", r["macro_area"])]
    if any(v for _, v in parts):
        print("   " + "   ".join(f"{k} {v:.2f} ({v / r['total_area']:.1%})" for k, v in parts if v))
    elif r["seq_cells"] is not None:
        print(f"   sequential cells {r['seq_cells']} ({r['seq_cells'] / max(r['total_cells'], 1):.1%} of all cells)")
    if r["modules"]:
        print(format_table(["Module", "Design", "Instances", "Area", "%"],
                           [[m["name"], m.get("design") or "", m.get("instances") or 1, f"{m['total_area']:.2f}",
                             f"{m['percent']:.1f}"] for m in r["modules"][:args.top]]))
    if r["cell_types"]:
        print(format_table(["Cell type", "Count"], [[c["cell"], c["count"]] for c in r["cell_types"][:args.top]]))
    return 0


def cmd_power(args):
    r = power_report.parse_file(args.file)
    t = r["totals"]

    def mw(v):
        return "-" if v is None else f"{v:.4f}"

    print(f"Power report: design {r['design'] or '?'}   total {mw(t['total'])} mW   dynamic {mw(t['dynamic'])}   "
          f"(internal {mw(t['internal'])}, switching {mw(t['switching'])})   leakage {mw(t['leakage'])} mW")
    if r["groups"]:
        print(format_table(["Group", "Internal", "Switching", "Leakage", "Total (mW)"],
                           [[g["group"], mw(g["internal"]), mw(g["switching"]), f"{g['leakage']:.6f}", mw(g["total"])]
                            for g in r["groups"] if g["total"]]))
    if r["hierarchy"]:
        print(format_table(["Instance", "Design", "Switching", "Internal", "Leakage", "Total (mW)", "%"],
                           [["  " * h["depth"] + h["name"], h["design"], mw(h["switching"]), mw(h["internal"]),
                             mw(h["leakage"]), mw(h["total"]), f"{h['percent']:.1f}"] for h in r["hierarchy"]]))
    return 0


def cmd_sdc(args):
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    ports = None
    if args.rtl:
        top, ports = sdc_check.ports_from_rtl(Path(args.rtl).read_text(encoding="utf-8", errors="replace"), args.module)
        if not ports:
            print(f"ERROR: no module found in {args.rtl}", file=sys.stderr)
            return 1
        print(f"RTL top: {top}  ({len(ports['inputs'])} inputs, {len(ports['outputs'])} outputs)")
    r = sdc_check.check(text, ports)
    if r["clocks"]:
        print(format_table(["Clock", "Period (ns)", "Freq (MHz)", "Source", "Uncertainty"],
                           [[c["name"], c["period"] if c["period"] is not None else "?", c["freq_mhz"] or "?",
                             " ".join(c["ports"]) or (f"from {c['master']}" if c["generated"] else ""),
                             "yes" if c["uncertainty"] else "no"] for c in r["clocks"]]))
    if r["issues"]:
        print(format_table(["Severity", "Rule", "Line", "Message"],
                           [[i["severity"], i["rule"], i["line"] or "-", i["message"]] for i in r["issues"]]))
    c = r["counts"]
    print(f"{c['ERROR']} error(s), {c['WARNING']} warning(s), {c['INFO']} info"
          + ("" if r["rtl_checked"] else "   (add --rtl top.v to also check port names and I/O coverage)"))
    return 2 if c["ERROR"] else 0


def cmd_compare(args):
    if args.kind == "regress":
        r = compare.compare_regressions(regress.analyze_folder(args.old), regress.analyze_folder(args.new))
        print(f"Pass rate: {r['old']['pass_rate']:.1%} -> {r['new']['pass_rate']:.1%}   verdict: {r['verdict'].upper()}")
        order = ["new_failure", "fixed", "still_failing", "added", "removed"]
        rows = [[x["change"].replace("_", " "), x["test"], x["old_status"] or "-", x["new_status"] or "-",
                 x["new_signature"] or x["old_signature"]] for x in sorted(r["rows"], key=lambda x: (order + ["still_passing"]).index(x["change"]))
                if x["change"] != "still_passing"]
        print(format_table(["Change", "Test", "Before", "Now", "Signature"], rows))
        return 2 if r["verdict"] == "regressed" else 0
    r = compare.compare_timing(timing_report.parse_file(args.old), timing_report.parse_file(args.new))
    print(f"Verdict: {r['verdict'].upper()}")
    print(format_table(["Check", "WNS before", "WNS now", "Delta", "TNS before", "TNS now", "Violations"],
                       [[c["check"], c["old_wns"], c["new_wns"], c["delta_wns"], c["old_tns"], c["new_tns"],
                         f"{c['old_violations']} -> {c['new_violations']}"] for c in r["checks"]]))
    changed = [x for x in r["rows"] if x["change"] != "unchanged"]
    print(format_table(["Change", "Check", "Endpoint", "Slack before", "Slack now", "Delta"],
                       [[x["change"].replace("_", " "), x["check"], x["endpoint"], x["old_slack"], x["new_slack"], x["delta"]]
                        for x in changed]))
    return 2 if r["verdict"] in ("regressed", "mixed") else 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="vlsi",
        description="VLSI Toolkit - Python helpers for chip design flows",
        epilog=__doc__.split("\n", 2)[2] + "\nRun 'python vlsi.py <command> -h' for the options of one command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("parse", help="show modules, parameters and ports of a Verilog file")
    s.add_argument("file")
    s.add_argument("--json", action="store_true", help="output JSON instead of tables")
    s.set_defaults(func=cmd_parse)

    s = sub.add_parser("inst", help="print an instantiation template")
    s.add_argument("file")
    s.add_argument("-m", "--module", help="module name (default: last module in file)")
    s.add_argument("-n", "--name", help="instance name (default: u_<module>)")
    s.set_defaults(func=cmd_inst)

    s = sub.add_parser("tb", help="generate a testbench")
    s.add_argument("file")
    s.add_argument("-m", "--module", help="module name (default: last module in file)")
    s.add_argument("-o", "--out", default="output", help="output folder (default: output)")
    s.add_argument("--cycles", type=int, default=100, help="random stimulus cycles (default 100)")
    s.add_argument("--period", type=int, default=10, help="clock period in ns (default 10)")
    s.add_argument("--cocotb", action="store_true", help="also generate a cocotb Python test")
    s.set_defaults(func=cmd_tb)

    s = sub.add_parser("timing", help="analyze an STA timing report")
    s.add_argument("file")
    s.add_argument("--top", type=int, default=10, help="number of worst paths to list")
    s.add_argument("--csv", help="write all paths to this CSV file")
    s.add_argument("--plot", help="save slack histogram PNG (needs matplotlib)")
    s.add_argument("--json", action="store_true", help="print paths as JSON")
    s.add_argument("--fail-on-violation", action="store_true", help="exit code 2 if any path violates")
    s.set_defaults(func=cmd_timing)

    s = sub.add_parser("regmap", help="generate register RTL, C header and HTML from a spec")
    s.add_argument("file")
    s.add_argument("-o", "--out", default="output", help="output folder (default: output)")
    s.set_defaults(func=cmd_regmap)

    s = sub.add_parser("vcd", help="analyze a VCD waveform dump")
    s.add_argument("file")
    s.add_argument("--glitch", type=int, default=2, help="pulses shorter than this (time units) are glitches")
    s.add_argument("--x-after", type=int, help="report X/Z seen after this time (default: 10%% of sim)")
    s.add_argument("--filter", help="only show signals whose name contains this text")
    s.set_defaults(func=cmd_vcd)

    s = sub.add_parser("lint", help="check RTL for common coding bugs")
    s.add_argument("paths", nargs="+", help="Verilog files and/or folders")
    s.add_argument("--severity", default="info", choices=["error", "warning", "info"],
                   help="lowest severity to show (default: info)")
    s.set_defaults(func=cmd_lint)

    s = sub.add_parser("regress", help="summarize a folder of simulation logs")
    s.add_argument("folder", help="folder with log files (searched recursively), or one log file")
    s.add_argument("--pattern", default="*.log", help="log file pattern (default *.log)")
    s.add_argument("--csv", help="write results to CSV")
    s.add_argument("--html", help="write a shareable HTML report")
    s.set_defaults(func=cmd_regress)

    s = sub.add_parser("pd", help="analyze a DEF file (utilization, cell mix, density)")
    s.add_argument("file", help="DEF file")
    s.add_argument("--lef", nargs="+", help="LEF file(s) with cell sizes (tech LEF + cell LEFs)")
    s.add_argument("--top", type=int, default=10, help="number of cell types to list")
    s.set_defaults(func=cmd_pd)

    s = sub.add_parser("hier", help="design hierarchy tree and state machines of an RTL project")
    s.add_argument("paths", nargs="+", help="Verilog files and/or folders")
    s.set_defaults(func=cmd_hier)

    s = sub.add_parser("workspace", help="find all design files in a folder and analyze them at once")
    s.add_argument("folder")
    s.add_argument("--save", action="store_true", help="store the results in the run history")
    s.add_argument("--label", help="label for the saved snapshot, e.g. 'nightly'")
    s.set_defaults(func=cmd_workspace)

    s = sub.add_parser("history", help="show saved workspace snapshots")
    s.add_argument("folder")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("axi", help="AXI protocol checker and transaction viewer for a VCD")
    s.add_argument("file", help="VCD waveform containing AXI signals")
    s.add_argument("--timeout", type=int, default=16, help="cycles VALID may wait for READY before a warning")
    s.add_argument("--no-transactions", action="store_true", help="only print the protocol check")
    s.set_defaults(func=cmd_axi)

    s = sub.add_parser("sva", help="generate SystemVerilog assertions for a module")
    s.add_argument("file")
    s.add_argument("-m", "--module", help="module name (default: last module in file)")
    s.add_argument("-o", "--out", help="folder to write <module>_sva.svh into (default: print)")
    s.set_defaults(func=cmd_sva)

    s = sub.add_parser("lib", help="explore a Liberty (.lib) standard-cell library")
    s.add_argument("file")
    s.add_argument("--cell", help="show pins and delay tables of one cell")
    s.set_defaults(func=cmd_lib)

    s = sub.add_parser("synth", help="analyze a synthesis area report (Yosys stat / DC report_area)")
    s.add_argument("file")
    s.add_argument("--top", type=int, default=15, help="rows to show per table (default 15)")
    s.set_defaults(func=cmd_synth)

    s = sub.add_parser("power", help="analyze a report_power output (totals, groups, hierarchy)")
    s.add_argument("file")
    s.set_defaults(func=cmd_power)

    s = sub.add_parser("sdc", help="check an SDC timing-constraints file for common mistakes")
    s.add_argument("file")
    s.add_argument("--rtl", help="top-level Verilog file: check port names and input/output delay coverage")
    s.add_argument("-m", "--module", help="top module name if the RTL file has several")
    s.set_defaults(func=cmd_sdc)

    s = sub.add_parser("compare", help="compare two regressions or two timing reports")
    s.add_argument("kind", choices=["regress", "timing"])
    s.add_argument("old", help="previous run: log folder (regress) or report file (timing)")
    s.add_argument("new", help="new run: log folder (regress) or report file (timing)")
    s.set_defaults(func=cmd_compare)

    sp = sub.add_parser("spice", help="analog/SPICE tools: info, sweep, measure")
    ssub = sp.add_subparsers(dest="spice_command", required=True)
    s = ssub.add_parser("info", help="netlist summary and connectivity checks")
    s.add_argument("file")
    s.set_defaults(func=cmd_spice_info)
    s = ssub.add_parser("sweep", help="generate/run a .param sweep")
    s.add_argument("file")
    s.add_argument("--param", required=True, help="NAME=start:stop:step or NAME=v1,v2,...  e.g. VDD=1.6:2.0:0.1")
    s.add_argument("-o", "--out", default="output/sweep", help="output folder")
    s.add_argument("--run", action="store_true", help="run ngspice on each netlist and collect .meas results")
    s.set_defaults(func=cmd_spice_sweep)
    s = ssub.add_parser("measure", help="measure waveforms from CSV / ngspice wrdata")
    s.add_argument("file")
    s.add_argument("-s", "--signal", nargs="+", required=True, help="signal(s) to measure, e.g. out or v(out)")
    s.add_argument("--ref", help="reference signal for propagation delay, e.g. in")
    s.add_argument("--vdd", type=float, help="supply voltage (sets 0/VDD as logic levels, enables overshoot)")
    s.set_defaults(func=cmd_spice_measure)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"ERROR: file not found: {exc.filename}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
