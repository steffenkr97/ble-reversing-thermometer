#!/usr/bin/env python3
"""App-Sync ohne BLE: Plan, Persistenz, Worker mit Fakes."""
from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_PY_DIR)
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from thermo_history import (  # noqa: E402
    default_history_csv_path,
    read_history_csv,
)
from thermo_parse import AdvLive, TARGET_MAC  # noqa: E402
from thermo_rooms import add_room, save_rooms  # noqa: E402
from thermo_sync import (  # noqa: E402
    AppStatus,
    persist_history_dump,
    plan_incremental,
    run_worker,
    stored_last_index,
    sync_history_one,
)
import app as app_mod  # noqa: E402


def _row(index, temp, hum=40.0):
    return {
        "mac": TARGET_MAC,
        "index": index,
        "record": index % 3,
        "temp_c": temp,
        "humidity_rh": hum,
        "raw_hex": "aa",
        "timestamp_inferred": "",
    }


class TestPlanIncremental(unittest.TestCase):
    def test_up_to_date(self):
        self.assertEqual(plan_incremental(1586, 1585), [])

    def test_tail_pages(self):
        self.assertEqual(plan_incremental(1586, 1583), [(1584, 1), (1585, 1)])

    def test_reset_full_plan(self):
        plan = plan_incremental(3, 20)
        self.assertEqual(plan, [(0, 3)])


class TestPersist(unittest.TestCase):
    def test_merge_writes_sync_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = [_row(0, 1.0), _row(1, 2.0)]
            incoming = [_row(2, 3.0)]
            result = persist_history_dump(
                TARGET_MAC,
                tmp,
                existing,
                incoming,
                sample_count=3,
                newest_utc="2026-09-04T12:00:00Z",
            )
            self.assertEqual(result["new_samples"], 1)
            self.assertEqual(result["state"], "ok")
            rows = read_history_csv(default_history_csv_path(TARGET_MAC, tmp))
            self.assertEqual([r["index"] for r in rows], [0, 1, 2])
            self.assertEqual(stored_last_index(tmp, TARGET_MAC), 2)
            self.assertEqual(persist_history_dump(
                TARGET_MAC, tmp, rows, [], 3, newest_utc="2026-09-04T13:00:00Z"
            )["state"], "up_to_date")


class TestWorker(unittest.TestCase):
    def test_only_confirmed_and_live_round(self):
        with tempfile.TemporaryDirectory() as tmp:
            rooms_path = os.path.join(tmp, "rooms.json")
            rooms = add_room([], "Büro", TARGET_MAC, confirmed=True)
            rooms = add_room(
                rooms,
                "Kandidat",
                "f4:d0:00:00:02:1a",
                confirmed=False,
                encoding_checked=False,
            )
            save_rooms(rooms_path, rooms)
            fetched = []

            async def fake_gatt(address, mac, rooms_arg, plan_fn):
                fetched.append(mac)
                plan_fn(3)
                return 3, []

            live_calls = []

            async def fake_scan(macs, timeout, address):
                live_calls.append(list(macs))
                return {
                    TARGET_MAC: AdvLive(
                        mac=TARGET_MAC,
                        temp_c=25.125,
                        humidity_rh=62.0,
                        battery_mv=2600,
                        counter=1,
                        raw_hex="11",
                    )
                }

            slept = []

            async def fake_sleep(_sec):
                slept.append(_sec)
                raise asyncio.CancelledError()

            status = AppStatus()
            stop = threading.Event()

            async def _run():
                try:
                    await run_worker(
                        rooms_path,
                        tmp,
                        status,
                        interval_sec=1,
                        scan_timeout=1,
                        stop_event=stop,
                        enable_live=True,
                        gatt_fetch=fake_gatt,
                        scan_fn=fake_scan,
                        sleep_fn=fake_sleep,
                    )
                except asyncio.CancelledError:
                    pass

            asyncio.run(_run())
            self.assertEqual(fetched, [TARGET_MAC])
            self.assertEqual(live_calls, [[TARGET_MAC]])
            snap = status.snapshot()
            self.assertTrue(snap["ble"])
            self.assertEqual(snap["devices"][TARGET_MAC]["live"]["temp_c"], 25.125)

    def test_sync_history_one_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            persist_history_dump(
                TARGET_MAC, tmp, [_row(0, 1.0)], [], 1, newest_utc="2026-09-04T12:00:00Z"
            )

            async def fake_gatt(address, mac, rooms_arg, plan_fn):
                self.assertEqual(plan_fn(1), [])
                return 1, []

            room = {"id": "buero", "name": "Büro", "mac": TARGET_MAC, "confirmed": True}
            result = asyncio.run(
                sync_history_one(room, tmp, [room], gatt_fetch=fake_gatt)
            )
            self.assertEqual(result["state"], "up_to_date")
            self.assertEqual(result["new_samples"], 0)


class TestAppCli(unittest.TestCase):
    def test_help_and_no_ble(self):
        with redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                app_mod.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        args = app_mod.parse_args(["--no-ble", "--port", "8766"])
        self.assertTrue(args.no_ble)
        self.assertEqual(args.port, 8766)
        self.assertEqual(args.interval, 60.0)


if __name__ == "__main__":
    unittest.main()
