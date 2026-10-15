# Crowd presentation optimization follow-up

The later [native presentation follow-up](crowd-native-presentation-kernels.md)
records the capsule cache and optional native cape/flight kernels, including
a fresh controlled 300-actor comparison. The results below are historical.

The combined presentation cleanup reduced the primary workload's median
headless CPU proxy from **41.691 to 29.272 ms** in an alternating comparison,
with the optimized version faster in all three pairs. Rendered Forward+
observations improved by roughly 5–10%. **The 300-actor 60 FPS target remains
unmet.** Exact cape/geometry comparisons pass; the armour-clearance fixture
still fails with both the optimized and original solvers.

This follow-up continues the review branch `perf/native-crowd-300-benchmark`
from `4c42ab09f12844d5b9e370619c9be93b4f48033f`. The original study and its
historical evidence remain in [native-crowd-study.md](native-crowd-study.md).

The original fetched `develop` starting point was
`05596ec5cfb3c3a363b55973dbe8611af42eecbb`. All work remains in
`C:/rabbitlands/rabbitlands-client`. The user's primary
checkout and local `develop` are separate; nothing is pushed or merged.
Final read-only checks found both primary HEAD and local `develop` still at
`349600742f6cd7646ccbe28eb31d33bf2809a2e8`.

## Acceptance and method

The unchanged primary fixture contains 300 actors, 150 actually camera-visible,
and 100 active remote actors, with real equipment, overheads, animation and
combat effects. The objective is a complete rendered frame within 16.67 ms on
the intended midrange hardware. Headless scene timing is a CPU proxy, not a
rendered frame or an FPS certification. Renderer CPU and asynchronous GPU
timers must not be added to it.

All heavy local work runs serially with processor affinity mask 15 (logical
processors 0–3) and task-local user data. Shared-machine interference remains
explicitly labeled, as authorized by the user. Fresh before/after runs use the
same workload and native reduction disabled to isolate presentation changes.
The source manifest includes the presentation files under investigation.

The host has an Intel Core Ultra 9 275HX, RTX 5080 Laptop GPU with 16 GiB VRAM,
31.38 GiB system RAM, Windows build 26100.9457 and NVIDIA driver 591.91. Runs use
Godot 4.7.2 stable official (`ed1daf0bf`). This is a development laptop with a
high-end GPU, not a midrange target-machine certification. The earlier proposed
headroom gates remain 8 ms mean/10 ms p95 for the headless scene CPU proxy,
3/4 ms render CPU and 6/8 ms world GPU, evaluated independently rather than
added together. The final target still requires a synchronized 16.67 ms frame
measurement on the intended hardware.

Each retained optimization must have a correctness argument, relevant tests,
and measured performance or required measurement value. Feature removal is
diagnostic evidence only. Renderer and level-of-detail changes additionally
require visual review; preserving actor identity and combat timing takes
precedence over a faster benchmark.

## Investigation order

1. Snapshot cape collision inputs once per modifier pass, retaining constraint
   order and all output bone transforms. Compare to the previous solver over
   motion, turns, armour profiles, reset and teleport scenarios.
2. Measure effect geometry construction; remove redundant allocations and
   calculations while preserving vertices, UVs, colours and event timing.
3. Reassess Forward+ using the same full primary workload and existing rendered
   effect, equipment and overhead fixtures.
4. Investigate overhead draw batching and distant-actor detail only against
   the remaining measured bottleneck and their visual correctness constraints.
5. Consider a further native batch only where post-optimization measurements
   identify substantial custom arithmetic or submission overhead.

## Results

### Controlled final comparison

The final comparison uses the same uninstrumented harness at
`2386ee77adcacef7b20526df0e51b063f10c9196`, changing only the four presentation
scripts. A restores their original `4c42ab09f12844d5b9e370619c9be93b4f48033f`
versions; B uses the reviewed optimized versions. Native reduction remains
disabled. Every run is a fresh process with the full primary fixture, 5,000 ms
sampling and at least 60 frames. Source hashes identify the effective variant,
including the intentionally dirty A sources.

| Headless order | Variant | Mean ms | p95 ms | p99 ms | Maximum ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | A: original | 42.485 | 65.143 | 74.073 | 83.561 |
| 2 | B: optimized | 28.517 | 44.158 | 50.173 | 50.866 |
| 3 | B: optimized | 31.177 | 45.933 | 56.170 | 58.130 |
| 4 | A: original | 41.691 | 61.333 | 71.110 | 72.067 |
| 5 | A: original | 33.427 | 49.729 | 56.848 | 60.517 |
| 6 | B: optimized | 29.272 | 43.757 | 54.623 | 57.468 |

The optimized mean is lower in all three adjacent pairs: reductions of 32.88%,
25.22% and 12.43%. The median of run means falls from **41.691 to 29.272 ms
(29.79%)**. This supports a whole-scene CPU-proxy gain for the combined changes
on this shared host, with substantial drift and only three pairs. It does not
allocate that gain among the individual optimizations or certify another
machine. Both the mean and tails remain above the 16.67 ms target; the proposed
8/10 ms development-host CPU headroom gate is also unmet.

All six runs passed execution and fixture validation. The helper restored and
verified every candidate source byte with no restoration error. An earlier
setup-only attempt exposed PowerShell's empty-array argument binding before
any engine run. It is retained as rejected; exact candidate hashes were verified
before the corrected helper was committed and the entire sequence restarted.

The same frozen candidate then completed a windowed Forward+ B,A,B sequence:

| Forward+ order | Variant | Wall mean ms | p95 ms | p99/max ms | Render CPU mean ms | GPU mean ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | B: optimized | 52.194 | 73.073 | 86.099 | 5.455 | 1.701 |
| 2 | A: original | 57.676 | 76.246 | 83.401 | 5.521 | 1.710 |
| 3 | B: optimized | 54.906 | 74.632 | 92.927 | 5.660 | 2.160 |

Both optimized window means are lower than the intervening baseline (9.50% and
4.80%). This is descriptive rendered confirmation, not a precise FPS speedup:
window wall time includes compositor/host pacing, tails and GPU timings overlap,
and optimized p99 values are not lower. Draw calls remain essentially flat at
2,461–2,463. The unchanged rendering workload and focused CPU results support
the conclusion that this iteration saves presentation work, not draw calls or
visual detail. All three runs passed, and the candidate was restored with no
restoration errors. No diagnostic attribution observers were enabled in these
nine comparison runs.

The [controlled comparison evidence](benchmarks/native-crowd-optimization-reversal-2026-09-19.json)
retains ordered runs, paired ratios, all tails, source-variant manifests and raw
report/process hashes, including the rejected zero-run setup attempt.

### Fresh pre-change baseline

Six validated processes at measurement revision
`bfbe55a865445d648e76ab1d608e3ed8e6fe448e` establish the comparison: three
headless and three windowed Forward+ runs, native reducer disabled, 5,000 ms
samples with at least 60 frames. Source-manifest hash:
`621d55fe7d582da5b4488b4c118e918024783ab7c74c625c79f22d88c8bc3816`.

Headless per-process means were 47.277, 37.258 and 48.842 ms; the median of
means was 47.277 ms. Their p95 values were 76.179, 53.927 and 75.109 ms, and
p99 values were 83.515, 61.158 and 94.649 ms. Forward+ median render CPU/GPU
means were 6.136/2.221 ms, with about 2,461 draw calls. Its window wall median
was 68.402 ms, a compositor-paced observation rather than an isolated CPU
measurement. The spread requires repeated comparisons and rules out a precise
speedup claim from one run. No foreign Godot process appeared in the pre/post
inventories; activity was not continuously monitored.

The [portable pre-change evidence](benchmarks/native-crowd-optimization-prechange-2026-09-19.json)
retains all runs and tails. All twelve raw-report/process-sidecar hashes were
verified, and every process passed execution and fixture validation.

### Cape input caching

The original pass repeatedly queried the same anchor/body poses and twelve
static cape rests. The replacement caches rest transforms for the existing
rig-cache lifetime and snapshots the anchor plus seven unique body endpoints
before writing any cape bones. Torso, lumbar and leg constraints retain their
order, as do integration, forward-plane/height limits and all bone writes.
Helpers called separately still obtain fresh live poses. No animation-rate,
cloth-quality, collision, reset or teleport policy changes accompany this work.

The frozen previous solver is compared against the replacement on paired real
rigs. The test checks body-input equality and immutability, cloth current and
previous points, anchor state and all cape bone transforms to 1e-6. It covers
negative/zero/hitch deltas, actual walk and attack clips, translation and yaw,
midsequence bare/nonuniform armour reaches, teleport/reset and missing optional
body capsules. Existing cape-clearance and idle tests also pass.

Seven rotated focused trials of 1,500 calls each measured median per-pass cost
of **77.714 µs before and 61.712 µs after**, a 20.6% reduction. This is solver
cost on a settled pose, not a claim of a 20.6% whole-frame gain. The earlier
no-cape diagnostic also removed geometry and skinning, so it cannot be used
as the recoverable budget for this smaller change.

The six cape-only primary runs used revision
`6c05c388e4d22edcffabf03cf2d9e6043834d481` and source hash
`4f13da14792c063f01f75d287572e9aa5da8a723f2b1c8cbcda79de843d135eb`.
All passed fixture and process validation. Headless per-run means were
43.618, 30.630 and 38.632 ms (median 38.632); p95 values were 67.602, 44.036
and 59.893 ms. The median is 18.3% below the fresh baseline, but the ranges
overlap. Forward+ window wall means instead increased to 83.968, 68.916 and
85.779 ms (median 83.968). Render CPU/GPU median means were 6.198/2.440 ms;
draw calls and primitives stayed essentially unchanged. Even unrelated
presentation/ground timers moved between series. These contradictory timing
directions demonstrate temporal/shared-host drift: **retain the focused solver
gain, but do not claim an established whole-frame cape improvement**.

The [cape-only evidence](benchmarks/native-crowd-optimization-cape-cache-2026-09-19.json)
preserves those differences and all per-run tails. The final controlled
comparison alternates original and optimized presentation to improve
whole-scene attribution.

A later final-source audit identified that the first focused run preceded a
small early-return correction. Final-source parity was therefore rerun, with
ordered pairs retained in JSON. It passed and measured 82.209 to 71.122 µs per
call, a **13.5% reduction**. Both measurements are retained; the earlier 20.6%
result is not substituted for final-source evidence.

### Effect geometry emission

Revision `22ebcd1cd220fa52444034cf3931cf115bd882f7` removes temporary primitive
arrays and redundant per-vertex colour submissions from the shared combat mesh
helper and spell-flight builder. Arcs and ribbons reuse their shared adjacent
endpoint; flight distance-derived values update with `set_endpoints`, the same
existing boundary that updates trajectory axes. Release delay, duration,
arrival, fade, power scaling, camera-facing bases, materials and vertex order
are retained. There is no particle-density reduction or event dropping.

The windowed Compatibility parity test passed 281 cases against frozen
reviewed implementations. It compares actual nonempty mesh arrays (all array
slots and order) and material/shader state; expired effects have no surfaces.
Cases cover effect families, powers, moving/zero/vertical/short/distant paths
and camera rotations. Existing spell-flight and combat-presentation tests pass.
Initial test attempts exposed unsupported mesh-query APIs in the test itself;
the strict launcher rejected those attempts, including one whose script exited
zero after a runtime error. Only the corrected passing run is accepted.

Eight alternating focused CPU pairs showed:

| Focused workload | Baseline median | Optimized median | Reduction |
| --- | ---: | ---: | ---: |
| 240 primitive batches (lines, arcs, sparks) | 83.2495 ms | 43.7530 ms | 47.4% |
| 180 spell-flight draws with moving endpoints | 45.4995 ms | 29.1525 ms | 35.9% |

The optimized version was faster in every paired trial. These are headless
GDScript emission measurements, excluding GPU and complete presentation frame
rate. Geometry equality comes from the separate windowed parity test. The
original raw microbenchmark's `meshLastVertices`/`flightLastVertices` fields
contain analytical workload counts, not renderer measurements; the reusable
benchmark now names them `meshExpectedLastVertices` and
`flightExpectedLastVertices` and states that distinction explicitly.

The combined cape/geometry stage passed six primary runs with source hash
`beb9afa6397a3c0707311b469510cba3dd53867de2953245e898f26d6a32809f`.
Headless means were 37.600, 36.498 and 31.910 ms (median 36.498), with p95
59.753, 56.345 and 48.189 ms. One run retained a 100.912 ms p99 and 124.833 ms
maximum. Forward+ window means were 56.856, 60.201 and 70.137 ms (median
60.201), with p95 89.262, 80.677 and 101.499 ms. The median render CPU/GPU
means were 5.733/1.739 ms; draw calls remained about 2,462 and primitives
about 4.529 million. These medians are descriptively 22.8% and 12.0% below
the fresh pre-change headless/window series, but ranges and tails overlap.
These consecutive stage summaries alone do not establish a whole-frame gain;
the alternating final comparison provides stronger evidence.

All ordered runs and raw-file attestations are retained in the
[combined geometry-stage evidence](benchmarks/native-crowd-optimization-effects-geometry-2026-09-19.json).

The final focused run with corrected analytical-count field names also passed:
primitive construction was 40.82% lower and flight construction 45.88% lower.
These repeated focused gains support retaining the bounded implementation,
without claiming that one batch percentage applies to the entire scene.

### World-effect palette and resource attribution

The unchanged 20-entry palette table is now a constant instead of being rebuilt
on each lookup. All colours matched exactly for IDs -32 through 255. Windowed
comparisons also matched every actual detail-mesh array slot for effect IDs 0–5
at power 10 across five lifetime phases. There is no shared mutable material or
particle resource in this change.

Eight rotated production/reference trials measured 31.6355 to 9.4880 ms for
18,432 lookups (1.716 to 0.515 µs each). Complete detail emission measured
13.6785 to 12.3905 ms for 180 calls, a 9.42% reduction in that focused workload.
A prior staged-candidate run showed the same direction: 69.1% lower lookup cost
and 5.83% lower detail-emission cost. These results are small component gains.

A separate allocation probe used actual crowd effect IDs 0–5, powers 1/5/10,
local and flying effects, and area effects. Median-of-case medians were 6.5/7 µs
for local/flight instantiation, 70/82 µs for configuration and 1 µs for the area
mutation. Repeated drawing cost about 74.32 µs per detail call and 137.64 µs per
flight call before the palette relocation. Configuration occurs once per event;
drawing repeats across active frames. The probe therefore does not justify
introducing broad mutable resource caches as the next primary CPU intervention.

Thirty-two held effect-2/power-10 instances had distinct ring, detail, particle
process, quad and texture resources, with about 2.08/2.60 MB of diagnostic static
memory growth for local/flight cases. The resource-count monitor did not expose
these generated resources, so it is not used to claim zero allocations. Sharing
resources could help burst memory, but requires isolation for per-instance fades,
power changes and area-radius mutation. That redesign remains deferred.

### Final-source diagnostic attribution

Optional benchmark-only instrumentation times Main's `_process` and the
combat callback reached from `Skeleton3D.skeleton_updated`, records actual
process delta, and counts updates by actor/process-frame. The fixture has
additional bone-attachment callbacks after combat. Instrumentation therefore
snapshots the entire callback list, replaces combat in its original position,
and verifies every resulting callable, flag and ordering. Reference-counted
connections are rejected because their internal reference counts cannot be
reconstructed from the signal API. Preflight happens before any mutation, with
rollback on failure. Shipping scene code contains no instrumentation.

Two clean headless diagnostics at
`57909dd2b51749a117a419584cf9c60db36b4f16` retained the same mixed 300/150/100
fixture. They are single shared-host observations with observer/timer overhead,
explicitly excluded from acceptance summaries.

| Mean per sampled frame | Full presentation | Effects disabled (diagnostic only) |
| --- | ---: | ---: |
| Wall CPU proxy | 35.022 ms | 24.604 ms |
| Wall p95 | 57.130 ms | 39.057 ms |
| Main process delta | 34.995 ms | 24.616 ms |
| Main `_process` inclusive | 1.738 ms | 1.395 ms |
| Combat callback from skeleton signal | 4.082 ms | 3.396 ms |
| Skeleton updates / unique skeletons | 150 / 150 | 150 / 150 |
| Maximum updates per actor/process-frame | 1 | 1 |
| Live world effects, mean / maximum | 57.79 / 78 | 0 / 0 |

All 180 combat callback replacements had their order verified; 120 other
actors received passive observers. Exactly 150 skeletons updated per sampled
frame. Repeated skeleton signals are therefore not an established problem in
these runs. The 10.418 ms full/no-effects difference is consistent with effects
remaining a material cost, but is not a controlled speedup measurement or an
acceptable gameplay optimization. Main and delegated combat timers can overlap
with other measured work and must not be added to invent a CPU breakdown.
Effects disabled still exceeded 16.67 ms, so eliminating effects alone would
not meet the target even if that visual loss were acceptable.

Known immediate handler invocation counts are mirrored estimates, not a count
or timing of every pose update. The full fixture averaged 1.182 special and
1.182 animation handler estimates per frame, with 0.182 palette estimates.
Slower runs naturally receive more real-time events per frame; compare rates
and fixture contracts before treating per-frame count differences as a change
in workload. Process delta closely followed wall time in both primary runs.

The bounded 500-actor all-combat diagnostic was **rejected**, with exit code 2:
live effects reached 4,162, exceeding the 4,096 safety limit, after only 45
frames, also failing the 60-frame minimum. Its retained descriptive wall mean
was 743.754 ms, p95 1,112.460 ms and maximum 1,303.947 ms. Process delta instead
averaged 133.585 ms and reached at most 150 ms. Effects rose from 625 to 4,162;
packet dispatch averaged 236.248 ms and the skeleton combat callback 34.337 ms.
There were 451 unique skeleton updates per frame, still at most one per actor.

This shows simulation time lagging real-time event delivery under severe
overload, consistent with effects aging slowly while catch-up events continue
creating them. It does not establish that a single expiry change solves the
problem: packet catch-up, geometry work and aging interact. Before accepting
that stress case, separately design and verify overload behavior for effect
age/release/arrival and event backlogs. This iteration preserves those semantics
and does not silently drop events or shorten effects to make the benchmark
pass. The failed run is never folded into accepted averages.

The [portable diagnostic record](benchmarks/crowd-attribution-diagnostics-2026-09-19.json)
contains raw arrays, callback-order attestations and execution evidence.
Initial parse and overly restrictive callback-order attempts are rejected;
successful dirty instrumentation checks remain separately marked superseded.
Final admission tests pass 13/13 and prevent diagnostic timing from entering
ordinary acceptance summaries.

### Rendered correctness and remaining failures

The final optimized source passed cape-motion clipping, overhead banners, world
effects and spell exchanges in both Compatibility and Forward+. The geometry
parity suite also passed all 281 cases under Forward+, complementing its earlier
Compatibility pass. Those are nine passing checks out of the eleven final
renderer checks. Source hashes, process identities, affinity and logs are kept
with every result; no failed record is relabeled as a pass.

`rendered_cape_over_armour.gd` failed on all four armour bodies in both renderers
(exit 4). A separate subclass injected the frozen original cape solver before
its first update, preserving modifier position, influence, activity, process
mode and armour reach. Its guard verified untouched initial solver state, and
its frozen-source hash matched the original. Both reproductions also failed
with exit 4: Compatibility printed identical clearance measurements; Forward+
differed by roughly 1 mm on two sheet measurements, with all four bodies still
failing. The armour-clearance issue therefore predates pose caching. It remains
visible and unresolved; this is not an entirely green visual-regression suite.

Manual inspection covered paired world-effect impact, spell-contact, armour
and overhead captures, including original/current armour. The inspected
geometry and placements were consistent, while Forward+ changed lighting,
colour and particle appearance. These fixtures and exact mesh comparisons do
not constitute exhaustive pixel parity across every map and GPU. The shipping
Compatibility default remains unchanged; Forward+ remains the measured
performance candidate for a separate renderer rollout decision.

Representative final-source spell-contact captures are included for review:
[Compatibility](benchmarks/crowd-presentation-spell-contact-gl.png) and
[Forward+](benchmarks/crowd-presentation-spell-contact-forward-plus.png).
They are visual evidence, not frame-timing measurements.

The [final QA package](benchmarks/native-crowd-optimization-final-qa-2026-09-19.json)
retains 13 processes: nine passes, two optimized-source armour failures and
two original-solver armour failures. It attests 119 artifacts, including 62
captures, while retaining the exact failure output.

The static GDScript reference guard retains exactly the seven previously
documented inherited failure files, with no new group. Earlier protocol,
actor-facing and Sunmane-grounding failures remain documented in the
[original regression record](benchmarks/native-crowd-regressions-2026-09-19.json);
this presentation iteration does not claim to repair or rerun those unrelated
failing suites.

## Rendering review constraints

Overhead presentation lives in `ReplicatedActor3D`. Names, titles and health
numbers use fixed-screen-size `Label3D` nodes; health backing and fill use two
billboard quads. Their materials deliberately use different global render
priorities (backing 1, fill 2, number 3), with depth testing disabled. Folding
each actor's backing and fill into one draw would change the layer ordering
when banners overlap. It is therefore not an appearance-preserving one-line
batching change. A replacement must retain camera-orbit and zoom behavior,
left-anchored health depletion, zero/unknown-health rules, distance fade,
gameplay-only visibility layers and cross-actor overlap ordering. Dense banner
overlap makes that last case material to the primary fixture.

A viable future prototype would keep separate crowd-wide backing and fill
batches, retaining those global priorities, and leave names/numbers as existing
labels initially. It would need per-instance camera-facing, fixed-screen-size
placement and colour/fade state, plus overlap and zoom comparisons. That is a
render-submission experiment; it cannot be credited with removing the much
larger headless scene cost measured here.

Godot's [MultiMesh guidance](https://docs.godotengine.org/en/stable/tutorials/performance/using_multimesh.html)
also describes the loss of per-instance frustum culling; its tutorial is marked
not yet updated for 4.7. Any such prototype must verify the actual 4.7.2 behavior
and retain the benchmark's visible-actor contract, rather than assuming one
large batch is automatically beneficial.

The existing animation gate already provides full-rate, half-rate and paused
tiers with one-shot exceptions. Capes remain active in the half-rate tier.
Changing their frequency or authored meshes would require a separate visual
quality experiment; it cannot be counted as the gain from pose caching. The
300/150/100 primary fixture must continue to display all required actors.

For effects, a next bounded experiment would compare retained topology or
coarse array submission against the remaining repeated ImmediateMesh rebuilds.
This is an inference from the measured setup/draw difference, not an implemented
gain. Godot's [ImmediateMesh guide](https://docs.godotengine.org/en/stable/tutorials/3d/procedural_geometry/immediatemesh.html)
distinguishes small dynamic meshes from complex geometry and notes that
unchanged generated surfaces can be reused. A prototype must still reproduce
the current moving endpoints, camera-facing ribbons, powers, alpha, timing and
material state. C++ is justified only if the complete batch, including boundary
and upload cost, wins a measured comparison; engine animation and skinning are
already native.

## Architecture decision

Retain the four bounded presentation changes: cape input snapshots, shared
primitive emission, spell-flight emission and immutable palette lookup. They
have direct output comparisons and repeated focused CPU evidence. Keep the
existing native reducer opt-in; this iteration changes no native implementation,
protocol reducer, actor identity policy, animation tier policy or shader.

The measurements do not justify porting Main, ordinary visibility scheduling
or more dictionary state merely to obtain a native implementation. They also
do not justify broad world-effect resource sharing as the next CPU change.
The next performance experiments should address repeated active effect work
and residual cloth/animation cost, with whole-frame attribution and the current
parity fixtures. An effect batch should be compared with retained Godot geometry
before adding an extension boundary. A cloth batch must separately measure
constraint arithmetic and skeleton-output cost; the focused solver total is
not all recoverable arithmetic.

The retained focused timings and correctness provenance are in the
[focused evidence package](benchmarks/native-crowd-optimization-focused-evidence-2026-09-19.json).
It preserves both earlier and final-source measurements, including the slower
final cape result, rather than selecting the largest reported speedup.

Overhead batching is a subsequent render-submission experiment with the layering
contract described above. Distant mesh/cloth or animation changes require a
separate visual-quality study retaining race, armour, weapons, shield, selected
targets, local-player fidelity and one-shot cues. No diagnostic feature removal
in this report is an accepted gameplay mode. Overload aging/backlog behavior
also remains an explicit requirement before calling 500-combat scaling healthy.

The optional native DLL remains unchanged, with SHA-256
`b3af98d7c04702f59f14626dff1a71090f3b34da54dae4a1f61d87a2cb52bab1`.
Only four production GDScript files changed in this follow-up; the rest of the
deliverable is verification tooling, frozen references, evidence and this
report. The final review commit is reported in the task handoff; measured
source revisions remain explicit above.

Final evidence audit: all seven portable JSON files parse, and all 311 unique
referenced on-disk artifacts match their recorded hashes. All 35 raw
report/process source-hash pairs match, including separately classified
diagnostic/rejected records; that count is not a count of accepted timings.
The 195 final QA source-hash observations match current files, as do all four
focused/current production hashes and all four restored comparison hashes.
Markdown links, Python syntax, PowerShell syntax and Git whitespace checks
also pass. The task branch remains the review deliverable; no engine process
was left running by this work.

## Reproduction

Run from this task worktree. All engine invocations must share the task's
four-core allocation and execute serially. The launchers pin logical processors
0–3, request two workers, capture exact executable/source identities, and put
mutable user data under ignored `test-artifacts`. Keep the shared-machine label
when the host is not exclusive. The console executable resolves to its direct
sibling executable for process monitoring.

```powershell
$godot = 'C:/path/to/Godot_v4.7.2-stable_win64_console.exe'
& godot-client/scripts/run_crowd_benchmarks.ps1 `
  -GodotPath $godot -Profile primary -NativeBackend GDScript `
  -Mode Headless -Renderer gl_compatibility -Repeats 3 `
  -SampleMilliseconds 5000 -WarmupMilliseconds 1000 `
  -Label presentation-primary `
  -InterferenceLabel 'shared host; activity not continuously monitored'
```

Use `-Mode Windowed -Renderer forward_plus -Capture` for the rendered comparison.
`-Attribution` enables diagnostic Main/callback counters and process delta;
those timings include instrumentation overhead and are rejected by the ordinary
acceptance summarizer. Omit it for performance comparisons.

Focused parity and geometry measurements use the separate strict test launcher:

```powershell
& godot-client/scripts/run_presentation_checks.ps1 -GodotPath $godot `
  -Renderer gl_compatibility -Label presentation-parity `
  -Scripts @('res://tests/test_effect_geometry_parity.gd',
    'res://tests/performance/effect_palette_microbench.gd')

$env:ELORIA_CAPE_PERF = '1'
& godot-client/scripts/run_presentation_checks.ps1 -GodotPath $godot `
  -Headless -Label cape-paired `
  -Scripts @('res://tests/test_cape_cloth_pose_cache.gd')
Remove-Item Env:ELORIA_CAPE_PERF
```

The reversible comparison helper requires the complete candidate commit ID,
the exact task branch and a clean tracked worktree. It backs up exact candidate
bytes and switches only the four reviewed presentation scripts between the
historical reference and candidate. Before every switch it checks branch, HEAD,
tracked paths and hashes; unexpected concurrent content is never overwritten.
It restores and verifies the candidate in `finally`, retaining recovery copies
and a session manifest. All writers must be paused during the session.

```powershell
# Set this to the full resolved commit being reviewed; do not use a moving ref.
$candidateCommit = '<full-candidate-commit-id>'
& godot-client/scripts/run_crowd_reversal_benchmark.ps1 `
  -GodotPath $godot -OptimizedRevision $candidateCommit `
  -CpuSlotGranted -Mode Headless -Renderer gl_compatibility `
  -Sequence 'A,B,B,A,A,B' -Label presentation-reversal-headless

& godot-client/scripts/run_crowd_reversal_benchmark.ps1 `
  -GodotPath $godot -OptimizedRevision $candidateCommit `
  -CpuSlotGranted -Mode Windowed -Renderer forward_plus -Capture `
  -Sequence 'B,A,B' -Label presentation-reversal-forward
```

Here A is the original presentation and B is the optimized presentation. The
current measurement harness is identical in both variants; a baseline variant
intentionally has four dirty source files, identified by exact byte hashes.
The report's Git HEAD identifies the harness/candidate checkout, while the
reversal manifest identifies the effective runtime variant. It is not a claim
that the whole original checkout was rerun.
