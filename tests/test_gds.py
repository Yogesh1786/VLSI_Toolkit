"""GDS viewer backend (skipped when gdstk is not installed).   Run:  python -m unittest -v"""

import base64
import unittest
from pathlib import Path

from vlsi_toolkit import gds_view

EX = Path(__file__).resolve().parent.parent / "examples" / "gds" / "demo_core.gds"


@unittest.skipUnless(gds_view.available(), "gdstk not installed")
class TestGds(unittest.TestCase):
    def test_example_layout(self):
        r = gds_view.analyze_file(EX)
        self.assertEqual((r["cell"], r["top_cells"]), ("demo_core", ["demo_core"]))
        self.assertEqual({u["cell"]: u["instances"] for u in r["usage"]}, {"INV_X1": 48, "NAND2_X1": 24})
        names = {l["name"] for l in r["layers"]}
        self.assertTrue({"nwell", "diff", "poly", "met1", "met2", "prBoundary"} <= names, names)
        met2 = next(l for l in r["layers"] if l["name"] == "met2")
        self.assertEqual(met2["polygons"], 5)
        self.assertTrue(met2["path"].startswith("M"))
        self.assertAlmostEqual(r["bbox"]["width"], 22.4, places=3)
        self.assertFalse(r["truncated"])

    def test_sub_cell_and_bad_input(self):
        inv = gds_view.analyze_file(EX, cell="INV_X1")
        self.assertEqual((inv["cell"], inv["instances"]), ("INV_X1", 0))
        with self.assertRaises(gds_view.GdsError):
            gds_view.analyze_file(EX, cell="NO_SUCH_CELL")
        with self.assertRaises(gds_view.GdsError):
            gds_view.analyze(b"definitely not gds", "x.gds")

    def test_api(self):
        from fastapi.testclient import TestClient
        from api.main import app
        c = TestClient(app)
        self.assertEqual(c.get("/api/pd/gds/example").json()["cell"], "demo_core")
        r = c.post("/api/pd/gds", json={"name": "d.gds", "data": base64.b64encode(EX.read_bytes()).decode(), "cell": "NAND2_X1"})
        self.assertEqual((r.status_code, r.json()["cell"]), (200, "NAND2_X1"))
        self.assertEqual(c.post("/api/pd/gds", json={"name": "d.gds", "data": base64.b64encode(b"junk").decode()}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
