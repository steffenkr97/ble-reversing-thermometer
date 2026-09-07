use thermobeacon::btsnoop::{find_cfa, parse_file, value_handles};
use thermobeacon::paths::repo_root;

#[test]
fn parse_entry_capture() {
    let logs = repo_root().join("hci-logs");
    let files = find_cfa(&logs);
    assert!(files.iter().any(|p| p
        .file_name()
        .unwrap()
        .to_string_lossy()
        .contains("14_52_44")));
    let path = files
        .iter()
        .find(|p| p.file_name().unwrap().to_string_lossy().contains("14_52_44"))
        .unwrap();
    let cap = parse_file(path);
    assert_eq!(cap.datalink, 1002);
    assert!(cap.records > 0);
    let hs = value_handles(&cap);
    assert_eq!(hs.get("FFF5").copied().flatten(), Some(0x0021));
    assert_eq!(hs.get("FFF3").copied().flatten(), Some(0x0024));
    let (writes, notifs, _) = thermobeacon::btsnoop::att_control_notify(&cap);
    assert!(!writes.is_empty());
    assert!(notifs.iter().any(|n| !n.value.is_empty() && n.value[0] == 0x07));
}

#[test]
fn att_timestamp_matches_python_millis() {
    let logs = repo_root().join("hci-logs");
    let path = find_cfa(&logs)
        .into_iter()
        .find(|p| {
            p.file_name()
                .unwrap()
                .to_string_lossy()
                .contains("14_52_44")
        })
        .unwrap();
    let cap = parse_file(&path);
    let pdu = cap
        .att
        .iter()
        .find(|p| p.rec == 355)
        .expect("rec 355 in 14_52_44");
    // Python: %f[:-3] → Millisekunden, Extract att.csv Zeile 2.
    assert_eq!(pdu.timestamp, "2025-11-26T14:53:01.758Z");
}
