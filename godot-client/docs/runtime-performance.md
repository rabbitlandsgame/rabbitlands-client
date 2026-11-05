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

## Hardware-aware first-run defaults (2026-11)

Every install used to start on Forward+, High quality, full map textures, 100%
3D resolution and 160 crowd bodies. On an integrated GPU with 8 GB of memory
that measured 24–27 FPS in a market crowd and 7.4–7.6 GB of process memory,
which does not fit; Low on the same machine needed about 3.7 GB, and the
Performance preset 3.2–3.35 GB while holding 30 FPS (perf audit GPU-01, RAM-01,
TEXTURES-08, GAP-PROCESS-MEMORY-ATTRIBUTION-08).

`src/runtime/hardware_tier.gd` now classifies a fresh profile once, at startup,
before the map texture tier is read for the session:

| Tier | Machine | Saved starting settings |
| --- | --- | --- |
| Low | integrated (not Apple silicon), software or virtual GPU, about 8 GB of memory or less, or four CPU threads or fewer | the Performance preset (Low, 30 FPS cap, vertical sync off, 75% 3D resolution, half map textures, the crowd count following the quality (60 bodies at Low), no swaying capes, no shadows, no extra grass, 20 m names), without its renderer change; the entry screen starts on its still |
| Medium | otherwise, about 16 GB or less, or eight CPU threads or fewer | High graphics quality, as before; the tier is only recorded (a discrete GPU with 16 GB or eight threads is not the weak hardware these defaults are for, and Medium there would drop RL heads and SSIL: an owner decision for the per-class budgets) |
| High | everything else | High graphics quality (the previous defaults) |

The GPU type comes from `RenderingServer.get_video_adapter_type()`. Under
D3D12 an Intel iGPU reports itself as discrete, and the Compatibility renderer
reports no type at all, so there the adapter name decides (Intel names without
an Arc A/B model number, AMD APU names such as "Radeon Graphics", "Vega 8
Graphics" or "780M"). Apple silicon reports an integrated GPU but is judged by
memory and threads alone, because the measurements behind Low are Intel and
AMD iGPUs that Windows lets share at most half of system memory; an 8 GB Mac
still starts Low. Memory is `OS.get_memory_info()` physical memory, with
each limit half a GiB above its nominal size; threads are
`OS.get_processor_count()`. Dedicated video memory is not readable from
GDScript, so a 2 GB discrete card is not detected by itself.

Only a profile with no `[graphics]` section is seeded: a player who has ever
saved a graphics preference is never touched. That check, and the settings
note below, read the file's text instead of parsing it: an established
player's file holds HUD presets and notes (about 0.5 MB, 14–20 ms per parse),
so only a fresh profile is parsed. The values are saved like any
other preference, with the tier recorded as `[graphics] hardware_tier`, so the
choice is stable and every control stays editable. Settings → Graphics shows a
note when a profile started Low. The renderer is unchanged:
Automatic stays Automatic. Nothing is seeded for headless runs, the browser
build, `--script`/`--editor` launches (tests, tools, `client_benchmarks.gd`),
the crowd benchmark (`RABBITLANDS_CROWD_BENCH_START_TOKEN`), optimisation-profile
arguments, or any graphics, crowd or runtime override variable
(`ELORIA_LOOK`, `ELORIA_LOOK_QUALITY`, `ELORIA_LOOK_QUALITY_TRIM`,
`ELORIA_VRAM_TEXTURES` and the `RABBITLANDS_*` knobs). Startup logs one
`hardware_tier` diagnostic with the inputs, the tier, whether it was applied
and why. `tests/test_hardware_tier.gd` covers the classifier, the launch and
saved-profile guards, the client reading a seeded profile, and that the low
tier still matches the in-game Performance preset.

The wave-2 measurement switches block seeding too and are parsed in one place,
`hardware_tier.gd`: `RABBITLANDS_MEMORY_CLASS=small|medium|large` or the user
argument `--memory-class=` (the argument wins), `ELORIA_WORLD_DISTANCE=off`,
`ELORIA_ACTOR_IMAGES=legacy|nomips`, `ELORIA_ACTOR_VRAM_SELF_TEST=<dir>` and
`RABBITLANDS_ACTOR_GEOMETRY=sidecar|off|generate` (`generate` only in
development builds), plus `RABBITLANDS_ACTOR_GEOMETRY_ROOT`, and since stage B
`ELORIA_VIEW_REACH=auto|ground|off` and `RABBITLANDS_OVERHEAD_2D` or the user
argument `--overhead-2d=`. See the wave 2 stage A and stage B sections below.

Below 100% 3D resolution, Forward+ and Mobile upscale with AMD FSR 1 rather
than bilinear filtering (`GraphicsOptions.scaling_mode`); Compatibility, which
has no FSR, keeps bilinear. FSR adds one full-resolution pass, which on the
seeded low tier (an iGPU at 75%) is unmeasured: `ELORIA_FSR=0` keeps bilinear
for an A/B capture.

## Idle render passes and their A/B switches (2026-11)

Three render-side passes now do less while nothing needs them (perf audit
UI-01, GPU-04, HITCHES-01). Each has an environment switch that restores the
previous behaviour for measurements:

| Pass | What changed | A/B switch |
| --- | --- | --- |
| Overhead text (`world_text_overlay.gd`, `world_text_presence.gd`) | The second camera that draws names, bars and markers stops rendering, and its full-screen composite is hidden, while no layer-20 text can show. It resumes in the frame text appears. One exception: while nothing else shows, a title with a visibility range that is itself moved into range faster than 30 m/s, or given a longer range, can be drawn up to 200 ms late (a camera moving into range is never late). | `ELORIA_WORLD_TEXT_IDLE=0` |
| Sun shadow distance (`sun_shadow_fit.gd`) | `directional_shadow_max_distance` follows the ground the camera can see, found with 28 rays against the walk surface, and never exceeds the scene's own 100 m. A ray that meets no walk surface (sky, open water, ground not loaded, or a hole in a town's walk surface), an orthographic camera or a warm-up keeps the scene's value. | `ELORIA_SHADOW_FIT=0` |
| Arrival shader warm-up (`camera_shader_warmup.gd`) | A world whose drawable content was already covered by a full sweep this session gets a 60-view sweep instead of 240 views. New content keys always get the full sweep. | `ELORIA_CAMERA_WARMUP_REUSE=0` |

The warm-up reuse still needs a `camera_rotation_probe` qualification after a
door exit before it is relied on there. The client's `viewport_snapshot`
diagnostic records `world_text_pass`, `sun_shadow_distance` and
`scaling_3d_mode`, so a capture shows how often each one is active.

## Wave 2 stage A: Low actor tier, memory classes and foundations (2026-11)

The owner's 2026-11-02 performance decisions are delivered in stages. Stage A adds a real
Low actor tier, memory budgets per machine class, and the foundations later stages build on:
one renderer-family switch, a worker-safe actor glTF parse, offline actor geometry and texture
preparation, content digests, one verified native loader, and per-file updates. Medium and High
draw exactly as before. Every visible change applies only at Low (and with the Performance
preset) or on small-class machines, apart from the new "Follow graphics quality" box under the
crowd count in Settings → Graphics (shown at every quality; while it is checked the count's
slider is greyed out), and is listed for the owner's sign-off after wave A.
Figures are from the development laptop (Core Ultra 9 275HX) unless marked as estimates. The
wave-A measurement on the iGPU proxy has not been run yet.

Switches that restore earlier behaviour for A/B runs. The first four rows block the first-run
tier seeding and are parsed in one place, `hardware_tier.gd`:

| Switch | Effect |
| --- | --- |
| `RABBITLANDS_MEMORY_CLASS=small\|medium\|large` or `--memory-class=` (the argument wins) | forces the memory class |
| `ELORIA_ACTOR_IMAGES=legacy` | the plain actor glTF parse, without the actor image extension. Since stage B, `nomips` keeps decoded actor images without the fallback CPU mip chain (sidecars still bring their own) |
| `RABBITLANDS_ACTOR_GEOMETRY=sidecar\|off\|generate` | actor geometry sidecars (`generate` only in development builds); `RABBITLANDS_ACTOR_GEOMETRY_ROOT` names a sidecar root. Since stage B every actor parse calls the applier (ALOD-C1h) |
| `ELORIA_WORLD_DISTANCE=off`, `ELORIA_ACTOR_VRAM_SELF_TEST=<dir>` | nothing read them in stage A. Since stage B the first turns off the world distance pass (WD-C3) and the far plane on LOW (WD-C4), and the second runs the actor VRAM self-test (AT-C2) |
| `--content-digest=sequential` / `RABBITLANDS_CONTENT_DIGEST=sequential` | the pre-wave-2 single-threaded digest (kill switch). It changes no graphics, so it does not block seeding; `content_digest.gd` parses it and logs `content_digest stage=backend` |

`ELORIA_WORLD_DISTANCE` and `ELORIA_ACTOR_IMAGES` also accept `off/0/false/no` for their off
mode and `on/1/true/yes` for their default; the memory class and actor geometry take only their
own names. Any other value is ignored. A launch that sets one of the first four rows logs the
resolved modes, and any ignored value, as `switches` in its `hardware_tier` diagnostic.

### Low actor tier (Low and the Performance preset)

`ActorRenderQuality` holds the tier table. `tests/test_actor_render_quality.gd` pins the
MEDIUM and HIGH rows to the pre-tier values: 160 bodies, half rate from 45 m, a 60 Hz cape
step and live effects at 0.75 and 1.0. At Low:

- **Crowd count follows the quality.** 60 bodies (Graphics > Characters drawn in a crowd >
  Follow graphics quality, on by default) and at most 24 overhead banners. The target,
  selection, combat target, party members and campaign actors are shown in addition. Medium
  and High are unchanged: 160 bodies and no banner cap. The actor cap declared to the server
  follows the cap in force, so a Low client asks for 60.
- **Remote Humans are not finished.** Humans other than the player are built without the
  per-vertex body refinement and face sculpt, so other players show the neutral face, with
  hair and beards groomed to it. The player's own actor, the creation preview, the appearance
  editor, leaderboard cards and the campaign replay figure stay finished. A dialogue close-up
  shows the world actor as it is drawn, so at Low the speaker is unfinished too (an owner
  question). Measured with 20 distinct remote Humans (debug build):
  - the finish phase fell from a median 111-139 ms (mean 195-217 ms, up to 0.9 s) to about 1 ms
    (mean 11-12 ms);
  - a whole remote Human build fell from a median 143-183 ms to 37-49 ms;
  - switching the quality up from Low finishes every built remote Human at once (about 4 s for
    21 distinct Humans).
- **Hand detail.** Remote Humans built at Low start on a fingerless crowd copy of their
  animation library: 75 instead of 195 tracks per Universal clip, about 12 us less per animation
  update (20 to 8 us per advance on configured actors). The gate gives fingers back within 12 m
  of the camera and keeps them until 15 m. The target, the selection and campaign actors always
  have them. Fingers hold their last pose; a body built far away holds the `Idle_A` grip.
  A swap rebuilds the mixer's track caches (0.2-1 ms for a real actor library), so the gate
  swaps at most one body a frame, to-full first. Deriving the variant costs 20-35 ms once per
  actor library and session, on the first remote Human built at Low. The variants hold about
  13.5 MB at Low (measured). Module: `src/actors/crowd_animation_library.gd`; microbenchmark
  `tests/integration/benchmark_crowd_animation_variant.gd`.
- **Hand cues and live effects.** Only full-rate bodies, priority actors and the player draw
  spell arcs, sparks, weapon trails and the bow release flash. For the others a skeleton update
  falls from about 114-135 us to 4 us (debug build). A body without cues keeps its bow carry,
  draw and release pose and its hand props. Live effects are a quarter of the High limits
  (12/12/8/6, 38 ordinary visuals; Medium draws three quarters, 36/36/24/18).
- **Half rate from 35 m** (45 m at Medium and High; `ActorRenderQuality.full_rate_metres`). The
  native remote presentation's batch classifier keeps 45 m, and Main applies the quality's
  distance over it (`AnimationGate.within_half_rate`).
- **Local cape at 30 Hz** (`ActorRenderQuality.local_cape_step_hz` through
  `CapeCloth.set_step_rate`). Under the 30 FPS cap the solver steps once per drawn frame
  instead of twice:
  - the settled hang is identical (within 0.3 mm) and settles in the same time;
  - the cape swings and trails about 15 % less in a walk, with a 10 % lower peak and about 20 %
    less steady trail in a run;
  - it costs about half of the solver's per-frame time, roughly 0.8-1.1 ms per frame (debug
    build), while the player is in a clip without approved cape motion. Approved cape motion
    and mounted cloth keep their own clocks.
- **Remote motion on the frame clock.** `ReplicatedActor3D.advance_frame_driven`, called first
  in `Main._process`, steps each awake remote actor once per drawn frame with the real frame
  delta (capped at 0.25 s), instead of twice under the 30 FPS cap at 60 Hz physics. The player's
  own actor stays on physics. Arrivals and settles are the same to the frame
  (`tests/test_frame_driven_motion.gd`). Headless microbenchmark: 3.9 to 2.1 us per walking actor
  per frame on a P-core, about 0.1 ms less at 60 walkers and 0.3 ms at 160 (about 2.2 times that
  on the E4 proxy, estimated).

`docs/crowd-presentation-policy.md` has the details. The wave-A measurement compares Low
before and after on the iGPU proxy. The plan targets 0.9-1.2 ms less in the market cell and
2.3-2.9 ms less in the combat cell on E4 at the Performance preset (estimates).

### Memory classes

Caches that hold meshes and textures size themselves by machine class, not by graphics quality.
`src/runtime/memory_budgets.gd` classifies the machine on **every** launch, from the same probe
and limits as `hardware_tier.gd`. The first-run tier, by contrast, is seeded once into a fresh
profile.

| Class | Machine |
| --- | --- |
| small | an integrated, software or virtual GPU (Apple silicon by memory only; a D3D12 Intel iGPU by its name), or about 8 GB of memory or less (8.5 GiB) |
| medium | otherwise about 16 GB or less (16.5 GiB), or memory unknown |
| large | everything else |

CPU threads are not used: a 4-thread desktop with 16 GB is tier low but memory class medium.
Every small machine is also tier low. A 2 GB card is small only through its machine's memory,
because dedicated video memory is not readable from GDScript.

The budget table is in one place, `MemoryBudgets.BUDGETS` (small / medium / large):
- WorldPark: 384 / 1,792 / 1,792 MiB. Preloading on approach and before scripted travel is off
  on small.
- Creature scene cache: 256 / 512 / 1,024 MiB, with idle ages of 20 / 60 / 120 s.
- RL head files: 64 / 192 / 384 MiB.
- RL identity bake: 64 / 192 / 192 MiB, idle 16 / 48 / 48.
- Crowd park pool: 16 / 48 / 48 bodies.

Medium and large keep today's WorldPark, bake and park values. The browser build keeps its
512 MiB WorldPark cap on top. The RL head rows have no reader until a later stage.

Ledgers count bytes with `src/runtime/resource_bytes.gd`, which never reads anything back from
the GPU:
- textures by Godot's own mip and block layout (three-channel formats count as four), with an
  imported texture's mip count from its `.ctex` header; an ImageTexture's chain is not exposed by
  Godot 4.7, so it counts its full chain unless its owner says otherwise, and errs high;
- meshes by their surface strides and indices, plus 20 B per vertex and blend shape (ArrayMesh
  LOD indices and per-instance skinning buffers are not counted);
- packed scenes by walking their SceneState without instantiating them.

**WorldPark by class.** On a small machine nothing is built ahead of the player, neither near a
door nor before scripted travel, so a first interior entry loads behind the arrival curtain. The
client log shows one `world_park {"event":"preload_disabled",...}` per map bind where a preload
would have started. A world is parked only when its estimate fits in what the other kept worlds
leave of the budget (`WorldParkPolicy.remaining`); nothing is evicted to make room. On small
machines:
- the parent territory, within its 256 MiB stream budget, is still parked during an interior
  visit;
- the Town (about 120 MiB) is parked after a visit;
- the Landfall underground (about 1.55-1.6 GiB estimated) is never parked (`park_refused`), so
  re-entering it is a cold load. Since stage B its scenery models are released too once the
  player has left it (FIX-MEM, in the stage B section).

Startup logs `world_park {"event":"budget","memory_class":...,"budget_mib":...,"preload":...}`.
Measured headless: the first Town entry takes about 1.1 s cold on small, against about 50 ms
preloaded on medium, with about 100 MiB less held at the door. Parked returns are unchanged.

**Memory census.** `src/runtime/memory_census.gd` adds a `memory` row to every
`viewport_snapshot` diagnostic (every 30 s), and Main records one `memory_class` diagnostic at
startup with the class, its source, basis, budgets and physical memory. The row costs about
0.2 ms, most of it Godot's `OS.get_memory_info()` on Windows. It reads only counters.

| Part | What it holds |
| --- | --- |
| class | The memory class, where it came from, and its budget row |
| `os` | `physical`, `free` and `available`. On Windows, `free` is the physical memory still available and `available` is the commit headroom. On Linux, `available` is MemAvailable. |
| `process` | Linux: VmRSS, VmHWM and RssAnon from `/proc/self/status`. Windows: none until the native runtime offers `process_memory()`. The QA harness's host sampler stays the source of the working set and private bytes on Windows. |
| `godot` | static memory (tracked only in debug builds, `static_tracked`), the renderer's video, texture and buffer memory, object/resource/node/orphan counts, and pipeline compilations |
| `caches` | `{entries, bytes, budget, evictions}` for the actor scene cache, animation importer, world mesh and texture pools, RL identity bake, WorldPark and the crowd park pool |
| `untracked` | The working set no Godot counter explains: working set minus static minus video on an iGPU. Only when both are available. |

Cache bytes are ledger estimates made when an entry is published, not measured allocations, and
a shared resource can appear in two caches, so the rows are not summed. The animation importer
counts the libraries it built and the source scenes it keeps; a source shared with the actor
scene cache counts its animations only. The animation estimate is per track: 200 B plus keys x
key size x 1.23 (32 B for position, rotation and scale keys, 24 B for blend shapes, 40 B for
value keys; 1.23 is the slack of key arrays grown one insert at a time). Checked against the
debug static counter: 1.06 times on synthetic tracks, and 22.6 MiB estimated for the shared
library against 24.2 MiB for its whole parse. Budgets act on ledgers, never on these counters.

**Actor scene cache.** `GlbSceneCache` keeps a byte ledger per entry, with a domain from the path
(creature, race, hair, equipment, rl_head, world, other). Creature rows are measured at
publication (about 0.1 ms on the main thread); the others are measured by the budget pass in
1 ms slices. Only creature entries that the warm-up prepared on its worker are evicted:
- when idle (every probe mesh's reference count back at its publication value) for the class's
  idle age;
- least recently used first, down to 85 % of the budget;
- by a pass every 5 s and after an over-budget creature publication.

Eviction also releases the creature's animation libraries; a live prewarm skips the entry. The
creature warm-up re-queues an evicted species on its worker, and `evicted_main_rebuilds` counts
any that are parsed on the main thread instead. Races, legacy hair and equipment stay for the
session. A logout (not a reconnect that keeps map resources) also drops the session's parsed
equipment, rebound skins and draped capes (`ReplicatedActor3D.clear_static_caches`).
Diagnostics: `resource_retention.actor_scenes` and the `budget_pass` timing. Test:
`tests/test_glb_scene_cache_budget.gd`. For an A/B run, use `RABBITLANDS_MEMORY_CLASS=large`
(1 GiB, 120 s).

**Crowd park pool.** `CrowdPresentation.park_limit` is the class's `crowd_park_limit`: 16 bodies
on small machines and 48 (unchanged) otherwise. Parked bodies are freed by the gate pass
(`expire_parked_due`, at most every 500 ms), so a departed crowd's bodies are gone 5-5.5 s after
it leaves even when no other actor changes. Before, they waited for the next actor-list change.

### Renderer family and Mobile

`src/runtime/renderer_family.gd` is the one place that tells the rendering methods apart:
- Forward+ and Mobile are the linear (RenderingDevice) family. They share colour trims and cache
  keys (`cache_renderer`).
- Only Forward+ has SSAO and SSIL.
- Mobile and Compatibility light at most 8 lights per mesh instance (`per_mesh_light_limit`).

Look code asks `LookProfile.linear_renderer()`. Tests use `RendererFamily.override_for_tests()`,
because headless runs report the project's method unless `--rendering-method` names another.
The Forward+ and Compatibility look dumps are byte-identical to before
(`tests/fixtures/renderer_family_look_golden.json`).

An explicit Mobile launch (`--rendering-method mobile`, or since stage B the Mobile choice in
Settings → Graphics) now:
- paints the Forward+ trims instead of the Compatibility ones, matching Godot's shaders, which
  already lit Mobile as linear;
- reads the shipped `forward_plus` prepared world (geometry, collision and paving; 404 MB in the
  current release);
- shares the user map caches with Forward+.

The Forward+ and Compatibility cache keys are unchanged, so nothing is recooked and no player
cache is invalidated.

### Actor glTF parse on any thread

Every actor glTF parses through `GlbSceneCache._parse_generate`, which enables
`src/actors/actor_images.gd` on its GLTFState:
- For equipment's imported URI textures, the extension hands GLTFDocument the very texture
  ResourceLoader returns, without GLTFDocument's `get_image()` readback. On the main thread that
  readback was a GPU sync per first-seen texture; on a worker it waited for the main thread.
- Embedded images are decoded by the extension with GLTFDocument's own decoder order and no
  mips.
- The extension is where actor VRAM sidecars (stage B, AT-C2) and the wardrobe CPU capture attach.

`PackedScene.pack()` still waits for the main thread from a worker (about one frame per mesh).
The actor worker path is therefore `GlbSceneCache.prepare_actor` (any thread: parse and generate,
unpacked root), then `install_actor_prepared` (main thread: pack and publish, about 1 ms per
file). Since stage B the actor preparer uses the worker path for remote bodies, the player's own
body and mounts (AW-04a, AW-04d, AW-07). Across all 2,118 actor glTFs the parse gives the same
textures, pixels, materials, nodes and mesh arrays as before. Verification:
`tests/test_actor_worker_parse.gd` (`RL_AW03_SWEEP=full` sweeps every actor glTF) and
`tests/test_package_actor_worker_contract.py`. Diagnostics: `actor_scenes.actor_images` in the
client diagnostics snapshot (`documents`, `uriTextures`, `uriLeft`, `decoded`, `decodeFailed`)
and the `actor_prepared_install` timing.

### Offline actor preparation

These run offline. Apart from the RL head image strip, nothing ships or is read by the game until
later stages.

- **RL hair and beard images (shipped by packaging).** Packages strip the RL hairstyles' and
  beards' embedded PNGs, which are byte-for-byte copies of the `rl_head_textures` maps that ship
  imported (BPTC/DXT with mips) in the PCK. The RL shader materials sample those maps, so the
  embedded copies were only decoded and uploaded as unused RGBA8 textures (4-32 MiB per drawn
  style, no mips). `tools/strip_rl_head_images.py` removes an image only when:
  - its bytes match a shipped map;
  - every material sampling it is one that `RLHeadLibrary.material()` replaces and names that
    map in `extras.texture`;
  - nothing else uses it.

  It verifies every accessor and every other JSON field against the original, and fails the
  build otherwise, or if a map's PCK import is missing. The receipt is `logs/rl-head-strip.json`.
  On develop content: 61 images in 42 of 44 files, a 68.7 MB smaller package (84.1 MB of decoded
  PNG). Checkouts keep the original GLBs, and the drawn result is identical.
- **Actor geometry sidecars.** `src/actors/actor_geometry.gd` attaches package-time LOD chains,
  masked lining bases and optional run compaction to the raw actor glTF parse. Since stage B every
  actor parse calls it (ALOD-C1h); exported builds have no catalogue until release packaging (C9).
  Apply cost (editor binary):
  - 1.2-1.6 ms for an L1 torso, or 2.3-3.3 ms with compaction, depending on the run count;
  - about 6 ms more when the catalogue asks for the actor file hash;
  - 21 ms once to read a full catalogue.

  Kill switch `RABBITLANDS_ACTOR_GEOMETRY=off`; details in `actor-geometry-lods.md`.
- **Actor geometry cook.** `tools/actor_geometry_cache.py` cooks LOD chains for all 2,072 actor
  glTFs in about one minute, on two headless Godot processes, into the ignored developer catalogue
  `.local/actor-geometry/rl-actor-geometry-v1/` (2,061 sidecars, 47 MB).
  - Policy v1 uses Godot's own simplifier on the exact runtime parse. Levels are near 50/25/12/5 %
    and switch no nearer than 8/18/36/70 m at High, and never before the level's error covers 3 px.
  - Per-face-tile soups (torso linings) and seam-crossing proxies (the cape) get no levels.
  - 82 % of source triangles, but only 43-47 % of the drawn market triangles, get at least two
    levels. On the design market census, the chains alone predict 32 % fewer actor triangles at
    High and 42 % fewer at Low (estimate; masks and the far tier come later).
- **Lining masks.** `eloria-assets/tools/lining_visibility.py` finds the generated lining
  triangles that no camera sees over 44 poses (mounted straddles included) and 128 directions.
  The only occluder is the piece's own shell, with a 2 cm margin.
  - On a 20-garment sample it removes 12 % of lining triangles (torsos 0-11 %, legs 14-60 %,
    boots 0-6 %), with 43 changed 3 mm pixels over 7,200 unsampled views.
  - Lining removal alone therefore saves far less than the plan estimated; LOD chains and the far
    tier carry the triangle budget.
  - Offline cost is about 14 hours on four Blender workers for all 400 garments, cached per
    garment.
- **Derived meshes keep LOD chains.** `src/actors/mesh_lods.gd` carries a source surface's index
  chains through the cape fold, armour fit, emblem projection, mounted attachment, beard patch and
  neck skin. With no chains (stage A) every derived mesh is byte-identical to before. Test:
  `tests/test_mesh_lod_carry.gd`.
- **Actor VRAM sidecars.** `tools/build_vram_textures.py --actor-dir <dir>` plans the embedded
  images of the tracked actor GLBs below `godot-client/assets/actors/native/<dir>`.
  - It never plans `rl_heads/`, which is stripped at package time instead, or retired models.
  - It uses the map recipes and floors (BC7 base, BC5 normal, BC1 ORM with a BC7 second chance),
    with one `vram/index.json` per GLB directory.
  - On the wave-2 tree: 697 unique images in 2,069 GLBs, 713 encodes in 4.5 min on one encoder
    process, 678 accepted at the map floors and 19 decoded.
  - That is 632.8 MB of sidecars (900 MiB on the GPU) in place of about 130 MB of embedded
    JPEG/PNG.

  The sidecars and the offline encode are Git-ignored (`assets/actors/native/**/vram/`,
  `/.local/texture-preparation/`).

### Content digests and the native runtime

**Content digests.** Every SHA-256 the client checks at load time can go through `ContentDigest`
(`src/runtime/content_digest.gd`). The digests are byte-identical to `FileAccess.get_sha256`, and
no manifest, cache key or server value changes. `--content-digest=` or
`RABBITLANDS_CONTENT_DIGEST` selects the mode:
- `auto` (default; GDScript until the native backend's own release-build A/B, see stage B);
- `gdscript`: on the main thread a batch is shared by the caller and up to 3 short-lived threads,
  `clamp(cores/2,1,4)` in all; worker-thread callers hash alone;
- `sequential`: the pre-wave-2 cost profile, for A/B runs and as the kill switch;
- `compare`: native qualification.

`RABBITLANDS_CONTENT_DIGEST_THREADS=N[,M]` overrides the main and worker thread counts.
Strictness is unchanged: every call reads and hashes every byte against an expected 256-bit
value, and nothing is remembered between calls. The startup log line
`content_digest stage=backend ...` names the mode, backend and reason. The package digest
(`MapSceneCache.package_digest`) hashes `world.glb` and the CRLF-folded `world.json` in one
batch.

**Native content digest.** The optional `client_runtime` payload contains
`RabbitLandsContentDigest`, a stateless SHA-256 hasher for files and buffers, with digests
byte-identical to `FileAccess.get_sha256`. It uses the CPU's SHA extensions (SHA-NI) where
available and an unrolled portable path elsewhere, streams files in 1 MiB reads, folds CRLF for
`world.json`, and hashes a batch on its own scoped threads plus the caller, never on the
WorkerThreadPool. Measured warm:
- the harrowcrag package digest goes from about 45 ms to about 7 ms;
- the package plus its 218 external images goes from about 175 ms sequential, or 46-55 ms with
  GDScript on four threads, to about 14 ms;
- the portable path is 1.1-1.7 times faster than GDScript on four threads.

`RABBITLANDS_CONTENT_DIGEST_SHA=portable` forces the portable path for qualification.
`tools/native_digest_check.py` compares every file of an install with Python's hashlib: on
release 4a57cea4, 51,467 files (12 GB) matched on both paths. Since stage B `ContentDigest` can
use the class (`native`, `compare`); `auto` keeps GDScript until its A/B.

**Native loader.** The optional `bin/client_runtime` payload is verified and loaded by one
script, `src/runtime/native_library.gd`. It checks the manifest ABI, the engine major and minor
version, the platform, x86_64, the library name, that both files are present, and the SHA-256 of
the library and the descriptor. Only then does it call `load_extension`, once, and only on the
main thread (`off_main_thread` otherwise). Callers keep their own fallback reasons.
`NativeLibrary.ensure()` is the once-per-process entry for later native consumers, and
`NativeLibrary.stats()` reports whether it ran, its code and the verification and load counts.
These are integrity and compatibility checks, not a signature.

**Native crowd kernels in the shipped runtime.** The payload now also compiles the
`native_crowd` cape-constraint, world-impact and spell-flight kernels, and the actor-command
reducer and compact store. Their source stays in `native/native_crowd`, and the payload's
`source_digest` covers it.
- Each class is registered by whichever library loads first: the payload or the benchmark
  `native_crowd.gdextension`. `RabbitLandsClientRuntime.runtime_info().native_crowd_providers`
  reports which library provides each class.
- Nothing changes by default: the kernels and the reducer stay opt-in
  (`ELORIA_NATIVE_PRESENTATION`, `ELORIA_NATIVE_CROWD=1`). With the payload loaded, an opt-in no
  longer needs a benchmark build. Since stage B the payload loads at startup in every profile
  (RB-C1g).
- The DLL grows by about 63 KB, to 1.46 MB (1.49 MB with stage B's exit watchdog and reducer runs).
- `tests/test_client_runtime_crowd_kernels.gd` and the `tests/test_client_runtime_kernels_*.gd`
  wrappers run the registration and parity suites against a payload (`--runtime-dir=`,
  `--expect-native=present`).

### Updates and packaging

- **Release descriptor package.** `app/client-release.json` and its loose copy
  `app/data/client_release.json` are their own `release-descriptor` package. A commit-only
  change no longer rewrites the client pack's package or a records bucket. There is no runtime
  change.
- **Loose duplicates.** The package no longer ships a loose copy of an imported audio or image
  file when the PCK holds its import and nothing reads the file raw. The packager decides this
  from:
  - the running client's path literals, each followed to `load()`/`ResourceLoader` or else
    counted as a raw read;
  - glTF URIs, which are raw unless the actor parse takes the image from the import;
  - the data a package carries and the installer's own reads.

  `check_loose_duplicates` verifies the final PCK. Release 4a57cea4 measured 108 files and
  87.1 MB, including all 71 audio files (83.4 MB). To keep a new file loose, read it raw in code
  or name it in shipped data; to let it go, load it only through `load()`, `preload()` or
  `ResourceLoader`. Older updaters retire the removed loose files through the normal inventory.
- **Per-file updates.** An existing installation now receives only its changed files. The
  updater unpacks changed package members into `.eloria-update-stage/`, journals every rename in
  `.eloria-update-journal-v2.json`, moves replaced originals into `.eloria-update-backup/`, and
  deletes that backup at the commit point. Unchanged files are hashed once, as before, and never
  copied; at the commit point they are stat-checked, and re-hashed only if changed or too recent
  to tell. No whole-game backup is kept after an update. On a 744 MB, 3,000-file synthetic
  install with 123 MB changed:
  - the updater wrote 466 MB instead of 1,086 MB;
  - its peak extra disk fell from 1,077 MB to 466 MB;
  - its install phase fell from 17-19 s to 5-6 s;
  - a crash after any install step is undone in under a second.

  The run on a copy of the real 6 GB install is pending. Details in `docs/client-updates.md`.
- **Setup and uninstall.** Online setup undoes an interrupted per-file update before it plans,
  as the launcher does. Its uninstaller also removes per-file update leftovers (the backup, the
  v2 journal and temporary journals). Its free-space request is unchanged: two downloads plus
  the unpacked game plus 512 MiB. Measured, the fresh-install peak equals two downloads plus the
  unpacked game to within 101 bytes; the extra join copy of a multi-part package never coexists
  with the unpacked files.

## Wave 2 stage B: renderer choice, world distance, actor runtime and hitches (2026-11)

Stage B builds on stage A. Several parts are built and tested but stay switched off until their own gate or a later
stage:
- **Mobile as Automatic's choice on integrated GPUs** stays off (`RendererPolicy.INTEGRATED_RENDERER = ""`) until the
  Mobile re-qualification (G4/MOB-C6) passes. An explicit Mobile choice in Settings works now.
- **Native features.** The verified `client_runtime` payload now loads at startup for every profile (D-NATIVE).
  Native hashing, the cape, flight and impact kernels and the native actor-command reducer still run on GDScript.
  Each one turns on by default only after its own release-build A/B.
- **Actor VRAM sidecars** are not built into release packages (`ACTOR_SIDECARS_RELEASE_ENABLED = False`) until AT-C4
  and the G6 smoke self-test.
- **The actor geometry catalogue** (LOD chains, lining masks, the helmet budget) reaches players only with release
  packaging (ALOD-C9). An exported build has no catalogue and draws exactly what it drew before.
- **The 2D overhead layer** is built but not wired (OV-3).
- **Manifest schema 3** is read but not yet written (UD-05p).

Medium and High draw as before, except for the marker-light budget (LIGHT) and the world distance work (WD-C2, WD-C3,
WD-C5), both described below. At every quality some behaviour changes without changing what is drawn: more map
changes wait behind the arrival curtain (TR-01), actor bodies and mounts appear once their files are prepared (AW-04a,
AW-04d, AW-07), the player's body is kept across map changes (AW-02), and Settings names the renderer Automatic starts
(MOB-C5). Figures are from the development laptop (Core Ultra 9 275HX), mostly headless debug builds, unless marked as
estimates. The stage-B measurement (the MOB-C6 matrix, the WD-C0 matrix and the hitch cells) has not been run yet.

**One release for the world distance work.** WD-C2, WD-C3 and WD-C5 ship together. Geometry policy 5
(`MapGeometryPolicy.VERSION`) and scene-cache format 12 (`MapSceneCache.CACHE_FORMAT_VERSION`) make every installed
geometry, collision, paving, scene-cache and prepared-world entry miss once. Re-cook the shipped `prepared-world` for
that release; until a re-cooked one is installed, clients load raw. Measurements on this branch must re-cook first,
otherwise arrivals measure raw loads.

New A/B switches. `ELORIA_VIEW_REACH` and the overhead switch now block first-run seeding, as the stage-A switches,
`ELORIA_VRAM_TEXTURES` and `RABBITLANDS_CROWD_PRESENTATION` already did. The other new switches change no first-run
graphics and do not block it.

| Switch | Effect |
| --- | --- |
| `RABBITLANDS_INTEGRATED_RENDERER=mobile\|off` | turns the integrated-GPU renderer policy on or off for one launch |
| `ELORIA_WORLD_DISTANCE=off` | turns off the WD-C3 distance pass (ranges, shadow rules, LOD bias) and the WD-C4 far plane on LOW. WD-C5's generated levels still draw, at Godot's bias 1.0 |
| `ELORIA_VIEW_REACH=auto\|ground\|off` | the far plane on LOW and its fog. `ground` adds the ground-fit A/B |
| `ELORIA_WORLD_SCENERY_RELEASE=all\|budget\|0` | the rule for releasing the scenery models of worlds left behind. `0` keeps them until logout |
| `ELORIA_ACTOR_PREPARER=off` | actor bodies and mounts are parsed on the main thread at first use, as before |
| `ELORIA_VRAM_TEXTURES=0` | no VRAM sidecars, actor sidecars included (`ELORIA_ACTOR_IMAGES=legacy` also leaves actor sidecars out) |
| `--native-runtime=off`, `RABBITLANDS_NATIVE_RUNTIME=off`, `[runtime] native_runtime = "off"` in `eloria_hud.cfg`, `--client-safe-mode` | the native payload is neither read nor loaded, and every caller stays on GDScript |
| `--content-digest=native\|compare` | native hashing, or both backends with a mismatch check (`auto` keeps GDScript) |
| `RABBITLANDS_NATIVE_REDUCER=run\|legacy`, `ELORIA_NATIVE_CROWD=1\|0` | the actor-command reducer mode: `run` (R2), per packet (R1, `ELORIA_NATIVE_CROWD=1`) or GDScript. Off wins over on |
| `--exit-watchdog=off\|<ms>`, `RABBITLANDS_EXIT_WATCHDOG` | the exit watchdog |
| `RABBITLANDS_OVERHEAD_2D=on\|off`, `--overhead-2d=` | the launch state of the 2D overhead layer. Nothing creates a layer yet |
| `RABBITLANDS_CROWD_PRESENTATION` with `-hands`, `-frameclock` or `-cues` | Low-tier measurement switches (below) |
| `RABBITLANDS_UPDATE_SCAN_THREADS=1` | the updater's installed-file scan on one thread |
| `RABBITLANDS_CACHE_JANITOR=off` | no stale-cache janitor |
| `--no-split-pck` (packager) | one monolithic `RabbitLands.pck` |
| `--actor-vram-textures` (packager) | stages actor VRAM sidecars. Release and runner builds refuse it while release-enable is off |

### Renderer choice and Mobile

- **Automatic on integrated graphics.** `src/runtime/renderer_policy.gd` decides which renderer Automatic starts.
  On a fresh first run on an integrated GPU (Windows, RenderingDevice working), it can record Mobile and restart into
  it once. The restart uses exit code 75 when the updater announces `renderer-relaunch` in
  `RABBITLANDS_LAUNCHER_FEATURES`, and `set_restart_on_exit` otherwise. **The default is off** until G4/MOB-C6
  passes. The startup record carries `renderer_effective`, `renderer_requested`, `renderer_fallback`,
  `auto_renderer*`, `adapter_class` and `renderer_policy`. A restart is logged as `renderer_restart`, and the
  confirmation after 30 s as `renderer_confirmed`.
- **Updater side.** `LaunchOptions.effective_renderer` applies the same rule as `RendererPolicy.resolve` with the
  policy on. The updater has no policy switch of its own, so turning `INTEGRATED_RENDERER` off works through the
  game's withdrawal on the next ordinary launch. While a recommendation is active, the updater starts it. On exit 75
  it starts the game once more with the renderer the settings now ask for and `--graphics-renderer-restarted`,
  keeping the installation lock. A trial start that exits with an error within 60 s sets
  `auto_renderer_state="failed_start"`. The relaunch costs one extra process start.
- **Behaviour changes that apply now.** The compatibility and safe-mode launchers keep OpenGL even over a saved
  explicit Forward+ choice; before, the game tried to restart into Forward+ and hung. A pending renderer restart skips
  Main's setup (`Diagnostics.restart_pending()`), so a direct launch whose saved explicit renderer differs from the
  running one now restarts (or exits with 75 under the updater) instead of stopping after one frame.
- **Settings → Graphics** names the renderer from `RendererFamily.method()`, so Mobile is no longer labelled Forward+.
  - The menu offers Automatic plus the renderers the launch code can start (`RendererPolicy.supported_renderers()`):
    Forward+, Mobile and OpenGL Compatibility.
  - The Automatic item names what Automatic starts on this computer, for example "Automatic (Forward+)", or
    "Automatic (Mobile)" while a recommendation is active.
  - The tooltip names the running renderer, graphics API and adapter, with one line per choice.
  - A note appears when a RenderingDevice renderer was asked for but OpenGL runs, or when Automatic's recommendation
    failed. A direct developer launch with `--rendering-method gl_compatibility` while the choice is Automatic shows
    this note too, because Godot consumes the flag before the game sees it.
  - The restart notice shows only when the choice starts a renderer that is neither running nor this launch's request
    (`SettingsWindow.renderer_restart_needed`).
  - The window reads ClientDiagnostics' startup `reconcile` result (`RendererPolicy.launch`) instead of parsing the
    settings file again.
  - Testers: `RABBITLANDS_INTEGRATED_RENDERER=mobile` shows "Automatic (Mobile)" for a profile with an active
    recommendation.
- **Mobile ground pre-pass (MOB-FIX).** Godot's Mobile renderer has no depth pre-pass for `depth_prepass_alpha`
  materials: it draws them only in its transparent pass, sorted by distance and writing no depth. The painted walk
  decks and solid ground patches rely on Forward+'s pre-pass. Without it, a deck's dark edging band drew black seams
  across crossing decks, and nearer-sorted cobble patches painted over the decks.
  - Under Mobile only, `LookGround.mobile_prepass` chains an opaque, unshaded copy of each such material as its
    `next_pass` (`painted_ground_deck_prepass` / `painted_ground_overlay_prepass`). The copy keeps the fragments
    Forward+ keeps (alpha ≥ 0.99) and writes their depth. Glazes below 0.99 get none, as on Forward+.
  - Forward+ and Compatibility are unchanged; their preprocessed shaders are identical. The look paints after the
    cache snapshot, so the shared Forward+/Mobile caches never hold a pre-pass.
  - Cost on the iGPU proxy: GPU below same-process noise; about +12 MiB working set and about 10 pipelines at Four
    Gates.
  - Rendered check: `tests/integration/rendered_mobile_ground_parity.gd`, once per renderer.
- **Mobile working set.** Mobile's working set above Forward+ is outside Godot's heap: it is driver memory per
  compiled pipeline. Godot's static memory is equal, and video memory is lower under Mobile. It varies by session (-2 %
  to +7 % at the plaza in stage A, about +3 % on the stage-B tree), so compare peaks in brackets, not single pairs.
- **For G4/MOB-C6.** Godot consumes engine flags such as `--gpu-index` and `--rendering-driver`, and neither
  `set_restart_on_exit` nor the updater's relaunch carries them. A first-run restart started with `--gpu-index 1` on
  the dual-GPU laptop therefore reopens on the default (discrete) GPU. To measure the restart on the iGPU, use a
  pre-seeded `trial` profile (through the updater it starts Mobile directly, with no environment variable) or the
  per-app GPU preference.

### Marker lights (LIGHT)

- `src/world/light_marker_budget.gd` keeps the marker lights nearest the camera focus lit: N = 6 / 12 / 24 at LOW /
  MEDIUM / HIGH, and never more than `RendererFamily.per_mesh_light_limit()` (8) in Mobile and Compatibility. Main owns
  one budget, binds it to each map's marker rig and ticks it every frame.
- The lights are chosen again at 5 Hz, after a 1.5 m focus move, and before the frame whenever SecretSections shows or
  hides a light. Changes fade over 0.3 s. On the limited renderers a light fading out keeps its slot, so no more than
  8 are lit on any frame; Forward+ fades across, with at most N + 2 lights.
- Lights are switched by gates (`LightMarkerBinder.gate_for`), never by `visible`, which SecretSections owns. A gate
  is added only when its light first goes out.
- `LanternMineLighting` leases its lamps (`LEASE_META`), so their energy is never faded. Its own nearest-8 fallback
  runs only where no budget manages the markers (cutaway stage lights).
- NightLamps keeps at most 6 lights and Weather3D at most 2 fire lights on renderers with a per-mesh limit (6 + 2 = 8
  per chunk ground mesh). Forward+ is unchanged.
- **What players see.** On Forward+ LOW, rooms with more than 6 marker lights show 6 (the Lantern Mine 6 of 18); at
  MEDIUM the town castle and the tavern's upper floor, and at HIGH the largest Insides caves, show fewer lights too.
  Forward+ HIGH in Landfall Town is unchanged. On Mobile and Compatibility at MEDIUM and HIGH, street lamps and fires
  go to 6 + 2 lights (from 8 + 4 and 12 + 8).
- Diagnostics: `main.light_marker_budget.stats()`. Cost (headless indication): 4-59 µs per timed choice, up to about
  0.6 ms once per room entered in the 78-light serpent undercity.
- Not budgeted yet: manifest environment lights (`WorldEnvironmentBinder._apply_lights`; up to 61 in gauntlets) and
  the scripted scene lights.

### World distance (WD-C2, WD-C3, WD-C4, WD-C5)

- **Size-class batch cells (WD-C2).** Continent and gauntlet static batches are split into size-class cells (S 32 /
  M 48 / L 64 / XL 96 m, by the instance's mesh-box radius times its scale, `src/world/world_distance_classes.gd`).
  Batch membership is unchanged, so the look passes, the paving cache, gauntlet contrast and the season passes see the
  same members; each split batch stands at its members' centre. Interiors and other maps keep their batches unchanged.
  - Landfall (34 chunks) plus Harrowcrag: 271 → 1,182 batches (Landfall 2.6x, the gauntlet 6.8x). The batching phase
    costs about +0.5 ms per chunk (mostly on workers) and +17 ms on the gauntlet; whole loads are within noise. A
    cooked Harrowcrag arrival adds about 350-410 ms of main-thread publish (estimate for the low-end reference: about
    1 s).
  - Computed main-pass primitives at the default view: -36 % on Landfall, -64 % on Suncoil, -35 % on Coilmere. Draws
    rise in wide views until WD-C3's ranges.
  - Full painted only: batched crowns re-shuffle their jitter seeds, and near region borders a crown takes its tint
    at its smaller batch's centre.
- **Runtime distance pass (WD-C3).** `src/world/world_distance.gd` classes every loaded continent territory, chunk and
  gauntlet after the cache snapshot and before the look pass.
  - Class-split batches, pooled placements and own meshes join one group per size class and extent step. They are
    culled beyond `camera bucket (8 m) + reach × quality scale + their own extent + 4 m`. Reach from the focus is S 30,
    M 70 and L 160 m at HIGH (×0.8 at MEDIUM, ×0.6 at LOW); XL is never culled. Nothing within the player's reach is
    culled at any zoom, and nothing is culled while a film owns the camera.
  - S and flat props, ground patches, flat walk decks, and `Terrain_` pieces beside an opaque base stop casting the
    sun's shadow. Flat means under 0.35 m tall, or under 1 m and under 0.15 times the footprint's narrower width (a
    slab, deck or pad); long low walls and wide enclosures such as a palisade ring keep their shadow.
  - Every classed node takes the quality's LOD bias (HIGH 1.0 / MEDIUM 0.4 / LOW 0.15).
  - Main's `WorldDistance` node follows the camera's orbit distance, the graphics quality and the film flag. It
    re-applies the ranges with one `set_group` per group when one of them changes (0.35-1.2 ms per 1-2k ranged
    nodes). A tree stamped with an older state is re-applied as it enters the scene.
  - Cost of the pass: about 1-3 ms per chunk (on the worker for background chunks, on Main for geometry-cache
    arrivals) and about 20 ms for a gauntlet. Caches stay tier-neutral: the loader restores the pass's values for a
    pack.
  - Main-pass estimates (world_draw_budget port) at 90 m and -15° on HIGH: Landfall 486 draws / 2.09 M primitives →
    380 / 1.54 M, Suncoil 611 / 2.28 M → 312 / 1.10 M.
  - The camera probe records `world_distance` (Main's snapshot).
- **Far plane on LOW (WD-C4).** On LOW, outdoor maps with fog draw to the orbit distance rounded up to 8 m, plus
  200 m (232 m at 26 m, 296 m at 90 m). The fog is fitted so that it is whole 10 m before the cut: a depth fog ends
  there and is opaque, and an exponential map fog becomes a depth fog from 80 m on curve 2 in its own colour.
  - MEDIUM and HIGH keep the scene's 1800 m and their fog. The plan's 300/400 m would clip ground that stays resident
    beyond the 320 m retain distance, which is measured to bounds.
  - `src/world/view_reach.gd` runs from the camera rig in `RenderingServer.frame_pre_draw`, over whatever the binders
    last wrote. Outdoor means `WorldEnvironmentBinder.horizon_map`.
  - `ELORIA_VIEW_REACH=ground` also narrows the renderer's camera to the sampled visible ground (+25 % + 16 m) whenever
    every ray meets ground, as an A/B for content hidden behind the ground.
  - Probes read `camera_rig.camera_diagnostics().view_reach` (`far`, `horizon_far`, `drawn_far`, `ground_far`,
    `fog_fitted`). `Camera3D.far` reports the far plane, not the ground fit.
  - The sun's shadow fit and the far plane share one ground sampler (`ViewReach.shared_depths`): 28 rays, one cast per
    frame, pose and lens.
- **Generated prototype LODs (WD-C5).** Shared prototypes carry generated LODs: 273 of the 532 placed prototypes, with
  79 % of placed triangles. `ExternalMeshPool.acquire` generates them (`ImporterMesh.generate_lods(25, 60)`) for every
  prototype with at least 600 triangles and a mesh-box half-diagonal of at least 1.5 m. Godot's 1 px rule picks the
  level, scaled by WD-C3's LOD bias.
  - At 1280×720 over the Landfall and Suncoil spawns, with C2 and C3 on: main-pass primitives fall 13-42 % at HIGH and
    22-54 % at LOW, and shadow-pass primitives 36-42 % at HIGH. Draw calls are unchanged.
  - The pixel difference is at most 0.09 % at HIGH. At LOW it is 3-5 % at 90 m, where foliage and thin trunks thin out.
  - The levels switch under Forward+, Mobile and Compatibility.
  - A raw parse spends about 2.6 ms per new prototype generating them (on the worker for background chunks). Cooked
    arrivals spend nothing: the geometry cook stores the levels.
  - The census counts the level indices (`world_meshes.prototype_lods`, `rl_lod_index_bytes`).

### Scenery of worlds left behind (FIX-MEM)

Stage A's small memory class refused to park the Landfall underground but released only its nodes: GlbSceneCache kept
its 155 scenery models (1.47 GiB) until logout. The cache now records which worlds used each world model, from the
map WorldPark names when it publishes or instantiates one (`GlbSceneCache.set_world_scope`).

- WorldPark tracks the worlds the player has left. A world is left when the park frees it (refused, evicted, a
  dropped preload) or when a map change that is not seamless lets it go; a seamless crossing counts at the next change
  that is not one. A world is resident again once it is the destination, bound, parked or preloading.
- While a world is left, `WorldPark.tick` drops the models that only left worlds used, once nothing holds them (mesh
  reference-count probes), in at most 2 ms a frame. On **small** machines it drops all of them. On **medium and large**
  machines it drops least recently used first, and only while what left worlds keep exceeds the 1,792 MiB budget minus
  the parked and preloaded worlds, so nothing changes unless a session outgrows it.
- Each burst logs `world_park {"event":"scenery_released",...}`, and `resource_retention.actor_scenes` reports
  `world_releases`, `world_released_bytes`, `world_retained_bytes`, `world_released_main_rebuilds` and the other
  `world_*` counters. The memory census row carries `world_released_bytes` and `world_retained_bytes`. The browser
  build retires sources by file pins and is unaffected.
- Measured on the iGPU proxy as small: after leaving the underground, video memory returns to its level before entry
  (785-815 against 765-781 MiB), and the `landfall_town_park.gd` WorldLoader + WorldPark script returns 1.68 GB of
  private bytes. The live client returns 0.3-0.56 GB within 20 s; the remaining ~1.6 GB is reused by the next load
  (MEM-M8).
- The cost: going back into the underground on small is a full cold load (a rendered settle of 11.5-14.3 s, against
  4.1 s parked on medium).

### Actor runtime: sidecars, worker preparation and the player's body

- **Actor VRAM sidecars at runtime (AT-C2).** The actor image extension (`src/actors/actor_images.gd`) now also reads
  the offline actor sidecars (stage A's AT-C1) when a GLB directory carries `vram/index.json`. An embedded image whose
  SHA-256 the index lists, in a format the renderer samples and encoded for every role this GLB samples it in, becomes
  that sidecar: BC7, BC5 or BC1 with its whole mip chain, checked like the map sidecars (file hash, header, size, DDS
  dimensions, format and mips). Anything else is decoded as before, without mips (`FALLBACK_MIPS` off).
  - Every embedded actor image is shared by SHA-256 across GLBs in a weak pool (16 race bodies on two atlases, 162
    legacy hair GLBs on four images). Even without sidecars, a market of races holds about a third less actor texture
    memory (headless bench: 916 → 680 MiB for 55 actor GLBs; 222 MiB with sidecars). It costs one SHA-256 per embedded
    image per parse (about 2.3 ms/MB).
  - Calls are matched to bufferView images by length and sampled bytes in image order, never to AW-03's URI
    placeholders, and a post-parse size and format check refuses to publish anything that is not where it was
    matched. `rl_heads` and data: or loose images never take sidecars.
  - Switches: `ELORIA_ACTOR_IMAGES=legacy` (plain parse), `nomips`, `ELORIA_VRAM_TEXTURES=0` (no sidecars),
    `ELORIA_ACTOR_VRAM_SELF_TEST=assets/actors/native/races` (the package smoke line
    `actor_images self_test ok entries=… format=… mips=… decompress=ok`). Diagnostics: `actor_scenes.actor_images`
    (counters and `pool`).
  - Do not stage race sidecars for windowed play before AT-C4: the wardrobe dye readback would receive BC7.
  - Verification: `tests/test_actor_images.gd`. The AW-03 sweep (`RL_AW03_SWEEP=full tests/test_actor_worker_parse.gd`)
    still finds all 2,118 actor glTFs equal to the plain parse in a checkout without sidecars.
- **Actor geometry hook (ALOD-C1h).** Every actor glTF parse hands its state to `ActorGeometry.apply` before
  `generate_scene()`, on the main thread and on the workers. Without a catalogue (every exported build until C9) this
  costs 62-72 µs per actor parse (about 0.1 % of a 57 ms parse). With the stage-A cook as a "parsed" root, the median
  is 1.3 ms and p90 4.8 ms per first-seen file; as a "file" root (the developer default), median 3.1 ms, p90 15.9 ms
  and up to 213 ms for a 52 MB creature (the file hash). Counters: `resource_retention.actor_scenes.actor_geometry` and
  the cache timing `actor_geometry_apply`. Kill switch `RABBITLANDS_ACTOR_GEOMETRY=off`. An editor run in a checkout
  that has the developer root `.local/actor-geometry/rl-actor-geometry-v1/` draws its cooked chains, so pin
  `RABBITLANDS_ACTOR_GEOMETRY=off` for like-for-like rows.
- **Remote bodies wait for their files, parsed on a worker (AW-04a).**
  - A remote actor's body (players, NPCs, every race; creatures as before) is built only once the actor glTFs it reads
    are in GlbSceneCache. Until then it stands as its deferred node.
  - `src/actors/actor_asset_closure.gd` names those files from the presented record with the actor's own lookups: the
    race scene, the game hairstyle, every worn piece with the race's fit variant, and a bow's arrow. A portrait
    Human's RL hairstyle module below High goes to `RLHeadLibrary.request`.
  - `ActorResourceWarmup` parses them one at a time on its worker with `GlbSceneCache.prepare_actor` (parse and
    generate, never pack), and reads the equipment pieces table there from the unpacked root. Jobs go most urgent
    first: the player's own (AW-04d), then selected, target and staged actors, then those within the build radius,
    then mounts, then the rest.
  - Main publishes one file a frame (`install_actor_prepared` packs it, about 1-4 ms) with its pieces, and charges the
    time to the frame's actor work. The worker pauses while 2 parsed roots wait.
  - A file the worker cannot prepare is parsed by Main on first use, as before. So is everything on the web build,
    with prepared content, under `ELORIA_ACTOR_IMAGES=legacy`, or with `ELORIA_ACTOR_PREPARER=off`; the kill switch
    restores the old behaviour exactly. A body wanted while the game view is hidden (before login) is built as before
    too, because no frame drains the preparer then (AW-07's rule for mount binds).
  - Diagnostics: the `actor_preparer` row in the client snapshot (`closures`, queued, awaiting, fallbacks,
    `filesPublished`, `piecesPublished`, `priorityRaises`, worker and publish time). `actor_scenes.lookup_misses` and
    the `cache_miss_build` timing show any main-thread parse that remains.
  - Verification: `tests/test_actor_asset_preparer.gd` and `tests/test_actor_preparer_contract.py`.
- **The player's own body waits behind the curtain (AW-04d).** While the arrival curtain is up, the player's body is
  built only once the actor preparer holds the glTFs it reads, at the preparer's most urgent class
  (`PRIORITY_LOCAL`). Its RL files go through `RLHeadLibrary.request` (the RL hairstyle below High; at High in the
  game, the RL head's head, hairstyle and beard modules).
  - The closure is asked for as soon as the player's record is known while its build is held (a map change waiting
    for its curtain, an arrival whose ground streams in), so the parses overlap the world build.
  - The wait is bounded (`src/actors/local_avatar_prep.gd`): 6 s from the first ask, then the body is built as before.
    A file the worker could not prepare counts as ready.
  - Built at once, as before: with the curtain down, on the web, with the preparer off, and for the body AW-02 held
    across the map change.
  - Diagnostics: the client snapshot row `local_avatar_prep` (waits, outcomes `ready`/`timeout`/`uncurtained`, early
    requests, last and maximum wait), a `local_avatar_prepared` record per waited build, and the preparer counters
    `localStartsPastLimit`, `localPublishedFirst` and `pendingLocalFiles`. Verification:
    `tests/test_local_avatar_prep.gd`.
- **Mount visuals outside the packet handler (AW-07).** A rider's first mount bind of a species used to parse the
  mount's creature GLB and the borrowed saddle GLB, and read two JSON files, inside the `mount_states` packet handler
  (0.9-2.9 s on the development laptop).
  - `MountProfiles.read` and `MountedPlayerVisual.animation_map` now parse each file once per process and hand out
    deep copies. `ActorAssetClosure.mount_closure` names the mount's scene and the borrowed tack's source, and the
    actor preparer prepares them on its worker. The mount's clips are retargeted on Main from the cached parse (about
    1-3 ms headless).
  - The mount visual's script (`mounted_player_visual.gd` and the mount scripts it preloads) loads on a
    ResourceLoader thread with the first mount files; compiling it on Main cost 177-192 ms on a session's first bind.
  - `main._apply_actor_mount` builds a mount visual only when its files are cached. Otherwise the rider is kept in
    `_mount_binds` (`src/mounts/mount_bind_queue.gd`) and drawn as it is (on foot, or on the mount it shows) until the
    files are in. A remote rider's ready bind is made by `_bind_pending_mounts` in Main's per-frame actor work, at most
    one a frame and within the actor work budget (own, selected, target and binds kept for 1 s go regardless).
  - Bound at once: in a body's own build or revival; the player's own when its files are ready or behind the arrival
    curtain; and as before with the game view hidden, on the web, and with the preparer off. A remote rider's body
    waits for its mount's files too (the AW-04a gate), so it is built on its mount. The player's own body behind the
    curtain waits for the ridden mount's files within AW-04d's 6 s.
  - Diagnostics: the client snapshot row `mount_binds`. Verification: `tests/test_mount_bind_prep.gd`.
- **The player's own body across map changes (AW-02).** A map change that is not a seamless crossing (a door, a
  teleport, a gauntlet entry, a same-map relocation) no longer rebuilds the player's body.
  - KILL_ALL_ACTORS or CHANGE_MAP's teardown hides it as a parked crowd body (invisible, `PROCESS_MODE_DISABLED`, not
    pickable, paused) after `ReplicatedActor3D.prepare_for_relocation()` has dropped the old map's motion, lean,
    markers, command memory and clip. It stays under `world_root` but out of `actor_nodes`.
  - The ADD the server sends after YOU_ARE wears it again when its actor id, identity key and model id match
    (`_adopt_local_avatar`: `rebind_map`, the parked-body revival, a cape reset at the new place). Changed equipment
    or appearance is applied on the kept body. Otherwise, and after 15 s, at session end or at close, it is freed and
    the ADD builds as before.
  - A death, a staged scene, the character intro and a held dialogue portrait are never held.
  - Diagnostics: `local_avatar_hold` in the client snapshot (`holds`, `adoptions`, `lastWaitMsec`, `releases`,
    `refusals`) and the `local_avatar_adopted` / `local_avatar_released` events. An adoption records no actor build,
    so `actor_creation_budget.totals.builds` and `slow_actor_creation` drop by the player's rebuild per map change.

### Actor geometry cook (ALOD-C4, ALOD-C11, ALOD-C5)

These change the developer catalogue only; players see them once release packaging ships a catalogue (C9). Details
are in `actor-geometry-lods.md`.

- **Lining masks (C4).** The cook drops lining triangles that no sampled pose and view can see (C3 masks, 2 cm margin)
  and keeps LOD chains that never draw more than before. Lossless masks remove about 1-2k triangles per equipped Human
  at close range (kit B -4 %, kit A -10 % of lining) and almost nothing at the default camera (market census -0.16 %
  at High, 0 at Low): leg linings already draw their coarse levels there, and torso masks remove 0-2 %. The triangle
  budget has to come from vertex-colour torso linings (C10) and the far tier (C7).
- **Race-refit helmet budget (C11).** Race helmet refits that carry more than twice their Human helmet's triangles
  (Votary refits up to 38.6k against 1.3k) are capped by the cook at a simplified base that meets the 3 px / 8 m clamp:
  326 of 896 refits, 1.71 M → 0.72 M base triangles. The saving is mostly close up (mean 5.2k → 2.2k per refit at 3 m,
  2.6k → 2.1k at 8 m). At the default 26 m camera the v1 chains already draw 1.5k (0.1k fewer now), and the benchmark
  market (Human kits) does not change.
- **LOD ladder (C5, gate G5: go).** `tests/integration/actor_lod_ladder.gd` (windowed) measures what an actor draws as
  the gameplay camera (FOV 50, 1920x1080) backs away 4-70 m, per quality and renderer, against the LOD rule's
  prediction; `actor_lod_ladder.py gate` judges G5. Compatibility selects exactly the levels Forward+ selects (96/96
  cells, 3 px and 6 px cooks). Mobile draws exactly what Forward+ draws, shadows included. The renderers differ only by
  the RL head (Forward+ and Mobile only, by design). With the 3 px cook an equipped Human (kit B) draws 38.4k
  primitives at 26 m on High (plain 52.9k), 29.5k on Medium and 27.4k on Low (plain 47.4k); a Glasswarden 12.5k /
  10.6k (plain 39.4k). About 21k per equipped Human has no chain (the torso lining soup and the cape), so the ~25k High
  budget needs C10/L2 and a cape chain. Index LODs cut raster and vertex-shader work, not skinning; frame time is C8's
  to measure. `ActorRenderQuality` also has the far-overlay API C7 will wire (`apply_actor(model, level, far)`,
  `far_by_rank`).

### Map changes behind the curtain (TR-01)

- **What now waits.** Every map change that is not a seamless crossing waits for a drawn arrival curtain
  (`arrival_curtain.has_drawn()`) before Main binds the new world and builds its actors. Before, only a cold whole map
  waited. Now so do a streamed territory loaded fresh, a resident neighbour reached without a seamless crossing (a
  non-continuous exterior handoff), and the ground a respawn or gauntlet exit prewarmed.
- **What does not.** Doors into worlds WorldPark keeps or builds ahead keep their uncurtained transition, and so do
  seamless crossings, the character intro and same-map relocations.
- The kind is judged before anything is taken (`_map_change_curtain_kind`), because taking hands the world over. The
  exterior handoff is judged from the camera focus at CHANGE_MAP time. A waiting prewarm is not discarded by the "not
  dead" death state that follows a respawn's CHANGE_MAP. The local RL head is prewarmed on a worker only during long
  waits (whole map, web files, WorldPark worker).
- **Grounding wait.** Behind the curtain, a built character that has found no ground for 1 s (its own cells are in,
  and its only ground is a neighbour's preview layer beside a seam) has its exterior neighbours updated from where it
  stands. Before, the curtain waited out its 60 s limit.
- **Off-map positions.** `ContinentChunkStream.ensure_position` no longer re-primes for a position no cell covers
  (`covers()`). That re-prime retired the focus's ground and orphaned its worker on every actor update while the player
  stood off the territory's cells. It is logged once per stretch as `arrival_off_map`.
- Diagnostics: `map_change_curtain` in the client snapshot (`deferrals` per kind `whole_map`, `streamed`, `exterior`,
  `prewarm`; `pending`, `last_wait`, `grounding_waits`, `grounding_updates`), the events `map_change_curtained {map,
  kind}` and `arrival_grounding_neighbours`, and the chunk event `arrival_off_map`.

### Low tier follow-up (FIX-CPU)

- **Measurement switches.** `RABBITLANDS_CROWD_PRESENTATION` (runner `--variants=`) takes `-hands` (no fingerless crowd
  variant), `-frameclock` (remote motion on the physics ticks) and `-cues` (hand cues for every body) under any policy.
  `describe()` / `crowdPolicy` reports `tierHands`, `tierFrameClock` and `tierCues`. Medium and High use none of them.
- **What the Low tier saves per body in a market** (Performance preset), measured in one process
  (`tests/integration/benchmark_low_tier_market.gd`, E4 proxy, 48 Humans in the market tier mix, two runs): fingers
  19-30 µs per stepped animation update and 18-44 µs per full-rate body; frame-driven motion 14-15 µs per walking body
  per frame (30-45 % of its motion cost, because per-event work and the transform notifications do not halve).
  Together -0.43..-0.69 ms (22-25 %) for 48 bodies, about -0.6..-1.0 ms for a 69-body market (estimate). Stage A's
  cross-tree figure (-0.34 ms) under-reads it: its stage-A runs ran in a slower host state (+3-11 % on unchanged
  components, +1 ms world GPU).
- **High combat after stage A** is unchanged in code terms: stage A's per-frame work at High is under ~0.05 ms
  (estimate), and the +0.7 ms in stage A's C5 cell is a host factor shared by unchanged engine phases. Main no longer
  calls the frame clock's step at Medium and High.
- For the wave-B C5 repeat: `--memory-class medium` in both trees (medium and large behave the same in the crowd cells
  today), and the main thread on the favoured cores (`--affinity C00000`) or the hostmon regime classifier.

### Native runtime, digests, the reducer and the exit watchdog

- **Native runtime at startup (RB-C1g, D-NATIVE).** A package with the verified `client_runtime` payload loads it once
  at `Main._ready`, in every profile, after the `geometry_preparation` stage (`NativeLibrary.startup()`; log line
  `native_runtime stage=startup code=… switch=… source=… us=…`; 6-11 ms on the dev laptop's debug build). That moves
  the verify and load that mounted cape arithmetic used to pay in its first frame. Loading registers classes only.
  One switch keeps the payload unread and unloaded and every caller on GDScript: `--native-runtime=off`,
  `RABBITLANDS_NATIVE_RUNTIME=off`, safe mode (`--client-safe-mode`, which also hashes `sequential`), or the support
  setting `[runtime] native_runtime = "off"` in `eloria_hud.cfg`. The safe-mode launchers of packages without the
  updater set `RABBITLANDS_CONTENT_DIGEST=sequential` and `RABBITLANDS_NATIVE_RUNTIME=off`.
- **One kernel loader.** `src/runtime/native_crowd.gd` hands the kernels and the reducer to their callers. It loads the
  payload through `NativeLibrary.ensure()` and uses a class only when `runtime_info().native_crowd_providers` names
  `client_runtime`. The benchmark extension `bin/native_crowd.gdextension` is used only with
  `ELORIA_NATIVE_PROVIDER=benchmark`. No other game script calls `load_extension`. The kernels stay opt-in
  (`ELORIA_NATIVE_PRESENTATION`, `ELORIA_NATIVE_CROWD=1`; `NativeCrowd.DEFAULTS` are all off).
- **Native content digest (NH-A2).** `ContentDigest` can hash with the payload's `RabbitLandsContentDigest`, which uses
  SHA-NI where the CPU has it and a portable path otherwise, on its own threads. Digests are byte-identical, and strict
  per-load verification is unchanged.
  - At startup, directly after the native load, `ContentDigest.initialize()` self-tests the class: NIST vectors, the
    payload's own files against the loader's SHA-256, and a CRLF-folded file. Any failure keeps GDScript.
  - Modes: `auto` (default), `native`, `gdscript`, `sequential`, `compare`. `--client-safe-mode` means `sequential`,
    and an unknown or empty mode no longer escapes it. `gdscript` and `sequential` never touch the DLL.
  - `auto` does not hash natively until its release-build A/B (NH-A7, D-NATIVE). It still reports
    `native=ready self_test=passed` in the `content_digest stage=backend` line.
  - `compare` hashes every row both ways, returns the FileAccess value, logs and counts any mismatch, and turns native
    off for the session. Rows native cannot open are read again by GDScript, and a refused call falls back for that
    call. PCK-resident `res://` paths of an exported build always stay on GDScript.
  - Measured over a tour of 10 maps and 200 chunks (210 packages, 2.18 GB, debug build, warm cache): sequential
    10.0 s, gdscript ×4 3.1 s, native SHA-NI 0.77 s, native portable 2.7 s. The `compare` tour gave 0 mismatches over
    10,862 rows on both SHA paths. After the native load, the probe (1.8-2.7 ms) and the self-test (1.8-2.5 ms) add
    about 4-5 ms at startup.
- **Actor-command reduction (RB-C7, rust-batch R1/R2).** AppState reduces ADD_ACTOR_COMMAND packets in one of three
  modes. `gdscript` (the default) is the original per-command loop. `packet` (R1, `ELORIA_NATIVE_CROWD=1`) runs
  `NativeCrowdReducer.reduce_packet` once per packet. `run` (R2, `RABBITLANDS_NATIVE_REDUCER=run`) only appends each
  command packet to a run, then reduces the run in one `reduce_run` call before anything else can read the actors:
  before the next other packet, at `Network.dispatch_drained` (the end of each dispatch pass, inside its budget), at
  512 commands, before `take_changed_actors`, on a connection change and at the end of the frame.
  - The result is the GDScript loop's, byte for byte, including step-stamp keys and their insertion order
    (`tests/test_native_crowd_run_parity.gd`). The only visible difference is that `actors` is announced once per
    flush instead of once per packet. The local actor's command 19 and corrupt records are reduced by the GDScript
    loop in their place, and any other native answer fails closed to GDScript for the session.
  - A 2,400-command burst costs 13.5 ms in the GDScript mode, 7.8 ms per packet (R1) and 2.0 ms as a run (R2); with
    server-time stamps 16.7, 10.4 and 2.25 ms (debug build). Steady market dispatch (about 1 packet per frame) is
    about 0.17 ms in every mode.
  - `RABBITLANDS_NATIVE_REDUCER=legacy` or `ELORIA_NATIVE_CROWD=0` forces GDScript; off wins over on. The mode stays
    `gdscript` until the reducer's own release-build A/B. `AppState.actor_reducer_stats()` reports the mode and the run
    counters. Both native reducers now insert missing fields as String keys, as GDScript does; before, sparse records
    got StringName keys, which `==` hid.
- **Bounded close and exit watchdog (AW-01).** `Main._close_client` waits for the actor warm-up, the RL head parse, the
  exterior preload (and the orphans it reaps) and the WorldPark preload through `ExitDrain.wait_until`, for at most 8 s
  per stage, and a repeat close is ignored. It then calls `ExitDrain.quit`, which prints `exit_drain
  result=clean|timeout ... stages=... watchdog=...` and arms `RabbitLandsExitWatchdog` from the `client_runtime`
  payload. The `--prepare-map-geometry` quit goes the same way.
  - If the process is still alive 10 s after `quit()`, the watchdog appends one `exit_watchdog fired` line to
    `user://logs/exit_watchdog.log` and stderr and ends the process with the same exit code (TerminateProcess /
    `_exit`). It never loads the library: without the payload, with the runtime switched off (safe mode included) or
    with an older payload, the close quits as before and `watchdog=` names the reason.
  - On the dev laptop, AW-00's exit-hang control (quit during an RL head parse) hangs indefinitely without the
    watchdog and ends 10.06 s after quit with it. A drained close exits 0.14-0.28 s after quit (35 of 35 runs).
  - `ExteriorRegionStream._exit_tree` now orphans its preload worker on the default (legacy) admission too. Before, the
    worker stayed on the freed node, and the stage-A tree crashed at exit (rc 139) in that case.
- **Diagnostics.** The `RABBITLANDS_OPTIMIZATION_STARTUP` receipt carries `content_digest`, `native_runtime`,
  `native_kernels` and `exit_watchdog`. The client diagnostics snapshot carries `native_runtime`, `native_kernels`,
  `actor_reducer` and `content_digest`.

### 2D overhead layer (OV-1, OV-2; not wired)

- `src/ui/overhead/` holds the layer that will replace the layer-20 Label3D text pass (OV-3 actors, OV-5 world labels,
  OV-6 removal). Nothing in the game creates a layer yet.
- **How it draws.** OverheadItems are retained RenderingServer canvas items under one Control above the game view,
  placed in `frame_pre_draw` from the world camera with the fixed-size scale (`OVERHEAD_PIXEL * P11 * H/2`). Order is
  far to near within each pass and batch group: font size for text, texture for icons and bars. Text is rasterised at
  its final size, by explicit oversampling.
- **Batching.** Godot 4.7.2 batches 2D draws only while they share a texture, and every font size, outline size and
  icon has its own. Batch groups therefore decide the cost: 300 banners cost 6 canvas draw calls, against 1,190 in
  strict per-pass order (all three renderers, windowed probe).
- **Switch.** `RABBITLANDS_OVERHEAD_2D=on|off` or `--overhead-2d=` sets the launch state, and
  `OverheadLayer.set_enabled()` switches every layer within a run.
- **Measuring.** Read `last_update_usec`, `items_drawn`, `rerecords_this_frame` and `rs_calls_this_frame` per frame.
  Headless runs need `update_when_headless`. Placement costs about 0.18 ms per frame for 160 banners (82 on screen),
  headless.
- **The banner (OV-2).** `src/ui/overhead/overhead_banner.gd` is the actor's overhead banner as layer content: Block
  (name, tag, title, occupation, health row, backing, icons), Boss, Quest (pulse by formula, no Tween), Speech and
  Pointer. Its layout and visibility rules are a port of the 3D banner's, pinned by
  `tests/test_overhead_banner_parity.gd` (28,021 states against the 3D node path) and the golden
  `tests/fixtures/overhead_banner_layout_golden.json`, which keeps the pin after OV-3 removes the nodes. Regenerate
  the golden only in a tree that still has the node path (`-- --write-golden`). A content change rebuilds the block
  lazily at record time (about 36-43 µs per build, headless); fade, crowding and range toggles rebuild nothing.

### Updates and packaging

- **Installed-file scan and downloads (FIX-UD).** The updater's scan lists the game folders once and hashes on up to
  four threads (`RABBITLANDS_UPDATE_SCAN_THREADS=1` for one). Every kept file is still SHA-256 checked once, and the
  plan is byte-identical to the one-thread scan's (checked on the real install: 157 packages, 419 changed members, 20
  retirements, 25,455 snapshot rows). On a freshly written copy of the real install (5.82 GB hashed) the scan took
  57.9 s (median of 3), against stage A's 236.9 s and wave 1's 104.4 s; warm, 10.2-12.1 s against 39.4-48.0 s and
  25.8-27.4 s (busy shared host; wall times). Package downloads now read 1 MiB per pass of HTTPRequest's download
  thread, which sleeps until the next timer tick after each read: the 64 KiB default capped downloads at 4.2 MB/s at
  Windows' default 15.6 ms tick (about 30 MB/s with a finer tick); 1 MiB lifts that to about 66 MB/s (about
  250 MB/s), measured on localhost HTTP and HTTPS. The end-to-end timed update on the real install has not been
  re-run.
- **Manifest schema 3 (UD-05u).** The updater reads manifest schema 3: inventory rows may be `"codec": "zstd"`, one
  STORED zstd frame per 8 MiB chunk, decoded into a buffer of exactly the chunk size and then SHA-256 checked as
  before. Decoding runs at 706-753 MB/s single-threaded, against 286-302 MB/s for today's deflate inflate (the same
  77 MB of real map and creature GLB chunks). Rows without a codec take the unchanged path, and the setup helper
  (`tools/install_client_payload.gd`) picks the package path through the same schema check. The download saving (about
  -9 %, -360 MB on a full install, design estimate) arrives only when UD-05p publishes schema 3.
- **Stale cache janitor (UD-03).** A release client removes stale cache generations 30 s after start on a low-priority
  worker: policy folders with an older version, engine or format (per renderer family, the newest kept), and the
  legacy scene-cache entries of geometry-scoped whole maps (about 709 MB on existing installs). It prints
  `RABBITLANDS_CACHE_JANITOR`; `RABBITLANDS_CACHE_JANITOR=off` compares. The shader-cache rule (14 days / 128 MiB) is
  built but owner-gated and off. To check a packaged build, wait more than 30 s after launch and read the line in
  `client.log`.
- **Split PCK (UD-06).** Windows and Linux packages split the exported PCK after the static PCK checks
  (`tools/pck_split.py`, `package_client.split_client_pack`).
  - `app/RabbitLands.pck` becomes a core pack: scripts, scenes, data, `.import`/`.remap`, the UID and class caches,
    the boot closure and `data/content_packs.json`. Prepared content stays in it until UD-07a.
  - Imported textures, audio and login videos move to `app/packs/{equipment-textures-0..3,textures-0..1,audio,video}.pck`.
  - The first autoload, `ContentPacks` (`src/boot/content_packs.gd`), checks each pack's size and mounts it before
    anything else loads. It logs `client_diagnostic {"event":"content_packs",...}` with `usec` (mount) and `check_usec`
    per pack. A missing or wrong-size pack shows a native message asking the player to repair the installation
    (the updater; Steam's integrity check; a standalone build is installed again).
  - Release 4a57cea4: the core is 346.6 MB (27.1 MB without prepared content) and the packs 539.9 MB. A code-only
    release downloads 322.9 MB instead of 769.3 MB (about 13 MB once UD-07a moves prepared content out); the release
    that introduces the split downloads the same 769 MB as any code release today. Mount: 22-27 ms warm on the dev
    laptop, 31-58 ms on the 4-E-core proxy (gate: 50 ms or less on the low-end reference machine). The packager proves
    the partition entry by entry and loads all 1,435 imported resources and the videos from both layouts.
  - macOS bundles and `--benchmark-profile` keep one PCK, and `--no-split-pck` builds one on purpose.
- **Actor sidecars in packages (AT-C3, not release-enabled).** `package_client.py --actor-vram-textures` runs
  `build_vram_textures.py --actor-dir` for `ACTOR_SIDECAR_DIRS` (creatures, races, hair, mounts, equipment) after the
  map sidecars, with the same encode cache, and stages one `vram/` index per actor GLB folder loose beside the GLBs in
  `app/assets/actors/native/` (quality reports in `logs/vram-report-app__*.json`, receipt
  `logs/actor-vram-textures.json`). `check_loose_vram_textures` (formerly `check_scenery_vram_textures`) checks every
  staged file against its index, and `check_actor_vram_coverage` requires every embedded image of every staged,
  non-retired GLB to have a sidecar for the roles its GLBs sample it in, or an exclusion reason. The smoke launch sets
  `ELORIA_ACTOR_VRAM_SELF_TEST=assets/actors/native/races` and requires `actor_images self_test ok ... decompress=ok`.
  Release and runner builds refuse the option until `ACTOR_SIDECARS_RELEASE_ENABLED` is set with AT-C4 (schedule 1.1
  #20). Measured on the wave-2 tree: 680 sidecars (678 unique), 633.2 MB in 98 update packages, 900 MiB on the GPU,
  21 images decoded at the map floors; 177.5 MB without creatures. Default packages are unchanged.

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

## K620 configuration follow-up (2026-10-31)

Twenty sequential camera configurations and repeats retained the same Landfall
location, one equipped actor and 941×1030 window. These use the editor engine with
extracted release imports and source overrides; they are local screening data,
not a complete exported-client or online qualification. OS and NVIDIA driver
caches were warm/shared; Godot profiles were isolated except explicit reuse.
See [configuration measurements](../../docs/qa/linux-configuration-trials-2026-10-31.json).

At the overhead camera angle, typical OpenGL Low frames averaged 7.5–7.9 ms.
Medium with shadows disabled was similar at 7.9 ms; enabling Medium shadows
increased this to 15.5 ms and warm-up from 4.6 s to 9.9 s. Forward+ and Mobile
averaged 14.8 and 13.5 ms with about 1.10 and 1.03 GB of reported graphics
allocations, versus about 0.51–0.52 GB with OpenGL. Reusing Forward+'s Godot
profile reduced map-request-to-ready time from 32.4 s to 12.3 s, but retained
its slower frames and larger allocations.

Quarter map textures saved about 50–60 MB versus Half, without a clear frame-rate
benefit. Full textures used about 180 MB more. Hiding the minimap reduced average
overhead-view frame time modestly, from roughly 7.5–7.9 ms to 7.2 ms. These
one-location results do not justify further texture or resolution reduction as
a universal default.

The shallow −15° camera exposed a pacing tradeoff:

| 3D resolution / rotation cap | Mean interval | Worst interval | Frames above 33.3 ms |
| --- | ---: | ---: | ---: |
| 75% / uncapped, repeat | 12.48 ms | 25.28 ms | 0 |
| 50% / uncapped | 10.80 ms | 102.20 ms | 5 |
| 50% / uncapped, no GPU polling | 10.78 ms | 102.21 ms | 5 |
| 50% / 60 FPS | 16.65 ms | 24.67 ms | 0 |
| 75% / 60 FPS | 16.65 ms | 23.30 ms | 0 |

The earlier 75% shallow run also had one 96.58 ms first-turn pause. Recurring
50% pauses shifted yaw and occurred on later turns too. Their world GPU/render
CPU measurements did not account for the full delay. A 60 FPS cap removed them
in these trials; the exact uncapped scheduling/driver mechanism remains
unresolved. Retain 75% for its sharper image when it already meets the cap;
50% is an option when a busier view exceeds the GPU budget. The user's saved
OpenGL/Low/Half/75%/shadows-off/60-FPS settings already matched this balance.

### Character texture cache trial

Configure-only attribution found the existing wardrobe-atlas neutralization
dominated appearance setup: about 3 s in the editor engine and 2 s in the native
release engine. `ELORIA_ACTOR_BUILD_PROFILE=1` adds `detail.appearance.*` and
`detail.equipment.*` durations to the existing slow-actor record. Finish/part
durations are nested in their parent phases and must not be added to them.

`ELORIA_WARDROBE_TEXTURE_CACHE=1` enables an experimental lossless cache, off by
default. It keys original image bytes, layout, recipe and engine generation,
validates bounded metadata/payload checksums and restores the full RGBA8 mip
chain. Invalid or unwritable entries retain the existing calculation. Entries
are published by same-directory rename in `user://wardrobe-dye-cache/v1`.

Alternating cache-on/off launches of the same disposable native release-engine
package and user profile measured:

| Mean of two launches | Cache off | Cache hit |
| --- | ---: | ---: |
| Local avatar setup | 4.45 s | 3.13 s |
| Map request to curtain release | 12.03 s | 10.97 s |

Actual actor atlas hashes, including every pixel, alpha and mip level, matched
across all five accepted launches. Every pass retained 240 views and two draws
per view, restoring the 60 FPS cap and VSync. The final native cached run also
completed three shallow rotations at 60 FPS with no interval above 21.96 ms.
The cache contract suite passed 63 checks. One generated entry occupied 22.4 MB.
These timings use warm OS/tmpfs storage; cold physical-disk behavior and a total
disk-cache eviction policy remain unqualified, so the cache stays opt-in.

Loading-only probes now drain owned imports, retirement work and deferred
callbacks before freeing Main. Their teardown duration is outside arrival
timing. An earlier direct-quit trial crashed after recording while imports were
still active and is excluded from the results.

### Synthetic crowds

The maintained market/combat fixtures each supplied 160 actors on Landfall,
with the minimap hidden, a 30 FPS cap, 30 s settling and 10 s samples. Both
configurations passed runtime-settings, readiness and teardown validation.

| Configuration / workload | Delivered FPS | 95th percentile interval | Reported graphics allocations |
| --- | ---: | ---: | ---: |
| Performance preset / market | 30.09 | 33.57 ms | 875 MB |
| Ordinary Low, 160-body setting / market | 30.10 | 33.71 ms | 1241 MB |
| Performance preset / combat | 29.94 | 41.62 ms | 834 MB |
| Ordinary Low, 160-body setting / combat | 29.49 | 43.41 ms | 1092 MB |

These compare the complete Performance preset with ordinary Low, including
texture size, render scale, cloth/grass preferences and body budget. They do not
isolate body count alone. Priority actors remain protected: the preset's
60-body setting retained 69 market bodies and 80 combat bodies, versus 160 for
ordinary Low. The preset's strongest gain here was graphics-memory headroom;
combat still had frames exceeding the 30 FPS budget.

The crowd harness now establishes its requested frame cap before map arrival,
so shader warm-up captures and restores that value. The validator rejected an
earlier ordinary-Low run that restored its saved unlimited cap; only the
corrected run appears above. Linux Performance-profile seeding uses fresh
`XDG_DATA_HOME` storage, with the exact runtime directory checked at startup.
The crowd-harness CPU suite passed all 48 checks.

For further camera trials, `ELORIA_CAMERA_PROBE_GRAPHICS` accepts a JSON object
of supported Graphics controls, for example
`{"render_scale":0.5,"map_texture_quality":"quarter","quality":"low"}`.
Use `ELORIA_CAMERA_PROBE_MINIMAP=show` or `hide`, and
`ELORIA_CAMERA_PROBE_ROTATION_FPS=60` to test delivered pacing instead of the
default uncapped cost. `ELORIA_CAMERA_PROBE_LOAD_ONLY=1` measures arrival without
the settling/rotation workload. Reports distinguish synchronous map setup,
map-request-to-ready time and Main setup; Main setup excludes earlier engine
and autoload parsing. Keep the existing isolated-profile guards enabled.

## Direct 2D navigation maps (2026-10-31)

Both the minimap and current-map panel draw prerendered images directly in UI
Controls. Their former SubViewports remain disabled, with 3D disabled, empty
private worlds and camera cull masks of zero. The retained orthographic cameras
provide projection and picking math only; neither viewport texture is displayed
or requested to render. Markers, round masks, HUD palettes, rotation, zoom, pan,
click-to-walk and territory transforms retain the same coordinate mapping.

`data/maps/map-backgrounds.json` requires coverage of all 90 canonical maps and
43 aliases. The 275 image references include 246 new lossless WebP images
(49.75 MB) and 29 existing, verified regional detail images. Fourteen sectioned
maps have 199 independently filtered room images and no aggregate image.
Unknown secret sections draw no background. Other-room geometry is filtered
before rasterization, including overlaps inside the selected room's bounds.
Only three decoded catalog images are retained; existing regional-detail
retention remains bounded by the visible-map plan.

Release packaging validates canonical/alias/section coverage, exact framing,
source and renderer freshness, image hashes/dimensions, actual staged bitmap
bytes and the catalog's PCK/loose-data presence. There is no live-world fallback
when a picture is missing. See the [authoring workflow](../../docs/asset-authoring.md)
and [qualification data](../../docs/qa/map-backgrounds-2d-2026-10-31.json).

Two alternating before/after K620 camera runs measured mean frame intervals of
7.83 ms before and 7.80 ms after: effectively unchanged in this already-baked
Landfall scene. Reported graphics allocations fell by 4.3–8.5 MB. Arrival times
varied and do not establish a loading speedup. The structural interior gain is
removal of its live map-render pass; an interior FPS speedup has not been
quantified. All comparison runs retained the complete camera warm-up.

Qualification includes 92 background projection/crop checks, 10 secret-catalog
selection checks, 1066 map framing/picking checks, handoff/detail/adjacency and
runtime suites, plus 28 minimap-drag and 39 Tab-map checks. Rendered color/atlas/
round-mask tests include model traps and zero map-viewport primitives. Real
interior/secret views, marker picking and the Reedfall territory seam were
rendered separately. Packaging verified all 275 staged images against source.

## Gauntlets and large invasions on K620 (2026-10-31)

These are source-project screening runs using extracted release imports and
current source overrides, rather than qualification of a newly exported client.
The machine, settings, retained warm-up, rejected evidence and accepted results
are recorded in [the trial report](../../docs/qa/linux-gauntlet-invasion-trials-2026-10-31.json).
OpenGL Compatibility, Low, Half textures, .75 render scale, shadows off and a
visible direct 2D minimap are used throughout. Crowd body allowance is 60 and
remote cloth allowance is zero; the local player's cape remains eligible.

Sunmane, Harrowcrag and Resin Road entry tests each completed three full camera
turns at approximately 60 FPS. All six raw/prepared entry runs had no intervals
above 33.3 ms; the worst was 25.65 ms. First raw arrivals took 14.185, 16.167 and
13.740 seconds respectively. These single-player tests retain all 240 warm-up
views and two draws per view; they do not qualify combat or traversal through
the entire gauntlet.

A three-map local OpenGL geometry cache built in 9.914 seconds, occupied
21,676,440 bytes, and passed a second verification with three entries reused.
Interleaved Harrowcrag raw/prepared trials did not establish a loading benefit:
mean loader time was 1.969/2.187 seconds and Main setup plus arrival was
21.308/21.676 seconds. The apparent .302-second arrival-only improvement omits
additional preparation checks during setup. Warm-up remained intact. The earlier
larger differences also included warming of OS/driver caches. Keep this result
separate from the opt-in wardrobe texture cache above, which targets a different
cost: avatar appearance and equipment construction still take about six seconds
in these gauntlet arrival tests.

`--cells production-undead-160`, `production-undead-300` and
`production-undead-500` select an equal-weight zombie/skeleton/drowned-lich-king
cohort derived from Twinbrook's authored onslaught. Counts are remote creatures
plus one local player. The authored wave permits up to 500 creatures, but 300/500
visible records exceed ordinary server publication caps and are client stress
tests. One third are active, distributed across all three species, with walking
and melee presentation. Navigation and server AI are not simulated.

Use a fresh process for each count. Growing several cells in one process can
reuse parked bodies and retain them under distance hysteresis, changing the
rendered population. The 60-body setting is a soft distance policy; report
actual `builtBodies`, `deferred`, `inFrustumBuiltBodies` and built-only tier
counts. Legacy `inFrustumAndDrawn` and `tierFull` also count deferred actor nodes
and do not establish visible or animated model counts. Delivered FPS comes from
`wallMilliseconds`; `frameTime` excludes cap sleep.

The accepted 30-second-settle/10-second-sample runs measured:

| Workload | Scale | Cap | Delivered FPS | Interval p95 | Built / in-frustum bodies |
| --- | ---: | ---: | ---: | ---: | ---: |
| 160 creatures + player | .75 | 60 | 60.3 | 17.26 ms | 82 / 48 |
| 300 creatures + player | .75 | 60 | 60.3 | 21.26 ms | 80 / 68 |
| 500 creatures + player | .75 | 30 | 30.1 | 34.00 ms | 80 / 79 |
| 500 creatures + player | .75 | 60 | 59.0 | 26.54 ms | 78 / 78 |
| Authored 21-creature gauntlet pulse + player | .75 | 60 | 60.4 | 16.69 ms | 22 / 8 |
| Same gauntlet pulse | .50 | 60 | 60.4 | 16.71 ms | 22 / 8 |

Frustum counts are actor-bound estimates, not pixel occlusion measurements.
The gauntlet observer stands on published, unused walkable tile 195,118 near
seven goblins; the authored wave centre remains 196,87. All 21 creature positions
are unchanged. Both pre- and post-sample checks require at least those seven
creature bodies and the player in frame. The gauntlet pair does not demonstrate
an FPS improvement at the 60-FPS cap.

A separate one-player camera sweep at the denser arena centre used distance 26m,
FOV 50°, pitch −60° and three full turns. Mean frame intervals were 16.804/16.655 ms
at .75/.50 scale; mean world GPU time was 11.500/9.145 ms.
The worst-turn p95 interval improved 18.677→16.748 ms, while the maximum interval
remained similar (22.677/23.671 ms). This suggests additional GPU headroom at .50,
with no established improvement in the single worst frame. These two cases have
contemporary before/after source, asset, engine and private-probe identities.

With 500 creatures and the minimap retained, .50 scale reduced mean world GPU
time from 11.906 to 7.975 ms. Delivered FPS changed only 59.0→59.9 and interval
p95 changed 26.538→26.295 ms, with the same 78 built/in-frustum bodies. Lower
resolution adds GPU headroom but does not remove the remaining CPU cost.

Hiding only the minimap at .75 scale was a diagnostic control: interval p95 fell
26.538→19.129 ms, while the map-update timer fell from 1.120 ms mean/5.108 ms p95
to .042/.007 ms. This pair had 78 versus 77 built bodies, and is not a precise
causal FPS estimate. It identifies map mark collection/projection and deferred
canvas drawing as useful next profiling targets; the timer does not include all
canvas work. All ordinary qualification cases retain the visible 2D minimap.

`--settings-profile performance-60` changes only the Performance preset's frame
cap from 30 to 60. Both named profiles reject conflicting overrides and validate
the actual runtime settings. `performance-60-scale50` changes only render scale
from .75 to .50 relative to `performance-60`. Run each with 30 seconds of settling and a
10-second sample, for example:

```sh
python3 godot-client/tests/integration/run_crowd_presentation_benchmark.py \
  --godot "$ELORIA_GODOT" --project-path "$ELORIA_BENCH_STAGE" \
  --settings-profile performance-60 --variants all \
  --cells production-undead-500 --mode windowed \
  --renderer gl_compatibility --resolution 941x1030 --minimap show \
  --warmup-ms 30000 --sample-ms 10000 --capture-boundaries \
  --label undead500-60 --out-dir /tmp/rabbitlands-undead500-60
```

`--cells authored-gauntlet-resinroad-combat-21` selects one real six-player-scale
Resin Road pulse: twenty Mire Goblins and one Giant Amber Moth, at the exact
published spawn tiles, plus the local observer on a separate unused mouth tile.
It uses stationary native melee
presentation and excludes earlier survivors, encounter progression and server
combat/pathfinding. Its JSON fixture is included in source identity and benchmark
exports. New cohorts seed the production footprint-table packet before Main
creates actors, bound synthetic health, and reject invalid live/profile census
before sampling. The initial invasion trial omitted that table; its wrong lich
footprints caused validation failure and all its timings remain excluded.
Six subsequent trials also remain quarantined: their early VSync acknowledgement
was contradicted by warm-up restoring VSync later. The harness now establishes
the frame cap and VSync before map loading, and requires actual VSync-off,
requested cap, completed 240×2 warming and no active arrival/head warming at
both sample boundaries. Short rendered smoke checks precede accepted runs.

## Minimap refresh reuse on K620 (2026-10-31)

Main now reuses a data-only marker dictionary per actor, updating the drawn
node's position on every collection. Style decisions use the same actor kind,
name colour and canonical colour function. The existing visibility, living,
local-player and service-duplicate filters remain in Main, including dots for
deferred bodies. Cached actor records are bounded to the current population plus
32; styles are bounded to 64, and world teardown clears both.

Neighbour-detail selection also reuses its last ownership result when the
actual camera samples and cartography inputs are unchanged. Pan, rotation,
zoom, viewport changes and picture rebinding invalidate that result. The native
projection/clipping, ownership rules, 66 ms refresh cadence and direct 2D
backgrounds remain unchanged. Explicit in-place ownership edits must call
`_invalidate_cartography_ownership_cache()` to clear both ownership caches.

Three planned before/after pairs used six fresh processes, in AB/BA/AB order,
with the same 500-creature cohort and `performance-60` configuration above.
All six retained full 240-view, two-draw warming and passed pre/post-sample
pacing, cohort, source/asset/engine identity and teardown checks. The
[refresh trial record](../../docs/qa/linux-minimap-refresh-trials-2026-10-31.json)
preserves each pair and its body census.

| Pair | Map CPU mean, before → after | Map CPU p95, before → after | Built bodies, before → after |
| --- | ---: | ---: | ---: |
| AB | 1.086 → .815 ms | 4.542 → 3.462 ms | 78 → 75 |
| BA | 1.073 → .797 ms | 4.617 → 3.445 ms | 77 → 78 |
| AB | 1.078 → .783 ms | 4.684 → 3.308 ms | 74 → 79 |

The median map CPU mean fell 26.1% (1.078 → .797 ms per frame), and its p95
fell 25.4% (4.617 → 3.445 ms). Median Main processing fell 5.804 → 5.591 ms.
Delivered FPS remained approximately 60: 60.064 → 60.168 median. The declared
five-body tolerance is not identical model membership; these trials establish
repeated map CPU savings, not a causal whole-frame FPS or memory improvement.
The map timer excludes deferred canvas work. Root UI captures retain the 2D
background and dense dots; the third pair was also inspected visually.

These remain source-project screening runs over extracted release imports,
based on `4b2bad69f`, with only Main differing between variants and the new
helper present in both. Later remote cape and Lantern Mine changes were
integrated separately and checked headlessly. Actor-cache integration passed
1,181 checks and detail memoization passed 81, with existing map projection,
background, marker, presence and section-privacy regressions also passing. A separate affine
projection experiment was discarded: the small microbenchmark saving changed
exact edge clipping. No shader warming or loading policy changed.

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

On Windows and Linux, `--settings-profile performance` seeds the game's Performance
preferences into fresh isolated storage before startup: Low, 30 FPS, 75% world
scale, Half map textures, 60 crowd bodies and the remaining preset values.
The runner records the seed and checks the actual loaded settings. Conflicting
options are rejected. Use market/invasion/combat cells for this profile; the
80-mount census requires a larger body allowance. Ordinary Low at 30 FPS uses
`--settings-profile default --quality low --fps-cap 30` and remains a separate
comparison. Generated preferences use isolated APPDATA on Windows and
XDG_DATA_HOME on Linux; startup attestation checks the engine's exact user directory.

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

### Harness additions in wave 2 (2026-11)

- **Worker threads.** `--worker-threads 4|8|affinity` runs a source project through a private
  configuration overlay (`<checkout>/.local/crowd-benchmark-overlay/threads-N/`, ignored), whose
  `override.cfg` sets `threading/worker_pool/max_threads`. Godot sizes its pool from the logical
  CPU count and ignores the affinity mask, so an E-core proxy run (`--affinity 3C0`) should add
  `--worker-threads affinity`. The report's `workerPool.maxThreadsSetting` records the setting.
- **Engine options.** `--engine-arg` adds allowlisted engine options before the runner's own:
  `--gpu-index N` (the laptop's iGPU proxy is 1), `--rendering-driver NAME` (checked against the
  renderer family) and `--gpu-profile`.
  - Write them as `--engine-arg=--gpu-index=1` or `--engine-arg "--gpu-index 1"`.
  - They apply to rendered runs only.
  - A requested driver must be the one the report says ran (`renderingDriver`), because the
    engine can fall back.
- **Warm repeats.** `--seed-profile DIR` copies Godot's `shader_cache/`, `vulkan/` and `d3d12/`,
  and nothing else, from a user data directory or from a finished run's `userdata/<run>` into
  every fresh run root. Without it every run is cold. GPU driver caches (LOCALAPPDATA) are not
  controlled. The copy is recorded as `profileSeed` (files, bytes, SHA-256).
- **Uncapped presets.** `--settings-profile performance --fps-cap 0` measures the Performance
  preset uncapped. 0 is the only cap override a preset takes.
- **Body cap at plain Low.** Since the Low actor tier, plain `--quality low` draws 60 bodies.
  Quiet-comparison runs at plain Low must pass `--body-cap`; 160 reproduces earlier runs.
- **Wrapped GPU timestamps.** A rendered cell with a GPU time above 60 s is rejected. The Intel
  iGPU occasionally reports a wrapped timestamp of about 1.8e13 ms.
- **Traversal route version 2.**
  - The route starts and returns on covered ground at whitehorn [601,241].
  - Legs chain arrival to start. Only the interior entry relocates, because a curtained arrival
    beside that door cannot ground.
  - A separate cell, `traversal-seam-walk`, cruises 190 tiles to the Amethyst/Whitehorn road seam
    and crosses it. Profile `traversal` selects all three route cells.
  - Legs report `settleMs` (to readiness, now including the arrival curtain) and `visibleMs` (to
    Main's arrival report). They also report the curtain times, the handoff with its seam
    distance, and `frameRanges`, which split each leg's frames into start, walk, transition and
    capture.
  - Compare traversal numbers only between reports with the same `route.routeVersion`.
  - Headless traversal runs log dummy-renderer RID errors and fail the runner's log gate. Use
    windowed runs for traversal evidence.
  - `tools/continent_stream_benchmark.py --renderer mobile` runs the route on Mobile. It takes the
    same `--engine-arg`, and its report must show the requested renderer and driver.
- **Long frames.** Frames of at least 1 s (`RABBITLANDS_CROWD_BENCH_LONG_FRAME_MSEC`) are logged
  with the harness stage, the engine phase split, and Main's arrival and streaming state, in
  `report.longFrames` and `<report>.long-frames.log`.
- **Census.** Actors may implement `presentation_census()`, and contributors in
  `tests/integration/census/` add `census.contributors.<name>`. The Low tier reports
  `census.actorFields.*.handDetailCrowd/handDetailFull/cuesAllowed/cuesOff` and the
  `framePresenting` count. A Performance-preset smoke showed 61 crowd and 1 full body in the
  market and 36/1 in combat, with 7 and 6 bodies keeping cues.
- **Frame-clock motion.** `frameMotionMilliseconds` is the frame-clock presentation step at Low,
  part of `mainProcessMilliseconds`. Compare it with the drop in `physicsPhaseMilliseconds`.
- **Teardown.** Teardown waits for RL head prewarm work (`teardown.rlHeadWarm`); quitting with
  that parse running hung headless in 5 of 5 runs. Every cell first waits, for 60 s at most, for
  RL head prewarm parses in flight.
- **Despawn sampling.** `memory.afterDespawn` is sampled `PARK_MSEC` + 1 s (6 s) after a cell's
  crowd leaves, once the gate pass has freed the parked bodies. The earlier 12-frame point is
  `memory.afterRemoval`. `memory.despawnResidue` is afterDespawn minus before, and `despawn`
  reports the parked bodies at removal and at the sample. The prewarm's bodies expire the same way
  before the first cell. Each cell takes about 6 s longer.
- **Overhead-text gate (decision 8 diagnostics only).** `--diagnostics no_text_pass` keeps every
  overhead label but stops the separate world-text pass (its composite is hidden and its target
  shrinks to 2x2). `text_pass_always` renders the pass every frame, which turns off wave 1's idle
  pass. `no_overhead` now hides every actor banner; before, idle crowd members kept theirs (120 of
  160 in the market). Unknown names are refused, and the runner clears an inherited
  `ELORIA_WORLD_TEXT_IDLE`.
  - Crowd cells report `textPass`, `overhead` (a banner census) and `memory.afterSample`. Frames
    add `textPassDrawn`, the pass's own CPU/GPU time and draws, `renderGpuSumMilliseconds` (world,
    text pass and root) and the engine's total draws, objects and primitives.
  - Headless runs never draw the pass, so measure it in windowed runs.
  - `tools/overhead_text_gate.py <reports>` compares full, no_overhead, no_text_pass and optional
    text_pass_always reports of one configuration and prints the G2 verdict. For Compatibility Low
    on the dGPU, run the runner four times with `--mode windowed --renderer gl_compatibility
    --quality low --body-cap 160 --cells empty,s3-market-160,combat-160` and a different
    `--diagnostics` each ("", `no_overhead`, `no_text_pass`, `text_pass_always`), in two
    interleaved repeats, then run the gate tool on the eight reports.
- **World-distance baseline.**
  - `camera_rotation_probe.gd` accepts comma lists in `ELORIA_CAMERA_PROBE_DISTANCE` and
    `_PITCH`. Each pose settles for `_POSE_SETTLE_MSEC` and turns `_TURNS` times. The probe also
    accepts `ELORIA_CAMERA_PROBE_MINUTE`, and `appearance` in `_GRAPHICS`. It records shadow-pass
    draws and primitives per turn, and camera near/far and the fitted shadow distance per pose. In
    a fresh user root it waits for Main's before-login world geometry preparation.
  - `tools/world_distance_baseline.py --godot <exe> --out-dir <ignored dir>` runs the matrix and
    writes `world-distance-baseline.json`: the Landfall and Suncoil spawns, 26/90 m x -60/-35/-15,
    LOW Painted, LOW Original and HIGH, in two interleaved repeats. It first prepares world
    geometry once per renderer in its out dir.
  - `tools/world_draw_budget.py <territory> [--shadows]` is the offline estimate the
    world-distance chunks are measured against; `--check-reference` reproduces the plan's tables.
    The plan's "+ranges" columns also hide every `Terrain_`, which is an upper bound; compare
    later results with `ranges_keep_terrain` instead.
- **Stage-B switches.** `WAVE2_SWITCHES` (`crowd_benchmark_support.py`) also passes
  `ELORIA_WORLD_SCENERY_RELEASE` and `RABBITLANDS_NATIVE_REDUCER` through to the client and
  records them. With the run reducer on, the benchmark flushes the run after its tick loop and
  charges it to `packetDispatch`, and `activeBackends.nativeReducerMode` records the mode. Both
  are feature-detected, so the harness still runs in the stage-A tree.
- **Example (gate G1 on the iGPU proxy).** One configuration of an interleaved F+/M/F+/M set:
  `--mode windowed --renderer mobile --settings-profile performance --fps-cap 0 --cells
  s3-market-160,combat-160,empty --affinity 3C0 --engine-arg=--gpu-index=1
  --engine-arg=--gpu-profile --seed-profile <warm user root> --measurement-status
  quiet-comparison`.

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

**One gameplay render, 2D navigation maps.** The historical map cameras shared
the gameplay world and rendered geometry, materials and shadows again. They
were first throttled, then exterior map images replaced their geometry. The
direct 2D path above now removes the map-render passes entirely, including
interiors. `Main._update_map_viewports()` refreshes UI pictures and markers only
while visible: the minimap at about 15 Hz, the full map at about 5 Hz. The
separate character-creation preview still uses `_update_preview_viewport()`.

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
* **Verification** (2026-11, perf audit HITCHES-05). Every load still hashes
  each listed image in full itself: no timestamp or size shortcut, nothing
  reused from another load (`WorldManifest.verify_external_resources`). It now
  hashes where the bytes are consumed. The cheap checks run first; a raw parse
  then hashes the very bytes it decodes, and a sidecar uploaded in place of a
  source is checked against its index as it is read, so the source behind it
  is not read or hashed. Every listed file the parse did not read is hashed
  after it, before anything is published, and any mismatch fails the load with
  the messages the up-front pass gave. Prepared content, the geometry,
  collision and paving caches and a legacy scene-cache entry stand for the
  images without reading them, so they complete the full hash first; their
  proofs also take the glb's and the manifest's raw digests from the package
  digest this load just computed instead of hashing those files again. The
  preparer's capture and cooking keep the whole pass up front.
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
