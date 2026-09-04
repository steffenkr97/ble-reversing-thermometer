#!/usr/bin/env python3
"""Live-Temperatur und Luftfeuchtigkeit aus ADV_IND, ohne GATT-Connect.

Scannt Manufacturer Specific Data (Company-ID 0x001B, 20-Byte-Live-Frame)
per Bleak. Filter ist die Payload-MAC gegen die Allowlist (rooms.json),
nicht der Gerätename. CLI-Standard: nur Büro-MAC.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Dict, Iterable, List, Optional

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
from thermo_rooms import (  # noqa: E402
    DEFAULT_ROOMS_PATH,
    allowlist_macs,
    load_rooms,
    mac_in_allowlist,
    normalize_mac,
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
    parser.add_argument(
        "--mac",
        default=TARGET_MAC,
        metavar="MAC",
        help="Payload-MAC (Standard: Büro {}). Muss auf der Allowlist stehen.".format(
            TARGET_MAC
        ),
    )
    parser.add_argument(
        "--rooms",
        default=DEFAULT_ROOMS_PATH,
        metavar="PATH",
        help="Allowlist rooms.json (Standard: dashboard/rooms.json)",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    return args


def _allowed_from_rooms(rooms_path: str, mac: Optional[str]) -> List[str]:
    rooms = load_rooms(rooms_path)
    allowed = allowlist_macs(rooms)
    if not allowed:
        allowed = [TARGET_MAC]
    if mac:
        want = normalize_mac(mac)
        if not mac_in_allowlist(want, allowed):
            raise ValueError(
                "MAC {} steht nicht in der Allowlist ({})".format(want, rooms_path)
            )
        return [want]
    return allowed


async def scan_live(
    timeout: float,
    address: Optional[str] = None,
    allowed_macs: Optional[Iterable[str]] = None,
) -> Optional[AdvLive]:
    """Erstes gültiges AdvLive oder None nach Timeout."""
    found = await scan_live_many(
        timeout, allowed_macs=allowed_macs, address=address, stop_after=1
    )
    if not found:
        return None
    return next(iter(found.values()))


async def scan_live_many(
    timeout: float,
    allowed_macs: Optional[Iterable[str]] = None,
    address: Optional[str] = None,
    stop_after: Optional[int] = None,
) -> Dict[str, AdvLive]:
    """Ein Sample je Allowlist-MAC, bis Timeout oder stop_after Treffer.

    allowed_macs None = nur Büro-TARGET_MAC (wie bisher).
    """
    wanted = [normalize_mac(m) for m in allowed_macs] if allowed_macs is not None else [
        TARGET_MAC
    ]
    if not wanted:
        return {}
    loop = asyncio.get_running_loop()
    done = asyncio.Event()
    found: Dict[str, AdvLive] = {}
    want_addr = address.lower() if address else None
    target_n = len(wanted) if stop_after is None else min(int(stop_after), len(wanted))

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
            live = parse_adv_manufacturer(frame, allowed_macs=wanted)
            if live is None:
                continue
            if live.mac in found:
                return
            found[live.mac] = live
            if len(found) >= target_n:
                loop.call_soon_threadsafe(done.set)
            return

    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        await scanner.stop()
    return found


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        allowed = _allowed_from_rooms(args.rooms, args.mac)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        live = asyncio.run(
            scan_live(timeout=args.timeout, address=args.address, allowed_macs=allowed)
        )
    except KeyboardInterrupt:
        print("Abgebrochen.", file=sys.stderr)
        return 1
    if live is None:
        print(
            "Kein Live-Sample innerhalb von {0} s (Allowlist {1}).".format(
                args.timeout, ", ".join(allowed)
            ),
            file=sys.stderr,
        )
        return 1
    print(format_sample(live))
    return 0


if __name__ == "__main__":
    sys.exit(main())
