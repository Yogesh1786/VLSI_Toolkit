"""UVM testbench and register-model generators.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from vlsi_toolkit import regmap_gen, uvm_gen, verilog_parser

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
try:
    from pyslang import syntax as sv_syntax
except ImportError:
    sv_syntax = None

UVM_MACRO_STUBS = """`define uvm_object_utils(T)
`define uvm_component_utils(T)
`define uvm_fatal(ID,MSG) $fatal(1, MSG);
`define uvm_error(ID,MSG) $error(MSG);
`define uvm_warning(ID,MSG) $warning(MSG);
`define uvm_info(ID,MSG,V) $display(MSG);
"""


def module(path):
    return verilog_parser.pick_module(verilog_parser.parse_file(EXAMPLES / path), None)


def inline_includes(files, name):
    text = files[name].replace('`include "uvm_macros.svh"', "")
    for inc, code in files.items():
        text = text.replace(f'`include "{inc}"', code)
    return text


class TestUvmTestbench(unittest.TestCase):
    def test_fifo_environment(self):
        r = uvm_gen.uvm_testbench(module("fifo.v"))
        f = r["files"]
        self.assertEqual(r["prefix"], "sync_fifo")
        for suffix in ("if", "seq_item", "sequence", "driver", "monitor", "agent", "scoreboard", "coverage", "env", "base_test", "pkg"):
            self.assertIn(f"sync_fifo_{suffix}.sv", f)
        self.assertIn("tb_top.sv", f)
        self.assertIn("rand logic [15:0] din;", f["sync_fifo_seq_item.sv"])
        self.assertIn("vif.drv_cb.wr_en <= req.wr_en;", f["sync_fifo_driver.sv"])
        self.assertIn("wait (vif.rst === 1'b0)", f["sync_fifo_driver.sv"])          # active-high reset
        self.assertIn(".clk(clk)", f["tb_top.sv"])
        self.assertIn("#(.DATA_W(16)", f["tb_top.sv"])                                 # parameters passed
        self.assertIn("auto_bin_max = 16", f["sync_fifo_coverage.sv"])                # wide input

    def test_active_low_reset_and_combinational_module(self):
        c = uvm_gen.uvm_testbench(module("counter.v"))
        self.assertIn("wait (vif.rst_n === 1'b1)", c["files"]["counter_driver.sv"])
        a = uvm_gen.uvm_testbench(module("alu.v"))
        self.assertIsNone(a["clock"])
        self.assertTrue(any("No clock" in n for n in a["notes"]))

    def test_custom_prefix(self):
        r = uvm_gen.uvm_testbench(module("counter.v"), prefix="cnt", num_items=7)
        self.assertIn("cnt_driver.sv", r["files"])
        self.assertIn("num_items = 7", r["files"]["cnt_sequence.sv"])

    @unittest.skipIf(sv_syntax is None, "pyslang not installed")
    def test_generated_code_is_valid_systemverilog(self):
        for path in ("fifo.v", "counter.v", "alu.v", "rtl_project/uart_tx.v"):
            files = uvm_gen.uvm_testbench(module(path))["files"]
            for name in [n for n in files if n.endswith(("_pkg.sv", "_if.sv")) or n == "tb_top.sv"]:
                tree = sv_syntax.SyntaxTree.fromText(UVM_MACRO_STUBS + inline_includes(files, name))
                errors = [str(d.code) for d in tree.diagnostics if d.isError()]
                self.assertEqual(errors, [], f"{path}: {name}")


class TestUvmRal(unittest.TestCase):
    def setUp(self):
        self.rm = regmap_gen.load_spec(EXAMPLES / "uart_regmap.json")
        self.r = uvm_gen.uvm_ral(self.rm)

    def test_register_classes_and_map(self):
        model = self.r["files"]["uart_reg_model.sv"]
        self.assertEqual(self.r["registers"], len(self.rm.registers))
        for reg in self.rm.registers:
            self.assertIn(f"class uart_{reg.name.lower()}_reg extends uvm_reg;", model)
            self.assertIn(f"default_map.add_reg({reg.name.lower()}, 'h{reg.offset:X},", model)
        self.assertIn("lock_model();", model)
        access = {r.access for r in self.rm.registers}
        if "W1C" in access:
            self.assertIn('"W1C", 1,', model)                    # W1C fields are volatile
        if "RO" in access:
            self.assertIn('"RO", 1,', model)

    @unittest.skipIf(sv_syntax is None, "pyslang not installed")
    def test_ral_is_valid_systemverilog(self):
        files = self.r["files"]
        tree = sv_syntax.SyntaxTree.fromText(UVM_MACRO_STUBS + inline_includes(files, "uart_ral_pkg.sv"))
        self.assertEqual([str(d.code) for d in tree.diagnostics if d.isError()], [])

    def test_api(self):
        from fastapi.testclient import TestClient
        from api.main import app
        c = TestClient(app)
        r = c.post("/api/verif/uvm", json={"name": "fifo.v", "text": (EXAMPLES / "fifo.v").read_text()})
        self.assertEqual((r.status_code, r.json()["prefix"]), (200, "sync_fifo"))
        z = c.post("/api/verif/uvm/zip", json={"name": "fifo.v", "text": (EXAMPLES / "fifo.v").read_text()})
        self.assertEqual(z.headers["content-type"], "application/zip")
        g = c.post("/api/rtl/regmap", json={"name": "s.json", "text": (EXAMPLES / "uart_regmap.json").read_text()}).json()
        self.assertIn("uart_reg_model.sv", g["outputs"])


if __name__ == "__main__":
    unittest.main()
