# ToDos — ThermoBeacon Data Collector

**Endziel:** Eigene ThermoBeacons (bis zu **5 Räume**) lokal auslesen — Live per ADV und Vergangenheit per GATT-History — und so speichern, dass später ein Dashboard die Verläufe zeigen kann. Keine Hersteller-App, keine Cloud.

Erstes Gerät (Protokoll-Beleg): `f4:db:00:00:00:d9`, System ID `D9 00 00 00 00 00 DB F4`.

**Aktuelle Phase:** Phase 9 lokale App (`python app.py`). Allowlist in `rooms.json` (Büro bestätigt, 4 Kandidaten). History seit letztem Abruf, Live-ADV im Lauf. Nicht `0x18`/`0x04`.

---

## Ist-Stand

| Bereich | Status |
|---------|--------|
| Gerät identifiziert (Name, MAC, System ID) | erledigt |
| GATT: Service `FFE0`, Write `FFF5`, Notify `FFF3` | erledigt |
| Scan / DIS-CSV (`mini.py`, `list_system_ids.py`) | erledigt |
| 1-Byte-Fuzzer auf `FFF5` (`ble_kurz.csv`) | erledigt, nicht vollständig dekodiert |
| HCI-Capture der offiziellen App | erledigt (`hci-logs/*.cfa`, [01-sessions.md](hci-logs/01-sessions.md)) |
| Encoding von °C / %rF | `/16`; Live: Temp = Display 25,125 °C; Hum ±3 %; Capture Nov 2025 hatte +10 |
| Collector mit Speichern | Code: Allowlist je MAC; ADV-Scan live OK; CSV-Lauf am Büro noch offen |
| Lokales Dashboard / App | `python app.py` (Sync+UI); `dashboard/server.py` ohne BLE |
| History-Dump / 5 Geräte | Dump-CLI + Extract 1586 Samples + `--all-rooms`; Live-GATT und Display-Check 2–5 offen |

Live-CSV = `collect.py` über ADV (kein GATT). GATT-Probe bleibt `read_thermometer_data.py`. `fuzzer.py` nur für bereits beobachtete Kommandos; Blacklist `0x04`, `0x05`, `0xFF`, `0xFE` bleibt unangetastet.

---

## Phase 1 — Capture der App

Captures lagen bereits unter `hci-logs/` (nicht `research-device/hci/`). Auswertung:

- [x] HCI-Log der offiziellen App (Android btsnoop, OnePlus 5T) — [01-sessions.md](hci-logs/01-sessions.md)
- [x] Quelle, App-Aktion, Display 33 °C / Offset +10 (%rF nicht notiert) — [hci-logs-notes.md](hci-logs-notes.md)
- [x] Reihenfolge Connect → Discovery → CCCD → FFF5 → FFF3 — [02-att-sequenz.md](hci-logs/02-att-sequenz.md)
- [x] Handles verifiziert: FFF5 Value `0x0021`, FFF3 Value `0x0024`, CCCD `0x0025` (nRF 32/35 = Declarations)
- [x] Advertising: Live-°C/%rF in ADV_IND ohne Connection — [03-advertising.md](hci-logs/03-advertising.md)

**Done:** Capture mit notierter Anzeige (33 °C / +10) im Repo, App-Writes auf FFF5 (Länge + Bytes) in [02-att-sequenz.md](hci-logs/02-att-sequenz.md). Extra: [04-opcodes.md](hci-logs/04-opcodes.md), [05-history-07.md](hci-logs/05-history-07.md).

---

## Phase 2 — Protokoll festhalten

- [x] Jeden `FFF5`-Write der App mit den folgenden `FFF3`-Notifications paaren (Timing, Länge, erstes Byte) — [06-encoding.md](hci-logs/06-encoding.md), [extract/pairs.csv](hci-logs/extract/pairs.csv)
- [x] Exakte App-Payloads dokumentieren (nicht nur 1 Byte wie im Fuzzer)
- [x] `FFF3`-Layout als Hypothesentabelle: Offset, Länge, Byte-Order, Skala (`/10`, `/100`, `/16`), Beleg (Capture-Zeile)
- [x] Felder zuordnen: Temperatur, Luftfeuchtigkeit, optional Zeit/Checksum — Unklares als Hypothese markieren
- [x] Bedeutung von `0x01` / `0x03` / `0x07` / `0x1A` / `0xF3` gegen App-Traffic prüfen. `0xF3` ist **kein** App-Befehl (nur Fuzzer); Live steht in ADV_IND
- [x] Neue Fakten in `hci-logs/*.md` (nicht nur AGENTS.md)

**Done:** reproduzierbar ist ADV_IND (Live, kein Connect) und GATT `07` (History). Dieselbe ADV-Frame: Temp `/16` = 22,06 °C (+10 → 32,06 vs. Display 33); Hum `/16` = 64,94 % im selben Frame. Display-% war nicht notiert; `/10` für Hum ist ausgeschlossen (>100 %). Rest: [06-encoding.md](hci-logs/06-encoding.md).

---

## Phase 3 — Reproduzierbares Read

- [x] Parser Rohbytes → `temp_c` / `humidity_rh` (`collector/thermo_parse.py`, Unittest `collector/test_thermo_parse.py`, 11 Tests)
- [x] ADV-Scan CLI `collector/scan_live.py` — Live 2026-09-03: Display = Roh 25,125 °C, Hum ±3 %
- [x] GATT-Probe in `collector/read_thermometer_data.py`: `--address`, `--use-system-id`, `--history INDEX`, `--debug-only`. Sequenz CCCD + `1A` + `01` + optional eine `07`-Page. Kein `--kick`, kein Erstes-Gerät-Fallback. (Code; Live-GATT offen)
- [x] Gegen Display live gegenprüfen (ADV): 2026-09-03, kein +10, [07-read.md](hci-logs/07-read.md)

Gerät über MAC / System ID und die Parser-Funktion sind **im Code** erledigt. Aufrufe, API, Goldvektoren: [hci-logs/07-read.md](hci-logs/07-read.md).

**Done, wenn:** ein Lauf auf dem Büro-Gerät konsistent plausible °C und %rF ausgibt (ADV und/oder GATT). ADV ist durch (Display = Roh). GATT-Probe live bleibt offen.

---

## Phase 4 — Collector-Skript

`collector/collect.py` sammelt Live-Werte **nur über ADV_IND** (kein Connect, kein GATT-Kick). Stack: Python 3.8+, `bleak>=0.21.0`. Details: [hci-logs/08-collect.md](hci-logs/08-collect.md).

- [x] Gerät finden über ADV/Payload-MAC (`scan_live`, `TARGET_MAC`) — kein GATT-Kick für Live
- [x] Messpunkt mit Zeitstempel ISO-8601 UTC (`…Z`)
- [x] CSV: `timestamp, mac, temp_c, humidity_rh, raw_hex`
- [x] Modi `--once` und `--interval`
- [x] Timeout: `--once` Exit 1; `--interval` loggen und retry
- [x] Keine Cloud, keine Hersteller-App, keine unbekannten Multi-Byte-Writes

**Done, wenn:** `python collector/collect.py` ohne App Messwerte in eine lokale Datei schreibt. ADV-Scan ist durch; CSV-Lauf bleibt offen.

---

## Phase 5 — Speichern so, dass Aufbereitung später einfach ist

- [x] Ausgabepfad `data/thermo_<mac12>_<datum>.csv` (UTC-Tag); Rohhex behalten
- [x] Eine Zeile = ein Sample; Rohhex in der CSV
- [x] Spalten, Einheiten, Intervall in [08-collect.md](hci-logs/08-collect.md)
- [ ] Live-CSV am Büro-Gerät (`collect.py` schreibt erst dann echte Zeilen)
- [ ] Optional: JSONL / eine Datei pro Gerät, sobald Live + History zusammen ins Dashboard sollen (Phase 8)

---

## Phase 6 — Vergangenheit (History-Dump, ein Gerät)

GATT wie die App: CCCD → `1A` → `01` (Sample-Count) → wiederholte `07`-Pages. Nur beobachtete Writes. Beleg: [05-history-07.md](hci-logs/05-history-07.md), Probe: `read_thermometer_data.py`.

History hat **keine Wanduhr** — nur Index (0 = älteste). Zeit fürs Dashboard: `timestamp_inferred` (Hypothese 10 min, [10-history-dump.md](hci-logs/10-history-dump.md)).

- [ ] GATT-Probe live am Büro-Gerät: `python collector/read_thermometer_data.py --address f4:db:00:00:00:d9` (`1A` + `01`, Count notieren)
- [ ] Eine Page: `--history 0` (älteste) und eine Page nahe Count (neueste) gegen aktuelles ADV
- [x] Sample-Intervall ableiten — **Hypothese 10 min** (ADV-Counter 949579 / Count 1583 ≈ 599,86 s). Nicht Fakt, bis zwei Live-Zeitpunkte passen
- [x] Dump-CLI: `collector/dump_history.py` — alle Pages `07` mit `count=03`, letzte Page ggf. `01`
- [x] Speichern `data/history_<mac12>.csv`: `mac, index, record, temp_c, humidity_rh, raw_hex` plus `timestamp_inferred`
- [x] Unittest gegen Capture-Goldvektoren (`07` count 03/01, Extract 1586 Samples, Page-Plan 1584/1586/820)
- [x] Extract-Export: `python collector/dump_history.py --from-extract hci-logs/extract` (Capture `15_14_35`, 1586 Samples)
- [ ] Ein Live-Dump am Büro-Gerät (`dump_history.py --address …`)

**Done, wenn:** ein vollständiger History-Dump des Büro-Geräts lokal liegt und die neueste Page zum Live-ADV passt. Code + Capture-Export sind da; Live-GATT offen. Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`.

---

## Phase 7 — Fünf eigene Geräte (Räume)

Allowlist, kein „erstes ThermoBeacon“. Encoding erst am Büro-Gerät belegt — Gerät 2–5 kurz gegen ADV `/16` prüfen, bevor History-Dump.

Kandidaten aus den HCI-Scans (Zugehörigkeit **bestätigen**, nicht annehmen):

| MAC | Notiz |
|-----|--------|
| `f4:db:00:00:00:d9` | Büro, Protokoll-Beleg |
| `f4:d0:00:00:02:1a` | in Captures, Name ThermoBeacon |
| `f4:db:00:00:02:37` | in Captures |
| `f4:db:00:00:02:42` | in Captures |
| `62:53:00:00:0f:1f` | in Captures; anderes Company-Präfix — extra prüfen |

- [x] Geräteliste anlegen: MAC + Raumname (+ optional System ID `2A23`) in `dashboard/rooms.json`. Büro `confirmed`. Vier Capture-MACs als Kandidaten (`confirmed: false`)
- [x] Live-Collector: Allowlist statt einer hart kodierten `TARGET_MAC` — ein Sample pro MAC in die jeweilige CSV
- [ ] ADV-Live pro Raum einmal gegen Display/`/16` (Temp sollte wie Büro die Anzeige treffen) — Feld, Gerät 2–5
- [x] History-Dump CLI je MAC (`--address` / `--all-rooms`); Extract nur Büro hat `07`-Pages
- [ ] History-Dump live für jedes **bestätigte** Gerät
- [x] Fremde MACs in Reichweite ignorieren (nicht in `rooms.json`)

**Done, wenn:** alle 5 eigenen Geräte `confirmed` + `encoding_checked` und je Live-CSV + History-Datei haben. Code und Kandidatenliste sind da; Zugehörigkeit ist Feldarbeit. Details: [hci-logs/11-rooms.md](hci-logs/11-rooms.md).

---

## Phase 8 — Dashboard

Lokales UI über die Collector-CSV und die HCI-Extracts. Kein BLE. Details: [09-dashboard.md](hci-logs/09-dashboard.md).

- [x] Gemeinsames Sample-JSON: Spalten wie Live-CSV plus `source`, `room`, optional `index`
- [x] Allowlist `dashboard/rooms.json` (Büro confirmed; 4 Kandidaten sichtbar, nicht als eigene Geräte angenommen)
- [x] Dashboard / Plots (Räume, Verläufe) — `python dashboard/server.py`
- [ ] Live-CSV am Büro, damit die Quelle `adv` echte Sammelzeiten hat
- [x] History-CSV aus Dump/Extract plotbar (`dump_history.py`, Quelle `history`)
- [ ] Optional JSONL / SQLite — **Parkplatz** (nicht Release 6.1/7)

**Done, wenn:** Live- und History-Dateien ohne Extra-Parsing plotbar sind. UI und History-CSV-Import sind da; Live-CSV und Live-GATT-Dump am Gerät fehlen noch.

---

## Phase 9 — Lokale App

Ein Prozess: Geräte speichern, History seit letztem Abruf, Live-ADV, Dashboard. [12-app.md](hci-logs/12-app.md).

- [x] `python app.py` — HTTP + BLE-Worker (`--no-ble` ohne Adapter)
- [x] Room-CRUD (MAC + Anzeigename, max. 5, nur localhost)
- [x] Inkrementeller History-Dump (nur confirmed, `1A`/`01`/`07`)
- [x] Live-ADV-Loop nach dem Sync
- [x] Status-API + Auto-Refresh
- [ ] Feldlauf am Büro-Gerät (`python app.py`)

---

## Bewusst nicht tun

- Fuzzer auf Blacklist oder unbekannte Multi-Byte-Writes ausweiten
- Firmware knacken, Pairing umgehen, **fremde** Geräte angreifen (nur Allowlist)
- History-Dump über `04`/`18` oder 1-Byte-Kicks statt App-`07`
- Collector bauen, bevor Phase 2 ein belegtes Encoding hat
- `reader.py` als Vorlage für Connection-Lifetime verwenden

---

## Parkplatz (nicht in Release 6.1 / 7)

Bewusst nicht bauen, bis 5 bestätigte Räume wehtun oder ein Kalibrier-Test ansteht:

- SQLite / JSONL statt CSV
- History-Intervall 10 min als Fakt (erst mit zwei Live-Counts in `data/interval_evidence.jsonl`)
- Hum-Anzeige enger als ±3 %
- `0x18` / `0x04` nur in einem bewussten Kalibrier-Test
- Dashboard-Komfort: Batterie in der CSV, Alarme, Live+History in einem Chart
  (Auto-Refresh und Geräte-UI: Phase 9)

---

## Empfohlene Reihenfolge (nächster konkreter Schritt)

1. ~~HCI-Capture der App~~ — erledigt, siehe `hci-logs/01-…05-*.md`
2. ~~`FFF5`/`FFF3`-Paare und Encoding~~ — erledigt, [06-encoding.md](hci-logs/06-encoding.md)
3. ~~Parser + ADV-CLI + GATT-Probe (Code)~~ — erledigt, [07-read.md](hci-logs/07-read.md)
4. ~~Collector ADV→CSV (Code)~~ — erledigt, [08-collect.md](hci-logs/08-collect.md)
5. ~~Live-ADV `scan_live.py`~~ — erledigt 2026-09-03, Display = Roh 25,125 °C, [07-read.md](hci-logs/07-read.md)
6. **Feld Büro:** `python app.py` oder `python collector/mvp_buero.py --address f4:db:00:00:00:d9`
7. ~~Extract-History + Dashboard~~ — Code da; App oder `dashboard/server.py`
8. Gerät 2–5: Zugehörigkeit, Display vs. `/16`, dann in der UI bestätigen
9. ~~Lokale App~~ — Code da ([12-app.md](hci-logs/12-app.md)); Live-GATT am Gerät offen

**Nicht** als Nächstes `0x18`/`0x04`, SQLite, Alarme.
