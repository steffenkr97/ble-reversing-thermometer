use std::fs;
use tempfile::tempdir;
use thermobeacon::dump::{dump_from_extract, fetch_history_pages, parse_dump_args};
use thermobeacon::parse::{build_history_07_write, parse_fff3, Fff3, TARGET_MAC};
use thermobeacon::paths::repo_root;

fn hex(s: &str) -> Vec<u8> {
    hex::decode(s.replace(' ', "")).unwrap()
}

fn gold_p0() -> Vec<u8> {
    hex("07000000000381017B017901B403BC03CB030000")
}
fn gold_p3() -> Vec<u8> {
    hex("070300000003740167015A01C003CE03EF030000")
}
fn gold_p6() -> Vec<u8> {
    let mut b = hex("0730060000016F01E8036E010E040F04F2030000");
    let idx = 6u16.to_le_bytes();
    b[1..3].copy_from_slice(&idx);
    b
}

#[test]
fn from_extract_defaults() {
    let args = parse_dump_args(["dump-history", "--from-extract", "hci-logs/extract"]).unwrap();
    assert_eq!(
        args.from_extract.unwrap().as_os_str(),
        "hci-logs/extract"
    );
    assert_eq!(args.interval_sec, 600.0);
    assert_eq!(args.mac, TARGET_MAC);
    assert_eq!(args.outdir.as_os_str(), "data");
    assert!(!args.no_timestamps);
}

#[test]
fn extract_and_address_conflict() {
    assert!(parse_dump_args([
        "dump-history",
        "--from-extract",
        "x",
        "--address",
        TARGET_MAC
    ])
    .is_err());
}

#[test]
fn interval_must_be_positive() {
    assert!(parse_dump_args([
        "dump-history",
        "--from-extract",
        "x",
        "--interval-sec",
        "0"
    ])
    .is_err());
}

#[test]
fn help_without_ble() {
    assert!(matches!(parse_dump_args(["dump-history", "--help"]), Err(0)));
}

#[tokio::test]
async fn seven_samples_three_pages() {
    let mut writes = Vec::new();
    let pages = fetch_history_pages(
        |payload| {
            writes.push(payload.clone());
            let p0 = build_history_07_write(0, 3);
            let p3 = build_history_07_write(3, 3);
            let p6 = build_history_07_write(6, 1);
            async move {
                if payload == p0 {
                    Some(gold_p0())
                } else if payload == p3 {
                    Some(gold_p3())
                } else if payload == p6 {
                    Some(gold_p6())
                } else {
                    panic!("unerwarteter Write {}", hex::encode(&payload));
                }
            }
        },
        7,
        None,
        0,
        None,
    )
    .await
    .unwrap();
    assert_eq!(pages.len(), 3);
    assert_eq!(
        pages.iter().map(|p| p.index).collect::<Vec<_>>(),
        vec![0, 3, 6]
    );
    assert_eq!(pages[0].count, 3);
    assert_eq!(pages[2].count, 1);
    assert_eq!(pages[2].records[0], (22.9375, 62.5));
    assert_eq!(writes[0][0], 0x07);
    assert!(writes.iter().all(|w| w[0] == 0x07));
    assert!(writes.iter().all(|w| w[5] == 1 || w[5] == 3));
    assert!(!writes.iter().any(|w| w[0] == 0x04));
    assert!(!writes.iter().any(|w| w[0] == 0x18));
}

#[tokio::test]
async fn timeout_then_retry() {
    let n = std::sync::Arc::new(std::sync::atomic::AtomicU32::new(0));
    let n2 = n.clone();
    let pages = fetch_history_pages(
        move |_payload| {
            let c = n2.fetch_add(1, std::sync::atomic::Ordering::SeqCst) + 1;
            async move {
                if c == 1 {
                    None
                } else {
                    Some(gold_p0())
                }
            }
        },
        3,
        Some(1),
        2,
        None,
    )
    .await
    .unwrap();
    assert_eq!(pages.len(), 1);
    assert_eq!(n.load(std::sync::atomic::Ordering::SeqCst), 2);
}

#[tokio::test]
async fn max_pages() {
    let pages = fetch_history_pages(
        |payload| {
            let p0 = build_history_07_write(0, 3);
            async move {
                if payload == p0 {
                    Some(gold_p0())
                } else {
                    Some(gold_p3())
                }
            }
        },
        1584,
        Some(1),
        0,
        None,
    )
    .await
    .unwrap();
    assert_eq!(pages.len(), 1);
}

#[test]
fn writes_complete_history_csv() {
    let extract = repo_root().join("hci-logs/extract");
    if !extract.join("att_fff5_fff3.csv").is_file() {
        return;
    }
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("history.csv");
    let args = parse_dump_args([
        "dump-history",
        "--from-extract",
        extract.to_str().unwrap(),
        "--output",
        path.to_str().unwrap(),
        "--newest-time",
        "2025-11-26T15:19:35Z",
    ])
    .unwrap();
    assert_eq!(dump_from_extract(&args), 0);
    assert!(path.is_file());
    let text = fs::read_to_string(&path).unwrap();
    let mut lines = text.lines();
    let _header = lines.next();
    let rows: Vec<_> = lines.collect();
    assert_eq!(rows.len(), 1586);
    assert!(rows[0].starts_with(TARGET_MAC));
    assert!(rows[0].contains("24.0625"));
    assert!(rows[1585].contains(",1585,"));
    assert!(rows[1584].contains(",1584,"));
    assert!(rows[1584].contains("22.9375"));
    assert!(rows[1584].contains("2025-11-26T15:09:35Z"));
    assert!(rows[1585].contains("2025-11-26T15:19:35Z"));
    let raw = rows[0].split(',').nth(5).unwrap();
    match parse_fff3(&hex(raw)) {
        Some(Fff3::History(h)) => assert_eq!(h.index, 0),
        _ => panic!("raw"),
    }
}

#[test]
fn all_rooms_extract_writes_buero_only() {
    let extract = repo_root().join("hci-logs/extract");
    if !extract.join("att_fff5_fff3.csv").is_file() {
        return;
    }
    let rooms = repo_root().join("dashboard/rooms.json");
    let tmp = tempdir().unwrap();
    let args = parse_dump_args([
        "dump-history",
        "--from-extract",
        extract.to_str().unwrap(),
        "--all-rooms",
        "--rooms",
        rooms.to_str().unwrap(),
        "--outdir",
        tmp.path().to_str().unwrap(),
        "--newest-time",
        "2025-11-26T15:19:35Z",
    ])
    .unwrap();
    assert_eq!(dump_from_extract(&args), 0);
    let buero = tmp.path().join("history_f4db000000d9.csv");
    assert!(buero.is_file());
    let n = fs::read_to_string(&buero).unwrap().lines().count() - 1;
    assert_eq!(n, 1586);
    assert!(!tmp.path().join("history_f4d00000021a.csv").is_file());
}

#[test]
fn all_rooms_and_output_conflict() {
    assert!(parse_dump_args([
        "dump-history",
        "--from-extract",
        "x",
        "--all-rooms",
        "--output",
        "y.csv"
    ])
    .is_err());
}
