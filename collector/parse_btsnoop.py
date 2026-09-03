#!/usr/bin/env python3
"""btsnoop/H4-Parser für ThermoBeacon-HCI-Captures (.cfa).

Liest Android-btsnoop (Datalink 1002, HCI UART H4). Keine BLE-Writes.
Nur Auswertung vorhandener Captures.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

MAGIC = b"btsnoop\0"
DATALINK_H4 = 1002
BTSNOOP_EPOCH_DELTA = 0x00DCDDB30F2F8000  # µs year-0 → Unix epoch

H4_CMD, H4_ACL, H4_SCO, H4_EVT = 0x01, 0x02, 0x03, 0x04

ATT_CID = 0x0004
ATT_WRITE_REQ = 0x12
ATT_WRITE_CMD = 0x52
ATT_WRITE_RSP = 0x13
ATT_NOTIFY = 0x1B
ATT_INDICATE = 0x1D
ATT_MTU_REQ, ATT_MTU_RSP = 0x02, 0x03
ATT_READ_BY_TYPE_REQ, ATT_READ_BY_TYPE_RSP = 0x08, 0x09
ATT_READ_BY_GROUP_REQ, ATT_READ_BY_GROUP_RSP = 0x10, 0x11
ATT_FIND_INFO_REQ, ATT_FIND_INFO_RSP = 0x04, 0x05
ATT_READ_REQ, ATT_READ_RSP = 0x0A, 0x0B

UUID_PRIMARY = 0x2800
UUID_CHAR_DECL = 0x2803
UUID_CCCD = 0x2902
UUID_FFE0 = 0xFFE0
UUID_FFF3 = 0xFFF3
UUID_FFF5 = 0xFFF5

HCI_EVENT_DISCONN = 0x05
HCI_EVENT_LE_META = 0x3E
LE_CONN_COMPLETE = 0x01
LE_ADV_REPORT = 0x02
LE_ENHANCED_CONN = 0x0A

TARGET_MAC = "f4:db:00:00:00:d9"

ATT_NAMES = {
    0x01: "ErrorRsp",
    0x02: "MTU-Req",
    0x03: "MTU-Rsp",
    0x04: "FindInfo-Req",
    0x05: "FindInfo-Rsp",
    0x06: "FindByType-Req",
    0x07: "FindByType-Rsp",
    0x08: "ReadByType-Req",
    0x09: "ReadByType-Rsp",
    0x0A: "Read-Req",
    0x0B: "Read-Rsp",
    0x0C: "ReadBlob-Req",
    0x0D: "ReadBlob-Rsp",
    0x10: "ReadByGrp-Req",
    0x11: "ReadByGrp-Rsp",
    0x12: "Write-Req",
    0x13: "Write-Rsp",
    0x16: "PrepWrite-Req",
    0x17: "PrepWrite-Rsp",
    0x18: "ExecWrite-Req",
    0x19: "ExecWrite-Rsp",
    0x1B: "Notify",
    0x1D: "Indicate",
    0x1E: "Confirm",
    0x52: "Write-Cmd",
}

ADV_EVENT_NAMES = {
    0x00: "ADV_IND",
    0x01: "ADV_DIRECT_IND",
    0x02: "ADV_SCAN_IND",
    0x03: "ADV_NONCONN_IND",
    0x04: "SCAN_RSP",
}

AD_TYPE_NAMES = {
    0x01: "Flags",
    0x02: "IncUUIDs16",
    0x03: "CmpUUIDs16",
    0x08: "ShortName",
    0x09: "Name",
    0x0A: "TxPower",
    0x12: "SlaveConnInterval",
    0x16: "ServiceData16",
    0x19: "Appearance",
    0xFF: "Manufacturer",
}


def u16le(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o : o + 2], "little")


def u16be(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o : o + 2], "big")


def u32be(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o : o + 4], "big")


def u64be(b: bytes, o: int = 0) -> int:
    return int.from_bytes(b[o : o + 8], "big")


def hex_of(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def mac_from_le(addr: bytes) -> str:
    return ":".join(f"{x:02x}" for x in addr[::-1])


def mac_norm(s: str) -> str:
    return s.lower().replace("-", ":")


def ts_iso(us_since_year0: int) -> str:
    unix_us = us_since_year0 - BTSNOOP_EPOCH_DELTA
    # Captures with unset clock (2018_01_01 in filename) still convert.
    sec = unix_us / 1_000_000.0
    try:
        dt = datetime.fromtimestamp(sec, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except (OverflowError, OSError, ValueError):
        return str(us_since_year0)


def parse_ad_structures(data: bytes) -> List[Tuple[int, bytes]]:
    out: List[Tuple[int, bytes]] = []
    i = 0
    while i < len(data):
        ln = data[i]
        if ln == 0:
            break
        if i + 1 + ln > len(data):
            break
        ad_type = data[i + 1]
        val = data[i + 2 : i + 1 + ln]
        out.append((ad_type, val))
        i += 1 + ln
    return out


@dataclass
class SnoopRecord:
    index: int
    orig_len: int
    incl_len: int
    flags: int
    timestamp_raw: int
    timestamp: str
    direction: str  # sent | recv
    h4_type: int
    payload: bytes


@dataclass
class AttPdu:
    rec: int
    timestamp: str
    direction: str
    conn: int
    peer: str
    opcode: int
    opcode_name: str
    handle: Optional[int]
    value: bytes
    raw: bytes


@dataclass
class AdvReport:
    rec: int
    timestamp: str
    event_type: int
    event_name: str
    addr_type: int
    mac: str
    rssi: int
    data: bytes
    ads: List[Tuple[int, bytes]]


@dataclass
class CharDecl:
    decl_handle: int
    properties: int
    value_handle: int
    uuid16: Optional[int]
    uuid_hex: str


@dataclass
class Capture:
    path: Path
    version: int
    datalink: int
    size: int
    records: int = 0
    strings_hint: List[str] = field(default_factory=list)
    conn_peer: Dict[int, str] = field(default_factory=dict)
    att: List[AttPdu] = field(default_factory=list)
    adv: List[AdvReport] = field(default_factory=list)
    chars: List[CharDecl] = field(default_factory=list)
    services: List[Tuple[int, int, str]] = field(default_factory=list)
    le_conns: List[Tuple[str, int, str]] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


def iter_snoop_records(data: bytes) -> Iterator[SnoopRecord]:
    if data[:8] != MAGIC:
        raise ValueError("kein btsnoop-Magic")
    version = u32be(data, 8)
    datalink = u32be(data, 12)
    if version != 1:
        raise ValueError(f"unbekannte btsnoop-Version {version}")
    i = 16
    idx = 0
    n = len(data)
    while i + 24 <= n:
        orig = u32be(data, i)
        incl = u32be(data, i + 4)
        flags = u32be(data, i + 8)
        ts = u64be(data, i + 16)
        i += 24
        if incl < 0 or i + incl > n:
            break
        pkt = data[i : i + incl]
        i += incl
        idx += 1
        if not pkt:
            continue
        # bit0: 0 = host→controller (sent), 1 = controller→host (recv)
        direction = "recv" if (flags & 0x01) else "sent"
        yield SnoopRecord(
            index=idx,
            orig_len=orig,
            incl_len=incl,
            flags=flags,
            timestamp_raw=ts,
            timestamp=ts_iso(ts),
            direction=direction,
            h4_type=pkt[0],
            payload=pkt[1:],
        )
    _ = datalink


def extract_ascii_hints(data: bytes) -> List[str]:
    interesting = (
        b"OnePlus",
        b"oneplus",
        b"ThermoBeacon",
        b"Android",
        b"btsnoop",
        b"Qualcomm",
        b"BlueDroid",
    )
    found = []
    for needle in interesting:
        if needle.lower() in data.lower():
            found.append(needle.decode("ascii", errors="replace"))
    # grab a nearby printable run around OnePlus if present
    low = data.lower()
    pos = low.find(b"oneplus")
    if pos >= 0:
        run = data[max(0, pos - 8) : pos + 24]
        printable = "".join(chr(c) if 32 <= c < 127 else "." for c in run)
        found.append(f"context:{printable}")
    return found


class AclReassembler:
    def __init__(self) -> None:
        self.buf: Dict[int, bytearray] = {}
        self.need: Dict[int, int] = {}

    def feed(self, handle: int, pb: int, data: bytes) -> List[bytes]:
        out: List[bytes] = []
        start = pb in (0x00, 0x02)
        cont = pb == 0x01
        if start:
            self.buf[handle] = bytearray(data)
            self.need[handle] = 0
            if len(data) >= 4:
                l2len = u16le(data, 0)
                self.need[handle] = 4 + l2len
        elif cont:
            if handle not in self.buf:
                return out
            self.buf[handle].extend(data)
        else:
            # treat as start
            self.buf[handle] = bytearray(data)
            self.need[handle] = 4 + u16le(data, 0) if len(data) >= 4 else 0

        buf = self.buf.get(handle)
        if buf is None:
            return out
        if len(buf) >= 4:
            need = 4 + u16le(bytes(buf[:2]), 0)
            self.need[handle] = need
            if len(buf) >= need:
                pdu = bytes(buf[:need])
                rest = buf[need:]
                out.append(pdu)
                if rest:
                    self.buf[handle] = rest
                    self.need[handle] = 4 + u16le(bytes(rest[:2]), 0) if len(rest) >= 4 else 0
                else:
                    self.buf.pop(handle, None)
                    self.need.pop(handle, None)
        return out


def parse_att_pdu(raw: bytes) -> Tuple[int, Optional[int], bytes]:
    if not raw:
        return 0, None, b""
    op = raw[0]
    handle = None
    value = raw[1:]
    if op in (
        ATT_WRITE_REQ,
        ATT_WRITE_CMD,
        ATT_NOTIFY,
        ATT_INDICATE,
        ATT_READ_REQ,
        ATT_READ_RSP,
    ):
        if len(raw) >= 3:
            handle = u16le(raw, 1)
            value = raw[3:] if op != ATT_READ_REQ else b""
            if op == ATT_READ_RSP:
                handle = None
                value = raw[1:]
            if op == ATT_READ_REQ:
                value = b""
    return op, handle, value


def parse_char_decls(value_blob_item_len: int, payload: bytes) -> List[CharDecl]:
    """payload after opcode+length of Read By Type Rsp."""
    out: List[CharDecl] = []
    rec_len = value_blob_item_len
    i = 0
    while i + rec_len <= len(payload):
        rec = payload[i : i + rec_len]
        decl_h = u16le(rec, 0)
        props = rec[2]
        val_h = u16le(rec, 3)
        uuid_bytes = rec[5:]
        uuid16 = u16le(uuid_bytes, 0) if len(uuid_bytes) >= 2 else None
        uuid_hex = hex_of(uuid_bytes)
        out.append(
            CharDecl(
                decl_handle=decl_h,
                properties=props,
                value_handle=val_h,
                uuid16=uuid16 if uuid_bytes[:2] == bytes([uuid16 & 0xFF, uuid16 >> 8]) else uuid16,
                uuid_hex=uuid_hex,
            )
        )
        i += rec_len
    return out


def parse_file(path: Path) -> Capture:
    data = path.read_bytes()
    cap = Capture(
        path=path,
        version=u32be(data, 8) if len(data) >= 12 else 0,
        datalink=u32be(data, 12) if len(data) >= 16 else 0,
        size=len(data),
        strings_hint=extract_ascii_hints(data),
    )
    if data[:8] != MAGIC:
        cap.parse_errors.append("kein btsnoop-Magic")
        return cap
    if cap.datalink != DATALINK_H4:
        cap.parse_errors.append(f"datalink={cap.datalink} (erwartet 1002)")

    acl = AclReassembler()
    pending_read_handle: Dict[int, int] = {}

    for rec in iter_snoop_records(data):
        cap.records += 1
        if rec.h4_type == H4_EVT:
            _parse_event(cap, rec)
        elif rec.h4_type == H4_ACL:
            if len(rec.payload) < 4:
                continue
            hdr = u16le(rec.payload, 0)
            handle = hdr & 0x0FFF
            pb = (hdr >> 12) & 0x03
            # dlen = u16le(rec.payload, 2)
            body = rec.payload[4:]
            for l2 in acl.feed(handle, pb, body):
                if len(l2) < 4:
                    continue
                l2len = u16le(l2, 0)
                cid = u16le(l2, 2)
                att_raw = l2[4 : 4 + l2len]
                if cid != ATT_CID:
                    continue
                peer = cap.conn_peer.get(handle, "")
                op, att_handle, value = parse_att_pdu(att_raw)
                # Read-Rsp follows Read-Req; remember handle
                if op == ATT_READ_REQ and att_handle is not None:
                    pending_read_handle[handle] = att_handle
                if op == ATT_READ_RSP:
                    att_handle = pending_read_handle.pop(handle, None)
                pdu = AttPdu(
                    rec=rec.index,
                    timestamp=rec.timestamp,
                    direction=rec.direction,
                    conn=handle,
                    peer=peer,
                    opcode=op,
                    opcode_name=ATT_NAMES.get(op, f"0x{op:02X}"),
                    handle=att_handle,
                    value=value,
                    raw=att_raw,
                )
                cap.att.append(pdu)
                if op == ATT_READ_BY_TYPE_RSP and len(att_raw) >= 2:
                    item_len = att_raw[1]
                    blob = att_raw[2:]
                    if item_len >= 7:
                        cap.chars.extend(parse_char_decls(item_len, blob))
                if op == ATT_READ_BY_GROUP_RSP and len(att_raw) >= 2:
                    item_len = att_raw[1]
                    blob = att_raw[2:]
                    j = 0
                    while j + item_len <= len(blob):
                        start_h = u16le(blob, j)
                        end_h = u16le(blob, j + 2)
                        uuid_b = blob[j + 4 : j + item_len]
                        uuid_s = f"{u16le(uuid_b, 0):04X}" if len(uuid_b) == 2 else hex_of(uuid_b)
                        cap.services.append((start_h, end_h, uuid_s))
                        j += item_len
    return cap


def _parse_event(cap: Capture, rec: SnoopRecord) -> None:
    p = rec.payload
    if len(p) < 2:
        return
    code, elen = p[0], p[1]
    params = p[2 : 2 + elen]
    if code == HCI_EVENT_DISCONN and len(params) >= 3:
        conn = u16le(params, 1) & 0x0FFF
        cap.conn_peer.pop(conn, None)
        return
    if code != HCI_EVENT_LE_META or not params:
        return
    sub = params[0]
    rest = params[1:]
    if sub in (LE_CONN_COMPLETE, LE_ENHANCED_CONN) and len(rest) >= 10:
        # status, handle, role, addr_type, addr[6]
        if rest[0] != 0:
            return
        conn = u16le(rest, 1) & 0x0FFF
        if sub == LE_CONN_COMPLETE:
            addr = rest[5:11]
        else:
            # Enhanced: status, handle, role, peer_addr_type, peer_addr,
            # local_rpa[6], peer_rpa[6], ...
            addr = rest[5:11]
        mac = mac_from_le(addr)
        cap.conn_peer[conn] = mac
        cap.le_conns.append((rec.timestamp, conn, mac))
        return
    if sub == LE_ADV_REPORT and len(rest) >= 1:
        num = rest[0]
        i = 1
        for _ in range(num):
            if i + 8 > len(rest):
                break
            et = rest[i]
            at = rest[i + 1]
            addr = rest[i + 2 : i + 8]
            dlen = rest[i + 8]
            i += 9
            if i + dlen + 1 > len(rest):
                break
            adata = rest[i : i + dlen]
            rssi = rest[i + dlen]
            if rssi >= 128:
                rssi -= 256
            i += dlen + 1
            mac = mac_from_le(addr)
            cap.adv.append(
                AdvReport(
                    rec=rec.index,
                    timestamp=rec.timestamp,
                    event_type=et,
                    event_name=ADV_EVENT_NAMES.get(et, f"0x{et:02X}"),
                    addr_type=at,
                    mac=mac,
                    rssi=rssi,
                    data=adata,
                    ads=parse_ad_structures(adata),
                )
            )


def find_cfa(root: Path) -> List[Path]:
    files = sorted(root.rglob("*.cfa"))
    return [p for p in files if p.is_file()]


def value_handles(cap: Capture) -> Dict[str, Optional[int]]:
    fff5 = fff3 = cccd = None
    for ch in cap.chars:
        if ch.uuid16 == UUID_FFF5:
            fff5 = ch.value_handle
        elif ch.uuid16 == UUID_FFF3:
            fff3 = ch.value_handle
    # CCCD is typically value_handle+1 of notify char; confirm via FindInfo if present
    if fff3 is not None:
        cccd = fff3 + 1
    for pdu in cap.att:
        if pdu.opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD) and pdu.handle is not None:
            if pdu.value == b"\x01\x00" and fff3 is not None and pdu.handle == fff3 + 1:
                cccd = pdu.handle
    return {"FFF5": fff5, "FFF3": fff3, "CCCD": cccd}


def is_target(mac: str) -> bool:
    return mac_norm(mac) == TARGET_MAC


def att_control_notify(cap: Capture) -> Tuple[List[AttPdu], List[AttPdu], List[AttPdu]]:
    hs = value_handles(cap)
    fff5, fff3, cccd = hs["FFF5"], hs["FFF3"], hs["CCCD"]
    writes, notifs, cccds = [], [], []
    for p in cap.att:
        if p.peer and not is_target(p.peer) and p.peer != "":
            continue
        if p.opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD) and p.handle == fff5:
            writes.append(p)
        elif p.opcode == ATT_NOTIFY and p.handle == fff3:
            notifs.append(p)
        elif p.opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD) and p.handle == cccd:
            cccds.append(p)
        # fallback if discovery missing: classic Android handles
        elif fff5 is None and p.opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD) and p.handle == 0x0021:
            writes.append(p)
        elif fff3 is None and p.opcode == ATT_NOTIFY and p.handle == 0x0024:
            notifs.append(p)
        elif cccd is None and p.opcode in (ATT_WRITE_REQ, ATT_WRITE_CMD) and p.handle == 0x0025:
            cccds.append(p)
    return writes, notifs, cccds


def unique_writes(writes: Iterable[AttPdu]) -> List[bytes]:
    seen = []
    got = set()
    for w in writes:
        key = bytes(w.value)
        if key not in got:
            got.add(key)
            seen.append(key)
    return seen


def opcode_hist(pdus: Iterable[AttPdu]) -> Counter:
    c: Counter = Counter()
    for p in pdus:
        if p.value:
            c[p.value[0]] += 1
        else:
            c[-1] += 1
    return c


def pair_writes_notifies(
    writes: List[AttPdu], notifs: List[AttPdu]
) -> List[Tuple[AttPdu, List[AttPdu]]]:
    """Jedem FFF5-Write die FFF3-Notifies zuordnen, die vor dem nächsten Write kommen."""
    events: List[Tuple[str, AttPdu]] = [("w", w) for w in writes] + [("n", n) for n in notifs]
    events.sort(key=lambda x: (x[1].rec, 0 if x[0] == "w" else 1))
    pairs: List[Tuple[AttPdu, List[AttPdu]]] = []
    i = 0
    while i < len(events):
        kind, pdu = events[i]
        if kind != "w":
            i += 1
            continue
        following: List[AttPdu] = []
        j = i + 1
        while j < len(events) and events[j][0] != "w":
            following.append(events[j][1])
            j += 1
        pairs.append((pdu, following))
        i = j if j > i else i + 1
    return pairs


def _dt_ms(write_ts: str, notify_ts: str) -> Optional[float]:
    try:
        w = datetime.strptime(write_ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        n = datetime.strptime(notify_ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return (n - w).total_seconds() * 1000.0
    except ValueError:
        return None


def write_csvs(caps: List[Capture], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    att_path = outdir / "att.csv"
    adv_path = outdir / "adv.csv"
    sum_path = outdir / "summary.csv"
    wr_path = outdir / "unique_writes.csv"
    op_path = outdir / "opcodes.csv"

    with att_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "rec",
                "timestamp",
                "dir",
                "peer",
                "att_op",
                "att_name",
                "handle",
                "value_hex",
                "value_len",
                "first_byte",
            ]
        )
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            writes, notifs, cccds = att_control_notify(cap)
            for p in cap.att:
                if p.opcode not in (
                    ATT_WRITE_REQ,
                    ATT_WRITE_CMD,
                    ATT_NOTIFY,
                    ATT_INDICATE,
                    ATT_WRITE_RSP,
                    ATT_MTU_REQ,
                    ATT_MTU_RSP,
                ):
                    # still dump control-related + discovery-ish writes
                    if p.handle not in (0x0021, 0x0024, 0x0025, None) and p.opcode not in (
                        ATT_READ_BY_TYPE_RSP,
                        ATT_READ_BY_GROUP_RSP,
                    ):
                        continue
                w.writerow(
                    [
                        rel,
                        p.rec,
                        p.timestamp,
                        p.direction,
                        p.peer,
                        f"0x{p.opcode:02X}",
                        p.opcode_name,
                        f"0x{p.handle:04X}" if p.handle is not None else "",
                        hex_of(p.value),
                        len(p.value),
                        f"0x{p.value[0]:02X}" if p.value else "",
                    ]
                )

    with (outdir / "att_fff5_fff3.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "rec",
                "timestamp",
                "kind",
                "peer",
                "handle",
                "opcode_byte",
                "value_hex",
                "value_len",
            ]
        )
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            writes, notifs, cccds = att_control_notify(cap)
            for kind, lst in (("CCCD", cccds), ("FFF5-Write", writes), ("FFF3-Notify", notifs)):
                for p in lst:
                    w.writerow(
                        [
                            rel,
                            p.rec,
                            p.timestamp,
                            kind,
                            p.peer,
                            f"0x{p.handle:04X}" if p.handle is not None else "",
                            f"0x{p.value[0]:02X}" if p.value else "",
                            hex_of(p.value),
                            len(p.value),
                        ]
                    )

    with adv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "rec",
                "timestamp",
                "mac",
                "target",
                "event",
                "rssi",
                "ad_hex",
                "name",
                "uuids16",
                "mfg_hex",
                "mfg_company",
            ]
        )
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            seen_keys = set()
            for a in cap.adv:
                key = (a.mac, a.event_type, a.data)
                # keep all target frames, unique others
                if not is_target(a.mac) and key in seen_keys:
                    continue
                seen_keys.add(key)
                name = ""
                uuids = []
                mfg = b""
                company = ""
                for t, v in a.ads:
                    if t in (0x08, 0x09):
                        name = v.decode("utf-8", errors="replace")
                    elif t in (0x02, 0x03):
                        for k in range(0, len(v), 2):
                            if k + 2 <= len(v):
                                uuids.append(f"{u16le(v, k):04X}")
                    elif t == 0xFF:
                        mfg = v
                        if len(v) >= 2:
                            company = f"0x{u16le(v, 0):04X}"
                w.writerow(
                    [
                        rel,
                        a.rec,
                        a.timestamp,
                        a.mac,
                        "yes" if is_target(a.mac) else "no",
                        a.event_name,
                        a.rssi,
                        hex_of(a.data),
                        name,
                        " ".join(uuids),
                        hex_of(mfg),
                        company,
                    ]
                )

    with wr_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "count", "first_byte", "len", "value_hex"])
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            writes, _, _ = att_control_notify(cap)
            counts: Counter = Counter(bytes(p.value) for p in writes)
            for val, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                w.writerow(
                    [
                        rel,
                        n,
                        f"0x{val[0]:02X}" if val else "",
                        len(val),
                        hex_of(val),
                    ]
                )

    with (outdir / "pairs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "write_rec",
                "write_ts",
                "write_hex",
                "write_len",
                "write_op",
                "n_notifies",
                "notify_rec",
                "notify_ts",
                "notify_hex",
                "notify_len",
                "notify_op",
                "dt_ms",
                "echo",
            ]
        )
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            writes, notifs, _ = att_control_notify(cap)
            for wr, ns in pair_writes_notifies(writes, notifs):
                if not ns:
                    w.writerow(
                        [
                            rel,
                            wr.rec,
                            wr.timestamp,
                            hex_of(wr.value),
                            len(wr.value),
                            f"0x{wr.value[0]:02X}" if wr.value else "",
                            0,
                            "",
                            "",
                            "",
                            "",
                            "",
                            "",
                            "no",
                        ]
                    )
                    continue
                for n in ns:
                    dt = _dt_ms(wr.timestamp, n.timestamp)
                    echo = (
                        "yes"
                        if wr.value and n.value and wr.value[0] == n.value[0]
                        else "no"
                    )
                    w.writerow(
                        [
                            rel,
                            wr.rec,
                            wr.timestamp,
                            hex_of(wr.value),
                            len(wr.value),
                            f"0x{wr.value[0]:02X}" if wr.value else "",
                            len(ns),
                            n.rec,
                            n.timestamp,
                            hex_of(n.value),
                            len(n.value),
                            f"0x{n.value[0]:02X}" if n.value else "",
                            f"{dt:.1f}" if dt is not None else "",
                            echo,
                        ]
                    )

    with op_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["file", "channel", "first_byte", "count"])
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            writes, notifs, _ = att_control_notify(cap)
            for ch, lst in (("FFF5-Write", writes), ("FFF3-Notify", notifs)):
                hist = opcode_hist(lst)
                for opb, n in sorted(hist.items()):
                    w.writerow([rel, ch, f"0x{opb:02X}" if opb >= 0 else "", n])

    with sum_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "file",
                "size",
                "records",
                "datalink",
                "le_conns",
                "adv_target",
                "adv_other",
                "fff5_writes",
                "fff3_notifies",
                "FFF5",
                "FFF3",
                "CCCD",
                "hints",
                "errors",
            ]
        )
        for cap in caps:
            rel = cap.path.name if cap.path.parent.name != "old" else f"old/{cap.path.name}"
            hs = value_handles(cap)
            writes, notifs, _ = att_control_notify(cap)
            adv_t = sum(1 for a in cap.adv if is_target(a.mac))
            adv_o = len(cap.adv) - adv_t
            w.writerow(
                [
                    rel,
                    cap.size,
                    cap.records,
                    cap.datalink,
                    len(cap.le_conns),
                    adv_t,
                    adv_o,
                    len(writes),
                    len(notifs),
                    f"0x{hs['FFF5']:04X}" if hs["FFF5"] is not None else "",
                    f"0x{hs['FFF3']:04X}" if hs["FFF3"] is not None else "",
                    f"0x{hs['CCCD']:04X}" if hs["CCCD"] is not None else "",
                    "; ".join(cap.strings_hint),
                    "; ".join(cap.parse_errors),
                ]
            )


def print_summary(caps: List[Capture]) -> None:
    for cap in caps:
        rel = cap.path.as_posix()
        hs = value_handles(cap)
        writes, notifs, cccds = att_control_notify(cap)
        print(f"\n=== {rel} ===")
        print(f"  size={cap.size} records={cap.records} datalink={cap.datalink}")
        print(f"  hints={cap.strings_hint}")
        print(f"  conns={cap.le_conns}")
        print(f"  services={cap.services}")
        print(f"  handles FFF5={hs['FFF5']} FFF3={hs['FFF3']} CCCD={hs['CCCD']}")
        print(f"  chars={[ (c.value_handle, f'{c.uuid16:04X}' if c.uuid16 else c.uuid_hex, c.decl_handle) for c in cap.chars ]}")
        print(f"  CCCD writes={len(cccds)} FFF5={len(writes)} FFF3={len(notifs)}")
        print(f"  unique FFF5: {len(unique_writes(writes))}")
        for val in unique_writes(writes):
            n = sum(1 for p in writes if bytes(p.value) == val)
            print(f"    n={n:4d} len={len(val):2d} {hex_of(val)}")
        hist_n = opcode_hist(notifs)
        print(f"  FFF3 first-byte: { {hex(k): v for k, v in sorted(hist_n.items())} }")
        tadv = [a for a in cap.adv if is_target(a.mac)]
        print(f"  adv target={len(tadv)} other={len(cap.adv) - len(tadv)}")
        shown = set()
        for a in tadv:
            key = (a.event_type, a.data)
            if key in shown:
                continue
            shown.add(key)
            ads = "; ".join(
                f"{AD_TYPE_NAMES.get(t, hex(t))}={hex_of(v) if t not in (0x08, 0x09) else v.decode('utf-8', errors='replace')}"
                for t, v in a.ads
            )
            print(f"    {a.event_name} rssi={a.rssi} {ads}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="btsnoop/H4 Parser für ThermoBeacon .cfa")
    ap.add_argument(
        "paths",
        nargs="*",
        help="Dateien oder Ordner (Default: hci-logs)",
    )
    ap.add_argument("--summary", action="store_true", help="Text-Summary auf stdout")
    ap.add_argument("--export", metavar="DIR", help="CSV nach DIR schreiben")
    ap.add_argument("--att", action="store_true", help="FFF5/FFF3-Zeilen auf stdout")
    ap.add_argument("--adv", action="store_true", help="Advertising des Zielgeräts auf stdout")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve().parent.parent
    if args.paths:
        files: List[Path] = []
        for p in args.paths:
            path = Path(p)
            if not path.is_absolute():
                path = here / path
            if path.is_dir():
                files.extend(find_cfa(path))
            else:
                files.append(path)
    else:
        files = find_cfa(here / "hci-logs")

    caps = [parse_file(p) for p in files]
    if args.export:
        out = Path(args.export)
        if not out.is_absolute():
            out = here / out
        write_csvs(caps, out)
        print(f"export -> {out}")
    if args.summary or not (args.export or args.att or args.adv):
        print_summary(caps)
    if args.att:
        for cap in caps:
            writes, notifs, cccds = att_control_notify(cap)
            rel = cap.path.name
            for kind, lst in (("CCCD", cccds), ("W", writes), ("N", notifs)):
                for p in lst:
                    print(f"{rel}\t{p.timestamp}\t{kind}\t{hex_of(p.value)}")
    if args.adv:
        for cap in caps:
            for a in cap.adv:
                if not is_target(a.mac):
                    continue
                print(
                    f"{cap.path.name}\t{a.timestamp}\t{a.mac}\t{a.event_name}\t{a.rssi}\t{hex_of(a.data)}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
