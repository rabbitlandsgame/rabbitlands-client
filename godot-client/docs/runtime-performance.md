# Client runtime performance

## Linux GPUs with limited video memory

The 2026-10-30 Linux release was measured on a 2 GiB Quadro K620 with NVIDIA
580.178.04. The affected live session ran at 6–7 FPS with Forward+, high quality
and full map textures; reported graphics allocations reached about 2.2 GB and
the driver reported 1983/2048 MiB occupied at 100% GPU utilization. Switching
quality during that session did not activate the half-resolution map textures:
the diagnostic `map_texture_mip_skip` remained zero until restart.

For affected machines, use **Settings → Graphics → Apply Performance preset**,
then close and reopen the game. The preset now changes Linux's Automatic
renderer to OpenGL Compatibility, in addition to its existing lower quality,
half-resolution map textures and 75% 3D resolution. Explicit renderer choices
are preserved; if Forward+ was selected explicitly, select OpenGL Compatibility
manually before restarting. The texture and renderer changes both require a
restart. This does not change Automatic or quality defaults for other players.

An isolated comparison using the installed release's PCK/assets and matching
Godot 4.7.2 editor engine loaded Landfall at focus `(-151.5, 121.6142, 33.5)`,
camera distance 9 m and pitch −24°, with a 941×1030 compositor-sized window.
After 45 seconds settling, 120 frames at low quality and half map textures
averaged 11.17 ms with OpenGL versus 18.97 ms with Vulkan. Both submitted
1,038,514 primitives; reported graphics allocations were 344 MB versus 767 MB.
These are terrain-only measurements with no server actors or character-creation
history, and do not reproduce the full live session or qualify all Linux GPUs.
The update-notice UI was visible in these runs. Full textures/high quality under
Vulkan averaged 25.75 ms and 952 MB in a separate terrain-only run.
See [the measurements](../../docs/qa/linux-low-vram-2026-10-30.json).

`tests/test_low_end_graphics.gd` checks preset persistence, the Linux OpenGL
launch arguments and preservation of explicit renderer choices. All 46 checks
passed headlessly against the modified source and installed resource dependencies.

## First-use camera rotation on Compatibility

The follow-up online session reached 51–56 FPS but still hitched while turning.
A three-turn offline reproduction at `(-220.5, 121.357, -2.5)`, distance 14 m,
pitch −60°, isolated the first-use cost: the first turn paused up to 2621 ms,
while the third turn's longest frame was 12 ms. Instrumented gameplay-script
stages stayed below 1 ms during those pauses. This implicated first-use render
work rather than the camera-input handler or continuous script load.

`camera_shader_warmup.gd` now renders representative views through a temporary
camera while the arrival curtain is opaque. It covers two pitches and a full
orbit in 3° steps, requiring two actual drawn frames per view. Occluder probes
use that camera too, preparing first-use triangle data and fading materials.
The gameplay camera's transform and saved framing are untouched. Completion
restores the gameplay camera and releases temporary scenery fades before the
curtain lifts and the server receives `#arrived`. Cancellation, map changes,
cutscene camera takeover and a 20-second limit all release the temporary camera.
Forward+ and headless runs skip this pass. No prepared-content format changes.

With one synthetic local actor and ordinary arrival/occluder handling, a matched
control's first turn peaked at 75.38 ms. The final warm-up took 5865 ms during
loading; the next three 360-frame turns peaked at 12.88, 13.81 and 12.73 ms,
with no measured frame above 33.3 ms. Godot user/shader-cache roots were isolated
per run, but NVIDIA's driver cache was shared. The earlier 2621 ms cold run is
diagnostic evidence, not a matched cold-cache speedup claim. Large online crowds,
other locations and other Linux GPUs have not been qualified by this probe.

Run `tests/integration/camera_rotation_probe.gd` with a rendered Godot 4.7.2
engine, isolated `XDG_DATA_HOME`, `ELORIA_CAMERA_PROBE_USER_ROOT` pointing to that
root, and `ELORIA_CAMERA_PROBE_REPORT` naming an output JSON file. It simulates
arrival without contacting a game server. `ELORIA_CAMERA_SHADER_WARMUP=0` selects
the control. `tests/test_camera_shader_warmup.gd` checks draw accounting,
restoration, cancellation, far teleports, camera takeover and the timeout.

### Reducing warm-up loading time

The selected pass retains all 240 views and both draws per view. It temporarily
removes the process frame cap and window VSync, draws through a shared-world
offscreen SubViewport with a maximum side of 192 pixels, and suspends the normal
3D SubViewport while doing so. The temporary viewport preserves aspect and the
camera's projection, layers and environment, copies MSAA/scaling/shadow settings,
and disables mesh LOD reduction for its draws. Completion and cancellation restore
the normal viewport's update mode, the player's frame cap and window VSync.
The gameplay camera remains current in its original viewport throughout.

Sequential offline trials on the same K620, with a 60 FPS arrival cap, measured:

| Warm-up configuration | Warm-up | Total arrival | Worst rotation frame |
| --- | ---: | ---: | ---: |
| Full viewport, capped, two draws | 8.45 s | 17.04 s | 16.08 ms |
| Full viewport, uncapped, two draws | 5.04 s | 13.64 s | 13.88 ms |
| Small viewport, uncapped, two draws | 4.14 s | 12.74 s | 14.50 ms |
| Selected configuration, repeat | 4.23 s | 12.86 s | 14.15 ms |

The selected pass also completed three shallow-angle rotations with no frame
above 22.45 ms, and restored VSync On and the 60 FPS cap. One draw per view was
faster but reintroduced shallow-angle hitches up to 106.93 ms, so it was rejected.
A preliminary 24-view pass overlapping chunk loading, followed by the full
two-draw pass, saved only 0.16–0.29 s overall; that scheduling experiment was
removed. Shader/mesh/light/fade variant deduplication remains unqualified.

The small viewport submitted up to 349 visible draw calls in the repeated trial;
it was not an undrawn placeholder. Native-resolution screenshots after warming
confirmed restoration of ordinary world rendering. See [trial data and
limitations](../../docs/qa/warmup-load-trials-2026-10-30.json). These are one-actor,
one-location measurements with isolated Godot profiles and a shared NVIDIA driver
cache. Full online crowds and other GPUs still need separate qualification.

Diagnostic controls retain comparisons: `ELORIA_CAMERA_WARMUP_UNCAP=0` preserves
the arrival cap, `ELORIA_CAMERA_WARMUP_VIEWPORT=screen` uses the original viewport,
and `ELORIA_CAMERA_WARMUP_FRAMES=1` reproduces the rejected single-draw trial.
The rotation probe accepts `ELORIA_CAMERA_PROBE_FPS`, `ELORIA_CAMERA_PROBE_PITCH`
and `ELORIA_CAMERA_PROBE_VSYNC=on`, and records cap/VSync restoration before
uncapping its measured rotations.

## Startup diagnostics

The rotating client log includes `startup_stage` records with a stage name,
duration in milliseconds, and elapsed time since engine startup. These cover
geometry preparation, catalogues, interface construction, fixed creation
defaults, art, preferences and final setup. `startup_deferred_stage` measures
the three deferred workspace setups. On graphical launches, `login_first_frame`
records the first completed draw and the time since `main_scene_ready`.
Compare both milestones: deferred theme work can delay drawing after setup
has finished. Source launches also include script compilation and asset loading;
compare equivalent source or exported builds with the same settings.

`startup_window` records split interface construction into a fixed set of window
names. The settings window does not inventory map-cache files during startup.
It counts them on a cancellable read-only worker when settings opens, publishing
the result on the main thread. Closing settings cancels that count; clearing
caches stops it before deleting files and starts a new count afterward.

Character creation starts with fixed Human Male choices. Its 3D preview is
constructed when creation opens and reused when reopened without changes.
Appearance and starting-equipment changes update that same preview actor;
changing its body model or actor type creates a new one. Select its graphics
quality before configuration to avoid building an intermediate tier.
Build the complete shared theme before installing it on the interface, and
publish live text-colour changes together to avoid repeated tree invalidation.

High-head GLB parsing can continue on workers during play. Speculative texture
uploads and the bulk head/hair/beard pipeline warm-up publish only on login or
behind a drawn, blocking loading curtain. Creation editing and ordinary play
defer that work. An already-started pipeline warm-up settles before arrival
releases input; pending work alone does not extend the curtain. Diagnostics
include `rl_head_warmup` state. `RL_HEAD_PIPELINE_PREWARM=0` skips only the bulk
pipeline stage for controlled investigations, retaining ordinary resource use.

## Reproducible performance checks

Run `tests/integration/run_crowd_presentation_benchmark.py` from `godot-client`.
Use explicit quality, renderer, resolution, frame cap and minimap choices for
comparisons. For example, a source-project screening run is:

```powershell
python tests/integration/run_crowd_presentation_benchmark.py --godot <Godot.exe> --variants all --cells phase1 --mode windowed --renderer gl_compatibility --quality low --resolution 1280x720 --fps-cap 30 --minimap show --label reference-low
```

`phase1` covers market160, invasion160, an equipped 160-actor crowd containing
80 supported mounts, combat160, empty, and cold/warm southern traversal. The
route drives real client map and actor handlers without a server connection;
it does not certify server navigation. “Cold” means the first application
pass, not an emptied operating-system cache. `authored-herd` is separately
selectable and reports unavailable content when the map has no authored herd.
Unavailable content is retained as pending, never accepted as an empty timing.

On Windows, `--settings-profile performance` seeds the game's Performance
preferences into fresh isolated storage before startup: Low, 30 FPS, 75% world
scale, Half map textures, 60 crowd bodies and the remaining preset values.
The runner records the seed and checks the actual loaded settings. Conflicting
options are rejected. Use market/invasion/combat cells for this profile; the
80-mount census requires a larger body allowance. Ordinary Low at 30 FPS uses
`--settings-profile default --quality low --fps-cap 30` and remains a separate
comparison. Performance profile seeding currently supports Windows only.

For shipping-path measurements, create a committed standalone benchmark export:

```powershell
python tools/package_client.py --distribution standalone --benchmark-profile --ref <commit> --no-fetch --no-zip --godot <Godot.exe> --build-dir <disposable-build-worktree> --out <local-checkpoints>
python tests/integration/run_crowd_presentation_benchmark.py --godot <package>/app/RabbitLands.exe --executable-mode exported --package-manifest <package>/benchmark-package.json --variants all --cells phase1 --mode windowed --renderer gl_compatibility --quality medium --resolution 1280x720 --fps-cap 60 --minimap show --label reference-medium
```

The local benchmark profile adds only allowlisted synthetic workload scripts
and a custom startup loop in its disposable export settings. The runner selects
the workload with `RABBITLANDS_CROWD_BENCH_EXECUTION_MODE=exported`; release templates
ignore `--script`. Starting the package normally opens the ordinary game, so
the checkpoint remains playable. Ordinary distributions keep tests excluded
and retain their normal startup settings. The manifest covers the executable,
PCK and loose files. Checkpoints and raw reports belong in ignored local storage.
Keep replay recordings and their reports outside repositories.

The runner first requires a startup acknowledgement bound to its unique run
token, process, executable, execution mode and isolated user directory. A wrong
entry point fails before the full workload timeout. It verifies source/content/
executable identity before and after each run, isolates settings, records effective settings and actual backend use,
and rejects errors, incomplete readiness, mismatched populations or invalid
statistics. It retains raw work-time and delivered-frame series separately.
Loading diagnostics distinguish preparation, verification, attach, deferred
grounding/binding, retirement and retained caches. Large indivisible work is
reported explicitly rather than implied to fit a nominal time allowance.

Windows runs also record `processMemory`: sampled resident working set and
private committed bytes, plus OS lifetime peaks. Samples are at most once per
second after startup acknowledgement through workload teardown; subsecond
changes and the final unsampled interval can be missed. Timestamps mark
observations, including when an OS peak was observed. These whole-process
counters are separate from Godot allocator and GPU memory. Unsupported or
failed observations are explicitly unavailable or partial, never zero memory.

`--disable-obs-vulkan-capture` optionally sets `DISABLE_VULKAN_OBS_CAPTURE=1`
only for the owned child. Without the switch, inherited values are preserved.
Per-run `externalInterference.obsVulkan` records the request and effective value;
`observedHookLoaded` remains unknown (`null`) because the runner does not inspect
modules. This requests disabling OBS's declared Vulkan implicit layer without
changing OBS or other capture jobs. It does not establish crash causality or
prove every capture hook is absent.

A process-owned lock serializes participating runners across worktrees. The
lock cannot reserve the machine against unrelated applications. Pause imports,
builds, tests and other benchmark jobs during a comparison. Use matched content
and settings, repeat runs in alternating order, and label shared-host results
as screening. A fast development machine does not qualify low-end hardware.

## Crowd and scenery presentation

Mounts inherit their rider's quality and use one clock for mount, rider, tack,
reins and cloth. Half/quarter-rate updates accumulate skipped time; offscreen
one-shot actions finish without posing the whole mount. Local, selected and
combat-target riders retain priority. Parking sleeps both model subtrees, and
revival reconciles current quality before restoring mount presentation. A worn
cape still needs quality, distance/tier and crowd allowance; remote Medium/Low
capes sleep, while the local cape remains available.

New and deferred actor bodies share one allowance per process frame: four
bodies and a soft 6 ms elapsed stop, with at most three distinct critical actor
exceptions. Ambient creation has its own shared allowance across populations:
Low/Medium/High allow two/three/four successful creations, at most 32 attempts,
and a soft 1.5 ms elapsed stop. One indivisible load can exceed either stop;
these independent allowances are not a combined frame-time guarantee.

Ambient meshes follow quality and animated scenery uses skeleton gating with
full/half-rate allowances of 8/8, 12/12 and 16/16 at Low, Medium and High, per
population. Those caps are separate from replicated actors. Retirement forgets
only departing animation members, preserving survivors' clocks; full clears
discard membership without reactivating retiring callbacks. Readiness includes
queued ambient creation. Synthetic fixtures cover these paths; authored-herd
performance remains pending approved populated content.

## Historical measurements

Notes on the runtime cost of the Godot client and the mechanisms that keep it
down. Measured on the Four Gates package (1717 imported mesh nodes referencing
42 meshes) at 1280x720 with the GL Compatibility renderer.

| | before | after |
| --- | --- | --- |
| Draw calls per frame, minimap and full map wired as shipped | 9 237 | 335 |
| Draw calls per frame, gameplay camera alone | 559 | 335 |
| Visible world `MeshInstance3D` | 1 717 | 687 + 132 batches |
| First actor spawned in a session | 1 169 ms | 1 204 ms |
| Every actor after the first | 1 148 ms | 2.5 ms |
| Loading the twelve regions once each | 28 106 ms | 11 749 ms |
| Loading them again, from the map cache | 28 106 ms | -41% of whatever the build costs |

## Where the frame goes

**One world, three cameras.** `MapViewport` and `FullMapViewport` share the
gameplay `World3D`, so each is a complete extra render of the region - geometry,
materials and the directional shadow pass. Both shipped on `UPDATE_ALWAYS`,
which is where the 9 237 draw calls came from. They are now idle by default and
`Main._update_map_viewports()` asks for a single redraw only while the matching
UI is on screen: the minimap at ~15 Hz, the full map at ~5 Hz. The character
creation preview follows the same rule through `_update_preview_viewport()`.

If you add another SubViewport over the gameplay world, drive it the same way.
Leaving one on `UPDATE_ALWAYS` silently doubles the client's raster cost.

**Static instance batching.** A region is mostly repeats: 140 tree trunks, 36
lamps, 32 wall segments, all pointing at a handful of shared meshes.
`WorldLoader._batch_static_instances()` collapses groups of four or more
identical opaque instances within a 180 m cell into one
`MultiMeshInstance3D`. Cells keep frustum culling meaningful; without them a
single batch spanning the whole city would always be drawn.

Instances are skipped when they carry collision (any child node), a skin, a
material override, a per-surface override, a visibility range, or a blended
material - blended surfaces are sorted per instance, so batching them would
change the picture. Source nodes stay in the tree with `visible = false`, so
manifest declarations, name lookups and tooling keep resolving.

Per-map controls live under `rendering` in the world manifest:

```json
"rendering": {
  "batchStaticInstances": true,
  "batchMinimumInstances": 4,
  "batchCellMetres": 180.0
}
```

**Actor visuals off the map cameras.** Nameplates and selection rings render on
visual layer 2. The gameplay camera draws layers 1 and 2; the map cameras draw
layers 1 and 3. They therefore cost nothing in the two top-down views, which
never showed them legibly anyway.

## Where actor spawns go

`ReplicatedActor3D.configuration_timings_usec()` returns the last configuration's
model-scene, import-adapter, appearance, animation, RL-head, equipment and total
times. These are setup spans rather than delivered frame timings. The initial
configuration still includes first-use appearance and equipment preparation;
the per-frame actor allowance cannot split one such blocking operation.
`slow_actor_creation` records the first sixteen body builds exceeding 100 ms in
a client session, including these phases and the static model/type, without
player names or actor identities. It does not sample ordinary process frames.

In source checkouts, actor folders protected by `.gdignore` always use their
loose runtime source, even if old editor import remaps and products remain.
Unguarded actor assets can still use a valid available editor scene. Keep the
local guards aligned with `tools/package_client.py`'s `actor_shipping()` plan.

**Model and equipment glTF parsing.** Every actor used to run
`GLTFDocument.append_from_file()` for its race mesh, again for its hair, and
again for each native equipment model. `GlbSceneCache` parses each file once,
packs it, and instantiates from there. Instances share mesh and material
resources; per-actor tinting goes through `material_override`, so nothing leaks
between actors.

**Animation retargeting.** `Universal_Animation_Library.glb` is 11 MB and holds
162 clips built from roughly 226 000 keyframes. `NativeAnimationImporter` used
to reparse it and rebuild every clip key by key, in GDScript, for each actor.
It now rebuilds only the clips the actor's action map can request - 18 of the
162 for the current maps - and caches the finished `AnimationLibrary` under the
source path, skeleton node path, rig signature and clip set. Animations are
immutable during playback, so one library backs many `AnimationPlayer`s safely.

The remaining ~1.2 s is the one-time parse of the animation library. It is paid
by the first actor that enters view. Prewarming it behind the map loading
screen is the obvious next step.

Both caches are dropped in `Main._clear_world_presentation()` when the session
ends.

## Per-packet and per-frame work

* `state_changed(&"actors")` fires once per actor packet. `Main` coalesces the
  burst into one `_sync_world()` per frame instead of rebuilding every actor's
  presentation once per packet.
* The rendered-surface ray sample is cached per actor and repeated only when
  that actor's position changes, instead of once per actor per packet.
* `ReplicatedActor3D` stops its physics processing once its interpolation
  segment has finished and it faces where the server says it should, and wakes
  on the next packet, keypress or surface sample.
* `EloriaProtocol.try_decode()` takes an offset so a burst drains without
  re-copying the receive buffer after each packet.
* `render_diagnostics()` walks an actor's whole subtree. It was an argument to a
  `print_debug` that ran on every placement; `print_debug` is a no-op outside
  debug builds but its arguments are always evaluated. It is now a one-shot per
  map load.

## Second pass: animation, per-packet rebuilds, spawns

Measured 2026-09-05 on develop, before and after, at 1280x720 on the GL
Compatibility renderer with an RTX 5080 laptop GPU. Scene CPU is a headless
run with the engine's idle sleep removed (`OS.low_processor_usage_mode_sleep_usec
= 1`, otherwise every headless frame is padded to 6.9 ms); render CPU and GPU
are the renderer's own timers (`RenderingServer.viewport_set_measure_render_time`
and `viewport_get_measured_render_time_cpu/gpu`). Windowed wall-clock frame
times are not usable for this work: the compositor throttles a background
window to steps of the refresh rate, and `Performance.TIME_PROCESS` read from a
SceneTree script is not meaningful either.

| | before | after |
| --- | --- | --- |
| Sunmane herd, 111 animals, GPU per frame over the empty steppe | +1.8 ms | +0.3 ms |
| 61 idle actors spread over 60x60 tiles, scene CPU per frame | 1.24 ms | 0.58 ms |
| `_sync_stats` with the statistics window hidden | 9.4 ms | 0.6 ms |
| One chat line arriving with a full 1000-line buffer | 7.7 ms | 0.15 ms |
| Actor flush with 81 actors and nothing changed | 1.1 ms | 0.1 ms |
| `ItemAtlas.icon_for` | 31 us | 2 us |
| Twenty actors entering view | 48 ms in one frame | 13 ms a frame for five frames |
| The first actor's animation-library parse | 330 ms on the main thread | a worker thread, during the map load |

**The animation gate.** Skinning was the largest cost on a populated map: about
5 ms a frame for sixty race actors on screen (77 bones, 9 skinned mesh
instances and 26 700 vertices each, re-posed and re-skinned every frame), and
every body was animated whether or not the camera could see it. `AnimationGate`
(`src/world/animation_gate.gd`) classifies each animated body against the
gameplay camera ten times a second: outside the frustum its AnimationPlayer is
paused where it stands, beyond 45 m it is stepped every other frame by the time
both frames covered, so it plays at the same speed with half the updates, and
otherwise it is untouched. `Main._update_animation_gate()` drives the actors
through `ReplicatedActor3D.set_animation_tier()`, which sleeps the cape cloth
along with a paused body and never pauses a clip that does not loop, so an
actor caught sitting down finishes the move; `AmbientPopulation` gates its own
herd from `_process`. What is on screen and near the camera animates exactly as
before; the local player is never gated.

**A window that is not showing is not rebuilt.** The statistics document, the
counters page and the session table are rebuilt from controls, and the
partial-stat packets that drive them arrive with every health, food and
experience tick. `_sync_stats_window()` now only marks them stale while the
window is hidden; `stats_panel.visibility_changed` rebuilds them when it is
shown. The meters, skill rows and indicators on the HUD are still refreshed by
every packet.

**Chat lines are appended.** `_append_chat_line()` appends the arriving line to
the chat panel and the console and drops the oldest paragraph past the cap with
`remove_paragraph(0, true)`, instead of clearing and re-appending a hundred and
a thousand lines. A log whose last rendered line is no longer the line before
the new one - a reconnect cleared the buffer, a fixture replaced it - is rebuilt
in full, so the incremental and full paths cannot disagree.

**Only the actors that changed are re-presented.** Every AppState site that
writes `actors` records the id in `changed_actors`; the per-frame flush calls
`_sync_world(AppState.take_changed_actors())` and visits those ids plus any
actor that still has no node. `_sync_world()` with no argument is still the
full pass a map load and the fixtures use. The command reducer copies the actor
record shallowly; nothing writes into its nested dictionaries in place.

**Spawns are budgeted and the library is prewarmed.** `_sync_world` builds at
most `ACTOR_SPAWN_BUDGET` actors per pass and leaves the rest for the next frame
(`_spawn_backlog`); the local player is always built at once.
`NativeAnimationImporter.prewarm()` parses a shared library on a worker thread
as the map starts loading, and the parsed source is kept for the session so a
second rig never parses the 11 MB file again.

**Item icons are shared.** `ItemAtlas.icon_for()` keeps one AtlasTexture per
picture, and command 226's descriptions are indexed by slot once per list
rather than searched for every slot of every refresh.

## Third pass: map load, memory, a hundred creatures, a packet burst

Measured 2026-09-07 on `roadmap/clientperf` at 1280x720 on the GL Compatibility
renderer with an RTX 5080 laptop GPU, by
`tests/integration/client_benchmarks.gd`. Four things the first two passes
never put a number on.

**How to run it, and why in two goes.**

```
# scene CPU
Godot --headless --path . --script res://tests/integration/client_benchmarks.gd
# GPU, draw calls and memory
Godot --audio-driver Dummy --rendering-method gl_compatibility --path . \
      --script res://tests/integration/client_benchmarks.gd
```

Headless, with `OS.low_processor_usage_mode_sleep_usec = 1` and
`Engine.max_fps = 0`, wall time per frame is the scene tree's own CPU cost:
without that the engine pads every headless frame to 6.9 ms because no window
can draw. Windowed, the renderer's own timers
(`viewport_set_measure_render_time` on the root viewport and on the 3D
SubViewport) are the only frame numbers worth having - a windowed run's wall
clock is the compositor's refresh steps - and `RENDERING_INFO_TEXTURE_MEM_USED`
and friends read zero under the headless dummy driver, so texture, buffer and
video memory only mean anything there. `ELORIA_BENCH_SECTIONS` picks the
sections; `ELORIA_BENCH_MAP_REPEATS` takes the median of several loads.

**This machine is shared** with about a dozen other agent sessions, so a single
load's wall time varies by a tenth either way and the load column below is a
median of three. The memory columns do not vary and are the ones to read.

### Map load and what a region holds

Median of three loads per region, windowed. `WorldLoader.load_world` only: the
manifest, the glTF parse, the mip chains, `generate_scene`, the collision and
walk-surface bodies and the static batching. Resident is
`OS.get_static_memory_usage()` while the region is up.

| region | load ms before | after | resident MB before | after | texture MB |
| --- | --- | --- | --- | --- | --- |
| four_gates | 1031 | 1037 | 65.9 | 64.4 | 79.7 |
| mirrorhold | 1428 | 1377 | 110.3 | 98.0 | 69.3 |
| crownwater | 1125 | 1420 | 83.9 | 82.5 | 51.9 |
| whitehorn_range | 1125 | 1206 | 103.2 | 101.5 | 54.2 |
| amethyst_barrens | 1137 | 997 | 85.0 | 83.4 | 53.4 |
| sunmane_steppe | 695 | 525 | 72.5 | 57.0 | 13.9 |
| amberwood | 5049 | 3941 | 272.6 | 177.4 | 75.3 |
| grey_moors | 3074 | 3080 | 129.1 | 127.2 | 73.5 |
| westhaven | 1416 | 1371 | 112.9 | 111.0 | 65.6 |
| verdant_stair | 4729 | 4366 | 149.0 | 142.8 | 66.3 |
| ssarathi_ruins | 1245 | 1238 | 102.4 | 101.9 | 61.9 |
| manymouth_delta | 2388 | 2104 | 134.2 | 133.3 | 63.1 |
| **twelve regions** | **24 442** | **22 661** | **1 421** | **1 280** | |

Where a region's load went before this pass, phase by phase, taken by walking
the loader's own steps against a fresh import (windowed, milliseconds):

| | four_gates | sunmane | amberwood | verdant_stair |
| --- | --- | --- | --- | --- |
| glTF parse | 320 | 134 | 550 | 405 |
| mip chains | 230 | 66 | 137 | 272 |
| `generate_scene` | 88 | 73 | 2 593 | 3 003 |
| declared collision | 6 | 124 | 638 | 22 |
| walk surfaces | 231 | 109 | 377 | 528 |
| the three material and index walks | 7 | 3 | 25 | 48 |
| static batching | 18 | 18 | 45 | 63 |

`generate_scene` is Godot's own glTF scene builder and is the whole of the two
worst regions: Amberwood imports 9 106 mesh nodes and Verdant Stair 12 243, and
the cost is worse than linear in them - Four Gates builds 3 028 in 88 ms. That
is not addressable from here; the collision and the walks are, and were.

> It was addressable, and the "worse than linear" was the clue. It is not the
> node count but the width of a sibling list: Godot checks each name it adds
> against the children the parent already holds, and Amberwood hangs 7 935
> nodes off one parent. Bucketing those before the scene is built took the
> twelve-region load from 28.1 s to 12.3 s. See `map-load-times.md`.

**Nothing leaks between maps.** Unloading a region gives back everything it
took, to within a rounding error, on nine of the twelve; the other three
(Four Gates +9.9 MB, Amberwood +10.1 MB, Verdant Stair +5.6 MB) are one-time
high-water marks in the allocator rather than a per-load leak, which is what
the revisit says: after the whole tour, loading Four Gates a second time costs
what it cost the first time and gives all of it back (-0.14 MB). Across the
whole tour the process keeps 26.8 MB of resident memory, 0.67 MB of texture
memory and no buffer memory, before and after this pass alike.

### A hundred creatures

A hundred creatures of ten species spread over sixty tiles square on Four
Gates, at the import scales the resized roster now uses, with the local player
standing in the middle of them - which is what puts the gameplay camera in the
crowd. The gate classifies them 51 full, 1 half, 48 paused. Scene CPU is
headless with the idle sleep removed; the render numbers are the 3D
SubViewport's own timers, windowed. "Walking" is every one of the hundred
taking a step in the same frame - a resync or a very dense fight, not an
ordinary second, since the server paces a step at a time per actor.

| | before | after |
| --- | --- | --- |
| Empty map, scene CPU per frame | 0.05 ms | 0.06 ms |
| A hundred idle, scene CPU per frame | 0.96, 0.91 ms | 0.94, 0.98 ms |
| A hundred walking, scene CPU per frame | 8.44, 9.44 ms | 6.64, 7.65 ms |
| of which re-presenting the actors | 5.38, 6.03 ms | 3.61, 4.13 ms |
| Building the pack of a hundred | 1.09, 1.14 s | 1.11, 1.21 s |
| World GPU per frame, empty / crowd | 0.35 / 4.24 ms | 0.42 / 4.21 ms |
| Draw calls, empty / crowd | 122 / 570 | 122 / 570 |
| Texture memory, empty / crowd | 110 / 320 MB | 110 / 320 MB |

Two numbers there are worth keeping in mind and neither moved, because neither
should have: the crowd is 4.2 ms of GPU a frame, and it is 210 MB of texture
memory. The 210 MB is ten species, not a hundred bodies - the eleventh actor of
a species costs 4 KB of texture memory, so `GlbSceneCache` is sharing what it
hands out - and two humanoid rigs in that ten carry a 2048x2048 base colour and
a 2048x2048 normal each, which is 64 MB of the total on its own. Actor textures
are uncompressed and have no mip chain; the map's do.

### A burst of packets

Five hundred packets in one buffer - 300 actor-move packets of eight actors
each, 100 partial stats, 100 chat lines - drained with
`EloriaProtocol.try_decode` at an offset and reduced through `AppState`.
Headless, median of three runs.

| | before | after |
| --- | --- | --- |
| Decoding the whole burst | 0.50 ms | 0.53 ms |
| Decoding and reducing it | 15.2 ms | 12.5 ms |
| of which the actor moves (2 400 commands) | 8.85 ms | 9.08 ms |
| of which the partial stats | 3.09 ms | 1.03 ms |
| of which the chat | 1.62 ms | 1.52 ms |
| Per packet | 30.4 us | 25.1 us |

Decoding is a fortieth of the cost; the reducer is the rest.

### What this pass changed

**A region's collision is built once per mesh.** A region names the same
handful of meshes over and over - Amberwood declares collision on 862 nodes
that between them reference 91 meshes - and `WorldLoader` built a fresh trimesh
shape for every node, walking the same geometry triangle by triangle and giving
it its own BVH in the physics server each time. Shapes are now built once per
mesh per load and shared by every body standing on one, which is how an
instanced scene has always worked: the faces are in the mesh's own space and
the placement lives on the body's parent. The table is per load. Amberwood
lost 95 MB of resident memory and 1.1 s of its load; Sunmane 15 MB and 0.17 s.

**The import is walked once.** Four `find_children` over as many as fifteen
thousand nodes, plus a name index, became one traversal shared by every pass,
and the two material passes share one loop over it.

**An actor that has not changed its clothes is not redressed.** Every actor
packet restates the whole wardrobe and almost none of them change it.
`apply_equipment_visuals` reconciled the request part by part, skipped every
part that agreed, and then walked the model's meshes again in
`_refresh_wardrobe_cover`. A request that matches in full now returns at once;
the first pass always runs, so nothing an actor is built with is skipped. That
was 0.64 ms of a frame with a hundred actors in it.

**The presentation record is copied shallowly.** `_presentation_dto` replaces
two top-level keys and nothing that reads the result writes into what is left,
which is the reasoning `ActorReducer.apply_command` already records.

**A stat's name is read out of a table, not built with one.** `stat_key()`
built a ninety-entry dictionary, looked one name up in it and threw it away,
several times per partial-stat packet - and one of those arrives with every
health, food and experience tick. `decode_stats` did the same with its three
slot tables and rebuilt its six-name resource list once per resource to search
it for the index the loop already had. All constants now. A chat line is
sliced out of its payload once and read twice instead of being copied for each
reading.

### What to try next

* **`generate_scene` is the map load.** Two and a half to three seconds of
  Amberwood's and Verdant Stair's four are Godot building nine to twelve
  thousand mesh nodes, and the client cannot make that faster - but it could
  stop blocking on it. The animation library is already parsed on a worker
  thread (`NativeAnimationImporter.prewarm`); a glTF map parse builds nodes
  that belong to no tree in exactly the same way, so `load_world` could become
  a thread plus the existing `load_completed` signal, and the client would stay
  responsive through a four-second load instead of freezing. Every fixture
  already waits for `world_root` rather than assuming it is there.
  *Since taken up in `map-load-times.md`: the scene build itself is now 8% of
  what it was, so the freeze is 0.5-1.4 s rather than up to eight seconds, and
  the threading is measured but not landed.*
* **A region built once is built again every time it is entered** - the same
  tree, out of bytes that do not change between one launch and the next.
  *Since landed: `MapSceneCache` and `WorldLoader` pack the built region to
  `user://map-cache` on the first visit and instantiate it afterwards, which is
  41% off every visit after the first, twice measured, for 383 MB of the
  player's disk and one 0.3-1.3 s write three frames after the first load.
  The entry is keyed on a sha256 of the package's own bytes and on
  `WorldLoader.CACHE_FORMAT_VERSION`, so a client update or a loader change
  rebuilds it with nothing to remember - and that version is the thing to
  raise when editing `WorldLoader`, because nothing checks that you did.
  `map-load-times.md` has the per-region table, what is and is not in an entry,
  and why the write happens three frames after the load rather than during it.*
* **Actor textures are 210 MB for ten species**, uncompressed and unmipped,
  against 14-80 MB for a whole region. Mip chains would cost another third and
  stop distant creatures shimmering; VRAM compression would cut it to a
  quarter. Both change what is on screen, so both want a decision rather than a
  patch.
* **The actor-move reducer is 9 ms of a five-hundred-packet burst** and did not
  move here. `ActorReducer.apply_command` copies the whole actor record per
  command and `decode_server` builds a dictionary per command inside it: 2 400
  of each for that burst.
* **Re-presenting a walking crowd is still 4 ms a frame** for a hundred actors.
  What is left is spread thin: about a third of it is the surface ray under
  each actor that moved (1.26 ms for a hundred), and most of the rest is
  `apply_server_state`'s pacing arithmetic, which is a hundred lines of
  GDScript run per actor per packet.
* **A hundred creatures are 570 draw calls and 4.2 ms of GPU.** The static
  batching that took a region from 9 237 draw calls to 335 does not apply to
  skinned bodies; whether it can be made to is the next rendering question.

## Reading the game socket

`Network` (`src/network/network_client.gd`) reads the game socket on the main
thread. Until 2026-10-21 it read once per frame, and over TLS each read took a
single TLS record: `StreamPeerTLS.poll()` decrypts one record and
`get_available_bytes()` counts only its plaintext. The server writes one record
per flush - every 50-ms tick, plus each immediate send such as the player's own
step - so whenever it wrote more records a second than the client drew frames,
the backlog grew for as long as that lasted. Plain TCP (`--dev-plain-tcp`)
returns everything buffered at once and never showed it, which is why local
play looked fine. Now:

* each read polls and reads until the TLS layer has nothing left (at most
  `MAXIMUM_RECORDS_PER_READ`, 64 records);
* a second read (`LateRead`, a child with a very high `process_priority`) runs
  after every other node's `_process` and before Main's deferred world sync, so
  packets that arrive during the frame's physics and process work are
  presented in that frame instead of the next. Both reads append to the one
  receive buffer and dispatch from it in arrival order, on the main thread;
  `Network.set_process(false)` stops both;
* `StreamPeerTCP.set_no_delay(true)` on each connection's socket, before the
  TLS handshake. TLS writes through that socket, so it covers both links.

Measured with `tests/integration/socket_read_latency.py` (headless, loopback,
the probe server writing the way the RL server writes: one record per 50-ms
tick holding three frames, plus an "own step" record every 233 ms). Times are
p50 / p95 / max milliseconds from the socket to `packet_received` (dispatch)
and to the world sync that could first draw the packet (present); the
own-step column is the spread of the interval the movement pacing measures
between steady steps. Raw results:
`docs/benchmarks/socket-reads-2026-10-21.json`.

| Scenario | Dispatch before | Dispatch after | Present before | Present after | Own-step sd before / after |
| --- | --- | --- | --- | --- | --- |
| TLS, 21 FPS (frame cap) | 802 / 1500 / 1589, growing | 29 / 47 / 59 | 802 / 1500 / 1589 | 29 / 47 / 59 | 25.0 / 17.2 |
| TLS, 29 FPS | 30 / 60 / 78 | 16 / 32 / 47 | 30 / 60 / 78 | 16 / 32 / 47 | 30.6 / 17.8 |
| TLS, 29 FPS, two flushes a tick | 2649 / 5014 / 5265, growing | 16 / 32 / 48 | 2649 / 5014 / 5265 | 16 / 32 / 48 | 17.0 / 16.9 |
| TLS, 60 FPS | 15 / 17 / 45 | 15 / 16 / 31 | 15 / 17 / 45 | 15 / 16 / 31 | 16.4 / 10.0 |
| TLS, CPU-bound 25 FPS | 33 / 62 / 82 | 10 / 22 / 26 | 48 / 77 / 97 | 20 / 37 / 42 | 24.5 / 15.0 |
| plain TCP, CPU-bound 25 FPS | 20 / 38 / 42 | 10 / 24 / 27 | 35 / 53 / 57 | 20 / 39 / 42 | 18.5 / 17.3 |

"Growing": at 21 FPS the old client was 0.28 s behind on average over the
first third of the ten-second run and 1.32 s over the last; with a second flush
per tick at 29 FPS, 0.88 s and 4.40 s. The CPU-bound rows spend 4 ms in each
physics tick, 15 ms in `_process` before the world sync and 15 ms after it
(standing in for rendering, which headless skips): the late read halves the
time to the world sync because the packets that land during physics and
`_process` no longer wait a frame. The 60-FPS row is a sanity check only - its
frames are phase-locked to the 50-ms tick, so it samples one phase. What is
left is the frame itself: a packet still waits for the next main-thread read,
up to a frame, and the own-step spread is that quantisation.

TCP no-delay, against a server in WSL2 (a Linux stack reached through the
Hyper-V switch; Windows loopback acknowledges at once, so Nagle never holds a
frame there): the client wrote two frames back to back every 100 ms to a
silent server. Before, the second frame waited for the first one's ACK - p50
0.27 ms on that 0.3-ms link (TCP) and once 42 ms behind Linux's delayed ACK
(TLS); after, the gap was under 0.12 ms every time in both. Over the internet
that wait is a round trip, or the server's delayed-ACK timer.

CPU: the Godot process used a median 1.16 s before and 1.13 s after over three
20-second TLS runs at 60 FPS; the reads on an open link with nothing waiting
cost 4-5 us a frame before and 7-10 us after (the late read's extra poll).

Not done, and why. A Timer or the physics tick does not read between frames:
Godot runs all of a frame's physics steps back to back at its start (median
0.03 ms apart at 21 FPS) and a 5-ms Timer fired once per frame, never more.
Only a thread reads while the main thread renders, and all it would buy is a
sub-frame arrival time: packets would still reach game state at the next
main-thread read. Movement pacing stamps a step's arrival at the world sync,
and today's jitter allowance also covers the next packet's presentation delay,
so feeding it sub-frame arrival times is a pacing change of its own
(`docs/input-and-movement-contracts.md`, "Movement presentation").

`tests/test_network_socket_reads.gd` guards this over a real loopback TLS
session: thirteen waiting records (the last frame split across two) taken in
one read and in order, no-delay set, the late read paused with
`set_process(false)`, and a packet arriving mid-frame dispatched before that
frame's deferred calls.

## Map textures: prepared once, uploaded VRAM-compressed

Every content-addressed map image (the `externalResources` of a map package,
all under `nymara-regions/_continent/shared-assets`) used to be decoded on the
importing thread, uploaded without mips, read back from the GPU, given its mip
chain and uploaded again, and it sat on the GPU as RGBA8: 4 bytes a pixel and a
third more for mips. A dressed hub held 460-600 MiB of map textures against the
chunk stream's 256 MiB budget, so the stream refused most of its neighbours.

* **Preparation** (`src/world/map_image_extension.gd`, `vram_textures.gd`). A
  `GLTFDocumentExtension` prepares a package's external images before the parse,
  in one WorkerThreadPool group task (every pool thread when the main thread
  waits for it; at most two low-priority threads for a streaming chunk worker,
  whose import must not take the CPU the frames need): decoded by their magic
  bytes (no more "Not a PNG file" for every `.jpg`) and given the mip chain the client always
  built, or taken from `ExternalTexturePool` when another map holds them. The
  texture GLTFDocument creates is the finished one; nothing is read back. Only
  states that carry WorldLoader's plan are touched, so actor GLBs and embedded
  images keep GLTFDocument's own path. `load_phases` reports `imagesPrepared`,
  `imagesSidecar`, `imagesDecoded`, `imagesPooled`, `imagesFailed`,
  `sidecarRejected`, `sidecarRoleMismatch`, `imagesPrivate`,
  `imagesPreparedOnMainThread`, `prepareThreads` and `prepareWaitUs`.
* **Sidecars.** `tools/build_vram_textures.py` writes `<image dir>/vram/` at
  package time: `<sha>.<recipe>.evt` (EVT1 header + zstd DDS with the full mip
  chain) and `index.json`. BC7 for base colour (alpha only where a MASK/BLEND
  material uses it), BC1 for ORM (BC7 when BC1 falls under the ORM floor), BC5
  for normals; images under a quality floor, in conflicting roles or not a
  multiple of 4 are listed as excluded and decode as before. The client uploads
  a sidecar as it is when the renderer samples its format (RenderingDevice on
  Forward+/Mobile, the GL driver on Compatibility) and falls back to decoding,
  image by image, on any doubt. Each index entry lists the material roles its
  encode was chosen for (`base`, `base_cutout`, `emissive`, `normal`, `orm`,
  `occlusion`); a map that samples the image in another role - an index left
  from before a content pass, say an opaque base that became a cutout - decodes
  it (`sidecarRoleMismatch`), and a pooled sidecar from another map is not
  reused for such a role (`imagesPrivate`). The client never compresses
  anything: the export templates have no BC encoder.
* **Budget.** `ContinentChunkStream.configure` reads the sidecar indexes of the
  images its territory manifest names (wherever they live), then counts each
  shared image at its sidecar's GPU bytes when it will be uploaded from one, the
  published RGBA8 figure otherwise (`VramTextures.resident_bytes`), and logs
  `vram_textures budget <territory>: N of M images at sidecar size`. "Will be
  uploaded" is judged by the index of the image's own directory, the one its
  load uses: another index read in the session can list a sidecar for a sha
  this one excludes (continent-v2 encodes images the Nymara index excludes for
  `no_material_role`), and pricing by it under-counted every Nymara territory
  visited after Landfall. An image its territory names no directory for keeps
  the published figure. No map is
  republished. An index entry missing a field, or claiming fewer GPU bytes than
  its format's top level holds, is not used; a sidecar refused at load sends
  its image back to the published figure for the rest of the session (the
  stream re-corrects and logs `... rechecked`).
* **Cache.** A package with external images folds `VramTextures.cache_token`
  (mode, usable formats, index hash) into its key, so its entries never mix
  with ones built from decoded images; `CACHE_FORMAT_VERSION` stays 7, because
  every other package builds exactly as before and keeps its players' entries.
  Live continent chunks are detached builds and never write the cache, so the
  sidecar formats reach it through whole-map loads only.
* **Switch.** `ELORIA_VRAM_TEXTURES=0` turns sidecars (and the budget
  correction) off; `force` uses them whatever the renderer says (tests). The
  client logs `vram_textures mode=... formats=... index=...` once at startup;
  with `ELORIA_VRAM_SELF_TEST=1` it also decodes one sidecar and logs
  `vram_textures self_test ok|failed`, which the package smoke launch requires.

The sidecars are not tracked. A dev checkout has none until the tool has run
(`index=missing` in the startup line, every image decoded as before), so run it
before a live test or a measurement of this path:

    python godot-client/tools/build_vram_textures.py

It needs the Godot 4.7.2 editor binary (found beside the checkout, or
`--godot` / `ELORIA_GODOT`) plus numpy and Pillow, takes about two and a half
minutes cold for the 1 464 shared images and seconds warm (its encode cache is
`.vram-encode-cache/`, ignored). `tools/package_client.py` runs it into the
package stage, checks every staged image has a sidecar or a reason, and
`--no-vram-textures` leaves them out. Tests: `tests/test_vram_textures.gd`,
`tests/test_continent_chunk_budget.gd`, `tests/test_build_vram_textures.py`,
`tests/test_package_vram.py`, and on a real renderer (windowed; CI runs it on
Compatibility under xvfb) `tests/integration/rendered_vram_textures.gd`, which
checks the formats the GPU really holds and draws the fixture both ways.

## Streaming work and resource lifetime

Chunk and exterior retirement share an allowance of 2 ms and 64 released nodes
per process frame. Weak owners take turns; each owner receives at most one
slice per frame. A single indivisible release can exceed the time allowance,
and diagnostics charge its full duration. Retirement estimates remain counted
until the nodes are actually released. Pausing, cancelling and adopting a
resident root preserve ownership without blocking other streams indefinitely.

Chunk surface notifications coalesce until the next physics frame. The refresh
checks live root identity and current transforms, then limits grounding work
to affected bounds, priority actors and actors or objects still missing ground.
Resident-map changes retain a full refresh. Scenery bindings are updated only
for the active map's changed chunks. Completion wall time includes the physics
wait; separate work counters measure the callback itself. Placement attempts
are not a count of physics rays.

Full map textures retain their existing budget policy. Reduced decoded images
can publish a conservative estimate from their actual CPU dimensions and mip
chain after the requested reduction succeeds. Unknown, unreduced or
incompatible private copies retain the published estimate. These figures are
streaming estimates, not a complete measurement of physical GPU allocation.
Runtime manifests continue to hash content on every verification: the current
mutable content provider offers no enforceable sealed identity for safe reuse.

## Checking a change

Local benchmark exports also record an asset-only identity from actual PCK
payload bytes and all loose assets, with explicit code/metadata exclusions.
The runner verifies it before and after each process. This allows different
client code to be compared with the same assets; it does not allow the runtime
loader to skip verification. Route boundary snapshots record selected and
resident content and their capture cost. Full-route frame/wall samples include
that diagnostic cost; transition timing ends before the arrival snapshot.
Mounted snapshots distinguish available joint scheduling counters from the
legacy path and record actual mount quality. Their counters cover each visual's
lifetime through the boundary, including warmup, rather than only the sample.

`tests/test_runtime_performance.gd` guards the viewport scheduling, the surface
sample cache, the in-place packet decode, the shared icons, the actor change
set, the hidden statistics window, the appended chat line, the prewarmed
library and the spawn budget; and from the third pass, the shared trimesh
shapes and single import walk, the skipped wardrobe pass, the shallow
presentation record and the decoders' constant tables.
`tests/test_animation_gate.gd` guards the gate's tiers and the one-shot
exemption. `tests/integration/client_benchmarks.gd` is the third pass's
instrument and re-runs any of its four sections on demand.
`tests/integration/sunmane_performance.gd` writes frame timings, draw calls and
primitive counts as JSON for a region package.
`tests/integration/sunmane_grounding.gd` and `sunmane_caves.gd` are what say
the shared collision shapes still hold a player up and in.
`tests/integration/map_load_phases.gd` takes a map load apart step by step out
of the loader's own `load_phases` - three ways per region now: built, first
visit, and warm out of the cache - and `tests/integration/map_regrouping.gd`
says the regrouped tree holds the same geometry in the same places;
`map-load-times.md` is what they were written for.
`tests/test_map_cache.gd` is the map cache's contract: that a second visit
hits, that a changed package or a raised format version misses, that a stale
entry is removed, that a cached region has the same meshes, placements,
collision, walk surfaces, batches and visibility as a built one, and that what
the interior cutaway, the secret sections and the occluder fade do to a region
after it loads cannot be baked into the entry.
`tests/integration/map_cache_render.gd` photographs a region from eight fixed
viewpoints built and cached and counts the pixels between them, against a floor
it measures on the same run by photographing two builds - it must be run
windowed, since headless draws nothing and every comparison would pass.

## Optional prepared content pilot

The normal client uses the existing raw/imported asset paths. A local Windows
standalone package can include an optional native-resource catalog with
`tools/package_client.py --prepared-catalog <generation/index.json>`.
`RABBITLANDS_PREPARED_CONTENT=auto` selects verified entries and falls back on a
miss. `require-pilot` rejects a missing exact variant for a listed pilot;
unlisted assets still use their existing paths. Successful startup alone does
not prove that a prepared entry was consumed: inspect the actual entry IDs,
source paths and texture tokens in `PreparedContent.snapshot()`.

The catalog binds complete source and payload bytes, engine/cook policy,
retired-model policy and the exact texture/format variant. It revalidates cached
and worker completions before publication. Native Resources can load on workers;
scene instantiation and attachment remain on the main thread. Instance material
overrides and MultiMesh transform buffers are private. Copying a MultiMesh can
read renderer data and is included in the atomic instantiation cost.

`tools/prepared_content_package.py describe-pilot` identifies the dense chunk,
shared prototype, equipped actor components, animation source, storage object
and independent interior. Cooking requires an explicitly marked disposable
project, fresh settings per texture variant, and an actual exported import
snapshot. Never re-import that project between snapshotting and cooking.
Generated resources belong in ignored local build output. The package checks
the initial and final actual PCK inputs; source editor import descriptors are
separate provenance because the exporter rewrites them.

The current cook policy preserves exact rig metadata as an identity-bound JSON
string. It also preserves original animation key clocks in binary double
precision and compressed textures' logical dimensions, which Godot's native
resource serialization otherwise changes. These are restored before verified
resources are published. Scripted, compressed-animation and local-to-scene
animation inputs are refused by this pilot. Materials held on prepared geometry
survive until its rendering instance is destroyed; these finite references are
released with the geometry itself.

This pilot does not establish a general loading or memory improvement. Compare
actual hits, total readiness, the largest main-thread operation, live resource
sharing and process memory against raw content in the same package. Script,
streaming lifetime and rendered isolation fixtures are separate from actual
asset parity and target-device performance qualification.

## Optional shared resource admission

The default loader remains unchanged. With a verified native payload,
`RABBITLANDS_CLIENT_RUNTIME=services` keeps ordinary presentation and enables
native services. `RABBITLANDS_RESOURCE_ADMISSION=rust` then selects one shared
worker admission queue and one main-thread publication turn across chunk and
exterior streams. Mandatory synchronous arrival can exceed that soft allowance.
Cancellation retains ownership until executing workers have joined; the existing
retirement budget remains the destruction clock.

The service deduplicates verified world, prototype and image source identities.
It holds accounting until actual weak Resource carriers disappear, including
prepared resources discarded before instantiation. Shared cache aliases can keep
a logical resource closure charged after its original scene is gone. Estimates
are not measured CPU or GPU allocations; actor and cache bytes remain explicitly
unknown. The default experimental allowance is 768 MiB and can be selected with
`--resource-admission-budget-mib=64..8192`. Compare equivalent full-content work
at a permissive allowance before testing a tighter policy. Inspect actual
`resource_admission` diagnostics for mode, registrations, failures, unknowns,
retained carriers, denials, readiness and largest atomic verification cost.

## Optional prepared placement reduction

Prepared worlds retain source nodes by default. An exact catalog variant with
`--prepared-node-policy=lazy-source-v1` can remove eligible hidden leaf meshes
already drawn by a static MultiMesh. Collision, scripts, lamps, skeletons and
semantically mixed batches retain their ordinary nodes. The original transform,
sibling order and material behavior remain available through a weak root-scoped
handle. Fade and named interaction binding restore the required source on main;
restored nodes remain until their chunk is destroyed.

Retained and reduced variants must be compared in the same package. Require
actual live Node and VisualInstance reductions, exact source hits, collision and
current look/season behavior, and measure the first restoration cost. Handle
snapshots report initial removal, reified sources and remaining savings. Logical
occluder registrations are retained. Templates and handles also occupy memory,
so reduced node count alone does not establish a total memory or frame benefit.

## Preset and continuous-session evidence

Benchmark snapshots include the effective cloth allowance, shadow preference and
sun state, particles, decorative grass and name distance alongside texture,
resolution, scale, frame cap and body policy. Compare ordinary Low at 30 FPS
separately from `--settings-profile performance`: the complete Performance
preset also selects fewer bodies, half textures, reduced scale and no cloth.
Requested flags alone do not prove those settings were applied.

The benchmark runner accepts `--cells route-soak-16` for sixteen consecutive
passes through the real client streaming route. Counts from 2 through 32 are
supported. Each pass includes two borders, interior entry and return, teleport
and return. All passes retain one process and Main instance. The first pass is
application-first; subsequent passes are warm. This does not flush operating
system or shader caches or certify server navigation.

Iteration witnesses include monotonic and wall clocks, process and Main IDs,
ordered ready legs and final worker/retirement teardown. A missing or failed
transition, restarted owner, regressed clock or incomplete drain invalidates the
soak. Report actual elapsed time and process-memory coverage; process restarts
are separate startup checks. Keep full raw reports and failures with the exact
package identity. Neither a short matrix nor a clean soak enables an optional
backend or qualifies untested hardware.
