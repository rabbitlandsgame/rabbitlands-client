"""CLI/fixture isolation checks; no engine, assets, live database or socket."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

INTEGRATION = Path(__file__).resolve().parent / "integration"
sys.path.insert(0, str(INTEGRATION))
import live_spawn_responsiveness as runner


class LiveSpawnRunnerTests(unittest.TestCase):
    def base_arguments(self):
        return ["--godot", "engine", "--terrain", "terrain", "--out", "output"]

    def test_help_does_not_need_a_sibling_server(self):
        result = subprocess.run([sys.executable, str(INTEGRATION / "live_spawn_responsiveness.py"), "--help"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--server-root", result.stdout)
        self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_default_keeps_sibling_checkout_convention(self):
        args = runner.arguments(self.base_arguments())
        self.assertEqual(args.server_root, runner.CLIENT.parent.parent / "rabbitlands-server")

    def test_headless_native_window_mode_is_not_a_display_attestation(self):
        for mode in ["windowed", "fullscreen"]:
            with self.subTest(mode=mode):
                args = runner.arguments(self.base_arguments() + ["--window-mode", mode])
                runner.validate_display({"fps_cap": 60, "window_mode": 1}, args)

    def test_rendered_window_mode_mismatch_is_rejected(self):
        for mode, actual in [("windowed", 1), ("fullscreen", 0)]:
            with self.subTest(mode=mode):
                args = runner.arguments(self.base_arguments() + ["--rendered", "--window-mode", mode])
                with self.assertRaisesRegex(AssertionError, "display mode"):
                    runner.validate_display({"fps_cap": 60, "window_mode": actual}, args)

    def test_rendered_matching_window_modes_are_accepted(self):
        for mode, actual in [("windowed", 0), ("fullscreen", 4)]:
            with self.subTest(mode=mode):
                args = runner.arguments(self.base_arguments() + ["--rendered", "--window-mode", mode])
                runner.validate_display({"fps_cap": 60, "window_mode": actual}, args)

    def test_wrong_fps_cap_is_rejected_in_both_rendering_modes(self):
        for rendered in [False, True]:
            with self.subTest(rendered=rendered):
                args = runner.arguments(self.base_arguments() + (["--rendered"] if rendered else []))
                with self.assertRaisesRegex(AssertionError, "FPS cap"):
                    runner.validate_display({"fps_cap": 30, "window_mode": 0}, args)

    def test_explicit_worktree_root_reaches_fixture_and_copies_settings(self):
        with tempfile.TemporaryDirectory(prefix="rl-spawn-cli-") as temporary:
            root = Path(temporary)
            server = root / "nested" / "server-worktree"
            config = server / "config" / "eloria"
            config.mkdir(parents=True)
            (config / "server.txt").write_text("map_data_directory = old\ninvasion_masters = old\n", encoding="utf8")
            terrain = root / "served-terrain"
            args = runner.arguments(self.base_arguments() + ["--server-root", str(server)])
            fixture = runner.FixtureServer(terrain, {"ProbeAdmin": "disposable"}, args.server_root)
            self.assertEqual(fixture.server_root, server.resolve())
            self.assertIn("map_data_directory = " + terrain.as_posix(), fixture._overrides["--settings"])
            self.assertIn("invasion_masters = ProbeAdmin", fixture._overrides["--settings"])
            self.assertEqual((config / "server.txt").read_text(encoding="utf8"),
                             "map_data_directory = old\ninvasion_masters = old\n")


if __name__ == "__main__":
    unittest.main()
