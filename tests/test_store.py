"""Storage (SQLite and MongoDB), activity log and feedback.   Run:  python -m unittest -v

The MongoDB tests use `mongomock` when it is installed (skipped otherwise). To test against a
real cluster, set MONGODB_URI_TEST (a throw-away database "vlsi_toolkit_test" is used and dropped).
"""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from vlsi_toolkit import activity, store

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


class StoreContract:
    """Behaviour every store must have. Subclasses provide self.store."""

    def test_snapshots(self):
        s = self.store
        a = s.add_snapshot({"ts": 100.0, "workspace": "/p", "label": "a", "metrics": {"x": 1}, "summary": {}, "demo": False})
        s.add_snapshot({"ts": 200.0, "workspace": "/p", "label": "b", "metrics": {"x": 2}, "summary": {}, "demo": True})
        s.add_snapshot({"ts": 150.0, "workspace": "/q", "label": "c", "metrics": {}, "summary": {}, "demo": False})
        self.assertIsInstance(a, str)
        self.assertEqual([x["label"] for x in s.list_snapshots("/p")], ["b", "a"])     # newest first
        self.assertEqual(len(s.list_snapshots()), 3)
        self.assertEqual([w["workspace"] for w in s.workspaces()], ["/p", "/q"])
        self.assertEqual(s.workspaces()[0]["snapshots"], 2)
        self.assertEqual(s.clear_snapshots("/p", demo_only=True), 1)
        self.assertEqual(s.delete_snapshot(a), 1)
        self.assertEqual(s.delete_snapshot(a), 0)
        self.assertEqual(s.delete_snapshot("not-an-id"), 0)
        self.assertEqual(len(s.list_snapshots()), 1)

    def test_events_and_summary(self):
        s = self.store
        now = time.time()
        s.add_event(store.new_event("RTL Lint", "/api/rtl/lint", True, 200, 12, [{"name": "a.v", "bytes": 10}], {"issues": 3}, ts=now - 3600))
        s.add_event(store.new_event("RTL Lint", "/api/rtl/lint", False, 400, 4, [], {}, "bad file", ts=now - 60))
        s.add_event(store.new_event("SDC Checker", "/api/pd/sdc", True, 200, 8, ts=now - 40 * 86400))   # outside 30 days
        self.assertEqual(s.count_events(), 3)
        self.assertEqual([e["ok"] for e in s.recent_events(10)], [False, True, True])
        self.assertEqual(len(s.recent_events(10, failures_only=True)), 1)
        r = activity.summary(30, s)
        self.assertEqual((r["totals"]["runs"], r["totals"]["failures"], r["totals"]["all_time_runs"]), (2, 1, 3))
        self.assertEqual(r["by_tool"], [{"tool": "RTL Lint", "runs": 2, "failures": 1, "avg_ms": 8.0}])
        self.assertEqual(len(r["by_day"]), 30)
        self.assertEqual(sum(d["runs"] for d in r["by_day"]), 2)

    def test_feedback(self):
        s = self.store
        self.assertEqual(s.feedback_stats(), {"count": 0, "avg_rating": None})
        s.add_feedback({"ts": 1.0, "message": "nice", "rating": 5, "name": "", "email": "", "page": "/"})
        s.add_feedback({"ts": 2.0, "message": "more rules", "rating": 4, "name": "A", "email": "", "page": "/sdc"})
        s.add_feedback({"ts": 3.0, "message": "no rating", "rating": None, "name": "", "email": "", "page": ""})
        self.assertEqual(s.feedback_stats(), {"count": 3, "avg_rating": 4.5})
        self.assertEqual([f["message"] for f in s.list_feedback()], ["no rating", "more rules", "nice"])
        self.assertTrue(all(isinstance(f["id"], str) for f in s.list_feedback()))


class TestSqliteStore(StoreContract, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = store.SqliteStore(Path(self._tmp.name) / "t.db")

    def tearDown(self):
        self._tmp.cleanup()


try:
    import mongomock
except ImportError:
    mongomock = None


@unittest.skipIf(mongomock is None, "mongomock not installed")
class TestMongoStoreMock(StoreContract, unittest.TestCase):
    def setUp(self):
        self.store = store.MongoStore("mongodb://mock", "vt_test", client=mongomock.MongoClient())


@unittest.skipUnless(os.environ.get("MONGODB_URI_TEST"), "MONGODB_URI_TEST not set")
class TestMongoStoreReal(StoreContract, unittest.TestCase):
    def setUp(self):
        self.store = store.MongoStore(os.environ["MONGODB_URI_TEST"], "vlsi_toolkit_test")
        self.store.client.drop_database("vlsi_toolkit_test")

    def tearDown(self):
        self.store.client.drop_database("vlsi_toolkit_test")


class TestSelection(unittest.TestCase):
    def test_placeholder_and_forced_sqlite_fall_back(self):
        with tempfile.TemporaryDirectory() as d:
            for env in ({"MONGODB_URI": "mongodb+srv://u:<password>@c.mongodb.net/", "VT_STORE": ""},
                        {"MONGODB_URI": "mongodb+srv://u:p@c.mongodb.net/", "VT_STORE": "sqlite"}):
                with mock.patch.dict(os.environ, env | {"VT_DATA_DIR": d}):
                    self.assertEqual(store.get_store().kind, "sqlite")

    def test_dotenv_does_not_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('# comment\nVT_A="from file"\nVT_B=from file\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"VT_B": "already set"}):
                store.load_dotenv(p)
                self.assertEqual((os.environ["VT_A"], os.environ["VT_B"]), ("from file", "already set"))
            os.environ.pop("VT_A", None)


class TestActivityApi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"VT_DATA_DIR": self._tmp.name, "VT_STORE": "sqlite"})
        self._env.start()
        from fastapi.testclient import TestClient
        from api import activity_log
        from api.main import app
        activity_log._recent.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def wait_for(self, n):
        for _ in range(50):     # events are written in a background thread
            if store.get_store().count_events() >= n:
                return
            time.sleep(0.05)
        self.fail(f"expected {n} events")

    def test_tool_runs_are_recorded_without_file_contents(self):
        text = (EXAMPLES / "cdc_demo.v").read_text()
        self.client.post("/api/rtl/lint", json={"files": [{"name": "cdc_demo.v", "text": text}]})
        self.client.post("/api/rtl/lint", json={"files": [{"name": "cdc_demo.v", "text": text + " "}]})  # repeat
        self.client.post("/api/pd/power", json={"name": "x.rpt", "text": "not a report"})
        self.wait_for(2)
        time.sleep(0.2)
        events = store.get_store().recent_events(10)
        self.assertEqual(len(events), 2)
        power, lint = events
        self.assertEqual((lint["tool"], lint["ok"], lint["files"]), ("RTL Lint", True, [{"name": "cdc_demo.v", "bytes": len(text)}]))
        self.assertEqual(lint["result"]["issues"], 3)
        self.assertFalse(power["ok"])
        self.assertIn("Not a recognised power report", power["error"])
        self.assertNotIn("module", str(events))     # no RTL text stored

    def test_feedback_validation_and_dashboard(self):
        ok = self.client.post("/api/feedback", json={"message": "Useful SDC checker", "rating": 5, "page": "/sdc"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post("/api/feedback", json={"message": "hi there", "email": "bad"}).status_code, 422)
        self.assertEqual(self.client.post("/api/feedback", json={"message": "x"}).status_code, 422)
        a = self.client.get("/api/activity?days=7").json()
        self.assertEqual(a["feedback"], {"count": 1, "avg_rating": 5.0})
        self.assertTrue(a["details"])
        self.assertIn("recent", a)
        self.assertEqual(self.client.get("/api/feedback").json()["feedback"][0]["message"], "Useful SDC checker")

    def test_hosted_site_shows_totals_only(self):
        with mock.patch.dict(os.environ, {"RENDER": "true"}):
            a = self.client.get("/api/activity").json()
            self.assertFalse(a["details"])
            self.assertNotIn("recent", a)
            self.assertEqual(self.client.get("/api/feedback").status_code, 403)
            self.assertEqual(self.client.post("/api/feedback", json={"message": "from the live site"}).status_code, 200)

    def test_health_reports_database(self):
        db = self.client.get("/api/health").json()["database"]
        self.assertEqual((db["kind"], db["connected"]), ("sqlite", True))


if __name__ == "__main__":
    unittest.main()
