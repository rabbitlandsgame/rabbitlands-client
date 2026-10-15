# Ssarathi Ruins change log

## Placeholder to production

The package this replaces was at `terrain-landmark-material-pass` and carried
the defects section 3 of `REGION-PRODUCTION-GUIDE.md` records for every region.
All were confirmed for this region before any work started, and none of the old
package is preserved.

| Defect | State before | State now |
| --- | --- | --- |
| Flat terrain | `world.json` had no `bounds`, no `coordinateTransform`, no spawns; the GLB was a single flat `Terrain_ELM_Authority` mesh | Sculpted heightfield over the whole 636 m x 636 m cut, playable relief −9.9 m to +104.7 m |
| Foreign landmarks | 10 of 47 named other regions — Mirrorhold Floating Market, Manymouth Hidden Dock, Whitehorn Rope Bridge, Resonant Crystal Cluster, Verdant Vine Bridge, Verdant Jungle Cave, Four Gates Waystone, Westhaven Lantern Tower, Verdant Tree Platform; the remaining 37 were six Ssarathi silhouettes repeated | 14 landmarks, all Ssarathi, each derived from the placement that actually carries it |
| Truncated concept board | `references/00-concept-detail-board.png` cut to exactly 786,444 bytes; only the top row of five panels decoded | Replaced with the intact 1983x793 board supplied for this build; all ten panels decode |
| Flat placeholder ELM | `server-collision/ssarathi_ruins.bin` was 32x32, tile 0 and height 11 everywhere | Regenerated at 96x96 with real elevation and 42.4% walkability |
| Registry status | `terrain-landmark-material-pass`, `serverOrigin [58, 58]` | `production-geometry-materials-population`, `serverOrigin [174, 174]`, `requiresServerMap` recorded |

## What was built

In the order the production guide prescribes.

1. **Terrain first, and grounding proved on it before any detail work.** The
   basin, the rim, the valley walls, the channels and the falls shelves, then
   the city's embankments, plazas, temple tiers and ramps. `verify_runtime.py`
   reported 0 grounding misses across all 331,776 reachable tiles on the first
   populated build and has on every build since.
2. Water, bridges, causeway furniture, the temple, the two courts, the
   landmarks, the working quarters, the massing pass, vegetation, dressing,
   metadata.

## Defects found and fixed during the build

Recorded because each is a trap the next region will meet.

* **The toolkit's `assign_surface_by_rule` ends with an unguarded
  `where(height < sea_level − 1, SHORE, …)`.** In a region whose subject is
  drowned paving it turned the ritual plaza's pool floor and the whole drowned
  quarter into beach shingle. Replaced by a region-local rule; the shared one is
  untouched.
* **Hand-listed bridge crossings.** Three of the first five were nowhere near
  the channel they were meant to span, and one re-cut the west dock down to the
  channel floor. Crossings are now computed from the street and channel
  polylines.
* **`plateau` does not set `tree_block`, `terrace` does.** The massing pass
  tests that mask, so the temple precinct was fair game and a ruin block landed
  on the summit and dropped it from 16.2 m to −0.84 m. The plateaus are now
  marked explicitly.
* **Testing only a block's centre against the claimed-ground mask.** A 19 m
  block sitting 15 m off the axis overran the causeway by four metres, which
  showed up as a wall standing in the middle of the panel-1 shot. The whole
  footprint is tested now — and that in turn made the blocks so much rarer that
  they had to be shrunk and the grid tightened.
* **`mesh.lathe(..., segments=4)` is a hollow shell, not a solid.** The first
  ziggurat was four such shells with a staircase running up the middle of
  nothing. `ssaratharch.square_frustum` uses `mesh.loft` with `cap_ends`.
* **Low-segment lathes and cylinders smooth-shade around the axis.** A
  four-sided prism gets normals pointing at its corners, so every flat face
  shades as if curving away from the light — the temple rendered near-black
  beside paving made of the same stone. `ssaratharch._facet` re-splits at 30°.
* **Carved pieces rotated through π show their backs.** `stone_face` and
  `sun_stela` carve on +Z, which is south, and both were placed at rotation π —
  so the panel-7 stela presented a blank slab to its own approach and the
  temple guardians presented plain boxes to everyone arriving up the causeway.
* **Fixed-size columns in a LOCAL-scaled court.** The pool colonnades were
  0.30 m shafts at 5.2 m in a 43 m-radius ring: 1.5 pixels at 85 m, and both
  pool-court captures came back as an empty paved shelf. Column size is derived
  from the ring radius now.
* **Vine cards hung from a tapering mass at a fixed width** fell through open
  air beside a temple that had already narrowed away from them.
* **Lily pads authored at 3 m across.** A lily pad is about 40 cm.
* **A negative derived seed** (`seed + int(sign)` at seed 0) is rejected by
  `numpy.random.default_rng`. Masked, deterministically.
* **`terrain._smoothstep` takes scalar edges.** An embankment whose width
  wobbles per cell needs array edges; `region._smoothstep_a` supplies them, with
  the same zero-span guard, because a reversed or zero span silently evaluates
  the mask to 1 everywhere and lifts the whole basin — the trap section 6 of the
  guide names.

## Changes to the shared toolkit

Three, all additive, all defaulting to the previous behaviour so no other
region's output changes. Reported here because the guide asks for it.

1. **`capture_views.py` gained a region-materials hook.** It called
   `preview.texture_sets()` with no way for a region to add its own recipes, so
   every capture of a region whose materials are not in the shared table
   rendered in fallback grey-tan — which is exactly how Ssarathi's first
   captures came back. Any region build module exposing
   `register_materials(sets)` is now called before the scene is built.
   Crownwater worked around this with a private `make_sheets.py`; this fixes it
   for everyone.
2. **`capture_views.py`: `REGION_LIGHTING` normalisation and `FIXED_VIEWS`.**
   `DAY_LIGHTING` / `GOLDEN_LIGHTING` are documented as dicts of overrides, and
   the same raw dicts also landed in `REGION_LIGHTING`, which is read as if it
   held `Lighting` objects — so the aerial view of any region declaring either
   constant died on `vars(dict)`. Fixed. Separately, a region may now list view
   ids in `views.FIXED_VIEWS` to pin a verified framing against the camera
   search, which no ground-level camera on a long axial street can satisfy.
3. **`godot_capture.gd` gained `--environment=manifest`.** The harness lit every
   frame with its own studio sun, so a package's declared `environment` was
   unverifiable: a manifest can light the world from underneath, or omit
   `tonemap` and render flat, and the captures looked identical either way.
   With the flag the frames are lit through the project's own
   `WorldEnvironmentBinder`. Off by default.

Nothing was forked. The four terrain surface classes (23–26) and the twelve
material recipes are registered into the shared tables at build time from this
region's own modules, and `_toolkit/amberwood/` is unmodified.

## Environment tuned against real client frames

The manifest's `environment` block was corrected three times against Godot
output, which no previous region has been able to do:

* The first version declared no `tonemap`, leaving Godot's linear default at
  exposure 1.0, and put the sun at `[-0.22, −0.90, 0.38]` — almost straight
  down, giving vertical faces nothing. The region rendered dim and blue-grey in
  the client while the offline preview looked bright.
* The correction over-shot: fog density 0.0006 with `aerialPerspective` 0.35 and
  a filmic exposure of 1.32 put a milky haze over everything and dissolved the
  temple.
* The shipped values are sun energy 2.35 on an oblique `[-0.38, −0.76, 0.52]`,
  ambient 0.42 at 0.35 sky contribution, fog density 0.00011, filmic tonemap at
  exposure 1.05.

Amberwood, Mirrorhold, Whitehorn Range, Amethyst Barrens and Crownwater all omit
`tonemap` and none has been rendered through this path. Amberwood additionally
declares a sun direction with a positive Y component, which lights its world
from underneath.

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

## September 2026 — a working drowned city

The arrival now has two supply shelters and grouped service posts, while the
eastern market has facing stall rows and an open aisle. Kerbs no longer cut
across those working courts. Southern roads converge on one Water Gate crossing
instead of three overlapping bridges. Five surveyed stone spans meet the
shore, and eight sloping jetties with three punts make the waterfront usable.

Lily Court now leads along a 58 m walk to a pile-supported cistern sounding
stage. The Crownwater ferry stands on its berth, and the Great Temple Focus
secret stands on the Sun Vault forecourt. These replace inaccessible or
misleading authored positions without adding a continent connection. Existing
NPC identities and all 26 creature spawns remain; danger increases toward the
northern terraces and rim.

The shared civic kit gains an open-shaft sounding stage. The camera writer
uses emitted walk triangles for deck views. This pass adds 1.41 MB and 26,681
instanced triangles to the full GLB. All five core outputs reproduce exactly;
thirty offline and thirty manifest-lit Godot views were refreshed and reviewed.
Current proof, warnings and full-suite results are in layout-review.md.

The final player-height review also turned the Water Gate across the causeway.
Separate pylon footprints leave its opening clear; the original quarter-turn
and whole-gate circular blocker obstructed the approach. Its camera now
stands on the rendered deck instead of the channel bed.
