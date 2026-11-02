"""Protocol checkers and decoders for VCD waveforms: APB, AHB-Lite, AXI-Stream, SPI, I2C, UART.

Interfaces are found from signal names (any prefix): APB `psel/penable/pwrite/paddr`, AHB-Lite
`htrans/haddr/hwrite/hready`, AXI-Stream `tvalid/tdata`, SPI `sclk + mosi/miso + cs`, I2C `scl + sda`,
UART a `tx/rx/txd/rxd` line (baud rate detected from the shortest bit).

    analyze_vcd_text(text, timeout=16) -> {"interfaces": [{protocol, interface, violations, transactions, stats, ...}],
                                           "rules": [...], "timescale"}

Every interface report has the same shape, so one page can show any protocol.
"""

import re
from collections import Counter

from .axi import _Sampler, _find_named, _hex, _int, _known, _rising_edges
from .vcd_analyzer import parse_text as parse_vcd

SEVERITY = {
    # APB
    "APB_ENABLE_WITHOUT_SETUP": "ERROR", "APB_SETUP_NOT_FOLLOWED": "ERROR", "APB_CHANGED_IN_ACCESS": "ERROR",
    "APB_SEL_DROPPED": "ERROR", "APB_X_CONTROL": "ERROR", "APB_TIMEOUT": "WARNING", "APB_SLVERR": "WARNING",
    # AHB-Lite
    "AHB_SEQ_WITHOUT_NONSEQ": "ERROR", "AHB_CHANGED_IN_WAIT": "ERROR", "AHB_BAD_INCREMENT": "ERROR",
    "AHB_1KB_BOUNDARY": "ERROR", "AHB_ERROR_RESPONSE": "WARNING", "AHB_BAD_ERROR_RESPONSE": "ERROR",
    "AHB_X_CONTROL": "ERROR", "AHB_TIMEOUT": "WARNING",
    # AXI-Stream
    "AXIS_VALID_DROPPED": "ERROR", "AXIS_PAYLOAD_CHANGED": "ERROR", "AXIS_X_ON_VALID": "ERROR",
    "AXIS_X_ON_DATA": "ERROR", "AXIS_NULL_BYTES": "WARNING", "AXIS_READY_TIMEOUT": "WARNING",
    "AXIS_UNTERMINATED": "WARNING",
    # SPI
    "SPI_PARTIAL_BYTE": "WARNING", "SPI_X_DATA": "ERROR", "SPI_CLOCK_WHILE_IDLE": "WARNING",
    # I2C
    "I2C_UNEXPECTED_CONDITION": "ERROR", "I2C_ADDRESS_NACK": "WARNING", "I2C_NO_STOP": "WARNING",
    # UART
    "UART_FRAMING_ERROR": "ERROR", "UART_BREAK": "WARNING", "UART_GLITCH": "WARNING",
}
RULE_HELP = {
    "APB_ENABLE_WITHOUT_SETUP": "PENABLE rose without a SETUP cycle (PSEL=1, PENABLE=0) just before.",
    "APB_SETUP_NOT_FOLLOWED": "A SETUP cycle must be followed by an ACCESS cycle (PENABLE=1).",
    "APB_CHANGED_IN_ACCESS": "PADDR, PWRITE or PWDATA changed between SETUP and the end of the transfer.",
    "APB_SEL_DROPPED": "PSEL went low while the slave was still inserting wait states (PREADY=0).",
    "APB_X_CONTROL": "PSEL, PENABLE or the address is unknown (X/Z) during a transfer.",
    "APB_TIMEOUT": "PREADY stayed low for longer than the timeout.",
    "APB_SLVERR": "The slave answered PSLVERR.",
    "AHB_SEQ_WITHOUT_NONSEQ": "HTRANS=SEQ must continue a burst started by NONSEQ.",
    "AHB_CHANGED_IN_WAIT": "Address or control changed while HREADY was low (the address phase must be held).",
    "AHB_BAD_INCREMENT": "In an INCR burst each SEQ address must be the previous one plus the transfer size.",
    "AHB_1KB_BOUNDARY": "An AHB burst must not cross a 1 KB address boundary.",
    "AHB_ERROR_RESPONSE": "The slave answered HRESP=ERROR.",
    "AHB_BAD_ERROR_RESPONSE": "An ERROR response must take two cycles: first HREADY=0, then HREADY=1.",
    "AHB_X_CONTROL": "HTRANS or the address is unknown (X/Z) while HREADY is high.",
    "AHB_TIMEOUT": "HREADY stayed low for longer than the timeout.",
    "AXIS_VALID_DROPPED": "TVALID fell before TREADY: the beat was withdrawn.",
    "AXIS_PAYLOAD_CHANGED": "TDATA/TLAST/TKEEP changed while TVALID was high and TREADY low.",
    "AXIS_X_ON_VALID": "TVALID is unknown (X/Z).",
    "AXIS_X_ON_DATA": "TDATA is unknown (X/Z) during a transfer.",
    "AXIS_NULL_BYTES": "TKEEP has null bytes in a beat that is not the last of its packet.",
    "AXIS_READY_TIMEOUT": "TREADY stayed low for longer than the timeout (back-pressure).",
    "AXIS_UNTERMINATED": "The dump ended in the middle of a packet (no TLAST).",
    "SPI_PARTIAL_BYTE": "Chip select was released after a number of bits that is not a multiple of 8.",
    "SPI_X_DATA": "MOSI/MISO is unknown (X/Z) at a sampling edge.",
    "SPI_CLOCK_WHILE_IDLE": "SCLK toggled while chip select was inactive.",
    "I2C_UNEXPECTED_CONDITION": "SDA changed while SCL was high in the middle of a byte, which the bus sees as a START or STOP.",
    "I2C_ADDRESS_NACK": "No device acknowledged the address byte.",
    "I2C_NO_STOP": "The dump ended without a STOP condition.",
    "UART_FRAMING_ERROR": "The stop bit was 0: wrong baud rate, wrong frame format or a corrupted byte.",
    "UART_BREAK": "The line was held low for a whole frame (break condition).",
    "UART_GLITCH": "A start bit that did not last half a bit time (noise).",
}
PROTOCOL_RULES = {p: [r for r in SEVERITY if r.startswith(k)] for p, k in
                  [("APB", "APB_"), ("AHB-Lite", "AHB_"), ("AXI-Stream", "AXIS_"), ("SPI", "SPI_"), ("I2C", "I2C_"), ("UART", "UART_")]}


# ============================================================================ helpers

class _Report:
    def __init__(self, protocol, prefix, vcd, clock=None):
        self.protocol, self.prefix, self.vcd, self.clock = protocol, prefix, vcd, clock
        self.violations, self.transactions, self.stats = [], [], {}
        self.signals, self.extra = {}, {}

    def add(self, rule, cycle, time, message):
        self.violations.append({"rule": rule, "severity": SEVERITY[rule], "cycle": cycle, "time": time, "message": message})

    def result(self):
        self.violations.sort(key=lambda v: (v["time"], v["rule"]))
        sev = Counter(v["severity"] for v in self.violations)
        return {
            "protocol": self.protocol, "interface": (self.prefix or "").rstrip("._") or "(top)", "clock": self.clock,
            "signals": {k: v for k, v in self.signals.items() if v}, "timescale": self.vcd.timescale_text,
            "violations": self.violations, "transactions": self.transactions,
            "stats": self.stats | {"errors": sev.get("ERROR", 0), "warnings": sev.get("WARNING", 0),
                                   "transactions": len(self.transactions)},
            "rules": [{"rule": r, "severity": SEVERITY[r], "description": RULE_HELP[r]} for r in PROTOCOL_RULES[self.protocol]],
            **self.extra,
        }


def _group(vcd, pattern):
    """Group signals by '<scope>.<prefix>' using a leaf regex with groups (prefix, field)."""
    groups = {}
    for full in vcd.signals:
        scope, _, leaf = full.rpartition(".")
        m = pattern.match(leaf)
        if m:
            key = (scope + "." if scope else "") + m.group(1)
            groups.setdefault(key, {})[m.group(2).lower()] = full
    return groups


def _clock_for(vcd, prefix, names):
    scope = prefix.rpartition(".")[0]
    return _find_named(vcd, scope, names, prefix)


def _width(vcd, name):
    return vcd.signals[name].width if name and name in vcd.signals else None


def _ascii(byte_values):
    return "".join(chr(b) if 32 <= b < 127 else "·" for b in byte_values)


# ============================================================================ APB

_APB_RE = re.compile(r"^(.*?)(psel\w*|penable|pwrite|paddr|pwdata|prdata|pready|pslverr|pprot|pstrb)$", re.I)


def _find_apb(vcd):
    out = []
    for prefix, s in _group(vcd, _APB_RE).items():
        sel = next((v for k, v in s.items() if k.startswith("psel")), None)
        if sel and "penable" in s and "paddr" in s:
            s["psel"] = sel
            out.append((prefix, s, _clock_for(vcd, prefix, ["pclk", "clk", "aclk", "clock"])))
    return out


def check_apb(vcd, prefix, s, clock, timeout=16):
    rep = _Report("APB", prefix, vcd, clock)
    rep.signals = {k: s.get(k) for k in ("psel", "penable", "pwrite", "paddr", "pwdata", "prdata", "pready", "pslverr")}
    if not clock:
        rep.extra["error"] = "No clock (pclk/clk) found next to the APB signals."
        return rep.result()
    edges = _rising_edges(vcd, clock)
    sm = _Sampler(vcd, [n for n in rep.signals.values() if n])
    awidth, dwidth = _width(vcd, s.get("paddr")), _width(vcd, s.get("pwdata") or s.get("prdata"))
    prev = None          # previous cycle sample
    cur_tx = None
    waits = 0
    for cyc, t in enumerate(edges):
        v = sm.at(t)
        g = lambda k: v.get(s.get(k)) if s.get(k) else None  # noqa: E731
        sel, en = g("psel"), g("penable")
        ready = g("pready") if s.get("pready") else "1"
        if sel == "1" and (not _known(en) or not _known(g("paddr"))):
            rep.add("APB_X_CONTROL", cyc, t, f"PENABLE/PADDR unknown while PSEL=1 (PENABLE={en}, PADDR={g('paddr')})")
        p_sel = prev and prev["sel"] == "1"
        p_en = prev and prev["en"] == "1"
        p_setup = p_sel and not p_en
        p_wait = p_sel and p_en and prev["ready"] != "1"
        if p_setup and not (sel == "1" and en == "1"):
            rep.add("APB_SETUP_NOT_FOLLOWED", cyc, t, "SETUP cycle not followed by ACCESS (PENABLE did not rise)")
            cur_tx = None
        if en == "1" and sel == "1" and not p_setup and not p_wait:
            rep.add("APB_ENABLE_WITHOUT_SETUP", cyc, t, "PENABLE=1 without a preceding SETUP cycle")
        if p_wait and sel != "1":
            rep.add("APB_SEL_DROPPED", cyc, t, "PSEL dropped while the slave held PREADY low")
            cur_tx = None
        # start of a transfer
        if sel == "1" and en != "1":
            cur_tx = {"kind": "WRITE" if g("pwrite") == "1" else "READ", "addr": _hex(g("paddr"), awidth),
                      "start_cycle": cyc, "start_time": t, "_ctl": (g("paddr"), g("pwrite"), g("pwdata")), "waits": 0}
            waits = 0
        elif cur_tx and sel == "1" and en == "1":
            ctl = (g("paddr"), g("pwrite"), g("pwdata") if cur_tx["kind"] == "WRITE" else cur_tx["_ctl"][2])
            if ctl != cur_tx["_ctl"]:
                rep.add("APB_CHANGED_IN_ACCESS", cyc, t, f"control/data changed during the transfer to {cur_tx['addr']}")
                cur_tx["_ctl"] = ctl
            if ready == "1":
                data = g("pwdata") if cur_tx["kind"] == "WRITE" else g("prdata")
                err = s.get("pslverr") and g("pslverr") == "1"
                if err:
                    rep.add("APB_SLVERR", cyc, t, f"PSLVERR on {cur_tx['kind'].lower()} to {cur_tx['addr']}")
                cur_tx.update(data=_hex(data, dwidth), resp="SLVERR" if err else "OKAY", end_cycle=cyc, end_time=t,
                              waits=waits, latency=cyc - cur_tx["start_cycle"])
                cur_tx.pop("_ctl", None)
                rep.transactions.append(cur_tx)
                cur_tx = None
            else:
                waits += 1
                if waits == timeout + 1:
                    rep.add("APB_TIMEOUT", cyc, t, f"PREADY low for more than {timeout} cycles")
        prev = {"sel": sel, "en": en, "ready": ready}
    txs = rep.transactions
    rep.stats = {"cycles": len(edges), "writes": sum(t["kind"] == "WRITE" for t in txs), "reads": sum(t["kind"] == "READ" for t in txs),
                 "avg_wait_states": round(sum(t["waits"] for t in txs) / len(txs), 2) if txs else None}
    return rep.result()


# ============================================================================ AHB-Lite

_AHB_RE = re.compile(r"^(.*?)(htrans|haddr|hwrite|hsize|hburst|hwdata|hrdata|hready|hreadyout|hresp|hsel\w*|hprot)$", re.I)
_HTRANS = {0: "IDLE", 1: "BUSY", 2: "NONSEQ", 3: "SEQ"}
_HBURST = {0: "SINGLE", 1: "INCR", 2: "WRAP4", 3: "INCR4", 4: "WRAP8", 5: "INCR8", 6: "WRAP16", 7: "INCR16"}


def _find_ahb(vcd):
    out = []
    for prefix, s in _group(vcd, _AHB_RE).items():
        if "htrans" in s and "haddr" in s and ("hready" in s or "hreadyout" in s):
            s.setdefault("hready", s.get("hreadyout"))
            out.append((prefix, s, _clock_for(vcd, prefix, ["hclk", "clk", "clock"])))
    return out


def check_ahb(vcd, prefix, s, clock, timeout=16):
    rep = _Report("AHB-Lite", prefix, vcd, clock)
    rep.signals = {k: s.get(k) for k in ("htrans", "haddr", "hwrite", "hsize", "hburst", "hwdata", "hrdata", "hready", "hresp")}
    if not clock:
        rep.extra["error"] = "No clock (hclk/clk) found next to the AHB signals."
        return rep.result()
    edges = _rising_edges(vcd, clock)
    sm = _Sampler(vcd, [n for n in rep.signals.values() if n])
    awidth, dwidth = _width(vcd, s.get("haddr")), _width(vcd, s.get("hwdata") or s.get("hrdata"))
    data_phase = None       # transfer whose data phase is in progress
    prev_addr = None        # last accepted address phase (for burst checks)
    held = None             # address phase waiting for HREADY
    low_run = 0
    prev_resp = prev_ready = None
    for cyc, t in enumerate(edges):
        v = sm.at(t)
        g = lambda k: v.get(s.get(k)) if s.get(k) else None  # noqa: E731
        ready = g("hready") or "1"
        trans = _int(g("htrans"))
        resp = g("hresp") if s.get("hresp") else "0"
        # two-cycle ERROR response
        if resp == "1" and ready == "1" and not (prev_resp == "1" and prev_ready == "0"):
            rep.add("AHB_BAD_ERROR_RESPONSE", cyc, t, "HRESP=ERROR completed in one cycle (needs HREADY=0 first)")
        low_run = low_run + 1 if ready != "1" else 0
        if low_run == timeout + 1:
            rep.add("AHB_TIMEOUT", cyc, t, f"HREADY low for more than {timeout} cycles")
        # data phase completes when HREADY is high
        if data_phase and ready == "1":
            data = g("hwdata") if data_phase["kind"] == "WRITE" else g("hrdata")
            data_phase.update(data=_hex(data, dwidth), resp="ERROR" if resp == "1" else "OKAY", end_cycle=cyc, end_time=t,
                              latency=cyc - data_phase["start_cycle"])
            if resp == "1":
                rep.add("AHB_ERROR_RESPONSE", cyc, t, f"ERROR response to {data_phase['kind'].lower()} at {data_phase['addr']}")
            rep.transactions.append(data_phase)
            data_phase = None
        # address phase
        ctl = (g("htrans"), g("haddr"), g("hwrite"), g("hsize"), g("hburst"))
        if held is not None and trans in (2, 3) and ctl != held and ready != "1":
            rep.add("AHB_CHANGED_IN_WAIT", cyc, t, "address/control changed while HREADY was low")
        if ready == "1":
            if trans is None or not _known(g("haddr")) and trans in (2, 3):
                rep.add("AHB_X_CONTROL", cyc, t, f"HTRANS/HADDR unknown (HTRANS={g('htrans')}, HADDR={g('haddr')})")
            if trans in (2, 3):
                addr, size = _int(g("haddr")), _int(g("hsize")) or 0
                burst = _int(g("hburst")) or 0
                if trans == 3:
                    if not prev_addr:
                        rep.add("AHB_SEQ_WITHOUT_NONSEQ", cyc, t, "SEQ transfer without a NONSEQ start")
                    elif addr is not None and prev_addr["addr"] is not None and _HBURST.get(prev_addr["burst"], "").startswith("INCR"):
                        exp = prev_addr["addr"] + (1 << prev_addr["size"])
                        if addr != exp:
                            rep.add("AHB_BAD_INCREMENT", cyc, t, f"SEQ address {_hex(g('haddr'), awidth)}, expected 0x{exp:X}")
                        if addr is not None and addr // 1024 != prev_addr["start"] // 1024:
                            rep.add("AHB_1KB_BOUNDARY", cyc, t, f"burst from 0x{prev_addr['start']:X} crosses a 1 KB boundary")
                start = addr if trans == 2 or not prev_addr else prev_addr["start"]
                prev_addr = {"addr": addr, "size": size, "burst": burst if trans == 2 else (prev_addr or {}).get("burst", burst),
                             "start": start if start is not None else 0}
                data_phase = {"kind": "WRITE" if g("hwrite") == "1" else "READ", "addr": _hex(g("haddr"), awidth),
                              "trans": _HTRANS[trans], "burst": _HBURST.get(prev_addr["burst"], "?"), "size": 1 << size,
                              "start_cycle": cyc, "start_time": t}
            elif trans == 0:
                prev_addr = None
            held = None
        elif trans in (2, 3):
            held = held or ctl
        prev_resp, prev_ready = resp, ready
    txs = rep.transactions
    rep.stats = {"cycles": len(edges), "writes": sum(t["kind"] == "WRITE" for t in txs), "reads": sum(t["kind"] == "READ" for t in txs),
                 "bursts": sum(t["trans"] == "NONSEQ" and t["burst"] != "SINGLE" for t in txs)}
    return rep.result()


# ============================================================================ AXI-Stream

_AXIS_RE = re.compile(r"^(.*?)(tvalid|tready|tdata|tlast|tkeep|tstrb|tuser|tid|tdest)$", re.I)


def _find_axis(vcd):
    out = []
    for prefix, s in _group(vcd, _AXIS_RE).items():
        if "tvalid" in s and "tdata" in s:
            out.append((prefix, s, _clock_for(vcd, prefix, ["aclk", "clk", "axis_aclk", "clock"])))
    return out


def check_axis(vcd, prefix, s, clock, timeout=16):
    rep = _Report("AXI-Stream", prefix, vcd, clock)
    rep.signals = {k: s.get(k) for k in ("tvalid", "tready", "tdata", "tlast", "tkeep", "tuser", "tid", "tdest")}
    if not clock:
        rep.extra["error"] = "No clock (aclk/clk) found next to the AXI-Stream signals."
        return rep.result()
    edges = _rising_edges(vcd, clock)
    sm = _Sampler(vcd, [n for n in rep.signals.values() if n])
    dwidth = _width(vcd, s["tdata"])
    nbytes = (dwidth + 7) // 8
    waiting, payload, stall = False, None, 0
    pkt, stall_total, beats_total = None, 0, 0
    for cyc, t in enumerate(edges):
        v = sm.at(t)
        g = lambda k: v.get(s.get(k)) if s.get(k) else None  # noqa: E731
        valid = g("tvalid")
        ready = g("tready") if s.get("tready") else "1"
        if not _known(valid):
            rep.add("AXIS_X_ON_VALID", cyc, t, f"TVALID is {valid}")
            continue
        cur_payload = (g("tdata"), g("tlast"), g("tkeep"))
        if waiting:
            if valid != "1":
                rep.add("AXIS_VALID_DROPPED", cyc, t, f"TVALID dropped after {stall} cycle(s) without TREADY")
            elif cur_payload != payload:
                rep.add("AXIS_PAYLOAD_CHANGED", cyc, t, "TDATA/TLAST/TKEEP changed while waiting for TREADY")
                payload = cur_payload
        if valid == "1":
            if not _known(g("tdata")):
                rep.add("AXIS_X_ON_DATA", cyc, t, "TDATA unknown during a transfer")
            if ready == "1":
                beats_total += 1
                keep = _int(g("tkeep")) if s.get("tkeep") else (1 << nbytes) - 1
                last = g("tlast") == "1" if s.get("tlast") else False
                if pkt is None:
                    pkt = {"kind": "PACKET", "start_cycle": cyc, "start_time": t, "beats": 0, "bytes": 0, "data": [],
                           "tid": g("tid"), "tdest": g("tdest")}
                pkt["beats"] += 1
                pkt["bytes"] += bin(keep or 0).count("1")
                if len(pkt["data"]) < 16:
                    pkt["data"].append(_hex(g("tdata"), dwidth))
                full = (1 << nbytes) - 1
                if keep is not None and keep != full and not last:
                    rep.add("AXIS_NULL_BYTES", cyc, t, f"TKEEP=0x{keep:X} in the middle of a packet")
                if last or not s.get("tlast"):
                    pkt.update(end_cycle=cyc, end_time=t, latency=cyc - pkt["start_cycle"])
                    rep.transactions.append(pkt)
                    pkt = None
                waiting, stall = False, 0
            else:
                if not waiting:
                    payload = cur_payload
                waiting = True
                stall += 1
                stall_total += 1
                if stall == timeout + 1:
                    rep.add("AXIS_READY_TIMEOUT", cyc, t, f"TREADY low for more than {timeout} cycles")
        else:
            waiting, stall = False, 0
    if pkt is not None:
        rep.add("AXIS_UNTERMINATED", len(edges) - 1, edges[-1] if edges else 0, f"packet of {pkt['beats']} beat(s) has no TLAST")
    sizes = [p["beats"] for p in rep.transactions]
    period = (edges[1] - edges[0]) if len(edges) > 1 else 0
    secs = len(edges) * period * vcd.timescale_s
    rep.stats = {"cycles": len(edges), "beats": beats_total, "packets": len(rep.transactions),
                 "avg_packet_beats": round(sum(sizes) / len(sizes), 1) if sizes else None,
                 "backpressure": round(stall_total / max(1, stall_total + beats_total), 3),
                 "throughput_MBps": round(beats_total * nbytes / secs / 1e6, 2) if secs else None}
    return rep.result()


# ============================================================================ SPI

_SPI_CLK = re.compile(r"^(.*?)(sclk|sck|spi_clk|spiclk)$", re.I)


def _find_spi(vcd):
    out = []
    for full in vcd.signals:
        scope, _, leaf = full.rpartition(".")
        m = _SPI_CLK.match(leaf)
        if not m:
            continue
        pre = m.group(1)
        base = (scope + "." if scope else "")

        def pick(names):
            for n in names:
                if base + pre + n in vcd.signals:
                    return base + pre + n
            return None

        mosi = pick(["mosi", "sdo", "copi", "sdi_o", "dout"])
        miso = pick(["miso", "sdi", "cipo", "din"])
        cs = pick(["cs_n", "csn", "ss_n", "ssn", "cs", "ss", "nss", "ncs"])
        if mosi or miso:
            out.append((base + pre, {"sclk": full, "mosi": mosi, "miso": miso, "cs": cs}, None))
    return out


def check_spi(vcd, prefix, s, clock=None, timeout=16, cpha=None):
    rep = _Report("SPI", prefix, vcd)
    rep.signals = dict(s)
    sclk = vcd.signals[s["sclk"]].changes
    cs_ch = vcd.signals[s["cs"]].changes if s.get("cs") else []
    active_low = not s.get("cs") or s["cs"].lower().endswith(("_n", "n", "nss", "ncs")) and not s["cs"].lower().endswith("cs")

    def value_at(changes, t):
        val = "x"
        for tt, v in changes:
            if tt > t:
                break
            val = v
        return val

    cpol = sclk[0][1] if sclk else "0"           # idle level at the start of the dump
    lead = "1" if cpol == "0" else "0"            # level the leading edge goes to
    mode = None
    # sampling edge: CPHA=0 samples on the leading edge
    sample_level = lead if (cpha or 0) == 0 else ("0" if lead == "1" else "1")
    mode = (0 if cpol == "0" else 2) + (1 if (cpha or 0) == 1 else 0)
    rep.extra["mode"] = mode
    frame, bits_mosi, bits_miso = None, [], []

    def cs_active(t):
        if not s.get("cs"):
            return True
        v = value_at(cs_ch, t)
        return v == ("0" if active_low else "1")

    def close(t):
        nonlocal frame, bits_mosi, bits_miso
        if frame is None:
            return
        n = len(bits_mosi) or len(bits_miso)
        if n % 8:
            rep.add("SPI_PARTIAL_BYTE", None, t, f"frame ended after {n} bits")
        to_bytes = lambda bits: [int("".join(bits[i:i + 8]), 2) for i in range(0, len(bits) - len(bits) % 8, 8) if all(b in "01" for b in bits[i:i + 8])]  # noqa: E731
        mo, mi = to_bytes(bits_mosi), to_bytes(bits_miso)
        frame.update(end_time=t, bits=n, mosi=" ".join(f"{b:02X}" for b in mo), miso=" ".join(f"{b:02X}" for b in mi),
                     text=_ascii(mo))
        rep.transactions.append(frame)
        frame, bits_mosi, bits_miso = None, [], []

    events = sorted([(t, "clk", v) for t, v in sclk] + [(t, "cs", v) for t, v in cs_ch])
    prev_clk = cpol
    stray = False
    for t, kind, v in events:
        if kind == "cs":
            stray = False
            if cs_active(t) and frame is None:
                frame = {"kind": "FRAME", "start_time": t}
            elif not cs_active(t):
                close(t)
            continue
        if v == prev_clk:
            continue
        prev_clk = v
        if not cs_active(t):
            if s.get("cs") and not stray:
                rep.add("SPI_CLOCK_WHILE_IDLE", None, t, "SCLK toggled while chip select is inactive")
                stray = True
            continue
        if frame is None:
            frame = {"kind": "FRAME", "start_time": t}
        if v == sample_level:
            for key, bits in (("mosi", bits_mosi), ("miso", bits_miso)):
                if s.get(key):
                    b = value_at(vcd.signals[s[key]].changes, t - 1 if t > 0 else t)
                    if b not in ("0", "1"):
                        rep.add("SPI_X_DATA", None, t, f"{key.upper()} is {b} at a sampling edge")
                    bits.append(b if b in ("0", "1") else "0")
    if frame is not None:
        close(vcd.end_time)
    for i, f in enumerate(rep.transactions):
        f["index"] = i + 1
    rep.stats = {"frames": len(rep.transactions), "bytes": sum(len(f["mosi"].split()) if f["mosi"] else len(f["miso"].split()) for f in rep.transactions),
                 "mode": mode, "cpol": int(cpol == "1")}
    return rep.result()


# ============================================================================ I2C

def _find_i2c(vcd):
    out = []
    for full in vcd.signals:
        scope, _, leaf = full.rpartition(".")
        m = re.match(r"^(.*?)scl(_i|_in|_io)?$", leaf, re.I)
        if not m:
            continue
        base = (scope + "." if scope else "") + m.group(1)
        sda = next((base + n for n in ("sda", "sda_i", "sda_in", "sda_io") if base + n in vcd.signals), None)
        if sda:
            out.append((base, {"scl": full, "sda": sda}, None))
    return out


def check_i2c(vcd, prefix, s, clock=None, timeout=16):
    rep = _Report("I2C", prefix, vcd)
    rep.signals = dict(s)
    events = sorted([(t, "scl", v) for t, v in vcd.signals[s["scl"]].changes] + [(t, "sda", v) for t, v in vcd.signals[s["sda"]].changes],
                    key=lambda e: (e[0], e[1] == "sda"))   # at equal times apply SCL first
    scl = sda = "1"
    tx, bits, byte_index = None, [], 0
    in_frame = False

    def finish_byte(t):
        nonlocal bits, byte_index
        if len(bits) < 9:
            return
        value = int("".join(bits[:8]), 2)
        ack = bits[8] == "0"
        if byte_index == 0:
            tx["addr"] = f"0x{value >> 1:02X}"
            tx["kind"] = "READ" if value & 1 else "WRITE"
            tx["addr_ack"] = ack
            if not ack:
                rep.add("I2C_ADDRESS_NACK", None, t, f"no ACK for address 0x{value >> 1:02X}")
        else:
            tx["bytes"].append(value)
            tx["acks"].append("A" if ack else "N")
        byte_index += 1
        bits = []

    # A bit is sampled when SCL rises and committed when SCL falls again; if SDA changes while SCL
    # is high in between, that is a START/STOP condition and the sample is dropped.
    pending = None
    for t, kind, v in events:
        if kind == "scl":
            if v == "1" and scl == "0" and in_frame:
                pending = sda if sda in "01" else "0"
            elif v == "0" and scl == "1" and pending is not None:
                bits.append(pending)
                pending = None
                if len(bits) == 9:
                    finish_byte(t)
            scl = v
            continue
        # SDA changed while SCL is high: START or STOP condition
        if scl == "1" and v != sda:
            pending = None
            if sda == "1" and v == "0":           # START (or repeated START)
                if in_frame and bits:
                    rep.add("I2C_UNEXPECTED_CONDITION", None, t, f"START (SDA fell with SCL high) after {len(bits)} bit(s) of a byte")
                if tx:
                    tx["end_time"] = t
                    rep.transactions.append(tx)
                tx = {"kind": "?", "start_time": t, "addr": None, "addr_ack": None, "bytes": [], "acks": [], "repeated": in_frame}
                bits, byte_index, in_frame = [], 0, True
            elif sda == "0" and v == "1":         # STOP
                if in_frame and bits:
                    rep.add("I2C_UNEXPECTED_CONDITION", None, t, f"STOP (SDA rose with SCL high) after {len(bits)} bit(s) of a byte")
                if tx:
                    tx["end_time"] = t
                    tx["stop"] = True
                    rep.transactions.append(tx)
                tx, bits, in_frame = None, [], False
        sda = v
    if tx:
        tx["end_time"] = vcd.end_time
        rep.transactions.append(tx)
        rep.add("I2C_NO_STOP", None, vcd.end_time, "the dump ended inside a transaction (no STOP)")
    for tx in rep.transactions:
        tx["data"] = " ".join(f"{b:02X}" for b in tx["bytes"])
        tx["text"] = _ascii(tx["bytes"])
        tx["acks"] = "".join(tx["acks"])
        tx["nbytes"] = len(tx.pop("bytes"))
    rep.stats = {"transactions": len(rep.transactions), "bytes": sum(t["nbytes"] for t in rep.transactions),
                 "nacks": sum(t["addr_ack"] is False for t in rep.transactions)}
    return rep.result()


# ============================================================================ UART

_UART_RE = re.compile(r"^(.*?)(uart_tx|uart_rx|txd|rxd|tx|rx|serial_out|serial_in)$", re.I)


def _find_uart(vcd, taken):
    out = []
    for full, sig in vcd.signals.items():
        if sig.width != 1 or full in taken:
            continue
        scope, _, leaf = full.rpartition(".")
        if _UART_RE.match(leaf) and len(sig.changes) >= 4:
            out.append((full, {"line": full}, None))
    return out


def check_uart(vcd, prefix, s, clock=None, timeout=16, data_bits=8, baud_ticks=None):
    rep = _Report("UART", prefix, vcd)
    rep.signals = dict(s)
    ch = [(t, v) for t, v in vcd.signals[s["line"]].changes if v in ("0", "1")]
    widths = [b[0] - a[0] for a, b in zip(ch, ch[1:]) if b[0] > a[0]]
    if not widths:
        rep.extra["error"] = "The line never toggles."
        return rep.result()
    if not baud_ticks:
        # shortest stable pulse that repeats is one bit; ignore lone glitches
        cnt = Counter(widths)
        common = sorted(w for w, n in cnt.items() if n >= 2) or sorted(widths)
        baud_ticks = common[0]
    bit = baud_ticks

    def level(t):
        val = "1"
        for tt, v in ch:
            if tt > t:
                break
            val = v
        return val

    t_end = vcd.end_time
    i = 0
    idle = ch[0][1] if ch else "1"
    frames = []
    while i < len(ch):
        t, v = ch[i]
        if v == "0" and (i == 0 or ch[i - 1][1] == "1" or idle == "1"):
            if t + bit * (data_bits + 1.5) > t_end:
                break
            if level(t + bit / 2) != "0":
                rep.add("UART_GLITCH", None, t, "start bit shorter than half a bit")
                i += 1
                continue
            data = [level(t + bit * (k + 1.5)) for k in range(data_bits)]
            stop = level(t + bit * (data_bits + 1.5))
            value = sum((1 << k) for k, b in enumerate(data) if b == "1")
            frame = {"kind": "BYTE", "start_time": t, "end_time": int(t + bit * (data_bits + 2)), "value": f"0x{value:02X}",
                     "char": _ascii([value]), "framing": stop == "1"}
            if stop != "1":
                if value == 0:
                    rep.add("UART_BREAK", None, t, "line held low for a whole frame")
                    frame["kind"] = "BREAK"
                else:
                    rep.add("UART_FRAMING_ERROR", None, t, f"stop bit is 0 after byte 0x{value:02X}")
            frames.append((frame, value))
            # continue after the stop bit
            t_next = t + bit * (data_bits + 1)
            while i < len(ch) and ch[i][0] < t_next:
                i += 1
            continue
        i += 1
    rep.transactions = [f for f, _ in frames]
    baud = 1 / (bit * vcd.timescale_s) if bit else None
    rep.extra["decoded_text"] = _ascii([v for f, v in frames if f["kind"] == "BYTE"])
    rep.stats = {"bytes": len(frames), "bit_time": bit, "baud": round(baud) if baud else None,
                 "framing_errors": sum(not f["framing"] for f, _ in frames)}
    return rep.result()


# ============================================================================ entry point

def analyze_vcd(vcd, timeout=16):
    interfaces = []
    taken = set()
    for finder, checker in ((_find_apb, check_apb), (_find_ahb, check_ahb), (_find_axis, check_axis),
                            (_find_spi, check_spi), (_find_i2c, check_i2c)):
        for prefix, sigs, clock in finder(vcd):
            interfaces.append(checker(vcd, prefix, sigs, clock, timeout))
            taken |= {v for v in sigs.values() if v}
    for prefix, sigs, clock in _find_uart(vcd, taken):
        r = check_uart(vcd, prefix, sigs, clock, timeout)
        if r["transactions"]:
            interfaces.append(r)
    return interfaces


def analyze_vcd_text(text, timeout=16):
    vcd = parse_vcd(text)
    return {"timescale": vcd.timescale_text, "end_time": vcd.end_time, "interfaces": analyze_vcd(vcd, timeout),
            "supported": list(PROTOCOL_RULES)}


def analyze_file(path, timeout=16):
    with open(path, encoding="utf-8", errors="replace") as f:
        return analyze_vcd_text(f.read(), timeout)
