# Phase 6 — History-Dump (GATT `07` / HCI-Extract)

**Gerät:** `f4:db:00:00:00:d9`  
**Code:** `collector/thermo_history.py`, `collector/dump_history.py`  
**Tests:** `python -m unittest discover -s collector -p "test_*.py"` (History-Tests in `test_thermo_history.py`, `test_dump_history.py`)  
**Framing:** [05-history-07.md](05-history-07.md), Encoding `/16`: [06-encoding.md](06-encoding.md)

Vollständigen Verlauf lokal speichern, wie die App: CCCD → Write `1A` → `01` (Sample-Count) → wiederholte `07`-Pages. Dashboard liest `data/history_<mac12>.csv` als Quelle `history`.

Live-GATT am Büro-Gerät ist **Code bereit**, in dieser Umgebung nicht gelaufen. Der vollständige Dump der Captures (1586 Samples) geht offline über `--from-extract`.

## CLI

Ohne bleak (nur Lesen der Extracts):

```
python collector/dump_history.py --from-extract hci-logs/extract
python collector/dump_history.py --from-extract hci-logs/extract --all-rooms
```

Am Gerät (venv, bleak):

```
python collector/dump_history.py --address f4:db:00:00:00:d9
python collector/dump_history.py --use-system-id
```

| Flag | Bedeutung |
|------|-----------|
| `--from-extract PATH` | `att_fff5_fff3.csv` oder Extract-Ordner. Kein BLE, keine Writes. Längster Dump des Ziel-MAC, `old/` übersprungen. |
| `--address` / `-a` | BLE-Adresse. Sequenz wie die App. Unverträglich mit `--from-extract`. |
| `--use-system-id` | Scan, Ziel nur bei `2A23 == TARGET_SYSTEM_ID`. Standard ohne `--address`/`--from-extract`. |
| `--mac` | MAC in der CSV (Standard Büro). Extract filtert `peer`. |
| `--rooms PATH` | Allowlist für `--all-rooms` und System-ID (Standard `dashboard/rooms.json`). |
| `--all-rooms` | je MAC in der Allowlist eine CSV. Unverträglich mit `--output`. Extract: MACs ohne `07` überspringen. |
| `--outdir` / `--output` | Standard `data/history_<mac12>.csv` (Dump **ersetzt** die Datei). |
| `--interval-sec` | Hypothese für `timestamp_inferred`, Standard **600** (10 min). |
| `--no-timestamps` | Spalte `timestamp_inferred` leer. |
| `--newest-time ISO` | Anker fürs neueste Sample. Sonst Capture-Ende bzw. Dump-Zeit. |
| `--max-pages N` | nur die ersten N Pages (Tests). |
| `--notify-timeout` | Standard 2 s je Notify (Capture `07` Median 157 ms, Max 449 ms). |
| `--retries` | Wiederholungen pro Page bei Timeout, Standard 2. |

`--all-rooms` schreibt je MAC in `rooms.json` eine History-CSV, sofern Pages existieren. In den Nov-2025-Captures nur Büro.

`--help` braucht kein bleak. Schritt-für-Schritt: [ANLEITUNG.md](../ANLEITUNG.md). Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`. `07`-Writes nur 6 Byte, `count` nur `01` oder `03` — nie `02`. GATT-System-ID nur gegen den Sollwert in `rooms.json` (Büro), nicht die Büro-`2A23` auf andere MACs.

## Ablauf Live (Fakt aus Captures)

1. Connect, System-ID prüfen (Büro: `D9 00 00 00 00 00 DB F4`; andere Allowlist-MACs: Sollwert aus `rooms.json` oder nur Adresse)
2. `start_notify(FFF3)` plus CCCD `2902` = `01 00`
3. Write FFF5 `1A` → Status
4. Write FFF5 `01` → `sample_count` als LE uint16
5. Für jedes `(index, count)` aus `page_plan(sample_count)`: Write `07 <u16le index> 00 00 <count>` → 20-Byte-Notify

`page_plan(1584)` = 528× `(0,3), (3,3), …, (1581,3)` — Capture `15_00_04`.  
`page_plan(1586)` = dasselbe plus `(1584,1)`, `(1585,1)` — Capture `15_14_35`.  
`page_plan(820)` = 273×`03` + `(819,1)` — `old/07_45_17`.

Index 0 = **älteste** Samples. Letzte Page ≈ Live/ADV derselben Session ([06-encoding.md](06-encoding.md): Index 1584 = ADV `6F 01` / `E8 03`).

## CSV

Spalten (`thermo_history.HISTORY_COLUMNS`):

| Spalte | Inhalt |
|--------|--------|
| `mac` | z. B. `f4:db:00:00:00:d9` |
| `index` | Sample-Index, 0 = älteste |
| `record` | 0..2 in der Page (`count=01` → nur 0) |
| `temp_c` | `int16le / 16` |
| `humidity_rh` | `int16le / 16` |
| `raw_hex` | 20-Byte-Notify, lowercase, ohne Leerzeichen |
| `timestamp_inferred` | optional, siehe unten |

Eine Zeile = ein Sample. `--from-extract hci-logs/extract` schreibt **1586** Zeilen aus `hci_snoop_2025_11_26_15_14_35.cfa` (längster Nicht-`old`-Dump; `count_01` = 1586). Goldvektor Index 0: 24,0625 °C / 59,25 %. Index 1584: 22,9375 °C / 62,5 % (`count=01`, Hum Offset 8).

## Intervall — Hypothese 10 min, nicht Fakt

History-Frames enthalten **keine Wanduhr**. ADV-Counter (Offset 16, Hypothese: Sekunden) und Sample-Count in derselben Session:

| Beleg | Wert |
|-------|------|
| ADV rec 171 (`14_52_30`) Counter | 949579 |
| Count `01` in `14_52_44` | 1583 |
| 949579 / 1583 | **599,86 s** ≈ 600 s |

Count stieg am 26. Nov 2025: 1583 (`14:53`) → 1584 (`15:00`, ~7 min) → 1585/1586 (`15:14`, ~14 min). Passt zu einem 10-Minuten-Takt, belegt ihn nicht allein.

Hersteller „bis 100 Tage“: bei 10 min wären das 14400 Samples (`uint16` reicht). In den Captures maximal **1586** ≈ 11 Tage. Kapazität 100 Tage ist **nicht** aus den HCI-Logs belegt.

`timestamp_inferred`: neuestes Sample ≈ Dump-/Capture-Zeit, ältere `index` um `interval_sec` zurück. Anker ist **Count−1**, nicht die letzte Zeile eines Teildumps ab Index 0.

## Extract-Wahl

`--from-extract` merged **nicht** über Sessions (Count steigt, erste Pages wären sonst aus einem älteren Dump). Es gewinnt die Capture-Datei mit den meisten Unique-Samples, `old/` aus (2018-Zeitstempel). Dashboard-Quelle `history_capture` bleibt der Merge „erstes Vorkommen“ — das ist der HCI-Beleg, nicht der Dump.

## Dashboard

`python dashboard/server.py` — Tab **History-CSV**, sobald `data/history_*.csv` existiert. Mit `timestamp_inferred` ist die X-Achse die abgeleitete Zeit; ohne bleibt der Index. Quelle `history_capture` nutzt weiter den Index (Capture-Zeit = Dump-Zeit).

## Nicht

- `0x18` / `0x04` / `0x05` / `0x19` / `0x0F` / `0xF3`
- 1-Byte-`07` wie der Fuzzer
- `count=02`
- fremde MACs
- Intervall 10 min als Fakt ohne zweiten Live-Zeitpunkt
