#!/usr/bin/env python3
"""History-Dump ohne BLE: Pages, CSV, Extract-Import, Zeit-Hypothese.

App-Sequenz und Framing: hci-logs/05-history-07.md, hci-logs/10-history-dump.md.
Nur Opcodes 1A / 01 / 07. Intervall 600 s ist Hypothese, kein Fakt.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from thermo_parse import (
    Count01,
    History07,
    TARGET_MAC,
    parse_fff3,
)

HISTORY_COLUMNS = (
    "mac",
    "index",
    "record",
    "temp_c",
    "humidity_rh",
    "raw_hex",
    "timestamp_inferred",
)

PAGE_RECORDS = 3
# Hypothese: ADV-Counter 949579 / Count 1583 ≈ 599,86 s → 10 min.
# 100-Tage-Angabe des Herstellers: bei 10 min ≈ 14400 Samples (nicht in Captures gesehen).
INTERVAL_SEC_HYPOTHESIS = 600.0
ALLOWED_WRITE_OPCODES = (0x1A, 0x01, 0x07)
BLACKLIST_WRITE_OPCODES = (0x04, 0x05, 0x0F, 0x18, 0x19, 0xF3)
EXTRACT_ATT_NAME = "att_fff5_fff3.csv"


def mac12(mac: str) -> str:
    return mac.replace(":", "").replace("-", "").replace(".", "").lower()


def normalize_mac(mac: str) -> str:
    compact = mac12(mac)
    if len(compact) == 12 and all(c in "0123456789abcdef" for c in compact):
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    return (mac or "").strip().lower()


def default_history_csv_path(mac: str, outdir: str = "data") -> str:
    """Pfad data/history_<mac12>.csv (eine Datei pro Gerät, Dump ersetzt sie)."""
    return os.path.join(outdir, "history_{}.csv".format(mac12(mac)))


def page_plan(sample_count: int) -> List[Tuple[int, int]]:
    """Write-Plan wie die App: count=03 in 3er-Schritten, Rest als count=01.

    Niemals count=02 — in den Captures kommt das nicht vor
    (1586 Samples = 528×03 + 2×01).
    """
    if sample_count < 0:
        raise ValueError("sample_count muss >= 0 sein")
    full, rem = divmod(int(sample_count), PAGE_RECORDS)
    pages = []  # type: List[Tuple[int, int]]
    for i in range(full):
        pages.append((i * PAGE_RECORDS, PAGE_RECORDS))
    for extra in range(rem):
        pages.append((full * PAGE_RECORDS + extra, 1))
    return pages


def page_plan_since(sample_count: int, after_index: int) -> List[Tuple[int, int]]:
    """page_plan ab der ersten Page, die Indizes > after_index enthält.

    Überlappende Page wird mitgeholt (Merge überschreibt). after_index=-1 = alles.
    """
    if after_index < -1:
        after_index = -1
    return [
        (index, count)
        for index, count in page_plan(sample_count)
        if index + count - 1 > after_index
    ]


def default_sync_state_path(mac: str, outdir: str = "data") -> str:
    """Pfad data/sync_<mac12>.json (letzter History-Abruf)."""
    return os.path.join(outdir, "sync_{}.json".format(mac12(mac)))


def load_sync_state(path: str) -> Optional[dict]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        return None
    return raw


def write_sync_state(path: str, state: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def _row_index(row: dict) -> Optional[int]:
    raw = row.get("index")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def read_history_csv(path: str) -> List[dict]:
    """Bestehende History-CSV lesen. Fehlende Datei → []."""
    if not path or not os.path.isfile(path):
        return []
    rows = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            index = _row_index(row)
            if index is None:
                continue
            try:
                record = int(row.get("record") or 0)
                temp_c = float(row.get("temp_c"))
                humidity_rh = float(row.get("humidity_rh"))
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "mac": normalize_mac(row.get("mac") or ""),
                    "index": index,
                    "record": record,
                    "temp_c": temp_c,
                    "humidity_rh": humidity_rh,
                    "raw_hex": (row.get("raw_hex") or "").replace(" ", "").lower(),
                    "timestamp_inferred": (row.get("timestamp_inferred") or "").strip(),
                }
            )
    rows.sort(key=lambda item: (item["index"], item["record"]))
    return rows


def max_history_index(rows: Sequence[dict]) -> Optional[int]:
    indices = [_row_index(row) for row in rows]
    present = [i for i in indices if i is not None]
    if not present:
        return None
    return max(present)


def merge_history_rows(existing: Sequence[dict], incoming: Sequence[dict]) -> List[dict]:
    """Nach index mergen; incoming gewinnt. Sortiert nach index."""
    by_index = {}  # type: Dict[int, dict]
    for row in existing:
        index = _row_index(row)
        if index is None:
            continue
        by_index[index] = dict(row)
        by_index[index]["index"] = index
    for row in incoming:
        index = _row_index(row)
        if index is None:
            continue
        item = dict(row)
        item["index"] = index
        by_index[index] = item
    return [by_index[key] for key in sorted(by_index)]


def apply_incremental_history(
    existing: Sequence[dict],
    incoming: Sequence[dict],
    sample_count: int,
    newest_utc: str,
    interval_sec: float = INTERVAL_SEC_HYPOTHESIS,
) -> List[dict]:
    """Merge + Zeitanker. Count-Rückgang (Gerät-Reset) ersetzt die alte CSV."""
    count = int(sample_count)
    last = max_history_index(existing)
    if last is not None and count < last + 1:
        merged = [dict(row) for row in incoming]
    else:
        merged = merge_history_rows(existing, incoming)
    if not merged:
        return []
    newest_index = count - 1 if count > 0 else max_history_index(merged)
    return apply_inferred_timestamps(
        merged,
        newest_utc=newest_utc,
        interval_sec=interval_sec,
        newest_index=newest_index,
    )


def assert_allowed_fff5_write(payload: bytes) -> None:
    """Nur beobachtete App-Writes: 1A, 01, oder 07 mit 6 Byte und count 01/03."""
    if not payload:
        raise ValueError("leerer FFF5-Write")
    opcode = payload[0]
    if opcode in BLACKLIST_WRITE_OPCODES:
        raise ValueError("Blacklist-Opcode 0x{:02X} — nicht senden".format(opcode))
    if opcode not in ALLOWED_WRITE_OPCODES:
        raise ValueError("unbeobachteter Opcode 0x{:02X}".format(opcode))
    if opcode == 0x07:
        if len(payload) != 6:
            raise ValueError("07-Write muss 6 Byte sein, nicht {}".format(len(payload)))
        if payload[3:5] != b"\x00\x00":
            raise ValueError("07-Write Bytes 3–4 müssen 00 00 sein")
        if payload[5] not in (1, 3):
            raise ValueError("07-Write count nur 01 oder 03, nicht {}".format(payload[5]))
    elif len(payload) != 1:
        raise ValueError("Opcode 0x{:02X} nur als 1-Byte-Write".format(opcode))


def samples_from_page(parsed: History07, mac: str) -> List[dict]:
    """Eine 07-Page → eine Zeile pro Record. index = Page-Index + Record."""
    rows = []
    raw_hex = (parsed.raw_hex or "").replace(" ", "").lower()
    mac_n = normalize_mac(mac)
    for rec_i, pair in enumerate(parsed.records):
        temp_c, humidity_rh = pair
        rows.append(
            {
                "mac": mac_n,
                "index": int(parsed.index) + rec_i,
                "record": rec_i,
                "temp_c": float(temp_c),
                "humidity_rh": float(humidity_rh),
                "raw_hex": raw_hex,
                "timestamp_inferred": "",
            }
        )
    return rows


def samples_from_pages(pages: Iterable[History07], mac: str) -> List[dict]:
    rows = []
    for page in pages:
        rows.extend(samples_from_page(page, mac))
    rows.sort(key=lambda item: (item["index"], item["record"]))
    return rows


def parse_iso_utc(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise ValueError("leerer Zeitstempel")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_inferred_timestamps(
    rows: Sequence[dict],
    newest_utc: str,
    interval_sec: float = INTERVAL_SEC_HYPOTHESIS,
    newest_index: Optional[int] = None,
) -> List[dict]:
    """timestamp_inferred: neuestes Sample ≈ newest_utc, ältere um interval_sec versetzt.

    Hypothese, keine Geräte-Wanduhr. newest_index = Count-1 (nicht max der Teilmenge),
    sonst bekäme ein Dump ab Index 0 falsche „kurze“ Zeiten.
    """
    if interval_sec <= 0:
        raise ValueError("interval_sec muss > 0 sein")
    if not rows:
        return []
    newest = parse_iso_utc(newest_utc)
    if newest_index is None:
        newest_index = max(int(row["index"]) for row in rows)
    out = []
    for row in rows:
        item = dict(row)
        delta = (int(newest_index) - int(item["index"])) * float(interval_sec)
        item["timestamp_inferred"] = format_iso_utc(newest - timedelta(seconds=delta))
        out.append(item)
    return out


def interval_from_count_and_counter(sample_count: int, adv_counter: int) -> Optional[float]:
    """ADV-Counter / Count → Sekunden/Sample. Hypothese, siehe 10-history-dump.md."""
    if sample_count <= 0 or adv_counter <= 0:
        return None
    return float(adv_counter) / float(sample_count)


def write_history_csv(path: str, rows: Sequence[dict]) -> None:
    """Dump komplett schreiben (überschreibt). Header immer HISTORY_COLUMNS."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(HISTORY_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "mac": row.get("mac", ""),
                    "index": row.get("index", ""),
                    "record": row.get("record", ""),
                    "temp_c": row.get("temp_c", ""),
                    "humidity_rh": row.get("humidity_rh", ""),
                    "raw_hex": (row.get("raw_hex") or "").replace(" ", "").lower(),
                    "timestamp_inferred": row.get("timestamp_inferred") or "",
                }
            )


def _hex_bytes(value: str) -> bytes:
    return bytes.fromhex(value.replace(" ", "").replace(":", "").strip())


def _extract_file_is_old(file_name: str) -> bool:
    name = (file_name or "").replace("\\", "/")
    return name.startswith("old/") or "/old/" in name


def resolve_extract_att_path(path: str) -> str:
    if os.path.isdir(path):
        return os.path.join(path, EXTRACT_ATT_NAME)
    return path


def load_extract_history(
    path: str,
    mac: str = TARGET_MAC,
    skip_old: bool = True,
) -> Tuple[List[dict], dict]:
    """FFF3-Notify 0x07 aus att_fff5_fff3.csv. Längster Capture-Dump (nicht old/).

    Nimmt die Datei mit den meisten Samples, nicht den Merge über Sessions
    (Count steigt zwischen Captures).
    """
    att_path = resolve_extract_att_path(path)
    if not os.path.isfile(att_path):
        raise FileNotFoundError(att_path)
    mac_n = normalize_mac(mac)
    by_file = {}  # type: Dict[str, dict]
    with open(att_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            file_name = row.get("file") or ""
            if skip_old and _extract_file_is_old(file_name):
                continue
            peer = normalize_mac(row.get("peer") or "")
            if peer != mac_n:
                continue
            if (row.get("kind") or "") != "FFF3-Notify":
                continue
            try:
                raw = _hex_bytes(row.get("value_hex") or "")
            except ValueError:
                continue
            parsed = parse_fff3(raw)
            bucket = by_file.setdefault(
                file_name,
                {"pages": {}, "counts": [], "first_ts": None, "last_ts": None},
            )
            ts = (row.get("timestamp") or "").strip() or None
            if isinstance(parsed, History07):
                if parsed.index not in bucket["pages"]:
                    bucket["pages"][parsed.index] = parsed
                if bucket["first_ts"] is None:
                    bucket["first_ts"] = ts
                bucket["last_ts"] = ts
            elif isinstance(parsed, Count01):
                bucket["counts"].append(int(parsed.sample_count))
                if ts:
                    bucket["last_ts"] = bucket["last_ts"] or ts

    if not by_file:
        return [], {
            "file": None,
            "sample_count": 0,
            "page_count": 0,
            "count_01": None,
            "first_ts": None,
            "last_ts": None,
            "att_path": att_path,
        }

    def _score(item):
        fn, bucket = item
        n_samples = sum(len(p.records) for p in bucket["pages"].values())
        n_pages = len(bucket["pages"])
        return (n_samples, n_pages, fn)

    file_name, bucket = max(by_file.items(), key=_score)
    pages = [bucket["pages"][idx] for idx in sorted(bucket["pages"])]
    rows = samples_from_pages(pages, mac_n)
    count_01 = bucket["counts"][-1] if bucket["counts"] else None
    meta = {
        "file": file_name,
        "sample_count": len(rows),
        "page_count": len(pages),
        "count_01": count_01,
        "first_ts": bucket["first_ts"],
        "last_ts": bucket["last_ts"],
        "att_path": att_path,
        "newest_index": (count_01 - 1) if count_01 else (rows[-1]["index"] if rows else None),
    }
    return rows, meta
