#!/usr/bin/env python3
"""Offline-Tests fuer collect.py-CLI (BLE gemockt). Skip wenn collect/bleak fehlen."""
from __future__ import annotations

import csv
import inspect
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from unittest.mock import patch

_PY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PY_DIR not in sys.path:
    sys.path.insert(0, _PY_DIR)

_COLLECT = None
_SKIP_COLLECT = None
_ADV = None


def _stub_bleak_if_missing():
    """collect/scan_live importieren bleak oben; ohne Package stubben, nicht nachbauen."""
    try:
        import bleak  # noqa: F401
    except ImportError:
        if "bleak" in sys.modules:
            return
        stub = types.ModuleType("bleak")
        stub.BleakScanner = object
        sys.modules["bleak"] = stub


def _load_collect():
    _stub_bleak_if_missing()
    try:
        import collect as mod

        return mod, None
    except ImportError as exc:
        msg = str(exc).lower()
        if "bleak" in msg:
            return None, "bleak fehlt"
        if "thermo_store" in msg:
            return None, "thermo_store fehlt"
        if "scan_live" in msg:
            return None, "scan_live fehlt"
        if "collect" in msg or "no module named" in msg:
            return None, "collect.py fehlt"
        return None, str(exc)


try:
    from thermo_parse import AdvLive

    _ADV = AdvLive(
        temp_c=22.0625,
        humidity_rh=64.9375,
        battery_mv=2997,
        counter=949579,
        mac="f4:db:00:00:00:d9",
        raw_hex="1B001000D9000000DBF4B50B61010F044B7D0E00",
    )
except ImportError as exc:
    _SKIP_COLLECT = "thermo_parse fehlt ({0})".format(exc)

if _SKIP_COLLECT is None:
    _COLLECT, _SKIP_COLLECT = _load_collect()

_CSV_COLS = ("timestamp", "mac", "temp_c", "humidity_rh", "raw_hex")


def _require_collect():
    if _COLLECT is None:
        raise unittest.SkipTest(_SKIP_COLLECT or "collect.py fehlt")
    return _COLLECT


def _main_accepts_argv(main_fn):
    try:
        params = list(inspect.signature(main_fn).parameters.values())
    except (TypeError, ValueError):
        return False
    if not params:
        return False
    kind = params[0].kind
    return kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.VAR_POSITIONAL,
    )


def _run_main(argv):
    collect = _require_collect()
    main_fn = getattr(collect, "main", None)
    if main_fn is None:
        raise unittest.SkipTest("kein collect.main")
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            if _main_accepts_argv(main_fn):
                result = main_fn(argv)
            else:
                with patch.object(sys, "argv", ["collect.py"] + list(argv)):
                    result = main_fn()
    except SystemExit as exc:
        return 0 if exc.code is None else exc.code
    if result is None:
        return 0
    return result


@contextmanager
def _mock_scan_live(return_value):
    collect = _require_collect()

    async def fake(*args, **kwargs):
        return return_value

    with ExitStack() as stack:
        if hasattr(collect, "scan_live"):
            stack.enter_context(patch.object(collect, "scan_live", fake))
        sl = sys.modules.get("scan_live")
        if sl is not None and hasattr(sl, "scan_live"):
            stack.enter_context(patch.object(sl, "scan_live", fake))
        yield fake


def _read_csv_rows(path):
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    return fieldnames, rows


@unittest.skipUnless(_COLLECT is not None, _SKIP_COLLECT or "collect.py fehlt")
class TestCollectOnceCsv(unittest.TestCase):
    def test_once_writes_header_and_one_row(self):
        _require_collect()
        if _ADV is None:
            self.skipTest("AdvLive fehlt")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            with _mock_scan_live(_ADV):
                rc = _run_main(
                    ["--once", "--output", path, "--timeout", "1", "--mac", _ADV.mac]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(path), "CSV fehlt nach --once")
            fieldnames, rows = _read_csv_rows(path)
            for col in _CSV_COLS:
                self.assertIn(col, fieldnames)
            self.assertNotIn("battery_mv", fieldnames)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertTrue(row["timestamp"])
            self.assertEqual(row["mac"], _ADV.mac)
            self.assertEqual(float(row["temp_c"]), _ADV.temp_c)
            self.assertEqual(float(row["humidity_rh"]), _ADV.humidity_rh)
            self.assertEqual(
                row["raw_hex"].replace(" ", "").lower(),
                _ADV.raw_hex.lower(),
            )

    def test_timeout_exit_1_no_data_row(self):
        _require_collect()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            with _mock_scan_live(None):
                rc = _run_main(
                    [
                        "--once",
                        "--output",
                        path,
                        "--timeout",
                        "1",
                        "--mac",
                        "f4:db:00:00:00:d9",
                    ]
                )
            self.assertEqual(rc, 1)
            if not os.path.isfile(path):
                return
            _fieldnames, rows = _read_csv_rows(path)
            self.assertEqual(len(rows), 0, "Timeout darf keine Messzeile schreiben")


@unittest.skipUnless(_COLLECT is not None, _SKIP_COLLECT or "collect.py fehlt")
class TestCollectArgparse(unittest.TestCase):
    def test_once_and_interval_is_error(self):
        collect = _require_collect()
        argv = ["--once", "--interval", "60"]
        if hasattr(collect, "parse_args"):
            with redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    collect.parse_args(argv)
            return
        main_fn = getattr(collect, "main", None)
        if main_fn is None or not _main_accepts_argv(main_fn):
            self.skipTest("kein parse_args und main akzeptiert kein argv")
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main_fn(argv)

    def test_timeout_and_outdir_defaults(self):
        collect = _require_collect()
        if not hasattr(collect, "parse_args"):
            self.skipTest("kein parse_args")
        args = collect.parse_args(["--once"])
        if not hasattr(args, "timeout"):
            self.skipTest("kein --timeout")
        self.assertEqual(float(args.timeout), 15.0)
        if not hasattr(args, "outdir"):
            self.skipTest("kein --outdir")
        self.assertEqual(args.outdir, "data")

    def test_output_without_mac_errors_when_many_rooms(self):
        collect = _require_collect()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            rc = _run_main(["--once", "--output", path, "--timeout", "1"])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
