# Amberwood change log

## 1.2.0 — 576 m, more forest, thinner stands

Amberwood grows again, to **576 m x 576 m** — three times its original linear
extent, nine times the area — still at one metre per tile. The server map goes
to 96x96 ELM tiles and the arrival datum to server (174, 174);
`../server-collision/amberwood.bin` is regenerated to match.

The brief for this pass was more forested area with slightly thinner stands, and
the two pull in opposite directions, so they are handled separately:

- **Coverage up.** The density field's floor is raised so it no longer collapses
  to nothing across large patches, the burnt country's boundary moves from
  design-x 90 to 104, and the meadow threshold tightens. Forest floor goes from
  32% to 41% of the terrain grid.
- **Local density down.** Tree spacing goes from 4.9 m to 6.2 m — about a fifth
  fewer trees per hectare than the 384 m build (one per 124 m² against one per
  102 m²), with more of them at the far detail tier.
- **Clearings stopped scaling with the map.** This was the real cause of the
  bare ground: courtyards, terraces and the cleared discs round every building
  were being multiplied by the region scale, so tripling the map tripled every
  clearing and ate the forest. Distances between places still scale; the places
  themselves now use a separate local scale. Paved ground drops from 7.3% to
  2.9% of the grid.

A third ring of places fills the new ground: a far grove and its camp, a sea
arch standing in the shallows, a kelp landing, a long orchard and skep rows, the
long meadow, a nine-stone ring, a western lodge, the upper falls and their
shrine, a coppice, an east grove, a ridge camp, a marchstone, a cinder chapel, a
cinder field, smoking ground, an east quarry and a far watch. Nine more road
routes and three more watercourses connect them. Landmarks go from 33 to
51.

Ground dressing was re-costed rather than re-counted: leaf drifts drop from 320
triangles to 80, mushroom clusters from 432 to 224, boulders from 320 to 80, and
far-tier trunks lose two sides.

Budgets: 28.7 MB GLB, 535,709 unique and
3,123,378 instanced triangles, 10,069 nodes;
LOD2 19.4 MB and 2,203,752
triangles. The client's grounding ray was cast at all 331,776 reachable tiles
with zero misses.

## 1.1.0 — the region at twice its linear extent

Amberwood grows from 192 m x 192 m to **384 m x 384 m** — four times the area —
at the same one metre per tile. The server map goes from 32x32 to 64x64 ELM
tiles and the arrival datum from server (58, 58) to (116, 116);
`../server-collision/amberwood.bin` is regenerated with real elevation and walkability
to match, replacing the flat placeholder, and must be loaded server-side.

The composition is written in the original design space and scaled, so the
aerial concept's layout survives intact rather than being stretched. The space
that opens up is filled with new authored places rather than by spreading the
original objects thinner: a second cove and its fisher huts, a forest lake with
a lakeside lodge, a deep old-growth grove with its own canopy platforms, amber
diggings, a northern hamlet, a second ravine and its bridge, a hill shrine, a
terraced orchard, a stone quarry, a south watch, an eastern hamlet, a burnt
battlefield, a cinder tower and a burnt mill. Three new forest arches, four new
lookouts, eight more road routes, two new watercourses and three more waterfalls
come with them.

Vertical relief is deliberately not doubled — it grows by about a third — so the
region does not read as the same picture at a larger size and slopes stay
climbable.

A reduced second package, `world-lod2.glb`, ships alongside: far-tier vegetation
only, no ground clutter, half-resolution textures. 38% fewer triangles and 38%
smaller on disk.

Budgets: 25.9 MB GLB, 458,891 unique and 2,202,463 instanced triangles, 6,538
nodes; LOD2 16.0 MB and 1,357,195 instanced triangles. 33 landmarks, 8
interactives, 32 harvestables, 21 roads. The client's grounding ray was cast at
all 147,456 reachable tiles with zero misses.

## 1.0.0 — production geometry, materials and population

Replaces the `terrain-landmark-material-pass` starter package.

### What the previous package was

* 487 KB GLB, 10,328 triangles for the whole region.
* Terrain was a flat 65 x 65 plane at y = 0 (`terrainHeightRange: [0.0, 0.0]`),
  `water: false`, spanning ±96 m about the origin — which leaves the north-east
  of the server footprint with no ground under it at all.
* Of its 20 meshes, eight belonged to other regions: `manymouth_flooded_cave`,
  `amethyst_crystal_bridge`, `westhaven_warehouse`, `crownwater_ferry`,
  `crownwater_fishing_boat`, `crownwater_patrol_boat`, `whitehorn_carved_stairs`,
  `mirrorhold_canal_stairs`, `ssarathi_curved_wall`, `sunmane_dry_cave`. Its 57
  landmark entries were named after them, on a regular grid.
* `references/00-concept-detail-board.png` was a truncated PNG — only the top
  row of five panels decodes. Every region package in
  `eloria-assets/maps/nymara-regions/` has the same defect, each file cut to
  exactly 786,444 bytes.

### What this package is

* Sculpted terrain over the whole server footprint with a rugged west coast,
  carved watercourses, a ravine, graded roads, built terraces and mountain
  boundaries: 0 m sea level to 100 m peaks.
* Seven authored terrain surface classes emitted as separate sub-meshes that
  share vertices, so material variety costs no cracks and no overlap.
* An authored old-growth tree kit — eleven species, three detail tiers, grown
  skeletons with buttress roots and leaf-spray canopies — instanced 744 times,
  plus undergrowth, fallen timber, stumps, boulders, fungi and leaf drifts.
* A timber-and-stone building kit, the monumental Amber Gate, two masonry
  bridges, four root-grown arches, two forest gates, the hollow-tree hall,
  canopy platforms and walkways, the garden terrace, the harbour, four
  watchtowers, forestry and charcoal works, and the burnt eastern country.
* 32 procedural PBR material sets, all generated from noise and drawn geometry.
* 26 landmarks, 6 interactives, 20 NPC and creature markers, 29 harvestables,
  4 portals, 13 roads, 3 spawn points.
* A minimap rendered from the final geometry, and a collision grid whose row
  order is server-tile-Y.

### Defects found and fixed during the build

* Canopy cards produced zero-length vertex normals at the card centre; glTF
  requires unit normals and Godot shades a zero normal black. Caught by the
  validator, fixed at the source.
* `collision.bin` rows were being written south-to-north while the server
  indexes them north-to-south, silently mirroring every walkability decision.
  Caught by the runtime verifier's cell-to-surface cross-check.
* Making a whole landmark a walk surface let the client's downward grounding ray
  snap actors onto the top of the Amber Gate. Walkable decks are now separate
  sub-meshes under the `Walk_` prefix.
* A reversed-edge `smoothstep` raised the entire terrain by the boundary-wall
  height instead of only its rim.


## Regeneration — package rebuilt to match its source

The committed package had drifted from the source that produces it. `world.glb`
was last written by `b169ed70`; `763104a6` then changed `textures.py` and
`materials.py` for the interiors without rebuilding, and the later determinism
fix changed five seeds again. So the shipped artefacts were the output of code
that no longer existed.

Rebuilt from the current source. Two independent cache-cold builds are
byte-identical across `world.glb`, `world-lod2.glb`, `world.json`,
`collision.bin`, `minimap.webp` and `performance-summary.md`, so the package now
matches its source and reproduces.

What changed, and why:

| | before | after |
| --- | --- | --- |
| GLB | 29.0 MB | 31.5 MB, then 28.7 MB once trimmed (below) |
| unique triangles | 534,697 | 535,709 |
| instanced triangles | 3,146,376 | 3,123,378 |
| nodes | 10,063 | 10,069 |
| materials embedded | 32 | 37 |
| LOD2 | 19.1 MB / 2,198,426 | 19.4 MB / 2,203,752 |

The geometry differences are the determinism fix: five seeds moved from
Python's salted `hash()` to `stable_hash()`, so tree variants, scatter
positions, bark textures and channel noise all resolve differently. The
composition is unchanged; the dice are.

The 2.5 MB of growth is not geometry. It is the five materials `763104a6`
appended to the shared table for the interiors, which the region's pinned set
inherited. **Six of the 37 embedded materials are not referenced by any mesh in
`world.glb`** - `foliage_green`, `lime_plaster`, `packed_earth`,
`sooted_plaster`, `charred_timber`, `water_deep` - and the 14 images reachable
only from them account for 2.79 MB. Pinning to the 31 actually used would
recover that. Left alone here because this pass was about reproducibility, not
about changing what the region ships; it is a one-line change when someone
wants it.

Verified after the rebuild:

```
validate_gltf.py        0 errors, 0 warnings, 6 infos
verify_runtime.py       0 errors, 331776 tiles sampled, 0 grounding misses
                        5 warnings, the same five as before
region_client_check.gd  in-engine, through the real WorldLoader
```

`../server-collision/amberwood.bin` is regenerated from the rebuilt collision grid.


## Material pin trimmed to what the package actually references

The pin added with the regeneration was the whole shared table - 37 materials -
which was exactly right on the day it was written and wrong the moment the
interiors commit appended five more. Six of the 37 were referenced by no mesh
in `world.glb`: `foliage_green`, `lime_plaster`, `packed_earth`,
`sooted_plaster`, `charred_timber`, `water_deep`. The 14 images reachable only
from them were 2.79 MB of a 31.5 MB package.

Pinned to the 31 the region actually uses, verified against the built GLB
rather than assumed.

| | before | after |
| --- | --- | --- |
| GLB | 31.5 MB | **28.7 MB** |
| materials embedded | 37 | 31 |
| images embedded | 100 | 86 |
| unreferenced materials | 6 | **0** |

Geometry is untouched: 535,709 unique and 3,123,378 instanced triangles across
10,069 nodes, exactly as before. Only textures nothing pointed at have gone.

The interiors are unaffected. `build_interiors.py` computes its own material
set per interior from that interior's own parts, so the four Amberwood
interiors still embed `lime_plaster`, `packed_earth`, `sooted_plaster` and
`charred_timber` where they use them - which is why those recipes exist.

`export_glb` now warns when a pinned material is unreferenced, because an
over-broad pin is otherwise completely silent - the package simply carries
textures nothing points at, and nothing says so. The warning is suppressed for
the reduced package, which drops ground dressing by design and would otherwise
report false positives. Suggested by the Crownwater session, which found the
same class of waste in its own pin.

Re-verified after the trim:

```
validate_gltf.py   0 errors, 0 warnings, 0 infos
verify_runtime.py  0 errors, 331776 tiles sampled, 0 grounding misses
determinism        two independent cache-cold builds byte-identical across
                   all six artefacts
```

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

## September 2026 - a market town above a working mill

The old scatter put water through the market, cottages in the western sea
and a footbridge against a hall. The new layout puts the arrival and services
on a clear court, carries the forest road around the hall, surveys seven
complete crossings and gives the quarry and orchard usable cart approaches.
The Mother rises above the roofline. The mill's exposed wheel stands in its
race below the settlement; packet and kelp boats sit beyond their quays.

The shared toolkit gains woodland mill and water-ribbon recipes. Amberwood
opts its lodges into retained timber, plaster, stone and shingle materials,
and its great arch into a continuous stair and podium. Their former default
recipes remain available to other regions. Every closed lodge now declares
its solid footprint; an apparent shortcut through a facade is no longer a
valid route.

Habitat and harvest discs retain the existing roster and names. A training
post completes the market's services. The client content contract follows
server object IDs and NPC names, and source/server-content.json makes those
positions reproducible after a standalone rebuild. Reviewed Godot frames,
comparisons and measured limits are recorded in layout-review.md.
