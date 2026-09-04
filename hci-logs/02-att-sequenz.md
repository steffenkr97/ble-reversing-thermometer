# ATT-Sequenz — FFF5 / FFF3

**Gerät:** `f4:db:00:00:00:d9`  
**Beleg:** Discovery und ATT in allen GATT-Sessions; Rohdump [extract/att_fff5_fff3.csv](extract/att_fff5_fff3.csv), [extract/unique_writes.csv](extract/unique_writes.csv)

Fakt vs. Hypothese ist an den Tabellen markiert.

## Handles (Fakt)

In **jeder** Session mit GATT-Discovery identisch. nRF-Connect-Handles sind die Characteristic-**Declarations**; Writes/Notifies laufen auf den **Value**-Handles.

| Rolle | UUID | Declaration | Value-Handle | Properties (Capture) |
|-------|------|-------------|--------------|----------------------|
| Service | `FFE0` | Start `0x001F` (31), Ende `0xFFFF` | — | — |
| Control | `FFF5` | `0x0020` (32) | **`0x0021` (33)** | Write |
| Data | `FFF3` | `0x0023` (35) | **`0x0024` (36)** | Notify |
| CCCD FFF3 | `2902` | — | **`0x0025` (37)** | Write `01 00` |

Weitere Services: GAP `1800` (1–7), GATT `1801` (8–11), DIS `180A` (12–30). Kein Health Thermometer `1839`.

Kein ATT-MTU-Austausch in diesen Captures. Notifications sind durchgängig **20 Byte** (Default-ATT-MTU 23 → 20 Byte Value).

## Ablauf der App (Fakt, `14_52_44`)

Zwei Verbindungen hintereinander (HCI-Handle 2 um 14:53:01Z, Handle 3 um 14:53:30Z). Dasselbe Muster in `15_00_04`.

1. LE Connection Complete → Peer `f4:db:00:00:00:d9`
2. Discovery: Read-by-Group (`1800`/`1801`/`180A`/`FFE0`), Read-by-Type (Characteristic-Declarations)
3. Write CCCD Handle **37** = `01 00` (Notify an)
4. Write FFF5 Handle **33** = `1A` (1 Byte) → Notify Handle **36**, 20 Byte, erstes Byte `1A`
5. (Reconnect / zweite Connection, wieder Discovery + CCCD)
6. Write FFF5 = `01` (1 Byte) → Notify `01 <count:u16le> 00 …`
7. Wiederholt Write FFF5 = `07 <index:u16le> 00 00 03` (6 Byte) → je eine Notify, Header echo + 3 Records

`start_notify()` auf macOS setzt CCCD nicht immer; in der Android-App ist der CCCD-Write explizit.

## Nicht-`07`-Writes (vollständig, Fakt)

Nur zitieren. `0x04` / `0x05` stehen auf der Fuzzer-Blacklist — nicht nachbauen.

### Echo-Befehle (Notify mit gleichem Opcode)

| Capture | Write FFF5 | Notify FFF3 (20 Byte) | Lesart |
|---------|------------|----------------------|--------|
| `14_52_44` rec 446 | `1A` | `1A 01 00 01 00` + 15× `00` | Status/Flags. Identisch in allen Sessions |
| `14_52_44` rec 682 | `01` | `01 2F 06 00` + Nullen | `0x062F` = **1583** Samples |
| `15_00_04` | `1A` / `01` | `01 30 06 00` … | `0x0630` = 1584 |
| `15_14_35` erstes `01` | `01` | `01 31 06 00` … | `0x0631` = 1585 |
| `15_14_35` späteres `01` | `01` | `01 32 06 00 00 01 6F 01 E8 03 6E 01 0E 04 0F 04 F2 03 00 00` | Count 1586 plus Zusatzbytes — [Hypothese](#01-mit-zusatzbytes) |
| `old/12_06_26` | `01` | `01 67 02 00` … bzw. mit Zusatz `… 00 03 40 01 40 01 40 01 6A 04 69 04 6A 04 00 00` | Count `0x0267` = 615 |
| `old/07_45_17` | `01` | `01 34 03 00 00 03 6B 01 6D 01 6F 01 FD 03 F6 03 F2 03 00 00` | Count `0x0334` = 820, Zusatz wie History-`07` |

`1A`-Notify ist in allen Dateien `1A 01 00 01 00` plus Nullen. Bedeutung der Flags offen (Hypothese: festes Statuswort).

### Ohne Opcode-Echo (kein passendes FFF3 mit gleichem Erstbyte)

| Capture | Write FFF5 | Notify? | Lesart |
|---------|------------|---------|--------|
| `15_14_35` rec 3164 | `04 00 00 00 00` (5 Byte) | kein Echo | App hat es gesendet. Blacklist. Bedeutung offen |
| `15_14_35` rec 3260 | `18 E7 03 5E` (4 Byte) | kein Echo | Config/Kalibrierung? Danach ADV-Feld `10 00` → `5E 00` |
| `15_14_35` rec 3593 | `18 00 00 70` (4 Byte) | kein Echo | Danach ADV-Feld → `70 00` |
| `old/07_45_17` rec 323 | `18 01 00 10` | kein Echo | gleiches Opcode-Muster |
| `old/07_45_17` rec 326 | `19 01 00 10` | kein Echo | ähnlich `18`, Bedeutung offen |
| `old/07_45_17` rec 329 | `05 FF FF FF FF FF FF FF FF` (9 Byte) | kein Echo | Blacklist. Sieht nach Maske/Reset aus |
| `old/07_45_17` rec 335 | `0F 01` (2 Byte) | kein Echo | offen |

`0x18` / `0x04` gegen Display 33 °C / +10: **nicht belegt**. Nur die Koinzidenz mit ADV-Bytes 2–3 ist beobachtet (siehe [03-advertising.md](03-advertising.md)). Nicht nachbauen.

## History-`07` (kurz)

Write immer **6 Byte**, Notify immer **20 Byte**, Index in 3er-Schritten. Layout: [05-history-07.md](05-history-07.md).

Beispiel erste Page (`14_52_44`):

- Write: `07 00 00 00 00 03`
- Notify: `07 00 00 00 00 03 81 01 7B 01 79 01 B4 03 BC 03 CB 03 00 00`

## `01` mit Zusatzbytes

Wenn Byte 5 (0-basiert) `03` ist, gleicht der Rest einem `07`-Frame (3× Temp, 3× Humidity, Ende `00 00`). Beispiel `old/12_06_26`: Temps `0x0140` = 20.0 °C (Skala `/16`, Hypothese).

Wenn Byte 5 `01` ist (`15_14_35` zweites `01`), Layout unklar. Nicht als Fakt für Live-Werte verwenden — ADV derselben Session ist eindeutiger.

## Was die App nicht schickt

`0xF3` kommt in **keinem** App-Capture vor. Der Fuzzer-Treffer `0xF3` ist ein anderer Record-Typ, kein App-Befehl. Live ohne GATT steht in ADV_IND. Paare und Encoding: [06-encoding.md](06-encoding.md).
