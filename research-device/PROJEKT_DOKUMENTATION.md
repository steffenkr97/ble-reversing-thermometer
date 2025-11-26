# ThermoBeacon Reverse Engineering - Projekt Dokumentation

## Übersicht

Dieses Projekt beschäftigt sich mit dem Reverse Engineering eines BLE-Thermometers (ThermoBeacon). Ziel ist es, die Temperaturdaten direkt über Python auszulesen, ohne die offizielle App zu verwenden.

**Gerät:** ThermoBeacon (unbekannter Hersteller)  
**Datum:** November 2024  
**Status:** In Arbeit - Datenempfang noch nicht erfolgreich

---

## Gerät-Informationen

### Identifikation

- **System ID:** `D9 00 00 00 00 00 DB F4`
- **BLE-Adresse (macOS):** `8277B476-C20F-BC82-678E-540BEC258660`
- **Gerätename:** ThermoBeacon

### Services und Characteristics

#### Standard Services

**Device Information Service (DIS) - UUID: 180A**
- `2A23` - System ID: `D9 00 00 00 00 00 DB F4` ✓ (eindeutiger Wert)
- `2A24` - Model Number: `"Model Number"` (Platzhalter)
- `2A25` - Serial Number: `"Serial Number"` (Platzhalter)
- `2A26` - Firmware Revision: `"Firmware Revision"` (Platzhalter)
- `2A27` - Hardware Revision: `"Hardware Revision"` (Platzhalter)
- `2A28` - Software Revision: `"Software Revision"` (Platzhalter)
- `2A29` - Manufacturer Name: `"Manufacturer Name"` (Platzhalter)
- `2A2A` - IEEE 11073-20601: `"experimental"`
- `2A50` - PnP ID: `01 04 05 00 00 10 01`

**Fazit:** Standard-Services sind vorhanden, aber größtenteils nicht befüllt. Nur die System ID ist eindeutig.

#### Custom Services

**Service FFE0 - UUID: 0000FFE0-0000-1000-8000-00805f9b34fb**

Dies ist der **wichtige Service** für die Temperaturdaten:

- **FFF5 (Control)** - Properties: `write`
  - Handle: 32
  - Verwendung: Start-Befehl senden (z.B. `0x01`)
  - Descriptors: 2901 (Characteristic User Description)

- **FFF3 (Data)** - Properties: `notify`
  - Handle: 35
  - Verwendung: Empfang von Temperaturdaten
  - Descriptors: 
    - 2902 (CCCD - Client Characteristic Configuration Descriptor)
    - 2901 (Characteristic User Description)

**Protokoll (vermutet):**
1. Verbindung herstellen
2. Start-Befehl auf FFF5 senden (z.B. `0x01`)
3. Notifications auf FFF3 aktivieren
4. Daten werden automatisch empfangen

---

## Erstellte Skripte

### 1. `py/mini.py` - Einfacher BLE-Scanner

**Zweck:** Findet alle BLE-Geräte in der Nähe

**Verwendung:**
```bash
python3 py/mini.py
```

**Ausgabe:** Liste aller gefundenen BLE-Geräte mit Adresse, Name und RSSI

---

### 2. `py/list_system_ids.py` - System ID Scanner

**Zweck:** Findet alle ThermoBeacon-Geräte und liest deren System IDs aus

**Features:**
- Scannt nach ThermoBeacon-Geräten
- Liest System ID (2A23) von jedem Gerät
- Liest weitere Device Information Characteristics
- Speichert Ergebnisse in CSV-Datei
- Markiert das Gerät mit der bekannten System ID

**Verwendung:**
```bash
# Automatischer Dateiname
python3 py/list_system_ids.py

# Eigenen Dateinamen angeben
python3 py/list_system_ids.py --output geräte.csv
```

**Ausgabe:** CSV-Datei mit allen gefundenen Geräten und deren Device Information

---

### 3. `py/read_thermometer_data.py` - Hauptskript für Datenempfang

**Zweck:** Verbindet sich mit dem Gerät und empfängt Temperaturdaten

**Features:**
- Automatische Gerätesuche (nach Name oder System ID)
- Detaillierte Service/Characteristic-Analyse
- Markiert Standard vs. Custom Services/Characteristics
- Liest Werte von Read-Characteristics automatisch
- Testet verschiedene Start-Befehle
- Aktiviert Notifications auf FFF3
- Zeigt empfangene Daten mit Temperatur-Interpretation

**Verwendung:**
```bash
# Debug-Info anzeigen (alle Services/Characteristics)
python3 py/read_thermometer_data.py --address "8277B476-C20F-BC82-678E-540BEC258660" --debug-only

# Mit Start-Befehl und Datenempfang
python3 py/read_thermometer_data.py --address "8277B476-C20F-BC82-678E-540BEC258660" --kick 0x01

# Automatische Gerätesuche
python3 py/read_thermometer_data.py --use-system-id

# Einmalig lesen (falls Read unterstützt)
python3 py/read_thermometer_data.py --address "..." --read-once
```

**Kommandozeilen-Optionen:**
- `--address, -a`: BLE-Adresse des Geräts
- `--use-system-id`: Suche Gerät anhand System ID
- `--kick, -k`: Start-Befehl als Hex (z.B. `0x01` oder `"01"`)
- `--debug-only`: Nur Debug-Info, keine Daten lesen
- `--read-once`: Versuche FFF3 einmalig zu lesen

**Aktueller Status:**
- ✅ Verbindung funktioniert
- ✅ Services werden gefunden
- ✅ Start-Befehle werden erfolgreich gesendet
- ❌ Notifications werden aktiviert, aber keine Daten empfangen
- ⚠️  CCCD kann auf macOS nicht manuell gesetzt werden

---

## Technische Erkenntnisse

### BLE-Kommunikation

#### Standard vs. Custom Services

**Standard Services (Bluetooth SIG):**
- Format: `0000XXXX-0000-1000-8000-00805f9b34fb`
- XXXX = 16-Bit UUID (z.B. `180A` = Device Information Service)
- Dokumentiert in Bluetooth-Spezifikation
- Funktionieren bei allen Geräten gleich

**Custom Services:**
- Format: `0000XXXX-0000-1000-8000-00805f9b34fb` mit XXXX im Bereich `0xF000-0xFFFF`
- Oder vollständige 128-Bit UUID
- Hersteller-spezifisch
- Müssen reverse-engineered werden

#### GATT-Operationen

1. **Read:** Einmaliges Lesen eines Werts
   ```python
   value = await client.read_gatt_char(UUID)
   ```

2. **Write:** Einmaliges Schreiben eines Werts
   ```python
   await client.write_gatt_char(UUID, bytes([0x01]))
   ```

3. **Notify:** Kontinuierlicher Empfang von Daten
   ```python
   await client.start_notify(UUID, callback_function)
   ```

#### CCCD (Client Characteristic Configuration Descriptor)

- UUID: `00002902-0000-1000-8000-00805f9b34fb`
- Steuert, ob Notifications aktiviert sind
- Wert: `0x0000` = deaktiviert, `0x0001` = Notifications aktiviert
- Problem auf macOS: Kann nicht manuell gesetzt werden
- `start_notify()` sollte es automatisch setzen, aber funktioniert nicht immer

---

## Bekannte Probleme

### 1. Keine Daten empfangen

**Symptom:** Notifications werden aktiviert, aber keine Daten kommen

**Mögliche Ursachen:**
- Falscher Start-Befehl (0x01 ist möglicherweise nicht korrekt)
- Gerät sendet nur auf bestimmte Trigger
- CCCD wird auf macOS nicht richtig gesetzt
- Gerät muss aktiv sein (z.B. App öffnen)

**Lösungsansätze:**
- Verschiedene Start-Befehle testen (0x00, 0xFF, 0x0100, etc.)
- Parallel mit App testen
- Auf Linux wechseln (bessere BLE-Unterstützung)

### 2. macOS-Limitierungen

**Problem:** CCCD kann nicht manuell gesetzt werden

**Fehlermeldung:**
```
NSInternalInconsistencyException - Client Characteristic Configuration descriptors must be configured using setNotifyValue:forCharacteristic:
```

**Workaround:** `start_notify()` sollte es automatisch machen, funktioniert aber nicht immer

**Lösung:** Auf Linux testen, wo manuelles Setzen möglich ist

---

## Nächste Schritte

### Kurzfristig (empfohlen)

1. **App parallel testen**
   - App öffnen und Daten anzeigen lassen
   - Gleichzeitig Skript laufen lassen
   - Prüfen, ob Daten kommen, wenn App aktiv ist

2. **Verschiedene Start-Befehle testen**
   ```bash
   python3 py/read_thermometer_data.py --address "..." --kick 0x00
   python3 py/read_thermometer_data.py --address "..." --kick 0xFF
   python3 py/read_thermometer_data.py --address "..." --kick 0x0100
   ```

3. **Längere Wartezeit**
   - `max_wait_time` im Code erhöhen oder entfernen
   - Manche Geräte senden nur alle paar Sekunden

### Mittelfristig

1. **Linux-Umgebung einrichten**
   - Raspberry Pi oder Linux-VM
   - `gatttool`, `bluetoothctl` installieren
   - CCCD manuell setzen können
   - Bessere BLE-Debugging-Tools

2. **App-Verhalten analysieren**
   - Mit nRF Connect oder ähnlichem Tool die App überwachen
   - Schauen, welche Befehle die App sendet
   - Timing analysieren

### Langfristig (falls nötig)

1. **BLE-Sniffing mit Wireshark**
   - Benötigt: Linux + kompatibler BLE-Adapter (z.B. Nordic nRF52840)
   - Exakte Analyse der BLE-Kommunikation
   - Sieht alle Pakete zwischen App und Gerät

2. **Firmware-Analyse**
   - Falls App-Dateien verfügbar sind
   - Protokoll-Details aus der App extrahieren

---

## Dateien und Struktur

```
rev-ble-thermoeter/
├── py/
│   ├── mini.py                    # Einfacher BLE-Scanner
│   ├── list_system_ids.py         # System ID Scanner mit CSV-Export
│   └── read_thermometer_data.py    # Hauptskript für Datenempfang
├── research-device/
│   ├── TermoBeacon_001B.md        # Original-Log von nRF Connect
│   └── PROJEKT_DOKUMENTATION.md   # Diese Datei
├── requirements.txt               # Python-Abhängigkeiten (bleak)
└── thermobeacon_devices_*.csv     # CSV-Exporte von list_system_ids.py
```

---

## Abhängigkeiten

```bash
pip install bleak>=0.21.0
```

**Python:** 3.7+  
**Bibliothek:** bleak (asyncio-basierte BLE-Bibliothek, plattformübergreifend)

---

## Referenzen

### Bluetooth SIG Standard Services

- **180A:** Device Information Service
- **1839:** Health Thermometer Service (Standard für Thermometer, aber nicht verwendet)

### Bluetooth SIG Standard Characteristics

- **2A23:** System ID
- **2A24:** Model Number String
- **2A25:** Serial Number String
- **2A26:** Firmware Revision String
- **2A27:** Hardware Revision String
- **2A28:** Software Revision String
- **2A29:** Manufacturer Name String
- **2A50:** PnP ID

### Nützliche Tools

- **nRF Connect:** BLE-Debugging-App (iOS/Android)
- **bluetoothctl:** Linux CLI-Tool für Bluetooth
- **gatttool:** Linux CLI-Tool für GATT-Operationen (veraltet, aber nützlich)
- **Wireshark:** Netzwerk-Sniffer (mit BLE-Support auf Linux)

---

## Changelog

### 2024-11-15
- Projekt gestartet
- BLE-Scanner erstellt (`mini.py`)
- System ID Scanner erstellt (`list_system_ids.py`)
- Hauptskript erstellt (`read_thermometer_data.py`)
- Services analysiert (Standard vs. Custom)
- Problem identifiziert: Keine Daten empfangen
- Dokumentation erstellt

---

## Notizen

- Gerät verwendet Custom-Service FFE0 statt Standard Health Thermometer Service (1839)
- Typisches Muster bei günstigen China-Geräten: "FFF5 start → FFF3 notify"
- System ID ist der einzige eindeutige Identifikator
- Device Information Service ist vorhanden, aber nicht befüllt
- macOS hat Limitierungen bei BLE-Operationen (CCCD kann nicht manuell gesetzt werden)

---

## Kontakt / Weitere Informationen

Bei Fragen oder neuen Erkenntnissen bitte diese Dokumentation aktualisieren.

## Notifications

```csv
cmd,sent_at,status,notifications
0x00,2025-11-15T14:07:56.877572Z,OK,
0x01,2025-11-15T14:07:59.916284Z,OK,2025-11-15T14:07:59.975621Z 0101000000000000000000000000000000000000
0x02,2025-11-15T14:08:02.977347Z,OK,
0x03,2025-11-15T14:08:06.139517Z,OK,2025-11-15T14:08:06.287491Z 0301000000000000000000000000000000000000
0x04,,SKIPPED (safe blacklist),
0x05,,SKIPPED (safe blacklist),
0x07,2025-11-15T14:08:12.438777Z,OK,2025-11-15T14:08:12.587222Z 0701000000010000000000000000000000000000
0x1A,2025-11-15T14:09:12.286832Z,OK,2025-11-15T14:09:12.434612Z 1A01000100000000000000000000000000000000
0xF3,2025-11-15T14:20:35.841520Z,OK,2025-11-15T14:20:35.989851Z 7B010000000000000000BC030000000000000000

```


