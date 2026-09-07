use std::fs;
use tempfile::tempdir;
use thermobeacon::history::{
    apply_inferred_timestamps, assert_allowed_fff5_write, default_history_csv_path,
    interval_from_count_and_counter, load_extract_history, page_plan, samples_from_page,
    samples_from_pages, write_history_csv, BLACKLIST_WRITE_OPCODES, HISTORY_COLUMNS,
    INTERVAL_SEC_HYPOTHESIS,
};
use thermobeacon::parse::{build_history_07_write, parse_fff3, Fff3, TARGET_MAC};
use thermobeacon::paths::repo_root;

fn hex(s: &str) -> Vec<u8> {
    hex::decode(s.replace(' ', "")).unwrap()
}

const GOLD_07_COUNT3: &str = "07000000000381017B017901B403BC03CB030000";
const GOLD_07_COUNT1: &str = "0730060000016F01E8036E010E040F04F2030000";

fn hist(data: &[u8]) -> thermobeacon::History07 {
    match parse_fff3(data) {
        Some(Fff3::History(h)) => h,
        _ => panic!("not history"),
    }
}

#[test]
fn page_plan_1584_all_count3() {
    let plan = page_plan(1584).unwrap();
    assert_eq!(plan.len(), 528);
    assert_eq!(plan[0], (0, 3));
    assert_eq!(plan[1], (3, 3));
    assert_eq!(*plan.last().unwrap(), (1581, 3));
    assert!(plan.iter().all(|(_, c)| *c == 3));
}

#[test]
fn page_plan_1586_two_remainder() {
    let plan = page_plan(1586).unwrap();
    assert_eq!(plan.len(), 530);
    assert_eq!(plan[plan.len() - 3], (1581, 3));
    assert_eq!(plan[plan.len() - 2], (1584, 1));
    assert_eq!(plan[plan.len() - 1], (1585, 1));
    assert!(plan.iter().all(|(_, c)| *c == 1 || *c == 3));
    assert_eq!(plan.iter().map(|(_, c)| *c as u32).sum::<u32>(), 1586);
}

#[test]
fn page_plan_820() {
    let plan = page_plan(820).unwrap();
    assert_eq!(plan.len(), 274);
    assert_eq!(*plan.last().unwrap(), (819, 1));
    assert_eq!(plan.iter().map(|(_, c)| *c as u32).sum::<u32>(), 820);
}

#[test]
fn page_plan_zero_and_one() {
    assert!(page_plan(0).unwrap().is_empty());
    assert_eq!(page_plan(1).unwrap(), vec![(0, 1)]);
    assert_eq!(page_plan(2).unwrap(), vec![(0, 1), (1, 1)]);
    assert_eq!(page_plan(3).unwrap(), vec![(0, 3)]);
}

#[test]
fn writes_match_capture_payloads() {
    assert_eq!(build_history_07_write(0, 3), hex("070000000003"));
    assert_eq!(build_history_07_write(1584, 1), hex("073006000001"));
    let plan = page_plan(1586).unwrap();
    for (index, count) in plan.iter().take(2).chain(plan.iter().rev().take(2)) {
        let payload = build_history_07_write(*index, *count);
        assert_allowed_fff5_write(&payload).unwrap();
    }
}

#[test]
fn app_opcodes_ok() {
    assert_allowed_fff5_write(&[0x1A]).unwrap();
    assert_allowed_fff5_write(&[0x01]).unwrap();
    assert_allowed_fff5_write(&build_history_07_write(0, 3)).unwrap();
    assert_allowed_fff5_write(&build_history_07_write(1584, 1)).unwrap();
}

#[test]
fn blacklist_rejected() {
    for opcode in BLACKLIST_WRITE_OPCODES {
        assert!(assert_allowed_fff5_write(&[opcode]).is_err());
    }
    assert!(assert_allowed_fff5_write(&hex("0400000000")).is_err());
    assert!(assert_allowed_fff5_write(&hex("18E7035E")).is_err());
    assert!(assert_allowed_fff5_write(&build_history_07_write(0, 2)).is_err());
    assert!(assert_allowed_fff5_write(&[0x07]).is_err());
}

#[test]
fn count3_gold() {
    let parsed = hist(&hex(GOLD_07_COUNT3));
    let rows = samples_from_page(&parsed, TARGET_MAC);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0].index, 0);
    assert_eq!(rows[0].record, 0);
    assert_eq!(rows[0].temp_c, 24.0625);
    assert_eq!(rows[0].humidity_rh, 59.25);
    assert_eq!(rows[1].index, 1);
    assert_eq!(rows[2].index, 2);
    assert_eq!(rows[2].temp_c, 23.5625);
    assert_eq!(rows[0].raw_hex, hex::encode(hex(GOLD_07_COUNT3)));
}

#[test]
fn count1_hum_offset8() {
    let parsed = hist(&hex(GOLD_07_COUNT1));
    let rows = samples_from_page(&parsed, TARGET_MAC);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].index, 1584);
    assert_eq!(rows[0].temp_c, 22.9375);
    assert_eq!(rows[0].humidity_rh, 62.5);
}

#[test]
fn interval_hypothesis_from_adv_counter() {
    let interval = interval_from_count_and_counter(1583, 949579).unwrap();
    assert!((interval - 599.86).abs() < 0.01);
    assert!((interval - INTERVAL_SEC_HYPOTHESIS).abs() <= 1.0);
}

#[test]
fn inferred_uses_device_count_not_dump_len() {
    let parsed = hist(&hex(GOLD_07_COUNT3));
    let rows = samples_from_pages(&[parsed], TARGET_MAC);
    let stamped = apply_inferred_timestamps(&rows, "2025-11-26T15:00:00Z", 600.0, Some(1582)).unwrap();
    assert_eq!(stamped[0].timestamp_inferred, "2025-11-15T15:20:00Z");
    assert_eq!(stamped[2].timestamp_inferred, "2025-11-15T15:40:00Z");
    let newest = apply_inferred_timestamps(
        &[thermobeacon::history::HistoryRow {
            mac: TARGET_MAC.into(),
            index: 1582,
            record: 0,
            temp_c: 1.0,
            humidity_rh: 2.0,
            raw_hex: String::new(),
            timestamp_inferred: String::new(),
        }],
        "2025-11-26T15:00:00Z",
        600.0,
        Some(1582),
    )
    .unwrap();
    assert_eq!(newest[0].timestamp_inferred, "2025-11-26T15:00:00Z");
}

#[test]
fn path_and_roundtrip() {
    let tmp = tempdir().unwrap();
    let path = default_history_csv_path(TARGET_MAC, tmp.path());
    assert_eq!(
        path.file_name().unwrap().to_str().unwrap(),
        "history_f4db000000d9.csv"
    );
    let parsed = hist(&hex(GOLD_07_COUNT3));
    let rows = apply_inferred_timestamps(
        &samples_from_page(&parsed, TARGET_MAC),
        "2025-11-26T15:00:00Z",
        600.0,
        Some(2),
    )
    .unwrap();
    write_history_csv(&path, &rows).unwrap();
    let text = fs::read_to_string(&path).unwrap();
    let mut lines = text.lines();
    assert_eq!(lines.next().unwrap(), HISTORY_COLUMNS.join(","));
    let got: Vec<_> = lines.collect();
    assert_eq!(got.len(), 3);
    assert!(got[0].starts_with(TARGET_MAC));
    assert!(got[0].contains(",0,"));
    assert!(got[0].contains("24.0625"));
    assert!(got[0].ends_with('Z') || got[0].contains("Z"));
}

#[test]
fn dashboard_fixture_gold_page() {
    let extract = repo_root().join("dashboard/testdata/extract");
    let (rows, meta) = load_extract_history(&extract, TARGET_MAC, true).unwrap();
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0].temp_c, 24.0625);
    assert_eq!(rows[2].temp_c, 23.5625);
    assert!(meta.file.is_some());
}

#[test]
fn real_extract_picks_complete_dump() {
    let extract = repo_root().join("hci-logs/extract");
    if !extract.join("att_fff5_fff3.csv").is_file() {
        return;
    }
    let (rows, meta) = load_extract_history(&extract, TARGET_MAC, true).unwrap();
    assert!(rows.len() >= 1584);
    assert_eq!(rows[0].index, 0);
    assert_eq!(rows[0].temp_c, 24.0625);
    assert_eq!(rows[0].humidity_rh, 59.25);
    let by_index: std::collections::HashMap<_, _> = rows.iter().map(|r| (r.index, r)).collect();
    assert_eq!(by_index.get(&1584).unwrap().temp_c, 22.9375);
    assert_eq!(by_index.get(&1584).unwrap().humidity_rh, 62.5);
    assert!(!meta.file.as_deref().unwrap_or("").contains("old/"));
    assert_eq!(meta.count_01, Some(1586));
    assert_eq!(rows.len(), 1586);
}
