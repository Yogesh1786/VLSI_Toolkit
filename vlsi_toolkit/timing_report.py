"""Static Timing Analysis (STA) report analyzer.

Understands the path-report formats of:
  * OpenSTA / OpenROAD   (report_checks)
  * Synopsys PrimeTime   (report_timing)  - same "Startpoint:" layout
  * Xilinx Vivado        (report_timing)  - "Slack (VIOLATED) : -0.12ns" layout

Key terms:
  slack = required time - arrival time.   slack < 0  ->  timing VIOLATED
  WNS   = Worst Negative Slack  (the most negative slack)
  TNS   = Total Negative Slack  (sum of all negative slacks)
  setup check = "max" path,  hold check = "min" path
"""

import csv
import re
from dataclasses import asdict, dataclass

from .common import format_table

_NUM = r"-?\d+(?:\.\d+)?"


@dataclass
class TimingPath:
    startpoint: str
    endpoint: str
    path_group: str = ""
    path_type: str = ""
    arrival: float | None = None
    required: float | None = None
    slack: float | None = None

    @property
    def check(self):
        t = self.path_type.lower()
        if t.startswith("max") or t.startswith("setup"):
            return "setup"
        if t.startswith("min") or t.startswith("hold"):
            return "hold"
        return t or "unknown"

    @property
    def violated(self):
        return self.slack is not None and self.slack < 0


def _first_number_on_line_with(block, phrase):
    for line in block.splitlines():
        if phrase in line:
            nums = re.findall(_NUM, line.replace(phrase, " "))
            if nums:
                return float(nums[0])
    return None


def _field(block, label):
    m = re.search(rf"{label}:\s*(\S+)", block)
    return m.group(1) if m else ""


def _parse_sta_style(text):
    """OpenSTA / PrimeTime: each path starts with 'Startpoint:'."""
    paths = []
    blocks = re.split(r"(?m)^\s*Startpoint:", text)[1:]
    for block in blocks:
        block = "Startpoint:" + block
        slack = None
        m = re.search(rf"(?m)^\s*({_NUM})?\s*slack\s*\((?:MET|VIOLATED)[^)]*\)\s*({_NUM})?", block)
        if m:
            slack = float(m.group(1) if m.group(1) is not None else m.group(2))
        paths.append(
            TimingPath(
                startpoint=_field(block, "Startpoint"),
                endpoint=_field(block, "Endpoint"),
                path_group=_field(block, "Path Group"),
                path_type=_field(block, "Path Type"),
                arrival=_first_number_on_line_with(block, "data arrival time"),
                required=_first_number_on_line_with(block, "data required time"),
                slack=slack,
            )
        )
    return paths


def _parse_vivado_style(text):
    """Vivado: each path starts with 'Slack (MET) :' or 'Slack (VIOLATED) :'."""
    paths = []
    blocks = re.split(r"(?m)^\s*(?=Slack\s*\()", text)
    for block in blocks:
        m = re.match(rf"\s*Slack\s*\((?:MET|VIOLATED)\)\s*:\s*({_NUM})", block)
        if not m:
            continue
        paths.append(
            TimingPath(
                startpoint=_field(block, "Source"),
                endpoint=_field(block, "Destination"),
                path_group=_field(block, "Path Group"),
                path_type=_field(block, "Path Type"),
                slack=float(m.group(1)),
            )
        )
    return paths


def parse_report(text):
    if re.search(r"(?m)^\s*Startpoint:", text):
        return _parse_sta_style(text)
    return _parse_vivado_style(text)


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_report(f.read())


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


def summarize(paths):
    """Per check type (setup/hold): path count, violations, WNS, TNS."""
    summary = {}
    for check in sorted({p.check for p in paths}):
        group = [p for p in paths if p.check == check and p.slack is not None]
        slacks = [p.slack for p in group]
        summary[check] = {
            "paths": len(group),
            "violations": sum(1 for s in slacks if s < 0),
            "wns": min(slacks) if slacks else None,
            "tns": round(sum(s for s in slacks if s < 0), 4),
        }
    return summary


def ascii_histogram(values, bins=10, width=40):
    """Text histogram, so you can see the slack spread without matplotlib."""
    if not values:
        return "(no data)"
    lo, hi = min(values), max(values)
    if lo == hi:
        hi = lo + 1e-9
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        counts[min(int((v - lo) / step), bins - 1)] += 1
    peak = max(counts)
    lines = []
    for i, c in enumerate(counts):
        a, b = lo + i * step, lo + (i + 1) * step
        bar = "#" * round(c / peak * width) if peak else ""
        flag = "  <-- includes negative slack" if a < 0 else ""
        lines.append(f"{a:8.3f} .. {b:8.3f} | {bar} {c}{flag}")
    return "\n".join(lines)


def report_text(paths, top=10):
    """Full human-readable analysis."""
    if not paths:
        return "No timing paths found. Is this an OpenSTA/PrimeTime/Vivado path report?"
    out = []
    summary = summarize(paths)
    rows = [
        [check, s["paths"], s["violations"], f"{s['wns']:.3f}" if s["wns"] is not None else "-", f"{s['tns']:.3f}",
         "FAIL" if s["violations"] else "PASS"]
        for check, s in summary.items()
    ]
    out.append("TIMING SUMMARY")
    out.append(format_table(["Check", "Paths", "Violations", "WNS", "TNS", "Status"], rows))

    worst = sorted((p for p in paths if p.slack is not None), key=lambda p: p.slack)[:top]
    out.append("")
    out.append(f"WORST {len(worst)} PATHS")
    out.append(
        format_table(
            ["#", "Check", "Slack", "Startpoint", "Endpoint", "Group"],
            [[i + 1, p.check, f"{p.slack:.3f}", p.startpoint, p.endpoint, p.path_group] for i, p in enumerate(worst)],
        )
    )

    violators = {}
    for p in paths:
        if p.violated:
            violators[p.endpoint] = violators.get(p.endpoint, 0) + 1
    if violators:
        out.append("")
        out.append("ENDPOINTS WITH MOST VIOLATIONS")
        top_ep = sorted(violators.items(), key=lambda kv: -kv[1])[:top]
        out.append(format_table(["Endpoint", "Violating paths"], top_ep))

    out.append("")
    out.append("SLACK HISTOGRAM")
    out.append(ascii_histogram([p.slack for p in paths if p.slack is not None]))
    return "\n".join(out)


def write_csv(paths, csv_path):
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["check", "startpoint", "endpoint", "path_group", "path_type", "arrival", "required", "slack", "status"])
        for p in paths:
            writer.writerow([p.check, p.startpoint, p.endpoint, p.path_group, p.path_type,
                             p.arrival, p.required, p.slack, "VIOLATED" if p.violated else "MET"])


def plot_histogram(paths, png_path):
    """Save a slack histogram PNG. Needs matplotlib (pip install matplotlib)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for check, color in (("setup", "#3b6fd6"), ("hold", "#d98a1c")):
        slacks = [p.slack for p in paths if p.check == check and p.slack is not None]
        if slacks:
            ax.hist(slacks, bins=20, alpha=0.75, label=f"{check} ({len(slacks)} paths)", color=color)
    ax.axvline(0, color="#c0392b", linestyle="--", linewidth=1.5, label="slack = 0")
    ax.set_xlabel("Slack (ns)")
    ax.set_ylabel("Number of paths")
    ax.set_title("Timing slack distribution")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path, dpi=120)
    plt.close(fig)


def to_dicts(paths):
    return [dict(asdict(p), check=p.check, violated=p.violated) for p in paths]
