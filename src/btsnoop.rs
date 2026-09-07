//! btsnoop/H4-Parser für ThermoBeacon-HCI-Captures (.cfa).
//!
//! Liest Android-btsnoop (Datalink 1002, HCI UART H4). Keine BLE-Writes.
//! Nur Auswertung vorhandener Captures.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use chrono::{TimeZone, Utc};
use walkdir::WalkDir;

pub const MAGIC: &[u8] = b"btsnoop\0";
pub const DATALINK_H4: u32 = 1002;
pub const BTSNOOP_EPOCH_DELTA: u64 = 0x00DCDDB30F2F8000;

pub const H4_ACL: u8 = 0x02;
pub const H4_EVT: u8 = 0x04;

pub const ATT_CID: u16 = 0x0004;
pub const ATT_WRITE_REQ: u8 = 0x12;
pub const ATT_WRITE_CMD: u8 = 0x52;
pub const ATT_WRITE_RSP: u8 = 0x13;
pub const ATT_NOTIFY: u8 = 0x1B;
pub const ATT_INDICATE: u8 = 0x1D;
pub const ATT_MTU_REQ: u8 = 0x02;
pub const ATT_MTU_RSP: u8 = 0x03;
pub const ATT_READ_BY_TYPE_RSP: u8 = 0x09;
pub const ATT_READ_BY_GROUP_RSP: u8 = 0x11;
pub const ATT_READ_REQ: u8 = 0x0A;
pub const ATT_READ_RSP: u8 = 0x0B;

pub const UUID_FFF3: u16 = 0xFFF3;
pub const UUID_FFF5: u16 = 0xFFF5;

pub const HCI_EVENT_DISCONN: u8 = 0x05;
pub const HCI_EVENT_LE_META: u8 = 0x3E;
pub const LE_CONN_COMPLETE: u8 = 0x01;
pub const LE_ADV_REPORT: u8 = 0x02;
pub const LE_ENHANCED_CONN: u8 = 0x0A;

pub const TARGET_MAC: &str = crate::parse::TARGET_MAC;

fn att_name(op: u8) -> &'static str {
    match op {
        0x01 => "ErrorRsp",
        0x02 => "MTU-Req",
        0x03 => "MTU-Rsp",
        0x04 => "FindInfo-Req",
        0x05 => "FindInfo-Rsp",
        0x06 => "FindByType-Req",
        0x07 => "FindByType-Rsp",
        0x08 => "ReadByType-Req",
        0x09 => "ReadByType-Rsp",
        0x0A => "Read-Req",
        0x0B => "Read-Rsp",
        0x0C => "ReadBlob-Req",
        0x0D => "ReadBlob-Rsp",
        0x10 => "ReadByGrp-Req",
        0x11 => "ReadByGrp-Rsp",
        0x12 => "Write-Req",
        0x13 => "Write-Rsp",
        0x16 => "PrepWrite-Req",
        0x17 => "PrepWrite-Rsp",
        0x18 => "ExecWrite-Req",
        0x19 => "ExecWrite-Rsp",
        0x1B => "Notify",
        0x1D => "Indicate",
        0x1E => "Confirm",
        0x52 => "Write-Cmd",
        _ => "",
    }
}

fn att_name_owned(op: u8) -> String {
    let n = att_name(op);
    if n.is_empty() {
        format!("0x{op:02X}")
    } else {
        n.to_string()
    }
}

fn adv_event_name(et: u8) -> String {
    match et {
        0x00 => "ADV_IND".into(),
        0x01 => "ADV_DIRECT_IND".into(),
        0x02 => "ADV_SCAN_IND".into(),
        0x03 => "ADV_NONCONN_IND".into(),
        0x04 => "SCAN_RSP".into(),
        _ => format!("0x{et:02X}"),
    }
}

fn ad_type_name(t: u8) -> String {
    match t {
        0x01 => "Flags".into(),
        0x02 => "IncUUIDs16".into(),
        0x03 => "CmpUUIDs16".into(),
        0x08 => "ShortName".into(),
        0x09 => "Name".into(),
        0x0A => "TxPower".into(),
        0x12 => "SlaveConnInterval".into(),
        0x16 => "ServiceData16".into(),
        0x19 => "Appearance".into(),
        0xFF => "Manufacturer".into(),
        _ => format!("0x{t:x}"),
    }
}

pub fn u16le(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}

pub fn u32be(b: &[u8], o: usize) -> u32 {
    u32::from_be_bytes([b[o], b[o + 1], b[o + 2], b[o + 3]])
}

pub fn u64be(b: &[u8], o: usize) -> u64 {
    u64::from_be_bytes([
        b[o], b[o + 1], b[o + 2], b[o + 3], b[o + 4], b[o + 5], b[o + 6], b[o + 7],
    ])
}

pub fn hex_of(b: &[u8]) -> String {
    b.iter()
        .map(|x| format!("{x:02X}"))
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn mac_from_le(addr: &[u8]) -> String {
    addr.iter()
        .rev()
        .map(|x| format!("{x:02x}"))
        .collect::<Vec<_>>()
        .join(":")
}

pub fn mac_norm(s: &str) -> String {
    s.to_lowercase().replace('-', ":")
}

pub fn ts_iso(us_since_year0: u64) -> String {
    let unix_us = us_since_year0 as i128 - BTSNOOP_EPOCH_DELTA as i128;
    let secs = unix_us.div_euclid(1_000_000);
    let micros = unix_us.rem_euclid(1_000_000) as u32;
    match Utc.timestamp_opt(secs as i64, micros * 1000) {
        chrono::LocalResult::Single(dt) => {
            // Python: strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z" (Millisekunden).
            // chrono %f ist Nanosekunden (9 Stellen); %3f = 3 Stellen wie der Extract.
            format!("{}Z", dt.format("%Y-%m-%dT%H:%M:%S.%3f"))
        }
        _ => us_since_year0.to_string(),
    }
}

pub fn parse_ad_structures(data: &[u8]) -> Vec<(u8, Vec<u8>)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < data.len() {
        let ln = data[i] as usize;
        if ln == 0 {
            break;
        }
        if i + 1 + ln > data.len() {
            break;
        }
        let ad_type = data[i + 1];
        let val = data[i + 2..i + 1 + ln].to_vec();
        out.push((ad_type, val));
        i += 1 + ln;
    }
    out
}

#[derive(Debug, Clone)]
pub struct SnoopRecord {
    pub index: usize,
    pub orig_len: u32,
    pub incl_len: u32,
    pub flags: u32,
    pub timestamp_raw: u64,
    pub timestamp: String,
    pub direction: String,
    pub h4_type: u8,
    pub payload: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct AttPdu {
    pub rec: usize,
    pub timestamp: String,
    pub direction: String,
    pub conn: u16,
    pub peer: String,
    pub opcode: u8,
    pub opcode_name: String,
    pub handle: Option<u16>,
    pub value: Vec<u8>,
    pub raw: Vec<u8>,
}

#[derive(Debug, Clone)]
pub struct AdvReport {
    pub rec: usize,
    pub timestamp: String,
    pub event_type: u8,
    pub event_name: String,
    pub addr_type: u8,
    pub mac: String,
    pub rssi: i16,
    pub data: Vec<u8>,
    pub ads: Vec<(u8, Vec<u8>)>,
}

#[derive(Debug, Clone)]
pub struct CharDecl {
    pub decl_handle: u16,
    pub properties: u8,
    pub value_handle: u16,
    pub uuid16: Option<u16>,
    pub uuid_hex: String,
}

#[derive(Debug, Clone)]
pub struct Capture {
    pub path: PathBuf,
    pub version: u32,
    pub datalink: u32,
    pub size: usize,
    pub records: usize,
    pub strings_hint: Vec<String>,
    pub conn_peer: HashMap<u16, String>,
    pub att: Vec<AttPdu>,
    pub adv: Vec<AdvReport>,
    pub chars: Vec<CharDecl>,
    pub services: Vec<(u16, u16, String)>,
    pub le_conns: Vec<(String, u16, String)>,
    pub parse_errors: Vec<String>,
}

pub fn iter_snoop_records(data: &[u8]) -> anyhow::Result<Vec<SnoopRecord>> {
    if data.len() < 8 || &data[..8] != MAGIC {
        anyhow::bail!("kein btsnoop-Magic");
    }
    let version = u32be(data, 8);
    if version != 1 {
        anyhow::bail!("unbekannte btsnoop-Version {version}");
    }
    let mut i = 16usize;
    let mut idx = 0usize;
    let n = data.len();
    let mut out = Vec::new();
    while i + 24 <= n {
        let orig = u32be(data, i);
        let incl = u32be(data, i + 4);
        let flags = u32be(data, i + 8);
        let ts = u64be(data, i + 16);
        i += 24;
        if i + incl as usize > n {
            break;
        }
        let pkt = &data[i..i + incl as usize];
        i += incl as usize;
        idx += 1;
        if pkt.is_empty() {
            continue;
        }
        let direction = if flags & 0x01 != 0 { "recv" } else { "sent" };
        out.push(SnoopRecord {
            index: idx,
            orig_len: orig,
            incl_len: incl,
            flags,
            timestamp_raw: ts,
            timestamp: ts_iso(ts),
            direction: direction.into(),
            h4_type: pkt[0],
            payload: pkt[1..].to_vec(),
        });
    }
    Ok(out)
}

pub fn extract_ascii_hints(data: &[u8]) -> Vec<String> {
    let interesting = [
        b"OnePlus".as_slice(),
        b"oneplus".as_slice(),
        b"ThermoBeacon".as_slice(),
        b"Android".as_slice(),
        b"btsnoop".as_slice(),
        b"Qualcomm".as_slice(),
        b"BlueDroid".as_slice(),
    ];
    let mut found = Vec::new();
    let low = data.to_ascii_lowercase();
    for needle in interesting {
        let nlow = needle.to_ascii_lowercase();
        if low.windows(nlow.len()).any(|w| w == nlow.as_slice()) {
            found.push(String::from_utf8_lossy(needle).into_owned());
        }
    }
    if let Some(pos) = low.windows(7).position(|w| w == b"oneplus") {
        let start = pos.saturating_sub(8);
        let end = (pos + 24).min(data.len());
        let run = &data[start..end];
        let printable: String = run
            .iter()
            .map(|c| if (32..127).contains(c) { *c as char } else { '.' })
            .collect();
        found.push(format!("context:{printable}"));
    }
    found
}

struct AclReassembler {
    buf: HashMap<u16, Vec<u8>>,
}

impl AclReassembler {
    fn new() -> Self {
        Self {
            buf: HashMap::new(),
        }
    }

    fn feed(&mut self, handle: u16, pb: u8, data: &[u8]) -> Vec<Vec<u8>> {
        let mut out = Vec::new();
        let start = pb == 0x00 || pb == 0x02;
        let cont = pb == 0x01;
        if start {
            self.buf.insert(handle, data.to_vec());
        } else if cont {
            if !self.buf.contains_key(&handle) {
                return out;
            }
            self.buf.get_mut(&handle).unwrap().extend_from_slice(data);
        } else {
            self.buf.insert(handle, data.to_vec());
        }
        loop {
            let buf = match self.buf.get(&handle) {
                Some(b) => b,
                None => break,
            };
            if buf.len() < 4 {
                break;
            }
            let need = 4 + u16le(buf, 0) as usize;
            if buf.len() < need {
                break;
            }
            let pdu = buf[..need].to_vec();
            let rest = buf[need..].to_vec();
            out.push(pdu);
            if rest.is_empty() {
                self.buf.remove(&handle);
                break;
            } else {
                self.buf.insert(handle, rest);
            }
        }
        out
    }
}

pub fn parse_att_pdu(raw: &[u8]) -> (u8, Option<u16>, Vec<u8>) {
    if raw.is_empty() {
        return (0, None, Vec::new());
    }
    let op = raw[0];
    let mut handle = None;
    let mut value = raw[1..].to_vec();
    if matches!(
        op,
        ATT_WRITE_REQ | ATT_WRITE_CMD | ATT_NOTIFY | ATT_INDICATE | ATT_READ_REQ | ATT_READ_RSP
    ) {
        if raw.len() >= 3 {
            handle = Some(u16le(raw, 1));
            value = if op != ATT_READ_REQ {
                raw[3..].to_vec()
            } else {
                Vec::new()
            };
            if op == ATT_READ_RSP {
                handle = None;
                value = raw[1..].to_vec();
            }
            if op == ATT_READ_REQ {
                value = Vec::new();
            }
        }
    }
    (op, handle, value)
}

pub fn parse_char_decls(item_len: usize, payload: &[u8]) -> Vec<CharDecl> {
    let mut out = Vec::new();
    let mut i = 0;
    while i + item_len <= payload.len() {
        let rec = &payload[i..i + item_len];
        let decl_h = u16le(rec, 0);
        let props = rec[2];
        let val_h = u16le(rec, 3);
        let uuid_bytes = &rec[5..];
        let uuid16 = if uuid_bytes.len() >= 2 {
            Some(u16le(uuid_bytes, 0))
        } else {
            None
        };
        out.push(CharDecl {
            decl_handle: decl_h,
            properties: props,
            value_handle: val_h,
            uuid16,
            uuid_hex: hex_of(uuid_bytes),
        });
        i += item_len;
    }
    out
}

pub fn parse_file(path: &Path) -> Capture {
    let data = fs::read(path).unwrap_or_default();
    let mut cap = Capture {
        path: path.to_path_buf(),
        version: if data.len() >= 12 { u32be(&data, 8) } else { 0 },
        datalink: if data.len() >= 16 { u32be(&data, 12) } else { 0 },
        size: data.len(),
        records: 0,
        strings_hint: extract_ascii_hints(&data),
        conn_peer: HashMap::new(),
        att: Vec::new(),
        adv: Vec::new(),
        chars: Vec::new(),
        services: Vec::new(),
        le_conns: Vec::new(),
        parse_errors: Vec::new(),
    };
    if data.len() < 8 || &data[..8] != MAGIC {
        cap.parse_errors.push("kein btsnoop-Magic".into());
        return cap;
    }
    if cap.datalink != DATALINK_H4 {
        cap.parse_errors
            .push(format!("datalink={} (erwartet 1002)", cap.datalink));
    }
    let recs = match iter_snoop_records(&data) {
        Ok(r) => r,
        Err(e) => {
            cap.parse_errors.push(e.to_string());
            return cap;
        }
    };
    let mut acl = AclReassembler::new();
    let mut pending_read_handle: HashMap<u16, u16> = HashMap::new();
    for rec in recs {
        cap.records += 1;
        if rec.h4_type == H4_EVT {
            parse_event(&mut cap, &rec);
        } else if rec.h4_type == H4_ACL {
            if rec.payload.len() < 4 {
                continue;
            }
            let hdr = u16le(&rec.payload, 0);
            let handle = hdr & 0x0FFF;
            let pb = ((hdr >> 12) & 0x03) as u8;
            let body = &rec.payload[4..];
            for l2 in acl.feed(handle, pb, body) {
                if l2.len() < 4 {
                    continue;
                }
                let l2len = u16le(&l2, 0) as usize;
                let cid = u16le(&l2, 2);
                let end = (4 + l2len).min(l2.len());
                let att_raw = &l2[4..end];
                if cid != ATT_CID {
                    continue;
                }
                let peer = cap.conn_peer.get(&handle).cloned().unwrap_or_default();
                let (op, mut att_handle, value) = parse_att_pdu(att_raw);
                if op == ATT_READ_REQ {
                    if let Some(h) = att_handle {
                        pending_read_handle.insert(handle, h);
                    }
                }
                if op == ATT_READ_RSP {
                    att_handle = pending_read_handle.remove(&handle);
                }
                let pdu = AttPdu {
                    rec: rec.index,
                    timestamp: rec.timestamp.clone(),
                    direction: rec.direction.clone(),
                    conn: handle,
                    peer,
                    opcode: op,
                    opcode_name: att_name_owned(op),
                    handle: att_handle,
                    value,
                    raw: att_raw.to_vec(),
                };
                cap.att.push(pdu);
                if op == ATT_READ_BY_TYPE_RSP && att_raw.len() >= 2 {
                    let item_len = att_raw[1] as usize;
                    let blob = &att_raw[2..];
                    if item_len >= 7 {
                        cap.chars.extend(parse_char_decls(item_len, blob));
                    }
                }
                if op == ATT_READ_BY_GROUP_RSP && att_raw.len() >= 2 {
                    let item_len = att_raw[1] as usize;
                    let blob = &att_raw[2..];
                    let mut j = 0;
                    while j + item_len <= blob.len() {
                        let start_h = u16le(blob, j);
                        let end_h = u16le(blob, j + 2);
                        let uuid_b = &blob[j + 4..j + item_len];
                        let uuid_s = if uuid_b.len() == 2 {
                            format!("{:04X}", u16le(uuid_b, 0))
                        } else {
                            hex_of(uuid_b)
                        };
                        cap.services.push((start_h, end_h, uuid_s));
                        j += item_len;
                    }
                }
            }
        }
    }
    cap
}

fn parse_event(cap: &mut Capture, rec: &SnoopRecord) {
    let p = &rec.payload;
    if p.len() < 2 {
        return;
    }
    let code = p[0];
    let elen = p[1] as usize;
    let end = (2 + elen).min(p.len());
    let params = &p[2..end];
    if code == HCI_EVENT_DISCONN && params.len() >= 3 {
        let conn = u16le(params, 1) & 0x0FFF;
        cap.conn_peer.remove(&conn);
        return;
    }
    if code != HCI_EVENT_LE_META || params.is_empty() {
        return;
    }
    let sub = params[0];
    let rest = &params[1..];
    if (sub == LE_CONN_COMPLETE || sub == LE_ENHANCED_CONN) && rest.len() >= 10 {
        if rest[0] != 0 {
            return;
        }
        let conn = u16le(rest, 1) & 0x0FFF;
        let addr = &rest[5..11];
        let mac = mac_from_le(addr);
        cap.conn_peer.insert(conn, mac.clone());
        cap.le_conns
            .push((rec.timestamp.clone(), conn, mac));
        return;
    }
    if sub == LE_ADV_REPORT && !rest.is_empty() {
        let num = rest[0] as usize;
        let mut i = 1;
        for _ in 0..num {
            if i + 8 > rest.len() {
                break;
            }
            let et = rest[i];
            let at = rest[i + 1];
            let addr = &rest[i + 2..i + 8];
            let dlen = rest[i + 8] as usize;
            i += 9;
            if i + dlen + 1 > rest.len() {
                break;
            }
            let adata = rest[i..i + dlen].to_vec();
            let mut rssi = rest[i + dlen] as i16;
            if rssi >= 128 {
                rssi -= 256;
            }
            i += dlen + 1;
            let mac = mac_from_le(addr);
            cap.adv.push(AdvReport {
                rec: rec.index,
                timestamp: rec.timestamp.clone(),
                event_type: et,
                event_name: adv_event_name(et),
                addr_type: at,
                mac,
                rssi,
                ads: parse_ad_structures(&adata),
                data: adata,
            });
        }
    }
}

pub fn find_cfa(root: &Path) -> Vec<PathBuf> {
    let mut files: Vec<PathBuf> = WalkDir::new(root)
        .into_iter()
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_path_buf())
        .filter(|p| {
            p.is_file()
                && p.extension()
                    .and_then(|s| s.to_str())
                    .map(|s| s.eq_ignore_ascii_case("cfa"))
                    .unwrap_or(false)
        })
        .collect();
    files.sort();
    files
}

pub fn value_handles(cap: &Capture) -> HashMap<&'static str, Option<u16>> {
    let mut fff5 = None;
    let mut fff3 = None;
    let mut cccd = None;
    for ch in &cap.chars {
        if ch.uuid16 == Some(UUID_FFF5) {
            fff5 = Some(ch.value_handle);
        } else if ch.uuid16 == Some(UUID_FFF3) {
            fff3 = Some(ch.value_handle);
        }
    }
    if let Some(h) = fff3 {
        cccd = Some(h + 1);
    }
    for pdu in &cap.att {
        if matches!(pdu.opcode, ATT_WRITE_REQ | ATT_WRITE_CMD) {
            if pdu.value == [0x01, 0x00] {
                if let (Some(h), Some(f3)) = (pdu.handle, fff3) {
                    if h == f3 + 1 {
                        cccd = Some(h);
                    }
                }
            }
        }
    }
    let mut m = HashMap::new();
    m.insert("FFF5", fff5);
    m.insert("FFF3", fff3);
    m.insert("CCCD", cccd);
    m
}

pub fn is_target(mac: &str) -> bool {
    mac_norm(mac) == TARGET_MAC
}

pub fn att_control_notify(cap: &Capture) -> (Vec<AttPdu>, Vec<AttPdu>, Vec<AttPdu>) {
    let hs = value_handles(cap);
    let fff5 = hs.get("FFF5").copied().flatten();
    let fff3 = hs.get("FFF3").copied().flatten();
    let cccd = hs.get("CCCD").copied().flatten();
    let mut writes = Vec::new();
    let mut notifs = Vec::new();
    let mut cccds = Vec::new();
    for p in &cap.att {
        if !p.peer.is_empty() && !is_target(&p.peer) {
            continue;
        }
        if matches!(p.opcode, ATT_WRITE_REQ | ATT_WRITE_CMD) && Some(p.handle.unwrap_or(0)) == fff5 && fff5.is_some() {
            writes.push(p.clone());
        } else if p.opcode == ATT_NOTIFY && Some(p.handle.unwrap_or(0)) == fff3 && fff3.is_some() {
            notifs.push(p.clone());
        } else if matches!(p.opcode, ATT_WRITE_REQ | ATT_WRITE_CMD)
            && Some(p.handle.unwrap_or(0)) == cccd
            && cccd.is_some()
        {
            cccds.push(p.clone());
        } else if fff5.is_none()
            && matches!(p.opcode, ATT_WRITE_REQ | ATT_WRITE_CMD)
            && p.handle == Some(0x0021)
        {
            writes.push(p.clone());
        } else if fff3.is_none() && p.opcode == ATT_NOTIFY && p.handle == Some(0x0024) {
            notifs.push(p.clone());
        } else if cccd.is_none()
            && matches!(p.opcode, ATT_WRITE_REQ | ATT_WRITE_CMD)
            && p.handle == Some(0x0025)
        {
            cccds.push(p.clone());
        }
    }
    (writes, notifs, cccds)
}

pub fn unique_writes(writes: &[AttPdu]) -> Vec<Vec<u8>> {
    let mut seen = Vec::new();
    let mut got = HashSet::new();
    for w in writes {
        if got.insert(w.value.clone()) {
            seen.push(w.value.clone());
        }
    }
    seen
}

pub fn opcode_hist(pdus: &[AttPdu]) -> Vec<(i16, usize)> {
    let mut c: HashMap<i16, usize> = HashMap::new();
    for p in pdus {
        let key = if p.value.is_empty() {
            -1
        } else {
            p.value[0] as i16
        };
        *c.entry(key).or_insert(0) += 1;
    }
    let mut v: Vec<_> = c.into_iter().collect();
    v.sort_by_key(|(k, _)| *k);
    v
}

pub fn pair_writes_notifies(writes: &[AttPdu], notifs: &[AttPdu]) -> Vec<(AttPdu, Vec<AttPdu>)> {
    let mut events: Vec<(char, AttPdu)> = writes
        .iter()
        .map(|w| ('w', w.clone()))
        .chain(notifs.iter().map(|n| ('n', n.clone())))
        .collect();
    events.sort_by(|a, b| {
        a.1.rec
            .cmp(&b.1.rec)
            .then_with(|| if a.0 == 'w' { 0 } else { 1 }.cmp(&if b.0 == 'w' { 0 } else { 1 }))
    });
    let mut pairs = Vec::new();
    let mut i = 0;
    while i < events.len() {
        if events[i].0 != 'w' {
            i += 1;
            continue;
        }
        let wr = events[i].1.clone();
        let mut following = Vec::new();
        let mut j = i + 1;
        while j < events.len() && events[j].0 != 'w' {
            following.push(events[j].1.clone());
            j += 1;
        }
        pairs.push((wr, following));
        i = if j > i { j } else { i + 1 };
    }
    pairs
}

fn dt_ms(write_ts: &str, notify_ts: &str) -> Option<f64> {
    let w = chrono::DateTime::parse_from_str(write_ts, " %Y-%m-%dT%H:%M:%S%.fZ")
        .or_else(|_| chrono::DateTime::parse_from_str(write_ts, "%Y-%m-%dT%H:%M:%S%.fZ"));
    let n = chrono::DateTime::parse_from_str(notify_ts, "%Y-%m-%dT%H:%M:%S%.fZ");
    match (w, n) {
        (Ok(w), Ok(n)) => Some((n - w).num_nanoseconds().unwrap_or(0) as f64 / 1_000_000.0),
        _ => None,
    }
}

fn rel_name(cap: &Capture) -> String {
    if cap
        .path
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|s| s.to_str())
        == Some("old")
    {
        format!("old/{}", cap.path.file_name().unwrap().to_string_lossy())
    } else {
        cap.path
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned()
    }
}

fn csv_writer(path: impl AsRef<Path>) -> anyhow::Result<csv::Writer<fs::File>> {
    // Python-csv: lineterminator='\r\n' (unabhängig vom OS).
    Ok(csv::WriterBuilder::new()
        .has_headers(false)
        .terminator(csv::Terminator::CRLF)
        .from_path(path)?)
}

fn csv_write_row(w: &mut csv::Writer<fs::File>, row: &[&str]) -> anyhow::Result<()> {
    w.write_record(row)?;
    Ok(())
}

pub fn write_csvs(caps: &[Capture], outdir: &Path) -> anyhow::Result<()> {
    fs::create_dir_all(outdir)?;
    {
        let mut w = csv_writer(outdir.join("att.csv"))?;
        csv_write_row(
            &mut w,
            &[
                "file",
                "rec",
                "timestamp",
                "dir",
                "peer",
                "att_op",
                "att_name",
                "handle",
                "value_hex",
                "value_len",
                "first_byte",
            ],
        )?;
        for cap in caps {
            let rel = rel_name(cap);
            for p in &cap.att {
                let keep = matches!(
                    p.opcode,
                    ATT_WRITE_REQ
                        | ATT_WRITE_CMD
                        | ATT_NOTIFY
                        | ATT_INDICATE
                        | ATT_WRITE_RSP
                        | ATT_MTU_REQ
                        | ATT_MTU_RSP
                ) || matches!(p.handle, Some(0x0021) | Some(0x0024) | Some(0x0025) | None)
                    || matches!(p.opcode, ATT_READ_BY_TYPE_RSP | ATT_READ_BY_GROUP_RSP);
                // Python: skip if opcode not in list AND handle not in (0x21, 0x24, 0x25, None) AND opcode not read-by-type/group
                let in_main = matches!(
                    p.opcode,
                    ATT_WRITE_REQ
                        | ATT_WRITE_CMD
                        | ATT_NOTIFY
                        | ATT_INDICATE
                        | ATT_WRITE_RSP
                        | ATT_MTU_REQ
                        | ATT_MTU_RSP
                );
                if !in_main {
                    let handle_ok = matches!(p.handle, Some(0x0021) | Some(0x0024) | Some(0x0025) | None);
                    let disc = matches!(p.opcode, ATT_READ_BY_TYPE_RSP | ATT_READ_BY_GROUP_RSP);
                    if !handle_ok && !disc {
                        continue;
                    }
                }
                let _ = keep;
                csv_write_row(
                    &mut w,
                    &[
                        &rel,
                        &p.rec.to_string(),
                        &p.timestamp,
                        &p.direction,
                        &p.peer,
                        &format!("0x{:02X}", p.opcode),
                        &p.opcode_name,
                        &p.handle
                            .map(|h| format!("0x{h:04X}"))
                            .unwrap_or_default(),
                        &hex_of(&p.value),
                        &p.value.len().to_string(),
                        &if p.value.is_empty() {
                            String::new()
                        } else {
                            format!("0x{:02X}", p.value[0])
                        },
                    ],
                )?;
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("att_fff5_fff3.csv"))?;
        csv_write_row(
            &mut w,
            &[
                "file",
                "rec",
                "timestamp",
                "kind",
                "peer",
                "handle",
                "opcode_byte",
                "value_hex",
                "value_len",
            ],
        )?;
        for cap in caps {
            let rel = rel_name(cap);
            let (writes, notifs, cccds) = att_control_notify(cap);
            for (kind, lst) in [("CCCD", &cccds), ("FFF5-Write", &writes), ("FFF3-Notify", &notifs)] {
                for p in lst {
                    csv_write_row(
                        &mut w,
                        &[
                            &rel,
                            &p.rec.to_string(),
                            &p.timestamp,
                            kind,
                            &p.peer,
                            &p.handle
                                .map(|h| format!("0x{h:04X}"))
                                .unwrap_or_default(),
                            &if p.value.is_empty() {
                                String::new()
                            } else {
                                format!("0x{:02X}", p.value[0])
                            },
                            &hex_of(&p.value),
                            &p.value.len().to_string(),
                        ],
                    )?;
                }
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("adv.csv"))?;
        csv_write_row(
            &mut w,
            &[
                "file",
                "rec",
                "timestamp",
                "mac",
                "target",
                "event",
                "rssi",
                "ad_hex",
                "name",
                "uuids16",
                "mfg_hex",
                "mfg_company",
            ],
        )?;
        for cap in caps {
            let rel = rel_name(cap);
            let mut seen_keys = HashSet::new();
            for a in &cap.adv {
                let key = (a.mac.clone(), a.event_type, a.data.clone());
                if !is_target(&a.mac) && seen_keys.contains(&key) {
                    continue;
                }
                seen_keys.insert(key);
                let mut name = String::new();
                let mut uuids = Vec::new();
                let mut mfg = Vec::new();
                let mut company = String::new();
                for (t, v) in &a.ads {
                    if *t == 0x08 || *t == 0x09 {
                        name = String::from_utf8_lossy(v).into_owned();
                    } else if *t == 0x02 || *t == 0x03 {
                        let mut k = 0;
                        while k + 2 <= v.len() {
                            uuids.push(format!("{:04X}", u16le(v, k)));
                            k += 2;
                        }
                    } else if *t == 0xFF {
                        mfg = v.clone();
                        if v.len() >= 2 {
                            company = format!("0x{:04X}", u16le(v, 0));
                        }
                    }
                }
                csv_write_row(
                    &mut w,
                    &[
                        &rel,
                        &a.rec.to_string(),
                        &a.timestamp,
                        &a.mac,
                        if is_target(&a.mac) { "yes" } else { "no" },
                        &a.event_name,
                        &a.rssi.to_string(),
                        &hex_of(&a.data),
                        &name,
                        &uuids.join(" "),
                        &hex_of(&mfg),
                        &company,
                    ],
                )?;
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("unique_writes.csv"))?;
        csv_write_row(&mut w, &["file", "count", "first_byte", "len", "value_hex"])?;
        for cap in caps {
            let rel = rel_name(cap);
            let (writes, _, _) = att_control_notify(cap);
            let mut counts: HashMap<Vec<u8>, usize> = HashMap::new();
            for p in &writes {
                *counts.entry(p.value.clone()).or_insert(0) += 1;
            }
            let mut items: Vec<_> = counts.into_iter().collect();
            items.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
            for (val, n) in items {
                csv_write_row(
                    &mut w,
                    &[
                        &rel,
                        &n.to_string(),
                        &if val.is_empty() {
                            String::new()
                        } else {
                            format!("0x{:02X}", val[0])
                        },
                        &val.len().to_string(),
                        &hex_of(&val),
                    ],
                )?;
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("pairs.csv"))?;
        csv_write_row(
            &mut w,
            &[
                "file",
                "write_rec",
                "write_ts",
                "write_hex",
                "write_len",
                "write_op",
                "n_notifies",
                "notify_rec",
                "notify_ts",
                "notify_hex",
                "notify_len",
                "notify_op",
                "dt_ms",
                "echo",
            ],
        )?;
        for cap in caps {
            let rel = rel_name(cap);
            let (writes, notifs, _) = att_control_notify(cap);
            for (wr, ns) in pair_writes_notifies(&writes, &notifs) {
                if ns.is_empty() {
                    csv_write_row(
                        &mut w,
                        &[
                            &rel,
                            &wr.rec.to_string(),
                            &wr.timestamp,
                            &hex_of(&wr.value),
                            &wr.value.len().to_string(),
                            &if wr.value.is_empty() {
                                String::new()
                            } else {
                                format!("0x{:02X}", wr.value[0])
                            },
                            "0",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "no",
                        ],
                    )?;
                    continue;
                }
                for n in &ns {
                    let dt = dt_ms(&wr.timestamp, &n.timestamp);
                    let echo = if !wr.value.is_empty()
                        && !n.value.is_empty()
                        && wr.value[0] == n.value[0]
                    {
                        "yes"
                    } else {
                        "no"
                    };
                    csv_write_row(
                        &mut w,
                        &[
                            &rel,
                            &wr.rec.to_string(),
                            &wr.timestamp,
                            &hex_of(&wr.value),
                            &wr.value.len().to_string(),
                            &if wr.value.is_empty() {
                                String::new()
                            } else {
                                format!("0x{:02X}", wr.value[0])
                            },
                            &ns.len().to_string(),
                            &n.rec.to_string(),
                            &n.timestamp,
                            &hex_of(&n.value),
                            &n.value.len().to_string(),
                            &if n.value.is_empty() {
                                String::new()
                            } else {
                                format!("0x{:02X}", n.value[0])
                            },
                            &dt.map(|d| format!("{d:.1}")).unwrap_or_default(),
                            echo,
                        ],
                    )?;
                }
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("opcodes.csv"))?;
        csv_write_row(&mut w, &["file", "channel", "first_byte", "count"])?;
        for cap in caps {
            let rel = rel_name(cap);
            let (writes, notifs, _) = att_control_notify(cap);
            for (ch, lst) in [("FFF5-Write", &writes), ("FFF3-Notify", &notifs)] {
                for (opb, n) in opcode_hist(lst) {
                    csv_write_row(
                        &mut w,
                        &[
                            &rel,
                            ch,
                            &if opb >= 0 {
                                format!("0x{opb:02X}")
                            } else {
                                String::new()
                            },
                            &n.to_string(),
                        ],
                    )?;
                }
            }
        }
        w.flush()?;
    }
    {
        let mut w = csv_writer(outdir.join("summary.csv"))?;
        csv_write_row(
            &mut w,
            &[
                "file",
                "size",
                "records",
                "datalink",
                "le_conns",
                "adv_target",
                "adv_other",
                "fff5_writes",
                "fff3_notifies",
                "FFF5",
                "FFF3",
                "CCCD",
                "hints",
                "errors",
            ],
        )?;
        for cap in caps {
            let rel = rel_name(cap);
            let hs = value_handles(cap);
            let (writes, notifs, _) = att_control_notify(cap);
            let adv_t = cap.adv.iter().filter(|a| is_target(&a.mac)).count();
            let adv_o = cap.adv.len() - adv_t;
            csv_write_row(
                &mut w,
                &[
                    &rel,
                    &cap.size.to_string(),
                    &cap.records.to_string(),
                    &cap.datalink.to_string(),
                    &cap.le_conns.len().to_string(),
                    &adv_t.to_string(),
                    &adv_o.to_string(),
                    &writes.len().to_string(),
                    &notifs.len().to_string(),
                    &hs.get("FFF5")
                        .and_then(|h| *h)
                        .map(|h| format!("0x{h:04X}"))
                        .unwrap_or_default(),
                    &hs.get("FFF3")
                        .and_then(|h| *h)
                        .map(|h| format!("0x{h:04X}"))
                        .unwrap_or_default(),
                    &hs.get("CCCD")
                        .and_then(|h| *h)
                        .map(|h| format!("0x{h:04X}"))
                        .unwrap_or_default(),
                    &cap.strings_hint.join("; "),
                    &cap.parse_errors.join("; "),
                ],
            )?;
        }
        w.flush()?;
    }
    Ok(())
}

fn py_opt_u16(v: Option<u16>) -> String {
    match v {
        Some(n) => n.to_string(),
        None => "None".into(),
    }
}

fn py_list(items: &[String]) -> String {
    format!(
        "[{}]",
        items
            .iter()
            .map(|s| format!("'{s}'"))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn py_conns(conns: &[(String, u16, String)]) -> String {
    format!(
        "[{}]",
        conns
            .iter()
            .map(|(ts, handle, mac)| format!("('{ts}', {handle}, '{mac}')"))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn py_services(services: &[(u16, u16, String)]) -> String {
    format!(
        "[{}]",
        services
            .iter()
            .map(|(a, b, uuid)| format!("({a}, {b}, '{uuid}')"))
            .collect::<Vec<_>>()
            .join(", ")
    )
}

fn py_hist(hist: &[(i16, usize)]) -> String {
    if hist.is_empty() {
        return "{}".into();
    }
    let inner = hist
        .iter()
        .map(|(k, n)| {
            let key = if *k < 0 {
                "-1".to_string()
            } else {
                format!("{:#x}", *k as u8)
            };
            format!("'{key}': {n}")
        })
        .collect::<Vec<_>>()
        .join(", ");
    format!("{{{inner}}}")
}

pub fn print_summary(caps: &[Capture]) {
    for cap in caps {
        let rel = cap.path.to_string_lossy();
        let hs = value_handles(cap);
        let (writes, notifs, cccds) = att_control_notify(cap);
        println!("\n=== {rel} ===");
        println!(
            "  size={} records={} datalink={}",
            cap.size, cap.records, cap.datalink
        );
        println!("  hints={}", py_list(&cap.strings_hint));
        println!("  conns={}", py_conns(&cap.le_conns));
        println!("  services={}", py_services(&cap.services));
        println!(
            "  handles FFF5={} FFF3={} CCCD={}",
            py_opt_u16(hs.get("FFF5").and_then(|h| *h)),
            py_opt_u16(hs.get("FFF3").and_then(|h| *h)),
            py_opt_u16(hs.get("CCCD").and_then(|h| *h)),
        );
        let chars: Vec<String> = cap
            .chars
            .iter()
            .map(|c| {
                let uuid = c
                    .uuid16
                    .map(|u| format!("'{u:04X}'"))
                    .unwrap_or_else(|| format!("'{}'", c.uuid_hex));
                format!("({}, {}, {})", c.value_handle, uuid, c.decl_handle)
            })
            .collect();
        println!("  chars=[{}]", chars.join(", "));
        println!(
            "  CCCD writes={} FFF5={} FFF3={}",
            cccds.len(),
            writes.len(),
            notifs.len()
        );
        println!("  unique FFF5: {}", unique_writes(&writes).len());
        for val in unique_writes(&writes) {
            let n = writes.iter().filter(|p| p.value == val).count();
            println!("    n={n:4} len={:2} {}", val.len(), hex_of(&val));
        }
        let hist_n = opcode_hist(&notifs);
        println!("  FFF3 first-byte: {}", py_hist(&hist_n));
        let tadv: Vec<_> = cap.adv.iter().filter(|a| is_target(&a.mac)).collect();
        println!("  adv target={} other={}", tadv.len(), cap.adv.len() - tadv.len());
        let mut shown = HashSet::new();
        for a in tadv {
            let key = (a.event_type, a.data.clone());
            if shown.contains(&key) {
                continue;
            }
            shown.insert(key);
            let ads: Vec<String> = a
                .ads
                .iter()
                .map(|(t, v)| {
                    let val = if *t == 0x08 || *t == 0x09 {
                        String::from_utf8_lossy(v).into_owned()
                    } else {
                        hex_of(v)
                    };
                    format!("{}={val}", ad_type_name(*t))
                })
                .collect();
            println!(
                "    {} rssi={} {}",
                a.event_name,
                a.rssi,
                ads.join("; ")
            );
        }
    }
}
