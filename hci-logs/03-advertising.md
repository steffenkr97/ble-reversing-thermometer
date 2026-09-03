# Advertising / Manufacturer Data

**Gerät:** `f4:db:00:00:00:d9`  
**Beleg:** LE Advertising Reports in allen `.cfa` außer `old/hci_snoop_2018_01_01_12_06_14.cfa`  
**Rohdump:** [extract/adv.csv](extract/adv.csv) (Zielgerät: Spalte `target=yes`)

Öffentliche Decoder (Theengs, aioblescan) dienen nur zum Vergleich. Unten steht, was **in unseren Bytes** hängt.

## Kurzantwort

Ja: Live-Temperatur und Luftfeuchtigkeit stehen in ADV_IND, **ohne GATT-Connection**. SCAN_RSP enthält den Namen, keine Messwerte.

Dieselben Rohwerte wie die älteste History-Page (`0x017B` / `0x03BC`) stehen **nicht** in ADV — ADV ist der aktuelle Wert, History-Index 0 ist alt. Live-ADV um 14:52 liegt bei ~22,1 °C, passend zu Display 33 °C minus Offset +10.

Zwei ADV_IND-Nutzlasten: 20 Byte (Live) und 22 Byte (Min/Max seit Power-On).

## AD-Strukturen (Fakt)

### ADV_IND (connectable, Event 0x00)

Beispiel `14_52_30` rec mit RSSI −37:

| AD-Typ | Name | Wert |
|--------|------|------|
| `01` | Flags | `06` (LE General Discoverable, BR/EDR nicht unterstützt) |
| `02` | Incomplete UUID 16 | `F0 FF` = UUID **`FFF0`** |
| `FF` | Manufacturer Specific | 20 oder 22 Byte, siehe unten |

### SCAN_RSP (Event 0x04)

Einziges Zielgerät-SCAN_RSP (alle Captures identisch):

```
0D 09 54 68 65 72 6D 6F 42 65 61 63 6F 6E 05 12 18 00 38 01 02 0A 00
```

| AD-Typ | Name | Wert |
|--------|------|------|
| `09` | Complete Local Name | `ThermoBeacon` |
| `12` | Slave Connection Interval Range | `18 00 38 01` → 30–390 ms (× 1,25 ms) |
| `0A` | Tx Power | `00` |

Keine Temperatur in SCAN_RSP.

## Manufacturer Data — Live, 20 Byte (Hypothese, intern konsistent)

Company-ID ist **`0x001B`** (Bytes `1B 00`), nicht `0x0010` wie in manchen öffentlichen Beispielen. `0x0010` taucht bei uns als **Config-Wort** danach auf.

Beleg `14_52_30`, ADV_IND:

```
1B 00 10 00 D9 00 00 00 DB F4 B5 0B 61 01 0F 04 4B 7D 0E 00
```

| Offset | Länge | Byte-Order | Feld | Beispiel | Skala | Beleg |
|--------|------:|------------|------|----------|-------|-------|
| 0 | 2 | LE | Company-ID | `1B 00` = `0x001B` | — | alle ADV_IND des Ziels |
| 2 | 2 | LE | Config / Flags | `10 00`, später `5E 00`, `70 00`, `FC 00`; Bit7 von Byte 3 oft `80` | unbekannt | wechselt nach `0x18`-Write |
| 4 | 6 | LE | MAC | `D9 00 00 00 DB F4` | = `f4:db:00:00:00:d9` | Fakt |
| 10 | 2 | LE uint16 | Batterie | `B5 0B` = 2997 | **mV** (Hypothese, typisch ~3,0 V) | alle 20-Byte-Frames |
| 12 | 2 | LE int16 | Temperatur | `61 01` = 353 | **/ 16 → 22,0625 °C** | `14_52_30`; Display 33 bei +10 |
| 14 | 2 | LE int16 | Luftfeuchtigkeit | `0F 04` = 1039 | **/ 16 → 64,9375 %** | dieselbe Frame; Display-% nicht notiert |
| 16 | 4 | LE uint32 | Counter | `4B 7D 0E 00` = 949579 | +1 je Frame, Sekunden seit Power-On? | steigt monoton in einer Session |

`10 80` statt `10 00`: dasselbe Layout, nur Bit 7 in Byte 3 gesetzt. Bedeutung offen.

Abgleich GATT: erste History-Page hat `7B 01` = 23,6875 °C (alt). ADV zur Scan-Zeit `61 01` = 22,0625 °C (aktuell). Gegen Ende von `15_14_35` steigt ADV auf `7B 01` / `7F 01` / `80 01` (23,7–24,0 °C) — gleiche `/16`-Skala wie History.

## Manufacturer Data — Min/Max, 22 Byte (Hypothese)

Beispiel `14_52_30`:

```
1B 00 10 00 D9 00 00 00 DB F4 A7 01 5F 0F 00 00 2A 01 7E 0C 04 00
```

| Offset | Länge | Feld | Beispiel | Lesart |
|--------|------:|------|----------|--------|
| 0–9 | 10 | wie Live | Company, Config, MAC | Fakt (MAC) |
| 10 | 2 | Max-Temp | `A7 01` = 423 / 16 = **26,4375 °C** | Hypothese |
| 12 | 4 | Max-Zeit | `5F 0F 00 00` = 3935 | Sekunden seit Power-On? |
| 16 | 2 | Min-Temp | `2A 01` = 298 / 16 = **18,625 °C** | Hypothese |
| 18 | 4 | Min-Zeit | `7E 0C 04 00` = 265342 | Sekunden seit Power-On? |

Min/Max-Werte sind über die Nov-26-Captures **konstant** (nicht die Live-Temp). Passt zu „seit Einschalten“, nicht zu „letzte Minute“.

Öffentliches 20-Byte-Min/Max-Layout (aioblescan, ohne unser Config-Wort) ist dasselbe Muster ab Offset 10, sobald Company+Config+MAC abgezogen sind.

## Config-Wort und Befehl `0x18`

| Session | Config-Bytes (Offset 2–3) | Bemerkung |
|---------|---------------------------|-----------|
| `14_52_30` / `14_52_44` / `15_00_04` | `10 00` / `10 80` | vor den Extra-Cmds |
| `15_14_35` nach Write `18 E7 03 5E` | `5E 00` | letztes Write-Byte taucht in ADV auf |
| `15_14_35` nach Write `18 00 00 70` | `70 00` | ebenso |
| `old/12_06_26`, Anfang `07_45_17` | `FC 00` / `FC 80` | ältere Sessions |
| `old/07_45_17` später | `10 00` | nach `18 01 00 10`? |
| Live 2026-09-03 `scan_live.py` | `00 80` | Display = Roh 25,125 °C, kein +10. Nicht als `0x18`-Effekt verkaufen |

**Hypothese:** `0x18 xx xx YY` schreibt das ADV-Config-Byte `YY`. Kein Beleg, dass `YY` der Display-Offset +10 ist (`0x0A` kommt nicht vor). Nicht nachbauen.

## Vergleich öffentliche Decoder

| Öffentlich | Dieses Gerät |
|------------|----------------|
| UUID `FFF0` | Fakt, Incomplete UUID |
| Company `0x0010` | bei uns Company **`0x001B`**, `0x0010` ist Config |
| Temp/Hum `/16`, Batterie mV, Counter, MAC im Payload | passt ab Offset 4 der 20-Byte-Payload |
| 18- vs 20-Byte-Payload nach Company | bei uns 18 Byte nach Company = Config(2)+MAC+Sensor; plus 22-Byte-Min/Max |

## Collector-Hinweis

Live-Werte ohne Connect sind in ADV_IND lesbar (`int16le / 16` an Offset 12/14). History bleibt GATT `07`. Filter MAC, nicht den Gerätenamen. Encoding: [06-encoding.md](06-encoding.md).
