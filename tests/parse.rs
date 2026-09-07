use thermobeacon::parse::{
    build_history_07_write, parse_adv_manufacturer, parse_fff3, AdvLive, Count01, Fff3, History07,
    Status1A, TARGET_MAC,
};

fn hex(s: &str) -> Vec<u8> {
    hex::decode(s.replace(' ', "")).unwrap()
}

#[test]
fn adv_rec_171_live() {
    let mfg = hex("1B001000D9000000DBF4B50B61010F044B7D0E00");
    let result = parse_adv_manufacturer(&mfg, None).unwrap();
    assert_eq!(result.temp_c, 22.0625);
    assert_eq!(result.humidity_rh, 64.9375);
    assert_eq!(result.battery_mv, 2997);
    assert_eq!(result.mac, TARGET_MAC);
    assert_eq!(result.mac, "f4:db:00:00:00:d9");
    assert_eq!(result.counter, 949579);
    let _ = AdvLive {
        temp_c: result.temp_c,
        humidity_rh: result.humidity_rh,
        battery_mv: result.battery_mv,
        counter: result.counter,
        mac: result.mac.clone(),
        raw_hex: result.raw_hex.clone(),
    };
}

#[test]
fn minmax_22_byte_is_none() {
    let mfg = hex("1B001000D9000000DBF4A7015F0F00002A017E0C0400");
    assert_eq!(mfg.len(), 22);
    assert!(parse_adv_manufacturer(&mfg, None).is_none());
}

#[test]
fn foreign_mac_is_none() {
    let mut mfg = hex("1B001000D9000000DBF4B50B61010F044B7D0E00");
    mfg[4] = 0xAA;
    assert!(parse_adv_manufacturer(&mfg, None).is_none());
}

#[test]
fn allowlist_accepts_other_mac() {
    let mut mfg = hex("1B001000D9000000DBF4B50B61010F044B7D0E00");
    let mac_le: Vec<u8> = hex("f4d00000021a").into_iter().rev().collect();
    mfg[4..10].copy_from_slice(&mac_le);
    assert!(parse_adv_manufacturer(&mfg, None).is_none());
    let allowed = vec!["f4:d0:00:00:02:1a".to_string()];
    let live = parse_adv_manufacturer(&mfg, Some(&allowed)).unwrap();
    assert_eq!(live.mac, "f4:d0:00:00:02:1a");
    assert_eq!(live.temp_c, 22.0625);
}

#[test]
fn allowlist_rejects_unlisted_mac() {
    let mfg = hex("1B001000D9000000DBF4B50B61010F044B7D0E00");
    let allowed = vec!["f4:d0:00:00:02:1a".to_string()];
    assert!(parse_adv_manufacturer(&mfg, Some(&allowed)).is_none());
}

#[test]
fn history_07_count03_index0() {
    let data = hex("07000000000381017B017901B403BC03CB030000");
    match parse_fff3(&data) {
        Some(Fff3::History(History07 {
            index,
            count,
            records,
            ..
        })) => {
            assert_eq!(index, 0);
            assert_eq!(count, 3);
            assert_eq!(
                records,
                vec![(24.0625, 59.25), (23.6875, 59.75), (23.5625, 60.6875)]
            );
        }
        other => panic!("{other:?}"),
    }
}

#[test]
fn history_07_count01_hum_at_offset8() {
    let data = hex("0730060000016F01E8036E010E040F04F2030000");
    match parse_fff3(&data) {
        Some(Fff3::History(h)) => {
            assert_eq!(h.index, 1584);
            assert_eq!(h.count, 1);
            assert_eq!(h.records.len(), 1);
            assert_eq!(h.records[0], (22.9375, 62.5));
        }
        other => panic!("{other:?}"),
    }
}

#[test]
fn status_1a() {
    let mut data = hex("1A01000100");
    data.extend(std::iter::repeat(0).take(15));
    match parse_fff3(&data) {
        Some(Fff3::Status(Status1A { .. })) => assert_eq!(data.len(), 20),
        other => panic!("{other:?}"),
    }
}

#[test]
fn count_01_form_a() {
    let mut data = hex("012F0600");
    data.extend(std::iter::repeat(0).take(16));
    match parse_fff3(&data) {
        Some(Fff3::Count(Count01 { sample_count, .. })) => assert_eq!(sample_count, 1583),
        other => panic!("{other:?}"),
    }
}

#[test]
fn opcode_f3_is_none() {
    let mut data = vec![0xF3];
    data.extend(std::iter::repeat(0).take(19));
    assert_eq!(data.len(), 20);
    assert!(parse_fff3(&data).is_none());
}

#[test]
fn build_writes() {
    assert_eq!(build_history_07_write(0, 3), hex("070000000003"));
    assert_eq!(build_history_07_write(0x011D, 3), hex("071D01000003"));
    assert_eq!(build_history_07_write(1584, 1), hex("073006000001"));
}
