# Grey Moors — change log

From `terrain-landmark-material-pass` placeholder to production package.

## The starting condition

Every defect in section 3 of the production guide was verified for this region
rather than assumed, and every one of them was present.

| defect | what was actually there |
| --- | --- |
| flat terrain | `world.glb` POSITION accessor `min [−96, 0, −96] max [96, 0, 96]` — y = 0 everywhere, and the extent only 192 m |
| foreign landmarks | 58 landmarks, opening with Crownwater Fishing Boat, Crownwater Ferry, Whitehorn Carved Stairs, Crownwater Patrol Boat, Mirrorhold Canal Stairs, Ssarathi Curved Wall, Sunmane Dry Cave, Mirrorhold Lake House, Amberwood Estate |
| truncated detail board | the tracked `00-concept-detail-board.png` was the broken 786,445-byte copy; only the top row of five panels decoded |
| flat placeholder ELM | `server-collision/grey_moors.bin` was 39,880 bytes, 32 × 32 tiles |
| QA README | present at `eloria-assets/qa/regions/grey-moors/README.md` — note the hyphen, not the underscore the guide implies |

**None of the placeholder geometry or metadata is preserved.** The package was
rebuilt from the concept art.

## What changed

### The detail board — resolved without a re-supply

An intact 2,853,593-byte board (1983 × 793, decodes fully, all ten panels) was
sitting **untracked** beside the broken one as
`references/grey-moors_00-concept-detail-board.png`. It matches the board the
user supplied. It is now the tracked `00-concept-detail-board.png`, and the
aerial concept is landed alongside it as `01-concept-aerial-overview.png`, so
the package carries both authorities.

### Extent

192 m → **576 m at one metre per tile**, on a 96 × 96 ELM grid with the arrival
datum at server (174, 174). Composition is authored in the placeholder's 192 m
design space and scaled by `region.SCALE`, so the change of extent is one
constant rather than a rewrite.

### Terrain

Flat → a sculpted low moor: a barrow ridge across the north-centre, eight
terrain-raised barrow mounds, twelve bog basins, three drains, four cut peat
terraces, a south-west bay, and a narrow closing rim. Playable height range
−16.0 m to 26.9 m; the walkable band is authored inside the server's six-bit
height byte.

### Toolkit

Added to, not forked (see `modeling-assumptions.md`): five surface classes,
fourteen material recipes, their specs, a `grey_moor_track` material over an
existing texture, a general `_bleed_into_alpha` helper, and a new
`amberwood/moorcraft.py` kit of 21 pieces.

### Metadata

58 foreign landmarks → 61 region-correct ones. 7 spawn points, 2 map
transitions taken from the server's own `maps.txt`, 4 interior entrances, 15
population markers, 64 harvestables, a complete `environment` block, and a
minimap rendered from the final geometry.

## Defects found and fixed during the build

These are the ones that mattered. Each was found by a tool or by looking at a
render, not by reasoning.

**Boardwalk planks the grounding ray fell through.** `mesh.box` takes full
extents; the deck was built with `width * 0.5` and its planks spaced at 40% of
their pitch. So the deck was half as wide as its own posts and 60% open gaps,
and the client's downward ray passed between the planks to the bog below. A
character crossing would have dropped off the boardwalk. Caught by
`verify_runtime`'s `COLLISION_SURFACE_MISMATCH` on a single sampled cell, then
traced by asking which placement claimed that cell.

**Boardwalk decks claiming ground behind them.** The mesh was modelled from its
near end, but the collision pass claims a deck's footprint symmetrically about
the placement using the mesh's half-extents. Each span therefore marked its own
length of open bog walkable at deck height. The mesh is now built centred.

**Scrub shading solid black in the real client.** Only the Godot capture showed
it; the offline preview looked correct throughout. Three compounding causes,
fixed in order: card normals were perpendicular to a vertical card so an
overhead key barely lit them; the atlas was drawn on a black background so
mip and bilinear filtering averaged plant colour with void; and the material
was double-sided, which makes Godot invert the normal on the back face, so an
up-leaning normal became a down-leaning one. The cards now carry explicit back
faces and the material is single-sided.

**Sixteen landmark markers floating.** Tower, dead-tree and Hanged Oak markers
sat at each feature's visual centre. Flagged by `LANDMARK_FLOATING`; moved to
where a player stands.

**A tenth of the walkable surface above the server's height ceiling.** The
closing rim was wide and gentle enough to be walkable, which put 10.4% of
reachable ground over the 10.4 m the ELM height byte can express. Cutting the
rim narrow relative to its height pushed its flanks past the collision slope
limit; the figure is now 3.05%, and those cells are rim shoulders.

**`TER.PATH` would have put forest litter down a moor.** The generic path class
maps to Amberwood's `leaf_path`. Rather than embed amber leaf litter, the region
took a fifth surface class, `MOOR_TRACK`, over the toolkit's existing
`packed_earth` texture with a cooled, darkened material.

## Corrections made after looking at renders

The guide is right that a map you have not looked at from 1.7 m is not finished.
Each of these was a render telling me something a validator could not.

- **The region read as a bright foggy beach.** Sky, ambient and fog all came
  down hard; the moor and scrub palettes went darker and cooler.
- **Peat read as flat near-black polygons with salt-and-pepper edges.** The
  cause was roughness, not colour: a sheen driving roughness to 0.22 turns matte
  peat into a dark mirror under overcast. Raised, and the surface dither pulled
  back now the two neighbouring classes sit nearer in tone.
- **Scrub read as straw bales, then as strewn blossom.** The atlas was 47%
  opaque — a solid mat, not an airy fringe — and the four atlas quarters were
  drawn uniformly, so a quarter of every clump on the moor carried white bog
  cotton. Thinned to 21% coverage and weighted so cotton is rare.
- **The barrow turf read as mown lawn.** Toned back toward the moor.
- **The bay was an inlet, not a coast.** 2.6% of the playable area, and the
  "coastal panorama" capture looked down a drain channel. Widened to 5.8%.
- **The standing stones were too small to read.** Measured against the painting
  — 576 m across 512 px puts its visible stones near 5 m — the first pass at
  1.7–3.2 m read as gravel from the air and as knee-high posts beside panel 3.
- **The moor was too sparsely stoned.** The aerial is covered in menhirs
  standing singly and in twos, not only in rings. 360 scattered standing stones
  were added.
- **Nine of the ten panel cameras framed the middle distance with their subject
  as a speck.** They were hand-written in design space; they are now derived
  from where the landmarks actually ended up, each eye a few metres off its
  subject on the subject's open side.

## Five kit pieces rebuilt after the first look

The barrow revetment stepped into a staircase because block count and arc span
both varied per course; the causeway bridge was built at half width; the croft
walls were rows of separate posts because stone size was not tied to course
spacing; the peat bank was buried below y = 0 leaving only its winch visible;
and the wisp's opaque outer shell hid its own core.

## Shared files touched

`godot-client/data/maps/registry.json` and
`maps/nymara-regions/production-index.json` — the `grey_moors` entry only, in
both. Expect to resolve any conflict by keeping both sides.

## Server

Separate branch, `feature/grey-moors-96-server-map` on `eloria-server`. Four
tables plus `maps.txt` and `client_content_manifest.json`. The portal
coordinates in `maps.txt` are rescaled from the 192-cell grid to the 576-cell
one for both of Grey Moors' declared neighbours.

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


## September 2026 — peat road, barrow approach and cove ferry

The arrival lacked a through road from Westhaven, and the boardwalks often
crossed the direction of the paths instead of the water on those paths.
Surveyed timber and stone spans now join their banks, while a low turf-roof
refuge groups existing services beside the western peat workings. Named
residents occupy their workplaces and existing species are placed in habitat
rings, retaining their counts, roles and dialogue.

The coastal shrine was below the sea and the ferry marker stood on a dry
eastern ridge. The shrine and headland moved above the cove, and the ferry now
uses a real jetty with the same stable portal id. The Great Barrow gained a
clearer stone crown, a south-facing entrance and an ascent around its shoulder.
The court footprint was reduced after player-height views revealed that it
cut an abrupt shelf into the mound.

The shared civic kit gained a continuous sloping plank walk and a low roadside
shelter. Moor doorway recipes can preserve their recessed dark material.
The distant backdrop now clips out of the playable ground; its old coarse
surface was visible through the moor. The manifest daylight direction and
offline deck lighting were corrected. No surface class or imported asset was
introduced. Validation and final captures are recorded in layout-review.md.
