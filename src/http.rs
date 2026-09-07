//! Lokales HTTP-Dashboard. Nur Lesen, kein BLE, kein Cloud.

use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use tiny_http::{Header, Method, Request, Response, Server, StatusCode};
use url::Url;

use crate::dash::{DashStore, KNOWN_SOURCES};

pub fn json_bytes(payload: &impl serde::Serialize) -> (u16, &'static str, Vec<u8>) {
    let body = serde_json::to_vec(payload).unwrap_or_else(|_| b"{}".to_vec());
    (200, "application/json; charset=utf-8", body)
}

pub fn json_error(status: u16, payload: serde_json::Value) -> (u16, &'static str, Vec<u8>) {
    let body = serde_json::to_vec(&payload).unwrap_or_else(|_| b"{}".to_vec());
    (status, "application/json; charset=utf-8", body)
}

pub fn safe_static_path(url_path: &str, static_dir: &Path) -> Option<PathBuf> {
    let decoded = urlencoding_decode(url_path);
    let mut rel = decoded.trim_start_matches('/').to_string();
    if rel.is_empty() || rel == "/" {
        rel = "index.html".into();
    }
    if rel.replace('\\', "/").split('/').any(|p| p == "..") {
        return None;
    }
    let static_root = fs::canonicalize(static_dir).unwrap_or_else(|_| static_dir.to_path_buf());
    let full = static_root.join(&rel);
    let full = fs::canonicalize(&full).unwrap_or(full);
    if full != static_root && !full.starts_with(&static_root) {
        return None;
    }
    let full = if full.is_dir() {
        full.join("index.html")
    } else {
        full
    };
    if full.is_file() {
        Some(full)
    } else {
        None
    }
}

fn urlencoding_decode(s: &str) -> String {
    percent_decode(s)
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(v) = u8::from_str_radix(std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or(""), 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

pub fn content_type(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase()
        .as_str()
    {
        "html" => "text/html; charset=utf-8",
        "js" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "ico" => "image/x-icon",
        _ => "application/octet-stream",
    }
}

fn header(name: &str, value: &str) -> Header {
    Header::from_bytes(name.as_bytes(), value.as_bytes()).expect("header")
}

fn send(request: Request, status: u16, ctype: &str, body: Vec<u8>) {
    let len = body.len();
    let response = Response::from_data(body)
        .with_status_code(StatusCode::from(status))
        .with_header(header("Content-Type", ctype))
        .with_header(header("Content-Length", &len.to_string()))
        .with_header(header("Cache-Control", "no-store"))
        .with_header(header("X-Content-Type-Options", "nosniff"));
    let _ = request.respond(response);
}

fn parse_query(raw_url: &str) -> (String, Vec<(String, String)>) {
    let dummy = format!("http://127.0.0.1{raw_url}");
    if let Ok(u) = Url::parse(&dummy) {
        let path = u.path().to_string();
        let q: Vec<_> = u
            .query_pairs()
            .map(|(k, v)| (k.into_owned(), v.into_owned()))
            .collect();
        return (path, q);
    }
    let path = raw_url.split('?').next().unwrap_or("/").to_string();
    (path, Vec::new())
}

fn qget<'a>(query: &'a [(String, String)], key: &str) -> Option<&'a str> {
    query
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, v)| v.as_str())
}

pub fn handle_request(request: Request, store: &Mutex<DashStore>, static_dir: &Path) {
    if *request.method() != Method::Get {
        send(
            request,
            405,
            "text/plain; charset=utf-8",
            b"nur GET\n".to_vec(),
        );
        return;
    }
    let url = request.url().to_string();
    let (path, query) = parse_query(&url);
    if path.starts_with("/api/") {
        handle_api(request, &path, &query, store);
        return;
    }
    match safe_static_path(&path, static_dir) {
        None => {
            if path.starts_with("/api") {
                let (st, ct, body) =
                    json_error(404, serde_json::json!({"error": "nicht gefunden"}));
                send(request, st, ct, body);
            } else {
                send(
                    request,
                    404,
                    "text/plain; charset=utf-8",
                    b"nicht gefunden\n".to_vec(),
                );
            }
        }
        Some(p) => match fs::read(&p) {
            Ok(body) => send(request, 200, content_type(&p), body),
            Err(_) => send(
                request,
                404,
                "text/plain; charset=utf-8",
                b"nicht gefunden\n".to_vec(),
            ),
        },
    }
}

fn handle_api(request: Request, path: &str, query: &[(String, String)], store: &Mutex<DashStore>) {
    let mut store = match store.lock() {
        Ok(s) => s,
        Err(_) => {
            let (st, ct, body) = json_error(
                500,
                serde_json::json!({"error": "intern", "detail": "lock"}),
            );
            send(request, st, ct, body);
            return;
        }
    };
    if path == "/api/overview" {
        let payload = store.overview();
        let (_, ct, body) = json_bytes(&payload);
        send(request, 200, ct, body);
        return;
    }
    if path == "/api/samples" {
        let mac = qget(query, "mac");
        let source = qget(query, "source");
        if let Some(src) = source {
            if !KNOWN_SOURCES.contains(&src) {
                let (st, ct, body) = json_error(
                    400,
                    serde_json::json!({
                        "error": "unbekannte source",
                        "allowed": KNOWN_SOURCES
                    }),
                );
                send(request, st, ct, body);
                return;
            }
        }
        let limit_raw = qget(query, "limit").unwrap_or("0");
        let limit: i64 = match limit_raw.parse() {
            Ok(n) => n,
            Err(_) => {
                let (st, ct, body) =
                    json_error(400, serde_json::json!({"error": "limit muss eine Zahl sein"}));
                send(request, st, ct, body);
                return;
            }
        };
        if limit < 0 {
            let (st, ct, body) =
                json_error(400, serde_json::json!({"error": "limit darf nicht negativ sein"}));
            send(request, st, ct, body);
            return;
        }
        let payload = store.query(mac, source, limit);
        let (_, ct, body) = json_bytes(&payload);
        send(request, 200, ct, body);
        return;
    }
    let (st, ct, body) = json_error(404, serde_json::json!({"error": "nicht gefunden"}));
    send(request, st, ct, body);
}

pub fn serve(store: Arc<Mutex<DashStore>>, static_dir: PathBuf, host: &str, port: u16) -> anyhow::Result<()> {
    let addr = format!("{host}:{port}");
    let server = Server::http(&addr).map_err(|e| anyhow::anyhow!("{e}"))?;
    for request in server.incoming_requests() {
        handle_request(request, &store, &static_dir);
    }
    Ok(())
}

pub fn bind_server(host: &str, port: u16) -> anyhow::Result<Server> {
    let addr = format!("{host}:{port}");
    Server::http(&addr).map_err(|e| anyhow::anyhow!("{e}"))
}
