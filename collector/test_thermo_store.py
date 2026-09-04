#!/usr/bin/env python3
"""Unittests für den CSV-Store (kein BLE)."""
import csv
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_store import (
    COLUMNS,
    append_sample,
    default_csv_path,
    iso_utc_now,
)


class TestIsoUtcNow(unittest.TestCase):
    def test_utc_z_format(self):
        ts = iso_utc_now()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)
        self.assertNotIn(".", ts)


class TestDefaultCsvPath(unittest.TestCase):
    def test_colon_mac_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = default_csv_path("f4:db:00:00:00:d9", tmp)
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self.assertEqual(
                os.path.basename(path),
                "thermo_f4db000000d9_{}.csv".format(day),
            )
            self.assertEqual(os.path.dirname(path), tmp)

    def test_dash_mac_is_mac12(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = default_csv_path("f4-db-00-00-00-d9", tmp)
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self.assertEqual(
                os.path.basename(path),
                "thermo_f4db000000d9_{}.csv".format(day),
            )


class TestAppendSample(unittest.TestCase):
    def test_header_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            append_sample(
                path, "2026-09-03T12:00:00Z", "f4:db:00:00:00:d9",
                22.0625, 64.94, "aabb",
            )
            append_sample(
                path, "2026-09-03T12:00:01Z", "f4:db:00:00:00:d9",
                22.125, 65.0, "ccdd",
            )
            with open(path, newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], list(COLUMNS))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[1][0], "2026-09-03T12:00:00Z")
            self.assertEqual(rows[2][0], "2026-09-03T12:00:01Z")

    def test_append_creates_missing_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "deeper", "out.csv")
            self.assertFalse(os.path.exists(os.path.dirname(path)))
            append_sample(
                path, "2026-09-03T12:00:00Z", "aa:bb",
                1.0, 2.0, "00",
            )
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
