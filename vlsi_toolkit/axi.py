"""AXI protocol checker and transaction viewer (works on VCD waveforms).

1. Finds AXI interfaces automatically from signal names
   (<prefix>awvalid, <prefix>wdata, <prefix>rresp ...), AXI4 or AXI4-Lite.
2. Samples every signal on the rising clock edge, as the hardware does.
3. Checks the protocol rules (ARM IHI 0022) that cause real silicon bugs:

   VALID_DROPPED      VALID fell before the handshake (READY) completed
   PAYLOAD_CHANGED    address/data/control changed while VALID was waiting for READY
   X_ON_VALID         VALID is X/Z after reset
   X_ON_PAYLOAD       address/data is X/Z during a VALID cycle
   VALID_IN_RESET     VALID high while ARESETn is low
   WLAST_MISMATCH     WLAST not on beat AWLEN+1 (early, late or missing)
   RLAST_MISMATCH     RLAST not on beat ARLEN+1
   BOUNDARY_4KB       INCR burst crosses a 4 KB address boundary (illegal)
   ERROR_RESPONSE     SLVERR / DECERR response
   UNEXPECTED_B / _R  response with no matching request
   NO_RESPONSE        request still unanswered at the end of the simulation
   READY_TIMEOUT      VALID waited longer than the timeout for READY

4. Rebuilds transactions: "WRITE 0x40001000 len 4 -> OKAY, 9 cycles".
"""

import re
from dataclasses import dataclass, field

from .vcd_analyzer import parse_text as parse_vcd

CHANNELS = {
    "aw": ["addr", "len", "size", "burst", "id", "prot", "cache", "lock", "qos"],
    "w": ["data", "strb", "last", "id"],
    "b": ["resp", "id"],
    "ar": ["addr", "len", "size", "burst", "id", "prot", "cache", "lock", "qos"],
    "r": ["data", "resp", "last", "id"],
}
_FIELDS = "valid|ready|" + "|".join(sorted({f for fs in CHANNELS.values() for f in fs}, key=len, reverse=True))
_SIG_RE = re.compile(rf"^(.*?)(aw|ar|w|b|r)_?({_FIELDS})$", re.I)
RESP = {0: "OKAY", 1: "EXOKAY", 2: "SLVERR", 3: "DECERR"}
SEVERITY = {
    "VALID_DROPPED": "ERROR", "PAYLOAD_CHANGED": "ERROR", "X_ON_VALID": "ERROR", "X_ON_PAYLOAD": "ERROR",
    "WLAST_MISMATCH": "ERROR", "RLAST_MISMATCH": "ERROR", "BOUNDARY_4KB": "ERROR", "UNEXPECTED_B": "ERROR",
    "UNEXPECTED_R": "ERROR", "VALID_IN_RESET": "WARNING", "ERROR_RESPONSE": "WARNING", "NO_RESPONSE": "WARNING",
    "READY_TIMEOUT": "WARNING",
}
RULE_HELP = {
    "VALID_DROPPED": "Once VALID is asserted it must stay high until the cycle where READY is also high.",
    "PAYLOAD_CHANGED": "While VALID waits for READY, address, data and control must stay stable.",
    "X_ON_VALID": "VALID must always be 0 or 1 after reset; X here can hang or corrupt the bus.",
    "X_ON_PAYLOAD": "Signals must be known (no X/Z) whenever VALID is high.",
    "VALID_IN_RESET": "A master must drive VALID low while ARESETn is asserted.",
    "WLAST_MISMATCH": "WLAST must be high on exactly the last write beat (beat AWLEN+1).",
    "RLAST_MISMATCH": "RLAST must be high on exactly the last read beat (beat ARLEN+1).",
    "BOUNDARY_4KB": "An INCR burst must not cross a 4 KB address boundary.",
    "ERROR_RESPONSE": "The slave answered SLVERR (slave error) or DECERR (no slave at this address).",
    "UNEXPECTED_B": "A write response arrived with no outstanding write request.",
    "UNEXPECTED_R": "Read data arrived with no outstanding read request.",
    "NO_RESPONSE": "A request was accepted but never answered: a hang or a lost response.",
    "READY_TIMEOUT": "VALID waited a long time for READY: back-pressure or a stuck slave.",
}


@dataclass
class Interface:
    prefix: str
    signals: dict            # (channel, field) -> full VCD signal name
    clock: str | None
    reset: str | None
    kind: str = "AXI4"       # AXI4 or AXI4-Lite

    def has(self, ch, f):
        return (ch, f) in self.signals


@dataclass
class Violation:
    rule: str
    channel: str
    cycle: int
    time: int
    message: str

    @property
    def severity(self):
        return SEVERITY[self.rule]


@dataclass
class Transaction:
    kind: str                      # WRITE / READ
    id: int | None
    addr: int | None
    length: int                    # beats expected (len+1)
    size: int | None               # bytes per beat
    burst: str
    start_cycle: int
    start_time: int
    beats: list = field(default_factory=list)   # [(data_hex, strb_hex)]
    resp: str | None = None
    end_cycle: int | None = None
    end_time: int | None = None
    waited: int = 0                # cycles the address VALID waited for READY before the handshake

    @property
    def latency(self):
        return None if self.end_cycle is None else self.end_cycle - self.start_cycle

    @property
    def status(self):
        if self.end_cycle is None:
            return "NO_RESPONSE"
        return self.resp or "OKAY"


# ---------------------------------------------------------------------------
# Interface detection
# ---------------------------------------------------------------------------


def find_interfaces(vcd):
    groups = {}
    for full in vcd.signals:
        scope, _, leaf = full.rpartition(".")
        m = _SIG_RE.match(leaf)
        if not m:
            continue
        prefix = (scope + "." if scope else "") + m.group(1)
        groups.setdefault(prefix, {})[(m.group(2).lower(), m.group(3).lower())] = full
    out = []
    for prefix, sigs in sorted(groups.items()):
        handshakes = [ch for ch in CHANNELS if (ch, "valid") in sigs and (ch, "ready") in sigs]
        if len(handshakes) < 2:
            continue
        scope = prefix.rpartition(".")[0]
        clock = _find_named(vcd, scope, ["aclk", "clk", "clock", "s_axi_aclk", "m_axi_aclk"], prefix)
        reset = _find_named(vcd, scope, ["aresetn", "aresetn_i", "rst_n", "resetn", "aresetn", "s_axi_aresetn"], prefix)
        kind = "AXI4" if any(k in sigs for k in [("aw", "len"), ("ar", "len"), ("w", "last"), ("r", "last")]) else "AXI4-Lite"
        out.append(Interface(prefix, sigs, clock, reset, kind))
    return out


def _find_named(vcd, scope, names, prefix):
    """Look for a clock/reset next to the interface, then in parent scopes."""
    leaf_prefix = prefix.rpartition(".")[2]
    parts = scope.split(".") if scope else []
    while True:
        base = ".".join(parts)
        for n in [leaf_prefix + "aclk" if "clk" in names[0] else leaf_prefix + "aresetn"] + names:
            cand = f"{base}.{n}" if base else n
            if cand in vcd.signals:
                return cand
        if not parts:
            return None
        parts.pop()


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


class _Sampler:
    """Value of each signal just before each rising clock edge."""

    def __init__(self, vcd, names):
        self.changes = {n: vcd.signals[n].changes for n in names if n in vcd.signals}
        self.idx = {n: 0 for n in self.changes}
        self.cur = {n: "x" for n in self.changes}

    def at(self, t):
        for n, ch in self.changes.items():
            i = self.idx[n]
            while i < len(ch) and ch[i][0] < t:
                self.cur[n] = ch[i][1]
                i += 1
            self.idx[n] = i
        return dict(self.cur)


def _known(v):
    return v is not None and v != "" and not any(c in v for c in "xz")


def _int(v):
    if not _known(v):
        return None
    try:
        return int(v, 2) if set(v) <= {"0", "1"} else int(float(v))
    except ValueError:
        return None


def _hex(v, width_bits=None):
    n = _int(v)
    if n is None:
        return "X" if v and any(c in v for c in "xz") else v
    digits = max(1, ((width_bits or len(v)) + 3) // 4)
    return f"0x{n:0{digits}X}"


def _rising_edges(vcd, clock):
    edges, prev = [], None
    for t, v in vcd.signals[clock].changes:
        if prev == "0" and v == "1":
            edges.append(t)
        prev = v
    return edges


# ---------------------------------------------------------------------------
# Checking + transaction building
# ---------------------------------------------------------------------------


def analyze_interface(vcd, itf, timeout=16):
    viol = []
    if not itf.clock:
        return {"error": f"No clock found for interface {itf.prefix} (expected ACLK/clk nearby)."}
    edges = _rising_edges(vcd, itf.clock)
    names = list(itf.signals.values()) + ([itf.reset] if itf.reset else [])
    sampler = _Sampler(vcd, names)
    get = lambda s, ch, f: s.get(itf.signals.get((ch, f)))  # noqa: E731
    width = {k: vcd.signals[n].width for k, n in itf.signals.items()}

    def add(rule, ch, cycle, msg):
        viol.append(Violation(rule, ch.upper(), cycle, edges[cycle] if cycle < len(edges) else 0, msg))

    prev = None
    wait = {ch: 0 for ch in CHANNELS}          # cycles VALID has been waiting
    stall = {ch: 0 for ch in CHANNELS}         # total stall cycles
    hs_count = {ch: 0 for ch in CHANNELS}
    timeout_flagged = {ch: False for ch in CHANNELS}
    payload_flagged = {ch: False for ch in CHANNELS}  # report a payload change once per stall

    aw_q, w_bursts, cur_w = [], [], []         # write assembly
    wait_b = []                                # writes waiting for B
    reads = []                                 # reads waiting for R data
    txns = []
    active_cycles = 0

    for c, t in enumerate(edges):
        s = sampler.at(t)
        in_reset = itf.reset is not None and s.get(itf.reset) == "0"
        if in_reset:
            for ch in CHANNELS:
                if itf.has(ch, "valid") and s.get(itf.signals[(ch, "valid")]) == "1" and ch in ("aw", "w", "ar"):
                    add("VALID_IN_RESET", ch, c, f"{ch.upper()}VALID high during reset")
            prev = s
            continue
        active_cycles += 1
        for ch, fields in CHANNELS.items():
            if not (itf.has(ch, "valid") and itf.has(ch, "ready")):
                continue
            v, r = get(s, ch, "valid"), get(s, ch, "ready")
            if not _known(v):
                if prev is not None and (prev.get(itf.reset) if itf.reset else "1") == "1":
                    add("X_ON_VALID", ch, c, f"{ch.upper()}VALID is '{v}'")
                continue
            if v == "1":
                for f in ("addr", "data", "len", "id"):
                    if itf.has(ch, f) and not _known(get(s, ch, f)):
                        add("X_ON_PAYLOAD", ch, c, f"{ch.upper()}{f.upper()} is unknown while {ch.upper()}VALID=1")
            # stability rules: compare with the previous cycle if it was a waiting VALID
            if prev is not None and get(prev, ch, "valid") == "1" and get(prev, ch, "ready") != "1":
                if v != "1":
                    add("VALID_DROPPED", ch, c, f"{ch.upper()}VALID dropped after {wait[ch]} cycle(s) without {ch.upper()}READY")
                else:
                    changed = [f for f in fields if itf.has(ch, f) and get(prev, ch, f) != get(s, ch, f)]
                    if changed and not payload_flagged[ch]:
                        payload_flagged[ch] = True
                        add("PAYLOAD_CHANGED", ch, c, f"{', '.join(ch.upper() + f.upper() for f in changed)} changed while waiting for {ch.upper()}READY")
            handshake = v == "1" and r == "1"
            waited = wait[ch]
            if v == "1" and not handshake:
                wait[ch] += 1
                stall[ch] += 1
                if wait[ch] > timeout and not timeout_flagged[ch]:
                    add("READY_TIMEOUT", ch, c, f"{ch.upper()}VALID waiting for READY for more than {timeout} cycles")
                    timeout_flagged[ch] = True
            else:
                wait[ch] = 0
                timeout_flagged[ch] = False
                payload_flagged[ch] = False
            if not handshake:
                continue
            hs_count[ch] += 1
            idv = _int(get(s, ch, "id")) if itf.has(ch, "id") else None

            if ch in ("aw", "ar"):
                addr = _int(get(s, ch, "addr"))
                length = (_int(get(s, ch, "len")) or 0) + 1 if itf.has(ch, "len") else 1
                size = 2 ** _int(get(s, ch, "size")) if itf.has(ch, "size") and _int(get(s, ch, "size")) is not None else \
                    (width.get(("w" if ch == "aw" else "r", "data"), 32) // 8)
                burst = {0: "FIXED", 1: "INCR", 2: "WRAP"}.get(_int(get(s, ch, "burst")), "INCR") if itf.has(ch, "burst") else "INCR"
                if burst == "INCR" and addr is not None and (addr // 4096) != ((addr + length * size - 1) // 4096):
                    add("BOUNDARY_4KB", ch, c, f"burst at 0x{addr:X}, {length} x {size} bytes crosses a 4 KB boundary")
                tx = Transaction("WRITE" if ch == "aw" else "READ", idv, addr, length, size, burst, c, t)
                tx.waited = waited
                if ch == "aw":
                    aw_q.append(tx)
                    _pair_writes(aw_q, w_bursts, wait_b, add, c)
                else:
                    reads.append(tx)
                    txns.append(tx)
            elif ch == "w":
                last = get(s, "w", "last") == "1" if itf.has("w", "last") else True
                cur_w.append((_hex(get(s, "w", "data"), width.get(("w", "data"))),
                              _hex(get(s, "w", "strb"), width.get(("w", "strb"))) if itf.has("w", "strb") else None))
                expected = aw_q[len(w_bursts)].length if len(w_bursts) < len(aw_q) else None
                if itf.has("w", "last"):
                    if last and expected is not None and len(cur_w) < expected:
                        add("WLAST_MISMATCH", "w", c, f"WLAST on beat {len(cur_w)}, expected on beat {expected} (AWLEN={expected - 1})")
                    if not last and expected is not None and len(cur_w) == expected:
                        add("WLAST_MISMATCH", "w", c, f"WLAST missing on beat {expected} (AWLEN={expected - 1})")
                        last = True  # close the burst so later beats are not mis-assigned
                if last:
                    w_bursts.append(cur_w)
                    cur_w = []
                    _pair_writes(aw_q, w_bursts, wait_b, add, c)
            elif ch == "b":
                tx = _pop_match(wait_b, idv)
                if tx is None:
                    add("UNEXPECTED_B", "b", c, "BVALID/BREADY handshake with no outstanding write")
                    continue
                tx.resp = RESP.get(_int(get(s, "b", "resp")), "OKAY") if itf.has("b", "resp") else "OKAY"
                tx.end_cycle, tx.end_time = c, t
                txns.append(tx)
                if tx.resp in ("SLVERR", "DECERR"):
                    add("ERROR_RESPONSE", "b", c, f"write to {_addr(tx)} answered {tx.resp}")
            elif ch == "r":
                tx = _first_match([x for x in reads if x.end_cycle is None], idv)
                if tx is None:
                    add("UNEXPECTED_R", "r", c, "RVALID/RREADY handshake with no outstanding read")
                    continue
                tx.beats.append((_hex(get(s, "r", "data"), width.get(("r", "data"))), None))
                resp = RESP.get(_int(get(s, "r", "resp")), "OKAY") if itf.has("r", "resp") else "OKAY"
                if resp != "OKAY" and tx.resp in (None, "OKAY"):
                    tx.resp = resp
                last = get(s, "r", "last") == "1" if itf.has("r", "last") else True
                n = len(tx.beats)
                if itf.has("r", "last") and last != (n == tx.length):
                    add("RLAST_MISMATCH", "r", c, f"RLAST {'on' if last else 'missing on'} beat {n}, expected on beat {tx.length} (ARLEN={tx.length - 1})")
                if last or n >= tx.length:
                    tx.end_cycle, tx.end_time = c, t
                    tx.resp = tx.resp or "OKAY"
                    if tx.resp in ("SLVERR", "DECERR"):
                        add("ERROR_RESPONSE", "r", c, f"read from {_addr(tx)} answered {tx.resp}")
        prev = s

    for tx in wait_b + [x for x in reads if x.end_cycle is None] + aw_q:
        add("NO_RESPONSE", "b" if tx.kind == "WRITE" else "r", len(edges) - 1 if edges else 0,
            f"{tx.kind} {_addr(tx)} (id {tx.id if tx.id is not None else '-'}) accepted at cycle {tx.start_cycle} but never completed")
        if tx not in txns:
            txns.append(tx)
    txns.sort(key=lambda x: (x.start_cycle, x.kind))
    return _report(vcd, itf, edges, txns, viol, stall, hs_count, active_cycles, width)


def _addr(tx):
    return f"0x{tx.addr:08X}" if tx.addr is not None else "?"


def _pair_writes(aw_q, w_bursts, wait_b, add, cycle):
    while aw_q and w_bursts:
        tx, beats = aw_q.pop(0), w_bursts.pop(0)
        tx.beats = beats
        wait_b.append(tx)


def _first_match(items, idv):
    for x in items:
        if idv is None or x.id is None or x.id == idv:
            return x
    return None


def _pop_match(items, idv):
    x = _first_match(items, idv)
    if x is not None:
        items.remove(x)
    return x


def _report(vcd, itf, edges, txns, viol, stall, hs_count, active_cycles, width):
    period = (edges[1] - edges[0]) if len(edges) > 1 else 0
    seconds = active_cycles * period * vcd.timescale_s if period else 0
    done = [t for t in txns if t.end_cycle is not None]

    def stats(kind):
        xs = [t for t in done if t.kind == kind]
        lat = [t.latency for t in xs]
        nbytes = sum(len(t.beats) * (t.size or 4) for t in xs)
        return {
            "count": sum(1 for t in txns if t.kind == kind), "completed": len(xs),
            "beats": sum(len(t.beats) for t in xs), "bytes": nbytes,
            "bandwidth_MBps": round(nbytes / seconds / 1e6, 2) if seconds else None,
            "latency_avg": round(sum(lat) / len(lat), 1) if lat else None,
            "latency_min": min(lat) if lat else None, "latency_max": max(lat) if lat else None,
            "errors": sum(1 for t in xs if t.resp in ("SLVERR", "DECERR")),
        }

    viol.sort(key=lambda v: (v.cycle, v.channel))
    return {
        "interface": itf.prefix, "kind": itf.kind, "clock": itf.clock, "reset": itf.reset,
        "data_width": width.get(("w", "data")) or width.get(("r", "data")),
        "addr_width": width.get(("aw", "addr")) or width.get(("ar", "addr")),
        "clock_period": period, "timescale": vcd.timescale_text, "cycles": len(edges), "active_cycles": active_cycles,
        "signals": sorted(f"{ch}{f}" for ch, f in itf.signals),
        "write": stats("WRITE"), "read": stats("READ"),
        "channels": [{
            "channel": ch.upper(), "handshakes": hs_count[ch], "stall_cycles": stall[ch],
            "utilization": round(hs_count[ch] / active_cycles, 3) if active_cycles else 0,
        } for ch in CHANNELS if itf.has(ch, "valid")],
        "violations": [{"rule": v.rule, "severity": v.severity, "channel": v.channel, "cycle": v.cycle,
                        "time": v.time, "message": v.message} for v in viol],
        "transactions": [{
            "kind": t.kind, "id": t.id, "addr": _addr(t), "length": t.length, "size": t.size, "burst": t.burst,
            "beats": len(t.beats), "data": [b[0] for b in t.beats], "strb": [b[1] for b in t.beats],
            "resp": t.resp, "status": t.status, "start_cycle": t.start_cycle, "end_cycle": t.end_cycle,
            "start_time": t.start_time, "end_time": t.end_time, "latency": t.latency,
            "waited": t.waited, "request_cycle": t.start_cycle - t.waited,
        } for t in txns],
    }


def analyze_vcd_text(text, timeout=16):
    vcd = parse_vcd(text)
    itfs = find_interfaces(vcd)
    return {
        "timescale": vcd.timescale_text, "end_time": vcd.end_time,
        "interfaces": [analyze_interface(vcd, itf, timeout) for itf in itfs],
        "rules": [{"rule": r, "severity": SEVERITY[r], "description": RULE_HELP[r]} for r in SEVERITY],
    }


def analyze_file(path, timeout=16):
    with open(path, encoding="utf-8", errors="replace") as f:
        return analyze_vcd_text(f.read(), timeout)
