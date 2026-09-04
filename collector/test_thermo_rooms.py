#!/usr/bin/env python3
"""Allowlist rooms.json (Phase 7)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PY_DIR)
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_rooms import (  # noqa: E402
    DEFAULT_ROOMS_PATH,
    allowlist_macs,
    encoding_checked_macs,
    load_rooms,
    mac_in_allowlist,
)

PROD_ROOMS = os.path.join(_ROOT, "dashboard", "rooms.json")


class TestProdRooms(unittest.TestCase):
    def test_five_entries_only_buero_checked(self):
        rooms = load_rooms(PROD_ROOMS)
        self.assertEqual(len(rooms), 5)
        macs = allowlist_macs(rooms)
        self.assertEqual(macs[0], "f4:db:00:00:00:d9")
        self.assertIn("f4:d0:00:00:02:1a", macs)
        self.assertIn("f4:db:00:00:02:37", macs)
        self.assertIn("f4:db:00:00:02:42", macs)
        self.assertIn("62:53:00:00:0f:1f", macs)
        checked = encoding_checked_macs(rooms)
        self.assertEqual(checked, ["f4:db:00:00:00:d9"])
        buero = rooms[0]
        self.assertTrue(buero["confirmed"])
        self.assertEqual(buero["system_id"], "D90000000000DBF4")
        for room in rooms[1:]:
            self.assertFalse(room["confirmed"])
            self.assertFalse(room["encoding_checked"])


class TestLoadRooms(unittest.TestCase):
    def test_encoding_checked_defaults_to_confirmed(self):
        payload = {
            "rooms": [
                {
                    "id": "x",
                    "name": "X",
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "confirmed": True,
                }
            ]
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            rooms = load_rooms(path)
            self.assertTrue(rooms[0]["encoding_checked"])
            self.assertTrue(mac_in_allowlist("AABBCCDDEEFF", allowlist_macs(rooms)))
        finally:
            os.remove(path)

    def test_default_path_exists(self):
        self.assertTrue(os.path.isfile(DEFAULT_ROOMS_PATH))


if __name__ == "__main__":
    unittest.main()
