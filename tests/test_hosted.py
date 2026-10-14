"""Hosted mode (online deployment): visitors must not be able to open folders on the server.   Run:  python -m unittest -v"""

import os
import tempfile
import unittest
from unittest import mock


class TestHostedMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        env = {"VERCEL": "1", "VT_DATA_DIR": self._tmp.name}
        self._env = mock.patch.dict(os.environ, env)
        self._env.start()
        from fastapi.testclient import TestClient
        from api.main import app

        self.client = TestClient(app)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def test_folders_cannot_be_opened(self):
        r = self.client.post(
            "/api/workspace/open", json={"path": os.path.dirname(__file__)}
        )
        self.assertEqual(r.status_code, 403)

    def test_workspace_shows_examples_without_server_path(self):
        w = self.client.get("/api/workspace").json()
        self.assertTrue(w["hosted"])
        self.assertEqual(w["root"], "examples")
        self.assertGreater(len(w["files"]), 10)
        self.assertTrue(self.client.get("/api/health").json()["hosted"])

    def test_files_outside_examples_are_refused(self):
        self.assertEqual(
            self.client.get(
                "/api/workspace/file", params={"path": "../api/main.py"}
            ).status_code,
            404,
        )

    def test_web_pages_are_served(self):
        from api.main import WEB_DIST

        if not WEB_DIST.is_dir():
            self.skipTest("web app not built")
        r = self.client.get("/sdc", headers={"Accept": "text/html"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("<!doctype html>", r.text.lower())


if __name__ == "__main__":
    unittest.main()
