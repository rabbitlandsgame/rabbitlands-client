# The Coil Causeway — modeling assumptions

The route follows the lore of a yearly lineage procession beneath the temple,
with a hatchery maintained for the rest of the year. The exterior's
[concept board](../../ssarathi_ruins/references/00-concept-detail-board.png)
sets the art direction: green carved masonry, pale weathered stone, gold sun
reliefs, lily pools and roots reclaiming the older ways.

The Water Gate's twin basins prepare the ceremonial approach. Three gateways
break the Lily Causeway into short reaches; their piers continue down to the
channel bed. Lily pads sit at water level below the guarded stone deck.
The Hatchery separates wall-fed water troughs from dry incubation mounds.
The gallery's repeating sun seals mark progress while the middle Lichen
alcove remains accessible.

The Two Mouths advertise their choice in the hub. The wet branch has a root
arch, nesting beds, a water trough and a humus floor. The carved branch has
formal gateways and raised sun reliefs. The Sun Stair reaches a tended upper
landing before the final court, where the largest spiral sun seal crowns
the reward doorway. A rear dais step keeps that doorway connected.

Eight-metre gate passages remove 36 metres of empty traversal. The package
runs 325 metres end to end, with 311 metres between arrival and vault.
Seven legs, both branches, the timed crossing and existing encounter rules
remain. Prop groups occupy side bays, and the central floors remain available
for combat. These are interior route landmarks, with increasing scale toward
the court; the temple remains the exterior zone's skyline landmark.

All geometry and textures are shared procedural recipes. The new templecraft
pieces take dimensions, material names and explicit seeds. The eggshell and
lily-pad material recipes are appended to the shared material list; no
terrain surface classes are changed. Room lids remain overhead nodes.
Coplanar joints are clipped and render batches are local to their lights.

The manifest uses a muted green ambient fill and warm point lights under a
sealed roof. Captures use the actual environment and the gameplay cutaway
controller. Gate cuts and the surrounding void deliberately stay blocked.
