# Ssarathi Ruins interiors

Ssarathi's four insides share **one map with unwalkable blackspace between
them**, the way Eternal Lands lays out a region's interiors, and the way
`amethyst_barrens_insides` and `crownwater_insides` already do in this
repository. One package, one GLB, one collision grid, four sections, one spawn
and one exit portal each.

Package: `interiors/ssarathi_insides/`. Server map: `ssarathi_royal_archive.elm`.

| section | name | class | walkable cells | surface door |
|---|---|---|---:|---|
| `royal_archive` | The Royal Archive | archive | 18,176 | `sun-vault` |
| `drowned_cistern` | The Drowned Cistern | utility | 13,820 | `cistern-shaft` |
| `serpent_hatchery` | The Serpent Hatchery | sanctum | 13,604 | `hatchery-descent` |
| `root_undercroft` | The Root Undercroft | ruin | 8,552 | `undercroft-mouth` |

115,294 triangles, 11.09 MB, 468 × 594 half-metre collision cells of which
**19.5% are walkable** — the rest is the blackspace between sections and the
rock around each.

## Layout

```
z=324  +----------------+          +------------------+
       | drowned        |          | root undercroft  |
       | cistern        |          |                  |
z=252  +----------------+          +------------------+

z=166  +----------------+          +----------------+
       | royal archive  |          | serpent        |
       | 68 x 135 m -   |          | hatchery       |
       | it sets the    |          |                |
       | map size       |          |                |
z= 31  +----------------+          +----------------+
         x=31      x=99             x=191     x=261
```

Closest approach between any two sections is **74 m** — far beyond the reach of
any lamp, any grounding ray, or the collision grid.

**The blackspace costs nothing to build.** `build_collision` marks a cell
walkable only where a `Walk_` surface actually covers it, so every cell between
the sections is already zero, which is exactly what "blocked" means in EWCG v1
and what the server reads as void. The gaps are not drawn; they are the absence
of floor.

## The Archive's concept board does not decode

`interiors/ssarathi_royal_archive/references/00-concept-detail-board.png` is the
same truncated 786,444-byte file fifteen of the seventeen boards in this
repository carry — but **this one is worse than the region's was**. The region's
board decoded its top row of five panels; this one decodes **zero rows**. The
IDAT stream is corrupt from its first byte, and the copy under `dev/` is
byte-identical. There is no intact version anywhere in the tree.

The intact region board was supplied for the exterior build. This one was not,
and it was not asked for in time to use.

So the Archive was worked from the two authorities that do survive:

1. **`concept.json` lists its ten subjects in words** — water entrance, reading
   hall, scaled mosaic, water arch, archive shelves, royal statue, vault trap,
   flooded repository, central archive, and a material study of scale, stone and
   papyrus. Every one is a space or a fitting in the build.
2. **The authored asset pack names the same pieces** —
   `ssarathi_water_door`, `ssarathi_curved_wall`, `ssarathi_scaled_floor`,
   `ssarathi_water_arch`, `ssarathi_archive_shelf`, `ssarathi_royal_statue`,
   `ssarathi_vault_trap`. That corroborates the list independently and settles
   the naming.

That pack carries one further Ssarathi interior piece that is **not** among the
ten: `ssarathi_hatchery_pool`. A hatchery is therefore intended content for this
region, and it is the second section below.

Crownwater's `drowned_crown` had the same defect and was handled the same way.
**There is no panel comparison for the Archive, because there is no panel.**

## Why these four

Ssarathi is a city the water took, so its insides are about what the water
reached and what it did not. Each section takes a different answer, so no two
are the same room with different textures.

**The Royal Archive** is what was saved, and the only section whose programme
was given rather than invented. Jade ashlar and gilt, curved walls, a
scale-tiled mosaic floor with a gilt ring in it. The through-line is *dryness*:
everything else in this region is wet, and the Archive was built to keep one
thing out. You wade in through a knee-deep water entrance, climb out of the
flood into the reading hall, cross a cut channel on an arch, pass the shelf
aisle and the Serpent King, get past the vault trap, wade a repository the water
*has* got into, and come up into a dry domed heart with a ring gallery. Walking
in is walking out of the water.

**The Serpent Hatchery** is what the place was for, and the Archive's opposite in
every axis. No straight line in it: a stair coils down around a stone serpent
into a cavern where the brooding pools are cut as four concentric terraces
stepping down to a clutch. Scale tiling and rock rather than coursed ashlar.
One dressed room — the warden's cell — so the rest reads as deliberately
undressed.

**The Drowned Cistern** is the water winning, and the counterweight to the
Archive. Undressed rubble, silt underfoot, a hundred columns standing in it,
nine of them gone over, and **not one gram of gold anywhere**. A raised walk
crosses it so the room is traversable rather than only wadeable, and an iron
sluice gear sits in a side room having failed to do its job. This is what the
drowned quarter on the surface is standing on.

**The Root Undercroft** is older than any of them and has no masonry order left.
The strangler figs came through the vault and are now the only thing holding the
ceiling up — the one section whose structure is wood rather than stone, and the
only one where daylight reaches the floor, down a light well the roots opened.
A tomb niche off the side is what it was built for.

## Building it

```sh
cd ../ssarathi_ruins/source
python build_insides.py                                  # the one map
python verify_interiors.py --report ../../interiors/ssarathi_insides/verification-report.json
python export_insides_collision.py                             # the server walk grid
python ../../_toolkit/interior_views.py --package ../../interiors/ssarathi_insides
```

`interiors_ssarathi.py` builds each section on its own for iteration;
`build_insides.py` assembles them and is what ships. Deterministic for a given
seed. Nothing in `_toolkit/` is modified by the interiors.

Real client frames (needs a Godot 4.7.2 binary and a GPU):

```sh
cd godot-client
Godot_v4.7.2-stable_win64_console.exe --path . \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
  --rendering-driver vulkan --resolution 1400x900 -- \
  --package=<abs path to ssarathi_insides> --out=<...>/references/captures \
  --environment=manifest
```

## Verification

`verify_interiors.py` rather than the region's `verify_runtime.py`, and the
difference matters more on a blackspace map than anywhere else. The region tool
casts the grounding ray at every tile of the bounding box and calls a floorless
tile a miss — on this map **80% of the tiles are deliberately floorless**.

The contract that actually holds here is narrower and stricter: *every cell the
collision grid calls walkable must have a walk surface under it.*

| check | result |
|---|---|
| Walkable cells | 54,152 |
| Walkable cells with no surface under them | **0** |
| Collision height disagreements | **0** |
| Spawn and portal grounding problems | **0** |
| glTF validator | **0 errors, 0 warnings** |
| In-client, Godot 4.7.2 through the real `WorldLoader` | **PASS** |

Per-section counts are reported separately, so a section that lost its floor
entirely is visible rather than averaged away across a map that is mostly void.

### The in-client result, and why its headline number looks alarming

```
grounding: 13689 tiles sampled, 11368 misses (83.04%)
  of those, 0 are on cells collision.bin marks walkable;
            11368 are blocked cells and expected
```

83% of sampled tiles miss, and **every one of them is blackspace**. This is
exactly the case develop's `568fbd6e` added the walkable-cell criterion for.
It works here because the package publishes `collision.originMetres`; without
that field the harness falls back to judging every tile and would report a
catastrophe.

All five spawns — the default plus one per door — ground within **0.05 m**.

Everything in `references/captures/` is a **real Godot client frame**, not an
offline preview.

## Where it attaches

Four `interior-entrance` portals on the Ssarathi Ruins region manifest, each on
the landmark it belongs to, all pointing at
`maps/nymara/ssarathi_royal_archive.elm` and choosing their section by spawn id.
The package carries the four matching return portals, and the region carries a
return spawn of each name so both directions resolve.

| door | on Ssarathi Ruins | arrives at | section |
|---|---|---|---|
| `archive-vault-door` | tile (234, 382) | tile (27, 288) | royal archive |
| `hatchery-descent` | tile (342, 291) | tile (189, 281) | serpent hatchery |
| `cistern-shaft` | tile (72, 234) | tile (41, 69) | drowned cistern |
| `undercroft-mouth` | tile (394, 96) | tile (185, 63) | root undercroft |

Three region additions were needed to give three of them a door, because the
region had no building at any of those points:

* **The Cistern Shaft** — a drum well-head with an annular walkable kerb and a
  head-frame, standing in the drowned quarter's shallow water.
* **The Hatchery Descent** — a stepped mouth with a lintel and a sun disc on the
  ritual plaza's north rim, flanked by two serpent columns.
* **The Undercroft Mouth** — a collapsed opening rather than a built door, edged
  in rubble with roots across it, near the Strangled Arch.

The Royal Archive needed nothing: the Sun Vault was already built and already a
landmark.

**Two of the four doors landed on blocked cells** and were nudged 0.4 m onto the
nearest walkable one. A landmark that collides blocks its own footprint and a
doorway is attached to a landmark, so this is the norm rather than the
exception — Amethyst Barrens found two of its four in the same state.
`build_ssarathi.py` now checks all four against the finished collision grid and
reports how far each moved.

## The reassigned portal

`ssarathi_royal_archive` was routed in `eloria-server`'s `config/eloria/maps.txt`
from **sunmane_steppe**. The Archive's own concept package declares
`parentRegion: ssarathi_ruins`, and it is the room behind the Sun Vault at the
Ssarathi temple, so that pair addressed a map that is not where it said it was.

The single `sunmane_steppe ↔ ssarathi_royal_archive` pair is replaced by the four
`ssarathi_ruins` pairs above, the server map's title becomes "Ssarathi Insides",
and `test_nymara_maps.INTERIOR_CONNECTIONS` is updated to match. This is the same
correction Crownwater made for `drowned_crown`, which had been routed from
mirrorhold.

**Sunmane Steppe now has no interior connection.** If it wants one it needs its
own. That is a gameplay change and is flagged here rather than buried.

## Known limitations

* **One environment block serves four sections of different character.** A dry
  archive, a warm hatchery, a flooded cistern and a root-broken ruin want
  different light. The per-section lamps carry most of the difference, but this
  is a genuine compromise of the single-map layout rather than a choice.
* **Lighting is judged by eye.** It was corrected twice against real client
  frames — the first pass had ambient 0.62, sun 0.55, fog 0.010 and lamps at
  15 m range, and produced rooms that were atmospheric in the sense of being
  unreadable. The shipped values are legible. Whether they are *right* is not
  something these captures settle.
* **Nothing has been played.** Collision response, navmesh generation, portal
  transitions and transparency sorting are unverified. The client frames prove
  the map loads and renders through the real `WorldLoader`; they do not prove an
  actor can walk it or that a portal fires.
* **No server has loaded the ELM.** It is exported from the package's own
  collision grid and its header is verified (64 × 64 tiles, 384 × 384 cells,
  90.8% blocked), but end-to-end play was not exercised. As with the region map,
  the server generates its own procedural heights instead.
* **Three of the four sections have no concept art at all**, and the fourth's
  does not decode. They are authored from the region's surface landmarks, its
  intact region board, and the asset pack's piece names.
* **Names are placeholders**, as the region's are.

## Small rooms

Three more sections joined the `ssarathi_royal_archive` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Ssarathi Ruins
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `water_gate_undercut` | the water-gate undercut | cave | `water-gate-undercut-mouth` | a saltmarsh crocodile's den under the south gate |
| `lineage_house` | the lineage house | cottage | `lineage-house-door` | a workshop at the serpent gate |
| `tenth_mouth` | the Tenth Mouth | shrine | `tenth-mouth-door` | a water shrine off the lily court |
