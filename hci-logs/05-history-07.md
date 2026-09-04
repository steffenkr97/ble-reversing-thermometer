# History-Frame `0x07`

**Gerät:** `f4:db:00:00:00:d9`  
**Beleg:** 1800 Notifications à 20 Byte in den GATT-Captures; erste Page `14_52_44`

## Write (Fakt)

Immer 6 Byte:

```
07 | index:u16le | 00 00 | count
```

| Offset | Länge | Inhalt |
|--------|------:|--------|
| 0 | 1 | Opcode `07` |
| 1 | 2 | Index, little-endian (0, 3, 6, …) |
| 3 | 2 | immer `00 00` |
| 5 | 1 | Anzahl Records: fast immer `03`, am Ende `01` wenn Count nicht durch 3 teilbar |

Beispiel Index 0: `07 00 00 00 00 03`  
Beispiel Index 3: `07 03 00 00 00 03`  
Beispiel Index 285 (`0x011D`): `07 1D 01 00 00 03`  
Beispiel Rest-Page (`15_14_35` rec 2967): `07 30 06 00 00 01` (Index 1584, 1 Record)

Index steigt in **+3**, passend zu `count=03`. 167 Frames mit Schritt 0 = neuer Dump ab Index 0 (Reconnect). Schritt **+1** = `count=01` (letzte Pages in `15_14_35` und `old/07_45_17`). Details: [06-encoding.md](06-encoding.md).

## Notify (Fakt: Bytes; Hypothese: Skala)

Immer 20 Byte, Header = Echo des Writes:

```
07 | index:u16le | 00 00 | 03 | t0:i16le | t1 | t2 | h0:i16le | h1 | h2 | 00 00
```

| Offset | Länge | Feld | Byte-Order | Skala | Status |
|--------|------:|------|------------|-------|--------|
| 0 | 1 | Opcode | — | `07` | Fakt |
| 1 | 2 | Index | LE uint16 | — | Fakt |
| 3 | 2 | Padding | — | `00 00` | Fakt in diesen Captures |
| 5 | 1 | Count | — | `03` oder `01` | Fakt |
| 6 | 2 | Temp 0 | LE int16 | `/ 16` → °C | Hypothese |
| 8 | 2 | Temp 1 | LE int16 | `/ 16` | Hypothese |
| 10 | 2 | Temp 2 | LE int16 | `/ 16` | Hypothese |
| 12 | 2 | Humidity 0 | LE int16 | `/ 16` → %rF | Hypothese |
| 14 | 2 | Humidity 1 | LE int16 | `/ 16` | Hypothese |
| 16 | 2 | Humidity 2 | LE int16 | `/ 16` | Hypothese |
| 18 | 2 | Ende | — | immer `00 00` (1800/1800) | Fakt als Konstante; Checksum damit unwahrscheinlich |

### Erste Page — `14_52_44`

Notify:

```
07 00 00 00 00 03 81 01 7B 01 79 01 B4 03 BC 03 CB 03 00 00
```

| Record | Temp raw | Temp /16 | Hum raw | Hum /16 |
|--------|----------|----------|---------|---------|
| 0 | `0x0181` = 385 | 24,0625 °C | `0x03B4` = 948 | 59,25 % |
| 1 | `0x017B` = 379 | 23,6875 °C | `0x03BC` = 956 | 59,75 % |
| 2 | `0x0179` = 377 | 23,5625 °C | `0x03CB` = 971 | 60,6875 % |

Index 0 = **älteste** gespeicherte Samples, nicht Live. Live steht im Advertising ([03-advertising.md](03-advertising.md)).

Zweite Page (`index=3`): `74 01 67 01 5A 01` / `C0 03 CE 03 EF 03` → 23,25 / 22,44 / 21,625 °C.

Letzte Page dieser Session (`index=0x011D`): `5A 01 5C 01 5C 01` / `E6 03 DC 03 D9 03`.

## Sample-Count vs. Pages

Antwort auf `01`: Count als uint16 LE.

| Capture | Count | `07`-Pages | Records (3er + Rest) |
|---------|------:|-----------:|---------------------:|
| `14_52_44` | 1583 (`0x062F`) | 96×`03` | 288 (Teilmenge) |
| `15_00_04` | 1584 (`0x0630`) | 528×`03` | **1584** (vollständig) |
| `15_14_35` | 1585 → 1586 | 528×`03` + 2×`01` | **1586** |
| `old/12_06_26` | 615 (`0x0267`) | 372×`03` | 1116 (mehr als Count — Hypothese: Wrap oder anderer Modus) |
| `old/07_45_17` | 820 (`0x0334`) | 273×`03` + 1×`01` | **820** |

Count steigt über die Nov-26-Sessions: 1583 → 1584 → 1585 → 1586.

Bei `count=01` liegen Temp/Hum als **ein Paar** bei Offset 6 und 8 (nicht 6 und 12). Bytes 10–17 sind dann keine weiteren Records — `E8 03` als Temp wäre 62,5 °C.

## Skala `/16`

Intern konsistent mit Advertising. Display 33 °C / Offset +10: ADV-Live `/16` = 22,06 °C (erwartet ~23). **%rF nicht gegen eine notierte Anzeige geprüft**; `/10` für Hum ist ausgeschlossen (>100 % in den meisten ADV-Frames). Abgleich: [06-encoding.md](06-encoding.md).

Fuzzer-`0xF3` enthielt `7B 01` und `BC 03` — dieselben Rohwerte wie Record 1 der ersten History-Page, anderes Framing. Nicht in der App.

Dump aller Pages: [10-history-dump.md](10-history-dump.md). Intervall **10 min** ist Hypothese (ADV-Counter 949579 / Count 1583 ≈ 599,86 s), kein Fakt.
