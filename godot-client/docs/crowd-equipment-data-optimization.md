# Equipment data and presentation follow-up

The retained changes substantially reduce catalog memory and actor lifecycle
cost. They do not establish sustained 60 FPS: the final candidate has a
22.223 ms median headless run mean, mixed frame tails, and windowed means of
52–61 ms in Compatibility and 39–41 ms in Forward+ on the shared host.

This study continues the isolated `perf/native-crowd-300-benchmark` branch from
`66f575ffe14f23153caa4920b2bfb47ccbc4f219`. The preceding
[impact geometry study](crowd-impact-geometry-optimization.md) measured a
21.114 ms median headless scene CPU proxy and no consistent rendered gain.
The target remains a complete frame below 16.67 ms with 300 actors, 150 visible
and 100 active, retaining equipment, overhead information, animation and effects.
The broader population matrix and original native-boundary investigation remain
in the [crowd study](native-crowd-study.md) and
[benchmark guide](native-crowd-benchmarks.md).

## Choosing the next change

The new [script profile evidence](benchmarks/crowd-script-profile-2026-09-19.json)
captures the existing primary fixture with native presentation `All` and the
GDScript reducer. The installed Godot executable requires both `--debug` and
`--profiling` for its local script profiler. Its `FRAME` output is one frame
snapshot sampled periodically, not an aggregate over the preceding interval.
The capture contains 18 snapshots; five contain the benchmark's `_sample_cell`
function. Coroutine scheduling makes that a useful indication of the sampling
phase, not an exact capture boundary or an unbiased sample of every frame.

Within those five snapshots, hand-prop visibility costs about 1.073 ms per
snapshot inclusive, with equipment-model resolution accounting for 0.770 ms.
That path resolves fit groups and duplicates fitted model data merely to test
whether the weapon has a separate animated-bow representation. These are
nested costs and must not be added. They justify a focused complete-callback
comparison, not a predicted whole-frame saving.

Other small candidates were deferred: cape bone-pose writing accounts for
about 0.588 ms per snapshot, world-detail mesh submission 0.369 ms, and flight
surface submission 0.206 ms. Even removing each entire measured cost would
leave a small upper bound before integration overhead. These sparse observations
do not justify another native kernel. Effect construction remains an event
cost; the earlier allocation probe already measured it separately.

Profiler timings are diagnostic only. Synchronous engine and extension calls
are charged to their script callers when native-call profiling is disabled.
Inherited callback accounting and nested functions can also make reported
script totals exceed the frame total. Neither those totals nor the profiled
29.720 ms wall mean are acceptance measurements.

The official Godot binary has no debug symbols, so the available script tools
cannot reliably distinguish engine animation evaluation, skeleton finalization,
skin upload and scene traversal. Godot recommends a production build with
`production=yes debug_symbols=yes` for that investigation.
[Official profiling documentation](https://docs.godotengine.org/en/4.7/engine_details/development/profiling/index.html#sampling-profilers).
The existing production animation schedule is retained; a synthetic manual
advance fixture would not be equivalent evidence.

The equipment audit also found a lifecycle cost: each actor deep-copies the
entire 860,660-byte equipment catalog. The current investigation tests bounded
immutable snapshots while preserving the previous defensive-copy behavior:
changing the caller's catalog must not change an existing actor, and a newly
configured actor must receive the changed contents. Actor equipment choices,
appearance, materials, nodes and animation remain individually owned.

## Implementation and focused checks

The hand-prop change caches only whether the resolved main-hand model has
`rangedAnimationScene`. Weapon removal/replacement and actor reconfiguration
invalidate it. Equipment creation seeds it from the model already resolved for
that operation. Every visibility call still assigns every valid current prop,
including a newly attached prop or a node whose visibility changed externally.
Disabled, empty and shield-only paths need no weapon lookup.

Seven rotated trials compare the complete `CombatPresentation3D.update_pose()`
callback against an exact frozen accessor from the preceding runtime. Timed
actors have no lookup-count instrumentation; separate actors provide the
untimed lookup traces. The windowed Compatibility medians are:

| Scenario | Frozen accessor (µs/callback) | Cached accessor | Change |
| --- | ---: | ---: | ---: |
| Idle bow | 18.610 | 9.682 | -48.0% |
| Ranged hold | 18.208 | 8.378 | -54.0% |
| Melee | 17.205 | 5.088 | -70.4% |
| Casting, effects disabled | 17.648 | 4.443 | -74.8% |
| Casting, full effects | 116.718 | 96.945 | -16.9% |

Headless results agree in direction. These focused timings exclude skeleton
evaluation and signal dispatch and do not predict a whole-frame gain. Exact
visibility snapshots cover melee and ranged weapons, shields, the legacy bow,
empty equipment, unchanged equipment, swaps, clearing, late props, external
visibility changes, effects disabled and a changed rig/fit-specific registry.
Warm candidate callbacks perform zero model lookups versus two in the frozen
accessor for the timed scenarios.
The [focused evidence](benchmarks/hand-prop-visibility-cache-2026-09-19.json)
preserves both raw runs. Their captured baseline commit string contained a
typo; the correction is explicit in the bundle. The reviewer independently
matched the frozen method bytes against the real historical commit and
recomputed every scenario median from the raw trials. No timing artifact was
rewritten to correct metadata.

The first catalog prototype serialized and compared content on every actor
acquisition. It reduced retained allocations by roughly 821 MB, but increased
the focused 300-copy median from 1.274 s to 5.490 s. That design was rejected.
The retained design prepares a recursively read-only snapshot once when Main
loads its catalog. Actors share only an exact recognized prepared identity;
arbitrary caller dictionaries still receive `duplicate(true)`. The registry
retains at most four prepared catalogs. Evicted identities safely fall back
to copying. No per-actor serialization or content hashing remains.

The final eight-trial rotated catalog probe measures 300 deep copies at a
median 1,535,054 µs versus 90.5 µs for prepared acquisitions. Preparation costs
36,255.5 µs once. The acquisition interval retains 824,672,634 additional Godot
static bytes for deep copies versus 7,434 bytes for shared references. The
latter excludes the prepared snapshot allocated before that interval; neither
counter is process RSS. This establishes a lifecycle/allocation improvement,
not a frame-rate result.

The final contract checks detached recursive freezing, mutable fallback,
typed containers, capacity/eviction and unsupported packed/Object input.
Two real rigs and two equipment kits produce matching surface-array hashes,
transforms, skin bindings, material texture/color state and visibility through
swaps. Actors keep distinct equipment nodes and material-override state, and
clearing or changing one actor cannot alter another. The existing equipment
fit-profile and 16-rig combat tests also pass under windowed Compatibility.
An earlier headless fit-profile attempt failed during script loading before
explicit helper preloads were added; it is rejected evidence, not a passed
test. The final-byte windowed rerun resolves that regression check.

The shared-catalog census runs outside the benchmark sample interval and
records actual actor registry identities, read-only state and sharing with
Main. This verifies whether the production fast path is used independently
of timing or memory counters. Full-scene results below must distinguish
Godot static allocation counters from process resident memory.

## Whole-scene results

The [portable whole-scene evidence](benchmarks/crowd-equipment-data-results-2026-09-19.json)
contains all twelve controlled runs, the separate attribution diagnostic,
process-memory observations and source/artifact hashes. A is the preceding
runtime; B is frozen commit `37b3c7a6a8c736a6499941d06f72aef27ed21d19`
(runtime implementation `7ccc290c0`). Each run retains 300 actors, 150 visible,
100 active, 150 fully equipped humanoids, 1,050 equipment visual selections,
1,500 skinned equipment nodes and 7,350 mesh instances. No equipment fallback
is used. Registry identity checks show exactly 300 private mutable catalogs
in every A run and one shared read-only Main catalog in every B run.

### Headless scene CPU proxy

Times are milliseconds; percentiles use the harness's nearest-rank method and
remain attached to each process. They are not pooled across runs.

| Order | Variant | Mean | p95 | p99 | Maximum |
| ---: | :---: | ---: | ---: | ---: | ---: |
| 1 | A | 23.671 | 37.423 | 52.686 | 53.878 |
| 2 | B | 21.992 | 39.024 | 47.990 | 51.040 |
| 3 | B | 22.481 | 39.306 | 46.230 | 52.942 |
| 4 | A | 21.396 | 37.008 | 45.094 | 52.815 |
| 5 | A | 23.703 | 43.089 | 46.535 | 56.325 |
| 6 | B | 22.223 | 38.577 | 48.538 | 51.755 |

The median of run means is 23.671 → 22.223 ms, a descriptive 6.12% reduction.
Two adjacent comparisons improve mean time; the middle one regresses.
Two of three paired p95 and p99 comparisons regress. This is insufficient
evidence for a stable frame-pacing gain. The focused callback result supports
retaining the small cache, but its microsecond savings are not added to these
whole-scene observations. Cross-study comparisons against the earlier
21.114 ms candidate are not controlled comparisons.

### Windowed rendering

Each renderer uses B/A/B order. Wall time includes host/compositor pacing.
World render CPU and asynchronous GPU observations are separate measurements,
not terms to add to wall time.

| Renderer | Variant | Wall mean | p95 | p99 | Max | World CPU mean | World GPU mean |
| --- | :---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Compatibility | B1 | 60.549 | 80.740 | 105.323 | 105.323 | 19.379 | 17.664 |
| Compatibility | A | 53.877 | 70.151 | 75.620 | 75.620 | 17.964 | 16.155 |
| Compatibility | B2 | 52.123 | 69.507 | 83.105 | 83.105 | 17.682 | 15.948 |
| Forward+ | B1 | 38.789 | 55.289 | 59.764 | 61.967 | 5.040 | 1.693 |
| Forward+ | A | 47.355 | 68.762 | 83.831 | 87.469 | 5.516 | 1.704 |
| Forward+ | B2 | 40.987 | 54.367 | 61.837 | 80.121 | 5.149 | 1.695 |

Compatibility shows no consistent gain; both candidate p99 values exceed A.
Forward+ improves both candidate means and tails relative to its one baseline
run, but remains far above 16.67 ms. One B/A/B sequence on a shared machine
does not establish a general renderer or frame-rate improvement. Draw calls
remain about 3,675 in Compatibility and 2,460 in Forward+; this patch does not
consolidate meshes or draw submissions. The shipping renderer is unchanged.

Eight active/settled captures were reviewed: B1 and A for both renderers.
Crowd identities, equipment, overhead information and active effects remain
present without an obvious within-renderer regression. Settled captures show
effects expired. Different simulation times prevent pixel or animation parity
claims. Forward+'s brighter ground and paler effects persist from earlier
studies; changing renderer still requires separate visual review. All twelve
capture files are retained and hashed. FPS overlays are not timing evidence.

### Memory and lifecycle

These are medians by variant: three A and three B headless runs, one A and
two B runs for each windowed renderer. Static memory is the absolute Godot
`memory.spawned.staticBytes` snapshot, including pre-existing world/assets.
The portable data also retains `spawnDelta`, a different measurement.

| Mode | Spawned static MiB A → B | Create 300 actors, ms A → B | Despawn, ms A → B |
| --- | ---: | ---: | ---: |
| Headless | 1,503.263 → 717.134 | 4,397.645 → 2,582.223 | 955.077 → 106.740 |
| Compatibility | 1,228.666 → 441.998 | 5,797.103 → 4,705.644 | 1,038.835 → 196.236 |
| Forward+ | 1,311.793 → 525.497 | 10,476.291 → 9,497.181 | 994.672 → 188.569 |

The roughly 786 MiB reduction appears in every rendering mode. Headless
creation improves by 41.3% and despawn by 88.8%, with all 300 actors created
over the same 38 budgeted passes. These lifecycle operations are outside
steady-state frame sampling. The catalog optimization is retained primarily
for this repeatable memory and lifecycle benefit.

Operating-system private memory is sampled approximately once per second
through the captured process's entire lifetime, including startup and teardown.
Maximum sampled private memory is 1,941–1,948 MiB for headless A versus
861–867 MiB for B; Compatibility is 3,535 MiB versus 2,448–2,463 MiB;
Forward+ is 3,756 MiB versus approximately 2,649 MiB. These are sampled maxima,
not a private-memory peak counter or steady-frame RSS. Working-set and OS
peak-working-set observations are retained separately. GPU texture/video
counters are separate again and must not be added to Godot static or process
private memory. Resource counters after despawn retain caches and harness
telemetry and are not a leak measurement.
At the spawned snapshot, Compatibility reports 366.92 MiB texture memory and
805.89 MiB video memory; Forward+ reports 422.36 MiB and 789.96 MiB respectively.
Those values match across A/B within each renderer. The snapshot retains
19,874 nodes; the candidate adds one helper script resource (172 versus 171).

## Remaining limit and recommendation

One final candidate attribution run reports 18.206 ms wall mean, 30.969 p95,
35.482 p99 and 47.461 maximum. Signal instrumentation changes the diagnostic
boundary, so it is excluded from acceptance and does not replace 22.223 ms.
Main's inclusive callback averages 1.014 ms, the combat callback from skeleton
updates 1.712 ms, animation gating 0.139 ms, overhead work 0.106 ms, grounding
0.076 ms and command-only reduction 0.071 ms. These nested/inclusive timings
must not be summed or subtracted from wall time to manufacture an engine cost.
There are exactly 150 unique skeleton updates per frame, at most one per
actor, across all 274 samples. Workload rates are 560.383 commands/s and
67.358 combat events/s. Native cape, flight and world geometry calls have zero
fallbacks; cape calls remain 75 per frame.

The next decision remains a symbolized engine CPU profile of the production
animation schedule, separating animation evaluation, skeleton finalization,
skin uploads and scene traversal. The measured scene CPU proxy still exceeds
the complete-frame target, and the current counters cannot assign its remainder
to one of those engine systems. Smaller reducer, overhead or grounding kernels
are not supported as the next high-impact native migration by these figures.

Rendering also remains a measured constraint: Compatibility world CPU and GPU
each consume approximately the complete 16.67 ms budget. Forward+ reduces
those observations, but its render CPU still exceeds the development-host
3/4 ms mean/p95 gate. A mesh/material consolidation prototype that preserves
near-actor equipment identity is justified as a separate rendering experiment;
a custom crowd renderer should follow measured benefit from that prototype.
The 8/10 ms scene CPU gate remains unmet. Forward+ passes the 6/8 ms world GPU
gate, which alone is insufficient for the complete-frame goal.

Godot continues to own actor state/presentation, animation, skeletons, UI,
resources and effects. This stage adds only GDScript caches. The prior optional
native numerical/geometry kernels and GDScript reducer remain unchanged.
The evidence supports the hybrid approach and does not justify a standalone
client or another broad native rewrite. Certification still requires a quiet
midrange target with the full workload and frame tails measured.

## Controlled comparison protocol

The historical runtime is `66f575ffe14f23153caa4920b2bfb47ccbc4f219`.
Both variants use native presentation `All`, the GDScript reducer and the same
981,504-byte native DLL, SHA-256
`7321af0475b974313a15317ed6f9db459cf6e47146c5b5ff4ca983f74ccb5a1a`.
Only Main and ReplicatedActor runtime sources are reversed; the final harness
and optional catalog helper remain identical, and the historical runtime never
calls that helper. The sequence was headless A/B/B/A/A/B, then windowed
B/A/B for each renderer, with five-second sample intervals and full features.
Report packaging rejects a baseline other than 300 independent mutable actor
catalogs or a candidate other than one shared read-only Main catalog.

Run serially from the dedicated worktree with clean tracked sources:

```powershell
(Get-Process -Id $PID).ProcessorAffinity = 15
$crowdRevision = (& git -c safe.directory=C:/rabbitlands/rabbitlands-client rev-parse HEAD).Trim()
$crowdReplay = @{
    OptimizedRevision = $crowdRevision
    BaselineRevision = '66f575ffe14f23153caa4920b2bfb47ccbc4f219'
    GodotPath = '.\godot-client\Godot_v4.7.2-stable_win64_console.exe'
    BaselineNativePresentation = 'All'
    CandidateNativePresentation = 'All'
    RelativePaths = @(
        'godot-client/src/app/main.gd'
        'godot-client/src/actors/replicated_actor_3d.gd'
    )
    SampleMilliseconds = 5000
    CpuSlotGranted = $true
}
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Headless -Renderer gl_compatibility -Sequence 'A,B,B,A,A,B' `
    -Label 'equipment-data-replay-headless'
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Windowed -Renderer gl_compatibility -Sequence 'B,A,B' -Capture `
    -Label 'equipment-data-replay-gl'
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Windowed -Renderer forward_plus -Sequence 'B,A,B' -Capture `
    -Label 'equipment-data-replay-forward-plus'
```

`-CpuSlotGranted` records an exclusive task-owned heavy-job handoff, not
permission to overlap task-owned engine jobs. Native setup remains in the
[extension README](../native/native_crowd/README.md).

## Measurement conditions

All task commands and their children use logical processors 0–3, affinity mask
15. Heavy engine/test jobs run serially with an explicit shared CPU-slot handoff.
The user-approved interference label remains:
`shared host; unrelated Godot jobs authorized; activity not continuously monitored`.
The high-end development host is not a midrange certification target. Native
presentation stays opt-in, the GDScript reducer is retained, and the shipping
renderer is unchanged. Headless scene time, windowed wall time, render CPU and
asynchronous GPU samples remain distinct measurements.

## Repository state and validation

The dedicated branch is `perf/native-crowd-300-benchmark`, in
`C:\rabbitlands\rabbitlands-client`. Its original fetched
`develop` base is `05596ec5cfb3c3a363b55973dbe8611af42eecbb`. The primary checkout
and local `develop` remain at `349600742f6cd7646ccbe28eb31d33bf2809a2e8`; their
existing working changes were not edited. No temporary agent worktrees were
created, and nothing was merged or pushed. The measured frozen commit is
`37b3c7a6a8c736a6499941d06f72aef27ed21d19`; later delivery commits contain
evidence/documentation only. The final response records the delivery SHA.

All twelve controlled cells and the separate attribution cell pass strict
report/process/affinity checks. Every controlled reversal restores the exact
candidate sources. The reviewer independently recomputed all twelve wall
means, p95, p99 and maxima, verified report/process hashes and exact registry
ownership, and inspected the eight selected captures. Focused helper,
shared-equipment, hand-prop, Main/crowd and existing equipment/combat checks
pass. Four PowerShell launchers parse successfully and whitespace checks pass.
All 102 file-reference records in the whole-scene bundle and all 30 candidate
source-manifest entries match their hashes.
These are scoped checks, not a claim that the entire historical repository
suite passes; the inherited armour-clearance failure documented in the prior
study remains outside this change.
