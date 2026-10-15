# Native crowd benchmark

For marker-bounded engine attribution with the normal animation schedule, see
[the engine profile workflow](crowd-engine-profile.md). The current
[Skin-sharing comparison](crowd-skin-sharing.md) records repeated full-workload
runs separately from instrumented diagnostic captures.

`tests/integration/crowd_benchmarks.gd` measures the existing actor pipeline at
100, 200, 300 and 500 actors. It keeps the local player inside that count,
builds actors through `Main._sync_world`, and drives movement and attacks through
the same `AppState` actor-command path used by network packets. The benchmark's
subclass of `main.gd` adds timers around presentation, grounding, overhead
health and animation-gate work; it does not change the shipping client.

## Run it

Run the PowerShell launcher from the repository root. It runs jobs serially,
pins the launcher and its children to logical processors 0-3, requests two
Godot worker threads, and places Godot user data and artifacts inside the
worktree.

```powershell
godot-client/scripts/run_crowd_benchmarks.ps1 `
  -GodotPath C:/path/to/Godot.exe -Profile primary -Mode Both `
  -NativeBackend Both -Renderer gl_compatibility -Repeats 3 -Capture `
  -Label acceptance
```

The `primary` profile is the acceptance fixture: 300 actors including the local
player, an even mixture of creatures and equipped humanoids, 150 actors whose
bounding spheres intersect the gameplay camera frustum while inside the 80 m
draw range, and 100 actors receiving movement or combat work. Equipped
humanoids wear real torso, legs, boots, helm, cape, weapon and shield assets.
The run fails if the node count, unique server-tile placement, sampled ground
height, camera-visible count, active workload count, or native-equipment
contract differs. The local player stays stationary in this fixture. The 100
remote active actors split into 50 moving and 50 fighting actors, which keeps
the gameplay camera and the streamed map region stable.

The other profiles are diagnostic:

| Profile | Coverage |
| --- | --- |
| `matrix` | 100/200/300/500 mixed actors at idle, one-third active, all moving and all fighting; half-frustum visibility. All-combat is a heavy scripted-spell stress case rather than ordinary gameplay density. |
| `features` | 300 humanoids with full equipment, bare bodies, no cape, effects disabled, overhead disabled, grounding disabled, and a diagnostic with actor AnimationPlayers frozen after normal gate classification. |
| `stress` | 500 mixed actors with normal and asynchronous command delivery, folded turn/attack packets, health/buff packets, unchanged wear packets, and alternating wear/unwear lifecycle packets. It also runs two 500-packet decode/reduce bursts. |
| `all` | Every predefined cell above. |
| `custom` | A Cartesian product selected with the launcher parameters below. Use narrowly. |

The launcher accepts comma-separated `-Counts`, `-Populations`, `-Activities`,
`-Visibilities`, `-Features`, and `-Networks`. These filter a predefined profile
or define the `custom` profile. Useful values are:

- populations: `creature`, `humanoid`, `mixed`;
- activities: `idle`, `move25`, `third_active`, `all_move`, `all_combat`;
- visibility: `concentrated`, `frustum_half`, `half300`, `range_bands`, `zoom`,
  `lod_bands` (300 actors only);
- features: `full`, `bare`, `no_cape`, `no_effects`, `no_overhead`, `no_ground`,
  `no_animation`;
- network: `normal_burst`, `asynchronous`, `folded_turn_attack`,
  `protocol_health_buffs`, `protocol_unchanged_gear`,
  `protocol_changed_gear_lifecycle`.

`-Attribution` is an optional diagnostic mode, off by default. It adds Main
process timing and delta, ordered combat-callback timing, per-actor skeleton
update counts and mirrored immediate-handler estimates. These measurements
include observer/timer overhead and are rejected by the ordinary acceptance
summarizer. They are not a complete engine animation/skinning profile. See the
[presentation follow-up](crowd-presentation-optimization.md) for diagnostic
results, strict presentation-test commands and the guarded old/new comparison
helper. Do not enable attribution when reproducing acceptance timing.

For example, this runs only the 100 and 500 actor all-move cells from the
standard scaling matrix:

```powershell
godot-client/scripts/run_crowd_benchmarks.ps1 `
  -GodotPath C:/path/to/Godot.exe -Profile matrix -Mode Headless `
  -Counts "100,500" -Activities all_move
```

The predefined `matrix` profile contains `all_combat` unless it is filtered.
That workload intentionally creates sustained spell effects and can fail the
sample-sufficiency or live-effect safety bounds. A default, unfiltered matrix
therefore can fail the whole profile by design. The accepted 12-cell scaling
matrix excludes that stress workload and can be replayed in the three measured
display/renderer configurations with:

```powershell
$runner = "godot-client/scripts/run_crowd_benchmarks.ps1"
$godot = "C:/path/to/Godot.exe"
$matrix = @{
  GodotPath = $godot
  Profile = "matrix"
  NativeBackend = "GDScript"
  Repeats = 1
  Counts = "100,200,300,500"
  Activities = "idle,third_active,all_move"
  Label = "final-matrix-coalesced"
}
& $runner @matrix -Mode Headless -Renderer gl_compatibility
& $runner @matrix -Mode Windowed -Renderer gl_compatibility
& $runner @matrix -Mode Windowed -Renderer forward_plus
```

Run the bounded all-combat cells separately so one rejected population cannot
prevent another population or display mode from producing an artifact. These
commands match the final stress fixture, including `frustum_half` at 300 actors:

```powershell
foreach ($count in 100, 200, 300, 500) {
  foreach ($mode in "Headless", "Windowed") {
    try {
      & $runner -GodotPath $godot -Profile custom -Mode $mode `
        -NativeBackend GDScript -Renderer forward_plus -Repeats 1 `
        -Counts ([string]$count) -Populations mixed -Activities all_combat `
        -Visibilities frustum_half -Features full -Networks normal_burst `
        -Label "final-combat-coalesced-$count"
    }
    catch {
      if ($count -ne 500) { throw }
      Write-Warning "Retained the rejected bounded 500-actor stress artifact: $_"
    }
  }
}
```

In the recorded 500-actor run, Godot exited with code 2 because the cell crossed
the 4,096-live-effect guard and consequently did not reach 60 frames. The
launcher correctly rejects that report. Its partial JSON is bounded overload
evidence, not accepted timing evidence; a replay is not required to fail at the
same point on another machine.

The focused feature repeats use opposite explicit cell orders, rather than
depending on dictionary or filesystem ordering:

```powershell
& $runner -GodotPath $godot -Profile custom -Mode Headless `
  -NativeBackend GDScript -Renderer gl_compatibility -Repeats 1 `
  -Counts 300 -Populations humanoid -Activities third_active `
  -Visibilities half300 `
  -Features "no_animation,no_effects,full,no_cape" -Networks normal_burst `
  -Label final-features-repeat-coalesced-a

& $runner -GodotPath $godot -Profile custom -Mode Headless `
  -NativeBackend GDScript -Renderer gl_compatibility -Repeats 1 `
  -Counts 300 -Populations humanoid -Activities third_active `
  -Visibilities half300 `
  -Features "no_cape,full,no_animation,no_effects" -Networks normal_burst `
  -Label final-features-repeat-coalesced-b
```

The remaining custom diagnostics use the same GDScript/full/normal-burst
boundary and request one headless and one Forward+ windowed run. `-Mode Both`
with one `forward_plus` renderer produces exactly those two artifacts:

```powershell
# One quarter of each population moves.
& $runner -GodotPath $godot -Profile custom -Mode Both `
  -NativeBackend GDScript -Renderer forward_plus -Repeats 1 `
  -Counts "100,200,300,500" -Populations mixed -Activities move25 `
  -Visibilities frustum_half -Features full -Networks normal_burst `
  -Label final-diagnostics-coalesced-move25

# 299 model-backed creatures plus the required local humanoid.
& $runner -GodotPath $godot -Profile custom -Mode Both `
  -NativeBackend GDScript -Renderer forward_plus -Repeats 1 `
  -Counts 300 -Populations creature -Activities third_active `
  -Visibilities half300 -Features full -Networks normal_burst `
  -Label final-diagnostics-coalesced-creature300

# Three distinct 300-actor visibility layouts.
& $runner -GodotPath $godot -Profile custom -Mode Both `
  -NativeBackend GDScript -Renderer forward_plus -Repeats 1 `
  -Counts 300 -Populations mixed -Activities third_active `
  -Visibilities "concentrated,range_bands,zoom" `
  -Features full -Networks normal_burst `
  -Label final-diagnostics-coalesced-visibility300

# Exact near/full, middle/half-rate and beyond-range/paused LOD bands.
& $runner -GodotPath $godot -Profile custom -Mode Both `
  -NativeBackend GDScript -Renderer forward_plus -Repeats 1 `
  -Counts 300 -Populations mixed -Activities third_active `
  -Visibilities lod_bands -Features full -Networks normal_burst `
  -Label final-diagnostics-coalesced-lod-bands
```

The creature preset uses the default 1 x 1 actor footprint and reserves unique
anchor tiles; it does not test multi-tile occupancy or collision. The fixture
selects a known actor but does not assert marker geometry, visibility, or marker
movement. Network stress validation is limited to decode/dispatch checks and
unchanged-gear identity, not authoritative gameplay outcomes for health, buffs
or changed equipment.
The zoom preset lays out a fresh population after changing camera distance, so
it is not a same-layout before/after culling comparison.

The `lod_bands` fixture fixes the camera at distance 32, pitch -25 degrees, yaw
0 degrees and a 50-degree field of view. Its initial census must contain exactly
100 actors at 0-45 m, 100 at 45-80 m and 100 beyond 80 m, corresponding to 100
full-rate, 100 half-rate and 100 paused animation tiers. Exactly 200 must remain
inside both the camera frustum and 80 m draw range throughout the validation
span. The exact tier assertion applies to the initial settled fixture. Timed
combat or movement can temporarily promote an actor for a one-shot animation;
the observed 101/99/100 post-workload split is valid and is not forced back to
the initial split by the summarizer.

`-Map none` removes map geometry for an actor-only diagnostic. Acceptance uses
Four Gates by default. `-SampleMilliseconds`, `-WarmupMilliseconds` and
`-CadenceMilliseconds` control real elapsed-time phases. Activity updates are
scheduled from the monotonic clock; a faster headless frame loop therefore
does not turn a nominal 100 ms server cadence into one packet per frame.
The asynchronous case dispatches one of ten groups every 10 ms at the default
cadence, so each actor still receives an update every 100 ms. Combat and effect
events remain on a 400 ms cadence in that case.

Driver version `deferred-coalesced-role-faithful-v2` leaves dirty actor IDs in
`AppState` for `Main` to consume through its normal deferred signal path. It
does not call `take_changed_actors` or `_sync_world` from the timed driver.
Catch-up ticks in one engine frame therefore coalesce into one presentation
pass, matching live network delivery. Every sample records actual benchmark-subclass
`sync_world_inclusive` calls in `raw.flushesPerFrame` and fails if a measured
frame has more than one. Dirty command traffic must also produce at least one
observed deferred flush.

Fighting actors repeat a four-role cycle: caster effect, ranged animation, and
two melee roles. Only the melee roles receive command 46 and folded turn
commands; caster and ranged roles receive their protocol presentation event
without a contradictory melee command. Priming sends command 18, waits one
process frame for deferred presentation, then sends the role-specific visuals.

`-NativeBackend Both` runs the same configuration first through the GDScript
actor-command reducer and then through the optional native reducer. A requested
native run fails if the extension did not load. `-Renderer` accepts
`gl_compatibility`, `forward_plus`, or both as a PowerShell array. Runs are
strictly serial. Each backend, renderer, display mode and trial gets a unique
UTC-stamped JSON, log, process-metadata file and screenshot name, so an A/B run
cannot overwrite its peer. The default is three trials per configuration.

`-NativePresentation` independently selects `Off` (default), `Cape`, `Flight`,
`Both` (cape and flight), `World` (impact detail geometry), or `All`. Keep
`-NativeBackend GDScript` when measuring presentation changes alone. Reports
verify active native instances, successful calls and zero fallbacks for every
requested component. Historical reports without world-detail attestation remain
readable but are grouped separately from reports with the newer counters.
See the [native extension options](../native/native_crowd/README.md#optional-presentation-kernels).

For source-reversal comparisons, `run_crowd_reversal_benchmark.ps1` accepts
`-RelativePaths` from a fixed runtime-file allowlist. Include every changed
runtime path, including `ranger_bow_3d.gd` when comparing bow caching. The runner
rejects an omitted changed path, requires a clean frozen revision and the
exclusive CPU slot, records both variants, and restores exact checkout bytes.

## Reading the report

Every cell records its exact requested configuration, spawn passes and time,
fixture census, separate frustum/draw-range counts and near/mid/far bands,
sampled surface matches, animation tiers, equipment and animation diagnostics,
per-component timings, renderer counters, and memory before spawn, after spawn
and after despawn. Timing series retain raw per-frame samples and summarize
mean, p50, p95, p99 and maximum. Screenshot capture and resource census occur
outside the timed interval. With `-Capture`, the primary 300-actor windowed run
writes settled and active PNGs for visual review.

The untimed `diagnostics.equipmentSkins` census distinguishes Skin resource
identity from exact ordered bind content. Per-actor totals show how many
different Skin resources and binds a skeleton may need to update, and how many
remain if identical contents are shared. The census does not expose Godot's
internal `SkinReference` count, register new bindings, or change resources.

`-EngineProfileMarkers` emits paired sample boundaries for an external engine
profiler while preserving the production animation schedule. The report records
the process ID, engine clock, process-frame counter, and diagnostic-only status;
the ordinary acceptance summarizer rejects these reports. Marker printing is
outside the sampled loop. See the [engine profiling setup](../scripts/engine-profile/README.md)
for the exact custom engine patch, capture tools, and trace analysis. Custom
engine timings must be compared with the same build, and nested inclusive zones
must not be added together.

Sampling continues until both the requested wall duration and 60 frames have
elapsed, subject to the greater of a 120-second or four-times-duration hard
bound for every population. A cell that
reaches that bound before 60 frames records `sampleSufficiency` as false and
fails report validation; it is excluded from performance evidence.

A sample also aborts and fails if live `WorldEffect3D` nodes exceed 4,096. The
report retains the partial frames, packet/event rates, effect counts, and an
`overloadAbort` reason. The guard stops runaway stress growth; it does not drop
effects or turn an overload into accepted frame-rate evidence.

The launcher records the commit, dirty state, requested and actual renderer,
backend activation, trial and process identity. Its composite source hash and
per-file hashes cover the benchmark, actor/state path, native reducer sources,
extension manifest and generated native DLL. It records `cleanExit` separately
from `abortedAfterReport`; the latter means the artifact was written but the
runner had to stop Godot after the five-second shutdown grace period. It applies affinity mask `0xF`
to the captured Godot process object. When given the Windows console binary,
it resolves and launches the sibling non-console executable directly; it does
not scan or modify other Godot processes by name. The companion process JSON
records the exact executable path, start time, observed mask, script-error
scan, and report-validation result. The two-thread
environment setting is recorded as a request because Godot exposes no runtime
worker-pool count; the four-CPU affinity is the enforced bound.

The primary, feature, matrix, combat and stress evidence reports retain the fixed
runtime composite source hash
`dcd930f19ce1ec9857c3b5a546b082aaf00a0ed4fa99ffea373d9d10d0311480`.
They also correctly record a dirty worktree because the tracked analytical
summary script changed while measurements were collected. Analysis and
documentation files such as that script and this guide are outside the runner's
runtime source manifest; the per-file manifest and fixed composite hash show
that the measured runtime inputs did not change. The reports should still be
described as dirty-worktree runs, not as a clean checkout.
The later `lod_bands` fixture changes the benchmark runtime source, so its
headless and windowed reports have a newer composite hash; those two reports
must match each other and carry their own per-file manifest.

Headless and windowed runs answer different questions:

- Headless removes Godot's idle sleep and reports wall time as a scene-tree CPU
  proxy. GPU, renderer and video-memory fields are `null` because the dummy
  renderer cannot measure them.
- Windowed runs use `RenderingServer` root-viewport and world-viewport CPU/GPU
  timers, draw calls and primitives. Window wall time is retained only as a
  diagnostic because the compositor and refresh rate pace it.

At an uncapped headless frame rate, a real 10 Hz packet can land in fewer than
one percent of frames, so the all-frame p95 or p99 may omit packet work. Reports
therefore include separate packet-bearing wall, presentation, grounding,
reducer and sync distributions, plus packet, actor-command, flush and combat
presentation event rates. Use those event distributions and frame maxima for
spikes. The generic headless percentiles remain a CPU-loop proxy.

`packetDispatchInclusiveMilliseconds` measures the complete `AppState` packet
dispatch, including synchronously emitted presentation handlers and effect
construction. `commandOnlyReduceMilliseconds` measures only the nested
`ADD_ACTOR_COMMAND` dispatch. The component timers overlap with these inclusive
packet timings, so they are attribution views rather than additive costs.

Do not add headless scene CPU to windowed renderer time to construct a frame
total. They come from separate executions. A windowed run also does not prove a
60 Hz end-to-end frame budget: compositor-paced wall time is not authoritative.
Use the renderer distributions, the headless CPU proxy, and a profiler capture
on the target machine as separate evidence.

The report marks the host as shared and records the interference label supplied
to the launcher. Compare repeated serial runs and treat small differences as
noise; the existing map study found that below roughly ten percent was not
distinguishable on this shared machine. The first population is prewarmed with
one equipped humanoid and one creature before cell baselines, so steady-state
cells do not silently mix cold glTF parsing with frame cost. Spawn cost remains
reported separately.

Before measuring a map or a population, the harness waits through a stable
window with no world cache write, continent-chunk worker, retirement queue,
or exterior-region worker pending. It records start/end scene node and resource
counts during the sample and counts live `WorldEffect3D` nodes separately, so
declared combat effects are distinguishable from late map or model loading.
Shutdown drains map workers before the scene and caches are released.

The component timers intentionally overlap: `syncWorldMilliseconds` is the
inclusive presentation flush, while `presentMilliseconds` excludes the timed
ground query. `animationGateMilliseconds` includes both the every-frame
half-rate advance and the periodic whole-population classification. The
remaining headless wall time includes animation, skeleton/skin work, physics,
camera and other scene processing. The benchmark-only clock reads themselves
remain in the measured frame, so component values are attribution aids rather
than a claim of zero instrumentation overhead.

The `no_animation` feature is a diagnostic bound, not an acceptance mode. It
keeps normal animation-gate classification, meshes, equipment, draw flags and
overhead nodes, then deactivates actor `AnimationPlayer` nodes after setup and
after gate or presentation updates. Its small benchmark-only freeze pass is
included in the animation-gate timer, which makes the inferred saving
conservative rather than an exact production animation cost.

The stress packet microbenchmark is explicitly a synthetic shape: 500
`ADD_ACTOR_COMMAND` frames with eight actor commands apiece, or 4,000 commands
over 24 seeded records. It reports decode-only and decode-plus-`AppState`
reduction distributions. It is not the older mixed 500-packet workload of
300 movement, 100 partial-stat and 100 chat packets, and the two results must
not be presented as the same workload.
