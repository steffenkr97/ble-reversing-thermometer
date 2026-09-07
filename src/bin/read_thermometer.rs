use clap::Parser;
use thermobeacon::parse::TARGET_MAC;

#[derive(Parser)]
#[command(
    name = "read-thermometer",
    about = "GATT-Probe ThermoBeacon: CCCD, dann 1A → 01, optional eine History-Page 07.",
    after_help = "Beispiele:\n  cargo run --bin read-thermometer -- --address f4:db:00:00:00:d9\n  cargo run --bin read-thermometer -- --use-system-id\n  cargo run --bin read-thermometer -- --address f4:db:00:00:00:d9 --history 0\n  cargo run --bin read-thermometer -- --debug-only --address f4:db:00:00:00:d9"
)]
struct Args {
    /// BLE-Adresse (Linux/Windows: MAC; macOS: CoreBluetooth-UUID)
    #[arg(short = 'a', long = "address")]
    address: Option<String>,
    /// Scan nach ThermoBeacon-Kandidaten, Ziel nur bei 2A23 == TARGET_SYSTEM_ID
    #[arg(long = "use-system-id", default_value_t = false)]
    use_system_id: bool,
    /// Genau eine History-Page: Write 07 <index> 00 00 03
    #[arg(long = "history", value_name = "INDEX")]
    history: Option<i64>,
    /// Nur Services listen, keine FFF5-Writes
    #[arg(long = "debug-only", default_value_t = false)]
    debug_only: bool,
}

#[tokio::main]
async fn main() {
    let mut args = match Args::try_parse() {
        Ok(a) => a,
        Err(e) => {
            let _ = e.print();
            std::process::exit(if e.exit_code() == 0 { 0 } else { 2 });
        }
    };
    if let Some(h) = args.history {
        if h < 0 {
            eprintln!("--history muss >= 0 sein");
            std::process::exit(2);
        }
    }
    if args.debug_only && args.history.is_some() {
        eprintln!("--debug-only und --history schließen sich aus");
        std::process::exit(2);
    }
    if args.address.is_none() && !args.use_system_id {
        args.use_system_id = true;
    }
    let given = args.address.is_some();
    let address = if let Some(a) = args.address.clone() {
        a
    } else {
        match thermobeacon::ble::find_device_by_system_id().await {
            Ok(Some(a)) => a,
            Ok(None) => {
                println!("Tipp: --address {TARGET_MAC} setzen.");
                return;
            }
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
    };
    if let Err(e) = thermobeacon::ble::run_probe(
        &address,
        args.history.map(|h| h as u16),
        args.debug_only,
        given,
    )
    .await
    {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
