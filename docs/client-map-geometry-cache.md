# Map geometry cache

The geometry cache keeps prepared meshes, collision, scene structure and texture
references separate from texture pixels. Normal texture loading still selects
the current texture quality and uses existing VRAM sidecars where compatible.
Preparing geometry does not generate textures, actors or authored map assets.

Travelling between an interior and its declared parent also keeps the world
just left resident in memory. Its loaded chunks are detached and paused, then
the same nodes are reattached on return. Registry `parentRegion`, `interiorOf`
and `insidesOf` relationships apply regardless of publication status, including
regional rooms, caves, secret areas and Landfall Underground. This uses the
existing WorldPark byte budget and travel/expiry cleanup; it adds no disk cache
or geometry preparation. Actors and map objects still refresh from the server.

Scripted rescue travel also prepares the mine while its opening conversation is
playing. The outdoor cave-mouth cells are prefetched at the same time and kept
with the parked territory for the family's return. Cinematic camera focus keeps
visible terrain streaming while world input is blocked. The parked/preloaded
world budget is 1,792 MiB; admission and eviction still apply. This preparation
uses existing source validation and caches without changing their format.

Published static map GLBs also consolidate byte-identical complete vertex records
with `eloria-assets/tools/consolidate_map_vertices.py`, called by
`publish_finish.py` after normal/tangent quantization and before prototype hash
reconciliation, resident-size figures and cartography rendering. This preserves
triangle order, component precision, every expanded triangle attribute, mesh/node
identities, material bindings and position bounds. It does not join across UV,
normal, tangent or colour seams. Unsupported deformation/extension contracts and
import-generated shading attributes retain their original storage; files are
written only when the complete verified GLB is smaller.

Consolidation changes source hashes, so affected geometry, collision and paving
entries naturally rebuild through the existing source-closure validation. It
does not change the native cache format or preparation scope. Prototype names
remain stable; their index and every consuming manifest must record the new file
hash. Map-picture source digests must follow too: ordinary publication renders
after finishing geometry. Carrying an existing picture forward is justified only
by a complete geometry/material/placement equivalence check and unchanged image
bytes, not merely by a smaller file or a matching triangle count.

Prepared-native loading may create private texture Resources on its worker, as
the raw loader does. The main thread alone publishes them to the weak pool,
binds the native scene and creates its Nodes. Stale native completions retain no
Nodes and release their private candidates. The default detached raw loader can
still build its private Node tree on its worker before main-thread attachment.
World instances keep private materials and MultiMesh buffers;
static scenery retains the existing immutable-template sharing and its consumers
create overrides when styling or fading an instance.

A raw territory preloader can prime private child chunks on its worker too.
Their decoded road fields travel with the resident chunk record; the main thread
binds them when publishing the owning territory. This handoff retains the
worker-built geometry and rechecks road dependencies before binding. A rejected
child is released and follows the stream's normal retry policy. A discarded
territory releases its private candidates without publishing road Resources.

On a synchronous main-thread underground arrival, each scenery asset is prepared,
installed with full revalidation and texture-bound before preparing the next asset.
Binding creates no Nodes and drops that asset's decoded CPU image carriers;
the ordinary placement pass then creates the real instances. Worker preparation
keeps its private handoff and first-use validation. Embedded-image jobs can share
one verified source GLB of at most 8 MiB for that preparation call, while still
checking each extracted image's hash. Larger sources keep the original per-image
read path. The container is released before preparation returns and is never
retained globally. For controlled comparisons,
`ELORIA_UNDERGROUND_BOUND_PREPARE=0` restores bulk main-thread preparation and
`ELORIA_GEOMETRY_CONTAINER_REUSE=0` restores per-image container reads.

Scope is declared in `godot-client/data/maps/geometry-cache-scope.json`: all 17
Landfall continent territories, `landfall_insides`, and all 17 canonical gauntlet
maps. Tier aliases share their canonical scene. Landfall means the complete
`continent-v2` territory group; the region named `landfall` is only one member.
Streaming territories prepare their declared chunk leaves, excluding review
GLBs. Used underground scenery assets are separate preparation targets.
The 35 production roots resolve to 1,294 world targets and 155 used scenery
assets, or 1,449 targets in total. `landfall_insides` is one full-map
package with 22 sections; its 6,110 scenery placements reuse those 155 assets.
The separate collision-face and paving shortcuts below apply to streamed
continent chunks.

`godot-client/data/maps/geometry-cache-interior-candidates.json` is a separate,
self-contained experimental scope. It retains those production roots and adds
the other 33 registered interior packages, including regional underground
assemblies, individual rooms and 12 secret-area assemblies. Its 68 roots resolve
to 1,482 preparation targets. The `interiors` group contains all 34 canonical
interiors; compatibility aliases share their canonical package. A coverage
contract checks registry entries marked `interiorOf` or `insidesOf` against that
inventory. These additional full-scene packages did not improve load/first-ready
times in the qualification cohort, so they are not read from this candidate file
by the game or automatic preparer. Reproducing the candidate requires explicitly
activating its scope in an owned task worktree; normal users incur no extra
preparation time or cache storage for the rejected expansion.
See [interior preparation and benchmarks](client-interior-preparation-performance.md)
for the expanded scope, measured storage, validation and controlled reproduction
workflow.

This path is independent of the six optional optimization-profile features.
Normal scoped loads can consume a valid geometry entry. Missing, stale or
incompatible entries retain the ordinary source-loading fallback. Cache keys
must match the current source closure and application cache format; the runtime
rechecks each entry when resuming preparation.

Continuous background continent streaming keeps the original detached raw loader:
rendered trials found the native path's publication checks increased frame stalls.
The preparer also saves exact collision faces and the existing kit-paving coverage
as small, separate caches. Background source loads can reuse these without reading
mesh data back from the renderer. Paving meshes receive the current load's private
materials, so texture quality and compatible VRAM sidecars still apply at runtime.
Missing or stale derived entries retain the original reconstruction path.
For diagnostics, `ELORIA_CACHED_COLLISION=0` and `ELORIA_CACHED_PAVING=0`
disable the corresponding shortcut without deleting its prepared files.
Raw map and prototype imports also set their final anisotropic filter before
first mesh materialization. `ELORIA_EARLY_MAP_FILTER=0` restores the previous
late-filter ordering for diagnostic comparisons. The final material properties
remain the same; this does not change the cache format.
Raw scenery imports under `assets/world/` use the same early final filter;
actors and other GLBs retain their existing material preparation. Setting
`ELORIA_EARLY_WORLD_OBJECT_FILTER=0` restores the old scenery-specific ordering
and unconditional late setter. The broader `ELORIA_EARLY_MAP_FILTER=0` control
also disables that early scenery pass. These switches affect preparation order,
not the final sampler, texture pixels, mip chains or stored geometry.
The shortcuts require scoped, non-capture loads. Those source fallbacks do not
write the legacy scene cache. Full painted mode with decorative grass retains
ordinary collision construction, because that path also supplies triangle data
used by the grass pass.

All continent chunks are still prepared for foreground loads. The diagnostic
`ELORIA_GEOMETRY_BACKGROUND_CHUNKS=1` switch enables native background consumption
for qualification and further performance work; it is not the default.

The commands require the matching runtime cache consumer and preparation script.
Use a client built with these changes; generating a plan alone does not update an
older installed client.

`MapGeometryPolicy.VERSION` in `src/world/map_geometry_policy.gd` is the central
format version. Bump it whenever a loader/producer change alters saved geometry,
collision, batching, scene structure or material interpretation, even when map
source bytes are unchanged. `MapGeometryCache.VERSION` aliases this shared version;
the collision and paving policies include it too. Update the writer, texture-source or binding policy
identifiers as well when their contracts change. The policy key also includes
the engine build, renderer, archived-model policy and older map-cache format.

Canonical map and scenery image sharing uses central geometry policy 4, map scene
format 11, and texture-source/binding policy v3. Existing prepared entries are
invalidated:
rebuild them with the matching runtime. Shared prototype and road material
loads retain each original image directory's texture policy even when the
physical pixel file is shared with another region.

Development checkouts lack a release identity. Selected source-input metadata
provides a cheap hint that preparation should run again; it is not evidence that
a cache entry is valid. Runtime source and payload hashes remain authoritative,
including when bytes change without a corresponding metadata hint. An invalid
entry falls back to source loading; explicit preparation can rebuild it.

Inspect the exact source closure without starting Godot:

```powershell
python godot-client/tools/map_geometry_cache.py plan --project godot-client --out .local/map-geometry-plan.json
```

Run preparation with an existing Godot executable and previously imported
runtime dependencies:

```powershell
python godot-client/tools/map_geometry_cache.py build --project godot-client --godot C:/path/to/Godot.exe --resume
```

The tool uses Forward+ by default; `--rendering-method gl_compatibility` selects
OpenGL explicitly. It renders in an offscreen window with dummy audio, and keeps
its profile, jobs, reports and logs under the ignored
`godot-client/test-artifacts/map-geometry-prepare/` directory. `--user-root`
selects another isolated output/profile directory; it does not copy player
settings. `--plan` accepts a saved plan and `--no-assets` excludes the separate
underground scenery targets. Resume validates source/cache identity rather than
skipping files merely because they exist.

The producer reads raw source content with the older map cache and VRAM sidecars
disabled for that child process. Logs are checked while it runs; engine errors
stop that process promptly. The default preparation timeout is two hours and can
be changed with `--timeout-seconds`. Logs and any partial report remain available
for diagnosis and resumption.

Release packages supply the complete scoped preparation as read-only loose
assets. A checksum-bound catalog provides geometry, collision and paving entries
for a compatible engine/renderer. Ordinary launches consume these in place and
skip the whole-world preparation screen. Missing or incompatible packaged data
retains source/local-cache fallback, rather than rebuilding every map before
login. The updater owns these installed assets; clearing player caches does not
delete the shipped preparation.

Source/custom builds without a shipped catalog retain the scoped local
preparation path. Its completion marker includes the release identity and cache
format. Later launches reuse it. Headless launches and launches with map/geometry
caching disabled skip automatic preparation. The settings window includes the
player-owned scene, geometry, collision-face and paving caches in its displayed
disk usage and Clear action.
"Skip for now" retains completed entries and continues to login; a later launch
resumes preparation. Missing entries use source loading in the meantime.
Clear also removes older geometry-policy files and is disabled during cooking.
Older policy folders are otherwise retained; a successful cook prunes only
unreferenced blobs in its current policy. Clearing the completion marker means a
later normal launch with caching enabled prepares the scoped data again.

The explicit client entry point `--prepare-map-geometry` prepares even when the
completion marker already exists, then exits with a success/failure status. The
Python command is the isolated developer workflow and does not run an editor
import. Missing imported dependencies, preparation failures and their logs are
reported instead of silently qualifying a cache. Generated caches belong in local
or installed cache storage, outside tracked source files.

An update can derive the collision and paving entries from compatible existing
native geometry without recooking the GLBs. A successful complete pass records
the derived policy versions and regional paving profiles in its startup marker;
a later unchanged launch skips preparation. Source and payload hashes are still
checked when loading an entry. Clearing the caches removes these derived files
as well as the completion marker, and a later launch can rebuild them.

Continent road fields are verified source inputs to native geometry preparation,
but bind to retained ground after materialization rather than being serialized
into its snapshot. See [continent road surfaces](continent-road-terrain-blend.md)
for the publication, collision and streaming-memory contracts.
