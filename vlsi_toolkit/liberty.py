"""Liberty (.lib) standard-cell library parser and explorer.

Liberty is the text format every synthesis/STA tool reads to know each
cell's area, pins, logic function, leakage, and timing (NLDM look-up tables
of delay vs input slew and output load).

    lib = parse_liberty(text)        -> generic Group tree
    info = library_summary(lib)      -> dict with units, cells, pins, arcs, tables

Supports the common subset: groups `name (args) { ... }`, simple attributes
`key : value ;` and complex attributes `key (a, b) ;`, with comments and
line continuations.
"""

import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(
    r'\s+|\\\r?\n|/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[(){}:;,]|[^\s(){}:;,"\\]+|\\',
    re.S,
)


@dataclass
class Group:
    type: str
    args: list
    attrs: dict = field(default_factory=dict)      # simple attributes
    complex: dict = field(default_factory=dict)    # complex attributes: name -> list of arg lists
    groups: list = field(default_factory=list)

    def children(self, gtype):
        return [g for g in self.groups if g.type == gtype]

    def first(self, gtype):
        return next((g for g in self.groups if g.type == gtype), None)


def _tokens(text):
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        if t.isspace() or t.startswith("\\") or t.startswith("/*") or t.startswith("//"):
            continue
        yield t


def _unq(t):
    return t[1:-1] if len(t) >= 2 and t[0] == '"' and t[-1] == '"' else t


def parse_liberty(text):
    toks = list(_tokens(text))
    pos = 0

    def parse_body(group):
        nonlocal pos
        while pos < len(toks) and toks[pos] != "}":
            name = toks[pos]
            pos += 1
            if pos >= len(toks):
                break
            t = toks[pos]
            if t == ":":
                pos += 1
                vals = []
                while pos < len(toks) and toks[pos] not in (";", "}"):
                    vals.append(_unq(toks[pos]))
                    pos += 1
                if pos < len(toks) and toks[pos] == ";":
                    pos += 1
                group.attrs[name] = " ".join(vals)
            elif t == "(":
                pos += 1
                args, cur = [], []
                while pos < len(toks) and toks[pos] != ")":
                    if toks[pos] == ",":
                        args.append(" ".join(cur))
                        cur = []
                    else:
                        cur.append(_unq(toks[pos]))
                    pos += 1
                if cur:
                    args.append(" ".join(cur))
                pos += 1  # ')'
                if pos < len(toks) and toks[pos] == "{":
                    pos += 1
                    child = Group(name, args)
                    parse_body(child)
                    pos += 1  # '}'
                    group.groups.append(child)
                else:
                    if pos < len(toks) and toks[pos] == ";":
                        pos += 1
                    group.complex.setdefault(name, []).append(args)
            elif t == ";":
                pos += 1
            # anything else: skip the stray token

    root = Group("root", [])
    parse_body(root)
    return root.first("library") or root


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------


def _floats(text):
    return [float(x) for x in re.split(r"[\s,]+", text.strip()) if x]


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


_TABLE_TYPES = ("cell_rise", "cell_fall", "rise_transition", "fall_transition",
                "rise_constraint", "fall_constraint")


def _table(group, templates):
    tpl = templates.get(group.args[0] if group.args else "", {})
    idx1 = _floats(group.complex["index_1"][0][0]) if "index_1" in group.complex else tpl.get("index_1", [])
    idx2 = _floats(group.complex["index_2"][0][0]) if "index_2" in group.complex else tpl.get("index_2", [])
    values = [_floats(row) for row in group.complex.get("values", [[]])[0]]
    return {
        "template": group.args[0] if group.args else "",
        "variable_1": tpl.get("variable_1", ""), "variable_2": tpl.get("variable_2", ""),
        "index_1": idx1, "index_2": idx2, "values": values,
    }


_STRENGTH_RE = re.compile(r"^(.*?)(?:_?X|_D|_)(\d+)$", re.I)


def drive_family(cell_name):
    """NAND2_X4 -> ('NAND2', 4);  INVX2 -> ('INV', 2);  FOO -> ('FOO', None)"""
    m = _STRENGTH_RE.match(cell_name)
    return (m.group(1), int(m.group(2))) if m else (cell_name, None)


def library_summary(lib):
    templates = {}
    for t in lib.children("lu_table_template"):
        templates[t.args[0]] = {
            "variable_1": t.attrs.get("variable_1", ""), "variable_2": t.attrs.get("variable_2", ""),
            "index_1": _floats(t.complex["index_1"][0][0]) if "index_1" in t.complex else [],
            "index_2": _floats(t.complex["index_2"][0][0]) if "index_2" in t.complex else [],
        }
    cap_unit = lib.complex.get("capacitive_load_unit", [[]])[0]
    oc = lib.first("operating_conditions")
    cells = []
    for c in lib.children("cell"):
        pins = []
        arcs = []
        for p in c.children("pin"):
            for pin_name in p.args:
                pins.append({
                    "name": pin_name, "direction": p.attrs.get("direction", ""),
                    "capacitance": _num(p.attrs.get("capacitance")),
                    "function": p.attrs.get("function", ""), "clock": p.attrs.get("clock", "") == "true",
                    "max_capacitance": _num(p.attrs.get("max_capacitance")),
                })
                for t in p.children("timing"):
                    arc = {
                        "from": t.attrs.get("related_pin", ""), "to": pin_name,
                        "timing_sense": t.attrs.get("timing_sense", ""),
                        "timing_type": t.attrs.get("timing_type", "combinational"),
                        "tables": {g.type: _table(g, templates) for g in t.groups if g.type in _TABLE_TYPES},
                    }
                    arcs.append(arc)
        family, strength = drive_family(c.args[0])
        delay = _typical_delay(arcs)
        cells.append({
            "name": c.args[0], "family": family, "strength": strength,
            "area": _num(c.attrs.get("area"), 0.0),
            "leakage": _num(c.attrs.get("cell_leakage_power")),
            "footprint": c.attrs.get("cell_footprint", ""),
            "sequential": bool(c.first("ff") or c.first("latch")),
            "kind": "flip-flop" if c.first("ff") else "latch" if c.first("latch") else "combinational",
            "function": next((p["function"] for p in pins if p["direction"] == "output" and p["function"]), ""),
            "inputs": [p["name"] for p in pins if p["direction"] == "input"],
            "outputs": [p["name"] for p in pins if p["direction"] == "output"],
            "pins": pins, "arcs": arcs, "typical_delay": delay,
        })
    return {
        "name": lib.args[0] if lib.args else "?",
        "units": {
            "time": lib.attrs.get("time_unit", ""), "voltage": lib.attrs.get("voltage_unit", ""),
            "leakage_power": lib.attrs.get("leakage_power_unit", ""),
            "capacitive_load": " ".join(cap_unit) if cap_unit else "",
        },
        "operating_conditions": {
            "name": oc.args[0] if oc else "", "process": _num(oc.attrs.get("process")) if oc else None,
            "voltage": _num(oc.attrs.get("voltage") if oc else lib.attrs.get("nom_voltage")),
            "temperature": _num(oc.attrs.get("temperature") if oc else lib.attrs.get("nom_temperature")),
        },
        "templates": templates,
        "cells": cells,
    }


def _typical_delay(arcs):
    """Average of cell_rise/cell_fall at the middle of the table: a quick 'how fast' number."""
    vals = []
    for a in arcs:
        if a["timing_type"] not in ("combinational", "rising_edge", "falling_edge"):
            continue
        for k in ("cell_rise", "cell_fall"):
            t = a["tables"].get(k)
            if t and t["values"] and t["values"][0]:
                rows = t["values"]
                vals.append(rows[len(rows) // 2][len(rows[0]) // 2])
    return sum(vals) / len(vals) if vals else None


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return library_summary(parse_liberty(f.read()))
