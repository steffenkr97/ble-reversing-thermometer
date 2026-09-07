//! MAC-Normalisierung (Allowlist, CSV-Dateinamen).

pub fn compact_mac(mac: &str) -> String {
    mac.replace([':', '-', '.'], "").to_lowercase()
}

pub fn mac12(mac: &str) -> String {
    compact_mac(mac)
}

pub fn normalize_mac(mac: &str) -> String {
    let compact = compact_mac(mac);
    if compact.len() == 12 && compact.chars().all(|c| c.is_ascii_hexdigit()) {
        return compact
            .as_bytes()
            .chunks(2)
            .map(|c| std::str::from_utf8(c).unwrap_or("00"))
            .collect::<Vec<_>>()
            .join(":");
    }
    mac.trim().to_lowercase()
}

pub fn mac_le_to_str(mac_le: &[u8]) -> String {
    mac_le
        .iter()
        .rev()
        .map(|b| format!("{b:02x}"))
        .collect::<Vec<_>>()
        .join(":")
}

pub fn macs_equal(a: &str, b: &str) -> bool {
    compact_mac(a) == compact_mac(b)
}

pub fn parse_hex_bytes(value: &str) -> Option<Vec<u8>> {
    let compact: String = value
        .chars()
        .filter(|c| !c.is_whitespace() && *c != ':')
        .collect();
    if compact.len() % 2 != 0 {
        return None;
    }
    hex::decode(compact).ok()
}
