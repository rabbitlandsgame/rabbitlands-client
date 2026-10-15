# Client runtime performance

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
  `vram_textures budget <territory>: N of M images at sidecar size`. No map is
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

## Checking a change

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
