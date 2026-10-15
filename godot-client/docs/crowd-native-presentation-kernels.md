# Native presentation kernels: second crowd follow-up

The combined candidate (GDScript capsule cache plus optional native cape and
spell-flight paths) reduces the primary
workload's median headless scene CPU proxy from **29.601 to 24.328 ms
(17.81%)**. All three alternating pairs improved, including p95 and p99.
Rendered observations also favor the candidate, with overlapping tails and
shared-host interference. **The 60 FPS / 16.67 ms target remains unmet.**

The subsequent [combat and impact geometry study](crowd-impact-geometry-optimization.md)
adds bow-shape reuse and an optional native world-impact builder, with its own
controlled comparisons and current remaining-bottleneck assessment.

This study continues `perf/native-crowd-300-benchmark` from
`b90e4238b129f09808ca3743987b5bc8ce76b436`. The earlier
[presentation cleanup](crowd-presentation-optimization.md) and
[original crowd study](native-crowd-study.md) retain the historical population
matrix, reducer investigation and original acceptance evidence.

## Scope and method

The primary fixture remains 300 actors, 150 camera-visible and 100 active,
with equipment, overhead information, animation, capes and representative
combat effects. The desired result is a complete rendered frame below
16.67 ms. The viewport is 1280 × 720. Headless results measure a scene CPU proxy; windowed wall samples
include compositor/host pacing. Neither alone certifies sustained 60 FPS on
the intended midrange target. Render CPU and asynchronous GPU samples are
reported independently, not added to wall time.

All heavy local work runs serially on logical processors 0–3 (affinity mask
15); native builds use `--parallel 2`. All agents share that affinity limit.
Every run carries the user-approved label: `shared host; unrelated Godot jobs
authorized; activity not continuously monitored`.

The machine is the same Intel Core Ultra 9 275HX / RTX 5080 Laptop GPU host
with 31.38 GiB RAM, 16 GiB VRAM, Windows build 26100.9457, NVIDIA 591.91 and
Godot 4.7.2 stable official (`ed1daf0bf`). This is not a midrange hardware
certification. The development-host component headroom gates remain 8/10 ms
mean/p95 scene CPU, 3/4 ms render CPU and 6/8 ms world GPU, evaluated separately.

## Measured decisions

### Cache capsule invariants in GDScript

The cape solver computed each capsule axis and squared span repeatedly within
its three chains and two relaxation passes. Computing these once per modifier
pass preserves constraint order, floating-point operation order and bone
writes. Complete-modifier measurements against frozen `b90e4238b` fell from
61.495 to 56.433 microseconds (8.23%) across seven rotated paired trials. All
seven pairs were faster. Prior-solver parity and the existing cloth and
idle tests passed. This change is enabled in the default GDScript path.

### Reject the GDScript ArrayMesh rewrite

Moving spell-flight geometry into packed arrays in GDScript preserved exact
mesh arrays and material parameters but made the complete construction and
submission measurement slower: 6.53% windowed Compatibility and 9.92%
headless. That candidate remains a test fixture only. Mesh readback was kept
outside the accepted timed loop; an earlier instrumented attempt is retained
separately as rejected evidence.

### Measure the cape solver's scene contribution

A diagnostic disabled cape simulation while retaining equipped cape meshes.
It does not preserve animated cape presentation and cannot qualify as an
optimization or acceptance run. Two rotated full/off comparisons reduced mean
scene CPU by 20.7% and 6.0%; the median of run means was 31.570 versus
27.383 ms. One disabled run had a worse p95. This noisy shared-host evidence,
together with 75 active modifiers and the focused call cost, justified testing
an arithmetic-only native kernel. It does not justify deleting simulation.

### Prototype two coarse native operations

`NativeCapeConstraintKernel.step()` advances all three cape chains in one
call. It validates inputs, computes into local packed copies and publishes
point/history arrays only after the complete step. Godot retains the modifier,
animated skeleton reads, rest construction, clock, state ownership and bone
pose writes. A rejected call leaves point/history state unchanged for the
original GDScript fallback.

`NativeSpellFlightGeometry.build()` constructs one complete flight's ribbon
and glow geometry and returns six packed arrays. Godot retains endpoint
tracking, event timing, lifetime, materials, nodes and mesh submission. A
rejected result selects the complete original ImmediateMesh implementation
for that flight. World-effect rings, runes, particles and actor combat cues
remain in Godot.

These kernels do not add native actor storage, a new renderer, animation LOD
or new visibility rules. The existing native reducer is independently
selectable and stays disabled in presentation comparisons. The default
renderer remains Compatibility.

The native presentation paths are opt-in through `ELORIA_NATIVE_PRESENTATION`:
`0`/unset disables both; `cape`, `flight` or `both` selects the corresponding
kernel. Missing extensions retain the GDScript path. Benchmarks verify actual
native instances, successful calls and zero fallback calls, so requesting a
native path cannot silently count as measuring one. Build instructions and
the exact boundary are in the [extension README](../native/native_crowd/README.md).

## Correctness and focused performance

The production flight path passed exact mesh-array and material-parameter
comparison in Compatibility and Forward+, opt-in mode checks, call-counter
checks and an injected malformed-result fallback comparison. The broader
Compatibility flight probe covers effect branches, powers, cameras, endpoint
changes, zero-length/vertical/long trajectories, release, arrival and expiry.
Forward+ ran the representative effect-2 production contract rather than that
entire matrix. Timings
include native boundary calls, production output validation and mesh submission.
The rendered complete-draw median fell from 21,971.5 to 7,624 microseconds per
180 draws (65.30% lower); the headless result fell from 21,789.5 to 6,868
microseconds (68.48% lower). These are focused construction measurements,
not total frame or GPU improvements.

The native cape path passed comparison to the immediately preceding frozen
GDScript solver over the complete motion/reset/teleport sequence, checked
actual native use with zero fallback, and verified atomic malformed/read-only
input rejection and wrapper fallback parity. Existing cloth and idle tests
passed. Its interface-inclusive complete-modifier median fell from 70.569
to 28.400 microseconds (59.76% lower), a saving of 42.169 microseconds per
pass across seven rotated trials of 1,500 passes. Baseline drift between
separate experiments means these focused results must not be combined into
an invented aggregate speedup.

The cape point/history and bone comparisons use a `1e-6` tolerance; flight
mesh-array comparison checks exact values and order. The flight focused
timing used the flight-only library (`cd19c0e8…`). The final combined library
(`ae9db9a4…`) separately passed the flight contract in both renderers, cape
checks and reducer smoke tests, and is the library used in all scene runs.
Native build, load, parity and performance evidence is Windows x86_64 only.
The documented Linux x86_64 build path has not been validated in this study.

The existing armour-clearance fixture already failed with both original and
optimized GDScript solvers in the previous study; this is a known inherited
failure, not a claim that every repository test passes.

## Controlled primary results

The final measurement revision is
`0af09ba2e540e7696fc750815a7610c62a6cbda8`. A uses the prior
`b90e4238b129f09808ca3743987b5bc8ce76b436` cape/flight scripts with native
presentation off. B uses current scripts with both native kernels enabled.
Both use the same final harness and combined DLL, with the native actor
reducer off. The combat/world-effect scripts are Git-blob-identical between
variants; the reversal helper preserves their checkout bytes. It switches
only genuinely different source files and verifies exact restoration.

Every process uses 1,000 ms warmup, 5,000 ms sampling, at least 60 frames,
the full primary fixture and no diagnostic attribution hooks. All 12
controlled runs passed process, source, workload and native-activity checks.
All three reversal sessions restored the candidate without errors. There
were no native fallback calls. In B, 150 equipped cape instances had native
kernels, with 75 successful solver calls per sampled frame; existing
visibility gating is retained. Flight build attempts all succeeded. Headless
event rates remained about 560–562 actor commands and 67.3–67.5 combat
presentation events per second, with about ten coalesced state flushes per
second. Faster runs process more frames, not fewer gameplay events.

### Headless alternating comparison

All values below come directly from the raw report summaries, in milliseconds.

| Order | Variant | Mean | p95 | p99 | Maximum |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A: prior GDScript | 28.212 | 42.450 | 54.675 | 55.745 |
| 2 | B: native presentation | 25.392 | 40.912 | 48.552 | 50.594 |
| 3 | B: native presentation | 24.328 | 41.203 | 47.682 | 53.540 |
| 4 | A: prior GDScript | 29.601 | 46.554 | 58.556 | 60.563 |
| 5 | A: prior GDScript | 33.119 | 49.955 | 57.915 | 58.820 |
| 6 | B: native presentation | 23.372 | 36.309 | 45.666 | 50.260 |

The three adjacent-pair mean reductions are approximately 10.0%, 17.8% and
29.4%. The median of run means falls 17.81%; median p95 falls from 46.554 to
40.912 ms. Three pairs on a shared host support retaining the combined
changes, but do not establish a precise universal speedup or assign all gains
to either kernel. The comparison also includes the GDScript capsule cache.
Packet-bearing frames remain more expensive: candidate mean wall times are
32.559, 31.183 and 29.924 ms versus baseline 34.133, 36.185 and 39.701 ms.

The preceding same-source four-mode screen was valid in every mode:

| Sequential screen | Mean ms | p95 ms | p99 ms |
| --- | ---: | ---: | ---: |
| Off | 29.480 | 45.651 | 57.917 |
| Cape only | 27.708 | 45.994 | 58.985 |
| Flight only | 25.268 | 37.694 | 46.710 |
| Both | 23.366 | 36.151 | 46.866 |

This screen verifies component selection and execution. Its fixed order and
host drift prevent using its differences as independent causal allocations.

### Rendered B/A/B comparisons

Windowed wall time is compositor-paced diagnostic evidence. World render
CPU and GPU are asynchronous viewport timers; they are not an additive
breakdown of that wall time. Each row retains the same actor/equipment fixture.

| Renderer/order | Variant | Wall mean | p95 | p99 | Maximum | World CPU mean | World GPU mean |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Compatibility 1 | B | 65.886 | 94.954 | 113.988 | 113.988 | 20.152 | 18.129 |
| Compatibility 2 | A | 69.783 | 94.984 | 103.123 | 103.123 | 20.029 | 18.047 |
| Compatibility 3 | B | 61.462 | 78.835 | 93.628 | 93.628 | 18.933 | 17.028 |
| Forward+ 1 | B | 46.864 | 60.970 | 79.628 | 90.266 | 5.830 | 1.699 |
| Forward+ 2 | A | 57.132 | 76.154 | 84.004 | 84.004 | 5.797 | 1.714 |
| Forward+ 3 | B | 47.268 | 69.878 | 80.322 | 84.706 | 5.303 | 1.704 |

Both candidate means are below the intervening baseline in each renderer:
5.6–11.9% for Compatibility and 17.3–18.0% for Forward+. This is descriptive
confirmation, not synchronized FPS certification. The first Compatibility
candidate's p99/maximum is worse than baseline, and both Forward+ candidate
maxima are higher than baseline. The native paths primarily reduce CPU
construction work; these results do not demonstrate a repeatable GPU gain.

Draw calls remain about 3,674 in Compatibility and 2,460–2,463 in Forward+;
both submit approximately 4.529 million primitives. Small differences track
sampled effect phases. No geometry, actor, equipment or overhead category is
removed by the native optimization. Compatibility world CPU and GPU remain
above 16.67 ms independently. Forward+ substantially lowers these rendering
costs, but scene CPU and frame pacing still miss the target.

### Other component and resource observations

Headless median per-frame means, including frames without network packets:

| Measured operation | A ms | B ms |
| --- | ---: | ---: |
| Actor presentation excluding grounding | 0.750 | 0.599 |
| Ground sampling | 0.125 | 0.107 |
| Command-only reduction | 0.131 | 0.100 |
| Inclusive packet dispatch | 0.522 | 0.417 |
| Inclusive world synchronization | 1.232 | 1.096 |
| Overhead update logic | 0.206 | 0.170 |
| Animation-gate scheduling | 0.274 | 0.258 |

These operations were not independently optimized in this stage. Per-frame
averages change as frame rate changes; packet-bearing summaries and event
rates are retained in the portable evidence. Inclusive measurements overlap
and must not be summed. Animation-gate time does not measure skeleton
evaluation or skinning.

All runs instantiate the same 19,874 scene nodes before timed effects. Native
cape instances add approximately 150 objects, not actor scene nodes. Spawned
static memory is approximately 1.576 GB headless, 1.288 GB Compatibility and
1.375 GB Forward+ in both variants. Renderer-reported video memory is
approximately 845–847 MB in Compatibility and 828 MB in Forward+, with
texture memory about 385 MB and 443 MB respectively. These engine monitors
are not total device VRAM usage. Headless video-memory values are unavailable.

The 300-actor spawn still takes 38 budgeted passes: roughly 4.3–4.8 seconds
headless, 6.2–6.8 seconds Compatibility and 10.1–10.8 seconds Forward+.
Despawn takes roughly 0.9–1.1 seconds. These include waits/resource setup and
are not isolated allocation timings. Post-despawn retained telemetry and
caches are reported explicitly; they are not a leak measurement. This stage
does not claim a spawn or memory improvement.

## Remaining bottleneck and next decision

A separate final-source Both-mode headless diagnostic passed at 23.769 ms
mean / 36.341 ms p95. Its inclusive Main callback averaged 1.285 ms, the
skeleton-triggered combat callback 3.423 ms, actor presentation 0.585 ms and
world synchronization 0.979 ms. There were exactly 150 skeleton updates and
150 unique skeletons per sampled frame, with at most one update per actor.
It verified zero native fallback, 75 native cape calls per frame and 5,624
successful flight builds over the sample. Timer/signal instrumentation makes
this a diagnostic, not a further acceptance observation.

The evidence supports the following order:

1. Retain the combined candidate for review and integration testing. Focused
   tests support both native kernels, and the combined candidate improves the
   full CPU workload without changing actor identity, animation schedules or
   gameplay event timing. The controlled gain also includes the GDScript cache.
2. Profile the remaining scene/engine CPU with the kernels enabled, especially
   the measured 3.4 ms combat callback, world-effect detail construction and
   skeleton/animation evaluation. The current instrumentation does not
   separate all of these costs. A new native boundary requires a measured
   complete-call saving and another alternating primary comparison. Repeated
   skeleton signals and packet decoding are not supported as the dominant
   current problem.
3. Continue Forward+ platform and visual validation. It offers much lower
   measured rendering cost here. The captures also show renderer-dependent
   ground lighting and effect brightness in both variants, so this evidence
   alone does not authorize changing the shipping renderer or art settings.
4. If submission remains limiting, test a compound health bar as a separate
   reversible experiment: merge backing/fill into one surface while retaining
   both text labels, dimensions, health thresholds, fades and visibility. The
   source suggests roughly 149 fewer draws, not the roughly 900 draws removed
   by the older all-overhead ablation. Require rendered correctness and a
   repeated CPU/GPU improvement; a lower draw count alone is insufficient.

The hybrid Godot/native boundary is justified, but it is **not yet sufficient
for the target**. Neither a custom crowd renderer nor a standalone client is
justified by this study. CPU sampling and renderer validation should precede
changes to animation fidelity or distant actor detail. The development-host
8/10 ms scene CPU and 3/4 ms render CPU headroom gates remain unmet;
Forward+ passes the 6/8 ms GPU gate on this host, which does not certify a
midrange GPU.

## Visual review

Eight full-scene captures were inspected: A2/B3 active and settled views in
both renderers. Actor silhouettes, equipped capes/armour, labels, health bars
and spell effects remain present. Effects expire in settled captures.
Snapshots occur at different animation/effect phases, so they are not pixel
parity tests or measurements of FPS. Deterministic mesh-array and cape-pose
tests provide the corresponding numerical checks. No new missing geometry
or equipment was observed; the inherited armour-clearance failure remains.

## Evidence and reproducibility

Portable evidence includes:

- [GDScript cape cache and solver diagnostic](benchmarks/crowd-cape-capsule-and-solver-diagnostics-2026-09-19.json).
- [Rejected GDScript ArrayMesh candidate](benchmarks/effect-arraymesh-flight-negative-2026-09-19.json).
- [Native flight production checks and focused timing](benchmarks/effect-native-flight-production-2026-09-19.json).
- [Native cape checks, focused timing and final library checks](benchmarks/native-cape-constraint-kernel-2026-09-19.json).
- [Controlled primary results, diagnostic and captures](benchmarks/crowd-native-presentation-results-2026-09-19.json).

Raw logs, process manifests, source/library hashes and captured arrays live
under the task worktree's ignored `godot-client/test-artifacts` directory.
Independent review verified 132 referenced artifact hashes across the five
portable evidence files and recomputed all six headless means from raw samples.
Failed attempts remain separate from accepted measurements. A native build
initially failed before compiling the candidate because its process lacked
the MinGW runtime directory in `PATH`; prepending that directory locally as
documented resolved the failure. No machine-wide compiler setting changed.

The first screen was rejected before measurement for a harness reflection
parse error. The first reversal setup was rejected for rewriting line endings
in blob-identical files. Both were fixed, committed and restarted; neither
failed attempt contributes to accepted timing. The earlier reducer smoke
attempt with a process-monitor race is likewise excluded and was rerun with
verified process identity. Final summarizer contract tests passed 29/29,
including native request/activity, counter-delta, process-mode consistency,
mixed-mode aggregation rejection and diagnostic-exclusion checks. The final
postprocessor at `ca8b402c0ae05eceda3e558a2a80d6c07693ce3b` independently
validated all 12 controlled report/process pairs, all four mode-screen runs
and 18 historical runs. It preserves explicit legacy/unattested labeling.

From the task repository root, after building the extension as documented:

```powershell
(Get-Process -Id $PID).ProcessorAffinity = 15
$godot = "$PWD/godot-client/Godot_v4.7.2-stable_win64_console.exe"
# One primary run; launches directly with isolated user data and affinity 15.
& ./godot-client/scripts/run_crowd_benchmarks.ps1 -GodotPath $godot `
  -Profile primary -Mode Headless -Renderer gl_compatibility `
  -NativeBackend GDScript -NativePresentation Both -Repeats 1 `
  -WarmupMilliseconds 1000 -SampleMilliseconds 5000 `
  -Label native-presentation-review `
  -InterferenceLabel 'shared host; unrelated Godot jobs authorized; activity not continuously monitored'
```

To reproduce the controlled experiment, use a clean task worktree at the
measurement revision (or a reviewed descendant with the same candidate),
while holding this task's exclusive heavy-execution slot:

```powershell
$candidateRevision = (git rev-parse HEAD).Trim()
& ./godot-client/scripts/run_crowd_reversal_benchmark.ps1 `
  -GodotPath $godot -OptimizedRevision $candidateRevision `
  -BaselineRevision b90e4238b129f09808ca3743987b5bc8ce76b436 `
  -BaselineNativePresentation Off -CandidateNativePresentation Both `
  -Mode Headless -Renderer gl_compatibility -Sequence 'A,B,B,A,A,B' `
  -SampleMilliseconds 5000 -Label native-presentation-review-reversal `
  -CpuSlotGranted
```

Run windowed comparisons serially with `-Mode Windowed -Sequence 'B,A,B'
-Capture`, once per renderer. `-Attribution` belongs on a separate direct
benchmark run and is excluded from acceptance summaries. Source variants,
environment flags, effective file hashes, final library hash and per-process
identity/affinity are recorded automatically. A reader must build the ignored
native library; the repository does not make it a mandatory client dependency.

## Repository isolation

The original fetched `develop` starting commit was
`05596ec5cfb3c3a363b55973dbe8611af42eecbb`. All work is confined to
`C:/rabbitlands/rabbitlands-client` on
`perf/native-crowd-300-benchmark`. No push or merge is part of this work.
No temporary subagent worktrees or branches were created in this follow-up.
The final validated runtime/harness commit is
`0af09ba2e540e7696fc750815a7610c62a6cbda8`; later commits harden summary
validation and package evidence and this report. Final read-only checks found
the primary checkout HEAD and local `develop` still at
`349600742f6cd7646ccbe28eb31d33bf2809a2e8`. The primary checkout contains user
changes; this task did not edit or reset them. The final delivery commit is
recorded in the task response.
