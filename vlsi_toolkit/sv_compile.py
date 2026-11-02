"""Full SystemVerilog compiler checks with slang (pip install pyslang).

Parses and elaborates all files together (packages, interfaces, macros, `include headers) and
turns the compiler's diagnostics into lint findings:

    SV_ERROR          ERROR    real compile errors (syntax, undeclared names, type errors ...)
    WIDTH_TRUNCATION  WARNING  a wider value silently cut to a narrower target
    WIDTH_EXPANSION   INFO     a narrower value silently zero/sign-extended
    UNDRIVEN_SIGNAL   WARNING  a variable/net that is read but never assigned or driven
    UNUSED_SIGNAL     INFO     a variable, net or input port that is never used
    UNKNOWN_MODULE    WARNING  instantiated module not in the files (black box?)
    SIGN_CONVERSION   INFO     signed value assigned to unsigned (or the reverse)
    SV_WARNING        WARNING  any other compiler warning

    available() -> bool
    check(files) -> {"issues": [...], "top_modules": [...], "available": bool}
"""

import re
import tempfile
from pathlib import Path

try:
    import pyslang
    from pyslang import analysis, ast, syntax
except ImportError:  # optional dependency
    pyslang = None

SEVERITY = {
    "SV_ERROR": "ERROR", "WIDTH_TRUNCATION": "WARNING", "WIDTH_EXPANSION": "INFO", "UNDRIVEN_SIGNAL": "WARNING",
    "UNUSED_SIGNAL": "INFO", "UNKNOWN_MODULE": "WARNING", "SIGN_CONVERSION": "INFO", "SV_WARNING": "WARNING",
}
RULE_HELP = {
    "SV_ERROR": "The SystemVerilog compiler (slang) rejects this code: simulators and synthesis will too.",
    "WIDTH_TRUNCATION": "A wider value is silently cut to fit a narrower signal: the upper bits are lost.",
    "WIDTH_EXPANSION": "A narrower value is silently extended to a wider signal. Usually harmless; check signedness.",
    "UNDRIVEN_SIGNAL": "Read but never assigned or driven: it is X in simulation and a constant/floating net in silicon.",
    "UNUSED_SIGNAL": "Declared (or an input port) but never used: dead code or a missing connection.",
    "UNKNOWN_MODULE": "Instantiated but not defined in the given files (a memory, IP or library cell?).",
    "SIGN_CONVERSION": "A signed value is assigned to an unsigned signal (or the reverse). Often intended in arithmetic; check comparisons.",
    "SV_WARNING": "Other compiler warning.",
}
# slang diagnostic code -> our rule (None = drop: the regex lint already reports it)
CODE_RULE = {
    "WidthTruncate": "WIDTH_TRUNCATION", "WidthExpand": "WIDTH_EXPANSION",
    "UnassignedVariable": "UNDRIVEN_SIGNAL", "UndrivenNet": "UNDRIVEN_SIGNAL", "UndrivenPort": "UNDRIVEN_SIGNAL",
    "UnusedVariable": "UNUSED_SIGNAL", "UnusedNet": "UNUSED_SIGNAL", "UnusedPort": "UNUSED_SIGNAL",
    "UnusedButSetVariable": "UNUSED_SIGNAL", "UnusedButSetNet": "UNUSED_SIGNAL",
    "UnknownModule": "UNKNOWN_MODULE",
    "SignConversion": "SIGN_CONVERSION",
    "EmptyOutputPortConn": "UNUSED_SIGNAL",
    "InferredLatch": None,                 # LATCH_RISK in lint.py
    "CaseDefault": None,                   # CASE_NO_DEFAULT in lint.py
    # common, harmless in RTL (parameter/integer comparisons, reg + 1'b1, file endings)
    "SignCompare": None, "ArithOpMismatch": None, "NewlineEOF": None,
}
# errors in slang that most simulators only warn about
DOWNGRADE = {"MissingTimeScale"}
_HEADER_EXT = (".vh", ".svh", ".vinc", ".inc")


def available():
    return pyslang is not None


def _safe(name, used):
    base = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).name) or "file.sv"
    out, n = base, 1
    while out in used:
        out, n = f"{n}_{base}", n + 1
    used.add(out)
    return out


def check(files):
    """files: [(name, text)]. Compiles everything together and returns lint-style issues."""
    if pyslang is None:
        return {"available": False, "issues": [], "top_modules": []}
    issues = []
    with tempfile.TemporaryDirectory(prefix="vt_slang_") as tmp:
        tmp = Path(tmp)
        used, names = set(), {}
        for name, text in files:
            safe = _safe(name, used)
            (tmp / safe).write_text(text, encoding="utf-8")
            names[safe] = name
        included = {inc for _, text in files for inc in re.findall(r'`include\s+"([^"]+)"', text)}
        sm = pyslang.SourceManager()
        sm.addUserDirectories(str(tmp))
        comp = ast.Compilation()
        for safe in names:
            if safe.lower().endswith(_HEADER_EXT) or Path(safe).name in included:
                continue        # headers are read through `include
            comp.addSyntaxTree(syntax.SyntaxTree.fromFile(str(tmp / safe), sm))
        diags = list(comp.getAllDiagnostics())
        if not any(d.isError() for d in diags):
            try:
                comp.freeze()
                opts = analysis.AnalysisOptions()
                opts.flags = analysis.AnalysisFlags.CheckUnused
                am = analysis.AnalysisManager(opts)
                am.analyze(comp)
                diags += list(am.getDiagnostics())
            except Exception:   # analysis is best-effort; compile diagnostics are what matter
                pass
        engine = pyslang.DiagnosticEngine(sm)
        seen = set()
        for d in diags:
            code = str(d.code).replace("DiagCode(", "").rstrip(")")
            rule = "SV_ERROR" if d.isError() and code not in DOWNGRADE else CODE_RULE.get(code, "SV_WARNING")
            if code in CODE_RULE and CODE_RULE[code] is None:
                continue
            if code == "UnknownModule":
                rule = "UNKNOWN_MODULE"
            loc = d.location
            try:
                loc = sm.getFullyOriginalLoc(loc)
                fname = Path(sm.getFileName(loc)).name
                line = sm.getLineNumber(loc)
            except Exception:
                fname, line = "?", 0
            try:
                msg = engine.formatMessage(d)
            except Exception:
                msg = code
            key = (rule, fname, line, msg)
            if key in seen:
                continue
            seen.add(key)
            issues.append({"file": names.get(fname, fname), "line": line, "severity": SEVERITY[rule], "rule": rule,
                           "message": msg, "code": code})
        tops = []
        try:
            tops = [inst.name for inst in comp.getRoot().topInstances]
        except Exception:
            pass
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["file"], i["line"]))
    return {"available": True, "issues": issues, "top_modules": tops}
