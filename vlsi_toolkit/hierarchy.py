"""Design hierarchy and FSM extraction for a multi-file RTL project.

hierarchy:  which module instantiates which (instance tree), top modules,
            modules that are instantiated but never defined (black boxes /
            library cells) and modules that are defined but never used.
FSMs:       finds `case (state)` blocks whose branches assign the next state,
            and returns states, transitions (with their if-conditions) and
            the reset state, ready to be drawn as a state diagram.

Pattern based (no full elaboration) - works well on conventional RTL coding
styles; very unusual code may be missed.
"""

import re
from dataclasses import dataclass, field

from .common import find_matching, split_top_level, strip_comments

_KEYWORDS = set("""
module endmodule input output inout wire reg logic bit integer real time genvar parameter localparam assign always
always_ff always_comb always_latch initial begin end if else case casez casex endcase default for while repeat forever
function endfunction task endtask generate endgenerate return typedef enum struct union packed signed unsigned posedge
negedge or and not xor nand nor buf supply0 supply1 tri wand wor defparam specify endspecify primitive endprimitive
fork join join_any join_none disable wait unique priority import export interface endinterface modport package endpackage
class endclass virtual automatic static const var string byte shortint int longint void
""".split())

_MODULE_RE = re.compile(r"\b(?:module|macromodule)\s+(\w+)")
_ENDMODULE_RE = re.compile(r"\bendmodule\b")
_INST_RE = re.compile(
    r"(?:^|;|\bend\b|\bbegin\b|\bgenerate\b|\belse\b|\))\s*([A-Za-z_]\w*)\s*"
    r"(#\s*\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)\s*)?"
    r"([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*\(",
    re.S,
)


@dataclass
class Instance:
    module: str
    name: str
    line: int
    params: dict = field(default_factory=dict)
    connections: int = 0


@dataclass
class ModuleDef:
    name: str
    file: str
    line: int
    instances: list = field(default_factory=list)
    fsms: list = field(default_factory=list)


@dataclass
class Transition:
    src: str
    dst: str
    condition: str


@dataclass
class FSM:
    module: str
    state_var: str
    states: list
    transitions: list
    reset_state: str | None
    line: int


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _module_bodies(text):
    """Yield (name, header_end, body_start, body_end) for each module in comment-free text."""
    pos = 0
    while True:
        m = _MODULE_RE.search(text, pos)
        if not m:
            return
        semi = text.find(";", m.end())
        # the header may contain #( ... ) and ( ... ) with semicolons only at the end
        i = m.end()
        while i < len(text) and text[i].isspace():
            i += 1
        if i < len(text) and text[i] == "#":
            i = find_matching(text, text.index("(", i)) + 1
            while i < len(text) and text[i].isspace():
                i += 1
        if i < len(text) and text[i] == "(":
            i = find_matching(text, i) + 1
        semi = text.find(";", i)
        end = _ENDMODULE_RE.search(text, semi)
        end_idx = end.start() if end else len(text)
        yield m.group(1), m.start(), semi + 1, end_idx
        pos = end.end() if end else len(text)


def _instances(text, start, end):
    body = text[start:end]
    # function/task bodies have no instances and confuse the pattern
    body_clean = re.sub(r"\b(function|task)\b.*?\bend\1\b", lambda m: " " * len(m.group(0)), body, flags=re.S)
    out = []
    pos = 0
    while True:
        m = _INST_RE.search(body_clean, pos)
        if not m:
            break
        mod, params, name = m.group(1), m.group(2), m.group(3)
        open_idx = m.end() - 1
        try:
            close_idx = find_matching(body_clean, open_idx)
        except ValueError:
            break
        pos = m.start(1) + 1
        if mod in _KEYWORDS or name in _KEYWORDS:
            continue
        after = body_clean[close_idx + 1 : close_idx + 40].lstrip()
        if not (after.startswith(";") or after.startswith(",")):
            continue  # a function call or expression, not an instance
        conns = split_top_level(body_clean[open_idx + 1 : close_idx])
        pmap = {}
        if params:
            inner = params[params.index("(") + 1 : params.rindex(")")]
            for item in split_top_level(inner):
                pm = re.match(r"\s*\.(\w+)\s*\((.*)\)\s*$", item, re.S)
                if pm:
                    pmap[pm.group(1)] = " ".join(pm.group(2).split())
        out.append(Instance(mod, name, _line_of(text, start + m.start(3)), pmap, len(conns)))
        pos = close_idx + 1
    return out


# ---------------------------------------------------------------------------
# FSM extraction
# ---------------------------------------------------------------------------

_CASE_RE = re.compile(r"\b(?:unique\s+|priority\s+)?case[zx]?\s*\(\s*([A-Za-z_]\w*)\s*\)")


def _case_items(block):
    """Split the inside of a case block into [(labels, body)] at nesting depth 0."""
    items = []
    tokens = list(re.finditer(r"\b(begin|end|case[zx]?|endcase|fork|join)\b|([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*|default)\s*:(?!:)", block))
    depth = 0
    starts = []
    for t in tokens:
        kw = t.group(1)
        if kw in ("begin", "fork") or (kw and kw.startswith("case") and kw != "endcase"):
            depth += 1
        elif kw in ("end", "join", "endcase"):
            depth -= 1
        elif t.group(2) and depth == 0:
            starts.append((t.start(), t.end(), [s.strip() for s in t.group(2).split(",")]))
    for k, (s, e, labels) in enumerate(starts):
        body_end = starts[k + 1][0] if k + 1 < len(starts) else len(block)
        items.append((labels, block[e:body_end]))
    return items


def _transitions_in(body, targets, states):
    """Find `target = STATE` assignments in a case branch, with the nearest if-condition."""
    out = []
    for m in re.finditer(r"\b(\w+)\s*<?=\s*([A-Za-z_]\w*)\s*;", body):
        if m.group(1) not in targets or m.group(2) not in states:
            continue
        before = body[: m.start()]
        cond = "always"
        # innermost unclosed if/else before the assignment
        ifs = list(re.finditer(r"\b(else\s+if|if)\s*\(", before))
        elses = [e.start() for e in re.finditer(r"\belse\b(?!\s+if)", before)]
        last_if = ifs[-1] if ifs else None
        last_else = elses[-1] if elses else -1
        if last_if and last_if.start() > last_else:
            open_idx = before.index("(", last_if.start())
            try:
                close_idx = find_matching(body, open_idx)
                cond = " ".join(body[open_idx + 1 : close_idx].split())
            except ValueError:
                pass
        elif last_else >= 0:
            cond = "else"
        out.append((m.group(2), cond))
    return out


def _fsms(module_name, text, start, end):
    body = text[start:end]
    found = []
    for cm in _CASE_RE.finditer(body):
        state_var = cm.group(1)
        # find the matching endcase
        depth, i = 0, cm.end()
        block_end = None
        for t in re.finditer(r"\b(case[zx]?|endcase)\b", body[cm.end():]):
            if t.group(1) == "endcase":
                if depth == 0:
                    block_end = cm.end() + t.start()
                    break
                depth -= 1
            else:
                depth += 1
        if block_end is None:
            continue
        items = _case_items(body[cm.end():block_end])
        states = [lbl for labels, _ in items for lbl in labels if lbl != "default" and not lbl[0].isdigit()]
        if len(states) < 2:
            continue
        # the register being updated: state itself, or next_state / state_next / nxt_state ...
        targets = {state_var} | set(re.findall(rf"\b(\w*(?:next|nxt|ns)\w*)\s*<?=", body[cm.end():block_end], re.I))
        transitions = []
        state_set = set(states)
        for labels, item_body in items:
            for lbl in labels:
                if lbl == "default":
                    continue
                for dst, cond in _transitions_in(item_body, targets, state_set):
                    transitions.append(Transition(lbl, dst, cond))
        if not transitions:
            continue
        reset = None
        rm = re.search(rf"if\s*\(\s*!?\s*\w*(?:rst|reset)\w*\s*\)\s*(?:begin\s*)?{re.escape(state_var)}\s*<=\s*([A-Za-z_]\w*)", body)
        if rm and rm.group(1) in state_set:
            reset = rm.group(1)
        # self-loops are implied when a state has no unconditional exit; keep only explicit ones
        unique = []
        seen = set()
        for t in transitions:
            key = (t.src, t.dst, t.condition)
            if key not in seen:
                seen.add(key)
                unique.append(t)
        found.append(FSM(module_name, state_var, states, unique, reset, _line_of(text, start + cm.start())))
    return found


# ---------------------------------------------------------------------------
# Project analysis
# ---------------------------------------------------------------------------


def analyze_project(files):
    """files: [(name, text)]. Returns a dict describing hierarchy and FSMs."""
    modules = {}
    duplicates = []
    for fname, raw in files:
        text = strip_comments(raw)
        for name, mstart, bstart, bend in _module_bodies(text):
            md = ModuleDef(name, fname, _line_of(text, mstart), _instances(text, bstart, bend),
                           _fsms(name, text, bstart, bend))
            if name in modules:
                duplicates.append(name)
            modules[name] = md

    instantiated = {i.module for m in modules.values() for i in m.instances}
    tops = sorted(n for n in modules if n not in instantiated)
    undefined = sorted(instantiated - set(modules))

    def tree(name, inst_name, path):
        md = modules.get(name)
        node = {"module": name, "instance": inst_name, "defined": md is not None,
                "file": md.file if md else None, "children": [], "fsm_count": len(md.fsms) if md else 0}
        if md and name not in path:
            for inst in md.instances:
                child = tree(inst.module, inst.name, path | {name})
                child["params"] = inst.params
                node["children"].append(child)
        elif md:
            node["recursive"] = True
        return node

    def count(node):
        return 1 + sum(count(c) for c in node["children"])

    trees = [tree(t, t, frozenset()) for t in tops]
    usage = {}
    for m in modules.values():
        for inst in m.instances:
            usage[inst.module] = usage.get(inst.module, 0) + 1
    # the real top is the root of the biggest tree; other roots are usually leftovers
    sizes = {t["module"]: count(t) for t in trees}
    main_top = max(tops, key=lambda t: (sizes[t], t)) if tops else None
    unused = sorted(t for t in tops if t != main_top and sizes[t] == 1)
    return {
        "tops": tops,
        "main_top": main_top,
        "unused": unused,
        "trees": sorted(trees, key=lambda t: -sizes[t["module"]]),
        "total_instances": sum(count(t) - 1 for t in trees),
        "undefined": undefined,
        "duplicates": sorted(set(duplicates)),
        "modules": [{
            "name": m.name, "file": m.file, "line": m.line, "instances": len(m.instances),
            "used": usage.get(m.name, 0), "fsms": len(m.fsms),
            "children": sorted({i.module for i in m.instances}),
        } for m in sorted(modules.values(), key=lambda m: m.name)],
        "fsms": [{
            "module": f.module, "state_var": f.state_var, "states": f.states, "reset_state": f.reset_state,
            "line": f.line, "file": modules[f.module].file,
            "transitions": [{"src": t.src, "dst": t.dst, "condition": t.condition} for t in f.transitions],
            "unreachable": sorted(_unreachable(f)),
            "dead_ends": sorted(s for s in f.states if not any(t.src == s and t.dst != s for t in f.transitions)),
        } for m in modules.values() for f in m.fsms],
    }


def _unreachable(fsm):
    """States that cannot be reached from the reset state (or the first state)."""
    start = fsm.reset_state or fsm.states[0]
    seen, todo = {start}, [start]
    while todo:
        s = todo.pop()
        for t in fsm.transitions:
            if t.src == s and t.dst not in seen:
                seen.add(t.dst)
                todo.append(t.dst)
    return set(fsm.states) - seen


def tree_text(node, prefix="", last=True, root=True):
    """ASCII tree for the command line."""
    label = f"{node['instance']} ({node['module']})" if not root else node["module"]
    if not node["defined"]:
        label += "  [not defined: black box?]"
    if node.get("fsm_count"):
        label += f"  [{node['fsm_count']} FSM]"
    lines = [label if root else f"{prefix}{'`-- ' if last else '|-- '}{label}"]
    kids = node["children"]
    for i, c in enumerate(kids):
        lines += tree_text(c, prefix if root else prefix + ("    " if last else "|   "), i == len(kids) - 1, False)
    return lines if not root else "\n".join(lines)
