//! CSV-Helfer: Python-`str(float)`-ähnliche Ausgabe.

pub fn fmt_float(v: f64) -> String {
    if !v.is_finite() {
        return v.to_string();
    }
    let s = format!("{v:.16}");
    let s = s.trim_end_matches('0').trim_end_matches('.').to_string();
    if !s.contains('.') && !s.contains('e') && !s.contains('E') {
        format!("{s}.0")
    } else {
        s
    }
}

pub fn iso_utc_now() -> String {
    chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string()
}

pub fn parse_iso_utc(value: &str) -> crate::error::Result<chrono::DateTime<chrono::Utc>> {
    let text = value.trim();
    if text.is_empty() {
        return Err(crate::error::Error::EmptyTimestamp);
    }
    let text = if let Some(stripped) = text.strip_suffix('Z') {
        format!("{stripped}+00:00")
    } else {
        text.to_string()
    };
    chrono::DateTime::parse_from_rfc3339(&text)
        .or_else(|_| {
            chrono::NaiveDateTime::parse_from_str(&text, "%Y-%m-%dT%H:%M:%S")
                .map(|n| n.and_utc().fixed_offset())
                .or_else(|_| {
                    chrono::NaiveDateTime::parse_from_str(&text, "%Y-%m-%dT%H:%M:%S%.f")
                        .map(|n| n.and_utc().fixed_offset())
                })
        })
        .map(|dt| dt.with_timezone(&chrono::Utc))
        .map_err(|e| crate::error::Error::Timestamp(e.to_string()))
}

pub fn format_iso_utc(dt: chrono::DateTime<chrono::Utc>) -> String {
    dt.format("%Y-%m-%dT%H:%M:%SZ").to_string()
}
