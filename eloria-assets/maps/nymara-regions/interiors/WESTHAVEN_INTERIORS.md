# Westhaven insides

Four interiors on **one map** with blackspace between them, in the Eternal Lands
convention: one GLB, one manifest, one collision grid, one server map key, and a
separate arrival point per surface door.

Package: `interiors/westhaven_insides/`
Server map key: `westhaven_insides` → `maps/nymara/westhaven_insides.elm`

| section | name | class | surface door | offset on the map | arrival | server tile |
|---|---|---|---|---|---|---|
| `custom_house` | The Custom House | civic | `custom-house-door` | (40, 30) | (40, 0.05, 30) | (35, 235) |
| `bonded_vaults` | The Bonded Vaults | stores | `bonded-vaults-door` | (150, 30) | (150, 0.05, 29) | (145, 236) |
| `gullstone_cave` | The Gullstone Undertow | cave | `gullstone-door` | (40, 170) | (40, 0.05, 170) | (35, 95) |
| `lamp_rock_light` | The Lamp Rock Light | tower | `lamp-rock-door` | (160, 170) | (160, 0.05, 170) | (155, 95) |

Combined: 51,432 triangles, 9.79 MB, collision 360 × 492 at 0.5 m. The map spans
x 7.5…201.3 and z 21.5…262.6, which fits a 64 × 64 tile server map with a margin
on every side.

## The blackspace

It is not drawn and it is not masked. The collision grid is built only where a
`Walk_` surface exists, so the gutters between sections are blocked by
construction — there is nothing there to render and nothing there to stand on.
That is why the combined map reports **17.9% walkable**: the other 82% is the
rock and masonry around each section and the void between them, which is the
whole point.

Sections are laid out two by two rather than in a row. Four sections in a line
span 350 m of x, which overflows the 384 m of a 64-tile map once the margin a
server map wants is allowed for. The closest pair is 45 m apart and the rest
further, which is what keeps one section's lamps and cameras out of the next.

## Why four different kinds of place

A region whose interiors are all the same room with different props has no
interiors. These are built from four deliberately disjoint material sets:

**The Custom House** — dressed ashlar, polished oak, brass and glass. The only
warm, orderly, occupied one. Organised around what actually happens to a cargo:
you come in at the tide board and the public counter, the ledger office runs
east with clerks' desks down both sides, the weighing floor is tall enough to
swing a beam scale with graded weights beside it, and what cannot be released
sits in the strongroom behind an iron door until the duty is paid. A records
loft over the office, up a stair.

**The Bonded Vaults** — the counterweight. The same cargo three metres lower and
without the paperwork: brick barrel vaults cut into the terrace riser under the
warehouse row, casks stacked to the springing, a windlass over an open shaft up
to the warehouse floor above, one tallyman's bench and brazier, and a sump at
the seaward end where the tide gets in through a grating and stands half a metre
deep over the shingle. No dressed stone, no brass, no daylight.

**The Lamp Rock Light** — stone, iron and glass, and almost nothing else. A
climb: the entry stage at the tower's foot, the year's oil on stillages, a stair
worked through the rock to a landing with a window slot, the watch room with its
chart table and stove, the lantern room with the burner and a Fresnel lens built
as stacked annular rings, and the gallery outside it, open to the sky.

**The Gullstone Undertow** — no dressed stone and no straight line except a
boat's keel and one timber staging. A cleft down from the watch tower into a sea
cave with a tidal pool over half its floor, a shingle beach inside it with two
boats drawn up and a fire, a smugglers' ledge holding what the Custom House
never saw, and a blowhole open to the sky that the sea breathes through.
Boulders are placed on a radial falloff from the walked centre line, so the rock
is dense at the walls and thin where the route runs.

## The tower is unfolded, on purpose

A real tower stacks its rooms one above another. The server's collision grid is
2-D — a cell carries one height, so an overhead deck owns its footprint and the
floor beneath it is not separately walkable. Stacking the Lamp Rock Light's five
spaces would make four of them unreachable.

So the climb is laid out in plan as well as in section: the lower spaces are cut
into the rock the tower stands on, and the stair works north through that rock
before rising into the tower head. The fiction holds — Lamp Rock is a stack of
stone with the light built on top of it — and every space is reachable. The cost
is that the tower you see from outside is not geometrically the tower you climb
inside. **No two spaces overlap in plan in any of the four sections**, and that
is the rule the whole layout is checked against.

## Building it

```sh
cd ../westhaven/source
python build_westhaven.py                 # the region, including its four doors
python build_interiors.py                 # the combined insides map
python preview_interior.py insides ../../interiors/westhaven_insides/references/00-checkpoint-contact-sheet.png \
       --captures ../../interiors/westhaven_insides/references/captures --cols 6
python export_insides_collision.py              # the server walk grid, from the package's own collision.bin
NYMARA_REGION_PACKAGE=../../interiors/westhaven_insides \
       python ../../_toolkit/verify_runtime.py --package ../../interiors/westhaven_insides
```

**The region must be built first.** `build_interiors.py` takes every surface
anchor from the region's finished `world.json` rather than from a constant, so
the entrance a section claims is the door the region actually built. Otherwise
the two drift the first time a door is nudged onto a walkable cell, and the
interiors go on claiming an entrance that has moved.

`interiors.py` still builds each section on its own for iteration —
`preview_interior.py custom_house …` works — and `combine()` assembles them.

## The round trip

Every one of the region's four doors targets `westhaven_insides` and differs
only in `destinationSpawn`. Each arrival on the insides map carries a return
portal back to the door it came in by, and the region carries a spawn of the
same name so the return has somewhere to land. Both directions resolve, and all
eight coordinates were checked against the exported ELM and are walkable.

The region build now checks every spawn and portal against the finished
collision grid and nudges any that landed on a blocked cell onto the nearest
walkable one, reporting the distance — a landmark that collides blocks its own
footprint, and a doorway is attached to the landmark. It moved six: the Custom
House door and its return spawn 3.15 m, the Gullstone door and its return spawn
3.14 m, and — found by the same check — two portals that were already shipped
in the region PR, the Grey Moors road by 6.67 m and the Crownwater berth by
16.41 m.

The Lamp Rock door anchors on `lighthouse_yard`, not `lighthouse`: the tower's
gallery is a walk surface 28 m up, so a door on the tower's own centre has the
grounding ray snap it onto the gallery instead of the rock.

## Server side

On `feature/westhaven-insides-server-map` in `eloria-server`: `maps.txt` gains
`westhaven_insides` and four bidirectional portal pairs, the generator builds it
at 64 tiles with the arrival at (35, 235), and the invasion spawn table gains
twenty groups sited inside the four sections rather than on the shared interior
point grid, which on this map is void.

Every tile in the portal table is derived from the two packages' own manifests
by `export_insides_collision.py` rather than counted by hand.

## Verification

```
validate_gltf    0 errors, 0 warnings
verify_runtime   0 errors, 1 warning
```

The warning is `GROUNDING_RAY_MISS` over 86.8% of sampled tiles. On a combined
insides map that is expected, and it is the blackspace being measured: the
harness samples the whole square footprint and most of this map is deliberately
void.

### In the real engine

```
Godot_v4.7.2-stable_win64_console.exe --path . --headless   --script _toolkit/region_client_check.gd -- --manifest=<...>/world.json --step=2

[client-check] interior package: 40 authored spaces, tiles outside them are expected void
[client-check] inside authored spaces: 1216 sampled, 0 misses
[client-check] grounding: 8100 tiles sampled, 6865 misses (84.75%)
[client-check] spawn default              deltaMetres 0.05
[client-check] spawn custom-house-hall    deltaMetres 0.05
[client-check] spawn bonded-vaults-tunnel deltaMetres 0.05
[client-check] spawn lamp-rock-foot       deltaMetres 0.05
[client-check] spawn gullstone-cleft      deltaMetres 0.05
[client-check] PASS
```

`region_client_check.gd` gained an interior criterion for this. "Every tile must
ground" is right for a region and wrong for a combined insides map - it reports
85% misses and fails a map that is correct. When the manifest declares `spaces`,
which only an interior package does, the test becomes **every tile inside an
authored space must ground**, and the void outside them is reported rather than
failed. 1,216 tiles inside the forty authored spaces, none missing.

`references/client-captures/` holds 21 **real Godot client frames**, drawn
through the project's own `WorldLoader` on Vulkan/Forward+.
`references/captures/` holds the offline previews from the same camera table.

`godot_capture.gd` gained two things for this too: it binds the manifest's own
`lights` array - forty lanterns, braziers and burners here - because a sealed
map lit only by the harness's lifted ambient comes back near black, which is
exactly what the first run produced; and it accepts the interior index's `fov`
field alongside the region index's `fieldOfViewDegrees`, or every interior frame
is taken at the 55-degree default instead of its authored framing.

### Lighting the cave

A lamp entry is `[x, y, z]` or `[x, y, z, range, energy]`. The defaults - 9 m of
throw at energy 1.5 - suit a room and are useless in a chamber 52 m across: the
Gullstone Undertow's first client frames averaged 12 to 15 out of 255, and
adding six more lamps at the default range moved that by 0.1. With the reach
declared (22 to 26 m through the cavern, less on the beach and the ledge) the
four cave frames come back at 22 to 37, which is dark - it is a smugglers' cave
lit by lanterns - and legible. The other three sections keep the defaults.

## What is not verified

- **Nothing has been played.** Collision response, navmesh generation, portal
  transitions and transparency sorting are unverified. The client frames prove
  the map loads and renders through the real `WorldLoader`; they do not prove an
  actor can walk it, or that a portal fires.
- **Client and server have never been run together.**
- **One environment for four places.** A combined map has one ambient and one
  fog. The lighthouse gallery and the cave's blowhole are genuinely open to the
  region's sky and stay declared in `openToSky`, but the map as a whole is lit
  as sealed, so neither will currently show sky. Per-space environments are a
  client change nobody has needed yet.
- **The blackspace is client-side only.** `validate_generated_map` rejects any
  exterior or interior ELM containing a zero height, and a zero is what blocked
  means, so the generated server map is flat and fully walkable and a player is
  not stopped from crossing the void server-side. This is exactly the situation
  the Amethyst Barrens insides are already in. The authored map with real
  blackspace is exported to `server-collision/westhaven_insides.bin` and is ready if
  that guard is ever given a per-map opt-out.
- **These interiors have no concept art of their own.** The region's ten-panel
  board covers the exterior; the four sections are authored from it and from the
  region's surface landmarks.
- **Place names are the author's throughout.**

## Small rooms

Three more sections joined the `westhaven_insides` map from the shared
`_toolkit/amberwood/smallrooms.py` kit, each with its own door on the Westhaven
map and its own arrival: a cave with a creature den, a cottage and a shrine.
They sit in a column east of the set pieces with the usual void between.

| section | name | kind | region door | what it is |
|---|---|---|---|---|
| `salvage_hole` | the salvage hole | cave | `salvage-hole-mouth` | a bronze tide crab's den under the east watch |
| `gullscar_farmhouse` | Gullscar farmhouse | cottage | `gullscar-farmhouse-door` | the upland farm's house |
| `haven_undercroft` | the haven undercroft | shrine | `haven-undercroft-door` | a lantern shrine over a crypt |
