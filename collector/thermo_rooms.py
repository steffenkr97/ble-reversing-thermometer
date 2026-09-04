#!/usr/bin/env python3
"""Allowlist aus dashboard/rooms.json (Phase 7). Kein BLE."""
from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DEFAULT_ROOMS_PATH = os.path.join(_ROOT, "dashboard", "rooms.json")


def mac12(mac: str) -> str:
    return (mac or "").replace(":", "").replace("-", "").replace(".", "").lower()


def normalize_mac(mac: str) -> str:
    compact = mac12(mac)
    if len(compact) == 12 and all(c in "0123456789abcdef" for c in compact):
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    return (mac or "").strip().lower()


def _system_id_hex(raw) -> Optional[str]:
    if not raw:
        return None
    hex_str = str(raw).replace(" ", "").replace(":", "").strip().upper()
    if len(hex_str) != 16:
        return None
    try:
        bytes.fromhex(hex_str)
    except ValueError:
        return None
    return hex_str


def load_rooms(path: str = DEFAULT_ROOMS_PATH) -> List[dict]:
    """Räume aus rooms.json. Kandidaten dürfen confirmed=false haben."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    rooms = []
    for raw in payload.get("rooms") or []:
        mac = normalize_mac(str(raw.get("mac") or ""))
        name = str(raw.get("name") or "").strip()
        room_id = str(raw.get("id") or mac12(mac))
        if not mac or not name:
            continue
        confirmed = bool(raw.get("confirmed", True))
        encoding_checked = bool(raw.get("encoding_checked", confirmed))
        rooms.append(
            {
                "id": room_id,
                "name": name,
                "mac": mac,
                "confirmed": confirmed,
                "encoding_checked": encoding_checked,
                "system_id": _system_id_hex(raw.get("system_id")),
                "note": str(raw.get("note") or "").strip() or None,
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
    """Alle Einträge — auch unbestätigte Kandidaten. Fremde MACs stehen nicht in der Datei."""
    return [room["mac"] for room in rooms]


def confirmed_macs(rooms: Sequence[dict]) -> List[str]:
    return [room["mac"] for room in rooms if room.get("confirmed")]


def encoding_checked_macs(rooms: Sequence[dict]) -> List[str]:
    """ADV-Parser gegen Display geprüft. Sonst nur Büro / encoding_checked."""
    return [room["mac"] for room in rooms if room.get("encoding_checked")]


def mac_in_allowlist(mac: str, allowed: Iterable[str]) -> bool:
    compact = mac12(mac)
    wanted = {mac12(item) for item in allowed}
    return compact in wanted
