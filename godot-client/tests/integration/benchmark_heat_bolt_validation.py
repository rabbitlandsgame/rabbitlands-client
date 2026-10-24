"""Fail-closed additive validation for the explicit Phase7 heat-bolt cell."""
from __future__ import annotations


class HeatBoltEvidenceError(ValueError):
    pass


def validate_heat_bolt_cell(cell: dict, request: dict) -> None:
    def need(condition: bool, message: str) -> None:
        if not condition:
            raise HeatBoltEvidenceError("heat-bolt: " + message)

    workload = cell.get("spellWorkload")
    need(isinstance(workload, dict), "workload evidence missing")
    need(workload.get("schemaVersion") == 1
         and workload.get("kind") == "synthetic_heat_bolt_packets"
         and workload.get("family") == "heat_bolt", "workload classification differs")
    need(workload.get("castsPerBurst") == 143 and workload.get("movingActors") == 16
         and workload.get("onFootActors") == 160
         and workload.get("burstPeriodMilliseconds") == 2000
         and workload.get("priorityPacketOrder") == "after-normal-burst", "workload policy differs")
    for point in ("afterSpawn", "afterSample"):
        census = cell.get("census", {}).get(point, {})
        need(census.get("nodes") == 160 and census.get("mountedActors") == 0,
             "on-foot population differs at " + point)
    start, end, delta = (workload.get(k) for k in ("sampleStart", "sampleEnd", "sampleCounters"))
    need(all(isinstance(v, dict) for v in (start, end, delta)), "counter boundaries missing")
    a, b = start.get("counters"), end.get("counters")
    need(isinstance(a, dict) and isinstance(b, dict), "lifetime counter snapshots missing")
    for key, value in b.items():
        need(type(value) is int and value >= 0, "invalid lifetime counter " + key)
        before = a.get(key, 0)
        need(type(before) is int and 0 <= before <= value, "counter regressed " + key)
        if key != "maximum_observed_live":
            need(delta.get(key) == value-before, "sample counter differs " + key)
    positive = ("bursts", "spell_packets", "movement_packets", "moving_target_casts", "admitted_visuals",
                "observed_releases", "observed_arrivals", "observed_expiries",
                "local_priority_packets", "selected_priority_packets", "combat_priority_packets",
                "local_priority_admitted", "selected_priority_admitted", "combat_priority_admitted")
    need(all(type(delta.get(k)) is int and delta[k] > 0 for k in positive),
         "sample did not exercise every required event/priority/anchor behavior")
    need(delta["spell_packets"] == delta["bursts"] * 143, "partial packet burst")
    need(b.get("phase_regressions", 0) == 0 and b.get("external_retirements", 0) == 0,
         "effect phase regressed or retired before expiry")
    need(b.get("observed_expiries", 0) <= b.get("observed_arrivals", 0)
         <= b.get("observed_releases", 0) <= b.get("admitted_visuals", 0)
         <= b.get("spell_packets", 0), "lifetime event counts are inconsistent")
    need(type(b.get("maximum_observed_live")) is int
         and 0 < b["maximum_observed_live"] <= b["admitted_visuals"], "invalid lifetime live maximum")
    for key in ("powerPackets", "powerAdmitted"):
        histogram = end.get(key)
        need(isinstance(histogram, dict) and set(histogram) == {str(p) for p in range(1, 11)}
             and all(type(v) is int and v > 0 for v in histogram.values()), "not every power exercised")
        need(sum(histogram.values()) == b.get("spell_packets" if key == "powerPackets" else "admitted_visuals"),
             "power histogram and admitted/packet counts differ")
    backends = end.get("admittedBackends")
    need(isinstance(backends, dict) and set(backends) == {"rust", "cpp", "gd"}
         and all(type(v) is int and v >= 0 for v in backends.values())
         and sum(backends.values()) == b.get("admitted_visuals"), "actual admission backends inconsistent")
    wanted = "rust" if request.get("rust_effects", "legacy") == "heat_bolt" else (
        "cpp" if request.get("native_presentation", "off") in ("flight", "both", "all") else "gd")
    need(backends[wanted] == b.get("admitted_visuals"), "requested complete family silently used another backend")
    actual = cell.get("effectiveRuntime", {}).get("activeBackends", {})
    if wanted == "rust":
        runtime = actual.get("rustSpellFlights", {})
        need(runtime.get("active") is True and runtime.get("frames", 0) > 0
             and runtime.get("fallbacks") == 0 and runtime.get("admitted_legacy") == 0,
             "Rust family failed, fell back, or never ran")
        events = runtime.get("events", {})
        need(all(type(events.get(k)) is int and events[k] > 0 for k in ("releases", "arrivals", "expiries")),
             "native exact-once lifecycle did not execute")
        need(runtime.get("admitted_rust") == b["admitted_visuals"]
             and all(events[k] == b["observed_"+k] for k in ("releases", "arrivals", "expiries")),
             "native lifecycle events differ from independent presentation observer")
    elif wanted == "cpp":
        provider = actual.get("clientRuntime", {}).get("native", {}).get("cpp_spell_flight_provider")
        need(provider == "client_runtime", "C++ comparator did not come from the verified runtime payload")
    probe = workload.get("removedTargetProbe", {})
    need(all(probe.get(k) is True for k in ("success", "outsideTimedSample", "spellAdmitted",
         "actorRecordRemoved", "actorPresentationRemoved", "finiteFlightEndpoints",
         "effectCompleted", "restoredRecord", "restorationReady")), "removed-target/restoration probe incomplete")
