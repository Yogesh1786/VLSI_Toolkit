"""Verification: testbenches, regression logs, VCD waveforms, AXI protocol checks."""

from pathlib import Path

from fastapi import APIRouter

from vlsi_toolkit import axi, regress, sva, tb_generator, vcd_analyzer, verilog_parser

from ..models import AxiRequest, Files, SvaRequest, TestbenchRequest, VcdRequest

router = APIRouter(prefix="/api/verif", tags=["Verification"])


def analyze_logs(files):
    """Analyze uploaded logs (also used by the compare router)."""
    return [regress.analyze_text(f.text, f.name) for f in files]


@router.post("/testbench")
def testbench(req: TestbenchRequest):
    modules = verilog_parser.parse_text(req.text)
    if not modules:
        return {"error": "No module found in this file.", "modules": []}
    try:
        mod = verilog_parser.pick_module(modules, req.module)
    except ValueError:
        mod = modules[-1]
    clocks, resets, data = tb_generator.classify(mod)
    return {
        "modules": [m.name for m in modules], "module": mod.name,
        "clocks": [c.name for c in clocks],
        "resets": [{"name": r.name, "active_low": tb_generator.reset_active_low(r)} for r in resets],
        "data_inputs": [p.name for p in data],
        "files": {f"tb_{mod.name}.v": tb_generator.verilog_tb(mod, req.cycles, req.period, source=req.name),
                  f"test_{mod.name}.py": tb_generator.cocotb_test(mod, Path(req.name), req.cycles, req.period)},
    }


@router.post("/regress")
def regression(req: Files):
    results = analyze_logs(req.files)
    return {
        "results": [{"file": r.file, "test": r.test, "seed": r.seed, "status": r.status, "errors": r.errors,
                     "fatals": r.fatals, "warnings": r.warnings, "first_error": r.first_error,
                     "short_error": r.short_error, "signature": r.signature} for r in results],
        "signatures": [{"signature": sig, "count": len(rs), "status": rs[0].status,
                        "tests": [f"{r.test}:{r.seed}" if r.seed else r.test for r in rs]}
                       for sig, rs in regress.signatures(results).items()],
        "html_report": regress.html_report(results),
    }


@router.post("/vcd")
def vcd(req: VcdRequest):
    dump = vcd_analyzer.parse_text(req.text)
    if not dump.signals:
        return {"error": "No signals found. Is this a VCD file?"}
    stats = vcd_analyzer.analyze(dump, req.glitch, req.x_after)
    return {
        "timescale": dump.timescale_text, "timescale_s": dump.timescale_s, "end_time": dump.end_time,
        "stats": [{"name": s.name, "width": s.width, "toggles": s.toggles,
                   "final": vcd_analyzer.short_value(s.final, s.width),
                   "clock": (vcd_analyzer.freq_text(s.period, dump.timescale_s) +
                             (f", duty {s.duty:.0%}" if s.duty else "")) if s.period else None,
                   "glitches": s.glitches, "x_after": s.x_after} for s in stats],
        # value changes for the waveform viewer (capped so huge dumps stay fast)
        "signals": {name: {"width": sig.width,
                           "changes": [[t, vcd_analyzer.short_value(v, sig.width)] for t, v in sig.changes[:5000]]}
                    for name, sig in sorted(dump.signals.items())},
    }


@router.post("/axi")
def axi_check(req: AxiRequest):
    result = axi.analyze_vcd_text(req.text, req.timeout)
    if not result["interfaces"]:
        return {"error": "No AXI interface found. Expected signals such as <prefix>awvalid, <prefix>awready, "
                         "<prefix>wdata ... in the VCD.", "rules": result["rules"]}
    return result


@router.post("/sva")
def assertions(req: SvaRequest):
    """SystemVerilog assertions for one module of the uploaded files."""
    modules = [(f.name, m.name) for f in req.files for m in verilog_parser.parse_text(f.text)]
    if not modules:
        return {"error": "No module found in these files.", "modules": []}
    target = req.module if req.module in [m for _, m in modules] else modules[-1][1]
    options = {k: getattr(req, k) for k in ("axi", "fsm", "onehot", "outputs", "covers")}
    try:
        result = sva.generate_files([(f.name, f.text) for f in req.files], target, options)
    except ValueError as exc:
        return {"error": str(exc), "modules": [m for _, m in modules], "module": target}
    result["all_modules"] = [{"file": f, "module": m} for f, m in modules]
    return result
