# Phase 4 — ADV-Collector (Live → CSV)

**Gerät:** `f4:db:00:00:00:d9`  
**Encoding-Beleg:** [03-advertising.md](03-advertising.md), [06-encoding.md](06-encoding.md), [07-read.md](07-read.md)  
**Code:** `collector/collect.py`, `collector/thermo_store.py` (Scan über `collector/scan_live.py`, Parser `collector/thermo_parse.py`, Allowlist `collector/thermo_rooms.py`)  
**Tests:** `python -m unittest discover -s collector -p "test_*.py"`

Phase-4-Code ist im Repo. ADV-Scan am Büro-Gerät ist durch ([07-read.md](07-read.md)); `collect.py` → CSV noch nicht.

`collector/collect.py` sammelt Live-Werte **nur über ADV_IND** (kein Connect, kein GATT-Kick). Filter ist die Allowlist in `dashboard/rooms.json` (Payload-MAC), nicht der Gerätename. Ohne `--mac` ein Sample je Allowlist-Treffer in die jeweilige CSV. GATT-Probe bleibt `read_thermometer_data.py`. Der Collector verbindet nicht und schreibt nicht auf `FFF5`.

## Abhängigkeit

`requirements.txt`: `bleak>=0.21.0`.

`collect.py` importiert `scan_live`, das `bleak` **oben** lädt. Ohne das Paket scheitert schon `--help`:

```
ModuleNotFoundError: No module named 'bleak'
```

`thermo_store` und `thermo_parse` brauchen kein bleak. Die Unittests stubben bleak, falls es fehlt. Syntax: `python -m py_compile collector/collect.py collector/thermo_store.py collector/scan_live.py collector/thermo_parse.py` ist ok. Ohne bleak scheitert `python collector/collect.py --help` (`ModuleNotFoundError: No module named 'bleak'`).

## CLI

```
python collector/collect.py
python collector/collect.py --mac f4:db:00:00:00:d9
python collector/collect.py --once
python collector/collect.py --interval 60
python collector/collect.py --timeout 15 --outdir data
python collector/collect.py --output PATH --mac f4:db:00:00:00:d9
python collector/collect.py --address f4:db:00:00:00:d9
```

| Flag | Bedeutung |
|------|-----------|
| `--once` | ein Scan-Fenster, dann Exit. **Standard**, wenn `--interval` fehlt (auch ohne Flag). |
| `--interval SEK` | Loop: Scan, schreiben oder Timeout loggen, dann `sleep`. Unverträglich mit `--once`. Muss `> 0` sein. |
| `--timeout SEK` | Scan-Timeout **pro Versuch**, Standard **15**. Muss `> 0` sein. |
| `--outdir DIR` | Verzeichnis wenn `--output` fehlt, Standard `data` |
| `--output PATH` | feste CSV-Datei; braucht genau ein `--mac` |
| `--mac MAC` | nur diese Payload-MAC (muss in `rooms.json` stehen) |
| `--rooms PATH` | Allowlist, Standard `dashboard/rooms.json` |
| `--address ADDR` | zusätzlich `device.address` an `scan_live` (Linux/Windows: MAC, macOS: UUID). Payload-MAC bleibt Pflicht. |

`--once` und `--interval` zusammen → argparse-Fehler (`SystemExit`).

Nur Advertising. Filter ist die Payload-MAC gegen die Allowlist, nicht der Gerätename. Framing wie in [07-read.md](07-read.md): `assemble_mfg_frame` → `parse_adv_manufacturer(..., allowed_macs=…)`. Ohne Allowlist-Argument parst der Parser nur die Büro-MAC.

## Ablauf

CSV-Pfad: `--output` (ein MAC) oder `default_csv_path(mac, outdir)` **je Treffer**. Die Datei entsteht erst beim ersten Sample (`append_sample`).

### `--once` (Default)

1. Scan der Allowlist (`scan_live` bei einem MAC, sonst `scan_live_many`)
2. Treffer: je MAC eine CSV-Zeile, Sample auf stdout (`format_sample` plus `geschrieben: PATH`), Exit **0** wenn mindestens ein Sample
3. Timeout ohne Treffer: Meldung auf stderr (`Kein Live-Sample innerhalb von … s (Allowlist …).`), Exit **1** — keine Messzeile
4. Teiltreffer: Exit 0, fehlende MACs auf stderr

### `--interval SEK`

Endlosschleife:

1. Scan wie oben
2. Treffer: CSV + stdout
3. Timeout: dieselbe Meldung auf stderr, **weiter** (kein Exit)
4. danach `asyncio.sleep(interval)` — auch nach Timeout
5. `KeyboardInterrupt` → Exit **0**

## CSV

Spalten fest (`thermo_store.COLUMNS`):

| Spalte | Einheit / Format |
|--------|------------------|
| `timestamp` | ISO-8601 UTC, `YYYY-MM-DDTHH:MM:SSZ` (`iso_utc_now`, keine lokale Zeit, keine Mikrosekunden). Sammelzeit, nicht Gerätezeit. |
| `mac` | Payload-MAC, z. B. `f4:db:00:00:00:d9` |
| `temp_c` | °C, `int16le / 16` |
| `humidity_rh` | %rF, `int16le / 16` (Display-% weiter unbelegt, siehe [06-encoding.md](06-encoding.md)) |
| `raw_hex` | Manufacturer-Frame, 20 Byte hex ohne Leerzeichen |

Kein `battery_mv`, kein `counter` in der CSV (die Felder stehen nur auf stdout über `format_sample`). Header genau einmal, wenn die Datei neu oder leer ist. Eine Zeile = ein Sample. Rohhex bleibt.

Default-Pfad (UTC-Kalendertag, MAC ohne Trenner, lowercase):

```
data/thermo_f4db000000d9_YYYY-MM-DD.csv
```

Beispiel Büro-Gerät am 2026-09-03: `data/thermo_f4db000000d9_2026-09-03.csv`. `--outdir` ändert nur das Verzeichnis, nicht das Namensschema. `.gitignore`: `data/*.csv` (Ordner bleibt über `data/.gitkeep`).

## Blacklist (keine Writes)

Der Collector schreibt **nicht** auf `FFF5`. Blacklist unverändert — nicht senden:

`04` / `05` / `18` / `19` / `0F` / `F3`

Details: [04-opcodes.md](04-opcodes.md). GATT-Reads (`1A` / `01` / `07`) bleiben in `read_thermometer_data.py`.

## Live-Ergebnis

ADV-Scan am Büro-Gerät ist durch ([07-read.md](07-read.md)): Display **25,125 °C = Roh `/16`**, Hum ±3 %, MAC stimmt. **Kein +10** am 2026-09-03.

`collect.py` → CSV ist **noch nicht am Büro gelaufen**. Feldlauf: `python collector/mvp_buero.py` oder `collect.py --mac f4:db:00:00:00:d9`. Allowlist: [11-rooms.md](11-rooms.md).
