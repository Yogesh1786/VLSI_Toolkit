"""Tests for the AXI protocol checker / transaction viewer.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from vlsi_toolkit import axi

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "axi"


def make_vcd(signals, cycles):
    """Tiny VCD writer: signals = {name: width}, cycles = [ {name: value} per clock cycle ]."""
    ids = {n: chr(40 + i) for i, n in enumerate(signals)}
    out = [
        "$timescale 1ns $end",
        "$scope module top $end",
        "$var wire 1 ! clk $end",
        '$var wire 1 " aresetn $end',
    ]
    out += [f"$var wire {w} {ids[n]} {n} $end" for n, w in signals.items()]
    out += ["$upscope $end", "$enddefinitions $end"]
    state = {n: 0 for n in signals}
    for c, values in enumerate(cycles):
        state.update(values)
        out += [f"#{10 * c}", "0!", '0"' if c < 2 else '1"', f"#{10 * c + 1}"]
        for n, w in signals.items():
            v = state[n]
            out.append(f"{v}{ids[n]}" if w == 1 else f"b{v:b} {ids[n]}")
        out += [f"#{10 * c + 5}", "1!"]
    out.append(f"#{10 * len(cycles)}")
    return "\n".join(out)


LITE = {
    f"m_axil_{n}": w
    for n, w in [
        ("awvalid", 1),
        ("awready", 1),
        ("awaddr", 16),
        ("wvalid", 1),
        ("wready", 1),
        ("wdata", 32),
        ("wstrb", 4),
        ("bvalid", 1),
        ("bready", 1),
        ("bresp", 2),
        ("arvalid", 1),
        ("arready", 1),
        ("araddr", 16),
        ("rvalid", 1),
        ("rready", 1),
        ("rdata", 32),
        ("rresp", 2),
    ]
}


def lite_cycles(drop_valid=False):
    p = "m_axil_"
    c = [{} for _ in range(16)]
    c[3] = {
        p + "awvalid": 1,
        p + "awaddr": 0x10,
        p + "wvalid": 1,
        p + "wdata": 0xABCD,
        p + "wstrb": 15,
        p + "bready": 1,
    }
    c[4] = {p + "awready": 1, p + "wready": 1}  # handshake (AW + W)
    c[5] = {p + "awvalid": 0, p + "awready": 0, p + "wvalid": 0, p + "wready": 0}
    c[6] = {p + "bvalid": 1}
    c[7] = {p + "bvalid": 0, p + "arvalid": 1, p + "araddr": 0x10, p + "rready": 1}
    if drop_valid:
        c[8] = {p + "arvalid": 0}  # dropped before ARREADY
        c[9] = {p + "arvalid": 1}
    c[10] = {p + "arready": 1}
    c[11] = {p + "arvalid": 0, p + "arready": 0, p + "rvalid": 1, p + "rdata": 0xABCD}
    c[12] = {p + "rvalid": 0}
    return c


class TestAxiExamples(unittest.TestCase):
    def test_clean_traffic_has_no_violations(self):
        r = axi.analyze_file(EXAMPLES / "axi_clean.vcd")
        itf = r["interfaces"][0]
        self.assertEqual(itf["kind"], "AXI4")
        self.assertEqual(itf["violations"], [])
        self.assertEqual(itf["write"]["completed"], 4)
        self.assertEqual(itf["read"]["completed"], 4)
        burst = next(
            t for t in itf["transactions"] if t["kind"] == "WRITE" and t["length"] == 8
        )
        self.assertEqual(burst["data"][0], "0xCAFE0000")
        self.assertEqual(burst["beats"], 8)

    def test_buggy_traffic_finds_every_planted_bug(self):
        itf = axi.analyze_file(EXAMPLES / "axi_buggy.vcd")["interfaces"][0]
        rules = [v["rule"] for v in itf["violations"]]
        for rule in (
            "VALID_DROPPED",
            "PAYLOAD_CHANGED",
            "WLAST_MISMATCH",
            "BOUNDARY_4KB",
            "X_ON_PAYLOAD",
            "READY_TIMEOUT",
            "NO_RESPONSE",
        ):
            self.assertEqual(rules.count(rule), 1, rule)
        self.assertEqual(
            rules.count("ERROR_RESPONSE"), 2
        )  # SLVERR on a write, DECERR on a read
        statuses = {t["addr"]: t["status"] for t in itf["transactions"]}
        self.assertEqual(statuses["0x40002000"], "SLVERR")
        self.assertEqual(statuses["0x40000300"], "NO_RESPONSE")


class TestAxiLite(unittest.TestCase):
    def test_lite_detection_and_transactions(self):
        r = axi.analyze_vcd_text(make_vcd(LITE, lite_cycles()))
        itf = r["interfaces"][0]
        self.assertEqual(itf["kind"], "AXI4-Lite")
        self.assertEqual(itf["interface"], "top.m_axil_")
        self.assertEqual(itf["clock"], "top.clk")
        self.assertEqual(itf["violations"], [])
        kinds = [
            (t["kind"], t["addr"], t["data"], t["status"]) for t in itf["transactions"]
        ]
        self.assertEqual(
            kinds,
            [
                ("WRITE", "0x00000010", ["0x0000ABCD"], "OKAY"),
                ("READ", "0x00000010", ["0x0000ABCD"], "OKAY"),
            ],
        )

    def test_lite_valid_drop(self):
        itf = axi.analyze_vcd_text(make_vcd(LITE, lite_cycles(drop_valid=True)))[
            "interfaces"
        ][0]
        self.assertEqual([v["rule"] for v in itf["violations"]], ["VALID_DROPPED"])
        self.assertEqual(itf["violations"][0]["channel"], "AR")

    def test_no_axi_signals(self):
        self.assertEqual(
            axi.analyze_vcd_text(make_vcd({"data": 8}, [{"data": 1}] * 4))[
                "interfaces"
            ],
            [],
        )


class TestAxiApi(unittest.TestCase):
    def test_endpoint(self):
        client = TestClient(app)
        text = (EXAMPLES / "axi_buggy.vcd").read_text()
        r = client.post(
            "/api/verif/axi",
            json={"name": "axi_buggy.vcd", "text": text, "timeout": 16},
        ).json()
        self.assertEqual(len(r["interfaces"][0]["violations"]), 9)
        r = client.post(
            "/api/verif/axi",
            json={"name": "axi_buggy.vcd", "text": text, "timeout": 50},
        ).json()
        self.assertNotIn(
            "READY_TIMEOUT", [v["rule"] for v in r["interfaces"][0]["violations"]]
        )
        self.assertIn(
            "error",
            client.post(
                "/api/verif/axi",
                json={"name": "x.vcd", "text": make_vcd({"d": 1}, [{}])},
            ).json(),
        )


if __name__ == "__main__":
    unittest.main()
