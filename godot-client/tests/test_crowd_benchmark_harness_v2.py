"""Wave 2 AW-00 harness contracts: route v2 legs, the seam cell, worker-pool overlays.

No engine, assets, GPU or network; overlay creation is exercised with a stand-in
tool, never the real junction-making one.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

INTEGRATION = Path(__file__).resolve().parent / "integration"
sys.path.insert(0, str(INTEGRATION))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import crowd_benchmark_support as support
import run_crowd_presentation_benchmark as runner
import test_crowd_benchmark_runner as base_tests  # Its helpers; its tests are not re-collected.

distribution, fixture = base_tests.distribution, base_tests.fixture
write_project, write_startup_ack = base_tests.write_project, base_tests.write_startup_ack


def leg(name: str, start: int, settle: float = 500.0, visible: float | None = 300.0, kind: str = "border") -> dict:
    """A route-v2 leg whose frames occupy [start, start + 8) of the route series."""
    return {"id": name, "kind": kind, "success": True, "milliseconds": settle, "settleMs": settle,
            "visibleMs": visible, "visibleBasis": "arrival_reported" if visible is not None else "none",
            "arrivalReports": 1 if visible is not None else 0,
            "curtain": {"shown": visible is not None, "shownMs": 20.0 if visible is not None else None,
                        "hiddenMs": 250.0 if visible is not None else None, "probeFrames": 4},
            "readiness": {"ready": True}, "expectContinuous": kind == "seam", "continuousHandoff": kind == "seam",
            "frameRanges": {"start": [start, start + 2], "walk": [start + 2, start + 4],
                            "transition": [start + 4, start + 7], "capture": [start + 7, start + 8]},
            "sampledFrames": 4}


def traversal_fixture(name: str = "traversal-southern-cold"):
    data, request = fixture()
    request["cells"] = name
    cell = data["cells"][0]
    cell.update(id=name, count=1, status="complete", plan={"active": 1, "moving": 1, "fighting": 0})
    for point in cell["census"].values():
        point.update(nodes=1, builtBodies=1)
    cell["wallFrameSeries"] = [20.] * 60
    cell["wallFrameTime"] = distribution(cell["wallFrameSeries"])
    seam = name.startswith("traversal-seam")
    ids = support.ROUTE_LEGS["seam" if seam else "southern"]
    cell["route"] = {"kind": "synthetic_client_streaming", "serverNavigationCertified": False,
                     "routeId": "seam" if seam else "southern", "routeVersion": 2, "legSchema": 2,
                     "legs": [leg(identity, index * 8, visible=None if seam else 300.0,
                                  kind="seam" if seam else "border") for index, identity in enumerate(ids)]}
    cell.pop("summary")
    return data, request


class RouteSelectionTests(unittest.TestCase):
    def test_traversal_profile_and_seam_cell_are_selectable(self):
        self.assertEqual(support.selected_cells("traversal"),
                         ["traversal-southern-cold", "traversal-southern-warm", "traversal-seam-walk"])
        self.assertEqual(support.selected_cells("traversal-seam-walk"), ["traversal-seam-walk"])
        self.assertNotIn("traversal-seam-walk", support.selected_cells("all"))  # Historical membership.
        self.assertEqual(support.selected_cells("traversal-seam-walk,traversal-southern-cold"),
                         ["traversal-seam-walk", "traversal-southern-cold"])
        self.assertEqual(len(support.selected_cells("phase1")), 7)
        self.assertEqual(support.route_legs_for("traversal-seam-walk"), ["walking-seam"])
        self.assertEqual(support.route_legs_for("traversal-southern-soak-aa"), support.ROUTE_LEGS["southern"])
        self.assertEqual(len(support.ROUTE_LEGS["southern"]), 6)


class RouteValidationTests(unittest.TestCase):
    def test_route_v2_southern_and_seam_cells_are_valid(self):
        for name in ("traversal-southern-cold", "traversal-seam-walk"):
            data, request = traversal_fixture(name)
            with self.subTest(name=name):
                self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_seam_crossing_that_was_not_continuous_is_still_valid_evidence(self):
        data, request = traversal_fixture("traversal-seam-walk")
        only = data["cells"][0]["route"]["legs"][0]
        only.update(continuousHandoff=False, visibleMs=450.0, visibleBasis="arrival_reported", arrivalReports=1,
                    curtain={"shown": True, "shownMs": 30.0, "hiddenMs": 420.0, "probeFrames": 9})
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_route_v2_rejects_inconsistent_legs(self):
        def changed(edit):
            data, request = traversal_fixture()
            edit(data["cells"][0]["route"])
            return data, request

        cases = {
            "wrong version": lambda route: route.update(routeVersion=1),
            "wrong route id": lambda route: route.update(routeId="seam"),
            "settle differs": lambda route: route["legs"][0].update(settleMs=400.0),
            "visible after settle": lambda route: route["legs"][0].update(visibleMs=900.0),
            "visible without report": lambda route: route["legs"][0].update(arrivalReports=0),
            "report without visible": lambda route: route["legs"][1].update(visibleMs=None),
            "curtain time without curtain": lambda route: route["legs"][0]["curtain"].update(shown=False),
            "gap between phases": lambda route: route["legs"][0]["frameRanges"].update(walk=[3, 4]),
            "gap between legs": lambda route: route["legs"][1]["frameRanges"].update(
                start=[9, 10], walk=[10, 12]),
            "beyond the series": lambda route: route["legs"][5]["frameRanges"].update(capture=[47, 61]),
            "sampled frames differ": lambda route: route["legs"][2].update(sampledFrames=3),
            "handoff missing": lambda route: route["legs"][3].pop("continuousHandoff"),
            "seam legs on the southern cell": lambda route: route.update(legs=[leg("walking-seam", 0)]),
        }
        for label, edit in cases.items():
            data, request = changed(edit)
            with self.subTest(label), self.assertRaises(support.EvidenceError):
                support.validate_report(data, request, "")

    def test_visible_time_tolerates_the_whole_millisecond_settle_clock(self):
        # settleMs is two truncated millisecond readings apart; visibleMs is microsecond based.
        data, request = traversal_fixture()
        data["cells"][0]["route"]["legs"][0].update(visibleMs=500.9)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        data["cells"][0]["route"]["legs"][0].update(visibleMs=501.0)
        with self.assertRaisesRegex(support.EvidenceError, "exceeds the settle time"):
            support.validate_report(data, request, "")

    def test_version_one_reports_keep_their_original_contract(self):
        data, request = traversal_fixture()
        route = data["cells"][0]["route"]
        for key in ("routeVersion", "legSchema", "routeId"):
            route.pop(key)
        for item in route["legs"]:
            for key in ("settleMs", "visibleMs", "frameRanges", "curtain", "continuousHandoff"):
                item.pop(key, None)
        self.assertTrue(support.validate_report(data, request, "")["valid"])


class WorkerPoolTests(unittest.TestCase):
    def test_thread_resolution(self):
        self.assertEqual(support.resolve_worker_threads("0", ""), 0)
        self.assertEqual(support.resolve_worker_threads("4", ""), 4)
        self.assertEqual(support.resolve_worker_threads("8", "3C0"), 8)
        self.assertEqual(support.resolve_worker_threads("affinity", "3C0"), 4)
        self.assertEqual(support.resolve_worker_threads("affinity", "FF"), 8)
        for value, affinity in (("affinity", ""), ("affinity", "3F"), ("6", ""), ("many", "")):
            with self.subTest(value=value, affinity=affinity), self.assertRaises(support.EvidenceError):
                support.resolve_worker_threads(value, affinity)

    def test_requested_pool_must_be_the_engines(self):
        data, request = fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])  # Not requested: unchecked.
        request["worker_threads"] = 4
        with self.assertRaisesRegex(support.EvidenceError, "workerPool: expected object"):
            support.validate_report(data, request, "")
        data["workerPool"] = {"maxThreadsSetting": -1, "processorCount": 24}
        with self.assertRaisesRegex(support.EvidenceError, "worker pool"):
            support.validate_report(data, request, "")
        data["workerPool"]["maxThreadsSetting"] = 4
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def stand_in_tool(self, root: Path, source: str = "SOURCE = ROOT / 'godot-client'", override: str | None = None):
        (root / "godot-client" / "tools").mkdir(parents=True)
        written = override if override is not None else "[threading]\\nworker_pool/max_threads={threads}\\n"
        (root / "godot-client" / "tools" / "continent_stream_benchmark_project.py").write_text(
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parents[2]\n"
            f"{source}\n"
            "def prepare(folder, threads):\n"
            "    project = folder / 'godot-client'\n"
            "    project.mkdir(parents=True, exist_ok=True)\n"
            "    (project / 'project.godot').write_text('[application]\\n')\n"
            f"    (project / 'override.cfg').write_text(\"{written}\".format(threads=threads))\n"
            "    return {'project': str(project), 'worker_threads': threads}\n")
        return root / "godot-client"

    def test_overlay_comes_from_the_projects_own_tool_in_its_local_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            project = self.stand_in_tool(Path(directory))
            manifest = support.prepare_worker_overlay(project, 4)
            overlay = Path(manifest["project"])
            self.assertEqual(overlay, Path(directory) / ".local/crowd-benchmark-overlay/threads-4/godot-client")
            self.assertIn("worker_pool/max_threads=4", (overlay / "override.cfg").read_text())

    def test_overlay_rejects_missing_foreign_or_unset_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(support.EvidenceError, "missing"):
                support.prepare_worker_overlay(Path(directory) / "godot-client", 4)
        with tempfile.TemporaryDirectory() as directory:
            project = self.stand_in_tool(Path(directory), source="SOURCE = Path('elsewhere')")
            with self.assertRaisesRegex(support.EvidenceError, "another checkout"):
                support.prepare_worker_overlay(project, 4)
        with tempfile.TemporaryDirectory() as directory:
            project = self.stand_in_tool(Path(directory), override="[threading]\\n")
            with self.assertRaisesRegex(support.EvidenceError, "does not set"):
                support.prepare_worker_overlay(project, 8)

    def test_runner_launches_the_overlay_but_identifies_the_source_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            exe = root / "Godot.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                "--cells", "s3-market-160", "--mode", "windowed", "--minimap", "show",
                "--sample-ms", "1000", "--warmup-ms", "100", "--fps-cap", "60", "--body-cap", "160",
                "--quality", "high", "--worker-threads", "affinity", "--affinity", "3C0"])
            args.godot = exe
            args.worker_threads_count = support.resolve_worker_threads(args.worker_threads, args.affinity)
            overlay = root / ".local-overlay" / "godot-client"
            data, _request = fixture()
            data["workerPool"] = {"maxThreadsSetting": 4, "processorCount": 24}
            launches = []

            def fake_launch(command, *, env, stdout, cwd, **_kwargs):
                launches.append((command, cwd))
                user_dir = Path(env["APPDATA"]) / "Godot/app_userdata/Eloria"
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(user_dir))
                write_startup_ack(env, exe, user_dir)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))

            manifest = {"project": str(overlay), "worker_threads": 4, "overlay_override_sha256": "x"}
            with mock.patch.object(runner, "prepare_worker_overlay", return_value=manifest) as prepare, \
                    mock.patch.object(runner, "set_affinity", return_value=0x3C0), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}) as identity, \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                result = runner.run_one(args, "all", 1, root)
            prepare.assert_called_once_with(root, 4)
            command, cwd = launches[0]
            self.assertEqual(command[command.index("--path") + 1], str(overlay))
            self.assertEqual(cwd, overlay)
            self.assertEqual(identity.call_args.args[0].project_path, root)
            self.assertTrue(result["validation"]["valid"], result["validation"])
            self.assertEqual(result["workerPool"], {"requestedThreads": 4, "overlay": manifest})
            recorded = support.read_json(next(root.glob("*.process.json")))
            self.assertEqual(recorded["workerPool"]["overlay"]["project"], str(overlay))

    def test_runner_rejects_overlays_for_exports_and_unmatched_masks(self):
        base = ["--godot", __file__, "--cells", "s3-market-160", "--out-dir", tempfile.gettempdir()]
        for extra in (["--worker-threads", "4", "--executable-mode", "exported", "--main-pack", __file__],
                      ["--worker-threads", "affinity"], ["--worker-threads", "affinity", "--affinity", "3F"]):
            with self.subTest(extra=extra), mock.patch.object(runner, "run_one") as run_one:
                self.assertEqual(runner.main(base + extra), 1)
                run_one.assert_not_called()

    def test_default_runs_have_no_overlay(self):
        args = runner.parser().parse_args(["--godot", "Godot.exe", "--project-path", "project"])
        self.assertEqual(args.worker_threads, "0")
        command = runner.command_for(args, Path("engine.log"))
        self.assertEqual(command[command.index("--path") + 1], "project")
        self.assertEqual(runner.request_for(args)["worker_threads"], 0)


if __name__ == "__main__":
    unittest.main()
