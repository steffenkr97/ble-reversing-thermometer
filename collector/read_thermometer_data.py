#!/usr/bin/env python3
"""GATT-Probe für das eigene ThermoBeacon (Phase 3).

App-Sequenz: Notify+CCCD → Write FFF5 ``1A`` → ``01`` → optional eine History-Page ``07``.
Kein Collector (kein CSV, kein Intervall). Ausgabe nur über ``parse_fff3``.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Optional

from bleak import BleakClient, BleakScanner

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_parse import (  # noqa: E402
    TARGET_MAC,
    TARGET_SYSTEM_ID,
    SERVICE_UUID,
    CONTROL_CHAR_UUID,
    DATA_CHAR_UUID,
    SYSTEM_ID_UUID,
    parse_fff3,
    build_history_07_write,
    Status1A,
    Count01,
    History07,
)

CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"
COMPANY_ID = 0x001B
NOTIFY_TIMEOUT = 1.0
SCAN_TIMEOUT = 10.0


def _hex(data: bytes) -> str:
    return " ".join("{:02X}".format(b) for b in data)


def _norm_mac(addr: str) -> str:
    return addr.replace("-", ":").replace(".", ":").lower()


def _macs_equal(a: str, b: str) -> bool:
    return _norm_mac(a) == _norm_mac(b)


def _uuid_eq(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _adv_mac(adv) -> Optional[str]:
    """MAC aus Manufacturer-Payload (Offset 2, 6 Byte LE), falls Company 0x001B."""
    if adv is None:
        return None
    payload = (adv.manufacturer_data or {}).get(COMPANY_ID)
    if not payload or len(payload) < 8:
        return None
    mac_le = payload[2:8]
    return ":".join("{:02x}".format(b) for b in reversed(mac_le))


def _is_thermobeacon_candidate(device, adv) -> bool:
    """Kandidat über Name, Company 0x001B, Service FFF0 oder TARGET_MAC."""
    names = []
    if device.name:
        names.append(device.name)
    if adv is not None and adv.local_name:
        names.append(adv.local_name)
    if any("ThermoBeacon" in n for n in names):
        return True
    if _macs_equal(device.address, TARGET_MAC):
        return True
    if adv is None:
        return False
    if COMPANY_ID in (adv.manufacturer_data or {}):
        return True
    adv_mac = _adv_mac(adv)
    if adv_mac and _macs_equal(adv_mac, TARGET_MAC):
        return True
    for uuid in adv.service_uuids or []:
        if "fff0" in uuid.lower():
            return True
    return False


def _candidate_score(device, adv) -> int:
    score = 0
    if _macs_equal(device.address, TARGET_MAC):
        score += 4
    adv_mac = _adv_mac(adv)
    if adv_mac and _macs_equal(adv_mac, TARGET_MAC):
        score += 4
    names = " ".join(
        n for n in (device.name, getattr(adv, "local_name", None) if adv else None) if n
    )
    if "ThermoBeacon" in names:
        score += 1
    return score


def _find_char(client: BleakClient, uuid: str):
    for service in client.services:
        for char in service.characteristics:
            if _uuid_eq(char.uuid, uuid):
                return char
    return None


def _find_cccd(char):
    for desc in char.descriptors:
        if "2902" in desc.uuid.lower() or _uuid_eq(desc.uuid, CCCD_UUID):
            return desc
    return None


def _sid_bytes(value) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return bytes.fromhex(str(value).replace(" ", ""))


def _print_parsed(parsed, raw: bytes) -> None:
    """Ausgabe nur über parse_fff3. Form-B-Zusatz bei Count01 nicht als Live."""
    if parsed is None:
        print("  unbekanntes Notify ({} Byte): {}".format(len(raw), _hex(raw)))
        return
    if isinstance(parsed, Status1A):
        print("  Status 1A  raw={}".format(parsed.raw_hex))
        return
    if isinstance(parsed, Count01):
        print(
            "  Count 01   samples={}  raw={}".format(
                parsed.sample_count, parsed.raw_hex
            )
        )
        return
    if isinstance(parsed, History07):
        print(
            "  History 07  index={}  count={}  raw={}".format(
                parsed.index, parsed.count, parsed.raw_hex
            )
        )
        for i, rec in enumerate(parsed.records):
            temp, hum = rec
            print("    [{:d}] {:.4f} °C  {:.4f} %rF".format(i, temp, hum))
        return
    print("  unerwarteter Parser-Typ: {!r}".format(parsed))


async def _read_system_id(client: BleakClient) -> Optional[bytes]:
    try:
        return bytes(await client.read_gatt_char(SYSTEM_ID_UUID))
    except Exception:
        return None


async def find_device_by_system_id() -> Optional[str]:
    """Scan: ThermoBeacon-Kandidaten (Payload/Name), dann 2A23 == TARGET_SYSTEM_ID.

    Kein Fallback auf das erstbeste ThermoBeacon.
    """
    print("Scanne nach ThermoBeacon-Kandidaten (Name / Manufacturer 0x001B / MAC)...")
    discovered = await BleakScanner.discover(timeout=SCAN_TIMEOUT, return_adv=True)

    candidates = []
    for _addr, pair in discovered.items():
        device, adv = pair
        if _is_thermobeacon_candidate(device, adv):
            candidates.append((_candidate_score(device, adv), device, adv))
    candidates.sort(key=lambda item: -item[0])

    if not candidates:
        print("Keine ThermoBeacon-Kandidaten gefunden.")
        return None

    target_sid = _sid_bytes(TARGET_SYSTEM_ID)
    print("Kandidaten: {}".format(len(candidates)))
    for _score, device, adv in candidates:
        adv_mac = _adv_mac(adv)
        print(
            "  {}  name={!r}  adv_mac={}".format(
                device.address, device.name, adv_mac or "-"
            )
        )
        try:
            async with BleakClient(device.address, timeout=8.0) as client:
                sid = await _read_system_id(client)
                if sid is None:
                    print("    System ID nicht lesbar")
                    continue
                if sid == target_sid:
                    print("    System ID stimmt — Zielgerät.")
                    return device.address
                print("    System ID abweichend: {}".format(_hex(sid)))
        except Exception as exc:
            print("    Connect fehlgeschlagen: {}".format(exc))

    print("Kein Gerät mit TARGET_SYSTEM_ID gefunden (kein Erstes-Gerät-Fallback).")
    return None


async def dump_services(client: BleakClient) -> None:
    """Kurz alle Services/Characteristics listen (--debug-only)."""
    print("\nServices und Characteristics:")
    for service in client.services:
        print("\nService {}".format(service.uuid))
        for char in service.characteristics:
            props = ", ".join(char.properties)
            print(
                "  {}  handle={}  [{}]".format(char.uuid, char.handle, props)
            )
            if "read" in char.properties:
                try:
                    value = await client.read_gatt_char(char.uuid)
                    try:
                        decoded = value.decode("utf-8", errors="ignore").strip("\x00").strip()
                    except Exception:
                        decoded = ""
                    if decoded and all(c.isprintable() or c in "\n\r\t" for c in decoded):
                        print('    Wert: "{}"'.format(decoded))
                    else:
                        print("    Wert: {}".format(_hex(bytes(value))))
                except Exception as exc:
                    print("    Wert: <nicht lesbar: {}>".format(exc))
            for desc in char.descriptors:
                print("    Descriptor {}  handle={}".format(desc.uuid, desc.handle))


async def enable_notify(client: BleakClient, handler) -> None:
    """start_notify plus expliziter CCCD-Write 01 00 (wie die App)."""
    data_char = _find_char(client, DATA_CHAR_UUID)
    if data_char is None:
        raise RuntimeError("Characteristic FFF3 nicht gefunden")

    await client.start_notify(DATA_CHAR_UUID, handler)
    print("start_notify(FFF3) ok")

    cccd = _find_cccd(data_char)
    if cccd is None:
        print("Warnung: CCCD 2902 nicht gefunden — nur start_notify.")
        return
    await client.write_gatt_descriptor(cccd.handle, b"\x01\x00")
    print("CCCD 2902 = 01 00")
    await asyncio.sleep(0.1)


async def wait_notify(queue: asyncio.Queue, opcode: int, timeout: float = NOTIFY_TIMEOUT):
    """Wartet auf ein 20-Byte-Notify mit Echo-Opcode."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            data = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if len(data) == 20 and data and data[0] == opcode:
            return data


def _drain(queue: asyncio.Queue) -> None:
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break


async def probe_write(client: BleakClient, queue: asyncio.Queue, payload: bytes):
    """Ein FFF5-Write, dann 20-Byte-Notify parsen. Nur 1A / 01 / 07."""
    opcode = payload[0]
    _drain(queue)
    await client.write_gatt_char(CONTROL_CHAR_UUID, payload, response=True)
    print("Write FFF5: {}".format(_hex(payload)))
    raw = await wait_notify(queue, opcode, timeout=NOTIFY_TIMEOUT)
    if raw is None:
        print("  Timeout (~{:.0f}s), keine 20-Byte-Antwort auf {:02X}".format(
            NOTIFY_TIMEOUT, opcode
        ))
        return None
    parsed = parse_fff3(raw)
    _print_parsed(parsed, raw)
    return parsed


async def run_probe(
    device_address: str,
    history_index: Optional[int],
    debug_only: bool,
    address_was_given: bool,
) -> None:
    print("Verbinde mit {} ...".format(device_address))
    async with BleakClient(device_address, timeout=20.0) as client:
        print("Verbunden.")

        sid = await _read_system_id(client)
        target_sid = _sid_bytes(TARGET_SYSTEM_ID)
        if sid is None:
            if address_was_given or _macs_equal(device_address, TARGET_MAC):
                print("System ID nicht lesbar; fahre mit gegebener Adresse fort.")
            else:
                print(
                    "System ID nicht lesbar und Adresse ist nicht TARGET_MAC — Abbruch."
                )
                return
        elif sid != target_sid:
            print(
                "System ID {} != Ziel {} — falsches Gerät, Abbruch.".format(
                    _hex(sid), _hex(target_sid)
                )
            )
            return
        else:
            print("System ID ok: {}".format(_hex(sid)))

        if _find_char(client, CONTROL_CHAR_UUID) is None:
            print("FFF5 (Control) nicht gefunden.")
            return
        if _find_char(client, DATA_CHAR_UUID) is None:
            print("FFF3 (Data) nicht gefunden.")
            return
        service_ok = any(_uuid_eq(s.uuid, SERVICE_UUID) for s in client.services)
        if not service_ok:
            print("Service FFE0 nicht gefunden.")
            return

        if debug_only:
            await dump_services(client)
            print("\n[--debug-only] keine Writes.")
            return

        queue = asyncio.Queue()

        def _on_notify(_sender, data):
            queue.put_nowait(bytes(data))

        await enable_notify(client, _on_notify)

        print("\nSequenz 1A → 01" + (
            " → 07 index={}".format(history_index) if history_index is not None else ""
        ))
        await probe_write(client, queue, bytes([0x1A]))
        await probe_write(client, queue, bytes([0x01]))

        if history_index is not None:
            payload = build_history_07_write(history_index, 3)
            if len(payload) != 6:
                print("build_history_07_write lieferte {} Byte, erwartet 6.".format(len(payload)))
                return
            await probe_write(client, queue, payload)

        try:
            await client.stop_notify(DATA_CHAR_UUID)
        except Exception:
            pass


async def async_main(args: argparse.Namespace) -> None:
    if args.address:
        address = args.address
    else:
        address = await find_device_by_system_id()
        if not address:
            print("Tipp: --address {} setzen.".format(TARGET_MAC))
            return

    await run_probe(address, args.history, args.debug_only, bool(args.address))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GATT-Probe ThermoBeacon: CCCD, dann 1A → 01, optional eine History-Page 07.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python collector/read_thermometer_data.py --address f4:db:00:00:00:d9
  python collector/read_thermometer_data.py --use-system-id
  python collector/read_thermometer_data.py --address f4:db:00:00:00:d9 --history 0
  python collector/read_thermometer_data.py --debug-only --address f4:db:00:00:00:d9
        """,
    )
    parser.add_argument(
        "--address",
        "-a",
        type=str,
        help="BLE-Adresse (Linux/Windows: MAC; macOS: CoreBluetooth-UUID)",
    )
    parser.add_argument(
        "--use-system-id",
        action="store_true",
        help="Scan nach ThermoBeacon-Kandidaten, Ziel nur bei 2A23 == TARGET_SYSTEM_ID "
        "(Standard, wenn --address fehlt)",
    )
    parser.add_argument(
        "--history",
        type=int,
        metavar="INDEX",
        default=None,
        help="Genau eine History-Page: Write 07 <index> 00 00 03",
    )
    parser.add_argument(
        "--debug-only",
        action="store_true",
        help="Nur Services listen, keine FFF5-Writes",
    )
    args = parser.parse_args()

    if args.history is not None and args.history < 0:
        parser.error("--history muss >= 0 sein")
    if args.debug_only and args.history is not None:
        parser.error("--debug-only und --history schließen sich aus")

    # --use-system-id ist der Scan-Pfad; ohne --address immer aktiv.
    if not args.address and not args.use_system_id:
        args.use_system_id = True

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nAbbruch.")


if __name__ == "__main__":
    main()
