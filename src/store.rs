//! CSV-Speicher für ThermoBeacon-Samples (kein BLE).

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::csvutil::fmt_float;
use crate::mac::mac12;
use crate::parse::AdvLive;

pub const COLUMNS: [&str; 5] = ["timestamp", "mac", "temp_c", "humidity_rh", "raw_hex"];

pub use crate::csvutil::iso_utc_now;

/// Pfad data/thermo_<mac12>_<YYYY-MM-DD>.csv (UTC-Tag, nicht lokal).
pub fn default_csv_path(mac: &str, outdir: impl AsRef<Path>) -> PathBuf {
    let day = chrono::Utc::now().format("%Y-%m-%d");
    outdir
        .as_ref()
        .join(format!("thermo_{}_{}.csv", mac12(mac), day))
}

/// Datei anlegen (inkl. Parent-Dirs), Header nur wenn Datei neu oder leer.
pub fn ensure_header(path: impl AsRef<Path>) -> crate::error::Result<()> {
    let path = path.as_ref();
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }
    let need_header = !path.exists()
        || path.metadata().map(|m| m.len() == 0).unwrap_or(true);
    if need_header {
        let mut f = OpenOptions::new()
            .create(true)
            .write(true)
            .truncate(true)
            .open(path)?;
        writeln!(f, "{}", COLUMNS.join(","))?;
    }
    Ok(())
}

pub fn append_sample(
    path: impl AsRef<Path>,
    timestamp: &str,
    mac: &str,
    temp_c: f64,
    humidity_rh: f64,
    raw_hex: &str,
) -> crate::error::Result<()> {
    let path = path.as_ref();
    ensure_header(path)?;
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            fs::create_dir_all(parent)?;
        }
    }
    let mut f = OpenOptions::new().create(true).append(true).open(path)?;
    writeln!(
        f,
        "{},{},{},{},{}",
        timestamp,
        mac,
        fmt_float(temp_c),
        fmt_float(humidity_rh),
        raw_hex
    )?;
    Ok(())
}

pub fn write_live_sample(path: impl AsRef<Path>, live: &AdvLive) -> crate::error::Result<()> {
    append_sample(
        path,
        &iso_utc_now(),
        &live.mac,
        live.temp_c,
        live.humidity_rh,
        &live.raw_hex,
    )
}
