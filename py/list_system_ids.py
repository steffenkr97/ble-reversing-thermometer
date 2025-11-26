#!/usr/bin/env python3
"""
Listet alle ThermoBeacon-Geräte und liest deren System ID (2A23) aus
Speichert die Ergebnisse in einer CSV-Datei
"""
import asyncio
import csv
import argparse
from datetime import datetime
from bleak import BleakScanner, BleakClient

# Bluetooth SIG Base UUID für 16-Bit UUIDs
BLE_BASE_UUID = "0000{}-0000-1000-8000-00805f9b34fb"

def get_standard_uuid(short_uuid: str) -> str:
    """
    Konvertiert eine 16-Bit UUID (z.B. "2A23") in die vollständige 128-Bit UUID.
    
    Args:
        short_uuid: 16-Bit UUID als Hex-String (z.B. "2A23" oder "2A24")
    
    Returns:
        Vollständige 128-Bit UUID
    """
    return BLE_BASE_UUID.format(short_uuid.upper())

# UUID für System ID (2A23) im Device Information Service
SYSTEM_ID_UUID = get_standard_uuid("2A23")

async def read_system_id(client):
    """Liest die System ID (2A23) vom Gerät"""
    try:
        data = await client.read_gatt_char(SYSTEM_ID_UUID)
        return data
    except Exception as e:
        return None

async def read_all_device_info(client):
    """Liest alle verfügbaren Device Information Characteristics"""
    device_info = {}
    
    # Standard Device Information Service Characteristics
    # Verwendet die Helper-Funktion für bessere Lesbarkeit
    characteristics = {
        "2A23": get_standard_uuid("2A23"),  # System ID
        "2A24": get_standard_uuid("2A24"),  # Model Number
        "2A25": get_standard_uuid("2A25"),  # Serial Number
        "2A26": get_standard_uuid("2A26"),  # Firmware Revision
        "2A27": get_standard_uuid("2A27"),  # Hardware Revision
        "2A28": get_standard_uuid("2A28"),  # Software Revision
        "2A29": get_standard_uuid("2A29"),  # Manufacturer Name
    }
    
    for name, uuid in characteristics.items():
        try:
            data = await client.read_gatt_char(uuid)
            if data:
                # Versuche als String zu dekodieren, sonst als Hex
                try:
                    decoded = data.decode('utf-8', errors='ignore').strip('\x00')
                    if decoded and all(c.isprintable() for c in decoded):
                        device_info[name] = decoded
                    else:
                        device_info[name] = data.hex().upper()
                except:
                    device_info[name] = data.hex().upper()
        except:
            pass  # Characteristic nicht verfügbar
    
    return device_info

async def test_device(device):
    """Testet ein Gerät und liest die System ID und andere Device Info"""
    result = {
        "address": device.address,
        "name": device.name or "Unbekannt",
        "rssi": device.rssi if hasattr(device, 'rssi') else None,
        "system_id": None,
        "error": None,
        "device_info": {}
    }
    
    try:
        print(f"  Verbinde mit {device.address}...", end=" ", flush=True)
        async with BleakClient(device.address, timeout=5.0) as client:
            print("✓", end=" ", flush=True)
            
            # Lese System ID
            system_id = await read_system_id(client)
            if system_id:
                hex_str = ' '.join(f'{b:02X}' for b in system_id)
                result["system_id"] = hex_str
                result["system_id_bytes"] = system_id
                print(f"System ID: {hex_str}")
            else:
                print("(System ID nicht lesbar)")
            
            # Lese weitere Device Info
            print("  Lese weitere Device Information...", end=" ", flush=True)
            device_info = await read_all_device_info(client)
            result["device_info"] = device_info
            if device_info:
                print(f"✓ ({len(device_info)} Characteristics)")
            else:
                print("(keine weiteren Infos)")
            
    except Exception as e:
        error_msg = str(e)
        result["error"] = error_msg
        print(f"✗ Fehler: {error_msg}")
    
    return result

def save_to_csv(results, filename):
    """Speichert die Ergebnisse in einer CSV-Datei"""
    if not results:
        print("Keine Daten zum Speichern.")
        return
    
    # Definiere Spalten
    fieldnames = [
        'Name',
        'Adresse',
        'RSSI (dBm)',
        'System ID (2A23)',
        'Model Number (2A24)',
        'Serial Number (2A25)',
        'Firmware Revision (2A26)',
        'Hardware Revision (2A27)',
        'Software Revision (2A28)',
        'Manufacturer Name (2A29)',
        'Fehler'
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for result in results:
            row = {
                'Name': result['name'],
                'Adresse': result['address'],
                'RSSI (dBm)': result['rssi'] if result['rssi'] is not None else '',
                'System ID (2A23)': result['system_id'] or '',
                'Model Number (2A24)': result['device_info'].get('2A24', ''),
                'Serial Number (2A25)': result['device_info'].get('2A25', ''),
                'Firmware Revision (2A26)': result['device_info'].get('2A26', ''),
                'Hardware Revision (2A27)': result['device_info'].get('2A27', ''),
                'Software Revision (2A28)': result['device_info'].get('2A28', ''),
                'Manufacturer Name (2A29)': result['device_info'].get('2A29', ''),
                'Fehler': result['error'] or ''
            }
            writer.writerow(row)
    
    print(f"\n✓ Ergebnisse gespeichert in: {filename}")

async def main(output_file):
    print("Scanne nach ThermoBeacon-Geräten...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    thermobeacons = [d for d in devices if d.name and "ThermoBeacon" in d.name]
    
    if not thermobeacons:
        print("Keine ThermoBeacon-Geräte gefunden!")
        return
    
    print(f"\nGefundene ThermoBeacon-Geräte: {len(thermobeacons)}\n")
    print("=" * 80)
    
    results = []
    
    for i, device in enumerate(thermobeacons, 1):
        print(f"\n[{i}/{len(thermobeacons)}] {device.name}")
        print(f"  Adresse: {device.address}")
        if hasattr(device, 'rssi'):
            print(f"  RSSI: {device.rssi} dBm")
        
        result = await test_device(device)
        results.append(result)
        
        print("-" * 80)
    
    # Zusammenfassung
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['name']}")
        print(f"   Adresse: {result['address']}")
        if result['rssi']:
            print(f"   RSSI: {result['rssi']} dBm")
        
        if result['system_id']:
            print(f"   System ID (2A23): {result['system_id']}")
        else:
            print(f"   System ID (2A23): <nicht lesbar>")
        
        if result['error']:
            print(f"   Fehler: {result['error']}")
        
        if result['device_info']:
            print(f"   Weitere Device Information:")
            for key, value in result['device_info'].items():
                if key != "2A23":  # System ID schon oben angezeigt
                    print(f"     - {key}: {value}")
    
    # Markiere das Gerät mit der bekannten System ID
    target_system_id = bytes.fromhex("D90000000000DBF4")
    print("\n" + "=" * 80)
    print("DEIN GERÄT (System ID: D9 00 00 00 00 00 DB F4):")
    print("=" * 80)
    
    found = False
    for result in results:
        if result.get('system_id_bytes') == target_system_id:
            print(f"\n✓ {result['name']}")
            print(f"  Adresse: {result['address']}")
            print(f"  System ID: {result['system_id']}")
            found = True
    
    if not found:
        print("\n❌ Gerät mit dieser System ID nicht gefunden!")
    
    # Speichere in CSV
    save_to_csv(results, output_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Listet ThermoBeacon-Geräte und speichert in CSV')
    parser.add_argument('--output', '-o', type=str, 
                       default=f'thermobeacon_devices_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
                       help='CSV-Ausgabedatei (Standard: automatisch generierter Name)')
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.output))
    except KeyboardInterrupt:
        print("\n\nAbgebrochen.")

