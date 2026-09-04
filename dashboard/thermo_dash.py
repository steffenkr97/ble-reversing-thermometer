#!/usr/bin/env python3
"""Dashboard-Datenlage: Live-CSV, History-CSV, HCI-Extracts (nur Lesen)."""
from __future__ import annotations

import csv
import json
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_COLLECTOR = os.path.join(_ROOT, "collector")

import sys

if _COLLECTOR not in sys.path:
    sys.path.insert(0, _COLLECTOR)

from thermo_parse import History07, parse_adv_manufacturer, parse_fff3  # noqa: E402
from thermo_store import COLUMNS  # noqa: E402

SOURCE_ADV = "adv"
SOURCE_HISTORY = "history"
SOURCE_ADV_CAPTURE = "adv_capture"
SOURCE_HISTORY_CAPTURE = "history_capture"
KNOWN_SOURCES = (
    SOURCE_ADV,
    SOURCE_HISTORY,
    SOURCE_ADV_CAPTURE,
    SOURCE_HISTORY_CAPTURE,
)

LIVE_CSV_RE = re.compile(r"^thermo_([0-9a-f]{12})_(\d{4}-\d{2}-\d{2})\.csv$")
HISTORY_CSV_RE = re.compile(r"^history_([0-9a-f]{12})\.csv$")

DEFAULT_ROOMS_PATH = os.path.join(_HERE, "rooms.json")
DEFAULT_DATA_DIR = os.path.join(_ROOT, "data")
DEFAULT_EXTRACT_DIR = os.path.join(_ROOT, "hci-logs", "extract")


def mac12(mac: str) -> str:
    return mac.replace(":", "").replace("-", "").replace(".", "").lower()


def normalize_mac(mac: str) -> str:
    compact = mac12(mac)
    if len(compact) == 12 and all(c in "0123456789abcdef" for c in compact):
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    return mac.strip().lower()


def _hex_bytes(value: str) -> bytes:
    return bytes.fromhex(value.replace(" ", "").replace(":", "").strip())


def _extract_file_is_old(file_name: str) -> bool:
    """old/*.cfa haben oft Geräteuhr 2018 — Zeitachse sonst unbrauchbar."""
    name = (file_name or "").replace("\\", "/")
    return name.startswith("old/") or "/old/" in name


def load_rooms(path: str = DEFAULT_ROOMS_PATH) -> List[dict]:
    """Allowlist aus rooms.json. Nur bestätigte eigene Geräte."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    rooms = []
    for raw in payload.get("rooms") or []:
        mac = normalize_mac(str(raw.get("mac") or ""))
        name = str(raw.get("name") or "").strip()
        room_id = str(raw.get("id") or mac12(mac))
        if not mac or not name:
            continue
        rooms.append(
            {
                "id": room_id,
                "name": name,
                "mac": mac,
                "confirmed": bool(raw.get("confirmed", True)),
            }
        )
    return rooms


def room_by_mac(rooms: Sequence[dict], mac: str) -> Optional[dict]:
    target = normalize_mac(mac)
    for room in rooms:
        if room["mac"] == target:
            return room
    return None


def allowlist_macs(rooms: Sequence[dict]) -> List[str]:
    return [room["mac"] for room in rooms]


def _sample(
    timestamp,
    mac,
    temp_c,
    humidity_rh,
    source,
    raw_hex="",
    index=None,
    record=None,
    room=None,
    file_name=None,
) -> dict:
    return {
        "timestamp": timestamp,
        "mac": normalize_mac(mac),
        "temp_c": float(temp_c),
        "humidity_rh": float(humidity_rh),
        "source": source,
        "raw_hex": (raw_hex or "").replace(" ", "").lower(),
        "index": index,
        "record": record,
        "room": room,
        "file": file_name,
    }


def _attach_room(sample: dict, rooms: Sequence[dict]) -> dict:
    found = room_by_mac(rooms, sample["mac"])
    if found:
        sample["room"] = found["name"]
        sample["room_id"] = found["id"]
    else:
        sample["room"] = None
        sample["room_id"] = None
    return sample


def _parse_float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_live_csv(path: str, rooms: Sequence[dict]) -> List[dict]:
    """Collector-CSV: timestamp, mac, temp_c, humidity_rh, raw_hex."""
    allowed = set(allowlist_macs(rooms))
    samples = []
    file_name = os.path.basename(path)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        fields = [name.strip() for name in reader.fieldnames]
        if set(COLUMNS) - set(fields):
            return []
        for row in reader:
            mac = normalize_mac(row.get("mac") or "")
            if allowed and mac not in allowed:
                continue
            temp_c = _parse_float(row.get("temp_c"))
            humidity_rh = _parse_float(row.get("humidity_rh"))
            ts = (row.get("timestamp") or "").strip() or None
            if temp_c is None or humidity_rh is None:
                continue
            samples.append(
                _attach_room(
                    _sample(
                        ts,
                        mac,
                        temp_c,
                        humidity_rh,
                        SOURCE_ADV,
                        row.get("raw_hex") or "",
                        file_name=file_name,
                    ),
                    rooms,
                )
            )
    return samples


def read_history_csv(path: str, rooms: Sequence[dict]) -> List[dict]:
    """History-Dump CSV (Phase 6): mac, index, record, temp_c, humidity_rh, raw_hex."""
    allowed = set(allowlist_macs(rooms))
    samples = []
    file_name = os.path.basename(path)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        for row in reader:
            mac = normalize_mac(row.get("mac") or "")
            if allowed and mac not in allowed:
                continue
            temp_c = _parse_float(row.get("temp_c"))
            humidity_rh = _parse_float(row.get("humidity_rh"))
            if temp_c is None or humidity_rh is None:
                continue
            index = row.get("index")
            record = row.get("record")
            try:
                index_i = int(index) if index not in (None, "") else None
            except ValueError:
                index_i = None
            try:
                record_i = int(record) if record not in (None, "") else None
            except ValueError:
                record_i = None
            ts = (row.get("timestamp_inferred") or row.get("timestamp") or "").strip() or None
            samples.append(
                _attach_room(
                    _sample(
                        ts,
                        mac,
                        temp_c,
                        humidity_rh,
                        SOURCE_HISTORY,
                        row.get("raw_hex") or "",
                        index=index_i,
                        record=record_i,
                        file_name=file_name,
                    ),
                    rooms,
                )
            )
    return samples


def list_data_csvs(data_dir: str) -> Tuple[List[str], List[str]]:
    live = []
    history = []
    if not os.path.isdir(data_dir):
        return live, history
    for name in sorted(os.listdir(data_dir)):
        path = os.path.join(data_dir, name)
        if not os.path.isfile(path):
            continue
        if LIVE_CSV_RE.match(name):
            live.append(path)
        elif HISTORY_CSV_RE.match(name):
            history.append(path)
    return live, history


def load_live_and_history(data_dir: str, rooms: Sequence[dict]) -> List[dict]:
    samples = []
    live_paths, history_paths = list_data_csvs(data_dir)
    for path in live_paths:
        samples.extend(read_live_csv(path, rooms))
    for path in history_paths:
        samples.extend(read_history_csv(path, rooms))
    return samples


def read_extract_adv(path: str, rooms: Sequence[dict]) -> List[dict]:
    """HCI-Extract ADV_IND, nur Allowlist. parse_adv_manufacturer filtert Büro-MAC."""
    if not os.path.isfile(path):
        return []
    allowed = set(allowlist_macs(rooms))
    samples = []
    file_name = os.path.basename(path)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if _extract_file_is_old(row.get("file") or ""):
                continue
            if (row.get("event") or "") != "ADV_IND":
                continue
            mac = normalize_mac(row.get("mac") or "")
            if allowed and mac not in allowed:
                continue
            mfg = (row.get("mfg_hex") or "").strip()
            if not mfg:
                continue
            try:
                frame = _hex_bytes(mfg)
            except ValueError:
                continue
            parsed = parse_adv_manufacturer(frame)
            if parsed is None:
                continue
            if allowed and parsed.mac not in allowed:
                continue
            samples.append(
                _attach_room(
                    _sample(
                        (row.get("timestamp") or "").strip() or None,
                        parsed.mac,
                        parsed.temp_c,
                        parsed.humidity_rh,
                        SOURCE_ADV_CAPTURE,
                        parsed.raw_hex,
                        file_name=file_name,
                    ),
                    rooms,
                )
            )
    return samples


def read_extract_history(path: str, rooms: Sequence[dict]) -> List[dict]:
    """HCI-Extract FFF3-Notify 0x07, nur Allowlist. Index 0 = älteste."""
    if not os.path.isfile(path):
        return []
    allowed = set(allowlist_macs(rooms))
    samples = []
    file_name = os.path.basename(path)
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if _extract_file_is_old(row.get("file") or ""):
                continue
            if (row.get("kind") or "") != "FFF3-Notify":
                continue
            if (row.get("opcode_byte") or "").lower() != "0x07":
                continue
            mac = normalize_mac(row.get("peer") or "")
            if allowed and mac not in allowed:
                continue
            try:
                raw = _hex_bytes(row.get("value_hex") or "")
            except ValueError:
                continue
            parsed = parse_fff3(raw)
            if not isinstance(parsed, History07):
                continue
            capture_ts = (row.get("timestamp") or "").strip() or None
            for rec_i, pair in enumerate(parsed.records):
                samples.append(
                    _attach_room(
                        _sample(
                            capture_ts,
                            mac,
                            pair[0],
                            pair[1],
                            SOURCE_HISTORY_CAPTURE,
                            parsed.raw_hex,
                            index=parsed.index + rec_i,
                            record=rec_i,
                            file_name=file_name,
                        ),
                        rooms,
                    )
                )
    return _dedupe_history_capture(samples)


def _dedupe_history_capture(samples: Sequence[dict]) -> List[dict]:
    """Mehrere Captures dumpen dieselben Pages. Pro (mac, index) ein Sample."""
    best = {}  # type: Dict[Tuple[str, int], dict]
    for sample in samples:
        if sample.get("index") is None:
            continue
        key = (sample["mac"], int(sample["index"]))
        prev = best.get(key)
        if prev is None:
            best[key] = sample
            continue
        # Längerer Dump bzw. spätere Datei überschreibt nicht, wenn Index schon da.
        # Erstes Vorkommen behalten (14_52_44 startet bei 0).
    ordered = sorted(best.values(), key=lambda item: (item["mac"], item["index"] or 0))
    return ordered


def load_extracts(extract_dir: str, rooms: Sequence[dict]) -> List[dict]:
    samples = []
    samples.extend(read_extract_adv(os.path.join(extract_dir, "adv.csv"), rooms))
    samples.extend(
        read_extract_history(os.path.join(extract_dir, "att_fff5_fff3.csv"), rooms)
    )
    return samples


def filter_samples(
    samples: Iterable[dict],
    mac: Optional[str] = None,
    source: Optional[str] = None,
    source_in: Optional[Sequence[str]] = None,
) -> List[dict]:
    wanted_mac = normalize_mac(mac) if mac else None
    sources = None
    if source:
        sources = {source}
    elif source_in:
        sources = set(source_in)
    out = []
    for sample in samples:
        if wanted_mac and sample["mac"] != wanted_mac:
            continue
        if sources and sample["source"] not in sources:
            continue
        out.append(sample)
    return out


def sort_samples(samples: Sequence[dict]) -> List[dict]:
    def key(sample: dict):
        src = sample.get("source")
        if src in (SOURCE_HISTORY, SOURCE_HISTORY_CAPTURE) and sample.get("index") is not None:
            return (1, sample["mac"], int(sample["index"]), sample.get("timestamp") or "")
        return (0, sample["mac"], sample.get("timestamp") or "", sample.get("index") or -1)

    return sorted(samples, key=key)


def downsample(samples: Sequence[dict], limit: int) -> List[dict]:
    """Gleichmäßig ausdünnen, Endpunkte behalten. limit <= 0 → unverändert."""
    if limit <= 0 or len(samples) <= limit:
        return list(samples)
    if limit == 1:
        return [samples[-1]]
    last_i = len(samples) - 1
    picked = []
    used = set()
    for step in range(limit):
        idx = int(round(step * last_i / float(limit - 1)))
        if idx in used:
            continue
        used.add(idx)
        picked.append(samples[idx])
    return picked


def summarize(samples: Sequence[dict]) -> dict:
    if not samples:
        return {
            "count": 0,
            "temp_c": None,
            "humidity_rh": None,
            "temp_min": None,
            "temp_max": None,
            "humidity_min": None,
            "humidity_max": None,
            "first_timestamp": None,
            "last_timestamp": None,
            "first_index": None,
            "last_index": None,
        }
    temps = [s["temp_c"] for s in samples]
    hums = [s["humidity_rh"] for s in samples]
    indexes = [s["index"] for s in samples if s.get("index") is not None]
    timestamps = [s["timestamp"] for s in samples if s.get("timestamp")]
    return {
        "count": len(samples),
        "temp_c": temps[-1],
        "humidity_rh": hums[-1],
        "temp_min": min(temps),
        "temp_max": max(temps),
        "humidity_min": min(hums),
        "humidity_max": max(hums),
        "first_timestamp": timestamps[0] if timestamps else None,
        "last_timestamp": timestamps[-1] if timestamps else None,
        "first_index": min(indexes) if indexes else None,
        "last_index": max(indexes) if indexes else None,
    }


class DashStore:
    """Lädt Live/History-CSV und optionale HCI-Extracts, cached nach mtime."""

    def __init__(
        self,
        data_dir: str = DEFAULT_DATA_DIR,
        rooms_path: str = DEFAULT_ROOMS_PATH,
        extract_dir: Optional[str] = DEFAULT_EXTRACT_DIR,
        include_extract: bool = True,
    ):
        self.data_dir = data_dir
        self.rooms_path = rooms_path
        self.extract_dir = extract_dir
        self.include_extract = include_extract
        self._stamp = None  # type: Optional[Tuple]
        self.rooms = []  # type: List[dict]
        self.samples = []  # type: List[dict]

    def _watch_paths(self) -> List[str]:
        paths = [self.rooms_path, self.data_dir]
        if self.include_extract and self.extract_dir:
            paths.append(os.path.join(self.extract_dir, "adv.csv"))
            paths.append(os.path.join(self.extract_dir, "att_fff5_fff3.csv"))
        live, history = list_data_csvs(self.data_dir)
        paths.extend(live)
        paths.extend(history)
        return paths

    def _mtime_stamp(self) -> Tuple:
        items = []
        for path in self._watch_paths():
            try:
                items.append((path, os.path.getmtime(path)))
            except OSError:
                items.append((path, None))
        return tuple(items)

    def refresh(self, force: bool = False) -> None:
        stamp = self._mtime_stamp()
        if not force and stamp == self._stamp:
            return
        self.rooms = load_rooms(self.rooms_path)
        samples = load_live_and_history(self.data_dir, self.rooms)
        if self.include_extract and self.extract_dir:
            samples.extend(load_extracts(self.extract_dir, self.rooms))
        self.samples = sort_samples(samples)
        self._stamp = stamp

    def sources_present(self) -> List[str]:
        found = []
        have = {s["source"] for s in self.samples}
        for name in KNOWN_SOURCES:
            if name in have:
                found.append(name)
        return found

    def overview(self) -> dict:
        self.refresh()
        live_paths, history_paths = list_data_csvs(self.data_dir)
        rooms_out = []
        for room in self.rooms:
            mac = room["mac"]
            for_mac = filter_samples(self.samples, mac=mac)
            live = filter_samples(for_mac, source=SOURCE_ADV)
            hist = filter_samples(for_mac, source=SOURCE_HISTORY)
            adv_cap = filter_samples(for_mac, source=SOURCE_ADV_CAPTURE)
            hist_cap = filter_samples(for_mac, source=SOURCE_HISTORY_CAPTURE)
            latest_live = live[-1] if live else None
            rooms_out.append(
                {
                    "id": room["id"],
                    "name": room["name"],
                    "mac": mac,
                    "confirmed": room.get("confirmed", True),
                    "latest": latest_live or (adv_cap[-1] if adv_cap else None),
                    "counts": {
                        SOURCE_ADV: len(live),
                        SOURCE_HISTORY: len(hist),
                        SOURCE_ADV_CAPTURE: len(adv_cap),
                        SOURCE_HISTORY_CAPTURE: len(hist_cap),
                    },
                    "summary_live": summarize(live),
                    "summary_history": summarize(hist or hist_cap),
                }
            )
        return {
            "rooms": rooms_out,
            "sources": self.sources_present(),
            "live_csv_count": len(live_paths),
            "history_csv_count": len(history_paths),
            "sample_count": len(self.samples),
            "encoding": {
                "scale": 16,
                "temp": "int16le / 16 → °C",
                "humidity": "int16le / 16 → %rF (Display ±3 %, nicht exakt)",
                "history_clock": (
                    "Keine Geräte-Wanduhr. timestamp_inferred = Hypothese 10 min "
                    "(ADV-Counter/Count ≈ 600 s); sonst X = Sample-Index (0 = älteste)."
                ),
                "history_interval_sec_hypothesis": 600,
            },
            "notes": [
                "Nur Allowlist (rooms.json). Keine fremden MACs.",
                "Live-CSV = collect.py über ADV. History-CSV = dump_history.py (GATT 07 oder Extract).",
                "History-Capture = HCI-Extract 07, Beleg. Hum /16 intern; Live ±3 % zum Display.",
            ],
        }

    def query(
        self,
        mac: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 0,
    ) -> dict:
        self.refresh()
        rows = filter_samples(self.samples, mac=mac, source=source)
        rows = sort_samples(rows)
        chart = downsample(rows, limit) if limit else rows
        return {
            "mac": normalize_mac(mac) if mac else None,
            "source": source,
            "count": len(rows),
            "returned": len(chart),
            "summary": summarize(rows),
            "samples": chart,
        }
