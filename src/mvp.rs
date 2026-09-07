//! Büro-MVP: Vergleich History vs. ADV, Intervall-Evidence (ohne BLE testbar).

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Write};
use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::csvutil::{iso_utc_now, parse_iso_utc};
use crate::mac::compact_mac;
use crate::parse::{AdvLive, TARGET_MAC};

pub const TEMP_TOL_C: f64 = 2.0;
pub const HUM_TOL: f64 = 5.0;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryLite {
    pub index: Option<Value>,
    pub temp_c: Value,
    pub humidity_rh: Value,
}

pub fn newest_history_index_row(rows: &[serde_json::Map<String, Value>]) -> Option<serde_json::Map<String, Value>> {
    if rows.is_empty() {
        return None;
    }
    let indexed: Vec<_> = rows
        .iter()
        .filter(|row| {
            match row.get("index") {
                None | Some(Value::Null) => false,
                Some(Value::String(s)) if s.is_empty() => false,
                Some(_) => true,
            }
        })
        .collect();
    if indexed.is_empty() {
        return rows.last().cloned();
    }
    indexed
        .into_iter()
        .max_by_key(|row| json_i64(row.get("index")).unwrap_or(-1))
        .cloned()
}

fn json_i64(v: Option<&Value>) -> Option<i64> {
    match v? {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s.parse().ok(),
        _ => None,
    }
}

fn json_f64(v: Option<&Value>) -> Option<f64> {
    match v? {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.parse().ok(),
        _ => None,
    }
}

/// Neueste History-Page gegen Live-ADV. Temp ≈ Display /16.
pub fn compare_live_to_newest_history(
    live: &AdvLive,
    rows: &[serde_json::Map<String, Value>],
    temp_tol: f64,
    hum_tol: f64,
) -> serde_json::Map<String, Value> {
    let mut out = serde_json::Map::new();
    let Some(newest) = newest_history_index_row(rows) else {
        out.insert("ok".into(), Value::Bool(false));
        out.insert("reason".into(), Value::String("keine History-Zeilen".into()));
        out.insert("live_temp_c".into(), json_num(live.temp_c));
        out.insert("live_humidity_rh".into(), json_num(live.humidity_rh));
        return out;
    };
    let hist_temp = json_f64(newest.get("temp_c")).unwrap_or(0.0);
    let hist_hum = json_f64(newest.get("humidity_rh")).unwrap_or(0.0);
    let temp_delta = (live.temp_c - hist_temp).abs();
    let hum_delta = (live.humidity_rh - hist_hum).abs();
    let ok = temp_delta <= temp_tol;
    let hist_index = json_i64(newest.get("index"))
        .map(Value::from)
        .or_else(|| newest.get("index").cloned())
        .unwrap_or(Value::Null);
    out.insert("ok".into(), Value::Bool(ok));
    out.insert("live_temp_c".into(), json_num(live.temp_c));
    out.insert("live_humidity_rh".into(), json_num(live.humidity_rh));
    out.insert("live_counter".into(), Value::from(live.counter));
    out.insert("history_index".into(), hist_index);
    out.insert("history_temp_c".into(), json_num(hist_temp));
    out.insert("history_humidity_rh".into(), json_num(hist_hum));
    out.insert("temp_delta_c".into(), json_num(temp_delta));
    out.insert("hum_delta".into(), json_num(hum_delta));
    out.insert("temp_tol_c".into(), json_num(temp_tol));
    out.insert("hum_tol".into(), json_num(hum_tol));
    out.insert("hum_ok".into(), Value::Bool(hum_delta <= hum_tol));
    out.insert("mac".into(), Value::String(live.mac.clone()));
    out
}

fn json_num(v: f64) -> Value {
    serde_json::Number::from_f64(v)
        .map(Value::Number)
        .unwrap_or(Value::Null)
}

pub fn append_evidence(path: impl AsRef<Path>, record: &Value) -> crate::error::Result<()> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }
    let line = serde_json::to_string(record)?;
    let mut f = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(f, "{line}")?;
    Ok(())
}

pub fn load_evidence(path: impl AsRef<Path>) -> crate::error::Result<Vec<Value>> {
    let path = path.as_ref();
    if !path.is_file() {
        return Ok(Vec::new());
    }
    let f = fs::File::open(path)?;
    let mut rows = Vec::new();
    for line in BufReader::new(f).lines() {
        let line = line?;
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        rows.push(serde_json::from_str(line)?);
    }
    Ok(rows)
}

/// Zwei Count-01-/Zeitpunkte → Sekunden je Sample. Hypothese 600 s.
pub fn infer_interval_sec(records: &[Value], mac: &str) -> Option<Value> {
    let wanted = compact_mac(mac);
    let mut points: Vec<(chrono::DateTime<chrono::Utc>, i64)> = Vec::new();
    for rec in records {
        let rec_mac = compact_mac(rec.get("mac").and_then(|v| v.as_str()).unwrap_or(""));
        if !rec_mac.is_empty() && rec_mac != wanted {
            continue;
        }
        let count = match rec.get("sample_count") {
            None | Some(Value::Null) => continue,
            Some(Value::String(s)) if s.is_empty() => continue,
            Some(v) => match json_i64(Some(v)) {
                Some(c) => c,
                None => continue,
            },
        };
        let Some(ts) = rec.get("recorded_at").and_then(|v| v.as_str()) else {
            continue;
        };
        if ts.is_empty() {
            continue;
        }
        let Ok(dt) = parse_iso_utc(ts) else {
            continue;
        };
        points.push((dt, count));
    }
    if points.len() < 2 {
        return None;
    }
    points.sort_by_key(|p| p.0);
    let (t0, c0) = points[0];
    let (t1, c1) = points[points.len() - 1];
    let dc = c1 - c0;
    let dt = (t1 - t0).num_microseconds().unwrap_or(0) as f64 / 1_000_000.0;
    if dc == 0 || dt <= 0.0 {
        return Some(serde_json::json!({
            "ok": false,
            "reason": "Count oder Zeit unverändert",
            "count_0": c0,
            "count_1": c1,
            "dt_sec": dt,
        }));
    }
    let interval = dt / dc as f64;
    Some(serde_json::json!({
        "ok": true,
        "count_0": c0,
        "count_1": c1,
        "dt_sec": dt,
        "interval_sec": interval,
        "hypothesis_sec": 600.0,
        "close_to_10min": (interval - 600.0).abs() <= 90.0,
    }))
}

pub fn infer_interval_sec_default(records: &[Value]) -> Option<Value> {
    infer_interval_sec(records, TARGET_MAC)
}

pub fn format_compare(cmp: &serde_json::Map<String, Value>) -> String {
    let has_hist = cmp.get("history_temp_c").and_then(|v| v.as_f64()).is_some();
    let ok = cmp.get("ok").and_then(|v| v.as_bool()).unwrap_or(false);
    if !has_hist && !ok {
        return format!(
            "Vergleich: {}",
            cmp.get("reason")
                .and_then(|v| v.as_str())
                .unwrap_or("fehlgeschlagen")
        );
    }
    let flag = if ok { "ok" } else { "abweichung" };
    format!(
        "Vergleich History vs. ADV ({flag}): live {:.4} °C / hist {:.4} °C  Δ={:.4} (Toleranz {} °C); Hum Δ={:.2}",
        cmp.get("live_temp_c").and_then(|v| v.as_f64()).unwrap_or(0.0),
        cmp.get("history_temp_c").and_then(|v| v.as_f64()).unwrap_or(0.0),
        cmp.get("temp_delta_c").and_then(|v| v.as_f64()).unwrap_or(0.0),
        cmp.get("temp_tol_c").and_then(|v| v.as_f64()).unwrap_or(TEMP_TOL_C),
        cmp.get("hum_delta").and_then(|v| v.as_f64()).unwrap_or(0.0),
    )
}

pub fn default_evidence_path() -> std::path::PathBuf {
    crate::paths::default_data_dir().join("interval_evidence.jsonl")
}

pub fn rows_from_history_csv(path: impl AsRef<Path>) -> crate::error::Result<Vec<serde_json::Map<String, Value>>> {
    let mut rdr = csv::Reader::from_path(path)?;
    let mut rows = Vec::new();
    for rec in rdr.deserialize() {
        let row: HashMap<String, String> = rec?;
        let mut map = serde_json::Map::new();
        for (k, v) in row {
            map.insert(k, Value::String(v));
        }
        rows.push(map);
    }
    Ok(rows)
}

pub fn evidence_record(
    mac: &str,
    live: Option<&AdvLive>,
    sample_count: Option<i64>,
    cmp: Option<&serde_json::Map<String, Value>>,
) -> Value {
    let mut rec = serde_json::json!({
        "recorded_at": iso_utc_now(),
        "mac": mac,
        "sample_count": sample_count,
        "adv_counter": live.map(|l| l.counter),
        "temp_c": live.map(|l| l.temp_c),
        "humidity_rh": live.map(|l| l.humidity_rh),
    });
    if let Some(cmp) = cmp {
        if let Some(obj) = rec.as_object_mut() {
            obj.insert(
                "history_newest_index".into(),
                cmp.get("history_index").cloned().unwrap_or(Value::Null),
            );
            obj.insert(
                "history_newest_temp_c".into(),
                cmp.get("history_temp_c").cloned().unwrap_or(Value::Null),
            );
            obj.insert(
                "temp_delta_c".into(),
                cmp.get("temp_delta_c").cloned().unwrap_or(Value::Null),
            );
        }
    }
    rec
}
