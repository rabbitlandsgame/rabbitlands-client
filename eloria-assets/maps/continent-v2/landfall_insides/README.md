# Landfall Underground

Four independent areas share `landfall_insides`, a 240 × 240 tile map. Unfloored,
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
| Lantern Mine | Landfall `(332, 86)` | 6 Coal, 3 Iron Ore, 1 Quartz | Peaceful working mine |
| Pinebrow Deep Workings | Pinebrow `(537, 490)` | Coal, Iron Ore, Copper, Sulfur, Slate | 2 Coal Kobolds, 1 Nightweave Spider |
| Cenote Deeps | Coilmere `(230, 754)` | Quartz, Salt, Slate, Sulfur, Crystal, Geode | 2 Cave Spiders, 1 Moss Golem |
| Boarsend Old Barrow | Boarsend `(825, 489)` | Quartz, Salt | 2 Skeletons, 1 Moss Golem |

The first mine supplies the missing starter fuel and metal without combat.
Creatures in the other areas remain deep beyond the safe entry chambers, with
short leashes. They use the existing reviewed models and combat balance: kobolds
and spiders start around attack 17–25; moss golems use 28 and skeletons 33.
Mining uses the existing Pickaxe and resource rules. Coal, Quartz, and Salt have
recommended harvesting level 4; Sulfur 8; Slate 12; Copper 15; Iron Ore 18;
Crystal and Geode 24. Lower-level harvesting retains the existing success rules.

## Sources and rebuilding

`_continent_v2/content/underground.json` is the single authored room, resource,
spawn, and connection plan. `_continent_v2/build_underground.py` produces the
package, minimap, three exterior entrance models, and the client registry row.
The models use the same original stone and timber material kit as other insides.
No external art or additional model service is required.

```powershell
python eloria-assets/maps/continent-v2/_continent_v2/build_underground.py --server ../eloria-server
godot --headless --path godot-client --script res://tests/integration/landfall_underground.gd
```

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
