# The secrets

Every exterior map has a `<region>_secrets` map: its hidden rooms, entered by
*using* a feature of the ground above (a loose stone, a hollow tree, a crack in
the ice), some only with an item in the pack. Inside a secret the client draws
only that secret; the rest of the map, the minimap and the full map stay black.
The rooms come from `_toolkit/secretrooms.py`, the maps from
`_toolkit/secrets_build.py`, the entrances from `_toolkit/secretdoors.py` (or
Sunmane's own kit, or the hand-declared list for Four Gates), and the server's
portals, interactives, spawns, nodes and areas from
`eloria-assets/tools/secret_doors.py` through the continent portal tool and the
content tool's `secrets` stage. `design` tables live in each region's
`source/secrets_design.py`.

## Kinds

| kind | what it gives |
|---|---|
| grotto | richer harvest hollow |
| garden | harvest beds, harvest_speed x2 |
| cache | storage chest + bench beside nodes |
| vault | experience x2, storage, bench |
| pen | training chamber, chosen spawn |
| school | fast_reading x3, lore plaques |
| spring | fast_regeneration x3 |
| range | ranging gallery, slow targets, experience x2 |
| reliquary | lore plaques, keyed |
| nullwell | no_magic, spawn |
| focus | cheap_magic x2 |
| tunnel | passage under the border to a neighbour |
| waystone | hub: stones to other hubs |
| eyrie | cistern, mechanics plaques, fast_regeneration x2 |
| mouth | far end of a neighbour's tunnel |

## Entrances

| prop | what a player reads |
|---|---|
| loose_stone | A loose stone in the rock; something moves behind it. |
| hollow_tree | A hollow tree. The dark inside it goes down, not in. |
| ice_crack | A crack in the ice, wider than it looks, and warm air rising from it. |
| cracked_slab | A cracked flagstone that rings hollow underfoot. |
| reed_hide | A hide of cut reeds, and a plank floor under it where there should be mud. |
| root_door | A knot of roots grown over a door frame. |
| shrine_slab | A shrine slab with fresh scratches where it has been slid aside. |
| well_shaft | A dry well. Handholds have been cut into its shaft. |
| crystal_seam | A seam of crystal that hums at a touch; the rock behind it is thin. |
| drain_grate | An iron drain grate, its bolts drawn. |
| tide_cave | A cave mouth the tide leaves open for an hour a day. |
| cellar_hatch | A cellar hatch under the leaves. |
| cairn | A cairn built over nothing, or over something. |
| chimney | A chimney with no house, still warm. |
| ivy_arch | An arch so grown with vine it reads as hedge. |
| sand_sink | A sink in the sand that never fills. |

## Amberwood Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Resin Hollow** (`amber-resin-hollow`) | grotto | hollow_tree at hollow-tree | - | nodes: Resin x5, Toadstool x4 |
| **The Beekeeper's Under-Garden** (`amber-beekeepers-garden`) | garden | cellar_hatch at beekeeper | - | nodes: Garden Sage x4, Rosemary x4, Hearthroot x3, Sage x3; area: harvest_speed x2 |
| **The Charcoal Burner's Cache** (`amber-charcoal-cache`) | cache | cellar_hatch at charcoal-camp | - | nodes: Coal x4, Bramble x3 |
| **The Moot Vault** (`amber-moot-vault`) | vault | cracked_slab at moot-hall | Storage Token | area: default for its kind; 1 plaques |
| **The Boar Run** (`amber-boar-run`) | pen | root_door at coppice | - | spawn: brambleback_boar x4, berry_bramble_boar x3 |
| **The Grove Reader's School** (`amber-grove-school`) | school | hollow_tree at deep-grove | - | area: default for its kind; 3 plaques |
| **The Warm Spring** (`amber-warm-spring`) | spring | loose_stone at upper-falls | - | area: default for its kind |
| **The Lookout Butts** (`amber-lookout-butts`) | range | cellar_hatch at lookout-2 | - | spawn: mossback_boar x3; area: default for its kind |
| **The Arch Reliquary** (`amber-arch-reliquary`) | reliquary | shrine_slab at great-arch | Resin | 3 plaques |
| **The Stone Ring Well** (`amber-stone-ring-well`) | nullwell | cairn at stone-ring | - | spawn: thornhide_wolf x3; area: default for its kind |
| **The Wayshrine Focus** (`amber-wayshrine-focus`) | focus | shrine_slab at wayshrine | Woven Charm | area: default for its kind |
| **The Undercut** (`amber-undercut`) | tunnel | root_door at boundary-stone | - | nodes: Coal x3, Moss x3; links: grey_moors |
| **The Amber Waystone** (`amber-waystone`) | waystone | loose_stone at west-forest-arch | Iron Rune | links: whitehorn_range_secrets, mirrorhold_secrets, grey_moors_secrets, westhaven_secrets |
| **The Kelp Landing Eyrie** (`amber-kelp-eyrie`) | eyrie | ivy_arch at kelp-landing | - | area: default for its kind; 2 plaques |
| **The Smugglers' Mouth** (`amber-smuggle-mouth`) | mouth | tide_cave at harbour | - | links: westhaven_secrets |

## Mirrorhold Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Reed Cut** (`mirror-reed-cut`) | grotto | reed_hide at lake-north | - | nodes: Reed x5, Clay x4 |
| **The Lens-Grinders' Garden** (`mirror-lens-garden`) | garden | drain_grate at lens-works | - | nodes: Quartz x4, Clear Quartz x4, Moon Salt x3, Storm Crystal x2; area: harvest_speed x2 |
| **The Canal Cache** (`mirror-canal-cache`) | cache | drain_grate at mirrorhold_interiors: cistern_pump_gallery | - | nodes: Clay x3, Reed x3 |
| **The Orrery Vault** (`mirror-orrery-vault`) | vault | cracked_slab at orrery | Storage Token | area: default for its kind; 1 plaques |
| **The East Stair Pit** (`mirror-stair-pit`) | pen | loose_stone at east-stair | - | spawn: frosthorn_elk x3, crown_antler_stag x3 |
| **The Rose Gallery School** (`mirror-rose-school`) | school | cracked_slab at rose-gallery | - | area: default for its kind; 3 plaques |
| **The Basin Spring** (`mirror-basin-spring`) | spring | loose_stone at mirror-basins | - | area: default for its kind |
| **The South Watch Butts** (`mirror-watch-butts`) | range | cellar_hatch at south-watch | - | spawn: reedhorn_stag x3; area: default for its kind |
| **The Citadel Reliquary** (`mirror-citadel-reliquary`) | reliquary | shrine_slab at upper-shrine | Reed | 3 plaques |
| **The Cistern Well** (`mirror-cistern-well`) | nullwell | drain_grate at cistern-yard | - | spawn: riverglass_otter x4; area: default for its kind |
| **The Lens Focus** (`mirror-lens-focus`) | focus | crystal_seam at lens-tower-west | Iron Rune | area: default for its kind |
| **The Quarry Adit** (`mirror-adit`) | tunnel | loose_stone at quarry-shelf | - | nodes: Clear Quartz x3, Slate x3; links: whitehorn_range |
| **The Mirror Waystone** (`mirror-waystone`) | waystone | cracked_slab at plaza | Iron Rune | links: whitehorn_range_secrets, amethyst_barrens_secrets, amberwood_secrets, four_gates_secrets, crownwater_secrets |
| **The Overlook Eyrie** (`mirror-overlook-eyrie`) | eyrie | ivy_arch at overlook | - | area: default for its kind; 2 plaques |
| **The Ice-Bore Mouth** (`mirror-icebore-mouth`) | mouth | ice_crack at north-post | - | links: whitehorn_range_secrets |

## Amethyst Barrens Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Geode Hollow** (`barrens-geode-hollow`) | grotto | crystal_seam at amethyst-geode-cave-1 | - | nodes: Crystal x4, Geode x3, Quartz x3 |
| **The Shard Garden** (`barrens-shard-garden`) | garden | crystal_seam at resonant-crystal-cluster-3 | - | nodes: Stormglass x4, Sulfur x3, Clear Quartz x3, Quartz x3; area: harvest_speed x2 |
| **The Field Station Cache** (`barrens-station-cache`) | cache | cellar_hatch at glasswarden-field-station-1 | - | nodes: Stormglass x3, Crystal x2 |
| **The Observatory Vault** (`barrens-observatory-vault`) | vault | cracked_slab at glasswarden-observatory | Storage Token | area: default for its kind; 1 plaques |
| **The Beetle Pit** (`barrens-beetle-pit`) | pen | loose_stone at amethyst-storm-ruin-0 | - | spawn: crystal_carapace_beetle x4, crystal_mite x4 |
| **The Tower School** (`barrens-tower-school`) | school | cracked_slab at glasswarden-tower-2 | - | area: default for its kind; 3 plaques |
| **The Resonance Spring** (`barrens-resonance-spring`) | spring | crystal_seam at resonance-ring | - | area: default for its kind |
| **The Bridge Butts** (`barrens-bridge-butts`) | range | cellar_hatch at amethyst-crystal-bridge-4 | - | spawn: amethyst_scorpion x3; area: default for its kind |
| **The Massif Reliquary** (`barrens-massif-reliquary`) | reliquary | shrine_slab at the-amethyst-massif | Crystal | 3 plaques |
| **The Storm Well** (`barrens-storm-well`) | nullwell | cracked_slab at amethyst-storm-ruin-3 | - | spawn: crystal_cave_spider x3; area: default for its kind |
| **The Shard Focus** (`barrens-lens-focus`) | focus | crystal_seam at resonant_vault: resonant_vault.lens | Iron Rune | area: default for its kind |
| **The Sap** (`barrens-sap`) | tunnel | sand_sink at amethyst-storm-ruin-3 | - | nodes: Sulfur x3, Flint x3; links: sunmane_steppe |
| **The Barrens Waystone** (`barrens-waystone`) | waystone | cracked_slab at glasswarden-field-station-3 | Iron Rune | links: whitehorn_range_secrets, mirrorhold_secrets, sunmane_steppe_secrets, crownwater_secrets |
| **The Geode Eyrie** (`barrens-cave-eyrie`) | eyrie | crystal_seam at amethyst-geode-cave-2 | - | area: default for its kind; 2 plaques |

## Crownwater Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Pearl Hollow** (`crown-pearl-hollow`) | grotto | tide_cave at crownwater-pavilion-pavilion_east | - | nodes: Pearl x4, Shell x4 |
| **The Kelp Garden** (`crown-kelp-garden`) | garden | drain_grate at crownwater-pavilion-pavilion_south | - | nodes: Kelp x4, Reed x4, Clay x3, Shell x3; area: harvest_speed x2 |
| **The Customs Cache** (`crown-customs-cache`) | cache | drain_grate at drowned_crown: customs_hall.bonded_store | - | nodes: Pearl x2, Kelp x3 |
| **The Campanile Vault** (`crown-campanile-vault`) | vault | cracked_slab at crownwater-campanile | Storage Token | area: default for its kind; 1 plaques |
| **The Crab Pit** (`crown-crab-pit`) | pen | tide_cave at crownwater-pavilion-pavilion_northeast | - | spawn: bronze_tide_crab x4, crystal_shore_crab x3 |
| **The Cathedral School** (`crown-cathedral-school`) | school | cracked_slab at crownwater-cathedral | - | area: default for its kind; 3 plaques |
| **The Crown Spring** (`crown-warm-spring`) | spring | tide_cave at crownwater-pavilion-pavilion_west | - | area: default for its kind |
| **The Pavilion Butts** (`crown-pavilion-butts`) | range | drain_grate at crownwater-pavilion-pavilion_north | - | spawn: river_otter x3; area: default for its kind |
| **The Sunken Court Reliquary** (`crown-court-reliquary`) | reliquary | shrine_slab at crownwater-sunken-court | Shell | 3 plaques |
| **The Cistern Well** (`crown-cistern-well`) | nullwell | drain_grate at crownwater-customs-hall | - | spawn: bronze_diving_beetle x4; area: default for its kind |
| **The Lake Focus** (`crown-lake-focus`) | focus | cracked_slab at crownwater-pavilion-pavilion_southeast | Iron Rune | area: default for its kind |
| **The Crown Drain** (`crown-drain`) | tunnel | drain_grate at crownwater-pavilion-pavilion_east | - | nodes: Clay x3, Reed x3; links: four_gates |
| **The Crown Waystone** (`crown-waystone`) | waystone | cracked_slab at crownwater-pavilion-pavilion_northwest | Iron Rune | links: mirrorhold_secrets, four_gates_secrets, manymouth_delta_secrets, westhaven_secrets, amethyst_barrens_secrets, grey_moors_secrets, ssarathi_ruins_secrets |
| **The Campanile Eyrie** (`crown-campanile-eyrie`) | eyrie | ivy_arch at crownwater-campanile | - | area: default for its kind; 2 plaques |

## Westhaven Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Wrack Hollow** (`haven-wrack-hollow`) | grotto | tide_cave at gullstone-watch | - | nodes: Kelp x5, Shell x4 |
| **The Ropewalk Garden** (`haven-ropewalk-garden`) | garden | cellar_hatch at ropewalk | - | nodes: Riverflax x4, Cotton x4, Flax x3, Verdigris x3; area: harvest_speed x2 |
| **The Bonded Cache** (`haven-bonded-cache`) | cache | cellar_hatch at westhaven_insides: bonded_vaults.bay_b | - | nodes: Iron Ore x3, Verdigris x3 |
| **The Guild Vault** (`haven-guild-vault`) | vault | cracked_slab at guild-hall | Storage Token | area: default for its kind; 1 plaques |
| **The Mole Pit** (`haven-mole-pit`) | pen | drain_grate at mole-bastion | - | spawn: brambleback_boar x4, moss_horn_ram x3 |
| **The Arcade School** (`haven-arcade-school`) | school | cracked_slab at great-arcade | - | area: default for its kind; 3 plaques |
| **The Lamp Rock Spring** (`haven-lamp-spring`) | spring | loose_stone at mole-bastion | - | area: default for its kind |
| **The Shipyard Butts** (`haven-shipyard-butts`) | range | cellar_hatch at shipyard | - | spawn: bronze_tide_crab x3; area: default for its kind |
| **The Cathedral Reliquary** (`haven-cathedral-reliquary`) | reliquary | shrine_slab at cathedral | Shell | 3 plaques |
| **The City Gate Well** (`haven-gate-well`) | nullwell | drain_grate at city-gate | - | spawn: moss_horn_ram x3; area: default for its kind |
| **The Spire Focus** (`haven-spire-focus`) | focus | cracked_slab at high-spire | Iron Rune | area: default for its kind |
| **The Smugglers' Run** (`haven-smuggle`) | tunnel | tide_cave at sea-arch | - | nodes: Shell x3, Kelp x3; links: amberwood |
| **The Haven Waystone** (`haven-waystone`) | waystone | cracked_slab at fish-market | Iron Rune | links: grey_moors_secrets, manymouth_delta_secrets, crownwater_secrets, amberwood_secrets |
| **The Lighthouse Eyrie** (`haven-lighthouse-eyrie`) | eyrie | ivy_arch at great-lighthouse | - | area: default for its kind; 2 plaques |
| **The Peat-Cut Mouth** (`haven-peatcut-mouth`) | mouth | cellar_hatch at upland-farm | - | links: grey_moors_secrets |

## Grey Moors Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Peat Hollow** (`moor-peat-hollow`) | grotto | cairn at grey-peat-working-2 | - | nodes: Peat x5, Bog Iron x4 |
| **The Croft Garden** (`moor-croft-garden`) | garden | cellar_hatch at grey-croft-1 | - | nodes: Cotton x4, Bramble x4, Moss x3, Peat x3; area: harvest_speed x2 |
| **The Boardwalk Cache** (`moor-boardwalk-cache`) | cache | reed_hide at grey-boardwalk-1 | - | nodes: Bog Iron x3, Moss x3 |
| **The Barrow Court Vault** (`moor-court-vault`) | vault | cracked_slab at grey-barrow-court | Storage Token | area: default for its kind; 1 plaques |
| **The Hound Pit** (`moor-hound-pit`) | pen | loose_stone at grey-tower-5 | - | spawn: mossbound_hound x4, moss_armored_hound x3 |
| **The Moor Shrine School** (`moor-shrine-school`) | school | cracked_slab at grey-shrine-1 | - | area: default for its kind; 3 plaques |
| **The Hanged Oak Spring** (`moor-hanged-spring`) | spring | hollow_tree at grey-hanged-oak | - | area: default for its kind |
| **The Stone Ring Butts** (`moor-ring-butts`) | range | cairn at grey-stone-ring-4 | - | spawn: moor_pony x3; area: default for its kind |
| **The West Crypt Reliquary** (`moor-crypt-reliquary`) | reliquary | shrine_slab at grey_moor_barrows: bone_gallery.gallery | Bones | 3 plaques |
| **The Barrow Well** (`moor-barrow-well`) | nullwell | cairn at grey-barrow-1 | - | spawn: briarhide_wolf x3; area: default for its kind |
| **The Wisp Focus** (`moor-wisp-focus`) | focus | cairn at grey-stone-ring-2 | Woven Charm | area: default for its kind |
| **The Peat-Cut** (`moor-peatcut`) | tunnel | reed_hide at grey-peat-working-3 | - | nodes: Peat x3, Cotton x3; links: westhaven |
| **The Moor Waystone** (`moor-waystone`) | waystone | cairn at grey-stone-ring-0 | Iron Rune | links: westhaven_secrets, crownwater_secrets, amberwood_secrets, manymouth_delta_secrets |
| **The Tower Eyrie** (`moor-tower-eyrie`) | eyrie | ivy_arch at grey-tower-3 | - | area: default for its kind; 2 plaques |
| **The Undercut Mouth** (`moor-undercut-mouth`) | mouth | root_door at grey-dead-tree-6 | - | links: amberwood_secrets |
| **The Bund-Run Mouth** (`moor-bund-mouth`) | mouth | reed_hide at grey-boardwalk-5 | - | links: manymouth_delta_secrets |

## Manymouth Delta Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Lotus Hollow** (`delta-lotus-hollow`) | grotto | reed_hide at great-banyan | - | nodes: Lotus x5, Sap x4 |
| **The Paddy Garden** (`delta-paddy-garden`) | garden | reed_hide at paddy-watchtower | - | nodes: Riverflax x4, Thistle x4, Lotus x3, Kelp x3; area: harvest_speed x2 |
| **The Market Cache** (`delta-market-cache`) | cache | cellar_hatch at manymouth_flooded_labyrinth: smugglers_warren.cache | - | nodes: Sap x3, Thistle x3 |
| **The Moot Vault** (`delta-moot-vault`) | vault | cracked_slab at moot-hall | Storage Token | area: default for its kind; 1 plaques |
| **The Crab Pit** (`delta-crab-pit`) | pen | reed_hide at delta-overlook | - | spawn: delta_mud_crab x4, mangrove_crab x3 |
| **The Deck Study School** (`delta-study-school`) | school | cellar_hatch at deck-study | - | area: default for its kind; 3 plaques |
| **The Green Temple Spring** (`delta-temple-spring`) | spring | loose_stone at green-temple | - | area: default for its kind |
| **The East Watch Butts** (`delta-watch-butts`) | range | cellar_hatch at east-watch | - | spawn: swamp_heron x3; area: default for its kind |
| **The Stelae Reliquary** (`delta-stelae-reliquary`) | reliquary | shrine_slab at stelae-court | Shell | 3 plaques |
| **The South Shrine Well** (`delta-shrine-well`) | nullwell | cracked_slab at south-shrine | - | spawn: delta_mud_crab x4; area: default for its kind |
| **The Great Arch Focus** (`delta-arch-focus`) | focus | reed_hide at great-arch | Iron Rune | area: default for its kind |
| **The Bund-Run** (`delta-bund-run`) | tunnel | reed_hide at paddy-watchtower | - | nodes: Riverflax x3, Peat x3; links: grey_moors |
| **The Delta Waystone** (`delta-waystone`) | waystone | cracked_slab at labyrinth-mouth | Iron Rune | links: crownwater_secrets, ssarathi_ruins_secrets, grey_moors_secrets, westhaven_secrets |
| **The Banyan Eyrie** (`delta-banyan-eyrie`) | eyrie | ivy_arch at great-banyan | - | area: default for its kind; 2 plaques |
| **The Root-Run Mouth** (`delta-rootrun-mouth`) | mouth | root_door at great-banyan | - | links: ssarathi_ruins_secrets |

## Verdant Stair Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Cenote Hollow** (`stair-cenote-hollow`) | grotto | ivy_arch at cenote | - | nodes: Watercress x5, Venom Bulb x3 |
| **The Under-Garden** (`stair-hanging-garden`) | garden | ivy_arch at hanging-gardens | - | nodes: Lavender x4, Thistle x4, Sap x3, Watercress x3; area: harvest_speed x2 |
| **The Provisioner's Cache** (`stair-provisioner-cache`) | cache | cellar_hatch at verdant_stair_insides: stair_quarry.sorting | - | nodes: Venom Bulb x2, Lavender x3 |
| **The Great Temple Vault** (`stair-temple-vault`) | vault | cracked_slab at great-temple | Storage Token | area: default for its kind; 1 plaques |
| **The Quarry Pit** (`stair-quarry-pit`) | pen | loose_stone at quarry | - | spawn: canopy_glider x4, leafwing_owl x3 |
| **The Stair-House School** (`stair-house-school`) | school | cracked_slab at stair-house | - | area: default for its kind; 3 plaques |
| **The Water Shrine Spring** (`stair-water-spring`) | spring | loose_stone at water-shrine | - | area: default for its kind |
| **The East Lookout Butts** (`stair-lookout-butts`) | range | cellar_hatch at east-lookout | - | spawn: swamp_heron x3; area: default for its kind |
| **The Ridge Shrine Reliquary** (`stair-ridge-reliquary`) | reliquary | shrine_slab at ridge-shrine | Bright Feather | 3 plaques |
| **The Cenote Well** (`stair-cenote-well`) | nullwell | loose_stone at cenote | - | spawn: moonshadow_lynx x2; area: default for its kind |
| **The Sun Pavilion Focus** (`stair-sun-focus`) | focus | cracked_slab at sun-pavilion | Iron Rune | area: default for its kind |
| **The Culvert** (`stair-culvert`) | tunnel | ivy_arch at boundary-shrine | - | nodes: Watercress x3, Lichen x3; links: ssarathi_ruins |
| **The Stair Waystone** (`stair-waystone`) | waystone | cracked_slab at upper-court | Iron Rune | links: sunmane_steppe_secrets, ssarathi_ruins_secrets |
| **The Summit Eyrie** (`stair-summit-eyrie`) | eyrie | ivy_arch at summit-watch | - | area: default for its kind; 2 plaques |

## Whitehorn Range Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Silverleaf Hollow** (`horn-silver-hollow`) | grotto | ice_crack at whitehorn-frozen-cascade-00 | - | nodes: Silverleaf x5, Salt x4 |
| **The Cairn Garden** (`horn-cairn-garden`) | garden | cairn at whitehorn-cairn-field-lower_cairns | - | nodes: Frost Reed x4, Copper x4, Slate x3, Salt x3; area: harvest_speed x2 |
| **The South Gate Cache** (`horn-gate-cache`) | cache | cellar_hatch at whitehorn-south-gate | - | nodes: Iron Ore x3, Slate x3 |
| **The Glacier Temple Vault** (`horn-temple-vault`) | vault | cracked_slab at whitehorn-glacier-temple | Storage Token | area: default for its kind; 1 plaques |
| **The Ram Pit** (`horn-ram-pit`) | pen | ice_crack at whitehorn-rope-bridge-01 | - | spawn: glacier_ram x4, whitehorn_yak x3 |
| **The Snowline School** (`horn-shrine-school`) | school | cracked_slab at whitehorn-shrine-02 | - | area: default for its kind; 3 plaques |
| **The Cascade Spring** (`horn-cascade-spring`) | spring | ice_crack at whitehorn-frozen-cascade-01 | - | area: default for its kind |
| **The Rope Bridge Butts** (`horn-bridge-butts`) | range | cellar_hatch at whitehorn-rope-bridge-00 | - | spawn: glacier_crab x3; area: default for its kind |
| **The Mine Reliquary** (`horn-mine-reliquary`) | reliquary | shrine_slab at whitehorn_glacier_temple: whitehorn_mine.pump_room | Salt | 3 plaques |
| **The Ice Well** (`horn-ice-well`) | nullwell | ice_crack at whitehorn-ice-cave | - | spawn: thornhide_wolf x3; area: default for its kind |
| **The Cairn Ridge Focus** (`horn-cairn-focus`) | focus | cairn at whitehorn-cairn-field-cairn_ridge | Iron Rune | area: default for its kind |
| **The Ice-Bore** (`horn-icebore`) | tunnel | ice_crack at whitehorn-shrine-01 | - | nodes: Salt x3, Frost Reed x3; links: mirrorhold |
| **The Horn Waystone** (`horn-waystone`) | waystone | cairn at whitehorn-cairn-field-west_watch | Iron Rune | links: mirrorhold_secrets, amberwood_secrets, amethyst_barrens_secrets |
| **The Temple Eyrie** (`horn-temple-eyrie`) | eyrie | ice_crack at whitehorn-glacier-temple | - | area: default for its kind; 2 plaques |
| **The Adit Mouth** (`horn-adit-mouth`) | mouth | loose_stone at whitehorn-mine | - | links: mirrorhold_secrets |

## Ssarathi Ruins Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Scale-Moss Hollow** (`ruins-moss-hollow`) | grotto | root_door at root-arch | - | nodes: Lichen x5, Moss x3 |
| **The Lily Court Garden** (`ruins-lily-garden`) | garden | cracked_slab at lily-court | - | nodes: Lotus x4, Watercress x4, Flint x3, Lichen x3; area: harvest_speed x2 |
| **The Serpent Gate Cache** (`ruins-gate-cache`) | cache | cellar_hatch at serpent-gate | - | nodes: Flint x3, Moss x3 |
| **The Sun Vault Undercroft** (`ruins-vault-of-the-sun`) | vault | cracked_slab at ssarathi_royal_archive: royal_archive.central_archive | Storage Token | area: default for its kind; 1 plaques |
| **The Hatchery Pit** (`ruins-hatchery-pit`) | pen | loose_stone at hatchery-descent | - | spawn: delta_mud_crab x4, canopy_glider x3 |
| **The Ritual Plaza School** (`ruins-plaza-school`) | school | cracked_slab at ritual-plaza | - | area: default for its kind; 3 plaques |
| **The East Falls Spring** (`ruins-falls-spring`) | spring | loose_stone at east-falls | - | area: default for its kind |
| **The West Shrine Butts** (`ruins-shrine-butts`) | range | cellar_hatch at west-shrine | - | spawn: swamp_heron x3; area: default for its kind |
| **The Sun Stela Reliquary** (`ruins-stela-reliquary`) | reliquary | shrine_slab at sun-stela | Flint | 3 plaques |
| **The Cistern Well** (`ruins-cistern-well`) | nullwell | drain_grate at cistern-shaft | - | spawn: saltmarsh_crocodile x2; area: default for its kind |
| **The Great Temple Focus** (`ruins-temple-focus`) | focus | cracked_slab at great-temple | Iron Rune | area: default for its kind |
| **The Root-Run** (`ruins-rootrun`) | tunnel | root_door at undercroft-mouth | - | nodes: Lichen x3, Sap x3; links: manymouth_delta |
| **The Ruins Waystone** (`ruins-waystone`) | waystone | cracked_slab at channel-bridge | Iron Rune | links: four_gates_secrets, verdant_stair_secrets, manymouth_delta_secrets, crownwater_secrets |
| **The East Shrine Eyrie** (`ruins-shrine-eyrie`) | eyrie | ivy_arch at east-shrine | - | area: default for its kind; 2 plaques |
| **The Culvert Mouth** (`ruins-culvert-mouth`) | mouth | drain_grate at north-falls | - | links: verdant_stair_secrets |

## Sunmane Steppe Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Seed Hollow** (`steppe-seed-hollow`) | grotto | sand_sink at (-46, -74) | - | nodes: Seed x5, Wheat x4 |
| **The Well Garden** (`steppe-well-garden`) | garden | well_shaft at (-33, 24) | - | nodes: Sage x4, Flax x4, Wheat x3, Seed x3; area: harvest_speed x2 |
| **The Mill Cache** (`steppe-mill-cache`) | cache | cellar_hatch at (44, 44) | - | nodes: Wheat x3, Copper x3 |
| **The Hall Vault** (`steppe-hall-vault`) | vault | cracked_slab at (-12, -20) | Storage Token | area: default for its kind; 1 plaques |
| **The Fox Pit** (`steppe-fox-pit`) | pen | loose_stone at (64, -58) | - | spawn: red_fox x4, dunrunner x3 |
| **The Caravanserai School** (`steppe-caravan-school`) | school | cellar_hatch at (-48, 12) | - | area: default for its kind; 3 plaques |
| **The Hidden Spring** (`steppe-spring`) | spring | sand_sink at (20, 52) | - | area: default for its kind |
| **The Outpost Butts** (`steppe-outpost-butts`) | range | cellar_hatch at (-54, -54) | - | spawn: dunrunner x3; area: default for its kind |
| **The Barrow Reliquary** (`steppe-barrow-reliquary`) | reliquary | shrine_slab at (-12, -60) | Bones | 3 plaques |
| **The Standing Stone Well** (`steppe-standing-well`) | nullwell | loose_stone at (-44, -30) | - | spawn: golden_plains_horse x3; area: default for its kind |
| **The Banner Focus** (`steppe-banner-focus`) | focus | cracked_slab at (30, 40) | Woven Charm | area: default for its kind |
| **The Steppe Waystone** (`steppe-waystone`) | waystone | loose_stone at (70, -20) | Iron Rune | links: four_gates_secrets, amethyst_barrens_secrets, verdant_stair_secrets |
| **The Dune Eyrie** (`steppe-dune-eyrie`) | eyrie | cairn at (4, -100) | - | area: default for its kind; 2 plaques |
| **The Sap Mouth** (`steppe-sap-mouth`) | mouth | sand_sink at (16, -118) | - | links: amethyst_barrens_secrets |

## Four Gates Secrets

| secret | kind | entrance | key | contents |
|---|---|---|---|---|
| **The Sunleaf Hollow** (`gates-sunleaf-hollow`) | grotto | drain_grate at (120, 60) | - | nodes: Sunleaf x5, Lavender x4 |
| **The Reedworks Garden** (`gates-reedworks-garden`) | garden | drain_grate at (-140, 90) | - | nodes: Flax x4, Cotton x4, Winter Wheat x3, Garden Sage x3; area: harvest_speed x2 |
| **The Lantern Row Cache** (`gates-lantern-cache`) | cache | cellar_hatch at (60, -120) | - | nodes: Rosemary x3, Clear Quartz x3 |
| **The Deposit Vault** (`gates-deposit-vault`) | vault | cracked_slab at (-60, -60) | Storage Token | area: default for its kind; 1 plaques |
| **The Otter Pit** (`gates-otter-pit`) | pen | drain_grate at (200, 200) | - | spawn: riverglass_otter x4, mirrorfin_otter x3 |
| **The Stormglass School** (`gates-stormglass-school`) | school | cracked_slab at (-200, -140) | - | area: default for its kind; 3 plaques |
| **The Plaza Spring** (`gates-plaza-spring`) | spring | cracked_slab at (30, 30) | - | area: default for its kind |
| **The Ferryman's Butts** (`gates-ferry-butts`) | range | cellar_hatch at (-250, 40) | - | spawn: reedhorn_stag x3; area: default for its kind |
| **The Sanctuary Reliquary** (`gates-sanctuary-reliquary`) | reliquary | shrine_slab at (14, -318) | Iron Rune | 3 plaques |
| **The Mirrorsmith's Well** (`gates-mirrorsmith-well`) | nullwell | drain_grate at (180, -60) | - | spawn: crown_antler_stag x3; area: default for its kind |
| **The Civic Focus** (`gates-civic-focus`) | focus | cracked_slab at (-30, 60) | Iron Rune | area: default for its kind |
| **The Gates Waystone** (`gates-waystone`) | waystone | cracked_slab at (0, 120) | Iron Rune | links: mirrorhold_secrets, sunmane_steppe_secrets, ssarathi_ruins_secrets, crownwater_secrets |
| **The Wall Eyrie** (`gates-wall-eyrie`) | eyrie | ivy_arch at (300, -200) | - | area: default for its kind; 2 plaques |
| **The Drain Mouth** (`gates-drain-mouth`) | mouth | drain_grate at (-300, 30) | - | links: crownwater_secrets |

176 secrets in all.
