# Sunmane Steppe interiors

Sunmane's two cave systems now share **one map with unwalkable blackspace
between them**, the way Eternal Lands lays out a region's interiors, and the way
`amethyst_barrens_insides`, `crownwater_insides` and `ssarathi_insides` already
do in this repository. One package, one GLB, one collision grid, two sections,
one spawn and one exit portal each.

Package: `interiors/sunmane_insides/`. Routed - see below.

| section | name | class | walkable cells | surface door on the steppe |
|---|---|---|---:|---|
| `sunmane_wind_caves` | Sunmane Wind Caves | cave | 2,118 | server `(128, 175)`, south face of the eastern butte |
| `sunmane_crystal_hollow` | Amethyst Crystal Hollow | cave | 2,291 | server `(182, 154)`, Amethyst badland |

6.61 MB, 384 × 384 half-metre collision cells of which **4,409 are walkable** —
the rest is the rock around each system and the 82 m of nothing between them.

## Nothing was re-authored

This is a layout change, not an art one. Both systems keep the specs, the
clearance field, the shell generator, the props, the braziers and the light
markers they already shipped as separate packages. `caves.Shell` gained a
movable sample centre so a system can be built somewhere other than the origin;
`insides.py` builds both into one `Builder` and writes one package.

`caves.py` still produces the two standalone packages and they are kept: they
are what you want when iterating on one system, exactly as
`crownwater/source/build_interiors.py` was kept alongside its
`build_insides.py`. Their *output* does change once, because of defect 1 below.

## Layout

```
z=-15  +----------------+                    +------------------+
       |  wind caves    |                    | crystal hollow   |
       |  60 x 60       |       82 m         | 60 x 60          |
z=-75  +----------------+                    +------------------+
         x=13     x=73                        x=139      x=199
```

Each system keeps its own 60 m sampling square; they sit 126 m apart centre to
centre. The shells taper well inside those squares, so the actual empty band
between any geometry of one and any of the other is **82 m**, measured off the
built GLB rather than assumed. The collision grid agrees: a 164-cell blocked
band separates the two occupied regions.

**The blackspace costs nothing to build.** The cavern floor only exists where a
system's clearance field is open, so there is no floor between the two systems
to stand on and nothing there to render. The gutter is not a wall; it is the
absence of cave.

## Verification

| check | result |
|---|---|
| `validate_gltf.py` | **0 errors, 0 warnings** |
| Godot 4.7.2, real `WorldLoader` | **PASS** — 8,815 of 9,216 sampled tiles miss and **every one is blackspace**: 0 misses on cells `collision.bin` marks walkable |
| Spawns | 3 / 3 grounded, within **0.005 m** |
| Determinism | byte-identical `world.glb` and `collision.bin` across repeat builds |
| Standalone packages | still build, and are now reproducible; regenerated once (defect 1) |

## Four defects this found

None were visible while each system was its own map.

### 1. The cave build was never reproducible

`caves.py` seeded from `abs(hash(spec["id"])) % 10_000`. Python salts `hash()`
on a str per process, so **two builds of identical code produced different
GLBs** — the two shipped cave packages could not be reproduced from their own
source. The production guide names this exact trap. Replaced with a CRC32-based
`stable_seed`, and verified: repeat builds are now identical, and pinning
`PYTHONHASHSEED` is no longer needed.

`settlement.py` has two more salted-hash seeds (lines 365 and 1075) that affect
the **region** build. Those are out of scope here and are still there.

### 2. Node names collided

Both systems number their boulders and stalactites from zero, so the combined
GLB failed the validator with 54 reused node names — and the client resolves
collision and navigation nodes by name. `Builder` gained a `name_suffix`, empty
by default.

**A suffix, not a prefix.** `navigation.surfaceNodePrefixes` matches the *start*
of a name, so tagging the front turned every `Terrain_CaveFloor_*` into
something the client did not recognise as a walk surface: the first attempt
built no navigation surface at all and grounded nothing on the entire map.

### 3. `Shell.axis` was read as a coordinate

`self.axis` served as both the x and the z axis while both were the symmetric
`-HALF_EXTENT..+HALF_EXTENT`. The moment a system moves, reading a z coordinate
out of the x axis places the whole cavern at the wrong end of the map — which is
exactly what happened. Now `axis_x` and `axis_z` are separate and `axis` is kept
only for its size.

### 4. The rim is not walkable, and the grid has to say so

The cavern tapers to a crawl space at its edge. Cells there have clearance and a
floor quad, so a naive grid called them walkable, and the in-engine check
reported a miss — a *different* single cell each time the mask was adjusted,
because it is a continuous rim rather than one hole. The grid now requires the
agent the manifest itself declares to fit: clearance ≥ `agentRadius` 0.55 and
headroom ≥ `agentHeight` 1.9. That took the in-engine result to zero misses.

## It is wired up

Both of the steppe's cave mouths now go to this package.

| door | on the steppe | arrives at | section |
|---|---|---|---|
| `wind-caves-mouth` | tile (128, 175) | tile (43, 27) | wind caves |
| `crystal-hollow-adit` | tile (182, 154) | tile (169, 28) | crystal hollow |

Arrival and exit share a tile, which is what the other combined insides maps
do (`drowned_crown`, `resonant_vault`, `ssarathi_royal_archive`): the package
puts each return portal in its own arrival chamber.

**`sunmane_crystal_hollow` is retired as a served map.** Sunmane was the first
region whose interiors were already *two* served server maps, so unlike
Crownwater's, Amethyst's and Ssarathi's absorbed rooms, combining them cost
something server-side. The hollow is now the eastern half of
`sunmane_wind_caves.elm`, which grows from 10 server tiles to 32.

| where | what changed |
|---|---|
| `config/eloria/maps.txt` | one map line, and four portal lines routing both doors to the one map |
| `tools/generate_nymara_maps.py` | interiors tuple, tile count, arrival tile |
| `tools/generate_nymara_invasion_spawns.py` | the hollow's groups spawn into the combined map, at points on it |
| `config/eloria/client_content_manifest.json` | one map entry with two `blocks` |
| `Dockerfile` | the retired ELM is no longer asserted into the image |
| five test files | connections, sizes, arrivals, content sync, Docker, invasion counts |
| `godot-client/data/maps/registry.json` | the map key points at this package; the hollow's keys become aliases |

The client registry keys `sunmane_crystal_hollow` and
`sunmane_crystal_hollow.elm` are kept as aliases onto the combined map rather
than deleted, so anything still asking for the hollow by name resolves instead
of failing.

### A defect the wiring found

The invasion spawn generator placed all of Sunmane's cave monsters on a single
shared 3x3 grid of tiles inherited from the old 60-tile maps. Checked against
this package's `collision.bin`, **six of the nine wind-cave points are inside
solid rock** - and always were. Neither standalone cave map shipped a collision
grid, so there was nothing to check them against. Both systems now get nine
points each, every one verified as a tile whose four half-metre cells are all
walkable.

## Known limitations

* **One environment block serves two systems of different character.** The
  limestone caves were lit warm and the amethyst hollow violet; a single map
  can carry only one environment, so this is pitched between them and the
  per-system light markers carry the difference. A genuine compromise of the
  single-map layout rather than a choice — the same one Crownwater's insides
  made.
* **Nothing has been played.** Collision response, navmesh generation and portal
  transitions are unverified. The in-engine check proves the map loads through
  the real `WorldLoader` and that every walkable cell has floor under it; it
  does not prove an actor can walk it or that a portal fires.
* **No server has loaded the map.** The registry entry, the portals, the ELM
  and the invasion spawns are all in place and the ELM regenerates at 32
  tiles, but no running server has served it and no client has walked
  through a door into it. End-to-end play is unexercised.
* **The retirement has no data migration.** A character row persisted with
  `map_id = sunmane_crystal_hollow` refers to a map that no longer exists,
  and the server looks maps up directly (`eloria/world.py`, the `CHANGE_MAP`
  send on login) with no fallback, so such a login would raise `KeyError`.
  Nothing here migrates those rows, and no live database was inspected to
  see whether any exist. On a fresh deployment this is moot; on a live one
  it needs an `UPDATE characters SET map_id=...` first.
* **No client frames.** The two standalone packages have their own rendered
  minimaps; this combined package ships neither a minimap nor capture frames.
  The manifest declares `minimap.webp` and the file is not there yet.
* **No new content.** Sunmane still has the two interiors it had. If the region
  wants a third — the drovers' shelter and the eastern adit are modelled cave
  mouths with closed backs — that is authoring work, not a layout change.
