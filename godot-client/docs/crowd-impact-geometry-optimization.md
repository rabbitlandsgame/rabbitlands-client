# Combat and impact geometry follow-up

Retaining unchanged bow geometry and enabling the optional native world-impact
builder reduced the primary workload's median of headless run means from
**23.666 to 21.114 ms (10.78%)**. All three paired means improved. Tail results
were mixed, and the rendered comparisons did not establish a consistent gain.
**The 60 FPS / 16.67 ms complete-frame target remains unmet.**

This study continues the isolated `perf/native-crowd-300-benchmark` branch from
`ef6825b92a468ff275a847cc063eed115695b1b5`. The previous
[native presentation study](crowd-native-presentation-kernels.md) retains its
separate before/after evidence; gains from different studies must not be
multiplied. The [original crowd study](native-crowd-study.md) retains the
population matrix and reducer decisions. This follow-up changes presentation
geometry only, with the GDScript reducer retained.

## Current bottleneck diagnostics

Two fresh processes used the unchanged production source, native cape and
flight kernels enabled, and the GDScript actor reducer. Each exercised the
same 300 actors, 150 camera-visible, 100 active fixture. They rotated the
order of full presentation, animation frozen, and effects disabled. Sampling
lasted five seconds after a one-second warmup, with at least 60 samples.

| Diagnostic | First process mean / p95 / p99 | Reversed process mean / p95 / p99 |
| --- | ---: | ---: |
| Full presentation | 23.992 / 37.654 / 45.283 ms | 23.827 / 40.226 / 44.880 ms |
| Animation frozen | 16.709 / 25.767 / 31.383 ms | 20.288 / 30.755 / 36.135 ms |
| Effects disabled | 17.293 / 25.707 / 32.315 ms | 19.955 / 31.645 / 41.103 ms |

Freezing animation reduced the mean by 3.539–7.283 ms in these two comparisons;
disabling effects reduced it by 3.872–6.699 ms. These are broad diagnostic
changes that remove visible behaviour, not candidate optimizations. They
overlap and must not be added. Full-scene means were stable, while the
ablations varied materially with order and host conditions.

The full fixture emitted exactly 150 skeleton updates per frame, with at
most one per actor. Freezing all AnimationPlayers still left 75 updates per
frame from active capes. Native cape calls stayed at 75 per frame in every
cell. Effects-disabled cells contained no world effects; full cells averaged
about 57–58 live effects. Event rates remained about 560–562 commands and
67.3–67.6 combat events per second. Native fallbacks were zero.

The complete combat callback cost about 3.50 ms per full frame, and still
2.92–3.28 ms with effect geometry disabled. This directs the next small
GDScript experiment toward repeated bow and prop work. Earlier focused
measurements also showed repeated world-effect detail construction cost
about 74 microseconds per call, justifying a separate coarse native geometry
experiment. The native path must preserve all effect branches, materials,
timing and geometry before scene measurements can qualify it.

The [diagnostic evidence](benchmarks/crowd-animation-effects-attribution-2026-09-19.json)
retains raw report hashes, source and process attestations, counters and
event rates. Diagnostic hooks add overhead and are excluded from ordinary
acceptance summaries. These measurements do not separately identify engine
animation evaluation, skeleton finalization or skinning cost.

## Changes and focused checks

### Retain unchanged bow geometry in GDScript

`RangerBow3D` caches the upper/lower limb nodes when loading an asset and
retains its string surface while the exact local draw point and flex are
unchanged. An asset change invalidates the cache. World transforms, aim,
smoothing, recoil calculations and arrow state still update every callback.
This change is enabled in the ordinary GDScript path.

The focused probe measures the complete combat callback, including its engine
calls. Eight trials alternate the frozen and current implementation. The
production Compatibility medians were 32.958 to 17.692 microseconds for an
idle equipped bow (46.32% lower), and 31.883 to 17.249 microseconds for a
stationary ranged hold (45.90% lower). Headless reductions were 40.82% and
40.30%. These fixed-pose focused measurements do not establish a whole-frame
gain, and differences in unchanged sword/casting paths are treated as noise.

Nineteen presentation scenarios matched the frozen implementation, including
casting, melee, ranged actions, disabled/hidden effects, rewinds, transitions
and equipment changes. A separate dynamic bow sequence covers changing world
poses, draw points and scale, release recoil, return to idle and a different
bow asset. The existing combat test passed across all 16 player rigs.
The [bow evidence](benchmarks/combat-bow-pose-cache-2026-09-19.json) retains
prototype and production results separately.

### Build complete world-impact detail surfaces natively

The optional `NativeWorldEffectGeometry.build()` constructs an entire effect's
detail surface in one call. It preserves radial marks, healing/ward/harm
shapes, contact sparks, area waves and every spell-specific shape branch.
Godot retains effect creation, anchors, clocks, lifetime, rings, particles,
materials and mesh submission. The default remains the existing GDScript path.

`ELORIA_NATIVE_PRESENTATION=world` enables this kernel alone; `all` combines it
with the existing cape and flight kernels. `both`/`1` still mean cape plus
flight. Missing native support retains the GDScript path, and a rejected build
permanently switches that effect instance to its original ImmediateMesh.
Benchmarks require active instances, successful calls and zero fallback calls.

The production probe measures complete construction, validation and submission.
Seven trials alternate implementations and exclude setup, mesh readback and
GPU completion. The timing workload uses effect IDs 0–5 at power 10; it does
not include ring, particle, flight or anchor work.

| Focused detail draw | Frozen GDScript | Native | Reduction |
| --- | ---: | ---: | ---: |
| Compatibility | 83.806 µs | 45.444 µs | 45.77% |
| Forward+ | 80.092 µs | 49.611 µs | 38.06% |
| Headless CPU | 75.447 µs | 36.719 µs | 51.33% |

The geometry comparison covers 18 effect IDs spanning every shape branch,
powers 1/3/5/7/10, progress endpoints and an intermediate phase, area effects,
flight contact and an unknown effect. A separate contract checks particle
counts at all ten power levels. Vertices, colours, array slots/order and
material properties match exactly in both rendered comparisons. Headless
readback is explicitly not authoritative. Production tests also check mode
selection, counters and exact GDScript fallback after injected malformed output.
The [native world-detail evidence](benchmarks/world-effect-native-geometry-2026-09-19.json)
records source/library hashes and rejected setup attempts separately.

Each focused production run recorded 2,520 successful native calls and no
fallbacks. Ten production checks passed across Compatibility, Forward+ and
headless execution, including the existing flight and cape contracts and all
eleven presentation-mode cases. The combined Windows x86_64 library is
981,504 bytes, SHA-256
`7321af0475b974313a15317ed6f9db459cf6e47146c5b5ff4ca983f74ccb5a1a`.
Linux build/runtime validation remains outstanding; the shipping renderer
and native opt-in default are unchanged.

## Controlled full-scene results

The frozen candidate is `5b7b2ae9b3d1669ded429738374a5f69f89807f8`.
Variant A restores the four changed runtime scripts from `ef6825b92a` and
enables native cape/flight (`Both`). Variant B uses the candidate scripts and
enables cape/flight/world (`All`). Both use the same final native library,
harness and GDScript actor reducer. The source reversal helper verifies every
changed runtime file is included and restores the original bytes afterward.
All three sessions restored successfully with no restoration errors.

Every acceptance cell keeps 300 actors, 150 camera-visible and 100 active,
including 150 fully equipped humanoids, normal animation, capes, overheads and
combat effects. Grounding checks match all 300 actors with zero height error.
The viewport is 1280 × 720, with a one-second warmup and five-second sample,
requiring at least 60 frames. Attribution hooks are disabled for these rows.
The [full-scene evidence](benchmarks/crowd-impact-geometry-results-2026-09-19.json)
contains source, library, report, process and capture hashes and all counters.

### Headless scene CPU proxy

The six separate processes run in A, B, B, A, A, B order. All times are ms.

| Run | Variant | Frames | Mean | p95 | p99 | Maximum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | A | 179 | 27.930 | 45.951 | 55.023 | 59.127 |
| 2 | B | 236 | 21.114 | 35.608 | 41.794 | 49.033 |
| 3 | B | 234 | 21.305 | 34.963 | 42.854 | 45.833 |
| 4 | A | 211 | 23.666 | 37.756 | 48.832 | 57.837 |
| 5 | A | 223 | 22.373 | 35.999 | 44.912 | 45.144 |
| 6 | B | 239 | 20.860 | 37.105 | 41.656 | 42.999 |

The median of run means is 23.666 for A and 21.114 for B. Pairing runs 1/2,
4/3 and 5/6 favors B for mean, p99 and maximum. The last pair's p95 worsens
from 35.999 to 37.105 ms. A drifts from 27.930 to 22.373 ms across the session,
so the first pair overstates the gain relative to later pairs. The 10.78%
summary describes this small shared-host sample, not a confidence bound.
The candidate still needs another 4.444 ms, or about 21%, just to bring this
CPU proxy's mean to 16.67 ms, before any midrange hardware headroom.

Command rates stay within 560.718–562.175/s and combat rates within
67.398–67.573/s. Every B run records successful world builds and zero native
fallbacks. Cape calls remain exactly 75 per frame in both variants. The census
contains 180 cape-compatible modifiers: 150 worn/configured native instances
and 30 dormant, unworn instances retaining the default GDScript backend label.
Only 75 visible worn capes simulate each frame; this is existing visibility
behavior, not a new reduction in fidelity.

### Rendered observations

Each renderer uses B, A, B order in separate windowed processes. These are
paced window wall measurements, not isolated scene CPU costs. Viewport render
CPU/GPU times are asynchronous measurements reported separately. All times
are ms; draw calls are frame means.

| Renderer / run | Wall mean / p95 / p99 / max | World CPU mean / p95 | World GPU mean / p95 | Draw calls |
| --- | ---: | ---: | ---: | ---: |
| Compatibility B1 | 52.757 / 74.354 / 90.303 / 90.303 | 17.312 / 21.907 | 15.615 / 19.222 | 3675.211 |
| Compatibility A | 50.540 / 66.791 / 68.761 / 68.761 | 16.401 / 18.909 | 14.549 / 16.190 | 3675.364 |
| Compatibility B2 | 61.847 / 87.728 / 96.733 / 96.733 | 20.430 / 25.476 | 18.497 / 22.875 | 3674.000 |
| Forward+ B1 | 44.757 / 65.632 / 71.304 / 88.863 | 5.796 / 7.481 | 1.701 / 1.831 | 2463.902 |
| Forward+ A | 44.496 / 63.881 / 66.165 / 68.829 | 5.657 / 7.243 | 1.699 / 1.828 | 2463.664 |
| Forward+ B2 | 40.346 / 57.293 / 61.361 / 63.250 | 5.199 / 5.908 | 1.696 / 1.817 | 2463.669 |

Neither renderer shows a consistent candidate gain; Compatibility B2 is
materially worse. These data do not establish whether that variation is host
interference or a renderer-side effect of the implementation. Keep the native
path opt-in and repeat rendered comparisons on a quiet target before any
rollout decision. The focused world draw gain and headless improvement justify
retaining the prototype, not a claim of better end-to-end rendered performance.
Rendered command rates remain 558.0–561.1/s and combat rates 67.08–67.44/s.

The reviewer inspected eight active/settled captures: B1 and A for both
renderers. Dense crowds, recognizable creature/equipped humanoid identities,
overhead names/health and active spell rings/sparks remain present. Settled
captures show expired effects. There is no obvious missing geometry or
equipment within a renderer. Captures have different simulation times and
cannot establish pixel or animation parity; exact focused array checks supply
the geometry evidence. Forward+ retains the previously observed brighter
ground and paler effects relative to Compatibility. The FPS overlays are not
used as timing evidence. All twelve captures remain hashed in the bundle.

### Resources and creation cost

The fixture has 7,350 mesh instances, including 1,500 skinned equipment nodes,
1,050 applied equipment visuals and no fallback equipment nodes. Rendered
samples contain about 20,590 nodes and 4.53 million primitives per frame;
171 resource objects remain stable. Live effects average about 57, peaking at
78. These changes do not consolidate draw calls or reduce the scene graph.

Candidate Compatibility spawn snapshots report about 1,229 MiB static memory,
367 MiB textures and 808 MiB video memory. Forward+ reports about 1,312 MiB,
422 MiB and 790 MiB respectively. These are Godot counters, not process RSS or
exclusive hardware allocations; video/texture/buffer counters overlap. Memory
after despawn retains caches and harness telemetry, so its delta is not a leak
measurement. Candidate creation of all 300 actors takes 6.37–6.57 seconds in
Compatibility and 10.17–11.63 seconds in Forward+, over 38 budgeted passes;
despawn takes 0.95–1.01 seconds. These are separate lifecycle observations,
not timed steady-state frames or improvements attributed to this patch.

## Remaining limit and next decision

A separate final attribution run on the candidate reports 19.856 ms mean wall
time, 33.136 p95 and 39.471 p99, with Main's inclusive callback at 1.082 ms and
the delegated combat skeleton callback at 2.567 ms. It still observes exactly
150 unique skeleton updates per frame, at most one per actor, and 75 native
cape calls per frame. All 6,722 flight and 9,802 world builds succeed with no
fallback. Attribution changes signal instrumentation and is excluded from the
acceptance aggregates; its lower wall result is not substituted for 21.114 ms.

The evidence supports these priorities:

1. **Resolve the remaining scene CPU cost.** Even headless exceeds the target.
   The final measured combat callback is substantial, while Main, overhead
   refresh (0.127 ms), grounding (0.075 ms) and command-only reduction (0.081 ms)
   are smaller in the attribution run. Inclusive/nested costs must not be
   summed. Obtain an engine-level CPU profile separating animation evaluation,
   skeleton finalization, skin/mesh updates and scene traversal before another
   native migration. The 150 skeleton updates are not duplicated, and the
   current counters cannot assign the unexplained remainder to animation.
2. **Reduce rendering submission and geometry cost.** Compatibility's measured
   world CPU and GPU each consume most or all of a 16.67 ms budget. Forward+
   substantially reduces those component observations, but render CPU remains
   5.2–5.8 ms and full window frames remain over 40 ms. Audit mesh/material and
   equipment consolidation while preserving identity and all near-actor detail.
   A custom crowd renderer should follow a measured prototype that reduces
   these costs, rather than follow from the native math results alone.
3. **Validate on a quiet midrange target.** Retain complete equipment, animation,
   overheads and effects, repeat alternating runs, and compare frame tails.
   Forward+ also needs a separate visual compatibility review before adoption.

The hybrid boundary remains appropriate for the measured improvements:
Godot owns actors, animation, skeletons, transforms, UI, effects and resources;
native code performs bounded coarse numerical/geometry operations. This study
does not justify a standalone client or a broad native actor rewrite. The
development-host gates remain 8/10 ms mean/p95 scene CPU, 3/4 ms render CPU and
6/8 ms world GPU, evaluated independently. The candidate fails the scene CPU
gate and both renderers fail render CPU; Forward+ passes the world GPU gate.
No claim of sustained 60 FPS is made.

## Reproduction and repository state

The task remains on `perf/native-crowd-300-benchmark` in
`C:\rabbitlands\rabbitlands-client`, originally based on
fetched `develop` commit `05596ec5cfb3c3a363b55973dbe8611af42eecbb`.
The primary checkout and local `develop` still point to
`349600742f6cd7646ccbe28eb31d33bf2809a2e8`; their existing changes were not
edited. No temporary subagent worktree was needed, and nothing was merged or
pushed. The measured runtime commit is `5b7b2ae9b`; subsequent commits package
evidence/documentation only. The delivery response records the final task SHA.

From the dedicated worktree, with a clean tracked tree and no other task-owned
heavy process, run the following. `-CpuSlotGranted` records the exclusive heavy
job handoff; it does not grant permission to overlap another heavy task job.
The helper requires the current full HEAD and a clean tracked tree. For a replay
from the delivered branch, verify its runtime bytes still match `5b7b2ae9b`;
the later evidence/documentation commits do not change them. Native setup is documented in the
[extension README](../native/native_crowd/README.md).

```powershell
(Get-Process -Id $PID).ProcessorAffinity = 15
$crowdRevision = (& git -c safe.directory=C:/rabbitlands/rabbitlands-client rev-parse HEAD).Trim()
$crowdReplay = @{
    OptimizedRevision = $crowdRevision
    BaselineRevision = 'ef6825b92a468ff275a847cc063eed115695b1b5'
    GodotPath = '.\godot-client\Godot_v4.7.2-stable_win64_console.exe'
    BaselineNativePresentation = 'Both'
    CandidateNativePresentation = 'All'
    RelativePaths = @(
        'godot-client/src/actors/cape_cloth.gd'
        'godot-client/src/actors/ranger_bow_3d.gd'
        'godot-client/src/world/spell_flight_3d.gd'
        'godot-client/src/world/world_effect_3d.gd'
    )
    SampleMilliseconds = 5000
    CpuSlotGranted = $true
}
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Headless -Renderer gl_compatibility -Sequence 'A,B,B,A,A,B' `
    -Label 'impact-geometry-replay-headless'
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Windowed -Renderer gl_compatibility -Sequence 'B,A,B' -Capture `
    -Label 'impact-geometry-replay-gl'
& .\godot-client\scripts\run_crowd_reversal_benchmark.ps1 @crowdReplay `
    -Mode Windowed -Renderer forward_plus -Sequence 'B,A,B' -Capture `
    -Label 'impact-geometry-replay-forward-plus'
```

All 12 controlled cells, two mode smokes and the separate final attribution
cell passed report/schema/process/affinity checks with no script errors.
The reviewer independently recomputed every controlled wall mean, p95, p99
and maximum from raw samples, verified all 53 referenced file records in the
final bundle and matched all 29 current source-manifest hashes. Documentation
links and whitespace checks pass. The summarizer's 34 unit tests, Python compile
check, both PowerShell parse checks, focused production contracts and the
existing 16-rig combat regression passed. Independent code reviews found no
actionable issues in the bow cache, native world builder or mode attestation.
This is scoped validation, not a claim that the entire historical test suite
passes: the previously documented armour-clearance fixture fails on both its
original and optimized implementations and remains outside this change.

## Measurement conditions

All task commands share logical processors 0–3, affinity mask 15. Engine
jobs and native builds run serially; builds use two workers. Every timing
run carries the user-approved label:
`shared host; unrelated Godot jobs authorized; activity not continuously monitored`.

The host is the same Core Ultra 9 275HX / RTX 5080 Laptop GPU system as the
previous study. Results are development-host observations, not certification
on a midrange target. Headless wall time is a scene CPU proxy; windowed wall
time includes host/compositor pacing. Render CPU and asynchronous GPU samples
are separate measurements, never summed with the wall samples.
