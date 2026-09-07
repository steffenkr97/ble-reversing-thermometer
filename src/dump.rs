//! History-Dump-CLI: Extract oder GATT 1A → 01 → 07-Pages.

use std::path::PathBuf;

use clap::{ArgGroup, Parser};

use crate::csvutil::{iso_utc_now, parse_iso_utc};
use crate::history::{
    apply_inferred_timestamps, assert_allowed_fff5_write, default_history_csv_path,
    load_extract_history, page_plan, samples_from_pages, write_history_csv,
    HistoryRow, INTERVAL_SEC_HYPOTHESIS,
};
use crate::mac::normalize_mac;
use crate::parse::{
    build_history_07_write, parse_fff3, Fff3, History07, TARGET_MAC, TARGET_SYSTEM_ID,
};
use crate::paths::default_rooms_path;
use crate::rooms::{allowlist_macs, load_rooms, room_by_mac, Room};

#[derive(Debug, Clone, Parser)]
#[command(
    name = "dump-history",
    about = "History-Dump ThermoBeacon: CCCD, dann 1A → 01 → alle 07-Pages in data/history_<mac12>.csv. Oder --from-extract ohne BLE.",
    after_help = "Beispiele:\n  cargo run --bin dump-history -- --from-extract hci-logs/extract\n  cargo run --bin dump-history -- --address f4:db:00:00:00:d9\n  cargo run --bin dump-history -- --use-system-id\n  cargo run --bin dump-history -- --from-extract hci-logs/extract --all-rooms\n\nNicht senden: 04 / 05 / 18 / 19 / 0F / F3.\ntimestamp_inferred ist Hypothese (10 min, ADV-Counter/Count ≈ 600 s)."
)]
#[command(group(ArgGroup::new("source_conflict").args(["from_extract", "address"]).multiple(false)))]
pub struct DumpArgs {
    /// BLE-Adresse (Linux/Windows: MAC; macOS: CoreBluetooth-UUID)
    #[arg(short = 'a', long = "address")]
    pub address: Option<String>,

    /// Scan, Ziel nur bei 2A23 == TARGET_SYSTEM_ID (ohne --address und ohne Extract)
    #[arg(long = "use-system-id", default_value_t = false)]
    pub use_system_id: bool,

    /// att_fff5_fff3.csv oder Extract-Ordner. Kein BLE, keine Writes.
    #[arg(long = "from-extract", value_name = "PATH")]
    pub from_extract: Option<PathBuf>,

    /// Geräte-MAC für CSV/Extract (Standard: Büro)
    #[arg(long = "mac", default_value = TARGET_MAC)]
    pub mac: String,

    /// Allowlist rooms.json (für --all-rooms und System-ID)
    #[arg(long = "rooms", default_value_os_t = default_rooms_path())]
    pub rooms: PathBuf,

    /// Extract/GATT für jede MAC in rooms.json (je history_<mac12>.csv)
    #[arg(long = "all-rooms", default_value_t = false)]
    pub all_rooms: bool,

    /// Ausgabeverzeichnis wenn --output fehlt (Standard: data)
    #[arg(long = "outdir", default_value = "data")]
    pub outdir: PathBuf,

    /// feste CSV-Datei (sonst history_<mac12>.csv)
    #[arg(long = "output", value_name = "PATH")]
    pub output: Option<PathBuf>,

    /// Hypothese für timestamp_inferred (Standard: 600 = 10 min)
    #[arg(long = "interval-sec", default_value_t = INTERVAL_SEC_HYPOTHESIS, value_name = "SEK")]
    pub interval_sec: f64,

    /// timestamp_inferred leer lassen
    #[arg(long = "no-timestamps", default_value_t = false)]
    pub no_timestamps: bool,

    /// Anker fürs neueste Sample (ISO-8601 UTC). Sonst Dump-/Capture-Zeit.
    #[arg(long = "newest-time", value_name = "ISO")]
    pub newest_time: Option<String>,

    /// Nur die ersten N Pages (Tests / Abbruch). Live: trotzdem 1A+01.
    #[arg(long = "max-pages", value_name = "N")]
    pub max_pages: Option<i64>,

    /// Extract: auch old/*.cfa (2018-Zeitstempel)
    #[arg(long = "include-old", default_value_t = false)]
    pub include_old: bool,

    /// Wartezeit je Notify (Standard: 2; Capture-Median 07 ≈ 0,16 s)
    #[arg(long = "notify-timeout", default_value_t = 2.0, value_name = "SEK")]
    pub notify_timeout: f64,

    /// Wiederholungen pro 07-Page bei Timeout/Parse (Standard: 2)
    #[arg(long = "retries", default_value_t = 2)]
    pub retries: i64,
}

impl DumpArgs {
    pub fn validate(&self) -> Result<(), String> {
        if self.from_extract.is_some() && self.address.is_some() {
            return Err("--from-extract und --address schließen sich aus".into());
        }
        if self.from_extract.is_some() && self.use_system_id {
            return Err("--from-extract und --use-system-id schließen sich aus".into());
        }
        if self.all_rooms && self.output.is_some() {
            return Err("--all-rooms und --output schließen sich aus".into());
        }
        if self.interval_sec <= 0.0 {
            return Err("--interval-sec muss größer als 0 sein".into());
        }
        if self.notify_timeout <= 0.0 {
            return Err("--notify-timeout muss größer als 0 sein".into());
        }
        if self.retries < 0 {
            return Err("--retries muss >= 0 sein".into());
        }
        if let Some(n) = self.max_pages {
            if n < 0 {
                return Err("--max-pages muss >= 0 sein".into());
            }
        }
        if let Some(ts) = &self.newest_time {
            parse_iso_utc(ts).map_err(|_| "--newest-time ist kein ISO-8601-Zeitstempel".to_string())?;
        }
        Ok(())
    }
}

pub fn parse_dump_args<I, T>(args: I) -> Result<DumpArgs, i32>
where
    I: IntoIterator<Item = T>,
    T: Into<std::ffi::OsString> + Clone,
{
    match DumpArgs::try_parse_from(args) {
        Ok(mut a) => {
            if let Err(msg) = a.validate() {
                eprintln!("{msg}");
                return Err(2);
            }
            if a.from_extract.is_none() && a.address.is_none() && !a.use_system_id {
                a.use_system_id = true;
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

pub fn expected_system_id(mac: &str, rooms: &[Room]) -> Option<Vec<u8>> {
    if let Some(room) = room_by_mac(rooms, mac) {
        if let Some(hex_id) = &room.system_id {
            if let Ok(bytes) = hex::decode(hex_id) {
                return Some(bytes);
            }
        }
    }
    if normalize_mac(mac) == TARGET_MAC {
        return Some(TARGET_SYSTEM_ID.to_vec());
    }
    None
}

pub fn rooms_or_empty(path: &std::path::Path) -> Vec<Room> {
    load_rooms(path).unwrap_or_default()
}

pub fn resolve_csv_path(args: &DumpArgs, mac: Option<&str>) -> PathBuf {
    if let Some(out) = &args.output {
        return out.clone();
    }
    default_history_csv_path(mac.unwrap_or(&args.mac), &args.outdir)
}

pub fn dump_macs(args: &DumpArgs) -> Vec<String> {
    if args.all_rooms {
        let rooms = rooms_or_empty(&args.rooms);
        let macs = allowlist_macs(&rooms);
        if macs.is_empty() {
            vec![normalize_mac(&args.mac)]
        } else {
            macs
        }
    } else {
        vec![normalize_mac(&args.mac)]
    }
}

pub fn stamp_rows(
    rows: Vec<HistoryRow>,
    args: &DumpArgs,
    newest_utc: &str,
    newest_index: Option<i64>,
) -> crate::error::Result<Vec<HistoryRow>> {
    if args.no_timestamps || rows.is_empty() {
        return Ok(rows);
    }
    apply_inferred_timestamps(&rows, newest_utc, args.interval_sec, newest_index)
}

pub async fn fetch_history_pages<F, Fut>(
    mut write_and_wait: F,
    sample_count: i64,
    max_pages: Option<usize>,
    retries: u32,
    mut on_progress: Option<Box<dyn FnMut(usize, usize, &History07) + Send>>,
) -> anyhow::Result<Vec<History07>>
where
    F: FnMut(Vec<u8>) -> Fut,
    Fut: std::future::Future<Output = Option<Vec<u8>>>,
{
    let mut plan = page_plan(sample_count)?;
    if let Some(n) = max_pages {
        plan.truncate(n);
    }
    let mut pages = Vec::new();
    let total = plan.len();
    for (step, (index, count)) in plan.into_iter().enumerate() {
        let step = step + 1;
        let payload = build_history_07_write(index, count);
        assert_allowed_fff5_write(&payload)?;
        let mut parsed: Option<History07> = None;
        for _ in 0..=retries {
            let raw = write_and_wait(payload.clone()).await;
            let Some(raw) = raw else {
                continue;
            };
            if let Some(Fff3::History(cand)) = parse_fff3(&raw) {
                parsed = Some(cand);
                break;
            }
        }
        let Some(parsed) = parsed else {
            anyhow::bail!("History-Page index={index} count={count} ohne gültiges Notify");
        };
        if let Some(cb) = on_progress.as_mut() {
            cb(step, total, &parsed);
        }
        pages.push(parsed);
    }
    Ok(pages)
}

pub fn dump_from_extract_one(args: &DumpArgs, mac: &str) -> i32 {
    let (rows, meta) = match load_extract_history(
        args.from_extract.as_ref().expect("from_extract"),
        mac,
        !args.include_old,
    ) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{e}");
            return 1;
        }
    };
    if rows.is_empty() {
        eprintln!(
            "Keine 07-Pages für {} in {}.",
            normalize_mac(mac),
            meta.att_path.display()
        );
        return 1;
    }
    let newest_utc = args
        .newest_time
        .clone()
        .or_else(|| meta.last_ts.clone())
        .unwrap_or_else(iso_utc_now);
    let newest_index = meta.newest_index.or_else(|| rows.last().map(|r| r.index));
    let rows = match stamp_rows(rows, args, &newest_utc, newest_index) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return 1;
        }
    };
    let path = resolve_csv_path(args, Some(mac));
    if let Err(e) = write_history_csv(&path, &rows) {
        eprintln!("{e}");
        return 1;
    }
    println!(
        "Extract {}  mac={}  pages={}  samples={}  count_01={}  newest_index={}",
        meta.file.as_deref().unwrap_or("-"),
        normalize_mac(mac),
        meta.page_count,
        rows.len(),
        meta.count_01
            .map(|c| c.to_string())
            .unwrap_or_else(|| "None".into()),
        newest_index
            .map(|i| i.to_string())
            .unwrap_or_else(|| "None".into()),
    );
    println!("geschrieben: {}", path.display());
    if !args.no_timestamps {
        let anchor = rows
            .last()
            .map(|r| r.timestamp_inferred.as_str())
            .filter(|s| !s.is_empty())
            .unwrap_or(&newest_utc);
        println!(
            "timestamp_inferred: Anker {anchor}  interval={} s (Hypothese)",
            args.interval_sec
        );
    }
    0
}

pub fn dump_from_extract(args: &DumpArgs) -> i32 {
    let macs = dump_macs(args);
    let mut rc = 1;
    let mut wrote = 0;
    for mac in &macs {
        let one = dump_from_extract_one(args, mac);
        if one == 0 {
            wrote += 1;
            rc = 0;
        }
    }
    if args.all_rooms && wrote == 0 {
        return 1;
    }
    if args.all_rooms {
        println!("Extract --all-rooms: {wrote}/{} MACs mit History.", macs.len());
    }
    rc
}

pub fn progress(step: usize, total: usize, parsed: &History07) {
    if step == 1 || step == total || step % 25 == 0 {
        println!(
            "  Page {}/{}  index={}  count={}  records={}",
            step,
            total,
            parsed.index,
            parsed.count,
            parsed.records.len()
        );
    }
}

pub fn finish_dump_rows(
    args: &DumpArgs,
    mac: &str,
    pages: &[History07],
    sample_count: i64,
    elapsed: f64,
) -> i32 {
    let rows = samples_from_pages(pages, mac);
    let newest_utc = args
        .newest_time
        .clone()
        .unwrap_or_else(iso_utc_now);
    let newest_index = if sample_count > 0 {
        Some(sample_count - 1)
    } else {
        None
    };
    let rows = match stamp_rows(rows, args, &newest_utc, newest_index) {
        Ok(r) => r,
        Err(e) => {
            eprintln!("{e}");
            return 1;
        }
    };
    let path = resolve_csv_path(args, Some(mac));
    if let Err(e) = write_history_csv(&path, &rows) {
        eprintln!("{e}");
        return 1;
    }
    println!(
        "fertig: {} Samples aus {} Pages in {:.1} s",
        rows.len(),
        pages.len(),
        elapsed
    );
    println!("geschrieben: {}", path.display());
    if !rows.is_empty() && !args.no_timestamps {
        let anchor = rows
            .last()
            .map(|r| r.timestamp_inferred.as_str())
            .filter(|s| !s.is_empty())
            .unwrap_or(&newest_utc);
        println!(
            "timestamp_inferred: Anker {anchor}  interval={} s (Hypothese)",
            args.interval_sec
        );
    }
    if sample_count > 0 && (rows.len() as i64) < sample_count {
        eprintln!(
            "Hinweis: CSV hat {} von {} Samples (--max-pages?).",
            rows.len(),
            sample_count
        );
    }
    0
}
