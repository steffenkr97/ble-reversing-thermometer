#!/usr/bin/env python3
"""Live-Temperatur und Luftfeuchtigkeit aus ADV_IND, ohne GATT-Connect.

Scannt Manufacturer Specific Data (Company-ID 0x001B, 20-Byte-Live-Frame)
per Bleak. Filter ist die MAC im Payload (TARGET_MAC), nicht der Gerätename.
Erstes gültiges Sample auf stdout, dann Exit 0.
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

from bleak import BleakScanner

from thermo_parse import (  # noqa: E402
    COMPANY_ID,
    TARGET_MAC,
    AdvLive,
    parse_adv_manufacturer,
)


def assemble_mfg_frame(company_id: int, payload: bytes) -> Optional[bytes]:
    """Company-ID und Rest zu einem 20-Byte-Frame zusammenbauen.

    bleak liefert ``dict[company_id, rest]``. Manche Backends geben die
    18 Byte nach der Company-ID, andere die 20 Byte inkl. ``1B 00``.
    """
    payload = bytes(payload)
    cid = int(COMPANY_ID)
    cid_le = cid.to_bytes(2, "little")
    if company_id == cid and len(payload) == 18:
        return cid_le + payload
    if len(payload) == 20 and payload.startswith(cid_le):
        return payload
    return None


def format_sample(live: AdvLive) -> str:
    return (
        "temp_c={0} humidity_rh={1} battery_mv={2} "
        "counter={3} mac={4} raw_hex={5}".format(
            live.temp_c,
            live.humidity_rh,
            live.battery_mv,
            live.counter,
            live.mac,
            live.raw_hex,
        )
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Live-Temperatur/Luftfeuchtigkeit aus ADV_IND Manufacturer Data. "
            "Kein Connect, kein GATT."
        )
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        metavar="SEK",
        help="Scan-Timeout in Sekunden (Standard: 15)",
    )
    parser.add_argument(
        "--address",
        default=None,
        metavar="ADDR",
        help=(
            "Optional: zusätzlich device.address filtern "
            "(Windows/Linux: MAC, macOS: UUID). Payload-MAC bleibt Pflicht."
        ),
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    return args


async def scan_live(
    timeout: float, address: Optional[str] = None
) -> Optional[AdvLive]:
    """Erstes gültiges AdvLive oder None nach Timeout."""
    loop = asyncio.get_running_loop()
    done = asyncio.Event()
    found: List[AdvLive] = []
    want_addr = address.lower() if address else None

    def on_detect(device, advertisement_data) -> None:
        if done.is_set():
            return
        if want_addr is not None and device.address.lower() != want_addr:
            return
        mfg = getattr(advertisement_data, "manufacturer_data", None) or {}
        for company_id, payload in mfg.items():
            frame = assemble_mfg_frame(company_id, payload)
            if frame is None:
                continue
            live = parse_adv_manufacturer(frame)
            if live is None:
                continue
            found.append(live)
            loop.call_soon_threadsafe(done.set)
            return

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        await scanner.stop()
    return found[0] if found else None


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        live = asyncio.run(scan_live(timeout=args.timeout, address=args.address))
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 1
    if live is None:
        print(
            "Kein Live-Sample innerhalb von {0} s (Ziel-MAC {1}).".format(
                args.timeout, TARGET_MAC
            ),
            file=sys.stderr,
        )
        return 1
    print(format_sample(live))
    return 0


if __name__ == "__main__":
    sys.exit(main())
