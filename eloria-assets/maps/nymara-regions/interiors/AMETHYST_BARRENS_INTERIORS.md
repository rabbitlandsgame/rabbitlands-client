# Amethyst Barrens insides

Four interiors on **one map** with blackspace between them, in the Eternal Lands
convention: one GLB, one manifest, one collision grid, one server map key, and a
separate arrival point per surface door.

Package: `interiors/amethyst_barrens_insides/`
Server map key: `resonant_vault` → `maps/nymara/resonant_vault.elm`

| section | name | class | surface door | offset on the map | arrival |
|---|---|---|---|---|---|
| `resonant_vault` | The Resonant Vault | dungeon | `glasswarden-observatory` | (53, 39) | (53, 0.05, 39) |
| `geode_hollow` | The Geode Hollow | cave | `amethyst-geode-cave-1` | (193, 39) | (193, 0.05, 39) |
| `shardworks` | The Shardworks | workings | `resonant-crystal-cluster-0` | (83, 229) | (83, 0.05, 229) |
| `storm_barrow` | The Storm Barrow | barrow | `amethyst-storm-ruin-0` | (218, 229) | (218, 0.05, 230) |

Combined: 129,254 triangles, 15.21 MB, 23 nodes, collision 444 × 636 at 0.5 m.
The map spans x 30…250, z 30…344, which fits a 64 × 64 tile server map with a
margin on every side.

## The blackspace

It is not drawn and it is not masked. The collision grid is built only where a
`Walk_` surface exists, so the gutters between sections are blocked by
construction — there is nothing there to render and nothing there to stand on.
That is why the combined map reports **18% walkable**: the other 82% is the rock
around each section and the void between them, which is the whole point.

Sections are placed from their measured footprints so no two come within about
forty metres. That gap is not decoration: it is what keeps one section's lamps
and cameras out of the next.

## Why four different kinds of place

A region whose interiors are all the same room with different props has no
interiors. These are built from four deliberately disjoint material sets:

**The Resonant Vault** — dressed slate and brass, lit, occupied. What the
Glasswardens actually do with the crystal. Follows the ten subjects its concept
package at `interiors/resonant_vault/concept.json` specified: sealed approach,
laboratory gallery, archive aisle, crystal brazier, experiment table, lens room,
containment cell, energy crossing, research hall, material study. The
brass-inlaid slate floor carries every one of them.

**The Geode Hollow** — the counterweight. No dressed stone, no brass, no
straight line: a throat down through rock into the inside of a geode, with a
still pool doubling it. Crystal is placed on a radial falloff so shards are
dense against the walls and thin over the floor a player crosses.

**The Shardworks** — timber, iron, dust and spoil. A headframe, a shaft, a
sorting floor with a scale pan, a cutting floor, a working stope with a cart, a
winze to the deep. The only section where people are working, and the only warm
one.

**The Storm Barrow** — coarse rubble and unadorned ashlar, older than the
Glasswardens. A ruined dromos, standing stones brought inside, and a strike well
open to the region's sky where lightning comes down onto a fused floor with
fulgurite branching up the walls. No brass anywhere in it.

## Building it

```sh
cd ../amethyst_barrens/source
python build_interiors.py                 # the combined map
python preview_interior.py insides ../../interiors/amethyst_barrens_insides/references/00-checkpoint-contact-sheet.png \
       --captures ../../interiors/amethyst_barrens_insides/references/captures --cols 6
python export_insides_collision.py              # the server walk grid, from the package's own collision.bin
PYTHONPATH=../../_toolkit python ../../_toolkit/verify_runtime.py \
       --package ../../interiors/amethyst_barrens_insides
```

`interiors.py` still builds each section on its own for iteration —
`preview_interior.py resonant_vault …` works — and `combine()` assembles them.

## The round trip

Every one of the region's four doors targets the same `destinationMap` and
differs only in `destinationSpawn`. Each arrival on the insides map carries a
return portal back to the door it came from, and the region carries a spawn of
the same name so the return has somewhere to land. Both directions resolve.

The server side is in `eloria-server` on `feature/amethyst-insides-server-map`:
`config/eloria/maps.txt` now routes `resonant_vault` to and from
`amethyst_barrens` — it previously routed to `four_gates`, which is not where the
Vault is — with one portal pair per door, and the generator builds it at 64
tiles with the arrival at (25, 307).

`export_insides_collision.py` writes the server walk grid by downsampling the package's own
`collision.bin`, so the client and server maps cannot drift apart. Every portal
coordinate in `maps.txt` was checked against that ELM and lands on a walkable
cell.

## Verification

```
validate_gltf   0 errors, 0 warnings
verify_runtime  0 errors, 1 warning
```

The warning is `GROUNDING_RAY_MISS` over 87% of sampled tiles. On a combined
insides map that is expected and is the blackspace being measured: the harness
samples the whole square footprint, and most of this map is deliberately void.

Two of the four doors were found sitting on **blocked** tiles — a landmark that
collides blocks its own footprint, and the doorway is attached to the landmark.
`build_amethyst.py` now checks every spawn and portal against the finished
collision grid and nudges any that landed on a blocked cell onto the nearest
walkable one, reporting the distance. The geode door moved 8.1 m and the barrow
door 5.0 m. All eight coordinates — four doors and four return spawns — are
walkable, and match the server's portal table.

## What is not verified

- **Nothing has been played.** Collision response, navmesh generation, portal
  transitions and transparency sorting are unverified. The client frames in
  `references/client-captures/` prove the map loads and renders through the real
  `WorldLoader.load_world()`; they do not prove an actor can walk it, or that a
  portal fires.
- **One environment for four places.** A combined map has one ambient and one
  fog. The Barrow's strike well is genuinely open to the region's sky and stays
  declared in `open_to_sky`, but the map as a whole is lit as sealed, so that
  well will not currently show sky. Per-space environments are a client change
  nobody has needed yet.
- **The concept package still describes only the Vault.**
  `interiors/resonant_vault/` holds the ten-panel brief for one of the four
  sections; the other three have no concept art and are authored from the
  region's board and its surface landmarks.
- Place names are the author's throughout except The Resonant Vault.

## Small rooms

Three more sections joined the `resonant_vault` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Amethyst Barrens
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `sour_cut` | Sour Cut | cave | `sour-cut-mouth` | a crystal cave with a crystal cave spider's den |
| `measure_house` | the Measure House | shrine | `measure-house-door` | a crystal shrine |
| `counting_house` | the Counting House | cottage | `counting-house-door` | a workshop cottage |
