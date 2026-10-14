"""Tests for the project workspace and run history.   Run:  python -m unittest -v"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_DATA = tempfile.mkdtemp(prefix="vt_test_data_")


def setUpModule():
    os.environ["VT_DATA_DIR"] = _DATA  # never touch the real ~/.vlsi_toolkit


def tearDownModule():
    os.environ.pop("VT_DATA_DIR", None)
    shutil.rmtree(_DATA, ignore_errors=True)


class TestScan(unittest.TestCase):
    def test_classifies_example_files(self):
        from vlsi_toolkit import workspace

        s = workspace.scan(EXAMPLES)
        kinds = {f["path"]: f["kind"] for f in s["files"]}
        self.assertEqual(kinds["counter.v"], "rtl")
        self.assertEqual(kinds["sta_report.rpt"], "timing")  # sniffed from content
        self.assertEqual(kinds["uart_regmap.json"], "regmap")  # sniffed from content
        self.assertEqual(kinds["regression_logs/uart_burst_test_7781.log"], "log")
        self.assertEqual(kinds["axi/axi_buggy.vcd"], "vcd")
        self.assertEqual(kinds["lib/vt_demo.lib"], "liberty")
        self.assertFalse(s["truncated"])

    def test_skips_tool_folders_and_unknown_files(self):
        from vlsi_toolkit import workspace

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "node_modules").mkdir()
            (Path(d) / "node_modules" / "x.v").write_text("module x; endmodule")
            (Path(d) / "notes.txt").write_text("just notes")
            (Path(d) / "top.sv").write_text("module top; endmodule")
            self.assertEqual(
                [f["path"] for f in workspace.scan(d)["files"]], ["top.sv"]
            )

    def test_read_file_stays_inside(self):
        from vlsi_toolkit import workspace

        self.assertIn("module counter", workspace.read_file(EXAMPLES, "counter.v"))
        with self.assertRaises(ValueError):
            workspace.read_file(EXAMPLES, "../api/main.py")


class TestAnalyze(unittest.TestCase):
    def test_project_health(self):
        from vlsi_toolkit import workspace

        r = workspace.analyze(EXAMPLES / "rtl_project")
        self.assertEqual(
            {c["name"] for c in r["checks"]}, {"RTL lint", "Design hierarchy"}
        )
        self.assertEqual(r["metrics"]["lint_errors"], 0)
        self.assertEqual(r["metrics"]["fsms"], 2)
        self.assertEqual(
            r["health_score"], 75
        )  # lint pass + hierarchy warning (black box, unreachable state)
        self.assertEqual(r["errors"], [])

    def test_full_examples(self):
        from vlsi_toolkit import workspace

        m = workspace.analyze(EXAMPLES)["metrics"]
        for key in (
            "lint_errors",
            "reg_pass_rate",
            "setup_wns",
            "axi_errors",
            "utilization",
            "spice_issues",
        ):
            self.assertIn(key, m)


class TestHistory(unittest.TestCase):
    def test_save_list_trend_delete(self):
        from vlsi_toolkit import history

        ws = "C:/projects/demo_ws"
        a = history.save_snapshot(
            ws, {"lint_errors": 3, "setup_wns": -0.2}, label="a", ts=1000
        )
        history.save_snapshot(
            ws, {"lint_errors": 1, "setup_wns": -0.05}, label="b", ts=2000
        )
        snaps = history.list_snapshots(ws)
        self.assertEqual([s["label"] for s in snaps], ["b", "a"])  # newest first
        self.assertEqual(
            [p["value"] for p in history.trends(ws)["lint_errors"]], [3, 1]
        )  # oldest first
        self.assertEqual(history.delete_snapshot(a), 1)
        self.assertEqual(len(history.list_snapshots(ws)), 1)
        self.assertEqual(history.seed_demo(ws, days=5), 5)
        self.assertEqual(history.clear(ws, demo_only=True), 5)
        self.assertEqual(len(history.list_snapshots(ws)), 1)


class TestWorkspaceApi(unittest.TestCase):
    def test_flow(self):
        from api.main import app

        c = TestClient(app)
        w = c.get("/api/workspace").json()
        self.assertTrue(w["is_default"])
        opened = c.post(
            "/api/workspace/open", json={"path": str(EXAMPLES / "rtl_project")}
        ).json()
        self.assertEqual(opened["name"], "rtl_project")
        self.assertEqual(opened["recent"][0], str((EXAMPLES / "rtl_project").resolve()))
        self.assertEqual(c.get("/api/workspace/file?path=uart_tx.v").status_code, 200)
        self.assertEqual(
            c.get("/api/workspace/file?path=../counter.v").status_code, 404
        )
        self.assertEqual(
            c.post(
                "/api/workspace/open", json={"path": "Z:/no/such/folder"}
            ).status_code,
            404,
        )
        a = c.post("/api/workspace/analyze", json={"save": True, "label": "t"}).json()
        self.assertIn("snapshot_id", a)
        h = c.get("/api/history").json()
        self.assertEqual(h["snapshots"][0]["label"], "t")
        self.assertIn("lint_errors", h["trends"])
        self.assertTrue(c.post("/api/workspace/reset").json()["is_default"])


if __name__ == "__main__":
    unittest.main()
