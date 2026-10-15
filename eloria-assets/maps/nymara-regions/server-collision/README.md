# Server walk grids

One file per served map whose collision the server cannot derive from a region
package on its own, resampled onto the server's own tile grid.

These replace `source-elm/*.elm`. That directory held Eternal Lands ELM binaries
which existed for one reason — the server read a height field out of them — and
carrying Eternal Lands map files in this repository is what this format exists
to stop. The bytes are unchanged: each file here holds the exact height field
its ELM held, so the server reads the same numbers it always did.

## Format

`_toolkit/server_walk_grid.py` writes and reads them. EWCG, the walk-grid format
every map package already ships as `collision.bin`:

| offset | size | field                                            |
|--------|------|--------------------------------------------------|
| 0      | 4    | `EWCG`                                           |
| 4      | 2    | version, `1`                                     |
| 6      | 2    | reserved, `0`                                    |
| 8      | 4    | width in cells, uint32 little-endian             |
| 12     | 4    | height in cells, uint32 little-endian            |
| 16     | w·h  | one elevation code per cell                      |

One cell is **one server tile** here, not the half metre a package's own
`collision.bin` uses. A cell byte of zero means blocked; anything else is
`code * 0.2 - 2.2` metres.

## What is here, and why only these

The server prefers a region's own half-metre `collision.bin` and resamples it
itself, so the eleven exteriors and the single-block interiors need nothing from
this directory. What is here is the eight maps that compose several interiors
onto one served map with blackspace between them: only the package that laid
them out knows that composition, so only it can state the server's grid.

| file                            | served map id                 | written by                                          |
|---------------------------------|-------------------------------|-----------------------------------------------------|
| `drowned_crown.bin`             | `drowned_crown`               | `crownwater/source/export_insides_collision.py`      |
| `grey_moor_barrows.bin`         | `grey_moor_barrows`           | `grey_moors/source/export_insides_collision.py`      |
| `manymouth_flooded_labyrinth.bin` | `manymouth_flooded_labyrinth` | `manymouth_delta/source/export_insides_collision.py` |
| `resonant_vault.bin`            | `resonant_vault`              | `amethyst_barrens/source/export_insides_collision.py` |
| `ssarathi_royal_archive.bin`    | `ssarathi_royal_archive`      | `ssarathi_ruins/source/export_insides_collision.py`  |
| `verdant_stair_insides.bin`     | `verdant_stair_insides`       | `verdant_stair/source/export_insides_collision.py`   |
| `westhaven_insides.bin`         | `westhaven_insides`           | `westhaven/source/export_insides_collision.py`       |
| `whitehorn_glacier_temple.bin`  | `whitehorn_glacier_temple`    | `whitehorn_range/source/export_insides_collision.py` |

`_toolkit/export_server_collision.py` writes an exterior's grid here too, on
demand. The server does not read those, so none are checked in.

## The matching server change

`eloria-server` reads this repository directly. Its `tools/collision_sources.py`
now declares these eight as

```python
_WALK = "nymara-regions/server-collision"
_SERVER_TILE = GridTransform(cell_tiles=1.0, shift=0.0)

def _composed(name: str) -> Source:
    return Source("ewcg", f"{_WALK}/{name}.bin", _SERVER_TILE)
```

`cell_tiles=1.0` makes the server's `resample` the identity, and `rebase=False`
leaves the elevation codes alone, so `Source.load` returns exactly the array its
ELM height reader returned. Re-running `tools/sync_authored_collision.py` against
this repository reproduces all 23 vendored `tools/collision/*.escg.gz` grids byte
for byte, which is the check that the format change moved nothing.

That module no longer reads ELM at all, and its tests refuse a source that asks
for one.

## Known divergence, carried over deliberately

Seven of the eight exporters sample one half-metre cell per server tile; only
Westhaven takes the maximum over the block. A stride sample steps over any wall
thinner than the stride, and it once put three of Westhaven's four arrival tiles
on blocked cells. Every region keeps the behaviour it shipped with — this is a
format migration, not a collision change — so each is stated as
`downsample="stride"` or `downsample="max"` at its call site rather than left to
a default. Moving a region to `max` is a change to where players can walk, and
belongs with that map's requalification.
