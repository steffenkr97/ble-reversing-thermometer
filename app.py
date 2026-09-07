#!/usr/bin/env python3
"""Lokale ThermoBeacon-App: Dashboard, History-Sync, Live-ADV.

Nur eigene Geräte (confirmed in rooms.json). Writes 1A / 01 / 07, nicht 0x18/0x04.
Ohne Adapter: python app.py --no-ble
"""
from __future__ import annotations

import argparse
import os
import sys
from http.server import ThreadingHTTPServer
from typing import List, Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
_COLLECTOR = os.path.join(_ROOT, "collector")
_DASHBOARD = os.path.join(_ROOT, "dashboard")
for _path in (_COLLECTOR, _DASHBOARD):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from server import make_handler  # noqa: E402
from thermo_dash import (  # noqa: E402
    DEFAULT_DATA_DIR,
    DEFAULT_EXTRACT_DIR,
    DEFAULT_ROOMS_PATH,
    DashStore,
)
from thermo_sync import (  # noqa: E402
    DEFAULT_LIVE_INTERVAL_SEC,
    DEFAULT_SCAN_TIMEOUT_SEC,
    AppStatus,
    default_status_path,
    run_worker_thread,
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Lokale ThermoBeacon-App: Dashboard plus History (GATT 07 seit "
            "letztem Abruf) und Live-ADV. --no-ble = nur Dashboard."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind-Adresse (Standard: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (Standard: 8765)")
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        metavar="DIR",
        help="Live/History-CSV (Standard: data/)",
    )
    parser.add_argument(
        "--rooms",
        default=DEFAULT_ROOMS_PATH,
        metavar="PATH",
        help="Allowlist rooms.json",
    )
    parser.add_argument(
        "--extract-dir",
        default=DEFAULT_EXTRACT_DIR,
        metavar="DIR",
        help="HCI-Extracts (adv.csv, att_fff5_fff3.csv)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="HCI-Belegdaten nicht einlesen (nur data/)",
    )
    parser.add_argument(
        "--no-ble",
        action="store_true",
        help="Kein History-Dump, kein Live-Scan (nur Dashboard)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_LIVE_INTERVAL_SEC,
        metavar="SEK",
        help="Sekunden zwischen Live-ADV-Versuchen (Standard: 60)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_SCAN_TIMEOUT_SEC,
        metavar="SEK",
        help="Scan-Timeout je Live-Versuch (Standard: 15)",
    )
    args = parser.parse_args(argv)
    if args.port <= 0 or args.port > 65535:
        parser.error("--port muss 1–65535 sein")
    if args.interval <= 0:
        parser.error("--interval muss größer als 0 sein")
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    data_dir = os.path.abspath(args.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    status = AppStatus(path=default_status_path(data_dir))
    if args.no_ble:
        status.update(
            ble=False,
            phase="idle",
            message="Gestartet mit --no-ble (nur Dashboard)",
        )
    store = DashStore(
        data_dir=data_dir,
        rooms_path=os.path.abspath(args.rooms),
        extract_dir=None if args.no_extract else os.path.abspath(args.extract_dir),
        include_extract=not args.no_extract,
    )
    store.refresh(force=True)
    handler = make_handler(store, status_provider=status.snapshot)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = "http://{0}:{1}/".format(args.host, args.port)
    print("App: {0}".format(url), flush=True)
    print("data-dir: {0}".format(store.data_dir), flush=True)
    print("rooms: {0}".format(store.rooms_path), flush=True)
    print(
        "extract: {0}".format(
            store.extract_dir if store.include_extract else "aus (--no-extract)"
        ),
        flush=True,
    )
    worker = None
    stop = None
    if args.no_ble:
        print("BLE aus (--no-ble). Nur Dashboard.", flush=True)
    else:
        import threading

        stop = threading.Event()
        worker = run_worker_thread(
            store.rooms_path,
            data_dir,
            status,
            interval_sec=args.interval,
            scan_timeout=args.timeout,
            stop_event=stop,
            log=print,
        )
        print("BLE-Worker: History (confirmed), danach Live-ADV alle {} s.".format(args.interval), flush=True)
        print("Nicht senden: 0x18 / 0x04. Nur Allowlist.", flush=True)
    print("Strg+C beendet.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        if stop is not None:
            stop.set()
        server.server_close()
        if worker is not None:
            worker.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
