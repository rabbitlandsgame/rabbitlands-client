"""Regression tests for crowd benchmark evidence validation."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


CLIENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = CLIENT_ROOT / "scripts" / "summarize_crowd_benchmarks.py"
SPEC = importlib.util.spec_from_file_location("summarize_crowd_benchmarks", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
SUMMARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUMMARY)


def _distribution(samples: int, mean: float, p50: float, p95: float,
                  p99: float, maximum: float) -> dict[str, float | int]:
    return {
        "samples": samples,
        "mean": mean,
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "max": maximum,
    }


def _raw_fixture() -> tuple[dict, dict, dict]:
    values = [float(value) for value in range(1, 101)]
    value_distribution = _distribution(100, 50.5, 50.0, 95.0, 99.0, 100.0)
    raw = {metric: values.copy() for metric in SUMMARY.PACKET_METRICS}
    raw["packetsPerFrame"] = [1.0] * 100
    summary = {
        metric: copy.deepcopy(value_distribution) for metric in SUMMARY.PACKET_METRICS
    }
    summary["packetsPerFrame"] = _distribution(100, 1.0, 1.0, 1.0, 1.0, 1.0)
    packet_summary = {
        metric: copy.deepcopy(value_distribution) for metric in SUMMARY.PACKET_METRICS
    }
    return raw, summary, packet_summary


def _validate_raw(raw: dict, summary: dict, packet_summary: dict) -> None:
    SUMMARY._validate_raw_distributions(
        raw,
        summary,
        summary,
        packet_summary,
        packet_summary,
        100,
        "sample",
    )


def _run(report_path: Path, *, dirty: bool = False) -> dict:
    report_path.write_text("{}", encoding="utf-8")
    return {
        "path": str(report_path),
        "runId": "synthetic-run",
        "backend": "gdscript",
        "renderer": "forward_plus",
        "headless": False,
        "trial": 1,
        "commit": "0123456789abcdef",
        "sourceHash": "source-hash",
        "dirty": dirty,
        "nativePresentation": {
            "attestation": "attested",
            "requestedMode": "off",
            "environmentValue": "0",
            "requestedComponents": {"cape": False, "flight": False},
            "actual": {},
        },
        "executionLimits": {
            "pid": 123,
            "requestedAffinityMask": 15,
            "requestedWorkerThreads": 2,
        },
    }


def _companion(*, dirty: bool = False) -> dict:
    return {
        "runId": "synthetic-run",
        "backend": "gdscript",
        "renderer": "forward_plus",
        "mode": "windowed",
        "trial": 1,
        "commit": "0123456789abcdef",
        "sourceHash": "source-hash",
        "exitCode": 0,
        "cleanExit": True,
        "abortedAfterReport": False,
        "postReportStop": False,
        "reportValid": True,
        "schemaValid": True,
        "scriptErrorsDetected": False,
        "forcedTermination": False,
        "monitoringError": "",
        "affinityMask": 15,
        "allObservedProcessesVerified": True,
        "rootPid": 123,
        "observedProcesses": {
            "123": {
                "affinityMask": 15,
                "name": "Godot",
                "path": "C:/Godot/Godot.exe",
                "startTimeUtc": "2026-09-19T10:00:00Z",
            }
        },
        "requestedGodotPath": "C:/Godot/Godot.exe",
        "launchExecutablePath": "C:/Godot/Godot.exe",
        "sourceFiles": {"godot-client/source.gd": "digest"},
        "dirty": dirty,
        "monitoring": "synthetic exact-process monitor",
        "nativePresentationRequested": "Off",
        "nativePresentationEnvironment": "0",
    }


class RawDistributionValidationTests(unittest.TestCase):
    def test_rejects_mean_that_does_not_match_raw_samples(self) -> None:
        raw, summary, packet_summary = _raw_fixture()
        summary["wallMilliseconds"]["mean"] = 50.6

        with self.assertRaisesRegex(SUMMARY.SummaryError, r"wallMilliseconds\.mean"):
            _validate_raw(raw, summary, packet_summary)

    def test_rejects_tail_that_does_not_match_raw_samples(self) -> None:
        raw, summary, packet_summary = _raw_fixture()
        summary["wallMilliseconds"]["p99"] = 98.0

        with self.assertRaisesRegex(SUMMARY.SummaryError, r"wallMilliseconds\.p99"):
            _validate_raw(raw, summary, packet_summary)

    def test_rejects_non_finite_raw_sample(self) -> None:
        raw, summary, packet_summary = _raw_fixture()
        raw["wallMilliseconds"][50] = float("inf")

        with self.assertRaisesRegex(SUMMARY.SummaryError, r"raw\.wallMilliseconds\[50\].*finite"):
            _validate_raw(raw, summary, packet_summary)


class AttributionAdmissionTests(unittest.TestCase):
    def test_accepts_legacy_or_explicit_uninstrumented_measurement(self) -> None:
        SUMMARY._validate_acceptance_attribution({}, "measurement")
        SUMMARY._validate_acceptance_attribution({
            "attribution": {
                "enabled": False,
                "acceptanceTimingComparable": True,
            },
        }, "measurement")

    def test_rejects_instrumented_diagnostic_from_acceptance_summary(self) -> None:
        with self.assertRaisesRegex(
                SUMMARY.SummaryError, "cannot enter acceptance timing summaries"):
            SUMMARY._validate_acceptance_attribution({
                "attribution": {
                    "enabled": True,
                    "acceptanceTimingComparable": False,
                },
            }, "measurement")

    def test_rejects_missing_nonboolean_or_inconsistent_flags(self) -> None:
        malformed = (
            {"enabled": False},
            {"enabled": "false", "acceptanceTimingComparable": True},
            {"enabled": False, "acceptanceTimingComparable": False},
            {"enabled": True, "acceptanceTimingComparable": True},
        )
        for attribution in malformed:
            with self.subTest(attribution=attribution):
                with self.assertRaises(SUMMARY.SummaryError):
                    SUMMARY._validate_acceptance_attribution(
                        {"attribution": attribution}, "measurement")


class AcceptanceEligibilityTests(unittest.TestCase):
    def test_accepts_legacy_or_explicit_production_measurement(self) -> None:
        production = [{"features": "full"}]
        SUMMARY._validate_acceptance_eligibility({}, production, "measurement")
        SUMMARY._validate_acceptance_eligibility({
            "acceptance": {
                "eligible": True,
                "diagnosticOnly": False,
                "reason": "production presentation features",
            },
        }, production, "measurement")

    def test_external_engine_profile_cannot_enter_acceptance(self) -> None:
        # Even erroneous eligibility metadata must not admit paused/instrumented
        # profiler samples into the ordinary frame-time comparison.
        for acceptance in ({}, {"eligible": True, "diagnosticOnly": False,
                                "reason": "incorrect production label"}):
            with self.subTest(acceptance=acceptance):
                with self.assertRaisesRegex(SUMMARY.SummaryError, "external engine profiling"):
                    SUMMARY._validate_acceptance_eligibility({
                        "engineProfileMarkersEnabled": True,
                        "acceptance": acceptance,
                    }, [{"features": "full"}], "measurement")
        SUMMARY._validate_acceptance_eligibility(
            {"engineProfileMarkersEnabled": False}, [{"features": "full"}], "measurement")

    def test_rejects_solver_off_even_when_attribution_is_disabled(self) -> None:
        measurement = {
            "attribution": {
                "enabled": False,
                "acceptanceTimingComparable": True,
            },
            "acceptance": {
                "eligible": False,
                "diagnosticOnly": True,
                "reason": "cape simulation bypass diagnostic",
            },
        }
        SUMMARY._validate_acceptance_attribution(measurement, "measurement")
        with self.assertRaisesRegex(
                SUMMARY.SummaryError, "diagnostic intervention"):
            SUMMARY._validate_acceptance_eligibility(
                measurement, [{"features": "cape_solver_off"}], "measurement")

    def test_solver_off_cannot_lie_about_acceptance_eligibility(self) -> None:
        with self.assertRaisesRegex(SUMMARY.SummaryError, "not marked diagnostic-only"):
            SUMMARY._validate_acceptance_eligibility({
                "acceptance": {
                    "eligible": True,
                    "diagnosticOnly": False,
                    "reason": "incorrect",
                },
            }, [{"features": "cape_solver_off"}], "measurement")

    def test_rejects_missing_or_inconsistent_acceptance_flags(self) -> None:
        malformed = (
            {"eligible": True, "reason": "missing flag"},
            {"eligible": "true", "diagnosticOnly": False, "reason": "wrong type"},
            {"eligible": True, "diagnosticOnly": True, "reason": "inconsistent"},
            {"eligible": False, "diagnosticOnly": False, "reason": "inconsistent"},
        )
        for acceptance in malformed:
            with self.subTest(acceptance=acceptance):
                with self.assertRaises(SUMMARY.SummaryError):
                    SUMMARY._validate_acceptance_eligibility(
                        {"acceptance": acceptance}, [{"features": "full"}],
                        "measurement")


class NativePresentationAdmissionTests(unittest.TestCase):
    @staticmethod
    def _fixture(
        mode: str, *, world_attested: bool | None = None
    ) -> tuple[dict, list[dict]]:
        if world_attested is None:
            world_attested = mode in {"world", "all"}
        wants_cape = mode in {"cape", "both", "all"}
        wants_flight = mode in {"flight", "both", "all"}
        wants_world = mode in {"world", "all"}
        cape_before = {
            "modifierInstances": 180,
            "statsSupportedInstances": 180,
            "activeInstances": 180 if wants_cape else 0,
            "nativeBackendInstances": 180 if wants_cape else 0,
            "gdscriptBackendInstances": 0 if wants_cape else 180,
            "nativeCalls": 10 if wants_cape else 0,
            "fallbackCalls": 0,
        }
        cape_after = dict(cape_before)
        cape_after["nativeCalls"] = 20 if wants_cape else 0
        flight_before = {
            "statsSupported": True,
            "instances": 3 if wants_flight else 0,
            "activeInstances": 3 if wants_flight else 0,
            "buildAttempts": 5 if wants_flight else 0,
            "buildSuccesses": 5 if wants_flight else 0,
            "buildFallbacks": 0,
        }
        flight_after = dict(flight_before)
        flight_after["buildAttempts"] = 10 if wants_flight else 0
        flight_after["buildSuccesses"] = 10 if wants_flight else 0
        world_before = {
            "statsSupported": True,
            "instances": 4 if wants_world else 0,
            "activeInstances": 4 if wants_world else 0,
            "buildAttempts": 7 if wants_world else 0,
            "buildSuccesses": 7 if wants_world else 0,
            "buildFallbacks": 0,
        }
        world_after = dict(world_before)
        world_after["buildAttempts"] = 14 if wants_world else 0
        world_after["buildSuccesses"] = 14 if wants_world else 0
        actual = {
            "capeModifierInstancesMaximum": 180,
            "capeStatsSupportedInstancesMaximum": 180,
            "capeActiveInstancesMaximum": 180 if wants_cape else 0,
            "capeNativeBackendInstancesMaximum": 180 if wants_cape else 0,
            "capeGdscriptBackendInstancesMaximum": 0 if wants_cape else 180,
            "capeNativeCalls": 10 if wants_cape else 0,
            "capeFallbackCalls": 0,
            "flightInstancesMaximum": 3 if wants_flight else 0,
            "flightActiveInstancesMaximum": 3 if wants_flight else 0,
            "flightBuildAttempts": 5 if wants_flight else 0,
            "flightBuildSuccesses": 5 if wants_flight else 0,
            "flightBuildFallbacks": 0,
            "capeMatchedRequest": True,
            "flightMatchedRequest": True,
            "matchedRequest": True,
        }
        if world_attested:
            actual.update({
                "worldStatsSupported": True,
                "worldInstancesMaximum": 4 if wants_world else 0,
                "worldActiveInstancesMaximum": 4 if wants_world else 0,
                "worldBuildAttempts": 7 if wants_world else 0,
                "worldBuildSuccesses": 7 if wants_world else 0,
                "worldBuildFallbacks": 0,
                "worldMatchedRequest": True,
            })
        presentation = {
            "requestedMode": mode,
            "environmentValue": {
                "off": "0", "cape": "cape", "flight": "flight", "both": "both",
                "world": "world", "all": "all",
            }[mode],
            "reducerIndependent": True,
            "actual": actual,
        }
        cells = [{
            "nativePresentation": {
                "requestedMode": mode,
                "beforeSample": {"cape": cape_before, "flight": flight_before},
                "afterSample": {"cape": cape_after, "flight": flight_after},
                "delta": {
                    "capeNativeCalls": 10 if wants_cape else 0,
                    "capeFallbackCalls": 0,
                    "flightBuildAttempts": 5 if wants_flight else 0,
                    "flightBuildSuccesses": 5 if wants_flight else 0,
                    "flightBuildFallbacks": 0,
                },
            },
        }]
        if world_attested:
            cells[0]["nativePresentation"]["beforeSample"]["world"] = world_before
            cells[0]["nativePresentation"]["afterSample"]["world"] = world_after
            cells[0]["nativePresentation"]["delta"].update({
                "worldBuildAttempts": 7 if wants_world else 0,
                "worldBuildSuccesses": 7 if wants_world else 0,
                "worldBuildFallbacks": 0,
            })
        return presentation, cells

    def test_accepts_legacy_and_each_attested_mode(self) -> None:
        self.assertIsNone(SUMMARY._validate_native_presentation(None, [], "run"))
        for mode in ("off", "cape", "flight", "both", "world", "all"):
            with self.subTest(mode=mode):
                presentation, cells = self._fixture(mode)
                checked = SUMMARY._validate_native_presentation(
                    presentation, cells, "run")
                self.assertEqual(mode, checked["requestedMode"])
        presentation, cells = self._fixture("both", world_attested=True)
        checked = SUMMARY._validate_native_presentation(presentation, cells, "run")
        self.assertTrue(checked["worldAttested"])

    def test_rejects_world_request_without_world_attestation(self) -> None:
        presentation, cells = self._fixture("world", world_attested=False)
        with self.assertRaisesRegex(SUMMARY.SummaryError, "without world attestation"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_world_fallback_or_unrequested_activity(self) -> None:
        presentation, cells = self._fixture("all")
        cells[0]["nativePresentation"]["delta"]["worldBuildFallbacks"] = 1
        cells[0]["nativePresentation"]["afterSample"]["world"]["buildFallbacks"] = 1
        presentation["actual"]["worldBuildFallbacks"] = 1
        with self.assertRaisesRegex(SUMMARY.SummaryError, "world activity"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_world_activity_when_both_does_not_request_world(self) -> None:
        presentation, cells = self._fixture("both", world_attested=True)
        before = cells[0]["nativePresentation"]["beforeSample"]["world"]
        after = cells[0]["nativePresentation"]["afterSample"]["world"]
        before.update({
            "instances": 4,
            "activeInstances": 4,
            "buildAttempts": 7,
            "buildSuccesses": 7,
        })
        after.update({
            "instances": 4,
            "activeInstances": 4,
            "buildAttempts": 14,
            "buildSuccesses": 14,
        })
        cells[0]["nativePresentation"]["delta"].update({
            "worldBuildAttempts": 7,
            "worldBuildSuccesses": 7,
        })
        presentation["actual"].update({
            "worldInstancesMaximum": 4,
            "worldActiveInstancesMaximum": 4,
            "worldBuildAttempts": 7,
            "worldBuildSuccesses": 7,
        })
        with self.assertRaisesRegex(SUMMARY.SummaryError, "world activity"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_partial_world_attestation(self) -> None:
        presentation, cells = self._fixture("both", world_attested=False)
        presentation["actual"]["worldBuildAttempts"] = 0
        with self.assertRaisesRegex(SUMMARY.SummaryError, "partial world attestation"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_requested_but_inactive_component(self) -> None:
        presentation, cells = self._fixture("cape")
        presentation["actual"]["capeActiveInstancesMaximum"] = 0
        with self.assertRaises(SUMMARY.SummaryError):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_unrequested_activity_or_fallback(self) -> None:
        presentation, cells = self._fixture("off")
        cells[0]["nativePresentation"]["delta"]["flightBuildFallbacks"] = 1
        cells[0]["nativePresentation"]["afterSample"]["flight"][
            "buildFallbacks"
        ] = 1
        presentation["actual"]["flightBuildFallbacks"] = 1
        with self.assertRaisesRegex(SUMMARY.SummaryError, "actual activity"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_environment_mode_mismatch(self) -> None:
        presentation, cells = self._fixture("both")
        presentation["environmentValue"] = "1"
        with self.assertRaisesRegex(SUMMARY.SummaryError, "environment/mode mismatch"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_reported_delta_that_does_not_match_snapshots(self) -> None:
        presentation, cells = self._fixture("cape")
        cells[0]["nativePresentation"]["delta"]["capeNativeCalls"] = 9
        with self.assertRaisesRegex(SUMMARY.SummaryError, "afterSample minus beforeSample"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")

    def test_rejects_counter_that_decreases_during_sampling(self) -> None:
        presentation, cells = self._fixture("flight")
        cells[0]["nativePresentation"]["afterSample"]["flight"][
            "buildSuccesses"
        ] = 4
        with self.assertRaisesRegex(SUMMARY.SummaryError, "counters decreased"):
            SUMMARY._validate_native_presentation(presentation, cells, "run")


class CompanionValidationTests(unittest.TestCase):
    def _validate(
        self, companion: dict, *, report_dirty: bool = False,
        report_affinity: int = 15,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "run.json"
            run = _run(report_path, dirty=report_dirty)
            run["executionLimits"]["requestedAffinityMask"] = report_affinity
            companion_path = report_path.with_name("run.process.json")
            companion_path.write_text(json.dumps(companion), encoding="utf-8")
            SUMMARY._validate_companion(run, allow_missing_for_fixtures=False)

    def test_accepts_complete_current_attestation(self) -> None:
        self._validate(_companion())

    def test_rejects_nonempty_monitoring_error(self) -> None:
        companion = _companion()
        companion["monitoringError"] = "process identity probe failed"

        with self.assertRaisesRegex(SUMMARY.SummaryError, "monitoringError is non-empty"):
            self._validate(companion)

    def test_current_attestation_flags_are_all_required(self) -> None:
        for field in (
            "reportValid",
            "schemaValid",
            "scriptErrorsDetected",
            "forcedTermination",
            "monitoringError",
        ):
            with self.subTest(field=field):
                companion = _companion()
                del companion[field]
                with self.assertRaisesRegex(SUMMARY.SummaryError, rf"\.{field} is required"):
                    self._validate(companion)

    def test_rejects_dirty_state_mismatch(self) -> None:
        with self.assertRaisesRegex(SUMMARY.SummaryError, "dirty does not match its report"):
            self._validate(_companion(dirty=True), report_dirty=False)

    def test_rejects_wrong_process_presentation_mode_or_environment(self) -> None:
        for key, value in (
            ("nativePresentationRequested", "Cape"),
            ("nativePresentationEnvironment", "cape"),
        ):
            with self.subTest(key=key):
                companion = _companion()
                companion[key] = value
                with self.assertRaisesRegex(
                    SUMMARY.SummaryError, rf"\.{key} does not match"
                ):
                    self._validate(companion)

    def test_rejects_process_execution_limit_mismatch(self) -> None:
        companion = _companion()
        with self.assertRaisesRegex(SUMMARY.SummaryError, "requestedAffinityMask"):
            self._validate(companion, report_affinity=7)

    def test_rejects_process_identity_mismatch_with_report(self) -> None:
        companion = _companion()
        companion["rootPid"] = 124
        companion["observedProcesses"]["124"] = companion["observedProcesses"].pop("123")
        with self.assertRaisesRegex(SUMMARY.SummaryError, "process.pid"):
            self._validate(companion)


class LodFixtureValidationTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        return {
            "before": {
                "distanceBands": {
                    "near0To45": 100,
                    "mid45To80": 100,
                    "beyond80": 100,
                },
                "animationTiers": {"full": 100, "half": 100, "paused": 100},
                "frustumAndDrawVisible": 200,
                "frustumIntersecting": 200,
                "withinDrawDistance": 200,
            },
            "after": {
                "animationTiers": {"full": 101, "half": 99, "paused": 100},
            },
            "camera": {
                "distance": 32.0,
                "pitchDegrees": -25.0,
                "yawDegrees": 0.0,
                "fieldOfViewDegrees": 50.0,
            },
            "visibilityValidation": {"min": 200, "max": 200},
            "grounding": {"surfaceHits": 300, "surfaceMatches": 300, "surfaceMisses": 0},
        }

    def test_accepts_declared_lod_census_and_post_workload_one_shot_shift(self) -> None:
        self.assertEqual(SUMMARY._expected_visible_count(300, "lod_bands", "cell"), 200)
        SUMMARY._validate_lod_fixture(self._fixture(), 300, "cell.fixture")

    def test_rejects_wrong_initial_band_or_tier(self) -> None:
        corruptions = (
            ("distanceBands", "mid45To80", 99),
            ("animationTiers", "half", 99),
        )
        for group, key, value in corruptions:
            with self.subTest(group=group, key=key):
                fixture = self._fixture()
                fixture["before"][group][key] = value
                with self.assertRaisesRegex(SUMMARY.SummaryError, rf"before\.{group}"):
                    SUMMARY._validate_lod_fixture(fixture, 300, "cell.fixture")


class NativePresentationAggregationTests(unittest.TestCase):
    @staticmethod
    def _run(mode: str | None, trial: int, *, world_attested: bool = False) -> dict:
        presentation = None
        if mode is not None:
            presentation = {
                "attestation": "attested",
                "worldAttested": world_attested,
                "requestedMode": mode,
                "environmentValue": {
                    "off": "0", "cape": "cape", "flight": "flight", "both": "both",
                }[mode],
                "requestedComponents": {
                    "cape": mode in {"cape", "both"},
                    "flight": mode in {"flight", "both"},
                    "world": False,
                },
                "actual": {
                    "capeActiveInstancesMaximum": 150 if mode in {"cape", "both"} else 0,
                    "capeNativeCalls": 100 if mode in {"cape", "both"} else 0,
                    "capeFallbackCalls": 0,
                    "flightActiveInstancesMaximum": 52 if mode in {"flight", "both"} else 0,
                    "flightBuildAttempts": 40 if mode in {"flight", "both"} else 0,
                    "flightBuildSuccesses": 40 if mode in {"flight", "both"} else 0,
                    "flightBuildFallbacks": 0,
                },
            }
            if world_attested:
                presentation["actual"].update({
                    "worldStatsSupported": True,
                    "worldInstancesMaximum": 0,
                    "worldActiveInstancesMaximum": 0,
                    "worldBuildAttempts": 0,
                    "worldBuildSuccesses": 0,
                    "worldBuildFallbacks": 0,
                })
        return {
            "path": f"C:/fixtures/run-{trial}.json",
            "sha256": f"sha-{trial}",
            "runId": f"run-{trial}",
            "label": "same-label",
            "backend": "gdscript",
            "nativeBackendActive": False,
            "renderer": "gl_compatibility",
            "display": "headless",
            "headless": True,
            "nativePresentation": presentation,
            "executionLimits": None,
            "commit": "0123456789abcdef",
            "sourceHash": "same-source-hash",
            "dirty": False,
            "trial": trial,
            "sharedMachine": True,
            "interferenceLabel": "synthetic shared host",
            "driver": {
                "status": "validated",
                "version": SUMMARY.DRIVER_VERSION,
                "productionFaithful": True,
                "caveat": None,
            },
            "cells": [],
            "companionProcess": {
                "status": "missingFixtureOptOut",
                "path": f"C:/fixtures/run-{trial}.process.json",
                "sha256": None,
                "fixtureOptOut": True,
                "executableIdentityAvailable": False,
            },
        }

    def test_rejects_same_provenance_label_with_different_modes(self) -> None:
        runs = [self._run("off", 1), self._run("both", 2)]
        with self.assertRaisesRegex(SUMMARY.SummaryError, "mixes native presentation"):
            SUMMARY._aggregate(runs, 60, [])

    def test_rejects_legacy_and_attested_runs_in_one_group(self) -> None:
        runs = [self._run(None, 1), self._run("off", 2)]
        with self.assertRaisesRegex(SUMMARY.SummaryError, "legacy/attested"):
            SUMMARY._aggregate(runs, 60, [])

    def test_rejects_world_attested_and_historical_mode_in_one_group(self) -> None:
        runs = [
            self._run("both", 1),
            self._run("both", 2, world_attested=True),
        ]
        with self.assertRaisesRegex(SUMMARY.SummaryError, "mixes native presentation"):
            SUMMARY._aggregate(runs, 60, [])

    def test_emits_group_and_per_run_mode_activity(self) -> None:
        report = SUMMARY._aggregate(
            [self._run("both", 1), self._run("both", 2)], 60, []
        )
        group = report["groups"][0]
        self.assertEqual("both", group["nativePresentation"]["requestedMode"])
        self.assertEqual(2, len(group["nativePresentation"]["activityPerRun"]))
        self.assertEqual(
            "both", group["runs"][0]["nativePresentation"]["requestedMode"]
        )
        markdown = SUMMARY._markdown(report)
        self.assertIn("Native presentation: `both`", markdown)
        self.assertIn("cape active max 150", markdown)


class MarkdownRegressionTests(unittest.TestCase):
    @staticmethod
    def _metric(value: float | None) -> dict:
        per_run = [] if value is None else [{
            "runId": "synthetic-run",
            "trial": 1,
            "value": {"mean": value, "p95": value, "p99": value, "max": value},
        }]
        return {"medianOfRunMeans": value, "perRun": per_run}

    def test_ambiguous_feature_cells_stay_out_of_scaling_projection(self) -> None:
        cells = []
        for feature, value in (("full", 10.0), ("no_cape", 8.0)):
            cells.append({
                "id": f"features-300-{feature}",
                "count": 300,
                "activity": "third_active",
                "metrics": {
                    "wallMilliseconds": self._metric(value),
                    "worldRenderCpuMilliseconds": self._metric(None),
                    "worldRenderGpuMilliseconds": self._metric(None),
                    "drawCalls": self._metric(None),
                },
            })
        report = {
            "minimumFrameRequirement": 60,
            "groups": [{
                "backend": "gdscript",
                "renderer": "dummy",
                "display": "headless",
                "headless": True,
                "commit": "0123456789abcdef",
                "sourceHash": "source-hash",
                "runCount": 1,
                "driver": {"productionFaithful": True, "version": SUMMARY.DRIVER_VERSION},
                "caveats": [],
                "interferenceLabels": [],
                "cells": cells,
            }],
            "inputs": {
                "files": [],
                "companionProcessMetadata": {"files": [], "fixtureOptOuts": []},
            },
        }

        markdown = SUMMARY._markdown(report)

        self.assertNotIn("### Scaling:", markdown)
        self.assertIn("`features-300-full`", markdown)
        self.assertIn("`features-300-no_cape`", markdown)


if __name__ == "__main__":
    unittest.main()
