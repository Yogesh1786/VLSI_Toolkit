"""VCD (Value Change Dump) waveform analyzer.

A .vcd file is what simulators write when a testbench calls $dumpfile /
$dumpvars. This tool reads it without any GUI and reports, per signal:

  * toggle count        - activity, useful for power estimation
  * final value
  * clock detection     - period, frequency and duty cycle of regular signals
  * glitches            - pulses narrower than a threshold
  * X / Z values        - unknown/undriven values after a given time
                          (often a missing reset or a multiply-driven net)
"""

import statistics
from dataclasses import dataclass, field

from .common import format_table

_UNIT_SECONDS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}


@dataclass
class Signal:
    name: str
    width: int
    var_type: str
    changes: list = field(default_factory=list)  # [(time, value_string)]


@dataclass
class VCD:
    timescale_s: float = 1e-9
    timescale_text: str = "1ns"
    signals: dict = field(default_factory=dict)  # full name -> Signal
    end_time: int = 0


def _parse_timescale(text):
    text = text.replace(" ", "")
    num = "".join(ch for ch in text if ch.isdigit()) or "1"
    unit = text[len(num):] or "ns"
    return int(num) * _UNIT_SECONDS.get(unit, 1e-9), f"{num}{unit}"


def parse_text(text):
    vcd = VCD()
    by_id = {}  # id code -> [Signal, ...] (several names may share one id)
    scope = []
    tokens = iter(text.split())
    time = 0

    def until_end():
        collected = []
        for t in tokens:
            if t == "$end":
                break
            collected.append(t)
        return collected

    def record(code, value):
        for sig in by_id.get(code, ()):
            if not sig.changes or sig.changes[-1][1] != value:
                sig.changes.append((time, value))

    for tok in tokens:
        if tok == "$timescale":
            vcd.timescale_s, vcd.timescale_text = _parse_timescale("".join(until_end()))
        elif tok == "$scope":
            parts = until_end()
            scope.append(parts[1] if len(parts) > 1 else "?")
        elif tok == "$upscope":
            until_end()
            if scope:
                scope.pop()
        elif tok == "$var":
            parts = until_end()  # type size id ref [range]
            if len(parts) >= 4:
                var_type, size, code, ref = parts[0], int(parts[1]), parts[2], parts[3]
                name = ".".join(scope + [ref])
                sig = Signal(name, size, var_type)
                vcd.signals[name] = sig
                by_id.setdefault(code, []).append(sig)
        elif tok in ("$comment", "$date", "$version", "$enddefinitions"):
            until_end()
        elif tok in ("$dumpvars", "$dumpall", "$dumpon", "$dumpoff", "$end"):
            continue
        elif tok.startswith("#"):
            time = int(tok[1:])
            vcd.end_time = max(vcd.end_time, time)
        elif tok[0] in "bBrR":
            value = tok[1:].lower()
            record(next(tokens), value)
        elif tok[0] in "01xXzZ":
            record(tok[1:], tok[0].lower())
    return vcd


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_text(f.read())


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


@dataclass
class SignalStats:
    name: str
    width: int
    toggles: int
    final: str
    period: float | None = None  # in VCD time units
    duty: float | None = None
    glitches: int = 0
    x_after: int | None = None  # first time an X/Z is seen after the check time


def _clock_info(changes):
    """Return (period, duty) if a 1-bit signal toggles regularly, else (None, None)."""
    rises = [t for t, v in changes if v == "1"]
    falls = [t for t, v in changes if v == "0"]
    if len(rises) < 3:
        return None, None
    periods = [b - a for a, b in zip(rises, rises[1:])]
    med = statistics.median(periods)
    if med <= 0 or any(abs(p - med) > 0.01 * med for p in periods):
        return None, None
    highs = []
    for r in rises:
        nxt = next((f for f in falls if f > r), None)
        if nxt is not None:
            highs.append(nxt - r)
    duty = statistics.median(highs) / med if highs else None
    return med, duty


def analyze(vcd, glitch_threshold=1, x_check_after=None):
    """Compute SignalStats for every signal.

    glitch_threshold : pulses shorter than this many time units count as glitches
    x_check_after    : report X/Z values seen after this time (default: 10% of sim)
    """
    if x_check_after is None:
        x_check_after = vcd.end_time // 10
    stats = []
    for sig in vcd.signals.values():
        ch = sig.changes
        st = SignalStats(sig.name, sig.width, max(len(ch) - 1, 0), ch[-1][1] if ch else "?")
        if sig.width == 1 and sig.var_type != "real":
            st.period, st.duty = _clock_info(ch)
            if st.period is None:
                # a glitch = value changes and changes back within the threshold
                for (t0, _), (t1, _) in zip(ch[1:], ch[2:]):
                    if 0 < t1 - t0 < glitch_threshold:
                        st.glitches += 1
        # flag any X/Z value that is still present after x_check_after
        for i, (t, v) in enumerate(ch):
            next_t = ch[i + 1][0] if i + 1 < len(ch) else vcd.end_time + 1
            if any(c in v for c in "xz") and next_t > x_check_after:
                st.x_after = max(t, x_check_after)
                break
        stats.append(st)
    return stats


def freq_text(period, timescale_s):
    hz = 1.0 / (period * timescale_s)
    for unit, scale in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
        if hz >= scale:
            return f"{hz / scale:.3g} {unit}"
    return f"{hz:.3g} Hz"


def short_value(value, width):
    if width == 1 or any(c in value for c in "xz") or not value or not set(value) <= {"0", "1"}:
        return value
    return f"0x{int(value, 2):X}"


def report_text(vcd, stats):
    out = [
        f"Timescale: {vcd.timescale_text}   Simulation end: {vcd.end_time} "
        f"({vcd.end_time * vcd.timescale_s * 1e9:.4g} ns)   Signals: {len(stats)}"
    ]
    rows = []
    for s in sorted(stats, key=lambda s: s.name):
        clock = ""
        if s.period:
            clock = f"{freq_text(s.period, vcd.timescale_s)}, duty {s.duty:.0%}" if s.duty else freq_text(s.period, vcd.timescale_s)
        rows.append([s.name, s.width, s.toggles, short_value(s.final, s.width), clock,
                     s.glitches or "", "" if s.x_after is None else f"X/Z @ {s.x_after}"])
    out.append(format_table(["Signal", "Width", "Toggles", "Final", "Clock", "Glitches", "Unknowns"], rows))

    issues = [s for s in stats if s.glitches or s.x_after is not None]
    idle = [s for s in stats if s.toggles == 0]
    if issues:
        out.append("")
        out.append("ISSUES")
        for s in issues:
            if s.glitches:
                out.append(f"  - {s.name}: {s.glitches} glitch(es) narrower than threshold")
            if s.x_after is not None:
                out.append(f"  - {s.name}: X/Z value still present at time {s.x_after} (missing reset or undriven net?)")
    if idle:
        out.append("")
        out.append("NEVER TOGGLED (check if stimulus reaches them): " + ", ".join(s.name for s in idle))
    return "\n".join(out)
