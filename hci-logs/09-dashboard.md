# Phase 8 — Lokales Dashboard (CSV + HCI-Beleg)

**Gerät (Allowlist):** `f4:db:00:00:00:d9` (Büro)  
**Code:** `dashboard/server.py`, `dashboard/thermo_dash.py`, `dashboard/static/`  
**Tests:** `python -m unittest discover -s dashboard -p "test_*.py"`  
**Encoding:** unverändert `int16le / 16` ([06-encoding.md](06-encoding.md), [08-collect.md](08-collect.md))

Kein GATT im HTTP-Prozess. Die **App** (`python app.py`) startet denselben Server plus BLE-Worker ([12-app.md](12-app.md)). `dashboard/server.py` allein bleibt ohne Worker. Writes auf `rooms.json` nur von localhost. Es gibt keine FFF5-Writes aus den HTTP-Handlern.

## Start

Im Repo-Root (kein bleak nötig):

```
python app.py
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

`dashboard/rooms.json` — eigene Geräte und sichtbare Kandidaten. Büro `confirmed` + `encoding_checked`. Vier Capture-MACs als Kandidaten (`confirmed: false`), nicht als eigene Räume annehmen. Fremde MACs außerhalb der Datei werden verworfen. Capture-ADV nur `encoding_checked` (Büro), bis Gerät 2–5 gegen Display geprüft sind. [11-rooms.md](11-rooms.md).

## Quellen

| `source` | Datei | X-Achse | Status |
|----------|-------|---------|--------|
| `adv` | `data/thermo_<mac12>_<YYYY-MM-DD>.csv` | `timestamp` UTC (Sammelzeit) | Live, sobald Collector läuft |
| `history` | `data/history_<mac12>.csv` | `timestamp_inferred` wenn gesetzt, sonst `index` | Phase 6: `dump_history.py` (GATT oder `--from-extract`) |
| `adv_capture` | `hci-logs/extract/adv.csv` | Capture-Zeit | Beleg, nur Allowlist + `parse_adv_manufacturer` |
| `history_capture` | `hci-logs/extract/att_fff5_fff3.csv` | Sample-Index | Beleg GATT `07`; Duplikate über Captures: erstes Vorkommen pro `(mac, index)` |

History hat **keine Geräte-Wanduhr**. `timestamp_inferred` ist Hypothese **10 min** (ADV-Counter/Count ≈ 600 s) — [10-history-dump.md](10-history-dump.md). Die Capture-Zeitstempel in `history_capture` sind Dump-Zeit, nicht Gerätezeit — die UI nutzt dort den Index.

`parse_adv_manufacturer` für Capture-ADV nur mit `encoding_checked`-MACs. Capture-ADV anderer MACs erscheint deshalb nicht, auch wenn sie in `rooms.json` stehen, bis der Parser gegen Display geprüft ist.

Zeilen aus `old/*.cfa` werden übersprungen: die 2018-Zeitstempel sind Geräteuhr, nicht Wanduhr, und würden die Zeitachse unlesbar machen.

## API

| Pfad | Inhalt |
|------|--------|
| `GET /api/overview` | Räume, Zähler je Quelle, Encoding-Hinweis |
| `GET /api/samples?mac=&source=&limit=` | Samples + Summary. `limit` dünnt gleichmäßig aus (History-Charts) |
| `GET /api/status` | BLE-Worker (Phase, History/Live je Gerät); ohne Worker `ble=false` |
| `POST /api/rooms` | Gerät anlegen (Name + MAC), max. 5, nur localhost |
| `PATCH /api/rooms/{id}` | Name / confirmed / encoding_checked / note |
| `DELETE /api/rooms/{id}` | Gerät entfernen |

Unbekannte `source` → 400. Statische Dateien nur unter `dashboard/static/` (kein `..`).

Sample-JSON:

```
timestamp, mac, temp_c, humidity_rh, source, raw_hex, index, record, room, file
```

Live-Spalten bleiben die Collector-Spalten ([08-collect.md](08-collect.md)). History-CSV: `mac, index, record, temp_c, humidity_rh, raw_hex` plus optionales `timestamp_inferred` ([10-history-dump.md](10-history-dump.md)).

## UI

Eine Seite, kein Build, kein npm. Canvas-Chart (Temperatur + Luftfeuchtigkeit), Raumkarten, Quellen-Tabs, Tabelle, Geräteformular, Sync-Leiste. Auto-Refresh 15 s. Auto-Auswahl: Live-CSV wenn Zeilen da sind, sonst History-CSV, sonst History-Capture.

Hum `/16` intern, Live ±3 % zum Display — in der Fußzeile, nicht als exakte Display-Kopie.

## Nicht

- `0x18` / `0x04` / andere Blacklist-Cmds
- fremde MACs als Räume
- Cloud, Hersteller-App, BLE-Scan aus dem Dashboard
