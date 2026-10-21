"""Examples Library: catalog, single downloads and the zip.   Run:  python -m unittest -v"""

import io
import unittest
import zipfile

from vlsi_toolkit import examples_catalog


class TestCatalog(unittest.TestCase):
    def test_every_example_is_described_and_openable(self):
        cat = examples_catalog.catalog()
        self.assertGreaterEqual(cat["count"], 40)
        for f in cat["files"]:
            self.assertTrue(f["description"], f["path"])
            self.assertTrue(f["tools"], f["path"])                   # at least one tool opens it
            self.assertTrue(f["tools"][0].startswith("/"), f["path"])
        sdc = next(f for f in cat["files"] if f["path"] == "signoff/uart_top.sdc")
        self.assertEqual((sdc["area"], sdc["tools"][0]), ("Physical design", "/sdc"))
        self.assertEqual({c["folder"] for c in cat["collections"]}, {"regression_logs", "regression_logs_prev"})

    def test_resolve_refuses_paths_outside_examples(self):
        self.assertTrue(examples_catalog.resolve("pd/demo.def").is_file())
        for bad in ("../api/main.py", "nope.v", "..\vlsi.py"):
            with self.assertRaises(FileNotFoundError):
                examples_catalog.resolve(bad)

    def test_zip_contains_every_file(self):
        z = zipfile.ZipFile(io.BytesIO(examples_catalog.zip_bytes()))
        names = set(z.namelist())
        self.assertEqual(len(names), examples_catalog.catalog()["count"])
        self.assertIn("vlsi_toolkit_examples/signoff/uart_top.sdc", names)


class TestExamplesApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from api.main import app
        self.client = TestClient(app)

    def test_endpoints(self):
        self.assertEqual(self.client.get("/api/examples/catalog").json()["count"], examples_catalog.catalog()["count"])
        r = self.client.get("/api/examples/download", params={"path": "cdc_demo.v"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn(b"module", r.content)
        self.assertEqual(self.client.get("/api/examples/download", params={"path": "../vlsi.py"}).status_code, 404)
        z = self.client.get("/api/examples/zip")
        self.assertEqual((z.status_code, z.headers["content-type"]), (200, "application/zip"))


if __name__ == "__main__":
    unittest.main()
