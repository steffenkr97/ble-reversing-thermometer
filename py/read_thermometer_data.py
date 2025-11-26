#!/usr/bin/env python3
"""
Liest Daten vom ThermoBeacon-Gerät über FFF3 (Notify)
"""
import asyncio
import argparse
from datetime import datetime
from bleak import BleakScanner, BleakClient

# UUIDs für dein Gerät (aus dem Log)
SERVICE_UUID = "0000FFE0-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "0000FFF5-0000-1000-8000-00805f9b34fb"  # Write (Start-Befehl)
DATA_CHAR_UUID = "0000FFF3-0000-1000-8000-00805f9b34fb"     # Notify (Daten)

# System ID deines Geräts (zum Identifizieren)
TARGET_SYSTEM_ID = bytes.fromhex("D90000000000DBF4")
SYSTEM_ID_UUID = "00002A23-0000-1000-8000-00805f9b34fb"

# Bekannte Bluetooth SIG Standard Services (16-Bit UUIDs)
STANDARD_SERVICES = {
    "1800": "Generic Access Profile (GAP)",
    "1801": "Generic Attribute Profile (GATT)",
    "180A": "Device Information Service (DIS)",
    "180F": "Battery Service",
    "1810": "Blood Pressure",
    "1811": "Alert Notification Service",
    "1812": "Human Interface Device (HID)",
    "1813": "Scan Parameters",
    "1814": "Running Speed and Cadence",
    "1815": "Automation IO",
    "1816": "Cycling Speed and Cadence",
    "1818": "Cycling Power",
    "1819": "Location and Navigation",
    "181A": "Environmental Sensing",
    "181B": "Body Composition",
    "181C": "User Data",
    "181D": "Weight Scale",
    "181E": "Bond Management",
    "181F": "Continuous Glucose Monitoring",
    "1820": "Internet Protocol Support",
    "1821": "Indoor Positioning",
    "1822": "Pulse Oximeter",
    "1823": "HTTP Proxy",
    "1824": "Transport Discovery",
    "1825": "Object Transfer",
    "1826": "Fitness Machine",
    "1827": "Mesh Provisioning",
    "1828": "Mesh Proxy",
    "1829": "Reconnection Configuration",
    "182A": "Insulin Delivery",
    "182B": "Binary Sensor",
    "182C": "Emergency Configuration",
    "182D": "Authorization Control",
    "182E": "Physical Activity Monitor",
    "182F": "Elapsed Time",
    "1830": "Generic Health Sensor",
    "1831": "Hearing Aid",
    "1832": "LE Transport Discovery",
    "1833": "Referenced Target Time",
    "1834": "Heart Rate",
    "1835": "Phone Alert Status",
    "1836": "Time",
    "1837": "Time with DST",
    "1838": "Glucose",
    "1839": "Health Thermometer",
    "183A": "Device Time",
    "183B": "Time Broadcast",
    "183C": "Time Synchronization",
    "183D": "Microphone Control",
    "183E": "Audio Stream Control",
    "183F": "Broadcast Audio Scan",
    "1840": "Published Audio Capabilities",
    "1841": "Basic Audio Announcement",
    "1842": "Broadcast Audio Announcement",
    "1843": "Common Audio",
    "1844": "Hearing Access",
    "1845": "Telephony and Media Audio",
    "1846": "Public Broadcast Announcement",
}

# Bekannte Bluetooth SIG Standard Characteristics (16-Bit UUIDs)
STANDARD_CHARACTERISTICS = {
    "2A00": "Device Name",
    "2A01": "Appearance",
    "2A02": "Peripheral Privacy Flag",
    "2A03": "Reconnection Address",
    "2A04": "Peripheral Preferred Connection Parameters",
    "2A05": "Service Changed",
    "2A06": "Alert Level",
    "2A07": "Tx Power Level",
    "2A08": "Date Time",
    "2A09": "Day of Week",
    "2A0A": "Day Date Time",
    "2A0B": "Exact Time 100",
    "2A0C": "DST Offset",
    "2A0D": "Time Zone",
    "2A0E": "Local Time Information",
    "2A0F": "Time with DST",
    "2A10": "Time Accuracy",
    "2A11": "Time Source",
    "2A12": "Reference Time Information",
    "2A13": "Time Update Control Point",
    "2A14": "Time Update State",
    "2A15": "Glucose Measurement",
    "2A16": "Battery Level",
    "2A17": "Temperature Measurement",
    "2A18": "Temperature Type",
    "2A19": "Intermediate Temperature",
    "2A1A": "Temperature Measurement Interval",
    "2A1B": "Temperature Measurement Interval (Fast)",
    "2A1C": "Temperature Measurement Interval (Slow)",
    "2A1D": "Temperature Measurement Interval (Very Fast)",
    "2A1E": "Temperature Measurement Interval (Very Slow)",
    "2A1F": "Temperature Measurement Interval (Ultra Fast)",
    "2A20": "Temperature Measurement Interval (Ultra Slow)",
    "2A21": "Temperature Measurement Interval (Extreme Fast)",
    "2A22": "Temperature Measurement Interval (Extreme Slow)",
    "2A23": "System ID",
    "2A24": "Model Number String",
    "2A25": "Serial Number String",
    "2A26": "Firmware Revision String",
    "2A27": "Hardware Revision String",
    "2A28": "Software Revision String",
    "2A29": "Manufacturer Name String",
    "2A2A": "IEEE 11073-20601 Regulatory Certification Data List",
    "2A2B": "Current Time",
    "2A2C": "Magnetic Declination",
    "2A2F": "Position 2D",
    "2A30": "Position 3D",
    "2A31": "Scan Refresh",
    "2A32": "Boot Keyboard Input Report",
    "2A33": "System ID",
    "2A34": "Model Number String",
    "2A35": "Serial Number String",
    "2A36": "Firmware Revision String",
    "2A37": "Hardware Revision String",
    "2A38": "Software Revision String",
    "2A39": "Manufacturer Name String",
    "2A3A": "IEEE 11073-20601 Regulatory Certification Data List",
    "2A50": "PnP ID",
}

def is_standard_uuid(uuid: str) -> tuple[bool, str]:
    """
    Prüft ob eine UUID ein Bluetooth SIG Standard ist.
    
    Returns:
        (is_standard, description)
    """
    uuid_lower = uuid.lower()
    
    # Prüfe ob es die Base-UUID Form hat: 0000XXXX-0000-1000-8000-00805f9b34fb
    if uuid_lower.startswith("0000") and uuid_lower.endswith("-0000-1000-8000-00805f9b34fb"):
        short_uuid = uuid_lower[4:8].upper()  # Extrahiere XXXX
        
        # Prüfe Services
        if short_uuid in STANDARD_SERVICES:
            return (True, f"Standard Service: {STANDARD_SERVICES[short_uuid]}")
        
        # Prüfe Characteristics
        if short_uuid in STANDARD_CHARACTERISTICS:
            return (True, f"Standard Characteristic: {STANDARD_CHARACTERISTICS[short_uuid]}")
        
        # Ist Base-UUID Format, aber nicht in unserer Liste
        # Könnte trotzdem Standard sein (nicht alle sind in unserer Liste)
        # Oder Custom im Bereich 0xF000-0xFFFF
        if int(short_uuid, 16) >= 0xF000:
            return (False, "Custom (wahrscheinlich hersteller-spezifisch, Bereich 0xF000-0xFFFF)")
        else:
            return (False, f"Möglicherweise Standard (nicht in unserer Liste), UUID: {short_uuid}")
    
    # Vollständige 128-Bit UUID (nicht Base-UUID Format) = immer Custom
    return (False, "Custom Service/Characteristic (vollständige 128-Bit UUID)")

def notification_handler(sender, data):
    """Wird aufgerufen, wenn Daten auf FFF3 empfangen werden"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    # Hex-Darstellung
    hex_str = ' '.join(f'{b:02X}' for b in data)
    
    # Raw Bytes
    raw_repr = repr(bytes(data))
    
    # Versuche als Zahlen zu interpretieren
    print(f"\n[{timestamp}] Daten empfangen ({len(data)} Bytes)")
    print(f"  Hex: {hex_str}")
    print(f"  Raw: {raw_repr}")
    
    # Versuche Temperatur zu dekodieren (verschiedene Formate)
    if len(data) >= 2:
        # Format 1: 16-Bit Little Endian (z.B. 0x1234 = 4660 = 46.60°C)
        temp_le = int.from_bytes(data[:2], byteorder='little', signed=False) / 100.0
        temp_le_signed = int.from_bytes(data[:2], byteorder='little', signed=True) / 100.0
        
        # Format 2: 16-Bit Big Endian
        temp_be = int.from_bytes(data[:2], byteorder='big', signed=False) / 100.0
        temp_be_signed = int.from_bytes(data[:2], byteorder='big', signed=True) / 100.0
        
        print(f"  Mögliche Temperaturen:")
        print(f"    Little Endian (unsigned): {temp_le:.2f}°C")
        print(f"    Little Endian (signed):   {temp_le_signed:.2f}°C")
        print(f"    Big Endian (unsigned):    {temp_be:.2f}°C")
        print(f"    Big Endian (signed):      {temp_be_signed:.2f}°C")
    
    print("-" * 60)

async def find_device_by_system_id():
    """Findet das Gerät anhand der System ID"""
    print("Scanne nach ThermoBeacon-Geräten...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    thermobeacons = [d for d in devices if d.name and "ThermoBeacon" in d.name]
    
    if not thermobeacons:
        return None
    
    print(f"Gefundene ThermoBeacon-Geräte: {len(thermobeacons)}")
    
    for device in thermobeacons:
        try:
            print(f"  Prüfe {device.address}...", end=" ", flush=True)
            async with BleakClient(device.address, timeout=5.0) as client:
                try:
                    system_id = await client.read_gatt_char(SYSTEM_ID_UUID)
                    if system_id == TARGET_SYSTEM_ID:
                        print("✓ Gefunden!")
                        return device.address
                    else:
                        hex_str = ' '.join(f'{b:02X}' for b in system_id)
                        print(f"System ID: {hex_str} (nicht das Ziel-Gerät)")
                except:
                    print("(System ID nicht lesbar)")
        except Exception as e:
            print(f"Fehler: {e}")
    
    return None

async def find_device_simple():
    """Findet einfach das erste ThermoBeacon-Gerät (ohne System ID Prüfung)"""
    print("Scanne nach ThermoBeacon-Geräten...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    thermobeacons = [d for d in devices if d.name and "ThermoBeacon" in d.name]
    
    if not thermobeacons:
        print("❌ Keine ThermoBeacon-Geräte gefunden!")
        return None
    
    if len(thermobeacons) == 1:
        print(f"✓ Gefunden: {thermobeacons[0].address}")
        return thermobeacons[0].address
    
    # Mehrere Geräte gefunden - zeige Liste
    print(f"\nGefundene ThermoBeacon-Geräte ({len(thermobeacons)}):")
    for i, device in enumerate(thermobeacons, 1):
        print(f"  {i}. {device.address} - {device.name}")
    
    print("\nVerwende das erste Gerät. Für spezifisches Gerät: --address verwenden")
    return thermobeacons[0].address

async def read_data(device_address=None, kick_command=None, use_system_id=False, debug_only=False, read_once=False):
    """Hauptfunktion: Verbindet sich und liest Daten"""
    
    # 1. Gerät finden
    if not device_address:
        if use_system_id:
            print("Suche Gerät anhand der System ID...")
            device_address = await find_device_by_system_id()
            if not device_address:
                print("❌ Gerät mit System ID nicht gefunden!")
                print("   Versuche einfache Suche...")
                device_address = await find_device_simple()
        else:
            device_address = await find_device_simple()
        
        if not device_address:
            print("❌ Gerät nicht gefunden!")
            print("   Tipp: Gib die BLE-Adresse mit --address an")
            return
    
    print(f"\nVerbinde mit {device_address}...")
    
    try:
        async with BleakClient(device_address) as client:
            print("✓ Verbunden!")
            
            # 2. Zeige ALLE Services und Characteristics (Debugging)
            print("\n" + "=" * 60)
            print("ALLE SERVICES UND CHARACTERISTICS:")
            print("=" * 60)
            service_found = False
            control_char = None
            data_char = None
            
            for service in client.services:
                # Prüfe ob Service Standard ist
                is_std, service_desc = is_standard_uuid(service.uuid)
                service_marker = "📋 STANDARD" if is_std else "🔧 CUSTOM"
                print(f"\n{service_marker} Service: {service.uuid}")
                print(f"  → {service_desc}")
                
                for char in service.characteristics:
                    # Prüfe ob Characteristic Standard ist
                    is_std_char, char_desc = is_standard_uuid(char.uuid)
                    char_marker = "📋" if is_std_char else "🔧"
                    char_short = char.uuid[-4:].upper() if len(char.uuid) > 4 else char.uuid
                    props = ', '.join(char.properties)
                    print(f"  {char_marker} Characteristic: {char_short}")
                    print(f"    UUID: {char.uuid}")
                    print(f"    → {char_desc}")
                    print(f"    Properties: {props}")
                    print(f"    Handle: {char.handle}")
                    
                    # Versuche Wert zu lesen (falls Read unterstützt)
                    if 'read' in char.properties:
                        try:
                            value = await client.read_gatt_char(char.uuid)
                            # Versuche als String zu dekodieren
                            try:
                                decoded = value.decode('utf-8', errors='ignore').strip('\x00').strip()
                                if decoded and all(c.isprintable() or c in '\n\r\t' for c in decoded):
                                    print(f"    Wert: \"{decoded}\"")
                                else:
                                    hex_str = ' '.join(f'{b:02X}' for b in value)
                                    print(f"    Wert (Hex): {hex_str}")
                            except:
                                hex_str = ' '.join(f'{b:02X}' for b in value)
                                print(f"    Wert (Hex): {hex_str}")
                        except Exception as e:
                            print(f"    Wert: <nicht lesbar: {e}>")
                    else:
                        print(f"    Wert: <nicht lesbar (kein 'read' Property)>")
                    
                    # Zeige Descriptors
                    if char.descriptors:
                        print(f"    Descriptors:")
                        for desc in char.descriptors:
                            print(f"      - {desc.uuid} (Handle: {desc.handle})")
                    
                    # Merke wichtige Characteristics
                    if SERVICE_UUID.lower() in service.uuid.lower():
                        service_found = True
                        if CONTROL_CHAR_UUID.lower() in char.uuid.lower():
                            control_char = char
                        if DATA_CHAR_UUID.lower() in char.uuid.lower():
                            data_char = char
            
            if not service_found:
                print("\n❌ Service FFE0 nicht gefunden!")
                return
            
            print("\n" + "=" * 60)
            print("ZUSAMMENFASSUNG:")
            print("=" * 60)
            if control_char:
                print(f"✓ Control-Char FFF5 gefunden: {', '.join(control_char.properties)}")
            else:
                print("⚠️  Control-Char FFF5 nicht gefunden!")
            
            if data_char:
                print(f"✓ Data-Char FFF3 gefunden: {', '.join(data_char.properties)}")
            else:
                print("⚠️  Data-Char FFF3 nicht gefunden!")
                return
            
            # 3. Teste READ auf FFF3 (falls möglich)
            if 'read' in data_char.properties:
                print(f"\n[TEST] Versuche FFF3 zu LESEN...")
                try:
                    data = await client.read_gatt_char(DATA_CHAR_UUID)
                    hex_str = ' '.join(f'{b:02X}' for b in data)
                    print(f"✓ Read erfolgreich: {hex_str} ({len(data)} Bytes)")
                    notification_handler(None, data)
                except Exception as e:
                    print(f"⚠️  Read fehlgeschlagen: {e}")
            
            # 4. Teste verschiedene Start-Befehle auf FFF5
            if control_char and 'write' in control_char.properties:
                test_commands = []
                if kick_command:
                    test_commands.append(("Benutzer-Befehl", kick_command))
                else:
                    # Teste verschiedene häufige Start-Befehle
                    test_commands = [
                        ("0x01", bytes([0x01])),
                        ("0x00", bytes([0x00])),
                        ("0xFF", bytes([0xFF])),
                        ("0x0100", bytes([0x01, 0x00])),
                        ("0x0001", bytes([0x00, 0x01])),
                    ]
                
                print(f"\n[TEST] Teste Start-Befehle auf FFF5:")
                for name, cmd in test_commands:
                    try:
                        print(f"  Sende {name} ({cmd.hex()})...", end=" ", flush=True)
                        await client.write_gatt_char(CONTROL_CHAR_UUID, cmd)
                        print("✓")
                        await asyncio.sleep(0.5)  # Kurz warten
                    except Exception as e:
                        print(f"✗ ({e})")
            elif not kick_command:
                print("\n⚠️  FFF5 unterstützt kein Write - kein Start-Befehl möglich")
            
            # 5. Aktiviere Notifications auf FFF3
            print(f"\n[SETUP] Aktiviere Notifications auf FFF3...")
            try:
                # Finde CCCD Descriptor
                cccd_descriptor = None
                if data_char.descriptors:
                    for desc in data_char.descriptors:
                        if "2902" in desc.uuid.lower():  # CCCD UUID
                            cccd_descriptor = desc
                            break
                
                # Versuche Notifications zu aktivieren
                await client.start_notify(DATA_CHAR_UUID, notification_handler)
                print("✓ start_notify() aufgerufen")
                
                # Prüfe und setze CCCD manuell (falls nötig)
                if cccd_descriptor:
                    try:
                        # Lese aktuellen CCCD-Wert
                        cccd_value = await client.read_gatt_descriptor(cccd_descriptor.handle)
                        cccd_int = int.from_bytes(cccd_value, byteorder='little')
                        print(f"  CCCD Wert vorher: 0x{cccd_int:04X} ({'aktiviert' if cccd_int & 0x0001 else 'deaktiviert'})")
                        
                        # Falls deaktiviert, setze manuell auf 0x0001 (Notifications)
                        if not (cccd_int & 0x0001):
                            print("  CCCD ist deaktiviert - setze manuell auf 0x0001...")
                            await client.write_gatt_descriptor(cccd_descriptor.handle, bytes([0x01, 0x00]))
                            
                            # Prüfe nochmal
                            await asyncio.sleep(0.2)
                            cccd_value = await client.read_gatt_descriptor(cccd_descriptor.handle)
                            cccd_int = int.from_bytes(cccd_value, byteorder='little')
                            print(f"  CCCD Wert nachher: 0x{cccd_int:04X} ({'aktiviert' if cccd_int & 0x0001 else 'deaktiviert'})")
                        else:
                            print("  ✓ CCCD bereits aktiviert")
                    except Exception as e:
                        print(f"  ⚠️  Konnte CCCD nicht manuell setzen: {e}")
                        print("  (start_notify sollte trotzdem funktionieren)")
                else:
                    print("  ⚠️  CCCD Descriptor nicht gefunden")
                
                print("✓ Notifications Setup abgeschlossen")
            except Exception as e:
                print(f"❌ Fehler beim Aktivieren von Notifications: {e}")
                import traceback
                traceback.print_exc()
                return
            
            # 6. Warte auf Daten (mit Timeout für Tests)
            if debug_only:
                print("\n[DEBUG-ONLY] Debug-Info angezeigt. Beende.")
                return
            
            if read_once:
                print("\n[READ-ONCE] Versuche einmalig zu lesen...")
                if 'read' in data_char.properties:
                    try:
                        data = await client.read_gatt_char(DATA_CHAR_UUID)
                        hex_str = ' '.join(f'{b:02X}' for b in data)
                        print(f"✓ Daten gelesen: {hex_str} ({len(data)} Bytes)")
                        notification_handler(None, data)
                    except Exception as e:
                        print(f"❌ Lesen fehlgeschlagen: {e}")
                else:
                    print("⚠️  FFF3 unterstützt kein Read")
                return
            
            print("\n" + "=" * 60)
            print("WARTE AUF DATEN...")
            print("=" * 60)
            print("Das Gerät sollte jetzt Daten senden.")
            print("Falls keine Daten kommen:")
            print("  - Prüfe ob das Gerät aktiv ist")
            print("  - Teste verschiedene --kick Befehle")
            print("  - Prüfe ob die App Daten sendet")
            print("  - Verwende --read-once um einmalig zu lesen")
            print("Drücke Ctrl+C zum Beenden\n")
            
            # Warte mit Heartbeat (zeigt dass Skript läuft)
            heartbeat_count = 0
            max_wait_time = 30  # Maximal 30 Sekunden warten für Test
            try:
                while heartbeat_count * 5 < max_wait_time:
                    await asyncio.sleep(5)
                    heartbeat_count += 1
                    elapsed = heartbeat_count * 5
                    if heartbeat_count % 6 == 0:  # Alle 30 Sekunden
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Warte noch... (seit {elapsed} Sekunden)")
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] ... ({elapsed}s)")
                
                print(f"\n⏱️  {max_wait_time} Sekunden abgelaufen. Beende Test.")
                print("Falls keine Daten kamen, versuche:")
                print("  - Verschiedene --kick Werte (0x01, 0x00, 0xFF)")
                print("  - Längere Wartezeit (entferne max_wait_time im Code)")
            except KeyboardInterrupt:
                pass
            
    except KeyboardInterrupt:
        print("\n\nBeende...")
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(
        description='Liest Daten vom ThermoBeacon-Gerät',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Nur Debug-Info anzeigen (alle Services/Characteristics)
  python read_thermometer_data.py --debug-only
  
  # Automatisch Gerät finden und einmalig lesen
  python read_thermometer_data.py --read-once
  
  # Mit Start-Befehl und dann warten
  python read_thermometer_data.py --kick 0x01
  
  # Mit BLE-Adresse (auf macOS UUID-Format)
  python read_thermometer_data.py --address "AC1284E0-8299-2366-EEF0-8C048CA6BF54"
  
  # Mit System ID Suche
  python read_thermometer_data.py --use-system-id
        """
    )
    
    parser.add_argument('--address', '-a', type=str,
                       help='BLE-Adresse des Geräts (optional, wird automatisch gesucht)')
    parser.add_argument('--use-system-id', action='store_true',
                       help='Suche Gerät anhand der System ID (statt erstes Gerät zu nehmen)')
    parser.add_argument('--kick', '-k', type=str,
                       help='Start-Befehl als Hex (z.B. "01" oder "0x01")')
    parser.add_argument('--debug-only', action='store_true',
                       help='Nur Debug-Info anzeigen, keine Daten lesen')
    parser.add_argument('--read-once', action='store_true',
                       help='Versuche FFF3 einmal zu lesen (falls Read unterstützt)')
    
    args = parser.parse_args()
    
    # Parse kick command
    kick_command = None
    if args.kick:
        try:
            if args.kick.startswith('0x') or args.kick.startswith('0X'):
                kick_command = bytes.fromhex(args.kick[2:])
            else:
                kick_command = bytes.fromhex(args.kick.replace(' ', ''))
        except ValueError as e:
            print(f"❌ Fehler beim Parsen von --kick: {e}")
            return
    
    asyncio.run(read_data(args.address, kick_command, args.use_system_id, args.debug_only, args.read_once))

if __name__ == "__main__":
    main()

