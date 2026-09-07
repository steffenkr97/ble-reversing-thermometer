use thermobeacon::scan::{allowed_from_rooms, parse_scan_args};

#[tokio::main]
async fn main() {
    let args = match parse_scan_args(std::env::args_os()) {
        Ok(a) => a,
        Err(code) => std::process::exit(code),
    };
    let allowed = match allowed_from_rooms(&args.rooms, Some(&args.mac)) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(2);
        }
    };
    let live = match thermobeacon::ble::scan_live(
        args.timeout,
        args.address.as_deref(),
        Some(&allowed),
    )
    .await
    {
        Ok(v) => v,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    match live {
        None => {
            eprintln!(
                "Kein Live-Sample innerhalb von {} s (Allowlist {}).",
                thermobeacon::csvutil::fmt_float(args.timeout),
                allowed.join(", ")
            );
            std::process::exit(1);
        }
        Some(live) => {
            println!("{}", thermobeacon::parse::format_sample(&live));
        }
    }
}
