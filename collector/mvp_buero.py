#!/usr/bin/env python3
"""Büro-MVP schließen: Live-CSV, GATT-Dump, History vs. ADV, Intervall-Beleg.

Feldlauf am Gerät f4:db:00:00:00:d9. Kein 0x18/0x04. Vergleich und
Evidence-Datei sind ohne BLE testbar.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from thermo_parse import TARGET_MAC, AdvLive  # noqa: E402
from thermo_store import iso_utc_now  # noqa: E402

DEFAULT_EVIDENCE_PATH = os.path.join(
    os.path.dirname(_HERE), "data", "interval_evidence.jsonl"
)
TEMP_TOL_C = 2.0
HUM_TOL = 5.0


def parse_iso_utc(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def newest_history_row(rows: Sequence[dict]) -> Optional[dict]:
    indexed = [row for row in rows if row.get("index") not in (None, "")]
    if not indexed:
        return rows[-1] if rows else None

    def key(row: dict) -> int:
        try:
            return int(row["index"])
        except (TypeError, ValueError):
            return -1

    return max(indexed, key=key)


def compare_live_to_newest_history(
    live: AdvLive,
    rows: Sequence[dict],
    temp_tol: float = TEMP_TOL_C,
    hum_tol: float = HUM_TOL,
) -> dict:
    """Neueste History-Page gegen Live-ADV. Temp ≈ Display /16."""
    newest = newest_history_row(rows)
    if newest is None:
        return {
            "ok": False,
            "reason": "keine History-Zeilen",
            "live_temp_c": live.temp_c,
            "live_humidity_rh": live.humidity_rh,
        }
    hist_temp = float(newest["temp_c"])
    hist_hum = float(newest["humidity_rh"])
    temp_delta = abs(live.temp_c - hist_temp)
    hum_delta = abs(live.humidity_rh - hist_hum)
    ok = temp_delta <= temp_tol
    try:
        hist_index = int(newest["index"])
    except (TypeError, ValueError, KeyError):
        hist_index = newest.get("index")
    return {
        "ok": ok,
        "live_temp_c": live.temp_c,
        "live_humidity_rh": live.humidity_rh,
        "live_counter": live.counter,
        "history_index": hist_index,
        "history_temp_c": hist_temp,
        "history_humidity_rh": hist_hum,
        "temp_delta_c": temp_delta,
        "hum_delta": hum_delta,
        "temp_tol_c": temp_tol,
        "hum_tol": hum_tol,
        "hum_ok": hum_delta <= hum_tol,
        "mac": live.mac,
    }


def append_evidence(path: str, record: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_evidence(path: str) -> List[dict]:
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def infer_interval_sec(records: Sequence[dict], mac: str = TARGET_MAC) -> Optional[dict]:
    """Zwei Count-01-/Zeitpunkte → Sekunden je Sample. Hypothese 600 s."""
    wanted = mac.replace(":", "").lower()
    points = []
    for rec in records:
        rec_mac = str(rec.get("mac") or "").replace(":", "").lower()
        if rec_mac and rec_mac != wanted:
            continue
        count = rec.get("sample_count")
        ts = rec.get("recorded_at")
        if count in (None, "") or not ts:
            continue
        try:
            points.append((parse_iso_utc(str(ts)), int(count)))
        except (TypeError, ValueError):
            continue
    if len(points) < 2:
        return None
    points.sort(key=lambda item: item[0])
    t0, c0 = points[0]
    t1, c1 = points[-1]
    dc = c1 - c0
    dt = (t1 - t0).total_seconds()
    if dc == 0 or dt <= 0:
        return {
            "ok": False,
            "reason": "Count oder Zeit unverändert",
            "count_0": c0,
            "count_1": c1,
            "dt_sec": dt,
        }
    interval = dt / float(dc)
    return {
        "ok": True,
        "count_0": c0,
        "count_1": c1,
        "dt_sec": dt,
        "interval_sec": interval,
        "hypothesis_sec": 600.0,
        "close_to_10min": abs(interval - 600.0) <= 90.0,
    }


def format_compare(cmp: dict) -> str:
    if not cmp.get("history_temp_c") and not cmp.get("ok"):
        return "Vergleich: {0}".format(cmp.get("reason") or "fehlgeschlagen")
    flag = "ok" if cmp.get("ok") else "abweichung"
    return (
        "Vergleich History vs. ADV ({flag}): "
        "live {live:.4f} °C / hist {hist:.4f} °C  Δ={delta:.4f} "
        "(Toleranz {tol} °C); Hum Δ={hum:.2f}".format(
            flag=flag,
            live=float(cmp.get("live_temp_c") or 0),
            hist=float(cmp.get("history_temp_c") or 0),
            delta=float(cmp.get("temp_delta_c") or 0),
            tol=float(cmp.get("temp_tol_c") or TEMP_TOL_C),
            hum=float(cmp.get("hum_delta") or 0),
        )
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Büro-MVP: collect.py + dump_history.py, History gegen ADV, "
            "Intervall-Beleg (Count 01 + Uhr). Nicht senden: 04 / 18."
        )
    )
    parser.add_argument(
        "--address",
        default=TARGET_MAC,
        help="BLE-Adresse (Standard: Büro-MAC)",
    )
    parser.add_argument(
        "--mac",
        default=TARGET_MAC,
        help="Payload-MAC / CSV-MAC (Standard: Büro)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="ADV-Scan-Timeout (Standard: 15)",
    )
    parser.add_argument(
        "--outdir",
        default="data",
        help="CSV-Verzeichnis (Standard: data)",
    )
    parser.add_argument(
        "--evidence",
        default=DEFAULT_EVIDENCE_PATH,
        metavar="PATH",
        help="JSONL für Count+Uhr (Standard: data/interval_evidence.jsonl)",
    )
    parser.add_argument(
        "--from-extract",
        default=None,
        metavar="PATH",
        help="History aus HCI-Extract statt GATT (kein Live-Dump)",
    )
    parser.add_argument(
        "--skip-collect",
        action="store_true",
        help="kein ADV-Scan (nur Dump/Extract + Evidence)",
    )
    parser.add_argument(
        "--skip-dump",
        action="store_true",
        help="kein History-Dump (nur Live-CSV + Evidence ohne Count)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        metavar="N",
        help="an dump_history durchreichen (Test)",
    )
    parser.add_argument(
        "--notify-timeout",
        type=float,
        default=2.0,
        help="GATT-Notify-Timeout je Page",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein")
    if args.skip_collect and args.skip_dump and not args.from_extract:
        parser.error("nichts zu tun (--skip-collect und --skip-dump)")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    live = None  # type: Optional[AdvLive]
    sample_count = None  # type: Optional[int]
    history_rows = []  # type: List[dict]

    if not args.skip_collect:
        from scan_live import scan_live
        import collect as collect_mod

        print("== 1. Live-CSV (ADV) ==")
        live = asyncio.run(
            scan_live(
                timeout=args.timeout,
                address=args.address,
                allowed_macs=[args.mac],
            )
        )
        if live is None:
            print(
                "Kein Live-Sample innerhalb von {0} s (Ziel-MAC {1}).".format(
                    args.timeout, args.mac
                ),
                file=sys.stderr,
            )
            return 1
        path = collect_mod.resolve_csv_path(
            collect_mod.parse_args(
                ["--once", "--outdir", args.outdir, "--mac", args.mac]
            ),
            live.mac,
        )
        collect_mod.write_sample(path, live)
        collect_mod._report_hit(path, live)

    if not args.skip_dump or args.from_extract:
        import dump_history

        print("== 2. History-Dump ==")
        dump_argv = ["--mac", args.mac, "--outdir", args.outdir]
        if args.from_extract:
            dump_argv.extend(["--from-extract", args.from_extract])
        else:
            dump_argv.extend(["--address", args.address])
            dump_argv.extend(["--notify-timeout", str(args.notify_timeout)])
            if args.max_pages is not None:
                dump_argv.extend(["--max-pages", str(args.max_pages)])
        rc = dump_history.main(dump_argv)
        if rc != 0:
            return rc
            from thermo_history import default_history_csv_path
        import csv

        hist_path = default_history_csv_path(args.mac, outdir=args.outdir)
        if os.path.isfile(hist_path):
            with open(hist_path, newline="", encoding="utf-8") as handle:
                history_rows = list(csv.DictReader(handle))
            if history_rows:
                try:
                    sample_count = max(int(r["index"]) for r in history_rows) + 1
                except (TypeError, ValueError, KeyError):
                    sample_count = len(history_rows)

    cmp = None
    if live is not None and history_rows:
        print("== 3. History vs. ADV ==")
        cmp = compare_live_to_newest_history(live, history_rows)
        print(format_compare(cmp))
        if not cmp.get("ok"):
            print(
                "Hinweis: Dump-Zeit vs. Live kann bei 10-min-Takt abweichen.",
                file=sys.stderr,
            )

    record = {
        "recorded_at": iso_utc_now(),
        "mac": args.mac,
        "sample_count": sample_count,
        "adv_counter": None if live is None else live.counter,
        "temp_c": None if live is None else live.temp_c,
        "humidity_rh": None if live is None else live.humidity_rh,
    }
    if cmp:
        record["history_newest_index"] = cmp.get("history_index")
        record["history_newest_temp_c"] = cmp.get("history_temp_c")
        record["temp_delta_c"] = cmp.get("temp_delta_c")
    append_evidence(args.evidence, record)
    print("Evidence: {0}".format(args.evidence))

    evidence = load_evidence(args.evidence)
    inferred = infer_interval_sec(evidence, mac=args.mac)
    if inferred is None:
        print(
            "Intervall: zweiter Lauf (Count 01 + Uhr) nötig, "
            "damit die 10-min-Hypothese prüfbar ist."
        )
    elif inferred.get("ok"):
        close = "≈ 10 min" if inferred.get("close_to_10min") else "weicht von 600 s ab"
        print(
            "Intervall aus {0}→{1} Counts in {2:.0f} s → {3:.1f} s/Sample ({4}).".format(
                inferred["count_0"],
                inferred["count_1"],
                inferred["dt_sec"],
                inferred["interval_sec"],
                close,
            )
        )
    else:
        print("Intervall: {0}".format(inferred.get("reason")))

    print("Nicht senden: 0x18 / 0x04.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
