#!/usr/bin/env python3
"""Vergleich Live vs. History und Intervall-Evidence (ohne BLE)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_parse import AdvLive  # noqa: E402
import mvp_buero  # noqa: E402

LIVE = AdvLive(
    temp_c=25.125,
    humidity_rh=62.0625,
    battery_mv=2617,
    counter=2025968,
    mac="f4:db:00:00:00:d9",
    raw_hex="00",
)


class TestCompare(unittest.TestCase):
    def test_close_temps_ok(self):
        rows = [
            {"index": "0", "temp_c": "20.0", "humidity_rh": "50"},
            {"index": "10", "temp_c": "25.0", "humidity_rh": "61.0"},
        ]
        cmp = mvp_buero.compare_live_to_newest_history(LIVE, rows)
        self.assertTrue(cmp["ok"])
        self.assertEqual(cmp["history_index"], 10)
        self.assertLess(cmp["temp_delta_c"], 0.2)

    def test_empty_history(self):
        cmp = mvp_buero.compare_live_to_newest_history(LIVE, [])
        self.assertFalse(cmp["ok"])

    def test_far_temp_not_ok(self):
        rows = [{"index": 3, "temp_c": 10.0, "humidity_rh": 40.0}]
        cmp = mvp_buero.compare_live_to_newest_history(LIVE, rows)
        self.assertFalse(cmp["ok"])


class TestIntervalEvidence(unittest.TestCase):
    def test_two_counts_yield_10min(self):
        records = [
            {
                "mac": "f4:db:00:00:00:d9",
                "recorded_at": "2026-09-04T10:00:00Z",
                "sample_count": 100,
            },
            {
                "mac": "f4:db:00:00:00:d9",
                "recorded_at": "2026-09-04T11:40:00Z",
                "sample_count": 110,
            },
        ]
        got = mvp_buero.infer_interval_sec(records)
        self.assertIsNotNone(got)
        self.assertTrue(got["ok"])
        self.assertAlmostEqual(got["interval_sec"], 600.0)
        self.assertTrue(got["close_to_10min"])

    def test_one_point_is_none(self):
        records = [
            {
                "mac": "f4:db:00:00:00:d9",
                "recorded_at": "2026-09-04T10:00:00Z",
                "sample_count": 100,
            }
        ]
        self.assertIsNone(mvp_buero.infer_interval_sec(records))

    def test_append_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "e.jsonl")
            mvp_buero.append_evidence(path, {"mac": "f4:db:00:00:00:d9", "n": 1})
            mvp_buero.append_evidence(path, {"mac": "f4:db:00:00:00:d9", "n": 2})
            rows = mvp_buero.load_evidence(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["n"], 2)

    def test_help(self):
        import io
        from contextlib import redirect_stdout

        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                mvp_buero.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
