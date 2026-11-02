"""Logic synthesis with Yosys (skipped when Yosys is not installed).   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from vlsi_toolkit import yosys_synth

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
HAVE_YOSYS = yosys_synth.engine()[0] is not None


def project():
    return [(p.name, p.read_text()) for p in sorted((EXAMPLES / "rtl_project").glob("*.v"))]


@unittest.skipUnless(HAVE_YOSYS, "Yosys not installed (pip install yowasp-yosys)")
class TestSynthesis(unittest.TestCase):
    def test_uart_hierarchy_totals_and_black_box(self):
        r = yosys_synth.synthesize(project(), top="uart_top")
        self.assertEqual(r["top"], "uart_top")
        self.assertEqual(r["black_boxes"], ["sram_32x8"])
        top = next(m for m in r["modules"] if m["name"] == "uart_top")
        self.assertEqual(top["submodules"].get("sync_fifo"), 2)          # parameterized module counted twice
        fifo = next(m for m in r["modules"] if m["name"] == "sync_fifo")
        self.assertTrue(fifo["parameterized"])
        self.assertGreater(r["totals"]["seq"], 2 * fifo["seq"])           # totals include both FIFO instances
        self.assertGreater(r["logic_depth"], 0)
        self.assertIn("module uart_top", r["netlist"])

    def test_flatten_gives_one_module_with_same_size(self):
        hier = yosys_synth.synthesize(project(), top="uart_top")
        flat = yosys_synth.synthesize(project(), top="uart_top", flatten=True)
        self.assertEqual([m["name"] for m in flat["modules"]], ["uart_top"])
        self.assertAlmostEqual(flat["totals"]["cells"], hier["totals"]["cells"], delta=hier["totals"]["cells"] * 0.05)

    def test_latches_and_multi_driver_are_reported(self):
        r = yosys_synth.synthesize([("lint_demo.v", (EXAMPLES / "lint_demo.v").read_text())])
        self.assertEqual(sorted(r["latches"]), ["lint_demo.y", "lint_demo.z"])
        self.assertTrue(any("conflicting drivers" in w for w in r["warnings"]))
        self.assertFalse(any("$auto$" in w or "\\" in w for w in r["warnings"]))   # readable messages

    def test_errors_are_readable(self):
        with self.assertRaisesRegex(yosys_synth.SynthError, r"my_file\.v:1.*syntax error"):
            yosys_synth.synthesize([("my_file.v", "module m(input a); assign b = ; endmodule")])
        with self.assertRaises(yosys_synth.SynthError):
            yosys_synth.synthesize(project(), top="bad name;")

    def test_api_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        c = TestClient(app)
        files = [{"name": n, "text": t} for n, t in project()]
        r = c.post("/api/rtl/synth", json={"files": files, "top": "uart_tx"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["top"], "uart_tx")
        self.assertEqual(c.post("/api/rtl/synth", json={"files": [{"name": "x.v", "text": "module x(; endmodule"}]}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
