use std::fs;
use tempfile::tempdir;
use thermobeacon::csvutil::iso_utc_now;
use thermobeacon::store::{append_sample, default_csv_path, COLUMNS};

#[test]
fn utc_z_format() {
    let ts = iso_utc_now();
    assert!(ts.ends_with('Z'));
    assert!(ts.contains('T'));
    assert!(!ts.contains('.'));
}

#[test]
fn colon_mac_filename() {
    let tmp = tempdir().unwrap();
    let path = default_csv_path("f4:db:00:00:00:d9", tmp.path());
    let day = chrono::Utc::now().format("%Y-%m-%d").to_string();
    assert_eq!(
        path.file_name().unwrap().to_str().unwrap(),
        format!("thermo_f4db000000d9_{day}.csv")
    );
    assert_eq!(path.parent().unwrap(), tmp.path());
}

#[test]
fn dash_mac_is_mac12() {
    let tmp = tempdir().unwrap();
    let path = default_csv_path("f4-db-00-00-00-d9", tmp.path());
    let day = chrono::Utc::now().format("%Y-%m-%d").to_string();
    assert_eq!(
        path.file_name().unwrap().to_str().unwrap(),
        format!("thermo_f4db000000d9_{day}.csv")
    );
}

#[test]
fn header_exactly_once() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("out.csv");
    append_sample(
        &path,
        "2026-09-03T12:00:00Z",
        "f4:db:00:00:00:d9",
        22.0625,
        64.94,
        "aabb",
    )
    .unwrap();
    append_sample(
        &path,
        "2026-09-03T12:00:01Z",
        "f4:db:00:00:00:d9",
        22.125,
        65.0,
        "ccdd",
    )
    .unwrap();
    let text = fs::read_to_string(&path).unwrap();
    let rows: Vec<&str> = text.trim_end().split('\n').collect();
    assert_eq!(rows[0], COLUMNS.join(","));
    assert_eq!(rows.len(), 3);
    assert!(rows[1].starts_with("2026-09-03T12:00:00Z"));
    assert!(rows[2].starts_with("2026-09-03T12:00:01Z"));
}

#[test]
fn append_creates_missing_dirs() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("nested/deeper/out.csv");
    assert!(!path.parent().unwrap().exists());
    append_sample(&path, "2026-09-03T12:00:00Z", "aa:bb", 1.0, 2.0, "00").unwrap();
    assert!(path.is_file());
}
