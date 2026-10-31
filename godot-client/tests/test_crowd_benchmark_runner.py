"""Focused evidence/locking tests; no engine, assets, GPU or network required."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

INTEGRATION = Path(__file__).resolve().parent / "integration"
sys.path.insert(0, str(INTEGRATION))
import crowd_benchmark_support as support
import run_crowd_presentation_benchmark as runner


def distribution(values):
    ordered = sorted(values)
    result = {"count": len(values), "mean": round(sum(values) / len(values), 3), "max": max(values)}
    for key, fraction in (("p5", .05), ("p50", .5), ("p95", .95), ("p99", .99)):
        result[key] = ordered[math.ceil(fraction * len(values)) - 1]
    return result


def runtime():
    stats = {"buildAttempts": 0, "buildSuccesses": 0, "buildFallbacks": 0}
    return {"effectiveSettings": {"quality": "high", "bodyCap": 160, "frameCap": 60,
                                  "renderer": "forward_plus", "rootSize": [1280, 720],
                                  "worldViewportSize": [1280, 720], "renderScale": 1.0,
                                  "textureQuality": "full", "textureSkip": 0,
                                  "minimap": True, "appearance": "painted_ground"},
            "activeBackends": {"nativeReducer": False, "preparedNodePolicy": "retain",
                               "preparedContent": {"mode": "raw", "active": False, "hits": 0,
                                   "misses": {"disabled": 1}, "consumed_entries": [], "timings": {},
                                   "strong_resource_entries": 0, "verification_reuse": False,
                                   "estimate_kind": "declared_content_not_allocation"},
                               "presentation": {"requested": "0", "nativeCapeInstances": 0,
                                                "nativeCapeCalls": 0, "capeFallbackCalls": 0,
                                                "flight": stats.copy(), "impact": stats.copy()}}}


def fixture():
    series = [round(i / 10, 3) for i in range(1, 61)]
    census = {"nodes": 160, "builtBodies": 160, "deferred": 0}
    summary = {key: distribution(series) for key in ("frameMilliseconds", "processPhaseMilliseconds",
                                                    "flushPhaseMilliseconds", "drawPhaseMilliseconds",
                                                    "worldRenderCpuMilliseconds", "worldRenderGpuMilliseconds", "drawCalls")}
    summary.update(actorRecords=distribution([160.] * 60), actorNodes=distribution([160.] * 60),
                   tickFrameMilliseconds=distribution(series[:20]), packetsPerFrame=distribution([1.] * 60))
    cell = {"id": "s3-market-160", "count": 160, "frames": 60, "sampleMilliseconds": 1000,
            "readiness": {"ready": True}, "frameSeries": series, "frameTime": distribution(series),
            "census": {"afterSpawn": census.copy(), "afterSample": census.copy()},
            "plan": {"active": 53, "moving": 27, "fighting": 26}, "packetsPerSecond": 60,
            "effectiveRuntime": runtime(),
            "summary": summary}
    data = {"schemaVersion": 1, "benchmark": "crowd_presentation", "failureCount": 0, "failures": [],
            "headless": False, "renderingMethod": "forward_plus", "graphicsQuality": "high",
            "viewport": [1280, 720], "map": "four_gates", "minimapVisible": True,
            "worldReadiness": {"ready": True}, "presenceDots": 0, "serverTime": False,
            "crowdPolicy": {"bodyCap": 160, "fullRateBodies": 16, "halfRateBodies": 16, "clothBodies": 8},
            "measurement": {"fpsCap": 60, "sampleMilliseconds": 1000, "warmupMilliseconds": 100,
                            "driver": "live", "requestedWindowMode": "windowed", "windowPlatform": "Windows",
                            "requestedDisplayWindowMode": 0, "actualWindowMode": 0}, "cells": [cell], **runtime(),
            "runtimeBuild": {"template": False, "editor": True}}
    request = {"mode": "windowed", "renderer": "forward_plus", "quality": "high",
               "resolution": (1280, 720), "map": "four_gates", "minimap": "show", "fps_cap": 60,
               "sample_ms": 1000, "warmup_ms": 100, "driver": "live", "body_cap": 160,
               "cells": "s3-market-160", "replay": False, "executable_mode": "project", "window_mode": "windowed"}
    return data, request


def performance_fixture():
    data, request = fixture()
    request.update(settings_profile="performance", quality="low", fps_cap=30, body_cap=60,
                   settings_seed_user_dir=str(INTEGRATION / "performance-userdata"))
    data.update(graphicsQuality="low")
    data["measurement"]["fpsCap"] = 30
    data["crowdPolicy"].update(bodyCap=60, fullRateBodies=8, halfRateBodies=8, clothBodies=0)
    data["runtimeBuild"]["userDataDir"] = request["settings_seed_user_dir"]
    for observed in (data, data["cells"][0]["effectiveRuntime"]):
        observed["effectiveSettings"].update(quality="low", frameCap=30, bodyCap=60, renderScale=.75,
                                              textureQuality="half", textureSkip=1, appearance="painted_ground", clothBudget=0,
                                              shadowsPreference=False, sunShadowsEnabled=False,
                                              particlesEnabled=True, decorativeGrass=False, nameDistanceMetres=20.0)
    for census in data["cells"][0]["census"].values():
        census.update(builtBodies=60, deferred=100)
    return data, request


def mounted_rust_fixture(quality="high"):
    data, request = fixture()
    request.update(client_runtime="rust", cells="mixed-mounted-160", quality=quality)
    data["graphicsQuality"] = quality
    body_budget = {"high": 16, "medium": 12, "low": 8}[quality]
    data["crowdPolicy"].update(fullRateBodies=body_budget, halfRateBodies=body_budget)
    cell = data["cells"][0]
    cell["id"] = "mixed-mounted-160"
    cell["mountProfiles"] = {"crystalback_tortoise": 14, "giant_rat": 14, "golden_plains_horse": 13,
                             "jadefeather_raptor": 13, "moor_pony": 13, "rabbit": 13}
    for observed in (data, cell["effectiveRuntime"]):
        observed["effectiveSettings"]["quality"] = quality
        observed["activeBackends"]["clientRuntime"] = {
            "requested": "rust", "mode": "rust", "presentation_backend": "mixed", "mismatches": 0,
            "native_available": True, "native": {"poses_applied": 200, "upper_applied": 200,
                "rein_calls": 200, "rein_attempts": 200, "rein_failures": 0,
                "mounted_cape_calls": 20 if quality == "high" else 0,
                "mounted_cape_attempts": 20 if quality == "high" else 0,
                "mounted_profile_api": 1, "mounted_upper_api": 1, "mounted_cape_api": 1, "mounted_reins_api": 1}}
        observed["activeBackends"]["mountedBatch"] = {"present": True, "fallbacks": 0, "batches": 10}
    for boundary, point in cell["census"].items():
        calls = 100 if boundary == "afterSample" else 66
        point.update(mountedActors=80, mountSkeletons=80, mountedPresentation={
            "scheduling": {"cloth": 8 if quality == "high" else 0}, "rustPose": {
                "available": 80, "supported": 66, "eligible": 66, "registered": 66,
                "profiles": dict(cell["mountProfiles"]), "requestedModes": {"rust": 80},
                "failures": 0, "disabled": 14, "activeVisuals": 40, "appliedActiveVisuals": 33,
                "eligibleActiveVisuals": 33, "appliedEligibleActiveVisuals": 33, "applications": calls,
                "freshness": {"available": 80, "currentSubmissionVisuals": 66,
                    "activeEligibleCurrentVisuals": 33,
                    "applicationAgeFrames": {"count": 66, "minimum": 0, "maximum": 12, "sum": 198}},
                "secondary": {"available": 80, "upperApplications": calls, "reinApplications": calls,
                    "reinAvailable": 66, "reinCalls": calls, "clothAvailable": 40,
                    "clothCalls": (12 if boundary == "afterSample" else 1) if quality == "high" else 0,
                    "clothFallbacks": 0}}})
    return data, request


def write_project(root):
    (root / "project.godot").write_text('[application]\nconfig/use_custom_user_dir=true\n'
                                      'config/custom_user_dir_name="Godot/app_userdata/Eloria"\n'
                                      'config/custom_user_dir_name.linuxbsd="godot/app_userdata/Eloria"\n')


def write_startup_ack(environment, executable, user_dir, **changes):
    ack = {"schemaVersion": 1, "benchmark": "crowd_presentation", "pid": 12345,
           "executablePath": str(executable), "userDataDir": str(user_dir),
           "executionMode": environment["RABBITLANDS_CROWD_BENCH_EXECUTION_MODE"],
           "startToken": environment["RABBITLANDS_CROWD_BENCH_START_TOKEN"]}
    ack.update(changes)
    Path(environment["RABBITLANDS_CROWD_BENCH_OUT"] + ".started.json").write_text(json.dumps(ack))
    return ack


class ReportValidationTests(unittest.TestCase):
    def test_fullscreen_requires_reported_backend_mode_and_keeps_resolution_checks(self):
        data, request = fixture()
        request["window_mode"] = "fullscreen"
        data["measurement"].update(requestedWindowMode="fullscreen", requestedDisplayWindowMode=4,
                                   actualWindowMode=4)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for changes in ({"actualWindowMode": 0}, {"requestedDisplayWindowMode": 0},
                        {"requestedWindowMode": "windowed"}):
            bad = copy.deepcopy(data)
            bad["measurement"].update(changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(support.EvidenceError, "window mode"):
                support.validate_report(bad, request, "")
        data["measurement"].update(windowPlatform="macOS", requestedDisplayWindowMode=3, actualWindowMode=3)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        data["viewport"] = [2560, 1600]
        with self.assertRaisesRegex(support.EvidenceError, "viewport differs"):
            support.validate_report(data, request, "")

    def check_rejected(self, mutate, request_mutate=None):
        data, request = fixture()
        mutate(data)
        if request_mutate:
            request_mutate(request)
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_valid_report_and_existing_selectors(self):
        data, request = fixture()
        result = support.validate_report(data, request, "Godot starts normally")
        self.assertEqual(result["measuredCells"], ["s3-market-160"])
        self.assertEqual(support.selected_cells("phase4"), support.OLD_CELLS)
        self.assertNotIn("mixed-mounted-160", support.selected_cells("phase4"))
        self.assertEqual(len(support.selected_cells("phase1")), 7)

    def test_absent_current_services_attest_only_legacy_requests(self):
        data, request = fixture()
        for observed in [data, data['cells'][0]['effectiveRuntime']]:
            backends = observed['activeBackends']
            absent = dict(available=False, backend='legacy', mode='legacy', requested='legacy',
                          presentation_backend='legacy', mismatches=0, native_available=False,
                          reason='not_in_current_main')
            backends.update(clientRuntime=absent.copy(), remotePresentation=absent.copy(),
                            remoteCoverage=dict(backend='legacy', reason='not_in_current_main'),
                            resourceAdmission=dict(available=False, mode='legacy', requested=False,
                                reason='not_in_current_main', requested_mode='legacy',
                                requested_estimate_budget=768 * 1048576))
        self.assertTrue(support.validate_report(data, request, '')['valid'])
        for key, value in [('client_runtime', 'rust'), ('client_runtime', 'compare'),
                           ('remote_presentation', 'rust'), ('resource_admission', 'rust')]:
            with self.subTest(key=key, value=value), self.assertRaises(support.EvidenceError):
                support.validate_report(data, request | {key: value}, '')

    def test_performance_requires_actual_preset_at_top_and_each_cell(self):
        data, request = performance_fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for location in ("report", "cell"):
            for key, incorrect in (("renderScale", 1.), ("textureQuality", "full"), ("textureSkip", 0),
                                   ("appearance", "original"), ("bodyCap", 160), ("quality", "high")):
                with self.subTest(location=location, key=key):
                    bad = copy.deepcopy(data)
                    runtime_data = bad if location == "report" else bad["cells"][0]["effectiveRuntime"]
                    runtime_data["effectiveSettings"][key] = incorrect
                    with self.assertRaises(support.EvidenceError):
                        support.validate_report(bad, request, "")
        bad = copy.deepcopy(data)
        bad["crowdPolicy"]["clothBodies"] = 8
        with self.assertRaises(support.EvidenceError):
            support.validate_report(bad, request, "")
        data["runtimeBuild"]["userDataDir"] += "/different-config-directory"
        with self.assertRaisesRegex(support.EvidenceError, "exact seeded"):
            support.validate_report(data, request, "")

    def test_missing_duplicate_and_unrequested_cells_rejected(self):
        for mutate in (lambda d: d.update(cells=[]),
                       lambda d: d["cells"].append(copy.deepcopy(d["cells"][0])),
                       lambda d: d["cells"][0].update(id="s2-invasion-160")):
            with self.subTest(mutate=mutate):
                self.check_rejected(mutate)
        for selector in ("", "typo", "empty,empty", "empty,"):
            with self.assertRaises(support.EvidenceError):
                support.selected_cells(selector)

    def test_failure_nonfinite_incomplete_and_bad_statistics_rejected(self):
        changes = [lambda d: d.update(failureCount=1), lambda d: d.pop("failures"),
                   lambda d: d["cells"][0].update(frames=59),
                   lambda d: d["cells"][0]["frameSeries"].pop(),
                   lambda d: d["cells"][0]["frameSeries"].__setitem__(0, float("nan")),
                   lambda d: d["cells"][0]["frameTime"].update(p95=1.0),
                   lambda d: d["cells"][0]["frameTime"].update(mean=2.0),
                   lambda d: d["cells"][0].update(sampleMilliseconds=999),
                   lambda d: d["cells"][0]["readiness"].update(ready=False),
                   lambda d: d["worldReadiness"].update(ready=False),
                   lambda d: d["cells"][0].update(status="failed")]
        for change in changes:
            with self.subTest(change=change):
                self.check_rejected(change)

    def test_script_errors_fail_even_when_report_passed(self):
        data, request = fixture()
        for log in ("SCRIPT ERROR: broken", "ERROR: resource", "Failed to load a scene", "Parse Error: bad"):
            with self.assertRaises(support.EvidenceError):
                support.validate_report(data, request, log)

    def test_requested_actual_settings_and_workload_must_match(self):
        for change in (lambda d: d.update(renderingMethod="gl_compatibility"),
                       lambda d: d.update(graphicsQuality="low"),
                       lambda d: d.update(viewport=[640, 480]),
                       lambda d: d["effectiveSettings"].update(frameCap=30),
                       lambda d: d["activeBackends"].update(nativeReducer=True),
                       lambda d: d["crowdPolicy"].update(fullRateBodies=8),
                       lambda d: d["cells"][0]["effectiveRuntime"]["effectiveSettings"].update(bodyCap=60),
                       lambda d: d["cells"][0]["census"]["afterSample"].update(builtBodies=159),
                       lambda d: d["cells"][0]["summary"]["actorRecords"].update(max=161.),
                       lambda d: d["cells"][0]["plan"].update(active=52),
                       lambda d: d["cells"][0].update(packetsPerSecond=0)):
            with self.subTest(change=change):
                self.check_rejected(change)

    def test_exported_runtime_requires_template_not_source_editor(self):
        data, request = fixture()
        request["executable_mode"] = "exported"
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")
        data["runtimeBuild"] = {"template": True, "editor": False, "standalone": False}
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_unavailable_authored_herd_is_explicit_pending_not_accepted_timing(self):
        data, request = fixture()
        request["cells"] = "authored-herd"
        data["cells"] = [{"id": "authored-herd", "status": "unavailable_content", "qualification": "pending",
                          "reason": "Current authored manifest has no herd", "declaredAmbientAnimals": 0,
                          "frames": 0, "readiness": {"ready": False}}]
        result = support.validate_report(data, request, "")
        self.assertEqual(result["qualification"], "pending_content")
        self.assertEqual(result["measuredCells"], [])
        data["cells"][0]["qualification"] = "passed"
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_mounted_workload_requires_actual_mounts(self):
        data, request = fixture()
        request["cells"] = data["cells"][0]["id"] = "mixed-mounted-160"
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")
        for point in ("afterSpawn", "afterSample"):
            data["cells"][0]["census"][point].update(mountedActors=80, mountSkeletons=80)
        self.assertTrue(support.validate_report(data, request, "")["valid"])

    def test_replay_dynamic_population_is_allowed_but_exhaustion_is_not(self):
        data, request = fixture()
        request.update(replay=True, driver="replay")
        data["measurement"]["driver"] = "replay"
        data["replay"] = {"ok": True}
        cell = data["cells"][0]
        cell["id"] = "replay-four_gates"
        cell["replayWindow"] = {"exhausted": False, "mapChanges": 0}
        cell["census"]["afterSample"].update(nodes=161, builtBodies=161)
        cell["summary"]["actorRecords"]["max"] = 161.
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        cell["replayWindow"]["exhausted"] = True
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_traversal_requires_all_successful_route_legs_and_delivered_frames(self):
        data, request = fixture()
        request["cells"] = "traversal-southern-cold"
        cell = data["cells"][0]
        cell.update(id=request["cells"], count=1, status="complete", plan={"active": 1, "moving": 1, "fighting": 0})
        for point in cell["census"].values():
            point.update(nodes=1, builtBodies=1)
        cell["wallFrameSeries"] = [20.] * 60
        cell["wallFrameTime"] = distribution(cell["wallFrameSeries"])
        cell["route"] = {"kind": "synthetic_client_streaming", "serverNavigationCertified": False,
                         "legs": [{"id": name, "success": True, "milliseconds": 500,
                                   "readiness": {"ready": True}}
                                  for name in ("first-southern-border", "consecutive-southern-border", "interior-entry",
                                               "interior-return", "teleport", "return")]}
        cell.pop("summary")
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        cell["route"]["legs"][0]["success"] = False
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_requested_native_path_requires_actual_calls_and_zero_fallbacks(self):
        data, request = fixture()
        request["native_presentation"] = "flight"
        data["activeBackends"]["presentation"]["requested"] = "flight"
        data["cells"][0]["effectiveRuntime"]["activeBackends"]["presentation"]["requested"] = "flight"
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")
        stats = data["cells"][0]["effectiveRuntime"]["activeBackends"]["presentation"]["flight"]
        stats.update(buildAttempts=10, buildSuccesses=10)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        stats["buildFallbacks"] = 1
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_rust_runtime_request_requires_observed_backend_and_calls(self):
        data, request = fixture()
        request["client_runtime"] = "compare"
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")
        runtime = {"requested": "compare", "mode": "compare", "presentation_backend": "legacy",
                   "mismatches": 0, "native_available": True, "comparisons": 1}
        data["activeBackends"]["clientRuntime"] = dict(runtime)
        observed = data["cells"][0]["effectiveRuntime"]["activeBackends"]
        observed["clientRuntime"] = dict(runtime)
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for change in ({"mode": "legacy"}, {"native_available": False}, {"mismatches": 1}, {"comparisons": 0}):
            observed["clientRuntime"] = runtime | change
            with self.subTest(change=change), self.assertRaises(support.EvidenceError):
                support.validate_report(data, request, "")

    def test_mounted_rust_workload_requires_actual_coverage_application_and_no_fallback(self):
        data, request = mounted_rust_fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        self.assertEqual(sum(data["cells"][0]["mountProfiles"][key] for key in support.RUST_MOUNT_PROFILES), 66)
        for change in ({"available": 79}, {"supported": 13}, {"eligible": 65}, {"registered": 67},
                       {"profiles": {"other": 80}}, {"requestedModes": {"legacy": 80}}, {"failures": 1},
                       {"disabled": 15}, {"appliedEligibleActiveVisuals": 32}, {"eligibleActiveVisuals": 0},
                       {"applications": 0}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["census"]["afterSample"]["mountedPresentation"]["rustPose"].update(change)
            with self.subTest(change=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        for profile_counts in ({"moor_pony": 80}, {"other": 80}, data["cells"][0]["mountProfiles"] | {"giant_rat": 0}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["mountProfiles"] = profile_counts
            with self.subTest(profiles=profile_counts), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        for change in ({"present": False}, {"fallbacks": 1}, {"batches": 0}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["effectiveRuntime"]["activeBackends"]["mountedBatch"].update(change)
            with self.subTest(batch=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")

    def test_mounted_runtime_requires_current_submissions_and_new_secondary_calls(self):
        data, request = mounted_rust_fixture()
        for change in ({"available": 79}, {"activeEligibleCurrentVisuals": 32}, {"currentSubmissionVisuals": 67},
                       {"applicationAgeFrames": {"count": 67, "minimum": 0, "maximum": 12, "sum": 198}},
                       {"applicationAgeFrames": {"count": 66, "minimum": 3, "maximum": 1, "sum": 198}}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["census"]["afterSample"]["mountedPresentation"]["rustPose"]["freshness"].update(change)
            with self.subTest(fresh=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        for change in ({"available": 0}, {"upperApplications": 66}, {"reinApplications": 66}, {"reinCalls": 66},
                       {"clothCalls": 1}, {"clothFallbacks": 1}, {"reinAvailable": 0}, {"clothAvailable": 0}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["census"]["afterSample"]["mountedPresentation"]["rustPose"]["secondary"].update(change)
            with self.subTest(secondary=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        for field in ("freshness", "secondary"):
            broken = copy.deepcopy(data)
            del broken["cells"][0]["census"]["afterSample"]["mountedPresentation"]["rustPose"][field]
            with self.subTest(missing=field), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")
        for change in ({"poses_applied": 0}, {"upper_applied": 0}, {"rein_calls": 0}, {"rein_failures": 1},
                       {"rein_attempts": 201}, {"mounted_cape_calls": 0}, {"mounted_cape_attempts": 21},
                       {"mounted_profile_api": 0}, {"mounted_upper_api": 0}, {"mounted_cape_api": 0}, {"mounted_reins_api": 0}):
            broken = copy.deepcopy(data)
            broken["cells"][0]["effectiveRuntime"]["activeBackends"]["clientRuntime"]["native"].update(change)
            with self.subTest(native=change), self.assertRaises(support.EvidenceError):
                support.validate_report(broken, request, "")

    def test_mounted_cloth_is_exercised_only_by_the_current_high_fixture(self):
        for quality in ("high", "medium", "low"):
            data, request = mounted_rust_fixture(quality)
            with self.subTest(quality=quality):
                self.assertTrue(support.validate_report(data, request, "")["valid"])
            if quality == "high":
                data["cells"][0]["census"]["afterSample"]["mountedPresentation"]["scheduling"]["cloth"] = 0
            else:
                data["cells"][0]["census"]["afterSample"]["mountedPresentation"]["rustPose"]["secondary"]["clothCalls"] = 1
                native = data["cells"][0]["effectiveRuntime"]["activeBackends"]["clientRuntime"]["native"]
                native.update(mounted_cape_calls=1, mounted_cape_attempts=1)
            with self.subTest(unexpected_cloth=quality), self.assertRaises(support.EvidenceError):
                support.validate_report(data, request, "")


class IdentityAndProcessTests(unittest.TestCase):
    def test_window_mode_default_selection_and_headless_rejection(self):
        args = runner.parser().parse_args(["--godot", "unused"])
        self.assertEqual(args.window_mode, "windowed")
        args = runner.parser().parse_args(["--godot", "unused", "--mode", "windowed",
                                          "--window-mode", "fullscreen"])
        self.assertEqual(runner.request_for(args)["window_mode"], "fullscreen")
        with mock.patch.object(runner, "executable_path") as resolve, \
                mock.patch.object(sys, "stderr"):
            rejected = runner.main(["--godot", "unused", "--window-mode", "fullscreen"])
        self.assertEqual(rejected, 1)
        resolve.assert_not_called()

    def test_settings_profile_defaults_and_conflicting_requests(self):
        ordinary = runner.parser().parse_args(["--godot", "unused", "--quality", "low", "--fps-cap", "30"])
        support.configure_settings_profile(ordinary, system="Linux")
        self.assertEqual((ordinary.settings_profile, ordinary.quality, ordinary.fps_cap, ordinary.body_cap),
                         ("default", "low", 30, None))
        defaults = runner.parser().parse_args(["--godot", "unused"])
        support.configure_settings_profile(defaults, system="Linux")
        self.assertEqual((defaults.fps_cap, defaults.quality, defaults.body_cap), (60, "", None))
        for system in ("Windows", "Linux"):
            args = runner.parser().parse_args(["--godot", "unused", "--settings-profile", "performance"])
            support.configure_settings_profile(args, system=system)
            self.assertEqual((args.quality, args.fps_cap, args.body_cap), ("low", 30, 60))
            support.configure_settings_profile(args, system=system)  # Idempotent before each repeated run.
        for options in (["--quality", "high"], ["--fps-cap", "60"], ["--body-cap", "160"],
                        ["--tuning", "cloth=8"], ["--cells", "mixed-mounted-160"], ["--cells", "phase1"]):
            args = runner.parser().parse_args(["--godot", "unused", "--settings-profile", "performance", *options])
            with self.subTest(options=options), self.assertRaises(support.EvidenceError):
                support.configure_settings_profile(args, system="Windows")
        with self.assertRaisesRegex(support.EvidenceError, "Windows and Linux only"):
            support.configure_settings_profile(runner.parser().parse_args(
                ["--godot", "unused", "--settings-profile", "performance"]), system="Darwin")

    def test_settings_seed_is_fresh_exact_and_hashed_in_actual_custom_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            fresh = root / "isolated"
            fresh.mkdir()
            metadata = support.seed_settings_profile("performance", root, fresh, {"APPDATA": str(fresh)}, "Windows")
            path = fresh / "Godot/app_userdata/Eloria/eloria_hud.cfg"
            self.assertEqual(Path(metadata["path"]), path)
            self.assertEqual(metadata["sha256"], support.sha256_file(path))
            self.assertEqual(metadata["content"], path.read_text())
            self.assertEqual(path.read_text(), '[graphics]\n\nquality="low"\nappearance="painted_ground"\n'
                             'fps_limit=30\nrender_scale=0.75\nmap_texture_quality="half"\ncrowd_bodies=60\n'
                             'swaying_capes=0\nshadows=false\nparticles=true\ndecorative_grass=false\nname_distance=20.0\n')
            with self.assertRaisesRegex(support.EvidenceError, "already exists"):
                support.seed_settings_profile("performance", root, fresh, {"APPDATA": str(fresh)}, "Windows")
            self.assertIsNone(support.seed_settings_profile("default", root, fresh, {}, "Linux"))

    def test_settings_seed_rejects_unverified_os_project_path_and_inherited_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            fresh = root / "isolated"
            fresh.mkdir()
            for system, appdata in (("Darwin", fresh), ("Linux", fresh), ("Windows", root / "player-settings")):
                with self.subTest(system=system), self.assertRaises(support.EvidenceError):
                    support.seed_settings_profile("performance", root, fresh, {"APPDATA": str(appdata)}, system)
            (root / "project.godot").write_text('[application]\nconfig/use_custom_user_dir=false\n')
            with self.assertRaisesRegex(support.EvidenceError, "custom user directory"):
                support.seed_settings_profile("performance", root, fresh, {"APPDATA": str(fresh)}, "Windows")

    def test_linux_settings_seed_uses_exact_lowercase_custom_path_and_refuses_inherited_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            fresh = root / "isolated"
            fresh.mkdir()
            inherited = root / "player-settings"
            inherited.mkdir()
            for environment in ({}, {"APPDATA": str(fresh)}, {"XDG_DATA_HOME": str(inherited)},
                                {"XDG_DATA_HOME": "relative-user-data"}):
                with self.subTest(environment=environment), self.assertRaisesRegex(support.EvidenceError, "XDG_DATA_HOME"):
                    support.seed_settings_profile("performance", root, fresh, environment, "Linux")
            self.assertEqual(list(inherited.iterdir()), [])
            environment = {"XDG_DATA_HOME": str(fresh), "APPDATA": str(inherited)}
            metadata = support.seed_settings_profile("performance", root, fresh, environment, "Linux")
            user_dir = fresh / "godot/app_userdata/Eloria"
            path = user_dir / "eloria_hud.cfg"
            self.assertEqual(metadata["userDataDir"], str(user_dir))
            self.assertEqual(metadata["content"], path.read_text())
            self.assertEqual(metadata["sha256"], support.sha256_file(path))
            self.assertIn('map_texture_quality="half"', path.read_text())
            self.assertIn('crowd_bodies=60', path.read_text())
            self.assertFalse((fresh / "Godot").exists())
            with self.assertRaisesRegex(support.EvidenceError, "already exists"):
                support.seed_settings_profile("performance", root, fresh, environment, "Linux")

    def test_linux_settings_seed_rejects_unknown_custom_override_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            original = (root / "project.godot").read_text()
            fresh = root / "isolated"
            fresh.mkdir()
            environment = {"XDG_DATA_HOME": str(fresh)}
            for replacement in ('"Godot/app_userdata/Eloria"', '"../player-settings"'):
                (root / "project.godot").write_text(original.replace('"godot/app_userdata/Eloria"', replacement))
                with self.subTest(replacement=replacement), self.assertRaisesRegex(support.EvidenceError, "custom user directory"):
                    support.seed_settings_profile("performance", root, fresh, environment, "Linux")
            write_project(root)
            inherited = root / "player-settings"
            inherited.mkdir()
            try:
                (fresh / "godot").symlink_to(inherited, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable on this host: {exc}")
            with self.assertRaisesRegex(support.EvidenceError, "escaped"):
                support.seed_settings_profile("performance", root, fresh, environment, "Linux")
            self.assertEqual(list(inherited.iterdir()), [])

    def test_performance_config_exists_before_process_starts_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            exe = root / "Godot.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                "--settings-profile", "performance", "--cells", "s3-market-160", "--mode", "windowed",
                "--minimap", "show", "--sample-ms", "1000", "--warmup-ms", "100"])
            args.godot = exe
            data, _request = performance_fixture()

            def fake_launch(command, *, env, stdout, **_kwargs):
                self.assertEqual(env["RABBITLANDS_CROWD_BENCH_WINDOW_MODE"], "windowed")
                user_dir = Path(env["APPDATA"]) / "Godot/app_userdata/Eloria"
                self.assertTrue((user_dir / "eloria_hud.cfg").is_file())
                self.assertIn('map_texture_quality="half"', (user_dir / "eloria_hud.cfg").read_text())
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(user_dir))
                write_startup_ack(env, exe, user_dir)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))

            with mock.patch.object(support.platform, "system", return_value="Windows"), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                result = runner.run_one(args, "all", 1, root)
            self.assertTrue(result["validation"]["valid"], result["validation"])
            self.assertTrue(result["startup"]["valid"])
            self.assertEqual(result["settingsProfile"], "performance")
            seed = result["settingsSeed"]
            self.assertEqual(seed["sha256"], result["settingsSeedFinalSha256"])
            self.assertEqual(seed["sha256"], support.sha256_file(Path(seed["path"])))
            recorded = support.read_json(next(root.glob("*.process.json")))
            self.assertEqual(recorded["settingsSeed"]["content"], seed["content"])

    def test_linux_runner_seeds_before_startup_and_attests_isolated_user_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_project(root)
            exe = root / "godot"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                "--settings-profile", "performance", "--cells", "s3-market-160", "--mode", "windowed",
                "--minimap", "show", "--sample-ms", "1000", "--warmup-ms", "100"])
            args.godot = exe
            data, _request = performance_fixture()
            data["measurement"]["windowPlatform"] = "Linux"

            def fake_launch(command, *, env, stdout, **_kwargs):
                isolated = Path(env["XDG_DATA_HOME"])
                self.assertTrue(isolated.is_relative_to(root / "userdata"))
                user_dir = isolated / "godot/app_userdata/Eloria"
                self.assertTrue((user_dir / "eloria_hud.cfg").is_file())
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(user_dir))
                write_startup_ack(env, exe, user_dir)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))

            with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(root / "player-settings")}), \
                    mock.patch.object(support.platform, "system", return_value="Linux"), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                result = runner.run_one(args, "all", 1, root)
            self.assertTrue(result["validation"]["valid"], result["validation"])
            self.assertTrue(result["startup"]["valid"])
            seed = result["settingsSeed"]
            self.assertEqual(seed["sha256"], result["settingsSeedFinalSha256"])
            self.assertFalse((root / "player-settings").exists())

    def test_missing_invalid_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for content in (None, "", "[]", "{bad}", '{"x":NaN}', '{"x":1e999}'):
                if content is not None:
                    path.write_text(content)
                with self.assertRaises(support.EvidenceError):
                    support.read_json(path)

    def test_artifact_manifest_verified_and_cannot_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "client.pck"
            artifact.write_bytes(b"a package")
            manifest = root / "manifest.json"
            data = {"artifacts": [{"path": "client.pck", "sha256": support.sha256_file(artifact)}]}
            manifest.write_text(json.dumps(data))
            self.assertEqual(support.manifest_identity(manifest)["fileCount"], 1)
            artifact.write_bytes(b"changed")
            with self.assertRaises(support.EvidenceError):
                support.manifest_identity(manifest)
            data["artifacts"][0]["path"] = "../private-file"
            manifest.write_text(json.dumps(data))
            with self.assertRaises(support.EvidenceError):
                support.manifest_identity(manifest)

    def test_hashes_cover_content_and_names_and_map_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "godot-client"
            (client / "data/maps").mkdir(parents=True)
            (client / "assets").mkdir()
            world = root / "maps/world.json"
            world.parent.mkdir()
            (world.parent / "world.glb").write_bytes(b"mesh")
            (world.parent / "texture.png").write_bytes(b"image")
            world.write_text(json.dumps({"asset": {"glb": "world.glb"}, "externalResources": {"texture.png": "digest"}}))
            (client / "data/maps/registry.json").write_text(json.dumps({"maps": {
                "test": {"manifest": "res://../maps/world.json"}}}))
            files = support.asset_files(client, ["test"])
            self.assertIn(world, files)
            self.assertIn(world.parent / "texture.png", files)
            initial = support.hash_files(files, root)["sha256"]
            (world.parent / "world.glb").write_bytes(b"changed mesh")
            self.assertNotEqual(initial, support.hash_files(files, root)["sha256"])

    def test_stream_root_omits_unused_monolith_but_requires_real_chunk_mesh(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = root / "godot-client"
            (client / "data/maps").mkdir(parents=True)
            world = root / "maps/world.json"
            chunk = root / "maps/chunks/one/world.json"
            chunk.parent.mkdir(parents=True)
            chunk.write_text(json.dumps({"asset": {"glb": "world.glb"}}))
            mesh = chunk.with_suffix(".glb")
            mesh.write_bytes(b"actual chunk geometry")
            world.write_text(json.dumps({"asset": {"glb": "unused-root.glb"},
                "streamingChunks": {"chunks": [{"manifest": "chunks/one/world.json"}]}}))
            (client / "data/maps/registry.json").write_text(json.dumps({"maps": {
                "test": {"manifest": "res://../maps/world.json"}}}))
            files = support.asset_files(client, ["test"])
            self.assertIn(mesh, files)
            self.assertNotIn(world.parent / "unused-root.glb", files)
            mesh.unlink()
            with self.assertRaises(support.EvidenceError):
                support.asset_files(client, ["test"])

    def test_complete_manifest_rejects_added_removed_files_and_false_sizes_or_aggregate(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "client.pck"
            artifact.write_bytes(b"packed")
            manifest = root / "benchmark-package.json"
            digest = support.sha256_file(artifact)
            content_hash = hashlib.sha256(b"client.pck\0" + bytes.fromhex(digest)).hexdigest()
            data = {"schemaVersion": 1, "contentComplete": True, "contentHash": content_hash,
                    "artifacts": [{"path": "client.pck", "sha256": digest, "bytes": 6}]}
            manifest.write_text(json.dumps(data))
            self.assertTrue(support.manifest_identity(manifest)["contentComplete"])
            unexpected = root / "new-runtime.glb"
            unexpected.write_bytes(b"unexpected")
            with self.assertRaisesRegex(support.EvidenceError, "inventory changed"):
                support.manifest_identity(manifest)
            unexpected.unlink()
            artifact.unlink()
            with self.assertRaises(support.EvidenceError):
                support.manifest_identity(manifest)
            artifact.write_bytes(b"packed")
            for mutation in (lambda d: d["artifacts"][0].update(bytes=5),
                             lambda d: d.update(contentHash="0" * 64),
                             lambda d: d["artifacts"][0].pop("bytes")):
                bad = copy.deepcopy(data)
                mutation(bad)
                manifest.write_text(json.dumps(bad))
                with self.assertRaises(support.EvidenceError):
                    support.manifest_identity(manifest)

    def test_environment_overrides_isolated_without_recording_unrelated_secrets(self):
        clean, names = support.clean_environment({"PATH": "usable", "ELORIA_LOOK_QUALITY": "low",
                                                  "ELORIA_WARDROBE_TEXTURE_CACHE": "1",
                                                  "ELORIA_ACTOR_BUILD_PROFILE": "1",
                                                  "RABBITLANDS_CROWD_TUNING": "full=0", "SECRET_TOKEN": "hidden"})
        self.assertEqual(clean["PATH"], "usable")
        self.assertNotIn("ELORIA_LOOK_QUALITY", clean)
        for diagnostic in ("ELORIA_WARDROBE_TEXTURE_CACHE", "ELORIA_ACTOR_BUILD_PROFILE"):
            self.assertNotIn(diagnostic, clean)
            self.assertIn(diagnostic, names)
        self.assertNotIn("SECRET_TOKEN", names)

    def test_replay_output_must_stay_outside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "repo"
            client = repo / "godot-client"
            client.mkdir(parents=True)
            (repo / ".git").write_text("gitdir: somewhere")
            with self.assertRaises(support.EvidenceError):
                support.require_private_replay_output(repo / "test-artifacts", client)
            support.require_private_replay_output(Path(root.anchor) / "rl-private-not-created", client)

    def test_exported_command_does_not_relabel_a_source_project(self):
        args = runner.parser().parse_args(["--godot", "test.exe", "--executable-mode", "exported",
                                          "--main-pack", "workload.pck"])
        command = runner.command_for(args, Path("engine.log"))
        self.assertIn("--main-pack", command)
        self.assertNotIn("--path", command)
        self.assertNotIn("--script", command)
        args.executable_mode = "project"
        self.assertIn("--script", runner.command_for(args, Path("engine.log")))
        args.executable_mode = "exported"
        args.benchmark_script = "res://other.gd"
        with self.assertRaisesRegex(support.EvidenceError, "custom --benchmark-script"):
            runner.command_for(args, Path("engine.log"))

    def test_startup_ack_is_bound_to_own_pid_executable_mode_token_and_isolated_user_dir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = {"pid": 12345, "executable": str(root / "app.exe"), "executable_mode": "exported",
                       "start_token": "unique-nonce", "user_root": str(root / "userdata")}
            ack = {"schemaVersion": 1, "benchmark": "crowd_presentation", "pid": request["pid"],
                   "executablePath": request["executable"], "executionMode": "exported",
                   "startToken": "unique-nonce", "userDataDir": str(root / "userdata/custom")}
            self.assertEqual(support.validate_startup_ack(ack, request), ack)
            for key, wrong in (("schemaVersion", True), ("benchmark", "ordinary_game"), ("pid", 12346),
                               ("executionMode", "project"), ("startToken", "old-nonce"),
                               ("executablePath", str(root / "other.exe")), ("userDataDir", str(root / "ordinary-user"))):
                with self.subTest(key=key), self.assertRaises(support.EvidenceError):
                    support.validate_startup_ack(ack | {key: wrong}, request)
            request["settings_seed_user_dir"] = str(root / "userdata/seeded")
            with self.assertRaisesRegex(support.EvidenceError, "exact seeded"):
                support.validate_startup_ack(ack, request)

    def test_startup_wait_is_bounded_and_detects_exit_even_if_exit_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.started.json"
            process = mock.Mock(poll=mock.Mock(return_value=None))
            with mock.patch.object(runner.time, "monotonic", side_effect=[0, 0, .1]), \
                    mock.patch.object(runner.time, "sleep") as sleep, \
                    self.assertRaisesRegex(support.EvidenceError, "within 0.1 seconds"):
                runner.wait_for_startup(process, path, {}, .1)
            sleep.assert_called_once_with(.05)
            process.poll.return_value = 0
            with self.assertRaisesRegex(support.EvidenceError, "exited before.*\\(0\\)"):
                runner.wait_for_startup(process, path, {}, 60)

    def test_startup_failure_stops_only_owned_process_and_retains_invalid_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "app.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                                              "--executable-mode", "exported", "--main-pack", "test.pck"])
            args.godot = exe
            process = mock.Mock(pid=12345, poll=mock.Mock(return_value=None), wait=mock.Mock(return_value=-9))
            with mock.patch.object(runner, "identity", side_effect=[{"source": "stable"}, support.EvidenceError("changed package")]), \
                    mock.patch.object(runner.subprocess, "Popen", return_value=process), \
                    mock.patch.object(runner, "wait_for_startup", side_effect=support.EvidenceError("wrong start token")):
                result = runner.run_one(args, "all", 1, root)
            process.kill.assert_called_once_with()
            process.wait.assert_called_once_with()
            self.assertFalse(result["validation"]["valid"])
            self.assertEqual(result["validation"]["errors"], ["wrong start token"])
            self.assertEqual(result["identityAfter"]["error"], "changed package")
            self.assertFalse(result["startup"]["valid"])
            recorded = support.read_json(next(root.glob("*.process.json")))
            self.assertEqual(recorded["pid"], 12345)
            self.assertEqual(recorded["startup"]["error"], "wrong start token")

    def test_exit_zero_with_missing_report_or_error_log_is_invalid(self):
        for missing, error_log, changed in ((True, False, False), (False, True, False), (False, False, True),
                                            (False, False, False)):
            with self.subTest(missing=missing, error_log=error_log, changed=changed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                exe = root / "Godot.exe"
                exe.write_bytes(b"not executed")
                args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                                                  "--cells", "s3-market-160", "--mode", "windowed",
                                                  "--window-mode", "fullscreen",
                                                  "--quality", "high", "--minimap", "show", "--body-cap", "160",
                                                  "--sample-ms", "1000", "--warmup-ms", "100"])
                args.godot = exe
                data, _request = fixture()
                data["measurement"].update(requestedWindowMode="fullscreen", requestedDisplayWindowMode=4,
                                           actualWindowMode=4)

                def fake_launch(command, *, env, stdout, **_kwargs):
                    self.assertEqual(env["RABBITLANDS_CROWD_BENCH_WINDOW_MODE"], "fullscreen")
                    data["runtimeBuild"].update(executablePath=str(exe), userDataDir=env["APPDATA"] + "/Godot/app_userdata/Eloria")
                    write_startup_ack(env, exe, data["runtimeBuild"]["userDataDir"])
                    if not missing:
                        Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                    Path(command[command.index("--log-file") + 1]).write_text("ERROR: broken resource" if error_log else "normal")
                    stdout.write("launched a Python mock, no engine")
                    return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))

                snapshots = [{"source": "initial"}, {"source": "changed" if changed else "initial"}]
                with mock.patch.object(runner, "identity", side_effect=snapshots), \
                        mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                    result = runner.run_one(args, "all", 1, root)
                self.assertEqual(result["validation"]["valid"], not (missing or error_log or changed), result["validation"])
                self.assertTrue(list(root.glob("*.process.json")))

    def test_actual_user_data_must_be_isolated(self):
        data, request = fixture()
        request["user_root"] = str(INTEGRATION / "isolated-run")
        data["runtimeBuild"]["userDataDir"] = str(INTEGRATION / "ordinary-preferences")
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_exclusive_lock_is_released_on_process_death_without_deleting_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared.lock"
            script = ("import sys,time;sys.path.insert(0,sys.argv[1]);"
                      "from crowd_benchmark_support import BenchmarkLock;"
                      "lock=BenchmarkLock(__import__('pathlib').Path(sys.argv[2]));lock.__enter__();"
                      "print('locked',flush=True);time.sleep(30)")
            child = subprocess.Popen([sys.executable, "-c", script, str(INTEGRATION), str(path)],
                                     stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), "locked")
                with path.open("rb") as stream:
                    stream.seek(1)  # Windows prohibits reading another process's locked byte.
                    original = stream.read()
                with self.assertRaises(support.EvidenceError):
                    with support.BenchmarkLock(path):
                        self.fail("second owner acquired lock")
                with path.open("rb") as stream:
                    stream.seek(1)
                    self.assertEqual(stream.read(), original)
                child.kill()
                child.wait(timeout=5)
                with support.BenchmarkLock(path):
                    self.assertTrue(path.exists())
                self.assertTrue(path.exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.stdout.close()


if __name__ == "__main__":
    unittest.main()
