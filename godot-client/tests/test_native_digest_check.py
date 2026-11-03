"""tools/native_digest_check.py: listing, reference digests and comparison; never starts Godot."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import native_digest_check as check


def per_byte_fold(raw: bytes) -> bytes:
    return bytes(byte for index, byte in enumerate(raw) if not (byte == 13 and raw[index + 1:index + 2] == b"\n"))


class NativeDigestCheckTests(unittest.TestCase):
    def test_fold_matches_the_per_byte_rule(self):
        for raw in [b"", b"a\r\nb", b"a\rb", b"a\r", b"\r\r\n", b"\r", b"\n\r", b"\r\n\r\n", b"x\r\ny\rz\r\n\r",
                    bytes([13, 10, 13, 13, 10, 10, 13]) * 50]:
            with self.subTest(raw=raw):
                self.assertEqual(check.fold_crlf(raw), per_byte_fold(raw))

    def test_listing_and_reference_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a/b").mkdir(parents=True)
            (root / "a/b/world.json").write_bytes(b"{\r\n}\r\n")
            (root / "big.bin").write_bytes(b"x" * (check.READ_BYTES + 3))
            (root / "empty.bin").write_bytes(b"")
            rows = check.list_files(root)
            self.assertEqual([Path(row).name for row in rows], ["world.json", "big.bin", "empty.bin"])
            self.assertTrue(all("\\" not in row and Path(row).is_absolute() for row in rows))
            self.assertEqual(check.python_digest(rows[1], False), (hashlib.sha256(b"x" * (check.READ_BYTES + 3)).hexdigest(), False))
            self.assertEqual(check.python_digest(rows[0], True), (hashlib.sha256(b"{\n}\n").hexdigest(), True))
            self.assertEqual(check.python_digest(rows[2], True), (hashlib.sha256(b"").hexdigest(), False))

    def test_compare_reports_raw_fold_status_and_count_differences(self):
        paths = ["C:/a.json", "C:/b.bin"]
        good = {"digests": ["aa", "bb"], "status": [0, 0], "fold": {"0": ["cc", 0, 1]}}
        report = check.compare(paths, good, ["aa", "bb"], {0: ("cc", True)})
        self.assertTrue(report["ok"])
        self.assertEqual((report["compared"], report["folded_compared"]), (2, 1))
        for native, kind in [
            ({"digests": ["aa", "bx"], "status": [0, 0], "fold": {"0": ["cc", 0, 1]}}, "raw"),
            ({"digests": ["aa", ""], "status": [0, 1], "fold": {"0": ["cc", 0, 1]}}, "raw"),
            ({"digests": ["aa", "bb"], "status": [0, 0], "fold": {"0": ["cc", 0, 0]}}, "fold"),
            ({"digests": ["aa", "bb"], "status": [0, 0], "fold": {}}, "fold"),
        ]:
            with self.subTest(native=native):
                report = check.compare(paths, native, ["aa", "bb"], {0: ("cc", True)})
                self.assertFalse(report["ok"])
                self.assertEqual(report["mismatches"][0]["kind"], kind)
        self.assertFalse(check.compare(paths, {"digests": ["aa"], "status": [0]}, ["aa", "bb"], {})["ok"])


if __name__ == "__main__":
    unittest.main()
