//! Allowlist aus dashboard/rooms.json (Phase 7). Kein BLE.

use serde::Deserialize;
use std::path::Path;

use crate::mac::{compact_mac, normalize_mac};
use crate::paths::default_rooms_path;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Room {
    pub id: String,
    pub name: String,
    pub mac: String,
    pub confirmed: bool,
    pub encoding_checked: bool,
    pub system_id: Option<String>,
    pub note: Option<String>,
}

#[derive(Deserialize)]
struct RoomsFile {
    rooms: Option<Vec<RawRoom>>,
}

#[derive(Deserialize)]
struct RawRoom {
    id: Option<String>,
    name: Option<String>,
    mac: Option<String>,
    confirmed: Option<bool>,
    encoding_checked: Option<bool>,
    system_id: Option<serde_json::Value>,
    note: Option<String>,
}

fn system_id_hex(raw: Option<&serde_json::Value>) -> Option<String> {
    let raw = raw?;
    let hex_str = match raw {
        serde_json::Value::String(s) => s.replace([' ', ':'], "").trim().to_uppercase(),
        serde_json::Value::Null => return None,
        other => other.to_string().replace([' ', ':'], "").trim().to_uppercase(),
    };
    if hex_str.is_empty() {
        return None;
    }
    if hex_str.len() != 16 {
        return None;
    }
    if hex::decode(&hex_str).is_err() {
        return None;
    }
    Some(hex_str)
}

/// Räume aus rooms.json. Kandidaten dürfen confirmed=false haben.
pub fn load_rooms(path: impl AsRef<Path>) -> crate::error::Result<Vec<Room>> {
    let data = std::fs::read_to_string(path)?;
    let payload: RoomsFile = serde_json::from_str(&data)?;
    let mut rooms = Vec::new();
    for raw in payload.rooms.unwrap_or_default() {
        let mac = normalize_mac(raw.mac.as_deref().unwrap_or(""));
        let name = raw.name.unwrap_or_default().trim().to_string();
        if mac.is_empty() || name.is_empty() {
            continue;
        }
        let room_id = raw
            .id
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| compact_mac(&mac));
        let confirmed = raw.confirmed.unwrap_or(true);
        let encoding_checked = raw.encoding_checked.unwrap_or(confirmed);
        let note = raw
            .note
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        rooms.push(Room {
            id: room_id,
            name,
            mac,
            confirmed,
            encoding_checked,
            system_id: system_id_hex(raw.system_id.as_ref()),
            note,
        });
    }
    Ok(rooms)
}

pub fn load_rooms_default() -> crate::error::Result<Vec<Room>> {
    load_rooms(default_rooms_path())
}

pub fn room_by_mac<'a>(rooms: &'a [Room], mac: &str) -> Option<&'a Room> {
    let target = normalize_mac(mac);
    rooms.iter().find(|r| r.mac == target)
}

/// Alle Einträge — auch unbestätigte Kandidaten. Fremde MACs stehen nicht in der Datei.
pub fn allowlist_macs(rooms: &[Room]) -> Vec<String> {
    rooms.iter().map(|r| r.mac.clone()).collect()
}

pub fn confirmed_macs(rooms: &[Room]) -> Vec<String> {
    rooms
        .iter()
        .filter(|r| r.confirmed)
        .map(|r| r.mac.clone())
        .collect()
}

/// ADV-Parser gegen Display geprüft. Sonst nur Büro / encoding_checked.
pub fn encoding_checked_macs(rooms: &[Room]) -> Vec<String> {
    rooms
        .iter()
        .filter(|r| r.encoding_checked)
        .map(|r| r.mac.clone())
        .collect()
}

pub fn mac_in_allowlist(mac: &str, allowed: &[String]) -> bool {
    let compact = compact_mac(mac);
    allowed.iter().any(|item| compact_mac(item) == compact)
}
