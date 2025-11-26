Dies scheint das korrekte Gerät zu sein.

Folgende Daten 

```c
[07:00:40.2380] Normal: Scanner On.
[07:00:40.6680] Normal: Device Scanned.
[07:00:40.6700] Normal: -29 dBm
[07:00:40.6700] Normal: 430.73 ms
[07:00:41.5150] Normal: -30 dBm
[07:00:41.5150] Normal: 845.36 ms
[07:00:43.2100] Normal: -29 dBm
[07:00:43.2100] Normal: 1695.29 ms
[07:00:44.0560] Normal: -29 dBm
[07:00:44.0560] Normal: 845.40 ms
[07:00:44.9050] Normal: -30 dBm
[07:00:44.9050] Normal: 847.69 ms
[07:00:45.7510] Normal: -30 dBm
[07:00:45.7510] Normal: 847.48 ms
[07:00:47.4440] Normal: -29 dBm
[07:00:47.4440] Normal: 1693.36 ms
[07:00:48.2910] Normal: -29 dBm
[07:00:48.2910] Normal: 847.07 ms
[07:00:49.1390] Normal: -30 dBm
[07:00:49.1390] Normal: 848.07 ms
[07:00:49.9870] Normal: -30 dBm
[07:00:49.9880] Normal: 847.82 ms
[07:00:52.5290] Normal: -22 dBm
[07:00:52.5290] Normal: 2541.40 ms
[07:00:53.3730] Normal: -23 dBm
[07:00:53.3730] Normal: 844.71 ms
[07:00:54.2190] Normal: -23 dBm
[07:00:54.2190] Normal: 845.78 ms
[07:00:55.0670] Normal: -23 dBm
[07:00:55.0670] Normal: 847.47 ms
[07:00:57.6070] Normal: -22 dBm
[07:00:57.6070] Normal: 2540.89 ms
[07:00:58.4540] Normal: -21 dBm
[07:00:58.4540] Normal: 846.86 ms
[07:00:59.3010] Normal: -22 dBm
[07:00:59.3010] Normal: 846.25 ms
[07:01:00.9960] Normal: -22 dBm
[07:01:00.9960] Normal: 1695.28 ms
[07:01:04.3850] Normal: -21 dBm
[07:01:04.3850] Normal: 3389.21 ms
[07:01:05.2500] Normal: -20 dBm
[07:01:05.2510] Normal: 847.66 ms
[07:01:05.2940] Normal: Connected.
[07:01:05.6490] Normal: Discovered Device Information and FFE0 Services.
[07:01:05.8320] Normal: Discovered System ID, Model Number String, Serial Number String, Firmware Revision String, Hardware Revision String, Software Revision String, Manufacturer Name String, IEEE 11073-20601 Regulatory Certification Data List, and PnP ID Characteristics for Service Device Information.
[07:01:05.9480] Normal: Discovered FFF5 and FFF3 Characteristics for Service FFE0.
[07:01:05.9480] Normal: System ID has no Descriptors.
[07:01:05.9490] Normal: Model Number String has no Descriptors.
[07:01:05.9490] Normal: Serial Number String has no Descriptors.
[07:01:05.9490] Normal: Firmware Revision String has no Descriptors.
[07:01:05.9500] Normal: Hardware Revision String has no Descriptors.
[07:01:05.9500] Normal: Software Revision String has no Descriptors.
[07:01:05.9500] Normal: Manufacturer Name String has no Descriptors.
[07:01:05.9510] Normal: IEEE 11073-20601 Regulatory Certification Data List has no Descriptors.
[07:01:05.9510] Normal: PnP ID has no Descriptors.
[07:01:06.0070] Normal: FFF5 has no Descriptors.
[07:01:06.1290] Normal: Discovered Client Characteristic Configuration Descriptors for Characteristic FFF3
[07:02:17.2120] Normal: Updated Value of Characteristic 2A23 to D900 0000 0000 DBF4.
[07:02:17.2120] Application: "D900 0000 0000 DBF4" value received.
[07:02:40.2420] Normal: Scanner Off.
[07:02:52.8530] Normal: Updated Value of Characteristic 2A24 to 4D6F 6465 6C20 4E75 6D62 6572.
[07:02:52.8530] Application: "Model Number" value received.
[07:03:09.0530] Normal: Updated Value of Characteristic 2A29 to 4D61 6E75 6661 6374 7572 6572 204E 616D 65.
[07:03:09.0530] Application: "Manufacturer Name" value received.
```

## Interpretation der Daten

Die Relevanten Daten werden voraussichtlich auf `FFF3` stehen. 

Service: FFE0
Control-Char (vermutlich): FFF5 (Write / ggf. „Start“)
Data-Char: FFF3 (Notify) → hier sollten die Messwerte/Logs als RAW-Bytes eintrudeln.
Das deckt sich mit vielen günstigen BLE-Thermometern: „FFF5 start → FFF3 notify“.


## Rückfragen:

- Warum meistens: `0000FFE0-0000-1000-8000-00805f9b34fb` ist das ein Fester Wert?
- Sind die Einträge wie z.b. `2A23 System ID` 2A23 standard durch das DIS oder woher weißt du das hier?
- 


----

Neues Log aus der APp 

[13:17:10.9710] Normal: Scanner On.
[13:17:11.5220] Normal: Device Scanned.
[13:17:11.5230] Normal: -33 dBm
[13:17:11.5230] Normal: 550.81 ms
[13:17:14.0630] Normal: -26 dBm
[13:17:14.0630] Normal: 2539.57 ms
[13:17:14.9140] Normal: -25 dBm
[13:17:14.9140] Normal: 852.24 ms
[13:17:15.7590] Normal: -15 dBm
[13:17:15.7590] Normal: 844.84 ms
[13:17:17.4550] Normal: -21 dBm
[13:17:17.4550] Normal: 1695.88 ms
[13:17:18.3000] Normal: -14 dBm
[13:17:18.3000] Normal: 844.57 ms
[13:17:20.8430] Normal: -14 dBm
[13:17:20.8430] Normal: 2543.68 ms
[13:17:21.6880] Normal: -15 dBm
[13:17:21.6890] Normal: 845.06 ms
[13:17:22.5380] Normal: -15 dBm
[13:17:22.5380] Normal: 849.82 ms
[13:17:23.3850] Normal: -14 dBm
[13:17:23.3850] Normal: 846.49 ms
[13:17:24.2340] Normal: -14 dBm
[13:17:24.2340] Normal: 849.35 ms
[13:17:25.0790] Normal: -13 dBm
[13:17:25.0790] Normal: 845.79 ms
[13:17:25.9300] Normal: -21 dBm
[13:17:25.9300] Normal: 849.82 ms
[13:17:26.7750] Normal: -13 dBm
[13:17:26.7750] Normal: 845.52 ms
[13:17:27.6230] Normal: -13 dBm
[13:17:27.6230] Normal: 847.72 ms
[13:17:28.4720] Normal: -13 dBm
[13:17:28.4720] Normal: 848.84 ms
[13:17:28.4720] Normal: -13 dBm
[13:17:28.4720] Normal: 849.08 ms
[13:17:30.1620] Normal: -14 dBm
[13:17:30.1620] Normal: 1690.42 ms
[13:17:31.0120] Normal: -14 dBm
[13:17:31.0120] Normal: 850.00 ms
[13:17:31.8590] Normal: -15 dBm
[13:17:31.8590] Normal: 846.72 ms
[13:17:32.7060] Normal: -14 dBm
[13:17:32.7070] Normal: 847.27 ms
[13:17:36.9400] Normal: -27 dBm
[13:17:36.9400] Normal: 4233.31 ms
[13:17:37.7870] Normal: -22 dBm
[13:17:37.7870] Normal: 847.60 ms
[13:17:38.6340] Normal: -24 dBm
[13:17:38.6340] Normal: 847.23 ms
[13:17:39.4820] Normal: -21 dBm
[13:17:39.4820] Normal: 847.97 ms
[13:17:41.1770] Normal: -23 dBm
[13:17:41.1770] Normal: 1694.15 ms
[13:17:41.2340] Normal: Connected.
[13:17:41.6130] Normal: Discovered Device Information and FFE0 Services.
[13:17:41.8310] Normal: Discovered System ID, Model Number String, Serial Number String, Firmware Revision String, Hardware Revision String, Software Revision String, Manufacturer Name String, IEEE 11073-20601 Regulatory Certification Data List, and PnP ID Characteristics for Service Device Information.
[13:17:41.9450] Normal: Discovered FFF5 and FFF3 Characteristics for Service FFE0.
[13:17:41.9450] Normal: System ID has no Descriptors.
[13:17:41.9460] Normal: Model Number String has no Descriptors.
[13:17:41.9460] Normal: Serial Number String has no Descriptors.
[13:17:41.9460] Normal: Firmware Revision String has no Descriptors.
[13:17:41.9460] Normal: Hardware Revision String has no Descriptors.
[13:17:41.9470] Normal: Software Revision String has no Descriptors.
[13:17:41.9470] Normal: Manufacturer Name String has no Descriptors.
[13:17:41.9480] Normal: IEEE 11073-20601 Regulatory Certification Data List has no Descriptors.
[13:17:41.9480] Normal: PnP ID has no Descriptors.
[13:17:42.0060] Normal: FFF5 has no Descriptors.
[13:17:42.1240] Normal: Discovered Client Characteristic Configuration Descriptors for Characteristic FFF3
[13:18:10.5950] Normal: Disconnected.
[13:18:12.5090] Normal: -38 dBm
[13:18:12.5090] Normal: 31332.12 ms
[13:18:13.3550] Normal: -36 dBm
[13:18:13.3550] Normal: 845.75 ms
[13:18:14.2040] Normal: -36 dBm
[13:18:14.2040] Normal: 848.80 ms
[13:18:15.0520] Normal: -36 dBm
[13:18:15.0520] Normal: 848.80 ms
[13:18:17.5930] Normal: -61 dBm
[13:18:17.5930] Normal: 2540.82 ms
[13:18:17.5930] Normal: -61 dBm
[13:18:17.5930] Normal: 2540.99 ms
[13:19:37.0980] Normal: Scanner Off.
[13:19:39.8380] Normal: Connected.
[13:19:40.1760] Normal: Discovered Device Information and FFE0 Services.
[13:19:40.3600] Normal: Discovered System ID, Model Number String, Serial Number String, Firmware Revision String, Hardware Revision String, Software Revision String, Manufacturer Name String, IEEE 11073-20601 Regulatory Certification Data List, and PnP ID Characteristics for Service Device Information.
[13:19:40.4790] Normal: Discovered FFF5 and FFF3 Characteristics for Service FFE0.
[13:19:40.4790] Normal: System ID has no Descriptors.
[13:19:40.4790] Normal: Model Number String has no Descriptors.
[13:19:40.4800] Normal: Serial Number String has no Descriptors.
[13:19:40.4800] Normal: Firmware Revision String has no Descriptors.
[13:19:40.4810] Normal: Hardware Revision String has no Descriptors.
[13:19:40.4810] Normal: Software Revision String has no Descriptors.
[13:19:40.4820] Normal: Manufacturer Name String has no Descriptors.
[13:19:40.4820] Normal: IEEE 11073-20601 Regulatory Certification Data List has no Descriptors.
[13:19:40.4830] Normal: PnP ID has no Descriptors.
[13:19:40.5370] Normal: FFF5 has no Descriptors.
[13:19:40.6580] Normal: Discovered Client Characteristic Configuration Descriptors for Characteristic FFF3
[13:20:18.2490] Normal: Changed Data Parser for Characteristic FFF5 to ThingyTemperatureParser
[13:20:18.2490] Application: Data Parser for FFF5 Characteristic set to Thingy:52 Temperature
[13:20:45.3990] Normal: Updated Value of Characteristic 2A23 to D900 0000 0000 DBF4.
[13:20:45.3990] Application: "D900 0000 0000 DBF4" value received.
[13:22:28.2060] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:28.2060] Application: "Serial Number" value received.
[13:22:29.4440] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:29.4440] Application: "Serial Number" value received.
[13:22:30.2540] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:30.2540] Application: "Serial Number" value received.
[13:22:31.1540] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:31.1540] Application: "Serial Number" value received.
[13:22:31.3360] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:31.3360] Application: "Serial Number" value received.
[13:22:31.6040] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:31.6040] Application: "Serial Number" value received.
[13:22:31.7850] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:31.7850] Application: "Serial Number" value received.
[13:22:31.9640] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:31.9640] Application: "Serial Number" value received.
[13:22:32.1440] Normal: Updated Value of Characteristic 2A25 to 5365 7269 616C 204E 756D 6265 72.
[13:22:32.1440] Application: "Serial Number" value received.
[13:22:33.2240] Normal: Updated Value of Characteristic 2A24 to 4D6F 6465 6C20 4E75 6D62 6572.
[13:22:33.2240] Application: "Model Number" value received.
[13:22:33.8540] Normal: Updated Value of Characteristic 2A24 to 4D6F 6465 6C20 4E75 6D62 6572.
[13:22:33.8540] Application: "Model Number" value received.
[13:22:34.3040] Normal: Updated Value of Characteristic 2A24 to 4D6F 6465 6C20 4E75 6D62 6572.
[13:22:34.3040] Application: "Model Number" value received.
[13:22:39.4370] Normal: Updated Value of Characteristic 2A26 to 4669 726D 7761 7265 2052 6576 6973 696F 6E.
[13:22:39.4370] Application: "Firmware Revision" value received.
[13:22:42.6740] Normal: Updated Value of Characteristic 2A27 to 4861 7264 7761 7265 2052 6576 6973 696F 6E.
[13:22:42.6740] Application: "Hardware Revision" value received.
[13:22:48.1670] Normal: Updated Value of Characteristic 2A29 to 4D61 6E75 6661 6374 7572 6572 204E 616D 65.
[13:22:48.1670] Application: "Manufacturer Name" value received.
[13:22:54.0140] Normal: Updated Value of Characteristic 2A50 to 0104 0500 0010 01.
[13:22:54.0140] Application: "0104 0500 0010 01" value received.
[13:22:56.3480] Application: Setting Boolean true for Notifying Characteristic FFF3
[13:23:00.5140] Application: Setting Boolean false for Notifying Characteristic FFF3
[13:23:04.1320] Application: Setting Boolean true for Notifying Characteristic FFF3
[13:23:48.5070] Application: Setting Boolean false for Notifying Characteristic FFF3
[13:24:06.2860] Normal: Disconnected.
[13:30:47.2570] Normal: Connected.
[13:30:47.6430] Normal: Discovered Device Information and FFE0 Services.
[13:30:47.8590] Normal: Discovered System ID, Model Number String, Serial Number String, Firmware Revision String, Hardware Revision String, Software Revision String, Manufacturer Name String, IEEE 11073-20601 Regulatory Certification Data List, and PnP ID Characteristics for Service Device Information.
[13:30:47.9750] Normal: Discovered FFF5 and FFF3 Characteristics for Service FFE0.
[13:30:47.9750] Normal: System ID has no Descriptors.
[13:30:47.9750] Normal: Model Number String has no Descriptors.
[13:30:47.9760] Normal: Serial Number String has no Descriptors.
[13:30:47.9760] Normal: Firmware Revision String has no Descriptors.
[13:30:47.9760] Normal: Hardware Revision String has no Descriptors.
[13:30:47.9770] Normal: Software Revision String has no Descriptors.
[13:30:47.9770] Normal: Manufacturer Name String has no Descriptors.
[13:30:47.9780] Normal: IEEE 11073-20601 Regulatory Certification Data List has no Descriptors.
[13:30:47.9780] Normal: PnP ID has no Descriptors.
[13:30:48.0340] Normal: FFF5 has no Descriptors.
[13:30:48.1550] Normal: Discovered Client Characteristic Configuration Descriptors for Characteristic FFF3


# Dokumentation

## Mein Gerät im Büro

Mac Adresse: f4:db:00:00:00:d9
BLE UUID:  8277B476-C20F-BC82-678E-540BEC258660


## Debug script

- Verbinden geht
- Services virhanden
  - FFE0 
  - FFF5 Control (write)
  - FFF3 Data (notify)
  
