"""Wave 2 OV-0: overhead/text-pass diagnostics in the crowd harness, and the decision-8 gate.

No engine, assets or GPU: the runner's diagnostic parsing, the report validator's
text-pass/overhead checks, the inherited-environment cleaning and tools/overhead_text_gate.py.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS / "integration"))
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "tools"))
import crowd_benchmark_support as support  # noqa: E402
import overhead_text_gate as gate  # noqa: E402
import run_crowd_presentation_benchmark as runner  # noqa: E402
import test_crowd_benchmark_runner as base_tests  # noqa: E402  Its helpers; its tests are not re-collected.


def text_pass(mode: str = "auto", drawn: int = 60, frames: int = 60, **extra) -> dict:
    state = {"present": True, "mode": mode, "overlayVisible": mode != "off", "drawingLastFrame": drawn > 0,
             "idleVariable": "", "idleWatching": mode != "always", "textNodesTracked": 800,
             "passViewportSize": [2, 2] if mode == "off" else [1280, 720], "worldViewportSize": [1280, 720],
             "drawnFrames": drawn, "sampledFrames": frames,
             "cellStart": {"ok": True, "mode": "auto", "overlayVisible": True, "passViewportSize": [1280, 720]}}
    state.update(extra)
    return state


def census(shown: int, actors: int = 160) -> dict:
    return {"actors": actors, "nameplateEnabled": shown, "overheadShown": shown, "healthShown": 0, "crowded": 0}


def report_fixture(diagnostics: str = "", mode: str = "windowed"):
    data, request = base_tests.fixture()
    request.update(diagnostics=diagnostics, mode=mode)
    data["diagnostics"] = diagnostics
    cell = data["cells"][0]
    names = support.parse_diagnostics(diagnostics)
    pass_mode = support.text_pass_mode(names)
    cell["textPass"] = text_pass(pass_mode, drawn=0 if pass_mode == "off" else 60)
    shown = 0 if "no_overhead" in names else 120
    cell["overhead"] = {"beforeDiagnostics": census(120), "sampleStart": census(shown), "afterSample": census(shown)}
    return data, request


class DiagnosticParsingTests(unittest.TestCase):
    def test_known_names_modes_and_refusals(self):
        self.assertEqual(support.parse_diagnostics(""), [])
        self.assertEqual(support.parse_diagnostics("no_overhead,,no_text_pass"), ["no_overhead", "no_text_pass"])
        self.assertEqual(support.text_pass_mode(["no_text_pass"]), "off")
        self.assertEqual(support.text_pass_mode(["text_pass_always", "no_ground"]), "always")
        self.assertEqual(support.text_pass_mode(["no_overhead"]), "auto")
        for text in ("no_text", " no_overhead", "no_overhead,no_overhead", "no_text_pass,text_pass_always"):
            with self.subTest(text=text), self.assertRaises(support.EvidenceError):
                support.parse_diagnostics(text)

    def test_runner_refuses_unknown_diagnostics_before_launch(self):
        with mock.patch.object(runner, "executable_path") as resolve, mock.patch.object(sys, "stderr"):
            self.assertEqual(runner.main(["--godot", "unused", "--diagnostics", "no_text"]), 1)
        resolve.assert_not_called()
        args = runner.parser().parse_args(["--godot", "unused", "--diagnostics", "no_text_pass"])
        self.assertEqual(runner.request_for(args)["diagnostics"], "no_text_pass")

    def test_inherited_idle_switch_is_cleared(self):
        clean, names = support.clean_environment({"PATH": "x", "ELORIA_WORLD_TEXT_IDLE": "0"})
        self.assertEqual(clean, {"PATH": "x"})
        self.assertEqual(names, ["ELORIA_WORLD_TEXT_IDLE"])


class ValidationTests(unittest.TestCase):
    def test_full_and_pre_ov0_reports_pass(self):
        data, request = report_fixture("")
        support.validate_report(data, request, "")
        old = copy.deepcopy(data)
        del old["cells"][0]["textPass"], old["cells"][0]["overhead"]
        support.validate_report(old, request, "")

    def test_no_text_pass_must_stop_and_release_the_pass(self):
        data, request = report_fixture("no_text_pass")
        support.validate_report(data, request, "")
        for change in ({"drawnFrames": 3}, {"overlayVisible": True}, {"passViewportSize": [1280, 720]},
                       {"mode": "auto"}, {"sampledFrames": 59}, {"cellStart": None},
                       {"cellStart": {"ok": True, "mode": "off", "overlayVisible": False, "passViewportSize": [2, 2]}},
                       {"cellStart": {"ok": True, "mode": "auto", "overlayVisible": True, "passViewportSize": [2, 2]}}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["textPass"].update(change)
            with self.subTest(change=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        missing = copy.deepcopy(data)
        del missing["cells"][0]["textPass"]
        with self.assertRaises(support.EvidenceError):
            support.validate_report(missing, request, "")

    def test_text_pass_always_renders_every_rendered_frame(self):
        data, request = report_fixture("text_pass_always")
        support.validate_report(data, request, "")
        broken = copy.deepcopy(data)
        broken["cells"][0]["textPass"]["drawnFrames"] = 59
        with self.assertRaises(support.EvidenceError):
            support.validate_report(broken, request, "")
        watching = copy.deepcopy(data)
        watching["cells"][0]["textPass"]["idleWatching"] = True
        with self.assertRaises(support.EvidenceError):
            support.validate_report(watching, request, "")
        # Headless draws nothing; only the mode and the stopped idle watch are required there.
        support.validate_overhead_diagnostics(broken, dict(request, mode="headless"))

    def test_every_cell_starts_from_the_shipping_pass(self):
        # A stopped pass left by the previous cell would shrink this cell's withCrowd video memory,
        # and the in-process VRAM delta would read about 0 instead of the pass's target.
        data, request = report_fixture("")
        leaked = copy.deepcopy(data)
        leaked["cells"][0]["textPass"]["cellStart"]["passViewportSize"] = [2, 2]
        with self.assertRaises(support.EvidenceError):
            support.validate_report(leaked, request, "")
        older = copy.deepcopy(data)
        del older["cells"][0]["textPass"]["cellStart"]
        support.validate_report(older, request, "")  # A full run's record without the field stays valid.
        with self.assertRaises(support.EvidenceError):
            support.validate_overhead_diagnostics(older, request, require_records=True)

    def test_no_overhead_must_leave_no_banner_shown(self):
        data, request = report_fixture("no_overhead")
        support.validate_report(data, request, "")
        for boundary in ("sampleStart", "afterSample"):
            broken = copy.deepcopy(data)
            broken["cells"][0]["overhead"][boundary]["overheadShown"] = 2
            with self.subTest(boundary=boundary), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")


def gate_report(diagnostics: str, frame: float, gpu: float, text_gpu: float | None, video_mib: float,
                cells=("empty", "s3-market-160", "combat-160"), adapter: str = "GPU", empty_offset: float = 0.0,
                spawn_mib: float = 899.0) -> dict:
    def dist(value: float) -> dict:
        return {"count": 60, "mean": value, "p5": value - 1, "p50": value, "p95": value + 2, "p99": value + 3,
                "max": value + 4}
    out = []
    for name in cells:
        offset = empty_offset if name == "empty" else 0.0
        summary = {"frameMilliseconds": dist(frame + offset), "renderGpuSumMilliseconds": dist(gpu + offset),
                   "worldRenderGpuMilliseconds": dist(gpu - 2), "rootRenderGpuMilliseconds": dist(1.0),
                   "totalDrawCalls": dist(900.0), "textPassDrawn": dist(1.0)}
        if text_gpu is not None:
            summary["textPassRenderGpuMilliseconds"] = dist(text_gpu)
        names = support.parse_diagnostics(diagnostics)
        pass_mode = support.text_pass_mode(names)
        shown = 0 if "no_overhead" in names else 30
        out.append({"id": name, "summary": summary, "frames": 60,
                    "textPass": text_pass(pass_mode, drawn=0 if pass_mode == "off" else 60),
                    "overhead": {"beforeDiagnostics": census(30), "sampleStart": census(shown),
                                 "afterSample": census(shown)},
                    "memory": {"withCrowd": {"videoBytes": int(spawn_mib * 1048576)},
                               "afterSample": {"videoBytes": int(video_mib * 1048576)}}})
    return {"benchmark": "crowd_presentation", "diagnostics": diagnostics, "failures": [],
            "renderingMethod": "gl_compatibility", "graphicsQuality": "low", "viewport": [1280, 720],
            "videoAdapter": adapter, "headless": False, "bodyCap": "160", "measurement": {"fpsCap": 0},
            "map": "four_gates", "effectiveSettings": {"quality": "low", "renderScale": 1.0, "frameCap": 0},
            "runtimeBuild": {"debug": True, "editor": True, "release": False, "template": False,
                             "standalone": False, "executablePath": "C:/godot.exe"},
            "cells": out}


class GateTests(unittest.TestCase):
    def reports(self, recover: float = 1.4):
        return [gate_report("", 20.0, 15.0, 1.1, 900.0),
                gate_report("", 20.2, 15.2, 1.3, 900.0),
                gate_report("no_overhead", 20.0 - recover, 15.0 - recover, None, 880.0),
                gate_report("no_text_pass", 19.0, 13.9, None, 878.0, spawn_mib=890.0),
                gate_report("text_pass_always", 20.1, 15.1, 1.2, 900.0, empty_offset=0.9)]

    def test_deltas_idle_saving_and_go(self):
        table, shared = gate.collect(self.reports())
        result = gate.gate(table)
        market = result["cells"]["s3-market-160"]
        self.assertEqual(result["repeats"]["full"]["s3-market-160"], 2)
        self.assertAlmostEqual(market["recoverable"]["frameMilliseconds"]["mean"], 1.5)
        self.assertAlmostEqual(market["recoverable"]["frameMilliseconds"]["p95"], 1.5)
        self.assertAlmostEqual(market["textPass"]["renderGpuSumMilliseconds"]["mean"], 1.2)
        self.assertEqual(market["textPass"]["videoMiBAfterSample"], 22.0)
        # In-process: full grows 1 MiB after spawning, no_text_pass shrinks 12 MiB: the pass held 13 MiB.
        self.assertEqual(market["textPass"]["videoMiBInProcess"], 13.0)
        self.assertAlmostEqual(result["cells"]["empty"]["idleSaving"]["frameMilliseconds"]["mean"], 0.9)
        self.assertEqual(result["verdict"], "GO")
        self.assertTrue(any(reason.startswith("s3-market-160 frameMilliseconds") for reason in result["reasons"]))
        text = gate.markdown(result, shared)
        self.assertIn("| s3-market-160 | full - no_overhead | 1.5 / 1.5 |", text)
        self.assertIn("| 22.0 | 13.0 |", text)

    def test_no_go_and_incomplete(self):
        table, _ = gate.collect(self.reports(recover=0.3))
        self.assertEqual(gate.gate(table)["verdict"], "NO-GO")
        only_empty = [gate_report(d, 10.0, 9.0, None, 1.0, cells=("empty",))
                      for d in ("", "no_overhead", "no_text_pass")]
        table, _ = gate.collect(only_empty)
        result = gate.gate(table)
        self.assertEqual((result["verdict"], result["missingCrowdCells"]), ("INCOMPLETE", list(gate.CROWD_CELLS)))
        table, _ = gate.collect(self.reports())
        self.assertEqual(gate.gate(table, headless=True)["verdict"], "HEADLESS", "headless never draws the pass")

    def test_refuses_mixed_or_incomplete_evidence(self):
        reports = self.reports()
        reports[3]["videoAdapter"] = "other GPU"
        with self.assertRaises(support.EvidenceError):
            gate.collect(reports)
        with self.assertRaises(support.EvidenceError):
            gate.collect(self.reports()[:3])  # no no_text_pass
        with self.assertRaises(support.EvidenceError):
            gate.collect([gate_report("no_overhead,no_animation", 1, 1, None, 1)])
        failed = self.reports()
        failed[0]["failures"] = ["x"]
        with self.assertRaises(support.EvidenceError):
            gate.collect(failed)

    def test_refuses_other_settings_map_or_build(self):
        # The Performance preset and plain Low share graphicsQuality "low"; only effectiveSettings tell them apart.
        for key, value in (("effectiveSettings", {"quality": "low", "renderScale": 0.75, "frameCap": 30}),
                           ("map", "landfall"),
                           ("runtimeBuild", {"debug": False, "editor": False, "release": True, "template": True,
                                             "standalone": True})):
            reports = self.reports()
            reports[2][key] = value
            with self.subTest(key=key), self.assertRaises(support.EvidenceError):
                gate.collect(reports)
        reports = self.reports()
        reports[1]["runtimeBuild"]["executablePath"] = "D:/elsewhere/godot.exe"
        gate.collect(reports)  # The same build kind from another path is the same configuration.

    def test_refuses_reports_without_ov0_records_or_with_a_diagnostic_not_in_effect(self):
        # Before OV-0 no_overhead reached only re-presented actors: 120 of 160 market banners stayed up.
        reports = self.reports()
        for cell in reports[2]["cells"]:
            del cell["textPass"], cell["overhead"]
        with self.assertRaisesRegex(support.EvidenceError, "textPass"):
            gate.collect(reports)
        reports = self.reports()
        reports[2]["cells"][1]["overhead"]["afterSample"]["overheadShown"] = 25
        with self.assertRaisesRegex(support.EvidenceError, "no_overhead left actor banners"):
            gate.collect(reports)
        reports = self.reports()
        del reports[0]["cells"][0]["textPass"]  # A full run is held to the records too.
        with self.assertRaises(support.EvidenceError):
            gate.collect(reports)
        reports = self.reports()
        reports[3]["cells"][2]["textPass"]["drawnFrames"] = 4
        with self.assertRaisesRegex(support.EvidenceError, "no_text_pass left"):
            gate.collect(reports)

    def test_command_line_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = []
            for index, report in enumerate(self.reports()):
                path = folder / f"r{index}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                paths.append(str(path))
            with mock.patch.object(sys, "stdout"):
                code = gate.main(paths + ["--json", str(folder / "gate.json"), "--markdown", str(folder / "gate.md")])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads((folder / "gate.json").read_text(encoding="utf-8"))["verdict"], "GO")
            self.assertIn("Overhead-text gate (OV-0): GO", (folder / "gate.md").read_text(encoding="utf-8"))
            with mock.patch.object(sys, "stderr"), mock.patch.object(sys, "stdout"):
                self.assertEqual(gate.main(paths[:2]), 2)


if __name__ == "__main__":
    unittest.main()
