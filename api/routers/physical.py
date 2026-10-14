"""Physical design: timing reports, DEF/LEF floorplans, Liberty libraries, sign-off reports (synthesis, power, SDC)."""

import hashlib
from collections import OrderedDict

from fastapi import APIRouter, HTTPException

from vlsi_toolkit import (
    liberty,
    pd_analyzer,
    power_report,
    sdc_check,
    synth_report,
    timing_report,
)

from ..models import FloorplanRequest, LibertyCellRequest, SdcRequest, SourceFile

router = APIRouter(prefix="/api/pd", tags=["Physical design"])


@router.post("/timing")
def timing(req: SourceFile):
    paths = timing_report.parse_report(req.text)
    return {
        "paths": timing_report.to_dicts(paths),
        "summary": timing_report.summarize(paths),
    }


@router.post("/floorplan")
def floorplan(req: FloorplanRequest):
    d = pd_analyzer.parse_def(req.def_file.text)
    lef = pd_analyzer.Lef()
    for f in req.lefs:
        pd_analyzer.parse_lef(f.text, lef)
    a = pd_analyzer.analyze(d, lef)
    x1, y1, x2, y2 = d.die
    cols = 48
    rows = max(8, round(cols * (y2 - y1) / max(x2 - x1, 1)))
    grid, macros = pd_analyzer.density_grid(d, lef, cols=cols, rows=rows)
    return {
        "design": d.design,
        "dbu": d.dbu,
        "die_w_um": (x2 - x1) / d.dbu,
        "die_h_um": (y2 - y1) / d.dbu,
        "die_um2": a["die_um2"],
        "core_um2": a["core_um2"],
        "rows": len(d.rows),
        "pins": d.pins,
        "nets": d.nets,
        "instances": len(d.components),
        "utilization": a["utilization"],
        "std_area": a["std_area"],
        "macro_area": a["macro_area"],
        "has_lef": a["has_lef"],
        "status": a["status"],
        "categories": [
            {"category": c, **v} for c, v in a["categories"].items() if v["count"]
        ],
        "cells": sorted(
            ({"cell": n, **v} for n, v in a["per_cell"].items()),
            key=lambda c: -c["count"],
        ),
        "unplaced": [c.name for c in d.components if c.status == "UNPLACED"],
        "missing_in_lef": (
            sorted({c.cell for c in d.components if c.cell not in lef.macros})
            if lef.macros
            else []
        ),
        "grid": grid,
        "macro_bins": sorted(macros),
    }


_LIB_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_LIB_CACHE_SIZE = 4


def _library(text):
    """Parsed libraries are cached by content hash, so clicking through cells is instant."""
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
    if key not in _LIB_CACHE:
        _LIB_CACHE[key] = liberty.library_summary(liberty.parse_liberty(text))
        while len(_LIB_CACHE) > _LIB_CACHE_SIZE:
            _LIB_CACHE.popitem(last=False)
    _LIB_CACHE.move_to_end(key)
    return _LIB_CACHE[key]


@router.post("/liberty")
def library(req: SourceFile):
    lib = _library(req.text)
    if not lib["cells"]:
        return {"error": "No cells found. Is this a Liberty (.lib) file?"}
    cells = [
        {k: v for k, v in c.items() if k not in ("pins", "arcs")}
        | {
            "pin_count": len(c["pins"]),
            "arc_count": len(c["arcs"]),
            "max_input_cap": max(
                (p["capacitance"] or 0 for p in c["pins"] if p["direction"] == "input"),
                default=None,
            ),
        }
        for c in lib["cells"]
    ]
    return {k: v for k, v in lib.items() if k != "cells"} | {"cells": cells}


@router.post("/liberty/cell")
def library_cell(req: LibertyCellRequest):
    for c in _library(req.text)["cells"]:
        if c["name"] == req.cell:
            return c
    raise HTTPException(404, f"cell '{req.cell}' not found in this library")


@router.post("/synthesis")
def synthesis(req: SourceFile):
    try:
        return synth_report.parse_report(req.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/power")
def power(req: SourceFile):
    try:
        return power_report.parse_report(req.text)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/sdc")
def sdc(req: SdcRequest):
    top, ports = None, None
    if req.rtl:
        top, ports = sdc_check.ports_from_rtl(
            "\n".join(f.text for f in req.rtl), req.module
        )
        if not ports:
            raise HTTPException(400, "No Verilog module found in the RTL file(s)")
    return sdc_check.check(req.text, ports) | {"rtl_top": top, "rtl_ports": ports}
