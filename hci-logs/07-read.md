# Phase 3 — Parser, ADV-Scan, GATT-Probe

**Gerät:** `f4:db:00:00:00:d9`  
**Encoding-Beleg:** [03-advertising.md](03-advertising.md), [06-encoding.md](06-encoding.md)  
**Code:** `collector/thermo_parse.py`, `collector/scan_live.py`, `collector/read_thermometer_data.py`  
**Tests:** `collector/test_thermo_parse.py` (11 Tests, Unittest)

Phase-3-Code ist im Repo. ADV-Live am Büro-Gerät: [unten](#live-ergebnis). GATT-Probe und Collector-CSV noch offen.

## Abhängigkeit

`requirements.txt`: `bleak>=0.21.0`.

Beide CLIs importieren `bleak` **oben**. Ohne das Paket scheitert schon `--help`:

```
ModuleNotFoundError: No module named 'bleak'
```

`thermo_parse` braucht kein bleak. Syntax: `python -m py_compile collector/scan_live.py collector/read_thermometer_data.py collector/thermo_parse.py` ist ok.

## CLI

### ADV-Scan (kein Connect)

```
python collector/scan_live.py
python collector/scan_live.py --timeout 15
python collector/scan_live.py --address f4:db:00:00:00:d9
```

| Flag | Bedeutung |
|------|-----------|
| `--timeout SEK` | Scan-Timeout, Standard 15 |
| `--address ADDR` | zusätzlich `device.address` (Linux/Windows: MAC, macOS: UUID). Die MAC **im Manufacturer-Payload** bleibt Pflicht (`TARGET_MAC`). |

Nur Advertising. Manufacturer 20 Byte: bleak liefert oft 18 Byte nach Company-ID `0x001B`, manchmal schon 20 Byte inkl. `1B 00`. `assemble_mfg_frame` baut daraus den 20-Byte-Frame, dann `parse_adv_manufacturer`. Erstes gültiges Sample auf stdout, Exit 0.

Filter ist die Payload-MAC, nicht der Gerätename. 22-Byte-Min/Max und fremde MAC → kein Treffer.

### GATT-Probe

```
python collector/read_thermometer_data.py --address f4:db:00:00:00:d9
python collector/read_thermometer_data.py --use-system-id
python collector/read_thermometer_data.py --address f4:db:00:00:00:d9 --history 0
python collector/read_thermometer_data.py --debug-only --address f4:db:00:00:00:d9
```

| Flag | Bedeutung |
|------|-----------|
| `--address` / `-a` | BLE-Adresse. Linux/Windows: MAC; macOS: CoreBluetooth-UUID |
| `--use-system-id` | Scan nach Kandidaten, Ziel nur wenn `2A23 == TARGET_SYSTEM_ID`. Ohne `--address` immer aktiv. |
| `--history INDEX` | genau eine Page: Write `07 <index:u16le> 00 00 03` |
| `--debug-only` | nur Services listen, keine FFF5-Writes. Unverträglich mit `--history`. |

Kein `--kick`, kein Fallback auf das erstbeste ThermoBeacon, kein `/100`-Raten.

Ablauf (nicht `--debug-only`):

1. Connect, System-ID prüfen (`D9 00 00 00 00 00 DB F4`)
2. `start_notify(FFF3)` plus CCCD `2902` = `01 00`
3. Write FFF5 `1A` → Notify parsen
4. Write FFF5 `01` → Notify parsen (Sample-Count, kein Live-°C)
5. optional eine History-Page (`--history`)

`--history` schickt immer `count=03`. Eine Rest-Page mit `count=01` ist im Parser, nicht als CLI-Flag.

## Parser-API (`thermo_parse`)

Kein BLE. Skala fest `int16le / 16` (`SCALE = 16.0`).

Konstanten: `TARGET_MAC`, `TARGET_SYSTEM_ID`, `COMPANY_ID` (`0x001B`), UUIDs `FFE0` / `FFF5` / `FFF3` / `2A23`.

| Dataclass | Felder | Quelle |
|-----------|--------|--------|
| `AdvLive` | `temp_c`, `humidity_rh`, `battery_mv`, `counter`, `mac`, `raw_hex` | 20-Byte ADV |
| `Status1A` | `raw_hex` | Notify `1A` — kein Messwert |
| `Count01` | `sample_count`, `raw_hex` | Notify `01` — kein Live-°C |
| `History07` | `index`, `count`, `records` (`[(temp, hum), …]`), `raw_hex` | Notify `07` |

| Funktion | Input | Output |
|----------|-------|--------|
| `i16le_div16(data, offset)` | Rohbytes + Offset | `int16le / 16` |
| `parse_adv_manufacturer(mfg)` | 20 Byte inkl. Company | `AdvLive` oder `None` |
| `parse_fff3(data)` | 20-Byte-Notify | `Status1A` / `Count01` / `History07` oder `None` |
| `build_history_07_write(index, count=3)` | Index, Count | 6 Byte `07 <u16le> 00 00 <count>` |

`parse_adv_manufacturer` → `None` bei Länge ≠ 20 (also 22-Byte-Min/Max), Company ≠ `0x001B`, oder MAC ≠ Ziel.

`parse_fff3` → `None` bei Länge ≠ 20, Opcode `0xF3`, unbekanntem Opcode, oder `07` mit `count` weder 1 noch 3. Form-B-Records hinter Opcode `01` werden **nicht** als Live gelesen — nur `sample_count` (LE uint16, Offset 1).

`07` mit `count=03`: Temp Offset 6/8/10, Hum 12/14/16. Mit `count=01`: nur ein Paar, Temp Offset 6, Hum Offset 8.

## Goldvektoren (Unittest)

Dieselben Bytes wie in [03-advertising.md](03-advertising.md) / [05-history-07.md](05-history-07.md) / [06-encoding.md](06-encoding.md).

### ADV rec 171 (`14_52_30`)

```
1B 00 10 00 D9 00 00 00 DB F4 B5 0B 61 01 0F 04 4B 7D 0E 00
```

→ `temp_c=22.0625`, `humidity_rh=64.9375`, `battery_mv=2997`, `counter=949579`, `mac=f4:db:00:00:00:d9`

22-Byte-Min/Max `1B001000D9000000DBF4A7015F0F00002A017E0C0400` → `None`. Fremde MAC im sonst gleichen Frame → `None`.

### History `07` count 03, Index 0

```
07 00 00 00 00 03 81 01 7B 01 79 01 B4 03 BC 03 CB 03 00 00
```

→ Records `(24.0625, 59.25)`, `(23.6875, 59.75)`, `(23.5625, 60.6875)`

Write: `build_history_07_write(0, 3)` = `07 00 00 00 00 03`. Index `0x011D`: `07 1D 01 00 00 03`.

### History `07` count 01, Index 1584

```
07 30 06 00 00 01 6F 01 E8 03 6E 01 0E 04 0F 04 F2 03 00 00
```

→ ein Record `(22.9375, 62.5)` — Hum an Offset 8, nicht 12.

Write: `build_history_07_write(1584, 1)` = `07 30 06 00 00 01`.

### Status `1A`

```
1A 01 00 01 00 + 15× 00
```

→ `Status1A` (kein °C/%rF).

### Count `01` Form A

```
01 2F 06 00 + 16× 00
```

→ `sample_count=1583` (`0x062F`).

Opcode `F3` (20 Byte) → `None`. Nicht nachbauen.

## Blacklist (keine Writes)

Nicht senden — App-Traffic bzw. nur Fuzzer, Bedeutung offen oder Settings/History:

`04` / `05` / `18` / `19` / `0F` / `F3`

Die CLIs schreiben nur `1A`, `01` und optional `07`. Details: [04-opcodes.md](04-opcodes.md).

## Live-Ergebnis

**ADV-Scan gelaufen** (Windows, `(.venv)`, 2026-09-03):

```
python collector/scan_live.py --timeout 15
```

```
temp_c=25.125 humidity_rh=62.0625 battery_mv=2617 counter=2025968 mac=f4:db:00:00:00:d9 raw_hex=1b000080d9000000dbf4390a9201e103f0e91e00
```

| Feld | Live | Display | Lesart |
|------|------|---------|--------|
| MAC | `f4:db:00:00:00:d9` | — | richtiges Gerät |
| Temp `92 01` = 402 `/16` | **25,125 °C** | **genau 25,125** (Anzeige) | `/16` = Display, **kein +10** |
| Hum `e1 03` = 993 `/16` | 62,0625 % | ungefähr gleich, **±3 %** | `/16` Display-nah, nicht exakt |
| Config Offset 2–3 | `00 80` | — | anders als Capture `10 00`; nicht als Kalibrier-Fakt |
| Batterie `39 0a` | 2617 mV | — | weiter Hypothese mV |

Nov-2025-Captures: Display 33 °C bei Offset **+10** (Roh ~22 °C). Am 2026-09-03 zeigt das Display den Rohwert. Offset ist also ein Gerätezustand, nicht fest im Encoding. `0x18`/`0x04` nicht zuordnen, nicht senden.

GATT-Probe und `collect.py`→CSV: noch nicht gelaufen. Encoding: [06-encoding.md](06-encoding.md).
