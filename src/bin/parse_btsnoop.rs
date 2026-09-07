use clap::Parser;
use std::path::PathBuf;
use thermobeacon::btsnoop::{find_cfa, parse_file, print_summary, write_csvs, Capture};
use thermobeacon::paths::{repo_root, resolve_path};

#[derive(Parser)]
#[command(name = "parse-btsnoop", about = "btsnoop/H4 Parser für ThermoBeacon .cfa")]
struct Args {
    /// Dateien oder Ordner (Default: hci-logs)
    paths: Vec<PathBuf>,
    /// Text-Summary auf stdout
    #[arg(long = "summary", default_value_t = false)]
    summary: bool,
    /// CSV nach DIR schreiben
    #[arg(long = "export", value_name = "DIR")]
    export: Option<PathBuf>,
    /// FFF5/FFF3-Zeilen auf stdout
    #[arg(long = "att", default_value_t = false)]
    att: bool,
    /// Advertising des Zielgeräts auf stdout
    #[arg(long = "adv", default_value_t = false)]
    adv: bool,
}

fn main() {
    let args = match Args::try_parse() {
        Ok(a) => a,
        Err(e) => {
            let _ = e.print();
            std::process::exit(if e.exit_code() == 0 { 0 } else { 2 });
        }
    };
    let root = repo_root();
    let files = if args.paths.is_empty() {
        find_cfa(&root.join("hci-logs"))
    } else {
        let mut files = Vec::new();
        for p in &args.paths {
            let path = resolve_path(p);
            if path.is_dir() {
                files.extend(find_cfa(&path));
            } else {
                files.push(path);
            }
        }
        files
    };
    let caps: Vec<Capture> = files.iter().map(|p| parse_file(p)).collect();
    if let Some(dir) = &args.export {
        let out = resolve_path(dir);
        if let Err(e) = write_csvs(&caps, &out) {
            eprintln!("{e}");
            std::process::exit(1);
        }
        println!("export -> {}", out.display());
    }
    if args.summary || !(args.export.is_some() || args.att || args.adv) {
        print_summary(&caps);
    }
    if args.att {
        for cap in &caps {
            let (writes, notifs, cccds) = thermobeacon::btsnoop::att_control_notify(cap);
            let rel = cap.path.file_name().unwrap().to_string_lossy();
            for (kind, lst) in [("CCCD", &cccds), ("W", &writes), ("N", &notifs)] {
                for p in lst {
                    println!(
                        "{rel}\t{}\t{kind}\t{}",
                        p.timestamp,
                        thermobeacon::btsnoop::hex_of(&p.value)
                    );
                }
            }
        }
    }
    if args.adv {
        for cap in &caps {
            for a in &cap.adv {
                if !thermobeacon::btsnoop::is_target(&a.mac) {
                    continue;
                }
                println!(
                    "{}\t{}\t{}\t{}\t{}\t{}",
                    cap.path.file_name().unwrap().to_string_lossy(),
                    a.timestamp,
                    a.mac,
                    a.event_name,
                    a.rssi,
                    thermobeacon::btsnoop::hex_of(&a.data)
                );
            }
        }
    }
}
