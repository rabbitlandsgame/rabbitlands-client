# Whitehorn Range insides

Every interior belonging to the Whitehorn Range, on **one map**, separated by
unwalkable void — the Eternal Lands arrangement. One GLB, one manifest, one
collision grid and one server map key instead of four of each, entered at a
different arrival depending on which surface door was used.

## The four sections

| section | door on the surface | class | what it is |
| --- | --- | --- | --- |
| `glacier_temple` | Glacier Temple portal | temple | The monastery: snow entry, vaulted nave, prayer colonnade, votive chamber, upper sanctuary, and past the last built arch the glacier altar cut in ice. |
| `whitehorn_mine` | mine adit, east massif | dungeon | The workings the monastery's silver came from. Timbered gallery, rails and cart, a crevasse the ice opened across it, and a pump engine for the water. |
| `ice_cave` | ice cave mouth, west | cave | Nobody built it. Meltwater cut it and refroze. Blue chamber of ice pillars, a pool that has not refrozen with a plank walk over it, and a crystal vault at the end. |
| `frost_barrow` | under the cairn ridge | barrow | Older than the monastery and not of it. A creep into a gallery of stone cists, and one chamber the monks walled up rather than empty. |

## The idea holding it together

**The glacier is eating the mountain, and everything in it.**

The monks cut a temple into the rock and followed a silver vein north into the
ice. In the temple the ice has cracked and bulged the colonnade's outer wall,
half-swallowed the last built arch, and carried an older colonnade twenty metres
off its foundations — it still stands in two rows in the altar chamber, every
column leaning the same way, because they are all riding the same ice. In the
mine it opened a crevasse straight across the main gallery, and rather than
abandon the far side the miners bridged it with `kit.rope_bridge` — the
identical piece the region uses on its gorge outside. The cave is what the ice
does where nobody built anything at all. The barrow is what was there first.

## The void

The blackspace is **not drawn**. The collision grid is built only where a
`Walk_` surface exists, so the gutters between the four sections are blocked
already, and nothing is rendered in them either: walking off a section's edge
finds no floor and no geometry, which is what EL's void is.

Section offsets keep at least 20 m of nothing between any two, and
`interiors._assert_gutters` fails the build if a later edit closes that. The gap
is not decoration — it is what stops a lamp in the mine lighting the barrow and
keeps a camera in one section from seeing into another.

```
  z
  ^   frost_barrow                      (void)
  |
  |   glacier_temple                    ice_cave
  |
  |   glacier_temple                    whitehorn_mine
  +-------------------------------------------------> x
```

## Runtime files

| File | What it is |
| --- | --- |
| `world.glb` | Self-contained glTF 2.0, 52,505 triangles, 7.98 MB. |
| `world.json` | Manifest with a `sections` block, five spawn points (one per door plus a default) and a matching return portal standing on each arrival. |
| `collision.bin` | `EWCG v1`, 348 × 348 half-metre cells, 31,816 walkable (26.3%). The rest is rock and void. |
| `references/00-insides-preview-sheet.webp` | Nineteen offline-rendered views across the four sections. |
| `references/godot-client-check.json` | In-engine grounding report. |

## Entering it

Each surface door carries a `destinationSpawn` naming a spawn point here:

| door on the region | arrival |
| --- | --- |
| `whitehorn-glacier-temple-door` | `glacier_temple.snow_entry` |
| `whitehorn-mine-adit` | `whitehorn_mine.adit_head` |
| `whitehorn-ice-cave-mouth` | `ice_cave.cave_mouth` |
| `whitehorn-barrow-door` | `frost_barrow.barrow_entry` |

All four point at `maps/nymara/whitehorn_glacier_temple.elm`, the map key the
server already carries for this region's interior; the registry maps that key to
this package. A return portal stands on each arrival and sends the player back
to the door they came in by, not to one shared exit.

## Building it

```sh
cd ../../whitehorn_range/source
python3 build_interiors.py
python3 export_insides_collision.py
python3 preview_interior.py insides /tmp/sheet.png
python3 ../../_toolkit/verify_runtime.py --package ../../interiors/whitehorn_insides
```

`export_insides_collision.py` downsamples this package's own `collision.bin` to the
one-metre ELM height map, so the client grid and the server map cannot drift
apart. The result is 192 × 192 cells — inside the 32 tiles an interior map
already allows, so **no server-side change is needed**.

## Verification

| Check | Result |
| --- | --- |
| `validate_gltf.py` | **0 errors, 0 warnings** |
| `verify_runtime.py` | **0 errors**, 1 warning |
| Godot 4.7.2 through the real `WorldLoader` | **PASS** — all 30,276 tiles, **0 misses on any cell `collision.bin` marks walkable**; all five spawns ground |
| Determinism | byte-identical across builds |

The `verify_runtime` warning is `GROUNDING_RAY_MISS` on 22,286 tiles. On a
combined insides map that is the void between sections plus the rock around each
— 74% of the bounding square is deliberately not floor. Every one of those tiles
is a blocked cell. See `validation-report.md`.
