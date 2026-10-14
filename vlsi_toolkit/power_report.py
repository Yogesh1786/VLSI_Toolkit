"""Power report analyzer (PrimePower / PrimeTime-PX / Design Compiler / Innovus `report_power`).

Reads, when present:
  * the summary (Cell Internal Power, Net Switching Power, Total Dynamic Power, Cell Leakage Power)
  * the power-group table (clock_network, register, combinational, memory, io_pad ...)
  * the hierarchy table of `report_power -hierarchy` (one row per instance, indented by depth)

All values are converted to milliwatts.
"""

import re

_NUM = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_UNIT = {"w": 1e3, "mw": 1.0, "uw": 1e-3, "nw": 1e-6, "pw": 1e-9}


def _mw(value, unit, default_unit="mw"):
    return float(value) * _UNIT.get((unit or default_unit).lower(), 1.0)


def _default_unit(text):
    """'Dynamic Power Units = 1mW' style headers; else mW."""
    m = re.search(r"Dynamic Power Units\s*=\s*1\s*(\w+)", text)
    if m:
        return m.group(1).lower()
    m = re.search(r"Power\s+Units?\s*[:=]\s*1?\s*(mW|uW|nW|W)\b", text, re.I)
    return m.group(1).lower() if m else "mw"


def parse_report(text):
    unit = _default_unit(text)
    leak_unit = (
        m.group(1).lower()
        if (m := re.search(r"Leakage Power Units\s*=\s*1\s*(\w+)", text))
        else unit
    )

    def summary(label, du=unit):
        m = re.search(rf"{label}\s*=?\s*({_NUM})\s*(W|mW|uW|nW|pW)?", text, re.I)
        return _mw(m.group(1), m.group(2), du) if m else None

    totals = {
        "internal": summary(r"Cell Internal Power"),
        "switching": summary(r"Net Switching Power"),
        "dynamic": summary(r"Total Dynamic Power"),
        "leakage": summary(r"Cell Leakage Power", leak_unit),
    }

    # power groups: name followed by 4 numbers (internal switching leakage total) and maybe (pct %)
    groups = []
    grp_re = re.compile(
        rf"(?m)^\s*(io_pad|memory|black_box|clock_network|register|sequential|combinational|"
        rf"[a-z_]+_network|pad|macro)\s+({_NUM})\s*(\w*W)?\s+({_NUM})\s*(\w*W)?\s+({_NUM})\s*(\w*W)?\s+({_NUM})\s*(\w*W)?"
    )
    for m in grp_re.finditer(text):
        g = {
            "group": m.group(1),
            "internal": _mw(m.group(2), m.group(3) or None, unit),
            "switching": _mw(m.group(4), m.group(5) or None, unit),
            "leakage": _mw(m.group(6), m.group(7) or None, leak_unit),
            "total": _mw(m.group(8), m.group(9) or None, unit),
        }
        groups.append(g)

    # hierarchy table rows: indented name [ (design) ] then 4 numbers then percent
    hierarchy = []
    in_hier = False
    for line in text.splitlines():
        # the column names (Switch/Int/Leak) may sit on the line above "Hierarchy"
        if re.match(r"^\s*Hierarchy\b", line):
            in_hier = True
            continue
        if not in_hier:
            continue
        m = re.match(
            rf"^(\s*)(\S+)(?:\s+\((\S+)\))?\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})\s*$",
            line,
        )
        if m:
            depth = len(m.group(1).replace("\t", "  ")) // 2
            hierarchy.append(
                {
                    "name": m.group(2),
                    "design": m.group(3) or m.group(2),
                    "depth": depth,
                    "switching": _mw(m.group(4), None, unit),
                    "internal": _mw(m.group(5), None, unit),
                    "leakage": _mw(m.group(6), None, unit),
                    "total": _mw(m.group(7), None, unit),
                    "percent": float(m.group(8)),
                }
            )
        elif hierarchy and line.strip() and not line.strip().startswith("-"):
            in_hier = False
    if hierarchy and hierarchy[0]["depth"]:
        base = hierarchy[0]["depth"]
        for h in hierarchy:
            h["depth"] -= base

    if (
        totals["dynamic"] is None
        and totals["internal"] is not None
        and totals["switching"] is not None
    ):
        totals["dynamic"] = totals["internal"] + totals["switching"]
    if totals["dynamic"] is None and hierarchy:
        totals["internal"] = totals["internal"] or hierarchy[0]["internal"]
        totals["switching"] = totals["switching"] or hierarchy[0]["switching"]
        totals["leakage"] = totals["leakage"] or hierarchy[0]["leakage"]
        totals["dynamic"] = totals["internal"] + totals["switching"]
    totals["total"] = (
        (totals["dynamic"] or 0) + (totals["leakage"] or 0)
        if totals["dynamic"] is not None
        else None
    )
    if totals["total"] is None:
        raise ValueError(
            "Not a recognised power report (expected report_power summary, power groups or hierarchy)"
        )
    design = re.search(r"Design\s*:\s*(\S+)", text)
    return {
        "design": (
            design.group(1) if design else (hierarchy[0]["name"] if hierarchy else None)
        ),
        "unit": "mW",
        "totals": totals,
        "groups": groups,
        "hierarchy": hierarchy,
    }


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_report(f.read())
