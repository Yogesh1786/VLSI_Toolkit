"""GDSII / OASIS layout reader for the web viewer (needs `pip install gdstk`).

    analyze(data, filename, cell=None) -> {
        cells, top_cells, cell, bbox, unit, layers: [{layer, datatype, name, polygons, area, path}],
        hierarchy, usage, labels, polygons, shown_polygons, truncated }

`path` is an SVG path (micrometres, y pointing down) with every polygon of that layer, so the
browser can draw the whole layout with one <path> per layer. Very large layouts keep only the
biggest polygons (MAX_POLYGONS) so the page stays fast.
"""

import tempfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    import gdstk
except ImportError:   # optional dependency
    gdstk = None

MAX_BYTES = 15 * 1024 * 1024
MAX_POLYGONS = 40000
MAX_LABELS = 400

# common layer names (SkyWater 130 numbering; GF180 / FreePDK45 use other numbers)
LAYER_NAMES = {
    (64, 20): "nwell", (64, 16): "nwell.pin", (65, 20): "diff", (65, 44): "tap", (66, 20): "poly", (66, 44): "licon1",
    (67, 20): "li1", (67, 44): "mcon", (68, 20): "met1", (68, 44): "via", (69, 20): "met2", (69, 44): "via2",
    (70, 20): "met3", (70, 44): "via3", (71, 20): "met4", (71, 44): "via4", (72, 20): "met5", (76, 20): "pad",
    (93, 44): "nsdm", (94, 20): "psdm", (95, 20): "npc", (78, 44): "hvi", (83, 44): "text", (235, 4): "prBoundary",
}


class GdsError(Exception):
    pass


def available():
    return gdstk is not None


def _fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def _usage(cell):
    """How many times each cell is placed below `cell`, counting array repetitions."""
    counts = Counter()

    def walk(c, mult):
        for ref in c.references:
            if not isinstance(ref.cell, gdstk.Cell):
                continue
            n = ref.repetition.size if ref.repetition and ref.repetition.size else 1
            counts[ref.cell.name] += mult * n
            walk(ref.cell, mult * n)

    walk(cell, 1)
    return counts


def _tree(cell, depth=0, max_depth=6):
    groups = Counter()
    by_name = {}
    for ref in cell.references:
        if isinstance(ref.cell, gdstk.Cell):
            n = ref.repetition.size if ref.repetition and ref.repetition.size else 1
            groups[ref.cell.name] += n
            by_name[ref.cell.name] = ref.cell
    node = {"name": cell.name, "polygons": len(cell.polygons) + len(cell.paths), "children": []}
    if depth < max_depth:
        node["children"] = [dict(_tree(by_name[n], depth + 1, max_depth), count=c) for n, c in groups.most_common()]
    return node


def analyze(data, filename="layout.gds", cell=None):
    if gdstk is None:
        raise GdsError("GDS support is not installed on this server (pip install gdstk).")
    if len(data) > MAX_BYTES:
        raise GdsError(f"The layout is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    suffix = ".oas" if filename.lower().endswith((".oas", ".oasis")) else ".gds"
    with tempfile.TemporaryDirectory(prefix="vt_gds_") as tmp:
        path = Path(tmp) / f"layout{suffix}"
        path.write_bytes(data)
        try:
            lib = gdstk.read_oas(str(path)) if suffix == ".oas" else gdstk.read_gds(str(path))
        except Exception as exc:
            raise GdsError(f"Not a readable {'OASIS' if suffix == '.oas' else 'GDSII'} file: {exc}")
    cells = {c.name: c for c in lib.cells if isinstance(c, gdstk.Cell)}
    if not cells:
        raise GdsError("The library contains no cells.")
    tops = [c for c in lib.top_level() if isinstance(c, gdstk.Cell)]

    def bbox_area(c):
        b = c.bounding_box()
        return 0 if b is None else (b[1][0] - b[0][0]) * (b[1][1] - b[0][1])

    tops.sort(key=bbox_area, reverse=True)
    target = cells.get(cell) if cell else (tops[0] if tops else next(iter(cells.values())))
    if target is None:
        raise GdsError(f"Cell '{cell}' not found.")

    polys = target.get_polygons(apply_repetitions=True, include_paths=True)
    total = len(polys)
    shown = polys
    truncated = False
    if total > MAX_POLYGONS:
        shown = sorted(polys, key=lambda p: abs(p.area()), reverse=True)[:MAX_POLYGONS]
        truncated = True

    stats = defaultdict(lambda: {"polygons": 0, "area": 0.0})
    for p in polys:
        s = stats[(p.layer, p.datatype)]
        s["polygons"] += 1
        s["area"] += abs(p.area())
    paths = defaultdict(list)
    for p in shown:
        pts = p.points
        if len(pts) < 3:
            continue
        d = "M" + " L".join(f"{_fmt(x)} {_fmt(-y)}" for x, y in pts) + "Z"
        paths[(p.layer, p.datatype)].append(d)

    layers = []
    for (layer, dt), s in sorted(stats.items()):
        layers.append({"layer": layer, "datatype": dt, "name": LAYER_NAMES.get((layer, dt), f"L{layer}/{dt}"),
                       "polygons": s["polygons"], "area": round(s["area"], 4), "path": "".join(paths.get((layer, dt), []))})

    labels = []
    for lab in target.get_labels(apply_repetitions=True)[:MAX_LABELS]:
        x, y = lab.origin
        labels.append({"text": lab.text, "x": round(x, 4), "y": round(-y, 4), "layer": lab.layer})

    b = target.bounding_box()
    (x0, y0), (x1, y1) = b if b is not None else ((0, 0), (1, 1))
    usage = _usage(target)
    return {
        "file": filename,
        "library": lib.name,
        "unit": lib.unit,
        "precision": lib.precision,
        "cells": sorted(cells),
        "top_cells": [c.name for c in tops],
        "cell": target.name,
        "bbox": {"x0": round(x0, 4), "y0": round(y0, 4), "x1": round(x1, 4), "y1": round(y1, 4),
                 "width": round(x1 - x0, 4), "height": round(y1 - y0, 4)},
        "layers": layers,
        "labels": labels,
        "hierarchy": _tree(target),
        "usage": [{"cell": n, "instances": c} for n, c in usage.most_common()],
        "instances": sum(usage.values()),
        "polygons": total,
        "shown_polygons": len(shown),
        "truncated": truncated,
    }


def analyze_file(path, cell=None):
    p = Path(path)
    return analyze(p.read_bytes(), p.name, cell)
