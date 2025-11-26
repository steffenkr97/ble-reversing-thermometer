#!/usr/bin/env python3
import asyncio

from bleak import BleakClient, BleakScanner

DEVICE_ADDRESS = "8277B476-C20F-BC82-678E-540BEC258660"
DEFAULT_SERVICE_UUID = "0000FFE0-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "0000FFF5-0000-1000-8000-00805f9b34fb"  # write
DATA_CHAR_UUID    = "0000FFF3-0000-1000-8000-00805f9b34fb"  # notify
## siehe csv
KICK = (bytes([0x01]))

async def main():
    print("Searching Devices")
    devices = await BleakScanner.discover(timeout=10)
    print(f"{len(devices)} devices found")

    # for device in devices:
    #     system_id = await device.
    #     print(f"{device.address}")
    #     if  device.address == DEVICE_ADDRESS:
    #         print(f"{device.name}")
    #         target_device_address = device.address




    print("Connecting...")

    async with BleakClient(DEVICE_ADDRESS, timeout=15.0) as client:
        if not client.is_connected:
            print("Could not connect to device")
            return

    print("Connected to device {}".format(DEVICE_ADDRESS))

    print("Write to FFF5: {}".format(str(KICK)))
    await  client.write_gatt_char(CONTROL_CHAR_UUID, KICK)

    await asyncio.sleep(1)

    data = await client.read_gatt_char(CONTROL_CHAR_UUID)
    print("Read from FFF5: {}".format(str(data)))

if __name__ == "__main__":
    asyncio.run(main())