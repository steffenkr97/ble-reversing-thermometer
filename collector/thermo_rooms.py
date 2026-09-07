#!/usr/bin/env python3
"""Allowlist aus dashboard/rooms.json (Phase 7). Kein BLE."""
from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
DEFAULT_ROOMS_PATH = os.path.join(_ROOT, "dashboard", "rooms.json")
MAX_ROOMS = 5


class RoomsError(ValueError):
    """Ungültige Allowlist (MAC, Name, Limit, Duplikat)."""


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


def is_valid_mac(mac: str) -> bool:
    compact = mac12(mac)
    return len(compact) == 12 and all(c in "0123456789abcdef" for c in compact)


def _room_to_json(room: dict) -> dict:
    out = {
        "id": room["id"],
        "name": room["name"],
        "mac": room["mac"],
        "confirmed": bool(room.get("confirmed", True)),
        "encoding_checked": bool(room.get("encoding_checked", room.get("confirmed", True))),
    }
    if room.get("system_id"):
        out["system_id"] = room["system_id"]
    if room.get("note"):
        out["note"] = room["note"]
    return out


def normalize_room(raw: dict) -> dict:
    mac = normalize_mac(str(raw.get("mac") or ""))
    name = str(raw.get("name") or "").strip()
    room_id = str(raw.get("id") or mac12(mac)).strip()
    confirmed = bool(raw.get("confirmed", True))
    encoding_checked = bool(raw.get("encoding_checked", confirmed))
    return {
        "id": room_id,
        "name": name,
        "mac": mac,
        "confirmed": confirmed,
        "encoding_checked": encoding_checked,
        "system_id": _system_id_hex(raw.get("system_id")),
        "note": str(raw.get("note") or "").strip() or None,
    }


def validate_rooms(rooms: Sequence[dict]) -> List[dict]:
    """Normalisieren und prüfen: Name, MAC, eindeutige id/MAC, max. 5."""
    out = []
    seen_mac = set()
    seen_id = set()
    for raw in rooms:
        room = normalize_room(raw)
        if not room["name"]:
            raise RoomsError("Anzeigename darf nicht leer sein")
        if not is_valid_mac(room["mac"]):
            raise RoomsError("MAC ungültig: {}".format(raw.get("mac") or ""))
        if not room["id"]:
            raise RoomsError("Raum-ID darf nicht leer sein")
        if room["mac"] in seen_mac:
            raise RoomsError("MAC doppelt: {}".format(room["mac"]))
        if room["id"] in seen_id:
            raise RoomsError("Raum-ID doppelt: {}".format(room["id"]))
        seen_mac.add(room["mac"])
        seen_id.add(room["id"])
        out.append(room)
    if len(out) > MAX_ROOMS:
        raise RoomsError("Maximal {} Geräte".format(MAX_ROOMS))
    return out


def save_rooms(path: str, rooms: Sequence[dict]) -> List[dict]:
    """Allowlist atomar schreiben. Wirft RoomsError bei ungültigen Daten."""
    validated = validate_rooms(rooms)
    parent = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    payload = {"rooms": [_room_to_json(room) for room in validated]}
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)
    return validated


def add_room(
    rooms: Sequence[dict],
    name: str,
    mac: str,
    confirmed: bool = True,
    encoding_checked: Optional[bool] = None,
    note: Optional[str] = None,
    room_id: Optional[str] = None,
    system_id: Optional[str] = None,
) -> List[dict]:
    """Gerät anhängen. UI-Geräte: confirmed=true (eigene)."""
    if encoding_checked is None:
        encoding_checked = confirmed
    new_room = {
        "id": (room_id or mac12(normalize_mac(mac))).strip(),
        "name": name,
        "mac": mac,
        "confirmed": confirmed,
        "encoding_checked": encoding_checked,
        "note": note,
        "system_id": system_id,
    }
    return validate_rooms(list(rooms) + [new_room])


def update_room(rooms: Sequence[dict], room_id: str, **fields) -> List[dict]:
    """Name / confirmed / encoding_checked / note ändern. MAC bleibt."""
    found = False
    out = []
    allowed = {"name", "confirmed", "encoding_checked", "note"}
    unknown = set(fields) - allowed
    if unknown:
        raise RoomsError("unbekanntes Feld: {}".format(", ".join(sorted(unknown))))
    for room in rooms:
        item = dict(room)
        if item["id"] == room_id:
            found = True
            if "name" in fields and fields["name"] is not None:
                item["name"] = fields["name"]
            if "confirmed" in fields and fields["confirmed"] is not None:
                item["confirmed"] = bool(fields["confirmed"])
            if "encoding_checked" in fields and fields["encoding_checked"] is not None:
                item["encoding_checked"] = bool(fields["encoding_checked"])
            if "note" in fields:
                note = fields["note"]
                item["note"] = (str(note).strip() or None) if note is not None else None
        out.append(item)
    if not found:
        raise RoomsError("Raum nicht gefunden: {}".format(room_id))
    return validate_rooms(out)


def delete_room(rooms: Sequence[dict], room_id: str) -> List[dict]:
    out = [dict(room) for room in rooms if room["id"] != room_id]
    if len(out) == len(rooms):
        raise RoomsError("Raum nicht gefunden: {}".format(room_id))
    return validate_rooms(out)
