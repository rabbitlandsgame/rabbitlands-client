#!/usr/bin/env python3
"""Validate and summarize Eloria crowd benchmark JSON reports.

The summary deliberately keeps frame percentiles attached to their source run.
Only per-run means are combined across trials, using their median.  This avoids
presenting a percentile computed from samples produced by different processes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable


SUMMARY_METRICS = (
    "wallMilliseconds",
    "presentMilliseconds",
    "groundMilliseconds",
    "overheadMilliseconds",
    "animationGateMilliseconds",
    "syncWorldMilliseconds",
    "packetDispatchInclusiveMilliseconds",
    "commandOnlyReduceMilliseconds",
    "rootRenderCpuMilliseconds",
    "rootRenderGpuMilliseconds",
    "worldRenderCpuMilliseconds",
    "worldRenderGpuMilliseconds",
    "drawCalls",
    "primitives",
    "sceneNodes",
    "resourceObjects",
    "transientWorldEffects",
)

PACKET_METRICS = (
    "wallMilliseconds",
    "presentMilliseconds",
    "groundMilliseconds",
    "syncWorldMilliseconds",
    "packetDispatchInclusiveMilliseconds",
    "commandOnlyReduceMilliseconds",
)

HEADLESS_UNAVAILABLE_METRICS = (
    "rootRenderCpuMilliseconds",
    "rootRenderGpuMilliseconds",
    "worldRenderCpuMilliseconds",
    "worldRenderGpuMilliseconds",
    "drawCalls",
    "primitives",
)

ACTIVITY_COLUMNS = (
    ("idle", "Idle"),
    ("third_active", "Third active"),
    ("all_move", "Move"),
    ("all_combat", "Combat"),
)

SCALING_COUNTS = (100, 200, 300, 500)

DRIVER_VERSION = "deferred-coalesced-role-faithful-v2"
DRIVER_ROLE_CYCLE = ["caster_effect", "ranged_animation", "melee_primary", "melee_primary"]
DRIVER_PRESENTATION_COALESCING = "timed AppState dirty signals consumed by Main deferred sync"
DRIVER_ACTUAL_FLUSH_METRIC = "benchmark Main sync_world_inclusive calls per measured frame"
DRIVER_FLUSH_SOURCE = "frame_calls.sync_world_inclusive"
STAT_FIELDS = ("mean", "p50", "p95", "p99", "max")
SERIALIZED_STAT_TOLERANCE = 5e-7


class SummaryError(ValueError):
    """Raised when an input is not a trustworthy completed benchmark run."""


def _is_process_metadata(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".process.json") or name in {
        "process.json",
        "process-metadata.json",
        "process_metadata.json",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SummaryError(f"{context} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise SummaryError(f"{context} must be finite")
    return number


def _required_text(mapping: dict[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SummaryError(f"{context}.{key} must be a non-empty string")
    return value


def _required_dict(mapping: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = mapping.get(key)
    if not isinstance(value, dict):
        raise SummaryError(f"{context}.{key} must be an object")
    return value


def _required_int(mapping: dict[str, Any], key: str, context: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SummaryError(f"{context}.{key} must be an integer")
    return value


def _required_bool(mapping: dict[str, Any], key: str, context: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise SummaryError(f"{context}.{key} must be a boolean")
    return value


def _validate_acceptance_attribution(measurement: dict[str, Any], context: str) -> None:
    """Keep observer-instrumented diagnostics out of acceptance aggregates."""
    attribution = measurement.get("attribution")
    if attribution is None:
        # Historical reports predate the explicit attribution attestation.
        return
    if not isinstance(attribution, dict):
        raise SummaryError(f"{context}.attribution must be an object")
    enabled = _required_bool(attribution, "enabled", f"{context}.attribution")
    comparable = _required_bool(
        attribution, "acceptanceTimingComparable", f"{context}.attribution"
    )
    if comparable == enabled:
        raise SummaryError(
            f"{context}: attribution and acceptance-comparable flags disagree"
        )
    if enabled:
        raise SummaryError(
            f"{context}: attribution diagnostics include observer/timer overhead "
            "and cannot enter acceptance timing summaries"
        )


def _validate_acceptance_eligibility(
    measurement: dict[str, Any], planned: list[Any], context: str
) -> None:
    """Reject benchmark-only feature probes from acceptance aggregates."""
    if "engineProfileMarkersEnabled" in measurement and _required_bool(
        measurement, "engineProfileMarkersEnabled", context
    ):
        raise SummaryError(
            f"{context}: external engine profiling is diagnostic and cannot "
            "enter acceptance timing summaries"
        )
    diagnostic_features = {
        str(spec.get("features", ""))
        for spec in planned
        if isinstance(spec, dict)
        and str(spec.get("features", "")) == "cape_solver_off"
    }
    acceptance = measurement.get("acceptance")
    if acceptance is None:
        if diagnostic_features:
            raise SummaryError(
                f"{context}: cape_solver_off requires explicit diagnostic-only metadata"
            )
        # Historical reports predate the acceptance eligibility attestation.
        return
    if not isinstance(acceptance, dict):
        raise SummaryError(f"{context}.acceptance must be an object")
    eligible = _required_bool(acceptance, "eligible", f"{context}.acceptance")
    diagnostic_only = _required_bool(
        acceptance, "diagnosticOnly", f"{context}.acceptance"
    )
    _required_text(acceptance, "reason", f"{context}.acceptance")
    if eligible == diagnostic_only:
        raise SummaryError(
            f"{context}: acceptance eligibility and diagnostic-only flags disagree"
        )
    if diagnostic_features:
        if eligible or not diagnostic_only:
            raise SummaryError(
                f"{context}: cape_solver_off is not marked diagnostic-only"
            )
        raise SummaryError(
            f"{context}: cape_solver_off is a diagnostic intervention and cannot "
            "enter acceptance timing summaries"
        )
    if not eligible:
        raise SummaryError(
            f"{context}: diagnostic-only measurements cannot enter acceptance timing summaries"
        )


def _nonnegative_counter(mapping: dict[str, Any], key: str, context: str) -> int:
    value = _required_int(mapping, key, context)
    if value < 0:
        raise SummaryError(f"{context}.{key} must be nonnegative")
    return value


def _validate_native_presentation(
    value: Any, cells: list[Any], context: str
) -> dict[str, Any] | None:
    """Attest requested native presentation components and measured execution."""
    if value is None:
        # Historical reports predate the independent presentation selector.
        return None
    if not isinstance(value, dict):
        raise SummaryError(f"{context}.nativePresentation must be an object")
    mode = _required_text(value, "requestedMode", f"{context}.nativePresentation")
    environments = {
        "off": "0", "cape": "cape", "flight": "flight", "both": "both",
        "world": "world", "all": "all",
    }
    if mode not in environments:
        raise SummaryError(f"{context}.nativePresentation.requestedMode is unsupported")
    environment = _required_text(
        value, "environmentValue", f"{context}.nativePresentation"
    )
    if environment != environments[mode]:
        raise SummaryError(f"{context}.nativePresentation environment/mode mismatch")
    if not _required_bool(
        value, "reducerIndependent", f"{context}.nativePresentation"
    ):
        raise SummaryError(f"{context}.nativePresentation.reducerIndependent must be true")

    base_aggregate_keys = (
        "capeModifierInstancesMaximum", "capeStatsSupportedInstancesMaximum",
        "capeActiveInstancesMaximum", "capeNativeBackendInstancesMaximum",
        "capeGdscriptBackendInstancesMaximum", "capeNativeCalls",
        "capeFallbackCalls", "flightInstancesMaximum",
        "flightActiveInstancesMaximum", "flightBuildAttempts",
        "flightBuildSuccesses", "flightBuildFallbacks",
    )
    actual = _required_dict(value, "actual", f"{context}.nativePresentation")
    world_aggregate_keys = (
        "worldInstancesMaximum", "worldActiveInstancesMaximum",
        "worldBuildAttempts", "worldBuildSuccesses", "worldBuildFallbacks",
    )
    world_actual_fields = ("worldStatsSupported", *world_aggregate_keys)
    world_field_presence = [key in actual for key in world_actual_fields]
    if any(world_field_presence) and not all(world_field_presence):
        raise SummaryError(
            f"{context}.nativePresentation.actual has a partial world attestation"
        )
    world_attested = all(world_field_presence)
    if mode in {"world", "all"} and not world_attested:
        raise SummaryError(
            f"{context}.nativePresentation requested {mode} without world attestation"
        )
    if world_attested and not isinstance(actual["worldStatsSupported"], bool):
        raise SummaryError(
            f"{context}.nativePresentation.actual.worldStatsSupported must be boolean"
        )
    aggregate_keys = base_aggregate_keys + (
        world_aggregate_keys if world_attested else ()
    )
    checked = {
        key: _nonnegative_counter(actual, key, f"{context}.nativePresentation.actual")
        for key in aggregate_keys
    }
    match_keys = ["capeMatchedRequest", "flightMatchedRequest", "matchedRequest"]
    if world_attested:
        match_keys.append("worldMatchedRequest")
    for key in match_keys:
        if not _required_bool(actual, key, f"{context}.nativePresentation.actual"):
            raise SummaryError(f"{context}.nativePresentation.actual.{key} must be true")

    observed = {key: 0 for key in aggregate_keys}
    observed_world_stats_supported = False
    cape_snapshot_keys = (
        "modifierInstances", "statsSupportedInstances", "activeInstances",
        "nativeBackendInstances", "gdscriptBackendInstances", "nativeCalls",
        "fallbackCalls",
    )
    flight_snapshot_keys = (
        "instances", "activeInstances", "buildAttempts", "buildSuccesses",
        "buildFallbacks",
    )
    base_delta_keys = (
        "capeNativeCalls", "capeFallbackCalls", "flightBuildAttempts",
        "flightBuildSuccesses", "flightBuildFallbacks",
    )
    world_delta_keys = (
        "worldBuildAttempts", "worldBuildSuccesses", "worldBuildFallbacks",
    )
    delta_keys = base_delta_keys + (world_delta_keys if world_attested else ())
    for index, cell in enumerate(cells):
        cell_context = f"{context}.cells[{index}].nativePresentation"
        if not isinstance(cell, dict):
            raise SummaryError(f"{cell_context} parent must be an object")
        attestation = _required_dict(cell, "nativePresentation", cell_context)
        if _required_text(attestation, "requestedMode", cell_context) != mode:
            raise SummaryError(f"{cell_context}.requestedMode changed within run")
        delta = _required_dict(attestation, "delta", cell_context)
        reported_delta = {
            key: _nonnegative_counter(delta, key, f"{cell_context}.delta")
            for key in delta_keys
        }
        snapshots: dict[
            str, tuple[dict[str, int], dict[str, int], dict[str, int]]
        ] = {}
        for phase in ("beforeSample", "afterSample"):
            snapshot = _required_dict(attestation, phase, cell_context)
            cape = _required_dict(snapshot, "cape", f"{cell_context}.{phase}")
            flight = _required_dict(snapshot, "flight", f"{cell_context}.{phase}")
            cape_values = {
                key: _nonnegative_counter(cape, key, f"{cell_context}.{phase}.cape")
                for key in cape_snapshot_keys
            }
            flight_values = {
                key: _nonnegative_counter(flight, key, f"{cell_context}.{phase}.flight")
                for key in flight_snapshot_keys
            }
            if not isinstance(flight.get("statsSupported"), bool):
                raise SummaryError(
                    f"{cell_context}.{phase}.flight.statsSupported must be boolean"
                )
            world_values: dict[str, int] = {}
            if world_attested:
                world = _required_dict(snapshot, "world", f"{cell_context}.{phase}")
                if not isinstance(world.get("statsSupported"), bool):
                    raise SummaryError(
                        f"{cell_context}.{phase}.world.statsSupported must be boolean"
                    )
                observed_world_stats_supported = (
                    observed_world_stats_supported or world["statsSupported"]
                )
                world_values = {
                    key: _nonnegative_counter(
                        world, key, f"{cell_context}.{phase}.world"
                    )
                    for key in (
                        "instances", "activeInstances", "buildAttempts",
                        "buildSuccesses", "buildFallbacks",
                    )
                }
            elif "world" in snapshot:
                raise SummaryError(
                    f"{cell_context}.{phase}.world is present without top-level attestation"
                )
            snapshots[phase] = (cape_values, flight_values, world_values)
            observed["capeModifierInstancesMaximum"] = max(
                observed["capeModifierInstancesMaximum"], cape_values["modifierInstances"]
            )
            observed["capeStatsSupportedInstancesMaximum"] = max(
                observed["capeStatsSupportedInstancesMaximum"],
                cape_values["statsSupportedInstances"],
            )
            observed["capeActiveInstancesMaximum"] = max(
                observed["capeActiveInstancesMaximum"], cape_values["activeInstances"]
            )
            observed["capeNativeBackendInstancesMaximum"] = max(
                observed["capeNativeBackendInstancesMaximum"],
                cape_values["nativeBackendInstances"],
            )
            observed["capeGdscriptBackendInstancesMaximum"] = max(
                observed["capeGdscriptBackendInstancesMaximum"],
                cape_values["gdscriptBackendInstances"],
            )
            observed["flightInstancesMaximum"] = max(
                observed["flightInstancesMaximum"], flight_values["instances"]
            )
            observed["flightActiveInstancesMaximum"] = max(
                observed["flightActiveInstancesMaximum"], flight_values["activeInstances"]
            )
            if world_attested:
                observed["worldInstancesMaximum"] = max(
                    observed["worldInstancesMaximum"], world_values["instances"]
                )
                observed["worldActiveInstancesMaximum"] = max(
                    observed["worldActiveInstancesMaximum"],
                    world_values["activeInstances"],
                )
        cape_before, flight_before, world_before = snapshots["beforeSample"]
        cape_after, flight_after, world_after = snapshots["afterSample"]
        expected_delta = {
            "capeNativeCalls": cape_after["nativeCalls"] - cape_before["nativeCalls"],
            "capeFallbackCalls": cape_after["fallbackCalls"] - cape_before["fallbackCalls"],
            "flightBuildAttempts": (
                flight_after["buildAttempts"] - flight_before["buildAttempts"]
            ),
            "flightBuildSuccesses": (
                flight_after["buildSuccesses"] - flight_before["buildSuccesses"]
            ),
            "flightBuildFallbacks": (
                flight_after["buildFallbacks"] - flight_before["buildFallbacks"]
            ),
        }
        if world_attested:
            expected_delta.update({
                "worldBuildAttempts": (
                    world_after["buildAttempts"] - world_before["buildAttempts"]
                ),
                "worldBuildSuccesses": (
                    world_after["buildSuccesses"] - world_before["buildSuccesses"]
                ),
                "worldBuildFallbacks": (
                    world_after["buildFallbacks"] - world_before["buildFallbacks"]
                ),
            })
        if any(value < 0 for value in expected_delta.values()):
            raise SummaryError(f"{cell_context} native counters decreased during sampling")
        if reported_delta != expected_delta:
            raise SummaryError(
                f"{cell_context}.delta does not equal afterSample minus beforeSample"
            )
        for key in delta_keys:
            observed[key] += reported_delta[key]
    if checked != observed:
        raise SummaryError(
            f"{context}.nativePresentation.actual does not match per-cell attestations"
        )
    if world_attested and actual["worldStatsSupported"] != observed_world_stats_supported:
        raise SummaryError(
            f"{context}.nativePresentation.actual.worldStatsSupported does not "
            "match per-cell snapshots"
        )

    wants_cape = mode in {"cape", "both", "all"}
    wants_flight = mode in {"flight", "both", "all"}
    wants_world = mode in {"world", "all"}
    cape_active = (
        checked["capeActiveInstancesMaximum"] > 0
        and checked["capeNativeBackendInstancesMaximum"] > 0
        and checked["capeNativeCalls"] > 0
        and checked["capeFallbackCalls"] == 0
    )
    flight_active = (
        checked["flightActiveInstancesMaximum"] > 0
        and checked["flightBuildAttempts"] > 0
        and checked["flightBuildSuccesses"] == checked["flightBuildAttempts"]
        and checked["flightBuildFallbacks"] == 0
    )
    cape_inactive = (
        checked["capeActiveInstancesMaximum"] == 0
        and checked["capeNativeBackendInstancesMaximum"] == 0
        and checked["capeNativeCalls"] == 0
        and checked["capeFallbackCalls"] == 0
    )
    flight_inactive = (
        checked["flightActiveInstancesMaximum"] == 0
        and checked["flightBuildAttempts"] == 0
        and checked["flightBuildSuccesses"] == 0
        and checked["flightBuildFallbacks"] == 0
    )
    cape_matches = cape_active if wants_cape else cape_inactive
    flight_matches = flight_active if wants_flight else flight_inactive
    if not cape_matches or not flight_matches:
        raise SummaryError(
            f"{context}.nativePresentation actual activity does not match requested mode"
        )
    world_matches = True
    if world_attested:
        world_active = (
            actual["worldStatsSupported"]
            and checked["worldActiveInstancesMaximum"] > 0
            and checked["worldBuildAttempts"] > 0
            and checked["worldBuildSuccesses"] == checked["worldBuildAttempts"]
            and checked["worldBuildFallbacks"] == 0
        )
        world_inactive = (
            checked["worldActiveInstancesMaximum"] == 0
            and checked["worldBuildAttempts"] == 0
            and checked["worldBuildSuccesses"] == 0
            and checked["worldBuildFallbacks"] == 0
        )
        world_matches = world_active if wants_world else world_inactive
    if not world_matches:
        raise SummaryError(
            f"{context}.nativePresentation world activity does not match requested mode"
        )
    checked_actual = dict(checked)
    if world_attested:
        checked_actual["worldStatsSupported"] = actual["worldStatsSupported"]
    return {
        "attestation": "attested",
        "worldAttested": world_attested,
        "requestedMode": mode,
        "environmentValue": environment,
        "requestedComponents": {
            "cape": wants_cape, "flight": wants_flight, "world": wants_world,
        },
        "actual": checked_actual,
    }


def _validate_report_process(
    value: Any, native_presentation: dict[str, Any] | None, context: str
) -> dict[str, Any] | None:
    """Validate report-side launch limits and the serialized runner request."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SummaryError(f"{context}.process must be an object")

    checked: dict[str, Any] = {}
    if "pid" in value:
        pid = _required_int(value, "pid", f"{context}.process")
        if pid <= 0:
            raise SummaryError(f"{context}.process.pid must be positive")
        checked["pid"] = pid
    if "requestedAffinityMask" in value:
        affinity = _required_int(value, "requestedAffinityMask", f"{context}.process")
        if affinity <= 0:
            raise SummaryError(
                f"{context}.process.requestedAffinityMask must be positive"
            )
        checked["requestedAffinityMask"] = affinity
    if "requestedWorkerThreads" in value:
        workers = _required_int(value, "requestedWorkerThreads", f"{context}.process")
        if workers <= 0:
            raise SummaryError(
                f"{context}.process.requestedWorkerThreads must be positive"
            )
        checked["requestedWorkerThreads"] = workers

    runner_metadata = value.get("runnerMetadata")
    if runner_metadata is not None:
        if not isinstance(runner_metadata, str) or not runner_metadata:
            raise SummaryError(f"{context}.process.runnerMetadata must be JSON text")
        try:
            runner = json.loads(runner_metadata)
        except json.JSONDecodeError as error:
            raise SummaryError(
                f"{context}.process.runnerMetadata is not valid JSON: {error}"
            ) from error
        if not isinstance(runner, dict):
            raise SummaryError(f"{context}.process.runnerMetadata must decode to an object")
        for key in ("affinityMask", "requestedWorkerThreads"):
            report_key = (
                "requestedAffinityMask" if key == "affinityMask" else key
            )
            if key in runner and report_key in checked:
                if runner[key] != checked[report_key]:
                    raise SummaryError(
                        f"{context}.process.runnerMetadata.{key} does not match "
                        f"process.{report_key}"
                    )
        if native_presentation is not None:
            expected_mode = native_presentation["requestedMode"]
            expected_environment = native_presentation["environmentValue"]
            requested_mode = runner.get("requestedNativePresentation")
            if not isinstance(requested_mode, str) or requested_mode.lower() != expected_mode:
                raise SummaryError(
                    f"{context}.process.runnerMetadata.requestedNativePresentation "
                    "does not match report native presentation mode"
                )
            if runner.get("nativePresentationEnvironment") != expected_environment:
                raise SummaryError(
                    f"{context}.process.runnerMetadata.nativePresentationEnvironment "
                    "does not match report native presentation environment"
                )
        checked["runnerMetadata"] = runner
    return checked


def _expected_active_count(count: int, activity: str, context: str) -> int:
    if activity == "idle":
        return 0
    if activity == "move25":
        return count // 4
    if activity in {"third_active", "sync_burst", "asynchronous"}:
        return count // 3
    if activity in {"all_move", "all_combat"}:
        return count
    raise SummaryError(f"{context}.activity has unsupported value {activity!r}")


def _expected_visible_count(count: int, visibility: str, context: str) -> int:
    if visibility == "lod_bands":
        if count != 300:
            raise SummaryError(f"{context}.visibility lod_bands requires exactly 300 actors")
        return 200
    if visibility in {"half300", "frustum_half", "range_bands"}:
        return count // 2
    if visibility in {"concentrated", "zoom"}:
        return count
    raise SummaryError(f"{context}.visibility has unsupported value {visibility!r}")


def _validate_lod_fixture(fixture: dict[str, Any], count: int, context: str) -> None:
    if count != 300:
        raise SummaryError(f"{context} requires exactly 300 actors")
    before = _required_dict(fixture, "before", context)
    expected_maps = {
        "distanceBands": {"near0To45": 100, "mid45To80": 100, "beyond80": 100},
        "animationTiers": {"full": 100, "half": 100, "paused": 100},
    }
    for key, expected in expected_maps.items():
        raw = _required_dict(before, key, f"{context}.before")
        if set(raw) != set(expected):
            raise SummaryError(
                f"{context}.before.{key} keys are {sorted(raw)}; expected {sorted(expected)}"
            )
        actual = {
            name: _required_int(raw, name, f"{context}.before.{key}") for name in expected
        }
        if actual != expected:
            raise SummaryError(
                f"{context}.before.{key} is {actual}; expected {expected}"
            )
    for key in ("frustumAndDrawVisible", "frustumIntersecting", "withinDrawDistance"):
        actual = _required_int(before, key, f"{context}.before")
        if actual != 200:
            raise SummaryError(f"{context}.before.{key} is {actual}; expected 200")

    camera = _required_dict(fixture, "camera", context)
    expected_camera = {
        "distance": 32.0,
        "pitchDegrees": -25.0,
        "yawDegrees": 0.0,
        "fieldOfViewDegrees": 50.0,
    }
    for key, expected in expected_camera.items():
        actual = _finite_number(camera.get(key), f"{context}.camera.{key}")
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=SERIALIZED_STAT_TOLERANCE):
            raise SummaryError(f"{context}.camera.{key} is {actual}; expected {expected}")

    visibility = _required_dict(fixture, "visibilityValidation", context)
    for key in ("min", "max"):
        actual = _required_int(visibility, key, f"{context}.visibilityValidation")
        if actual != 200:
            raise SummaryError(
                f"{context}.visibilityValidation.{key} is {actual}; expected 200"
            )
    grounding = _required_dict(fixture, "grounding", context)
    expected_grounding = {"surfaceHits": 300, "surfaceMatches": 300, "surfaceMisses": 0}
    for key, expected in expected_grounding.items():
        actual = _required_int(grounding, key, f"{context}.grounding")
        if actual != expected:
            raise SummaryError(f"{context}.grounding.{key} is {actual}; expected {expected}")


def _validate_driver(data: dict[str, Any], context: str, allow_legacy: bool) -> dict[str, Any]:
    raw = data.get("driver")
    if raw is None:
        if not allow_legacy:
            raise SummaryError(
                f"{context}.driver is missing; this historical forced-presentation report is "
                "superseded. Use --allow-legacy-forced-presentation only for explicit historical review"
            )
        return {
            "status": "legacyForcedPresentationOptIn",
            "version": None,
            "productionFaithful": False,
            "caveat": (
                "Historical driver manually consumed dirty actors and forced presentation; "
                "it does not attest Main's deferred coalescing path."
            ),
        }
    if not isinstance(raw, dict):
        raise SummaryError(f"{context}.driver must be an object")
    if raw.get("version") != DRIVER_VERSION:
        raise SummaryError(
            f"{context}.driver.version is {raw.get('version')!r}; expected {DRIVER_VERSION!r}"
        )
    if raw.get("presentationCoalescing") != DRIVER_PRESENTATION_COALESCING:
        raise SummaryError(f"{context}.driver.presentationCoalescing is not the deferred Main path")
    if _required_bool(raw, "manualPresentationFlushes", f"{context}.driver"):
        raise SummaryError(f"{context}.driver.manualPresentationFlushes must be false")
    if raw.get("actualFlushMetric") != DRIVER_ACTUAL_FLUSH_METRIC:
        raise SummaryError(f"{context}.driver.actualFlushMetric is unsupported")
    if raw.get("roleCycle") != DRIVER_ROLE_CYCLE:
        raise SummaryError(f"{context}.driver.roleCycle does not match the role-faithful cycle")
    if _required_int(raw, "combatCadenceMultiplier", f"{context}.driver") != 4:
        raise SummaryError(f"{context}.driver.combatCadenceMultiplier must be 4")
    return {
        "status": "validated",
        "version": DRIVER_VERSION,
        "productionFaithful": True,
        "presentationCoalescing": raw["presentationCoalescing"],
        "manualPresentationFlushes": raw["manualPresentationFlushes"],
        "actualFlushMetric": raw["actualFlushMetric"],
        "roleCycle": raw["roleCycle"],
        "combatCadenceMultiplier": raw["combatCadenceMultiplier"],
    }


def _validate_stat(value: Any, context: str, maximum_samples: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SummaryError(f"{context} must be null or an object")
    samples = value.get("samples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
        raise SummaryError(f"{context}.samples must be a positive integer")
    if samples > maximum_samples:
        raise SummaryError(
            f"{context}.samples ({samples}) exceeds the cell frame count ({maximum_samples})"
        )
    checked: dict[str, Any] = {"samples": samples}
    for key in STAT_FIELDS:
        checked[key] = _finite_number(value.get(key), f"{context}.{key}")
    if not (checked["p50"] <= checked["p95"] <= checked["p99"] <= checked["max"]):
        raise SummaryError(f"{context} percentile exceeds max")
    return checked


def _validate_summary(
    summary: Any,
    context: str,
    frames: int,
    required_metrics: Iterable[str],
) -> dict[str, dict[str, Any] | None]:
    if not isinstance(summary, dict):
        raise SummaryError(f"{context} must be an object")
    result: dict[str, dict[str, Any] | None] = {}
    for metric in set(summary).union(required_metrics):
        result[metric] = _validate_stat(summary.get(metric), f"{context}.{metric}", frames)
    return result


def _integer_series(value: Any, context: str, frames: int) -> list[int]:
    if not isinstance(value, list) or len(value) != frames:
        raise SummaryError(f"{context} length must equal frames")
    result: list[int] = []
    for index, item in enumerate(value):
        number = _finite_number(item, f"{context}[{index}]")
        if number < 0 or not number.is_integer():
            raise SummaryError(f"{context}[{index}] must be a non-negative integer")
        result.append(int(number))
    return result


def _harness_round(value: float) -> float:
    # Mirrors snappedf(value, 0.001) for the benchmark's non-negative samples.
    return math.floor(value / 0.001 + 0.5) * 0.001


def _raw_series(value: Any, context: str, frames: int) -> list[float | None]:
    if not isinstance(value, list) or len(value) != frames:
        raise SummaryError(f"{context} length must equal frames")
    checked: list[float | None] = []
    for index, item in enumerate(value):
        checked.append(None if item is None else _finite_number(item, f"{context}[{index}]"))
    return checked


def _harness_distribution(values: Iterable[float | None]) -> dict[str, float | int] | None:
    usable = sorted(value for value in values if value is not None)
    if not usable:
        return None
    total = 0.0
    for value in usable:
        total += value

    def percentile(fraction: float) -> float:
        index = min(max(math.ceil(fraction * len(usable)) - 1, 0), len(usable) - 1)
        return _harness_round(usable[index])

    return {
        "samples": len(usable),
        "mean": _harness_round(total / len(usable)),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "max": _harness_round(usable[-1]),
    }


def _require_distribution_match(
    actual: dict[str, Any] | None,
    expected: dict[str, float | int] | None,
    context: str,
) -> None:
    if expected is None:
        if actual is not None:
            raise SummaryError(f"{context} must be null because every raw sample is null")
        return
    if actual is None:
        raise SummaryError(f"{context} is null despite available raw samples")
    if actual["samples"] != expected["samples"]:
        raise SummaryError(
            f"{context}.samples is {actual['samples']}; raw samples produce {expected['samples']}"
        )
    for key in STAT_FIELDS:
        if not math.isclose(
            actual[key], float(expected[key]), rel_tol=1e-12, abs_tol=SERIALIZED_STAT_TOLERANCE
        ):
            raise SummaryError(
                f"{context}.{key} is {actual[key]}; raw samples produce {expected[key]}"
            )


def _validate_raw_distributions(
    raw_value: Any,
    summary_value: Any,
    summary: dict[str, dict[str, Any] | None],
    packet_summary_value: Any,
    packet_summary: dict[str, dict[str, Any] | None],
    frames: int,
    context: str,
) -> dict[str, list[float | None]]:
    if not isinstance(raw_value, dict):
        raise SummaryError(f"{context}.raw must be an object")
    if not isinstance(summary_value, dict):
        raise SummaryError(f"{context}.summary must be an object")
    if set(summary_value) != set(raw_value):
        raise SummaryError(f"{context}.summary keys must exactly match raw metric keys")

    raw: dict[str, list[float | None]] = {}
    for metric, values in raw_value.items():
        if not isinstance(metric, str) or not metric:
            raise SummaryError(f"{context}.raw metric names must be non-empty strings")
        raw[metric] = _raw_series(values, f"{context}.raw.{metric}", frames)
        _require_distribution_match(
            summary.get(metric),
            _harness_distribution(raw[metric]),
            f"{context}.summary.{metric}",
        )

    if not isinstance(packet_summary_value, dict):
        raise SummaryError(f"{context}.packetBearingSummary must be an object")
    if set(packet_summary_value) != set(PACKET_METRICS):
        raise SummaryError(
            f"{context}.packetBearingSummary keys must exactly match packet-bearing metrics"
        )
    packets = raw.get("packetsPerFrame")
    if packets is None or any(value is None for value in packets):
        raise SummaryError(f"{context}.raw.packetsPerFrame must contain a value for every frame")
    for metric in PACKET_METRICS:
        values = raw.get(metric)
        if values is None:
            raise SummaryError(f"{context}.raw.{metric} is required for packet-bearing validation")
        selected = [values[index] for index, count in enumerate(packets) if int(count) > 0]
        _require_distribution_match(
            packet_summary.get(metric),
            _harness_distribution(selected),
            f"{context}.packetBearingSummary.{metric}",
        )
    return raw


def _validate_driver_attestation(
    sample: dict[str, Any],
    summary: dict[str, dict[str, Any] | None],
    raw: dict[str, Any],
    frames: int,
    network: str,
    fighting: int,
    context: str,
) -> dict[str, Any]:
    cadence = _required_int(sample, "driverCadenceMilliseconds", context)
    combat_cadence = _required_int(sample, "combatCadenceMilliseconds", context)
    if cadence < 1:
        raise SummaryError(f"{context}.driverCadenceMilliseconds must be positive")
    expected_combat_cadence = cadence * (40 if network == "asynchronous" else 4)
    if combat_cadence != expected_combat_cadence:
        raise SummaryError(
            f"{context}.combatCadenceMilliseconds is {combat_cadence}; "
            f"expected {expected_combat_cadence}"
        )

    flushes = _integer_series(raw.get("flushesPerFrame"), f"{context}.raw.flushesPerFrame", frames)
    commands = _integer_series(raw.get("commandsPerFrame"), f"{context}.raw.commandsPerFrame", frames)
    actual_flushes = sum(flushes)
    maximum_flushes = max(flushes, default=0)
    if maximum_flushes > 1:
        raise SummaryError(
            f"{context}.raw.flushesPerFrame has maximum {maximum_flushes}; expected at most 1"
        )
    flush_summary = summary.get("flushesPerFrame")
    if flush_summary is None or flush_summary["samples"] != frames:
        raise SummaryError(f"{context}.summary.flushesPerFrame must cover every frame")
    if flush_summary["max"] != float(maximum_flushes):
        raise SummaryError(f"{context}.summary.flushesPerFrame.max does not match raw samples")

    calls = _required_dict(sample, "calls", context)
    call_count = calls.get("sync_world_inclusive", 0)
    if isinstance(call_count, bool) or not isinstance(call_count, int) or call_count < 0:
        raise SummaryError(f"{context}.calls.sync_world_inclusive must be a non-negative integer")
    if call_count != actual_flushes:
        raise SummaryError(
            f"{context}.calls.sync_world_inclusive is {call_count}; "
            f"raw flush total is {actual_flushes}"
        )

    attestation = _required_dict(sample, "driverAttestation", context)
    if attestation.get("version") != DRIVER_VERSION:
        raise SummaryError(f"{context}.driverAttestation.version is unsupported")
    if _required_bool(attestation, "manualPresentationFlushes", f"{context}.driverAttestation"):
        raise SummaryError(f"{context}.driverAttestation.manualPresentationFlushes must be false")
    if attestation.get("flushMetricSource") != DRIVER_FLUSH_SOURCE:
        raise SummaryError(f"{context}.driverAttestation.flushMetricSource is unsupported")
    if _required_int(attestation, "actualFlushes", f"{context}.driverAttestation") != actual_flushes:
        raise SummaryError(f"{context}.driverAttestation.actualFlushes does not match raw samples")
    if _required_int(
        attestation, "maximumFlushesPerFrame", f"{context}.driverAttestation"
    ) != maximum_flushes:
        raise SummaryError(
            f"{context}.driverAttestation.maximumFlushesPerFrame does not match raw samples"
        )
    if not _required_bool(attestation, "atMostOneFlushPerFrame", f"{context}.driverAttestation"):
        raise SummaryError(f"{context}.driverAttestation.atMostOneFlushPerFrame must be true")
    dirty_commands = sum(commands) > 0
    if _required_bool(
        attestation, "dirtyCommandsObserved", f"{context}.driverAttestation"
    ) != dirty_commands:
        raise SummaryError(f"{context}.driverAttestation.dirtyCommandsObserved is inconsistent")
    produced_flush = not dirty_commands or actual_flushes > 0
    if _required_bool(
        attestation, "dirtyCommandsProducedFlush", f"{context}.driverAttestation"
    ) != produced_flush or not produced_flush:
        raise SummaryError(f"{context}.driverAttestation.dirtyCommandsProducedFlush is false")
    if attestation.get("roleCycle") != DRIVER_ROLE_CYCLE:
        raise SummaryError(f"{context}.driverAttestation.roleCycle is unsupported")
    role_counts = _required_dict(attestation, "roleCounts", f"{context}.driverAttestation")
    caster = (fighting + 3) // 4
    ranged = (fighting + 2) // 4
    expected_roles = {
        "fighting": fighting,
        "casterEffect": caster,
        "rangedAnimation": ranged,
        "meleePrimary": fighting - caster - ranged,
    }
    if role_counts != expected_roles:
        raise SummaryError(
            f"{context}.driverAttestation.roleCounts is {role_counts}; expected {expected_roles}"
        )
    if not _required_bool(
        attestation, "meleeRolesReceiveCommand46", f"{context}.driverAttestation"
    ):
        raise SummaryError(f"{context}.driverAttestation.meleeRolesReceiveCommand46 must be true")
    if not _required_bool(
        attestation,
        "casterAndRangedRolesReceiveVisualEventsOnly",
        f"{context}.driverAttestation",
    ):
        raise SummaryError(
            f"{context}.driverAttestation.casterAndRangedRolesReceiveVisualEventsOnly must be true"
        )

    overload = _required_dict(sample, "overloadAbort", context)
    if _required_bool(overload, "aborted", f"{context}.overloadAbort"):
        raise SummaryError(f"{context}.overloadAbort.aborted is true")
    if overload.get("reason") is not None:
        raise SummaryError(f"{context}.overloadAbort.reason must be null when not aborted")
    if _required_int(overload, "liveWorldEffectLimit", f"{context}.overloadAbort") != 4096:
        raise SummaryError(f"{context}.overloadAbort.liveWorldEffectLimit must be 4096")
    return {
        "status": "validated",
        "driverCadenceMilliseconds": cadence,
        "combatCadenceMilliseconds": combat_cadence,
        "attestation": attestation,
        "overloadAbort": overload,
    }


def _validate_cell(
    cell: Any,
    run_context: str,
    min_frames: int,
    headless: bool,
    driver: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(cell, dict):
        raise SummaryError(f"{run_context}.cells entries must be objects")
    cell_id = _required_text(cell, "id", run_context)
    context = f"{run_context}.cells[{cell_id}]"
    count = cell.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise SummaryError(f"{context}.count must be a positive integer")
    for key in ("activity", "population", "visibility", "features", "network"):
        _required_text(cell, key, context)
    expected_visible = _expected_visible_count(count, cell["visibility"], context)
    expected_active = _expected_active_count(count, cell["activity"], context)
    fixture = _required_dict(cell, "fixture", context)
    for phase in ("before", "after"):
        census = _required_dict(fixture, phase, f"{context}.fixture")
        actual_total = _required_int(census, "total", f"{context}.fixture.{phase}")
        actual_visible = _required_int(
            census, "frustumAndDrawVisible", f"{context}.fixture.{phase}"
        )
        if actual_total != count:
            raise SummaryError(
                f"{context}.fixture.{phase}.total is {actual_total}; expected {count}"
            )
        if actual_visible != expected_visible:
            raise SummaryError(
                f"{context}.fixture.{phase}.frustumAndDrawVisible is {actual_visible}; "
                f"expected {expected_visible}"
            )
    if cell["visibility"] == "lod_bands":
        _validate_lod_fixture(fixture, count, f"{context}.fixture")
    planned_active = _required_int(cell, "plannedActive", context)
    if planned_active != expected_active:
        raise SummaryError(
            f"{context}.plannedActive is {planned_active}; expected {expected_active} "
            f"for activity {cell['activity']!r}"
        )
    planned_workload = _required_dict(cell, "plannedWorkload", context)
    workload_active = _required_int(planned_workload, "active", f"{context}.plannedWorkload")
    workload_moving = _required_int(planned_workload, "moving", f"{context}.plannedWorkload")
    workload_fighting = _required_int(planned_workload, "fighting", f"{context}.plannedWorkload")
    if workload_active != planned_active or workload_moving + workload_fighting != planned_active:
        raise SummaryError(f"{context}.plannedWorkload does not partition plannedActive")
    if cell["activity"] == "all_combat" and (workload_moving != 0 or workload_fighting != planned_active):
        raise SummaryError(f"{context}.plannedWorkload does not match all_combat")
    if cell["activity"] == "third_active" and (
        workload_moving != planned_active // 2
        or workload_fighting != planned_active - planned_active // 2
    ):
        raise SummaryError(f"{context}.plannedWorkload does not match third_active")
    if cell["activity"] not in {"all_combat", "third_active"} and (
        workload_moving != planned_active or workload_fighting != 0
    ):
        raise SummaryError(f"{context}.plannedWorkload does not match {cell['activity']!r}")
    readiness = _required_dict(cell, "resourceReadiness", context)
    if readiness.get("ready") is not True:
        raise SummaryError(f"{context}.resourceReadiness.ready must be true")
    diagnostics = _required_dict(cell, "diagnostics", context)
    memory = _required_dict(cell, "memory", context)
    spawn = _required_dict(cell, "spawn", context)
    despawn_milliseconds = _finite_number(
        cell.get("despawnMilliseconds"), f"{context}.despawnMilliseconds"
    )
    sample = cell.get("sample")
    if not isinstance(sample, dict):
        raise SummaryError(f"{context}.sample must be an object")
    frames = sample.get("frames")
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise SummaryError(f"{context}.sample.frames must be an integer")
    if frames < min_frames:
        raise SummaryError(
            f"{context}.sample.frames is {frames}; minimum required is {min_frames}"
        )

    summary_value = sample.get("summary")
    summary = _validate_summary(
        summary_value, f"{context}.sample.summary", frames, SUMMARY_METRICS
    )
    wall = summary.get("wallMilliseconds")
    if wall is None:
        raise SummaryError(f"{context}.sample.summary.wallMilliseconds is unavailable")
    if wall["samples"] != frames:
        raise SummaryError(
            f"{context}.sample.summary.wallMilliseconds.samples must equal frames"
        )

    packet_summary_value = sample.get("packetBearingSummary", {})
    packet_summary = _validate_summary(
        packet_summary_value,
        f"{context}.sample.packetBearingSummary",
        frames,
        PACKET_METRICS,
    )
    raw = _validate_raw_distributions(
        sample.get("raw"),
        summary_value,
        summary,
        packet_summary_value,
        packet_summary,
        frames,
        f"{context}.sample",
    )

    if headless:
        for metric in HEADLESS_UNAVAILABLE_METRICS:
            if summary.get(metric) is not None:
                raise SummaryError(
                    f"{context}.sample.summary.{metric} must be null for a headless run"
                )

    if driver["productionFaithful"]:
        driver_attestation = _validate_driver_attestation(
            sample,
            summary,
            raw,
            frames,
            cell["network"],
            workload_fighting,
            f"{context}.sample",
        )
    else:
        driver_attestation = {
            "status": "legacyForcedPresentationOptIn",
            "productionFaithful": False,
            "caveat": driver["caveat"],
        }

    rates = sample.get("rates", {})
    if not isinstance(rates, dict):
        raise SummaryError(f"{context}.sample.rates must be an object")
    checked_rates: dict[str, float | None] = {}
    for key, value in rates.items():
        checked_rates[key] = None if value is None else _finite_number(value, f"{context}.sample.rates.{key}")

    return {
        "id": cell_id,
        "count": count,
        "activity": cell["activity"],
        "population": cell["population"],
        "visibility": cell["visibility"],
        "features": cell["features"],
        "network": cell["network"],
        "frames": frames,
        "fixture": fixture,
        "plannedActive": planned_active,
        "plannedWorkload": planned_workload,
        "resourceReadiness": readiness,
        "diagnostics": diagnostics,
        "memory": memory,
        "spawn": spawn,
        "despawnMilliseconds": despawn_milliseconds,
        "driverValidation": driver_attestation,
        "summary": summary,
        "packetBearingSummary": packet_summary,
        "rates": checked_rates,
    }


def _planned_id(spec: Any, context: str) -> str:
    if not isinstance(spec, dict):
        raise SummaryError(f"{context} entries must be objects")
    return _required_text(spec, "id", context)


def _validate_run(
    path: Path, data: Any, min_frames: int, allow_legacy_driver: bool
) -> dict[str, Any]:
    context = str(path)
    if not isinstance(data, dict):
        raise SummaryError(f"{context}: report root must be an object")
    if data.get("schemaVersion") != 1:
        raise SummaryError(f"{context}: unsupported schemaVersion {data.get('schemaVersion')!r}")
    failure_count = data.get("failureCount")
    if isinstance(failure_count, bool) or not isinstance(failure_count, int):
        raise SummaryError(f"{context}: failureCount must be an integer")
    if failure_count != 0:
        raise SummaryError(f"{context}: failureCount is {failure_count}")
    failures = data.get("failures")
    if not isinstance(failures, list) or failures:
        raise SummaryError(f"{context}: failures must be an empty array")

    run_id = _required_text(data, "runId", context)
    label = _required_text(data, "label", context)
    backend = _required_text(data, "nativeBackend", context)
    renderer = _required_text(data, "actualRenderingMethod", context)
    display = _required_text(data, "display", context)
    commit = _required_text(data, "commit", context)
    source_hash = _required_text(data, "sourceHash", context)
    active = data.get("nativeBackendActive")
    if not isinstance(active, bool):
        raise SummaryError(f"{context}: nativeBackendActive must be a boolean")
    if backend == "native" and not active:
        raise SummaryError(f"{context}: requested native backend was not active")
    if backend == "gdscript" and active:
        raise SummaryError(f"{context}: gdscript backend unexpectedly reports native active")
    if backend not in {"native", "gdscript", "current"}:
        raise SummaryError(f"{context}: unsupported nativeBackend {backend!r}")
    trial = data.get("trial")
    if isinstance(trial, bool) or not isinstance(trial, int) or trial < 1:
        raise SummaryError(f"{context}: trial must be a positive integer")
    headless = data.get("headless")
    if not isinstance(headless, bool):
        raise SummaryError(f"{context}: headless must be a boolean")
    if (display == "headless") != headless:
        raise SummaryError(f"{context}: display/headless fields disagree")
    shared_machine = data.get("sharedMachine")
    if not isinstance(shared_machine, bool):
        raise SummaryError(f"{context}: sharedMachine must be a boolean")
    dirty = data.get("dirty")
    if not isinstance(dirty, bool):
        raise SummaryError(f"{context}: dirty must be a boolean")
    planned = data.get("plannedCells")
    cells = data.get("cells")
    if not isinstance(planned, list) or not planned:
        raise SummaryError(f"{context}: plannedCells must be a non-empty array")
    if not isinstance(cells, list) or not cells:
        raise SummaryError(f"{context}: cells must be a non-empty array")
    measurement = _required_dict(data, "measurement", context)
    _validate_acceptance_attribution(measurement, f"{context}.measurement")
    _validate_acceptance_eligibility(
        measurement, planned, f"{context}.measurement"
    )
    driver = _validate_driver(data, context, allow_legacy_driver)
    planned_ids = [_planned_id(spec, f"{context}.plannedCells") for spec in planned]
    if len(planned_ids) != len(set(planned_ids)):
        raise SummaryError(f"{context}: plannedCells contains duplicate ids")
    checked_cells = [
        _validate_cell(cell, context, min_frames, headless, driver) for cell in cells
    ]
    actual_ids = [cell["id"] for cell in checked_cells]
    if len(actual_ids) != len(set(actual_ids)):
        raise SummaryError(f"{context}: cells contains duplicate ids")
    missing = sorted(set(planned_ids) - set(actual_ids))
    extra = sorted(set(actual_ids) - set(planned_ids))
    if missing or extra:
        raise SummaryError(f"{context}: cell plan mismatch; missing={missing}, extra={extra}")
    planned_by_id = {spec["id"]: spec for spec in planned}
    for cell in checked_cells:
        spec = planned_by_id[cell["id"]]
        for key in ("count", "activity", "population", "visibility", "features", "network"):
            if spec.get(key) != cell[key]:
                raise SummaryError(
                    f"{context}: completed cell {cell['id']!r} changed planned {key}; "
                    f"planned={spec.get(key)!r}, actual={cell[key]!r}"
                )
    native_presentation = _validate_native_presentation(
        data.get("nativePresentation"), cells, context
    )
    execution_limits = _validate_report_process(
        data.get("process"), native_presentation, context
    )

    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
        "runId": run_id,
        "label": label,
        "backend": backend,
        "nativeBackendActive": active,
        "renderer": renderer,
        "display": display,
        "headless": headless,
        "nativePresentation": native_presentation,
        "executionLimits": execution_limits,
        "commit": commit,
        "sourceHash": source_hash,
        "dirty": dirty,
        "trial": trial,
        "sharedMachine": shared_machine,
        "interferenceLabel": data.get("interferenceLabel"),
        "driver": driver,
        "cells": checked_cells,
    }


def _expand_inputs(inputs: list[str], directories: list[str], label: str | None) -> tuple[list[Path], list[Path]]:
    candidates: list[Path] = []
    directory_used = False
    for item in inputs:
        matches = [Path(match) for match in glob.glob(item)]
        if not matches and not glob.has_magic(item):
            matches = [Path(item)]
        for match in matches:
            if match.is_dir():
                directory_used = True
                candidates.extend(match.glob("*.json"))
            else:
                candidates.append(match)
    for item in directories:
        directory_used = True
        directory = Path(item)
        if not directory.is_dir():
            raise SummaryError(f"artifact directory does not exist: {directory}")
        candidates.extend(directory.glob("*.json"))
    if directory_used and not label:
        raise SummaryError("--label is required when reading an artifact directory")

    unique: dict[str, Path] = {}
    ignored: list[Path] = []
    for path in candidates:
        if _is_process_metadata(path):
            ignored.append(path.resolve())
            continue
        if path.suffix.lower() != ".json":
            continue
        if not path.is_file():
            raise SummaryError(f"input file does not exist: {path}")
        unique[str(path.resolve()).lower()] = path.resolve()
    return sorted(unique.values(), key=lambda value: str(value).lower()), sorted(set(ignored))


def _read_runs(
    paths: list[Path], label: str | None, min_frames: int, allow_legacy_driver: bool
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SummaryError(f"cannot read benchmark JSON {path}: {error}") from error
        if not isinstance(data, dict):
            raise SummaryError(f"{path}: report root must be an object")
        if label is not None and data.get("label") != label:
            continue
        runs.append(_validate_run(path, data, min_frames, allow_legacy_driver))
    if not runs:
        suffix = f" for label {label!r}" if label else ""
        raise SummaryError(f"no benchmark runs selected{suffix}")
    run_ids = [run["runId"] for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise SummaryError("selected inputs contain duplicate runId values")
    return runs


def _validate_companion(run: dict[str, Any], allow_missing_for_fixtures: bool) -> None:
    report_path = Path(run["path"])
    companion_path = report_path.with_name(report_path.stem + ".process.json")
    context = str(companion_path)
    if not companion_path.is_file():
        if not allow_missing_for_fixtures:
            raise SummaryError(
                f"{report_path}: required process companion is missing: {companion_path}; "
                "use --allow-missing-process-companion-for-fixtures only for independent fixtures"
            )
        run["companionProcess"] = {
            "status": "missingFixtureOptOut",
            "path": str(companion_path.resolve()),
            "sha256": None,
            "fixtureOptOut": True,
            "executableIdentityAvailable": False,
        }
        return
    try:
        data = json.loads(companion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SummaryError(f"cannot read process companion {companion_path}: {error}") from error
    if not isinstance(data, dict):
        raise SummaryError(f"{context}: process companion root must be an object")

    expected_fields = {
        "runId": run["runId"],
        "backend": run["backend"],
        "renderer": run["renderer"],
        "mode": "headless" if run["headless"] else "windowed",
        "trial": run["trial"],
        "commit": run["commit"],
        "sourceHash": run["sourceHash"],
    }
    for key, expected in expected_fields.items():
        if data.get(key) != expected:
            raise SummaryError(
                f"{context}.{key} does not match its report; "
                f"companion={data.get(key)!r}, report={expected!r}"
            )
    presentation = run.get("nativePresentation")
    companion_has_presentation = any(
        key in data
        for key in ("nativePresentationRequested", "nativePresentationEnvironment")
    )
    if presentation is None:
        if companion_has_presentation:
            raise SummaryError(
                f"{context}: companion declares native presentation for a legacy-unattested report"
            )
    else:
        requested = data.get("nativePresentationRequested")
        if not isinstance(requested, str) or requested.lower() != presentation["requestedMode"]:
            raise SummaryError(
                f"{context}.nativePresentationRequested does not match its report"
            )
        if data.get("nativePresentationEnvironment") != presentation["environmentValue"]:
            raise SummaryError(
                f"{context}.nativePresentationEnvironment does not match its report"
            )
    exit_code = _required_int(data, "exitCode", context)
    if exit_code != 0:
        raise SummaryError(f"{context}.exitCode is {exit_code}; expected 0")
    if not _required_bool(data, "cleanExit", context):
        raise SummaryError(f"{context}.cleanExit is false")
    if _required_bool(data, "abortedAfterReport", context):
        raise SummaryError(f"{context}.abortedAfterReport is true")
    if _required_bool(data, "postReportStop", context):
        raise SummaryError(f"{context}.postReportStop is true (forced post-report termination)")
    current_fields = (
        "reportValid",
        "schemaValid",
        "scriptErrorsDetected",
        "forcedTermination",
        "monitoringError",
    )
    current_attestation = any(
        key in data for key in current_fields
    )
    if current_attestation:
        for key in current_fields:
            if key not in data:
                raise SummaryError(f"{context}.{key} is required for current process metadata")
    forced_termination = data.get("forcedTermination")
    if current_attestation:
        if _required_bool(data, "forcedTermination", context):
            raise SummaryError(f"{context}.forcedTermination is true")
        monitoring_error = data["monitoringError"]
        if not isinstance(monitoring_error, str):
            raise SummaryError(f"{context}.monitoringError must be a string")
        if monitoring_error:
            raise SummaryError(f"{context}.monitoringError is non-empty: {monitoring_error}")
        if not _required_bool(data, "reportValid", context):
            raise SummaryError(f"{context}.reportValid is false")
        if not _required_bool(data, "schemaValid", context):
            raise SummaryError(f"{context}.schemaValid is false")
        if _required_bool(data, "scriptErrorsDetected", context):
            raise SummaryError(f"{context}.scriptErrorsDetected is true")
    elif "forceTerminated" in data and _required_bool(data, "forceTerminated", context):
        raise SummaryError(f"{context}.forceTerminated is true")
    monitoring_error = data.get("monitoringError")

    affinity_mask = _required_int(data, "affinityMask", context)
    if affinity_mask != 0xF:
        raise SummaryError(f"{context}.affinityMask is {affinity_mask}; expected 15")
    execution_limits = run.get("executionLimits")
    if execution_limits is not None:
        requested_affinity = execution_limits.get("requestedAffinityMask")
        if requested_affinity is not None and requested_affinity != affinity_mask:
            raise SummaryError(
                f"{context}.affinityMask does not match report process.requestedAffinityMask"
            )
        if "requestedWorkerThreads" in data:
            requested_workers = _required_int(data, "requestedWorkerThreads", context)
            if requested_workers != execution_limits.get("requestedWorkerThreads"):
                raise SummaryError(
                    f"{context}.requestedWorkerThreads does not match its report"
                )
    if not _required_bool(data, "allObservedProcessesVerified", context):
        raise SummaryError(f"{context}.allObservedProcessesVerified is false")
    observed = _required_dict(data, "observedProcesses", context)
    if not observed:
        raise SummaryError(f"{context}.observedProcesses must not be empty")
    root_pid = _required_int(data, "rootPid", context)
    if str(root_pid) not in observed:
        raise SummaryError(f"{context}.rootPid is absent from observedProcesses")
    if execution_limits is not None:
        report_pid = execution_limits.get("pid")
        if report_pid is not None and report_pid != root_pid:
            raise SummaryError(f"{context}.rootPid does not match report process.pid")
    identity_available = True
    for pid, raw_process in observed.items():
        if not isinstance(raw_process, dict):
            raise SummaryError(f"{context}.observedProcesses[{pid!r}] must be an object")
        mask = _required_int(raw_process, "affinityMask", f"{context}.observedProcesses[{pid!r}]")
        if mask <= 0 or mask & ~0xF:
            raise SummaryError(
                f"{context}.observedProcesses[{pid!r}].affinityMask ({mask}) "
                "uses CPUs outside mask 15"
            )
        if not isinstance(raw_process.get("name"), str) or not raw_process["name"]:
            raise SummaryError(f"{context}.observedProcesses[{pid!r}].name is missing")
        if not isinstance(raw_process.get("path"), str) or not raw_process["path"]:
            identity_available = False
        if not isinstance(raw_process.get("startTimeUtc"), str) or not raw_process["startTimeUtc"]:
            identity_available = False

    requested_path = data.get("requestedGodotPath")
    launch_path = data.get("launchExecutablePath")
    if current_attestation:
        if not isinstance(requested_path, str) or not requested_path:
            raise SummaryError(f"{context}.requestedGodotPath is required for current metadata")
        if not isinstance(launch_path, str) or not launch_path:
            raise SummaryError(f"{context}.launchExecutablePath is required for current metadata")
        if not identity_available:
            raise SummaryError(f"{context}: current metadata lacks process path/start identity")
        normalized_launch = launch_path.replace("/", "\\").lower()
        for pid, raw_process in observed.items():
            normalized_observed = raw_process["path"].replace("/", "\\").lower()
            if normalized_observed != normalized_launch:
                raise SummaryError(
                    f"{context}.observedProcesses[{pid!r}].path does not match launchExecutablePath"
                )

    source_files = _required_dict(data, "sourceFiles", context)
    if not source_files:
        raise SummaryError(f"{context}.sourceFiles must not be empty")
    for source_path, digest in source_files.items():
        if not isinstance(source_path, str) or not source_path or not isinstance(digest, str) or not digest:
            raise SummaryError(f"{context}.sourceFiles must map non-empty paths to hashes")
    dirty = data.get("dirty")
    if not isinstance(dirty, bool):
        raise SummaryError(f"{context}.dirty must be a boolean")
    if dirty != run["dirty"]:
        raise SummaryError(
            f"{context}.dirty does not match its report; "
            f"companion={dirty!r}, report={run['dirty']!r}"
        )

    run["companionProcess"] = {
        "status": "validated",
        "metadataGeneration": "current" if current_attestation else "legacy",
        "path": str(companion_path.resolve()),
        "sha256": _sha256(companion_path),
        "fixtureOptOut": False,
        "runId": data["runId"],
        "rootPid": root_pid,
        "exitCode": exit_code,
        "cleanExit": data["cleanExit"],
        "abortedAfterReport": data["abortedAfterReport"],
        "postReportStop": data["postReportStop"],
        "forcedTermination": forced_termination,
        "monitoringError": monitoring_error,
        "reportValid": data.get("reportValid"),
        "schemaValid": data.get("schemaValid"),
        "scriptErrorsDetected": data.get("scriptErrorsDetected"),
        "affinityMask": affinity_mask,
        "allObservedProcessesVerified": data["allObservedProcessesVerified"],
        "observedProcesses": observed,
        "executableIdentityAvailable": identity_available,
        "requestedGodotPath": requested_path,
        "launchExecutablePath": launch_path,
        "commit": data["commit"],
        "dirty": dirty,
        "sourceHash": data["sourceHash"],
        "sourceFiles": source_files,
        "monitoring": data.get("monitoring"),
        "nativePresentationRequested": data.get("nativePresentationRequested"),
        "nativePresentationEnvironment": data.get("nativePresentationEnvironment"),
        "executionLimits": execution_limits,
    }


def _aggregate_metric(
    cell_runs: list[tuple[dict[str, Any], dict[str, Any]]], section: str, metric: str
) -> dict[str, Any]:
    per_run: list[dict[str, Any]] = []
    means: list[float] = []
    unavailable = 0
    for run, cell in cell_runs:
        stat = cell[section].get(metric)
        entry = {"runId": run["runId"], "trial": run["trial"]}
        if stat is None:
            entry["value"] = None
            unavailable += 1
        else:
            value = {
                "samples": stat["samples"],
                "mean": stat["mean"],
                "p95": stat["p95"],
                "p99": stat["p99"],
                "max": stat["max"],
            }
            entry["value"] = value
            means.append(stat["mean"])
        per_run.append(entry)
    return {
        "medianOfRunMeans": statistics.median(means) if means else None,
        "availableRuns": len(means),
        "unavailableRuns": unavailable,
        "perRun": per_run,
    }


def _aggregate_rate(
    cell_runs: list[tuple[dict[str, Any], dict[str, Any]]], metric: str
) -> dict[str, Any]:
    per_run: list[dict[str, Any]] = []
    values: list[float] = []
    for run, cell in cell_runs:
        value = cell["rates"].get(metric)
        per_run.append({"runId": run["runId"], "trial": run["trial"], "value": value})
        if value is not None:
            values.append(value)
    return {
        "medianOfRunValues": statistics.median(values) if values else None,
        "availableRuns": len(values),
        "unavailableRuns": len(per_run) - len(values),
        "perRun": per_run,
    }


def _aggregate_cell(cell_runs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    first = cell_runs[0][1]
    invariant_keys = ("count", "activity", "population", "visibility", "features", "network")
    for _, cell in cell_runs[1:]:
        for key in invariant_keys:
            if cell[key] != first[key]:
                raise SummaryError(
                    f"cell {first['id']!r} has inconsistent {key}: "
                    f"{first[key]!r} versus {cell[key]!r}"
                )
    seen_trials: set[int] = set()
    for run, _ in cell_runs:
        if run["trial"] in seen_trials:
            raise SummaryError(
                f"cell {first['id']!r} has duplicate trial number {run['trial']} in one group"
            )
        seen_trials.add(run["trial"])

    summary_names = sorted(set(SUMMARY_METRICS).union(*(cell["summary"] for _, cell in cell_runs)))
    packet_names = sorted(set(PACKET_METRICS).union(*(cell["packetBearingSummary"] for _, cell in cell_runs)))
    rate_names = sorted(set().union(*(cell["rates"] for _, cell in cell_runs)))
    result = {key: first[key] for key in ("id", *invariant_keys)}
    result.update(
        {
            "trialCount": len(cell_runs),
            "minimumFramesObserved": min(cell["frames"] for _, cell in cell_runs),
            "framesPerRun": [
                {"runId": run["runId"], "trial": run["trial"], "frames": cell["frames"]}
                for run, cell in cell_runs
            ],
            "evidencePerRun": [
                {
                    "runId": run["runId"],
                    "trial": run["trial"],
                    "fixture": cell["fixture"],
                    "plannedActive": cell["plannedActive"],
                    "plannedWorkload": cell["plannedWorkload"],
                    "resourceReadiness": cell["resourceReadiness"],
                    "diagnostics": cell["diagnostics"],
                    "memory": cell["memory"],
                    "spawn": cell["spawn"],
                    "despawnMilliseconds": cell["despawnMilliseconds"],
                    "driverValidation": cell["driverValidation"],
                }
                for run, cell in cell_runs
            ],
            "metrics": {
                metric: _aggregate_metric(cell_runs, "summary", metric)
                for metric in summary_names
            },
            "packetBearingMetrics": {
                metric: _aggregate_metric(cell_runs, "packetBearingSummary", metric)
                for metric in packet_names
            },
            "rates": {metric: _aggregate_rate(cell_runs, metric) for metric in rate_names},
        }
    )
    return result


def _aggregate(runs: list[dict[str, Any]], min_frames: int, ignored: list[Path]) -> dict[str, Any]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for run in runs:
        groups.setdefault((run["backend"], run["renderer"], run["display"]), []).append(run)

    group_results: list[dict[str, Any]] = []
    for key in sorted(groups):
        group_runs = sorted(groups[key], key=lambda run: (run["trial"], run["runId"]))
        commits = {run["commit"] for run in group_runs}
        source_hashes = {run["sourceHash"] for run in group_runs}
        labels = {run["label"] for run in group_runs}
        driver_states = {
            (run["driver"]["status"], run["driver"]["version"])
            for run in group_runs
        }
        active_values = {run["nativeBackendActive"] for run in group_runs}
        headless_values = {run["headless"] for run in group_runs}
        presentation_states = {
            (
                ("legacy-unattested", False)
                if run["nativePresentation"] is None
                else (
                    run["nativePresentation"]["requestedMode"],
                    run["nativePresentation"]["worldAttested"],
                )
            )
            for run in group_runs
        }
        if len(commits) != 1 or len(source_hashes) != 1:
            raise SummaryError(
                f"group {key} mixes commit/sourceHash provenance; summarize those runs separately"
            )
        if len(labels) != 1:
            raise SummaryError(f"group {key} mixes benchmark labels; select one with --label")
        if len(driver_states) != 1:
            raise SummaryError(f"group {key} mixes benchmark driver generations")
        if len(active_values) != 1 or len(headless_values) != 1:
            raise SummaryError(f"group {key} mixes backend-active or headless state")
        if len(presentation_states) != 1:
            raise SummaryError(
                f"group {key} mixes native presentation modes or legacy/attested runs; "
                "summarize each presentation mode separately"
            )
        expected_cells = {cell["id"] for cell in group_runs[0]["cells"]}
        for run in group_runs[1:]:
            actual_cells = {cell["id"] for cell in run["cells"]}
            if actual_cells != expected_cells:
                raise SummaryError(
                    f"group {key} run {run['runId']!r} has a different cell set; "
                    f"missing={sorted(expected_cells - actual_cells)}, "
                    f"extra={sorted(actual_cells - expected_cells)}"
                )

        by_cell: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for run in group_runs:
            for cell in run["cells"]:
                by_cell.setdefault(cell["id"], []).append((run, cell))
        cells = [_aggregate_cell(by_cell[cell_id]) for cell_id in sorted(by_cell)]
        shared = any(run["sharedMachine"] for run in group_runs)
        interference = sorted(
            {
                str(run["interferenceLabel"])
                for run in group_runs
                if run["interferenceLabel"] not in (None, "")
            }
        )
        caveats = []
        if shared:
            caveats.append(
                "Runs were collected on a shared host; scheduler and concurrent-load noise may affect comparisons."
            )
        if key[2] == "headless":
            caveats.append(
                "Headless renderer, GPU, draw-call, and primitive metrics are unavailable and remain null."
            )
        driver = group_runs[0]["driver"]
        first_presentation = group_runs[0]["nativePresentation"]
        if first_presentation is None:
            group_presentation = {
                "attestation": "legacy-unattested",
                "worldAttested": False,
                "requestedMode": None,
                "environmentValue": None,
                "requestedComponents": None,
                "activityPerRun": [],
            }
        else:
            group_presentation = {
                "attestation": first_presentation["attestation"],
                "worldAttested": first_presentation["worldAttested"],
                "requestedMode": first_presentation["requestedMode"],
                "environmentValue": first_presentation["environmentValue"],
                "requestedComponents": first_presentation["requestedComponents"],
                "activityPerRun": [
                    {
                        "runId": run["runId"],
                        "trial": run["trial"],
                        "actual": run["nativePresentation"]["actual"],
                    }
                    for run in group_runs
                ],
            }
        if not driver["productionFaithful"]:
            caveats.append(driver["caveat"])
        group_results.append(
            {
                "backend": key[0],
                "nativeBackendActive": next(iter(active_values)),
                "renderer": key[1],
                "display": key[2],
                "label": next(iter(labels)),
                "headless": next(iter(headless_values)),
                "commit": next(iter(commits)),
                "sourceHash": next(iter(source_hashes)),
                "driver": driver,
                "nativePresentation": group_presentation,
                "dirtyValues": sorted({str(run["dirty"]) for run in group_runs}),
                "sharedMachine": shared,
                "interferenceLabels": interference,
                "caveats": caveats,
                "runCount": len(group_runs),
                "runs": [
                    {
                        "runId": run["runId"],
                        "trial": run["trial"],
                        "label": run["label"],
                        "path": run["path"],
                        "sha256": run["sha256"],
                        "driver": run["driver"],
                        "nativePresentation": run["nativePresentation"],
                        "executionLimits": run["executionLimits"],
                        "companionProcess": run["companionProcess"],
                    }
                    for run in group_runs
                ],
                "cells": cells,
            }
        )

    companions = [run["companionProcess"] for run in runs]
    validated_companions = [item for item in companions if item["status"] == "validated"]
    fixture_opt_outs = [item for item in companions if item["status"] == "missingFixtureOptOut"]
    selected_companion_paths = {
        str(Path(item["path"])).lower() for item in validated_companions
    }

    return {
        "schemaVersion": 1,
        "generatedAtUtc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "aggregationMethod": (
            "median of per-run means; per-run p95, p99, and max retained; "
            "percentiles are not pooled across processes"
        ),
        "minimumFrameRequirement": min_frames,
        "inputs": {
            "files": [
                {"path": run["path"], "sha256": run["sha256"]}
                for run in sorted(runs, key=lambda item: item["path"].lower())
            ],
            "companionProcessMetadata": {
                "aggregationUse": "validationOnlyExcludedFromTimingAggregation",
                "validationStatus": "fixtureOptOutPresent" if fixture_opt_outs else "validated",
                "files": [
                    {
                        "path": item["path"],
                        "sha256": item["sha256"],
                        "metadataGeneration": item["metadataGeneration"],
                        "executableIdentityAvailable": item["executableIdentityAvailable"],
                    }
                    for item in validated_companions
                ],
                "fixtureOptOuts": fixture_opt_outs,
                "unmatchedExcludedCandidateCount": sum(
                    1 for path in ignored if str(path).lower() not in selected_companion_paths
                ),
            },
        },
        "groups": group_results,
    }


def _format_number(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):.3f}"


def _run_values(metric: dict[str, Any], key: str) -> str:
    values = [entry["value"].get(key) for entry in metric["perRun"] if entry["value"] is not None]
    return ", ".join(_format_number(value) for value in values) if values else "—"


def _find_scaling_cell(cells: list[dict[str, Any]], count: int, activity: str) -> dict[str, Any] | None:
    matches = [
        cell
        for cell in cells
        if cell["id"] != "acceptance-mixed300"
        and cell["count"] == count
        and cell["activity"] == activity
    ]
    if not matches:
        return None
    preferred = [cell for cell in matches if cell["id"] == f"matrix-{count}-{activity}"]
    if len(preferred) == 1:
        return preferred[0]
    if len(matches) == 1:
        return matches[0]
    return None


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Crowd benchmark summary",
        "",
        "Values labeled `median of run means` combine trial means only. Per-run p95, p99, and max values remain attached to their source process; this report does not pool percentiles.",
        "",
        f"Minimum accepted frame count per cell: **{report['minimumFrameRequirement']}**.",
        "",
    ]
    for group in report["groups"]:
        presentation = group.get("nativePresentation") or {
            "attestation": "legacy-unattested",
            "worldAttested": False,
            "requestedMode": None,
            "environmentValue": None,
            "activityPerRun": [],
        }
        driver_description = (
            f"`{group['driver']['version']}` (validated deferred-coalescing path)"
            if group["driver"]["productionFaithful"]
            else "legacy forced-presentation opt-in (not production-faithful)"
        )
        lines.extend(
            [
                f"## {group['backend']} · {group['renderer']} · {group['display']}",
                "",
                (
                    "Headless `wallMilliseconds` is a **scene CPU proxy**; renderer, GPU, "
                    "draw-call, and primitive metrics are unavailable."
                    if group["headless"]
                    else "Windowed `wallMilliseconds` is **diagnostic and non-authoritative**; "
                    "display pacing and compositor scheduling can affect it."
                ),
                "",
                f"Commit: `{group['commit']}`  ",
                f"Source hash: `{group['sourceHash']}`  ",
                f"Runs: {group['runCount']}  ",
                f"Driver: {driver_description}  ",
                (
                    "Native presentation: legacy/unattested"
                    if presentation["attestation"] == "legacy-unattested"
                    else (
                        f"Native presentation: `{presentation['requestedMode']}` "
                        f"(`ELORIA_NATIVE_PRESENTATION={presentation['environmentValue']}`)"
                    )
                ),
                "",
            ]
        )
        for item in presentation["activityPerRun"]:
            actual = item["actual"]
            lines.append(
                "- Native presentation activity "
                f"`{item['runId']}`: cape active max "
                f"{actual['capeActiveInstancesMaximum']}, cape native calls "
                f"{actual['capeNativeCalls']}, cape fallback "
                f"{actual['capeFallbackCalls']}; flight active max "
                f"{actual['flightActiveInstancesMaximum']}, flight builds "
                f"{actual['flightBuildSuccesses']}/{actual['flightBuildAttempts']}, "
                f"flight fallback {actual['flightBuildFallbacks']}"
                + (
                    "; world active max "
                    f"{actual['worldActiveInstancesMaximum']}, world builds "
                    f"{actual['worldBuildSuccesses']}/{actual['worldBuildAttempts']}, "
                    f"world fallback {actual['worldBuildFallbacks']}"
                    if presentation["worldAttested"] else ""
                )
                + "."
            )
        for caveat in group["caveats"]:
            lines.append(f"- {caveat}")
        if group["interferenceLabels"]:
            lines.append("- Interference labels: " + ", ".join(group["interferenceLabels"]))
        if group["caveats"] or group["interferenceLabels"]:
            lines.append("")

        scaling_columns = [
            (activity, label)
            for activity, label in ACTIVITY_COLUMNS
            if any(
                _find_scaling_cell(group["cells"], count, activity) is not None
                for count in SCALING_COUNTS
            )
        ]
        if scaling_columns:
            scaling_title = (
                "### Scaling: scene CPU proxy wall milliseconds, median of run means"
                if group["headless"]
                else "### Scaling: diagnostic wall milliseconds, median of run means (non-authoritative)"
            )
            lines.extend(
                [
                    scaling_title,
                    "",
                    "| Actors | " + " | ".join(label for _, label in scaling_columns) + " |",
                    "| ---: | " + " | ".join("---:" for _ in scaling_columns) + " |",
                ]
            )
            for count in SCALING_COUNTS:
                row = [str(count)]
                for activity, _ in scaling_columns:
                    cell = _find_scaling_cell(group["cells"], count, activity)
                    value = (
                        None
                        if cell is None
                        else cell["metrics"]["wallMilliseconds"]["medianOfRunMeans"]
                    )
                    row.append(_format_number(value))
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        nonprimary_cells = [
            cell for cell in group["cells"] if cell["id"] != "acceptance-mixed300"
        ]
        if nonprimary_cells:
            cell_title = (
                "### Cells: scene CPU proxy wall and renderer metrics"
                if group["headless"]
                else "### Cells: diagnostic wall and world-render metrics (wall non-authoritative)"
            )
            lines.extend(
                [
                    cell_title,
                    "",
                    "| Cell | Wall mean, median of run means (ms) | Per-run wall p95 (ms) | Per-run wall p99 (ms) | World render CPU mean (ms) | World render GPU mean (ms) | Draw calls mean |",
                    "| --- | ---: | --- | --- | ---: | ---: | ---: |",
                ]
            )
            for cell in nonprimary_cells:
                wall = cell["metrics"]["wallMilliseconds"]
                world_cpu = cell["metrics"]["worldRenderCpuMilliseconds"]
                world_gpu = cell["metrics"]["worldRenderGpuMilliseconds"]
                draw_calls = cell["metrics"]["drawCalls"]
                row = [
                    f"`{cell['id']}`",
                    _format_number(wall["medianOfRunMeans"]),
                    _run_values(wall, "p95"),
                    _run_values(wall, "p99"),
                    _format_number(world_cpu["medianOfRunMeans"]),
                    _format_number(world_gpu["medianOfRunMeans"]),
                    _format_number(draw_calls["medianOfRunMeans"]),
                ]
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        primary = next((cell for cell in group["cells"] if cell["id"] == "acceptance-mixed300"), None)
        if primary is not None:
            primary_title = (
                "### Primary scene CPU proxy components"
                if group["headless"]
                else "### Primary diagnostic wall components (non-authoritative)"
            )
            lines.extend(
                [
                    primary_title,
                    "",
                    "All-frame component values are milliseconds.",
                    "",
                    "| Component | Median of run means | Per-run means | Per-run p95 | Per-run p99 | Per-run max |",
                    "| --- | ---: | --- | --- | --- | --- |",
                ]
            )
            for metric in (
                "wallMilliseconds",
                "presentMilliseconds",
                "groundMilliseconds",
                "overheadMilliseconds",
                "animationGateMilliseconds",
                "syncWorldMilliseconds",
                "packetDispatchInclusiveMilliseconds",
                "commandOnlyReduceMilliseconds",
            ):
                aggregate = primary["metrics"].get(metric)
                cells = [
                    metric,
                    _format_number(aggregate["medianOfRunMeans"]),
                    _run_values(aggregate, "mean"),
                    _run_values(aggregate, "p95"),
                    _run_values(aggregate, "p99"),
                    _run_values(aggregate, "max"),
                ]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

            if not group["headless"]:
                renderer_metrics = (
                    ("worldRenderCpuMilliseconds", "ms"),
                    ("worldRenderGpuMilliseconds", "ms"),
                    ("drawCalls", "calls/frame"),
                )
                if any(
                    primary["metrics"][metric]["medianOfRunMeans"] is not None
                    for metric, _ in renderer_metrics
                ):
                    lines.extend(
                        [
                            "### Primary windowed world-render metrics",
                            "",
                            "| Metric | Unit | Median of run means | Per-run means | Per-run p95 | Per-run p99 | Per-run max |",
                            "| --- | --- | ---: | --- | --- | --- | --- |",
                        ]
                    )
                    for metric, unit in renderer_metrics:
                        aggregate = primary["metrics"][metric]
                        cells = [
                            metric,
                            unit,
                            _format_number(aggregate["medianOfRunMeans"]),
                            _run_values(aggregate, "mean"),
                            _run_values(aggregate, "p95"),
                            _run_values(aggregate, "p99"),
                            _run_values(aggregate, "max"),
                        ]
                        lines.append("| " + " | ".join(cells) + " |")
                    lines.append("")

            lines.extend(
                [
                    "Packet-bearing frames are summarized separately; their sample counts can be lower than the cell frame count.",
                    "",
                    "| Packet-bearing component | Median of run means | Per-run means | Per-run p95 | Per-run p99 | Per-run max |",
                    "| --- | ---: | --- | --- | --- | --- |",
                ]
            )
            for metric in PACKET_METRICS:
                aggregate = primary["packetBearingMetrics"].get(metric)
                cells = [
                    metric,
                    _format_number(aggregate["medianOfRunMeans"]),
                    _run_values(aggregate, "mean"),
                    _run_values(aggregate, "p95"),
                    _run_values(aggregate, "p99"),
                    _run_values(aggregate, "max"),
                ]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

    lines.extend(["## Inputs", ""])
    for item in report["inputs"]["files"]:
        lines.append(f"- `{item['sha256']}`  `{item['path']}`")
    process_metadata = report["inputs"]["companionProcessMetadata"]
    lines.extend(["", "Companion process metadata is excluded from timing aggregation and validated as a report gate."])
    for item in process_metadata["files"]:
        identity = "identity recorded" if item["executableIdentityAvailable"] else "legacy: executable identity unavailable"
        lines.append(f"- `{item['sha256']}`  `{item['path']}` ({identity})")
    for item in process_metadata["fixtureOptOuts"]:
        lines.append(f"- Fixture opt-out: missing companion `{item['path']}`")
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Explicit benchmark JSON paths, globs, or directories. Quote globs on Windows.",
    )
    parser.add_argument(
        "--artifact-directory",
        action="append",
        default=[],
        metavar="DIR",
        help="Directory containing run JSON files; requires --label. May be repeated.",
    )
    parser.add_argument("--label", help="Select only reports whose label exactly matches this value.")
    parser.add_argument(
        "--min-frames",
        type=int,
        default=60,
        help="Reject any completed cell with fewer frames (default: 60).",
    )
    parser.add_argument(
        "--json-output",
        default="crowd-benchmark-summary.json",
        metavar="PATH",
        help="Compact machine-readable output path.",
    )
    parser.add_argument(
        "--markdown-output",
        default="crowd-benchmark-summary.md",
        metavar="PATH",
        help="Markdown table output path.",
    )
    parser.add_argument(
        "--allow-missing-process-companion-for-fixtures",
        action="store_true",
        help=(
            "Allow a missing .process.json only for independently constructed parser fixtures. "
            "Existing companions are always validated and benchmark reports should not use this opt-out."
        ),
    )
    parser.add_argument(
        "--allow-legacy-forced-presentation",
        action="store_true",
        help=(
            "Include superseded historical reports whose driver manually forced presentation. "
            "The JSON and Markdown outputs mark them as not production-faithful."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.min_frames < 1:
            raise SummaryError("--min-frames must be positive")
        if not args.inputs and not args.artifact_directory:
            raise SummaryError("provide at least one JSON path, glob, or artifact directory")
        paths, ignored = _expand_inputs(args.inputs, args.artifact_directory, args.label)
        runs = _read_runs(
            paths, args.label, args.min_frames, args.allow_legacy_forced_presentation
        )
        for run in runs:
            _validate_companion(run, args.allow_missing_process_companion_for_fixtures)
        report = _aggregate(runs, args.min_frames, ignored)
        json_output = Path(args.json_output)
        markdown_output = Path(args.markdown_output)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        markdown_output.write_text(_markdown(report), encoding="utf-8")
    except (OSError, SummaryError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"summarized {len(report['inputs']['files'])} run(s) into "
        f"{json_output} and {markdown_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
