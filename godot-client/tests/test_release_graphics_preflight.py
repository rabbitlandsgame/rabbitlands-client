"""Fake-process launcher/lifetime checks; no renderer, native API or network."""
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import release_graphics_preflight as preflight


class FinishedChild:
    def __init__(self, code):
        self.returncode = code
        self.pid = 7654321

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class GraphicsPreflightTests(unittest.TestCase):
    def fixture(self, temporary):
        base = Path(temporary)
        tools = base / "fixture-tools"
        tools.mkdir()
        for name in preflight.SCRIPTS:
            (tools / name).write_text("extends RefCounted\n# " + name + "\n", encoding="utf-8")
        godot = base / "fake-godot.exe"
        godot.write_bytes(b"fake engine; never executed")
        sibling = base / "preserved-sibling"
        sibling.mkdir()
        (sibling / "keep.txt").write_text("unrelated", encoding="utf-8")
        config = {"platform": "windows", "rendering_method": "forward_plus",
                  "rendering_driver": "d3d12", "display_driver": "windows",
                  "gpu_index": 2, "command_prefix": [], "env": {}}
        return base / "owned-preflight", tools, godot, sibling, config

    def launch(self, config, godot, root, tools, *, code=0, report=None,
               launch_text="fixture engine completed\n", engine_text="fixture renderer ready\n",
               tamper_owner=False, verification_error=None, environment=None, budget=None):
        if report is None:
            # The actual report schema is independently tested elsewhere.
            # Keep distinctive observed failure fields to verify retention.
            report = {"schema_version": 1, "status": "pass", "failures": [],
                      "graphics": {"adapter_name": "Microsoft Basic Render Driver",
                                   "adapter_type": 4, "detected_format_mask": 7,
                                   "resource_buffer_probe": True}}
        calls = []

        def fake_popen(command, **kwargs):
            calls.append((list(command), kwargs))
            job_path = Path(command[command.index("--") + 1])
            job = json.loads(job_path.read_text(encoding="utf-8"))
            project = Path(job["expected_project_root"])
            users = Path(job["expected_user_directory"])
            users.mkdir(parents=True)
            (users / "shader-cache.bin").write_bytes(b"generated user cache")
            (project / ".godot").mkdir()
            (project / ".godot" / "shader-cache.bin").write_bytes(b"generated project cache")
            Path(job["report"]).write_text(json.dumps(report), encoding="utf-8")
            (root / "engine.log").write_text(engine_text, encoding="utf-8")
            kwargs["stdout"].write(launch_text)
            kwargs["stdout"].flush()
            if tamper_owner:
                owner_path = root / "owner.json"
                owner = json.loads(owner_path.read_text(encoding="utf-8"))
                owner["root"] = str(root.parent / "preserved-sibling")
                owner_path.write_text(json.dumps(owner), encoding="utf-8")
            return FinishedChild(code)

        validator = mock.Mock(return_value={"status": "verified", "fixture": "actual report gate called"},
                              side_effect=verification_error)
        process = mock.Mock(side_effect=fake_popen)
        with mock.patch.object(preflight, "TOOLS", tools), \
             mock.patch.object(preflight.subprocess, "Popen", process), \
             mock.patch.object(preflight.graphics, "validate_preflight_report", validator), \
             mock.patch.dict(os.environ, environment or {}, clear=True):
            result = preflight.run_preflight(config, godot, root, budget or mock.Mock())
        return result, calls, validator, process

    def test_child_credentials_and_feature_overrides_are_removed_without_parent_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, _, config = self.fixture(temporary)
            inherited = {name: "fixture-private-value" for name in preflight.PRIVATE_ENV}
            inherited.update({"ELORIA_NATIVE_PRESENTATION": "all", "RABBITLANDS_CLIENT_RUNTIME": "rust",
                              "RABBITLANDS_PREPARED_CONTENT": "require-pilot", "MESA_GL_VERSION_OVERRIDE": "99",
                              "VK_ICD_FILENAMES": "fixture.json", "UNCHANGED": "yes"})
            with mock.patch.dict(os.environ, inherited, clear=True):
                before = dict(os.environ)
                _, calls, _, _ = self.launch(config, godot, root, tools, environment=inherited)
                self.assertEqual(dict(os.environ), before)
            command, kwargs = calls[0]
            child_env = kwargs["env"]
            for name in inherited:
                if name != "UNCHANGED":
                    self.assertNotIn(name, child_env)
            self.assertEqual(child_env["UNCHANGED"], "yes")
            for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
                self.assertEqual(Path(child_env[name]), root / "users")
            self.assertEqual(kwargs["cwd"], root)
            self.assertEqual(kwargs["stderr"], preflight.subprocess.STDOUT)
            self.assertEqual(kwargs["start_new_session"], os.name != "nt")
            self.assertEqual(command[0], str(godot))
            self.assertEqual(command[command.index("--gpu-index") + 1], "2")
            self.assertIn("Dummy", command)

    def test_success_keeps_bound_evidence_and_retires_only_owned_project_and_users(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, sibling, config = self.fixture(temporary)
            budget = mock.Mock()
            result, calls, validator, process = self.launch(config, godot, root, tools, budget=budget)
            self.assertEqual(result["status"], "verified_scratch_retired")
            self.assertEqual(result["exit"], 0)
            self.assertEqual(result["engine_sha256"], hashlib.sha256(godot.read_bytes()).hexdigest())
            self.assertEqual(set(path.name for path in root.iterdir()),
                             {"owner.json", "job.json", "report.json", "receipt.json", "launch.log", "engine.log"})
            self.assertEqual(json.loads((root / "receipt.json").read_text()), result)
            self.assertEqual(json.loads((root / "report.json").read_text()), result["report"])
            self.assertFalse((root / "project").exists())
            self.assertFalse((root / "users").exists())
            self.assertEqual((sibling / "keep.txt").read_text(), "unrelated")
            self.assertEqual(set(result["scripts"]), set(preflight.SCRIPTS))
            for name, identity in result["scripts"].items():
                self.assertEqual(identity["sha256"], hashlib.sha256((tools / name).read_bytes()).hexdigest())
            validator.assert_called_once_with(config, result["report"], project=root / "project",
                                               user_directory=root / "users" / "RabbitLandsReleaseGraphicsProbe",
                                               godot=godot)
            process.assert_called_once()
            self.assertEqual(len(calls), 1)
            self.assertEqual(budget.call_args_list,
                             [mock.call("before standalone graphics preflight", 256 * 1024**2),
                              mock.call("standalone graphics preflight verified and scratch retired")])

    def test_nonzero_exit_retains_actual_failed_observation_logs_and_scratch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, sibling, config = self.fixture(temporary)
            failed = {"status": "failed", "graphics": {"adapter_name": "Actual Hardware Fixture",
                      "adapter_type": 2, "detected_format_mask": 3}, "failures": ["CPU required"]}
            with self.assertRaisesRegex(ValueError, "preflight failed"):
                self.launch(config, godot, root, tools, code=7, report=failed,
                            launch_text="actual renderer failure retained\n")
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["report"], failed)
            self.assertEqual(receipt["exit"], 7)
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("actual renderer failure", (root / "launch.log").read_text())
            self.assertTrue((root / "project" / ".godot" / "shader-cache.bin").is_file())
            self.assertTrue((root / "users" / "RabbitLandsReleaseGraphicsProbe" / "shader-cache.bin").is_file())
            self.assertEqual((sibling / "keep.txt").read_text(), "unrelated")

    def test_rejected_report_retains_observation_and_scratch_even_with_exit_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, _, config = self.fixture(temporary)
            actual = {"status": "pass", "graphics": {"adapter_type": 4, "detected_format_mask": 0,
                      "adapter_name": "Actual WARP Fixture"}}
            with self.assertRaisesRegex(ValueError, "fixture actual mask mismatch"):
                self.launch(config, godot, root, tools, report=actual,
                            verification_error=ValueError("fixture actual mask mismatch"))
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["report"], actual)
            self.assertEqual(receipt["exit"], 0)
            self.assertEqual(receipt["status"], "failed")
            self.assertTrue((root / "project").is_dir())
            self.assertTrue((root / "users").is_dir())

    def test_zero_exit_ansi_shader_error_and_leak_diagnostics_reject_in_either_sink(self):
        diagnostics = ("\x1b[31mSHADER ERROR: fixture compiler failure\x1b[0m\n",
                       "\x1b[1mERROR: fixture renderer failure\x1b[0m\n",
                       "WARNING: ObjectDB instances leaked at exit\n",
                       "Resources still in use at exit\n")
        for diagnostic in diagnostics:
            for sink in ("launch", "engine"):
                with self.subTest(diagnostic=diagnostic, sink=sink), tempfile.TemporaryDirectory() as temporary:
                    root, tools, godot, _, config = self.fixture(temporary)
                    text = {"launch_text" if sink == "launch" else "engine_text": diagnostic}
                    with self.assertRaisesRegex(ValueError, "Engine diagnostic"):
                        self.launch(config, godot, root, tools, **text)
                    receipt = json.loads((root / "receipt.json").read_text())
                    self.assertEqual(receipt["status"], "failed")
                    self.assertEqual(receipt["exit"], 0)
                    self.assertEqual((root / ("launch.log" if sink == "launch" else "engine.log")).read_text(), diagnostic)
                    self.assertTrue((root / "project").is_dir())
                    self.assertTrue((root / "users").is_dir())

    def test_verified_linux_vsync_warning_is_receipted_and_raw_logs_are_preserved(self):
        for sink in ("launch", "engine"):
            with self.subTest(sink=sink), tempfile.TemporaryDirectory() as temporary:
                root, tools, godot, _, config = self.fixture(temporary)
                config.update(platform="linux", rendering_method="gl_compatibility",
                              rendering_driver="opengl3", display_driver="x11", gpu_index=None)
                warning = preflight.LINUX_VSYNC_WARNING + "\n   at: set_use_vsync (gl_manager_x11.cpp:372)\n"
                arguments = {"launch_text" if sink == "launch" else "engine_text": warning}
                result, _, validator, _ = self.launch(config, godot, root, tools, **arguments)
                validator.assert_called_once()
                self.assertEqual(result["status"], "verified_scratch_retired")
                self.assertEqual(result["allowed_driver_warnings"], [preflight.LINUX_VSYNC_WARNING])
                self.assertEqual((root / ("launch.log" if sink == "launch" else "engine.log")).read_text(), warning)
                self.assertFalse((root / "project").exists())

    def test_driver_warning_exception_requires_exact_linux_gl_context(self):
        cases = (("windows", "forward_plus", "d3d12", preflight.LINUX_VSYNC_WARNING),
                 ("linux", "forward_plus", "vulkan", preflight.LINUX_VSYNC_WARNING),
                 ("linux", "gl_compatibility", "opengl3", preflight.LINUX_VSYNC_WARNING + " altered"),
                 ("linux", "gl_compatibility", "opengl3", "WARNING: unrecognized driver warning"))
        for platform, method, driver, warning in cases:
            with self.subTest(warning=warning, platform=platform, method=method), tempfile.TemporaryDirectory() as temporary:
                root, tools, godot, _, config = self.fixture(temporary)
                config.update(platform=platform, rendering_method=method, rendering_driver=driver)
                with self.assertRaisesRegex(ValueError, "Engine diagnostic"):
                    self.launch(config, godot, root, tools, launch_text=warning + "\n")
                self.assertEqual(json.loads((root / "receipt.json").read_text())["status"], "failed")
                self.assertTrue((root / "project").is_dir())

    def test_linux_warning_never_bypasses_report_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, _, config = self.fixture(temporary)
            config.update(platform="linux", rendering_method="gl_compatibility",
                          rendering_driver="opengl3", display_driver="x11", gpu_index=None)
            with self.assertRaisesRegex(ValueError, "actual mask mismatch"):
                self.launch(config, godot, root, tools, launch_text=preflight.LINUX_VSYNC_WARNING + "\n",
                            verification_error=ValueError("actual mask mismatch"))
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertNotIn("allowed_driver_warnings", receipt)
            self.assertTrue((root / "project").is_dir())

    def test_changed_owner_prevents_all_scratch_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, sibling, config = self.fixture(temporary)
            with self.assertRaisesRegex(ValueError, "ownership changed"):
                self.launch(config, godot, root, tools, tamper_owner=True)
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertIn("verification", receipt)
            self.assertTrue((root / "project" / ".godot").is_dir())
            self.assertTrue((root / "users" / "RabbitLandsReleaseGraphicsProbe").is_dir())
            self.assertEqual((sibling / "keep.txt").read_text(), "unrelated")

    def test_budget_refusal_precedes_project_creation_and_process_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, tools, godot, sibling, config = self.fixture(temporary)
            budget = mock.Mock(side_effect=ValueError("fixture capacity reserve refused"))
            with mock.patch.object(preflight, "TOOLS", tools), \
                 mock.patch.object(preflight.subprocess, "Popen") as process, \
                 mock.patch.object(preflight.graphics, "validate_preflight_report") as validator, \
                 self.assertRaisesRegex(ValueError, "capacity reserve refused"):
                preflight.run_preflight(config, godot, root, budget)
            budget.assert_called_once_with("before standalone graphics preflight", 256 * 1024**2)
            process.assert_not_called()
            validator.assert_not_called()
            self.assertFalse(root.exists())
            self.assertEqual((sibling / "keep.txt").read_text(), "unrelated")


if __name__ == "__main__":
    unittest.main()
