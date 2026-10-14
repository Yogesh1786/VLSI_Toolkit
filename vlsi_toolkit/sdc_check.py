"""SDC (Synopsys Design Constraints) checker.

Reads the common timing-constraint commands and reports the mistakes that make
STA silently wrong:

  NO_CLOCK             ERROR    no create_clock at all
  DUPLICATE_CLOCK      ERROR    the same clock name defined twice
  UNKNOWN_CLOCK        ERROR    a command refers to a clock that was never created
  BAD_PERIOD           ERROR    clock period missing, zero or negative
  GENERATED_NO_SOURCE  ERROR    create_generated_clock without -source
  UNKNOWN_PORT         ERROR    get_ports names a port that is not in the RTL (typo?)
  NO_UNCERTAINTY       WARNING  clock without set_clock_uncertainty (no margin for jitter/skew)
  MISSING_INPUT_DELAY  WARNING  input port without set_input_delay      (needs the RTL top)
  MISSING_OUTPUT_DELAY WARNING  output port without set_output_delay    (needs the RTL top)
  IO_DELAY_TOO_LARGE   WARNING  I/O delay above 80 % of the clock period
  MCP_WITHOUT_HOLD     WARNING  set_multicycle_path -setup N without the matching -hold N-1
  BROAD_FALSE_PATH     WARNING  set_false_path without -from/-to/-through: disables timing broadly
  UNRELATED_CLOCKS     INFO     clocks with no set_clock_groups / false path between them are
                                timed as synchronous (fine only if they really are)
"""

import fnmatch
import re

SEVERITY = {
    "NO_CLOCK": "ERROR", "DUPLICATE_CLOCK": "ERROR", "UNKNOWN_CLOCK": "ERROR", "BAD_PERIOD": "ERROR",
    "GENERATED_NO_SOURCE": "ERROR", "UNKNOWN_PORT": "ERROR", "NO_UNCERTAINTY": "WARNING",
    "MISSING_INPUT_DELAY": "WARNING", "MISSING_OUTPUT_DELAY": "WARNING", "IO_DELAY_TOO_LARGE": "WARNING",
    "MCP_WITHOUT_HOLD": "WARNING", "BROAD_FALSE_PATH": "WARNING", "UNRELATED_CLOCKS": "INFO",
}
RULE_HELP = {
    "NO_CLOCK": "Without create_clock nothing is timed: every register-to-register path is unconstrained.",
    "DUPLICATE_CLOCK": "A second create_clock with the same name silently replaces the first.",
    "UNKNOWN_CLOCK": "The command references a clock that does not exist, so the constraint is ignored.",
    "BAD_PERIOD": "The period must be a positive number in the library time unit (usually ns).",
    "GENERATED_NO_SOURCE": "A generated clock must say which clock or pin it is derived from (-source).",
    "UNKNOWN_PORT": "get_ports matched nothing in the RTL, usually a typo; the constraint is dropped.",
    "NO_UNCERTAINTY": "Clock uncertainty models jitter and skew; without it timing is optimistic.",
    "MISSING_INPUT_DELAY": "Inputs without set_input_delay are unconstrained: their paths are not timed.",
    "MISSING_OUTPUT_DELAY": "Outputs without set_output_delay are unconstrained: their paths are not timed.",
    "IO_DELAY_TOO_LARGE": "Almost the whole period is given to the outside world; little time is left inside the block.",
    "MCP_WITHOUT_HOLD": "A setup multicycle of N moves the hold check too; add -hold N-1 or hold will fail badly.",
    "BROAD_FALSE_PATH": "A false path without endpoints can disable timing on far more paths than intended.",
    "UNRELATED_CLOCKS": "Paths between these clocks are timed as synchronous; if they are asynchronous use set_clock_groups.",
}
_CLOCKS_RE = re.compile(r"\[\s*get_clocks\s+(\{[^}]*\}|\S+?)\s*\]")
_PORTS_RE = re.compile(r"\[\s*get_ports\s+(\{[^}]*\}|\S+?)\s*\]")


def _logical_lines(text):
    out, buf, start = [], "", 1
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not buf:
            start = n
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            out.append((start, buf.strip()))
        buf = ""
    return out


def _names(arg):
    arg = arg.strip()
    if arg.startswith("{"):
        arg = arg[1:-1]
    return [a for a in arg.split() if a]


def _opt(tokens, flag):
    if flag in tokens:
        i = tokens.index(flag)
        if i + 1 < len(tokens):
            return tokens[i + 1]
    return None


_ENDPOINT_RE = re.compile(r"(-(?:rise_|fall_)?(?:from|to|through))\s+(\[[^\]]*\]|\{[^}]*\}|\S+)")


def _endpoint_key(cmd):
    """Identify an exception by its -from/-to/-through arguments only, so -setup and -hold lines pair up."""
    return " ".join(f"{flag} {' '.join(arg.split())}" for flag, arg in _ENDPOINT_RE.findall(cmd))


def parse(text):
    clocks, io, exceptions, uncertainty, groups_cmds, commands, clock_refs = {}, [], [], set(), [], [], []
    issues = []

    def add(rule, line, msg):
        issues.append({"rule": rule, "severity": SEVERITY[rule], "line": line, "message": msg})

    for line_no, cmd in _logical_lines(text):
        word = cmd.split()[0]
        commands.append(word)
        refs = [c for g in _CLOCKS_RE.findall(cmd) for c in _names(g)]
        ports = [p for g in _PORTS_RE.findall(cmd) for p in _names(g)]
        plain = re.sub(r"\[[^\]]*\]", " ", cmd)
        plain = re.sub(r"\{[^}]*\}", " ", plain)
        toks = plain.split()
        if word == "create_clock":
            name = _opt(toks, "-name") or (ports[0] if ports else None)
            period = _opt(toks, "-period")
            p = float(period) if period and re.fullmatch(r"[-+]?\d+(\.\d+)?", period) else None
            if name in clocks:
                add("DUPLICATE_CLOCK", line_no, f"clock '{name}' is defined again (line {clocks[name]['line']})")
            if p is None or p <= 0:
                add("BAD_PERIOD", line_no, f"clock '{name}' has period '{period}'")
            clocks[name] = {"name": name, "period": p, "freq_mhz": round(1000 / p, 3) if p else None, "ports": ports,
                            "generated": False, "master": None, "line": line_no, "uncertainty": False}
        elif word == "create_generated_clock":
            name = _opt(toks, "-name") or (ports[0] if ports else "?")
            src_match = re.search(r"-source\s+(\[[^\]]*\]|\S+)", cmd)
            master = _opt(toks, "-master_clock") or (refs[0] if refs else None)
            div = _opt(toks, "-divide_by")
            mul = _opt(toks, "-multiply_by")
            if not src_match:
                add("GENERATED_NO_SOURCE", line_no, f"generated clock '{name}' has no -source")
            clocks[name] = {"name": name, "period": None, "freq_mhz": None, "ports": ports, "generated": True,
                            "master": master, "divide_by": int(div) if div and div.isdigit() else None,
                            "multiply_by": int(mul) if mul and mul.isdigit() else None, "line": line_no, "uncertainty": False,
                            "source": src_match.group(1) if src_match else None}
        elif word in ("set_input_delay", "set_output_delay"):
            clk = _opt(toks, "-clock") or (refs[0] if refs else None)
            if "-clock" in toks and refs:
                clk = refs[0]
            nums = [t for t in toks[1:] if re.fullmatch(r"[-+]?\d+(\.\d+)?", t) and toks[toks.index(t) - 1] != "-clock"]
            value = float(nums[0]) if nums else None
            io.append({"kind": "input" if word == "set_input_delay" else "output", "clock": clk, "value": value,
                       "ports": ports, "all": "all_inputs" in cmd or "all_outputs" in cmd,
                       "minmax": "min" if "-min" in toks else "max" if "-max" in toks else "both", "line": line_no})
        elif word in ("set_clock_uncertainty", "set_clock_latency", "set_clock_transition"):
            if word == "set_clock_uncertainty":
                uncertainty.update(refs or ["*"])
        elif word in ("set_false_path", "set_multicycle_path", "set_max_delay", "set_min_delay"):
            has_ends = any(f in toks for f in ("-from", "-to", "-through", "-rise_from", "-fall_from", "-rise_to", "-fall_to"))
            n = next((int(t) for t in toks[1:] if t.isdigit()), None)
            exceptions.append({"kind": word.replace("set_", ""), "line": line_no, "text": cmd, "clocks": refs,
                               "setup": "-setup" in toks or ("-hold" not in toks), "hold": "-hold" in toks,
                               "multiplier": n, "has_endpoints": has_ends,
                               "key": _endpoint_key(cmd)})
            if word == "set_false_path" and not has_ends:
                add("BROAD_FALSE_PATH", line_no, "set_false_path without -from/-to/-through")
        elif word == "set_clock_groups":
            groups_cmds.append({"line": line_no, "groups": [_names(g) for g in re.findall(r"-group\s+(\{[^}]*\}|\[[^\]]*\]|\S+)", cmd)],
                                "type": next((t for t in ("-asynchronous", "-logically_exclusive", "-physically_exclusive") if t in toks), "")})
        # clock references are checked once all create_clock commands are known
        if word != "create_clock":
            clock_refs.extend((line_no, c, word) for c in refs)
    return clocks, io, exceptions, uncertainty, groups_cmds, clock_refs, issues


def check(text, rtl_ports=None):
    """rtl_ports: optional {"inputs": [...], "outputs": [...]} of the top module for coverage/typo checks."""
    clocks, io, exceptions, uncertainty, groups_cmds, clock_refs, issues = parse(text)
    unknown_seen = set()

    def add(rule, line, msg):
        issues.append({"rule": rule, "severity": SEVERITY[rule], "line": line, "message": msg})

    def unknown_clock(line, name, where):
        if (line, name) not in unknown_seen and not any(fnmatch.fnmatchcase(k, name) for k in clocks):
            unknown_seen.add((line, name))
            add("UNKNOWN_CLOCK", line, f"{where} refers to clock '{name}', which is never created")

    if not clocks:
        add("NO_CLOCK", 1, "no create_clock found: nothing will be timed")
    # generated clocks: period from master
    for c in clocks.values():
        if c["generated"] and c["master"] in clocks and clocks[c["master"]]["period"]:
            p = clocks[c["master"]]["period"]
            p = p * (c.get("divide_by") or 1) / (c.get("multiply_by") or 1)
            c["period"], c["freq_mhz"] = p, round(1000 / p, 3)
    for line_no, name, word in clock_refs:
        unknown_clock(line_no, name, word)
    for g in groups_cmds:
        for grp in g["groups"]:
            for name in grp:
                if not name.startswith("["):
                    unknown_clock(g["line"], name, "set_clock_groups")
    for c in clocks.values():
        c["uncertainty"] = "*" in uncertainty or any(fnmatch.fnmatchcase(c["name"], u) for u in uncertainty)
        if not c["uncertainty"] and not c["generated"]:
            add("NO_UNCERTAINTY", c["line"], f"clock '{c['name']}' has no set_clock_uncertainty")
    for d in io:
        clk = clocks.get(d["clock"])
        if d["clock"] and not clk:
            unknown_clock(d["line"], d["clock"], f"set_{d['kind']}_delay")
        if clk and clk["period"] and d["value"] is not None and d["value"] > 0.8 * clk["period"]:
            add("IO_DELAY_TOO_LARGE", d["line"], f"{d['kind']} delay {d['value']} is {d['value'] / clk['period']:.0%} of the "
                f"{clk['period']} period of '{clk['name']}'")
    # multicycle setup without hold
    mcps = [e for e in exceptions if e["kind"] == "multicycle_path"]
    for e in mcps:
        if e["setup"] and not e["hold"] and (e["multiplier"] or 1) > 1:
            if not any(o["hold"] and o["key"] == e["key"] for o in mcps):
                add("MCP_WITHOUT_HOLD", e["line"], f"setup multicycle of {e['multiplier']} without a matching "
                    f"'-hold {e['multiplier'] - 1}': hold is checked {e['multiplier'] - 1} cycle(s) too late")
    # RTL ports: typos and coverage
    clock_ports = {p for c in clocks.values() for p in c["ports"]}
    if rtl_ports:
        all_ports = set(rtl_ports.get("inputs", [])) | set(rtl_ports.get("outputs", [])) | set(rtl_ports.get("inouts", []))
        mentioned = [(d["line"], p) for d in io for p in d["ports"]] + [(c["line"], p) for c in clocks.values() for p in c["ports"]]
        for line_no, p in mentioned:
            if not any(fnmatch.fnmatchcase(r, p.split("[")[0]) for r in all_ports):
                add("UNKNOWN_PORT", line_no, f"get_ports '{p}' matches no port of the top module")

        def covered(kind, port):
            return any(d["kind"] == kind and (d["all"] or any(fnmatch.fnmatchcase(port, q.split("[")[0]) for q in d["ports"])) for d in io)

        for p in rtl_ports.get("inputs", []):
            if p not in clock_ports and not re.search(r"rst|reset", p, re.I) and not covered("input", p):
                add("MISSING_INPUT_DELAY", 0, f"input '{p}' has no set_input_delay")
        for p in rtl_ports.get("outputs", []):
            if not covered("output", p):
                add("MISSING_OUTPUT_DELAY", 0, f"output '{p}' has no set_output_delay")
    # clocks without any relationship constraint
    masters = [c for c in clocks.values() if not c["generated"]]
    related = set()
    for g in groups_cmds:
        for grp in g["groups"]:
            related |= {(a, b) for a in grp for b in clocks}
            related |= {(b, a) for a in grp for b in clocks}
    for e in exceptions:
        if e["kind"] == "false_path" and len(e["clocks"]) >= 2:
            related |= {(e["clocks"][0], e["clocks"][1]), (e["clocks"][1], e["clocks"][0])}
    for i, a in enumerate(masters):
        for b in masters[i + 1:]:
            if (a["name"], b["name"]) not in related:
                add("UNRELATED_CLOCKS", b["line"], f"'{a['name']}' and '{b['name']}' have no set_clock_groups or false path: "
                    "timed as synchronous")
    order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    issues.sort(key=lambda i: (order[i["severity"]], i["line"]))
    return {
        "clocks": list(clocks.values()), "io_delays": io,
        "exceptions": [{k: v for k, v in e.items() if k != "key"} for e in exceptions],
        "clock_groups": groups_cmds, "issues": issues,
        "counts": {s: sum(i["severity"] == s for i in issues) for s in order},
        "rules": [{"rule": r, "severity": SEVERITY[r], "description": RULE_HELP[r]} for r in SEVERITY],
        "rtl_checked": bool(rtl_ports),
    }


def ports_from_rtl(text, module=None):
    from . import verilog_parser
    mods = verilog_parser.parse_text(text)
    if not mods:
        return None, None
    m = verilog_parser.pick_module(mods, module)
    return m.name, {"inputs": [p.name for p in m.inputs], "outputs": [p.name for p in m.outputs],
                    "inouts": [p.name for p in m.inouts]}
