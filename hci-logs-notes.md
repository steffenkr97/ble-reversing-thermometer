# HCI-Log-Notizen

Kalibrier-Test (Nov 2025, Captures): Display auf **33 °C** gesetzt = Offset **+10**. Rohwert sollte ~23 °C entsprechen. Luftfeuchtigkeit wurde damals nicht notiert.

Live 2026-09-03: `scan_live.py` → Display **25,125 °C = Roh `/16`**, Hum ±3 %. Kein +10. Collector-CSV noch offen. [hci-logs/07-read.md](hci-logs/07-read.md).

Captures liegen unter `hci-logs/*.cfa` (Android-btsnoop, OnePlus 5T), nicht unter `research-device/hci/`.

## Auswertung

| Datei | Inhalt |
|-------|--------|
| [01-sessions.md](hci-logs/01-sessions.md) | Dateien, Quelle, App-Aktion, andere ThermoBeacons |
| [02-att-sequenz.md](hci-logs/02-att-sequenz.md) | Handles, Ablauf, alle nicht-`07`-FFF5-Payloads |
| [03-advertising.md](hci-logs/03-advertising.md) | Live-Temp/%rF in ADV_IND ohne Connect |
| [04-opcodes.md](hci-logs/04-opcodes.md) | Histogram, `04`/`18`/`05`/`0F`/`19`, Fuzzer vs. App |
| [05-history-07.md](hci-logs/05-history-07.md) | History-Page, `/16`, Ende `00 00` |
| [06-encoding.md](hci-logs/06-encoding.md) | Phase 2: Paare, Payloads, Skala `/16` gegen Display |
| [07-read.md](hci-logs/07-read.md) | Phase 3: Parser, `scan_live.py`, GATT-Probe; ADV-Live 2026-09-03 |
| [08-collect.md](hci-logs/08-collect.md) | Phase 4: ADV-Collector `collect.py` → CSV; CSV-Lauf noch offen |
| [09-dashboard.md](hci-logs/09-dashboard.md) | Lokales Dashboard (CSV + HCI-Beleg), kein BLE |
| [extract/](hci-logs/extract/) | CSV-Rohdumps aus `collector/parse_btsnoop.py` (inkl. `pairs.csv`) |
