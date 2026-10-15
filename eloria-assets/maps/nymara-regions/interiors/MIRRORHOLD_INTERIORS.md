# Mirrorhold interiors

Three interiors on **one map**, in the Eternal Lands manner: separate blocks of
rooms on a single square map with unreachable ground between them, entered at
three different arrivals rather than through three map files.

Built by `mirrorhold/source/build_interiors.py` from
`mirrorhold/source/interiors_mirrorhold.py`, on the shared interiors toolkit.

Map: `mirrorhold_interiors`, 204 m square (34 ELM tiles), 12.3% walkable.

| block | name | entered from | arrival spawn |
| --- | --- | --- | --- |
| `lens-vault` | The Lens Vault | the orrery drum, summit | `lens-vault-stair` |
| `cistern` | The Mirror Cistern | the fountain plaza | `cistern-door` |
| `cellars` | The Stair Cellars | the cliff town | `stair-cellars-door` |

`references/plan.png` renders the collision grid: three blocks, black between
them, and an empty fourth quarter where a later interior goes without moving
anything already placed.

## Why one map

Two constraints decide the shape. The server's `validate_generated_map`
requires `width == height`, and a map is a whole number of six-metre ELM tiles.
The first layout put the blocks in a row - 296 x 56 m - which is neither, and
could never have been served. They are now placed on a grid and the map squared
up to the next tile boundary.

The gaps carry no geometry at all, so the collision grid reads 0 there: the
space between blocks is unreachable by construction rather than merely unlit.

## Why these three

The region is an observatory of mirrors on a glacier mountain. Each interior
explains something the exterior only asserts:

**The Lens Vault** is where the mirrors are made, so the instrument on the
summit has a workshop under it. Its plan is a working sequence rather than a
loop — grind, anneal, then test against the still pool in the well. The
instrument of record is a *liquid* mirror: a shaft over black water, which is
a real technique and the literal reading of the region's name.

**The Mirror Cistern** is the waterworks. Glacier meltwater arrives loaded with
rock flour — which is what makes the lake turquoise and what would ruin a
reflecting basin — so it is dropped through a settling basin, filter beds, and
finally a stilling floor wide and shallow enough to go glass-flat. It explains
both the terrace pools and the colour of the lake in one room.

**The Stair Cellars** are the lived-in counterweight: rubble instead of dressed
stone, glacier ice bedded in sawdust, a niche shrine, and a long stair down to
a barred water gate the citadel would rather not inventory.

## Areas

| interior | areas |
| --- | --- |
| Lens Vault | stairhead, sighting floor (meridian line, oculus), grinding room (laps, blank racks, drive shaft), annealing room (ice-lined), mirror well (liquid mirror, -7.2 m), chart aisle |
| Mirror Cistern | sluice hall (gates), settling basin (baffles, spoil), stilling floor (walkway, columns in water), filter racks, pump gallery |
| Stair Cellars | cellar head, common cellar, cold larder (ice store), rock shrine, water gate (-8.4 m, boat) |

Sixteen rooms and nine connecting passages in total.

## Verification

The package carries `world.glb`, `world.json`, `collision.bin`, its validator
report, `client-check-report.json` and `references/plan.png`.

| | value |
| --- | --- |
| triangles | 26,030 |
| GLB | 7.01 MB |
| collision grid | 408 x 408 cells at 0.5 m, square |
| walkable cells | 20,460 (12.3%) |
| validator | 0 errors |
| in-engine | PASS - 166,464 cells sampled, 20,460 walkable, **0 with no surface** |
| arrivals | all four within 0.05 m of their manifest height |

The in-engine column is `_toolkit/region_client_check.gd`: Godot loads the
package through the project's own `WorldLoader` and casts `main.gd`'s grounding
ray at **every** cell the collision grid marks walkable. Zero cells lack a
surface, and all four arrivals land within 0.05 m of their manifest height.

That check was extended for this work. Its previous pass condition — every tile
in the bounding box must have floor — is right for a region, whose terrain
covers everything, and wrong for an interior, which is rooms inside solid rock
and whose box is mostly *meant* to have no floor. It now tests the contract
that holds for both: every cell the collision grid calls walkable must have a
surface under it. Re-run against both regions afterwards, which still pass.

## Captures

`references/godot-captures/`: real Godot 4.7.2 frames on a Vulkan device, one
per area across all three blocks, generated from the manifest's own space list
by `_toolkit/interior_views.py` rather than maintained by hand.

The plan is `references/plan.png`, rendered from the collision grid by
`_toolkit/plan_image.py`, not from a camera. A top-down 3D shot of a lidded map
photographs its ceilings and comes back black; the grid is what a plan of an
interior actually wants to show.

The capture harness now honours what a package declares — `sky: "none"`, the
ambient and fog block, and the point lights standing in its lamps — instead of
lighting every package with an outdoor sun. An interior lit as though it were
outdoors is not a picture of anything that will exist.

## Known gaps

- **No concept art.** These three are inventions: the repository has interior
  concept packages for `drowned_crown` and `resonant_vault`, but neither is
  Mirrorhold's (see below), and there is no board for these. Nothing here was
  compared against concept art because there is none to compare against.
- **Names are placeholders**, as everywhere else in this region.
- **Server entries are in place** on `feature/mirrorhold-576m-server-map`:
  `mirrorhold_interiors` at 34 tiles with three portal pairs, generator sizes,
  arrival tiles and the content manifest. Both maps generate square at the
  expected dimensions and the four content tests pass.
- **Lighting is declared, not baked.** The manifests carry point lights; there
  are no lightmaps.

## The two interiors that are not Mirrorhold's

`drowned_crown` and `resonant_vault` both had entrances from Mirrorhold in an
earlier pass of this region. Both were wrong, in different ways:

- **`resonant_vault`** declares `parentRegion: amethyst_barrens` and the server
  links it to `four_gates`. Mirrorhold had no claim on it at all; the portal
  was mine and has been removed.
- **`drowned_crown`** declares `parentRegion: crownwater`, but
  `config/eloria/maps.txt` has linked it to `mirrorhold` since before any of
  this work:

  ```
  portal | mirrorhold | 58 | 100 | drowned_crown | 58 | 12
  portal | drowned_crown | 58 | 10 | mirrorhold | 58 | 98
  ```

  The user has settled it: **`drowned_crown` is Crownwater's.** Mirrorhold's
  manifest portal to it is removed, and this branch's 576-scale portal pair in
  `config/eloria/maps.txt` with it. The pre-existing 192-scale pair is left
  alone - it predates all of this work and belongs to whoever repoints it,
  which is the Crownwater session, not this change.
