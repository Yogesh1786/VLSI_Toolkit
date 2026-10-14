"""Tests for the AXI4-Lite slave + testbench generator.   Run:  python -m unittest -v"""

import re
import tempfile
import unittest
from pathlib import Path

from vlsi_toolkit import regmap_gen, verilog_parser

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class TestAxiLiteSlave(unittest.TestCase):
    def setUp(self):
        self.rm = regmap_gen.load_spec(EXAMPLES / "uart_regmap.json")
        self.v = regmap_gen.gen_axi_lite(self.rm)
        self.tb = regmap_gen.gen_axi_lite_tb(self.rm)

    def test_interface(self):
        mod = verilog_parser.parse_text(self.v)[0]
        self.assertEqual(mod.name, "uart_axil")
        ports = {p.name: p for p in mod.ports}
        for name in (
            "s_axil_awvalid",
            "s_axil_awready",
            "s_axil_wstrb",
            "s_axil_bresp",
            "s_axil_arready",
            "s_axil_rdata",
            "s_axil_rresp",
        ):
            self.assertIn(name, ports)
        self.assertEqual(ports["s_axil_wstrb"].width, 4)
        self.assertEqual(ports["s_axil_rdata"].width, 32)
        # hardware side follows the access type of each register
        self.assertEqual(ports["status_i"].direction, "input")  # RO
        self.assertEqual(ports["int_status_set_i"].direction, "input")  # W1C
        self.assertEqual(ports["ctrl_o"].direction, "output")  # RW
        self.assertNotIn("tx_data_i", ports)  # WO has no input

    def test_behaviour_is_described(self):
        self.assertIn("RESP_SLVERR", self.v)  # unmapped addresses
        self.assertIn("strb_bits[8*gi +: 8] = {8{w_strb[gi]}}", self.v)  # byte strobes
        self.assertIn("assign s_axil_awready = !aw_full && !s_axil_bvalid;", self.v)
        self.assertIn(
            "ADDR_TX_DATA: r_value = {DATA_WIDTH{1'b0}};  // write-only", self.v
        )
        self.assertTrue(self.v.startswith("`timescale"))

    def test_generated_rtl_is_lint_clean(self):
        from vlsi_toolkit import lint

        self.assertEqual(
            [i for i in lint.lint_text(self.v, "uart_axil.v") if i.severity != "INFO"],
            [],
        )

    def test_testbench(self):
        self.assertIn("module tb_uart_axil;", self.tb)
        self.assertIn('$display("TEST PASSED")', self.tb)
        self.assertNotRegex(
            self.tb, r"\bexpect\s*\("
        )  # 'expect' is a SystemVerilog keyword
        self.assertIn('check_eq("unmapped write resp", resp, 2)', self.tb)
        self.assertIn("int_status_set_i =", self.tb)  # W1C exercised
        self.assertEqual(len(re.findall(r"axi_read\(", self.tb)) >= 5, True)

    def test_generate_all_writes_axil_files(self):
        with tempfile.TemporaryDirectory() as d:
            _, files = regmap_gen.generate_all(EXAMPLES / "uart_regmap.json", d)
            names = sorted(f.name for f in files)
            self.assertIn("uart_axil.v", names)
            self.assertIn("tb_uart_axil.v", names)


if __name__ == "__main__":
    unittest.main()
