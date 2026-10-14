"""Verilog / SystemVerilog module-header parser.

Extracts, for every module in a file:
  * module name
  * parameters (with their default values evaluated when possible)
  * ports: direction, net type, signedness, packed range and computed width

Both port styles are supported:

  ANSI (Verilog-2001):            Non-ANSI (Verilog-1995):
    module m #(parameter W=8) (     module m (a, b, y);
        input  [W-1:0] a, b,          input  [7:0] a, b;
        output reg     y              output       y;
    );                                reg          y;

This is a lightweight regex-based parser meant for headers, not a full
compiler. For full SystemVerilog elaboration use a real front end such as
pyslang or Verilator.
"""

import json
import re
from dataclasses import asdict, dataclass, field

from .common import find_matching, format_table, split_top_level, strip_comments, try_eval

DIRECTIONS = ("input", "output", "inout")
NET_TYPES = r"(?:wire|reg|logic|bit|tri|var|wand|wor|uwire)"

_MODULE_RE = re.compile(r"\b(?:module|macromodule)\s+(\w+)")
_ENDMODULE_RE = re.compile(r"\bendmodule\b")
_FUNC_TASK_RE = re.compile(r"\b(function|task)\b.*?\bend\1\b", re.S)

# One ANSI port item, e.g. "output reg signed [7:0] q = 0"
_ANSI_PORT_RE = re.compile(
    rf"""^(?:(?P<dir>input|output|inout)\s+)?
        (?P<types>(?:{NET_TYPES}\s+)*)
        (?:(?P<sign>signed|unsigned)\s+)?
        (?P<range>(?:\[[^\]]*\]\s*)*)
        (?P<name>\w+)\s*
        (?:\[[^\]]*\]\s*)*          # unpacked dimensions (ignored)
        (?:=.*)?$""",
    re.X | re.S,
)

# The part after "input"/"output"/"reg" in a body declaration
_DECL_RE = re.compile(
    rf"""^\s*(?P<types>(?:{NET_TYPES}\s+)*)
        (?:(?P<sign>signed|unsigned)\s+)?
        (?P<range>(?:\[[^\]]*\]\s*)*)
        (?P<names>.*)$""",
    re.X | re.S,
)

_PARAM_ITEM_RE = re.compile(
    r"""^(?:(?P<kind>parameter|localparam)\s+)?
        (?:(?:integer|int|real|logic|bit|signed|unsigned|string|time)\s+)*
        (?:\[[^\]]*\]\s*)?
        (?P<name>\w+)\s*=\s*(?P<value>.+)$""",
    re.X | re.S,
)


@dataclass
class Parameter:
    name: str
    default: str
    local: bool = False
    value: int | None = None  # evaluated value, None if not a constant integer


@dataclass
class Port:
    name: str
    direction: str
    net_type: str = "wire"
    signed: bool = False
    packed_range: str = ""  # e.g. "[WIDTH-1:0]" ("" means 1 bit)
    width: int | None = 1  # None when the range could not be evaluated

    @property
    def width_str(self):
        if not self.packed_range:
            return "1"
        return str(self.width) if self.width is not None else "?"


@dataclass
class Module:
    name: str
    parameters: list = field(default_factory=list)
    ports: list = field(default_factory=list)
    ansi: bool = True
    warnings: list = field(default_factory=list)

    def ports_by_dir(self, direction):
        return [p for p in self.ports if p.direction == direction]

    @property
    def inputs(self):
        return self.ports_by_dir("input")

    @property
    def outputs(self):
        return self.ports_by_dir("output")

    @property
    def inouts(self):
        return self.ports_by_dir("inout")

    @property
    def overridable_params(self):
        return [p for p in self.parameters if not p.local]

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------
# Width calculation
# --------------------------------------------------------------------------


def range_width(packed_range, env):
    """Width of a packed range like "[WIDTH-1:0]" or "[3:0][7:0]"."""
    if not packed_range.strip():
        return 1
    total = 1
    for dim in re.findall(r"\[([^\]]*)\]", packed_range):
        bounds = split_top_level(dim, ":")
        if len(bounds) == 2:
            msb, lsb = try_eval(bounds[0], env), try_eval(bounds[1], env)
            if msb is None or lsb is None:
                return None
            total *= abs(msb - lsb) + 1
        elif len(bounds) == 1:  # SystemVerilog "[8]" means 8 bits
            size = try_eval(bounds[0], env)
            if size is None:
                return None
            total *= size
        else:
            return None
    return total


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _parse_param_items(text, local, kind_default="parameter"):
    params = []
    for item in split_top_level(text):
        m = _PARAM_ITEM_RE.match(item.strip())
        if not m:
            continue
        kind = m.group("kind") or kind_default
        params.append(
            Parameter(
                name=m.group("name"),
                default=" ".join(m.group("value").split()),
                local=local or kind == "localparam",
            )
        )
        if m.group("kind"):
            kind_default = m.group("kind")
    return params


def _net_type(types_text, default="wire"):
    words = types_text.split()
    # "wire logic" -> "logic"; "reg" -> "reg"
    return words[-1] if words else default


def _parse_ansi_ports(port_text, module):
    ports = []
    prev = None
    for item in split_top_level(port_text):
        m = _ANSI_PORT_RE.match(item.strip())
        if not m:
            module.warnings.append(f"skipped unsupported port item: '{item.strip()}'")
            continue
        rng = " ".join(m.group("range").split())
        if m.group("dir"):
            port = Port(
                name=m.group("name"),
                direction=m.group("dir"),
                net_type=_net_type(m.group("types")),
                signed=m.group("sign") == "signed",
                packed_range=rng,
            )
        elif prev is not None:
            # "input [7:0] a, b" -> b inherits direction/type/range from a
            has_own = bool(m.group("types") or m.group("sign") or rng)
            port = Port(
                name=m.group("name"),
                direction=prev.direction,
                net_type=_net_type(m.group("types"), prev.net_type) if has_own else prev.net_type,
                signed=(m.group("sign") == "signed") if has_own else prev.signed,
                packed_range=rng if has_own else prev.packed_range,
            )
        else:
            module.warnings.append(f"port '{m.group('name')}' has no direction")
            continue
        ports.append(port)
        prev = port
    return ports


def _parse_non_ansi_ports(port_text, body, module):
    names = []
    for item in split_top_level(port_text):
        m = re.match(r"\s*\.?(\w+)", item)
        if m:
            names.append(m.group(1))
    found = {}

    for m in re.finditer(r"\b(input|output|inout)\b([^;]*);", body):
        decl = _DECL_RE.match(m.group(2))
        if not decl:
            continue
        rng = " ".join(decl.group("range").split())
        for name_item in split_top_level(decl.group("names")):
            nm = re.match(r"\s*(\w+)", name_item)
            if nm:
                found[nm.group(1)] = Port(
                    name=nm.group(1),
                    direction=m.group(1),
                    net_type=_net_type(decl.group("types")),
                    signed=decl.group("sign") == "signed",
                    packed_range=rng,
                )

    # A later "reg [7:0] q;" turns output q into a reg
    for m in re.finditer(rf"\b(reg|logic)\b([^;]*);", body):
        decl = _DECL_RE.match(m.group(2))
        if not decl:
            continue
        for name_item in split_top_level(decl.group("names")):
            nm = re.match(r"\s*(\w+)", name_item)
            if nm and nm.group(1) in found:
                found[nm.group(1)].net_type = m.group(1)

    ports = []
    for name in names:
        if name in found:
            ports.append(found[name])
        else:
            module.warnings.append(f"no direction declaration found for port '{name}'")
            ports.append(Port(name=name, direction="unknown"))
    return ports


def _skip_ws(text, i):
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def parse_text(text):
    """Parse Verilog source text and return a list of Module objects."""
    text = strip_comments(text)
    modules = []
    pos = 0
    while True:
        m = _MODULE_RE.search(text, pos)
        if not m:
            break
        module = Module(name=m.group(1))
        i = _skip_ws(text, m.end())

        header_params = None
        if i < len(text) and text[i] == "#":
            j = text.index("(", i)
            k = find_matching(text, j)
            header_params = text[j + 1 : k]
            i = _skip_ws(text, k + 1)

        port_text = ""
        if i < len(text) and text[i] == "(":
            k = find_matching(text, i)
            port_text = text[i + 1 : k]
            i = k + 1

        semi = text.find(";", i)
        end = _ENDMODULE_RE.search(text, semi)
        end_idx = end.start() if end else len(text)
        body = _FUNC_TASK_RE.sub("", text[semi + 1 : end_idx])

        # ---- parameters ----
        if header_params is not None:
            module.parameters += _parse_param_items(header_params, local=False)
        has_header = header_params is not None
        for pm in re.finditer(r"\b(parameter|localparam)\b([^;]*);", body):
            # With a #() header list, body "parameter"s are local (IEEE 1364-2005)
            local = pm.group(1) == "localparam" or has_header
            module.parameters += _parse_param_items(pm.group(2), local=local)

        env = {}
        for p in module.parameters:
            p.value = try_eval(p.default, env)
            if p.value is not None:
                env[p.name] = p.value

        # ---- ports ----
        if port_text.strip():
            module.ansi = bool(re.match(r"\s*(input|output|inout)\b", port_text))
            if module.ansi:
                module.ports = _parse_ansi_ports(port_text, module)
            else:
                module.ports = _parse_non_ansi_ports(port_text, body, module)

        for port in module.ports:
            port.width = range_width(port.packed_range, env)

        modules.append(module)
        pos = end.end() if end else len(text)
    return modules


def parse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return parse_text(f.read())


def pick_module(modules, name=None):
    """Return the module called `name`, or the last module in the file."""
    if not modules:
        raise ValueError("no module found in file")
    if name is None:
        return modules[-1]  # by convention the top module is usually last
    for m in modules:
        if m.name == name:
            return m
    raise ValueError(f"module '{name}' not found (available: {', '.join(m.name for m in modules)})")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def describe(module):
    """Human-readable summary of one module."""
    lines = [f"Module: {module.name}   (style: {'ANSI' if module.ansi else 'non-ANSI'})"]
    if module.parameters:
        rows = [
            [p.name, p.default, "" if p.value is None else p.value, "localparam" if p.local else "parameter"]
            for p in module.parameters
        ]
        lines.append(format_table(["Parameter", "Default", "Value", "Kind"], rows))
    rows = [
        [p.name, p.direction, p.net_type, "signed" if p.signed else "", p.packed_range or "-", p.width_str]
        for p in module.ports
    ]
    lines.append(format_table(["Port", "Dir", "Type", "Sign", "Range", "Width"], rows))
    total_in = sum(p.width or 0 for p in module.inputs)
    total_out = sum(p.width or 0 for p in module.outputs)
    lines.append(
        f"Inputs: {len(module.inputs)} ({total_in} bits)   "
        f"Outputs: {len(module.outputs)} ({total_out} bits)   Inouts: {len(module.inouts)}"
    )
    for w in module.warnings:
        lines.append(f"WARNING: {w}")
    return "\n".join(lines)


def to_json(modules):
    return json.dumps([m.to_dict() for m in modules], indent=2)
