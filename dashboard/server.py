#!/usr/bin/env python3
"""Lokales ThermoBeacon-Dashboard. Nur Lesen, kein BLE, kein Cloud."""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import List, Optional
from urllib.parse import parse_qs, unquote, urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from thermo_dash import (  # noqa: E402
    DEFAULT_DATA_DIR,
    DEFAULT_EXTRACT_DIR,
    DEFAULT_ROOMS_PATH,
    DashStore,
    KNOWN_SOURCES,
)

STATIC_DIR = os.path.join(_HERE, "static")
INDEX_NAME = "index.html"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Lokales Dashboard für ThermoBeacon-CSV und HCI-Belegdaten. "
            "Kein Connect, kein GATT, keine Cloud."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind-Adresse (Standard: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (Standard: 8765)")
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        metavar="DIR",
        help="Live/History-CSV (Standard: data/)",
    )
    parser.add_argument(
        "--rooms",
        default=DEFAULT_ROOMS_PATH,
        metavar="PATH",
        help="Allowlist rooms.json",
    )
    parser.add_argument(
        "--extract-dir",
        default=DEFAULT_EXTRACT_DIR,
        metavar="DIR",
        help="HCI-Extracts (adv.csv, att_fff5_fff3.csv)",
    )
    parser.add_argument(
        "--no-extract",
        action="store_true",
        help="HCI-Belegdaten nicht einlesen (nur data/)",
    )
    args = parser.parse_args(argv)
    if args.port <= 0 or args.port > 65535:
        parser.error("--port muss 1–65535 sein")
    return args


def json_bytes(payload: dict, status: int = 200) -> tuple:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return status, "application/json; charset=utf-8", body


def safe_static_path(url_path: str) -> Optional[str]:
    rel = unquote(url_path).lstrip("/")
    if not rel or rel == "/":
        rel = INDEX_NAME
    if ".." in rel.replace("\\", "/").split("/"):
        return None
    full = os.path.normpath(os.path.join(STATIC_DIR, rel))
    static_root = os.path.normpath(STATIC_DIR)
    if full != static_root and not full.startswith(static_root + os.sep):
        return None
    if os.path.isdir(full):
        full = os.path.join(full, INDEX_NAME)
    if not os.path.isfile(full):
        return None
    return full


def content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }.get(ext, "application/octet-stream")


def make_handler(store: DashStore):
    class DashboardHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send(self, status: int, ctype: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            code, ctype, body = json_bytes(payload, status)
            self._send(code, ctype, body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path.startswith("/api/"):
                self._api(path, parse_qs(parsed.query))
                return
            static_path = safe_static_path(path)
            if static_path is None:
                if path.startswith("/api"):
                    self._send_json({"error": "nicht gefunden"}, 404)
                    return
                self._send(404, "text/plain; charset=utf-8", b"nicht gefunden\n")
                return
            with open(static_path, "rb") as handle:
                body = handle.read()
            self._send(200, content_type(static_path), body)

        def _api(self, path: str, query: dict) -> None:
            try:
                if path == "/api/overview":
                    self._send_json(store.overview())
                    return
                if path == "/api/samples":
                    mac = (query.get("mac") or [None])[0]
                    source = (query.get("source") or [None])[0]
                    if source and source not in KNOWN_SOURCES:
                        self._send_json(
                            {"error": "unbekannte source", "allowed": list(KNOWN_SOURCES)},
                            400,
                        )
                        return
                    limit_raw = (query.get("limit") or ["0"])[0]
                    try:
                        limit = int(limit_raw)
                    except (TypeError, ValueError):
                        self._send_json({"error": "limit muss eine Zahl sein"}, 400)
                        return
                    if limit < 0:
                        self._send_json({"error": "limit darf nicht negativ sein"}, 400)
                        return
                    self._send_json(store.query(mac=mac, source=source, limit=limit))
                    return
                self._send_json({"error": "nicht gefunden"}, 404)
            except FileNotFoundError as exc:
                self._send_json({"error": "Datei fehlt", "detail": str(exc)}, 500)
            except Exception as exc:  # noqa: BLE001 — API soll nicht den Thread killen
                self._send_json({"error": "intern", "detail": str(exc)}, 500)

    return DashboardHandler


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    store = DashStore(
        data_dir=os.path.abspath(args.data_dir),
        rooms_path=os.path.abspath(args.rooms),
        extract_dir=None if args.no_extract else os.path.abspath(args.extract_dir),
        include_extract=not args.no_extract,
    )
    store.refresh(force=True)
    handler = make_handler(store)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = "http://{0}:{1}/".format(args.host, args.port)
    print("Dashboard: {0}".format(url))
    print("data-dir: {0}".format(store.data_dir))
    print(
        "extract: {0}".format(
            store.extract_dir if store.include_extract else "aus (--no-extract)"
        )
    )
    print("Samples geladen: {0}".format(len(store.samples)))
    print("Nur lokal, kein BLE. Strg+C beendet.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
