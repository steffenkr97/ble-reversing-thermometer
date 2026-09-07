use thermobeacon::dump::{dump_from_extract, parse_dump_args};
use thermobeacon::parse::TARGET_MAC;

#[tokio::main]
async fn main() {
    let args = match parse_dump_args(std::env::args_os()) {
        Ok(a) => a,
        Err(code) => std::process::exit(code),
    };
    if args.from_extract.is_some() {
        std::process::exit(dump_from_extract(&args));
    }
    if args.all_rooms {
        let macs = thermobeacon::dump::dump_macs(&args);
        let mut rc = 1;
        let mut wrote = 0;
        for mac in &macs {
            println!("== {mac} ==");
            let mut one_args = args.clone();
            one_args.mac = mac.clone();
            match thermobeacon::ble::dump_via_gatt(&one_args, mac, true).await {
                Ok(0) => {
                    wrote += 1;
                    rc = 0;
                }
                Ok(_) => {}
                Err(e) => eprintln!("{e}"),
            }
        }
        println!("GATT --all-rooms: {wrote}/{} MACs geschrieben.", macs.len());
        std::process::exit(if wrote == 0 { 1 } else { rc });
    }
    let (address, given) = if let Some(a) = args.address.clone() {
        (a, true)
    } else {
        match thermobeacon::ble::find_device_by_system_id().await {
            Ok(Some(a)) => (a, false),
            Ok(None) => {
                println!("Tipp: --address {TARGET_MAC} setzen.");
                std::process::exit(1);
            }
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
    };
    match thermobeacon::ble::dump_via_gatt(&args, &address, given).await {
        Ok(code) => std::process::exit(code),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    }
}
