"""The Sunmane Steppe's secrets: what the grass keeps.

The steppe is not a toolkit region: its entrances are placed by
`settlement.py` from `SECRETS` with the steppe's own kit assets, so `at`
here is a world position inside the server's addressable band
(x -58..133, z -133..58) rather than a landmark id.
"""
from secretrooms import Secret

REGION = "sunmane_steppe"
NAME = "Sunmane Steppe Secrets"
PALETTE = {"floor": "packed_earth", "wall": "rubble_stone", "ceil": "timber_warm", "rock": "cliff_rock",
           "stone": "ashlar", "timber": "timber_warm", "water": "water_pool", "crystal": "amethyst_crystal",
           "node": "amber_resin", "turf": "meadow_grass"}
PROP_PALETTE = {"rock": "cliff_rock", "bark": "bark_oak", "stone": "ashlar", "timber": "timber_warm"}

SECRETS = [
    Secret("steppe-seed-hollow", "The Seed Hollow", "grotto", "sand_sink", (-46.0, -74.0),
           resources=(("Seed", 5), ("Wheat", 4)),
           note="A sink in the grass where the seed-heads fall and nobody follows them."),
    Secret("steppe-well-garden", "The Well Garden", "garden", "well_shaft", (-33.0, 24.0),
           resources=(("Sage", 4), ("Flax", 4), ("Wheat", 3), ("Seed", 3)),
           area=("harvest_speed", 2),
           note="A garden under the dry well where the herd-mothers grow what the horses do not eat."),
    Secret("steppe-mill-cache", "The Mill Cache", "cache", "cellar_hatch", (44.0, 44.0),
           resources=(("Wheat", 3), ("Copper", 3)),
           note="The miller's cellar: a chest, a bench and grain not on the tally."),
    Secret("steppe-hall-vault", "The Hall Vault", "vault", "cracked_slab", (-10.0, -5.0), key="Storage Token",
           texts=(("The sour ground", "The fourth well hummed and was filled. What is made under the hall is made on sweet ground, and counts double."),),
           note="Under the hall, the khan's strongroom."),
    Secret("steppe-fox-pit", "The Fox Pit", "pen", "loose_stone", (64.0, -58.0),
           creatures=(("red_fox", 4), ("dunrunner", 3)),
           note="An outpost cellar where the riders pen foxes for the young to learn on."),
    Secret("steppe-caravan-school", "The Caravanserai School", "school", "cellar_hatch", (-49.0, 5.0),
           texts=(("Reading", "The caravanserai's under-room. Books read three times as fast off the road."),
                  ("The hum", "The well hummed, the crates hum, and the foals will not stand. The salt reader says it is the same hum."),
                  ("The frontier", "The east gate leads nowhere. The roads out are west, north and south.")),
           note="Where the caravan masters teach their drovers the roads."),
    Secret("steppe-spring", "The Hidden Spring", "spring", "sand_sink", (20.0, 52.0),
           note="A warm spring under the south road; the only sweet water the well-digger will vouch for."),
    Secret("steppe-outpost-butts", "The Outpost Butts", "range", "cellar_hatch", (-54.0, -54.0),
           creatures=(("dunrunner", 3),),
           note="A gallery under the west outpost with dunrunners at the far end."),
    Secret("steppe-barrow-reliquary", "The Barrow Reliquary", "reliquary", "shrine_slab", (-12.0, -60.0), key="Bones",
           texts=(("The hum", "The fourth well hummed because it was dug into something that answers."),
                  ("The foals", "Foals born the season the well hummed would not stand. The herd-mother moved the herd; the hum did not follow."),
                  ("The crates", "Shard crates hum on the road south and stop at the border. The shard-hauler has stopped asking why.")),
           note="Under the barrow field, opened with bones as the Orun open a barrow."),
    Secret("steppe-standing-well", "The Standing Stone Well", "nullwell", "loose_stone", (-44.0, -30.0),
           creatures=(("golden_plains_horse", 3),),
           note="Inside the stones nothing casts; the horses penned below are honest work."),
    Secret("steppe-banner-focus", "The Banner Focus", "focus", "cracked_slab", (30.0, 40.0), key="Woven Charm",
           note="Under the banner shrines the ether pools; spells cost half."),
    Secret("steppe-waystone", "The Steppe Waystone", "waystone", "loose_stone", (70.0, -20.0), key="Iron Rune",
           links=(("four_gates_secrets", "gates-waystone", "The Four Gates"),
                  ("amethyst_barrens_secrets", "barrens-waystone", "The Amethyst Barrens"),
                  ("verdant_stair_secrets", "stair-waystone", "The Verdant Stair")),
           note="Three stones by the east caravanserai. An iron rune wakes them."),
    Secret("steppe-dune-eyrie", "The Dune Eyrie", "eyrie", "cairn", (4.0, -100.0),
           texts=(("Breath", "Rest here and the breath comes back twice as fast."),
                  ("Water", "A desert station and a well restore food; each can be used again after five minutes.")),
           note="A pocket under the desert road's first station."),
    Secret("steppe-sap-mouth", "The Sap Mouth", "mouth", "sand_sink", (16.0, -118.0),
           links=(("amethyst_barrens_secrets", "barrens-sap-far", "Down the sap to the Amethyst Barrens"),),
           note="Where the Barrens' sap comes out on the steppe."),
]
