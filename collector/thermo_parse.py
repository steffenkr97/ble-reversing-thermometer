#!/usr/bin/env python3
"""
Reiner ThermoBeacon-Parser (kein BLE). Encoding: int16le / 16.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

TARGET_MAC = "f4:db:00:00:00:d9"
TARGET_SYSTEM_ID = bytes.fromhex("D90000000000DBF4")
COMPANY_ID = 0x001B
SCALE = 16.0

SERVICE_UUID = "0000FFE0-0000-1000-8000-00805f9b34fb"
CONTROL_CHAR_UUID = "0000FFF5-0000-1000-8000-00805f9b34fb"
DATA_CHAR_UUID = "0000FFF3-0000-1000-8000-00805f9b34fb"
SYSTEM_ID_UUID = "00002A23-0000-1000-8000-00805f9b34fb"

_ADV_LIVE_LEN = 20
_FFF3_LEN = 20
_MAC_LEN = 6
_OPCODE_1A = 0x1A
_OPCODE_01 = 0x01
_OPCODE_07 = 0x07
_OPCODE_F3 = 0xF3


@dataclass(frozen=True)
class AdvLive:
    """Live-Werte aus 20-Byte ADV Manufacturer Data."""

    temp_c: float
    humidity_rh: float
    battery_mv: int
    counter: int
    mac: str
    raw_hex: str


@dataclass(frozen=True)
class Status1A:
    """Status-Echo auf Write 1A; kein Messwert."""

    raw_hex: str


@dataclass(frozen=True)
class Count01:
    """Sample-Count aus Notify 01 (Form A/B). Kein Live-°C."""

    sample_count: int
    raw_hex: str


@dataclass(frozen=True)
class History07:
    """History-Page aus Notify 07."""

    index: int
    count: int
    records: List[Tuple[float, float]]
    raw_hex: str


def i16le_div16(data: bytes, offset: int) -> float:
    """int16 little-endian ab offset, geteilt durch SCALE (16)."""
    return int.from_bytes(data[offset : offset + 2], "little", signed=True) / SCALE


def _mac_le_to_str(mac_le: bytes) -> str:
    return ":".join("{:02x}".format(b) for b in reversed(mac_le))


def _target_mac_le() -> bytes:
    parts = TARGET_MAC.split(":")
    return bytes(int(p, 16) for p in reversed(parts))


def parse_adv_manufacturer(mfg: bytes) -> Optional[AdvLive]:
    """
    20-Byte-Live-ADV parsen. 22-Byte-Min/Max, fremde Company/MAC → None.
    """
    if len(mfg) != _ADV_LIVE_LEN:
        return None
    company = int.from_bytes(mfg[0:2], "little", signed=False)
    if company != COMPANY_ID:
        return None
    mac_le = mfg[4:10]
    if len(mac_le) != _MAC_LEN or mac_le != _target_mac_le():
        return None
    battery_mv = int.from_bytes(mfg[10:12], "little", signed=False)
    temp_c = i16le_div16(mfg, 12)
    humidity_rh = i16le_div16(mfg, 14)
    counter = int.from_bytes(mfg[16:20], "little", signed=False)
    return AdvLive(
        temp_c=temp_c,
        humidity_rh=humidity_rh,
        battery_mv=battery_mv,
        counter=counter,
        mac=_mac_le_to_str(mac_le),
        raw_hex=mfg.hex(),
    )


def _parse_history_07(data: bytes) -> Optional[History07]:
    index = int.from_bytes(data[1:3], "little", signed=False)
    count = data[5]
    records = []  # type: List[Tuple[float, float]]
    if count == 3:
        for i in range(3):
            temp_c = i16le_div16(data, 6 + i * 2)
            humidity_rh = i16le_div16(data, 12 + i * 2)
            records.append((temp_c, humidity_rh))
    elif count == 1:
        # Ein Paar: t0 Offset 6, h0 Offset 8 — nicht Hum an Offset 12.
        records.append((i16le_div16(data, 6), i16le_div16(data, 8)))
    else:
        return None
    return History07(
        index=index,
        count=count,
        records=records,
        raw_hex=data.hex(),
    )


def parse_fff3(data: bytes) -> Optional[Union[Status1A, Count01, History07]]:
    """
    20-Byte-FFF3-Notify. Unbekannt und Opcode F3 → None.
    Form-B-Records bei 01 nicht als Live parsen.
    """
    if len(data) != _FFF3_LEN:
        return None
    opcode = data[0]
    if opcode == _OPCODE_F3:
        return None
    if opcode == _OPCODE_1A:
        return Status1A(raw_hex=data.hex())
    if opcode == _OPCODE_01:
        sample_count = int.from_bytes(data[1:3], "little", signed=False)
        return Count01(sample_count=sample_count, raw_hex=data.hex())
    if opcode == _OPCODE_07:
        return _parse_history_07(data)
    return None


def build_history_07_write(index: int, count: int = 3) -> bytes:
    """Write-Payload 6 Byte: 07 <u16le index> 00 00 <count>."""
    return b"\x07" + index.to_bytes(2, "little") + b"\x00\x00" + bytes([count & 0xFF])
