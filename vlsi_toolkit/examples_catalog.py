"""Catalog of the bundled example files: what each one is, and which tools open it.

Used by the Examples Library page so visitors of the hosted site can find, preview,
download and open the right example without seeing the project folder.

    catalog()          -> {"files": [...], "collections": [...], "count", "bytes"}
    zip_bytes()        -> all examples as one .zip (cached)
"""

import io
import zipfile
from functools import lru_cache
from pathlib import Path

from . import workspace

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# title, description, highlight (short tag), first tool to open it in
INFO = {
    "counter.v": ("Parameterized counter", "A small up-counter with enable and synchronous reset: the simplest module to explore ports and parameters.", "clean", "/modules"),
    "alu.v": ("8-bit ALU", "Combinational ALU with an opcode case statement, good for testbench generation.", "clean", "/testbench"),
    "fifo.v": ("Synchronous FIFO", "Parameterized FIFO with $clog2 widths, full/empty flags and pointer logic.", "clean", "/modules"),
    "lint_demo.v": ("Lint demo (buggy)", "Contains a multi-driven net, a latch, blocking assignments in a flop and a case without default.", "4 planted bugs", "/lint"),
    "cdc_demo.v": ("CDC demo (buggy)", "Two clock domains with an unsynchronized signal, a single-flop crossing and a multi-bit bus crossing, plus one correct 2-flop synchronizer.", "3 CDC bugs", "/lint"),
    "sample.vcd": ("Sample waveform", "A short simulation dump with clocks, a counter bus and a glitch.", "waveform", "/vcd"),
    "sta_report.rpt": ("STA report", "OpenSTA/PrimeTime-style report_checks output with setup and hold paths, some violating.", "WNS < 0", "/timing"),
    "sta_report_eco.rpt": ("STA report after ECO", "The same design after an ECO: some endpoints fixed, some degraded. Compare it with sta_report.rpt.", "before/after", "/compare"),
    "uart_regmap.json": ("UART register map spec", "JSON register spec (RW, RO, WO and W1C fields) that generates RTL, an AXI4-Lite slave, a C header and HTML docs.", "generator input", "/regmap"),
    "rtl_project/uart_top.v": ("UART top", "Top level of a small UART: baud generator, TX/RX, two FIFOs and a black-box SRAM.", "top module", "/hierarchy"),
    "rtl_project/uart_rx.v": ("UART receiver", "Receiver with a state machine that contains an unreachable state.", "FSM", "/hierarchy"),
    "rtl_project/uart_tx.v": ("UART transmitter", "Transmitter with a 5-state FSM.", "FSM", "/hierarchy"),
    "rtl_project/baud_gen.v": ("Baud generator", "Clock-enable generator with a divider counter.", "", "/modules"),
    "rtl_project/sync_fifo.v": ("UART FIFO", "Synchronous FIFO used twice in the UART.", "", "/modules"),
    "rtl_project/debug_mux.v": ("Debug mux (unused)", "Defined but never instantiated: the hierarchy view flags it.", "unused", "/hierarchy"),
    "axi/axi_buggy.vcd": ("AXI4 traffic (buggy)", "AXI4 reads and writes with VALID dropped early, payload changes, a 4 KB boundary crossing, X values and a missing response.", "9 planted bugs", "/axi"),
    "axi/axi_clean.vcd": ("AXI4 traffic (clean)", "Protocol-correct AXI4 bursts with back-pressure: the checker passes.", "passes", "/axi"),
    "axi/uart_axil.v": ("AXI4-Lite slave", "Register block generated from uart_regmap.json with WSTRB, SLVERR and W1C support.", "generated RTL", "/sva"),
    "signoff/synth_yosys.rpt": ("Yosys stat report", "Yosys `stat -liberty` output for the UART: area per module and cell usage.", "Yosys", "/synthesis"),
    "signoff/synth_dc_area.rpt": ("Design Compiler area report", "report_area -hierarchy output with combinational, sequential and macro area.", "DC", "/synthesis"),
    "signoff/power.rpt": ("Power report", "report_power -hierarchy output: internal, switching and leakage power, power groups and instances.", "PrimePower", "/power"),
    "signoff/uart_top.sdc": ("SDC constraints (buggy)", "Timing constraints with an unknown clock, misspelled ports, missing output delays and a multicycle path without hold.", "10 findings", "/sdc"),
    "signoff/uart_top_fixed.sdc": ("SDC constraints (fixed)", "The corrected constraints: the checker reports no issues.", "clean", "/sdc"),
    "pd/demo.def": ("Placed DEF", "A placed design with a macro, 1 400 instances and 3 unplaced cells.", "60.8% util", "/floorplan"),
    "pd/demo.lef": ("Cell LEF", "LEF with the cell and macro sizes used by demo.def.", "", "/floorplan"),
    "lib/vt_demo.lib": ("Liberty library", "A small standard-cell library with NLDM delay and transition tables.", "16 cells", "/liberty"),
    "analog/buggy_bias.sp": ("Bias netlist (buggy)", "SPICE netlist with a floating node and a floating gate.", "3 issues", "/netlist"),
    "analog/inverter_chain.sp": ("Inverter chain", "Parameterized inverter chain with .meas statements, ready for a VDD sweep.", "sweep", "/sweep"),
    "analog/inverter_tran.csv": ("Inverter transient", "Transient waveform (in/out) for rise, fall and delay measurements.", "waveform", "/measure"),
}

COLLECTIONS = {
    "regression_logs": ("Regression run (current)", "Simulation logs from UVM, Questa and Icarus with failures that share a few root causes.", "/regression"),
    "regression_logs_prev": ("Regression run (previous)", "The previous night's logs: compare them with the current run to see new failures and fixes.", "/compare"),
}

AREA_OF_KIND = {
    "rtl": "RTL design", "regmap": "RTL design", "log": "Verification", "vcd": "Verification",
    "timing": "Physical design", "def": "Physical design", "lef": "Physical design", "liberty": "Physical design",
    "sdc": "Physical design", "synth": "Physical design", "power": "Physical design",
    "spice": "Analog", "waveform": "Analog",
}


@lru_cache(maxsize=1)
def catalog():
    scan = workspace.scan(EXAMPLES_DIR)
    files = []
    for f in scan["files"]:
        path = f["path"]
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        tools = list(workspace.TOOLS_FOR_KIND.get(f["kind"], []))
        if path in INFO:
            title, desc, highlight, first = INFO[path]
        elif folder in COLLECTIONS:
            title, desc, first = path.rsplit("/", 1)[-1], COLLECTIONS[folder][1], COLLECTIONS[folder][2]
            highlight = "log"
        else:
            title, desc, highlight, first = path.rsplit("/", 1)[-1], "", "", tools[0] if tools else None
        if first and first in tools:
            tools.remove(first)
        if first:
            tools.insert(0, first)
        files.append({
            "path": path, "name": path.rsplit("/", 1)[-1], "folder": folder, "kind": f["kind"],
            "kind_label": scan["kinds"].get(f["kind"], f["kind"]), "area": AREA_OF_KIND.get(f["kind"], "Other"),
            "size": f["size"], "title": title, "description": desc, "highlight": highlight, "tools": tools,
        })
    files.sort(key=lambda x: (x["area"], x["folder"], x["path"]))
    collections = [{"folder": k, "title": v[0], "description": v[1], "tool": v[2],
                    "files": sum(1 for f in files if f["folder"] == k)} for k, v in COLLECTIONS.items()]
    return {"files": files, "collections": collections, "count": len(files), "bytes": sum(f["size"] for f in files)}


@lru_cache(maxsize=1)
def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in catalog()["files"]:
            z.write(EXAMPLES_DIR / f["path"], f"vlsi_toolkit_examples/{f['path']}")
    return buf.getvalue()


def resolve(path):
    """Absolute path of an example, refusing anything outside the examples folder."""
    target = (EXAMPLES_DIR / path).resolve()
    if EXAMPLES_DIR.resolve() not in target.parents or not target.is_file():
        raise FileNotFoundError(path)
    return target
