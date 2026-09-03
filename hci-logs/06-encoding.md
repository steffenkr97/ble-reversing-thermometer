# Encoding — FFF5/FFF3-Paare und Skala

**Gerät:** `f4:db:00:00:00:d9`  
**Beleg:** Paarung aller App-Writes in den GATT-Captures; Rohdump [extract/pairs.csv](extract/pairs.csv)  
**Display Captures (Nov 2025):** 33 °C = Offset **+10** (Roh ~23 °C). **%rF war nicht notiert.**  
**Display Live (2026-09-03, Windows `scan_live.py`):** Roh `/16` = **25,125 °C = Anzeige**. Hum `/16` ≈ Anzeige **±3 %**. Details: [07-read.md](07-read.md).

Phase-2-Ergebnis: ein reproduzierbarer Live-Pfad (ADV_IND, ohne GATT) und ein reproduzierbarer History-Pfad (GATT `07`). Temperatur `/16` ist gegen das Live-Display belegt (ohne Offset). Luftfeuchtigkeit `/16` bleibt intern die einzige Skala in 0–100 % und ist live Display-nah (±3 %), nicht pixelgenau.

## Kurz: was der Collector nehmen darf

| Quelle | Befehl | Temp / Hum | Nachbauen? |
|--------|--------|------------|------------|
| ADV_IND Manufacturer (20 Byte) | Scan, kein Connect | Offset 12 / 14, `int16le / 16` | **ja** — Live |
| GATT `07` | Write 6 Byte auf FFF5 | 3 Records (oder 1 am Ende) | **ja** — History |
| GATT `1A` / `01` | Write 1 Byte | kein Live-°C; Count / Status | ja, beobachtet |
| GATT `0xF3` | nur Fuzzer | dieselben Rohwerte, anderes Framing | **nein** (nicht in der App) |
| GATT `04` / `05` / `18` / `19` / `0F` | siehe [04-opcodes.md](04-opcodes.md) | kein Echo | **nein** |

## Paarung Write → Notify (Fakt)

Regel: jedes FFF5-Write bekommt die FFF3-Notifies, die **vor dem nächsten Write** liegen. Keine verwaisten Notifies. 1:1 außer bei den sieben Writes ohne Echo.

| Write-Opcode | Paare | Notify | Länge W → N | Δ Write→Notify | Echo Erstbyte |
|--------------|------:|--------|-------------|----------------|---------------|
| `0x1A` | 5 | 1× 20 Byte | 1 → 20 | 14–32 ms (Median 16) | ja |
| `0x01` | 8 | 1× 20 Byte | 1 → 20 | 10–23 ms (Median 11,5) | ja |
| `0x07` | 1800 | 1× 20 Byte | 6 → 20 | 49–449 ms (Median 157) | ja, Header = Write |
| `0x04` | 1 | keine | 5 → — | — | nein |
| `0x18` | 3 | keine | 4 → — | — | nein |
| `0x19` | 1 | keine | 4 → — | — | nein |
| `0x05` | 1 | keine | 9 → — | — | nein |
| `0x0F` | 1 | keine | 2 → — | — | nein |

`0x07`: 1800/1800 Header `Write == Notify[:6]`.

Ungepaarte Writes (vollständig):

| Capture | rec | Write |
|---------|----:|-------|
| `15_14_35` | 3164 | `04 00 00 00 00` |
| `15_14_35` | 3260 | `18 E7 03 5E` |
| `15_14_35` | 3593 | `18 00 00 70` |
| `old/07_45_17` | 323 | `18 01 00 10` |
| `old/07_45_17` | 326 | `19 01 00 10` |
| `old/07_45_17` | 329 | `05 FF FF FF FF FF FF FF FF` |
| `old/07_45_17` | 335 | `0F 01` |

## Exakte App-Payloads (FFF5)

Nicht 1-Byte-Fuzzer. Jede **nicht-`07`-**Payload und das `07`-Muster:

| Opcode | Länge | Bytes (vollständig) | Sessions |
|--------|------:|---------------------|----------|
| `0x1A` | 1 | `1A` | alle GATT-Sessions |
| `0x01` | 1 | `01` | alle GATT-Sessions |
| `0x07` | 6 | `07 <index:u16le> 00 00 <count>` | History; `count` fast immer `03` |
| `0x04` | 5 | `04 00 00 00 00` | `15_14_35` rec 3164 |
| `0x18` | 4 | `18 E7 03 5E` / `18 00 00 70` / `18 01 00 10` | `15_14_35`, `old/07_45_17` |
| `0x19` | 4 | `19 01 00 10` | `old/07_45_17` rec 326 |
| `0x05` | 9 | `05 FF FF FF FF FF FF FF FF` | `old/07_45_17` rec 329 |
| `0x0F` | 2 | `0F 01` | `old/07_45_17` rec 335 |

`07` mit `count=01` (Rest der History, wenn Count nicht durch 3 teilbar):

| Capture | rec | Write |
|---------|----:|-------|
| `15_14_35` | 2967 | `07 30 06 00 00 01` (Index 1584) |
| `15_14_35` | 3431 | `07 31 06 00 00 01` (Index 1585) |
| `old/07_45_17` | 1542 | `07 33 03 00 00 01` (Index 819) |

Der eine Index-Schritt **+1** in `15_14_35` ist genau dieser Wechsel `count=03` → `count=01`, nicht ein Protokollfehler.

## FFF3-Layouts

Antworten sind durchgängig **20 Byte**. Kein ATT-MTU-Austausch.

### `0x1A` Status (Fakt: Bytes; Hypothese: Bedeutung)

Notify in **allen** 5 Sessions identisch. Beleg `14_52_44` rec 448, Δ 16 ms nach Write rec 446:

```
1A 01 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

| Offset | Länge | Byte-Order | Feld | Skala | Status | Beleg |
|--------|------:|------------|------|-------|--------|-------|
| 0 | 1 | — | Opcode | `1A` | Fakt | Echo des Writes |
| 1 | 1 | — | Flag? | `01` | Hypothese | konstant |
| 2 | 1 | — | ? | `00` | offen | konstant |
| 3 | 1 | — | Flag? | `01` | Hypothese | konstant |
| 4–19 | 16 | — | Padding | `00` | Fakt in diesen Captures | — |

Keine Temperatur, keine Luftfeuchtigkeit. Collector: nur „Gerät antwortet“.

### `0x01` Sample-Count (Fakt: Count; Hypothese: Zusatz)

Zwei Formen. Immer Byte 0 = `01`, Bytes 1–2 = Count als LE uint16.

**Form A — nur Count** (`14_52_44` rec 684, Δ 12 ms nach Write rec 682):

```
01 2F 06 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

| Offset | Länge | Byte-Order | Feld | Skala | Status | Beleg |
|--------|------:|------------|------|-------|--------|-------|
| 0 | 1 | — | Opcode | `01` | Fakt | Echo |
| 1 | 2 | LE uint16 | Sample-Count | `0x062F` = 1583 | Fakt | steigt 1583→1584→1585→1586 |
| 3–19 | 17 | — | Padding | `00` | Fakt in Form A | — |

**Form B — Count plus Records**, Byte 5 = Record-Zahl (wie bei `07`):

```
01 67 02 00 00 03 40 01 40 01 40 01 6A 04 69 04 6A 04 00 00
```

(`old/12_06_26` rec 1283). Byte 5 = `03`: Rest = History-Body (3× Temp, 3× Hum). Temps `0x0140` = 20,0 °C unter `/16`.

```
01 32 06 00 00 01 6F 01 E8 03 6E 01 0E 04 0F 04 F2 03 00 00
```

(`15_14_35` rec 3428). Byte 5 = `01`: Rest gleicht der `07`-Antwort mit `count=01` (rec 2969), nicht dem Live-ADV derselben Sekunde. **Nicht als Live-Frame verwenden.**

| Offset | Länge | Byte-Order | Feld | Skala | Status |
|--------|------:|------------|------|-------|--------|
| 0 | 1 | — | Opcode | `01` | Fakt |
| 1 | 2 | LE uint16 | Sample-Count | — | Fakt |
| 3 | 2 | — | `00 00` | — | Fakt in Form B |
| 5 | 1 | — | Record-Count `01` oder `03` | — | Fakt wenn Zusatz da |
| 6–17 | 12 | siehe `07` | Records | `/16` | Hypothese, gleiches Layout wie `07` |
| 18–19 | 2 | — | `00 00` | — | Fakt |

### `0x07` History (Fakt: Framing; Hypothese: Skala)

Write immer 6 Byte, Notify immer 20 Byte. Layout für `count=03` in [05-history-07.md](05-history-07.md).

```
07 | index:u16le | 00 00 | count | t0 t1 t2 | h0 h1 h2 | 00 00
```

| Offset | Länge | Byte-Order | Feld | Skala | Status | Beleg |
|--------|------:|------------|------|-------|--------|-------|
| 0 | 1 | — | Opcode | `07` | Fakt | 1800 Echo |
| 1 | 2 | LE uint16 | Index | — | Fakt | +3, außer Rest-Page +1 |
| 3 | 2 | — | Padding | `00 00` | Fakt | — |
| 5 | 1 | — | Count | `03` oder `01` | Fakt | `01` nur letzte Pages |
| 6 | 2 | LE int16 | Temp 0 | `/ 16` → °C | Hypothese, Display-konsistent | erste Page `14_52_44` rec 689 |
| 8 | 2 | LE int16 | Temp 1 | `/ 16` | Hypothese | nur wenn `count=03` |
| 10 | 2 | LE int16 | Temp 2 | `/ 16` | Hypothese | nur wenn `count=03` |
| 12 | 2 | LE int16 | Humidity 0 | `/ 16` → %rF | Hypothese | Display-% fehlt |
| 14 | 2 | LE int16 | Humidity 1 | `/ 16` | Hypothese | nur `count=03` |
| 16 | 2 | LE int16 | Humidity 2 | `/ 16` | Hypothese | nur `count=03` |
| 18 | 2 | — | Ende | `00 00` | Fakt 1800/1800 | keine laufende Checksum |

**`count=01`:** nur Record 0 ist ein Messpaar. Bytes 8–17 sind **nicht** Temp1/Temp2 — `E8 03` als Temp wäre 62,5 °C (unplausibel). Lesart: `t0` bei Offset 6, `h0` bei Offset 8, Rest Altlast/Padding.

Beleg `15_14_35` rec 2969:

```
07 30 06 00 00 01 6F 01 E8 03 6E 01 0E 04 0F 04 F2 03 00 00
```

`0x016F` / 16 = 22,9375 °C, `0x03E8` / 16 = 62,5 % — dieselben Rohwerte wie ADV um 15:14:41Z in derselben Datei (`6F 01` / `E8 03`). Index 1584 ≈ Count 1585/1586 = **neuestes** Sample, nicht Index 0.

Index 0 bleibt über alle Captures die **älteste** Page (`81 01 7B 01 …`), auch in `old/12_06_26`. Ringpuffer hat in diesen Logs nicht überschrieben.

### Advertising Live, 20 Byte (Position Fakt; Skala: Temp Live-Display, Hum ±3 %)

Kein GATT. Beleg `14_52_30` rec 171, 14:52:39Z — zeitnah zur notierten Anzeige 33 °C:

```
1B 00 10 00 D9 00 00 00 DB F4 B5 0B 61 01 0F 04 4B 7D 0E 00
```

| Offset | Länge | Byte-Order | Feld | Beispiel | Skala | Status | Beleg |
|--------|------:|------------|------|----------|-------|--------|-------|
| 0 | 2 | LE | Company-ID | `0x001B` | — | Fakt | alle ADV_IND Ziel |
| 2 | 2 | LE | Config | `10 00` | — | Fakt als Feld; Bedeutung offen | wechselt nach `0x18` |
| 4 | 6 | LE | MAC | `D9 … DB F4` | — | Fakt | = `f4:db:00:00:00:d9` |
| 10 | 2 | LE uint16 | Batterie | 2997 | mV | Hypothese | ~3,0 V |
| 12 | 2 | LE int16 | **Temperatur** | `0x0161` = 353 | **`/ 16` → 22,0625 °C** | Capture: +10 → Display 33; **Live 2026-09-03: Display = Roh 25,125** | rec 171 / `scan_live` |
| 14 | 2 | LE int16 | **Luftfeuchtigkeit** | `0x040F` = 1039 | **`/ 16` → 64,9375 %** | intern; Live ±3 % zum Display | dieselbe Frame; Live [07-read.md](07-read.md) |
| 16 | 4 | LE uint32 | Counter | 949579 | +1 / Frame | Hypothese: Sekunden | monoton |

Min/Max-22-Byte-Frames: [03-advertising.md](03-advertising.md). Kein Live.

## Skalen `/10` / `/16` / `/100` — derselbe Frame

Anzeige 33 °C, Offset +10 → Roh **~23 °C**. Frame: ADV rec 171.

| Skala | Temp 353 | vs. ~23 °C | vs. Display 33 | Hum 1039 | in 0–100 %? |
|-------|----------:|------------|----------------|----------:|-------------|
| `/ 10` | 35,30 °C | zu hoch | ohne Offset 2,3 °C daneben | 103,9 % | **nein** (38/60 ADV-Frames > 100 %) |
| `/ 16` | **22,0625 °C** | 0,94 °C unter 23 | **+10 → 32,06** (Display 33) | **64,94 %** | **ja** (60/60) |
| `/ 100` | 3,53 °C | unbrauchbar | — | 10,39 % | ja, aber Temp unmöglich |

`/16` ist die einzige Skala, die **beide** Felder derselben Frame gleichzeitig plausibel macht. Temp liegt 0,9 °C unter der Notiz „~23“; Display ist ganzzahlig 33, Offset +10 ist ganzzahlig — die Differenz ist erwartet.

History-Index 0 derselben Session: 24,06 / 23,69 / 23,56 °C unter `/16` — **alt**, nicht Live. Live ist ADV 22,06 °C.

**%rF:** Feld und Skala sind intern konsistent (ADV, History, Fuzzer-`0xF3`). Live 2026-09-03: `/16` liegt **±3 %** neben der Anzeige — Display-nah, nicht exakt. `/10` ist für Hum ausgeschlossen.

## Opcodes gegen App-Traffic

| Opcode | In der App? | Bedeutung |
|--------|-------------|-----------|
| `0x1A` | ja, 1 Byte | Status-Ping, festes 20-Byte-Echo. Kein Messwert. |
| `0x01` | ja, 1 Byte | History-Länge (uint16 LE). Manchmal letzte Records angehängt. |
| `0x07` | ja, **6 Byte** | History-Page. 1-Byte-Fuzzer lieferte leere ACKs, weil die Länge fehlt. |
| `0x03` | **nein** | nur Fuzzer: `03 01` + Nullen. Leeres ACK, keine °C/%rF. |
| `0xF3` | **nein** | nur Fuzzer (`ble_kurz.csv`). 20 Byte: Temp `7B 01` bei Offset 0, Hum `BC 03` bei Offset 10 — dieselben Rohwerte wie History-Record 1 der ersten Page, **anderes** Framing. Kein App-Kick, kein Live-ADV-Ersatz. Collector nimmt ADV oder `07`. |

Fuzzer-`0xF3` (`ble_kurz.csv`):

```
7B 01 00 00 00 00 00 00 00 00 BC 03 00 00 00 00 00 00 00 00
```

`0x017B` / 16 = 23,6875 °C, `0x03BC` / 16 = 59,75 % = History t1/h1 Index 0, nicht der ADV-Livewert der App-Session (22,06 °C). Zeitlich: Fuzzer 15. Nov, App-Capture 26. Nov — derselbe Rohwert in der ältesten History-Page, nicht „aktuell“.

## Felder — Temperatur, Luftfeuchtigkeit, Zeit, Checksum

| Feld | Wo | Status |
|------|-----|--------|
| Temperatur | ADV Offset 12; `07` Offset 6,8,10 (`count=03`) bzw. 6 (`count=01`) | `/16`; Live-Display = Roh; Capture hatte +10 |
| Luftfeuchtigkeit | ADV Offset 14; `07` Offset 12,14,16 bzw. 8 bei `count=01` | `/16`; Live ±3 % zum Display |
| Zeit / Sample-Zeit | kein Unix-Timestamp in GATT. ADV-Counter Offset 16 (Hypothese: Sekunden seit Power-On). History-Index ist die Reihenfolge, nicht die Uhr. | Hypothese |
| Checksum | letzte 2 Byte von `07` immer `00 00` (1800 Frames) | Padding, keine Checksum |
| Batterie | ADV Offset 10 | mV, Hypothese |

## Reproduzierbarer Befehl (Phase 3)

Live ohne Connect:

1. Scan ADV_IND, MAC `f4:db:00:00:00:d9` (nicht den Namen).
2. Manufacturer 20 Byte, Company `0x001B`, Temp/Hum wie oben.

History (Linux, CCCD explizit):

1. Connect → Discovery → CCCD Handle Value `0x0025` = `01 00`.
2. Write FFF5 `1A` → 20 Byte Status.
3. Write FFF5 `01` → Count.
4. Write FFF5 `07 <index:u16le> 00 00 03` (letzte Page ggf. `count=01`).

Keine Writes `04` / `05` / `18` / `19` / `0F` / `F3`.
