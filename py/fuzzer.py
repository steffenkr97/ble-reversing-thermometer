#!/usr/bin/env python3
"""ble_fuzzer.py
Python BLE fuzzer for ThermoBeacon-like devices.

Features:
- Connects to a BLE device (by address or system id)
- Enables notifications on FFF3 (Data)
- Writes commands 0x00..0xFF to FFF5 (Control) one by one
- Logs any notifications received after each command
- Safe-mode to skip a small blacklist of potentially destructive commands
- CSV logfile with timestamped results

Requirements:
- Python 3.8+
- bleak (pip install bleak)
- Run where BLE access is available (Linux/Windows with USB passthrough recommended)

Usage example:
    python3 ble_fuzzer.py --address AA:BB:CC:DD:EE:FF --wait 1.0 --log results.csv

CAUTION:
- This tool will write bytes to your device. Some commands may modify or erase data
  on the device (history, settings). Use --safe to enable a conservative blacklist.
"""

import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime
from typing import List

from bleak import BleakClient, BleakScanner, BleakError

# Default UUIDs (common for many cheap sensors)
DEFAULT_SERVICE_UUID = "0000FFE0-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "0000FFF5-0000-1000-8000-00805f9b34fb"  # write
DATA_CHAR_UUID    = "0000FFF3-0000-1000-8000-00805f9b34fb"  # notify

# Conservative blacklist of commands to skip when --safe is used.
# These are guesses (common patterns). Edit as needed.
SAFE_BLACKLIST = {0x04, 0x05, 0xFF, 0xFE}  # e.g., delete-history, factory-reset, unknown


def hexdump(b: bytes) -> str:
    return b.hex().upper()


class NotificationCollector:
    def __init__(self):
        self._items = []  # list of (timestamp, bytes)

    def push(self, data: bytes):
        ts = datetime.utcnow().isoformat() + "Z"
        self._items.append((ts, data))

    def pop_all(self) -> List[tuple]:
        items = self._items[:]
        self._items.clear()
        return items

    def any(self) -> bool:
        return len(self._items) > 0


async def find_device_by_system_id(system_id_hex: str, timeout: int = 8):
    # system_id_hex like "D90000000000DBF4" or with spaces
    normalized = system_id_hex.replace(" ", "").lower()
    print(f"Scanning for device with System ID: {normalized} ... (timeout {timeout}s)")
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        # We may need to connect and read Device Information service to get 2A23
        # Try quick connect to read service if the name matches or manufacturer present
        try:
            async with BleakClient(d.address, timeout=4.0) as client:
                # Try read characteristic 2A23 (System ID) if present
                DIS_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
                SYS_CHAR_UUID = "00002a23-0000-1000-8000-00805f9b34fb"
                svcs = await client.get_services()
                if SYS_CHAR_UUID in [c.uuid for s in svcs for c in s.characteristics]:
                    try:
                        raw = await client.read_gatt_char(SYS_CHAR_UUID)
                        if raw.hex().lower().startswith(normalized):
                            print(f"Found device by System ID: {d.address} ({d.name})")
                            return d.address
                    except Exception:
                        pass
        except Exception:
            # ignore devices we can't briefly connect to
            pass
    return None


async def run_fuzzer(address: str,
                     control_uuid: str,
                     data_uuid: str,
                     start: int,
                     end: int,
                     wait_time: float,
                     logpath: str,
                     safe: bool,
                     write_without_response: bool):
    collector = NotificationCollector()

    def handle_notification(_, data: bytearray):
        # this callback runs in bleak event loop context
        collector.push(bytes(data))

    results = []  # rows for CSV

    print(f"Connecting to {address} ...")
    try:
        async with BleakClient(address, timeout=10.0) as client:
            if not client.is_connected:
                raise BleakError("Could not connect")

            print("Connected. Enabling notifications on data characteristic...")
            try:
                await client.start_notify(data_uuid, handle_notification)
            except Exception as e:
                print(f"Failed to start notifications on {data_uuid}: {e}", file=sys.stderr)
                # continue anyway, maybe notifications are not supported

            # Allow device a moment to settle
            await asyncio.sleep(0.5)

            for cmd in range(start, end + 1):
                if safe and cmd in SAFE_BLACKLIST:
                    note = "SKIPPED (safe blacklist)"
                    print(f"[0x{cmd:02X}] {note}")
                    results.append({
                        "cmd": f"0x{cmd:02X}",
                        "sent_at": "",
                        "status": note,
                        "notifications": ""
                    })
                    continue

                payload = bytes([cmd])
                sent_at = datetime.utcnow().isoformat() + "Z"
                try:
                    if write_without_response:
                        await client.write_gatt_char(control_uuid, payload, response=False)
                    else:
                        await client.write_gatt_char(control_uuid, payload, response=True)
                    status = "OK"
                    print(f"[0x{cmd:02X}] written -> waiting {wait_time}s for notifications...")
                except Exception as e:
                    status = f"WRITE_ERROR: {e}"
                    print(f"[0x{cmd:02X}] write failed: {e}", file=sys.stderr)

                # Wait for notifications to arrive
                await asyncio.sleep(wait_time)

                notes = []
                notifs = collector.pop_all()
                if notifs:
                    for ts, data in notifs:
                        notes.append(f"{ts} {hexdump(data)}")

                results.append({
                    "cmd": f"0x{cmd:02X}",
                    "sent_at": sent_at,
                    "status": status,
                    "notifications": " | ".join(notes)
                })

            # cleanup
            try:
                await client.stop_notify(data_uuid)
            except Exception:
                pass

    except Exception as e:
        print(f"Connection error: {e}", file=sys.stderr)
        # Save what we have if any
    finally:
        # write CSV
        fieldnames = ["cmd", "sent_at", "status", "notifications"]
        try:
            with open(logpath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for r in results:
                    writer.writerow(r)
            print(f"Log written to {logpath}")
        except Exception as e:
            print(f"Failed to write log: {e}", file=sys.stderr)


def parse_args():
    p = argparse.ArgumentParser(description="BLE Fuzzer for ThermoBeacon-like devices")
    p.add_argument("--address", "-a", help="BLE device address (MAC). If omitted, --system-id is required")
    p.add_argument("--system-id", "-s", help="System ID (hex) to find device automatically (e.g. D90000... )")
    p.add_argument("--control-uuid", default=CONTROL_CHAR_UUID, help=f"Control characteristic UUID (default {CONTROL_CHAR_UUID})")
    p.add_argument("--data-uuid", default=DATA_CHAR_UUID, help=f"Data/notify characteristic UUID (default {DATA_CHAR_UUID})")
    p.add_argument("--start", type=lambda x: int(x,0), default=0, help="Start command (inclusive), e.g. 0 or 0x00")
    p.add_argument("--end", type=lambda x: int(x,0), default=255, help="End command (inclusive), e.g. 255 or 0xFF")
    p.add_argument("--wait", type=float, default=1.0, help="Seconds to wait after each write for notifications (default 1.0)")
    p.add_argument("--log", default="ble_fuzzer_results.csv", help="CSV log output path")
    p.add_argument("--safe", action="store_true", default=True, help="Enable safe-mode (skip a small blacklist). Use --no-safe to disable")
    p.add_argument("--no-safe", dest="safe", action="store_false", help="Disable safe-mode to run all commands including blacklist")
    p.add_argument("--write-without-response", action="store_true", default=False, help="Use write without response (may be required for some characteristics)")
    return p.parse_args()


async def main():
    args = parse_args()

    if not args.address and not args.system_id:
        print("Either --address or --system-id must be provided.", file=sys.stderr)
        return

    address = args.address
    if not address and args.system_id:
        found = await find_device_by_system_id(args.system_id)
        if not found:
            print("Device with specified System ID not found.", file=sys.stderr)
            return
        address = found

    print(f"Using address: {address}")
    print(f"Control UUID: {args.control_uuid}, Data UUID: {args.data_uuid}")
    print(f"Commands: 0x{args.start:02X} .. 0x{args.end:02X}, wait {args.wait}s, safe={args.safe}")
    print("WARNING: This tool will actively write to the device. Proceed only if you accept potential state changes on the device.")

    await run_fuzzer(address,
                     args.control_uuid,
                     args.data_uuid,
                     args.start,
                     args.end,
                     args.wait,
                     args.log,
                     args.safe,
                     args.write_without_response)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
