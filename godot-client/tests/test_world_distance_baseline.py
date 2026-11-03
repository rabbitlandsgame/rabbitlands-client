"""Wave 2 WD-C0: tools/world_distance_baseline.py plans and summarizes the camera-probe matrix.

No engine or GPU: the plan (interleaving, isolation, probe settings), the dry run, the
per-pose summary and the run result without a launch.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
import world_distance_baseline as baseline  # noqa: E402


def write_territory(maps: Path, name: str, tile) -> None:
    folder = maps / name / "client"
    folder.mkdir(parents=True)
    spawn = {"id": "arrival", "default": True, "position": [0, 0, 0]}
    if tile is not None:
        spawn["serverTile"] = tile
    folder.joinpath("world.json").write_text(json.dumps(
        {"spawnPoints": [{"id": "side", "serverTile": [1, 1]}, spawn]}), encoding="utf-8")


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.maps = self.root / "maps"
        write_territory(self.maps, "landfall", [130, 214])
        write_territory(self.maps, "suncoil", [230, 711])

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, *extra: str):
        return baseline.parser().parse_args(["--godot", "godot.exe", "--out-dir", str(self.root / "out"),
                                             "--maps-dir", str(self.maps), *extra])

    def test_repeat_major_interleaving_and_one_warm_root_per_renderer(self):
        runs = baseline.plan(self.args())
        self.assertEqual(len(runs), 2 * 2 * 3)
        self.assertEqual([run["label"] for run in runs[:4]],
                         ["landfall-low-painted-forward_plus-r1", "landfall-low-original-forward_plus-r1",
                          "landfall-high-forward_plus-r1", "suncoil-low-painted-forward_plus-r1"])
        self.assertTrue(all(run["repeat"] == 1 for run in runs[:6]) and all(run["repeat"] == 2 for run in runs[6:]))
        first, again = runs[0], runs[6]
        self.assertNotEqual(first["report"], again["report"])
        self.assertEqual({run["userRoot"] for run in runs}, {str(self.root / "out/userdata/forward_plus")},
                         "every run shares the renderer's isolated root (geometry cache keyed by renderer)")
        compat = baseline.plan(self.args("--renderer", "gl_compatibility"))[0]
        self.assertTrue(compat["userRoot"].endswith("gl_compatibility"))

    def test_probe_environment_and_command(self):
        run = baseline.plan(self.args("--gpu-index", "1", "--renderer", "mobile", "--world-distance", "off"))[1]
        env = run["env"]
        self.assertEqual(env["ELORIA_CAMERA_PROBE_TILE"], "130,214", "the default spawn's server tile")
        self.assertEqual((env["ELORIA_CAMERA_PROBE_DISTANCE"], env["ELORIA_CAMERA_PROBE_PITCH"]),
                         ("26,90", "-60,-35,-15"))
        self.assertEqual(json.loads(env["ELORIA_CAMERA_PROBE_GRAPHICS"]),
                         {"quality": "low", "appearance": "original"})
        self.assertEqual((env["ELORIA_CAMERA_PROBE_TURNS"], env["ELORIA_CAMERA_PROBE_MINUTE"]), ("2", "600"))
        self.assertEqual(env["ELORIA_WORLD_DISTANCE"], "off")
        self.assertEqual(env["APPDATA"], run["userRoot"])
        self.assertTrue(env["ELORIA_CAMERA_PROBE_REPORT"].endswith("landfall-low-original-mobile-r1.json"))
        command = run["command"]
        self.assertLess(command.index("--log-file"), command.index("--path"), "--log-file precedes --path")
        self.assertEqual(command[command.index("--rendering-method") + 1], "mobile")
        self.assertEqual(command[command.index("--gpu-index") + 1], "1")
        self.assertEqual(command[-2:], ["--script", baseline.PROBE])
        self.assertNotIn("--headless", command)
        self.assertNotIn("ELORIA_WORLD_DISTANCE", baseline.plan(self.args())[0]["env"])
        self.assertNotIn("ELORIA_NO_GEOMETRY_CACHE", env, "prepared geometry by default")
        self.assertEqual(baseline.plan(self.args("--geometry-cache", "off"))[0]["env"]["ELORIA_NO_GEOMETRY_CACHE"], "1")

    def test_preparation_runs_once_per_renderer_root(self):
        args = self.args("--gpu-index", "1")
        prepare = baseline.preparation(args)
        self.assertEqual(prepare["command"][-2:], ["--", "--prepare-map-geometry"])
        self.assertNotIn("--script", prepare["command"])
        self.assertEqual(prepare["command"][prepare["command"].index("--gpu-index") + 1], "1")
        self.assertEqual(prepare["userRoot"], baseline.plan(args)[0]["userRoot"])
        self.assertEqual(prepare["env"]["APPDATA"], prepare["userRoot"])
        self.assertIsNone(baseline.preparation(self.args("--geometry-cache", "off")))

    def test_refusals_and_dry_run(self):
        with self.assertRaises(baseline.EvidenceError):
            baseline.plan(self.args("--configs", "ultra"))
        write_territory(self.maps, "tileless", None)
        with self.assertRaises(baseline.EvidenceError):
            baseline.plan(self.args("--maps", "tileless"))
        with mock.patch.object(sys, "stdout") as out:
            code = baseline.main(["--godot", "godot.exe", "--out-dir", str(self.root / "out"),
                                  "--maps-dir", str(self.maps), "--maps", "suncoil", "--configs", "high",
                                  "--repeats", "1", "--dry-run"])
        self.assertEqual(code, 0)
        printed = "".join(call.args[0] for call in out.write.call_args_list)
        self.assertEqual([row["label"] for row in json.loads(printed)],
                         ["prepare-forward_plus", "suncoil-high-forward_plus-r1"])
        self.assertFalse((self.root / "out").exists(), "a dry run writes nothing")
        with mock.patch.object(sys, "stderr"):
            self.assertEqual(baseline.main(["--godot", "x", "--out-dir", "o", "--repeats", "0"]), 2)


class SummaryTests(unittest.TestCase):
    def test_summary_keeps_each_pose_last_turn(self):
        def turn(index: int, gpu: float) -> dict:
            return {"turn": index, "gpu_mean_ms": gpu, "gpu_p95_ms": gpu + 1, "mean_ms": 9.0, "p95_ms": 12.0,
                    "draw_calls_mean": 60.0, "primitives_mean": 2.4e5, "objects_mean": 50.0,
                    "shadow_draw_calls_mean": 0.0, "shadow_primitives_mean": 0.0, "spikes": [{"yaw": 3}] * index,
                    "render_cpu_mean_ms": 1.0}
        report = {"poses": [{"distance": 26.0, "pitch": -60.0, "turns": [turn(0, 9.0), turn(1, 5.0)],
                             "camera_far": 1800.0, "camera_near": 1.0, "sun_shadows_enabled": False,
                             "sun_shadow_max_distance": 48.0, "world_distance": {"present": False}},
                            {"distance": 90.0, "pitch": -15.0, "turns": []}]}
        rows = baseline.summarize(report)
        self.assertEqual(len(rows), 1, "a pose without turns is left out")
        self.assertEqual((rows[0]["turn"], rows[0]["worldGpuMeanMs"], rows[0]["worldGpuP95Ms"], rows[0]["spikes"]),
                         (1, 5.0, 6.0, 1))
        self.assertEqual((rows[0]["cameraFar"], rows[0]["sunShadowMaxDistance"]), (1800.0, 48.0))

    def test_failed_launch_is_invalid_and_reports_log_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            log = folder / "run.log"
            log.write_text("SCRIPT ERROR: from an earlier run\n", encoding="utf-8")
            script = "import sys; open(sys.argv[1], 'w').write('ok' + chr(10) + 'SCRIPT ERROR: boom' + chr(10))"
            run = {"label": "x", "territory": "landfall", "tile": [1, 2], "configuration": "high",
                   "graphics": {}, "repeat": 1, "userRoot": str(folder / "user"), "report": str(folder / "none.json"),
                   "log": str(log), "env": {"LOCALAPPDATA": str(folder / "user/local")},
                   "command": [sys.executable, "-c", script, str(log)]}
            result = baseline.execute(run, 60, folder / "gpu.lock")
            self.assertFalse(result["valid"])
            self.assertEqual((result["exitCode"], result["ending"]), (0, "exited"))
            self.assertEqual(result["logErrors"], ["SCRIPT ERROR: boom"], "only this run's log is read")
            self.assertFalse((folder / "gpu.lock").exists(), "the GPU lock is released after the run")

    def test_preparation_result_reads_the_client_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            log = folder / "prepare.log"
            script = ("import json, sys; open(sys.argv[1], 'w').write('cooking\\nMAP_GEOMETRY_PREPARE ' + "
                      "json.dumps({'ok': True, 'prepared': 3}) + '\\n')")
            run = {"label": "prepare-forward_plus", "userRoot": str(folder / "user"), "log": str(log),
                   "env": {"LOCALAPPDATA": str(folder / "user/local")},
                   "command": [sys.executable, "-c", script, str(log)]}
            result = baseline.prepare(run, 60, None)
            self.assertTrue(result["ok"])
            self.assertEqual(result["report"], {"ok": True, "prepared": 3})
            run["command"] = [sys.executable, "-c", "import sys; sys.exit(1)"]
            log.unlink()
            self.assertFalse(baseline.prepare(run, 60, None)["ok"])

    def test_inherited_probe_and_world_switches_are_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            run = {"userRoot": str(folder / "user"),
                   "env": {"LOCALAPPDATA": str(folder / "user/local"), "ELORIA_CAMERA_PROBE_TURNS": "2"}}
            inherited = {"PATH": "x", "ELORIA_CAMERA_PROBE_FPS": "30", "ELORIA_CAMERA_PROBE_VSYNC": "on",
                         "ELORIA_CAMERA_PROBE_LOAD_ONLY": "1", "ELORIA_CAMERA_PROBE_POSE_SETTLE_MSEC": "0",
                         "ELORIA_CAMERA_PROBE_TURNS": "9", "ELORIA_CAMERA_SHADER_WARMUP": "0",
                         "RABBITLANDS_MEMORY_CLASS": "small", "ELORIA_WORLD_DISTANCE": "off",
                         "ELORIA_NO_GEOMETRY_CACHE": "1", "ELORIA_LOOK": "0"}
            with mock.patch.dict(baseline.os.environ, inherited, clear=True):
                env, cleared = baseline._environment(run)
        self.assertEqual(env, {"PATH": "x", "LOCALAPPDATA": str(folder / "user/local"),
                               "ELORIA_CAMERA_PROBE_TURNS": "2"}, "only the run's own settings reach the probe")
        self.assertEqual(cleared, sorted(set(inherited) - {"PATH"}))

    def test_an_unreadable_report_is_an_invalid_run_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = folder / "probe.json"
            script = "import sys; open(sys.argv[1], 'w').write('{\"map\": \"landf')"
            run = {"label": "x", "territory": "landfall", "tile": [1, 2], "configuration": "high",
                   "graphics": {}, "repeat": 1, "userRoot": str(folder / "user"), "report": str(report),
                   "log": str(folder / "missing.log"), "env": {"LOCALAPPDATA": str(folder / "user/local")},
                   "command": [sys.executable, "-c", script, str(report)]}
            result = baseline.execute(run, 60, None, grace=1.0)
        self.assertEqual((result["exitCode"], result["ending"]), (0, "exited"))
        self.assertTrue(result["error"].startswith("unreadable probe report"))
        self.assertFalse(result["valid"])

    def test_a_probe_that_hands_over_is_ended_after_the_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = folder / "probe.json"
            # Writes a failure report, then waits forever, as the probe does for its runner.
            script = ("import json, sys, time; open(sys.argv[1], 'w').write(json.dumps("
                      "{'error': 'arrival_not_ready', 'teardown': {}})); time.sleep(120)")
            run = {"label": "x", "territory": "landfall", "tile": [1, 2], "configuration": "high",
                   "graphics": {}, "repeat": 1, "userRoot": str(folder / "user"), "report": str(report),
                   "log": str(folder / "missing.log"), "env": {"LOCALAPPDATA": str(folder / "user/local")},
                   "command": [sys.executable, "-c", script, str(report)]}
            result = baseline.execute(run, 60, None, grace=1.0)
            self.assertEqual((result["exitCode"], result["ending"]), (None, "terminated_after_report"))
            self.assertLess(result["seconds"], 30)
            self.assertEqual(result["error"], "arrival_not_ready")
            self.assertFalse(result["valid"])
        self.assertTrue(baseline.abandoned_text('{"teardown": {"ready": false}}'))
        self.assertFalse(baseline.abandoned_text('{"teardown": {"ready": true}, "poses": []}'))


if __name__ == "__main__":
    unittest.main()
