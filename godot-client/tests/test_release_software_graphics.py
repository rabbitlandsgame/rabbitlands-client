"""Fake-only software-cook configuration checks; no renderer or tools launched."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_software_graphics as graphics


class SoftwareGraphicsTests(unittest.TestCase):
    def config(self, root, platform="windows"):
        tools = root / "tools"
        tools.mkdir(exist_ok=True)
        godot = tools / "godot"
        godot.mkdir(exist_ok=True)
        commands = tools / "commands"
        commands.mkdir(exist_ok=True)
        for name in ("xvfb-run", "Xvfb", "xauth"):
            (commands / name).touch()
        with mock.patch.object(graphics, "host_platform", return_value=platform), \
             mock.patch.object(graphics.shutil, "which", side_effect=lambda name: str(commands / name)), \
             mock.patch.object(graphics, "_linux_packages", return_value={name: "fixture-version" for name in graphics.LINUX_PACKAGES}):
            return graphics.prepare_graphics(platform, godot, tools, mock.Mock())

    def observation(self, config):
        return {"policy": graphics.OBSERVATION_POLICY,
                "platform": config["platform"], "rendering_method": config["rendering_method"],
                "rendering_driver": config["rendering_driver"], "detected_format_mask": 7,
                "resource_buffer_probe": True, "software_adapter": True,
                "adapter_type": 4 if config["platform"] == "windows" else 0,
                "adapter_name": "Microsoft Basic Render Driver" if config["platform"] == "windows" else "llvmpipe (LLVM fixture)"}

    def test_windows_uses_system_warp_without_driver_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            self.assertEqual(config["rendering_driver"], "d3d12")
            self.assertEqual(config["gpu_index"], 0)
            self.assertEqual(config["command_prefix"], [])
            self.assertFalse(config["ships_driver_files"])
            self.assertTrue(config["requires_actual_observation"])

    def test_linux_requests_real_llvmpipe_x11_display(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary), "linux")
            command = graphics.cook_command(config, ["godot", "--script", "cook.gd", "--", "--variant=full"])
            self.assertEqual(command[1:4], ["-a", "-s", "-screen 0 1280x720x24 -nolisten tcp"])
            self.assertIn("opengl3", command)
            self.assertIn("x11", command)
            self.assertNotIn("--headless", command)
            self.assertEqual(command[-2:], ["--", "--variant=full"])
            self.assertEqual(config["env"]["GALLIUM_DRIVER"], "llvmpipe")

    def test_environment_is_process_local_and_removes_feature_spoofing(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary), "linux")
            original = {"MESA_GL_VERSION_OVERRIDE": "9.9", "MESA_EXTENSION_OVERRIDE": "+fake", "VK_ICD_FILENAMES": "bad", "UNCHANGED": "yes"}
            result = graphics.child_environment(config, original)
            self.assertEqual(original["MESA_GL_VERSION_OVERRIDE"], "9.9")
            self.assertNotIn("MESA_EXTENSION_OVERRIDE", result)
            self.assertNotIn("VK_ICD_FILENAMES", result)
            self.assertEqual(result["UNCHANGED"], "yes")

    def test_conflicting_headless_renderer_duplicate_and_gpu_flags_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            for flags in (["--headless"], ["--rendering-driver", "vulkan"], ["--rendering-method=mobile"],
                          ["--display-driver", "headless"], ["--gpu-index", "1"],
                          ["--gpu-index=0", "--gpu-index", "0"]):
                with self.subTest(flags=flags), self.assertRaises(ValueError):
                    graphics.cook_command(config, ["godot", *flags])

    def test_matching_flags_preserved_once_and_script_flags_not_interpreted(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            command = graphics.cook_command(config, ["godot", "--rendering-driver=d3d12", "--", "--gpu-index=2"])
            self.assertEqual(command.count("--rendering-driver=d3d12"), 1)
            self.assertEqual(command[-2:], ["--", "--gpu-index=2"])

    def test_observed_windows_cpu_and_linux_other_are_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            for platform in ("windows", "linux"):
                config = self.config(Path(temporary), platform)
                observation = self.observation(config)
                receipt = graphics.validate_observation(config, observation)
                self.assertEqual(receipt["observed"], observation)
                self.assertEqual(receipt["status"], "verified")

    def test_missing_capability_readback_or_actual_driver_rejects(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary))
            for update in ({"detected_format_mask": 0}, {"detected_format_mask": True},
                           {"policy": "unsupported"},
                           {"resource_buffer_probe": False}, {"resource_buffer_probe": 1},
                           {"software_adapter": False}, {"adapter_type": 2},
                           {"adapter_name": "Hardware GPU"}, {"rendering_driver": "vulkan"},
                           {"rendering_method": "gl_compatibility"}, {"platform": "linux"}):
                with self.subTest(update=update), self.assertRaises(ValueError):
                    graphics.validate_observation(config, dict(self.observation(config), **update))

    def test_linux_rejects_hardware_even_with_claimed_software_boolean(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary), "linux")
            with self.assertRaisesRegex(ValueError, "llvmpipe"):
                graphics.validate_observation(config, dict(self.observation(config), adapter_name="NVIDIA"))

    def test_native_os_accounted_root_and_no_sideload_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.config(root)
            with mock.patch.object(graphics, "host_platform", return_value="linux"), self.assertRaises(ValueError):
                graphics.prepare_graphics("windows", config["godot_dir"], config["tool_root"], mock.Mock())
            with mock.patch.object(graphics, "host_platform", return_value="windows"):
                for change in ({"external_driver_dir": root}, {"gpu_index": -1}, {"gpu_index": True}):
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        graphics.prepare_graphics("windows", config["godot_dir"], config["tool_root"], mock.Mock(), **change)
                with self.assertRaisesRegex(ValueError, "accounted"):
                    graphics.prepare_graphics("windows", root, config["tool_root"], mock.Mock())

    def test_missing_xvfb_dependency_fails_before_cook(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.config(Path(temporary), "linux")
            with mock.patch.object(graphics, "host_platform", return_value="linux"), \
                 mock.patch.object(graphics.shutil, "which", return_value=None), self.assertRaisesRegex(ValueError, "xvfb"):
                graphics.prepare_graphics("linux", config["godot_dir"], config["tool_root"], mock.Mock())

    def test_package_inventory_requires_exact_installed_entries(self):
        good = "".join(name + ":amd64\t1.2\tinstalled\n" for name in graphics.LINUX_PACKAGES)
        with mock.patch.object(graphics.subprocess, "run", return_value=mock.Mock(stdout=good)):
            self.assertEqual(set(graphics._linux_packages()), set(graphics.LINUX_PACKAGES))
        for bad in (good.rsplit("\n", 2)[0], good + good.splitlines()[0] + "\n", good.replace("installed", "unpacked", 1)):
            with self.subTest(bad=bad), mock.patch.object(graphics.subprocess, "run", return_value=mock.Mock(stdout=bad)), self.assertRaises(ValueError):
                graphics._linux_packages()


if __name__ == "__main__":
    unittest.main()
