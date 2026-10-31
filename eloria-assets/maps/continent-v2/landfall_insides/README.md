# Landfall Underground

Twenty-three independent sections share `landfall_insides`, a 720 × 720 tile map. Unfloored,
blocked blackspace separates them, following the existing shared-insides layout.
Each exterior mouth is saved in its territory's authoring scene. Click its portal
to enter; the doorway in the entry chamber returns to open ground outside.
Entry requires a client declaring `landfall_underground_v1`, so an older continent
client receives an update message before being sent onto the new interior map.

Exterior entrances are marked by tan dots and permanent names on the Tab map,
region previews, Landfall overview, and minimap. Their locations are published
from the authored underground plan into `cartography-continent-v2.json`.

| Area | Exterior entrance | Resources | Encounters |
|---|---|---|---|
| Lantern Mine: Upper Galleries → workings → Old Seam | Landfall `(332, 86)` | Existing mine resources retained | Four native groups of three Lantern Goblins in the Upper Galleries |
| Pinebrow Deep Workings | Pinebrow `(537, 490)` | Coal, Iron Ore, Copper, Sulfur, Slate | 2 Coal Kobolds, 1 Nightweave Spider |
| Cenote Deeps | Coilmere `(230, 754)` | Quartz, Salt, Slate, Sulfur, Crystal, Geode | 2 Cave Spiders, 1 Moss Golem |
| Boarsend Old Barrow | Boarsend `(825, 489)` | Quartz, Salt | 2 Skeletons, 1 Moss Golem |

## The Cenote Deeps

The owner asked on 2026-10-20 for Coilmere's cave to become a jungle cenote, laid
out like the reference undergrounds (a narrow winding tunnel opening into a great
cavern, side caves, lamps and glowing stone in the dark) and drawn in Rabbit
Lands' own art. Style `cenote` in the plan builds an entry grotto with a serpent
arch over the way out, a winding root tunnel, the sinkhole itself (a jade pool
against its back wall under a waterfall, a rock island with a jade cairn, a shaft
of daylight, a limestone outcrop) and three side caves: the Drowned Gallery
(sunk serpent ruins, an altar, braziers, salt and slate), the Glowmoss Grotto
(jade-lit crystals, a geode, the moss golem) and the Root Crawl (quartz, sulfur,
toadstools, a spider). The builder draws only the shell: floor, a low rock face,
the pools' water, banks and beds, and the daylight. Everything else is reviewed
Meshy kit art from Landfall A3's `lf-biomes` kit, placed by
`tools/prepare_underground_scenery.py` from the builder's `dressing()`: the plan's
props, and limestone crags and boulders set into every wall. A wall's crags stand
in a `Rocks_<section>_<facing>` group that the cutaway hides with that wall, as
the video's near walls drop out of view. The props that stand on the floor block
their footprint in the walk grid; flora is walk-through.

Lantern Mine's Upper Galleries is a larger first level with fifteen chambers,
looping haulage tunnels and side cuts. The outside door now arrives at
`(520, 548)`; stairs `(530, 685)` lead to the original workings at `(55, 32)`.
The return stair in the workings is `(55, 27)`. The existing Old Seam passage
remains in place. Public Lantern Goblins use the existing goblin model, level 5
stats, short leashes and ordinary respawns; entry and stair landings stay clear.

All three mine levels use a warm lantern atmosphere, with 57 lights in the
Upper Galleries, 18 in the workings and 6 in Old Seam. The compatibility renderer
prioritizes the eight lanterns nearest the camera so distant lights cannot
exhaust its per-mesh light limit. Other underground sections retain their own
lighting. Map backgrounds and portal labels follow the new route.

New rescue quests enter the Upper Galleries in a party-private copy and fight
four additional groups of four goblins before descending together. Stair travel
requires the nearby party and Elen, and preserves her finite health and mana.
Existing saved rescues retain their original route and defeated enemies. Quest
enemy names and map dots use invasion red, without invasion scaling or loot.

Creatures in the other areas remain deep beyond the safe entry chambers, with
short leashes. They use the existing reviewed models and combat balance: kobolds
and spiders start around attack 17–25; moss golems use 28 and skeletons 33.
Mining uses the existing Pickaxe and resource rules. Coal, Quartz, and Salt have
recommended harvesting level 4; Sulfur 8; Slate 12; Copper 15; Iron Ore 18;
Crystal and Geode 24. Lower-level harvesting retains the existing success rules.

## Sources and rebuilding

`_continent_v2/content/underground.json` is the single authored room, resource,
spawn, and connection plan. `_continent_v2/build_underground.py` produces the
package (shell, collision, served grid, markers, lights, cutaway) and minimap, and
moves its images into the shared pool (`eloria-assets/tools/shared_images.py`).
It was retired with the procedural generators on 2026-10-16 and re-enabled by the
owner on 2026-10-20 for the Cenote Deeps: it runs only with `--owner-approved`.
The owner also authorized the connecting Upper Galleries and additional mine
lanterns on 2026-10-31; the rebuild reuses the existing approved kit.
The doors' exterior art is reused Meshy scenery in `godot-client/data/world/objects.json`
(`retarget_underground.py` keeps its tiles and labels), not a builder output.

```powershell
python eloria-assets/maps/continent-v2/_continent_v2/build_underground.py --server ../rabbitlands-server --owner-approved "<who, when, what>"
python tools/prepare_underground_scenery.py --map landfall_insides --configs-only
python eloria-assets/maps/continent-v2/_continent_v2/retarget_underground.py --check
godot --headless --path godot-client --script res://tests/integration/landfall_underground.gd
```

A plan change that moves a room or prop is a rebuild: the scenery must follow the
same `dressing()` the walk grid was cut from. The builder refuses a cenote prop or
pool that cuts floor off from the arrival (it closes only scraps of 12 tiles or
fewer). The other sections' meshes and grids rebuild byte-identical.

Exterior entrance changes follow the normal saved-scene bake, collision export,
client-package and crossings workflow. `publish_server.py` then validates both
the exterior entrance markers and the interior package, and publishes their
portals, harvest nodes, encounters and collision in the continent overlay. Its
`--check` also compares the interior collision and source digests. Interiors have
their own frames and do not participate in the exterior polygon partition or
seamless borders. Server map generation reads their `interiorMaps` metadata.

Publication refuses disconnected room pockets, connections across blackspace,
unreachable exits or harvest approaches, blocked exterior landings, invalid
creature footprints, and encounters too close to entry. The runtime test covers
all entrance/exit round trips and gathering coal and iron with a fresh miner.

After rebuilding, preserve the existing canonical image URIs and compression
policy with `eloria-assets/tools/canonicalize_map_images.py`; do not leave raw
duplicates of already shared images. Regenerate section backgrounds with
`eloria-assets/tools/render_map_backgrounds.py --map landfall_insides --apply`
and run the server publication check against the same exterior package versions
already served. An interior change must not silently promote unrelated exterior
collision or crossing changes. The 2026-10-31 mine publication keeps the exterior
packages from client `2c04d2e8`; their exact hashes remain in the publication
record. The mine source, collision and manifest hashes identify the new interior.
