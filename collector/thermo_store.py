#!/usr/bin/env python3
"""CSV-Speicher für ThermoBeacon-Samples (kein BLE)."""
import csv
import os
from datetime import datetime, timezone


COLUMNS = ("timestamp", "mac", "temp_c", "humidity_rh", "raw_hex")


def iso_utc_now() -> str:
    """UTC, Format YYYY-MM-DDTHH:MM:SSZ (keine lokale Zeit, keine Mikrosekunden)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mac12(mac: str) -> str:
    """MAC ohne Trenner, lowercase (12 Hex-Zeichen bei 6-Byte-MAC)."""
    return mac.replace(":", "").replace("-", "").replace(".", "").lower()


def default_csv_path(mac: str, outdir: str = "data") -> str:
    """Pfad data/thermo_<mac12>_<YYYY-MM-DD>.csv (UTC-Tag, nicht lokal)."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return os.path.join(outdir, "thermo_{}_{}.csv".format(_mac12(mac), day))


def ensure_header(path: str) -> None:
    """Datei anlegen (inkl. Parent-Dirs), Header nur wenn Datei neu oder leer."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    need_header = (not os.path.exists(path)) or (os.path.getsize(path) == 0)
    if need_header:
        with open(path, "w", newline="") as handle:
            csv.writer(handle).writerow(COLUMNS)


def append_sample(path, timestamp, mac, temp_c, humidity_rh, raw_hex) -> None:
    """ensure_header, dann eine CSV-Zeile. csv-Modul, kein manuelles Komma-Join."""
    ensure_header(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", newline="") as handle:
        csv.writer(handle).writerow([timestamp, mac, temp_c, humidity_rh, raw_hex])
