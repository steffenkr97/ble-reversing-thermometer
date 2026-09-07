//! ADV-Scan-CLI (Flags). Der eigentliche Scan liegt in `ble`.

use clap::Parser;

use crate::mac::normalize_mac;
use crate::parse::TARGET_MAC;
use crate::paths::default_rooms_path;
use crate::rooms::{allowlist_macs, load_rooms, mac_in_allowlist};

#[derive(Debug, Parser)]
#[command(
    name = "scan-live",
    about = "Live-Temperatur/Luftfeuchtigkeit aus ADV_IND Manufacturer Data. Kein Connect, kein GATT."
)]
pub struct ScanArgs {
    /// Scan-Timeout in Sekunden (Standard: 15)
    #[arg(long = "timeout", default_value_t = 15.0, value_name = "SEK")]
    pub timeout: f64,

    /// Optional: zusätzlich device.address filtern (Windows/Linux: MAC, macOS: UUID).
    #[arg(long = "address", value_name = "ADDR")]
    pub address: Option<String>,

    /// Payload-MAC (Standard: Büro). Muss auf der Allowlist stehen.
    #[arg(long = "mac", default_value = TARGET_MAC)]
    pub mac: String,

    /// Allowlist rooms.json (Standard: dashboard/rooms.json)
    #[arg(long = "rooms", default_value_os_t = default_rooms_path())]
    pub rooms: std::path::PathBuf,
}

impl ScanArgs {
    pub fn validate(&self) -> Result<(), String> {
        if self.timeout <= 0.0 {
            return Err("--timeout muss größer als 0 sein".into());
        }
        Ok(())
    }
}

pub fn parse_scan_args<I, T>(args: I) -> Result<ScanArgs, i32>
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    match ScanArgs::try_parse_from(args) {
        Ok(a) => {
            if let Err(msg) = a.validate() {
                eprintln!("{msg}");
                return Err(2);
            }
            Ok(a)
        }
        Err(e) => {
            let _ = e.print();
            if e.exit_code() == 0 {
                Err(0)
            } else {
                Err(2)
            }
        }
    }
}

pub fn allowed_from_rooms(rooms_path: &std::path::Path, mac: Option<&str>) -> Result<Vec<String>, String> {
    let rooms = load_rooms(rooms_path).map_err(|e| e.to_string())?;
    let mut allowed = allowlist_macs(&rooms);
    if allowed.is_empty() {
        allowed = vec![TARGET_MAC.to_string()];
    }
    if let Some(mac) = mac {
        let want = normalize_mac(mac);
        if !mac_in_allowlist(&want, &allowed) {
            return Err(format!(
                "MAC {} steht nicht in der Allowlist ({})",
                want,
                rooms_path.display()
            ));
        }
        return Ok(vec![want]);
    }
    Ok(allowed)
}
