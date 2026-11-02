"""slang compiler checks and the reset-domain-crossing lint rule.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from vlsi_toolkit import lint, sv_compile

EX = Path(__file__).resolve().parent.parent / "examples"


class TestRdc(unittest.TestCase):
    def test_demo_has_exactly_one_crossing(self):
        found = [i for i in lint.lint_files([EX / "rdc_demo.v"]) if i.rule == "RDC_UNSYNC"]
        self.assertEqual(len(found), 1)
        self.assertIn("'cfg'", found[0].message)
        self.assertIn("'state'", found[0].message)

    def test_no_false_positives(self):
        files = [EX / f for f in ("cdc_demo.v", "counter.v", "fifo.v", "axi/uart_axil.v")] + sorted((EX / "rtl_project").glob("*.v"))
        self.assertEqual([i for i in lint.lint_files(files) if i.rule == "RDC_UNSYNC"], [])


@unittest.skipUnless(sv_compile.available(), "pyslang not installed")
class TestCompiler(unittest.TestCase):
    def rules(self, files):
        return [(i["rule"], i["line"]) for i in sv_compile.check(files)["issues"]]

    def test_width_undriven_unused_and_includes(self):
        src = """`include "defs.vh"
module t(input logic clk, input logic [`W-1:0] a, input logic spare, output logic [3:0] y, output logic z);
  logic [7:0] never_used;
  logic never_set;
  assign y = a;
  assign z = never_set;
endmodule
"""
        r = sv_compile.check([("defs.vh", "`define W 8\n"), ("t.sv", src)])
        rules = {i["rule"] for i in r["issues"]}
        self.assertTrue({"WIDTH_TRUNCATION", "UNDRIVEN_SIGNAL", "UNUSED_SIGNAL"} <= rules, rules)
        self.assertEqual(r["top_modules"], ["t"])
        self.assertTrue(all(i["file"] == "t.sv" for i in r["issues"]))

    def test_syntax_error_is_reported_with_line(self):
        r = self.rules([("bad.sv", "module m(input a);\n  assign b = a +;\nendmodule\n")])
        self.assertIn(("SV_ERROR", 2), r)

    def test_black_box_is_a_warning_not_an_error(self):
        files = [(p.name, p.read_text()) for p in sorted((EX / "rtl_project").glob("*.v"))]
        issues = sv_compile.check(files)["issues"]
        self.assertFalse([i for i in issues if i["severity"] == "ERROR"])
        self.assertTrue(any(i["rule"] == "UNKNOWN_MODULE" and "sram_32x8" in i["message"] for i in issues))

    def test_lint_api_merges_compiler_findings(self):
        from fastapi.testclient import TestClient
        from api.main import app
        c = TestClient(app)
        files = [{"name": "bad.sv", "text": "module m(input a);\n  assign b = a +;\nendmodule\n"}]
        r = c.post("/api/rtl/lint", json={"files": files}).json()
        self.assertTrue(r["compiler"]["ran"])
        self.assertTrue(any(i["rule"] == "SV_ERROR" and i["source"] == "compiler" for i in r["issues"]))
        off = c.post("/api/rtl/lint", json={"files": files, "compiler": False}).json()
        self.assertFalse(any(i["source"] == "compiler" for i in off["issues"]))


if __name__ == "__main__":
    unittest.main()
