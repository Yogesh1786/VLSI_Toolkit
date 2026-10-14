"""Analog: SPICE netlist checks, parameter sweeps, waveform measurements."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException

from vlsi_toolkit import spice

from ..models import MeasureRequest, SourceFile, SweepRequest

router = APIRouter(prefix="/api/analog", tags=["Analog"])


@router.post("/netlist")
def netlist(req: SourceFile):
    nl = spice.parse_netlist(req.text)
    inst = {}
    for d in nl.devices:
        if d.kind == "x":
            inst[d.model.lower()] = inst.get(d.model.lower(), 0) + 1
    return {
        "title": nl.title, "params": {k: spice.eng(v).strip() for k, v in nl.params.items()},
        "analyses": nl.analyses, "measures": nl.measures, "includes": nl.includes,
        "devices": [{"name": d.name, "type": spice.DEVICE_NAMES[d.kind], "scope": d.scope or "top", "nodes": d.nodes,
                     "model": d.model, "params": d.params} for d in nl.devices],
        "subckts": [{"name": s.name, "pins": s.pins, "devices": sum(1 for d in nl.devices if d.scope == s.name),
                     "instances": inst.get(s.name, 0)} for s in nl.subckts.values()],
        "mosfets": [{**r, "w_text": spice.eng(r["w"], "m"), "l_text": spice.eng(r["l"], "m")} for r in spice.mosfet_table(nl)],
        "issues": spice.connectivity_issues(nl),
    }


def _sweep_values(spec):
    try:
        return spice.parse_sweep_values(spec) or None
    except (ValueError, TypeError):
        return None


@router.post("/sweep")
def sweep(req: SweepRequest):
    values = _sweep_values(req.values)
    if not values:
        return {"error": "Could not read the values. Use start:stop:step (e.g. 1.2:1.8:0.2) or a list like 1n,2n,5n."}
    nl = spice.parse_netlist(req.text)
    stem = Path(req.name).stem
    current = nl.params.get(req.param.lower())
    return {
        "params": {k: spice.eng(v).strip() for k, v in nl.params.items()},
        "current": spice.eng(current).strip() if current is not None else None,
        "values": values, "measures": nl.measures, "ngspice": bool(spice.find_ngspice()),
        "netlists": [{"name": f"{stem}_{req.param}_{v}.sp", "value": v, "text": t}
                     for v, t in spice.make_sweep(req.text, req.param, values)],
    }


@router.post("/sweep/run")
def sweep_run(req: SweepRequest):
    if not spice.find_ngspice():
        raise HTTPException(400, "ngspice is not installed on this computer")
    values = _sweep_values(req.values)
    if not values:
        raise HTTPException(400, "Could not read the sweep values")
    nl = spice.parse_netlist(req.text)
    rows = []
    with tempfile.TemporaryDirectory(prefix="vlsi_sweep_") as tmp:  # deleted automatically afterwards
        for v, text in spice.make_sweep(req.text, req.param, values):
            path = Path(tmp) / f"sweep_{v}.sp"
            path.write_text(text, encoding="utf-8")
            out = spice.run_ngspice(path)
            rows.append({"value": v, "value_num": spice.spice_value(v), **spice.parse_measurements(out, nl.measures)})
    return {"measures": nl.measures, "rows": rows}


@router.post("/measure")
def measure(req: MeasureRequest):
    try:
        waves = spice.parse_waveforms(req.text)
    except ValueError as exc:
        return {"error": f"Could not read the waveform file: {exc}"}
    names = list(waves)[1:]
    if not names:
        return {"error": "The file needs a time column and at least one signal column."}
    signals = [s for s in req.signals if s in names] or [names[-1]]
    ref = req.ref if req.ref in names else None
    results = {s: spice.measure(waves, s, ref, req.vdd or None) for s in signals}
    tkey = list(waves)[0]
    step = max(1, len(waves[tkey]) // 3000)
    show = list(dict.fromkeys(([ref] if ref else []) + signals))
    return {
        "signals": names, "selected": signals, "ref": ref, "results": results,
        "labels": [{"key": k, "label": label, "unit": unit} for k, label, unit in spice.MEAS_LABELS],
        "plot": [{"t_ns": waves[tkey][i] * 1e9, **{s: waves[s][i] for s in show}}
                 for i in range(0, len(waves[tkey]), step)],
    }
