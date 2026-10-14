"""Tests for the CDC lint rules and the SVA generator.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from vlsi_toolkit import lint, sva

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestCdc(unittest.TestCase):
    def test_demo_finds_three_crossing_bugs(self):
        issues = [i for i in lint.lint_files([EXAMPLES / "cdc_demo.v"]) if i.rule.startswith("CDC")]
        rules = sorted(i.rule for i in issues)
        self.assertEqual(rules, ["CDC_MULTIBIT", "CDC_SINGLE_FLOP", "CDC_UNSYNC"])
        self.assertTrue(all("flag_a" not in i.message for i in issues))  # the proper 2-flop sync is accepted

    def test_single_clock_designs_have_no_cdc(self):
        for f in ("counter.v", "fifo.v", "rtl_project/uart_tx.v", "axi/uart_axil.v"):
            self.assertFalse([i for i in lint.lint_files([EXAMPLES / f]) if i.rule.startswith("CDC")], f)

    def test_reset_is_not_a_clock(self):
        src = """module m(input clk, input rst_n, input d, output reg q);
          always @(posedge clk or negedge rst_n) if (!rst_n) q <= 0; else q <= d;
        endmodule"""
        self.assertEqual(lint.lint_text(src), [])


class TestSva(unittest.TestCase):
    def gen(self, path, **kw):
        return sva.generate((EXAMPLES / path).read_text(), filename=Path(path).name, **kw)

    def test_fsm_assertions(self):
        r = self.gen("rtl_project/uart_tx.v")
        self.assertEqual((r["module"], r["clock"], r["reset"]), ("uart_tx", "clk", "rst_n"))
        names = [a["name"] for a in r["assertions"]]
        self.assertIn("a_state_legal", names)
        self.assertIn("a_state_reset", names)
        self.assertIn("c_state_idle_to_start", names)
        legal = next(a for a in r["assertions"] if a["name"] == "a_state_legal")
        self.assertIn("state inside {IDLE, START, DATA, PARITY, STOP}", legal["code"])
        self.assertIn("disable iff (!rst_n)", legal["code"])

    def test_unreachable_state_gets_cover(self):
        r = self.gen("rtl_project/uart_rx.v")
        self.assertIn("c_state_reach_break_det", [a["name"] for a in r["assertions"]])

    def test_axi_assertions(self):
        r = self.gen("axi/uart_axil.v")
        self.assertEqual(r["axi_prefixes"], ["s_axil_"])
        aw = next(a for a in r["assertions"] if a["name"] == "a_s_axil_aw_valid_stable")
        self.assertIn("(s_axil_awvalid && !s_axil_awready) |=> s_axil_awvalid", aw["code"])
        self.assertEqual(r["counts"]["AXI"], 20)  # 5 channels x (stable, payload, known, cover)

    def test_options_and_onehot(self):
        src = """module arb(input clk, input rst_n, input [3:0] req, output reg [3:0] grant);
          always @(posedge clk) grant <= req & -req;
        endmodule"""
        r = sva.generate(src, options={"outputs": False})
        self.assertEqual([a["name"] for a in r["assertions"]], ["a_grant_onehot0"])
        self.assertIn("$onehot0(grant)", r["code"])

    def test_no_clock_is_reported(self):
        with self.assertRaises(ValueError):
            sva.generate("module c(input a, output y); assign y = ~a; endmodule")


if __name__ == "__main__":
    unittest.main()
