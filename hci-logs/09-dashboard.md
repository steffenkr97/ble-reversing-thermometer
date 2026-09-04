# Phase 8 — Lokales Dashboard (CSV + HCI-Beleg)

**Gerät (Allowlist):** `f4:db:00:00:00:d9` (Büro)  
**Code:** `dashboard/server.py`, `dashboard/thermo_dash.py`, `dashboard/static/`  
**Tests:** `python -m unittest discover -s dashboard -p "test_*.py"` — 23 Tests  
**Encoding:** unverändert `int16le / 16` ([06-encoding.md](06-encoding.md), [08-collect.md](08-collect.md))

Kein BLE, kein GATT, keine Cloud. Der Server **liest** nur: Live-CSV aus `data/`, optionale History-CSV, und die schon exportierten HCI-Extracts. Es gibt keine Writes auf `FFF5`.

## Start

Im Repo-Root (kein bleak nötig):

```
python dashboard/server.py
```

Dann Browser: `http://127.0.0.1:8765/`

| Flag | Bedeutung |
|------|-----------|
| `--host` | Bind, Standard `127.0.0.1` (nur lokal) |
| `--port` | Standard **8765** |
| `--data-dir DIR` | Live/History-CSV, Standard `data` |
| `--rooms PATH` | Allowlist, Standard `dashboard/rooms.json` |
| `--extract-dir DIR` | HCI-CSV, Standard `hci-logs/extract` |
| `--no-extract` | nur `data/`, keine Capture-Belege |

Ohne Live-CSV (Collector noch nicht gelaufen) zeigt die UI die **HCI-Belege** vom Büro-Gerät: Capture-ADV und History `07`. Sobald `collect.py` schreibt, erscheint die Quelle **Live-CSV (ADV)** zuerst.

## Allowlist

`dashboard/rooms.json` — nur eigene Geräte. Aktuell ein Eintrag: Büro. Fremde MACs in CSV/Extracts werden verworfen. Weitere Räume (Phase 7) hier ergänzen, nicht „erstes ThermoBeacon“.

## Quellen

| `source` | Datei | X-Achse | Status |
|----------|-------|---------|--------|
| `adv` | `data/thermo_<mac12>_<YYYY-MM-DD>.csv` | `timestamp` UTC (Sammelzeit) | Live, sobald Collector läuft |
| `history` | `data/history_<mac12>.csv` | `index` (0 = älteste) | Phase 6, noch keine Live-Dumps |
| `adv_capture` | `hci-logs/extract/adv.csv` | Capture-Zeit | Beleg, nur Allowlist + `parse_adv_manufacturer` |
| `history_capture` | `hci-logs/extract/att_fff5_fff3.csv` | Sample-Index | Beleg GATT `07`; Duplikate über Captures: erstes Vorkommen pro `(mac, index)` |

History hat **keine Wanduhr**. Die Capture-Zeitstempel in `history_capture` sind Dump-Zeit, nicht Gerätezeit — die UI nutzt den Index.

`parse_adv_manufacturer` bleibt auf die Büro-MAC begrenzt. Capture-ADV anderer MACs erscheint deshalb nicht, auch wenn sie später in `rooms.json` stehen, bis der Parser gegen Display geprüft ist.

## API (nur GET)

| Pfad | Inhalt |
|------|--------|
| `/api/overview` | Räume, Zähler je Quelle, Encoding-Hinweis |
| `/api/samples?mac=&source=&limit=` | Samples + Summary. `limit` dünnt gleichmäßig aus (History-Charts) |

Unbekannte `source` → 400. Statische Dateien nur unter `dashboard/static/` (kein `..`).

Sample-JSON:

```
timestamp, mac, temp_c, humidity_rh, source, raw_hex, index, record, room, file
```

Live-Spalten bleiben die Collector-Spalten ([08-collect.md](08-collect.md)). History-CSV (wenn vorhanden): `mac, index, record, temp_c, humidity_rh, raw_hex` plus optionales `timestamp_inferred`.

## UI

Eine Seite, kein Build, kein npm. Canvas-Chart (Temperatur + Luftfeuchtigkeit), Raumkarten, Quellen-Tabs, Tabelle. Auto-Auswahl: Live-CSV wenn Zeilen da sind, sonst History-Capture.

Hum `/16` intern, Live ±3 % zum Display — in der Fußzeile, nicht als exakte Display-Kopie.

## Nicht

- `0x18` / `0x04` / andere Blacklist-Cmds
- fremde MACs als Räume
- Cloud, Hersteller-App, BLE-Scan aus dem Dashboard
