# Büro-Gerät — Live, History-Dump und Dashboard

Gerät: `f4:db:00:00:00:d9` (Windows: diese MAC).  
Hersteller-App währenddessen **nicht** verbunden. Bluetooth am PC an.

Früherer Kalibrier-Test (Captures Nov 2025): Display **33 °C** = Offset **+10** → Rohwert ~23 °C.

Live 2026-09-03: Display **= Roh** (`temp_c=25.125` genau die Anzeige). Hum ungefähr **±3 %**. Offset +10 gilt gerade **nicht**.

---

## 0. Einmal: venv

Im Repo-Ordner, PowerShell:

```
python -m venv .venv
```

```
.\.venv\Scripts\Activate.ps1
```

Falls Activate blockiert:

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```
.\.venv\Scripts\Activate.ps1
```

Prompt muss `(.venv)` zeigen, dann:

```
python -m pip install -U pip
```

```
pip install -r requirements.txt
```

```
python collector/scan_live.py --help
```

`--help` muss die Flags zeigen, nicht `No module named 'bleak'`.  
`.venv` nicht committen.

History aus den Captures (Schritt 6) braucht **kein** bleak:

```
python collector/dump_history.py --help
```

---

## 1. Display notieren (vor dem ersten Scan)

Aufschreiben:

- angezeigte °C
- angezeigte %rF (falls vorhanden)
- ob Offset noch +10 ist (am 2026-09-03: nein, Display = Roh)

---

## 2. Ein Scan, kein CSV

```
python collector/scan_live.py --timeout 15
```

Kein Treffer? Dann:

```
python collector/scan_live.py --timeout 30
```

### Ausgabe lesen

**Treffer** (Exit 0), eine Zeile z. B.:

```
temp_c=25.125 humidity_rh=62.0625 battery_mv=2617 counter=2025968 mac=f4:db:00:00:00:d9 raw_hex=1b000080d9000000dbf4390a9201e103f0e91e00
```

(Live 2026-09-03, Display war genau 25,125 °C.)

| Feld | Soll |
|------|------|
| `mac` | **genau** `f4:db:00:00:00:d9` — sonst falsches Gerät |
| `temp_c` | Roh `/16`. **Jetzt:** gleich der Anzeige. Nur bei Kalibrier-Offset +10: Display minus 10 |
| `humidity_rh` | `/16`, oft 0–100. Live ±3 % zur Anzeige, nicht exakt |
| `battery_mv` | nur stdout, nicht in der CSV. Live 2617; Capture ~3000 |
| `counter` | steigt zwischen Scans, Gerätezähler |
| `raw_hex` | 20-Byte-Frame, zur Kontrolle behalten |

**Timeout** (Exit 1):

```
Kein Live-Sample innerhalb von 15 s (Ziel-MAC f4:db:00:00:00:d9).
```

Dann: Gerät näher, Bluetooth neu, App zu, Timeout 30. Unter Windows fehlt Manufacturer Data manchmal im Scan — dann kommt Timeout, obwohl das Gerät „da“ ist.

---

Scan 2026-09-03 ist durch (MAC, Temp, Hum passen). Als Nächstes CSV:

## 3. Ein Sample in CSV

```
python collector/collect.py
```

### Ausgabe lesen

Zwei Zeilen bei Treffer:

```
temp_c=… humidity_rh=… battery_mv=… counter=… mac=f4:db:00:00:00:d9 raw_hex=…
geschrieben: data/thermo_f4db000000d9_YYYY-MM-DD.csv
```

Datei öffnen. Eine Datenzeile, Spalten:

| Spalte | Bedeutung |
|--------|-----------|
| `timestamp` | Sammelzeit UTC (`…Z`), nicht Geräteuhr |
| `mac` | wieder `f4:db:00:00:00:d9` |
| `temp_c` | wie oben, `/16` |
| `humidity_rh` | wie oben, `/16` |
| `raw_hex` | derselbe Frame wie auf stdout |

CSV-Dateien unter `data/` sind gitignored.

Timeout: dieselbe Meldung wie beim Scan, Exit 1, **keine** Messzeile.

---

## 4. Optional: alle 60 s sammeln

```
python collector/collect.py --interval 60
```

Strg+C beendet (Exit 0).  
Timeout im Loop: nur Meldung auf stderr, Skript läuft weiter.

---

## 5. Dashboard (lokal, kein BLE)

Kein venv/bleak nötig. Im Repo-Ordner:

```
python dashboard/server.py
```

Browser: `http://127.0.0.1:8765/`

Ohne Live-CSV und ohne History-CSV zeigt die Seite die HCI-Belege vom Büro (Capture-ADV und History-Capture `07`). Nach Schritt 3 erscheint **Live-CSV (ADV)** zuerst. Nach Schritt 6 erscheint der Tab **History-CSV**. Allowlist: `dashboard/rooms.json`. Nicht senden, kein GATT.

Details: [hci-logs/09-dashboard.md](hci-logs/09-dashboard.md).

---

## 6. History aus den Captures (kein BLE)

Die Geräte speichern den Verlauf intern (Hersteller: bis ~100 Tage; in den Nov-2025-Captures **1586 Samples**, ≈ 11 Tage bei 10-min-Hypothese). Das schreibt die App per GATT `07` raus. Ohne Gerät geht derselbe Dump aus den HCI-Logs:

Kein venv/bleak nötig:

```
python collector/dump_history.py --help
```

```
python collector/dump_history.py --from-extract hci-logs/extract
```

### Ausgabe lesen

Zwei Blöcke bei Treffer:

```
Extract hci_snoop_2025_11_26_15_14_35.cfa  pages=530  samples=1586  count_01=1586  newest_index=1585
geschrieben: data/history_f4db000000d9.csv
timestamp_inferred: Anker 2025-11-26T15:19:35Z  interval=600.0 s (Hypothese)
```

| Feld | Soll |
|------|------|
| Datei | längster Nicht-`old`-Dump, hier `15_14_35` |
| `pages` / `samples` | 530 Pages → **1586** Zeilen |
| `count_01` | Antwort auf Write `01` in derselben Capture (History-Länge) |
| Datei auf Disk | `data/history_f4db000000d9.csv` (gitignored, Dump **ersetzt** die Datei) |

Datei öffnen. Header plus 1586 Datenzeilen. Erste und letzte Zeile zur Kontrolle:

| Spalte | Bedeutung |
|--------|-----------|
| `mac` | `f4:db:00:00:00:d9` |
| `index` | 0 = **älteste**, letzte Zeile = neueste. Nicht die Dump-Uhr. |
| `record` | 0..2 in der Page (`count=01` nur 0) |
| `temp_c` | `/16`. Index 0: **24,0625**. Index 1584: **22,9375** (Hum an Offset 8) |
| `humidity_rh` | `/16`. Index 0: **59,25**. Index 1584: **62,5** |
| `raw_hex` | 20-Byte-Notify `07`, ohne Leerzeichen |
| `timestamp_inferred` | **Hypothese 10 min** (ADV-Counter/Count ≈ 600 s), keine Geräte-Wanduhr. Index 0 ≈ 15.11.2025, neueste ≈ Capture-Ende 26.11.2025 15:19Z |

Keine Zeilen / Exit 1: Extract-Pfad prüfen (`hci-logs/extract/att_fff5_fff3.csv` muss existieren).

Optional:

```
python collector/dump_history.py --from-extract hci-logs/extract --no-timestamps
python collector/dump_history.py --from-extract hci-logs/extract --output PATH
```

Protokoll und Intervall: [hci-logs/10-history-dump.md](hci-logs/10-history-dump.md).

Dashboard neu laden (Schritt 5). Tab **History-CSV (1586)**. X-Achse ist die abgeleitete Zeit, nicht der Index. Quelle **History-Capture (07)** bleibt der HCI-Beleg (Index, Dump-Zeit).

---

## 7. History vom Gerät (GATT)

Hersteller-App **nicht** verbunden. venv wie in Schritt 0 (`bleak` muss da sein). Linux setzt CCCD zuverlässiger als macOS.

```
python collector/dump_history.py --address f4:db:00:00:00:d9
```

Ohne MAC, Ziel nur über System ID `D9 00 00 00 00 00 DB F4`:

```
python collector/dump_history.py --use-system-id
```

### Was passiert

Dieselbe Sequenz wie die App, sonst nichts:

1. Connect, System ID prüfen
2. Notify an (CCCD `01 00`)
3. Write `1A` → Status
4. Write `01` → Sample-Count
5. Wiederholt Write `07 <index> 00 00 <count>` — `count` 03, letzte Pages ggf. 01

528 Pages à 3 Samples dauern grob **1–2 Minuten** (Capture-Median ~0,16 s je Page). Fortschritt alle 25 Pages auf stdout.

### Ausgabe lesen

```
Sequenz 1A → 01 → 07-Pages
  Status 1A  raw=…
  Count 01   samples=1586  pages=530  (~106 s bei 0,2 s/Page)
  Page 1/530  index=0  count=3  records=3
  …
fertig: 1586 Samples aus 530 Pages in … s
geschrieben: data/history_f4db000000d9.csv
```

`samples` kommt vom Gerät (`01`), nicht aus einer Schätzung. CSV-Spalten wie in Schritt 6. `timestamp_inferred`: neuestes Sample ≈ jetzt, ältere um 10 min (Hypothese).

Neueste Page grob gegen ein Live-ADV (Schritt 2) halten: Temp `/16` sollte in der Nähe der Anzeige liegen (kein +10, Stand 2026-09-03). Index 0 ist alt, nicht Live.

**Timeout auf 1A/01:** Gerät näher, App zu, `--notify-timeout 3`. Falsche System ID → Abbruch (kein Erstes-Gerät-Fallback).

Nur die ersten Pages (Test):

```
python collector/dump_history.py --address f4:db:00:00:00:d9 --max-pages 2
```

Eine einzelne Page ohne CSV: Schritt 8.

Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`. Kein 1-Byte-`07`.

---

## 8. Optional: eine Page probehalber

Nur Count oder eine History-Page, keine CSV:

```
python collector/read_thermometer_data.py --address f4:db:00:00:00:d9
python collector/read_thermometer_data.py --address f4:db:00:00:00:d9 --history 0
```

`--history 0` = älteste Page (`count=03`). Volle History bleibt `dump_history.py`.

Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`.
