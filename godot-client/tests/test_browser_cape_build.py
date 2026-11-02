"""Preserve executable wasm and dynamic-link metadata while removing debug paths."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_browser_cape import strip_debug_sections

HEADER = b"\0asm\x01\0\0\0"


def custom(name, payload):
    body = bytes([len(name)]) + name.encode() + payload
    return b"\0" + bytes([len(body)]) + body


class BrowserCapeBuildTests(unittest.TestCase):
    def test_code_and_dynamic_link_sections_remain_exactly_as_compiled(self):
        link = custom("dylink.0", b"\x00\x01\x02")
        code = b"\x0a\x04\x01\x02\x00\x0b"
        before = HEADER + custom("name", b"local path") + link + code + custom(".debug_info", b"local path")
        self.assertEqual(strip_debug_sections(before), HEADER + link + code)

    def test_other_custom_metadata_is_retained(self):
        data = HEADER + custom("target_features", b"shared memory")
        self.assertEqual(strip_debug_sections(data), data)

    def test_malformed_input_is_rejected_before_writing_an_artifact(self):
        for data in (b"not wasm", HEADER + b"\x00\x80", HEADER + b"\x0a\x10\x01", HEADER + b"\0\x01\x08"):
            with self.assertRaises(ValueError): strip_debug_sections(data)


if __name__ == "__main__": unittest.main()
