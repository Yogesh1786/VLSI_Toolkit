"""Synthesis report analyzer: area and cell counts per module.

Formats:
  * Yosys `stat` (optionally with a Liberty file: `stat -liberty cells.lib` adds areas)
  * Synopsys Design Compiler `report_area` / `report_area -hierarchy`

parse_report(text) -> {
    format, top, total_area, comb_area, seq_area, buf_inv_area, macro_area, total_cells,
    modules:    [{name, design, area, percent, cells, comb_area, seq_area}],
    cell_types: [{cell, count}]          (Yosys)
}
"""

import re

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Yosys
# ---------------------------------------------------------------------------

def _parse_yosys(text):
    blocks = re.split(r"(?m)^===\s*(.+?)\s*===\s*$", text)
    modules, hierarchy, top = {}, None, None
    for name, body in zip(blocks[1::2], blocks[2::2]):
        name = name.strip().lstrip("\\")
        if name == "design hierarchy":
            hierarchy = body
            continue
        cells = re.search(r"Number of cells:\s*(\d+)", body)
        area = re.search(rf"Chip area for module\s+'\\?([^']+)':\s*({_NUM})", body)
        types = []
        if cells:
            # cell type lines follow "Number of cells:" and are indented deeper
            after = body[cells.end():]
            for m in re.finditer(r"(?m)^\s{4,}(\S+)\s+(\d+)\s*$", after):
                if m.group(1).startswith(("Chip", "Number")):
                    break
                types.append({"cell": m.group(1).lstrip("\\"), "count": int(m.group(2))})
        modules[name] = {
            "name": name, "design": name, "cells": int(cells.group(1)) if cells else None,
            "area": float(area.group(2)) if area else None, "cell_types": types,
            "wires": int(m.group(1)) if (m := re.search(r"Number of wires:\s*(\d+)", body)) else None,
        }
    total_area = total_cells = None
    instances = {}
    if hierarchy:
        t = re.search(rf"Chip area for top module\s+'\\?([^']+)':\s*({_NUM})", hierarchy)
        if t:
            top, total_area = t.group(1), float(t.group(2))
        c = re.findall(r"Number of cells:\s*(\d+)", hierarchy)
        if c:
            total_cells = int(c[-1])
        for m in re.finditer(r"(?m)^\s{3,}(\S+)\s+(\d+)\s*$", hierarchy.split("Number of")[0]):
            instances[m.group(1).lstrip("\\")] = int(m.group(2))
        if not top and instances:
            top = next(iter(instances))
    if top is None and modules:
        top = max(modules.values(), key=lambda m: m["cells"] or 0)["name"]
    # per-module totals: own area x number of instances
    rows = []
    for m in modules.values():
        n = instances.get(m["name"], 1)
        rows.append({**m, "instances": n, "total_area": (m["area"] or 0) * n if m["area"] is not None else None})
    if total_area is None and rows and all(r["area"] is not None for r in rows):
        total_area = sum(r["total_area"] for r in rows)
    if total_cells is None and rows:
        total_cells = sum((r["cells"] or 0) * r["instances"] for r in rows)
    agg = {}
    for r in rows:
        for t_ in r["cell_types"]:
            agg[t_["cell"]] = agg.get(t_["cell"], 0) + t_["count"] * r["instances"]
    seq_area = None
    for r in rows:
        r["percent"] = round(100 * r["total_area"] / total_area, 2) if total_area and r["total_area"] is not None else None
        r["seq_cells"] = sum(t_["count"] for t_ in r["cell_types"] if _is_seq(t_["cell"]))
    return {
        "format": "yosys", "top": top, "total_area": total_area, "total_cells": total_cells,
        "comb_area": None, "seq_area": seq_area, "buf_inv_area": None, "macro_area": None,
        "seq_cells": sum(c for k, c in agg.items() if _is_seq(k)),
        "modules": sorted(rows, key=lambda r: -((r["total_area"] or 0) or (r["cells"] or 0))),
        "cell_types": sorted(({"cell": k, "count": v, "sequential": _is_seq(k)} for k, v in agg.items()), key=lambda c: -c["count"]),
    }


def _is_seq(cell):
    c = cell.lower().split("__")[-1]
    return bool(re.search(r"(^|_)\$?_?(s?df|dff|sdff|adff|dlatch|latch|ff)", c)) or c.startswith(("$_dff", "$_sdff", "$_dlatch", "$adff", "$dff"))


# ---------------------------------------------------------------------------
# Design Compiler
# ---------------------------------------------------------------------------

def _parse_dc(text):
    def val(label):
        m = re.search(rf"{label}:\s*({_NUM})", text)
        return float(m.group(1)) if m else None

    rows = []
    hier = re.search(r"Hierarchical area distribution(.*?)(?:\n\s*\n\s*\n|\Z|^1$)", text, re.S | re.M)
    if hier:
        for line in hier.group(1).splitlines():
            parts = line.split()
            if len(parts) >= 7 and all(_f(p) is not None for p in parts[1:6]):
                rows.append({"name": parts[0], "design": parts[6] if len(parts) > 6 else parts[0],
                             "total_area": float(parts[1]), "percent": float(parts[2]),
                             "comb_area": float(parts[3]), "seq_area": float(parts[4]), "macro_area": float(parts[5]),
                             "cells": None, "instances": 1, "area": float(parts[3]) + float(parts[4]) + float(parts[5])})
    design = re.search(r"Design\s*:\s*(\S+)", text)
    cells = re.search(r"Number of cells:\s*(\d+)", text)
    total = val("Total cell area")
    return {
        "format": "design_compiler", "top": design.group(1) if design else (rows[0]["name"] if rows else None),
        "total_area": total, "total_cells": int(cells.group(1)) if cells else None,
        "comb_area": val("Combinational area"), "seq_area": val("Noncombinational area"),
        "buf_inv_area": val("Buf/Inv area"), "macro_area": val("Macro/Black Box area"),
        "seq_cells": int(m.group(1)) if (m := re.search(r"Number of sequential cells:\s*(\d+)", text)) else None,
        "modules": rows, "cell_types": [],
        "ports": int(m.group(1)) if (m := re.search(r"Number of ports:\s*(\d+)", text)) else None,
        "nets": int(m.group(1)) if (m := re.search(r"Number of nets:\s*(\d+)", text)) else None,
    }


def parse_report(text):
    if re.search(r"(?m)^===\s*.+\s*===", text) and "Number of cells" in text:
        return _parse_yosys(text)
    if re.search(r"Total cell area|Combinational area", text):
        return _parse_dc(text)
    raise ValueError("Not a recognised synthesis report (expected Yosys 'stat' or Design Compiler 'report_area')")


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_report(f.read())
