use std::collections::HashMap;
use std::fs;
use tempfile::tempdir;
use thermobeacon::collect::{parse_collect_args, run_once_with_found};
use thermobeacon::parse::AdvLive;

fn live() -> AdvLive {
    AdvLive {
        temp_c: 22.0625,
        humidity_rh: 64.9375,
        battery_mv: 2997,
        counter: 949579,
        mac: "f4:db:00:00:00:d9".into(),
        raw_hex: "1B001000D9000000DBF4B50B61010F044B7D0E00".into(),
    }
}

#[test]
fn once_writes_header_and_one_row() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("out.csv");
    let args = parse_collect_args([
        "collect",
        "--once",
        "--output",
        path.to_str().unwrap(),
        "--timeout",
        "1",
        "--mac",
        "f4:db:00:00:00:d9",
    ])
    .unwrap();
    let adv = live();
    let found = HashMap::from([(adv.mac.clone(), adv.clone())]);
    let rc = run_once_with_found(&args, &["f4:db:00:00:00:d9".into()], found);
    assert_eq!(rc, 0);
    assert!(path.is_file());
    let text = fs::read_to_string(&path).unwrap();
    let mut lines = text.lines();
    let header = lines.next().unwrap();
    for col in ["timestamp", "mac", "temp_c", "humidity_rh", "raw_hex"] {
        assert!(header.contains(col));
    }
    assert!(!header.contains("battery_mv"));
    let row = lines.next().unwrap();
    assert!(row.contains("f4:db:00:00:00:d9"));
    assert!(row.contains("22.0625"));
    assert!(row.to_lowercase().contains("1b001000d9000000dbf4b50b61010f044b7d0e00"));
    assert!(lines.next().is_none());
}

#[test]
fn timeout_exit_1_no_data_row() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("out.csv");
    let args = parse_collect_args([
        "collect",
        "--once",
        "--output",
        path.to_str().unwrap(),
        "--timeout",
        "1",
        "--mac",
        "f4:db:00:00:00:d9",
    ])
    .unwrap();
    let rc = run_once_with_found(&args, &["f4:db:00:00:00:d9".into()], HashMap::new());
    assert_eq!(rc, 1);
    if path.is_file() {
        let n = fs::read_to_string(&path).unwrap().lines().skip(1).count();
        assert_eq!(n, 0);
    }
}

#[test]
fn once_and_interval_is_error() {
    assert!(parse_collect_args(["collect", "--once", "--interval", "60"]).is_err());
}

#[test]
fn timeout_and_outdir_defaults() {
    let args = parse_collect_args(["collect", "--once"]).unwrap();
    assert_eq!(args.timeout, 15.0);
    assert_eq!(args.outdir.as_os_str(), "data");
}

#[test]
fn output_without_mac_errors_when_many_rooms() {
    let tmp = tempdir().unwrap();
    let path = tmp.path().join("out.csv");
    let args = parse_collect_args([
        "collect",
        "--once",
        "--output",
        path.to_str().unwrap(),
        "--timeout",
        "1",
    ])
    .unwrap();
    let macs = thermobeacon::collect::resolve_macs(&args).unwrap();
    let rc = if args.output.is_some() && macs.len() > 1 {
        2
    } else {
        0
    };
    assert_eq!(rc, 2);
}
