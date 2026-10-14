"""RTL lint checker - catches common Verilog/SystemVerilog coding mistakes.

Rules (severity):
  MULTI_DRIVER        ERROR    same signal driven from more than one always/assign
  BLOCKING_IN_SEQ     WARNING  "=" inside a clocked always block (use "<=")
  NONBLOCKING_IN_COMB WARNING  "<=" inside a combinational always block (use "=")
  LATCH_RISK          WARNING  combinational block may not assign a signal on
                               every path -> synthesis infers a latch
  CASE_NO_DEFAULT     WARNING  case statement without a default branch
  SENS_LIST           INFO     explicit sensitivity list; @(*) / always_comb is safer
  CASEX               INFO     casex treats X as don't-care; prefer casez
  INITIAL_IN_RTL      INFO     initial blocks are ignored by ASIC synthesis
  DELAY_IN_RTL        INFO     #delays are ignored by synthesis
  CDC_UNSYNC          ERROR    signal from another clock domain used in logic without
                               a synchronizer (metastability)
  CDC_SINGLE_FLOP     WARNING  clock-domain crossing through only one flip-flop
  CDC_MULTIBIT        WARNING  multi-bit bus through a 2-flop synchronizer: bits may
                               arrive in different cycles (use Gray code, handshake or FIFO)

This is a fast, heuristic checker (pattern based, no full elaboration).
It does not replace a commercial lint tool (SpyGlass, Ascent, HAL), but it
catches the classic mistakes in seconds, before you even run a simulation.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .common import format_table, strip_comments

SEVERITY = {
    "MULTI_DRIVER": "ERROR",
    "BLOCKING_IN_SEQ": "WARNING",
    "NONBLOCKING_IN_COMB": "WARNING",
    "LATCH_RISK": "WARNING",
    "CASE_NO_DEFAULT": "WARNING",
    "SENS_LIST": "INFO",
    "CASEX": "INFO",
    "INITIAL_IN_RTL": "INFO",
    "DELAY_IN_RTL": "INFO",
    "CDC_UNSYNC": "ERROR",
    "CDC_SINGLE_FLOP": "WARNING",
    "CDC_MULTIBIT": "WARNING",
}
_SEV_ORDER = {"ERROR": 0, "WARNING": 1, "INFO": 2}

_KEYWORDS = {
    "if",
    "else",
    "begin",
    "end",
    "case",
    "casez",
    "casex",
    "default",
    "for",
    "while",
    "assign",
    "return",
}

_MODULE_RE = re.compile(r"\bmodule\b.*?(?:\bendmodule\b|\Z)", re.S)
_ALWAYS_RE = re.compile(r"\balways(_ff|_comb|_latch)?\b")
_STOP_RE = re.compile(
    r"\b(always\w*|assign|initial|endmodule|function|task|generate|endgenerate)\b"
)
# A statement that assigns to a signal: boundary, then  name[sel]  then = or <=
_LHS_RE = re.compile(
    r"(?:^|;|\bbegin\b|\belse\b|\)|:)\s*([A-Za-z_][\w.]*)((?:\s*\[[^\]]*\])*)\s*(<=|=)(?!=)",
    re.M,
)
_ASSIGN_RE = re.compile(
    r"\bassign\s+(?:#\s*\S+\s+)?([A-Za-z_]\w*)((?:\s*\[[^\]]*\])*)\s*="
)
_CASE_TOKEN_RE = re.compile(r"\b(casex|casez|case|endcase|default)\b")


@dataclass
class Issue:
    file: str
    line: int
    rule: str
    message: str

    @property
    def severity(self):
        return SEVERITY[self.rule]


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _cases_without_default(text, start=0, end=None):
    """Return positions of case statements (in text[start:end]) that have no default."""
    end = len(text) if end is None else end
    stack, missing = [], []
    for m in _CASE_TOKEN_RE.finditer(text, start, end):
        tok = m.group(1)
        if tok.startswith("case") and tok != "endcase":
            before = text[max(0, m.start() - 12) : m.start()]
            # "unique case" / "priority case" document full coverage on purpose
            has_qualifier = bool(re.search(r"\b(unique0?|priority)\s*$", before))
            stack.append([m.start(), has_qualifier])
        elif tok == "default" and stack:
            stack[-1][1] = True
        elif tok == "endcase" and stack:
            pos, ok = stack.pop()
            if not ok:
                missing.append(pos)
    return missing


def _always_blocks(text, start, end):
    blocks = []
    for m in _ALWAYS_RE.finditer(text, start, end):
        kind = m.group(1) or ""
        i = m.end()
        sens = ""
        sm = re.compile(r"\s*@\s*(\*|\((?:[^()]|\([^()]*\))*\))").match(text, i)
        if sm:
            sens = sm.group(1)
            i = sm.end()
        if re.compile(r"\s*begin\b").match(text, i):
            depth, body_end = 0, end
            for t in re.finditer(r"\b(begin|end)\b", text[i:end]):
                depth += 1 if t.group(1) == "begin" else -1
                if depth == 0:
                    body_end = i + t.end()
                    break
        else:
            s = _STOP_RE.search(text, i, end)
            body_end = s.start() if s else end
        clocked = kind == "_ff" or bool(re.search(r"\b(posedge|negedge)\b", sens))
        comb = kind == "_comb" or (not clocked and kind != "_latch" and sens != "")
        blocks.append(
            {
                "pos": m.start(),
                "start": i,
                "end": body_end,
                "sens": sens,
                "clocked": clocked,
                "comb": comb,
            }
        )
    return blocks


def _assignments(text, start, end):
    """[(name, select, operator, position)] for assignments inside text[start:end]."""
    body = text[start:end]
    loop_vars = set(
        re.findall(r"\bfor\s*\(\s*(?:int(?:eger)?\s+|genvar\s+)?(\w+)\s*=", body)
    )
    out = []
    for m in _LHS_RE.finditer(body):
        name = m.group(1)
        if name in loop_vars or name in _KEYWORDS:
            continue
        out.append((name, "".join(m.group(2).split()), m.group(3), start + m.start(1)))
    return out


def _lint_module(text, start, end, file):
    issues = []

    def add(pos, rule, msg):
        issues.append(Issue(file, _line_of(text, pos), rule, msg))

    drivers = {}  # signal -> [(select, description, position)]

    for blk in _always_blocks(text, start, end):
        assigns = _assignments(text, blk["start"], blk["end"])
        for name, sel, op, pos in assigns:
            if blk["clocked"] and op == "=":
                add(
                    pos,
                    "BLOCKING_IN_SEQ",
                    f"blocking '=' to '{name}' in clocked always block; use '<='",
                )
            if blk["comb"] and op == "<=":
                add(
                    pos,
                    "NONBLOCKING_IN_COMB",
                    f"non-blocking '<=' to '{name}' in combinational block; use '='",
                )
        for name in {a[0] for a in assigns}:
            sels = {a[1] for a in assigns if a[0] == name}
            drivers.setdefault(name, []).append(
                (
                    "" if "" in sels else ",".join(sorted(sels)),
                    "always block",
                    blk["pos"],
                )
            )

        if (
            blk["comb"]
            and blk["sens"]
            and blk["sens"].replace(" ", "") not in ("*", "(*)")
        ):
            add(
                blk["pos"],
                "SENS_LIST",
                f"sensitivity list {blk['sens']} - use @(*) or always_comb to avoid sim/synth mismatch",
            )

        if blk["comb"]:
            body = text[blk["start"] : blk["end"]]
            first_branch = re.search(r"\b(if|case[xz]?)\b", body)
            if first_branch:
                branch_pos = blk["start"] + first_branch.start()
                defaults = {n for n, _, _, p in assigns if p < branch_pos}
                ifs = len(re.findall(r"\bif\b", body))
                elses = len(re.findall(r"\belse\b", body))
                no_default = _cases_without_default(text, blk["start"], blk["end"])
                if ifs > elses or no_default:
                    risky = sorted({a[0] for a in assigns} - defaults)
                    if risky:
                        add(
                            blk["pos"],
                            "LATCH_RISK",
                            f"{', '.join(risky)} not assigned on every path -> latch "
                            "(add default values at the top of the block)",
                        )

    for m in _ASSIGN_RE.finditer(text, start, end):
        drivers.setdefault(m.group(1), []).append(
            ("".join(m.group(2).split()), "assign", m.start())
        )

    for name, drv in drivers.items():
        if len(drv) < 2:
            continue
        sels = [d[0] for d in drv]
        # different constant bit-selects (assign y[0]=..; assign y[1]=..) are fine
        if "" not in sels and len(set(sels)) == len(sels):
            continue
        where = ", ".join(f"{d[1]} (line {_line_of(text, d[2])})" for d in drv)
        add(
            drv[1][2],
            "MULTI_DRIVER",
            f"'{name}' is driven from multiple places: {where}",
        )

    for pos in _cases_without_default(text, start, end):
        add(pos, "CASE_NO_DEFAULT", "case without default branch")
    for m in re.finditer(r"\bcasex\b", text[start:end]):
        add(
            start + m.start(),
            "CASEX",
            "casex hides X bugs in simulation; prefer casez or 'unique case'",
        )
    for m in re.finditer(r"\binitial\b", text[start:end]):
        add(
            start + m.start(),
            "INITIAL_IN_RTL",
            "initial block is ignored by ASIC synthesis (OK in testbenches)",
        )
    for m in re.finditer(r"(?<![\w)`])#\s*\d+(?:\.\d+)?\b", text[start:end]):
        add(start + m.start(), "DELAY_IN_RTL", "#delay is ignored by synthesis")
    issues += _cdc(text, start, end, file)
    return issues


# ---------------------------------------------------------------------------
# Clock-domain crossings
# ---------------------------------------------------------------------------

_EDGE_RE = re.compile(r"\b(posedge|negedge)\s+([A-Za-z_]\w*)")
_NB_ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*<=\s*([^;]+);")
_DECL_RE = re.compile(
    r"\b(?:input|output|inout|reg|wire|logic)\b\s*(?:reg|wire|logic)?\s*(?:signed\s*)?(\[[^\]]+\])?\s*([^;()]+?)\s*[;,)]"
)
_IDENT_RE = re.compile(r"(?<!['\w])[A-Za-z_]\w*")
_RESET_NAME = re.compile(r"rst|reset", re.I)


def _block_clock(sens):
    """Clock of a sensitivity list: the edge signal that is not a reset."""
    edges = [n for _, n in _EDGE_RE.findall(sens)]
    clocks = [n for n in edges if not _RESET_NAME.search(n)]
    return clocks[0] if clocks else (edges[0] if len(edges) == 1 else None)


def _signal_widths(body):
    """{signal: True if multi-bit} from the declarations of a module."""
    widths = {}
    for rng, names in _DECL_RE.findall(body):
        multi = bool(rng) and not re.fullmatch(r"\[\s*0\s*:\s*0\s*\]", rng)
        for n in re.findall(r"[A-Za-z_]\w*", names.split("=")[0]):
            if n not in ("input", "output", "inout", "reg", "wire", "logic", "signed"):
                widths[n] = multi
    return widths


def _cdc(text, start, end, file):
    """Find signals that cross from one clock domain to another inside a module."""
    flops = []  # (clock, lhs, rhs, position)
    for b in _always_blocks(text, start, end):
        if not b["clocked"]:
            continue
        clk = _block_clock(b["sens"])
        if not clk:
            continue
        for m in _NB_ASSIGN_RE.finditer(text, b["start"], b["end"]):
            flops.append((clk, m.group(1), " ".join(m.group(2).split()), m.start(1)))
    if len({c for c, *_ in flops}) < 2:
        return []  # single clock domain: nothing can cross
    domain = {}
    for clk, lhs, _, _ in flops:
        domain.setdefault(lhs, set()).add(clk)
    multibit = _signal_widths(text[start:end])
    issues, seen = [], set()
    for clk, lhs, rhs, pos in flops:
        for src in sorted(set(_IDENT_RE.findall(rhs))):
            src_domains = domain.get(src, set())
            if not src_domains or clk in src_domains or (src, clk, lhs) in seen:
                continue
            seen.add((src, clk, lhs))
            src_clk = sorted(src_domains)[0]
            line = _line_of(text, pos)
            if rhs != src:
                issues.append(
                    Issue(
                        file,
                        line,
                        "CDC_UNSYNC",
                        f"'{src}' ({src_clk} domain) is used in {clk} logic ('{lhs} <= {rhs}') without a synchronizer",
                    )
                )
                continue
            # plain copy into this domain: is it registered again (2-flop synchronizer)?
            if not any(c == clk and r == lhs for c, _, r, _ in flops):
                issues.append(
                    Issue(
                        file,
                        line,
                        "CDC_SINGLE_FLOP",
                        f"'{src}' ({src_clk} -> {clk}) passes through only one flop ('{lhs}'); use two to stop metastability",
                    )
                )
            elif multibit.get(src, False):
                issues.append(
                    Issue(
                        file,
                        line,
                        "CDC_MULTIBIT",
                        f"multi-bit '{src}' ({src_clk} -> {clk}) through a 2-flop synchronizer: bits can arrive in "
                        "different cycles; use Gray code, a handshake or an async FIFO",
                    )
                )
    return issues


def lint_text(text, file="<text>"):
    text = strip_comments(text)  # keeps line numbers
    issues = []
    for m in _MODULE_RE.finditer(text):
        issues += _lint_module(text, m.start(), m.end(), file)
    return sorted(issues, key=lambda i: (i.file, i.line, _SEV_ORDER[i.severity]))


def collect_files(paths):
    """Expand folders into all .v/.sv files inside them."""
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(
                f for f in p.rglob("*") if f.suffix in (".v", ".sv", ".vh", ".svh")
            )
        else:
            files.append(p)
    return files


def lint_files(paths):
    issues = []
    for f in collect_files(paths):
        issues += lint_text(f.read_text(encoding="utf-8", errors="replace"), str(f))
    return issues


def report_text(issues, min_severity="INFO"):
    shown = [i for i in issues if _SEV_ORDER[i.severity] <= _SEV_ORDER[min_severity]]
    counts = {s: sum(1 for i in issues if i.severity == s) for s in _SEV_ORDER}
    summary = f"Errors: {counts['ERROR']}   Warnings: {counts['WARNING']}   Info: {counts['INFO']}"
    if not shown:
        return "No issues found.  " + summary
    rows = [[f"{i.file}:{i.line}", i.severity, i.rule, i.message] for i in shown]
    return (
        format_table(["Location", "Severity", "Rule", "Message"], rows) + "\n" + summary
    )
