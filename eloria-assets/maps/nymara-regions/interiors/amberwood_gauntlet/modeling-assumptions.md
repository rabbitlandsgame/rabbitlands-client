# The Resin Road — modeling assumptions

The route is the disused charcoal and resin haul road below Amberwood's charcoal
camp. Its design follows the camp's warm timber, dark bark, grey stone and amber
glass palette; the exterior references remain the art direction. It is a worked
underground passage being reclaimed by the forest.

The supply hall holds a cart, timber and barrels beside a clear arrival and home
waystone. Packed earth marks the working rooms; leaf litter belongs to the
rooted hollows. The cellar's vats collect resin near seepage, and the raised,
stone-lined collection basin distinguishes the wet branch from dry timber
storage. The upper landing carries a hand winch where carts once climbed.

Seven legs and their fork remain. Main and branch passages are eight metres
long, reducing the overall footprint from 361 to 325 metres. The arrival-to-vault
distance is 311 metres. Gate cuts stay sealed until the server opens a portal;
neither exterior walk-grid corrections nor island joining apply to those cuts.

Root arches grow larger deeper along the route, ending in a fourteen-metre crown
behind the Boar King's dais. Timber frames, lit storage bays and the exposed,
railed bridge interrupt the long views. Furniture occupies working bays and
edges, preserving the combat floors, door approaches and existing boss position
relative to its court.

All assets and textures are procedural recipes in the shared toolkit. No surface
classes were added or renumbered. Room lids, including the pit vault, remain
separate overhead nodes. Same-facing joint overlaps are clipped geometrically,
with navigation taking ownership of shared floor coverage. Twelve-metre render
bands let local lamps illuminate nearby geometry in Godot Compatibility.

The package declares no sun and uses warm point lights over a modest green-grey
ambient fill. Captures use that exact manifest environment and the game's
InteriorCutaway controller. Both eye-level and isometric views are checked.
