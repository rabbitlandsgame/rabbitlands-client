# Exterior region streaming

Twelve exterior regions share one north-up continent coordinate plan. Most
native landscapes are 360–396 metres across; Manymouth's compact core is a
480 × 396 metre delta. Irregular ownership polygons extend the physical shores
and passes to their neighbors. The square server address grids contain those
footprints without dictating their visible shape. The client loads the actual
receiving scene before arrival. The server's map handoff adopts that same root and rebases
the traveller and camera, preserving their position, heading and zoom.

## Scope

The generated continent graph enables background preloading and simultaneous
visible scenery on all 17 walking and causeway links. Seven further geographic
neighbors meet along shores or cliffs without a direct road; their actual
landscapes also load into view. These are `visualConnections`, kept separate
from the server's travel graph. Seven ferry links and
interior/magical portals retain their own travel behavior.

This is scene streaming with authoritative map handoff. Harvest objects, audio
and dynamic lamps still belong to the active server map. Actors are the
exception: a client that advertises `adjacent_actors_v1` is told about the
creatures, NPCs and players on the maps adjoining its own across a seamless
land crossing, within the same perception radius that gates creatures on its
own map. Their packets carry the neighbour's handle in the stock "z" field
(`ELORIA_ADJACENT_MAPS` names the handles per map), `AppState` tags each actor
with its map once, and `Main` places a neighbour's actor through that map's
adapter carried by the frame its resident scene stands in
(`FramedCoordinateAdapter`). A seamless crossing keeps every actor on both
sides: the server re-files the ones on the map arrived at as the client's own
and the ones on the map left as its neighbours, sends no `KILL_ALL_ACTORS`,
and the client rides every actor node through the rebase. Combat and resource
selection across the seam still need their own rules.
The minimap changes to the active region's existing coordinate system.
Crowded arrivals can still be adjusted by the server's existing free-tile rule;
the current live proof uses one QA traveller, not a multiplayer border crowd.

## Runtime

- `ExteriorRegionStream` checks proximity every 250 ms. It begins a private
  background import within 240 m and retains a neighbor until 320 m. For a
  geographic join, distance is measured to the nearest finite segment of the
  actual shared ownership edge. Older manifests use the road anchor, outward
  direction and `viewHalfWidth`. A lateral approach can prepare visible scenery
  before reaching the central road. Beyond the segment ends, distance includes
  the lateral gap; an infinite border line cannot keep faraway scenes resident.
  Unsurveyed transitions retain point distance to their authored crossing.
  The nearest three distinct neighbors are eligible; loading uses one worker.
- Three is a hard neighbor-root ceiling, even when configuration requests more.
  The worker starts only with a free slot and no outstanding retirement. Roots
  retired by movement, teleport or disconnect immediately lose visibility and
  collision, then release their nodes and prepared visual resources in bounded
  main-thread slices. A worker already in flight may complete into that queue;
  the conservative temporary limit is three neighbor trees plus that one
  existing worker result. No new import starts until retirement is drained.
  A zero-neighbor configuration disables proximity loading.
- `WorldLoader.prepare_detached` constructs a private tree, including collision
  and static batches, off the active SceneTree. It does not publish shared cache
  state or write disk cache entries on the worker. Completed results attach on
  the main thread. The existing package digest validates disk cache reads.
- Declared NPC body and harvest model scenes are prepared privately, then
  installed in `GlbSceneCache` on arrival. Resource and absolute paths share a
  canonical cache key. Equipment and individual creature animation preparation
  are not yet part of the proximity manifest.
- Generation tokens discard work superseded by disconnect, teleport or another
  transition. Closing the client lets its worker finish before renderer teardown.
  Distant resident roots are freed. Shared actor model caches last until logout.
- Active ground keeps navigation layer 8. A visible neighbor exposes its actual
  ground only on picking layer 16, with no active structural collision. Clicking into
  it routes through the existing road graph, then continues to the clicked tile
  after the authoritative arrival. A new world click, minimap click or keyboard
  movement cancels that continuation. The target stays in the destination's
  tile frame, preserves Shift/run intent, and rejects out-of-map margins.
  The walking marker appears on the clicked ground. A rejected move clears
  the pending continuation.
  A visible shore without a direct crossing can require intermediate regions;
  each arrival issues its next road gate and retains the final tile. The
  server caps each path request at 512 steps. After 448 observed authoritative
  movement commands, the client renews that same target, preserving one user
  click through long first, intermediate and final legs. Coalesced packets use
  command-sequence deltas; stationary updates do not cause retries. Exact
  authoritative arrival releases the intent. Combat, sitting, death or an
  unexpected map cancels it, and each leg permits at most 16 renewals. A
  geographic view alone never creates a new server crossing or changes a ferry.
  If the expected next road map misses its preload, fallback loading preserves
  the click until that map loads. An unrelated cold map and ordinary explicit
  clears still cancel it.
- A ready scene is transferred, not parsed again. A nearby surveyed crossing
  also retains the old scene for looking back. The camera focus, pan, yaw, and
  traveller's interpolation endpoints all receive the same rigid transform.
  Continuous adoption still measures proximity to the actual crossing point;
  wider lateral preloading cannot reclassify a remote teleport as a seamless
  road handoff. Exact neighbor-click destination tiles are unchanged.
- If no scene is ready (for example a teleport directly to a cold border), the
  existing synchronous loader remains the fallback. This can still stall.
- Atmosphere and light colour/energy blend across 65 m on either side of the
  shared road. Player position does not change the sun's direction; the game
  clock drives its elevation. A continuous crossing rebases the sun with the
  terrain and camera to preserve its physical direction. The sky resource is
  reused.

## Authored geography and contracts

`_toolkit/streaming_borders.py` defines each reciprocal frame, a 42 m graded
approach, pair-specific ground materials and matching texture coordinates.
Moor crossings use meadow/heather/earth; the inhabited upland uses turf and
gravel; alpine and crystalline approaches use their own frost or scree mix.
Southern dry collars use low golden grass shoulders and dusty tracks. Lake
causeways carry seven clear lanes above a channel with continuous water;
grading a dry pass leaves submerged background water at its own elevation.
One road's grading protects another road's surveyed strip. This matters at
Mirrorhold's two northern cols, only 87 m apart.

Terrain is partitioned on exact triangle edges within an 80 m wide, 145 m deep
receiving strip. Each approach piece is removed from the core and stored once.
Overlapping strips share intersection pieces with multiple view memberships;
whole props also retain one node. The same nodes draw before and after adoption.
Frames declare `geometryMode: shared-cells-v2` and their `sceneNodes` membership.
No copied `StreamView_` scenery or extended `_StreamOverflow_` surface is exported.
An invisible two-metre `_StreamThreshold_` navigation skin supports the server's
trigger one metre beyond the visual seam; it never draws or blocks a click on
the real neighbor. No neighbouring generated GLB is an input to these builds.
The surveyed-region packages use this export. Cache format 6 invalidates
the earlier duplicate-view scene layout. Minimap rendering includes each real
surface once and excludes the invisible threshold.
Placement selection uses transformed mesh bounds, so a tree canopy or boulder
that reaches into the strip stays visible even when its origin lies outside.
Grading also lifts linked portal, spawn and secret metadata with its landmark.

The loader groups core geometry under `StreamActive` and shared pieces under
`StreamCell_<membership>`. An active map exposes all its pieces; a resident
using `shared-cells-v2` exposes the matching approach through the same nodes.
This prevents distant terrain or unrelated exits overlapping the current region
when reciprocal frames fold otherwise unrelated local layouts together.

The opt-in `continent-owned-v1` frame mode exposes all of the resident's actual
core and shared geometry. It requires globally consistent region transforms and
validated disjoint ownership footprints from the continent builder. Full owned
views fill corners where several neighbors meet without copying any scene or
allocating additional maps; normal renderer frustum culling still applies. The
three-neighbor and single-worker limits are unchanged. Both modes keep the
invisible trigger skin hidden and exclude it from neighbor picking. Actual
resident ground uses picking layer 16; adoption restores active navigation and
structural collision. Shared pieces retain their original nodes and the core
keeps its static batches. Cache format 6 preserves this grouping and invalidates
previous scene layouts. Owned corner scenery can be clicked even when its
footprint wraps behind the central road's seam plane: actual foreground
occlusion and destination map bounds still apply, and walking continues through
the same server crossing to the exact clicked tile. Legacy strips retain their
outward-side restriction. Cross-border actor simulation remains separate work.

Anchors sit halfway between each departure tile center and the reciprocal
arrival. `continent_portals.py` generates seven lanes with mirrored lateral
coordinates, validates their walkability, and preserves two tiles of arrival
clearance. The server transports facing and omits magical teleport effects for
declared ordinary land travel. The server still decides all traversal.

The shared geography source fixes every region's translation, actual owned
outline, road frame, protected destination and sampled boundary height profile.
Common edge knots keep adjacent terrain tessellations at the same height.
Broad skirts and paired soil mixtures blend into the local biome. Native
architecture retains its size; scatter follows the reshaped ground.

The twelve continental exteriors use `continent-owned-v1`, north-up translations
and nonrectangular ownership. Native playable dimensions and the bounding box of
the owned terrain are separate measurements: connecting ground and coast can
extend beyond the compact native region. The Tab atlas uses those same outlines
and translations.

Regional approaches also retain their geographic character. Tidal routes use
bank-supported spans; woodland crossings leave the streams below their decks;
Sunmane's high southern approach has a broad dry ridge; Verdant's receiving burn
uses a rock-sided ravine and a culvert. These treatments live in regional authored
sources around the common connector pass. The shared endpoint, full crossing
width, source content identities and protected foundations remain constraints.

## Rebuild

Rebuild and integrate the group from the client root:

```powershell
python eloria-assets/tools/rebuild_continent_geography.py --server C:/path/to/server --data C:/path/to/generated-data --artifacts C:/path/to/review-output
```

Run stages in order: `geometry`, `prepare`, `collision`, `content`, `publish`.
`--region` can select individual geometry rebuilds. `prepare` requires the full
continent's current authored grid contracts before publishing origins. Revision-guarded
migrations preserve content IDs while moving coordinates. Collision generation,
all reciprocal portals, services, resources and encounters are synchronized in
one coordinating checkout. A relocation over 12 m stops for a designed approach.
The publisher records the actual served roster in `source/runtime-content.json`
and `runtimePopulation`, then updates only this group's package digests and the
shared connection JSON. Original lore/editor markers remain identifiable.
Gauntlet completion and bailout definitions use the same surveyed exterior
return as their portal records.

`continent-geography.json` declares native and published origins. Source posts
stay in the native frame; published markers, registry, server rosters, returns
and saved-position migrations use the expanded frame. Manymouth additionally
records its authored nonlinear compact field. Interior metadata and Sunmane's
LOD manifest synchronize before family package digests are refreshed.
The atlas uses actual geometry images under common lighting, the same global
translations and shaped hit targets, with no independent schematic placement.

## Verification and expansion

Run `tests/test_exterior_streaming.gd`, `tests/test_exterior_preloading.gd`,
`tests/test_exterior_retirement.gd`, `tests/test_shared_stream_cells.gd` and
`tests/test_map_cache.gd` and `tests/test_continent_water.gd` in Godot,
the client movement/object/lighting/reconnect checks, and the server's
`tests/test_exterior_streaming.py` plus collision, content, portal, surveyed-deck
and inhabited-route contracts. `tests/integration/rendered_exterior_streaming.gd`
extends the real-client route walker with scene/actor identity and camera
continuity assertions and adjacent crossing captures. It accepts the same
`ELORIA_WALK_SPEC` and isolated local-server environment as the landscape walk.

Before enabling another visible join, survey both roads, blend their landforms
and materials, align tile-centre arrival frames, regenerate contracts, and walk
every lane in both directions. Test camera angles, shoulders, multi-neighbour
visibility and single-arrival connectivity, not just the portal's own tile.

Use actual exported upward-facing triangles for route and water tests. A
two-sided height ray can hit a reversed bridge face that the collision raster
rejects. Clipping and native-deck subtraction must preserve upward walking tops;
test both the fine half-cell footprint and `World.can_walk_step` against the
final guarded grid. Include bridge-to-bank joins and the complete width of bends.
Water must remain below the physical walking surface, and bridge supports must
reach the actual bed. The distant package must preserve water coverage as well
as road and structural membership.

Inspect the generated scene from the gameplay camera before accepting numerical
proof. A supported road can still produce a narrow artificial embankment, a
straight grassy wall or a trench. Shape broad slopes first, preserve the exact
shared boundary and nearby foundation heights, and choose exposed rock or soil
where the landform warrants it. Retake the same camera views after the final
build and keep their input hashes with the collision and traversal receipts.

The continent is globally embedded, with each exterior still owned by its
server map. Region interiors, actors,
resources, ambient life and audio still activate with the server map. Their
handoff can remain visible even when the road and camera are continuous.
An unready scene still takes the synchronous fallback. Broader open-world work
requires cross-map server interest, lower-memory chunks and asynchronous GPU
preparation/attachment. The current steady-state budget remains one active map
and at most three neighbouring roots, with one loader worker and bounded
retirement as described above.

See the [northern](northern-region-rollout.md), [coastal](coastal-region-rollout.md)
and [southern](southern-region-rollout.md) rollout records for landscape decisions
and the remaining biome-by-biome work.
