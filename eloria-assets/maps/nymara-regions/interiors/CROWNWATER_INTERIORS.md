# Crownwater interiors

Crownwater's four insides share **one map with unwalkable blackspace between
them**, the way Eternal Lands lays out a region's interiors, and the way
`amethyst_barrens_insides` already does in this repository. One package, one
GLB, one collision grid, four sections, one spawn and one exit portal each.

Package: `interiors/crownwater_insides/`. Server map: `drowned_crown.elm`.

| section | name | class | walkable cells | surface anchor |
|---|---|---|---:|---|
| `drowned_crown` | The Drowned Crown | dungeon | 17,100 | `crownwater-cathedral` |
| `tide_cistern` | The Tide Cistern | utility | 11,784 | `crownwater-pavilion-pavilion_west` |
| `customs_hall` | The Harbour Customs Hall | settlement | 9,304 | `crownwater-customs-hall` |
| `tide_campanile` | The Tide Campanile | tower | 536 | `crownwater-campanile` |

76,526 triangles, 9.98 MB, 600 × 570 half-metre collision cells of which
**11.3% are walkable** — the rest is the blackspace between sections and the
rock around each.

## Layout

```
z=334  +----------------+                +--------------+
       | customs hall   |                |              |
z=251  +----------------+   blackspace   |              |
                                         |              |
z=179  +-------------------+             +--------------+
       | drowned crown     |             | tide cistern |
z=  7  +-------------------+             +--------------+
         x=9         x=170                x=234    x=304

  the campanile stands alone at x 55-65, z 295-305
```

The closest approach between any two sections is 60 m — far beyond the reach of
any lamp, any grounding ray, or the collision grid.

**The blackspace costs nothing to build.** `build_collision` marks a cell
walkable only where a `Walk_` surface actually covers it, so every cell between
the sections is already zero, which is exactly what "blocked" means in EWCG v1
and what the server reads as void. The gaps are not drawn; they are the absence
of floor.

## Why these four

Crownwater is a city on water, so its insides are about water: what lies under
it, what holds it back, and what floats on it. Each section takes a different
answer, so no two are the same room with different textures.

**The Drowned Crown** is the water winning — an older palace the basilica was
built on top of, now half flooded. The only section whose programme was *given*
rather than invented: `drowned_crown/concept.json` lists flooded vestibule,
water galleries, submerged arch, shell altar, statue court, water channel,
collapsed dome, air pocket and objective hall, and every one is a space. The
water line is held flat at y = −6.05 and the floors step down beneath it, so the
wading deepens as you go in until the collapsed dome lets the light back.

**The Tide Cistern** is water put to use: a hundred columns standing in a hand's
depth of fresh water under the garden islet, lit by oculi down from the plaza,
with a brass sluice gear that lets the basin down to the lagoon. A raised walk
crosses it so the room is traversable rather than only wadeable.

**The Harbour Customs Hall** is the only one with a job — ledger hall, mezzanine
office, bonded store stacked to the trusses, a strongroom, and a water gate
where a lighter comes in *under* the building. Mundane on purpose: three
monuments in a row would make Crownwater a museum rather than a place people
work.

**The Tide Campanile** is the one dry, bright, vertical space — a hollow 26 m
shaft with a switchback stair, a ringing floor and an open belfry.

## Building it

```sh
cd ../crownwater/source
python build_insides.py                                  # the one map
python verify_interiors.py --report ../interiors-verification.json
python export_insides_collision.py                             # the server walk grid
```

`build_interiors.py` still builds the four as **separate** packages and is kept
for working on one section in isolation; `build_insides.py` is what ships.
Deterministic for a given seed. Nothing in `_toolkit/` is modified.

Real client frames (needs a Godot 4.7.2 binary and a display):

```sh
ELORIA_ARTIFACT_DIR=<dir> godot --audio-driver Dummy \
  --rendering-method gl_compatibility --path godot-client \
  --script res://tests/integration/rendered_crownwater_interiors.gd
```

## Verification

`verify_interiors.py` rather than the region's `verify_runtime.py`, and the
difference matters more on a blackspace map than anywhere else. The region tool
casts the grounding ray at every tile of the bounding box and calls a floorless
tile a miss — on this map **89% of the tiles are deliberately floorless**, so it
would report a catastrophe.

The contract that actually holds here is narrower and stricter: *every cell the
collision grid calls walkable must have a walk surface under it.*

| check | result |
|---|---|
| Walkable cells | 38,724 |
| Walkable cells with no surface under them | **0** |
| Collision height disagreements | **0** |
| Spawn and portal grounding problems | **0** |
| glTF validator | **0 errors** |
| In-client | loads through the real `WorldLoader`; 23 frames captured |

Per-section counts are reported separately, so a section that lost its floor
entirely is visible rather than averaged away across a map that is mostly void.

Everything in `references/captures/` is a **real Godot client frame**, not an
offline preview.

## Three client-contract defects this found

None were visible to the offline tools. All three appeared only on rendering
through the client's own code path, and **all three affect Amberwood's interiors
too, where they are not fixed.**

### 1. Manifest lights are read from `environment.lights`, keyed `color`

`WorldEnvironmentBinder._apply_lights` reads
`manifest.data["environment"]["lights"]` and `entry["color"]`.
`build_interiors.py` — inherited from Amberwood's — emitted a **top-level**
`lights` array keyed `colour`. The binder never looks there, so an interior lit
only by a directional sun it has a ceiling against renders black.

**Amberwood's four interiors still emit 27 lights the binder cannot see.**

The capture harness now asserts a non-zero light count, so this cannot regress
silently.

### 2. Placement is single-layer, so no deck may span a tower's footprint

The client places an actor on the **first** surface a ray from y = 400 meets.
The campanile's ringing floor and belfry gallery originally spanned the full
10 m footprint, so every placement in the tower — including its arrival spawn —
grounded 26 m up on the belfry.

Both decks are now **annular**, leaving a well down the middle where a campanile
hangs its bell anyway. A player can still *walk* the stair normally; only
placement is single-layer. The rule this leaves: **no spawn or portal may sit
beneath a deck.**

### 3. `hanging_lamps` returns a pair, and lamp positions are `[x, y, z]`

`hanging_lamps(points)` returns `(mesh, positions)` and takes `(x, y, z)`.
Hand-built entries written `[x, z, y]` lit a point 27 m above the cistern basin
instead of 3 m above it — silent, because a light in the wrong place is still a
valid light.

## Where it attaches

Four `interior-entrance` portals on the Crownwater region manifest, each on the
landmark it belongs to, all pointing at `maps/nymara/drowned_crown.elm` and
choosing their section by spawn id. The package carries the four matching return
portals. Registered in `godot-client/data/maps/registry.json` with
`"interiorOf"` and `"insidesOf"` set to `maps/nymara/crownwater.elm`.

| door | on Crownwater | arrives at | section |
|---|---|---|---|
| `basilica-undercroft` | tile (288, 306) | tile (43, 277) | drowned crown |
| `cistern-stair` | tile (126, 288) | tile (253, 277) | tide cistern |
| `customs-door` | tile (196, 176) | tile (243, 76) | customs hall |
| `campanile-door` | tile (336, 324) | tile (53, 37) | tide campanile |

Two region changes were needed to give two of them a door:

* **The cathedral was renamed** from "The Drowned Crown" to **"The Crown
  Basilica"**. The interior beneath it is the drowned palace it was built over,
  and two things could not carry the same name.
* **A customs house was added** to the harbour islet — the region had no
  building there at all, only quays and stalls.

## The contested portal, now resolved

`drowned_crown/concept.json` has always declared `parentRegion: crownwater`,
while `eloria-server`'s `config/eloria/maps.txt` linked the map to `mirrorhold`.
The Mirrorhold session and I each declined to change it on our own authority.

The map's owner has since assigned Crownwater's insides to this session, so the
single `mirrorhold ↔ drowned_crown` pair is replaced by the four
`crownwater ↔ drowned_crown` pairs above and the server map's title becomes
"Crownwater Insides". Mirrorhold now has no interior connection; if it wants one
it needs its own.

## Known limitations

* **One environment block serves four sections of different character.** A
  drowned ruin and a working warehouse want different light. The per-section
  lamps carry most of the difference, but this is a genuine compromise of the
  single-map layout rather than a choice.
* **`drowned_crown`'s own detail board is truncated** (786,446 bytes — the same
  defect as fifteen of the seventeen region boards), so there is no panel
  comparison for it. Its ten subjects were worked from `concept.json`'s written
  list, and every one is built.
* **No server has loaded the ELM.** It is exported from the package's own
  collision grid and its header is verified (64 × 64 tiles, 384 × 384 cells),
  but end-to-end play was not exercised.
* **Names are placeholders**, as the region's are.
* **Lighting is judged by eye.** The sections are readable in client frames, but
  "dark enough to be atmospheric" versus "too dark to play" is not something
  these captures settle.

## Small rooms

Three more sections joined the `drowned_crown` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Crownwater
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `the_grating` | the Grating | cave | `grating-mouth` | an abyssal armoured fish's den under the open grating |
| `case_room` | the case room | cottage | `case-room-door` | a chandlery |
| `eleventh_bell` | the Eleventh Bell | shrine | `eleventh-bell-door` | a lantern shrine |
