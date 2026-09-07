use clap::Parser;

#[derive(Parser)]
#[command(name = "scan-devices", about = "Kurzer BLE-Scan (Name/Adresse/RSSI)")]
struct Args {
    #[arg(long = "timeout", default_value_t = 10.0)]
    timeout: f64,
}

#[tokio::main]
async fn main() {
    let args = Args::parse();
    if let Err(e) = thermobeacon::ble::scan_devices(args.timeout).await {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
