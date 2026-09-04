#!/usr/bin/env python3
"""Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben.

Kein Connect, kein GATT. Filter ist TARGET_MAC im Parser/scan_live.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from scan_live import format_sample, scan_live  # noqa: E402
from thermo_parse import TARGET_MAC, AdvLive  # noqa: E402
from thermo_store import append_sample, default_csv_path, iso_utc_now  # noqa: E402


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben. "
            "Kein Connect, kein GATT."
        )
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="ein Sample, dann Exit (Standard ohne --interval)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        metavar="SEK",
        help="Sekunden zwischen Versuchen (Loop). Unverträglich mit --once",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        metavar="SEK",
        help="Scan-Timeout pro Versuch in Sekunden (Standard: 15)",
    )
    parser.add_argument(
        "--outdir",
        default="data",
        metavar="DIR",
        help="Ausgabeverzeichnis wenn --output fehlt (Standard: data)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help="feste CSV-Datei (sonst default_csv_path mit TARGET_MAC)",
    )
    parser.add_argument(
        "--address",
        default=None,
        metavar="ADDR",
        help=(
            "Optional: zusätzlich device.address an scan_live "
            "(Windows/Linux: MAC, macOS: UUID). Payload-MAC bleibt Pflicht."
        ),
    )
    args = parser.parse_args(argv)
    if args.once and args.interval is not None:
        parser.error("--once und --interval schließen sich aus")
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    if args.interval is not None and args.interval <= 0:
        parser.error("--interval muss größer als 0 sein")
    return args


def resolve_csv_path(args: argparse.Namespace) -> str:
    if args.output:
        return args.output
    return default_csv_path(TARGET_MAC, outdir=args.outdir)


def write_sample(path: str, live: AdvLive) -> None:
    append_sample(
        path,
        iso_utc_now(),
        live.mac,
        live.temp_c,
        live.humidity_rh,
        live.raw_hex,
    )


def _timeout_msg(timeout: float) -> str:
    return "Kein Live-Sample innerhalb von {0} s (Ziel-MAC {1}).".format(
        timeout, TARGET_MAC
    )


def _report_hit(path: str, live: AdvLive) -> None:
    print(format_sample(live))
    print("geschrieben: {0}".format(path))


async def run_once(args: argparse.Namespace, path: str) -> int:
    live = await scan_live(timeout=args.timeout, address=args.address)
    if live is None:
        print(_timeout_msg(args.timeout), file=sys.stderr)
        return 1
    write_sample(path, live)
    _report_hit(path, live)
    return 0


async def run_interval(args: argparse.Namespace, path: str) -> None:
    while True:
        live = await scan_live(timeout=args.timeout, address=args.address)
        if live is None:
            print(_timeout_msg(args.timeout), file=sys.stderr)
        else:
            write_sample(path, live)
            _report_hit(path, live)
        await asyncio.sleep(args.interval)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    path = resolve_csv_path(args)
    try:
        if args.interval is not None:
            asyncio.run(run_interval(args, path))
            return 0
        return asyncio.run(run_once(args, path))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
