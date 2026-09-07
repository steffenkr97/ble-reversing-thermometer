//! Dashboard-Datenlage: Live-CSV, History-CSV, HCI-Extracts (nur Lesen).

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use regex::Regex;
use serde::Serialize;

use crate::history::extract_file_is_old;
use crate::mac::{normalize_mac, parse_hex_bytes};
use crate::parse::{parse_adv_manufacturer, parse_fff3, Fff3};
use crate::rooms::{
    allowlist_macs, encoding_checked_macs, room_by_mac, Room,
};
pub use crate::rooms::load_rooms;
use crate::store::COLUMNS;

pub const SOURCE_ADV: &str = "adv";
pub const SOURCE_HISTORY: &str = "history";
pub const SOURCE_ADV_CAPTURE: &str = "adv_capture";
pub const SOURCE_HISTORY_CAPTURE: &str = "history_capture";
pub const KNOWN_SOURCES: [&str; 4] = [
    SOURCE_ADV,
    SOURCE_HISTORY,
    SOURCE_ADV_CAPTURE,
    SOURCE_HISTORY_CAPTURE,
];

#[derive(Debug, Clone, Serialize)]
pub struct Sample {
    pub timestamp: Option<String>,
    pub mac: String,
    pub temp_c: f64,
    pub humidity_rh: f64,
    pub source: String,
    pub raw_hex: String,
    pub index: Option<i64>,
    pub record: Option<i64>,
    pub room: Option<String>,
    pub file: Option<String>,
    pub room_id: Option<String>,
}

fn live_csv_re() -> Regex {
    Regex::new(r"^thermo_([0-9a-f]{12})_(\d{4}-\d{2}-\d{2})\.csv$").unwrap()
}

fn history_csv_re() -> Regex {
    Regex::new(r"^history_([0-9a-f]{12})\.csv$").unwrap()
}

fn parse_float(value: Option<&str>) -> Option<f64> {
    let v = value?;
    if v.is_empty() {
        return None;
    }
    v.parse().ok()
}

fn sample(
    timestamp: Option<String>,
    mac: &str,
    temp_c: f64,
    humidity_rh: f64,
    source: &str,
    raw_hex: &str,
    index: Option<i64>,
    record: Option<i64>,
    file_name: Option<&str>,
) -> Sample {
    Sample {
        timestamp,
        mac: normalize_mac(mac),
        temp_c,
        humidity_rh,
        source: source.to_string(),
        raw_hex: raw_hex.replace(' ', "").to_lowercase(),
        index,
        record,
        room: None,
        file: file_name.map(|s| s.to_string()),
        room_id: None,
    }
}

fn attach_room(mut s: Sample, rooms: &[Room]) -> Sample {
    if let Some(found) = room_by_mac(rooms, &s.mac) {
        s.room = Some(found.name.clone());
        s.room_id = Some(found.id.clone());
    } else {
        s.room = None;
        s.room_id = None;
    }
    s
}

/// Collector-CSV: timestamp, mac, temp_c, humidity_rh, raw_hex.
pub fn read_live_csv(path: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let path = path.as_ref();
    let allowed: HashSet<String> = allowlist_macs(rooms).into_iter().collect();
    let file_name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let mut samples = Vec::new();
    let Ok(mut rdr) = csv::Reader::from_path(path) else {
        return samples;
    };
    let headers = match rdr.headers() {
        Ok(h) => h.clone(),
        Err(_) => return samples,
    };
    let fields: HashSet<String> = headers.iter().map(|s| s.trim().to_string()).collect();
    if COLUMNS.iter().any(|c| !fields.contains(*c)) {
        return samples;
    }
    for rec in rdr.deserialize() {
        let Ok(row): Result<HashMap<String, String>, _> = rec else {
            continue;
        };
        let mac = normalize_mac(row.get("mac").map(|s| s.as_str()).unwrap_or(""));
        if !allowed.is_empty() && !allowed.contains(&mac) {
            continue;
        }
        let Some(temp_c) = parse_float(row.get("temp_c").map(|s| s.as_str())) else {
            continue;
        };
        let Some(humidity_rh) = parse_float(row.get("humidity_rh").map(|s| s.as_str())) else {
            continue;
        };
        let ts = row
            .get("timestamp")
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        samples.push(attach_room(
            sample(
                ts,
                &mac,
                temp_c,
                humidity_rh,
                SOURCE_ADV,
                row.get("raw_hex").map(|s| s.as_str()).unwrap_or(""),
                None,
                None,
                Some(&file_name),
            ),
            rooms,
        ));
    }
    samples
}

/// History-Dump CSV: mac, index, record, temp_c, humidity_rh, raw_hex.
pub fn read_history_csv(path: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let path = path.as_ref();
    let allowed: HashSet<String> = allowlist_macs(rooms).into_iter().collect();
    let file_name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let mut samples = Vec::new();
    let Ok(mut rdr) = csv::Reader::from_path(path) else {
        return samples;
    };
    if rdr.headers().is_err() {
        return samples;
    }
    for rec in rdr.deserialize() {
        let Ok(row): Result<HashMap<String, String>, _> = rec else {
            continue;
        };
        let mac = normalize_mac(row.get("mac").map(|s| s.as_str()).unwrap_or(""));
        if !allowed.is_empty() && !allowed.contains(&mac) {
            continue;
        }
        let Some(temp_c) = parse_float(row.get("temp_c").map(|s| s.as_str())) else {
            continue;
        };
        let Some(humidity_rh) = parse_float(row.get("humidity_rh").map(|s| s.as_str())) else {
            continue;
        };
        let index = row
            .get("index")
            .map(|s| s.as_str())
            .filter(|s| !s.is_empty())
            .and_then(|s| s.parse().ok());
        let record = row
            .get("record")
            .map(|s| s.as_str())
            .filter(|s| !s.is_empty())
            .and_then(|s| s.parse().ok());
        let ts = row
            .get("timestamp_inferred")
            .filter(|s| !s.is_empty())
            .cloned()
            .or_else(|| row.get("timestamp").cloned())
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        samples.push(attach_room(
            sample(
                ts,
                &mac,
                temp_c,
                humidity_rh,
                SOURCE_HISTORY,
                row.get("raw_hex").map(|s| s.as_str()).unwrap_or(""),
                index,
                record,
                Some(&file_name),
            ),
            rooms,
        ));
    }
    samples
}

pub fn list_data_csvs(data_dir: impl AsRef<Path>) -> (Vec<PathBuf>, Vec<PathBuf>) {
    let mut live = Vec::new();
    let mut history = Vec::new();
    let data_dir = data_dir.as_ref();
    let Ok(rd) = fs::read_dir(data_dir) else {
        return (live, history);
    };
    let live_re = live_csv_re();
    let hist_re = history_csv_re();
    let mut names: Vec<_> = rd.filter_map(|e| e.ok()).collect();
    names.sort_by_key(|e| e.file_name());
    for entry in names {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let name = entry.file_name().to_string_lossy().to_string();
        if live_re.is_match(&name) {
            live.push(path);
        } else if hist_re.is_match(&name) {
            history.push(path);
        }
    }
    (live, history)
}

pub fn load_live_and_history(data_dir: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let mut samples = Vec::new();
    let (live_paths, history_paths) = list_data_csvs(data_dir);
    for path in live_paths {
        samples.extend(read_live_csv(path, rooms));
    }
    for path in history_paths {
        samples.extend(read_history_csv(path, rooms));
    }
    samples
}

/// HCI-Extract ADV_IND. Nur Allowlist + encoding_checked (Büro bis Display-Check).
pub fn read_extract_adv(path: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let path = path.as_ref();
    if !path.is_file() {
        return Vec::new();
    }
    let allowed: HashSet<String> = allowlist_macs(rooms).into_iter().collect();
    let checked: Vec<String> = encoding_checked_macs(rooms);
    let file_name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let mut samples = Vec::new();
    let Ok(mut rdr) = csv::Reader::from_path(path) else {
        return samples;
    };
    for rec in rdr.deserialize() {
        let Ok(row): Result<HashMap<String, String>, _> = rec else {
            continue;
        };
        if extract_file_is_old(row.get("file").map(|s| s.as_str()).unwrap_or("")) {
            continue;
        }
        if row.get("event").map(|s| s.as_str()).unwrap_or("") != "ADV_IND" {
            continue;
        }
        let mac = normalize_mac(row.get("mac").map(|s| s.as_str()).unwrap_or(""));
        if !allowed.is_empty() && !allowed.contains(&mac) {
            continue;
        }
        let mfg = row.get("mfg_hex").map(|s| s.trim().to_string()).unwrap_or_default();
        if mfg.is_empty() {
            continue;
        }
        let Some(frame) = parse_hex_bytes(&mfg) else {
            continue;
        };
        let allowed_slice = if checked.is_empty() {
            None
        } else {
            Some(checked.as_slice())
        };
        let Some(parsed) = parse_adv_manufacturer(&frame, allowed_slice) else {
            continue;
        };
        if !allowed.is_empty() && !allowed.contains(&parsed.mac) {
            continue;
        }
        let ts = row
            .get("timestamp")
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        samples.push(attach_room(
            sample(
                ts,
                &parsed.mac,
                parsed.temp_c,
                parsed.humidity_rh,
                SOURCE_ADV_CAPTURE,
                &parsed.raw_hex,
                None,
                None,
                Some(&file_name),
            ),
            rooms,
        ));
    }
    samples
}

/// HCI-Extract FFF3-Notify 0x07, nur Allowlist. Index 0 = älteste.
pub fn read_extract_history(path: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let path = path.as_ref();
    if !path.is_file() {
        return Vec::new();
    }
    let allowed: HashSet<String> = allowlist_macs(rooms).into_iter().collect();
    let file_name = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_string();
    let mut samples = Vec::new();
    let Ok(mut rdr) = csv::Reader::from_path(path) else {
        return samples;
    };
    for rec in rdr.deserialize() {
        let Ok(row): Result<HashMap<String, String>, _> = rec else {
            continue;
        };
        if extract_file_is_old(row.get("file").map(|s| s.as_str()).unwrap_or("")) {
            continue;
        }
        if row.get("kind").map(|s| s.as_str()).unwrap_or("") != "FFF3-Notify" {
            continue;
        }
        if row
            .get("opcode_byte")
            .map(|s| s.to_lowercase())
            .as_deref()
            != Some("0x07")
        {
            continue;
        }
        let mac = normalize_mac(row.get("peer").map(|s| s.as_str()).unwrap_or(""));
        if !allowed.is_empty() && !allowed.contains(&mac) {
            continue;
        }
        let Some(raw) = parse_hex_bytes(row.get("value_hex").map(|s| s.as_str()).unwrap_or("")) else {
            continue;
        };
        let Some(Fff3::History(parsed)) = parse_fff3(&raw) else {
            continue;
        };
        let capture_ts = row
            .get("timestamp")
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());
        for (rec_i, pair) in parsed.records.iter().enumerate() {
            samples.push(attach_room(
                sample(
                    capture_ts.clone(),
                    &mac,
                    pair.0,
                    pair.1,
                    SOURCE_HISTORY_CAPTURE,
                    &parsed.raw_hex,
                    Some(i64::from(parsed.index) + rec_i as i64),
                    Some(rec_i as i64),
                    Some(&file_name),
                ),
                rooms,
            ));
        }
    }
    dedupe_history_capture(samples)
}

fn dedupe_history_capture(samples: Vec<Sample>) -> Vec<Sample> {
    let mut best: HashMap<(String, i64), Sample> = HashMap::new();
    for sample in samples {
        let Some(index) = sample.index else {
            continue;
        };
        let key = (sample.mac.clone(), index);
        best.entry(key).or_insert(sample);
    }
    let mut ordered: Vec<Sample> = best.into_values().collect();
    ordered.sort_by(|a, b| {
        a.mac
            .cmp(&b.mac)
            .then_with(|| a.index.unwrap_or(0).cmp(&b.index.unwrap_or(0)))
    });
    ordered
}

pub fn load_extracts(extract_dir: impl AsRef<Path>, rooms: &[Room]) -> Vec<Sample> {
    let extract_dir = extract_dir.as_ref();
    let mut samples = read_extract_adv(extract_dir.join("adv.csv"), rooms);
    samples.extend(read_extract_history(
        extract_dir.join("att_fff5_fff3.csv"),
        rooms,
    ));
    samples
}

pub fn filter_samples<'a>(
    samples: impl IntoIterator<Item = &'a Sample>,
    mac: Option<&str>,
    source: Option<&str>,
    source_in: Option<&[&str]>,
) -> Vec<Sample> {
    let wanted_mac = mac.map(normalize_mac);
    let sources: Option<HashSet<String>> = if let Some(s) = source {
        Some(HashSet::from([s.to_string()]))
    } else {
        source_in.map(|xs| xs.iter().map(|s| (*s).to_string()).collect())
    };
    let mut out = Vec::new();
    for sample in samples {
        if let Some(ref want) = wanted_mac {
            if &sample.mac != want {
                continue;
            }
        }
        if let Some(ref srcs) = sources {
            if !srcs.contains(&sample.source) {
                continue;
            }
        }
        out.push(sample.clone());
    }
    out
}

#[derive(PartialEq, Eq, PartialOrd, Ord)]
enum SampleKey {
    Live(String, String, i64),
    Hist(String, i64, String),
}

pub fn sort_samples(mut samples: Vec<Sample>) -> Vec<Sample> {
    samples.sort_by_key(|s| {
        let hist = s.source == SOURCE_HISTORY || s.source == SOURCE_HISTORY_CAPTURE;
        if hist && s.index.is_some() {
            (
                1u8,
                SampleKey::Hist(
                    s.mac.clone(),
                    s.index.unwrap_or(0),
                    s.timestamp.clone().unwrap_or_default(),
                ),
            )
        } else {
            (
                0u8,
                SampleKey::Live(
                    s.mac.clone(),
                    s.timestamp.clone().unwrap_or_default(),
                    s.index.unwrap_or(-1),
                ),
            )
        }
    });
    samples
}

fn py_round_half_even(x: f64) -> i64 {
    let floor = x.floor();
    let diff = x - floor;
    if diff < 0.5 {
        floor as i64
    } else if diff > 0.5 {
        floor as i64 + 1
    } else {
        let n = floor as i64;
        if n % 2 == 0 {
            n
        } else {
            n + 1
        }
    }
}

/// Gleichmäßig ausdünnen, Endpunkte behalten. limit <= 0 → unverändert.
pub fn downsample(samples: &[Sample], limit: i64) -> Vec<Sample> {
    if limit <= 0 || (samples.len() as i64) <= limit {
        return samples.to_vec();
    }
    if limit == 1 {
        return vec![samples[samples.len() - 1].clone()];
    }
    let last_i = samples.len() - 1;
    let mut picked = Vec::new();
    let mut used = HashSet::new();
    for step in 0..limit {
        let idx = py_round_half_even(step as f64 * last_i as f64 / (limit - 1) as f64) as usize;
        let idx = idx.min(last_i);
        if used.contains(&idx) {
            continue;
        }
        used.insert(idx);
        picked.push(samples[idx].clone());
    }
    picked
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    pub count: usize,
    pub temp_c: Option<f64>,
    pub humidity_rh: Option<f64>,
    pub temp_min: Option<f64>,
    pub temp_max: Option<f64>,
    pub humidity_min: Option<f64>,
    pub humidity_max: Option<f64>,
    pub first_timestamp: Option<String>,
    pub last_timestamp: Option<String>,
    pub first_index: Option<i64>,
    pub last_index: Option<i64>,
}

pub fn summarize(samples: &[Sample]) -> Summary {
    if samples.is_empty() {
        return Summary {
            count: 0,
            temp_c: None,
            humidity_rh: None,
            temp_min: None,
            temp_max: None,
            humidity_min: None,
            humidity_max: None,
            first_timestamp: None,
            last_timestamp: None,
            first_index: None,
            last_index: None,
        };
    }
    let temps: Vec<f64> = samples.iter().map(|s| s.temp_c).collect();
    let hums: Vec<f64> = samples.iter().map(|s| s.humidity_rh).collect();
    let indexes: Vec<i64> = samples.iter().filter_map(|s| s.index).collect();
    let timestamps: Vec<String> = samples
        .iter()
        .filter_map(|s| s.timestamp.clone())
        .collect();
    Summary {
        count: samples.len(),
        temp_c: temps.last().copied(),
        humidity_rh: hums.last().copied(),
        temp_min: temps.iter().cloned().reduce(f64::min),
        temp_max: temps.iter().cloned().reduce(f64::max),
        humidity_min: hums.iter().cloned().reduce(f64::min),
        humidity_max: hums.iter().cloned().reduce(f64::max),
        first_timestamp: timestamps.first().cloned(),
        last_timestamp: timestamps.last().cloned(),
        first_index: indexes.iter().copied().min(),
        last_index: indexes.iter().copied().max(),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct EncodingInfo {
    pub scale: i32,
    pub temp: String,
    pub humidity: String,
    pub history_clock: String,
    pub history_interval_sec_hypothesis: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct RoomCounts {
    pub adv: usize,
    pub history: usize,
    pub adv_capture: usize,
    pub history_capture: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct RoomOverview {
    pub id: String,
    pub name: String,
    pub mac: String,
    pub confirmed: bool,
    pub encoding_checked: bool,
    pub note: Option<String>,
    pub latest: Option<Sample>,
    pub counts: RoomCounts,
    pub summary_live: Summary,
    pub summary_history: Summary,
}

#[derive(Debug, Clone, Serialize)]
pub struct Overview {
    pub rooms: Vec<RoomOverview>,
    pub sources: Vec<String>,
    pub live_csv_count: usize,
    pub history_csv_count: usize,
    pub sample_count: usize,
    pub encoding: EncodingInfo,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct QueryResult {
    pub mac: Option<String>,
    pub source: Option<String>,
    pub count: usize,
    pub returned: usize,
    pub summary: Summary,
    pub samples: Vec<Sample>,
}

pub struct DashStore {
    pub data_dir: PathBuf,
    pub rooms_path: PathBuf,
    pub extract_dir: Option<PathBuf>,
    pub include_extract: bool,
    stamp: Option<Vec<(PathBuf, Option<SystemTime>)>>,
    pub rooms: Vec<Room>,
    pub samples: Vec<Sample>,
}

impl DashStore {
    pub fn new(
        data_dir: PathBuf,
        rooms_path: PathBuf,
        extract_dir: Option<PathBuf>,
        include_extract: bool,
    ) -> Self {
        Self {
            data_dir,
            rooms_path,
            extract_dir,
            include_extract,
            stamp: None,
            rooms: Vec::new(),
            samples: Vec::new(),
        }
    }

    fn watch_paths(&self) -> Vec<PathBuf> {
        let mut paths = vec![self.rooms_path.clone(), self.data_dir.clone()];
        if self.include_extract {
            if let Some(dir) = &self.extract_dir {
                paths.push(dir.join("adv.csv"));
                paths.push(dir.join("att_fff5_fff3.csv"));
            }
        }
        let (live, history) = list_data_csvs(&self.data_dir);
        paths.extend(live);
        paths.extend(history);
        paths
    }

    fn mtime_stamp(&self) -> Vec<(PathBuf, Option<SystemTime>)> {
        self.watch_paths()
            .into_iter()
            .map(|path| {
                let mtime = fs::metadata(&path).and_then(|m| m.modified()).ok();
                (path, mtime)
            })
            .collect()
    }

    pub fn refresh(&mut self, force: bool) {
        let stamp = self.mtime_stamp();
        if !force && self.stamp.as_ref() == Some(&stamp) {
            return;
        }
        self.rooms = load_rooms(&self.rooms_path).unwrap_or_default();
        let mut samples = load_live_and_history(&self.data_dir, &self.rooms);
        if self.include_extract {
            if let Some(dir) = &self.extract_dir {
                samples.extend(load_extracts(dir, &self.rooms));
            }
        }
        self.samples = sort_samples(samples);
        self.stamp = Some(stamp);
    }

    pub fn sources_present(&self) -> Vec<String> {
        let have: HashSet<&str> = self.samples.iter().map(|s| s.source.as_str()).collect();
        KNOWN_SOURCES
            .iter()
            .filter(|n| have.contains(*n))
            .map(|s| (*s).to_string())
            .collect()
    }

    pub fn overview(&mut self) -> Overview {
        self.refresh(false);
        let (live_paths, history_paths) = list_data_csvs(&self.data_dir);
        let mut rooms_out = Vec::new();
        for room in &self.rooms {
            let mac = &room.mac;
            let for_mac = filter_samples(&self.samples, Some(mac), None, None);
            let live = filter_samples(&for_mac, None, Some(SOURCE_ADV), None);
            let hist = filter_samples(&for_mac, None, Some(SOURCE_HISTORY), None);
            let adv_cap = filter_samples(&for_mac, None, Some(SOURCE_ADV_CAPTURE), None);
            let hist_cap = filter_samples(&for_mac, None, Some(SOURCE_HISTORY_CAPTURE), None);
            let latest = live.last().cloned().or_else(|| adv_cap.last().cloned());
            let hist_for_summary = if hist.is_empty() {
                hist_cap.clone()
            } else {
                hist.clone()
            };
            rooms_out.push(RoomOverview {
                id: room.id.clone(),
                name: room.name.clone(),
                mac: mac.clone(),
                confirmed: room.confirmed,
                encoding_checked: room.encoding_checked,
                note: room.note.clone(),
                latest,
                counts: RoomCounts {
                    adv: live.len(),
                    history: hist.len(),
                    adv_capture: adv_cap.len(),
                    history_capture: hist_cap.len(),
                },
                summary_live: summarize(&live),
                summary_history: summarize(&hist_for_summary),
            });
        }
        Overview {
            rooms: rooms_out,
            sources: self.sources_present(),
            live_csv_count: live_paths.len(),
            history_csv_count: history_paths.len(),
            sample_count: self.samples.len(),
            encoding: EncodingInfo {
                scale: 16,
                temp: "int16le / 16 → °C".into(),
                humidity: "int16le / 16 → %rF (Display ±3 %, nicht exakt)".into(),
                history_clock: "Keine Geräte-Wanduhr. timestamp_inferred = Hypothese 10 min (ADV-Counter/Count ≈ 600 s); sonst X = Sample-Index (0 = älteste).".into(),
                history_interval_sec_hypothesis: 600,
            },
            notes: vec![
                "Allowlist = rooms.json. Kandidaten (confirmed=false) sind nicht automatisch eigene Geräte.".into(),
                "Live-CSV = collect über ADV. History-CSV = dump-history (GATT 07 oder Extract).".into(),
                "Capture-ADV nur encoding_checked (Büro). Hum /16 intern; Live ±3 % zum Display.".into(),
            ],
        }
    }

    pub fn query(&mut self, mac: Option<&str>, source: Option<&str>, limit: i64) -> QueryResult {
        self.refresh(false);
        let mut rows = filter_samples(&self.samples, mac, source, None);
        rows = sort_samples(rows);
        let chart = if limit > 0 {
            downsample(&rows, limit)
        } else {
            rows.clone()
        };
        QueryResult {
            mac: mac.map(normalize_mac),
            source: source.map(|s| s.to_string()),
            count: rows.len(),
            returned: chart.len(),
            summary: summarize(&rows),
            samples: chart,
        }
    }
}
