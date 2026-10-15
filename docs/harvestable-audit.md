# Harvestable audit — 2026-08-28

Audit of the harvestable layer of the Eloria client data pack: the models, the
materials, the client-side lookup that decides whether an object can be
harvested at all, and how harvest nodes are distributed across the Nymara maps.
Every claim below is against `develop` at the time of the audit, and every fix
described here is in the same change.

## Summary

| | before | after |
| --- | --- | --- |
| harvestable resources | 16 | 32 |
| distinct harvest models | 8 (5 resources shared one 8-triangle model) | 32 |
| harvest model triangles | 8–90 | 116–392 |
| harvest model materials | 128×128 checker (pack) / 256×256 (generated) | 256×256 authored, four regions |
| foliage rendering | opaque, back-face culled | alpha tested, both faces |
| objects the client can harvest | **0** | every placed node |
| harvest nodes in the world | 48, on 4 shared coordinates per region | 309, scattered per region |
| decorative ground flora | none (`obj_2d_no == 0` in every map) | 16 sprites, 1 152 instances |

## Findings

### 1. Nothing in the world was harvestable (blocking)

`3d_objects.c:543` calls `is_harvestable(fbase)` where `fbase` is the
**basename** of the object file (`3d_objects.c:494`), and `cursors.c:91`
resolves that with a `bsearch`/`strcmp` over the entries loaded from
`harvestable.lst`, which `load_harvestable_list()` lowercases. The generated
pack wrote relative paths:

```
3dobjects/harvestables/sunleaf.e3d
```

`strcmp("sunleaf.e3d", "3dobjects/harvestables/sunleaf.e3d")` never matches, so
`OBJ_3D_HARVESTABLE` was never set on any object on any map: no harvest cursor,
no harvest interaction. `FASTER_MAP_LOAD` — the code path that behaves this way
— is enabled by default in `CMakeLists.txt`, `make.defaults` and `meson.build`.
`entrable.lst` had the identical defect.

The list also named only the five legacy Emberhaven bootstrap harvestables,
while the twelve Nymara regions place sixteen entirely different resources.

**Fixed:** both lists are written as sorted lowercase basenames, and
`harvestable.lst` is rewritten at the end of the pipeline with the whole
catalogue (legacy Emberhaven set included).

### 2. Three disjoint harvestable vocabularies

* `generate_scenery.py` produced eighteen Eternal-Lands-generic harvestables
  (`sunleaf`, `wheat`, `coal`, `moon_salt`, …) and wrote them to
  `harvestables_eloria.lst`, a filename the client never reads.
* the Nymara pack generator placed a different sixteen (`REGION_HARVESTS`).
* the client asset pack shipped a third sixteen as `.2d` sprites and inventory
  icons, on item ids `1000+`, colliding with the equipment range recorded in
  `nymara_id_allocations.json` (`nymara_equipment: [1000, 1035]`).
* `maps/nymara-regions/sunmane_steppe/source/settlement.py`, which builds the highest-fidelity map in the
  project, declares a fourth set: *Sunmane wheat, Steppe herbs, Shore clay,
  Mesa flint*.

**Fixed:** `eloria-assets/tools/harvestables.py` is now the single catalogue.
Models, materials, icons, `harvestable.lst`, the ELM placements, the Four Gates
world package and the server-facing manifest all read from it. Harvestable
items moved to their own reserved id range (1100+). The Sunmane vocabulary is
reconciled: `steppe_wheat`, `wayside_sage`, `deep_lake_clay` and
`sunstone_flint` are catalogue entries.

### 3. Fidelity did not match the maps the nodes sit in

Measured triangle counts of the harvest models that shipped:

| resource | triangles | shared with |
| --- | --- | --- |
| `delta_lotus`, `ghost_orchid`, `ssarathi_scale_moss`, `verdant_venom_bulb`, `whitehorn_silverleaf` | 8 | one shared model: four intersecting quads |
| `amber_resin`, `deep_lake_clay`, `mangrove_sap`, `moor_peat` | 26 | one shared box-and-cone |
| `crownwater_pearl`, `glacier_salt`, `voltaic_geode` | 26 | one shared pair of cones |
| `mirror_reed` | 82 | — |
| `resonant_crystal`, `stormglass_shard` | 80 | one shared model |
| `sunmane_seed` | 90 | — |

The landmarks standing next to them run 12–424 triangles, with the refined Four
Gates civic kit at 224–424 and a stated contract of "intentional silhouette
topology, 256px authored procedural materials, stable scale and pivots". The
region GLBs run 9–10k triangles; `sunmane_steppe`, the current production
reference, is 168k triangles across 27 PBR materials. A harvest node is the
prop a player stands over for the whole harvest animation, and it was the
lowest-fidelity object in the scene by an order of magnitude — with a third of
the roster visually identical.

Materials were as thin as the geometry: the pack's harvestables carried
128×128 two-colour checkers, while the refined kit uses 256×256 authored
materials.

**Fixed:** every resource has its own authored model, 116–392 triangles, built
from a shared archetype vocabulary (stalk cluster, leafy herb, bloom, bulb,
fungus ring, ribbon weed, resin flow, mineral seam, crystal cluster, shell bed,
salt pan, moss mat). Each carries one 256×256 RGBA material quartered into
stalk, blade, bloom and bed regions so faces sample matching texel density, and
each sits in a small disturbed-ground bed so a node reads as a worked site.

### 4. Foliage was opaque and single sided

Every generated harvest model wrote material `options = 0`. `3d_objects.c:600`
turns a non-zero value into a transparent material, and the transparent draw
path (`3d_objects.c:303-314`) is what enables `GL_ALPHA_TEST` and disables
`GL_CULL_FACE`. With `options = 0` the leaf cards were back-face culled, so
they disappeared from half the camera angles, and the checker texture filled
the whole quad, so foliage read as painted cardboard.

**Fixed:** models whose silhouette depends on leaf cards declare a transparent
material and their material's blade quadrant carries a real alpha silhouette;
mineral and crystal nodes stay opaque so they keep culling and the cheaper
solid draw path. The validator asserts the flag matches the catalogue.

### 5. Every region got the same four nodes in the same four places

`generate_maps()` placed exactly four harvest objects per region, at
`(26,82) (48,84) (78,82) (98,76)` — the same coordinates in all eleven regions,
in a near-straight line — and four more in Four Gates. Forty-eight nodes in the
whole world. The recorded `object_id` (`8 + offset`) was not the ELM object
index either, because harvest placements are appended after the authored
composition, so the manifest could not identify the object it described.

**Fixed:** a deterministic per-region scatter places each region's catalogue
resources across its walkable footprint, keeps land resources off water tiles,
requires aquatic resources to be within a tile of water, keeps nodes clear of
authored landmarks and of each other, and records the real ELM object index.

### 6. Map object placements were written at twice their intended scale

Not a harvestable-only defect, but it decides where harvest nodes actually
land, so it is fixed here.

Placement and light coordinates throughout the generators are authored in
height-map cells — the same grid the tile and height callbacks use, and the
grid the server addresses. `four_gates_tile()` centres the capital on cell
`(96,96)`; `four_gates_height()` measures its radius from `(96,96)`. ELM object
records, however, store **world units**, and the client's own conversion is
`world = 0.5 * cell` (`map.c:679`, and `2d_objects` cluster assignment divides
by `0.5f`). A tile is 3.0 world units (`tile_map.c:93`), so a 32×32 map is
96×96 world units.

Writing cell coordinates straight into the record therefore placed the Four
Gates city geometry at world `(96,96)` — the far corner of its own map — while
the city terrain sits at world `(48,48)`, and pushed objects authored beyond
cell 192 off the terrain entirely.

**Fixed:** `make_map()` takes a `placement_scale` (0.5 by default) and applies
it to object and light coordinates, so the authored cell-space compositions
land on the terrain those same cell-space functions generate. Server-facing
manifests keep cell coordinates, which is the convention the server uses.

### 7. The 2D map object system was never used

Every generated ELM was written with `obj_2d_no == 0`, while the client has
full support for alpha-tested ground sprites (`obj_2d_io` in `io/map_io.h`,
`.2d` definitions parsed in `2d_objects.c`). The only `.2d` files in the
project were the sixteen shipped in the client asset pack, and they were the
**inventory icons** re-used as world sprites — and nothing placed them.

**Fixed:** `make_map()` writes 2D object records, and sixteen authored ground
flora sprites (grass, reeds, ferns, heather, jungle fronds, cattails,
saltgrass, thistle, snow tufts, dry brush, lily pads, moss, pebbles, crystal
grit) are scattered per region from biome-specific palettes. The icon-derived
harvestable `.2d` files are gone; a harvest node has to be a 3D object for the
client to flag it harvestable.

## New harvestables

Sixteen general resources were added so that every region has ordinary
crafting work alongside its signature rarity, rather than sixteen exotic
resources and nothing else:

`wayside_sage`, `steppe_wheat`, `riverflax`, `moorcotton`, `hearthroot`,
`barrow_bramble`, `lantern_cap`, `tidewrack_kelp`, `shorebank_shell`,
`verdigris_bloom`, `bogiron_nodule`, `emberseam_coal`, `pale_quartz`,
`sunstone_flint`, `indigo_thistle`, `cenote_watercress`.

They cover fibre, grain, root food, berries, fungus, kelp, shell lime, copper,
bog iron, fuel, quartz, flint, dye and cress, and each is assigned to three to
eight regions so the common resources overlap between neighbours while the
rarities stay regional.

## Verifying

> Reproduction commands removed: this stage was validated against the
> Eternal Lands format data pack, which was deleted with the C client
> on 2026-09-03. The evidence below is kept as the record of it.

`validate_harvestables.py` ran as part of that pipeline's validation stage and
checks the list format, model presence, the triangle band, the alpha-test flag,
material size, per-region node counts and spread, and the flora definitions.
