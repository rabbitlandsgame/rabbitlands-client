# Interior preparation and load qualification

The production geometry scope remains unchanged: 17 continent territories,
17 canonical gauntlets and Landfall Underground (1,449 preparation targets).
An expanded candidate covered all 34 registered canonical interior packages,
including regional caves, secret areas and individual Four Gates rooms. It
prepared 33 additional worlds, but failed the loading-time promotion targets.
It is retained as `data/maps/geometry-cache-interior-candidates.json` for explicit
owned-worktree experiments, rather than enabled for automatic preparation or
native consumption in normal play.

The retained changes bound transient image memory in the already-cached
underground and fix sampler ordering in raw world-model loading. Whole native
interiors already include collision; the continent's separate collision-face
and paving caches are not extra caches required by full interior scenes.
See [the geometry cache contract](client-map-geometry-cache.md).

## Recommendation and measured limits

Keep the bounded underground texture preparation and early scenery sampler.
Do not promote the expanded native-interior scope on the measured evidence.
In three fresh-process matched pairs per map (AB/BA/AB), native geometry was
slower in both median loader-call time and controller first-ready time:

| Map | Raw load | Native load | Raw first-ready | Native first-ready |
| --- | ---: | ---: | ---: | ---: |
| Four Gates Stormglass House | 408.056 ms | 526.476 ms | 528.532 ms | 559.658 ms |
| Resonant Vault | 714.820 ms | 867.222 ms | 833.723 ms | 903.977 ms |
| Sunmane Wind Caves | 689.812 ms | 913.280 ms | 886.332 ms | 1,039.865 ms |
| Landfall Underground | 6,946.492 ms | 7,188.928 ms | 7,726.128 ms | 7,851.883 ms |

All four failed the predeclared 20% loader-time and 10% first-ready improvement
requirements. Peak-memory and through-settle guards passed on all four. Landfall
Underground's maximum Windows high-water working set across the three runs
fell from 1,912,197,120 to 1,225,039,872 bytes (about 36% lower). That comparison
uses raw loading versus the new native path; it is not the isolated effect of
the lifetime fix against the former native implementation.

The 24 qualified timing processes used full-resolution original textures,
Forward+/Vulkan, the same current sampler default, matching authored cameras and
observed focused windows. One unfocused run was preserved and excluded, and
its whole matched pair was repeated. Fresh processes retained operating-system
and driver caches. These component/controller results do not measure the real
application curtain or network/avatar startup.

Full scene/material/shader/mip/collision and authored grounding witnesses match
on all four maps. House, Vault and Landfall rendered views match exactly,
including all 22 Landfall entries and 44 yaw views. Sunmane has a stable three-
pixel difference out of 921,600 pixels in one of its four views, at a beam
intersection, with at most 5/255 difference per channel. Same-arm repeats are
exact and camera/fade/visibility states match. Its strict pixel verdict remains
failed; a draw-order edge is a hypothesis, not a proven cause. No render-order
change was introduced to mask it.

Twelve additional fresh-process option runs used three varied-order blocks.
They identify the memory effect more directly, while retained OS/driver state
and overlapping timing ranges prevent a robust speed claim:

| Underground native preparation | Median load | Maximum peak working set |
| --- | ---: | ---: |
| Earlier bulk path | 7,578.854 ms | 2,477,944,832 bytes |
| Shared container only | 6,426.492 ms | 2,446,876,672 bytes |
| Per-model binding only | 6,949.585 ms | 1,178,873,856 bytes |
| Retained combined default, cohort reference | 7,188.928 ms | 1,225,039,872 bytes |

Per-model binding drives the reduction: the combined reference peaks about
50.6% below the earlier native path. Sharing the container alone does not solve
the retained-image memory problem. The combined reference and raw early-filter
reference come from the earlier frozen cohort; these rows are descriptive
attribution, not a contemporaneous randomized four-arm speed comparison.
Raw scenery's old filter order measured 7,300.978 ms versus 6,946.492 ms for the
new order, also with overlapping ranges. The sampler change preserves final
properties and avoids the unused initial key; no guaranteed latency reduction
is claimed from these warm-driver measurements.

Separate restored-default real Main checks passed for Stormglass House and
Landfall Underground. They verify grounded actors, loading-curtain completion,
cutaway, drained surface follow-ups, no server connection and clean resource
release. House uses its existing raw/legacy route; Landfall records one native
world plus 155 native scenery hits and all 6,110 placements. These are functional
offline checks with a startup-preparer bypass and synthetic surface notification,
not additional UI-performance or live-server measurements.

## Keep transient image memory bounded

Landfall Underground has 22 entry sections and 6,110 scenery placements. Its
155 source models contain 463 embedded image records. Preparing every model's
decoded full mip chains before binding any of them retains much more CPU image
memory than loading those models one at a time.

Main-thread underground preparation now validates, loads and binds one model
before preparing the next. Binding releases its temporary CPU images; the same
immutable native scene templates and GPU textures remain available to the
placement loop. This does not change placement order, transforms, mineral
styling, cutaway metadata or worker publication behavior.

Embedded-image jobs can share one verified source GLB during an asset's
preparation call. The container is limited to 8 MiB, its complete source hash
must match, each extracted image still checks its own hash, and temporary byte
references are removed before preparation returns. Oversized sources retain
the original read-and-decode fallback. No global container cache is retained.

`ELORIA_GEOMETRY_CONTAINER_REUSE=0` and
`ELORIA_UNDERGROUND_BOUND_PREPARE=0` reproduce the earlier native preparation
paths for diagnostic comparisons. These do not change the native cache format.
The shared geometry policy remains unchanged because final geometry, material
properties, texture pixels and collision are preserved.

Raw world-model fallback also sets its final anisotropic filter before scene
generation, using the same material-preparation helper as maps and prototypes.
The late pass skips an identical assignment. Actors and other GLBs retain their
existing behavior. `ELORIA_EARLY_WORLD_OBJECT_FILTER=0` restores the earlier
world-model ordering for attribution; the existing early-map-filter opt-out
also retains its diagnostic behavior. Both benchmark arms use the same default
filter preparation when comparing geometry consumption.

## Candidate preparation cost and correctness

The 33 newly covered packages prepared in 42.867 seconds on the measured local
machine. They added 346 finished native entry/payload files totaling 24,276,499
bytes (23.15 MiB). Their main GLBs total 37,477,784 bytes; referenced external
prototypes and images are additional source inputs. Every previously prepared
native entry and payload remained byte-identical.
The expanded completion marker adds another 61,018 bytes, for 24,337,517 bytes
(23.21 MiB) of finished current-policy runtime growth. Scratch, repeated
benchmark profiles and older policies are excluded; this is not a release
download-size measurement.

Under the expanded candidate scope, a full resume reused all 1,482 targets without recooking, pruning or failures
and recorded the expanded completion marker. A rendered check of the isolated
preparation profile confirmed `needs_preparation=false`. This proves that
profile is prepared; it does not install task output into another checkout or
player profile. The rejected candidate cache and its scope snapshot remain
in ignored task storage; the extra 23.21 MiB and preparation work are not imposed
by the retained production changes.

After restoring the exact production scope, a separate isolated production
profile reused all 1,449 targets with zero recooking, pruning or failures.
Its rendered readiness check confirmed 1,449 native entries, 1,276 collision
entries, 34 paving entries and `needs_preparation=false`, with the existing
cache policy unchanged. This extra validation profile is scratch evidence,
not additional installed cache growth. The expanded candidate profile was
kept intact rather than pruned by a smaller-scope resume.

All 33 added packages passed 267 raw/native functional checks, including full
effective geometry, stored materials, mip pixels, collision and resource
release. Separate lifetime contracts exercise source/image hash failures,
oversized-container fallback, Main-only binding, worker handoff and cleanup in
headless and Vulkan modes. Timing and rendered controller qualification are
separate from those data checks.
The sampler-order test observes material identities and filters across the
actual glTF post-parse/pre-generation boundary and checks final properties,
world-model/actor boundaries and both opt-outs in each render mode.

No embedded BC texture build was added. The 155 underground GLBs total
70,416,244 source bytes, including geometry and encoded images. Their embedded
images are not covered by the existing external-image BC inventory. Original
full-resolution textures and their fallback remain intact. See
[texture preparation](client-texture-preparation.md) before measuring a texture
variant or extending packaging.

## Reproduce an interior comparison

For a new candidate experiment, use a task-owned worktree. Preserve the exact
production `data/maps/geometry-cache-scope.json` bytes privately, temporarily
activate the self-contained `geometry-cache-interior-candidates.json` declaration
at that path, and restore the original bytes in a finally/cleanup step. This
is an explicit experiment, not a production-scope update. Keep candidate and
production cache profiles separate: successful preparation can prune blobs that
are outside its current scope.

Prepare that candidate scope with the supported editor executable and an ignored
isolated profile, as described in the geometry cache document. Select that
profile's actual `Godot/app_userdata/Eloria` directory when invoking the
benchmark. For example:

```powershell
python godot-client/tools/interior_load_benchmark.py --target landfall_insides --mode native --cache-user-root .local/map-geometry-prepare/Godot/app_userdata/Eloria --output .local/interior-trial/native-1
python godot-client/tools/interior_load_benchmark.py --target landfall_insides --mode raw --cache-user-root .local/map-geometry-prepare/Godot/app_userdata/Eloria --output .local/interior-trial/raw-1
```

Each output directory must be new. Both arms receive the same declared native
payload closure and fixed full-resolution original textures; raw mode opts out
of geometry consumption without writing the older scene cache. Use three fresh
matched pairs with both AB and BA ordering. A fresh process does not imply a
cold operating-system or driver cache.

The fixture uses production world loading, camera/environment, secret-section,
cutaway and occluder controllers. First-ready means a first draw and three
consecutive grounded physics frames. It excludes Main, network, avatar startup
and the application loading curtain. Report loader time, controller binding,
first-ready, the subsequent settle and Windows peak working set separately.

`--qualify` runs a separate untimed process for full scene/material/mip/collision
witnesses and rendered views. Private shader copies replace `TIME` with a fixed
value for those pixel witnesses only; timed processes use the original shaders.
Witnesses must match the timed target, settings and source/runtime generation.
Never include texture or mesh readback in the timed load.

Coordinate imports, preparation, encodes and benchmarks under the shared
performance lock. Keep generated caches, receipts and profiles ignored. When
adding or changing a map, update the explicit scope, run the registry coverage
contract, and follow the geometry policy's invalidation and full-resume rules.
