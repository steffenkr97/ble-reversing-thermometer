#!/usr/bin/env python3
"""Unittests für Dashboard-Datenlage (kein BLE)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from thermo_dash import (
    SOURCE_ADV,
    SOURCE_ADV_CAPTURE,
    SOURCE_HISTORY,
    SOURCE_HISTORY_CAPTURE,
    DashStore,
    downsample,
    filter_samples,
    load_rooms,
    normalize_mac,
    read_extract_adv,
    read_extract_history,
    read_history_csv,
    read_live_csv,
    summarize,
)

TESTDATA = os.path.join(_HERE, "testdata")
ROOMS_PATH = os.path.join(TESTDATA, "rooms.json")
EXTRACT_DIR = os.path.join(TESTDATA, "extract")
LIVE_CSV = os.path.join(TESTDATA, "thermo_f4db000000d9_2026-09-03.csv")
HISTORY_CSV = os.path.join(TESTDATA, "history_f4db000000d9.csv")


class TestMac(unittest.TestCase):
    def test_normalize_colon(self):
        self.assertEqual(normalize_mac("F4:DB:00:00:00:D9"), "f4:db:00:00:00:d9")

    def test_normalize_bare(self):
        self.assertEqual(normalize_mac("f4db000000d9"), "f4:db:00:00:00:d9")


class TestRooms(unittest.TestCase):
    def test_buero_allowlist(self):
        rooms = load_rooms(ROOMS_PATH)
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]["mac"], "f4:db:00:00:00:d9")
        self.assertEqual(rooms[0]["name"], "Büro")
        self.assertTrue(rooms[0]["encoding_checked"])

    def test_prod_rooms_five_candidates(self):
        prod = os.path.join(_HERE, "rooms.json")
        rooms = load_rooms(prod)
        self.assertEqual(len(rooms), 5)
        self.assertTrue(rooms[0]["confirmed"])
        self.assertFalse(rooms[1]["confirmed"])


class TestLiveCsv(unittest.TestCase):
    def test_drops_foreign_mac(self):
        rooms = load_rooms(ROOMS_PATH)
        rows = read_live_csv(LIVE_CSV, rooms)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["temp_c"], 25.125)
        self.assertEqual(rows[0]["source"], SOURCE_ADV)
        self.assertEqual(rows[0]["room"], "Büro")
        macs = {row["mac"] for row in rows}
        self.assertEqual(macs, {"f4:db:00:00:00:d9"})

    def test_wrong_header_is_empty(self):
        rooms = load_rooms(ROOMS_PATH)
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as handle:
            handle.write("foo,bar\n1,2\n")
            path = handle.name
        try:
            self.assertEqual(read_live_csv(path, rooms), [])
        finally:
            os.remove(path)


class TestHistoryCsv(unittest.TestCase):
    def test_index_and_source(self):
        rooms = load_rooms(ROOMS_PATH)
        rows = read_history_csv(HISTORY_CSV, rooms)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], SOURCE_HISTORY)
        self.assertEqual(rows[0]["index"], 0)
        self.assertEqual(rows[0]["temp_c"], 24.0625)
        self.assertEqual(rows[0]["timestamp"], "2025-11-15T12:00:00Z")
        self.assertEqual(rows[1]["timestamp"], "2025-11-15T12:10:00Z")


class TestExtract(unittest.TestCase):
    def test_adv_gold_vector(self):
        rooms = load_rooms(ROOMS_PATH)
        rows = read_extract_adv(os.path.join(EXTRACT_DIR, "adv.csv"), rooms)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], SOURCE_ADV_CAPTURE)
        self.assertEqual(rows[0]["temp_c"], 22.0625)
        self.assertEqual(rows[0]["humidity_rh"], 64.9375)
        self.assertEqual(rows[0]["mac"], "f4:db:00:00:00:d9")
        self.assertTrue(rows[0]["timestamp"].startswith("2025-"))

    def test_history_gold_and_dedupe(self):
        rooms = load_rooms(ROOMS_PATH)
        rows = read_extract_history(
            os.path.join(EXTRACT_DIR, "att_fff5_fff3.csv"), rooms
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["source"], SOURCE_HISTORY_CAPTURE)
        self.assertEqual(rows[0]["index"], 0)
        self.assertEqual(rows[0]["temp_c"], 24.0625)
        self.assertEqual(rows[1]["index"], 1)
        self.assertEqual(rows[2]["index"], 2)
        self.assertEqual(rows[2]["temp_c"], 23.5625)


class TestDownsampleAndSummary(unittest.TestCase):
    def test_downsample_keeps_ends(self):
        samples = [{"i": n} for n in range(10)]
        out = downsample(samples, 3)
        self.assertEqual(out[0]["i"], 0)
        self.assertEqual(out[-1]["i"], 9)
        self.assertEqual(len(out), 3)

    def test_summarize_empty(self):
        self.assertEqual(summarize([])["count"], 0)

    def test_filter_source(self):
        rows = [
            {"mac": "f4:db:00:00:00:d9", "source": SOURCE_ADV},
            {"mac": "f4:db:00:00:00:d9", "source": SOURCE_HISTORY},
        ]
        self.assertEqual(len(filter_samples(rows, source=SOURCE_ADV)), 1)


class TestStore(unittest.TestCase):
    def test_overview_and_query(self):
        store = DashStore(
            data_dir=TESTDATA,
            rooms_path=ROOMS_PATH,
            extract_dir=EXTRACT_DIR,
            include_extract=True,
        )
        overview = store.overview()
        self.assertEqual(overview["live_csv_count"], 1)
        self.assertEqual(overview["history_csv_count"], 1)
        self.assertIn(SOURCE_ADV, overview["sources"])
        self.assertIn(SOURCE_HISTORY, overview["sources"])
        self.assertIn(SOURCE_HISTORY_CAPTURE, overview["sources"])
        buero = overview["rooms"][0]
        self.assertEqual(buero["name"], "Büro")
        self.assertTrue(buero["encoding_checked"])
        self.assertEqual(buero["counts"][SOURCE_ADV], 2)
        self.assertEqual(buero["latest"]["temp_c"], 25.1875)

        live = store.query(mac="f4:db:00:00:00:d9", source=SOURCE_ADV)
        self.assertEqual(live["count"], 2)
        hist = store.query(mac="F4:DB:00:00:00:D9", source=SOURCE_HISTORY_CAPTURE)
        self.assertEqual(hist["count"], 3)
        dumped = store.query(mac="f4:db:00:00:00:d9", source=SOURCE_HISTORY)
        self.assertEqual(dumped["count"], 2)
        self.assertEqual(dumped["samples"][0]["timestamp"], "2025-11-15T12:00:00Z")

    def test_no_extract(self):
        store = DashStore(
            data_dir=TESTDATA,
            rooms_path=ROOMS_PATH,
            extract_dir=EXTRACT_DIR,
            include_extract=False,
        )
        store.refresh(force=True)
        sources = store.sources_present()
        self.assertNotIn(SOURCE_ADV_CAPTURE, sources)
        self.assertNotIn(SOURCE_HISTORY_CAPTURE, sources)


if __name__ == "__main__":
    unittest.main()
