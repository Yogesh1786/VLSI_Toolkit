"""Tests for hierarchy/FSM, compare runs and Liberty explorer.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app
from vlsi_toolkit import compare, hierarchy, liberty, regress, timing_report

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
client = TestClient(app)


def project_files():
    return [
        (p.name, p.read_text(encoding="utf-8"))
        for p in sorted((EXAMPLES / "rtl_project").glob("*.v"))
    ]


class TestHierarchy(unittest.TestCase):
    def setUp(self):
        self.r = hierarchy.analyze_project(project_files())

    def test_tree(self):
        self.assertEqual(self.r["main_top"], "uart_top")
        self.assertEqual(self.r["unused"], ["debug_mux"])
        self.assertEqual(self.r["undefined"], ["sram_32x8"])
        top = self.r["trees"][0]
        self.assertEqual(
            [c["instance"] for c in top["children"]],
            ["u_baud", "u_tx_fifo", "u_tx", "u_rx", "u_rx_fifo", "u_scratch"],
        )
        self.assertEqual(top["children"][1]["params"], {"DATA_W": "8", "DEPTH": "16"})
        self.assertFalse(top["children"][-1]["defined"])

    def test_fsms(self):
        fsms = {f["module"]: f for f in self.r["fsms"]}
        self.assertEqual(
            set(fsms), {"uart_tx", "uart_rx"}
        )  # the output-logic case in uart_tx is not an FSM
        tx = fsms["uart_tx"]
        self.assertEqual(tx["reset_state"], "IDLE")
        self.assertIn(
            {"src": "DATA", "dst": "PARITY", "condition": "tick && bit_idx == 3'd7"},
            tx["transitions"],
        )
        rx = fsms["uart_rx"]
        self.assertEqual(rx["unreachable"], ["BREAK_DET"])
        self.assertIn(
            {"src": "CHECK_STOP", "dst": "FRAME_ERR", "condition": "tick && !rx"},
            rx["transitions"],
        )

    def test_recursion_and_comments(self):
        src = """module a(input x); a u_self (.x(x)); endmodule  // recursive
                 module top(input y); /* b u_fake (.q(y)); */ a u_a (.x(y)); endmodule"""
        r = hierarchy.analyze_project([("t.v", src)])
        self.assertEqual(r["main_top"], "top")
        self.assertEqual(r["undefined"], [])  # commented-out instance ignored
        self.assertTrue(r["trees"][0]["children"][0]["children"][0].get("recursive"))


class TestCompare(unittest.TestCase):
    def test_regressions(self):
        r = compare.compare_regressions(
            regress.analyze_folder(EXAMPLES / "regression_logs_prev"),
            regress.analyze_folder(EXAMPLES / "regression_logs"),
        )
        self.assertEqual(r["verdict"], "regressed")
        self.assertEqual(r["counts"]["new_failure"], 3)
        self.assertEqual(r["counts"]["fixed"], 1)
        self.assertEqual(r["counts"]["removed"], 1)
        change = {x["test"]: x["change"] for x in r["rows"]}
        self.assertEqual(change["uart_parity_test"], "fixed")
        self.assertEqual(change["uart_reset_test"], "new_failure")

    def test_timing(self):
        r = compare.compare_timing(
            timing_report.parse_file(EXAMPLES / "sta_report.rpt"),
            timing_report.parse_file(EXAMPLES / "sta_report_eco.rpt"),
        )
        self.assertEqual(r["verdict"], "mixed")
        setup = r["checks"][0]
        self.assertEqual(setup["check"], "setup")
        self.assertAlmostEqual(setup["delta_wns"], 0.41)
        change = {
            x["endpoint"]: x["change"] for x in r["rows"] if x["check"] == "setup"
        }
        self.assertEqual(change["u_cnt/count_reg[7]"], "new_violation")
        self.assertEqual(change["u_fifo/dout_reg[15]"], "degraded")
        self.assertEqual(change["u_alu/y_reg[30]"], "fixed")

    def test_same_run_is_unchanged(self):
        paths = timing_report.parse_file(EXAMPLES / "sta_report.rpt")
        self.assertEqual(compare.compare_timing(paths, paths)["verdict"], "unchanged")


class TestLiberty(unittest.TestCase):
    def setUp(self):
        self.lib = liberty.parse_file(EXAMPLES / "lib" / "vt_demo.lib")
        self.cells = {c["name"]: c for c in self.lib["cells"]}

    def test_library(self):
        self.assertEqual(self.lib["name"], "vt_demo_lib")
        self.assertEqual(len(self.lib["cells"]), 23)
        self.assertEqual(self.lib["units"]["time"], "1ns")
        self.assertEqual(self.lib["operating_conditions"]["voltage"], 1.8)
        self.assertEqual(self.lib["templates"]["delay_5x5"]["index_1"][0], 0.01)

    def test_cells(self):
        nand = self.cells["NAND2_X1"]
        self.assertEqual(nand["function"], "!(A&B)")
        self.assertEqual(nand["inputs"], ["A", "B"])
        table = nand["arcs"][0]["tables"]["cell_rise"]
        self.assertEqual(len(table["values"]), 5)
        self.assertEqual(len(table["values"][0]), 5)
        self.assertEqual(self.cells["DFF_X1"]["kind"], "flip-flop")
        # stronger drive -> faster
        self.assertLess(
            self.cells["INV_X4"]["typical_delay"], self.cells["INV_X1"]["typical_delay"]
        )
        self.assertEqual(liberty.drive_family("NAND2_X4"), ("NAND2", 4))

    def test_crlf(self):
        text = (EXAMPLES / "lib" / "vt_demo.lib").read_text().replace("\n", "\r\n")
        self.assertEqual(
            len(liberty.library_summary(liberty.parse_liberty(text))["cells"]), 23
        )


class TestUpgradeApi(unittest.TestCase):
    def post(self, url, body):
        r = client.post(url, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_endpoints(self):
        files = [{"name": n, "text": t} for n, t in project_files()]
        self.assertEqual(
            self.post("/api/rtl/hierarchy", {"files": files})["main_top"], "uart_top"
        )

        lib_text = (EXAMPLES / "lib" / "vt_demo.lib").read_text()
        lib = self.post("/api/pd/liberty", {"name": "vt_demo.lib", "text": lib_text})
        self.assertNotIn("arcs", lib["cells"][0])  # summary stays light
        cell = self.post(
            "/api/pd/liberty/cell",
            {"name": "vt_demo.lib", "text": lib_text, "cell": "DFF_X1"},
        )
        self.assertEqual(len(cell["arcs"]), 2)
        self.assertEqual(
            client.post(
                "/api/pd/liberty/cell",
                json={"name": "x", "text": lib_text, "cell": "NOPE"},
            ).status_code,
            404,
        )

        def logs(folder):
            return [
                {"name": p.name, "text": p.read_text()}
                for p in sorted((EXAMPLES / folder).glob("*.log"))
            ]

        r = self.post(
            "/api/compare/regress",
            {"old": logs("regression_logs_prev"), "new": logs("regression_logs")},
        )
        self.assertEqual(r["verdict"], "regressed")
        rpt = lambda n: {"name": n, "text": (EXAMPLES / n).read_text()}
        t = self.post(
            "/api/compare/timing",
            {"old": rpt("sta_report.rpt"), "new": rpt("sta_report_eco.rpt")},
        )
        self.assertEqual(t["counts"]["new_violation"], 1)


if __name__ == "__main__":
    unittest.main()
