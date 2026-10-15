# Manymouth Delta change log

## Placeholder → production (this pass)

The package that existed before this pass was the region's
`terrain-landmark-material-pass` placeholder. Nothing of its geometry survives.

### The starting condition, verified rather than assumed

Every defect the production guide lists was checked for this region:

1. **Terrain was flat.** `production-index.json` recorded
   `terrainHeightRange: [0.0, 0.0]`; the GLB held one `Terrain_ELM_Authority`
   mesh at y = 0 across 65 nodes and 19 meshes in 491 KB. Confirmed.
2. **Landmarks belonged to other regions.** Of 64 landmark entries, the named
   ones included `Resonant Crystal Cluster`, `Four Gates Waystone`,
   `Westhaven Lantern Tower`, `Ssarathi Sunken Court`, `Ssarathi Sun Stela`,
   `Amethyst Geode Cave`, `Grey Moor Dead Tree`, `Whitehorn Cairn` and three
   `Verdant *`. None preserved.
3. **The committed detail board was truncated** to exactly 786,445 bytes; its
   IDAT stream fails to inflate and only the top row of five panels decodes. An
   intact board was supplied and is now committed in its place.
4. **`server-collision/manymouth_delta.bin` was a flat placeholder** — 32×32 tiles,
   every tile id 0, every height byte 11. Confirmed and replaced.
5. **`world.json` had no `bounds` key** and no production status.
6. **There is no `qa/regions/manymouth_delta/` brief at all**, so unlike the
   other regions there was no prose starting point. The paintings were the only
   authority, which is what the guide says should win anyway.

### Built

* 576 m × 576 m at one metre per tile, on a 96×96-tile server map, arrival datum
  at server (174, 174).
* A braided delta: ~270 lens-shaped silt bars on a jittered lattice filtered by
  a land-probability field, seven named distributaries cut through them, a
  ridged-noise braid network between, an open-sea shelf to the north-west and a
  jungle head to the south-east.
* A walkway network of 27 routes, 73 deck segments and 28 landing stairs, which
  is this region's road system.
* Twenty-three named places: the great arch and its drowned platform, the stelae
  court, the stilt town with its tiered hall, arched market and quay, the
  floating market, the banyan landing, the paddy terraces and watchtower, the
  stepped temple and its quay, the labyrinth mouth, the overlook, ten hamlets.
* Nine new material recipes and five new tree species (`deltakit.py`,
  `stiltkit.py`), including a pinnate palm-frond atlas.
* `collision.swimmable`, `water.depths`, `water.channels` and
  `environment.traversal` in the manifest, so an aquatic traversal mode needs no
  rebuild. See `traversal-modes.md`.

### Bugs found and fixed in this region's own code

* **Every scattered bar came out identical.** `noise.stable_hash` is CRC-32 and
  tops out near 2.1e9, so slicing five decimal digits out of one key gave the
  size field a range of 0–2. Fixed by deriving each variate from its own salted
  hash. Invisible until you look at the map.
* **Walkway decks inherited the temple's height.** Taking a deck's level from the
  higher of its two landings ran the stelae-court-to-temple route dead level at
  14.8 m for a hundred metres. Deck level is now capped 2.2 m above the *lower*
  landing.
* **Boardwalk handrails were walkable.** Setting `walk_surface=True` on a
  `MeshGroup` placement renames the node `Walk_…`, and `export_glb` then names
  every *solid* child `<node>__<material>` — inheriting the prefix. Rails, pile
  heads and bamboo posts all became navigation surfaces and spawns snapped to
  the top of a rail post two metres above the deck. No placement in this region
  sets the flag now; `add_walk` alone is the correct idiom for a `MeshGroup`.
* **Spawns were declared on decks the client's ray falls through.**
  `plank_floor` lays real planks with real gaps and a run ends exactly on its
  endpoint, so a bounding-rectangle test claims coverage the geometry does not
  have. Spawns are now sited by a deterministic spiral search for flat ground
  with no deck over it.
* **The great arch rendered as a solid glowing teal ring.** glTF's
  `emissiveFactor` has no mask without an `emissiveTexture`, so it floods the
  whole surface; on near-black ruin stone it erased the albedo entirely. Found
  only because a real client frame was available. The inlay is painted into base
  colour now.
* **Bar tops came back as sand.** `assign_surface_by_rule` paints SHORE within
  1.6 m of the water line, and these bars are 1–2.5 m high. The first client
  aerial was a white sand flat. Sand now keeps the last 0.9 m at the edge.

### Fixes made in the shared toolkit

Three, all region-agnostic bug fixes rather than new behaviour, plus one small
capability. Flagged here because they change what **every** region's previews
and comparison sheets look like.

1. **`preview.py: scene_from_build` added only `parts`, never `walk_parts`.**
   Every walkable deck a landmark carries — a causeway deck, a quay, a canopy
   platform floor — was missing from every offline preview in every region: the
   previews were of the structure without its floor. Worse, a `MeshGroup` with
   *only* walk parts has an empty `parts`, which is falsy, so the group itself
   was passed to `add_mesh`; `MeshGroup.triangle_count` reports its parts' total
   while the group's own index buffer is empty, so the packed geometry claimed
   triangles it had no indices for and the C rasteriser read past the end of the
   buffer. On this region — whose walkway landings are exactly that shape — it
   segfaulted the preview and the minimap render. Now uses `all_parts`.
2. **`capture_views.py` built its material table before the region could
   register its own recipes.** A region adds materials by appending to
   `materials.SPECS` in memory inside its own `main()`, which this script never
   calls, so every region-specific material resolved to index 0 — `bark_oak`.
   Manymouth's water, decking, silt, sand and paddy all came back as bark and
   the delta rendered as a dry sand flat with no water in it. A region now opts
   in by exposing `register_materials(sets)` from its build module.
3. **`capture_views.py` and the region build resolved cameras differently.**
   The build snaps a `deck` camera onto the walk surface under it; this script
   only knew ground-relative heights, and additionally nudged every eye below
   20 m up to 33 m sideways looking for standing room. Because
   `godot_capture.gd` reads *this* script's index, the real client frames
   inherited the wrong framing too: this region's macro camera was authored 2 m
   from its subject and photographed village rooftops 30 m away. The build's
   `camera-views.json` now wins where it exists — one resolution, three
   consumers. A trailing `!` on a view's mode additionally pins the eye.
4. **`godot_capture.gd` now writes an `index.json`** beside the frames it
   produces, stamped with the engine version. Without it `make_comparison.py`
   found real client frames but no index and silently fell back to the preview
   renderer, so the sheets said "offline preview" while a better set sat unused
   in the next directory.

Nothing else in `_toolkit/` was touched. `libraster.so` could not be rebuilt —
there is no C compiler on this machine — so two rasteriser defects found during
this work are documented rather than fixed: it has **no BLEND path at all** and
draws every transparent material opaque, and `(int)floorf` on an unbounded UV
can overflow into a negative texture index.

### Server side

`eloria-server`, branch `feature/manymouth-delta-96-server-map`:

* `tools/generate_nymara_maps.py` — `manymouth_delta: 96` in
  `MAP_TILES_WIDE_BY_NAME` and `(174, 174)` in `ARRIVAL_TILES`.
* `tests/test_nymara_collision_contract.py` — expected size and arrival.
* `config/eloria/maps.txt` — the Ssarathi pair moved off Manymouth's 32-scale
  coordinates (which are open water on the production map) to the east watch
  landing at (537, 210), taken from the built `world.json`; and the Flooded
  Labyrinth repointed from Amberwood to Manymouth, where the concept puts it.
* `tests/test_nymara_maps.py` — the matching interior connection.

Verified: the generator produces a 576×576 collision grid with a walkable
arrival at (174, 174); the five Nymara/content test modules pass (21 passed).
On the wider suite, 81 of 513 tests fail on this branch — the suite was run with
the change and again with it stashed and the two failure lists are byte-for-byte
identical, so none are introduced and none fixed. Pre-existing and unrelated.


## Interiors pass

Four authored insides on one map with unwalkable blackspace between them, in the
Eternal Lands convention Amethyst Barrens and Crownwater already use: one GLB,
one manifest, one collision grid, one server map key, one arrival per door.

    flooded_labyrinth   drowned ruin        the cave mouth in the headland
    smugglers_warren    working warren      a hatch under the town quay
    tide_hall           inhabited hall      the Tide Hall door
    temple_sanctum      monumental sanctum  the Sanctum stair

79,438 triangles, 11.4 MB, collision 366 x 702 at half a metre, 21.4% walkable,
spanning x 38..219 and z 32..381 - a 64x64 tile server map with margin.
glTF 0 errors 0 warnings; `verify_runtime` 0 errors and two documented warnings.

The region gained four doors and four return spawns. Every door targets the same
`destinationMap` and differs only in `destinationSpawn`; the return spawn is
sited by `spawn_point` rather than at the door, because a door is on a deck and
a spawn declared on a deck is a spawn the grounding ray may fall through between
two planks.

The strongest idea in the four is the labyrinth's gate chamber: the ring-arch
that stands out of the whirlpool on the region map is the *top* of a gate whose
lower half is down here. You row past it on the surface and then walk in under
it.

### Found and fixed in this pass

* **The glyph stone tiled into dots.** `manymouth_glyph_stone` carries an
  inlaid band of teal strokes - right on an arch or a stele, and completely
  wrong tiled ten times across a 28 m floor. The first render of these rooms had
  cyan dashes over every surface. Bulk stone is `cliff_rock` now and the glyph
  stone is reserved for things actually cut with glyphs.
* **The boardwalk maze rendered as a black frame.** The generic "stand in a
  corner, look at the middle" camera put the eye inside a plank deck. Four
  subjects now carry explicit cameras.
* **Capture filenames contained colons.** A combined map's subject is
  "<Section>: <subject>", Windows will not take ':' in a filename, and Godot's
  `save_png` produced four zero-byte files named up to the colon and lost the
  rest. `preview_interior.py` sanitises the id now. This would have hit any
  region's combined insides map on Windows.

### Fixed in the shared toolkit

* **`godot_capture.gd` instantiated none of the manifest's lights.** It builds a
  sky and a sun, which is right for an exterior and useless for an interior: the
  frames came back with the lanterns visible as small orange discs illuminating
  nothing, and a reviewer would have concluded the interior was unlit when what
  shipped was 126 declared lights. It now reads `world.json`'s `lights` and adds
  an `OmniLight3D` per entry, taking range, energy and colour from the manifest.
  Every region's interiors benefit.

### Server side

`manymouth_flooded_labyrinth` grows from 32 to 64 tiles with its arrival at
(23, 344), and its single 32-scale portal pair is replaced by four bidirectional
pairs, one per door - the same shape `drowned_crown` and `resonant_vault` have.


## Interiors, second pass: the board, the map and the portals

**The portals.** A fifth door, and the one that justifies the convention: the
ring-arch standing out of the whirlpool on the region map is the top of the
Submerged Gate in the labyrinth's last chamber, so descending through it lands
underneath it and a drowned stair on the far side comes back up. Both ends were
already geometry. The labyrinth now has two ways in; the other three sections
have one.

Every arrival gained **built exit geometry** - a root-hung arch, a ladder and
hatch, a carved doorway, a columned stair head, a drowned flight - because an
arrival used to be a bare point in a room, and on a map with four sections and
no connecting corridors there is no wrong door to find by accident, so an
invisible right one leaves nothing at all. Arrivals also carry a facing now, so
a player is not dropped looking at the wall they came through.

**`build_interiors.py` now fails the build** unless every region door names an
arrival that exists, every arrival is reachable from a door, and every return
portal names a region spawn that exists. Nothing had ever checked that the two
halves of a transition agree; it caught the fifth door's missing arrival on its
first run.

**The map.** Roughly 8,000 more triangles of the things that make a room look
used rather than built: votive niches with offerings and a wrecked dugout in the
labyrinth's wading hall, offerings around the gate, a moored boat at the foot of
the Underdeck's ladder and drying lines strung between its piles, sleeping mats,
a loom and fish on a line in the Tide Hall, and a relic niche with a figure in
the Sanctum's core so the ambulatory has something to walk around.

**The board.** `references/00-detail-board.png`, a ten-panel 5x2 board answering
the exact ten subjects `concept.json` names, composed from real client frames by
`source/make_interior_board.py`. The concept board cannot be opened; this one
can. It is labelled on its face as a build reference rather than concept art,
and the truncated original is left untouched where it is.

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


## September 8, 2026: surveyed waterfront and working districts

The delta's separate flat boardwalks disagreed at their shared anchors and
often stopped behind a rail or across a floor gap. The new shared waterfront
recipes give each landing one height, cut routes to its actual edge, and use
one continuous walking skin. Shore ramps alter existing dry bars; channel
beds are recessed beneath decks. The native collision now samples triangles.

Arrival moves into the stilt-town service court. Houses face connected
porches and leave room between their roofs; six market stalls form two rows
around an open aisle. The hall's gallery posts use the correct height and
depth arguments. The market roof has a separate inner lining. The quay gains
a lateen packet built from shared procedural geometry. A branch reaches the
lore court, the temple faces its approach, and the arch descent is under the
ring itself. Existing content is assigned to working and dangerous districts.

The cost is a wider timber network and explicit landing surveys in the region
source. No surface classes or third-party assets were introduced. Build and
verification evidence, known remaining legacy warnings and comparison frames
are recorded in layout-review.md.
