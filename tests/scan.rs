use thermobeacon::parse::{assemble_mfg_frame, COMPANY_ID};

const GOLD: &str = "1B001000D9000000DBF4B50B61010F044B7D0E00";
const CID_LE: [u8; 2] = [0x1B, 0x00];

fn gold() -> Vec<u8> {
    hex::decode(GOLD).unwrap()
}

#[test]
fn company_and_18_byte_payload_prepends_cid() {
    let frame = gold();
    let payload = &frame[2..];
    assert_eq!(payload.len(), 18);
    let result = assemble_mfg_frame(COMPANY_ID, payload).unwrap();
    assert_eq!(result, [CID_LE.as_slice(), payload].concat());
    assert_eq!(result.len(), 20);
}

#[test]
fn twenty_byte_payload_starting_with_cid_returned_as_is() {
    let frame = gold();
    assert_eq!(frame.len(), 20);
    assert!(frame.starts_with(&CID_LE));
    assert_eq!(assemble_mfg_frame(COMPANY_ID, &frame).unwrap(), frame);
}

#[test]
fn gold_fall_a_and_b() {
    let frame = gold();
    assert_eq!(assemble_mfg_frame(COMPANY_ID, &frame[2..]).unwrap(), frame);
    assert_eq!(assemble_mfg_frame(COMPANY_ID, &frame).unwrap(), frame);
}

#[test]
fn len_19_is_none() {
    let frame = gold();
    assert!(assemble_mfg_frame(COMPANY_ID, &frame[..19]).is_none());
}

#[test]
fn wrong_company_id_18_byte_is_none() {
    let frame = gold();
    assert!(assemble_mfg_frame(0x001C, &frame[2..]).is_none());
}

#[test]
fn twenty_byte_not_starting_with_cid_is_none() {
    let frame = gold();
    let mut bad = vec![0xff, 0xff];
    bad.extend_from_slice(&frame[2..]);
    assert_eq!(bad.len(), 20);
    assert!(!bad.starts_with(&CID_LE));
    assert!(assemble_mfg_frame(COMPANY_ID, &bad).is_none());
}
