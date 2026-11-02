"""RTL design: module parsing, lint, register maps, hierarchy and FSMs, logic synthesis (Yosys)."""

import json

from fastapi import APIRouter, HTTPException

from vlsi_toolkit import hierarchy, lint, regmap_gen, sv_compile, tb_generator, uvm_gen, verilog_parser, yosys_synth

from ..models import Files, LintRequest, SourceFile, SynthRequest

router = APIRouter(prefix="/api/rtl", tags=["RTL design"])


def _module_json(m):
    return {
        "name": m.name,
        "ansi": m.ansi,
        "warnings": m.warnings,
        "parameters": [
            {"name": p.name, "default": p.default, "value": p.value, "local": p.local}
            for p in m.parameters
        ],
        "ports": [
            {
                "name": p.name,
                "direction": p.direction,
                "net_type": p.net_type,
                "signed": p.signed,
                "range": p.packed_range,
                "width": p.width,
            }
            for p in m.ports
        ],
        "instantiation": tb_generator.instantiation(m),
    }


@router.post("/parse")
def parse(req: SourceFile):
    return {"modules": [_module_json(m) for m in verilog_parser.parse_text(req.text)]}


@router.post("/lint")
def run_lint(req: LintRequest):
    issues = []
    for f in req.files:
        issues += lint.lint_text(f.text, f.name)
    found = [{"file": i.file, "line": i.line, "severity": i.severity, "rule": i.rule, "message": i.message, "source": "lint"}
             for i in issues]
    compiler = {"available": sv_compile.available(), "ran": False, "top_modules": []}
    if req.compiler and sv_compile.available():
        c = sv_compile.check([(f.name, f.text) for f in req.files])
        compiler.update(ran=True, top_modules=c["top_modules"])
        found += [{k: i[k] for k in ("file", "line", "severity", "rule", "message")} | {"source": "compiler"} for i in c["issues"]]
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    found.sort(key=lambda i: (order[i["severity"]], i["file"], i["line"]))
    return {
        "files": [f.name for f in req.files],
        "issues": found,
        "rules": lint.SEVERITY | (sv_compile.SEVERITY if compiler["ran"] else {}),
        "rule_help": sv_compile.RULE_HELP if compiler["ran"] else {},
        "compiler": compiler,
    }


@router.post("/regmap")
def regmap(req: SourceFile):
    try:
        if req.name.lower().endswith((".yaml", ".yml")):
            import yaml  # optional dependency

            data = yaml.safe_load(req.text)
        else:
            data = json.loads(req.text)
        rm = regmap_gen.build_regmap(data)
    except ImportError:
        return {
            "error": "YAML specs need PyYAML (pip install pyyaml). Or use a JSON spec."
        }
    except json.JSONDecodeError as exc:
        return {
            "error": f"JSON syntax error at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        }
    except (regmap_gen.RegMapError, AttributeError, TypeError) as exc:
        return {"error": str(exc)}
    digits = rm.data_width // 4
    return {
        "block": rm.block,
        "data_width": rm.data_width,
        "addr_width": rm.addr_width,
        "base_address": f"0x{rm.base_address:08X}",
        "description": rm.description,
        "registers": [
            {
                "name": r.name,
                "offset": f"0x{r.offset:02X}",
                "access": r.access,
                "reset": f"0x{r.reset:0{digits}X}",
                "mask": f"0x{r.mask:0{digits}X}",
                "description": r.description,
                "fields": [
                    {
                        "name": f.name,
                        "bits": f.bits,
                        "reset": f"0x{f.reset:X}",
                        "description": f.description,
                    }
                    for f in r.fields
                ],
            }
            for r in rm.registers
        ],
        "outputs": {
            f"{rm.block}_regs.v": regmap_gen.gen_verilog(rm),
            f"{rm.block}_regs.h": regmap_gen.gen_c_header(rm),
            f"{rm.block}_regs.html": regmap_gen.gen_html(rm),
            f"{rm.block}_axil.v": regmap_gen.gen_axi_lite(rm),
            f"tb_{rm.block}_axil.v": regmap_gen.gen_axi_lite_tb(rm),
            **uvm_gen.uvm_ral(rm)["files"],
        },
    }


@router.post("/hierarchy")
def design_hierarchy(req: Files):
    return hierarchy.analyze_project([(f.name, f.text) for f in req.files])


@router.post("/synth")
def synthesize(req: SynthRequest):
    """Real logic synthesis with Yosys: gate counts, flip-flops, NAND2 equivalents, logic depth, netlist."""
    try:
        return yosys_synth.synthesize([(f.name, f.text) for f in req.files], req.top or None, req.flatten)
    except yosys_synth.SynthError as exc:
        raise HTTPException(400, str(exc))
