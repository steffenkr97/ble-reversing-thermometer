use clap::Parser;
use thermobeacon::collect::{parse_collect_args, report_hit, resolve_csv_path};
use thermobeacon::dump::dump_from_extract;
use thermobeacon::history::default_history_csv_path;
use thermobeacon::mvp::{
    append_evidence, compare_live_to_newest_history, default_evidence_path, evidence_record,
    format_compare, infer_interval_sec, load_evidence, rows_from_history_csv, HUM_TOL, TEMP_TOL_C,
};
use thermobeacon::parse::TARGET_MAC;

#[derive(Parser)]
#[command(
    name = "mvp-buero",
    about = "Büro-MVP: collect + dump-history, History gegen ADV, Intervall-Beleg (Count 01 + Uhr). Nicht senden: 04 / 18."
)]
struct Args {
    /// BLE-Adresse (Standard: Büro-MAC)
    #[arg(long = "address", default_value = TARGET_MAC)]
    address: String,
    /// Payload-MAC / CSV-MAC (Standard: Büro)
    #[arg(long = "mac", default_value = TARGET_MAC)]
    mac: String,
    /// ADV-Scan-Timeout (Standard: 15)
    #[arg(long = "timeout", default_value_t = 15.0)]
    timeout: f64,
    /// CSV-Verzeichnis (Standard: data)
    #[arg(long = "outdir", default_value = "data")]
    outdir: std::path::PathBuf,
    /// JSONL für Count+Uhr
    #[arg(long = "evidence", default_value_os_t = default_evidence_path())]
    evidence: std::path::PathBuf,
    /// History aus HCI-Extract statt GATT (kein Live-Dump)
    #[arg(long = "from-extract")]
    from_extract: Option<std::path::PathBuf>,
    /// kein ADV-Scan (nur Dump/Extract + Evidence)
    #[arg(long = "skip-collect", default_value_t = false)]
    skip_collect: bool,
    /// kein History-Dump (nur Live-CSV + Evidence ohne Count)
    #[arg(long = "skip-dump", default_value_t = false)]
    skip_dump: bool,
    /// an dump-history durchreichen (Test)
    #[arg(long = "max-pages")]
    max_pages: Option<i64>,
    /// GATT-Notify-Timeout je Page
    #[arg(long = "notify-timeout", default_value_t = 2.0)]
    notify_timeout: f64,
}

#[tokio::main]
async fn main() {
    let args = match Args::try_parse() {
        Ok(a) => {
            if a.timeout <= 0.0 {
                eprintln!("--timeout muss größer als 0 sein");
                std::process::exit(2);
            }
            if a.skip_collect && a.skip_dump && a.from_extract.is_none() {
                eprintln!("nichts zu tun (--skip-collect und --skip-dump)");
                std::process::exit(2);
            }
            a
        }
        Err(e) => {
            let _ = e.print();
            std::process::exit(if e.exit_code() == 0 { 0 } else { 2 });
        }
    };

    let mut live = None;
    let mut sample_count = None;
    let mut history_rows = Vec::new();

    if !args.skip_collect {
        println!("== 1. Live-CSV (ADV) ==");
        match thermobeacon::ble::scan_live(
            args.timeout,
            Some(&args.address),
            Some(&[args.mac.clone()]),
        )
        .await
        {
            Ok(Some(sample)) => {
                let collect_args = parse_collect_args([
                    "collect",
                    "--once",
                    "--outdir",
                    args.outdir.to_str().unwrap_or("data"),
                    "--mac",
                    &args.mac,
                ])
                .unwrap_or_else(|c| {
                    std::process::exit(c);
                });
                let path = resolve_csv_path(&collect_args, &sample.mac);
                if let Err(e) = thermobeacon::store::write_live_sample(&path, &sample) {
                    eprintln!("{e}");
                    std::process::exit(1);
                }
                report_hit(&path, &sample);
                live = Some(sample);
            }
            Ok(None) => {
                eprintln!(
                    "Kein Live-Sample innerhalb von {} s (Ziel-MAC {}).",
                    thermobeacon::csvutil::fmt_float(args.timeout),
                    args.mac
                );
                std::process::exit(1);
            }
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
    }

    if !args.skip_dump || args.from_extract.is_some() {
        println!("== 2. History-Dump ==");
        let mut dump_argv = vec![
            "dump-history".into(),
            "--mac".into(),
            args.mac.clone(),
            "--outdir".into(),
            args.outdir.to_string_lossy().into_owned(),
        ];
        if let Some(p) = &args.from_extract {
            dump_argv.push("--from-extract".into());
            dump_argv.push(p.to_string_lossy().into_owned());
        } else {
            dump_argv.push("--address".into());
            dump_argv.push(args.address.clone());
            dump_argv.push("--notify-timeout".into());
            dump_argv.push(args.notify_timeout.to_string());
            if let Some(n) = args.max_pages {
                dump_argv.push("--max-pages".into());
                dump_argv.push(n.to_string());
            }
        }
        let dump_args = match thermobeacon::dump::parse_dump_args(dump_argv) {
            Ok(a) => a,
            Err(c) => std::process::exit(c),
        };
        let rc = if dump_args.from_extract.is_some() {
            dump_from_extract(&dump_args)
        } else {
            match thermobeacon::ble::dump_via_gatt(&dump_args, &args.address, true).await {
                Ok(c) => c,
                Err(e) => {
                    eprintln!("{e}");
                    1
                }
            }
        };
        if rc != 0 {
            std::process::exit(rc);
        }
        let hist_path = default_history_csv_path(&args.mac, &args.outdir);
        if hist_path.is_file() {
            if let Ok(rows) = rows_from_history_csv(&hist_path) {
                history_rows = rows;
                if !history_rows.is_empty() {
                    sample_count = history_rows
                        .iter()
                        .filter_map(|r| {
                            r.get("index")
                                .and_then(|v| v.as_str())
                                .and_then(|s| s.parse::<i64>().ok())
                        })
                        .max()
                        .map(|i| i + 1)
                        .or(Some(history_rows.len() as i64));
                }
            }
        }
    }

    let mut cmp = None;
    if let (Some(ref live), true) = (&live, !history_rows.is_empty()) {
        println!("== 3. History vs. ADV ==");
        let c = compare_live_to_newest_history(live, &history_rows, TEMP_TOL_C, HUM_TOL);
        println!("{}", format_compare(&c));
        if !c.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) {
            eprintln!("Hinweis: Dump-Zeit vs. Live kann bei 10-min-Takt abweichen.");
        }
        cmp = Some(c);
    }

    let record = evidence_record(
        &args.mac,
        live.as_ref(),
        sample_count,
        cmp.as_ref(),
    );
    if let Err(e) = append_evidence(&args.evidence, &record) {
        eprintln!("{e}");
    }
    println!("Evidence: {}", args.evidence.display());

    let evidence = load_evidence(&args.evidence).unwrap_or_default();
    match infer_interval_sec(&evidence, &args.mac) {
        None => println!(
            "Intervall: zweiter Lauf (Count 01 + Uhr) nötig, damit die 10-min-Hypothese prüfbar ist."
        ),
        Some(inferred) if inferred.get("ok").and_then(|v| v.as_bool()).unwrap_or(false) => {
            let close = if inferred
                .get("close_to_10min")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                "≈ 10 min"
            } else {
                "weicht von 600 s ab"
            };
            println!(
                "Intervall aus {}→{} Counts in {:.0} s → {:.1} s/Sample ({}).",
                inferred.get("count_0").and_then(|v| v.as_i64()).unwrap_or(0),
                inferred.get("count_1").and_then(|v| v.as_i64()).unwrap_or(0),
                inferred.get("dt_sec").and_then(|v| v.as_f64()).unwrap_or(0.0),
                inferred
                    .get("interval_sec")
                    .and_then(|v| v.as_f64())
                    .unwrap_or(0.0),
                close
            );
        }
        Some(inferred) => {
            println!(
                "Intervall: {}",
                inferred
                    .get("reason")
                    .and_then(|v| v.as_str())
                    .unwrap_or("?")
            );
        }
    }
    println!("Nicht senden: 0x18 / 0x04.");
}
