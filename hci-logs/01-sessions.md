# Sessions — HCI-Captures

**Gerät:** `f4:db:00:00:00:d9` (System ID `D9 00 00 00 00 00 DB F4`)  
**Quelle der Auswertung:** `collector/parse_btsnoop.py` über alle `hci-logs/**/*.cfa`  
**Roh-Dumps:** [extract/summary.csv](extract/summary.csv)

## Fakt

Alle `.cfa` sind Android-**btsnoop** (Magic `btsnoop\0`, Datalink **1002**, HCI UART H4), aufgenommen auf einem **OnePlus 5T** (ASCII-String in jeder Datei). Die Endung `.cfa` ist irreführend — der Inhalt ist kein Frontline-Format.

nRF-Connect-Textlogs unter `research-device/` enthalten **keine** ATT-Nutzdaten. Sie ersetzen diese Captures nicht.

## Display / Kalibrierung

Aus [../hci-logs-notes.md](../hci-logs-notes.md): Display während eines Kalibrier-Tests (Nov 2025) auf **33 °C** gesetzt = Offset **+10**. Rohwert sollte dann ~23 °C sein. **%rF war in den Captures nicht notiert.**

Live 2026-09-03 (`scan_live.py`): Display **= Roh `/16`** (25,125 °C), Hum ±3 %. Der +10-Offset ist also ein Gerätezustand, nicht Teil der Skala. [07-read.md](07-read.md).

Welche Capture-Datei genau der Kalibrier-Klick ist, steht nicht in den Notizen. Zeitlich und inhaltlich passt `hci_snoop_2025_11_26_15_14_35.cfa` (Befehle `0x04` / `0x18`, danach ändert sich ein Feld in der Advertising-Payload). Zuordnung bleibt **Hypothese**. Nicht nachbauen.

## Dateien

| Datei | Größe | HCI-Records | Rolle | Zielgerät verbunden | App-Aktion (Lesart) |
|-------|------:|------------:|-------|---------------------|---------------------|
| `hci_snoop_2025_11_26_14_52_30.cfa` | 19 960 | 255 | Scan | nein | Nur Advertising, kein GATT |
| `hci_snoop_2025_11_26_14_52_44.cfa` | 66 531 | 1182 | **Startdatei** | 2× | Connect, Status `1A`, History-Länge `01`, 96× `07` |
| `hci_snoop_2025_11_26_15_00_04.cfa` | 146 578 | 2948 | langer Dump | 2× | wie oben, 528× `07` (volle History zur damaligen Länge) |
| `hci_snoop_2025_11_26_15_14_35.cfa` | 193 832 | 3712 | History + Extra | 6× CCCD | History plus `04` / `18` (Kalibrierung?) |
| `old/hci_snoop_2018_01_01_12_06_14.cfa` | 19 788 | 293 | unklar | nein | Timestamp-Jahr 2018 (Geräteuhr?). Kein ATT, kein ADV des Ziels |
| `old/hci_snoop_2018_01_01_12_06_26.cfa` | 380 810 | 4640 | ältere Sync | 2× | `1A` / `01` / 372× `07`; Uhr 2018-01-01 |
| `old/hci_snoop_2025_11_21_07_45_17.cfa` | 98 906 | 1873 | Extra-Cmds | 2× | `18` `19` `05` `0F` dann `01` und History; später `1A` |

Handles in jeder GATT-Session mit Discovery: FFF5 Value **0x0021**, FFF3 Value **0x0024**, CCCD **0x0025**. Details: [02-att-sequenz.md](02-att-sequenz.md). Encoding: [06-encoding.md](06-encoding.md).

## Andere ThermoBeacons in den Scans

Nicht das Büro-Gerät — nicht als Quelle für Encoding verwenden:

| MAC | Name |
|-----|------|
| `f4:d0:00:00:02:1a` | ThermoBeacon |
| `f4:db:00:00:02:37` | ThermoBeacon |
| `f4:db:00:00:02:42` | ThermoBeacon |
| `62:53:00:00:0f:1f` | ThermoBeacon |

Zusätzlich Hue-Lampen und unbenannte BLE-Geräte. Filter immer auf `f4:db:00:00:00:d9`.

## Parser

```text
python collector/parse_btsnoop.py --summary --export hci-logs/extract
```

Skript liest nur Dateien, schreibt nicht aufs Gerät, ändert keine `.cfa`.
