# Phase 9 — Lokale App (Dashboard + Sync)

**Start:** `python app.py` → `http://127.0.0.1:8765/`  
**Code:** `app.py`, `collector/thermo_sync.py`, `collector/thermo_rooms.py` (`save_rooms`), History-Merge in `thermo_history.py`  
**Tests:** `python -m unittest discover -s collector -p "test_*.py"` und `discover -s dashboard`  
**Nur:** Opcodes `1A` / `01` / `07`. Nicht senden: `0x18` / `0x04`.

Ein Prozess: HTTP-Dashboard und optionaler BLE-Worker. `python dashboard/server.py` bleibt der Lese-Modus ohne Worker. `--no-ble` startet die App ohne Adapter (Tests, Maschinen ohne BlueZ).

## Ablauf

1. Allowlist aus `dashboard/rooms.json` (max. 5, MAC + Anzeigename).
2. Beim Start: für jedes **confirmed**-Gerät History seit dem letzten Abruf (GATT `07`).
3. Danach Live-ADV-Loop (Standard 60 s), Append in `data/thermo_<mac12>_<UTC-Tag>.csv`.
4. UI wie bisher (Charts/Tabs), plus Geräteformular, Sync-Status, Auto-Refresh 15 s.

Kandidaten (`confirmed: false`) bleiben sichtbar und werden **nicht** per GATT verbunden. Über die UI hinzugefügte Geräte sind `confirmed: true`. Neu bestätigte Geräte holt der laufende Worker nach (rooms.json-mtime).

## History inkrementell

| Schritt | Verhalten |
|---------|-----------|
| CSV fehlt | voller `page_plan(count)` |
| `max(index)` bekannt | `page_plan_since(count, last_index)`, überlappende Page mit |
| `count <= last_index+1` | keine Pages, CSV bleibt, Sync-State aktualisieren |
| Count sinkt | voller Dump, alte höhere Indizes verwerfen (Reset-Hypothese) |

Merge nach `index` (neue Zeile gewinnt). Anschließend `apply_inferred_timestamps` mit Anker *jetzt* und `newest_index = count-1` (10-min-Hypothese, kein Fakt). Cursor: `data/sync_<mac12>.json` (`last_index`, `last_count`, `last_dump_at`).

## API

| Methode | Pfad | Rolle |
|---------|------|--------|
| GET | `/api/overview`, `/api/samples` | unverändert |
| GET | `/api/status` | Worker-Phase, pro Gerät History/Live |
| POST | `/api/rooms` | Gerät anlegen (Name + MAC) |
| PATCH | `/api/rooms/{id}` | Name, `confirmed`, `encoding_checked`, `note` |
| DELETE | `/api/rooms/{id}` | Gerät entfernen |

Writes nur von localhost (`127.0.0.1` / `::1`). Kein BLE in den HTTP-Handlern.

## CLI

```
python app.py
python app.py --no-ble
python app.py --interval 60 --timeout 15
```

Feld/Debug unverändert: `collect.py`, `dump_history.py`, `mvp_buero.py`.

## Nicht

- SQLite / JSONL (Parkplatz)
- Scan-to-Add, Alarme, fremde Geräte
- Kandidaten automatisch `confirmed` setzen
- `0x18` / `0x04`
