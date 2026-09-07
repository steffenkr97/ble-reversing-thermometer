use std::fs;
use tempfile::tempdir;
use thermobeacon::mac::normalize_mac;
use thermobeacon::paths::default_rooms_path;
use thermobeacon::rooms::{allowlist_macs, encoding_checked_macs, load_rooms, mac_in_allowlist};

#[test]
fn five_entries_only_buero_checked() {
    let rooms = load_rooms(thermobeacon::paths::repo_root().join("dashboard/rooms.json")).unwrap();
    assert_eq!(rooms.len(), 5);
    let macs = allowlist_macs(&rooms);
    assert_eq!(macs[0], "f4:db:00:00:00:d9");
    assert!(macs.contains(&"f4:d0:00:00:02:1a".into()));
    assert!(macs.contains(&"f4:db:00:00:02:37".into()));
    assert!(macs.contains(&"f4:db:00:00:02:42".into()));
    assert!(macs.contains(&"62:53:00:00:0f:1f".into()));
    let checked = encoding_checked_macs(&rooms);
    assert_eq!(checked, vec!["f4:db:00:00:00:d9".to_string()]);
    let buero = &rooms[0];
    assert!(buero.confirmed);
    assert_eq!(buero.system_id.as_deref(), Some("D90000000000DBF4"));
    for room in &rooms[1..] {
        assert!(!room.confirmed);
        assert!(!room.encoding_checked);
    }
}

#[test]
fn encoding_checked_defaults_to_confirmed() {
    let dir = tempdir().unwrap();
    let path = dir.path().join("rooms.json");
    fs::write(
        &path,
        r#"{"rooms":[{"id":"x","name":"X","mac":"aa:bb:cc:dd:ee:ff","confirmed":true}]}"#,
    )
    .unwrap();
    let rooms = load_rooms(&path).unwrap();
    assert!(rooms[0].encoding_checked);
    assert!(mac_in_allowlist("AABBCCDDEEFF", &allowlist_macs(&rooms)));
}

#[test]
fn default_path_exists() {
    assert!(default_rooms_path().is_file());
}

#[test]
fn normalize_variants() {
    assert_eq!(normalize_mac("F4:DB:00:00:00:D9"), "f4:db:00:00:00:d9");
    assert_eq!(normalize_mac("f4db000000d9"), "f4:db:00:00:00:d9");
}
