use clap::Parser;
use chrono::Local;

#[derive(Parser)]
#[command(name = "list-system-ids", about = "Listet ThermoBeacon-Geräte und speichert System ID in CSV")]
struct Args {
    #[arg(short = 'o', long = "output")]
    output: Option<std::path::PathBuf>,
}

#[tokio::main]
async fn main() {
    let args = Args::parse();
    let output = args.output.unwrap_or_else(|| {
        std::path::PathBuf::from(format!(
            "thermobeacon_devices_{}.csv",
            Local::now().format("%Y%m%d_%H%M%S")
        ))
    });
    if let Err(e) = thermobeacon::ble::list_system_ids(&output).await {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
