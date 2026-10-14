"""Tests for the HTTP API used by the React frontend.   Run:  python -m unittest -v"""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
client = TestClient(app)


def src(path):
    p = EXAMPLES / path
    return {"name": p.name, "text": p.read_text(encoding="utf-8")}


class TestApi(unittest.TestCase):
    def post(self, url, body):
        r = client.post(url, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_health_and_examples(self):
        self.assertTrue(client.get("/api/health").json()["ok"])
        self.assertIn(
            "regression_logs/uart_burst_test_7781.log",
            client.get("/api/examples?folder=regression_logs").json(),
        )
        self.assertEqual(
            client.get("/api/example?path=pd/demo.lef").json()["name"], "demo.lef"
        )
        self.assertEqual(
            client.get("/api/example?path=../README.md").status_code, 404
        )  # no path escape

    def test_rtl(self):
        mods = self.post("/api/rtl/parse", src("fifo.v"))["modules"]
        self.assertEqual(mods[0]["name"], "sync_fifo")
        self.assertEqual({p["name"]: p["width"] for p in mods[0]["ports"]}["count"], 6)
        lint = self.post(
            "/api/rtl/lint", {"files": [src("lint_demo.v"), src("counter.v")]}
        )
        self.assertEqual(lint["issues"][0]["severity"], "ERROR")  # most serious first
        rm = self.post("/api/rtl/regmap", src("uart_regmap.json"))
        self.assertEqual(rm["registers"][0]["reset"], "0x000001B0")
        self.assertIn("uart_regs.v", rm["outputs"])
        self.assertIn(
            "error", self.post("/api/rtl/regmap", {"name": "x.json", "text": "{bad"})
        )

    def test_verification(self):
        tb = self.post(
            "/api/verif/testbench", {**src("counter.v"), "cycles": 50, "period": 5}
        )
        self.assertEqual(tb["clocks"], ["clk"])
        self.assertTrue(tb["resets"][0]["active_low"])
        logs = [
            src(f"regression_logs/{p.name}")
            for p in sorted((EXAMPLES / "regression_logs").glob("*.log"))
        ]
        reg = self.post("/api/verif/regress", {"files": logs})
        self.assertEqual(sum(r["status"] == "PASS" for r in reg["results"]), 3)
        self.assertEqual(reg["signatures"][0]["count"], 3)
        vcd = self.post("/api/verif/vcd", {**src("sample.vcd"), "glitch": 2})
        self.assertEqual(vcd["end_time"], 400)
        self.assertIn("tb.clk", vcd["signals"])

    def test_pd(self):
        t = self.post("/api/pd/timing", src("sta_report.rpt"))
        self.assertEqual(len(t["paths"]), 10)
        self.assertAlmostEqual(t["summary"]["setup"]["wns"], -0.52)
        fp = self.post(
            "/api/pd/floorplan",
            {"def_file": src("pd/demo.def"), "lefs": [src("pd/demo.lef")]},
        )
        self.assertEqual(fp["instances"], 1404)
        self.assertTrue(0.5 < fp["utilization"] < 0.7)
        self.assertEqual(len(fp["unplaced"]), 3)
        self.assertTrue(fp["macro_bins"])

    def test_analog(self):
        nl = self.post("/api/analog/netlist", src("analog/buggy_bias.sp"))
        self.assertEqual(len(nl["issues"]), 3)
        sw = self.post(
            "/api/analog/sweep",
            {
                **src("analog/inverter_chain.sp"),
                "param": "vdd",
                "values": "1.2:1.8:0.2",
            },
        )
        self.assertEqual(len(sw["netlists"]), 4)
        m = self.post(
            "/api/analog/measure",
            {
                **src("analog/inverter_tran.csv"),
                "signals": ["v(out)"],
                "ref": "v(in)",
                "vdd": 1.8,
            },
        )
        self.assertTrue(30e-12 < m["results"]["v(out)"]["tpd"] < 60e-12)
        self.assertTrue(m["plot"])


class TestApiRobustness(unittest.TestCase):
    """Behaviour of the refactored API around errors and versioning."""

    def test_health_reports_version_and_endpoints(self):
        h = client.get("/api/health").json()
        from api.routers.general import API_VERSION

        self.assertEqual(h["api_version"], API_VERSION)
        for ep in (
            "/api/rtl/hierarchy",
            "/api/verif/axi",
            "/api/pd/liberty",
            "/api/compare/regress",
        ):
            self.assertIn(ep, h["endpoints"])

    def test_unknown_endpoint_is_json_404_for_any_method(self):
        for method in ("get", "post", "put", "delete"):
            r = getattr(client, method)("/api/does/not/exist")
            self.assertEqual(r.status_code, 404, method)
            self.assertIn("Unknown API endpoint", r.json()["detail"])

    def test_invalid_request_is_readable_422(self):
        r = client.post("/api/rtl/lint", json={"files": []})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json()["detail"].startswith("Invalid request - files:"))
        r = client.post("/api/rtl/parse", json={"name": "a.v"})
        self.assertIn("text: Field required", r.json()["detail"])

    def test_internal_error_is_json_500(self):
        from unittest import mock

        safe = TestClient(app, raise_server_exceptions=False)
        with mock.patch(
            "vlsi_toolkit.verilog_parser.parse_text", side_effect=RuntimeError("boom")
        ):
            r = safe.post(
                "/api/rtl/parse", json={"name": "a.v", "text": "module a; endmodule"}
            )
        self.assertEqual(r.status_code, 500)
        self.assertIn("RuntimeError: boom", r.json()["detail"])

    def test_example_paths_cannot_escape(self):
        self.assertEqual(client.get("/api/examples?folder=../..").status_code, 404)
        self.assertEqual(
            client.get("/api/example?path=../api/main.py").status_code, 404
        )


if __name__ == "__main__":
    unittest.main()
