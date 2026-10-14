"""Analog / SPICE helpers.

  netlist_report()  - device summary, MOSFET W/L table, sub-circuits and
                      connectivity checks (floating nodes, floating gates)
  make_sweep()      - generate one netlist per value of a .param (corner /
                      supply / sizing sweeps), optionally run ngspice on each
                      and collect the .meas results into one table
  measure()         - read waveform data (CSV or ngspice 'wrdata' output) and
                      measure rise/fall time, propagation delay, frequency,
                      duty cycle, overshoot/undershoot

Values understand SPICE suffixes: f p n u m k meg g t (e.g. 0.42u, 10f, 1.8).
"""

import ast
import csv
import operator
import re
import shutil
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .common import format_table

# ---------------------------------------------------------------------------
# Numbers with SPICE suffixes
# ---------------------------------------------------------------------------

_SUFFIX = [("meg", 1e6), ("mil", 25.4e-6), ("t", 1e12), ("g", 1e9), ("k", 1e3), ("m", 1e-3),
           ("u", 1e-6), ("n", 1e-9), ("p", 1e-12), ("f", 1e-15), ("a", 1e-18)]
_NUM_RE = re.compile(r"(?<![\w.])([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)([a-z]*)", re.I)
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _suffix_scale(suffix):
    s = suffix.lower()
    for k, v in _SUFFIX:
        if s.startswith(k):
            return v
    return 1.0  # plain number or unit only, e.g. "1.8v"


def _eval_float(node, params):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_float(node.left, params), _eval_float(node.right, params))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_float(node.operand, params))
    if isinstance(node, ast.Name) and node.id.lower() in params:
        return params[node.id.lower()]
    raise ValueError("unsupported")


def spice_value(text, params=None):
    """'0.42u' -> 4.2e-07 ;  '{WN*2}' -> evaluated with .param values ;  None if unknown."""
    s = text.strip().strip("{}'\"").strip()
    m = _NUM_RE.fullmatch(s)
    if m:
        return float(m.group(1)) * _suffix_scale(m.group(2))
    expr = _NUM_RE.sub(lambda mm: repr(float(mm.group(1)) * _suffix_scale(mm.group(2))), s)
    try:
        return _eval_float(ast.parse(expr, mode="eval").body, params or {})
    except (ValueError, SyntaxError, ZeroDivisionError, TypeError):
        return None


def eng(value, unit=""):
    """1.23e-11 -> '12.3 p' + unit"""
    if value is None:
        return "-"
    for exp, prefix in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f")):
        if abs(value) >= exp:
            return f"{value / exp:.4g} {prefix}{unit}"
    return f"{value:.3g} {unit}"


# ---------------------------------------------------------------------------
# Netlist parsing
# ---------------------------------------------------------------------------

DEVICE_NAMES = {"m": "MOSFET", "r": "Resistor", "c": "Capacitor", "l": "Inductor", "v": "Voltage source",
                "i": "Current source", "d": "Diode", "q": "BJT", "j": "JFET", "x": "Subckt instance",
                "e": "VCVS", "g": "VCCS", "f": "CCCS", "h": "CCVS", "b": "Behavioral source", "k": "Coupling"}
_NODE_COUNT = {"m": 4, "r": 2, "c": 2, "l": 2, "v": 2, "i": 2, "d": 2, "q": 3, "j": 3, "e": 4, "g": 4,
               "f": 2, "h": 2, "b": 2, "k": 0}
GROUND = {"0", "gnd", "gnd!"}


@dataclass
class Device:
    name: str
    kind: str  # first letter, lower case
    nodes: list
    model: str
    params: dict
    scope: str  # "" = top level, else sub-circuit name


@dataclass
class Subckt:
    name: str
    pins: list


@dataclass
class Netlist:
    title: str = ""
    devices: list = field(default_factory=list)
    subckts: dict = field(default_factory=dict)
    params: dict = field(default_factory=dict)
    analyses: list = field(default_factory=list)
    measures: list = field(default_factory=list)
    includes: list = field(default_factory=list)


def _logical_lines(text):
    """Join '+' continuation lines and drop comments."""
    lines = []
    for raw in text.splitlines():
        line = re.split(r"\s;|\s\$\s|^\s*\$", raw)[0].rstrip()  # inline comments
        s = line.strip()
        if not s or s.startswith("*"):
            continue
        if s.startswith("+") and lines:
            lines[-1] += " " + s[1:].strip()
        else:
            lines.append(s)
    return lines


def parse_netlist(text):
    nl = Netlist()
    raw_lines = text.splitlines()
    nl.title = raw_lines[0].strip() if raw_lines else ""
    scope = ""
    in_control = False
    # SPICE rule: the first line is always the title
    for line in _logical_lines("\n".join(raw_lines[1:])):
        line = re.sub(r"\s*=\s*", "=", line)
        tok = line.split()
        head = tok[0].lower()
        # .control ... .endc holds ngspice commands (run, plot, wrdata), not devices
        if head == ".control":
            in_control = True
            continue
        if head == ".endc":
            in_control = False
            continue
        if in_control:
            continue
        if head.startswith("."):
            if head == ".subckt" and len(tok) > 1:
                pins = [t for t in tok[2:] if "=" not in t and t.lower() != "params:"]
                nl.subckts[tok[1].lower()] = Subckt(tok[1].lower(), [p.lower() for p in pins])
                scope = tok[1].lower()
            elif head == ".ends":
                scope = ""
            elif head == ".param":
                for item in re.findall(r"(\w+)=(\{[^}]*\}|'[^']*'|\S+)", line[len(tok[0]):]):
                    v = spice_value(item[1], nl.params)
                    if v is not None:
                        nl.params[item[0].lower()] = v
            elif head in (".tran", ".dc", ".ac", ".op", ".noise", ".tf", ".pz", ".sens"):
                nl.analyses.append(line)
            elif head in (".meas", ".measure") and len(tok) > 2:
                nl.measures.append(tok[2].lower())
            elif head in (".include", ".inc", ".lib"):
                nl.includes.append(line)
            continue

        kind = head[0]
        if kind not in DEVICE_NAMES:
            continue
        params = {}
        plain = []
        for t in tok[1:]:
            if "=" in t:
                k, v = t.split("=", 1)
                params[k.lower()] = v
            else:
                plain.append(t)
        if kind == "x":
            nodes, model = plain[:-1], plain[-1] if plain else ""
        else:
            n = _NODE_COUNT.get(kind, 2)
            nodes = plain[:n]
            model = plain[n] if len(plain) > n else ""
        nl.devices.append(Device(tok[0], kind, [x.lower() for x in nodes], model, params, scope))
    return nl


def parse_netlist_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_netlist(f.read())


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def connectivity_issues(nl):
    """Find nodes touched by only one terminal, and gate-only (undriven) nodes."""
    issues = []
    scopes = {d.scope for d in nl.devices}
    for scope in sorted(scopes):
        pins = set(nl.subckts[scope].pins) if scope in nl.subckts else set()
        roles = {}  # node -> list of terminal roles
        for d in nl.devices:
            if d.scope != scope:
                continue
            for i, node in enumerate(d.nodes):
                role = "gate" if d.kind == "m" and i == 1 else "other"
                roles.setdefault(node, []).append(role)
        where = f"subckt {scope}" if scope else "top level"
        for node, r in sorted(roles.items()):
            if node in GROUND or node in pins:
                continue
            if len(r) == 1:
                issues.append(f"[{where}] node '{node}' connects to only one device terminal (floating?)")
            elif all(x == "gate" for x in r):
                issues.append(f"[{where}] node '{node}' only drives MOSFET gates - nothing drives it (floating gate)")
    if not nl.analyses:
        issues.append("no analysis statement (.tran/.dc/.ac/.op) found")
    return issues


def mosfet_table(nl):
    rows = []
    for d in nl.devices:
        if d.kind != "m":
            continue
        w = spice_value(d.params.get("w", ""), nl.params) if "w" in d.params else None
        length = spice_value(d.params.get("l", ""), nl.params) if "l" in d.params else None
        nf = d.params.get("nf", "1")
        mult = d.params.get("m", "1")
        rows.append({
            "name": d.name, "scope": d.scope or "top", "model": d.model,
            "d": d.nodes[0] if d.nodes else "", "g": d.nodes[1] if len(d.nodes) > 1 else "",
            "s": d.nodes[2] if len(d.nodes) > 2 else "", "b": d.nodes[3] if len(d.nodes) > 3 else "",
            "w": w, "l": length, "w_over_l": (w / length) if w and length else None, "nf": nf, "m": mult,
        })
    return rows


def netlist_report(nl):
    out = [f"Title: {nl.title}"]
    if nl.params:
        out.append("Parameters: " + ", ".join(f"{k}={eng(v).strip()}" for k, v in nl.params.items()))
    if nl.includes:
        out.append("Includes: " + " | ".join(nl.includes))
    out.append("Analyses: " + (" | ".join(nl.analyses) or "none"))
    if nl.measures:
        out.append("Measurements: " + ", ".join(nl.measures))

    counts = {}
    for d in nl.devices:
        counts[(d.scope or "top", DEVICE_NAMES[d.kind])] = counts.get((d.scope or "top", DEVICE_NAMES[d.kind]), 0) + 1
    out.append("")
    out.append("DEVICES")
    out.append(format_table(["Scope", "Type", "Count"], [[s, t, c] for (s, t), c in sorted(counts.items())]))

    if nl.subckts:
        out.append("")
        out.append("SUB-CIRCUITS")
        inst = {}
        for d in nl.devices:
            if d.kind == "x":
                inst[d.model.lower()] = inst.get(d.model.lower(), 0) + 1
        out.append(format_table(["Name", "Pins", "Devices inside", "Instances"],
                                [[s.name, " ".join(s.pins), sum(1 for d in nl.devices if d.scope == s.name), inst.get(s.name, 0)]
                                 for s in nl.subckts.values()]))

    mos = mosfet_table(nl)
    if mos:
        out.append("")
        out.append("MOSFETS")
        out.append(format_table(
            ["Name", "Scope", "Model", "D G S B", "W", "L", "W/L", "nf", "m"],
            [[r["name"], r["scope"], r["model"], f"{r['d']} {r['g']} {r['s']} {r['b']}",
              eng(r["w"], "m"), eng(r["l"], "m"), f"{r['w_over_l']:.2f}" if r["w_over_l"] else "-", r["nf"], r["m"]]
             for r in mos],
        ))

    issues = connectivity_issues(nl)
    out.append("")
    out.append("CHECKS")
    out += [f"  WARNING: {i}" for i in issues] or ["  No connectivity issues found."]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Parameter sweep
# ---------------------------------------------------------------------------


def parse_sweep_values(spec):
    """'1.6:2.0:0.1' (start:stop:step, inclusive) or '1.6,1.8,2.0' -> list of strings."""
    if ":" in spec:
        start, stop, step = (spice_value(x) for x in spec.split(":"))
        if not step or step <= 0:
            raise ValueError("sweep step must be > 0")
        vals, i = [], 0
        while start + i * step <= stop + step * 1e-9:
            vals.append(f"{start + i * step:.6g}")
            i += 1
        return vals
    return [v.strip() for v in spec.split(",") if v.strip()]


def make_sweep(text, param, values):
    """Return [(value, netlist_text)] with .param <param> replaced by each value."""
    pattern = re.compile(rf"(?im)^(\s*\.param\b[^\n]*?\b{re.escape(param)}\s*=\s*)(\{{[^}}]*\}}|'[^']*'|\S+)")
    out = []
    for v in values:
        if pattern.search(text):
            new = pattern.sub(lambda m: m.group(1) + v, text, count=1)
        else:  # parameter not defined yet: add it right after the title line
            title, _, rest = text.partition("\n")
            new = f"{title}\n.param {param}={v}\n{rest}"
        out.append((v, new))
    return out


def find_ngspice():
    return shutil.which("ngspice_con") or shutil.which("ngspice")


def run_ngspice(netlist_path, timeout=300):
    exe = find_ngspice()
    if not exe:
        raise FileNotFoundError("ngspice not found on PATH")
    res = subprocess.run([exe, "-b", str(netlist_path)], capture_output=True, text=True, timeout=timeout)
    return res.stdout + res.stderr


def parse_measurements(output, names):
    """Pick 'name = value' lines that ngspice prints for each .meas."""
    found = {}
    for name in names:
        m = re.search(rf"(?im)^\s*{re.escape(name)}\s*=\s*([-+]?\d[\d.]*(?:e[-+]?\d+)?)", output)
        found[name] = float(m.group(1)) if m else None
    return found


def run_sweep(netlist_path, param, spec, out_dir, run=False):
    text = Path(netlist_path).read_text(encoding="utf-8", errors="replace")
    nl = parse_netlist(text)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for value, new_text in make_sweep(text, param, parse_sweep_values(spec)):
        path = out_dir / f"{Path(netlist_path).stem}_{param}_{value}.sp"
        path.write_text(new_text, encoding="utf-8")
        row = {"value": value, "netlist": str(path)}
        if run:
            output = run_ngspice(path)
            (path.with_suffix(".log")).write_text(output, encoding="utf-8")
            row.update(parse_measurements(output, nl.measures))
        results.append(row)
    return nl, results


# ---------------------------------------------------------------------------
# Waveform measurements
# ---------------------------------------------------------------------------


def load_waveforms(path):
    """Read a waveform file. See parse_waveforms()."""
    return parse_waveforms(Path(path).read_text(encoding="utf-8", errors="replace"))


def parse_waveforms(text):
    """CSV (with header) or whitespace columns (ngspice wrdata) -> {name: [values]}; first column is time."""
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l and not l.startswith(("#", "*"))]
    if not lines:
        raise ValueError("waveform file is empty")
    delim = "," if "," in lines[0] else None
    rows = [next(csv.reader([l])) if delim else l.split() for l in lines]
    rows = [[c.strip() for c in r] for r in rows]
    first_is_header = spice_value(rows[0][0]) is None
    header = rows[0] if first_is_header else [("time" if i == 0 else f"col{i}") for i in range(len(rows[0]))]
    data_rows = rows[1:] if first_is_header else rows
    try:
        cols = list(zip(*[[float(c) for c in r] for r in data_rows if len(r) == len(header)]))
    except ValueError as exc:
        raise ValueError(f"non-numeric value in the data rows ({exc})") from exc
    waves = {}
    for name, col in zip(header, cols):
        # ngspice wrdata repeats the time column before every vector: drop the copies
        if waves and list(col) == waves[header[0]]:
            continue
        key = name if name not in waves else f"{name}_{len(waves)}"
        waves[key] = list(col)
    return waves


def find_wave(waves, name):
    for key in (name, f"v({name})", f"V({name})"):
        if key in waves:
            return key
    low = {k.lower(): k for k in waves}
    for key in (name.lower(), f"v({name.lower()})"):
        if key in low:
            return low[key]
    raise ValueError(f"signal '{name}' not found; available: {', '.join(waves)}")


def crossings(t, y, level, direction):
    """Times where y crosses `level` going 'rise' or 'fall' (linear interpolation)."""
    out = []
    for i in range(len(y) - 1):
        a, b = y[i], y[i + 1]
        if (direction == "rise" and a < level <= b) or (direction == "fall" and a > level >= b):
            out.append(t[i] + (level - a) * (t[i + 1] - t[i]) / (b - a))
    return out


def _transition_times(t, y, lo, hi, direction):
    """10-90 % rise (or 90-10 % fall) time of each edge."""
    lvl_a, lvl_b = (lo, hi) if direction == "rise" else (hi, lo)
    starts = crossings(t, y, lvl_a, direction)
    ends = crossings(t, y, lvl_b, direction)
    times, prev_end = [], float("-inf")
    for e in ends:
        cands = [s for s in starts if prev_end < s <= e]
        if cands:
            times.append(e - cands[-1])
        prev_end = e
    return times


def measure(waves, signal, ref=None, vdd=None):
    """Return a dict of measurements for `signal` (optionally relative to `ref`)."""
    tkey = next(iter(waves))
    t = waves[tkey]
    y = waves[find_wave(waves, signal)]
    vmin, vmax = min(y), max(y)
    low, high = (0.0, vdd) if vdd else (vmin, vmax)
    swing = high - low
    res = {"vmin": vmin, "vmax": vmax}
    if swing <= 0:
        return res
    mid = low + 0.5 * swing
    rises = _transition_times(t, y, low + 0.1 * swing, low + 0.9 * swing, "rise")
    falls = _transition_times(t, y, low + 0.1 * swing, low + 0.9 * swing, "fall")
    res["rise_time"] = statistics.mean(rises) if rises else None
    res["fall_time"] = statistics.mean(falls) if falls else None
    r50 = crossings(t, y, mid, "rise")
    f50 = crossings(t, y, mid, "fall")
    if len(r50) >= 2:
        period = statistics.median([b - a for a, b in zip(r50, r50[1:])])
        res["period"] = period
        res["frequency"] = 1 / period if period else None
        highs = [next((f for f in f50 if f > r), None) for r in r50]
        highs = [f - r for f, r in zip(highs, r50) if f is not None]
        res["duty"] = statistics.median(highs) / period if highs and period else None
    if vdd:
        res["overshoot_pct"] = max(0.0, vmax - vdd) / vdd * 100
        res["undershoot_pct"] = max(0.0, -vmin) / vdd * 100
    if ref:
        ry = waves[find_wave(waves, ref)]
        rlo, rhi = (0.0, vdd) if vdd else (min(ry), max(ry))
        rmid = rlo + 0.5 * (rhi - rlo)
        ref_edges = sorted(crossings(t, ry, rmid, "rise") + crossings(t, ry, rmid, "fall"))

        def delays(out_edges):
            ds = []
            for e in out_edges:
                before = [r for r in ref_edges if r <= e]
                if before:
                    ds.append(e - before[-1])
            return ds

        lh, hl = delays(r50), delays(f50)
        res["tpLH"] = statistics.mean(lh) if lh else None
        res["tpHL"] = statistics.mean(hl) if hl else None
        both = [x for x in (res["tpLH"], res["tpHL"]) if x is not None]
        res["tpd"] = statistics.mean(both) if both else None
    return res


MEAS_LABELS = [
    ("vmin", "Minimum voltage", "V"), ("vmax", "Maximum voltage", "V"),
    ("rise_time", "Rise time (10-90%)", "s"), ("fall_time", "Fall time (90-10%)", "s"),
    ("tpLH", "Prop. delay, output rising (tpLH)", "s"), ("tpHL", "Prop. delay, output falling (tpHL)", "s"),
    ("tpd", "Average propagation delay (tpd)", "s"), ("period", "Period", "s"), ("frequency", "Frequency", "Hz"),
]


def measure_report(res, signal, ref=None):
    rows = [[label, eng(res[k], unit)] for k, label, unit in MEAS_LABELS if k in res]
    if res.get("duty") is not None:
        rows.append(["Duty cycle", f"{res['duty']:.1%}"])
    for k, label in (("overshoot_pct", "Overshoot"), ("undershoot_pct", "Undershoot")):
        if k in res:
            rows.append([label, f"{res[k]:.2f} % of VDD"])
    title = f"MEASUREMENTS for '{signal}'" + (f" (delay reference: '{ref}')" if ref else "")
    return title + "\n" + format_table(["Measurement", "Value"], rows)
