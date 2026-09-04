#!/usr/bin/env python3
"""HTTP-API-Tests für dashboard/server.py (kein BLE)."""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import server  # noqa: E402
from thermo_dash import DashStore  # noqa: E402

TESTDATA = os.path.join(_HERE, "testdata")


class TestCli(unittest.TestCase):
    def test_help(self):
        with self.assertRaises(SystemExit) as ctx:
            server.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_once_and_interval_not_relevant(self):
        args = server.parse_args(["--port", "9999", "--no-extract"])
        self.assertEqual(args.port, 9999)
        self.assertTrue(args.no_extract)

    def test_bad_port(self):
        with self.assertRaises(SystemExit):
            server.parse_args(["--port", "0"])


class TestStaticSafety(unittest.TestCase):
    def test_index(self):
        path = server.safe_static_path("/")
        self.assertTrue(path.endswith("index.html"))
        self.assertTrue(os.path.isfile(path))

    def test_traversal_rejected(self):
        self.assertIsNone(server.safe_static_path("/../thermo_dash.py"))
        self.assertIsNone(server.safe_static_path("/static/../../AGENTS.md"))


class TestHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        store = DashStore(
            data_dir=TESTDATA,
            rooms_path=os.path.join(TESTDATA, "rooms.json"),
            extract_dir=os.path.join(TESTDATA, "extract"),
            include_extract=True,
        )
        store.refresh(force=True)
        handler = server.make_handler(store)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:{0}".format(cls.port)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _json(self, path, status=200):
        url = self.base + path
        try:
            with urlopen(url, timeout=5) as resp:
                self.assertEqual(resp.status, status)
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(exc.code, status)
            return body

    def test_index_html(self):
        with urlopen(self.base + "/", timeout=5) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("ThermoBeacon", html)
        self.assertIn("canvas", html)

    def test_overview(self):
        payload = self._json("/api/overview")
        self.assertEqual(payload["rooms"][0]["mac"], "f4:db:00:00:00:d9")
        self.assertGreaterEqual(payload["sample_count"], 2)

    def test_samples_live(self):
        payload = self._json(
            "/api/samples?mac=f4:db:00:00:00:d9&source=adv"
        )
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["samples"][0]["temp_c"], 25.125)

    def test_bad_source(self):
        payload = self._json("/api/samples?source=nope", status=400)
        self.assertIn("unbekannte source", payload["error"])

    def test_unknown_api(self):
        payload = self._json("/api/nope", status=404)
        self.assertEqual(payload["error"], "nicht gefunden")


if __name__ == "__main__":
    unittest.main()
