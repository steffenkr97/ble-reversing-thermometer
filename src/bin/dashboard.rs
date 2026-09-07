use clap::Parser;
use std::sync::{Arc, Mutex};
use thermobeacon::dash::DashStore;
use thermobeacon::http::{handle_request, bind_server};
use thermobeacon::paths::{default_data_dir, default_extract_dir, default_rooms_path, default_static_dir, resolve_path};

#[derive(Parser)]
#[command(
    name = "dashboard",
    about = "Lokales Dashboard für ThermoBeacon-CSV und HCI-Belegdaten. Kein Connect, kein GATT, keine Cloud."
)]
struct Args {
    /// Bind-Adresse (Standard: 127.0.0.1)
    #[arg(long = "host", default_value = "127.0.0.1")]
    host: String,
    /// Port (Standard: 8765)
    #[arg(long = "port", default_value_t = 8765)]
    port: u16,
    /// Live/History-CSV (Standard: data/)
    #[arg(long = "data-dir", default_value_os_t = default_data_dir())]
    data_dir: std::path::PathBuf,
    /// Allowlist rooms.json
    #[arg(long = "rooms", default_value_os_t = default_rooms_path())]
    rooms: std::path::PathBuf,
    /// HCI-Extracts (adv.csv, att_fff5_fff3.csv)
    #[arg(long = "extract-dir", default_value_os_t = default_extract_dir())]
    extract_dir: std::path::PathBuf,
    /// HCI-Belegdaten nicht einlesen (nur data/)
    #[arg(long = "no-extract", default_value_t = false)]
    no_extract: bool,
}

fn main() {
    let args = match Args::try_parse() {
        Ok(a) => {
            if a.port == 0 {
                eprintln!("--port muss 1–65535 sein");
                std::process::exit(2);
            }
            a
        }
        Err(e) => {
            let _ = e.print();
            std::process::exit(if e.exit_code() == 0 { 0 } else { 2 });
        }
    };
    let mut store = DashStore::new(
        resolve_path(&args.data_dir),
        resolve_path(&args.rooms),
        if args.no_extract {
            None
        } else {
            Some(resolve_path(&args.extract_dir))
        },
        !args.no_extract,
    );
    store.refresh(true);
    let n = store.samples.len();
    let static_dir = default_static_dir();
    let store = Arc::new(Mutex::new(store));
    println!("Dashboard: http://{}:{}/", args.host, args.port);
    println!("data-dir: {}", resolve_path(&args.data_dir).display());
    println!(
        "extract: {}",
        if args.no_extract {
            "aus (--no-extract)".into()
        } else {
            resolve_path(&args.extract_dir).display().to_string()
        }
    );
    println!("Samples geladen: {n}");
    println!("Nur lokal, kein BLE. Strg+C beendet.");
    let server = match bind_server(&args.host, args.port) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    for request in server.incoming_requests() {
        handle_request(request, &store, &static_dir);
    }
}
