#!/usr/bin/env python3
"""App-Sync: inkrementelle History (GATT 07) und Live-ADV. Kein 0x18/0x04."""
from __future__ import annotations

import json
import os
import threading
from typing import Callable, Dict, List, Optional, Sequence

from thermo_history import (
    INTERVAL_SEC_HYPOTHESIS,
    apply_incremental_history,
    default_history_csv_path,
    default_sync_state_path,
    load_sync_state,
    max_history_index,
    page_plan,
    page_plan_since,
    read_history_csv,
    samples_from_pages,
    write_history_csv,
    write_sync_state,
)
from thermo_rooms import confirmed_macs, load_rooms, normalize_mac, room_by_mac
from thermo_store import append_sample, default_csv_path, iso_utc_now

DEFAULT_LIVE_INTERVAL_SEC = 60.0
DEFAULT_SCAN_TIMEOUT_SEC = 15.0


def stored_last_index(data_dir: str, mac: str) -> int:
    """Max-Index aus History-CSV, sonst -1 (voller Dump)."""
    path = default_history_csv_path(mac, outdir=data_dir)
    last = max_history_index(read_history_csv(path))
    if last is not None:
        return last
    state = load_sync_state(default_sync_state_path(mac, outdir=data_dir))
    if state and state.get("last_index") is not None:
        try:
            return int(state["last_index"])
        except (TypeError, ValueError):
            return -1
    return -1


def plan_incremental(sample_count: int, last_index: int) -> List[tuple]:
    """07-Pages seit last_index. Count-Rückgang → voller Plan."""
    count = int(sample_count)
    if count < last_index + 1:
        return page_plan(count)
    return page_plan_since(count, last_index)


def persist_history_dump(
    mac: str,
    data_dir: str,
    existing: Sequence[dict],
    incoming: Sequence[dict],
    sample_count: int,
    newest_utc: Optional[str] = None,
    interval_sec: float = INTERVAL_SEC_HYPOTHESIS,
) -> dict:
    """Merge, Zeitanker, CSV + sync_*.json. Ohne BLE."""
    mac_n = normalize_mac(mac)
    last_before = max_history_index(existing)
    newest = newest_utc or iso_utc_now()
    rows = apply_incremental_history(
        existing,
        incoming,
        sample_count,
        newest,
        interval_sec=interval_sec,
    )
    path = default_history_csv_path(mac_n, outdir=data_dir)
    write_history_csv(path, rows)
    last_index = max_history_index(rows)
    if last_index is None:
        last_index = -1
    if last_before is None or int(sample_count) < last_before + 1:
        new_samples = len(rows)
    else:
        new_samples = max(0, int(sample_count) - (last_before + 1))
    state = {
        "mac": mac_n,
        "last_index": last_index,
        "last_count": int(sample_count),
        "last_dump_at": newest,
        "new_samples": new_samples,
    }
    write_sync_state(default_sync_state_path(mac_n, outdir=data_dir), state)
    return {
        "state": "ok" if new_samples else "up_to_date",
        "path": path,
        "sample_count": int(sample_count),
        "last_index": last_index,
        "new_samples": new_samples,
        "last_dump_at": newest,
        "row_count": len(rows),
    }


class AppStatus:
    """Thread-sicherer Sync-Status für /api/status und data/app_status.json."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self.path = path
        self._data = {
            "ble": False,
            "phase": "idle",
            "started_at": None,
            "live_interval_sec": DEFAULT_LIVE_INTERVAL_SEC,
            "message": "",
            "devices": {},
        }  # type: dict

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))

    def update(self, **fields) -> dict:
        with self._lock:
            self._data.update(fields)
            data = json.loads(json.dumps(self._data))
        self._write(data)
        return data

    def set_device(self, mac: str, **fields) -> dict:
        mac_n = normalize_mac(mac)
        with self._lock:
            devices = dict(self._data.get("devices") or {})
            current = dict(devices.get(mac_n) or {})
            current.update(fields)
            current["mac"] = mac_n
            devices[mac_n] = current
            self._data["devices"] = devices
            data = json.loads(json.dumps(self._data))
        self._write(data)
        return data

    def _write(self, data: dict) -> None:
        if not self.path:
            return
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, self.path)


async def sync_history_one(
    room: dict,
    data_dir: str,
    rooms: Sequence[dict],
    *,
    address: Optional[str] = None,
    notify_timeout: float = 2.0,
    retries: int = 2,
    interval_sec: float = INTERVAL_SEC_HYPOTHESIS,
    status: Optional[AppStatus] = None,
    gatt_fetch=None,
    log: Optional[Callable[[str], None]] = None,
) -> dict:
    """Inkrementeller GATT-Dump für ein bestätigtes Gerät."""
    mac = normalize_mac(room["mac"])
    addr = address or mac
    existing = read_history_csv(default_history_csv_path(mac, outdir=data_dir))
    last_index = stored_last_index(data_dir, mac)
    if status:
        status.set_device(
            mac,
            name=room.get("name"),
            confirmed=True,
            history={"state": "running", "last_index": last_index},
        )
        status.update(phase="history", message="History-Sync {} …".format(room.get("name") or mac))

    def plan_for_count(sample_count: int):
        return plan_incremental(sample_count, last_index)

    fetch = gatt_fetch
    if fetch is None:
        import dump_history

        async def fetch(device_address, mac_arg, rooms_arg, plan_fn):
            return await dump_history.gatt_history_pages(
                device_address,
                mac_arg,
                rooms_arg,
                address_was_given=True,
                notify_timeout=notify_timeout,
                retries=retries,
                plan_for_count=plan_fn,
                log=log,
            )

    sample_count, pages = await fetch(addr, mac, rooms, plan_for_count)
    incoming = samples_from_pages(pages, mac)
    result = persist_history_dump(
        mac,
        data_dir,
        existing,
        incoming,
        sample_count,
        interval_sec=interval_sec,
    )
    if status:
        status.set_device(mac, name=room.get("name"), confirmed=True, history=result)
        status.update(
            message="History {} : {} neue Samples".format(
                room.get("name") or mac, result["new_samples"]
            )
        )
    return result


async def collect_live_round(
    macs: Sequence[str],
    data_dir: str,
    timeout: float = DEFAULT_SCAN_TIMEOUT_SEC,
    address: Optional[str] = None,
    scan_fn=None,
) -> Dict[str, dict]:
    """Ein ADV-Fenster, Append je Treffer. Filter: Payload-MAC."""
    wanted = [normalize_mac(m) for m in macs]
    if not wanted:
        return {}
    if scan_fn is None:
        from scan_live import scan_live, scan_live_many

        if len(wanted) == 1:
            live = await scan_live(
                timeout=timeout, address=address, allowed_macs=wanted
            )
            found = {live.mac: live} if live is not None else {}
        else:
            found = await scan_live_many(
                timeout=timeout, allowed_macs=wanted, address=address
            )
    else:
        found = await scan_fn(wanted, timeout, address)

    written = {}
    for mac, live in found.items():
        path = default_csv_path(live.mac, outdir=data_dir)
        stamp = iso_utc_now()
        append_sample(
            path,
            stamp,
            live.mac,
            live.temp_c,
            live.humidity_rh,
            live.raw_hex,
        )
        written[normalize_mac(mac)] = {
            "mac": live.mac,
            "temp_c": live.temp_c,
            "humidity_rh": live.humidity_rh,
            "last_sample_at": stamp,
            "path": path,
        }
    return written


def _rooms_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


async def run_worker(
    rooms_path: str,
    data_dir: str,
    status: AppStatus,
    *,
    interval_sec: float = DEFAULT_LIVE_INTERVAL_SEC,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT_SEC,
    stop_event: Optional[threading.Event] = None,
    enable_live: bool = True,
    gatt_fetch=None,
    scan_fn=None,
    sleep_fn=None,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """History für confirmed, dann Live-ADV-Loop. Rooms-mtime neu laden."""
    import asyncio

    stop = stop_event or threading.Event()
    sleeper = sleep_fn or asyncio.sleep
    status.update(
        ble=True,
        phase="history",
        started_at=iso_utc_now(),
        live_interval_sec=interval_sec,
        message="History-Sync startet",
    )
    synced = set()  # type: set

    async def ensure_history(rooms: Sequence[dict]) -> None:
        for room in rooms:
            if stop.is_set():
                return
            if not room.get("confirmed"):
                continue
            mac = normalize_mac(room["mac"])
            if mac in synced:
                continue
            try:
                await sync_history_one(
                    room,
                    data_dir,
                    rooms,
                    gatt_fetch=gatt_fetch,
                    status=status,
                    log=log,
                )
            except Exception as exc:  # noqa: BLE001 — ein Gerät darf die anderen nicht stoppen
                if status:
                    status.set_device(
                        mac,
                        name=room.get("name"),
                        confirmed=True,
                        history={"state": "error", "error": str(exc)},
                    )
                    status.update(
                        message="History {} fehlgeschlagen: {}".format(
                            room.get("name") or mac, exc
                        )
                    )
                if log:
                    log("History {} : {}".format(mac, exc))
            synced.add(mac)

    last_mtime = _rooms_mtime(rooms_path)
    rooms = load_rooms(rooms_path)
    await ensure_history(rooms)

    if not enable_live or stop.is_set():
        status.update(phase="idle", message="History-Sync fertig")
        return

    status.update(phase="live", message="Live-ADV läuft")
    while not stop.is_set():
        mtime = _rooms_mtime(rooms_path)
        if mtime != last_mtime:
            last_mtime = mtime
            rooms = load_rooms(rooms_path)
            await ensure_history(rooms)
        macs = confirmed_macs(rooms)
        if macs:
            try:
                found = await collect_live_round(
                    macs,
                    data_dir,
                    timeout=scan_timeout,
                    scan_fn=scan_fn,
                )
                for mac in macs:
                    room = room_by_mac(rooms, mac)
                    name = room["name"] if room else mac
                    hit = found.get(normalize_mac(mac))
                    if hit:
                        status.set_device(
                            mac,
                            name=name,
                            confirmed=True,
                            live={
                                "last_sample_at": hit["last_sample_at"],
                                "temp_c": hit["temp_c"],
                                "humidity_rh": hit["humidity_rh"],
                                "error": None,
                            },
                        )
                    else:
                        status.set_device(
                            mac,
                            name=name,
                            confirmed=True,
                            live={"error": "kein ADV in diesem Fenster"},
                        )
                if found:
                    status.update(
                        phase="live",
                        message="Live: {} Gerät(e)".format(len(found)),
                    )
                else:
                    status.update(
                        phase="live",
                        message="Kein Live-Sample in diesem Fenster",
                    )
            except Exception as exc:  # noqa: BLE001
                status.update(phase="live", message="Live-Fehler: {}".format(exc))
                if log:
                    log("Live: {}".format(exc))
        await sleeper(interval_sec)


def run_worker_thread(
    rooms_path: str,
    data_dir: str,
    status: AppStatus,
    **kwargs,
) -> threading.Thread:
    """Hintergrund-Thread mit eigenem asyncio-Loop."""
    import asyncio

    def _target() -> None:
        asyncio.run(
            run_worker(rooms_path, data_dir, status, **kwargs)
        )

    thread = threading.Thread(target=_target, name="thermo-ble-worker", daemon=True)
    thread.start()
    return thread


def default_status_path(data_dir: str) -> str:
    return os.path.join(data_dir, "app_status.json")
