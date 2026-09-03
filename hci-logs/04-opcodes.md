# Opcode-Katalog FFF5 → FFF3

**Gerät:** `f4:db:00:00:00:d9`  
**Beleg:** [extract/opcodes.csv](extract/opcodes.csv), [extract/unique_writes.csv](extract/unique_writes.csv)

Nur App-Traffic. Fuzzer-Kommandos, die hier fehlen, sind keine App-Befehle.

## Histogram (FFF5-Writes / FFF3-Notifies)

| Datei | `1A` | `01` | `07` | `04` | `18` | `19` | `05` | `0F` |
|-------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| `14_52_44` | 1 / 1 | 1 / 1 | 96 / 96 | | | | | |
| `15_00_04` | 1 / 1 | 1 / 1 | 528 / 528 | | | | | |
| `15_14_35` | 1 / 1 | 2 / 2 | 530 / 530 | 1 / 0 | 2 / 0 | | | |
| `old/12_06_26` | 1 / 1 | 3 / 3 | 372 / 372 | | | | | |
| `old/07_45_17` | 1 / 1 | 1 / 1 | 274 / 274 | | 1 / 0 | 1 / 0 | 1 / 0 | 1 / 0 |
| Scan-only / `old/12_06_14` | — | — | — | | | | | |

Spalte = Writes / Notifies mit diesem Erstbyte. `07` paired 1:1. `04`/`18`/`19`/`05`/`0F` erzeugen **kein** Opcode-Echo.

## Bekannte Payloads

Vollständige Bytes: [02-att-sequenz.md](02-att-sequenz.md).

| Opcode | App-Länge | Echo auf FFF3? | Lesart | Nachbauen? |
|--------|-----------|----------------|--------|------------|
| `0x1A` | 1 | ja, 20 Byte | Status | ja, beobachtet |
| `0x01` | 1 | ja, 20 Byte | Sample-Count, manchmal letzte Records | ja, beobachtet |
| `0x07` | 6 | ja, 20 Byte | History-Page, 3 Samples (letzte Page ggf. 1) | ja, beobachtet |
| `0x04` | 5 (`04 00 00 00 00`) | nein | offen, Blacklist | **nein** |
| `0x05` | 9 (`05` + 8× `FF`) | nein | offen, Blacklist | **nein** |
| `0x18` | 4 | nein | ändert ADV-Config-Byte (Hypothese) | **nein** bis belegt |
| `0x19` | 4 (`19 01 00 10`) | nein | offen | **nein** |
| `0x0F` | 2 (`0F 01`) | nein | offen | **nein** |
| `0xF3` | — | — | nur Fuzzer (`ble_kurz.csv`), **nicht** in der App | nicht als App-Kick verwenden |
| `0x03` | — | — | Fuzzer-ACK, nicht in der App | — |
| `0xFF` / `0xFE` | — | — | Blacklist, nicht in der App | **nein** |

## `0x18` / `0x04` vs. Kalibrierung +10

Notiert: Display 33 °C = +10. In `15_14_35`:

1. `04 00 00 00 00`
2. `18 E7 03 5E` → ADV Config wird `5E 00`
3. `01` mit Zusatzbytes
4. `18 00 00 70` → ADV Config wird `70 00`

Kein Byte ist `0x0A` (+10) oder `0x0210` (33×16). Zuordnung Kalibrierung **unbewiesen**. Encoding-Abgleich (ohne diese Opcodes): [06-encoding.md](06-encoding.md).

## Fuzzer vs. App

1-Byte-Kick `0x07` im Fuzzer lieferte leere ACKs. Die App schickt **6 Byte**. `0xF3` im Fuzzer trug `7B 01` / `BC 03` — dieselben Rohwerte wie History, anderes Framing. App nutzt das nicht.
