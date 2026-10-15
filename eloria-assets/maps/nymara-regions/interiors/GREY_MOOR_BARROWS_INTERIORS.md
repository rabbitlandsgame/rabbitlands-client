# Grey Moor barrows

Four barrows on **one map** with blackspace between them, in the Eternal Lands
convention: one GLB, one manifest, one collision grid, one server map key, and a
separate arrival point per surface door.

Package: `interiors/grey_moors_insides/`
Server map key: `grey_moor_barrows` → `maps/nymara/grey_moor_barrows.elm`
Concept package: `interiors/grey_moor_barrows/`

| section | name | class | surface door | offset | arrival | ELM tile |
|---|---|---|---|---|---|---|
| `great_barrow` | The Great Barrow | tomb | `great-barrow-mouth` | (40, 36) | (44.5, 0.05, 39.5) | (11, 162) |
| `root_crypt` | The Root Crypt | crypt | `west-crypt-stair` | (135, 36) | (138.0, 0.05, 38.75) | (105, 163) |
| `bone_gallery` | The Bone Gallery | ossuary | `east-crypt-stair` | (40, 141) | (43.0, 0.05, 143.5) | (10, 58) |
| `fen_crypt` | The Fen Crypt | flooded | `south-crypt-stair` | (135, 141) | (138.0, 0.05, 143.5) | (105, 58) |

Combined: 32,386 triangles, 9.01 MB, 19 meshes, collision 270 × 336 at 0.5 m,
11.0% walkable. The map spans roughly x 33…168, z 36…202, which fits a 64 × 64
tile server map with a margin on every side.

## The blackspace

It is not drawn and it is not masked. The collision grid is built only where a
`Walk_` surface exists, so the gutters between sections are blocked by
construction — there is nothing there to render and nothing there to stand on.
That is why the map reports **11% walkable**: the other 89% is the rock around
each section and the void between them, which is the whole point.

Sections are placed from their measured footprints so no two come within about
forty metres. The narrowest gap is 47 m, between the Great Barrow's tomb end and
the Bone Gallery's stair head. That gap is not decoration: it is what keeps one
section's candles and cameras out of the next.

## Why four different kinds of place

A region whose interiors are all the same room with different props has no
interiors. These are built from four deliberately disjoint sets:

**The Great Barrow** — the royal one, and the only one built to be looked at.
Dressed granite, a dromos descending under a spiral-carved arch, a vaulted hall
with eight sarcophagi between a colonnade, and a tomb chamber where a raised
dais carries the royal chest between two standing stones brought inside. Its
shaft is declared `open_to_sky`. Panels 1, 3, 5 and 9.

**The Root Crypt** — the counterweight. No dressed stone worth the name: earth
floors, a rubble vault the moor has pushed in, and the roots of the moor's dead
trees through the ceiling and down the walls, with two sarcophagi they have
broken open. Root geometry comes from the toolkit's own `root_ribs`, which is
what it was written for. Panel 7.

**The Bone Gallery** — long, dry and mean. A corbelled burial gallery whose
walls are thirty-two bone niches in two tiers, a ritual altar at its head
between two menhirs, and a stake corridor that is the only part of these barrows
built to keep people out rather than in. The stakes are geometry, not collision:
the trap is the server's to run. Panels 2, 4 and 6.

**The Fen Crypt** — drowned. Shin-deep peat water standing over an ossuary
floor, pillars in it, bones and skulls on the bottom, a sunken sarcophagus with
its lid off, and a drystone shelf and causeway a step up out of the water.
Panel 8.

## Building it

```sh
cd ../grey_moors/source
python build_interiors.py                 # the combined map
python preview_interior.py insides ../../interiors/grey_moors_insides/references/00-checkpoint-contact-sheet.png \
       --captures ../../interiors/grey_moors_insides/references/captures --cols 5
python export_insides_collision.py              # the server walk grid, from the package's own collision.bin
PYTHONPATH=../../_toolkit python ../../_toolkit/verify_runtime.py \
       --package ../../interiors/grey_moors_insides
```

`interiors.py` still builds each section on its own for iteration —
`preview_interior.py great_barrow …` works — and `combine()` assembles them.

## The round trip

Every one of the region's four doors targets the same `destinationMap` and
differs only in `destinationSpawn`. Each arrival on the insides map carries a
return portal back to the door it came from, and the region carries a spawn of
the same name so the return has somewhere to land. Both directions resolve.

**All eight coordinates are on walkable cells**, checked against the collision
grid rather than assumed — and checked with the grid's own
`collision.originMetres` anchor, not the world origin, which is what makes the
first attempt at this check report every one of them blocked.

The server side is in `eloria-server` on `feature/grey-moors-96-server-map`,
alongside the region's own 96x96 change: both touch the same six files, so
keeping them on one branch avoids a conflict between two of my own PRs.
`config/eloria/maps.txt` had a single portal pair between `amethyst_barrens` and
`grey_moor_barrows` — the same shape of error the Resonant Vault had when it
routed to `four_gates`. The barrows are Grey Moors' own insides:
`interiors/grey_moor_barrows/concept.json` has always declared
`parentRegion: grey_moors`, and the four doors stand on the Grey Moors map. That
pair is replaced by four, one per door, both directions, and every coordinate is
checked against an exported ELM.

## Verification

```
validate_gltf   0 errors, 0 warnings, 0 infos
verify_runtime  0 errors, 2 warnings
```

Both warnings are the blackspace being measured, and both are expected on a
combined insides map:

- `GROUNDING_RAY_MISS` over 91% of sampled tiles. The harness samples the whole
  square footprint and most of this map is deliberately void.
- `COLLISION_TOO_TIGHT` at 11% walkable, for the same reason.

## A toolkit bug this found

`preview_interior.py` built each capture's filename from its subject text, and
subjects are prose containing colons — "The Great Barrow: the royal tomb". A
colon is legal in a POSIX filename and is not on Windows, where `name:rest.png`
silently creates an alternate data stream on `name` rather than a file. The
captures came out as a directory of empty extension-less files, and the Godot
harness — which takes its output filename from the same id — wrote nothing at
all while reporting success.

Fixed with a `_safe_name` sanitiser on the capture id. **`amethyst_barrens_insides`
has the same latent defect**: its `references/captures/` is a directory of
extension-less files for exactly this reason. It is not fixed here because
re-running its captures is that region's change to make, not this one's.

## What is not verified

- **Nothing has been played.** Collision response, navmesh generation, portal
  transitions and water rendering are unverified. The frames in
  `references/client-captures/` are real Godot 4.7.2 renders through the
  client's own `WorldLoader.load_world()`; they prove the map loads and renders,
  not that an actor can walk it or that a portal fires.
- **One environment for four places.** A combined map has one ambient and one
  fog. The Great Barrow's shaft stays declared in `open_to_sky`, but the map is
  lit as sealed, so it will not currently show sky. Per-space environments are a
  client change nobody has needed yet.
- **The client frames are very dark.** `godot_capture.gd` lights every region
  identically so regions can be compared, and that key is calibrated for
  outdoor regions. Judge geometry and material from those frames; judge the
  intended candle-lit look from `references/captures/`, which use the barrows'
  own tallow key.
- **The concept package's ten panels cover the barrows as a whole**, not one
  section each. The mapping of panels to sections above is this package's
  reading of the board.
- **Place names are the author's throughout.** The authoritative written
  descriptions for Nymara were not available, as they were not for the region.

## Small rooms

Three more sections joined the `grey_moor_barrows` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Grey Moors
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `fifth_chamber` | the Fifth Chamber | cave | `fifth-chamber-mouth` | the false barrow, a moorland dire wolf's den |
| `peat_croft` | the peat croft | cottage | `peat-croft-door` | a hearth cottage |
| `warm_stone` | the Warm Stone | shrine | `warm-stone-door` | a stone shrine over a crypt |
