"""Optional owned-child Vulkan-layer flag; fake Popen only, no engine/OBS APIs."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "integration"))
import run_crowd_presentation_benchmark as runner
from crowd_benchmark_support import EvidenceError, read_json

FLAG = "DISABLE_VULKAN_OBS_CAPTURE"


class ObsVulkanChildEnvironmentTests(unittest.TestCase):
    def test_switch_is_opt_in(self):
        parser = runner.parser()
        self.assertFalse(parser.parse_args(["--godot", "fake.exe"]).disable_obs_vulkan_capture)
        self.assertTrue(parser.parse_args(["--godot", "fake.exe", "--disable-obs-vulkan-capture"])
                        .disable_obs_vulkan_capture)

    def check_owned_child(self, inherited, requested):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            options = ["--godot", str(root / "fake.exe"), "--project-path", str(root)]
            if requested:
                options.append("--disable-obs-vulkan-capture")
            args = runner.parser().parse_args(options)
            args.godot = root / "fake.exe"
            child = mock.Mock(pid=12345, poll=mock.Mock(return_value=None), wait=mock.Mock(return_value=-9))
            launched = []

            def fake_launch(command, *, env, **kwargs):
                self.assertIsNot(env, runner.os.environ)
                launched.append(env.copy())
                self.assertEqual(dict(runner.os.environ), before)
                return child

            with mock.patch.dict(runner.os.environ, inherited, clear=True), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch) as popen, \
                    mock.patch.object(runner, "wait_for_startup", side_effect=EvidenceError("fake startup stop")):
                before = dict(runner.os.environ)
                result = runner.run_one(args, "all", 1, root)
                self.assertEqual(dict(runner.os.environ), before)
                popen.assert_called_once()
            expected = "1" if requested else inherited.get(FLAG)
            self.assertEqual(launched[0].get(FLAG), expected)
            self.assertEqual(launched[0]["UNRELATED_CAPTURE_JOB"], "preserved")
            info = result["externalInterference"]["obsVulkan"]
            self.assertEqual(info, {"requestedDisabled": requested, "effectiveEnvValue": expected,
                                    "observedHookLoaded": None})
            self.assertIsNone(info["observedHookLoaded"])
            self.assertEqual(result["effectiveOverrides"].get(FLAG), "1" if requested else None)
            saved = read_json(next(root.glob("*.process.json")))
            self.assertEqual(saved["externalInterference"]["obsVulkan"], info)
            self.assertFalse(result["validation"]["valid"])
            self.assertEqual(result["validation"]["errors"], ["fake startup stop"])
            child.kill.assert_called_once_with()
            child.wait.assert_called_once_with()

    def test_omitted_switch_preserves_inherited_value_including_absent_and_empty(self):
        for value in (None, "", "0", "1", "custom"):
            with self.subTest(value=value):
                inherited = {"UNRELATED_CAPTURE_JOB": "preserved"}
                if value is not None:
                    inherited[FLAG] = value
                self.check_owned_child(inherited, False)

    def test_explicit_switch_overrides_only_owned_child(self):
        for value in (None, "0", "custom"):
            with self.subTest(value=value):
                inherited = {"UNRELATED_CAPTURE_JOB": "preserved"}
                if value is not None:
                    inherited[FLAG] = value
                self.check_owned_child(inherited, True)


if __name__ == "__main__":
    unittest.main()
