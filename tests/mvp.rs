use serde_json::json;
use tempfile::tempdir;
use thermobeacon::mvp::{
    append_evidence, compare_live_to_newest_history, infer_interval_sec_default, load_evidence,
    HUM_TOL, TEMP_TOL_C,
};
use thermobeacon::parse::AdvLive;
use thermobeacon::scan::parse_scan_args;

fn live() -> AdvLive {
    AdvLive {
        temp_c: 25.125,
        humidity_rh: 62.0625,
        battery_mv: 2617,
        counter: 2025968,
        mac: "f4:db:00:00:00:d9".into(),
        raw_hex: "00".into(),
    }
}

fn row(index: &str, temp: &str, hum: &str) -> serde_json::Map<String, serde_json::Value> {
    let mut m = serde_json::Map::new();
    m.insert("index".into(), json!(index));
    m.insert("temp_c".into(), json!(temp));
    m.insert("humidity_rh".into(), json!(hum));
    m
}

#[test]
fn close_temps_ok() {
    let rows = vec![
        row("0", "20.0", "50"),
        row("10", "25.0", "61.0"),
    ];
    let cmp = compare_live_to_newest_history(&live(), &rows, TEMP_TOL_C, HUM_TOL);
    assert_eq!(cmp.get("ok"), Some(&json!(true)));
    assert_eq!(cmp.get("history_index"), Some(&json!(10)));
    assert!(cmp.get("temp_delta_c").and_then(|v| v.as_f64()).unwrap() < 0.2);
}

#[test]
fn empty_history() {
    let cmp = compare_live_to_newest_history(&live(), &[], TEMP_TOL_C, HUM_TOL);
    assert_eq!(cmp.get("ok"), Some(&json!(false)));
}

#[test]
fn far_temp_not_ok() {
    let mut m = serde_json::Map::new();
    m.insert("index".into(), json!(3));
    m.insert("temp_c".into(), json!(10.0));
    m.insert("humidity_rh".into(), json!(40.0));
    let cmp = compare_live_to_newest_history(&live(), &[m], TEMP_TOL_C, HUM_TOL);
    assert_eq!(cmp.get("ok"), Some(&json!(false)));
}

#[test]
fn two_counts_yield_10min() {
    let records = vec![
        json!({
            "mac": "f4:db:00:00:00:d9",
            "recorded_at": "2026-09-04T10:00:00Z",
            "sample_count": 100
        }),
        json!({
            "mac": "f4:db:00:00:00:d9",
            "recorded_at": "2026-09-04T11:40:00Z",
            "sample_count": 110
        }),
    ];
    let got = infer_interval_sec_default(&records).unwrap();
    assert_eq!(got.get("ok"), Some(&json!(true)));
    assert!((got.get("interval_sec").unwrap().as_f64().unwrap() - 600.0).abs() < 0.001);
    assert_eq!(got.get("close_to_10min"), Some(&json!(true)));
}

#[test]
fn one_point_is_none() {
    let records = vec![json!({
        "mac": "f4:db:00:00:00:d9",
        "recorded_at": "2026-09-04T10:00:00Z",
        "sample_count": 100
    })];
    assert!(infer_interval_sec_default(&records).is_none());
}

#[test]
fn append_and_load() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("e.jsonl");
    append_evidence(&path, &json!({"mac":"f4:db:00:00:00:d9","n":1})).unwrap();
    append_evidence(&path, &json!({"mac":"f4:db:00:00:00:d9","n":2})).unwrap();
    let rows = load_evidence(&path).unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[1].get("n"), Some(&json!(2)));
}

#[test]
fn mvp_help() {
    // scan-live --help as stand-in that clap help exits 0; mvp binary uses clap too
    assert!(matches!(parse_scan_args(["scan-live", "--help"]), Err(0)));
}
