# Sunmane Steppe validation report

Every result below was produced in this workspace against the committed
artefacts. Commands are in `README.md`. The region now includes the desert,
badland and mountain ground north and east of the grassland and two cave
interiors, and every check was re-run against that content.

## glTF 2.0 conformance

Khronos glTF-Validator 2.0.0-dev.3.10, the same version the Four Gates package
records.

| Package | Errors | Warnings | Infos |
|---|---:|---:|---:|
| `world.glb` | 0 | 0 | 12 |
| `world-lod2.glb` | 0 | 0 | 12 |
| `../interiors/sunmane_wind_caves/world.glb` | 0 | 0 | 1 |
| `../interiors/sunmane_crystal_hollow/world.glb` | 0 | 0 | 0 |

The twelve infos in each surface package are `NODE_EMPTY`, one per lighting
marker node. Those nodes are intentional: they carry the warm landmark and
transition light positions as named transforms rather than a glTF light
extension, so the package needs no loader change and depends on no extension
the client does not implement. The single info in the Wind Caves package is an
unused `TEXCOORD_0` on the still pool's water surface, which has no texture.
Full reports are committed beside each GLB as `*.glb.validator.json`.

Independent structural verification, separate from the Khronos tool and from
Godot, is in `maps/nymara-regions/sunmane_steppe/source/validate_package.py`: it parses the GLB container
and JSON chunk itself and checks self-containment, node-name uniqueness, that
every declared collision and landmark node actually exists, the coordinate and
minimap transforms, server-tile addressability, and the landmark counts the
written region description specifies. **735 of 735 checks pass.**

## Client tests

Run with Godot 4.7.2 - the version `godot-client/project.godot` pins. The
physics tests run headless; the render and minimap passes need a real GL
context and run under `xvfb` with the `gl_compatibility` renderer.

| Test | Result |
|---|---|
| `sunmane_grounding.gd` | PASS |
| `sunmane_traversal.gd` | PASS |
| `sunmane_caves.gd` (new) | PASS |
| `rendered_sunmane_steppe.gd` | PASS |
| `sunmane_caves_rendered.gd` (new) | PASS |
| `sunmane_minimap.gd` | PASS |
| `sunmane_performance.gd` | PASS |
| `test_protocol.gd` (existing) | PASS |
| `test_world_input.gd` (existing) | PASS |
| `test_native_glb_assets.py` (existing) | PASS |

### Grounding

`sunmane_grounding.gd` loads the package through the real `WorldLoader`, then
raycasts the navigation-surface layer exactly as `main.gd` does when it places
an actor.

- Navigation-surface bodies created: 102 (100 terrain chunks, the edge apron and
  the crossroads plaza).
- Arrival datum `(58, 58)` grounds at y = 9.71.
- All three surface portal approaches ground: west `(6, 58)`, east `(110, 58)`,
  north `(58, 100)`.
- **2809 of 2809 sampled columns ground successfully - zero misses** across the
  whole addressable band on a 4 m grid, over a ground range of -20.50 m to
  35.76 m, so no position exists where an actor would fall through to the
  manifest fallback height.

This test caught two real defects during the original build, both since fixed:
terrain quads wound clockwise from above, which made the ground simultaneously
invisible and transparent to the grounding ray, and an 18-column gap on the
exact map boundary line.

### Traversal

`sunmane_traversal.gd` exercises the client-side half of gameplay against the
package. Movement authorisation and map transitions belong to the server and are
not exercised; everything the client itself computes is.

- Server tile to world position and back round-trips exactly for every sampled
  tile, and the arrival datum maps to the world origin.
- Click-to-move picking - a camera ray into the navigation layer, converted to a
  server tile exactly as `main.gd` does - succeeds at all 14 representative
  locations, and every picked point converts to an on-map tile.
- The camera stays above its focus ground across all 100 combinations of the
  isometric rig's pitch, yaw and zoom range.
- All 139 declared collision nodes produced bodies, and all 14 probed structures
  stop a player-sized body as their form implies.
- The world edge is raised rim, mountain or open water on 95 of 96 perimeter
  samples.
- All three portal approaches ground with standing headroom.
- Every server tile maps inside the minimap image, and the declared pixel
  transform maps the declared bounds onto the image on both axes.

This test found five real defects, all since fixed:

1. The west and east caravanserais stood exactly on their portal tiles, so an
   arriving player would have materialised inside the building.
2. The cove landing, two outposts, two satellite camps, an outlying pen and
   several resource and population records sat outside the addressable tile
   band - addresses the server cannot express, so a player could never have
   walked to them.
3. A herd and a boar spawn were likewise outside that band.
4. **The structural-collision probe was measuring the wrong thing.** It fanned
   infinitely thin rays through each structure, which thread between a lookout
   tower's splayed legs and report missing collision where a player would in
   fact be stopped; whether a given tower passed came down to whether its
   rotation happened to align a leg with one of twelve ray directions. It now
   sweeps a player-sized capsule - the same volume the character controller
   moves - straight through each structure at two heights, and every structure
   including the open frames stops it.
5. **The Wind Caves entrance was outside the addressable band**, at Godot
   Z -150 against a limit of -133. A portal a player cannot walk to is not a
   portal. It now sits in the south face of the eastern butte at Godot
   `(70, -117)`, server tile `(128, 175)`, a few metres off the desert road.
   The builder now refuses outright to emit an interaction on an unreachable
   landmark, and the package validator asserts the same rule.

### Cave interiors

`sunmane_caves.gd` loads both interior packages through the real `WorldLoader`
and checks that a player can stand, walk and be contained in them.

- Every chamber is floored throughout its sampled area, and every chamber has
  standing headroom over at least three quarters of it - props, formations and
  camp furniture legitimately occupy the rest.
- Every spawn point and light marker sits over the cavern floor.
- All declared collision nodes produced bodies: 116 in the Wind Caves, 134 in
  the Crystal Hollow.
- **Containment**: from each spawn, a player-sized body is walked outward in 24
  directions in 0.35 m steps, dropping to the floor at each step exactly as the
  character controller does, and stopping when the rock leaves it no room. No
  walk reaches the declared bounds in either interior.
- Both exit portals are reachable ground with standing headroom and declare
  their destination map.

The containment check first ran as a straight capsule sweep at constant height
and reported one escape from the Crystal Hollow's geode chamber. That was the
test's fault, not the map's: the floor falls away past the chamber rim, so a
body held at a fixed height sails over rock the roof has already pinched down
to 0.14 m. Walking the body along the floor is what a player actually does, and
it is contained.

### Rendered views

`rendered_sunmane_steppe.gd` loads the package through the client's world
loader, applies the manifest environment through `WorldEnvironmentBinder`,
spawns the ambient livestock through `AmbientPopulation`, then captures 32
framings plus 7 golden-hour variants - the original 21 plus eleven covering the
dune field, the salt pans, the desert stations and camps, the waystone road, the
badland spires, both cave mouths, the Whitehorn front, the eastern watch and the
eastern pass. `sunmane_caves_rendered.gd` does the same for the two interiors,
binding their brazier and crystal lights through the new `LightMarkerBinder`,
and captures an eye-level view in each of their ten chambers. Framings come from
`camera-views.json` and from the interiors' own chamber list, so each is a view
a player can reach in game. Each capture is asserted to be the reference
resolution and to contain enough distinct sampled colours to fail loudly on a
blank or single-material frame.

Three visible artefacts were found by looking at those captures and fixed:

1. **A trench around the whole map.** The heightfield's road smoothing and slope
   limiter used `np.roll`, which wraps: the northern edge was being averaged and
   slope-limited against the southern one, 38 m below it. The result was a
   drowned rim on all four sides - the mountain boundary that is supposed to
   close the world was cut down into sea. Neighbour lookups now replicate the
   edge instead of wrapping, and the north and east edges stand at +32 m and
   +45 m as intended.
2. **A chequerboard across every hillside.** Quads were switching between two
   shading and UV treatments on a relief threshold, and on a slope the relief
   per quad hovers around that threshold, so neighbouring quads alternated and
   the ground read as a chequerboard of light and dark tiles. The decision is
   now made from the quad's own normal - face-projected texture past about 63
   degrees, faceted shading only where the smoothed normal genuinely opposes the
   face - and the alternation is gone.
3. **Measles on the cave rock.** The surface `stone` family carries worley
   pitting, which over a chamber floor tens of metres across repeats into a
   spotted pattern. Cave surfaces now use a purpose-authored `cavern` family:
   damp mottling and flowstone drapery, no pitting.

### Minimap

`sunmane_minimap.gd` renders orthographically from the exported geometry into a
1024 x 1024 SubViewport. The manifest records `pixelsPerMetre = 3.657143` and an
explicit pixel transform per axis, because the region is no longer centred on
the world origin: it spans Godot X -104..176 and Z -176..104 around a centre at
`(36, -36)`. Each interior renders its own 512 x 512 minimap with its roof
hidden, the way a floor plan omits a ceiling.

## Geometry integrity

`maps/nymara-regions/sunmane_steppe/source/checks.py` runs inside the builder and fails the build on
malformed geometry. Every emitted primitive is checked for triangles wound
against their vertex normals, degenerate triangles, non-finite positions or
UVs, and non-unit normals; closed kit solids are additionally checked for
positive signed volume, which catches inside-out geometry that a winding check
alone cannot see. The current build of all four packages emits zero of any of
these.

Two defects in the new content were caught by these gates before they ever
reached the client: the badland spires folded the heightfield when they were
sculpted into it at two cells wide, and the cave-mouth throat had 31 triangles
facing the wrong way where its floor, back wall and face ring disagreed with
their declared normals.

## What is not verified here

- **No live server session.** `eloria-server` is not reachable from this
  workspace, so the real login flow, protocol round-trip and server-side
  walkability were not exercised. Everything the client does with the package -
  manifest parse, GLB import, collision build, grounding raycast, environment
  binding, light-marker binding, ambient population, minimap - was exercised
  directly. See `server-integration.md`.
- **No GPU.** All rendering was Mesa llvmpipe software rasterisation. Frame
  times are therefore not player frame rates; see `performance-summary.md`.
- **Map transitions are declared, not executed.** Both sides of each cave portal
  are authored and registered, but a transition is a server decision, so the
  actual hop between the steppe and an interior has not been performed.
