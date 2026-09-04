#!/usr/bin/env python3
"""History-Dump: GATT 1A → 01 → alle 07-Pages, oder Import aus HCI-Extract.

Live verbindet und schreibt nur beobachtete FFF5-Payloads (1A, 01, 07).
``--from-extract`` braucht kein bleak und sendet nichts.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from typing import Callable, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from thermo_history import (  # noqa: E402
    INTERVAL_SEC_HYPOTHESIS,
    apply_inferred_timestamps,
    assert_allowed_fff5_write,
    default_history_csv_path,
    load_extract_history,
    normalize_mac,
    page_plan,
    parse_iso_utc,
    samples_from_pages,
    write_history_csv,
)
from thermo_parse import (  # noqa: E402
    CONTROL_CHAR_UUID,
    Count01,
    DATA_CHAR_UUID,
    History07,
    SERVICE_UUID,
    TARGET_MAC,
    TARGET_SYSTEM_ID,
    build_history_07_write,
    parse_fff3,
)
from thermo_store import iso_utc_now  # noqa: E402


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "History-Dump ThermoBeacon: CCCD, dann 1A → 01 → alle 07-Pages "
            "in data/history_<mac12>.csv. Oder --from-extract ohne BLE."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python collector/dump_history.py --from-extract hci-logs/extract
  python collector/dump_history.py --address f4:db:00:00:00:d9
  python collector/dump_history.py --use-system-id

Nicht senden: 04 / 05 / 18 / 19 / 0F / F3.
timestamp_inferred ist Hypothese (10 min, ADV-Counter/Count ≈ 600 s).
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
        help="Scan, Ziel nur bei 2A23 == TARGET_SYSTEM_ID (ohne --address und ohne Extract)",
    )
    parser.add_argument(
        "--from-extract",
        metavar="PATH",
        default=None,
        help="att_fff5_fff3.csv oder Extract-Ordner. Kein BLE, keine Writes.",
    )
    parser.add_argument(
        "--mac",
        default=TARGET_MAC,
        help="Geräte-MAC für CSV/Extract (Standard: Büro {})".format(TARGET_MAC),
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
        help="feste CSV-Datei (sonst history_<mac12>.csv)",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=INTERVAL_SEC_HYPOTHESIS,
        metavar="SEK",
        help="Hypothese für timestamp_inferred (Standard: 600 = 10 min)",
    )
    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        help="timestamp_inferred leer lassen",
    )
    parser.add_argument(
        "--newest-time",
        default=None,
        metavar="ISO",
        help="Anker fürs neueste Sample (ISO-8601 UTC). Sonst Dump-/Capture-Zeit.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="Nur die ersten N Pages (Tests / Abbruch). Live: trotzdem 1A+01.",
    )
    parser.add_argument(
        "--include-old",
        action="store_true",
        help="Extract: auch old/*.cfa (2018-Zeitstempel)",
    )
    parser.add_argument(
        "--notify-timeout",
        type=float,
        default=2.0,
        metavar="SEK",
        help="Wartezeit je Notify (Standard: 2; Capture-Median 07 ≈ 0,16 s)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Wiederholungen pro 07-Page bei Timeout/Parse (Standard: 2)",
    )
    args = parser.parse_args(argv)
    if args.from_extract and args.address:
        parser.error("--from-extract und --address schließen sich aus")
    if args.from_extract and args.use_system_id:
        parser.error("--from-extract und --use-system-id schließen sich aus")
    if args.interval_sec <= 0:
        parser.error("--interval-sec muss größer als 0 sein")
    if args.notify_timeout <= 0:
        parser.error("--notify-timeout muss größer als 0 sein")
    if args.retries < 0:
        parser.error("--retries muss >= 0 sein")
    if args.max_pages is not None and args.max_pages < 0:
        parser.error("--max-pages muss >= 0 sein")
    if args.newest_time:
        try:
            parse_iso_utc(args.newest_time)
        except ValueError:
            parser.error("--newest-time ist kein ISO-8601-Zeitstempel")
    if not args.from_extract and not args.address and not args.use_system_id:
        args.use_system_id = True
    return args


def resolve_csv_path(args: argparse.Namespace) -> str:
    if args.output:
        return args.output
    return default_history_csv_path(args.mac, outdir=args.outdir)


def _stamp_rows(rows, args, newest_utc, newest_index):
    if args.no_timestamps or not rows:
        return list(rows)
    return apply_inferred_timestamps(
        rows,
        newest_utc=newest_utc,
        interval_sec=args.interval_sec,
        newest_index=newest_index,
    )


async def fetch_history_pages(
    write_and_wait,
    sample_count: int,
    max_pages: Optional[int] = None,
    retries: int = 2,
    on_progress: Optional[Callable[[int, int, History07], None]] = None,
) -> List[History07]:
    """Alle 07-Pages gemäß page_plan. write_and_wait(payload) → 20-Byte-Notify oder None."""
    plan = page_plan(sample_count)
    if max_pages is not None:
        plan = plan[: max_pages]
    pages = []  # type: List[History07]
    total = len(plan)
    for step, (index, count) in enumerate(plan, start=1):
        payload = build_history_07_write(index, count)
        assert_allowed_fff5_write(payload)
        parsed = None  # type: Optional[History07]
        for _attempt in range(retries + 1):
            raw = await write_and_wait(payload)
            if raw is None:
                continue
            cand = parse_fff3(raw)
            if isinstance(cand, History07):
                parsed = cand
                break
        if parsed is None:
            raise RuntimeError(
                "History-Page index={} count={} ohne gültiges Notify".format(index, count)
            )
        pages.append(parsed)
        if on_progress is not None:
            on_progress(step, total, parsed)
    return pages


def dump_from_extract(args: argparse.Namespace) -> int:
    rows, meta = load_extract_history(
        args.from_extract,
        mac=args.mac,
        skip_old=not args.include_old,
    )
    if not rows:
        print(
            "Keine 07-Pages für {} in {}.".format(
                normalize_mac(args.mac), meta.get("att_path") or args.from_extract
            ),
            file=sys.stderr,
        )
        return 1
    newest_utc = args.newest_time or meta.get("last_ts") or iso_utc_now()
    newest_index = meta.get("newest_index")
    if newest_index is None:
        newest_index = rows[-1]["index"]
    rows = _stamp_rows(rows, args, newest_utc, newest_index)
    path = resolve_csv_path(args)
    write_history_csv(path, rows)
    print(
        "Extract {}  pages={}  samples={}  count_01={}  newest_index={}".format(
            meta.get("file"),
            meta.get("page_count"),
            len(rows),
            meta.get("count_01"),
            newest_index,
        )
    )
    print("geschrieben: {}".format(path))
    if not args.no_timestamps:
        print(
            "timestamp_inferred: Anker {}  interval={} s (Hypothese)".format(
                rows[-1]["timestamp_inferred"] or newest_utc,
                args.interval_sec,
            )
        )
    return 0


def _progress(step: int, total: int, parsed: History07) -> None:
    if step == 1 or step == total or step % 25 == 0:
        print(
            "  Page {}/{}  index={}  count={}  records={}".format(
                step, total, parsed.index, parsed.count, len(parsed.records)
            )
        )


async def dump_via_gatt(args: argparse.Namespace, device_address: str, address_was_given: bool) -> int:
    from bleak import BleakClient

    import read_thermometer_data as probe

    print("Verbinde mit {} ...".format(device_address))
    async with BleakClient(device_address, timeout=20.0) as client:
        print("Verbunden.")
        sid = await probe._read_system_id(client)
        target_sid = probe._sid_bytes(TARGET_SYSTEM_ID)
        if sid is None:
            if address_was_given or probe._macs_equal(device_address, TARGET_MAC):
                print("System ID nicht lesbar; fahre mit gegebener Adresse fort.")
            else:
                print("System ID nicht lesbar und Adresse ist nicht TARGET_MAC — Abbruch.")
                return 1
        elif sid != target_sid:
            print(
                "System ID {} != Ziel {} — falsches Gerät, Abbruch.".format(
                    probe._hex(sid), probe._hex(target_sid)
                )
            )
            return 1
        else:
            print("System ID ok: {}".format(probe._hex(sid)))

        if probe._find_char(client, CONTROL_CHAR_UUID) is None:
            print("FFF5 (Control) nicht gefunden.")
            return 1
        if probe._find_char(client, DATA_CHAR_UUID) is None:
            print("FFF3 (Data) nicht gefunden.")
            return 1
        if not any(probe._uuid_eq(s.uuid, SERVICE_UUID) for s in client.services):
            print("Service FFE0 nicht gefunden.")
            return 1

        queue = asyncio.Queue()

        def _on_notify(_sender, data):
            queue.put_nowait(bytes(data))

        await probe.enable_notify(client, _on_notify)

        async def write_and_wait(payload: bytes):
            assert_allowed_fff5_write(payload)
            probe._drain(queue)
            await client.write_gatt_char(CONTROL_CHAR_UUID, payload, response=True)
            return await probe.wait_notify(
                queue, payload[0], timeout=args.notify_timeout
            )

        print("Sequenz 1A → 01 → 07-Pages")
        assert_allowed_fff5_write(bytes([0x1A]))
        raw_1a = await write_and_wait(bytes([0x1A]))
        if raw_1a is None:
            print("Timeout auf 1A.", file=sys.stderr)
            return 1
        print("  Status 1A  raw={}".format(raw_1a.hex()))

        assert_allowed_fff5_write(bytes([0x01]))
        raw_01 = await write_and_wait(bytes([0x01]))
        if raw_01 is None:
            print("Timeout auf 01.", file=sys.stderr)
            return 1
        parsed_01 = parse_fff3(raw_01)
        if not isinstance(parsed_01, Count01):
            print("Antwort auf 01 ist kein Count01: {}".format(raw_01.hex()), file=sys.stderr)
            return 1
        sample_count = parsed_01.sample_count
        plan = page_plan(sample_count)
        if args.max_pages is not None:
            plan = plan[: args.max_pages]
        print(
            "  Count 01   samples={}  pages={}  (~{:.0f} s bei 0,2 s/Page)".format(
                sample_count, len(plan), len(plan) * 0.2
            )
        )

        t0 = time.monotonic()
        pages = []
        try:
            pages = await fetch_history_pages(
                write_and_wait,
                sample_count,
                max_pages=args.max_pages,
                retries=args.retries,
                on_progress=_progress,
            )
        except KeyboardInterrupt:
            print("\nAbbruch während der Pages — schreibe {} bisherige Pages.".format(len(pages)))
        finally:
            try:
                await client.stop_notify(DATA_CHAR_UUID)
            except Exception:
                pass

        elapsed = time.monotonic() - t0
        rows = samples_from_pages(pages, args.mac)
        newest_utc = args.newest_time or iso_utc_now()
        newest_index = sample_count - 1 if sample_count else None
        rows = _stamp_rows(rows, args, newest_utc, newest_index)
        path = resolve_csv_path(args)
        write_history_csv(path, rows)
        print(
            "fertig: {} Samples aus {} Pages in {:.1f} s".format(
                len(rows), len(pages), elapsed
            )
        )
        print("geschrieben: {}".format(path))
        if rows and not args.no_timestamps:
            print(
                "timestamp_inferred: Anker {}  interval={} s (Hypothese)".format(
                    rows[-1].get("timestamp_inferred") or newest_utc,
                    args.interval_sec,
                )
            )
        if sample_count and len(rows) < sample_count:
            print(
                "Hinweis: CSV hat {} von {} Samples (--max-pages?).".format(
                    len(rows), sample_count
                ),
                file=sys.stderr,
            )
        return 0


async def async_main(args: argparse.Namespace) -> int:
    if args.from_extract:
        return dump_from_extract(args)

    import read_thermometer_data as probe

    if args.address:
        address = args.address
        given = True
    else:
        address = await probe.find_device_by_system_id()
        given = False
        if not address:
            print("Tipp: --address {} setzen.".format(TARGET_MAC))
            return 1
    return await dump_via_gatt(args, address, given)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.from_extract:
            return dump_from_extract(args)
        return asyncio.run(async_main(args))
    except KeyboardInterrupt:
        print("\nAbbruch.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
