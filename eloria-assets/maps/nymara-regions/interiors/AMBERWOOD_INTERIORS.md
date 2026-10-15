# Amberwood interiors

Four authored interiors reached from named landmarks on the 576 m Amberwood map.
They are built with the region's own toolkit — `amberwood/mesh.py`,
`architecture.py`, `stonework.py`, `treecraft.py`, `props.py` and the single
material table in `materials.py` — so a doorway, a stair tread and a carved
bracket are the same construction indoors as out.

| package | name | class | surface anchor | triangles | GLB | walk cells |
|---|---|---|---|---:|---:|---:|
| `amberwood_motherroot` | The Motherroot | dungeon | `great-tree` | 22,669 | 7.4 MB | 13,440 |
| `amberwood_gate_undercroft` | The Gate Undercroft | annex | `great-arch` | 13,078 | 3.5 MB | 9,500 |
| `amberwood_amber_hall` | The Amber Hall | settlement | `amber-hall` | 21,696 | 6.0 MB | 8,168 |
| `amberwood_cinder_chapel` | The Cinder Chapel | transition | `ash-chapel` | 12,178 | 5.1 MB | 6,744 |

## Building them

    cd ../amberwood/source
    python3 build_interiors.py                 # all four
    python3 build_interiors.py --only motherroot
    python3 preview_interior.py motherroot /tmp/sheet.png
    python3 verify_runtime.py --package ../../interiors/amberwood_motherroot

`build_interiors.py` emits `world.glb`, `world.json`, `collision.bin` and a glTF
validator report per package, and is deterministic for a given seed.

## The two contracts that matter

**Walk surfaces.** Every standable surface is emitted as a `Walk_<material>`
node. The client turns node names matching `navigation.surfaceNodePrefixes` into
the collision layer its downward grounding ray tests; a floor emitted as ordinary
geometry is scenery the player falls through.

**Collision.** `collision.bin` is the region's `EWCG v1` format — magic, version,
width, height, then one unsigned byte per half-metre cell, rows running north to
south. The byte is a six-bit height code, not a flag: 0 is blocked, 1..63 decode
as `origin + value * step`. Each interior fits its own `step` to its vertical
range. Inventing a second format here would have produced a file the loader
cannot read.

## Where they attach

Each interior's surface entrance is a portal on the Amberwood region manifest,
sitting on the landmark it belongs to, and each package carries the matching
return portal. Entries are registered in `godot-client/data/maps/registry.json`.

## Verification, and its limit

`verify_runtime.py` — the region's own harness, which reproduces the client's
`_place_actor_on_surface` grounding ray offline — reports **0 errors** on all
four packages. All four pass `validate_gltf.py` with no errors.

Each still reports one `GROUNDING_RAY_MISS` warning. That is expected and not a
defect: the harness samples the whole square footprint, and an interior is rooms
inside rock, so most of its bounding square is legitimately not walkable. A
region has ground everywhere; an interior does not.

**These have not been opened in Godot.** No client is installable in the build
environment, so collision response, navmesh generation, portal transitions, LOD
and transparency sorting are unverified. `eloria-server` has not registered the
map keys, so the client can load these but the server has not agreed them.

## References

`references/00-checkpoint-contact-sheet.png` in each package is rendered from
that package's own exported GLB with `preview_interior.py`, one view per concept
subject. These interiors have no concept board of their own; they are
art-directed from the Amberwood region board.
