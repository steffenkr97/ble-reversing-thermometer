# Phase 7 — Fünf Räume (Allowlist)

**Geräteliste:** [`dashboard/rooms.json`](../dashboard/rooms.json)  
**Code:** `collector/thermo_rooms.py`, `collector/collect.py`, `collector/scan_live.py`, `collector/dump_history.py --all-rooms`, Dashboard-Raumkarten  
**Tests:** `python -m unittest discover -s collector -p "test_*.py"` und `discover -s dashboard`

Kein „erstes ThermoBeacon“. Live und History nur für MACs in `rooms.json`. Fremde Geräte in Reichweite werden ignoriert.

## rooms.json

| Feld | Bedeutung |
|------|-----------|
| `id` | stabile Raum-ID (`buero`, `kandidat-021a`, …) |
| `name` | Anzeigename |
| `mac` | Payload-MAC, Allowlist |
| `system_id` | optional, 8 Byte hex (`2A23`). Büro: `D90000000000DBF4` |
| `confirmed` | eigenes Gerät. `false` = Kandidat aus HCI-Scans, nicht annehmen |
| `encoding_checked` | ADV `/16` gegen Display geprüft. Nur Büro `true` |
| `note` | Hinweis in der Datei / API |

Aktuell **ein** bestätigtes Gerät (Büro). Vier Capture-MACs stehen als Kandidaten mit `confirmed: false` — Zugehörigkeit und Display-Check sind Feldarbeit.

| MAC | Status |
|-----|--------|
| `f4:db:00:00:00:d9` | Büro, Encoding-Beleg |
| `f4:d0:00:00:02:1a` | Kandidat 2 |
| `f4:db:00:00:02:37` | Kandidat 3 |
| `f4:db:00:00:02:42` | Kandidat 4 |
| `62:53:00:00:0f:1f` | Kandidat 5, anderes Company-Präfix — extra prüfen |

Nach Display-Check: `confirmed` und `encoding_checked` auf `true` setzen, `name` auf den Raumnamen — in der App-UI („Bestätigen“) oder in der Datei. Die App synct nur **confirmed** (kein GATT auf Kandidaten). Über die UI hinzugefügte Geräte sind confirmed. Max. 5 Einträge (`save_rooms`). [12-app.md](12-app.md).

## Collector

`python collector/collect.py` scannt **alle** Allowlist-MACs in einem Fenster, schreibt `data/thermo_<mac12>_<datum>.csv` je Treffer. Fehlende MACs stehen auf stderr, Exit 0 sobald mindestens ein Sample da ist.

Nur Büro:

```
python collector/collect.py --mac f4:db:00:00:00:d9
```

`--output` braucht genau ein `--mac`. Parser: `parse_adv_manufacturer(..., allowed_macs=Allowlist)`. Ohne Allowlist bleibt das Default-Verhalten nur Büro (HCI-Beleg).

`scan_live.py` CLI bleibt standardmäßig Büro (`--mac` Default). `--rooms` prüft, dass die MAC in der Liste steht.

## History je MAC

```
python collector/dump_history.py --address f4:db:00:00:00:d9
python collector/dump_history.py --from-extract hci-logs/extract --all-rooms
```

`--all-rooms` schreibt je vorhandener Extract-/GATT-History `data/history_<mac12>.csv`. In den Nov-2025-Captures hat nur das Büro `07`-Pages — andere MACs werden übersprungen, kein Fehler wenn mindestens eine Datei entsteht.

GATT: System-ID nur gegen `rooms.json` / Büro-Sollwert. Andere Allowlist-MACs nicht mit der Büro-`2A23` vergleichen.

Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`.

## Dashboard

Raumkarten für jeden Eintrag. Kandidaten (`confirmed=false`) gestrichelt, Hinweis „Zugehörigkeit bestätigen“. Capture-ADV (`adv_capture`) nur für `encoding_checked` — andere MACs erscheinen dort nicht, auch wenn sie in der Allowlist stehen, bis der Display-Check da ist. Live-CSV und History-CSV der Kandidaten werden gelesen, sobald Dateien existieren.

## Büro-MVP (Release 6.1)

Feldlauf, kein neues Opcode:

```
python collector/mvp_buero.py --address f4:db:00:00:00:d9
```

1. Live-CSV ADV  
2. GATT-Dump `07` (oder `--from-extract`)  
3. neueste History vs. Live-ADV (Temp-Toleranz 2 °C)  
4. Zeile in `data/interval_evidence.jsonl` (Count + Uhr). Zweiter Lauf prüft die 10-min-Hypothese  

Hersteller-App zu. Nicht `0x18`/`0x04`.

## Nicht

- SQLite / Alerts / MQTT (Parkplatz)  
- `parse_adv_manufacturer` ohne Allowlist für beliebige MACs  
- Kalibrier-Writes `0x18` / `0x04`  
- unbestätigte Capture-MACs als eigene Räume behandeln  
