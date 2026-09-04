#!/usr/bin/env python3
"""Unittests gegen belegte Goldvektoren (hci-logs/03, 05, 06)."""
import os
import sys
import unittest

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

from thermo_parse import (
    AdvLive,
    Count01,
    History07,
    Status1A,
    TARGET_MAC,
    build_history_07_write,
    parse_adv_manufacturer,
    parse_fff3,
)


class TestParseAdvManufacturer(unittest.TestCase):
    def test_adv_rec_171_live(self):
        mfg = bytes.fromhex("1B001000D9000000DBF4B50B61010F044B7D0E00")
        result = parse_adv_manufacturer(mfg)
        self.assertIsInstance(result, AdvLive)
        self.assertEqual(result.temp_c, 22.0625)
        self.assertEqual(result.humidity_rh, 64.9375)
        self.assertEqual(result.battery_mv, 2997)
        self.assertEqual(result.mac, TARGET_MAC)
        self.assertEqual(result.mac, "f4:db:00:00:00:d9")
        self.assertEqual(result.counter, 949579)

    def test_minmax_22_byte_is_none(self):
        mfg = bytes.fromhex("1B001000D9000000DBF4A7015F0F00002A017E0C0400")
        self.assertEqual(len(mfg), 22)
        self.assertIsNone(parse_adv_manufacturer(mfg))

    def test_foreign_mac_is_none(self):
        mfg = bytearray.fromhex("1B001000D9000000DBF4B50B61010F044B7D0E00")
        mfg[4] = 0xAA
        self.assertIsNone(parse_adv_manufacturer(bytes(mfg)))


class TestParseFff3(unittest.TestCase):
    def test_history_07_count03_index0(self):
        data = bytes.fromhex("07000000000381017B017901B403BC03CB030000")
        result = parse_fff3(data)
        self.assertIsInstance(result, History07)
        self.assertEqual(result.index, 0)
        self.assertEqual(result.count, 3)
        self.assertEqual(
            result.records,
            [
                (24.0625, 59.25),
                (23.6875, 59.75),
                (23.5625, 60.6875),
            ],
        )

    def test_history_07_count01_hum_at_offset8(self):
        data = bytes.fromhex("0730060000016F01E8036E010E040F04F2030000")
        result = parse_fff3(data)
        self.assertIsInstance(result, History07)
        self.assertEqual(result.index, 1584)
        self.assertEqual(result.count, 1)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0], (22.9375, 62.5))

    def test_status_1a(self):
        data = bytes.fromhex("1A01000100" + "00" * 15)
        result = parse_fff3(data)
        self.assertIsInstance(result, Status1A)
        self.assertEqual(len(data), 20)

    def test_count_01_form_a(self):
        data = bytes.fromhex("012F0600" + "00" * 16)
        result = parse_fff3(data)
        self.assertIsInstance(result, Count01)
        self.assertEqual(result.sample_count, 1583)

    def test_opcode_f3_is_none(self):
        data = bytes.fromhex("F3" + "00" * 19)
        self.assertEqual(len(data), 20)
        self.assertIsNone(parse_fff3(data))


class TestBuildHistory07Write(unittest.TestCase):
    def test_index0_count3(self):
        self.assertEqual(
            build_history_07_write(0, 3),
            bytes.fromhex("070000000003"),
        )

    def test_index_0x011d_count3(self):
        self.assertEqual(
            build_history_07_write(0x011D, 3),
            bytes.fromhex("071D01000003"),
        )

    def test_index_1584_count1(self):
        self.assertEqual(
            build_history_07_write(1584, 1),
            bytes.fromhex("073006000001"),
        )


if __name__ == "__main__":
    unittest.main()
