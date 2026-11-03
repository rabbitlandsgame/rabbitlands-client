"""Wave-2 stage-A measurement harness: switches, memory class, underground route, G1 gate.

The same harness files run on the stage-A client and on the wave-1 baseline, so these
contracts cover both: an inherited client switch is cleared, a run sets one only through
--memory-class or --switch and records every switch, a client without memory classes is
accepted with the pin recorded as ignored, the underground round trip validates with its
dwell ranges, and the G1 evaluator applies the MOB-C6 criteria. No engine, assets or GPU.
"""
from __future__ import annotations

import copy
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
sys.path.insert(0, str(TESTS.parent / "tools"))
import crowd_benchmark_support as support
import run_crowd_presentation_benchmark as runner
import test_crowd_benchmark_harness_v2 as v2  # Its helpers; its tests are not re-collected.
import test_crowd_benchmark_runner as base_tests
import igpu_mobile_gate as gate
import world_memory_phases as phases

fixture, distribution, write_startup_ack = base_tests.fixture, base_tests.distribution, base_tests.write_startup_ack


class SwitchTests(unittest.TestCase):
    def test_every_inherited_client_switch_is_cleared(self):
        inherited = {"PATH": "p", "SECRET_TOKEN": "s", "RABBITLANDS_MEMORY_CLASS": "small", "ELORIA_FSR": "0",
                     "ELORIA_ACTOR_IMAGES": "legacy", "RABBITLANDS_CONTENT_DIGEST": "sequential",
                     "RABBITLANDS_ACTOR_GEOMETRY_ROOT": "x", "ELORIA_SHADOW_FIT": "0", "RL_HEADS": "0",
                     "RL_HEAD_PREWARM": "0", "ELORIA_WORLD_DISTANCE": "off", "ELORIA_VRAM_SELF_TEST": "a"}
        clean, cleared = support.clean_environment(inherited)
        self.assertEqual(clean, {"PATH": "p", "SECRET_TOKEN": "s"})
        self.assertNotIn("SECRET_TOKEN", cleared)
        self.assertEqual(set(cleared), set(inherited) - {"PATH", "SECRET_TOKEN"})

    def test_explicit_switches(self):
        self.assertEqual(support.parse_switches([], "auto"), {})
        self.assertEqual(support.parse_switches(["ELORIA_FSR=0", "RABBITLANDS_CONTENT_DIGEST=sequential"], "medium"),
                         {"RABBITLANDS_MEMORY_CLASS": "medium", "ELORIA_FSR": "0",
                          "RABBITLANDS_CONTENT_DIGEST": "sequential"})
        root = "RABBITLANDS_ACTOR_GEOMETRY_ROOT=C:" + chr(92) + "x/y-1.0"
        self.assertEqual(support.parse_switches([root])["RABBITLANDS_ACTOR_GEOMETRY_ROOT"], root.split("=", 1)[1])
        for bad in (["ELORIA_FSR"], ["PATH=x"], ["RABBITLANDS_MEMORY_CLASS=small"], ["ELORIA_FSR=0", "ELORIA_FSR=1"],
                    ["ELORIA_FSR=a b"], ["ELORIA_WORLD_TEXT_IDLE=0"], ["ELORIA_FSR=$(x)"]):
            with self.subTest(bad=bad), self.assertRaises(support.EvidenceError):
                support.parse_switches(bad)
        with self.assertRaises(support.EvidenceError):
            support.parse_switches([], "tiny")
        record = support.switch_record({"ELORIA_FSR": "0", "PATH": "x"})
        self.assertEqual(set(record), set(support.SWITCH_NAMES))
        self.assertEqual(record["ELORIA_FSR"], "0")
        self.assertIsNone(record["RABBITLANDS_MEMORY_CLASS"])

    def test_runner_options_reach_the_request(self):
        args = runner.parser().parse_args(["--godot", "x", "--memory-class", "medium", "--switch", "ELORIA_FSR=0"])
        args.switches = support.parse_switches(args.switch, args.memory_class)
        request = runner.request_for(args)
        self.assertEqual((request["memory_class"], request["switches"]),
                         ("medium", {"RABBITLANDS_MEMORY_CLASS": "medium", "ELORIA_FSR": "0"}))
        plain = runner.parser().parse_args(["--godot", "x"])
        self.assertEqual((runner.request_for(plain)["memory_class"], runner.request_for(plain)["switches"]),
                         ("auto", {}))
        with mock.patch.object(runner.subprocess, "Popen") as launch, mock.patch.object(sys, "stderr"):
            self.assertEqual(runner.main(["--godot", "unused", "--switch", "NOT_A_SWITCH=1"]), 1)
        launch.assert_not_called()

    def test_child_gets_only_explicit_switches_and_metadata_records_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "Godot.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                "--cells", "s3-market-160", "--mode", "windowed", "--quality", "high", "--minimap", "show",
                "--body-cap", "160", "--sample-ms", "1000", "--warmup-ms", "100", "--memory-class", "medium",
                "--switch", "ELORIA_FSR=0"])
            args.godot = exe
            args.engine_args = []
            args.switches = support.parse_switches(args.switch, args.memory_class)
            data, _ = fixture()
            data["memoryClass"] = {"available": True, "class": "medium", "source": "environment"}
            data["hardwareSwitches"] = {"available": True, "switches": {"memory_class": "medium",
                                                                         "memory_class_source": "environment"}}

            def fake_launch(command, *, env, stdout, **kwargs):
                self.assertEqual(env["RABBITLANDS_MEMORY_CLASS"], "medium")
                self.assertEqual(env["ELORIA_FSR"], "0")
                self.assertNotIn("ELORIA_ACTOR_IMAGES", env)
                self.assertNotIn("RL_HEADS", env)
                user = Path(env["APPDATA"]) / "Godot/app_userdata/Eloria"
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(user))
                write_startup_ack(env, exe, user)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))
            with mock.patch.dict(os.environ, {"ELORIA_ACTOR_IMAGES": "legacy", "RL_HEADS": "0",
                                             "RABBITLANDS_MEMORY_CLASS": "small"}), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner, "ProcessMemorySampler"), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                runner.ProcessMemorySampler.return_value.snapshot.return_value = {"status": "unavailable"}
                result = runner.run_one(args, "all", 1, root)
            self.assertTrue(result["validation"]["valid"], result["validation"])
            self.assertEqual(result["switches"]["RABBITLANDS_MEMORY_CLASS"], "medium")
            self.assertEqual(result["switches"]["ELORIA_FSR"], "0")
            self.assertIsNone(result["switches"]["ELORIA_ACTOR_IMAGES"])
            self.assertIn("ELORIA_ACTOR_IMAGES", result["clearedOverrideNames"])
            self.assertEqual(result["explicitSwitches"], {"RABBITLANDS_MEMORY_CLASS": "medium", "ELORIA_FSR": "0"})


class MemoryClassValidationTests(unittest.TestCase):
    def check(self, record, switches=None, wanted="medium"):
        data, request = fixture()
        request["memory_class"] = wanted
        data["memoryClass"] = record
        if switches is not None:
            data["hardwareSwitches"] = switches
        return support.validate_report(data, request, "")

    def test_pinned_class_must_be_the_class_run(self):
        ok = {"available": True, "class": "medium", "source": "environment"}
        self.assertTrue(self.check(ok)["valid"])
        self.assertTrue(self.check(ok, {"available": True, "switches": {"memory_class": "medium"}})["valid"])
        self.assertTrue(self.check(ok, {"available": False})["valid"])
        for bad in ({"available": True, "class": "small", "source": "probe"},
                    {"available": True, "class": "medium", "source": "probe"}):
            with self.subTest(bad=bad), self.assertRaises(support.EvidenceError):
                self.check(bad)
        with self.assertRaises(support.EvidenceError):
            self.check(ok, {"available": True, "switches": {"memory_class": "small"}})
        with self.assertRaises(support.EvidenceError):
            self.check(None)

    def test_a_client_without_memory_classes_records_the_pin_as_ignored(self):
        self.assertTrue(self.check({"available": False, "class": None})["valid"])
        self.assertTrue(self.check(None, wanted="auto")["valid"])


def underground_fixture():
    data, request = v2.traversal_fixture("traversal-southern-cold")
    request["cells"] = "traversal-underground-roundtrip"
    cell = data["cells"][0]
    cell["id"] = "traversal-underground-roundtrip"
    legs, start = [], 0
    for name in support.ROUTE_LEGS["underground"]:
        row = v2.leg(name, start, kind="interior_return" if name.endswith("exit") else "interior")
        start += 8
        if name.endswith("exit"):
            capture = row["frameRanges"]["capture"]
            row["frameRanges"]["capture"] = [capture[0], capture[0] + 1]
            row["frameRanges"]["dwell"] = [capture[0] + 1, start]
            row["dwell"] = {"milliseconds": 20000, "points": []}
        legs.append(row)
    cell["route"].update(routeId="underground", legs=legs)
    return data, request


class UndergroundRouteTests(unittest.TestCase):
    def test_selection_route_and_identity_maps(self):
        self.assertEqual(support.selected_cells("traversal-underground-roundtrip"), ["traversal-underground-roundtrip"])
        self.assertNotIn("traversal-underground-roundtrip", support.selected_cells("traversal"))
        self.assertEqual(support.route_id_for("traversal-underground-roundtrip"), "underground")
        self.assertEqual(support.route_id_for("traversal-seam-walk"), "seam")
        self.assertEqual(support.route_id_for("traversal-southern-soak-ab"), "southern")
        self.assertEqual(support.route_maps_for(["empty", "traversal-underground-roundtrip"]),
                         ["landfall", "landfall_insides"])
        self.assertEqual(support.route_maps_for(["empty"]), [])
        self.assertIn("sunmane_steppe", support.route_maps_for(["traversal-southern-cold"]))

    def test_round_trip_with_dwells_validates(self):
        data, request = underground_fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_dwell_range_and_record_must_agree_and_stay_contiguous(self):
        for mutate in (lambda legs: legs[1].pop("dwell"),
                       lambda legs: legs[1]["frameRanges"].pop("dwell"),
                       lambda legs: legs[1]["frameRanges"].update(dwell=[9, 15]),
                       lambda legs: legs[1].update(id="underground-out")):
            data, request = underground_fixture()
            mutate(data["cells"][0]["route"]["legs"])
            with self.assertRaises(support.EvidenceError):
                support.validate_report(data, request, "")


def gate_run(directory: Path, name: str, renderer: str, resolution, started: str, gpu: dict, p99: float = 20.0,
             peak: int = 2_000_000_000, warm: bool = True, arrival: float = 5000.0, valid: bool = True) -> Path:
    report = {"renderingMethod": renderer, "viewport": list(resolution), "videoAdapter": "Intel(R) Graphics",
              "graphicsQuality": "low", "map": "four_gates", "headless": False,
              "measurement": {"fpsCap": 0}, "effectiveSettings": {"renderScale": .75},
              "memoryClass": {"available": True, "class": "medium"}, "crowdPolicy": {"bodyCap": 60},
              "runtimeBuild": {"debug": True, "editor": True, "template": False, "standalone": False},
              "firstArrival": {"arrivalReportMs": arrival, "readyMs": arrival + 1500},
              "cells": [{"id": cell, "frameTime": {"p99": p99, "mean": p99 / 2},
                         "summary": {"worldRenderGpuMilliseconds": {"mean": value}}} for cell, value in gpu.items()]}
    (directory / f"{name}.json").write_text(json.dumps(report))
    metadata = {"report": str(directory / f"{name}.json"), "startedUtc": started,
                "validation": {"valid": valid, "errors": [] if valid else ["engine log contains 1 lines"]},
                "engineArgs": ["--gpu-index", "1"], "affinityObserved": 960, "settingsProfile": "performance",
                "profileSeed": {"files": 3} if warm else None,
                "identityBefore": {"sourceRevision": {"commit": "abc", "dirty": False}},
                "processMemory": {"peaks": {"workingSetBytes": {"bytes": peak}}}}
    path = directory / f"{name}.process.json"
    path.write_text(json.dumps(metadata))
    return path


def full_gate(directory: Path, mobile_gpu: float = 15.0, mobile_arrival: float = 4000.0, **mobile) -> list[Path]:
    paths, minute = [], 0
    for resolution in ((1280, 720), (1920, 1080)):
        for repeat in range(2):
            for renderer, value in (("forward_plus", 22.0), ("mobile", mobile_gpu)):
                minute += 1
                kwargs = mobile if renderer == "mobile" else {}
                paths.append(gate_run(directory, f"{renderer}-{resolution[0]}-{repeat}", renderer, resolution,
                                      f"2026-11-03T10:{minute:02d}:00Z",
                                      {"s3-market-160": value, "combat-160": value + 1, "empty": value / 2}, **kwargs))
    for renderer, arrival in (("forward_plus", 5000.0), ("mobile", mobile_arrival)):
        minute += 1
        paths.append(gate_run(directory, f"{renderer}-cold", renderer, (1280, 720), f"2026-11-03T10:{minute:02d}:00Z",
                              {"empty": 5.0}, warm=False, arrival=arrival))
    return paths


class MobileGateTests(unittest.TestCase):
    def test_go_when_every_criterion_holds(self):
        with tempfile.TemporaryDirectory() as directory:
            result = gate.evaluate(gate.load_runs([Path(directory)] if full_gate(Path(directory)) else []))
            self.assertEqual(result["verdict"], "GO", result)
            self.assertEqual(len(result["pairs"]), 4)
            self.assertEqual(result["pairs"][0]["cells"]["s3-market-160"]["worldGpuRatio"], round(15 / 22, 4))

    def test_no_go_on_gpu_p99_memory_or_cold_arrival(self):
        for kwargs, reason in (({"mobile_gpu": 19.0}, "world GPU"), ({"p99": 21.5}, "frame p99"),
                               ({"peak": 2_200_000_000}, "peak working set"),
                               ({"mobile_arrival": 6000.0}, "cold first arrival")):
            with tempfile.TemporaryDirectory() as directory, self.subTest(reason=reason):
                result = gate.evaluate(gate.load_runs(full_gate(Path(directory), **kwargs)))
                self.assertEqual(result["verdict"], "NO-GO")
                self.assertTrue(any(reason in failure for failure in result["failures"]), result["failures"])

    def test_incomplete_invalid_and_mixed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [path for path in full_gate(Path(directory)) if "1920" not in path.name]
            self.assertEqual(gate.evaluate(gate.load_runs(paths))["verdict"], "INCOMPLETE")
        with tempfile.TemporaryDirectory() as directory:
            paths = full_gate(Path(directory))
            paths.append(gate_run(Path(directory), "bad", "mobile", (1280, 720), "2026-11-03T11:00:00Z",
                                  {"empty": 1.0}, valid=False))
            self.assertEqual(gate.evaluate(gate.load_runs(paths))["verdict"], "INVALID-INPUT")
        with tempfile.TemporaryDirectory() as directory:
            paths = full_gate(Path(directory))
            metadata = json.loads(paths[0].read_text())
            metadata["engineArgs"] = ["--gpu-index", "0"]
            paths[0].write_text(json.dumps(metadata))
            with self.assertRaises(gate.GateError):
                gate.evaluate(gate.load_runs(paths))
        self.assertEqual(gate.main([str(Path(tempfile.gettempdir()) / "no-such-g1-input")]), 2)


class MemoryPhaseTests(unittest.TestCase):
    def test_points_take_the_next_sample_and_their_window(self):
        samples = [{"unixTime": 100.0 + i, "privateBytes": 1000 + i, "workingSetBytes": 500 + i} for i in range(10)]
        rows = phases.match_samples([{"phase": "a", "unixTime": 101.5}, {"phase": "b", "unixTime": 105.0},
                                     {"phase": "late", "unixTime": 200.0}, {"phase": "none"}], samples)
        self.assertEqual(rows[0]["at"], {"lagSeconds": 0.5, "privateBytes": 1002, "workingSetBytes": 502})
        self.assertEqual(rows[0]["window"]["privateBytes"], {"min": 1002, "max": 1004})
        self.assertEqual(rows[1]["window"]["privateBytes"], {"min": 1005, "max": 1009})
        self.assertIsNone(rows[2]["at"])
        self.assertIsNone(rows[3]["at"])

    def test_park_phase_lines_and_crowd_points(self):
        text = "noise\nLANDFALL_TOWN_PARK phase " + json.dumps(
            {"phase": "exterior_parked", "unix_time": 5.0, "static_bytes": 7, "world_park_kept_bytes": 9}) + "\n"
        self.assertEqual(phases.park_phases(text)[0]["phase"], "exterior_parked")
        report = {"cells": [{"id": "traversal-underground-roundtrip", "route": {"legs": [
            {"id": "underground-exit", "memory": {"arrival": {"label": "arrival", "unixTime": 3.0, "map": "landfall",
                                                              "actorScenes": {"bytes": 5}}},
             "dwell": {"points": [{"label": "dwell", "unixTime": 4.0, "worldPark": {"keptBytes": 2}}]}}]}}]}
        points = phases.crowd_points(report)
        self.assertEqual([p["phase"] for p in points], ["underground-exit:arrival", "underground-exit:dwell"])
        self.assertEqual((points[0]["actorSceneBytes"], points[1]["worldParkKeptBytes"]), (5, 2))

    def test_park_command(self):
        args = phases.parser().parse_args(["park", "--godot", "g.exe", "--out-dir", "o", "--memory-class", "small",
                                           "--engine-arg=--gpu-index=1", "--dwell-ms", "5000", "--park-held"])
        args.engine_args = support.parse_engine_args(args.engine_arg, args.renderer, args.mode)
        args.project = Path("p")
        command = phases.park_command(args, Path("r.json"), Path("l.log"))
        self.assertEqual(command[:3], ["g.exe", "--gpu-index", "1"])
        self.assertIn("--rendering-method", command)
        tail = command[command.index("--"):]
        self.assertEqual(tail, ["--", "--report", "r.json", "--interior", "landfall_insides", "--park-held",
                                "--dwell-ms", "5000"])


if __name__ == "__main__":
    unittest.main()
