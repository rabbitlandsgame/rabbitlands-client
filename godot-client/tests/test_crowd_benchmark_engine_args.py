"""Wave 2 MOB-C6a: engine options, warm profiles and renderer choice in the benchmark runners.

No engine, assets or GPU: --engine-arg parsing and placement, --seed-profile copying
and attestation, the uncapped Performance preset, the plain-Low body-cap pin
(LAT-L5), and tools/continent_stream_benchmark.py --renderer/--engine-arg.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS / "integration"))
sys.path.insert(0, str(TESTS))
import crowd_benchmark_support as support  # noqa: E402
import run_crowd_presentation_benchmark as runner  # noqa: E402
import test_crowd_benchmark_runner as base_tests  # noqa: E402  Its helpers; its tests are not re-collected.

_spec = importlib.util.spec_from_file_location(
    "continent_stream_benchmark_c6a", TESTS.parent / "tools/continent_stream_benchmark.py")
continent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(continent)

WINDOWED = ["--mode", "windowed", "--cells", "s3-market-160", "--minimap", "show",
            "--sample-ms", "1000", "--warmup-ms", "100"]


def seed_tree(root: Path, layout: str = "Godot/app_userdata/Eloria") -> Path:
    """A finished run's user root: caches the seed copies, and things it must not."""
    user = root / layout
    for relative, content in (("shader_cache/CanvasShaderRD/abc/0.cache", b"canvas"),
                              ("shader_cache/SceneForwardClusteredShaderRD/def/1.cache", b"scene"),
                              ("vulkan/pipelines.forward_plus.intel_r_graphics.cache", b"fplus"),
                              ("vulkan/pipelines.mobile.intel_r_graphics.cache", b"mobile"),
                              ("d3d12/pipelines.forward_plus.intel_r_graphics.cache", b"dx"),
                              ("eloria_hud.cfg", b"[graphics]\nquality=\"high\"\n"),
                              ("map-geometry-cache/policy/entry.res", b"prepared"),
                              ("logs/godot.log", b"log")):
        path = user / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return user


class EngineArgTests(unittest.TestCase):
    def test_forms_order_and_values(self):
        parse = support.parse_engine_args
        self.assertEqual(parse([], "forward_plus", "windowed"), [])
        self.assertEqual(parse(None, "forward_plus", "headless"), [])
        self.assertEqual(parse(["--gpu-index 1"], "forward_plus", "windowed"), ["--gpu-index", "1"])
        self.assertEqual(parse(["--gpu-index=1", "--gpu-profile", "--rendering-driver=d3d12"], "mobile", "windowed"),
                         ["--gpu-index", "1", "--gpu-profile", "--rendering-driver", "d3d12"])
        self.assertEqual(parse(["--rendering-driver", "vulkan"], "forward_plus", "windowed"),
                         ["--rendering-driver", "vulkan"])
        self.assertEqual(parse(["--rendering-driver opengl3_angle"], "gl_compatibility", "windowed"),
                         ["--rendering-driver", "opengl3_angle"])
        self.assertEqual(support.engine_arg_value(["--gpu-index", "1", "--rendering-driver", "d3d12"],
                                                  "--rendering-driver"), "d3d12")
        self.assertEqual(support.engine_arg_value(["--gpu-profile"], "--gpu-profile"), "")
        self.assertIsNone(support.engine_arg_value([], "--rendering-driver"))

    def test_refusals(self):
        for values, renderer, mode, message in (
                (["--rendering-method mobile"], "forward_plus", "windowed", "unsupported"),
                (["--path elsewhere"], "forward_plus", "windowed", "unsupported"),
                (["--log-file x.log"], "forward_plus", "windowed", "unsupported"),
                (["--script res://other.gd"], "forward_plus", "windowed", "unsupported"),
                (["--resolution 640x480"], "forward_plus", "windowed", "unsupported"),
                (["--headless"], "forward_plus", "windowed", "unsupported"),
                (["--"], "forward_plus", "windowed", "unsupported"),
                (["1"], "forward_plus", "windowed", "unsupported"),
                (["--gpu-index 1", "--gpu-index=0"], "forward_plus", "windowed", "twice"),
                (["--gpu-index"], "forward_plus", "windowed", "needs a value"),
                (["--gpu-index="], "forward_plus", "windowed", "needs a value"),
                (["--gpu-index -1"], "forward_plus", "windowed", "device index"),
                (["--gpu-index one"], "forward_plus", "windowed", "device index"),
                (["--rendering-driver opengl3"], "forward_plus", "windowed", "does not run"),
                (["--rendering-driver d3d12"], "gl_compatibility", "windowed", "does not run"),
                (["--rendering-driver d3d11"], "mobile", "windowed", "does not run"),
                (["--gpu-profile"], "forward_plus", "headless", "windowed"),
                (["--gpu-index 1"], "forward_plus", "headless", "windowed")):
            with self.subTest(values=values, renderer=renderer, mode=mode), \
                    self.assertRaisesRegex(support.EvidenceError, message):
                support.parse_engine_args(values, renderer, mode)

    def test_argparse_forms_reach_the_engine_command_first(self):
        args = runner.parser().parse_args(["--godot", "godot.exe", *WINDOWED, "--engine-arg=--gpu-index=1",
                                          "--engine-arg", "--rendering-driver d3d12", "--engine-arg=--gpu-profile"])
        self.assertEqual(args.engine_arg, ["--gpu-index=1", "--rendering-driver d3d12", "--gpu-profile"])
        args.engine_args = support.parse_engine_args(args.engine_arg, args.renderer, args.mode)
        command = runner.command_for(args, Path("engine.log"))
        self.assertEqual(command[1:7], ["--gpu-index", "1", "--rendering-driver", "d3d12", "--gpu-profile", "--path"])
        self.assertEqual(command[command.index("--rendering-method") + 1], "forward_plus")
        self.assertEqual(command.count("--rendering-method"), 1)
        self.assertEqual(runner.request_for(args)["engine_args"],
                         ["--gpu-index", "1", "--rendering-driver", "d3d12", "--gpu-profile"])
        args.executable_mode, args.main_pack = "exported", Path("workload.pck")
        self.assertEqual(runner.command_for(args, Path("engine.log"))[1:7],
                         ["--gpu-index", "1", "--rendering-driver", "d3d12", "--gpu-profile", "--main-pack"])
        plain = runner.parser().parse_args(["--godot", "godot.exe"])
        self.assertEqual(runner.command_for(plain, Path("engine.log"))[1], "--path")
        self.assertEqual(runner.request_for(plain)["engine_args"], [])
        self.assertIsNone(runner.request_for(plain)["seed_profile"])

    def test_main_refuses_before_launch(self):
        for extra in (["--engine-arg=--gpu-index=1"],  # headless default
                      ["--mode", "windowed", "--engine-arg=--rendering-method=mobile"],
                      ["--mode", "windowed", "--renderer", "gl_compatibility", "--engine-arg=--rendering-driver=vulkan"],
                      ["--mode", "windowed", "--quality", "low", "--measurement-status", "quiet-comparison"]):
            with self.subTest(extra=extra), mock.patch.object(runner, "executable_path") as resolve, \
                    mock.patch.object(runner, "run_one") as run_one, mock.patch.object(sys, "stderr"):
                self.assertEqual(runner.main(["--godot", "unused", *extra]), 1)
                resolve.assert_not_called()
                run_one.assert_not_called()

    def test_requested_driver_is_validated_against_the_report(self):
        data, request = base_tests.fixture()
        request["engine_args"] = ["--gpu-index", "1", "--rendering-driver", "d3d12"]
        data["renderingDriver"] = "d3d12"
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for actual in ("vulkan", None):
            bad = copy.deepcopy(data)
            bad["renderingDriver"] = actual
            with self.subTest(actual=actual), self.assertRaisesRegex(support.EvidenceError, "rendering driver"):
                support.validate_report(bad, request, "")
        # Without a requested driver the field is informational (older reports omit it).
        request["engine_args"] = ["--gpu-index", "1"]
        data.pop("renderingDriver")
        self.assertTrue(support.validate_report(data, request, "")["valid"])


class GpuTimestampTests(unittest.TestCase):
    def test_a_wrapped_gpu_timestamp_rejects_the_rendered_run(self):
        # Measured on the iGPU proxy (Mobile, seeded, market cell): one of 60 world GPU
        # readings was 18446739832832.0 ms and the cell's mean became 3.07e11 ms.
        data, request = base_tests.fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for metric in support.GPU_TIME_METRICS:
            bad = copy.deepcopy(data)
            summary = bad["cells"][0]["summary"]
            series = summary.get(metric) or base_tests.distribution([0.5] * 60)
            summary[metric] = dict(series, max=18446739832832.0)
            with self.subTest(metric=metric), self.assertRaisesRegex(support.EvidenceError, "wrapped GPU timestamp"):
                support.validate_report(bad, request, "")
        ok = copy.deepcopy(data)
        ok["cells"][0]["summary"]["rootRenderGpuMilliseconds"] = base_tests.distribution([0.5] * 59 + [900.0])
        self.assertTrue(support.validate_report(ok, request, "")["valid"])  # Slow, not impossible.
        support.validate_gpu_timestamps({}, "empty")  # Nothing measured, nothing refused.


class UncappedPerformanceTests(unittest.TestCase):
    def test_fps_cap_zero_is_the_only_override_a_preset_takes(self):
        for profile in ("performance", "performance-60", "performance-60-scale50"):
            args = runner.parser().parse_args(["--godot", "unused", "--settings-profile", profile, "--fps-cap", "0"])
            support.configure_settings_profile(args, system="Windows")
            self.assertEqual((args.quality, args.fps_cap, args.body_cap), ("low", 0, 60))
            support.configure_settings_profile(args, system="Windows")  # Idempotent per repeat.
            self.assertEqual(args.fps_cap, 0)
        for cap in ("60", "120"):
            args = runner.parser().parse_args(["--godot", "unused", "--settings-profile", "performance", "--fps-cap", cap])
            with self.subTest(cap=cap), self.assertRaisesRegex(support.EvidenceError, "fps-cap"):
                support.configure_settings_profile(args, system="Windows")

    def test_uncapped_preset_report_validates_and_keeps_the_preset_seed(self):
        data, request = base_tests.performance_fixture()
        request["fps_cap"] = 0
        data["measurement"]["fpsCap"] = 0
        for observed in (data, data["cells"][0]["effectiveRuntime"]):
            observed["effectiveSettings"]["frameCap"] = 0
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        bad = copy.deepcopy(data)
        bad["effectiveSettings"]["frameCap"] = 30
        with self.assertRaisesRegex(support.EvidenceError, "frameCap"):
            support.validate_report(bad, request, "")
        request["fps_cap"] = 45
        with self.assertRaisesRegex(support.EvidenceError, "frame cap differs"):
            support.validate_runtime(data, request, "forward_plus", "low", 60, "report")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_tests.write_project(root)
            fresh = root / "isolated"
            fresh.mkdir()
            seeded = support.seed_settings_profile("performance", root, fresh, {"APPDATA": str(fresh)}, "Windows")
            self.assertIn("fps_limit=30\n", seeded["content"])  # The preset as players get it.


class BodyCapPinTests(unittest.TestCase):
    def args(self, *extra):
        args = runner.parser().parse_args(["--godot", "unused", *extra])
        support.configure_settings_profile(args, system="Windows")
        return args

    def test_plain_low_comparisons_state_the_cap(self):
        with self.assertRaisesRegex(support.EvidenceError, "--body-cap 160"):
            support.require_pinned_body_cap(self.args("--quality", "low", "--measurement-status", "quiet-comparison"))
        note = support.require_pinned_body_cap(self.args("--quality", "low"))
        self.assertIn("--body-cap 160", note)
        for extra in (["--quality", "low", "--body-cap", "160", "--measurement-status", "quiet-comparison"],
                      ["--quality", "low", "--body-cap", "60", "--measurement-status", "quiet-comparison"],
                      ["--quality", "high", "--measurement-status", "quiet-comparison"],
                      ["--measurement-status", "quiet-comparison"],
                      ["--settings-profile", "performance", "--measurement-status", "quiet-comparison"],
                      ["--settings-profile", "performance", "--fps-cap", "0", "--measurement-status", "quiet-comparison"]):
            with self.subTest(extra=extra):
                self.assertIsNone(support.require_pinned_body_cap(self.args(*extra)))


class SeedProfileTests(unittest.TestCase):
    def test_source_forms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user = seed_tree(root / "run")
            self.assertEqual(support.profile_seed_source(root / "run"), user.resolve())
            self.assertEqual(support.profile_seed_source(user), user.resolve())
            linux = seed_tree(root / "linux-run", "godot/app_userdata/Eloria")
            self.assertEqual(support.profile_seed_source(root / "linux-run"), linux.resolve())
            (root / "empty/Godot/app_userdata/Eloria").mkdir(parents=True)
            for path, message in ((root / "empty", "holds no"), (root / "missing", "does not exist")):
                with self.subTest(path=path), self.assertRaisesRegex(support.EvidenceError, message):
                    support.profile_seed_source(path)

    def test_copies_only_caches_and_verifies_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_tests.write_project(root)
            seed_tree(root / "warm")
            digests = []
            for name in ("fresh-a", "fresh-b"):
                fresh = root / name
                fresh.mkdir()
                seeded = support.seed_profile_caches(root / "warm", root, fresh, {"APPDATA": str(fresh)}, "Windows")
                user = fresh / "Godot/app_userdata/Eloria"
                self.assertEqual(Path(seeded["userDataDir"]), user)
                self.assertEqual((user / "vulkan/pipelines.mobile.intel_r_graphics.cache").read_bytes(), b"mobile")
                self.assertEqual((user / "shader_cache/CanvasShaderRD/abc/0.cache").read_bytes(), b"canvas")
                for absent in ("eloria_hud.cfg", "map-geometry-cache", "logs"):
                    self.assertFalse((user / absent).exists(), absent)
                self.assertEqual(seeded["directories"], {"shader_cache": {"files": 2, "bytes": 11},
                                                         "vulkan": {"files": 2, "bytes": 11},
                                                         "d3d12": {"files": 1, "bytes": 2}})
                self.assertEqual((seeded["files"], seeded["bytes"]), (5, 24))
                self.assertEqual(seeded["pipelineCaches"], ["d3d12/pipelines.forward_plus.intel_r_graphics.cache",
                                                            "vulkan/pipelines.forward_plus.intel_r_graphics.cache",
                                                            "vulkan/pipelines.mobile.intel_r_graphics.cache"])
                digests.append(seeded["sha256"])
            self.assertEqual(digests[0], digests[1])
            (root / "warm/Godot/app_userdata/Eloria/vulkan/pipelines.mobile.intel_r_graphics.cache").write_bytes(b"other")
            fresh = root / "fresh-c"
            fresh.mkdir()
            changed = support.seed_profile_caches(root / "warm", root, fresh, {"APPDATA": str(fresh)}, "Windows")
            self.assertNotEqual(changed["sha256"], digests[0])

    def test_linux_and_refusals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_tests.write_project(root)
            seed_tree(root / "warm")
            fresh = root / "linux"
            fresh.mkdir()
            seeded = support.seed_profile_caches(root / "warm", root, fresh, {"XDG_DATA_HOME": str(fresh)}, "Linux")
            self.assertEqual(Path(seeded["userDataDir"]), fresh / "godot/app_userdata/Eloria")
            with self.assertRaisesRegex(support.EvidenceError, "would overwrite"):
                support.seed_profile_caches(root / "warm", root, fresh, {"XDG_DATA_HOME": str(fresh)}, "Linux")
            other = root / "other"
            other.mkdir()
            with self.assertRaisesRegex(support.EvidenceError, "fresh isolated APPDATA"):
                support.seed_profile_caches(root / "warm", root, other, {"APPDATA": str(root / "player")}, "Windows")
            with self.assertRaisesRegex(support.EvidenceError, "Windows and Linux"):
                support.seed_profile_caches(root / "warm", root, other, {"APPDATA": str(other)}, "Darwin")
            with self.assertRaisesRegex(support.EvidenceError, "overlaps"):
                support.seed_profile_caches(root / "warm", root, root / "warm", {"APPDATA": str(root / "warm")},
                                            "Windows")
            empty = root / "empty/Godot/app_userdata/Eloria/vulkan"
            empty.mkdir(parents=True)
            with self.assertRaisesRegex(support.EvidenceError, "empty"):
                support.seed_profile_caches(root / "empty", root, other, {"APPDATA": str(other)}, "Windows")

    def test_links_are_refused(self):
        made = 0
        for kind in ("symlink", "junction"):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base_tests.write_project(root)
                user = seed_tree(root / "warm")
                outside = root / "outside"
                outside.mkdir()
                (outside / "player.cache").write_bytes(b"outside")
                try:
                    if kind == "symlink":
                        os.symlink(outside / "player.cache", user / "vulkan/linked.cache")
                    else:
                        import _winapi  # Windows only; a junction needs no privilege.
                        _winapi.CreateJunction(str(outside), str(user / "shader_cache/linked"))
                except (OSError, NotImplementedError, ImportError):
                    continue
                made += 1
                fresh = root / "fresh"
                fresh.mkdir()
                with self.subTest(kind=kind), self.assertRaisesRegex(support.EvidenceError, "link"):
                    support.seed_profile_caches(root / "warm", root, fresh, {"APPDATA": str(fresh)}, "Windows")
                self.assertFalse((fresh / "Godot/app_userdata/Eloria/shader_cache/linked/player.cache").exists())
        if not made:
            self.skipTest("this account can create neither symbolic links nor junctions")

    def test_headless_runs_take_no_seed(self):
        # A headless run compiles no shaders: a valid seed would only label it warm.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_tree(root / "warm")
            with mock.patch.object(runner, "executable_path") as resolve, \
                    mock.patch.object(runner, "run_one") as run_one, mock.patch.object(sys, "stderr") as stderr:
                self.assertEqual(runner.main(["--godot", "unused", "--seed-profile", str(root / "warm"),
                                              "--out-dir", str(root / "out"), "--lock-path", str(root / "lock")]), 1)
            resolve.assert_not_called()
            run_one.assert_not_called()
            self.assertIn("rendered", "".join(str(call) for call in stderr.write.call_args_list))
            self.assertFalse((root / "out").exists())

    def run_seeded(self, ack_dir=None, profile="default"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_tests.write_project(root)
            seed_tree(root / "warm")
            exe = root / "Godot.exe"
            exe.write_bytes(b"not executed")
            extra = ["--settings-profile", "performance"] if profile == "performance" else []
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root), *WINDOWED, *extra,
                                              "--seed-profile", str(root / "warm"),
                                              "--engine-arg=--gpu-index=1", "--engine-arg=--rendering-driver=d3d12"])
            args.godot = exe
            support.configure_settings_profile(args, system="Windows")
            args.engine_args = support.parse_engine_args(args.engine_arg, args.renderer, args.mode)
            args.seed_profile = support.profile_seed_source(args.seed_profile)
            data, _request = base_tests.performance_fixture() if profile == "performance" else base_tests.fixture()
            data["renderingDriver"] = "d3d12"
            seen = {}

            def fake_launch(command, *, env, stdout, **_kwargs):
                user_dir = Path(env["APPDATA"]) / "Godot/app_userdata/Eloria"
                seen["command"] = command
                seen["cache"] = (user_dir / "vulkan/pipelines.forward_plus.intel_r_graphics.cache").read_bytes()
                seen["settings"] = (user_dir / "eloria_hud.cfg").read_text() if (user_dir / "eloria_hud.cfg").exists() \
                    else None
                reported = Path(env["APPDATA"]) / ack_dir if ack_dir else user_dir
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(reported))
                base_tests.write_startup_ack(env, exe, reported)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))

            with mock.patch.object(support.platform, "system", return_value="Windows"), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                result = runner.run_one(args, "all", 1, root)
            recorded = support.read_json(next(root.glob("*.process.json")))
            return result, seen, recorded

    def test_run_one_seeds_before_launch_and_records_it(self):
        result, seen, recorded = self.run_seeded()
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertEqual(seen["command"][1:5], ["--gpu-index", "1", "--rendering-driver", "d3d12"])
        self.assertEqual(seen["cache"], b"fplus")
        self.assertIsNone(seen["settings"])  # The source's settings never travel with the caches.
        self.assertEqual(result["engineArgs"], ["--gpu-index", "1", "--rendering-driver", "d3d12"])
        self.assertEqual(result["profileSeed"]["files"], 5)
        self.assertEqual(recorded["profileSeed"]["sha256"], result["profileSeed"]["sha256"])
        self.assertEqual(recorded["engineArgs"], result["engineArgs"])

    def test_seed_and_performance_settings_share_the_user_directory(self):
        result, seen, _recorded = self.run_seeded(profile="performance")
        self.assertTrue(result["validation"]["valid"], result["validation"])
        self.assertIn('map_texture_quality="half"', seen["settings"])  # Generated, not the source's file.
        self.assertEqual(result["profileSeed"]["userDataDir"], result["settingsSeed"]["userDataDir"])

    def test_engine_must_open_the_seeded_directory(self):
        result, _seen, _recorded = self.run_seeded(ack_dir="Godot/app_userdata/Other")
        self.assertFalse(result["validation"]["valid"])
        self.assertIn("--seed-profile", " ".join(result["validation"]["errors"]))
        data, request = base_tests.fixture()
        request["profile_seed_user_dir"] = str(TESTS / "seeded")
        data["runtimeBuild"]["userDataDir"] = str(TESTS / "elsewhere")
        with self.assertRaisesRegex(support.EvidenceError, "--seed-profile"):
            support.validate_report(data, request, "")


class ContinentRendererTests(unittest.TestCase):
    def test_command_uses_the_renderer_and_engine_options(self):
        command = continent.engine_command(Path("godot.exe"), Path("project"), Path("engine.log"), "mobile",
                                           ["--gpu-index", "1", "--gpu-profile"])
        self.assertEqual(command[1:4], ["--gpu-index", "1", "--gpu-profile"])
        self.assertEqual(command[command.index("--rendering-method") + 1], "mobile")
        self.assertEqual(command[-2:], ["--log-file", "engine.log"])
        default = continent.engine_command(Path("godot.exe"), Path("project"), Path("engine.log"))
        self.assertEqual(default[default.index("--rendering-method") + 1], "forward_plus")
        self.assertEqual(default[1], "--path")
        parse_only = continent.engine_command(Path("godot.exe"), Path("project"), Path("engine.log"), parse_only=True)
        self.assertIn("--headless", parse_only)
        self.assertNotIn("--rendering-method", parse_only)

    def test_report_must_match_the_requested_renderer_and_driver(self):
        report = {"ok": True, "configuration": {"run_id": "new"}, "configuration_sha256": "digest",
                  "frames": [{"phase": "walk", "frame_ms": 16, "ground_hit": True, "resident": True}],
                  "renderer": "mobile", "window_context": {"start": {"render_driver": "d3d12"}}}
        configuration = {"run_id": "new", "renderer": "mobile", "engine_args": ["--rendering-driver", "d3d12"]}
        self.assertEqual(continent.qualification_errors(report, configuration, "digest", {}, {}), [])
        wrong = copy.deepcopy(report)
        wrong["renderer"] = "forward_plus"
        wrong["window_context"]["start"]["render_driver"] = "vulkan"
        self.assertEqual(continent.qualification_errors(wrong, configuration, "digest", {}, {}),
                         ["renderer_mismatch", "rendering_driver_mismatch"])
        # Configurations from before --renderer carry neither key.
        self.assertEqual(continent.qualification_errors(wrong, {"run_id": "new"}, "digest", {}, {}), [])

    def test_main_refuses_engine_options_it_cannot_honour(self):
        for extra in (["--engine-arg=--rendering-method=mobile"], ["--parse-only", "--engine-arg=--gpu-index=1"],
                      ["--renderer", "gl_compatibility", "--engine-arg=--rendering-driver=d3d12"]):
            with self.subTest(extra=extra), mock.patch.object(sys, "argv", ["continent_stream_benchmark.py", *extra]), \
                    mock.patch.object(continent.subprocess, "Popen") as popen, mock.patch.object(sys, "stderr"), \
                    self.assertRaises(SystemExit):
                continent.main()
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
