# Coastal landscape update — 2026-09-11

- Recompose Westhaven into a 396m square with origin `(120,172)` and explicit anchors; keep full-sized service and building geometry.
- Regrade the city hillside and both islands before foundations; connect house yards, market/civic streets, farm routes and both physical island approaches.
- Face warehouses toward their loading paths, frame the service court, retain a quiet quay strip and reduce repetitive moored ships.
- Preserve all portals, interiors, secret roles and the League Post-House lore; move secret props beside clear authored standing posts.
- Use actual transformed Walk triangles for raw deck collision; preserve the shared border clipping in both main and reduced packages.
- Record deterministic migration and a read-only server-path verification helper. Gameplay-camera evidence is in the coastal rollout artifact.

---

# Westhaven: change log

From the `terrain-landmark-material-pass` placeholder to a production package.

## The starting condition

The placeholder had the defects section 3 of `REGION-PRODUCTION-GUIDE.md`
records for every region. All were verified rather than assumed:

- **Flat terrain.** `production-index.json` recorded
  `terrainHeightRange: [0.0, 0.0]`, and `world.glb` was a single
  `Terrain_ELM_Authority` mesh at y = 0.
- **Foreign landmarks.** 52 landmark instances, of which 11 belonged to other
  regions entirely: Ssarathi Curved Wall, Sunmane Dry Cave, Grey Moor Cairn,
  Grey Moor Boardwalk, Mirrorhold Lake House, Amberwood Estate, Crownwater
  Ferry Dock, Four Gates Gatehouse, Mirrorhold Floating Market, Ssarathi Water
  Gate. None preserved.
- **Incomplete manifest.** No `bounds`, no `coordinateTransform`, no spawn
  points, an empty navmesh, and `surfaceNodePrefixes` of `["Terrain_"]` only.
- **Truncated detail board.** `references/00-concept-detail-board.png` was
  exactly 786,445 bytes and its IDAT stream would not inflate; only the top row
  of five panels decoded. An intact 3,171,071-byte board was supplied and
  replaces it.
- **Placeholder server map.** `server-collision/westhaven.bin` was 32 x 32 tiles, tile
  0 and height 11 everywhere.

## What was built

### Terrain first, and grounding proved on it

Following section 5 of the guide, the heightfield was built and exported with
every population pass returning early, and `verify_runtime.py` run on that bare
terrain **before any detail work**:

```
[grounding] 331776 tiles sampled, 0 misses (0.00%)
[verify] 0 errors, 1 warnings
```

The in-engine check agreed at the same stage. Only then was anything placed.

### Composition

The aerial is read on an 8 x 8 grid and mapped 1:1 onto the playable square on
both axes. Buying that required moving the arrival datum from (174, 174) to
(174, 250); the reasoning is in `modeling-assumptions.md` and `README.md`.

The city is authored as an explicit six-band terrace staircase — quay 3.4 m,
lower town 9.5, mid town 18.0, upper town 28.5, citadel 41.0, crown 52.0 — with
graded ramp streets between the bands and retaining walls on the risers.

### Population

| pass | what it placed |
| --- | --- |
| `build_water` | one sea plane at sea level, cut 240 m beyond the terrain |
| `populate_surf` | 719 foam cards and 7 breakers along every shoreline, weighted by exposure |
| `populate_seawall` | 10 mole runs, the bastion, the mole light, 14 bollards |
| `populate_waterfront` | 6 quay-wall runs, 26 bollards, 13 warehouses, the quay-street arch, the fish market arcade and 9 stalls, 2 piers, 8 jetties, the crane, the gantry, 14 ships, the harbour gate, the custom house |
| `populate_shipyard` | the hull on the stocks, 2 yard sheds, 9 timber stacks, the ropewalk |
| `populate_city` | 385 houses from 12 variants, retaining walls, the city gate, the great arcade, the cathedral, the campanile, the domed hall, the high spire, 7 lesser towers, the guild hall, lamps and cisterns |
| `populate_lighthouses` | the great lighthouse, the Gullstone watch, the sea arch, rock clutter on both masses |
| `populate_upland` | chapel, farm, hill estate, east watch, field fences, signpost |
| `populate_vegetation` | 257 trees in shelter belts, 536 ground-dressing patches |
| `populate_props` | ~90 quay props, the chandlery still-life, 6 boats |
| `populate_metadata` | 10 interactives, 39 harvestables |

## Defects found and fixed during the build

Recorded because each cost time and each would cost the next region the same.

1. **Coastline polygons left in design space.** The masks were built from
   `cell()` output and tested against a world-metre terrain grid, silently
   shrinking every landmass to a sixth of its area. No error, no warning — the
   region simply came out wrong. `_poly` now scales at construction.
2. **A rotation formula correct only when dz = 0.** `atan2(dx, dz) - pi/2` was
   used to align pieces along a route; the correct expression for this
   codebase's `rotation_y` is `atan2(-dz, dx)`. Wrong by up to pi everywhere the
   route was not east-west, which is why the mole rendered as a chain of planks
   lying across its own line. Now one `_align` helper, used everywhere.
3. **Terrace bands applied to the whole mainland.** Confined to a city polygon;
   without it the open upland was banded into contour stripes 500 m wide.
4. **Two water planes 2 cm apart.** Z-fought into a checkerboard across the
   whole harbour. Collapsed to one body; the shallow/deep distinction moved to
   `environment.water`.
5. **The offline preview had no region materials.** `capture_views.py` built its
   scene from the shared material table only, so a region registering its own
   materials at build time rendered them through a fallback. Every Westhaven
   preview came back as one flat sand colour with no water in it, and nothing
   said so. Fixed in the toolkit — see below.
6. **A backdrop with one open side on a map open on two.** Put a continent of
   grey rock along the western horizon. Dropped.
7. **Straight balustrades wrapped around circles.** `SW.balustrade(2*pi*r)`
   translated to a point is a tangent bar flying off into the sky, which is what
   the first panel-2 capture showed on the lighthouse gallery. Replaced with
   rings of stanchions in three places.
8. **Metadata recorded at terrain height under decks.** The lighthouse spawn,
   two interactives and four landmarks were recorded at the ground beneath a
   walk surface, and `verify_runtime` correctly called the spawn an error. Fixed
   by moving them off the deck footprint or recording them at the deck.
9. **The market arcade standing between the camera and its own stalls**, and the
   warehouse row running straight through the market. Both re-sited.
10. **Aerial camera rolled 45 degrees and then mirrored.** `capture_views` nudges
    a target coincident with the eye diagonally, and the offset has to be to the
    *south* for north to come out at the top.
11. **A transform composed the wrong way round.** `rotation @ translation`
    rotates an *already placed* piece about the world origin and flings it
    somewhere else on a circle; the order that means "face that way, then go
    there" is `translation @ rotation`. Nothing in the shared toolkit ever
    writes the first form, and fourteen sites in `havenarch.py` did. The
    crane's treadwheels ended up below the quay, the bastion's merlons bunched
    at double their intended angle, the pier rails had their X and Z swapped,
    and the ship's sterncastle roof was mirrored across the hull. There is now
    one `havenarch.at(x, y, z, yaw, pitch, roll)` helper and no bare
    composition anywhere.
12. **Two portals standing on blocked cells.** A landmark that collides blocks
    its own footprint, so the natural place to put something next to one is
    exactly the place the collision grid has just marked unwalkable. The build
    now checks every spawn and portal against the finished grid and moves any
    that landed on one onto the nearest walkable cell, reporting the distance.
    It caught the Grey Moors road at 6.67 m and the Crownwater berth at
    16.41 m.
13. **Tide banding baked into a terrain material.** `westhaven_sea_rock` put
    the three tide zones in as horizontal bands of the V coordinate, which is
    right for the vertical sea wall of panel 8 and wrong for the lighthouse
    rocks and the headland, which are terrain: at terrain UV scale the bands
    tiled into hard stripes every three and a half metres. The recipe is now
    isotropic and the tide is told by the surf geometry instead.
14. **The upland roads were surfaced in ship decking.** The terrain class the
    road operator marks is PATH, and PATH was pointed at
    `westhaven_quay_plank` because the shipyard slipway needed decking on the
    ground. Every cart track over the open grazing was therefore planked like a
    deck. PATH is now a proper cart track and the slipway is authored as paving.
15. **`west_quay` had been in sixteen metres of water since the first build.**
    The coast at that v runs through u = 1.11 and the anchor was at 0.72.
    Nothing caught it; once the walkable-cell check existed it quietly
    relocated the Crownwater berth 16 m every build rather than reporting the
    anchor as wrong. Probed against the built terrain now, not guessed.
16. **The nudge could relocate a portal under a deck.** An elevated deck makes
    its footprint walkable at deck height, and the harbour gate's piers stand
    on dry ground, so "nearest walkable cell with dry ground" could land under
    the gate roadway and take its Y from the terrain sixteen metres below.
    `build_collision` records which cells a deck claims and the nudge excludes
    them.
17. **Four pinned but unreferenced materials** — `shingles`, `cobble_paving`,
    `bark_pale`, `water_sea` — each superseded by a Westhaven recipe and each
    embedding its textures for nothing. 1.4 MB. The build's own warning caught
    them. `undergrowth` likewise in the LOD package.

## Additions to the shared toolkit

Per section 1 of the guide, capability was added to `_toolkit/` rather than
forked. Two changes, both additive and both opt-in:

- **`regionpaths.region_material_sets(package, sets)`**, called by
  `capture_views.py`. Asks the region's build module for a
  `register_materials(sets)` hook and applies it. Regions that use only shared
  materials define nothing and are unaffected. Crownwater has the same latent
  problem and can adopt it with one function.
- **`godot_capture.gd` now writes an `index.json`** into its output directory.
  `make_comparison.py` reads an index from whichever capture directory it
  picks, so a `godot-captures` directory without one made the comparison step
  fail outright rather than fall back — the frames were there and unusable.

Nothing else under `_toolkit/` was modified. Westhaven's nine material specs,
eight texture recipes and fourteen kit pieces live in `source/havenkit.py` and
`source/havenarch.py`, registered at build time, for the reason Crownwater's
`crownkit.py` gives: `materials.SPECS` is a module-level tuple that four
unfinished regions are queued to append to.

## Server side

On `feature/westhaven-576m-server-map` in `eloria-server`:

- `MAP_TILES_WIDE_BY_NAME["westhaven"] = 96`
- `ARRIVAL_TILES["westhaven"] = (174, 250)`
- `westhaven_elevation()` — an authored height function reproducing the
  coastline, the two rocks, the terrace staircase and the upland from the same
  reading-grid coordinates the client plan uses, so the two are edited together.

Westhaven is the first exterior whose server relief is authored rather than
noised, because it is the first whose client terrain is a coastline: the generic
ridge-and-noise field puts land where the client has 240 m of open harbour.

The generated map passes `validate_generated_map`: 96 x 96 tiles, 576 x 576
height cells, heights 7–24, arrival datum exactly 11.

On the client side, `server-collision/westhaven.bin` was regenerated from the built
terrain — 96 x 96 tiles, 341,112 bytes, 55.8% walkable, real relief, water
blocked.

## Files touched outside this package

| file | change |
| --- | --- |
| `_toolkit/regionpaths.py` | added `region_material_sets` |
| `_toolkit/capture_views.py` | one line, to call it |
| `_toolkit/godot_capture.gd` | write `index.json` for the frames it produced |
| `server-collision/westhaven.bin` | regenerated at 96 x 96 from the built terrain |
| `godot-client/data/maps/registry.json` | Westhaven's entry only |
| `maps/nymara-regions/production-index.json` | Westhaven's entry only |

## The ground is cut inside the cell, not at its corners

The heightfield is sampled every two metres and `build_meshes` gave each quad
whole to the class of one corner, so a road could only ever turn on a cell
boundary and read as a flight of two-metre steps.

A class now takes every quad it touches and carries a per-vertex coverage in
COLOR_0's alpha, drawn with an alpha-tested copy of its material, so each pixel
goes to whichever class covers it. Where an operator knows its own edge -
`grade_path` for a road, `plateau` for a rim - `Terrain.surface_strength` puts
the cut on the real edge; elsewhere it falls half way between samples, which is
still a diagonal rather than a staircase. `despeckle_surfaces` clears class
islands under six cells first, because a crumb that read as a stray square at
whole-quad ownership reads as a deliberate blob once it is cut smoothly.

An alpha test is opaque, so it writes depth and sorts like any other ground.
The classes overlap where they meet by design, and `check_zfighting.py` skips
pairs that are both alpha-tested with vertex coverage.

See `whitehorn_range/change-log.md` for the full account, including why the
heightfield was not taken to one metre instead.
## September 2026: a port with roads that reach its hinterland

The quay, civic skyline and upland were individually legible but the circulation
between them was not. Added a cart climb along the eastern shoulder, a link
between the crown and north gate, lanes to the farm and watch, and a descent
from the coast road to the bay. The farm and estate roads now skirt their
buildings. Two raised, sloping crossings carry the existing shore track over
the yard gully and the Lamp Rock saddle. Roads use surveyed station heights and
a full-width bed, so hard terrace aprons cannot leave their ends stranded.

Gullscar now has enclosed planted strips downhill of its house and a water
store above them. Existing storage, crafting and information roles gather on
the main quay, joined by combat practice. The server reads habitat and field
discs from the package: common wildlife stays near the farm and bay, hounds
occupy the outer upland, and the cart routes stay clear. This keeps the
landscape and content generator working from the same layout.

Town plots now reject overlapping roof envelopes and leave small gaps between
houses. Window fronts project clear of the timber frame to remove their
near-coplanar shimmer. All new pieces use the existing procedural palette;
surveyed roads, mitred causeways and grain rows are shared toolkit recipes.

The server's isolated-step correction also had a defect: adjusting one outlier
clipped every high tile to 63 before stage selection. It now changes only the
outlier. A regression test preserves an otherwise continuous high plateau,
so a flat server grid can no longer conceal this class of broken approach.

Validation and remaining limitations are recorded in `layout-review.md`.
