# Verdant Stair insides

Four interiors on **one map** with blackspace between them, in the Eternal Lands
convention: one GLB, one manifest, one collision grid, one server map key, and a
separate arrival point per surface door.

Package: `interiors/verdant_stair_insides/`
Server map key: `verdant_stair_insides` → `maps/nymara/verdant_stair_insides.elm`

| section | name | class | surface door | offset on the map | arrival |
|---|---|---|---|---|---|
| `temple_sanctum` | The Green Sanctum | temple | `great-temple` | (60, 34) | (60, 0.05, 32) |
| `cenote_deeps` | The Cenote Deeps | cave | `cenote` | (210, 34) | (210, 0.05, 34) |
| `banyan_hollow` | The Banyan Hollow | tree-hall | `canopy-village` | (60, 209) | (60, 0.05, 207.5) |
| `stair_quarry` | The Stair Quarry | workings | `quarry` | (180, 209) | (180, 0.05, 210) |

Combined: 62,717 triangles, 10.53 MB, collision 546 × 594 at 0.5 m. The map
spans x 15…285, z 19…314, which fits a 64 × 64-tile server map with a margin on
every side.

## The blackspace

It is not drawn and it is not masked. The collision grid is built only where a
`Walk_` surface exists, so the gutters between sections are blocked by
construction — there is nothing there to render and nothing there to stand on.
That is why the combined map reports **18.6% walkable**: the other 81% is the
rock around each section and the void between them, which is the whole point.
The exported server ELM says the same thing from the other side — 10.2%
walkable over its 384 × 384 cells.

Sections are placed from their measured footprints so no two come within about
forty metres. That gap is not decoration: it is what keeps one section's lamps
and cameras out of the next.

## Why four different kinds of place

A region whose interiors are all the same room with different props has no
interiors. These are built from four deliberately disjoint material sets:

**The Green Sanctum** — cut jade, carved jade and gilt on mossy stone. Lit,
level, and the only section in the map with a straight axis: a narthex behind a
relief screen, a colonnaded processional with the aqueduct's water running down
a runnel in its floor, a domed sanctum around a seated figure on a gilt-ringed
dais, a still basin off the east side, and an aisle of relief racks. This is
what the whole stair climbs toward, so it is the one place that is *finished*.

**The Cenote Deeps** — the counterweight. No dressed stone and no straight
line: the foot of the shaft the surface package cuts, open to the sky and
growing ferns where the light lands, then a water-cut gallery, a half-drowned
hall of flowstone pillars and stalactites, and a root hall where banyan roots
have come down through the roof. The only built object in it is the bottom of
the same spiral stair the surface uses.

**The Banyan Hollow** — bark, timber, thatch and rope. People living inside a
tree: a root arch, the hollow itself with a stair winding up the trunk and two
rope walkways crossing overhead, a store among the roots, and a loft with a
plank floor, trusses and a hearth. The warm one, and the only section with a
floor above another floor.

**The Stair Quarry** — rubble, timber, iron and spoil. Every terrace on the
surface is faced with cut limestone and this is the hole it came out of: a
propped adit, a working face with blocks still keyed into it and the wedge
channels cut round them, a sorting floor with spoil and a cart, and a flooded
sump down a winze. The only section where the stone is a product rather than a
setting.

## Building it

```sh
cd ../verdant_stair/source
python build_interiors.py                 # the combined map
python preview_interior.py insides ../../interiors/verdant_stair_insides/references/00-checkpoint-contact-sheet.png \
       --captures ../../interiors/verdant_stair_insides/references/captures --cols 5
python export_insides_collision.py              # the server walk grid, from the package's own collision.bin
PYTHONPATH=../../_toolkit python ../../_toolkit/verify_runtime.py \
       --package ../../interiors/verdant_stair_insides
```

`interiors.py` still builds each section on its own for iteration —
`preview_interior.py temple_sanctum …` works — and `combine()` assembles them.

Real client frames, which is what `references/client-captures/` holds:

```sh
cd ../../../../../godot-client
Godot_v4.7.2-stable_win64_console.exe --path . --headless \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/region_client_check.gd -- \
  --manifest=<abs>/verdant_stair_insides/world.json --step=2 \
  --report=<abs>/verdant_stair_insides/client-check-report.json
Godot_v4.7.2-stable_win64_console.exe --path . \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
  --rendering-driver vulkan --resolution 1180x760 -- \
  --package=<abs>/verdant_stair_insides --out=<abs>/verdant_stair_insides/references/client-captures
```

## The round trip

Every one of the region's four doors targets the same `destinationMap` and
differs only in `destinationSpawn`. Each arrival on the insides map carries a
return portal back to the door it came from, and the region carries a spawn of
the same name so the return has somewhere to land. Both directions resolve, and
that is checked rather than assumed:

```
region doors ask for : banyan-hollow-arch cenote-deeps-stair stair-quarry-adit temple-sanctum-door
insides provides     : banyan-hollow-arch cenote-deeps-stair stair-quarry-adit temple-sanctum-door
insides returns ask  : banyan-hollow-arch cenote-deeps-stair stair-quarry-adit temple-sanctum-door
region provides      : ... all four, plus default, temple-court and west-quay
```

All thirteen coordinates — four doors, four region return spawns, two edge
portals, and the three original region spawns — land on walkable collision
cells, and all five insides arrivals land on walkable cells of the exported
ELM.

The server side is in `eloria-server` on
`feature/verdant-stair-insides-server-map`: `config/eloria/maps.txt` registers
the map and routes four portal pairs between `verdant_stair` and
`verdant_stair_insides`, and the generator builds it at 64 tiles with the
arrival at (47, 284). `export_insides_collision.py` writes the server walk grid by
downsampling the package's own `collision.bin`, so the client and server maps
cannot drift apart, and every portal coordinate in `maps.txt` was checked
against that ELM.

## Verification

```
validate_gltf   0 errors, 0 warnings
verify_runtime  0 errors, 3 warnings
client check    PASS (Godot 4.7.2, through the project's own WorldLoader)
```

The `verify_runtime` warnings are `GROUNDING_RAY_MISS` over 82.9% of sampled
tiles, `GROUNDING_DISCONTINUITY` at the Banyan Hollow's loft over its own floor,
and one landmark note. The first is the blackspace being measured: the harness
samples the whole square footprint and most of this map is deliberately void.

In-engine, develop's `region_client_check.gd` measures the same thing far more
usefully. It reads this package's own `collision.bin` through the
`originMetres` the manifest publishes and splits the misses in two:

```
grounding: 18769 tiles sampled, 15283 misses (81.43%)
  of those, 0 are on cells collision.bin marks walkable;
            15283 are blocked cells and expected
```

**Zero misses on walkable cells** is the criterion that matters, and it is the
one this package is judged on. It says every cell the grid invites a player to
stand on has floor under it in the running client - which is a stronger claim
than the miss rate, and not one the raw 81% can make either way. The same check
finds eleven such tiles in Whitehorn's interior and more in two of Amberwood's,
so it is a criterion with teeth rather than a formality.

## Three defects this pass found in code that was already shipped

1. **Interior capture file names could contain a colon.** `preview_interior.py`
   builds a file name out of the subject prose — "The Green Sanctum: the seated
   figure" — and a colon is a drive separator on Windows, so the Godot capture
   pass silently wrote *directories* instead of PNGs. Names are sanitised now.
2. **`build_collision` stamped an elevated walk surface as a filled disc.**
   Right for a solid deck, wrong for a ring: the cenote's spiral stair winds
   around an open shaft, so the grid claimed a floor across the middle of an
   eighteen metre hole — cells the server would let a player walk onto and the
   client would drop them through. Spawn and portal heights are taken by casting
   the client's own ray against the `Walk_` geometry rather than read out of the
   grid, and **the grid itself is now fixed too**: the region rasterises its
   walk surfaces triangle by triangle, the way this package's `build_collision`
   always did. `../verdant_stair/change-log.md`, items 14 and 15 — 15 being why
   `verify_runtime` could not catch it.
3. **The region's arrival platform had a hole exactly where the player lands.**
   The waygate was a lathe whose profile ends on the axis; the pole's sliver fan
   is removed by `drop_degenerate` on export, leaving a pinhole on the axis -
   where the default spawn stands. The client grounded the player 0.54 m inside
   their own platform, and nothing caught it, because the manifest read its
   spawn height from the terrain too and the check compared two values derived
   the same wrong way. Replacing the lathe with a capped cylinder then wound the
   new cap downward, which is worse - Godot's navigation collision is one-sided
   for raycasts, so the whole platform went invisible rather than just its
   centre. This is a defect in the region package, not in the insides; it was
   only found here. Full account and the three changes it took in
   `../verdant_stair/change-log.md`, item 13.

## What is not verified

- **Nothing has been played.** Collision response, navmesh generation, portal
  transitions and transparency sorting are unverified. The client frames in
  `references/client-captures/` prove the map loads and renders through the real
  `WorldLoader`; they do not prove an actor can walk it, or that a portal fires.
- **`verify_runtime`'s walkable-cell cross-check is inert on a region.** The
  cenote grid is fixed, but not because a check found it. That check has two
  arms and this defeated both: "no surface under this cell" never fires, because
  a ray down the shaft still hits the terrain at the bottom, and the height
  comparison is skipped for any cell whose encoded height saturates — which is
  **98.1% of the region's walkable cells**, the six-bit field ceilinging at
  10.4 m against 149 m of relief. Left alone deliberately: it is a shared-toolkit
  change affecting every region and wants its own commit and verification.
- **One environment for four places.** A combined map has one ambient and one
  fog. The cenote shaft foot and the top of the banyan trunk stay declared in
  `openToSky` because both are genuinely holes the surface package cuts, but the
  map as a whole is lit as sealed, so neither will currently show sky.
- **No concept package.** Verdant Stair has an aerial and a ten-panel board and
  no interior brief at all, so all four sections are authored from the region's
  surface landmarks and that board. Every place name here is the author's.
- **The server has not served it.** The 19 affected tests pass; that is not the
  same as the map being loaded by a running server.

## Small rooms

Three more sections joined the `verdant_stair_insides` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Verdant Stair
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `anchor_hollow` | Anchor Hollow | cave | `anchor-hollow-mouth` | a moonshadow lynx's den behind the fern camp |
| `physick_still` | the physick still | cottage | `physick-still-door` | the herbalist's still |
| `nine_lost` | the Nine Lost | shrine | `nine-lost-door` | a water shrine by the south quay |
