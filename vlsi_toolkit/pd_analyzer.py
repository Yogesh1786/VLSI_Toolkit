"""Physical design analyzer for DEF (+ optional LEF) files.

DEF = Design Exchange Format: the placed/routed layout database that every
P&R tool (Innovus, ICC2, OpenROAD) can export.
LEF = Library Exchange Format: cell sizes (MACRO ... SIZE w BY h) and sites.

Reports:
  * die area, core area (from ROWs) and std-cell utilization (needs LEF)
  * cell mix: flops, latches, clock cells, buffers/inverters, logic,
    physical-only cells (fill/decap/tap) and macros
  * most used cell types, placement status (PLACED / FIXED / UNPLACED)
  * a text "density map" of where cells sit on the die - hot spots often
    mean routing congestion later
"""

import re
from dataclasses import dataclass, field

from .common import format_table

# ---------------------------------------------------------------------------
# LEF
# ---------------------------------------------------------------------------


@dataclass
class LefMacro:
    name: str
    cls: str  # CORE, BLOCK, PAD, ENDCAP ...
    subclass: str
    width: float  # microns
    height: float


@dataclass
class Lef:
    macros: dict = field(default_factory=dict)
    sites: dict = field(default_factory=dict)  # name -> (w, h)


def _strip_hash_comments(text):
    return re.sub(r"#[^\n]*", "", text)


def parse_lef(text, lef=None):
    """Parse LEF text. Pass an existing Lef to merge several files (tech + cells)."""
    lef = lef or Lef()
    text = _strip_hash_comments(text)
    for m in re.finditer(r"^\s*SITE\s+(\S+)(.*?)^\s*END\s+\1\b", text, re.M | re.S):
        size = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", m.group(2))
        if size:
            lef.sites[m.group(1)] = (float(size.group(1)), float(size.group(2)))
    for m in re.finditer(r"^\s*MACRO\s+(\S+)(.*?)^\s*END\s+\1\b", text, re.M | re.S):
        body = m.group(2)
        cls = re.search(r"CLASS\s+(\w+)(?:\s+(\w+))?\s*;", body)
        size = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", body)
        lef.macros[m.group(1)] = LefMacro(
            m.group(1),
            cls.group(1).upper() if cls else "CORE",
            (cls.group(2) or "").upper() if cls else "",
            float(size.group(1)) if size else 0.0,
            float(size.group(2)) if size else 0.0,
        )
    return lef


# ---------------------------------------------------------------------------
# DEF
# ---------------------------------------------------------------------------


@dataclass
class Component:
    name: str
    cell: str
    status: str  # PLACED / FIXED / COVER / UNPLACED
    x: int = 0
    y: int = 0
    orient: str = ""


@dataclass
class Row:
    name: str
    site: str
    x: int
    y: int
    nx: int
    ny: int
    step_x: int


@dataclass
class Def:
    design: str = ""
    dbu: int = 1000  # database units per micron
    die: tuple = (0, 0, 0, 0)  # bounding box in DBU
    die_area_dbu: int = 0
    rows: list = field(default_factory=list)
    components: list = field(default_factory=list)
    pins: int = 0
    nets: int = 0
    special_nets: int = 0


def _polygon_area(points):
    """Shoelace formula - DIEAREA may be a rectilinear polygon, not just a box."""
    if len(points) == 2:
        (x1, y1), (x2, y2) = points
        return abs(x2 - x1) * abs(y2 - y1)
    s = 0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) // 2


def parse_def(text):
    d = Def()
    text = _strip_hash_comments(text)
    if m := re.search(r"^\s*DESIGN\s+(\S+)\s*;", text, re.M):
        d.design = m.group(1)
    if m := re.search(r"UNITS\s+DISTANCE\s+MICRONS\s+(\d+)", text):
        d.dbu = int(m.group(1))
    if m := re.search(r"DIEAREA\s+((?:\(\s*-?\d+\s+-?\d+\s*\)\s*)+);", text):
        pts = [(int(x), int(y)) for x, y in re.findall(r"\(\s*(-?\d+)\s+(-?\d+)\s*\)", m.group(1))]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        d.die = (min(xs), min(ys), max(xs), max(ys))
        d.die_area_dbu = _polygon_area(pts)

    row_re = re.compile(
        r"^\s*ROW\s+(\S+)\s+(\S+)\s+(-?\d+)\s+(-?\d+)\s+\S+"
        r"(?:\s+DO\s+(\d+)\s+BY\s+(\d+)(?:\s+STEP\s+(\d+)\s+(\d+))?)?\s*;",
        re.M,
    )
    for m in row_re.finditer(text):
        d.rows.append(Row(m.group(1), m.group(2), int(m.group(3)), int(m.group(4)),
                          int(m.group(5) or 1), int(m.group(6) or 1), int(m.group(7) or 0)))

    if m := re.search(r"^\s*COMPONENTS\s+\d+\s*;(.*?)^\s*END\s+COMPONENTS", text, re.M | re.S):
        place_re = re.compile(r"\+\s*(PLACED|FIXED|COVER)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\S+)")
        for stmt in m.group(1).split(";"):
            tokens = stmt.split()
            if len(tokens) < 3 or tokens[0] != "-":
                continue
            comp = Component(tokens[1], tokens[2], "UNPLACED")
            if p := place_re.search(stmt):
                comp.status, comp.x, comp.y, comp.orient = p.group(1), int(p.group(2)), int(p.group(3)), p.group(4)
            d.components.append(comp)

    if m := re.search(r"^\s*PINS\s+(\d+)\s*;", text, re.M):
        d.pins = int(m.group(1))
    if m := re.search(r"^\s*NETS\s+(\d+)\s*;", text, re.M):
        d.nets = int(m.group(1))
    if m := re.search(r"^\s*SPECIALNETS\s+(\d+)\s*;", text, re.M):
        d.special_nets = int(m.group(1))
    return d


def parse_files(def_path, lef_paths=()):
    with open(def_path, encoding="utf-8", errors="replace") as f:
        d = parse_def(f.read())
    lef = Lef()
    for p in lef_paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            parse_lef(f.read(), lef)
    return d, lef


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

CATEGORIES = ["Macro", "Flip-flop", "Latch", "Clock cell", "Buffer/Inverter", "Logic", "Physical-only"]

_PHYSICAL_RE = re.compile(r"fill|decap|tap|endcap|antenna|diode|phy_|spacer|welltie|tie(hi|lo)", re.I)


def base_cell_name(cell):
    """sky130_fd_sc_hd__dfrtp_4 -> dfrtp ;  NAND2X1 -> nand2x ;  INV_X2 -> inv_x"""
    name = cell.split("__")[-1].lower()
    return re.sub(r"_?\d+$", "", name)


def categorize(cell, lef=None):
    macro = lef.macros.get(cell) if lef else None
    if macro and macro.cls in ("BLOCK", "PAD", "RING"):
        return "Macro"
    if macro and macro.cls in ("ENDCAP",) or (macro and macro.subclass in ("SPACER", "WELLTAP", "ANTENNACELL")):
        return "Physical-only"
    base = base_cell_name(cell)
    if _PHYSICAL_RE.search(base):
        return "Physical-only"
    if re.match(r"(clk|ck)", base):
        return "Clock cell"
    if re.match(r"(s|e|se|sed)?df|dff|sdff|fd\d|edff", base):
        return "Flip-flop"
    if re.match(r"(dl|t?lat|ld)", base) and not base.startswith("dly"):
        return "Latch"
    if re.match(r"(buf|inv|dly|bu\d|in\d)", base):
        return "Buffer/Inverter"
    return "Logic"


def cell_area(cell, lef):
    m = lef.macros.get(cell) if lef else None
    return m.width * m.height if m else 0.0


def core_area_um2(d, lef):
    """Area covered by placement rows, in square microns."""
    if not d.rows:
        return 0.0
    ys = sorted({r.y for r in d.rows})
    inferred_h = min((b - a for a, b in zip(ys, ys[1:]) if b > a), default=0) / d.dbu
    total = 0.0
    for r in d.rows:
        site = lef.sites.get(r.site) if lef else None
        site_w = site[0] if site else r.step_x / d.dbu
        site_h = site[1] if site else inferred_h
        total += r.nx * r.ny * site_w * site_h
    return total


def analyze(d, lef=None):
    lef = lef or Lef()
    has_lef = bool(lef.macros)
    stats = {c: {"count": 0, "area": 0.0} for c in CATEGORIES}
    per_cell = {}
    status = {}
    for c in d.components:
        cat = categorize(c.cell, lef)
        area = cell_area(c.cell, lef)
        stats[cat]["count"] += 1
        stats[cat]["area"] += area
        pc = per_cell.setdefault(c.cell, {"count": 0, "area": 0.0, "category": cat})
        pc["count"] += 1
        pc["area"] += area
        status[c.status] = status.get(c.status, 0) + 1

    die_um2 = d.die_area_dbu / d.dbu**2
    core_um2 = core_area_um2(d, lef)
    std_area = sum(stats[c]["area"] for c in CATEGORIES if c not in ("Macro", "Physical-only"))
    macro_area = stats["Macro"]["area"]
    util = None
    if has_lef and core_um2 > macro_area:
        util = std_area / (core_um2 - macro_area)
    return {
        "die_um2": die_um2,
        "core_um2": core_um2,
        "std_area": std_area,
        "macro_area": macro_area,
        "utilization": util,
        "categories": stats,
        "per_cell": per_cell,
        "status": status,
        "has_lef": has_lef,
    }


_RAMP = " .:-=+*#%@"


def density_grid(d, lef=None, cols=48, rows=16):
    """Cell density per bin: (grid[row][col], macro_bins).

    grid holds cell area (if LEF given) or cell count per bin; row 0 is the
    bottom of the die. macro_bins is a set of (col, row) covered by macros.
    Returns (None, set()) when the DEF has no DIEAREA.
    """
    x1, y1, x2, y2 = d.die
    if x2 <= x1 or y2 <= y1:
        return None, set()
    grid = [[0.0] * cols for _ in range(rows)]
    for c in d.components:
        if c.status == "UNPLACED" or categorize(c.cell, lef) in ("Physical-only", "Macro"):
            continue
        cx = min(cols - 1, max(0, int((c.x - x1) / (x2 - x1) * cols)))
        cy = min(rows - 1, max(0, int((c.y - y1) / (y2 - y1) * rows)))
        grid[cy][cx] += cell_area(c.cell, lef) or 1.0
    marks = set()
    for c in d.components:
        m = lef.macros.get(c.cell) if lef else None
        if c.status != "UNPLACED" and m and categorize(c.cell, lef) == "Macro":
            w, h = m.width * d.dbu, m.height * d.dbu
            if c.orient in ("E", "W", "FE", "FW"):
                w, h = h, w
            for gy in range(rows):
                for gx in range(cols):
                    bx = x1 + (gx + 0.5) * (x2 - x1) / cols
                    by = y1 + (gy + 0.5) * (y2 - y1) / rows
                    if c.x <= bx <= c.x + w and c.y <= by <= c.y + h:
                        marks.add((gx, gy))
    return grid, marks


def density_map(d, lef=None, cols=48, rows=16):
    """ASCII map of cell density (cell area per bin if LEF given, else cell count)."""
    grid, marks = density_grid(d, lef, cols, rows)
    if grid is None:
        return "(no DIEAREA)"
    peak = max(max(r) for r in grid) or 1.0
    lines = ["+" + "-" * cols + "+"]
    for gy in reversed(range(rows)):  # y grows upward on a chip
        row = ""
        for gx in range(cols):
            if (gx, gy) in marks:
                row += "M"
            else:
                v = grid[gy][gx] / peak
                row += _RAMP[min(len(_RAMP) - 1, int(v * (len(_RAMP) - 1) + 0.999)) if v > 0 else 0]
        lines.append("|" + row + "|")
    lines.append("+" + "-" * cols + "+")
    lines.append(f"density: ' ' empty  {_RAMP[1:]}  dense    M = macro")
    return "\n".join(lines)


def report_text(d, lef=None, top=10):
    a = analyze(d, lef)
    x1, y1, x2, y2 = d.die
    out = [
        f"Design: {d.design or '?'}   DBU/micron: {d.dbu}",
        f"Die: {(x2 - x1) / d.dbu:.2f} x {(y2 - y1) / d.dbu:.2f} um  = {a['die_um2']:,.1f} um^2",
        f"Core (rows): {a['core_um2']:,.1f} um^2   Rows: {len(d.rows)}   "
        f"Pins: {d.pins}   Nets: {d.nets}   Special nets: {d.special_nets}",
    ]
    if a["utilization"] is not None:
        out.append(f"Std-cell area: {a['std_area']:,.1f} um^2   Macro area: {a['macro_area']:,.1f} um^2   "
                   f"UTILIZATION: {a['utilization']:.1%}")
    elif not a["has_lef"]:
        out.append("(give --lef files to get cell areas and utilization)")

    total = len(d.components) or 1
    out.append("")
    out.append("CELL MIX")
    rows = []
    for cat in CATEGORIES:
        s = a["categories"][cat]
        if s["count"]:
            rows.append([cat, s["count"], f"{s['count'] / total:.1%}", f"{s['area']:,.1f}" if a["has_lef"] else "-"])
    rows.append(["TOTAL", len(d.components), "100%", f"{sum(s['area'] for s in a['categories'].values()):,.1f}" if a["has_lef"] else "-"])
    out.append(format_table(["Category", "Instances", "Share", "Area um^2"], rows))

    out.append("")
    out.append(f"TOP {top} CELL TYPES")
    top_cells = sorted(a["per_cell"].items(), key=lambda kv: -kv[1]["count"])[:top]
    out.append(format_table(
        ["Cell", "Category", "Count", "Area um^2"],
        [[n, v["category"], v["count"], f"{v['area']:,.1f}" if a["has_lef"] else "-"] for n, v in top_cells],
    ))

    out.append("")
    out.append("PLACEMENT STATUS: " + "   ".join(f"{k} {v}" for k, v in sorted(a["status"].items())))
    unplaced = [c.name for c in d.components if c.status == "UNPLACED"]
    if unplaced:
        out.append(f"WARNING: {len(unplaced)} unplaced instance(s): {', '.join(unplaced[:8])}"
                   + (" ..." if len(unplaced) > 8 else ""))
    if lef and lef.macros:
        missing = sorted({c.cell for c in d.components if c.cell not in lef.macros})
        if missing:
            out.append(f"WARNING: {len(missing)} cell type(s) not found in LEF: {', '.join(missing[:8])}")
    out.append("")
    out.append("PLACEMENT DENSITY MAP")
    out.append(density_map(d, lef))
    return "\n".join(out)
