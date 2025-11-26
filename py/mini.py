#!/usr/bin/env python3
import asyncio
from bleak import BleakScanner

async def scan():
    print("Scanne 10 Sekunden...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    for device in devices:
        # device.address ist die BLE-Adresse (auf Mac als UUID, auf Linux als MAC)
        address = device.address
        name = device.name or 'Unbekannt'
        rssi = device.rssi if hasattr(device, 'rssi') else 'N/A'
        
        print(f"{address} - {name} (RSSI: {rssi} dBm)")

asyncio.run(scan())