#!/usr/bin/env python3
"""CLI- und Page-Fetch-Tests für dump_history.py (BLE gemockt bzw. Extract)."""
from __future__ import annotations

import asyncio
import csv
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PY_DIR)
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

import dump_history  # noqa: E402
from thermo_parse import (  # noqa: E402
    TARGET_MAC,
    build_history_07_write,
    parse_fff3,
)

GOLD_P0 = bytes.fromhex("07000000000381017B017901B403BC03CB030000")
GOLD_P3 = bytes.fromhex("070300000003740167015A01C003CE03EF030000")
GOLD_P6 = bytearray.fromhex("0730060000016F01E8036E010E040F04F2030000")
GOLD_P6[1:3] = (6).to_bytes(2, "little")
GOLD_P6 = bytes(GOLD_P6)

EXTRACT_DIR = os.path.join(_ROOT, "hci-logs", "extract")


class TestParseArgs(unittest.TestCase):
    def test_from_extract_defaults(self):
        args = dump_history.parse_args(["--from-extract", "hci-logs/extract"])
        self.assertEqual(args.from_extract, "hci-logs/extract")
        self.assertEqual(args.interval_sec, 600.0)
        self.assertEqual(args.mac, TARGET_MAC)
        self.assertEqual(args.outdir, "data")
        self.assertFalse(args.no_timestamps)

    def test_extract_and_address_conflict(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                dump_history.parse_args(
                    ["--from-extract", "x", "--address", TARGET_MAC]
                )

    def test_interval_must_be_positive(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                dump_history.parse_args(["--from-extract", "x", "--interval-sec", "0"])

    def test_help_without_bleak(self):
        with redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(SystemExit) as ctx:
                dump_history.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("from-extract", out.getvalue())


class TestFetchPages(unittest.TestCase):
    def test_seven_samples_three_pages(self):
        writes = []

        async def fake(payload):
            writes.append(bytes(payload))
            if payload == build_history_07_write(0, 3):
                return GOLD_P0
            if payload == build_history_07_write(3, 3):
                return GOLD_P3
            if payload == build_history_07_write(6, 1):
                return GOLD_P6
            self.fail("unerwarteter Write {}".format(payload.hex()))

        pages = asyncio.run(dump_history.fetch_history_pages(fake, 7, retries=0))
        self.assertEqual(len(pages), 3)
        self.assertEqual([p.index for p in pages], [0, 3, 6])
        self.assertEqual(pages[0].count, 3)
        self.assertEqual(pages[2].count, 1)
        self.assertEqual(pages[2].records[0], (22.9375, 62.5))
        self.assertEqual(writes[0][0], 0x07)
        self.assertTrue(all(w[0] == 0x07 for w in writes))
        self.assertTrue(all(w[5] in (1, 3) for w in writes))
        self.assertNotIn(0x04, [w[0] for w in writes])
        self.assertNotIn(0x18, [w[0] for w in writes])

    def test_timeout_then_retry(self):
        calls = {"n": 0}

        async def flaky(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return GOLD_P0

        pages = asyncio.run(
            dump_history.fetch_history_pages(flaky, 3, max_pages=1, retries=2)
        )
        self.assertEqual(len(pages), 1)
        self.assertEqual(calls["n"], 2)

    def test_max_pages(self):
        async def fake(payload):
            return GOLD_P0 if payload == build_history_07_write(0, 3) else GOLD_P3

        pages = asyncio.run(
            dump_history.fetch_history_pages(fake, 1584, max_pages=1, retries=0)
        )
        self.assertEqual(len(pages), 1)


class TestDumpFromExtractCli(unittest.TestCase):
    def test_writes_complete_history_csv(self):
        if not os.path.isfile(os.path.join(EXTRACT_DIR, "att_fff5_fff3.csv")):
            self.skipTest("hci-logs/extract fehlt")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.csv")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = dump_history.main(
                    [
                        "--from-extract",
                        EXTRACT_DIR,
                        "--output",
                        path,
                        "--newest-time",
                        "2025-11-26T15:19:35Z",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(path))
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1586)
            self.assertEqual(rows[0]["mac"], TARGET_MAC)
            self.assertEqual(float(rows[0]["temp_c"]), 24.0625)
            self.assertEqual(rows[-1]["index"], "1585")
            self.assertEqual(rows[1584]["index"], "1584")
            self.assertEqual(float(rows[1584]["temp_c"]), 22.9375)
            self.assertEqual(rows[1584]["timestamp_inferred"], "2025-11-26T15:09:35Z")
            self.assertEqual(rows[-1]["timestamp_inferred"], "2025-11-26T15:19:35Z")
            self.assertIn("geschrieben:", buf.getvalue())
            parsed0 = parse_fff3(bytes.fromhex(rows[0]["raw_hex"]))
            self.assertEqual(parsed0.index, 0)

    def test_all_rooms_extract_writes_buero_only(self):
        if not os.path.isfile(os.path.join(EXTRACT_DIR, "att_fff5_fff3.csv")):
            self.skipTest("hci-logs/extract fehlt")
        rooms_path = os.path.join(_ROOT, "dashboard", "rooms.json")
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                rc = dump_history.main(
                    [
                        "--from-extract",
                        EXTRACT_DIR,
                        "--all-rooms",
                        "--rooms",
                        rooms_path,
                        "--outdir",
                        tmp,
                        "--newest-time",
                        "2025-11-26T15:19:35Z",
                    ]
                )
            self.assertEqual(rc, 0)
            buero = os.path.join(tmp, "history_f4db000000d9.csv")
            self.assertTrue(os.path.isfile(buero))
            with open(buero, newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1586)
            other = os.path.join(tmp, "history_f4d00000021a.csv")
            self.assertFalse(os.path.isfile(other))
            self.assertIn("all-rooms", buf.getvalue())

    def test_all_rooms_and_output_conflict(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                dump_history.parse_args(
                    ["--from-extract", "x", "--all-rooms", "--output", "y.csv"]
                )


if __name__ == "__main__":
    unittest.main()
