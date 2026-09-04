#!/usr/bin/env python3
"""Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben.

Kein Connect, kein GATT. Filter ist die Allowlist in rooms.json
(Payload-MAC), nicht der Gerätename. Ein Sample je MAC in die jeweilige CSV.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Dict, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from scan_live import format_sample, scan_live, scan_live_many  # noqa: E402
from thermo_parse import TARGET_MAC, AdvLive  # noqa: E402
from thermo_rooms import (  # noqa: E402
    DEFAULT_ROOMS_PATH,
    allowlist_macs,
    load_rooms,
    mac_in_allowlist,
    normalize_mac,
)
from thermo_store import append_sample, default_csv_path, iso_utc_now  # noqa: E402


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben. "
            "Kein Connect, kein GATT. Allowlist: rooms.json."
        )
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="ein Scan-Fenster, dann Exit (Standard ohne --interval)",
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
        help="feste CSV-Datei (nur ein Ziel-MAC; sonst default_csv_path je MAC)",
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
    parser.add_argument(
        "--rooms",
        default=DEFAULT_ROOMS_PATH,
        metavar="PATH",
        help="Allowlist rooms.json (Standard: dashboard/rooms.json)",
    )
    parser.add_argument(
        "--mac",
        default=None,
        metavar="MAC",
        help="Nur diese Payload-MAC (muss auf der Allowlist stehen)",
    )
    args = parser.parse_args(argv)
    if args.once and args.interval is not None:
        parser.error("--once und --interval schließen sich aus")
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    if args.interval is not None and args.interval <= 0:
        parser.error("--interval muss größer als 0 sein")
    return args


def resolve_macs(args: argparse.Namespace) -> List[str]:
    rooms = load_rooms(args.rooms)
    allowed = allowlist_macs(rooms) or [TARGET_MAC]
    if args.mac:
        want = normalize_mac(args.mac)
        if not mac_in_allowlist(want, allowed):
            raise ValueError(
                "MAC {} steht nicht in der Allowlist ({}).".format(want, args.rooms)
            )
        return [want]
    return allowed


def resolve_csv_path(args: argparse.Namespace, mac: str) -> str:
    if args.output:
        return args.output
    return default_csv_path(mac, outdir=args.outdir)


def write_sample(path: str, live: AdvLive) -> None:
    append_sample(
        path,
        iso_utc_now(),
        live.mac,
        live.temp_c,
        live.humidity_rh,
        live.raw_hex,
    )


def _timeout_msg(timeout: float, macs: Sequence[str]) -> str:
    return "Kein Live-Sample innerhalb von {0} s (Allowlist {1}).".format(
        timeout, ", ".join(macs)
    )


def _report_hit(path: str, live: AdvLive) -> None:
    print(format_sample(live))
    print("geschrieben: {0}".format(path))


def _write_found(
    args: argparse.Namespace, found: Dict[str, AdvLive]
) -> List[str]:
    written = []
    for mac, live in found.items():
        path = resolve_csv_path(args, mac)
        write_sample(path, live)
        _report_hit(path, live)
        written.append(path)
    return written


async def _scan(args: argparse.Namespace, macs: Sequence[str]) -> Dict[str, AdvLive]:
    if len(macs) == 1:
        live = await scan_live(
            timeout=args.timeout, address=args.address, allowed_macs=macs
        )
        if live is None:
            return {}
        return {live.mac: live}
    return await scan_live_many(
        timeout=args.timeout, allowed_macs=macs, address=args.address
    )


async def run_once(args: argparse.Namespace, macs: Sequence[str]) -> int:
    found = await _scan(args, macs)
    if not found:
        print(_timeout_msg(args.timeout, macs), file=sys.stderr)
        return 1
    _write_found(args, found)
    missing = [m for m in macs if m not in found]
    if missing:
        print(
            "kein Sample in diesem Fenster: {0}".format(", ".join(missing)),
            file=sys.stderr,
        )
    return 0


async def run_interval(args: argparse.Namespace, macs: Sequence[str]) -> None:
    while True:
        found = await _scan(args, macs)
        if not found:
            print(_timeout_msg(args.timeout, macs), file=sys.stderr)
        else:
            _write_found(args, found)
            missing = [m for m in macs if m not in found]
            if missing:
                print(
                    "kein Sample in diesem Fenster: {0}".format(", ".join(missing)),
                    file=sys.stderr,
                )
        await asyncio.sleep(args.interval)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        macs = resolve_macs(args)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output and len(macs) > 1:
        print(
            "--output braucht genau ein Ziel-MAC (--mac …).",
            file=sys.stderr,
        )
        return 2
    try:
        if args.interval is not None:
            asyncio.run(run_interval(args, macs))
            return 0
        return asyncio.run(run_once(args, macs))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
