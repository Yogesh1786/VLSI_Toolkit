"""Register map generator.

One spec file (JSON, or YAML if PyYAML is installed) describes a block's
control/status registers. From it we generate:

  * <block>_regs.v     synthesizable Verilog register file
  * <block>_regs.h     C header for firmware (addresses, masks, shifts)
  * <block>_regs.html  human-readable documentation
  * <block>_axil.v     AXI4-Lite slave with the same registers (connect it to a CPU bus)
  * tb_<block>_axil.v  self-checking testbench for the AXI4-Lite slave

Keeping all three in sync by hand is a classic source of silicon bugs;
generating them from one source of truth avoids that.

Access types (per register):
  RW  - read/write, flop inside the block, value driven out on <name>_o
  RO  - read-only, value comes from hardware on <name>_i
  WO  - write-only, flop driven out on <name>_o, reads return 0
  W1C - write-1-to-clear status, hardware sets bits via <name>_set_i
        (set has priority over clear), value driven out on <name>_o

Spec format (see examples/uart_regmap.json):
  {
    "block": "uart", "base_address": "0x40000000", "data_width": 32,
    "registers": [
      {"name": "CTRL", "offset": "0x00", "access": "RW", "description": "...",
       "fields": [{"name": "EN", "bits": "0", "reset": "0x1", "description": "..."}]}
    ]
  }
"""

import html
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ACCESS_TYPES = ("RW", "RO", "WO", "W1C")


class RegMapError(ValueError):
    pass


@dataclass
class Field:
    name: str
    msb: int
    lsb: int
    reset: int = 0
    description: str = ""

    @property
    def width(self):
        return self.msb - self.lsb + 1

    @property
    def mask(self):
        return ((1 << self.width) - 1) << self.lsb

    @property
    def bits(self):
        return f"{self.msb}:{self.lsb}" if self.msb != self.lsb else str(self.lsb)


@dataclass
class Register:
    name: str
    offset: int
    access: str
    description: str = ""
    fields: list = field(default_factory=list)

    @property
    def mask(self):
        m = 0
        for f in self.fields:
            m |= f.mask
        return m

    @property
    def reset(self):
        r = 0
        for f in self.fields:
            r |= f.reset << f.lsb
        return r


@dataclass
class RegMap:
    block: str
    base_address: int
    data_width: int
    addr_width: int
    registers: list
    description: str = ""


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------


def _to_int(value, what):
    if isinstance(value, int):
        return value
    try:
        return int(str(value).replace("_", ""), 0)
    except ValueError as exc:
        raise RegMapError(f"{what}: '{value}' is not a number") from exc


def _parse_bits(bits, what):
    if isinstance(bits, int):
        return bits, bits
    if isinstance(bits, (list, tuple)) and len(bits) == 2:
        return int(bits[0]), int(bits[1])
    text = str(bits).strip().strip("[]")
    if ":" in text:
        msb, lsb = text.split(":")
        return int(msb), int(lsb)
    try:
        return int(text), int(text)
    except ValueError as exc:
        raise RegMapError(f"{what}: bad bit range '{bits}' (use '7:4' or '3')") from exc


def load_spec(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise RegMapError(
                "YAML spec needs PyYAML: pip install pyyaml (or use a .json spec)"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    return build_regmap(data)


def build_regmap(data):
    """Turn a spec dict into a validated RegMap. Raises RegMapError on problems."""
    errors = []
    block = str(data.get("block", "")).strip()
    if not block.isidentifier():
        raise RegMapError(f"'block' must be a valid identifier, got '{block}'")
    dw = _to_int(data.get("data_width", 32), "data_width")
    if dw not in (8, 16, 32, 64):
        raise RegMapError("data_width must be 8, 16, 32 or 64")
    bytes_per_reg = dw // 8

    registers = []
    for i, r in enumerate(data.get("registers", [])):
        rname = str(r.get("name", f"REG{i}")).upper()
        where = f"register {rname}"
        access = str(r.get("access", "RW")).upper()
        if access not in ACCESS_TYPES:
            errors.append(f"{where}: access '{access}' not in {ACCESS_TYPES}")
        offset = _to_int(r.get("offset", i * bytes_per_reg), f"{where} offset")
        if offset % bytes_per_reg:
            errors.append(
                f"{where}: offset 0x{offset:X} not aligned to {bytes_per_reg} bytes"
            )

        fields = []
        for j, f in enumerate(r.get("fields") or []):
            fname = str(f.get("name", f"F{j}")).upper()
            msb, lsb = _parse_bits(f.get("bits", j), f"{where}.{fname}")
            if msb < lsb:
                msb, lsb = lsb, msb
            if msb >= dw:
                errors.append(f"{where}.{fname}: bit {msb} exceeds data width {dw}")
            reset = _to_int(f.get("reset", 0), f"{where}.{fname} reset")
            if reset >> (msb - lsb + 1):
                errors.append(
                    f"{where}.{fname}: reset 0x{reset:X} does not fit in {msb - lsb + 1} bits"
                )
            fields.append(Field(fname, msb, lsb, reset, str(f.get("description", ""))))
        if not fields:
            # no fields given: the whole register is one field
            reset = _to_int(r.get("reset", 0), f"{where} reset")
            fields.append(
                Field("VALUE", dw - 1, 0, reset, str(r.get("description", "")))
            )

        # overlapping fields?
        used = 0
        for f in sorted(fields, key=lambda f: f.lsb):
            if used & f.mask:
                errors.append(f"{where}: field {f.name} overlaps another field")
            used |= f.mask
        registers.append(
            Register(
                rname,
                offset,
                access,
                str(r.get("description", "")),
                sorted(fields, key=lambda f: -f.lsb),
            )
        )

    seen = {}
    for reg in registers:
        if reg.offset in seen:
            errors.append(
                f"register {reg.name}: offset 0x{reg.offset:X} already used by {seen[reg.offset]}"
            )
        seen[reg.offset] = reg.name
    names = [r.name for r in registers]
    for n in set(names):
        if names.count(n) > 1:
            errors.append(f"register name {n} used more than once")
    if not registers:
        errors.append("spec has no registers")
    if errors:
        raise RegMapError("Register map has errors:\n  - " + "\n  - ".join(errors))

    max_addr = max(r.offset for r in registers) + bytes_per_reg - 1
    addr_width = _to_int(
        data.get("addr_width", max(max_addr.bit_length(), 2)), "addr_width"
    )
    if max_addr >> addr_width:
        raise RegMapError(
            f"addr_width {addr_width} too small for offset 0x{max_addr:X}"
        )

    return RegMap(
        block=block,
        base_address=_to_int(data.get("base_address", 0), "base_address"),
        data_width=dw,
        addr_width=addr_width,
        registers=sorted(registers, key=lambda r: r.offset),
        description=str(data.get("description", "")),
    )


# --------------------------------------------------------------------------
# Verilog
# --------------------------------------------------------------------------


def _hex(value, width):
    return f"{width}'h{value:0{(width + 3) // 4}X}"


def gen_verilog(rm):
    dw, aw = rm.data_width, rm.addr_width
    mod = f"{rm.block}_regs"
    rng = "[DATA_WIDTH-1:0]"
    out = []
    a = out.append
    a("`timescale 1ns/1ps")
    a("// " + "=" * 70)
    a(f"// {mod}: register file for block '{rm.block}'")
    a(
        f"// Auto-generated by VLSI Toolkit on {date.today().isoformat()}. DO NOT EDIT BY HAND -"
    )
    a("// change the spec file and regenerate instead.")
    a("//")
    a("// Bus: simple synchronous write (wr_en), combinational read (rd_en).")
    a("// " + "=" * 70)
    a(f"module {mod} #(")
    a(f"    parameter ADDR_WIDTH = {aw},  // fixed by the spec - do not override")
    a(f"    parameter DATA_WIDTH = {dw}")
    a(") (")
    ports = [
        "input  wire                  clk",
        "input  wire                  rst_n",
        "input  wire                  wr_en",
        "input  wire                  rd_en",
        "input  wire [ADDR_WIDTH-1:0] addr",
        "input  wire [DATA_WIDTH-1:0] wdata",
        "output reg  [DATA_WIDTH-1:0] rdata",
    ]
    for r in rm.registers:
        n = r.name.lower()
        if r.access == "RO":
            ports.append(
                f"input  wire {rng} {n}_i      // {r.name} (RO) hardware value"
            )
        elif r.access == "W1C":
            ports.append(
                f"input  wire {rng} {n}_set_i  // {r.name} (W1C) set pulses from hardware"
            )
            ports.append(
                f"output wire {rng} {n}_o      // {r.name} (W1C) current value"
            )
        else:
            ports.append(f"output wire {rng} {n}_o      // {r.name} ({r.access})")
    for i, p in enumerate(ports):
        code, _, comment = p.partition("//")
        sep = "," if i < len(ports) - 1 else ""
        a(f"    {code.rstrip()}{sep}" + (f"  //{comment}" if comment else ""))
    a(");")
    a("")
    a("    // ---------------- Addresses, masks and reset values ----------------")
    for r in rm.registers:
        a(f"    localparam [ADDR_WIDTH-1:0] ADDR_{r.name} = {_hex(r.offset, aw)};")
        a(f"    localparam [DATA_WIDTH-1:0] {r.name}_MASK  = {_hex(r.mask, dw)};")
        a(f"    localparam [DATA_WIDTH-1:0] {r.name}_RESET = {_hex(r.reset, dw)};")
    a("")

    for r in rm.registers:
        n = r.name.lower()
        hit = f"wr_en && (addr == ADDR_{r.name})"
        a(
            f"    // ---------------- {r.name} ({r.access}) @ 0x{r.offset:02X}: {r.description} ----------------"
        )
        if r.access in ("RW", "WO"):
            a(f"    reg {rng} {n}_q;")
            a("    always @(posedge clk or negedge rst_n) begin")
            a(f"        if (!rst_n)")
            a(f"            {n}_q <= {r.name}_RESET;")
            a(f"        else if ({hit})")
            a(f"            {n}_q <= wdata & {r.name}_MASK;")
            a("    end")
            a(f"    assign {n}_o = {n}_q;")
        elif r.access == "W1C":
            a(f"    reg  {rng} {n}_q;")
            a(
                f"    wire {rng} {n}_clr = ({hit}) ? (wdata & {r.name}_MASK) : {{DATA_WIDTH{{1'b0}}}};"
            )
            a("    always @(posedge clk or negedge rst_n) begin")
            a(f"        if (!rst_n)")
            a(f"            {n}_q <= {r.name}_RESET;")
            a("        else")
            a(
                f"            {n}_q <= ({n}_q & ~{n}_clr) | ({n}_set_i & {r.name}_MASK);  // set wins"
            )
            a("    end")
            a(f"    assign {n}_o = {n}_q;")
        else:
            a(f"    // read-only: value comes from {n}_i")
        a("")

    a("    // ---------------- Read mux ----------------")
    a("    always @(*) begin")
    a("        rdata = {DATA_WIDTH{1'b0}};")
    a("        if (rd_en) begin")
    a("            case (addr)")
    for r in rm.registers:
        n = r.name.lower()
        if r.access == "RO":
            a(f"                ADDR_{r.name}: rdata = {n}_i & {r.name}_MASK;")
        elif r.access == "WO":
            a(
                f"                ADDR_{r.name}: rdata = {{DATA_WIDTH{{1'b0}}}};  // write-only"
            )
        else:
            a(f"                ADDR_{r.name}: rdata = {n}_q;")
    a("                default: rdata = {DATA_WIDTH{1'b0}};")
    a("            endcase")
    a("        end")
    a("    end")
    a("")
    a("endmodule")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# AXI4-Lite slave
# --------------------------------------------------------------------------


def gen_axi_lite(rm):
    """Standalone AXI4-Lite slave containing all registers (byte strobes, SLVERR on unmapped addresses)."""
    dw, aw = rm.data_width, rm.addr_width
    nb = dw // 8
    mod = f"{rm.block}_axil"
    rng = "[DATA_WIDTH-1:0]"
    writable = [r for r in rm.registers if r.access in ("RW", "WO", "W1C")]
    align = ((1 << aw) - 1) & ~(nb - 1)
    out = []
    a = out.append
    a("`timescale 1ns/1ps")
    a("// " + "=" * 74)
    a(f"// {mod}: AXI4-Lite slave with the registers of block '{rm.block}'")
    a(
        f"// Auto-generated by VLSI Toolkit on {date.today().isoformat()}. DO NOT EDIT BY HAND -"
    )
    a("// change the register spec and regenerate instead.")
    a("//")
    a(
        "//  * write address (AW) and write data (W) are accepted independently, in any order"
    )
    a(
        "//  * WSTRB byte enables are honoured; bits outside the defined fields read as 0"
    )
    a(
        "//  * unmapped addresses answer SLVERR; writes to read-only registers are ignored (OKAY)"
    )
    a(
        "//  * one outstanding write and one outstanding read at a time (fine for register access)"
    )
    a("// " + "=" * 74)
    a(f"module {mod} #(")
    a(f"    parameter ADDR_WIDTH = {aw},  // fixed by the spec - do not override")
    a(f"    parameter DATA_WIDTH = {dw}")
    a(") (")
    ports = [
        "input  wire                    s_axil_aclk",
        "input  wire                    s_axil_aresetn",
        "// write address channel",
        "input  wire                    s_axil_awvalid",
        "output wire                    s_axil_awready",
        "input  wire [ADDR_WIDTH-1:0]   s_axil_awaddr",
        "input  wire [2:0]              s_axil_awprot",
        "// write data channel",
        "input  wire                    s_axil_wvalid",
        "output wire                    s_axil_wready",
        "input  wire [DATA_WIDTH-1:0]   s_axil_wdata",
        "input  wire [DATA_WIDTH/8-1:0] s_axil_wstrb",
        "// write response channel",
        "output reg                     s_axil_bvalid",
        "input  wire                    s_axil_bready",
        "output reg  [1:0]              s_axil_bresp",
        "// read address channel",
        "input  wire                    s_axil_arvalid",
        "output wire                    s_axil_arready",
        "input  wire [ADDR_WIDTH-1:0]   s_axil_araddr",
        "input  wire [2:0]              s_axil_arprot",
        "// read data channel",
        "output reg                     s_axil_rvalid",
        "input  wire                    s_axil_rready",
        "output reg  [DATA_WIDTH-1:0]   s_axil_rdata",
        "output reg  [1:0]              s_axil_rresp",
        "// hardware side",
    ]
    for r in rm.registers:
        n = r.name.lower()
        if r.access == "RO":
            ports.append(
                f"input  wire {rng}   {n}_i      // {r.name} (RO) value from hardware"
            )
        elif r.access == "W1C":
            ports.append(
                f"input  wire {rng}   {n}_set_i  // {r.name} (W1C) set pulses from hardware"
            )
            ports.append(
                f"output wire {rng}   {n}_o      // {r.name} (W1C) current flags"
            )
        else:
            ports.append(f"output wire {rng}   {n}_o      // {r.name} ({r.access})")
    signal_ports = [p for p in ports if not p.startswith("//")]
    for p in ports:
        if p.startswith("//"):
            a(f"    {p}")
            continue
        code, _, comment = p.partition("//")
        sep = "," if p != signal_ports[-1] else ""
        a(f"    {code.rstrip()}{sep}" + (f"  //{comment}" if comment else ""))
    a(");")
    a("")
    a("    localparam [1:0] RESP_OKAY = 2'b00, RESP_SLVERR = 2'b10;")
    a(
        f"    localparam [ADDR_WIDTH-1:0] ALIGN = {_hex(align, aw)};  // word-aligned address"
    )
    for r in rm.registers:
        a(f"    localparam [ADDR_WIDTH-1:0] ADDR_{r.name} = {_hex(r.offset, aw)};")
        a(f"    localparam [DATA_WIDTH-1:0] {r.name}_MASK  = {_hex(r.mask, dw)};")
        if r.access != "RO":
            a(f"    localparam [DATA_WIDTH-1:0] {r.name}_RESET = {_hex(r.reset, dw)};")
    a("")
    a("    wire clk   = s_axil_aclk;")
    a("    wire rst_n = s_axil_aresetn;")
    a("")
    a(
        "    // ---------------- write channel: capture AW and W independently ----------------"
    )
    a("    reg                    aw_full, w_full;")
    a("    reg [ADDR_WIDTH-1:0]   aw_addr;")
    a("    reg [DATA_WIDTH-1:0]   w_data;")
    a("    reg [DATA_WIDTH/8-1:0] w_strb;")
    a("    assign s_axil_awready = !aw_full && !s_axil_bvalid;")
    a("    assign s_axil_wready  = !w_full  && !s_axil_bvalid;")
    a("    wire do_write = aw_full && w_full && !s_axil_bvalid;")
    a("    wire [ADDR_WIDTH-1:0] w_addr = aw_addr & ALIGN;")
    a("")
    a("    // WSTRB expanded to a bit mask")
    a("    wire [DATA_WIDTH-1:0] strb_bits;")
    a("    genvar gi;")
    a("    generate")
    a("        for (gi = 0; gi < DATA_WIDTH/8; gi = gi + 1) begin : g_strb")
    a("            assign strb_bits[8*gi +: 8] = {8{w_strb[gi]}};")
    a("        end")
    a("    endgenerate")
    a("")
    hit_terms = (
        " ||\n                     ".join(
            f"(w_addr == ADDR_{r.name})" for r in rm.registers
        )
        or "1'b0"
    )
    a(f"    wire w_mapped = {hit_terms};")
    a("")
    a("    always @(posedge clk or negedge rst_n) begin")
    a("        if (!rst_n) begin")
    a("            aw_full       <= 1'b0;")
    a("            w_full        <= 1'b0;")
    a("            aw_addr       <= {ADDR_WIDTH{1'b0}};")
    a("            w_data        <= {DATA_WIDTH{1'b0}};")
    a("            w_strb        <= {(DATA_WIDTH/8){1'b0}};")
    a("            s_axil_bvalid <= 1'b0;")
    a("            s_axil_bresp  <= RESP_OKAY;")
    a("        end else begin")
    a("            if (s_axil_awvalid && s_axil_awready) begin")
    a("                aw_full <= 1'b1;")
    a("                aw_addr <= s_axil_awaddr;")
    a("            end")
    a("            if (s_axil_wvalid && s_axil_wready) begin")
    a("                w_full <= 1'b1;")
    a("                w_data <= s_axil_wdata;")
    a("                w_strb <= s_axil_wstrb;")
    a("            end")
    a("            if (do_write) begin")
    a("                aw_full       <= 1'b0;")
    a("                w_full        <= 1'b0;")
    a("                s_axil_bvalid <= 1'b1;")
    a("                s_axil_bresp  <= w_mapped ? RESP_OKAY : RESP_SLVERR;")
    a("            end else if (s_axil_bvalid && s_axil_bready) begin")
    a("                s_axil_bvalid <= 1'b0;")
    a("            end")
    a("        end")
    a("    end")
    a("")
    for r in writable:
        n = r.name.lower()
        a(
            f"    // ---------------- {r.name} ({r.access}) @ 0x{r.offset:02X}: {r.description} ----------------"
        )
        a(f"    reg  {rng} {n}_q;")
        if r.access == "W1C":
            a(
                f"    wire {rng} {n}_clr = (do_write && w_addr == ADDR_{r.name}) ? (w_data & strb_bits & {r.name}_MASK) : {{DATA_WIDTH{{1'b0}}}};"
            )
            a("    always @(posedge clk or negedge rst_n) begin")
            a(f"        if (!rst_n) {n}_q <= {r.name}_RESET;")
            a(
                f"        else        {n}_q <= ({n}_q & ~{n}_clr) | ({n}_set_i & {r.name}_MASK);  // set wins"
            )
            a("    end")
        else:
            a("    always @(posedge clk or negedge rst_n) begin")
            a(f"        if (!rst_n)")
            a(f"            {n}_q <= {r.name}_RESET;")
            a(f"        else if (do_write && w_addr == ADDR_{r.name})")
            a(
                f"            {n}_q <= ({n}_q & ~strb_bits) | (w_data & strb_bits & {r.name}_MASK);"
            )
            a("    end")
        a(f"    assign {n}_o = {n}_q;")
        a("")
    a("    // ---------------- read channel ----------------")
    a("    wire [ADDR_WIDTH-1:0] r_addr = s_axil_araddr & ALIGN;")
    a("    reg  [DATA_WIDTH-1:0] r_value;")
    a("    reg                   r_mapped;")
    a("    always @(*) begin")
    a("        r_mapped = 1'b1;")
    a("        case (r_addr)")
    for r in rm.registers:
        n = r.name.lower()
        expr = {"RO": f"{n}_i & {r.name}_MASK", "WO": "{DATA_WIDTH{1'b0}}"}.get(
            r.access, f"{n}_q"
        )
        note = "  // write-only: reads return 0" if r.access == "WO" else ""
        a(f"            ADDR_{r.name}: r_value = {expr};{note}")
    a("            default: begin r_value = {DATA_WIDTH{1'b0}}; r_mapped = 1'b0; end")
    a("        endcase")
    a("    end")
    a("")
    a("    assign s_axil_arready = !s_axil_rvalid;")
    a("    always @(posedge clk or negedge rst_n) begin")
    a("        if (!rst_n) begin")
    a("            s_axil_rvalid <= 1'b0;")
    a("            s_axil_rdata  <= {DATA_WIDTH{1'b0}};")
    a("            s_axil_rresp  <= RESP_OKAY;")
    a("        end else if (s_axil_arvalid && s_axil_arready) begin")
    a("            s_axil_rvalid <= 1'b1;")
    a("            s_axil_rdata  <= r_value;")
    a("            s_axil_rresp  <= r_mapped ? RESP_OKAY : RESP_SLVERR;")
    a("        end else if (s_axil_rvalid && s_axil_rready) begin")
    a("            s_axil_rvalid <= 1'b0;")
    a("        end")
    a("    end")
    a("")
    a("    // AWPROT / ARPROT are accepted but not used")
    a("    wire unused_prot = ^{s_axil_awprot, s_axil_arprot};")
    a("")
    a("endmodule")
    return "\n".join(out) + "\n"


def gen_axi_lite_tb(rm):
    """Self-checking testbench for gen_axi_lite(): resets, read-back, byte strobes, W1C, SLVERR.

    Prints TEST PASSED / TEST FAILED and dumps a VCD that the AXI protocol checker can read.
    """
    dw, aw, nb = rm.data_width, rm.addr_width, rm.data_width // 8
    mod = f"{rm.block}_axil"
    tb = f"tb_{mod}"
    ro_pattern = int(("A5" * nb)[: dw // 4], 16)
    used = {r.offset for r in rm.registers}
    unmapped = next((o for o in range(0, 1 << aw, nb) if o not in used), None)
    full = (1 << dw) - 1
    out = []
    a = out.append
    a("`timescale 1ns/1ps")
    a(
        f"// Self-checking testbench for {mod} (auto-generated by VLSI Toolkit on {date.today().isoformat()})"
    )
    a(f"// Run:  iverilog -g2012 -o sim.out {tb}.v {mod}.v && vvp sim.out")
    a(f"// Then check the bus with:  python vlsi.py axi {tb}.vcd")
    a(f"module {tb};")
    a(f"    localparam AW = {aw}, DW = {dw}, NB = {nb};")
    a("    reg clk = 1'b0, rst_n = 1'b0;")
    a("    always #5 clk = ~clk;")
    a("")
    a("    reg           awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;")
    a("    reg  [AW-1:0] awaddr = 0, araddr = 0;")
    a("    reg  [DW-1:0] wdata = 0;")
    a("    reg  [NB-1:0] wstrb = 0;")
    a("    wire          awready, wready, bvalid, arready, rvalid;")
    a("    wire [1:0]    bresp, rresp;")
    a("    wire [DW-1:0] rdata;")
    for r in rm.registers:
        n = r.name.lower()
        if r.access == "RO":
            a(f"    wire [DW-1:0] {n}_i = {_hex(ro_pattern, dw)};")
        elif r.access == "W1C":
            a(f"    reg  [DW-1:0] {n}_set_i = 0;")
            a(f"    wire [DW-1:0] {n}_o;")
        else:
            a(f"    wire [DW-1:0] {n}_o;")
    a("")
    conns = [
        ".s_axil_aclk(clk)",
        ".s_axil_aresetn(rst_n)",
        ".s_axil_awvalid(awvalid)",
        ".s_axil_awready(awready)",
        ".s_axil_awaddr(awaddr)",
        ".s_axil_awprot(3'b000)",
        ".s_axil_wvalid(wvalid)",
        ".s_axil_wready(wready)",
        ".s_axil_wdata(wdata)",
        ".s_axil_wstrb(wstrb)",
        ".s_axil_bvalid(bvalid)",
        ".s_axil_bready(bready)",
        ".s_axil_bresp(bresp)",
        ".s_axil_arvalid(arvalid)",
        ".s_axil_arready(arready)",
        ".s_axil_araddr(araddr)",
        ".s_axil_arprot(3'b000)",
        ".s_axil_rvalid(rvalid)",
        ".s_axil_rready(rready)",
        ".s_axil_rdata(rdata)",
        ".s_axil_rresp(rresp)",
    ]
    for r in rm.registers:
        n = r.name.lower()
        if r.access == "RO":
            conns.append(f".{n}_i({n}_i)")
        elif r.access == "W1C":
            conns += [f".{n}_set_i({n}_set_i)", f".{n}_o({n}_o)"]
        else:
            conns.append(f".{n}_o({n}_o)")
    a(f"    {mod} dut (")
    for i, cn in enumerate(conns):
        a(f"        {cn}{',' if i < len(conns) - 1 else ''}")
    a("    );")
    a("")
    a("    integer errors = 0;")
    a("    reg [1:0] resp;")
    a("    reg [DW-1:0] value;")
    a("")
    a("    // write: AW and W presented together, each dropped after its own handshake")
    a(
        "    task axi_write(input [AW-1:0] addr, input [DW-1:0] data, input [NB-1:0] strb);"
    )
    a("        reg aw_done, w_done;")
    a("        begin")
    a("            @(negedge clk);")
    a("            awvalid = 1; awaddr = addr; wvalid = 1; wdata = data; wstrb = strb;")
    a("            aw_done = 0; w_done = 0;")
    a("            while (!(aw_done && w_done)) begin")
    a("                @(posedge clk);")
    a("                if (awvalid && awready) aw_done = 1;")
    a("                if (wvalid && wready) w_done = 1;")
    a("                @(negedge clk);")
    a("                if (aw_done) awvalid = 0;")
    a("                if (w_done) wvalid = 0;")
    a("            end")
    a("            bready = 1;")
    a("            @(posedge clk); while (!bvalid) @(posedge clk);")
    a("            resp = bresp;")
    a("            @(negedge clk); bready = 0;")
    a("        end")
    a("    endtask")
    a("")
    a("    task axi_read(input [AW-1:0] addr);")
    a("        begin")
    a("            @(negedge clk); arvalid = 1; araddr = addr;")
    a("            @(posedge clk); while (!arready) @(posedge clk);")
    a("            @(negedge clk); arvalid = 0; rready = 1;")
    a("            @(posedge clk); while (!rvalid) @(posedge clk);")
    a("            value = rdata; resp = rresp;")
    a("            @(negedge clk); rready = 0;")
    a("        end")
    a("    endtask")
    a("")
    a("    task check_eq(input [255:0] what, input [DW-1:0] got, input [DW-1:0] exp);")
    a("        if (got !== exp) begin")
    a('            $display("ERROR: %0s: got 0x%h, expected 0x%h", what, got, exp);')
    a("            errors = errors + 1;")
    a("        end")
    a("    endtask")
    a("")
    a("    initial begin")
    a(f'        $dumpfile("{tb}.vcd");')
    a(f"        $dumpvars(0, {tb});")
    a("        repeat (4) @(posedge clk);")
    a("        rst_n = 1;")
    a("")
    a("        // 1. reset values")
    for r in rm.registers:
        if r.access == "WO":
            continue
        exp = (ro_pattern & r.mask) if r.access == "RO" else r.reset
        a(
            f'        axi_read({_hex(r.offset, aw)}); check_eq("{r.name} reset value", value, {_hex(exp, dw)});'
        )
    a("")
    a("        // 2. write all ones, read back: only the defined bits stick")
    for r in rm.registers:
        if r.access == "RW":
            a(
                f'        axi_write({_hex(r.offset, aw)}, {_hex(full, dw)}, {{NB{{1\'b1}}}}); check_eq("{r.name} write resp", resp, 0);'
            )
            a(
                f'        axi_read({_hex(r.offset, aw)}); check_eq("{r.name} read-back", value, {_hex(r.mask, dw)});'
            )
    rw = next((r for r in rm.registers if r.access == "RW"), None)
    if rw:
        a("")
        a("        // 3. byte strobes: only byte 0 is written")
        a(f"        axi_write({_hex(rw.offset, aw)}, {_hex(0, dw)}, {{NB{{1'b1}}}});")
        a(f"        axi_write({_hex(rw.offset, aw)}, {_hex(full, dw)}, {_hex(1, nb)});")
        a(
            f'        axi_read({_hex(rw.offset, aw)}); check_eq("{rw.name} byte-strobe write", value, {_hex(0xFF & rw.mask, dw)});'
        )
    w1c = next((r for r in rm.registers if r.access == "W1C"), None)
    if w1c:
        n = w1c.name.lower()
        a("")
        a("        // 4. W1C: hardware sets the flags, software writes 1 to clear")
        a(
            f"        @(negedge clk); {n}_set_i = {_hex(w1c.mask, dw)}; @(negedge clk); {n}_set_i = 0;"
        )
        a(
            f'        axi_read({_hex(w1c.offset, aw)}); check_eq("{w1c.name} after set", value, {_hex(w1c.mask, dw)});'
        )
        a(
            f"        axi_write({_hex(w1c.offset, aw)}, {_hex(w1c.mask, dw)}, {{NB{{1'b1}}}});"
        )
        a(
            f'        axi_read({_hex(w1c.offset, aw)}); check_eq("{w1c.name} after clear", value, 0);'
        )
    if unmapped is not None:
        a("")
        a("        // 5. unmapped address answers SLVERR")
        a(
            f'        axi_write({_hex(unmapped, aw)}, 0, {{NB{{1\'b1}}}}); check_eq("unmapped write resp", resp, 2);'
        )
        a(
            f'        axi_read({_hex(unmapped, aw)}); check_eq("unmapped read resp", resp, 2);'
        )
    a("")
    a("        repeat (4) @(posedge clk);")
    a('        if (errors == 0) $display("TEST PASSED");')
    a('        else $display("TEST FAILED: %0d error(s)", errors);')
    a("        $finish;")
    a("    end")
    a("endmodule")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# C header
# --------------------------------------------------------------------------


def gen_c_header(rm):
    dw = rm.data_width
    ctype = f"uint{dw}_t"
    suffix = "ULL" if dw == 64 else "U"
    digits = dw // 4
    P = rm.block.upper()
    guard = f"{P}_REGS_H"
    out = []
    a = out.append
    a(
        f"/* {rm.block}_regs.h - auto-generated by VLSI Toolkit on {date.today().isoformat()}. DO NOT EDIT. */"
    )
    a(f"#ifndef {guard}")
    a(f"#define {guard}")
    a("")
    a("#include <stdint.h>")
    a("")
    a(f"#define {P}_BASE_ADDR 0x{rm.base_address:08X}UL")
    a("")
    a(f"#define {P}_REG(offset)  (*(volatile {ctype} *)({P}_BASE_ADDR + (offset)))")
    a("")
    for r in rm.registers:
        a(f"/* {r.name} ({r.access}) - {r.description} */")
        a(f"#define {P}_{r.name}_OFFSET 0x{r.offset:02X}U")
        a(f"#define {P}_{r.name}_ADDR   ({P}_BASE_ADDR + {P}_{r.name}_OFFSET)")
        a(f"#define {P}_{r.name}_RESET  0x{r.reset:0{digits}X}{suffix}")
        for f in r.fields:
            if f.name == "VALUE" and len(r.fields) == 1:
                continue
            a(f"#define {P}_{r.name}_{f.name}_SHIFT {f.lsb}U")
            a(
                f"#define {P}_{r.name}_{f.name}_MASK  0x{f.mask:0{digits}X}{suffix}  /* bits {f.bits} */"
            )
        a("")
    a(f"#endif /* {guard} */")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# HTML documentation
# --------------------------------------------------------------------------

_CSS = """
:root { --bg:#ffffff; --fg:#1d2330; --muted:#5b6475; --line:#d9dee7; --head:#f2f4f8; --accent:#2f5bd3; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14171d; --fg:#e6e9ef; --muted:#9aa3b2; --line:#2c323d; --head:#1c2028; --accent:#7ea2ff; }
}
body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:960px; padding:24px 16px; }
h1 { margin-bottom:4px; } h2 { margin-top:36px; border-bottom:1px solid var(--line); padding-bottom:4px; }
.meta { color:var(--muted); }
table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }
th, td { border:1px solid var(--line); padding:6px 10px; text-align:left; vertical-align:top; }
th { background:var(--head); }
code { font-family: ui-monospace, Consolas, monospace; }
.acc { font-weight:600; color:var(--accent); }
a { color:var(--accent); }
"""


def gen_html(rm):
    e = html.escape
    digits = rm.data_width // 4
    out = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{e(rm.block)} registers</title><style>{_CSS}</style></head><body>",
        f"<h1>{e(rm.block.upper())} register map</h1>",
        f"<p class='meta'>Base address <code>0x{rm.base_address:08X}</code> &middot; "
        f"{rm.data_width}-bit registers &middot; generated {date.today().isoformat()}</p>",
    ]
    if rm.description:
        out.append(f"<p>{e(rm.description)}</p>")
    out.append(
        "<h2>Summary</h2><table><tr><th>Offset</th><th>Name</th><th>Access</th><th>Reset</th><th>Description</th></tr>"
    )
    for r in rm.registers:
        out.append(
            f"<tr><td><code>0x{r.offset:02X}</code></td><td><a href='#{e(r.name)}'>{e(r.name)}</a></td>"
            f"<td class='acc'>{r.access}</td><td><code>0x{r.reset:0{digits}X}</code></td><td>{e(r.description)}</td></tr>"
        )
    out.append("</table>")
    for r in rm.registers:
        out.append(
            f"<h2 id='{e(r.name)}'>{e(r.name)} <span class='meta'>@ 0x{r.offset:02X} &middot; {r.access}</span></h2>"
        )
        if r.description:
            out.append(f"<p>{e(r.description)}</p>")
        out.append(
            "<table><tr><th>Bits</th><th>Field</th><th>Reset</th><th>Description</th></tr>"
        )
        for f in r.fields:
            out.append(
                f"<tr><td><code>[{f.bits}]</code></td><td>{e(f.name)}</td>"
                f"<td><code>0x{f.reset:X}</code></td><td>{e(f.description)}</td></tr>"
            )
        out.append("</table>")
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def generate_all(spec_path, out_dir):
    """Generate .v, .h and .html files. Returns the list of written paths."""
    rm = load_spec(spec_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        out_dir / f"{rm.block}_regs.v": gen_verilog(rm),
        out_dir / f"{rm.block}_regs.h": gen_c_header(rm),
        out_dir / f"{rm.block}_regs.html": gen_html(rm),
        out_dir / f"{rm.block}_axil.v": gen_axi_lite(rm),
        out_dir / f"tb_{rm.block}_axil.v": gen_axi_lite_tb(rm),
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    return rm, list(files)
