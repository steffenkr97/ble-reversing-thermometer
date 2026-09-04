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
    MAX_ROOMS,
    RoomsError,
    add_room,
    allowlist_macs,
    delete_room,
    encoding_checked_macs,
    load_rooms,
    mac_in_allowlist,
    save_rooms,
    update_room,
    validate_rooms,
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


class TestSaveRooms(unittest.TestCase):
    def test_add_update_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rooms.json")
            rooms = add_room([], "Büro", "F4:DB:00:00:00:D9")
            self.assertTrue(rooms[0]["confirmed"])
            self.assertEqual(rooms[0]["mac"], "f4:db:00:00:00:d9")
            save_rooms(path, rooms)
            loaded = load_rooms(path)
            self.assertEqual(loaded[0]["name"], "Büro")
            renamed = update_room(loaded, loaded[0]["id"], name="Keller")
            save_rooms(path, renamed)
            self.assertEqual(load_rooms(path)[0]["name"], "Keller")
            empty = delete_room(renamed, renamed[0]["id"])
            save_rooms(path, empty)
            self.assertEqual(load_rooms(path), [])

    def test_reject_bad_mac_and_duplicate(self):
        with self.assertRaises(RoomsError):
            validate_rooms([{"name": "X", "mac": "zz"}])
        rooms = add_room([], "A", "aa:bb:cc:dd:ee:ff")
        with self.assertRaises(RoomsError):
            add_room(rooms, "B", "aa:bb:cc:dd:ee:ff")
        with self.assertRaises(RoomsError):
            add_room([], "  ", "aa:bb:cc:dd:ee:ff")

    def test_max_five(self):
        rooms = []
        for i in range(MAX_ROOMS):
            mac = "aa:bb:cc:dd:ee:{:02x}".format(i)
            rooms = add_room(rooms, "R{}".format(i), mac)
        with self.assertRaises(RoomsError):
            add_room(rooms, "Extra", "aa:bb:cc:dd:ee:ff")


if __name__ == "__main__":
    unittest.main()
