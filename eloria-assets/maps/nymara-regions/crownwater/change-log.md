# Crownwater change log

## 2026-09-08: share the Crownwater palette with the Drowned Arcades

Promoted the six material recipes from source/crownkit.py into the shared
_toolkit/amberwood/crownmaterials.py. The old module re-exports the same
public interface for the exterior and its insides. All eighteen generated
base-colour, ORM and normal arrays match the former implementation at
their default full sizes, and material specs and names are unchanged.
Existing registration remains append-only and idempotent.

This supersedes the original private-material exception recorded below.
The exterior binaries were not rebuilt. The Drowned Arcades uses this
shared palette with new reusable arcade, bell, sluice and cargo recipes;
its layout and validation are documented under interiors/crownwater_gauntlet.

## 2026-09-07: the harbour and the surveyed archipelago

The harbour now works as a settlement: a sheltered bank and field workbench,
an information point and training post, stalls arranged around the court,
and the customs warehouse beside a cart ramp. Named local people stand at
their work rather than at scattered legacy coordinates. Inner gardens and
shores carry the easier gathering and wildlife; the outer branches hold the
serpents, constructs and temple guards. Existing creature counts are retained.

The Crown Basilica faces its plaza. Its portico has an open centre between
six columns, a fitted stair, and a visible front door. The undercroft has its
own covered side entrance, and the campanile and customs doors stand outside
their building footprints. Four ferry waystations have dry island sites.

Twenty-four stone causeways use exact shore lengths and elevations. The
survey is frozen before grading and belongs to the terrain instance; the old
rounded spans and shared height cache could leave steps or gaps at the shore.
The new shared civic recipes also remove the duplicate walking decks and
overlapping arch boxes. Bridgeheads are recessed beneath the deck and quay
caps finish clear of the terrain plane.

The full results, limitations and reproducible build sequence are recorded
in [layout-review.md](layout-review.md). Earlier entries below describe the
previous geometry and camera harness.


## From placeholder to production

The starting package was `terrain-landmark-material-pass` and carried the
defects the production guide lists. All were confirmed for Crownwater before any
work started:

| Defect | Confirmed | Resolution |
| --- | --- | --- |
| Terrain flat, `terrainHeightRange: [0, 0]` | yes | sculpted lagoon and archipelago, -16.4 to 42.2 m |
| Landmarks belong to other regions | yes, **all 65** - Grey Moor Ritual Shrine, Sunmane Caravan Camp, Amberwood Hollow Tree, eight Mirrorhold Civic Towers | discarded entirely; 10 authored landmarks replace them |
| `world.json` incomplete | worse than stated - **no `bounds`, no `coordinateTransform`** | full schema-1 manifest |
| Detail board truncated | yes, 786,445 bytes; **only 91 of 793 rows decode** | **resolved** - an intact 3,395,261-byte board was supplied and is committed here; all ten panels crop |
| `server-collision/crownwater.bin` a 32x32 flat placeholder | yes | regenerated, 96x96 tiles / 576x576 cells, from this build's collision grid |

## Build history, in order

1. **Terrain and water first, grounding proven before any detail work**, as the
   guide requires. Lagoon floor, deep moat ring, two navigable approaches,
   seventeen islands. `verify_runtime.py`: 331,776 tiles, 0 misses. Committed on
   its own.
2. Material recipes: veined marble, patinated verdigris copper, gilt leaf,
   mosaic tesserae, lagoon sand, lagoon water.
3. Architecture kit: domes, pavilions, campanile, cathedral, causeways, quays,
   bollards, banner poles, boats.
4. Population: causeways, crown isle, pavilion ring, harbour, sunken court,
   vegetation, props, metadata.
5. In-client capture harness and 23 framings.
6. Colour and lighting corrected against real client frames, iteratively.
7. Docs, sheets, server ELM.

## Bugs found and fixed during the build

Recorded because each was invisible until something specific caught it.

| Bug | Symptom | Caught by |
| --- | --- | --- |
| Deep channel carved through the crown isle | central island at y=0.26, barely above water | height probe before any modelling |
| Causeways graded as roads | harbour quay 2.5 m under water; a ridge raised under the water each span crosses | anchor height probe |
| Two anchors overlapping | the sunken court's terrace silently overwrote the harbour quay | anchor proximity check |
| Islands built as domes | 4.7% walkable; only the tips were inside the slope limit | `COLLISION_TOO_TIGHT` warning |
| `walk_surface=True` on `MeshGroup` placements | every pavilion grounded 12.8 m up, **on top of its own dome** - the guide's trap 2, exactly | `verify_runtime.py` `SPAWN_HEIGHT_MISMATCH` |
| Elevated deck footprint was a disc | a 48 x 5.4 m causeway claimed a 2.3 m circle; the rest disagreed with the surface | `COLLISION_SURFACE_MISMATCH` |
| Deck footprint mirrored about its origin | quay aprons claimed walkable water on their seaward side | same, after the first fix |
| `environment.sun.direction` sign | the whole region lit from below, reading as night | first real client capture |
| World-boundary rim | a dark slab floating at the map edge in every elevated view | first real client capture |
| Whole islands paved | the aerial read as one continuous white slab | first real client capture |
| Mosaic too bright and too contrasty | islands blew out to white; cyan aliasing from the air | client captures |
| Water tinted rather than authored | slate blue, not turquoise - a base-colour factor can only darken | client captures |
| Water plane at 3 m over a 420 m reach | 480,000 triangles, over half the region's unique geometry, for flat water | performance summary |
| Seven cameras inside or under geometry | panels 1, 2, 4, 6, 10, 13 and 40 framed the inside of a causeway | contact sheet |

## Deviations from the production guide

Both deliberate, both stated where they matter.

1. **Material recipes are registered at build time rather than appended to
   `_toolkit/amberwood/materials.py`.** Three other sessions were appending to
   that file concurrently. Nothing in `_toolkit/` is modified by this region.
   See `modeling-assumptions.md` #7.
2. **`_toolkit/make_comparison.py` was not used.** Against a truncated board it
   silently crops garbage and presents it as concept art.
   `source/make_sheets.py` refuses to fabricate. See `comparison-report.md`.

## Shared files touched

Only this region's entries, so a merge keeps both sides:

- `godot-client/data/maps/registry.json` - the `maps/nymara/crownwater.elm`
  entry only: `serverOrigin` 58 -> 174, `walkingHeight` 0.0 -> 4.5, status, and
  `requiresServerMap`.
- `maps/nymara-regions/production-index.json` - the `crownwater` entry only.
- `maps/nymara-regions/server-collision/crownwater.bin` - regenerated.

New files outside the package:

- `godot-client/tests/integration/rendered_crownwater.gd`

## Second pass, after the intact detail board arrived

Seven framings re-aimed against the real panels, and five changes to the map
that only the panels revealed: the cathedral precinct raised 9 m, lagoon alpha
0.82 to 0.70, the sunken court raised to -1.05 m, gilt metallic 1.0 to 0.34
(fully metallic renders near-black with no IBL), and banner cloth changed to
canvas. A `deck` camera mode was added to the view emitter, snapping an eye to
the walk surface under it the way the client grounds an actor.

| Bug | Symptom | Caught by |
| --- | --- | --- |
| Ground-relative eye height on a causeway | panel 4's camera 7 m above the deck, deck out of frame | the panel sheet |
| Gilt fully metallic | every finial and the panel-10 bollard rendered near-black | the panel sheet |
| Banner poles on the quay's seaward edge | four dark slabs across panel 2 | the panel sheet |

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
