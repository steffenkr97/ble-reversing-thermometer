#!/usr/bin/env python3
"""Unittests fuer assemble_mfg_frame (ohne BLE). Goldvektor ADV rec 171."""
from __future__ import annotations

import os
import sys
import types
import unittest

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

COMPANY_ID = 0x001B
CID_LE = b"\x1b\x00"
# ADV rec 171, hci-logs/07-read.md
GOLD_FRAME = bytes.fromhex("1B001000D9000000DBF4B50B61010F044B7D0E00")


def _load_assemble_mfg_frame():
    """scan_live.assemble_mfg_frame laden; bleak bei Bedarf stubben, nicht nachbauen."""
    try:
        from scan_live import assemble_mfg_frame

        return assemble_mfg_frame
    except ImportError as exc:
        if "bleak" not in str(exc).lower():
            raise
    sys.modules.pop("scan_live", None)
    if "bleak" not in sys.modules:
        stub = types.ModuleType("bleak")
        stub.BleakScanner = object
        sys.modules["bleak"] = stub
    from scan_live import assemble_mfg_frame

    return assemble_mfg_frame


_ASSEMBLE = None
_SKIP_ASSEMBLE = None
try:
    _ASSEMBLE = _load_assemble_mfg_frame()
except ImportError:
    _SKIP_ASSEMBLE = "bleak fehlt"


def _assemble():
    if _ASSEMBLE is None:
        raise unittest.SkipTest(_SKIP_ASSEMBLE or "bleak fehlt")
    return _ASSEMBLE


@unittest.skipUnless(_ASSEMBLE is not None, _SKIP_ASSEMBLE or "bleak fehlt")
class TestAssembleMfgFrame(unittest.TestCase):
    def test_company_and_18_byte_payload_prepends_cid(self):
        assemble = _assemble()
        payload = GOLD_FRAME[2:]
        self.assertEqual(len(payload), 18)
        result = assemble(COMPANY_ID, payload)
        self.assertEqual(result, CID_LE + payload)
        self.assertEqual(len(result), 20)

    def test_20_byte_payload_starting_with_cid_returned_as_is(self):
        assemble = _assemble()
        self.assertEqual(len(GOLD_FRAME), 20)
        self.assertTrue(GOLD_FRAME.startswith(CID_LE))
        result = assemble(COMPANY_ID, GOLD_FRAME)
        self.assertEqual(result, GOLD_FRAME)

    def test_gold_fall_a_18_byte_rest_equals_frame(self):
        assemble = _assemble()
        self.assertEqual(assemble(COMPANY_ID, GOLD_FRAME[2:]), GOLD_FRAME)

    def test_gold_fall_b_20_byte_incl_company_equals_frame(self):
        assemble = _assemble()
        self.assertEqual(assemble(COMPANY_ID, GOLD_FRAME), GOLD_FRAME)

    def test_len_19_is_none(self):
        assemble = _assemble()
        self.assertIsNone(assemble(COMPANY_ID, GOLD_FRAME[:19]))

    def test_wrong_company_id_18_byte_is_none(self):
        assemble = _assemble()
        self.assertIsNone(assemble(0x001C, GOLD_FRAME[2:]))

    def test_20_byte_not_starting_with_cid_is_none(self):
        assemble = _assemble()
        bad = b"\xff\xff" + GOLD_FRAME[2:]
        self.assertEqual(len(bad), 20)
        self.assertFalse(bad.startswith(CID_LE))
        self.assertIsNone(assemble(COMPANY_ID, bad))


if __name__ == "__main__":
    unittest.main()
