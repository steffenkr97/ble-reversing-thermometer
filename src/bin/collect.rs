use std::collections::HashMap;
use thermobeacon::collect::{
    parse_collect_args, resolve_macs, run_once_with_found, timeout_msg, write_found, CollectArgs,
};

#[tokio::main]
async fn main() {
    let args = match parse_collect_args(std::env::args_os()) {
        Ok(a) => a,
        Err(code) => std::process::exit(code),
    };
    let macs = match resolve_macs(&args) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(2);
        }
    };
    if args.output.is_some() && macs.len() > 1 {
        eprintln!("--output braucht genau ein Ziel-MAC (--mac …).");
        std::process::exit(2);
    }
    if let Some(interval) = args.interval {
        loop {
            let found = scan(&args, &macs).await;
            if found.is_empty() {
                eprintln!("{}", timeout_msg(args.timeout, &macs));
            } else {
                write_found(&args, &found);
                let missing: Vec<_> = macs.iter().filter(|m| !found.contains_key(*m)).cloned().collect();
                if !missing.is_empty() {
                    eprintln!("kein Sample in diesem Fenster: {}", missing.join(", "));
                }
            }
            tokio::time::sleep(std::time::Duration::from_secs_f64(interval)).await;
        }
    } else {
        let found = scan(&args, &macs).await;
        std::process::exit(run_once_with_found(&args, &macs, found));
    }
}

async fn scan(args: &CollectArgs, macs: &[String]) -> HashMap<String, thermobeacon::AdvLive> {
    if macs.len() == 1 {
        match thermobeacon::ble::scan_live(args.timeout, args.address.as_deref(), Some(macs)).await {
            Ok(Some(live)) => HashMap::from([(live.mac.clone(), live)]),
            Ok(None) => HashMap::new(),
            Err(e) => {
                eprintln!("{e}");
                HashMap::new()
            }
        }
    } else {
        match thermobeacon::ble::scan_live_many(args.timeout, Some(macs), args.address.as_deref(), None)
            .await
        {
            Ok(m) => m,
            Err(e) => {
                eprintln!("{e}");
                HashMap::new()
            }
        }
    }
}
