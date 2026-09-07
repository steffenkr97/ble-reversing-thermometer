use thermobeacon::dash::{
    downsample, filter_samples, load_rooms, read_extract_adv, read_extract_history, read_history_csv,
    read_live_csv, summarize, DashStore, Sample, SOURCE_ADV, SOURCE_ADV_CAPTURE, SOURCE_HISTORY,
    SOURCE_HISTORY_CAPTURE,
};
use thermobeacon::mac::normalize_mac;
use thermobeacon::paths::repo_root;

fn testdata() -> std::path::PathBuf {
    repo_root().join("dashboard/testdata")
}

#[test]
fn normalize() {
    assert_eq!(normalize_mac("F4:DB:00:00:00:D9"), "f4:db:00:00:00:d9");
    assert_eq!(normalize_mac("f4db000000d9"), "f4:db:00:00:00:d9");
}

#[test]
fn buero_allowlist() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    assert_eq!(rooms.len(), 1);
    assert_eq!(rooms[0].mac, "f4:db:00:00:00:d9");
    assert_eq!(rooms[0].name, "Büro");
    assert!(rooms[0].encoding_checked);
}

#[test]
fn prod_rooms_five_candidates() {
    let rooms = load_rooms(repo_root().join("dashboard/rooms.json")).unwrap();
    assert_eq!(rooms.len(), 5);
    assert!(rooms[0].confirmed);
    assert!(!rooms[1].confirmed);
}

#[test]
fn live_csv_drops_foreign_mac() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    let rows = read_live_csv(testdata().join("thermo_f4db000000d9_2026-09-03.csv"), &rooms);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].temp_c, 25.125);
    assert_eq!(rows[0].source, SOURCE_ADV);
    assert_eq!(rows[0].room.as_deref(), Some("Büro"));
    let macs: std::collections::HashSet<_> = rows.iter().map(|r| r.mac.clone()).collect();
    assert_eq!(macs, ["f4:db:00:00:00:d9".to_string()].into_iter().collect());
}

#[test]
fn wrong_header_is_empty() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    let tmp = tempfile::NamedTempFile::new().unwrap();
    std::fs::write(tmp.path(), "foo,bar\n1,2\n").unwrap();
    assert!(read_live_csv(tmp.path(), &rooms).is_empty());
}

#[test]
fn history_csv_index_and_source() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    let rows = read_history_csv(testdata().join("history_f4db000000d9.csv"), &rooms);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].source, SOURCE_HISTORY);
    assert_eq!(rows[0].index, Some(0));
    assert_eq!(rows[0].temp_c, 24.0625);
    assert_eq!(rows[0].timestamp.as_deref(), Some("2025-11-15T12:00:00Z"));
    assert_eq!(rows[1].timestamp.as_deref(), Some("2025-11-15T12:10:00Z"));
}

#[test]
fn extract_adv_gold_vector() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    let rows = read_extract_adv(testdata().join("extract/adv.csv"), &rooms);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].source, SOURCE_ADV_CAPTURE);
    assert_eq!(rows[0].temp_c, 22.0625);
    assert_eq!(rows[0].humidity_rh, 64.9375);
    assert_eq!(rows[0].mac, "f4:db:00:00:00:d9");
    assert!(rows[0].timestamp.as_deref().unwrap().starts_with("2025-"));
}

#[test]
fn history_gold_and_dedupe() {
    let rooms = load_rooms(testdata().join("rooms.json")).unwrap();
    let rows = read_extract_history(testdata().join("extract/att_fff5_fff3.csv"), &rooms);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0].source, SOURCE_HISTORY_CAPTURE);
    assert_eq!(rows[0].index, Some(0));
    assert_eq!(rows[0].temp_c, 24.0625);
    assert_eq!(rows[1].index, Some(1));
    assert_eq!(rows[2].index, Some(2));
    assert_eq!(rows[2].temp_c, 23.5625);
}

#[test]
fn downsample_keeps_ends() {
    let samples: Vec<Sample> = (0..10)
        .map(|n| Sample {
            timestamp: None,
            mac: "x".into(),
            temp_c: n as f64,
            humidity_rh: 0.0,
            source: SOURCE_ADV.into(),
            raw_hex: String::new(),
            index: Some(n),
            record: None,
            room: None,
            file: None,
            room_id: None,
        })
        .collect();
    let out = downsample(&samples, 3);
    assert_eq!(out[0].index, Some(0));
    assert_eq!(out.last().unwrap().index, Some(9));
    assert_eq!(out.len(), 3);
}

#[test]
fn summarize_empty() {
    assert_eq!(summarize(&[]).count, 0);
}

#[test]
fn filter_source() {
    let rows = vec![
        Sample {
            timestamp: None,
            mac: "f4:db:00:00:00:d9".into(),
            temp_c: 1.0,
            humidity_rh: 1.0,
            source: SOURCE_ADV.into(),
            raw_hex: String::new(),
            index: None,
            record: None,
            room: None,
            file: None,
            room_id: None,
        },
        Sample {
            timestamp: None,
            mac: "f4:db:00:00:00:d9".into(),
            temp_c: 1.0,
            humidity_rh: 1.0,
            source: SOURCE_HISTORY.into(),
            raw_hex: String::new(),
            index: None,
            record: None,
            room: None,
            file: None,
            room_id: None,
        },
    ];
    assert_eq!(filter_samples(&rows, None, Some(SOURCE_ADV), None).len(), 1);
}

#[test]
fn store_overview_and_query() {
    let mut store = DashStore::new(
        testdata(),
        testdata().join("rooms.json"),
        Some(testdata().join("extract")),
        true,
    );
    let overview = store.overview();
    assert_eq!(overview.live_csv_count, 1);
    assert_eq!(overview.history_csv_count, 1);
    assert!(overview.sources.iter().any(|s| s == SOURCE_ADV));
    assert!(overview.sources.iter().any(|s| s == SOURCE_HISTORY));
    assert!(overview.sources.iter().any(|s| s == SOURCE_HISTORY_CAPTURE));
    let buero = &overview.rooms[0];
    assert_eq!(buero.name, "Büro");
    assert!(buero.encoding_checked);
    assert_eq!(buero.counts.adv, 2);
    assert_eq!(buero.latest.as_ref().unwrap().temp_c, 25.1875);

    let live = store.query(Some("f4:db:00:00:00:d9"), Some(SOURCE_ADV), 0);
    assert_eq!(live.count, 2);
    let hist = store.query(Some("F4:DB:00:00:00:D9"), Some(SOURCE_HISTORY_CAPTURE), 0);
    assert_eq!(hist.count, 3);
    let dumped = store.query(Some("f4:db:00:00:00:d9"), Some(SOURCE_HISTORY), 0);
    assert_eq!(dumped.count, 2);
    assert_eq!(
        dumped.samples[0].timestamp.as_deref(),
        Some("2025-11-15T12:00:00Z")
    );
}

#[test]
fn no_extract() {
    let mut store = DashStore::new(
        testdata(),
        testdata().join("rooms.json"),
        Some(testdata().join("extract")),
        false,
    );
    store.refresh(true);
    let sources = store.sources_present();
    assert!(!sources.iter().any(|s| s == SOURCE_ADV_CAPTURE));
    assert!(!sources.iter().any(|s| s == SOURCE_HISTORY_CAPTURE));
}
