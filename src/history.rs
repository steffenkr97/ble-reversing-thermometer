//! History-Dump ohne BLE: Pages, CSV, Extract-Import, Zeit-Hypothese.
//!
//! App-Sequenz und Framing: hci-logs/05-history-07.md, hci-logs/10-history-dump.md.
//! Nur Opcodes 1A / 01 / 07. Intervall 600 s ist Hypothese, kein Fakt.

use std::collections::HashMap;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::csvutil::{fmt_float, format_iso_utc, parse_iso_utc};
use crate::error::{Error, Result};
use crate::mac::{mac12, normalize_mac, parse_hex_bytes};
use crate::parse::{parse_fff3, Fff3, History07, TARGET_MAC};

pub const HISTORY_COLUMNS: [&str; 7] = [
    "mac",
    "index",
    "record",
    "temp_c",
    "humidity_rh",
    "raw_hex",
    "timestamp_inferred",
];

pub const PAGE_RECORDS: u16 = 3;
/// Hypothese: ADV-Counter 949579 / Count 1583 ≈ 599,86 s → 10 min.
pub const INTERVAL_SEC_HYPOTHESIS: f64 = 600.0;
pub const ALLOWED_WRITE_OPCODES: [u8; 3] = [0x1A, 0x01, 0x07];
pub const BLACKLIST_WRITE_OPCODES: [u8; 6] = [0x04, 0x05, 0x0F, 0x18, 0x19, 0xF3];
pub const EXTRACT_ATT_NAME: &str = "att_fff5_fff3.csv";

#[derive(Debug, Clone)]
pub struct HistoryRow {
    pub mac: String,
    pub index: i64,
    pub record: i64,
    pub temp_c: f64,
    pub humidity_rh: f64,
    pub raw_hex: String,
    pub timestamp_inferred: String,
}

#[derive(Debug, Clone, Default)]
pub struct ExtractMeta {
    pub file: Option<String>,
    pub sample_count: usize,
    pub page_count: usize,
    pub count_01: Option<u16>,
    pub first_ts: Option<String>,
    pub last_ts: Option<String>,
    pub att_path: PathBuf,
    pub newest_index: Option<i64>,
}

/// Pfad data/history_<mac12>.csv (eine Datei pro Gerät, Dump ersetzt sie).
pub fn default_history_csv_path(mac: &str, outdir: impl AsRef<Path>) -> PathBuf {
    outdir.as_ref().join(format!("history_{}.csv", mac12(mac)))
}

/// Write-Plan wie die App: count=03 in 3er-Schritten, Rest als count=01.
/// Niemals count=02 — in den Captures kommt das nicht vor.
pub fn page_plan(sample_count: i64) -> Result<Vec<(u16, u8)>> {
    if sample_count < 0 {
        return Err(Error::NegativeSampleCount);
    }
    let sample_count = sample_count as u32;
    let full = sample_count / u32::from(PAGE_RECORDS);
    let rem = sample_count % u32::from(PAGE_RECORDS);
    let mut pages = Vec::new();
    for i in 0..full {
        pages.push(((i * u32::from(PAGE_RECORDS)) as u16, PAGE_RECORDS as u8));
    }
    for extra in 0..rem {
        pages.push((
            (full * u32::from(PAGE_RECORDS) + extra) as u16,
            1,
        ));
    }
    Ok(pages)
}

/// Nur beobachtete App-Writes: 1A, 01, oder 07 mit 6 Byte und count 01/03.
pub fn assert_allowed_fff5_write(payload: &[u8]) -> Result<()> {
    if payload.is_empty() {
        return Err(Error::EmptyWrite);
    }
    let opcode = payload[0];
    if BLACKLIST_WRITE_OPCODES.contains(&opcode) {
        return Err(Error::BlacklistOpcode(opcode));
    }
    if !ALLOWED_WRITE_OPCODES.contains(&opcode) {
        return Err(Error::UnknownOpcode(opcode));
    }
    if opcode == 0x07 {
        if payload.len() != 6 {
            return Err(Error::HistoryWriteLen(payload.len()));
        }
        if payload[3..5] != [0x00, 0x00] {
            return Err(Error::HistoryWritePadding);
        }
        if payload[5] != 1 && payload[5] != 3 {
            return Err(Error::HistoryWriteCount(payload[5]));
        }
    } else if payload.len() != 1 {
        return Err(Error::SingleByteWrite(opcode));
    }
    Ok(())
}

/// Eine 07-Page → eine Zeile pro Record. index = Page-Index + Record.
pub fn samples_from_page(parsed: &History07, mac: &str) -> Vec<HistoryRow> {
    let raw_hex = parsed.raw_hex.replace(' ', "").to_lowercase();
    let mac_n = normalize_mac(mac);
    parsed
        .records
        .iter()
        .enumerate()
        .map(|(rec_i, (temp_c, humidity_rh))| HistoryRow {
            mac: mac_n.clone(),
            index: i64::from(parsed.index) + rec_i as i64,
            record: rec_i as i64,
            temp_c: *temp_c,
            humidity_rh: *humidity_rh,
            raw_hex: raw_hex.clone(),
            timestamp_inferred: String::new(),
        })
        .collect()
}

pub fn samples_from_pages(pages: &[History07], mac: &str) -> Vec<HistoryRow> {
    let mut rows = Vec::new();
    for page in pages {
        rows.extend(samples_from_page(page, mac));
    }
    rows.sort_by_key(|item| (item.index, item.record));
    rows
}

/// timestamp_inferred: neuestes Sample ≈ newest_utc, ältere um interval_sec versetzt.
///
/// Hypothese, keine Geräte-Wanduhr. newest_index = Count-1 (nicht max der Teilmenge).
pub fn apply_inferred_timestamps(
    rows: &[HistoryRow],
    newest_utc: &str,
    interval_sec: f64,
    newest_index: Option<i64>,
) -> Result<Vec<HistoryRow>> {
    if interval_sec <= 0.0 {
        return Err(Error::NonPositiveInterval);
    }
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let newest = parse_iso_utc(newest_utc)?;
    let newest_index = newest_index.unwrap_or_else(|| rows.iter().map(|r| r.index).max().unwrap_or(0));
    let mut out = Vec::with_capacity(rows.len());
    for row in rows {
        let mut item = row.clone();
        let delta = (newest_index - item.index) as f64 * interval_sec;
        let micros = (delta * 1_000_000.0).round() as i64;
        let ts = newest - chrono::Duration::microseconds(micros);
        item.timestamp_inferred = format_iso_utc(ts);
        out.push(item);
    }
    Ok(out)
}

/// ADV-Counter / Count → Sekunden/Sample. Hypothese, siehe 10-history-dump.md.
pub fn interval_from_count_and_counter(sample_count: i64, adv_counter: i64) -> Option<f64> {
    if sample_count <= 0 || adv_counter <= 0 {
        return None;
    }
    Some(adv_counter as f64 / sample_count as f64)
}

/// Dump komplett schreiben (überschreibt). Header immer HISTORY_COLUMNS.
pub fn write_history_csv(path: impl AsRef<Path>, rows: &[HistoryRow]) -> Result<()> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }
    let mut f = File::create(path)?;
    writeln!(f, "{}", HISTORY_COLUMNS.join(","))?;
    for row in rows {
        writeln!(
            f,
            "{},{},{},{},{},{},{}",
            row.mac,
            row.index,
            row.record,
            fmt_float(row.temp_c),
            fmt_float(row.humidity_rh),
            row.raw_hex.replace(' ', "").to_lowercase(),
            row.timestamp_inferred,
        )?;
    }
    Ok(())
}

pub fn extract_file_is_old(file_name: &str) -> bool {
    let name = file_name.replace('\\', "/");
    name.starts_with("old/") || name.contains("/old/")
}

pub fn resolve_extract_att_path(path: impl AsRef<Path>) -> PathBuf {
    let path = path.as_ref();
    if path.is_dir() {
        path.join(EXTRACT_ATT_NAME)
    } else {
        path.to_path_buf()
    }
}

struct FileBucket {
    pages: HashMap<u16, History07>,
    counts: Vec<u16>,
    first_ts: Option<String>,
    last_ts: Option<String>,
}

/// FFF3-Notify 0x07 aus att_fff5_fff3.csv. Längster Capture-Dump (nicht old/).
pub fn load_extract_history(
    path: impl AsRef<Path>,
    mac: &str,
    skip_old: bool,
) -> Result<(Vec<HistoryRow>, ExtractMeta)> {
    let att_path = resolve_extract_att_path(path);
    if !att_path.is_file() {
        return Err(Error::Io(std::io::Error::new(
            std::io::ErrorKind::NotFound,
            att_path.display().to_string(),
        )));
    }
    let mac_n = normalize_mac(mac);
    let mut by_file: HashMap<String, FileBucket> = HashMap::new();
    let mut rdr = csv::Reader::from_path(&att_path)?;
    for rec in rdr.deserialize() {
        let row: HashMap<String, String> = rec?;
        let file_name = row.get("file").cloned().unwrap_or_default();
        if skip_old && extract_file_is_old(&file_name) {
            continue;
        }
        let peer = normalize_mac(row.get("peer").map(|s| s.as_str()).unwrap_or(""));
        if peer != mac_n {
            continue;
        }
        if row.get("kind").map(|s| s.as_str()).unwrap_or("") != "FFF3-Notify" {
            continue;
        }
        let Some(raw) = parse_hex_bytes(row.get("value_hex").map(|s| s.as_str()).unwrap_or("")) else {
            continue;
        };
        let parsed = parse_fff3(&raw);
        let bucket = by_file.entry(file_name).or_insert_with(|| FileBucket {
            pages: HashMap::new(),
            counts: Vec::new(),
            first_ts: None,
            last_ts: None,
        });
        let ts = row
            .get("timestamp")
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        match parsed {
            Some(Fff3::History(h)) => {
                bucket.pages.entry(h.index).or_insert(h);
                if bucket.first_ts.is_none() {
                    bucket.first_ts = ts.clone();
                }
                bucket.last_ts = ts;
            }
            Some(Fff3::Count(c)) => {
                bucket.counts.push(c.sample_count);
                if ts.is_some() && bucket.last_ts.is_none() {
                    bucket.last_ts = ts;
                }
            }
            _ => {}
        }
    }

    if by_file.is_empty() {
        return Ok((
            Vec::new(),
            ExtractMeta {
                att_path,
                ..ExtractMeta::default()
            },
        ));
    }

    let (file_name, bucket) = by_file
        .into_iter()
        .max_by(|(fn_a, a), (fn_b, b)| {
            let n_a: usize = a.pages.values().map(|p| p.records.len()).sum();
            let n_b: usize = b.pages.values().map(|p| p.records.len()).sum();
            n_a.cmp(&n_b)
                .then_with(|| a.pages.len().cmp(&b.pages.len()))
                .then_with(|| fn_a.cmp(fn_b))
        })
        .expect("by_file nicht leer");

    let mut indices: Vec<u16> = bucket.pages.keys().copied().collect();
    indices.sort_unstable();
    let pages: Vec<History07> = indices
        .into_iter()
        .filter_map(|idx| bucket.pages.get(&idx).cloned())
        .collect();
    let rows = samples_from_pages(&pages, &mac_n);
    let count_01 = bucket.counts.last().copied();
    let newest_index = if let Some(c) = count_01 {
        Some(i64::from(c) - 1)
    } else {
        rows.last().map(|r| r.index)
    };
    let meta = ExtractMeta {
        file: Some(file_name),
        sample_count: rows.len(),
        page_count: pages.len(),
        count_01,
        first_ts: bucket.first_ts,
        last_ts: bucket.last_ts,
        att_path,
        newest_index,
    };
    Ok((rows, meta))
}

pub fn load_extract_history_default(
    path: impl AsRef<Path>,
) -> Result<(Vec<HistoryRow>, ExtractMeta)> {
    load_extract_history(path, TARGET_MAC, true)
}
