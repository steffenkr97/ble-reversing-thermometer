use std::io::{Read, Write};
use std::net::TcpStream;
use std::sync::{Arc, Mutex};
use std::thread;
use thermobeacon::dash::DashStore;
use thermobeacon::http::{handle_request, safe_static_path};
use thermobeacon::paths::{default_static_dir, repo_root};

fn testdata() -> std::path::PathBuf {
    repo_root().join("dashboard/testdata")
}

fn http_get(port: u16, path: &str) -> (u16, String) {
    let mut stream = TcpStream::connect(("127.0.0.1", port)).unwrap();
    stream
        .write_all(format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n").as_bytes())
        .unwrap();
    let mut buf = String::new();
    stream.read_to_string(&mut buf).unwrap();
    let (head, body) = buf.split_once("\r\n\r\n").unwrap_or((buf.as_str(), ""));
    let status = head
        .lines()
        .next()
        .unwrap_or("")
        .split_whitespace()
        .nth(1)
        .unwrap_or("0")
        .parse()
        .unwrap_or(0);
    (status, body.to_string())
}

#[test]
fn static_index() {
    let path = safe_static_path("/", &default_static_dir()).unwrap();
    assert!(path.to_string_lossy().ends_with("index.html"));
    assert!(path.is_file());
}

#[test]
fn traversal_rejected() {
    let root = default_static_dir();
    assert!(safe_static_path("/../thermo_dash.py", &root).is_none());
    assert!(safe_static_path("/static/../../AGENTS.md", &root).is_none());
}

fn spawn_server() -> (u16, thread::JoinHandle<()>) {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let server = tiny_http::Server::from_listener(listener, None).unwrap();
    let mut store = DashStore::new(
        testdata(),
        testdata().join("rooms.json"),
        Some(testdata().join("extract")),
        true,
    );
    store.refresh(true);
    let store = Arc::new(Mutex::new(store));
    let static_dir = default_static_dir();
    let handle = thread::spawn(move || {
        for request in server.incoming_requests() {
            handle_request(request, &store, &static_dir);
        }
    });
    (port, handle)
}

#[test]
fn http_api() {
    let (port, _h) = spawn_server();
    let (st, html) = http_get(port, "/");
    assert_eq!(st, 200);
    assert!(html.contains("ThermoBeacon"));
    assert!(html.contains("canvas"));

    let (st, body) = http_get(port, "/api/overview");
    assert_eq!(st, 200);
    let overview: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(overview["rooms"][0]["mac"], "f4:db:00:00:00:d9");
    assert!(overview["sample_count"].as_u64().unwrap() >= 2);
    assert_eq!(overview["encoding"]["history_interval_sec_hypothesis"], 600);
    assert_eq!(overview["history_csv_count"], 1);

    let (st, body) = http_get(port, "/api/samples?mac=f4:db:00:00:00:d9&source=adv");
    assert_eq!(st, 200);
    let live: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(live["count"], 2);
    assert_eq!(live["samples"][0]["temp_c"], 25.125);

    let (st, body) = http_get(port, "/api/samples?mac=f4:db:00:00:00:d9&source=history");
    assert_eq!(st, 200);
    let hist: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(hist["count"], 2);
    assert_eq!(hist["samples"][0]["index"], 0);
    assert_eq!(hist["samples"][0]["temp_c"], 24.0625);
    assert_eq!(hist["samples"][0]["timestamp"], "2025-11-15T12:00:00Z");

    let (st, body) = http_get(port, "/api/samples?source=nope");
    assert_eq!(st, 400);
    let err: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert!(err["error"].as_str().unwrap().contains("unbekannte source"));

    let (st, body) = http_get(port, "/api/nope");
    assert_eq!(st, 404);
    let miss: serde_json::Value = serde_json::from_str(&body).unwrap();
    assert_eq!(miss["error"], "nicht gefunden");
}
