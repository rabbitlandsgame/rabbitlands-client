# Secrets: what needs a decision

The secrets ship with what the game already has - existing resources, fielded
species, the four new area kinds - so nothing below blocks them. Each item is
something the secrets would be better for, and a call to make.

## New harvestables (proposed, not added)

Each secret garden and grotto would carry one resource found nowhere else.
Adding one means an item id, an icon, a `resource |` line with its level band
and tool, and a model in the client's world-object catalogue (the item-economy
notes in the repo cover the id ledger and icon pipeline).

| region | proposed resource | grows in | level band | tool | use |
|---|---|---|---|---|---|
| Amberwood | Heartwood Sap | the Resin Hollow | 14-22 | - | amber glass, resin potions |
| Mirrorhold | Lens Sand | the Lens-Grinders' Garden | 10-18 | - | lens grinding, glass |
| Amethyst Barrens | Songstone Dust | the Shard Garden | 26-38 | Pickaxe | tuned shards, resonance dyes |
| Crownwater | Drowned Pearl | the Pearl Hollow | 28-40 | - | jewellery, tide charms |
| Westhaven | Wreck Copper | the Wrack Hollow | 16-24 | Pickaxe | bronze fittings |
| Grey Moors | Barrowlight Moss | the Peat Hollow | 20-30 | - | lamp oil, wisp lures |
| Manymouth Delta | Tide Lotus | the Lotus Hollow | 14-22 | - | dyes, regeneration potions |
| Verdant Stair | Cenote Orchid | the Cenote Hollow | 24-34 | - | perfumes, venom antidotes |
| Whitehorn Range | Glacier Milk | the Silverleaf Hollow | 18-28 | - | cold protection potions |
| Ssarathi Ruins | Serpent-Scale Lichen | the Scale-Moss Hollow | 22-32 | - | scale armour lacquer |
| Sunmane Steppe | Dune Amber | the Seed Hollow | 12-20 | - | saddlery, amber glass |
| Four Gates | Lantern Oil Bloom | the Sunleaf Hollow | 6-12 | - | lamp oil |

Until these exist the hollows carry the region's existing resources at higher
counts, which is still a reward for finding them.

## Mechanics the secrets could use (not built)

| feature | what the secrets do today | what it would take |
|---|---|---|
| Drag an item onto a terrain feature ("use with") | a keyed entrance checks the key is *in the pack* when the feature is used; the item is not consumed | the client has no use-with cursor mode; the wire packet has room for an inventory slot; server reads it |
| Per-skill schools | the `experience` area multiplies every skill's gain inside the room | an area kind carrying a skill name, read in `experience_multiplier` |
| Cheaper summons | `cheap_magic` halves spell ether; summoning pays its own cost path | apply the same divisor in `summoning.py` |
| Ranging targets as objects | the ranges use slow live creatures and the `training` post | a target object kind that takes shots and reports hits |
| Consumable keys | keys are never used up | a `key!:<Item>` target that removes one from the pack |
| Time-limited secrets | every entrance is always open | an area or portal calendar hook (the special-days system is the obvious host) |
| Secret-only creatures | the pens field species the region already spawns | new reviewed rigs, or variants named for the room |
| PK arenas | the null wells are no-magic training pens | a PK zone declared on the room's tiles (`pk.py` already has zones) |

## Things worth a look in play

* The entrance props stand on open ground beside their landmark: natural
  ground within 14 m first, then paved ground with room around it, then the
  same out to 60 m (a giant tree or a stone ring blocks the ground for 30 m
  around). Each region manifest's `interactives` records where each one
  landed; anything the dresser could not place is in its build notes.
* Four Gates' fourteen entrances are server objects only: the Four Gates
  package is not built by the region toolkit, so nothing was added to its
  GLB and each entrance shows as the client's ground ring for a model-less
  object. Giving them props means a Four Gates rebuild, which also rewrites
  its world.json and collision.bin.
* The Four Gates sanctuary and its beacon stand beyond the served map
  (z -700, the map ends at -360), so the Sanctuary Reliquary's slab is on
  the north road at (14, -318) rather than at the sanctuary itself.
* The hub stones link every region to its graph neighbours and Four Gates;
  Crownwater's seven-stone hub is the busiest and may want a second room.
* Mouths (the far ends of tunnels) are one-way in the sense that a tunnel
  exits to the region it was dug toward; the mouth on that region leads back
  down the same tunnel.
