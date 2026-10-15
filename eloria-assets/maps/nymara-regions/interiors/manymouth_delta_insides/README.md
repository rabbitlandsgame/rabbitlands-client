# Manymouth Delta insides

Four authored interiors on one map, in the Eternal Lands convention: **one GLB,
one manifest, one collision grid, one server map key, and a separate arrival
point per surface door**, with unwalkable blackspace between the sections.

The server map key is `manymouth_flooded_labyrinth` — the key the region's one
placeholder interior already had — grown from 32 to 64 ELM tiles, exactly as
`resonant_vault` and `drowned_crown` were grown for Amethyst Barrens and
Crownwater.

| Section | Kind | Offset | Surface door | Arrival spawn |
| --- | --- | --- | --- | --- |
| `flooded_labyrinth` | drowned ruin | (60, 40) | the cave mouth in the rock headland | `labyrinth-mouth` |
| `smugglers_warren` | working warren | (170, 40) | a hatch under the town quay's ferry post | `underdeck-hatch` |
| `tide_hall` | inhabited hall | (60, 240) | the Tide Hall door | `tide-hall-door` |
| `temple_sanctum` | monumental sanctum | (165, 230) | the Sanctum stair on the temple | `temple-sanctum-door` |

There is a **fifth** arrival, and it is the one worth the convention:

| `gate-descent` | the great arch in the whirlpool | into the gate chamber, under it |
| --- | --- | --- |

The ring standing out of the water on the region map is the **top of the
Submerged Gate** in the labyrinth's last chamber. Descending through the arch
lands underneath it, and a drowned stair on the far side of that chamber comes
back up. Both ends were already geometry; the portal only admits they are the
same object. It is why the labyrinth has two ways in and the other three
sections have one.

Every door on the region map targets the same `destinationMap` and differs only
in `destinationSpawn`. Each arrival carries a return portal back to the door it
came from, and the region gained a spawn of the same name so the return has
somewhere to land. Both directions resolve.

## Why these four

A region whose interiors are all the same room with different props has no
interiors. These are four different kinds of place, and each answers a question
the exterior raises but cannot:

* **The Flooded Labyrinth** — drowned, dark, ancient. *What the great arch is.*
  The ring that stands out of the whirlpool on the region map is the **top of a
  gate whose lower half is down here**: you row past it for hours on the surface
  and then walk in under it. That reversal is the reason the region's
  centrepiece is worth having an interior at all. Floors step down while the
  water line stays at y = 0, so the player wades progressively deeper without a
  single depth being authored.
* **The Underdeck** — timber, lamplit, working. *What is under the town.* Every
  ceiling in here is plank decking somebody is walking on, and every column is a
  pile you moor a boat to on the surface. The maze's crossings sit at four
  different levels and are deliberately not aligned, so from under one you can
  see the others overhead.
* **The Tide Hall** — dry, inhabited, warm. *Who lives here.* The only one of
  the four with fire and textiles in it, and the only one whose floor is swept.
  Its tide post is a carved post banded in bronze at every flood the village
  remembers: a delta village's history is a list of how high the water came.
* **The Sanctum** — monumental, austere, half open to the sky. *What they
  believe.* The counterweight to the warren: no timber in it anywhere, every
  dimension larger than it needs to be, and rain falling down the oculus into a
  standing pool.

## Runtime files

| File | What it is |
| --- | --- |
| `world.glb` | Self-contained glTF 2.0 — 87,378 triangles, 11.8 MB |
| `world.json` | Manifest: four sections, 6 spawns (default plus five arrivals), 5 return portals, 127 lights, spaces, landmarks, interactives, NPC markers, harvestables |
| `collision.bin` | `EWCG` v1, 366 × 702 at half a metre, 21.4% walkable |
| `world.glb.validator.json` | glTF 2.0 validation — **0 errors, 0 warnings** |
| `verification-report.json` | Runtime contract — **0 errors**, 1 documented warning |
| `references/captures/` | Offline preview renderer |
| `references/godot-captures/` | **Real Godot 4.7.2 client frames** |
| `references/00-detail-board.png` | The ten-panel board, **built, not concept art** — see below |

## The blackspace

Not drawn and not masked. The collision grid is built only where a `Walk_`
surface exists, so the gutters between sections are blocked *by construction*
rather than by a mask that could drift out of step with the geometry. Sections
are placed so no two come within about forty metres, which keeps one section's
lamps out of the next.

The consequence, which is expected and is the point: `verify_runtime.py` reports
**88.8% grounding-ray misses** on this map. It is measuring the void. The
server-side walk grid comes out 90.7% blocked for the same reason.

## Lighting

Two classes, because one is not enough:

* **Hanging oil lanterns** — 116 of them, range 9 m, warm. The region's readable
  light source, and what almost every room is lit by.
* **Shafts** — 11 large cold sources, in the only two rooms a lantern cannot
  light: the forty-metre gate chamber, whose subject is a glowing ring, and the
  sanctum's court, which is open to the sky. Giving those rooms thirty more
  lanterns would light them by making the lantern meaningless.

## Build

```sh
cd ../../manymouth_delta/source
python3 build_interiors.py                       # writes this package
python3 export_insides_collision.py                    # writes the 64x64 server ELM
python3 preview_interior.py insides sheet.png --captures ../../interiors/manymouth_delta_insides/references/captures
python3 ../../_toolkit/verify_runtime.py --package ../../interiors/manymouth_delta_insides
```

Real client frames, from the repository's own Godot project:

```sh
cd ../../../../godot-client
Godot_v4.7.2-stable_win64_console.exe --headless --path . --import   # once
Godot_v4.7.2-stable_win64_console.exe --path . \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
  --rendering-driver vulkan --resolution 1400x900 -- \
  --package=<abs>/interiors/manymouth_delta_insides --out=<abs>/.../godot-captures
```

## The board

`references/00-detail-board.png` is a ten-panel 5x2 board answering the exact
ten subjects `concept.json` names, composed by `source/make_interior_board.py`
from real client frames. It says on its own face that it is a build reference
and not concept art, and it is deliberately **not** written into the concept
package and **not** named `00-concept-detail-board.png`: the truncated original
stays exactly where it is, so a re-supplied board replaces that one and this
stays what it is.

It exists because a detail board answers "what does this place look like at eye
height?" and the file that was supposed to answer it cannot be opened.

## Every transition is checked

`build_interiors.py` fails the build unless every region door names an arrival
that exists, every arrival is reachable from a door, and every return portal
names a region spawn that exists. The two halves of a transition are authored in
two different build scripts and nothing had ever checked they agree; a door
whose `destinationSpawn` names nothing drops the player at the map's default
spawn, which on a combined insides map is in a completely different section, and
neither failure shows up in a validator. The check caught exactly that while the
fifth door was being added.

## Honest about the concept art

**The interior concept board is truncated** to 786,446 bytes and only the top
tenth of each panel decodes — worse than the region board, which at least gave
its top row. What survives establishes a palette of wet dark stone, hanging
root, lamplit timber and green water, and nothing else.

These four compositions are therefore authored from:

1. the ten subjects `manymouth_flooded_labyrinth/concept.json` names — *hidden
   entry, stilt corridor, boardwalk maze, flood channel, smuggler cache, crate
   workroom, root chamber, submerged gate, labyrinth panorama, reed rope
   mangrove materials*;
2. the QA brief's prose layout — boardwalk crossings over flood channels between
   smuggler shelves and fishing-cargo caches;
3. the region board's **intact** panel 8, the drowned chamber with the glowing
   ring;
4. the region itself — its materials, its kit, its palette.

The rest is invented. **Anything a re-supplied board contradicts should be
changed to match it.**

## What has not been verified

* **No portal transition was ever taken.** The frames are real Godot renders of
  the real GLB through `GLTFDocument`, which is the loader path, but no server
  ran, so neither direction of any door has been walked through.
* **`sky: none` and `openToSky` are declared, not implemented.** The sanctum's
  court is authored as open to the sky and lit as if it were; nothing in the
  client currently puts a hole in a roof.
* **Every name is invented**, as in the region above.
* **The Underdeck's NPC and creature markers are positions**, not an encounter
  design. They carry `"authority": "server"`.
