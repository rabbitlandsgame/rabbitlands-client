import unittest

from run_crowd_presentation_benchmark import parser, request_for


class BenchmarkRequestTests(unittest.TestCase):
    def test_family_and_capture_reach_validator(self):
        args = parser().parse_args([
            "--godot", "owned-client.exe", "--client-runtime", "rust",
            "--rust-effects", "heat_bolt", "--capture-boundaries",
        ])
        request = request_for(args)
        self.assertEqual(request["rust_effects"], "heat_bolt")
        self.assertTrue(request["capture_boundaries"])

    def test_default_request_disables_optional_family_and_capture(self):
        request = request_for(parser().parse_args(["--godot", "owned-client.exe"]))
        self.assertEqual(request["rust_effects"], "legacy")
        self.assertFalse(request["capture_boundaries"])


if __name__ == "__main__":
    unittest.main()
