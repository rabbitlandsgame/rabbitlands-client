# Trail gauntlets: package format

A trail gauntlet is one open map. Its sections flow into each other with no gates
or portals. The approved pilot is the Harrowcrag Road
(`harrowcrag_gauntlet/`). Eight more roads redraw the gated gauntlets in the same
format, in grey box: `resin_road_gauntlet` (Amberwood), `ice_stair_gauntlet`
(Whitehorn), `coil_causeway_gauntlet` (Ssarathi), `barrow_run_gauntlet` (Grey
Moors), `drowned_arcades_gauntlet` (Crownwater), `red_canyon_gauntlet` (Sunmane),
`resonant_cut_gauntlet` (Amethyst) and `bund_run_gauntlet` (Manymouth). The gated
gauntlets keep their own ids and keepers; Rellan on Landfall offers the trail roads.

```
gauntlets/
  _toolkit/build_trail.py           builds a route's client package from its source
  _toolkit/landforms.py             the ground round a road, from layout.json `land`
  _toolkit/trail_dressing.py        grey-box dressing from layout.json `dressing`
  _toolkit/kits.py                  region kit models placed and instanced
  <route>/source/layout.json        geometry: arenas, paths, mouths, checkpoints (plan metres, y south)
  <route>/source/design.json        bands, waves, pulses, bosses, cache, broker (read by the server tool)
  <route>/client/                   the package: world.glb, world.json, collision.bin,
                                    served-grid.escg.gz, minimap.webp
```

Rebuild:

```sh
python eloria-assets/maps/gauntlets/_toolkit/build_trail.py harrowcrag_gauntlet --server <eloria-server checkout>
```

The server side (`tools/author_trail_gauntlet.py` in eloria-server) reads
`source/design.json` and the package's `world.json` `gauntlet` block.

## Dressing

`source/dressing.py` places kit models with `_toolkit/kits.py`. A model is the
route's own Meshy piece (`source/kit/`, with `MESHY_BATCH.md` and any fix
scripts) or a region's `kit-*.glb` prototype. Each is written into
`world.glb` once and instanced, so the client's static batching draws it as
one MultiMesh per cell. A placement's `solid` decides the walk grids:
- `footprint` closes the ground the model's upright faces cross at body height
  (0.25-2.1 m), with enclosed holes filled.
- `trunk` closes a disc at the origin. Trees use it.
- `None` is walk-through.

Solid pieces never stand in a creature mouth's opening. Every interactive
object's tile is re-opened, and areas the dressing lists in `props.clear`
(the vault) stay open.

Ground nodes are named for the look pass:
- `Terrain_` is off-road ground it paints.
- `Walk_Terrain_` is walkable ground it paints.
- `Walk_` keeps its own texture: the trail ribbon, and the dirt, cobble and
  stone floors drawn over the meadow as smooth overlays.

`godot-client/tests/integration/rendered_trail_gauntlet.gd` renders
`source/camera-views.json` through the loader and the look pass. It also
prints each game view's GPU and CPU frame time.

## The `land` block

A layout without one (the Harrowcrag Road) keeps the builder's own crag and river.
With one, `landforms.Land` shapes the ground and the builder carves the road into it.
The walkable ground is still exactly the route network; `land` decides what is
round it and what the network may not cross.

- **Land mode** (no `waterLevel`): the ground follows the road's own level, blurred,
  plus `banks` metres, `hills` of noise and a rising `frame` at the map's edge. The
  road cuts in over `cut` metres and is filled out over 3 m.
- **Water mode** (`waterLevel`, `floor`, optional `shore`): the land is a floor under
  water; the road stands out of it as causeways and islands. One water plane is drawn
  at `waterLevel` (material `water`).
- Landforms: `walls` (west/east valley walls), `massifs` (flat-topped mesas), `islands`,
  `pits` (a bench `profile` of radius and level, quantised into `benches`), `paddies`
  (a grid of bunds), `mounds` (barrows; `split` cuts a trench through one).
- What the road crosses: `lakes` (`deep` false is wading water), `rivers` (points
  `[x, y, level]`; `dry` is a sandy wash), `canals`, `crevasses`. All of them close the
  ground except inside `crossings` (`at`, `half`, `rot`): a bridge, a log, a boardwalk
  or a lock gate, walked at the road's own level. A mound 0.6 m or higher closes too.
- `ground` names a material per kind of ground: `bank`, `network`, `trail`, `cliff`,
  `mesa`, `bed`, `crevasse`, `bund`, `deck`.

Checkpoints may carry `reach` (metres; 9 by default).

## The `dressing` block

`trail_dressing.py` reads it: the road's kits (`"region/kit-stem"` or `"@kit/file.glb"`),
woods, cover, rocks and frame crags by weighted mix, the camp, the checkpoint fires,
road lanterns, a city of houses packed off the road (`city`), set pieces (`landmarks`:
a kit or a grey-box block, singly, in a `ring` or along a `line`) and the words on the
plaques and the cache (`labels`). A solid piece never stands in a mouth's way in or
within reach of an interactive object, and never on a tile the road owns; a refused
piece is listed under `dressing.refused` in the build report.

A landmark kit may also carry:
- `deck` true: a bridge, causeway, stair or log the road walks over. Its deck (the
  level holding the most up-facing area, `kits.deck_top`) sits on the road height
  under it, and it closes nothing: the road under it is terrain. `deckMax` and
  `deckLift` adjust which level counts and how far it is raised.
- `fitLength` (metres): scaled so its long side spans a crossing. With `deck`,
  `fitLength` or `alongLength`, a model longer in z than in x is turned so its long
  side follows `rot`.
- `solid` `{"disc": r}`: a trunk of its own size (r scaled with the piece), for big
  trees whose canopy footprint would close a clearing.
- `encloses` true: a shell the vault or another object stands inside (the Resonant
  Cut's geode), so the object and road checks skip it.

A `line` with step `"auto"` spaces its pieces by the kit's long side less `overlap`
(1 m by default).

The eight redrawn roads' sources are written by the design stage's
`work-output/gauntlet-v2-design/regions/tools/author_routes.py` from the approved
concept layouts: it places the mouths where nothing else is, the checkpoint fires
after waves 2 and 4 and the side pocket, sizes the waves from each band's roster, and
checks that no two pieces of the road come within 3 m unless they are joined.

## The `gauntlet` block in `client/world.json`

All tiles are **server tiles**: x east, y north, `0 <= x < serverCells[0]`,
`0 <= y < serverCells[1]`. All polygons are lists of `[x, y]` tile-corner
coordinates. A tile `(x, y)` is inside a polygon when its centre
`(x + 0.5, y + 0.5)` is.

```jsonc
{
  "schema": "eloria-trail-gauntlet-v1",
  "id": "harrowcrag_gauntlet",
  "style": "trail",
  "name": "The Harrowcrag Road",
  "short": "harrowcrag",
  "serverCells": [384, 336],
  "arrival": {"tile": [x, y]},                     // where a run puts the party (trailhead)
  "objects": {                                     // interactive object ids on this map
    "stagingExit": {"objectId": 800, "tile": [x, y], "label": "Waystone"},
    "vaultExit":   {"objectId": 799, "tile": [x, y], "label": "Waystone"},
    "cache":       {"objectId": 798, "tile": [x, y], "label": "The Castellan's strongbox"},
    "plaques": [{"objectId": 861, "tile": [x, y], "at": "trailhead"}, ...]
  },
  "sections": [                                    // in walking order; the last is the court
    {
      "id": "w1", "order": 1, "kind": "arena",     // kind: arena | court
      "name": "Hollow Meadow",
      "area": [[x, y], ...],                       // trigger polygon: a participant inside lands the wave
      "areaTiles": 2790,                           // open tiles inside `area` (a check value)
      "centre": [x, y],
      "mouths": [
        {"id": "w1-west", "kind": "pocket",        // pocket | ledge | floor
         "tile": [x, y],                           // the pocket's centre
         "spawnTiles": [[x, y], ...]}              // open tiles a pulse may land on, nearest the arena first
      ]
    }
  ],
  "sides": [{"id": "heron-pool", "name": "Heron Pool", "tile": [x, y], "nodeTile": [x, y], "plaqueTile": [x, y]}],
  "checkpoints": [                                 // in walking order
    {"id": "cp1", "name": "The look-out fire", "after": "w2",
     "tile": [x, y],                               // the fire (not walkable)
     "reach": [[x, y], ...],                       // polygon: a participant inside has reached it
     "respawnTiles": [[x, y], ...]}                // open tiles round the fire
  ],
  "vault": {"area": [[x, y], ...], "centre": [x, y]},
  "route": [[x, y], ...]                           // centreline tiles from arrival to vault, for tests
}
```

## Rules the package guarantees (the client test checks them)

- Every tile the served grid opens belongs to exactly one of: the trail
  corridors, an arena or court, a mouth pocket or ledge, a side pocket, the
  camp, or the vault.
- **No shortcut.** Close any arena's `area` tiles, and the arena before it
  and the arena after it are no longer connected. The trailhead reaches the
  vault only through every arena in order.
- Every mouth's spawn tiles reach its own arena without crossing any other
  arena's area.
- A mouth pocket touches its own arena only.
- Relief runs to 40-70 m on most roads, so the served grid is ESCG v2 (50 mm codes,
  1.0 m climb). The old ESCG v1 can hold only about 12.6 m.
