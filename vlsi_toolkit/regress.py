"""Regression log analyzer - summarize hundreds of simulation logs in seconds.

Point it at a folder of logs (one per test) and it reports:
  * PASS / FAIL / INCOMPLETE per test (INCOMPLETE = crashed or timed out:
    no end-of-simulation marker found)
  * error / fatal / warning counts, test name and seed
  * the first error message of every failing test
  * FAILURE SIGNATURES: failing tests grouped by their first error, with
    numbers/times/paths removed - 50 failures often turn out to be 2 bugs

Recognised message styles: UVM (UVM_ERROR/UVM_FATAL + report summary),
Questa (** Error), Xcelium (*E,), VCS (Error-[...]) and plain
$display / $error "ERROR:" messages.
"""

import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path

from .common import format_table

_ERROR_RES = [
    re.compile(r"^\s*UVM_(ERROR|FATAL)\b(?!\s*:\s*\d)"),  # UVM message (not the summary)
    re.compile(r"^\s*#?\s*\*\*\s*(Error|Fatal)\b"),  # Questa / ModelSim ("# ** Error")
    re.compile(r"^\s*\*([EF]),\w+"),  # Xcelium
    re.compile(r"^\s*(Error|Fatal)-\["),  # VCS
    re.compile(r"\b(ERROR|FATAL)\b\s*[:\-\]]"),  # $error / $display("ERROR: ...")
    re.compile(r"^\s*(Error|Fatal):"),
]
_WARNING_RE = re.compile(r"^\s*#?\s*(UVM_WARNING\b(?!\s*:\s*\d)|\*\*\s*Warning\b|\*W,\w+|Warning-\[|WARNING\s*:)")
_UVM_SUMMARY_RE = re.compile(r"^\s*UVM_(ERROR|FATAL|WARNING)\s*:\s*(\d+)", re.M)
_PASS_RE = re.compile(r"\bTEST\s*(?:CASE\s*)?PASS(?:ED)?\b", re.I)
_FAIL_RE = re.compile(r"\bTEST\s*(?:CASE\s*)?FAIL(?:ED)?\b", re.I)
_DONE_RE = re.compile(
    r"\$finish|UVM Report Summary|Simulation complete|End of simulation|TEST DONE|"
    r"Simulation\s+(?:stopped|ended)|V C S\s+S i m u l a t i o n",
    re.I,
)
_TESTNAME_RES = [re.compile(r"\+UVM_TESTNAME=(\w+)"), re.compile(r"Running test\s+(\w+)")]
_SEED_RE = re.compile(r"(?:sv_seed|ntb_random_seed|svseed|\bseed)\s*[=:]?\s*(\d+)", re.I)


@dataclass
class TestResult:
    file: str
    test: str
    seed: str
    status: str
    errors: int
    fatals: int
    warnings: int
    first_error: str

    @property
    def signature(self):
        if self.status == "INCOMPLETE" and not (self.errors or self.fatals):
            return "(incomplete: no end-of-simulation marker - crash, kill or timeout?)"
        return error_signature(self.first_error) if self.first_error else ""

    @property
    def short_error(self):
        """First error without the file(line) prefix, for display."""
        return re.sub(r"\S*[/\\]\S*\(\d+\):?\s*", "", self.first_error)


def error_signature(message):
    """Normalize an error message so that the same bug gives the same text."""
    s = message.strip()
    s = re.sub(r"^\s*#?\s*(UVM_(ERROR|FATAL)|\*\*\s*(Error|Fatal):?|\*[EF],\w+:?|(ERROR|FATAL|Error|Fatal)\s*:?)\s*", "", s)
    s = re.sub(r"\S*[/\\]\S*\(\d+\)", "", s)  # file.sv(123)
    s = re.sub(r"@\s*[\d.]+\s*\w*:?", "", s)  # @ 1500ns:
    s = re.sub(r"\buvm_test_top(\.\w+)*", "<path>", s)
    s = re.sub(r"0x[0-9a-fA-F_]+|\d*'[sS]?[hHdDbBoO][0-9a-fA-FxXzZ_]+", "<val>", s)
    s = re.sub(r"\b\d+(\.\d+)?\w*", "<n>", s)
    s = " ".join(s.split()).lstrip(": ")
    return s[:110]


def analyze_log(path):
    path = Path(path)
    return analyze_text(path.read_text(encoding="utf-8", errors="replace"), str(path))


def analyze_text(text, name="log"):
    """Analyze the text of one simulation log. `name` is the file name (used as test name fallback)."""
    errors = fatals = warnings = 0
    first_error = ""
    for line in text.splitlines():
        for rx in _ERROR_RES:
            m = rx.search(line)
            if m:
                if m.group(1)[0].upper() == "F":  # FATAL / Fatal / *F
                    fatals += 1
                else:
                    errors += 1
                if not first_error:
                    first_error = line.strip()
                break
        else:
            if _WARNING_RE.search(line):
                warnings += 1

    # The UVM report summary is the most reliable count when it exists
    summary = {k: int(v) for k, v in _UVM_SUMMARY_RE.findall(text)}
    if summary:
        errors = summary.get("ERROR", errors)
        fatals = summary.get("FATAL", fatals)
        warnings = summary.get("WARNING", warnings)

    test = Path(name).stem
    for rx in _TESTNAME_RES:
        m = rx.search(text)
        if m:
            test = m.group(1)
            break
    seed_m = _SEED_RE.search(text)

    finished = bool(_DONE_RE.search(text) or _PASS_RE.search(text) or _FAIL_RE.search(text))
    if errors or fatals or _FAIL_RE.search(text):
        status = "FAIL"
    elif not finished:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    if status == "INCOMPLETE" and not first_error:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        first_error = "no end-of-simulation marker; last line: " + (lines[-1][:80] if lines else "<empty log>")
    return TestResult(name, test, seed_m.group(1) if seed_m else "", status, errors, fatals, warnings, first_error)


def analyze_folder(folder, pattern="*.log"):
    folder = Path(folder)
    files = [folder] if folder.is_file() else sorted(folder.rglob(pattern))
    return [analyze_log(f) for f in files]


def signatures(results):
    """{signature: [TestResult, ...]} for non-passing tests, most common first."""
    groups = {}
    for r in results:
        if r.status != "PASS":
            groups.setdefault(r.signature or "(no error message)", []).append(r)
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))


def report_text(results):
    if not results:
        return "No log files found."
    n = len(results)
    counts = {s: sum(1 for r in results if r.status == s) for s in ("PASS", "FAIL", "INCOMPLETE")}
    out = [
        f"REGRESSION SUMMARY: {n} tests   PASS {counts['PASS']}   FAIL {counts['FAIL']}   "
        f"INCOMPLETE {counts['INCOMPLETE']}   pass rate {counts['PASS'] / n:.1%}",
        format_table(
            ["Test", "Seed", "Status", "Err", "Fatal", "Warn", "First error"],
            [[r.test, r.seed, r.status, r.errors, r.fatals, r.warnings, r.short_error[:70]]
             for r in sorted(results, key=lambda r: (r.status == "PASS", r.test))],
        ),
    ]
    groups = signatures(results)
    if groups:
        out.append("")
        out.append("FAILURE SIGNATURES (debug the biggest group first)")
        rows = [[len(rs), sig, ", ".join(f"{r.test}:{r.seed}" if r.seed else r.test for r in rs[:4])
                 + (" ..." if len(rs) > 4 else "")] for sig, rs in groups.items()]
        out.append(format_table(["Count", "Signature", "Tests (name:seed)"], rows))
    return "\n".join(out)


def write_csv(results, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["test", "seed", "status", "errors", "fatals", "warnings", "first_error", "signature", "log"])
        for r in results:
            w.writerow([r.test, r.seed, r.status, r.errors, r.fatals, r.warnings, r.first_error, r.signature, r.file])


def write_html(results, path):
    """Save the shareable HTML report to a file."""
    Path(path).write_text(html_report(results), encoding="utf-8")


def html_report(results):
    """A shareable, self-contained HTML page (e.g. to mail to the team after a nightly run)."""
    e = html.escape
    n = len(results) or 1
    passed = sum(1 for r in results if r.status == "PASS")
    color = {"PASS": "#1e8e3e", "FAIL": "#d93025", "INCOMPLETE": "#e37400"}
    rows = "".join(
        f"<tr><td>{e(r.test)}</td><td>{e(r.seed)}</td><td style='color:{color[r.status]};font-weight:600'>{r.status}</td>"
        f"<td>{r.errors}</td><td>{r.fatals}</td><td>{r.warnings}</td><td><code>{e(r.first_error)}</code></td></tr>"
        for r in sorted(results, key=lambda r: (r.status == "PASS", r.test))
    )
    sig_rows = "".join(
        f"<tr><td>{len(rs)}</td><td><code>{e(sig)}</code></td><td>{e(', '.join(r.test for r in rs))}</td></tr>"
        for sig, rs in signatures(results).items()
    )
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Regression report</title>
<style>
:root {{ --bg:#fff; --fg:#1d2330; --line:#d9dee7; --head:#f2f4f8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171d; --fg:#e6e9ef; --line:#2c323d; --head:#1c2028; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.5 system-ui,sans-serif; max-width:1100px; margin:auto; padding:24px 16px; }}
table {{ border-collapse:collapse; width:100%; margin:12px 0 28px; }} th,td {{ border:1px solid var(--line); padding:5px 8px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); }} code {{ font-size:12px; word-break:break-word; }}
</style></head><body>
<h1>Regression report</h1>
<p><b>{len(results)}</b> tests &middot; <b>{passed}</b> passed &middot; pass rate <b>{passed / n:.1%}</b></p>
<h2>Failure signatures</h2><table><tr><th>Count</th><th>Signature</th><th>Tests</th></tr>{sig_rows or '<tr><td colspan=3>None</td></tr>'}</table>
<h2>All tests</h2><table><tr><th>Test</th><th>Seed</th><th>Status</th><th>Err</th><th>Fatal</th><th>Warn</th><th>First error</th></tr>{rows}</table>
</body></html>"""
    return page
