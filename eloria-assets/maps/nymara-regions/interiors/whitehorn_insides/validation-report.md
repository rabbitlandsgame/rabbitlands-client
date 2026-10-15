# Whitehorn Range insides validation report

What was checked, and what was not.

## Automated checks

| Check | Command | Result |
| --- | --- | --- |
| glTF 2.0 validity | `_toolkit/validate_gltf.py world.glb` | **0 errors, 0 warnings** |
| Runtime contract | `_toolkit/verify_runtime.py --package .` | **0 errors**, 1 warning |
| In-engine grounding | `_toolkit/region_client_check.gd` | **PASS**, 30,276 tiles, 0 misses on walkable cells, all five arrivals ground |
| Determinism | two builds | `world.glb`, `world.json`, `collision.bin` byte-identical |
| Collision dimensions | — | 348 × 348, both multiples of six |
| Section separation | `interiors._assert_gutters` | at least 20 m of void between every pair, checked at build time |

## The one warning, and why it is not a defect

```
[warning] GROUNDING_RAY_MISS: 22286 server tiles have no walk surface under them
```

On a combined insides map that is two things at once: the rock around each
section, and the **void between them**, which is the whole point of the layout.
74% of the bounding square is deliberately not floor. Amberwood's and Amethyst's
interiors carry the same warning for the same reason.

The check that distinguishes a real defect from expected rock is whether the
misses land on cells the package's **own** collision grid marks walkable. They
do not:

```
[client-check] grounding: 30276 tiles sampled, 22286 misses (73.61%)
[client-check]   of those, 0 are on cells collision.bin marks walkable;
                 22286 are blocked cells and expected
[client-check] PASS
```

## A real defect this found, and the rule that came out of it

The first in-engine run reported **11 misses on walkable cells**, all along the
sanctuary stair. The cause is quantisation, and it is worth writing down because
it will catch anyone building an interior:

The collision grid is half-metre. The server samples tile centres a **metre**
apart. A corridor of half-width `h` centred on an integer therefore marks the
cell centred at `h − 0.25` walkable, while the grounding ray at the next whole
tile — at distance `⌈h⌉` — finds nothing. Any half-width in the open interval
(1.75, 2.00) produces that gap: **the server lets a player stand where the
client cannot ground them**, which is exactly the fall-through the production
guide warns about.

Widths of 3.6 m (h = 1.8) and 4.0 m (h = 2.0) are precisely the bad cases. This
package now uses 3.4 (h = 1.7), 4.4 (h = 2.2), 4.6 and 5.0 throughout, and the
rule is recorded in a comment beside the passage table in
`source/interiors_temple.py`.

**Two of Amberwood's four shipped interiors have this defect**, measured with
the same harness against the packages currently on `develop`:

| package | misses on walkable cells |
| --- | ---: |
| `amberwood_motherroot` | 36 |
| `amberwood_amber_hall` | 19 |
| `amberwood_gate_undercroft` | 0 |
| `amberwood_cinder_chapel` | 0 |

Not fixed here: they are another region's packages, Amberwood was regenerated
only recently and must stay byte-reproducible, and changing its geometry to
close these needs its own commit and its own verification. Reported so somebody
can pick it up.

## Toolkit change

`_toolkit/region_client_check.gd` previously failed a package if **any** sampled
tile missed. That is the right rule for a region, which has ground under every
tile, and the wrong one for an interior, which does not — it failed every
correctly-built interior and so could never have found the defect above.

It now reads the package's own `collision.bin` (via the `originMetres` the
interior manifests publish) and judges on walkable cells only, reporting both
numbers. Packages that publish no grid origin — the regions — keep the old
strict criterion exactly, so nothing regresses there.

## What is NOT verified

1. **No client frame.** The in-engine check runs headless, which has no
   renderer. Everything in `references/` is the offline rasteriser. Nobody has
   looked at this interior rendered by the game.
2. **No portal transition test.** The region manifest's
   `whitehorn-glacier-temple-door` portal and this package's
   `exit-to-whitehorn` name each other correctly, but no client has walked
   through either. No server was run.
3. **The interior's own detail board is truncated.** The supplied
   `references/00-concept-detail-board.png` is 786,446 bytes and does not
   decode, so there are no panel images to compare against. The ten subjects
   come from `concept.json`'s explicit list and from the parent region's intact
   board, which covers the temple facade, the shrine alcove, the ice cave and
   the mine at player scale. A panel-by-panel comparison sheet is therefore not
   possible for this package; the preview sheet is one frame per room instead.
4. **Every name is invented**, as with the region above.
5. **The server's generated collision for this key does not match this
   geometry.** `export_insides_collision.py` writes
   `server-collision/whitehorn_glacier_temple.bin` from this package's own
   `collision.bin` — 192 × 192 cells, 21.6% walkable, the rest void and rock —
   and it fits the 32 tiles an interior map already allows, so no server change
   is needed for extent. But `tools/generate_nymara_maps.py` still generates its
   own fully-walkable placeholder for that key and does not ingest this ELM.
   Until it does, the server will let a player walk across the void between
   sections while the client drops them. That is the same gap the region above
   has, and it is the most important open item on this package.
6. **Performance is measured, not profiled.** 38,929 triangles and 7.2 MB;
   frame rate untested.
