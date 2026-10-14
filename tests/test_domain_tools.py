"""Tests for lint, regress, pd_analyzer and spice.   Run:  python -m unittest -v"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from vlsi_toolkit import lint, pd_analyzer, regress, spice
from vlsi_toolkit.cli import main


def run_cli(argv):
    """Run the CLI with its printed output hidden; return the exit code."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return main(argv)


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestLint(unittest.TestCase):
    def rules(self, src):
        return sorted((i.rule, i.line) for i in lint.lint_text(src))

    def test_demo_file_finds_all_planted_bugs(self):
        issues = lint.lint_files([EXAMPLES / "lint_demo.v"])
        found = {i.rule for i in issues}
        self.assertEqual(
            found,
            {
                "BLOCKING_IN_SEQ",
                "LATCH_RISK",
                "CASE_NO_DEFAULT",
                "SENS_LIST",
                "NONBLOCKING_IN_COMB",
                "MULTI_DRIVER",
            },
        )
        multi = [i for i in issues if i.rule == "MULTI_DRIVER"]
        self.assertEqual(len(multi), 1)  # 'bits[0]' / 'bits[1]' must NOT be flagged
        self.assertIn("'w'", multi[0].message)

    def test_clean_examples_have_no_issues(self):
        for f in ("counter.v", "fifo.v", "alu.v"):
            self.assertEqual(lint.lint_files([EXAMPLES / f]), [], f)

    def test_default_assignment_prevents_latch_warning(self):
        src = """module m(input a, en, output reg y);
        always @(*) begin
            y = 1'b0;
            if (en) y = a;
        end
        endmodule"""
        self.assertEqual(self.rules(src), [])

    def test_unique_case_needs_no_default(self):
        src = """module m(input [1:0] s, output logic y);
        always_comb begin
            y = 0;
            unique case (s) 2'd0: y = 1; 2'd1: y = 0; endcase
        end
        endmodule"""
        self.assertEqual(self.rules(src), [])

    def test_same_name_in_two_modules_is_not_multi_driver(self):
        src = "module a(output w); assign w = 1'b0; endmodule\nmodule b(output w); assign w = 1'b1; endmodule"
        self.assertEqual(self.rules(src), [])

    def test_for_loop_variable_in_clocked_block(self):
        src = """module m(input clk, input [3:0] d, output reg [3:0] q);
        integer i;
        always @(posedge clk) for (i = 0; i < 4; i = i + 1) q[i] <= d[i];
        endmodule"""
        self.assertEqual(self.rules(src), [])


class TestRegress(unittest.TestCase):
    def setUp(self):
        self.results = {
            r.file.split("\\")[-1].split("/")[-1]: r
            for r in regress.analyze_folder(EXAMPLES / "regression_logs")
        }

    def test_statuses(self):
        status = {k: r.status for k, r in self.results.items()}
        self.assertEqual(status["uart_basic_test_1001.log"], "PASS")
        self.assertEqual(status["counter_smoke_test.log"], "PASS")
        self.assertEqual(status["uart_burst_test_7781.log"], "FAIL")
        self.assertEqual(status["uart_timeout_test_4242.log"], "FAIL")
        self.assertEqual(
            status["fifo_directed_test.log"], "FAIL"
        )  # Questa "# ** Error"
        self.assertEqual(status["uart_reset_test_3141.log"], "INCOMPLETE")

    def test_counts_test_name_and_seed(self):
        r = self.results["uart_burst_test_7781.log"]
        self.assertEqual(
            (r.test, r.seed, r.errors, r.fatals, r.warnings),
            ("uart_burst_test", "7781", 2, 0, 1),
        )
        self.assertEqual(self.results["uart_timeout_test_4242.log"].fatals, 1)

    def test_signatures_group_same_bug(self):
        groups = regress.signatures(list(self.results.values()))
        top_sig, top_tests = next(iter(groups.items()))
        self.assertEqual(len(top_tests), 3)
        self.assertIn("SB_MISMATCH", top_sig)

    def test_signature_normalization(self):
        a = regress.error_signature(
            "UVM_ERROR /a/b.sv(12) @ 100: uvm_test_top.env [X] got 0x1F at 55"
        )
        b = regress.error_signature(
            "UVM_ERROR /a/b.sv(12) @ 999: uvm_test_top.env [X] got 0xAA at 7"
        )
        self.assertEqual(a, b)


class TestPd(unittest.TestCase):
    def setUp(self):
        self.d, self.lef = pd_analyzer.parse_files(
            EXAMPLES / "pd" / "demo.def", [EXAMPLES / "pd" / "demo.lef"]
        )

    def test_parse(self):
        self.assertEqual(self.d.design, "uart_top")
        self.assertEqual(self.d.dbu, 1000)
        self.assertEqual(self.d.die, (0, 0, 160000, 120000))
        self.assertEqual(len(self.d.rows), 40)
        self.assertEqual(len(self.d.components), 1404)
        self.assertEqual(self.d.nets, 1134)
        self.assertEqual(self.lef.sites["unithd"], (0.46, 2.72))

    def test_analysis(self):
        a = pd_analyzer.analyze(self.d, self.lef)
        self.assertAlmostEqual(a["die_um2"], 19200.0)
        self.assertAlmostEqual(a["core_um2"], 40 * 326 * 0.46 * 2.72, places=3)
        self.assertAlmostEqual(a["macro_area"], 60.0 * 48.96, places=3)
        self.assertEqual(a["status"]["UNPLACED"], 3)
        self.assertEqual(a["categories"]["Macro"]["count"], 1)
        self.assertTrue(0.5 < a["utilization"] < 0.7)

    def test_categorize(self):
        c = pd_analyzer.categorize
        self.assertEqual(c("sky130_fd_sc_hd__dfrtp_1"), "Flip-flop")
        self.assertEqual(c("sky130_fd_sc_hd__clkbuf_8"), "Clock cell")
        self.assertEqual(c("sky130_fd_sc_hd__dlygate4sd3_1"), "Buffer/Inverter")
        self.assertEqual(c("sky130_fd_sc_hd__dlxtp_1"), "Latch")
        self.assertEqual(c("sky130_fd_sc_hd__decap_4"), "Physical-only")
        self.assertEqual(c("NAND2X1"), "Logic")
        self.assertEqual(c("DFFRX2"), "Flip-flop")
        self.assertEqual(c("sram_64x32", self.lef), "Macro")

    def test_polygon_die(self):
        d = pd_analyzer.parse_def(
            "DIEAREA ( 0 0 ) ( 0 100 ) ( 50 100 ) ( 50 50 ) ( 100 50 ) ( 100 0 ) ;"
        )
        self.assertEqual(d.die_area_dbu, 100 * 50 + 50 * 50)  # L-shaped die


class TestSpice(unittest.TestCase):
    def test_values(self):
        self.assertAlmostEqual(spice.spice_value("0.42u"), 0.42e-6)
        self.assertAlmostEqual(spice.spice_value("10f"), 10e-15)
        self.assertAlmostEqual(spice.spice_value("2meg"), 2e6)
        self.assertAlmostEqual(spice.spice_value("1.8"), 1.8)
        self.assertAlmostEqual(spice.spice_value("{wn*2}", {"wn": 1e-6}), 2e-6)
        self.assertIsNone(spice.spice_value("unknown_param"))

    def test_inverter_chain(self):
        nl = spice.parse_netlist_file(EXAMPLES / "analog" / "inverter_chain.sp")
        kinds = sorted(d.kind for d in nl.devices)
        self.assertEqual(
            kinds, ["c", "m", "m", "v", "v", "x", "x", "x"]
        )  # .control block ignored
        mos = {r["name"]: r for r in spice.mosfet_table(nl)}
        self.assertAlmostEqual(mos["M1"]["w"], 0.84e-6)
        self.assertAlmostEqual(mos["M1"]["w_over_l"], 5.6)
        self.assertEqual(nl.measures, ["tphl", "tplh", "trise"])
        self.assertEqual(spice.connectivity_issues(nl), [])

    def test_buggy_netlist(self):
        nl = spice.parse_netlist_file(EXAMPLES / "analog" / "buggy_bias.sp")
        text = " ".join(spice.connectivity_issues(nl))
        for node in ("bias_en", "ntail", "ntial"):
            self.assertIn(f"'{node}'", text)

    def test_floating_gate(self):
        nl = spice.parse_netlist(
            "title\nM1 d g 0 0 nch W=1u L=1u\nM2 d2 g 0 0 nch W=1u L=1u\nR1 d d2 1k\n.op\n"
        )
        self.assertTrue(
            any("floating gate" in i for i in spice.connectivity_issues(nl))
        )

    def test_sweep(self):
        self.assertEqual(spice.parse_sweep_values("1.6:2.0:0.2"), ["1.6", "1.8", "2"])
        self.assertEqual(spice.parse_sweep_values("1n,2n"), ["1n", "2n"])
        text = "t\n.param VDD=1.8 WN=1u\nV1 a 0 {VDD}\n"
        out = dict(spice.make_sweep(text, "VDD", ["1.2"]))
        self.assertIn(".param VDD=1.2 WN=1u", out["1.2"])
        added = dict(spice.make_sweep(text, "TEMP", ["85"]))
        self.assertIn(".param TEMP=85", added["85"])

    def test_measure(self):
        waves = spice.load_waveforms(EXAMPLES / "analog" / "inverter_tran.csv")
        vin = spice.measure(waves, "in")
        self.assertAlmostEqual(
            vin["rise_time"], 40e-12, delta=1e-12
        )  # 10-90% of a 50 ps edge
        self.assertAlmostEqual(vin["period"], 2e-9, delta=1e-12)
        self.assertAlmostEqual(vin["duty"], 0.525, places=3)
        out = spice.measure(waves, "v(out)", ref="in", vdd=1.8)
        self.assertTrue(30e-12 < out["tpd"] < 60e-12)
        self.assertGreater(
            out["rise_time"], out["fall_time"]
        )  # weaker pull-up in the model

    def test_wrdata_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "w.txt"
            p.write_text("0 0 0 1.8\n1e-9 0.9 1e-9 0.9\n2e-9 1.8 2e-9 0\n")
            waves = spice.load_waveforms(p)
            self.assertEqual(len(waves), 3)  # duplicate time column removed


class TestCliDomain(unittest.TestCase):
    def test_commands(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                run_cli(["lint", str(EXAMPLES / "lint_demo.v")]), 1
            )  # has an ERROR
            self.assertEqual(run_cli(["lint", str(EXAMPLES / "counter.v")]), 0)
            self.assertEqual(
                run_cli(
                    [
                        "regress",
                        str(EXAMPLES / "regression_logs"),
                        "--html",
                        str(Path(d) / "r.html"),
                    ]
                ),
                2,
            )
            self.assertTrue((Path(d) / "r.html").exists())
            self.assertEqual(
                run_cli(
                    [
                        "pd",
                        str(EXAMPLES / "pd" / "demo.def"),
                        "--lef",
                        str(EXAMPLES / "pd" / "demo.lef"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                run_cli(["spice", "info", str(EXAMPLES / "analog" / "buggy_bias.sp")]),
                0,
            )
            self.assertEqual(
                run_cli(
                    [
                        "spice",
                        "sweep",
                        str(EXAMPLES / "analog" / "inverter_chain.sp"),
                        "--param",
                        "VDD=1.2,1.8",
                        "-o",
                        d,
                    ]
                ),
                0,
            )
            self.assertEqual(len(list(Path(d).glob("*.sp"))), 2)
            self.assertEqual(
                run_cli(
                    [
                        "spice",
                        "measure",
                        str(EXAMPLES / "analog" / "inverter_tran.csv"),
                        "-s",
                        "out",
                        "--ref",
                        "in",
                    ]
                ),
                0,
            )


if __name__ == "__main__":
    unittest.main()
