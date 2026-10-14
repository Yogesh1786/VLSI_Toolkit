"""SystemVerilog Assertion (SVA) generator.

From a module's RTL it writes a block of assertions and cover points:

  AXI      for every AXI channel found on the ports (<prefix>awvalid / awready ...):
           VALID held until READY, payload stable while waiting, no X on VALID,
           and a cover point per handshake
  FSM      for every state machine: state always legal, reset state after reset,
           only known transitions (assert) and one cover point per transition
  ONE-HOT  signals named *_oh, *onehot*, grant*: $onehot0
  OUTPUTS  no X/Z on outputs after reset

The result is meant to be `included just before `endmodule`, so every
internal signal, parameter and state name is in scope:

    `ifdef ASSERT_ON
      `include "uart_tx_sva.svh"
    `endif
    endmodule
"""

import re
from datetime import date

from . import hierarchy, tb_generator, verilog_parser
from .axi import CHANNELS, _SIG_RE

_ONEHOT_RE = re.compile(r"(_oh$|^oh_|onehot|^grant|_grant$|_gnt$)", re.I)


def _axi_channels(ports):
    """{prefix: {channel: {field: port_name}}} for AXI-like port names."""
    groups = {}
    for p in ports:
        m = _SIG_RE.match(p.name)
        if m:
            groups.setdefault(m.group(1), {}).setdefault(m.group(2).lower(), {})[m.group(3).lower()] = p.name
    return {pre: {ch: f for ch, f in chans.items() if "valid" in f and "ready" in f}
            for pre, chans in groups.items() if sum("valid" in f and "ready" in f for f in chans.values()) >= 1}


def _declared_signals(text, module):
    """Internal reg/wire/logic names of the module (for one-hot detection)."""
    body = text
    m = re.search(rf"\bmodule\s+{re.escape(module)}\b(.*?)\bendmodule\b", text, re.S)
    if m:
        body = m.group(1)
    names = []
    for decl in re.findall(r"\b(?:reg|wire|logic)\b[^;]*;", body):
        decl = re.sub(r"\[[^\]]*\]", " ", decl)
        for n in re.findall(r"[A-Za-z_]\w*", decl.split("=")[0]):
            if n not in ("reg", "wire", "logic", "signed", "unsigned"):
                names.append(n)
    return names


def generate(text, module_name=None, filename="design.v", options=None):
    """Return {module, clock, reset, assertions: [...], code, counts} for one module of `text`."""
    opts = {"axi": True, "fsm": True, "onehot": True, "outputs": True, "covers": True, **(options or {})}
    modules = verilog_parser.parse_text(text)
    if not modules:
        raise ValueError("no module found")
    mod = verilog_parser.pick_module(modules, module_name)
    clocks, resets, _ = tb_generator.classify(mod)
    clk = clocks[0].name if clocks else None
    if not clk:
        raise ValueError(f"module {mod.name} has no clock input: assertions need a clock (clk, aclk, clock ...)")
    rst = resets[0].name if resets else None
    low = tb_generator.reset_active_low(resets[0]) if resets else True
    disable = f"disable iff (!{rst})" if rst and low else f"disable iff ({rst})" if rst else ""
    out_of_reset = (f"$rose({rst})" if low else f"$fell({rst})") if rst else None
    clock = f"@(posedge {clk})"

    items = []   # (kind, name, sva text, description)

    def prop(kind, name, body, desc, cover=False):
        label = f"{'c' if cover else 'a'}_{name}"
        verb = "cover" if cover else "assert"
        msg = "" if cover else f' else $error("{label}: {desc}")'
        items.append((kind, label, f"{label}: {verb} property ({clock} {disable} {body}){msg};".replace("  ", " "), desc,
                      "cover" if cover else "assert"))

    # ---- AXI channels
    if opts["axi"]:
        for pre, chans in _axi_channels(mod.ports).items():
            for ch, f in sorted(chans.items(), key=lambda kv: list(CHANNELS).index(kv[0])):
                v, r = f["valid"], f["ready"]
                tag = f"{pre}{ch}".strip("_")
                prop("AXI", f"{tag}_valid_stable", f"({v} && !{r}) |=> {v}",
                     f"{v.upper()} dropped before {r.upper()}")
                payload = [f[k] for k in CHANNELS[ch] if k in f]
                if payload:
                    prop("AXI", f"{tag}_payload_stable", f"({v} && !{r}) |=> $stable({{{', '.join(payload)}}})",
                         f"{ch.upper()} payload changed while waiting for {r.upper()}")
                prop("AXI", f"{tag}_valid_known", f"!$isunknown({v})", f"{v.upper()} is X/Z")
                if opts["covers"]:
                    prop("AXI", f"{tag}_handshake", f"{v} && {r}", f"{ch.upper()} handshake", cover=True)

    # ---- FSMs
    fsms = [f for f in hierarchy.analyze_project([(filename, text)])["fsms"] if f["module"] == mod.name] if opts["fsm"] else []
    for f in fsms:
        st = f["state_var"]
        prop("FSM", f"{st}_legal", f"{st} inside {{{', '.join(f['states'])}}}", f"{st} holds an illegal value")
        if f["reset_state"] and out_of_reset:
            items.append(("FSM", f"a_{st}_reset", f"a_{st}_reset: assert property ({clock} {out_of_reset} |-> {st} == {f['reset_state']}) "
                          f'else $error("a_{st}_reset: {st} is not {f["reset_state"]} after reset");',
                          f"{st} == {f['reset_state']} right after reset", "assert"))
        for s in f["states"]:
            nxt = sorted({t["dst"] for t in f["transitions"] if t["src"] == s} | {s})
            if len(nxt) > 1:
                prop("FSM", f"{st}_from_{s.lower()}", f"{st} == {s} |=> {st} inside {{{', '.join(nxt)}}}",
                     f"illegal transition out of {s}")
        if opts["covers"]:
            for t in f["transitions"]:
                if t["src"] != t["dst"]:
                    prop("FSM", f"{st}_{t['src'].lower()}_to_{t['dst'].lower()}", f"{st} == {t['src']} ##1 {st} == {t['dst']}",
                         f"{t['src']} -> {t['dst']} ({t['condition']})", cover=True)
            for s in f["unreachable"]:
                prop("FSM", f"{st}_reach_{s.lower()}", f"{st} == {s}", f"reach {s} (detected as UNREACHABLE)", cover=True)

    # ---- one-hot
    if opts["onehot"]:
        candidates = [p.name for p in mod.ports if p.width and p.width > 1] + _declared_signals(text, mod.name)
        for n in sorted({c for c in candidates if _ONEHOT_RE.search(c)}):
            prop("One-hot", f"{n}_onehot0", f"$onehot0({n})", f"{n} has more than one bit set")

    # ---- outputs known after reset
    if opts["outputs"]:
        for p in mod.outputs:
            prop("Outputs", f"{p.name}_known", f"!$isunknown({p.name})", f"{p.name} is X/Z after reset")

    counts = {}
    for kind, *_ in items:
        counts[kind] = counts.get(kind, 0) + 1
    code = _render(mod.name, filename, clk, rst, low, items)
    return {
        "module": mod.name, "modules": [m.name for m in modules], "clock": clk, "reset": rst, "reset_active_low": low,
        "fsms": len(fsms), "axi_prefixes": list(_axi_channels(mod.ports)) if opts["axi"] else [],
        "assertions": [{"kind": k, "name": n, "type": t, "description": d, "code": c} for k, n, c, d, t in items],
        "counts": counts, "code": code, "filename": f"{mod.name}_sva.svh",
    }


def _render(module, filename, clk, rst, low, items):
    lines = [
        "// " + "=" * 74,
        f"// Assertions for module '{module}' ({filename})",
        f"// Auto-generated by VLSI Toolkit on {date.today().isoformat()}",
        "//",
        "// Use: add these lines just before `endmodule` in the RTL (the block sees every",
        "// internal signal and state name), then simulate with +define+ASSERT_ON:",
        "//     `ifdef ASSERT_ON",
        f'//       `include "{module}_sva.svh"',
        "//     `endif",
        "//",
        f"// Clock: {clk}" + (f"   Reset: {rst} (active-{'low' if low else 'high'})" if rst else "   Reset: none found"),
        "// Properties on input ports describe what the *environment* must do: in formal",
        "// verification turn those `assert` into `assume`.",
        "// " + "=" * 74,
    ]
    current = None
    for kind, _name, code, desc, _t in items:
        if kind != current:
            lines += ["", f"// ---- {kind} " + "-" * max(4, 66 - len(kind))]
            current = kind
        lines.append(f"// {desc}")
        lines.append(code)
    return "\n".join(lines) + "\n"


def generate_files(files, module_name=None, options=None):
    """files: [(name, text)]. Finds the module in any of the files."""
    for name, text in files:
        mods = [m.name for m in verilog_parser.parse_text(text)]
        if module_name is None or module_name in mods:
            if mods:
                return generate(text, module_name, name, options)
    raise ValueError(f"module '{module_name}' not found")
