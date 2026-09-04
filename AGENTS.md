# AGENTS.md — ThermoBeacon BLE Reverse Engineering

Dieses Repo reverse-engineert das Bluetooth-Protokoll **eigener** ThermoBeacon-Thermometer. Ziel: Live (ADV) und Vergangenheit (GATT `07`) lokal speichern und im Dashboard zeigen — bis zu **5 Räume**. Keine Hersteller-App.

**Aktuelle Phase:** Lokales Dashboard liest Live-CSV + HCI-Belege ([09-dashboard.md](hci-logs/09-dashboard.md)). Live-CSV am Büro noch offen, dann History-Dump (Phase 6–7). Nicht `0x18`/`0x04`.

## Auftrag an Agents

1. **Jetzt:** `python collector/collect.py` (venv) — Live-CSV, dann `python dashboard/server.py`. Hum `/16` nur ±3 % zum Display. `0x18` nicht als Offset-Fakt.
2. **Danach:** History-Dump nur mit App-Sequenz `1A` → `01` → `07`-Pages. Dann Allowlist für 5 eigene MACs in `dashboard/rooms.json`. `0x18` / `0x04` nicht senden.
3. **Nicht:** fremde Geräte, Exploits/PoCs, Fuzzer auf destruktive Kommandos, Firmware knacken.

Nur Geräte auf der Allowlist (TODO Phase 7). Unklare Bytes als Hypothese markieren, nicht als Fakt. Encoding-Beleg bleibt das Büro-Gerät, bis Gerät 2–5 gegen Display geprüft sind.

## Zielgerät (Büro)

| Feld | Wert |
|------|------|
| Name | ThermoBeacon |
| MAC | `f4:db:00:00:00:d9` |
| macOS-Adresse | `8277B476-C20F-BC82-678E-540BEC258660` (CoreBluetooth-UUID, keine MAC) |
| System ID (`2A23`) | `D9 00 00 00 00 00 DB F4` (MAC-Bytes, little-endian) |
| Kalibrier-Hinweis | Nov 2025: Display 33 °C = **+10**. Live 2026-09-03: Display **= Roh `/16`** (25,125 °C), kein Offset. |

Weitere ThermoBeacons in den Captures — Zugehörigkeit zu den 5 eigenen Räumen in TODO Phase 7 bestätigen. Nicht das erstbeste Gerät nehmen — Allowlist (MAC / System ID).

## Auswertung

Tabellen und Belege stehen in den MDs, nicht doppelt hier:

| MD | Inhalt |
|----|--------|
| [hci-logs/01-sessions.md](hci-logs/01-sessions.md) | Captures, Quelle OnePlus 5T, Display +10 / 33 °C |
| [hci-logs/02-att-sequenz.md](hci-logs/02-att-sequenz.md) | Handles, App-Ablauf, alle nicht-`07`-Writes |
| [hci-logs/03-advertising.md](hci-logs/03-advertising.md) | Live-°C/%rF in ADV_IND ohne GATT |
| [hci-logs/04-opcodes.md](hci-logs/04-opcodes.md) | Opcode-Histogram, Blacklist-Cmds |
| [hci-logs/05-history-07.md](hci-logs/05-history-07.md) | History-Frame, `count` 03/01 |
| [hci-logs/06-encoding.md](hci-logs/06-encoding.md) | Phase 2: Paare, Payloads, Skala `/16` |
| [hci-logs/07-read.md](hci-logs/07-read.md) | Phase 3: Parser-API, CLIs, Goldvektoren, ADV-Live 2026-09-03 |
| [hci-logs/08-collect.md](hci-logs/08-collect.md) | Phase 4: ADV-Collector, CSV-Spalten, Flags |
| [hci-logs/09-dashboard.md](hci-logs/09-dashboard.md) | Lokales Dashboard: API, Quellen, Allowlist |
| [hci-logs-notes.md](hci-logs-notes.md) | Index + Kalibrier-Hinweis |
| [ANLEITUNG.md](ANLEITUNG.md) | CLI-Schritte für den Live-Lauf |

Parser: `python collector/parse_btsnoop.py --export hci-logs/extract` (nur Lesen).

## Repo-Karte

```
py/                                  ältere User-Skripte (Fuzzer, mini, reader, list_system_ids)
collector/                           Phase-3/4-Code (Parser, ADV-Scan, GATT-Probe, Collector, btsnoop)
dashboard/                           lokales Frontend (CSV + HCI-Extract, kein BLE)
data/                                Live-CSV (`data/.gitkeep`; `*.csv` in `.gitignore`)
research-device/                     nRF-Connect-Logs, ältere Doku
hci-logs/                            Android HCI-Snoop (.cfa = btsnoop) + Auswertung
  01-sessions.md … 08-collect.md  Befund-MDs
  extract/                           CSV aus parse_btsnoop.py
  hci_snoop_2025_11_26_14_52_44.cfa  Einstiegs-Capture (App-Sync, History)
  hci_snoop_2025_11_26_15_00_04.cfa  langer History-Dump
  hci_snoop_2025_11_26_15_14_35.cfa  inkl. Extra-Cmds (Kalibrierung?)
  old/                               ältere / andere Sessions
hci-logs-notes.md                    Index (Kalibrierung +10)
```

**Wichtig:** `.cfa` ist für Glob/Read oft unsichtbar (Binärdatei). Verzeichnis per Shell listen (`Get-ChildItem hci-logs`). Nicht nach `research-device/hci/` suchen.

## HCI-Captures (`.cfa`)

Magic-Bytes `btsnoop\0`, Datalink **1002** (HCI UART H4). Das ist ein **Android HCI Snoop Log**, trotz Endung `.cfa` (Frontline-ähnlicher Name). Quelle in den Strings: **OnePlus 5T**. nRF-Connect-Textlogs sind kein Ersatz — die enthalten keine ATT-Nutzdaten.

| Datei | Größe | Inhalt (kurz) |
|-------|-------|----------------|
| `hci-logs/hci_snoop_2025_11_26_14_52_30.cfa` | ~20 KB | Scan, kaum ATT |
| `hci-logs/hci_snoop_2025_11_26_14_52_44.cfa` | ~67 KB | **Startdatei:** CCCD + `1A` + `01` + History `07` (~96 Pages) |
| `hci-logs/hci_snoop_2025_11_26_15_00_04.cfa` | ~147 KB | langer `07`-Dump (~528 Pages) |
| `hci-logs/hci_snoop_2025_11_26_15_14_35.cfa` | ~194 KB | History plus `0x04` / `0x18` (vermutlich Kalibrier-Session) |
| `hci-logs/old/*.cfa` | — | ältere Sessions; u. a. `0x05` / `0x0F` / `0x19` |

Öffnen: Wireshark → Datei öffnen (Filter `btatt`). Kopie als `.log` ist optional, der Inhalt ist schon btsnoop. `tshark -r hci_snoop_….cfa -Y btatt` falls installiert.

Neue Captures weiter nach `hci-logs/` legen und in `hci-logs-notes.md` notieren: was die App tat, angezeigte Temperatur.

## GATT-Stand (belegt)

Kein Standard Health Thermometer (`1839`). DIS (`180A`) mit Platzhalter-Strings. System ID ist echt.

Custom-Service (Base UUID `0000XXXX-0000-1000-8000-00805f9b34fb`):

| Rolle | 16-bit | Properties | Value-Handle (Android-Capture) | nRF-Handle |
|-------|--------|------------|--------------------------------|------------|
| Service `FFE0` | `FFE0` | — | start `0x001F` | — |
| Control `FFF5` | `FFF5` | Write | **`0x0021` (33)** | 32 (Declaration) |
| Data `FFF3` | `FFF3` | Notify | **`0x0024` (36)** | 35 (Declaration) |
| CCCD FFF3 | `2902` | Write | **`0x0025` (37)** | — |

nRF-Handles sind die Characteristic-Declarations; Writes/Notifications gehen auf die Value-Handles. In jedem Capture Handles über Discovery verifizieren.

App-Ablauf in `14_52_44`:

1. Connect + Discovery (Service `FFE0` ab Handle `0x001F`)
2. CCCD `0x0025` = `01 00` (Notify an)
3. Write `1A` auf `0x0021` → Notify 20 Byte Status
4. Write `01` auf `0x0021` → Notify `01 XX XX 00 …` (History-Länge, LE uint16)
5. Wiederholt Write `07 <index:u16le> 00 00 00 03` → je 3 History-Records als Notify

`start_notify()` auf macOS setzt CCCD nicht immer. Linux ist zum Reproduzieren besser.

## Befehle aus den Captures (FFF5 → FFF3)

Antworten sind **20 Byte**, erstes Byte = Opcode (Echo), außer wo unten anders.

| Write FFF5 | Notify (Beispiel) | Lesart |
|------------|-------------------|--------|
| `1A` | `1A 01 00 01 00 …` | Status/Flags |
| `01` | `01 2F 06 00 …` | `0x062F` = 1583 → **Anzahl gespeicherter Samples** (steigt in späteren Captures: `0630`, `0631`) |
| `07 idx 00 00 <count>` | `07 idx 00 00 <count>` + Records | History-Page; `count` fast immer `03`, letzte Page ggf. `01` |
| `04 00 00 00 00` | (in `15_14_35`) | App hat es gesendet; Fuzzer-Blacklist — nicht nachbauen, bis die Bedeutung klar ist |
| `18 …` | (in `15_14_35`) | vermutlich Config/Zeit/Kalibrierung; nicht bestätigt |
| `05 FF…`, `0F 01`, `19 …` | (`hci-logs/old`) | selten, Bedeutung offen |

**History-Frame `0x07` (Framing Fakt; Skala Hypothese, Display-konsistent):**

```
07 | index:u16le | 00 00 | count | t0:i16le t1 t2 | h0:i16le h1 h2 | 00 00
```

Bei `count=01` nur ein Paar: Temp Offset 6, Hum Offset 8. Details: [06-encoding.md](hci-logs/06-encoding.md).

Beispiel erste Page: `81 01 7B 01 79 01` / `B4 03 BC 03 CB 03`

- Temp = `int16_le / 16` → ADV-Live `0x0161` = **22,0625 °C** (+10 → 32,06 vs. Display 33)
- Humidity = `int16_le / 16` → ADV `0x040F` = **64,94 %** (Display-% nicht notiert; `/10` ausgeschlossen)

Fuzzer-Frame `0xF3` enthält dieselben Rohwerte wie History-Record 1 (`0x017B` / `0x03BC`), anderes Framing. **Nicht** in der App; Live steht in ADV_IND.

## Fuzzer vs. App

`ble_kurz.csv` hat 1-Byte-Kicks. Die App schickt bei `0x07` **6 Byte**. Deshalb wirkten Fuzzer-Antworten wie leere ACKs.

Blacklist `0x04` / `0x05` / `0xFF` / `0xFE` bleibt: die App nutzt `0x04`/`0x05`, sie können History oder Settings ändern. Nicht fuzzing-mäßig wiederholen.

## HCI-Logs lesen

Filter Wireshark: `btatt`. Relevant: Write Request `0x12` auf Handle 33, Handle Value Notification `0x1B` auf Handle 36.

Was noch offen ist (Details in den MDs):

1. Hum-Skala `/16` intern und gegen `/10`/`/100`; Live ±3 % zum Display — [06-encoding.md](hci-logs/06-encoding.md)
2. `0x18` / `0x04` ändern vermutlich ADV-Config, nicht belegt als +10-Kalibrierung — [04-opcodes.md](hci-logs/04-opcodes.md)
3. `0xF3` kommt in der App **nicht** vor (nur Fuzzer); Live ohne GATT = ADV_IND
4. Letzte 2 Byte von `0x07` sind in 1800 Frames `00 00` (Padding, keine laufende Checksum)

Hypothesen als Tabelle: Offset, Länge, Byte-Order, Skala, Beleg — in den `hci-logs/0*.md`.

## Collector (Phase 3/4)

Phase-3-Code: [07-read.md](hci-logs/07-read.md). Phase-4-Collector: [08-collect.md](hci-logs/08-collect.md). Encoding: ADV Offset 12/14, History GATT `07`, `int16le / 16`.

- Live ohne Connect: `python collector/scan_live.py` (Payload-MAC `f4:db:00:00:00:d9`)
- Live-CSV: `python collector/collect.py` (ein Sample) bzw. `python collector/collect.py --interval 60` — nur ADV, kein GATT
- Dashboard: `python dashboard/server.py` — `http://127.0.0.1:8765/` (kein bleak, kein GATT)
- GATT-Probe: `python collector/read_thermometer_data.py --address …` — CCCD, dann `1A` → `01` → optional `--history INDEX`
- Gerät über MAC oder `--use-system-id` (`2A23`); kein Erstes-Gerät-Fallback
- Probe bleibt in `read_thermometer_data.py`; Live-CSV ist `collect.py` (ADV), keine zweite GATT-Sequenz. Keine Cloud, keine Hersteller-App

Stack: Python 3.8+, `bleak>=0.21.0` (`requirements.txt`; ohne bleak scheitert `--help` der CLIs). `fuzzer.py` nur für gezielte, bereits beobachtete Kommandos.

## Arbeitsregeln

- Deutsch in Doku und Commit-Messages.
- Neue Protokollfakten in `hci-logs/*.md` (ein Todo → ein MD); `AGENTS.md` nur Kurzstand + Links.
- `.cfa` nicht umschreiben; Auswertungen als Markdown/CSV daneben ablegen.
- macOS-Adressen sind UUIDs; auf Linux/Windows MAC verwenden.
- `reader.py` nicht als Referenz für Connection-Lifetime.
- Keine Firmware-Extraktion, kein Pairing-Bypass, kein Angriff auf andere Geräte.

## Offene Punkte

- [x] HCI-Capture der offiziellen App liegt unter `hci-logs/*.cfa`
- [x] Advertising-Payload dokumentiert ([03-advertising.md](hci-logs/03-advertising.md)) — Live-Temp ohne GATT
- [x] Encoding `/16` gegen Display 33 °C / +10 in Captures ([06-encoding.md](hci-logs/06-encoding.md)); Live 2026-09-03: Temp = Display, Hum ±3 %
- [x] Parser + ADV-CLI + GATT-Probe im Code ([07-read.md](hci-logs/07-read.md))
- [x] Collector-Skript im Code (`collect.py` ADV→CSV, [08-collect.md](hci-logs/08-collect.md))
- [x] Live-ADV am Büro-Gerät (`scan_live.py`, Display = Roh 25,125 °C)
- [x] Lokales Dashboard (CSV + HCI-Beleg, [09-dashboard.md](hci-logs/09-dashboard.md))
- [ ] Live-CSV `collect.py` am Büro-Gerät
- [ ] History-Dump Büro (GATT `07`, alle Pages) — TODO Phase 6
- [ ] Geräteliste 5 Räume + Live/History je MAC — TODO Phase 7
- [ ] SQLite/JSONL falls 5 Geräte × History unhandlich — Rest Phase 8
- [ ] `0x18` / `0x04` gegen Kalibrier-Test zuordnen (nicht senden, bis bewusst getestet)
