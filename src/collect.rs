//! Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben.

use std::collections::HashMap;
use std::path::PathBuf;

use clap::Parser;

use crate::csvutil::fmt_float;
use crate::mac::normalize_mac;
use crate::parse::{format_sample, AdvLive, TARGET_MAC};
use crate::paths::default_rooms_path;
use crate::rooms::{allowlist_macs, load_rooms, mac_in_allowlist};
use crate::store::{default_csv_path, write_live_sample};

#[derive(Debug, Parser)]
#[command(
    name = "collect",
    about = "Live-Samples aus ADV_IND periodisch oder einmalig in CSV schreiben. Kein Connect, kein GATT. Allowlist: rooms.json."
)]
pub struct CollectArgs {
    /// ein Scan-Fenster, dann Exit (Standard ohne --interval)
    #[arg(long = "once", default_value_t = false)]
    pub once: bool,

    /// Sekunden zwischen Versuchen (Loop). Unverträglich mit --once
    #[arg(long = "interval", value_name = "SEK")]
    pub interval: Option<f64>,

    /// Scan-Timeout pro Versuch in Sekunden (Standard: 15)
    #[arg(long = "timeout", default_value_t = 15.0, value_name = "SEK")]
    pub timeout: f64,

    /// Ausgabeverzeichnis wenn --output fehlt (Standard: data)
    #[arg(long = "outdir", default_value = "data")]
    pub outdir: PathBuf,

    /// feste CSV-Datei (nur ein Ziel-MAC; sonst default_csv_path je MAC)
    #[arg(long = "output", value_name = "PATH")]
    pub output: Option<PathBuf>,

    /// Optional: zusätzlich device.address (Windows/Linux: MAC, macOS: UUID).
    #[arg(long = "address", value_name = "ADDR")]
    pub address: Option<String>,

    /// Allowlist rooms.json (Standard: dashboard/rooms.json)
    #[arg(long = "rooms", default_value_os_t = default_rooms_path())]
    pub rooms: PathBuf,

    /// Nur diese Payload-MAC (muss auf der Allowlist stehen)
    #[arg(long = "mac", value_name = "MAC")]
    pub mac: Option<String>,
}

impl CollectArgs {
    pub fn validate(&self) -> Result<(), String> {
        if self.once && self.interval.is_some() {
            return Err("--once und --interval schließen sich aus".into());
        }
        if self.timeout <= 0.0 {
            return Err("--timeout muss größer als 0 sein".into());
        }
        if let Some(i) = self.interval {
            if i <= 0.0 {
                return Err("--interval muss größer als 0 sein".into());
            }
        }
        Ok(())
    }
}

pub fn parse_collect_args<I, T>(args: I) -> Result<CollectArgs, i32>
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    match CollectArgs::try_parse_from(args) {
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

pub fn resolve_macs(args: &CollectArgs) -> Result<Vec<String>, String> {
    let rooms = load_rooms(&args.rooms).map_err(|e| e.to_string())?;
    let mut allowed = allowlist_macs(&rooms);
    if allowed.is_empty() {
        allowed = vec![TARGET_MAC.to_string()];
    }
    if let Some(mac) = &args.mac {
        let want = normalize_mac(mac);
        if !mac_in_allowlist(&want, &allowed) {
            return Err(format!(
                "MAC {} steht nicht in der Allowlist ({}).",
                want,
                args.rooms.display()
            ));
        }
        return Ok(vec![want]);
    }
    Ok(allowed)
}

pub fn resolve_csv_path(args: &CollectArgs, mac: &str) -> PathBuf {
    if let Some(out) = &args.output {
        out.clone()
    } else {
        default_csv_path(mac, &args.outdir)
    }
}

pub fn timeout_msg(timeout: f64, macs: &[String]) -> String {
    format!(
        "Kein Live-Sample innerhalb von {} s (Allowlist {}).",
        fmt_float(timeout),
        macs.join(", ")
    )
}

pub fn report_hit(path: &std::path::Path, live: &AdvLive) {
    println!("{}", format_sample(live));
    println!("geschrieben: {}", path.display());
}

pub fn write_found(args: &CollectArgs, found: &HashMap<String, AdvLive>) -> Vec<PathBuf> {
    let mut written = Vec::new();
    for live in found.values() {
        let path = resolve_csv_path(args, &live.mac);
        if let Err(e) = write_live_sample(&path, live) {
            eprintln!("{e}");
            continue;
        }
        report_hit(&path, live);
        written.push(path);
    }
    written
}

pub fn run_once_with_found(
    args: &CollectArgs,
    macs: &[String],
    found: HashMap<String, AdvLive>,
) -> i32 {
    if found.is_empty() {
        eprintln!("{}", timeout_msg(args.timeout, macs));
        return 1;
    }
    write_found(args, &found);
    let missing: Vec<_> = macs
        .iter()
        .filter(|m| !found.contains_key(*m))
        .cloned()
        .collect();
    if !missing.is_empty() {
        eprintln!("kein Sample in diesem Fenster: {}", missing.join(", "));
    }
    0
}
