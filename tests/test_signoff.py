"""Tests for the sign-off report analyzers (synthesis, power, SDC).   Run:  python -m unittest -v"""

import os
import tempfile
import unittest
from pathlib import Path

from vlsi_toolkit import power_report, sdc_check, synth_report

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
SIGNOFF = EXAMPLES / "signoff"


def uart_ports():
    return sdc_check.ports_from_rtl(
        (EXAMPLES / "rtl_project" / "uart_top.v").read_text()
    )[1]


class TestSynthesis(unittest.TestCase):
    def test_yosys_stat(self):
        r = synth_report.parse_file(SIGNOFF / "synth_yosys.rpt")
        self.assertEqual(
            (r["format"], r["top"], r["total_cells"]), ("yosys", "uart_top", 1667)
        )
        self.assertAlmostEqual(r["total_area"], 22105.222, places=3)
        fifo = next(m for m in r["modules"] if m["name"] == "sync_fifo")
        self.assertEqual(fifo["instances"], 2)
        self.assertAlmostEqual(fifo["percent"], 89.36, places=2)
        self.assertGreater(r["seq_cells"], 0)
        self.assertEqual(r["cell_types"][0]["cell"], "sky130_fd_sc_hd__mux2_1")

    def test_design_compiler_area(self):
        r = synth_report.parse_file(SIGNOFF / "synth_dc_area.rpt")
        self.assertEqual(r["format"], "design_compiler")
        self.assertAlmostEqual(r["total_area"], 23002.494025)
        self.assertAlmostEqual(r["comb_area"], 14822.61172)
        self.assertAlmostEqual(r["seq_area"], 6131.882305)
        self.assertEqual(
            [m["design"] for m in r["modules"]][:3],
            ["uart_top", "sync_fifo", "sync_fifo"],
        )

    def test_rejects_other_text(self):
        with self.assertRaises(ValueError):
            synth_report.parse_report("hello world")


class TestPower(unittest.TestCase):
    def test_example_report(self):
        r = power_report.parse_file(SIGNOFF / "power.rpt")
        t = r["totals"]
        self.assertAlmostEqual(t["dynamic"], 2.3482)
        self.assertAlmostEqual(
            t["leakage"], 0.041231, places=6
        )  # 41.231 uW converted to mW
        self.assertEqual(len(r["groups"]), 7)
        clock = next(g for g in r["groups"] if g["group"] == "clock_network")
        self.assertAlmostEqual(clock["leakage"], 0.00192, places=6)  # 1.92e3 nW
        # the hierarchy header is split over two lines in this report
        self.assertEqual(
            [h["name"] for h in r["hierarchy"]][:2], ["uart_top", "u_rx_fifo"]
        )
        self.assertEqual([h["depth"] for h in r["hierarchy"]], [0, 1, 1, 1, 1, 1])

    def test_summary_only_in_uw(self):
        r = power_report.parse_report(
            "Total Dynamic Power = 512.0 uW\nCell Leakage Power = 3.5 uW\n"
        )
        self.assertAlmostEqual(r["totals"]["total"], 0.5155)

    def test_rejects_other_text(self):
        with self.assertRaises(ValueError):
            power_report.parse_report("nothing here")


class TestSdc(unittest.TestCase):
    def rules(self, text, ports=None):
        return sorted(i["rule"] for i in sdc_check.check(text, ports)["issues"])

    def test_planted_mistakes(self):
        r = sdc_check.check((SIGNOFF / "uart_top.sdc").read_text(), uart_ports())
        self.assertEqual(r["counts"], {"ERROR": 3, "WARNING": 6, "INFO": 1})
        self.assertEqual(
            sorted({i["rule"] for i in r["issues"]}),
            sorted(
                [
                    "UNKNOWN_PORT",
                    "UNKNOWN_CLOCK",
                    "MISSING_OUTPUT_DELAY",
                    "NO_UNCERTAINTY",
                    "IO_DELAY_TOO_LARGE",
                    "MCP_WITHOUT_HOLD",
                    "BROAD_FALSE_PATH",
                    "UNRELATED_CLOCKS",
                ]
            ),
        )

    def test_fixed_file_is_clean(self):
        r = sdc_check.check((SIGNOFF / "uart_top_fixed.sdc").read_text(), uart_ports())
        self.assertEqual(r["issues"], [])

    def test_hold_pairs_with_setup_on_same_endpoints(self):
        base = "create_clock -name c -period 10 [get_ports clk]\nset_clock_uncertainty 0.1 [get_clocks c]\n"
        setup = (
            "set_multicycle_path 3 -setup -from [get_cells a/*] -to [get_cells b/*]\n"
        )
        self.assertEqual(self.rules(base + setup), ["MCP_WITHOUT_HOLD"])
        self.assertEqual(
            self.rules(
                base
                + setup
                + "set_multicycle_path 2 -hold -from [get_cells a/*] -to [get_cells b/*]\n"
            ),
            [],
        )
        # a hold on different endpoints does not count
        self.assertEqual(
            self.rules(
                base
                + setup
                + "set_multicycle_path 2 -hold -from [get_cells x/*] -to [get_cells b/*]\n"
            ),
            ["MCP_WITHOUT_HOLD"],
        )

    def test_clock_errors(self):
        self.assertEqual(self.rules("set_input_delay 1 [get_ports a]"), ["NO_CLOCK"])
        text = (
            "create_clock -name c -period 0 [get_ports clk]\ncreate_clock -name c -period 5 [get_ports clk]\n"
            "create_generated_clock -name g -divide_by 2 [get_pins div/Q]\nset_clock_uncertainty 0.1 [get_clocks *]\n"
        )
        self.assertEqual(
            self.rules(text), ["BAD_PERIOD", "DUPLICATE_CLOCK", "GENERATED_NO_SOURCE"]
        )

    def test_generated_clock_period_and_groups(self):
        text = (
            "create_clock -name a -period 10 [get_ports clk]\ncreate_clock -name b -period 7 [get_ports clk2]\n"
            "create_generated_clock -name a2 -source [get_ports clk] -master_clock a -divide_by 2 [get_pins d/Q]\n"
            "set_clock_uncertainty 0.1 [get_clocks *]\nset_clock_groups -asynchronous -group {a a2} -group {b}\n"
        )
        r = sdc_check.check(text)
        self.assertEqual(r["issues"], [])
        self.assertEqual(
            next(c for c in r["clocks"] if c["name"] == "a2")["period"], 20
        )

    def test_line_continuations_and_comments(self):
        text = (
            "# comment\ncreate_clock -name c \\\n   -period 4 [get_ports clk]  ;# 250 MHz\n"
            "set_clock_uncertainty 0.1 [get_clocks c]\n"
        )
        r = sdc_check.check(text)
        self.assertEqual(
            (r["issues"], r["clocks"][0]["freq_mhz"], r["clocks"][0]["line"]),
            ([], 250.0, 2),
        )


class TestSignoffApiAndWorkspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["VT_DATA_DIR"] = cls._tmp.name
        from fastapi.testclient import TestClient
        from api.main import app

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("VT_DATA_DIR", None)
        cls._tmp.cleanup()

    def post(self, url, body):
        r = self.client.post(url, json=body)
        return r.status_code, r.json()

    def test_endpoints(self):
        code, r = self.post(
            "/api/pd/synthesis",
            {"name": "a.rpt", "text": (SIGNOFF / "synth_yosys.rpt").read_text()},
        )
        self.assertEqual((code, r["total_cells"]), (200, 1667))
        code, r = self.post("/api/pd/power", {"name": "p.rpt", "text": "garbage"})
        self.assertEqual(code, 400)
        code, r = self.post(
            "/api/pd/sdc",
            {
                "name": "t.sdc",
                "text": (SIGNOFF / "uart_top.sdc").read_text(),
                "rtl": [
                    {
                        "name": "t.v",
                        "text": (EXAMPLES / "rtl_project/uart_top.v").read_text(),
                    }
                ],
            },
        )
        self.assertEqual(
            (code, r["rtl_top"], r["counts"]["ERROR"]), (200, "uart_top", 3)
        )
        self.assertGreaterEqual(self.client.get("/api/health").json()["api_version"], 5)

    def test_workspace_analysis_includes_signoff(self):
        from vlsi_toolkit import workspace

        r = workspace.analyze(EXAMPLES)
        names = {c["name"] for c in r["checks"]}
        self.assertTrue(
            {"Synthesis area", "Power", "Timing constraints"} <= names, names
        )
        self.assertIn("power_total_mw", r["metrics"])
        self.assertEqual(r["metrics"]["sdc_errors"], 3)
        self.assertEqual(r["errors"], [])


if __name__ == "__main__":
    unittest.main()
