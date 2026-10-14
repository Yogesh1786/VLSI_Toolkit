"""Shared helpers used by every tool in the toolkit.

- strip_comments()   : remove // and /* */ comments from Verilog source
- find_matching()    : find the closing bracket that matches an opening one
- split_top_level()  : split "a, b[3:0], {c, d}" on commas that are not nested
- eval_expr()        : safely evaluate Verilog constant expressions such as
                       "WIDTH-1", "$clog2(DEPTH)" or "8'hFF"
- format_table()     : pretty-print rows as an aligned text table
"""

import ast
import operator
import re

# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*', re.S)


def strip_comments(text):
    """Remove Verilog comments, keeping string literals and line numbers intact."""

    def repl(match):
        s = match.group(0)
        if s.startswith('"'):
            return s  # string literal: keep as-is
        if s.startswith("/*"):
            return "\n" * s.count("\n") or " "
        return ""

    return _COMMENT_RE.sub(repl, text)


_PAIRS = {"(": ")", "[": "]", "{": "}"}


def find_matching(text, open_idx):
    """Return the index of the bracket that closes text[open_idx]."""
    opener = text[open_idx]
    closer = _PAIRS[opener]
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"Unbalanced '{opener}' at position {open_idx}")


def split_top_level(text, sep=","):
    """Split on `sep`, ignoring separators nested inside (), [] or {}."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


# --------------------------------------------------------------------------
# Safe constant-expression evaluation
# --------------------------------------------------------------------------

# Sized/based Verilog literals: 8'hFF, 4'b1010, 'd10, 16'sd5
_VNUM_RE = re.compile(r"(\d+)?\s*'\s*[sS]?([bBoOdDhH])\s*([0-9a-fA-F_]+)")
_BASES = {"b": 2, "o": 8, "d": 10, "h": 16}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.BitXor: operator.xor,
}
_UNARY_OPS = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Invert: operator.invert}


def clog2(value):
    """Verilog $clog2: number of bits needed to address `value` items."""
    return 0 if value <= 1 else (value - 1).bit_length()


def _vnum_to_int(match):
    base = _BASES[match.group(2).lower()]
    return str(int(match.group(3).replace("_", ""), base))


def _eval_node(node, env):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left, env), _eval_node(node.right, env)
        if isinstance(node.op, ast.Pow) and right > 1024:
            raise ValueError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand, env))
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise ValueError(f"unknown identifier '{node.id}'")
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "clog2"
        and len(node.args) == 1
    ):
        return clog2(_eval_node(node.args[0], env))
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def eval_expr(expr, env=None):
    """Evaluate a Verilog constant expression. Raises ValueError on failure."""
    s = _VNUM_RE.sub(_vnum_to_int, expr.strip())
    s = s.replace("$clog2", "clog2").replace("/", "//")
    try:
        tree = ast.parse(s, mode="eval")
        return _eval_node(tree.body, env or {})
    except (SyntaxError, ZeroDivisionError, TypeError, KeyError) as exc:
        raise ValueError(f"cannot evaluate '{expr}': {exc}") from exc


def try_eval(expr, env=None):
    """Like eval_expr() but returns None instead of raising."""
    try:
        return eval_expr(expr, env)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------


def format_table(headers, rows):
    """Return rows as an aligned plain-text table."""
    rows = [["" if c is None else str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    out = [line, "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |", line]
    for row in rows:
        out.append("| " + " | ".join(c.ljust(w) for c, w in zip(row, widths)) + " |")
    out.append(line)
    return "\n".join(out)
