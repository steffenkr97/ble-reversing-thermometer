//! Reiner ThermoBeacon-Parser (kein BLE). Encoding: int16le / 16.

use crate::mac::{compact_mac, mac_le_to_str};

pub const TARGET_MAC: &str = "f4:db:00:00:00:d9";
pub const TARGET_SYSTEM_ID: [u8; 8] = [0xD9, 0x00, 0x00, 0x00, 0x00, 0x00, 0xDB, 0xF4];
pub const COMPANY_ID: u16 = 0x001B;
pub const SCALE: f64 = 16.0;

pub const SERVICE_UUID: &str = "0000FFE0-0000-1000-8000-00805f9b34fb";
pub const CONTROL_CHAR_UUID: &str = "0000FFF5-0000-1000-8000-00805f9b34fb";
pub const DATA_CHAR_UUID: &str = "0000FFF3-0000-1000-8000-00805f9b34fb";
pub const SYSTEM_ID_UUID: &str = "00002A23-0000-1000-8000-00805f9b34fb";
pub const CCCD_UUID: &str = "00002902-0000-1000-8000-00805f9b34fb";

const ADV_LIVE_LEN: usize = 20;
const FFF3_LEN: usize = 20;
const MAC_LEN: usize = 6;
const OPCODE_1A: u8 = 0x1A;
const OPCODE_01: u8 = 0x01;
const OPCODE_07: u8 = 0x07;
const OPCODE_F3: u8 = 0xF3;

#[derive(Debug, Clone, PartialEq)]
pub struct AdvLive {
    pub temp_c: f64,
    pub humidity_rh: f64,
    pub battery_mv: u16,
    pub counter: u32,
    pub mac: String,
    pub raw_hex: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Status1A {
    pub raw_hex: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Count01 {
    pub sample_count: u16,
    pub raw_hex: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct History07 {
    pub index: u16,
    pub count: u8,
    pub records: Vec<(f64, f64)>,
    pub raw_hex: String,
}

#[derive(Debug, Clone, PartialEq)]
pub enum Fff3 {
    Status(Status1A),
    Count(Count01),
    History(History07),
}

pub fn i16le_div16(data: &[u8], offset: usize) -> f64 {
    let lo = data[offset] as u16;
    let hi = data[offset + 1] as u16;
    let raw = i16::from_le_bytes([lo as u8, hi as u8]);
    f64::from(raw) / SCALE
}

fn mac_allowed(mac: &str, allowed_macs: Option<&[String]>) -> bool {
    let compact = compact_mac(mac);
    match allowed_macs {
        None => compact == compact_mac(TARGET_MAC),
        Some(items) => items.iter().any(|item| compact_mac(item) == compact),
    }
}

/// 20-Byte-Live-ADV parsen. 22-Byte-Min/Max, fremde Company/MAC → None.
///
/// Ohne `allowed_macs` nur Büro (Encoding-Beleg). Collector übergibt die
/// rooms.json-Allowlist; Capture-ADV im Dashboard nur encoding_checked.
pub fn parse_adv_manufacturer(mfg: &[u8], allowed_macs: Option<&[String]>) -> Option<AdvLive> {
    if mfg.len() != ADV_LIVE_LEN {
        return None;
    }
    let company = u16::from_le_bytes([mfg[0], mfg[1]]);
    if company != COMPANY_ID {
        return None;
    }
    let mac_le = &mfg[4..10];
    if mac_le.len() != MAC_LEN {
        return None;
    }
    let mac = mac_le_to_str(mac_le);
    if !mac_allowed(&mac, allowed_macs) {
        return None;
    }
    let battery_mv = u16::from_le_bytes([mfg[10], mfg[11]]);
    let temp_c = i16le_div16(mfg, 12);
    let humidity_rh = i16le_div16(mfg, 14);
    let counter = u32::from_le_bytes([mfg[16], mfg[17], mfg[18], mfg[19]]);
    Some(AdvLive {
        temp_c,
        humidity_rh,
        battery_mv,
        counter,
        mac,
        raw_hex: hex::encode(mfg),
    })
}

fn parse_history_07(data: &[u8]) -> Option<History07> {
    let index = u16::from_le_bytes([data[1], data[2]]);
    let count = data[5];
    let mut records = Vec::new();
    if count == 3 {
        for i in 0..3 {
            let temp_c = i16le_div16(data, 6 + i * 2);
            let humidity_rh = i16le_div16(data, 12 + i * 2);
            records.push((temp_c, humidity_rh));
        }
    } else if count == 1 {
        // Ein Paar: t0 Offset 6, h0 Offset 8 — nicht Hum an Offset 12.
        records.push((i16le_div16(data, 6), i16le_div16(data, 8)));
    } else {
        return None;
    }
    Some(History07 {
        index,
        count,
        records,
        raw_hex: hex::encode(data),
    })
}

/// 20-Byte-FFF3-Notify. Unbekannt und Opcode F3 → None.
/// Form-B-Records bei 01 nicht als Live parsen.
pub fn parse_fff3(data: &[u8]) -> Option<Fff3> {
    if data.len() != FFF3_LEN {
        return None;
    }
    let opcode = data[0];
    if opcode == OPCODE_F3 {
        return None;
    }
    if opcode == OPCODE_1A {
        return Some(Fff3::Status(Status1A {
            raw_hex: hex::encode(data),
        }));
    }
    if opcode == OPCODE_01 {
        let sample_count = u16::from_le_bytes([data[1], data[2]]);
        return Some(Fff3::Count(Count01 {
            sample_count,
            raw_hex: hex::encode(data),
        }));
    }
    if opcode == OPCODE_07 {
        return parse_history_07(data).map(Fff3::History);
    }
    None
}

/// Write-Payload 6 Byte: 07 <u16le index> 00 00 <count>.
pub fn build_history_07_write(index: u16, count: u8) -> Vec<u8> {
    let mut out = Vec::with_capacity(6);
    out.push(0x07);
    out.extend_from_slice(&index.to_le_bytes());
    out.extend_from_slice(&[0x00, 0x00]);
    out.push(count);
    out
}

/// Company-ID und Rest zu einem 20-Byte-Frame zusammenbauen.
///
/// bleak/btleplug liefern oft 18 Byte nach der Company-ID, manchmal 20 Byte inkl. `1B 00`.
pub fn assemble_mfg_frame(company_id: u16, payload: &[u8]) -> Option<Vec<u8>> {
    let cid_le = COMPANY_ID.to_le_bytes();
    if company_id == COMPANY_ID && payload.len() == 18 {
        let mut frame = Vec::with_capacity(20);
        frame.extend_from_slice(&cid_le);
        frame.extend_from_slice(payload);
        return Some(frame);
    }
    if payload.len() == 20 && payload.starts_with(&cid_le) {
        return Some(payload.to_vec());
    }
    None
}

pub fn format_sample(live: &AdvLive) -> String {
    format!(
        "temp_c={} humidity_rh={} battery_mv={} counter={} mac={} raw_hex={}",
        crate::csvutil::fmt_float(live.temp_c),
        crate::csvutil::fmt_float(live.humidity_rh),
        live.battery_mv,
        live.counter,
        live.mac,
        live.raw_hex,
    )
}
