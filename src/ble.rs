//! BLE über btleplug: ADV-Scan und GATT 1A/01/07. Keine Blacklist-Opcodes.

use std::collections::HashMap;
use std::time::{Duration, Instant};

use btleplug::api::{
    Central, Characteristic, Descriptor, Manager as _, Peripheral as _, ScanFilter, ValueNotification,
    WriteType,
};
use btleplug::platform::{Adapter, Manager, Peripheral};
use futures::StreamExt;
use tokio::sync::mpsc;
use uuid::Uuid;

use crate::dump::{expected_system_id, finish_dump_rows, progress, rooms_or_empty, DumpArgs};
use crate::history::{assert_allowed_fff5_write, page_plan};
use crate::mac::{macs_equal, normalize_mac};
use crate::parse::{
    assemble_mfg_frame, parse_adv_manufacturer, parse_fff3, AdvLive, Count01, Fff3, History07,
    CCCD_UUID, COMPANY_ID, CONTROL_CHAR_UUID, DATA_CHAR_UUID, SERVICE_UUID, SYSTEM_ID_UUID,
    TARGET_MAC, TARGET_SYSTEM_ID,
};

fn uuid_eq(a: &Uuid, b: &str) -> bool {
    a.to_string().eq_ignore_ascii_case(b)
}

fn hex_spaced(data: &[u8]) -> String {
    data.iter()
        .map(|b| format!("{b:02X}"))
        .collect::<Vec<_>>()
        .join(" ")
}

async fn adapter() -> anyhow::Result<Adapter> {
    let manager = Manager::new().await?;
    let adapters = manager.adapters().await?;
    adapters
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("kein Bluetooth-Adapter"))
}

fn mfg_from_props(props: &btleplug::api::PeripheralProperties) -> Vec<(u16, Vec<u8>)> {
    props
        .manufacturer_data
        .iter()
        .map(|(k, v)| (*k, v.clone()))
        .collect()
}

fn live_from_props(
    props: &btleplug::api::PeripheralProperties,
    allowed: &[String],
    want_addr: Option<&str>,
) -> Option<AdvLive> {
    if let Some(want) = want_addr {
        if props.address.to_string().to_lowercase() != want.to_lowercase() {
            return None;
        }
    }
    for (cid, payload) in mfg_from_props(props) {
        let frame = assemble_mfg_frame(cid, &payload)?;
        if let Some(live) = parse_adv_manufacturer(&frame, Some(allowed)) {
            return Some(live);
        }
    }
    None
}

/// Erstes gültiges AdvLive oder None nach Timeout.
pub async fn scan_live(
    timeout: f64,
    address: Option<&str>,
    allowed_macs: Option<&[String]>,
) -> anyhow::Result<Option<AdvLive>> {
    let found = scan_live_many(timeout, allowed_macs, address, Some(1)).await?;
    Ok(found.into_values().next())
}

/// Ein Sample je Allowlist-MAC, bis Timeout oder stop_after Treffer.
pub async fn scan_live_many(
    timeout: f64,
    allowed_macs: Option<&[String]>,
    address: Option<&str>,
    stop_after: Option<usize>,
) -> anyhow::Result<HashMap<String, AdvLive>> {
    let wanted: Vec<String> = match allowed_macs {
        Some(m) => m.iter().map(|s| normalize_mac(s)).collect(),
        None => vec![TARGET_MAC.to_string()],
    };
    if wanted.is_empty() {
        return Ok(HashMap::new());
    }
    let target_n = stop_after.unwrap_or(wanted.len()).min(wanted.len());
    let adapter = adapter().await?;
    adapter.start_scan(ScanFilter::default()).await?;
    let deadline = Instant::now() + Duration::from_secs_f64(timeout);
    let mut found: HashMap<String, AdvLive> = HashMap::new();
    while Instant::now() < deadline && found.len() < target_n {
        let remaining = deadline.saturating_duration_since(Instant::now());
        tokio::time::sleep(remaining.min(Duration::from_millis(200))).await;
        for p in adapter.peripherals().await? {
            let Some(props) = p.properties().await? else {
                continue;
            };
            if let Some(live) = live_from_props(&props, &wanted, address) {
                if !found.contains_key(&live.mac) {
                    found.insert(live.mac.clone(), live);
                    if found.len() >= target_n {
                        break;
                    }
                }
            }
        }
    }
    let _ = adapter.stop_scan().await;
    Ok(found)
}

fn find_char<'a>(chars: &'a [Characteristic], uuid_s: &str) -> Option<&'a Characteristic> {
    chars.iter().find(|c| uuid_eq(&c.uuid, uuid_s))
}

fn find_cccd(char: &Characteristic) -> Option<Descriptor> {
    char.descriptors.iter().find(|d| {
        let s = d.uuid.to_string();
        s.eq_ignore_ascii_case(CCCD_UUID) || s.to_lowercase().contains("2902")
    }).cloned()
}

async fn read_system_id(p: &Peripheral) -> Option<Vec<u8>> {
    let chars: Vec<_> = p.characteristics().into_iter().collect();
    let ch = find_char(&chars, SYSTEM_ID_UUID)?;
    p.read(ch).await.ok()
}

fn is_thermobeacon_candidate(props: &btleplug::api::PeripheralProperties) -> bool {
    let names: Vec<String> = props
        .local_name
        .iter()
        .cloned()
        .chain(std::iter::once(props.address.to_string()))
        .collect();
    if names.iter().any(|n| n.contains("ThermoBeacon")) {
        return true;
    }
    if macs_equal(&props.address.to_string(), TARGET_MAC) {
        return true;
    }
    if props.manufacturer_data.contains_key(&COMPANY_ID) {
        return true;
    }
    if let Some(payload) = props.manufacturer_data.get(&COMPANY_ID) {
        if payload.len() >= 8 {
            let mac = crate::mac::mac_le_to_str(&payload[2..8]);
            if macs_equal(&mac, TARGET_MAC) {
                return true;
            }
        }
    }
    props
        .services
        .iter()
        .any(|u| u.to_string().to_lowercase().contains("fff0"))
}

fn candidate_score(props: &btleplug::api::PeripheralProperties) -> i32 {
    let mut score = 0;
    if macs_equal(&props.address.to_string(), TARGET_MAC) {
        score += 4;
    }
    if let Some(payload) = props.manufacturer_data.get(&COMPANY_ID) {
        if payload.len() >= 8 {
            let mac = crate::mac::mac_le_to_str(&payload[2..8]);
            if macs_equal(&mac, TARGET_MAC) {
                score += 4;
            }
        }
    }
    if props
        .local_name
        .as_deref()
        .map(|n| n.contains("ThermoBeacon"))
        .unwrap_or(false)
    {
        score += 1;
    }
    score
}

pub async fn find_device_by_system_id() -> anyhow::Result<Option<String>> {
    println!("Scanne nach ThermoBeacon-Kandidaten (Name / Manufacturer 0x001B / MAC)...");
    let adapter = adapter().await?;
    adapter.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs(10)).await;
    let _ = adapter.stop_scan().await;
    let mut candidates = Vec::new();
    for p in adapter.peripherals().await? {
        let Some(props) = p.properties().await? else {
            continue;
        };
        if is_thermobeacon_candidate(&props) {
            candidates.push((candidate_score(&props), p, props));
        }
    }
    candidates.sort_by_key(|(s, _, _)| -s);
    if candidates.is_empty() {
        println!("Keine ThermoBeacon-Kandidaten gefunden.");
        return Ok(None);
    }
    println!("Kandidaten: {}", candidates.len());
    let target_sid = TARGET_SYSTEM_ID.to_vec();
    for (_score, p, props) in candidates {
        let adv_mac = props
            .manufacturer_data
            .get(&COMPANY_ID)
            .and_then(|payload| {
                if payload.len() >= 8 {
                    Some(crate::mac::mac_le_to_str(&payload[2..8]))
                } else {
                    None
                }
            });
        println!(
            "  {}  name={:?}  adv_mac={}",
            props.address,
            props.local_name.unwrap_or_default(),
            adv_mac.as_deref().unwrap_or("-")
        );
        match p.connect().await {
            Ok(()) => {
                let _ = p.discover_services().await;
                match read_system_id(&p).await {
                    None => println!("    System ID nicht lesbar"),
                    Some(sid) if sid == target_sid => {
                        println!("    System ID stimmt — Zielgerät.");
                        let _ = p.disconnect().await;
                        return Ok(Some(props.address.to_string()));
                    }
                    Some(sid) => println!("    System ID abweichend: {}", hex_spaced(&sid)),
                }
                let _ = p.disconnect().await;
            }
            Err(e) => println!("    Connect fehlgeschlagen: {e}"),
        }
    }
    println!("Kein Gerät mit TARGET_SYSTEM_ID gefunden (kein Erstes-Gerät-Fallback).");
    Ok(None)
}

async fn enable_notify(
    p: &Peripheral,
    data_char: &Characteristic,
    tx: mpsc::UnboundedSender<Vec<u8>>,
) -> anyhow::Result<()> {
    p.subscribe(data_char).await?;
    println!("start_notify(FFF3) ok");
    if let Some(desc) = find_cccd(data_char) {
        let _ = p.write_descriptor(&desc, &[0x01, 0x00]).await;
        println!("CCCD 2902 = 01 00");
    } else {
        println!("Warnung: CCCD 2902 nicht gefunden — nur start_notify.");
    }
    tokio::time::sleep(Duration::from_millis(100)).await;
    let mut notifs = p.notifications().await?;
    tokio::spawn(async move {
        while let Some(ValueNotification { value, .. }) = notifs.next().await {
            let _ = tx.send(value);
        }
    });
    Ok(())
}

async fn wait_notify(
    rx: &mut mpsc::UnboundedReceiver<Vec<u8>>,
    opcode: u8,
    timeout: f64,
) -> Option<Vec<u8>> {
    let deadline = Instant::now() + Duration::from_secs_f64(timeout);
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return None;
        }
        match tokio::time::timeout(remaining, rx.recv()).await {
            Ok(Some(data)) if data.len() == 20 && data[0] == opcode => return Some(data),
            Ok(Some(_)) => continue,
            Ok(None) => return None,
            Err(_) => return None,
        }
    }
}

fn drain(rx: &mut mpsc::UnboundedReceiver<Vec<u8>>) {
    while rx.try_recv().is_ok() {}
}

fn print_parsed(parsed: Option<&Fff3>, raw: &[u8]) {
    match parsed {
        None => println!(
            "  unbekanntes Notify ({} Byte): {}",
            raw.len(),
            hex_spaced(raw)
        ),
        Some(Fff3::Status(s)) => println!("  Status 1A  raw={}", s.raw_hex),
        Some(Fff3::Count(c)) => println!(
            "  Count 01   samples={}  raw={}",
            c.sample_count, c.raw_hex
        ),
        Some(Fff3::History(h)) => {
            println!(
                "  History 07  index={}  count={}  raw={}",
                h.index, h.count, h.raw_hex
            );
            for (i, (temp, hum)) in h.records.iter().enumerate() {
                println!("    [{i}] {temp:.4} °C  {hum:.4} %rF");
            }
        }
    }
}

async fn dump_services(p: &Peripheral) {
    println!("\nServices und Characteristics:");
    for s in p.services() {
        println!("\nService {}", s.uuid);
        for c in &s.characteristics {
            let props: Vec<_> = format!("{:?}", c.properties)
                .trim_matches(|ch: char| ch == '{' || ch == '}')
                .split('|')
                .map(|x| x.trim().to_lowercase())
                .filter(|x| !x.is_empty())
                .collect();
            println!("  {}  [{:?}]", c.uuid, c.properties);
            if props.iter().any(|p| p.contains("read"))
                || format!("{:?}", c.properties).to_lowercase().contains("read")
            {
                match p.read(c).await {
                    Ok(value) => {
                        let decoded = String::from_utf8_lossy(&value)
                            .trim_matches('\0')
                            .trim()
                            .to_string();
                        if !decoded.is_empty()
                            && decoded
                                .chars()
                                .all(|c| c.is_ascii_graphic() || c.is_whitespace())
                        {
                            println!("    Wert: \"{decoded}\"");
                        } else {
                            println!("    Wert: {}", hex_spaced(&value));
                        }
                    }
                    Err(e) => println!("    Wert: <nicht lesbar: {e}>"),
                }
            }
        }
    }
}

pub async fn run_probe(
    device_address: &str,
    history_index: Option<u16>,
    debug_only: bool,
    address_was_given: bool,
) -> anyhow::Result<()> {
    println!("Verbinde mit {device_address} ...");
    let adapter = adapter().await?;
    let p = find_peripheral(&adapter, device_address).await?;
    p.connect().await?;
    println!("Verbunden.");
    p.discover_services().await?;
    let sid = read_system_id(&p).await;
    let target_sid = TARGET_SYSTEM_ID.to_vec();
    match sid {
        None => {
            if address_was_given || macs_equal(device_address, TARGET_MAC) {
                println!("System ID nicht lesbar; fahre mit gegebener Adresse fort.");
            } else {
                println!("System ID nicht lesbar und Adresse ist nicht TARGET_MAC — Abbruch.");
                let _ = p.disconnect().await;
                return Ok(());
            }
        }
        Some(ref s) if *s != target_sid => {
            println!(
                "System ID {} != Ziel {} — falsches Gerät, Abbruch.",
                hex_spaced(s),
                hex_spaced(&target_sid)
            );
            let _ = p.disconnect().await;
            return Ok(());
        }
        Some(ref s) => println!("System ID ok: {}", hex_spaced(s)),
    }
    let chars: Vec<_> = p.characteristics().into_iter().collect();
    if find_char(&chars, CONTROL_CHAR_UUID).is_none() {
        println!("FFF5 (Control) nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(());
    }
    if find_char(&chars, DATA_CHAR_UUID).is_none() {
        println!("FFF3 (Data) nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(());
    }
    if !p.services().iter().any(|s| uuid_eq(&s.uuid, SERVICE_UUID)) {
        println!("Service FFE0 nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(());
    }
    if debug_only {
        dump_services(&p).await;
        println!("\n[--debug-only] keine Writes.");
        let _ = p.disconnect().await;
        return Ok(());
    }
    let data_char = find_char(&chars, DATA_CHAR_UUID).cloned().unwrap();
    let control = find_char(&chars, CONTROL_CHAR_UUID).cloned().unwrap();
    let (tx, mut rx) = mpsc::unbounded_channel();
    enable_notify(&p, &data_char, tx).await?;

    async fn probe_write(
        p: &Peripheral,
        control: &Characteristic,
        rx: &mut mpsc::UnboundedReceiver<Vec<u8>>,
        payload: &[u8],
    ) -> Option<Fff3> {
        let opcode = payload[0];
        drain(rx);
        if let Err(e) = p.write(control, payload, WriteType::WithResponse).await {
            println!("Write FFF5 fehlgeschlagen: {e}");
            return None;
        }
        println!("Write FFF5: {}", hex_spaced(payload));
        let raw = wait_notify(rx, opcode, 1.0).await;
        let Some(raw) = raw else {
            println!("  Timeout (~1s), keine 20-Byte-Antwort auf {opcode:02X}");
            return None;
        };
        let parsed = parse_fff3(&raw);
        print_parsed(parsed.as_ref(), &raw);
        parsed
    }

    print!("\nSequenz 1A → 01");
    if let Some(idx) = history_index {
        println!(" → 07 index={idx}");
    } else {
        println!();
    }
    probe_write(&p, &control, &mut rx, &[0x1A]).await;
    probe_write(&p, &control, &mut rx, &[0x01]).await;
    if let Some(idx) = history_index {
        let payload = crate::parse::build_history_07_write(idx, 3);
        if payload.len() != 6 {
            println!("build_history_07_write lieferte {} Byte, erwartet 6.", payload.len());
            let _ = p.disconnect().await;
            return Ok(());
        }
        probe_write(&p, &control, &mut rx, &payload).await;
    }
    let _ = p.unsubscribe(&data_char).await;
    let _ = p.disconnect().await;
    Ok(())
}

async fn find_peripheral(adapter: &Adapter, address: &str) -> anyhow::Result<Peripheral> {
    let want = address.to_lowercase();
    // Direct connect via address: scan briefly then match.
    let _ = adapter.start_scan(ScanFilter::default()).await;
    tokio::time::sleep(Duration::from_millis(800)).await;
    for p in adapter.peripherals().await? {
        if p.address().to_string().to_lowercase() == want {
            let _ = adapter.stop_scan().await;
            return Ok(p);
        }
        if let Some(props) = p.properties().await? {
            if props.address.to_string().to_lowercase() == want {
                let _ = adapter.stop_scan().await;
                return Ok(p);
            }
        }
    }
    let _ = adapter.stop_scan().await;
    anyhow::bail!("Gerät {address} nicht gefunden")
}

pub async fn dump_via_gatt(
    args: &DumpArgs,
    device_address: &str,
    address_was_given: bool,
) -> anyhow::Result<i32> {
    println!("Verbinde mit {device_address} ...");
    let adapter = adapter().await?;
    let p = find_peripheral(&adapter, device_address).await?;
    p.connect().await?;
    println!("Verbunden.");
    p.discover_services().await?;
    let sid = read_system_id(&p).await;
    let rooms = rooms_or_empty(&args.rooms);
    let expected_sid = expected_system_id(&args.mac, &rooms);
    match sid {
        None => {
            let mut allow_missing = address_was_given || expected_sid.is_none();
            if expected_sid.is_some() && macs_equal(device_address, &args.mac) {
                allow_missing = true;
            }
            if allow_missing {
                println!("System ID nicht lesbar; fahre mit gegebener Adresse fort.");
            } else {
                println!("System ID nicht lesbar und nicht auf der Allowlist — Abbruch.");
                let _ = p.disconnect().await;
                return Ok(1);
            }
        }
        Some(ref s) if expected_sid.is_none() => {
            println!("System ID {} (kein Sollwert in rooms.json).", hex_spaced(s));
        }
        Some(ref s) if expected_sid.as_ref() != Some(s) => {
            println!(
                "System ID {} != Ziel {} — falsches Gerät, Abbruch.",
                hex_spaced(s),
                hex_spaced(expected_sid.as_ref().unwrap())
            );
            let _ = p.disconnect().await;
            return Ok(1);
        }
        Some(ref s) => println!("System ID ok: {}", hex_spaced(s)),
    }
    let chars: Vec<_> = p.characteristics().into_iter().collect();
    if find_char(&chars, CONTROL_CHAR_UUID).is_none() {
        println!("FFF5 (Control) nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(1);
    }
    if find_char(&chars, DATA_CHAR_UUID).is_none() {
        println!("FFF3 (Data) nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(1);
    }
    if !p.services().iter().any(|s| uuid_eq(&s.uuid, SERVICE_UUID)) {
        println!("Service FFE0 nicht gefunden.");
        let _ = p.disconnect().await;
        return Ok(1);
    }
    let data_char = find_char(&chars, DATA_CHAR_UUID).cloned().unwrap();
    let control = find_char(&chars, CONTROL_CHAR_UUID).cloned().unwrap();
    let (tx, mut rx) = mpsc::unbounded_channel();
    enable_notify(&p, &data_char, tx).await?;

    let notify_timeout = args.notify_timeout;
    println!("Sequenz 1A → 01 → 07-Pages");
    assert_allowed_fff5_write(&[0x1A])?;
    drain(&mut rx);
    p.write(&control, &[0x1A], WriteType::WithResponse).await?;
    let raw_1a = wait_notify(&mut rx, 0x1A, notify_timeout).await;
    let Some(raw_1a) = raw_1a else {
        eprintln!("Timeout auf 1A.");
        let _ = p.disconnect().await;
        return Ok(1);
    };
    println!("  Status 1A  raw={}", hex::encode(&raw_1a));

    assert_allowed_fff5_write(&[0x01])?;
    drain(&mut rx);
    p.write(&control, &[0x01], WriteType::WithResponse).await?;
    let raw_01 = wait_notify(&mut rx, 0x01, notify_timeout).await;
    let Some(raw_01) = raw_01 else {
        eprintln!("Timeout auf 01.");
        let _ = p.disconnect().await;
        return Ok(1);
    };
    let parsed_01 = parse_fff3(&raw_01);
    let Some(Fff3::Count(Count01 { sample_count, .. })) = parsed_01 else {
        eprintln!("Antwort auf 01 ist kein Count01: {}", hex::encode(&raw_01));
        let _ = p.disconnect().await;
        return Ok(1);
    };
    let sample_count = i64::from(sample_count);
    let mut plan = page_plan(sample_count)?;
    if let Some(n) = args.max_pages {
        plan.truncate(n as usize);
    }
    println!(
        "  Count 01   samples={}  pages={}  (~{:.0} s bei 0,2 s/Page)",
        sample_count,
        plan.len(),
        plan.len() as f64 * 0.2
    );

    let t0 = Instant::now();
    let retries = args.retries.max(0) as u32;

    let mut pages: Vec<History07> = Vec::new();
    let total = plan.len();
    for (step, (index, count)) in plan.into_iter().enumerate() {
        let step = step + 1;
        let payload = crate::parse::build_history_07_write(index, count);
        assert_allowed_fff5_write(&payload)?;
        let mut parsed: Option<History07> = None;
        for _ in 0..=retries {
            drain(&mut rx);
            if p.write(&control, &payload, WriteType::WithResponse)
                .await
                .is_err()
            {
                continue;
            }
            if let Some(raw) = wait_notify(&mut rx, 0x07, notify_timeout).await {
                if let Some(Fff3::History(h)) = parse_fff3(&raw) {
                    parsed = Some(h);
                    break;
                }
            }
        }
        let Some(parsed) = parsed else {
            let _ = p.unsubscribe(&data_char).await;
            let _ = p.disconnect().await;
            anyhow::bail!("History-Page index={index} count={count} ohne gültiges Notify");
        };
        progress(step, total, &parsed);
        pages.push(parsed);
    }
    let _ = p.unsubscribe(&data_char).await;
    let elapsed = t0.elapsed().as_secs_f64();
    let rc = finish_dump_rows(args, &args.mac, &pages, sample_count, elapsed);
    let _ = p.disconnect().await;
    Ok(rc)
}

pub async fn list_system_ids(output: &std::path::Path) -> anyhow::Result<()> {
    println!("Scanne nach ThermoBeacon-Geräten...");
    let adapter = adapter().await?;
    adapter.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs(10)).await;
    let _ = adapter.stop_scan().await;
    let mut results = Vec::new();
    for p in adapter.peripherals().await? {
        let Some(props) = p.properties().await? else {
            continue;
        };
        let name = props.local_name.clone().unwrap_or_else(|| "Unbekannt".into());
        if !name.contains("ThermoBeacon") {
            continue;
        }
        println!("\n{}  Adresse: {}", name, props.address);
        let mut row = HashMap::from([
            ("Name".to_string(), name),
            ("Adresse".to_string(), props.address.to_string()),
            (
                "RSSI (dBm)".to_string(),
                props.rssi.map(|r| r.to_string()).unwrap_or_default(),
            ),
        ]);
        match p.connect().await {
            Ok(()) => {
                let _ = p.discover_services().await;
                if let Some(sid) = read_system_id(&p).await {
                    row.insert("System ID (2A23)".into(), hex_spaced(&sid));
                    println!("  System ID: {}", hex_spaced(&sid));
                }
                let _ = p.disconnect().await;
            }
            Err(e) => {
                row.insert("Fehler".into(), e.to_string());
                println!("  Fehler: {e}");
            }
        }
        results.push(row);
    }
    if results.is_empty() {
        println!("Keine ThermoBeacon-Geräte gefunden!");
        return Ok(());
    }
    let mut w = csv::Writer::from_path(output)?;
    w.write_record([
        "Name",
        "Adresse",
        "RSSI (dBm)",
        "System ID (2A23)",
        "Fehler",
    ])?;
    for r in &results {
        w.write_record([
            r.get("Name").map(|s| s.as_str()).unwrap_or(""),
            r.get("Adresse").map(|s| s.as_str()).unwrap_or(""),
            r.get("RSSI (dBm)").map(|s| s.as_str()).unwrap_or(""),
            r.get("System ID (2A23)").map(|s| s.as_str()).unwrap_or(""),
            r.get("Fehler").map(|s| s.as_str()).unwrap_or(""),
        ])?;
    }
    w.flush()?;
    println!("\n✓ Ergebnisse gespeichert in: {}", output.display());
    Ok(())
}

pub async fn scan_devices(timeout: f64) -> anyhow::Result<()> {
    println!("Scanne {timeout:.0} Sekunden...");
    let adapter = adapter().await?;
    adapter.start_scan(ScanFilter::default()).await?;
    tokio::time::sleep(Duration::from_secs_f64(timeout)).await;
    for p in adapter.peripherals().await? {
        let Some(props) = p.properties().await? else {
            continue;
        };
        println!(
            "{} - {} (RSSI: {:?} dBm)",
            props.address,
            props.local_name.unwrap_or_else(|| "Unbekannt".into()),
            props.rssi
        );
    }
    let _ = adapter.stop_scan().await;
    Ok(())
}
