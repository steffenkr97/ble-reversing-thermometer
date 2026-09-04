#!/usr/bin/env python3
"""Unittests History-Dump (kein BLE). Goldvektoren aus hci-logs/05 und 07."""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PY_DIR)
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_history import (
    BLACKLIST_WRITE_OPCODES,
    HISTORY_COLUMNS,
    INTERVAL_SEC_HYPOTHESIS,
    apply_incremental_history,
    apply_inferred_timestamps,
    assert_allowed_fff5_write,
    default_history_csv_path,
    interval_from_count_and_counter,
    load_extract_history,
    max_history_index,
    merge_history_rows,
    page_plan,
    page_plan_since,
    read_history_csv,
    samples_from_page,
    samples_from_pages,
    write_history_csv,
)
from thermo_parse import (
    TARGET_MAC,
    build_history_07_write,
    parse_fff3,
)

GOLD_07_COUNT3 = bytes.fromhex("07000000000381017B017901B403BC03CB030000")
GOLD_07_COUNT1 = bytes.fromhex("0730060000016F01E8036E010E040F04F2030000")
EXTRACT_DIR = os.path.join(_ROOT, "hci-logs", "extract")
DASH_EXTRACT = os.path.join(_ROOT, "dashboard", "testdata", "extract")


class TestPagePlan(unittest.TestCase):
    def test_1584_all_count3(self):
        plan = page_plan(1584)
        self.assertEqual(len(plan), 528)
        self.assertEqual(plan[0], (0, 3))
        self.assertEqual(plan[1], (3, 3))
        self.assertEqual(plan[-1], (1581, 3))
        self.assertTrue(all(count == 3 for _idx, count in plan))

    def test_1586_two_remainder_pages(self):
        """15_14_35: 528×03 + 2×01, nicht count=02."""
        plan = page_plan(1586)
        self.assertEqual(len(plan), 530)
        self.assertEqual(plan[-3], (1581, 3))
        self.assertEqual(plan[-2], (1584, 1))
        self.assertEqual(plan[-1], (1585, 1))
        self.assertEqual(plan[-2], (1584, 1))
        self.assertTrue(all(c in (1, 3) for _i, c in plan))
        self.assertEqual(sum(c for _i, c in plan), 1586)

    def test_820_matches_old_capture(self):
        plan = page_plan(820)
        self.assertEqual(len(plan), 274)
        self.assertEqual(plan[-1], (819, 1))
        self.assertEqual(sum(c for _i, c in plan), 820)

    def test_zero_and_one(self):
        self.assertEqual(page_plan(0), [])
        self.assertEqual(page_plan(1), [(0, 1)])
        self.assertEqual(page_plan(2), [(0, 1), (1, 1)])
        self.assertEqual(page_plan(3), [(0, 3)])

    def test_writes_match_capture_payloads(self):
        self.assertEqual(build_history_07_write(0, 3), bytes.fromhex("070000000003"))
        self.assertEqual(build_history_07_write(1584, 1), bytes.fromhex("073006000001"))
        for index, count in page_plan(1586)[:2] + page_plan(1586)[-2:]:
            payload = build_history_07_write(index, count)
            assert_allowed_fff5_write(payload)

    def test_page_plan_since_tail_and_overlap(self):
        self.assertEqual(page_plan_since(1586, 1585), [])
        self.assertEqual(page_plan_since(1586, 1583), [(1584, 1), (1585, 1)])
        self.assertEqual(page_plan_since(12, 7), [(6, 3), (9, 3)])
        self.assertEqual(page_plan_since(3, -1), [(0, 3)])
        self.assertEqual(sum(c for _i, c in page_plan_since(1590, 1585)), 6)


class TestAllowedWrites(unittest.TestCase):
    def test_app_opcodes_ok(self):
        assert_allowed_fff5_write(bytes([0x1A]))
        assert_allowed_fff5_write(bytes([0x01]))
        assert_allowed_fff5_write(build_history_07_write(0, 3))
        assert_allowed_fff5_write(build_history_07_write(1584, 1))

    def test_blacklist_rejected(self):
        for opcode in BLACKLIST_WRITE_OPCODES:
            with self.assertRaises(ValueError):
                assert_allowed_fff5_write(bytes([opcode]))
        with self.assertRaises(ValueError):
            assert_allowed_fff5_write(bytes.fromhex("0400000000"))
        with self.assertRaises(ValueError):
            assert_allowed_fff5_write(bytes.fromhex("18E7035E"))
        with self.assertRaises(ValueError):
            assert_allowed_fff5_write(build_history_07_write(0, 2))
        with self.assertRaises(ValueError):
            assert_allowed_fff5_write(bytes([0x07]))


class TestSamplesFromPage(unittest.TestCase):
    def test_count3_gold(self):
        parsed = parse_fff3(GOLD_07_COUNT3)
        rows = samples_from_page(parsed, TARGET_MAC)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["index"], 0)
        self.assertEqual(rows[0]["record"], 0)
        self.assertEqual(rows[0]["temp_c"], 24.0625)
        self.assertEqual(rows[0]["humidity_rh"], 59.25)
        self.assertEqual(rows[1]["index"], 1)
        self.assertEqual(rows[2]["index"], 2)
        self.assertEqual(rows[2]["temp_c"], 23.5625)
        self.assertEqual(rows[0]["raw_hex"], GOLD_07_COUNT3.hex())

    def test_count1_hum_offset8(self):
        parsed = parse_fff3(GOLD_07_COUNT1)
        rows = samples_from_page(parsed, TARGET_MAC)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["index"], 1584)
        self.assertEqual(rows[0]["temp_c"], 22.9375)
        self.assertEqual(rows[0]["humidity_rh"], 62.5)


class TestTimestamps(unittest.TestCase):
    def test_interval_hypothesis_from_adv_counter(self):
        interval = interval_from_count_and_counter(1583, 949579)
        self.assertIsNotNone(interval)
        self.assertAlmostEqual(interval, 599.86, places=2)
        self.assertAlmostEqual(interval, INTERVAL_SEC_HYPOTHESIS, delta=1.0)

    def test_inferred_uses_device_count_not_dump_len(self):
        parsed = parse_fff3(GOLD_07_COUNT3)
        rows = samples_from_pages([parsed], TARGET_MAC)
        stamped = apply_inferred_timestamps(
            rows,
            newest_utc="2025-11-26T15:00:00Z",
            interval_sec=600,
            newest_index=1582,
        )
        self.assertEqual(stamped[0]["timestamp_inferred"], "2025-11-15T15:20:00Z")
        self.assertEqual(stamped[2]["timestamp_inferred"], "2025-11-15T15:40:00Z")
        newest = apply_inferred_timestamps(
            [{"mac": TARGET_MAC, "index": 1582, "record": 0, "temp_c": 1, "humidity_rh": 2, "raw_hex": ""}],
            newest_utc="2025-11-26T15:00:00Z",
            interval_sec=600,
            newest_index=1582,
        )
        self.assertEqual(newest[0]["timestamp_inferred"], "2025-11-26T15:00:00Z")


class TestHistoryCsv(unittest.TestCase):
    def test_path_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = default_history_csv_path(TARGET_MAC, tmp)
            self.assertEqual(os.path.basename(path), "history_f4db000000d9.csv")
            parsed = parse_fff3(GOLD_07_COUNT3)
            rows = apply_inferred_timestamps(
                samples_from_page(parsed, TARGET_MAC),
                newest_utc="2025-11-26T15:00:00Z",
                interval_sec=600,
                newest_index=2,
            )
            write_history_csv(path, rows)
            with open(path, newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(list(reader.fieldnames), list(HISTORY_COLUMNS))
                got = list(reader)
            self.assertEqual(len(got), 3)
            self.assertEqual(got[0]["mac"], TARGET_MAC)
            self.assertEqual(got[0]["index"], "0")
            self.assertEqual(float(got[0]["temp_c"]), 24.0625)
            self.assertTrue(got[0]["timestamp_inferred"].endswith("Z"))

    def test_read_merge_and_incremental_stamp(self):
        existing = [
            {"mac": TARGET_MAC, "index": 0, "record": 0, "temp_c": 1.0, "humidity_rh": 10.0, "raw_hex": "aa", "timestamp_inferred": ""},
            {"mac": TARGET_MAC, "index": 1, "record": 1, "temp_c": 2.0, "humidity_rh": 20.0, "raw_hex": "bb", "timestamp_inferred": ""},
        ]
        incoming = [
            {"mac": TARGET_MAC, "index": 1, "record": 1, "temp_c": 2.5, "humidity_rh": 21.0, "raw_hex": "cc", "timestamp_inferred": ""},
            {"mac": TARGET_MAC, "index": 2, "record": 2, "temp_c": 3.0, "humidity_rh": 30.0, "raw_hex": "dd", "timestamp_inferred": ""},
        ]
        merged = merge_history_rows(existing, incoming)
        self.assertEqual([r["index"] for r in merged], [0, 1, 2])
        self.assertEqual(merged[1]["temp_c"], 2.5)
        self.assertEqual(max_history_index(merged), 2)
        stamped = apply_incremental_history(
            existing,
            incoming,
            sample_count=3,
            newest_utc="2026-09-04T12:00:00Z",
            interval_sec=600,
        )
        self.assertEqual(stamped[2]["timestamp_inferred"], "2026-09-04T12:00:00Z")
        self.assertEqual(stamped[0]["timestamp_inferred"], "2026-09-04T11:40:00Z")

    def test_incremental_reset_replaces(self):
        existing = [
            {"mac": TARGET_MAC, "index": 5, "record": 0, "temp_c": 1.0, "humidity_rh": 10.0, "raw_hex": "", "timestamp_inferred": ""},
        ]
        incoming = [
            {"mac": TARGET_MAC, "index": 0, "record": 0, "temp_c": 9.0, "humidity_rh": 11.0, "raw_hex": "", "timestamp_inferred": ""},
        ]
        rows = apply_incremental_history(
            existing,
            incoming,
            sample_count=1,
            newest_utc="2026-09-04T12:00:00Z",
            interval_sec=600,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["index"], 0)
        self.assertEqual(rows[0]["temp_c"], 9.0)

    def test_read_history_csv_missing(self):
        self.assertEqual(read_history_csv("/tmp/thermo-missing-history-nope.csv"), [])


class TestLoadExtract(unittest.TestCase):
    def test_dashboard_fixture_gold_page(self):
        rows, meta = load_extract_history(DASH_EXTRACT, mac=TARGET_MAC)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["temp_c"], 24.0625)
        self.assertEqual(rows[2]["temp_c"], 23.5625)
        self.assertTrue(meta["file"])

    def test_real_extract_picks_complete_dump(self):
        if not os.path.isfile(os.path.join(EXTRACT_DIR, "att_fff5_fff3.csv")):
            self.skipTest("hci-logs/extract fehlt")
        rows, meta = load_extract_history(EXTRACT_DIR, mac=TARGET_MAC, skip_old=True)
        self.assertGreaterEqual(len(rows), 1584)
        self.assertEqual(rows[0]["index"], 0)
        self.assertEqual(rows[0]["temp_c"], 24.0625)
        self.assertEqual(rows[0]["humidity_rh"], 59.25)
        by_index = {row["index"]: row for row in rows}
        self.assertIn(1584, by_index)
        self.assertEqual(by_index[1584]["temp_c"], 22.9375)
        self.assertEqual(by_index[1584]["humidity_rh"], 62.5)
        self.assertNotIn("old/", meta["file"] or "")
        self.assertEqual(meta["count_01"], 1586)
        self.assertEqual(len(rows), 1586)


if __name__ == "__main__":
    unittest.main()
