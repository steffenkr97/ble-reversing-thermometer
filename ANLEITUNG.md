# Live am Büro-Gerät — Befehle und Auslesen

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

## Noch nicht

GATT und Extra-Cmds erst, wenn Scan + CSV stimmen:

```
python collector/read_thermometer_data.py --address f4:db:00:00:00:d9
```

Nicht senden: `04` / `05` / `18` / `19` / `0F` / `F3`.
