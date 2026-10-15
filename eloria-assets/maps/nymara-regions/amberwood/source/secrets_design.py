"""Amberwood's secrets: what the forest keeps under its roots.

Entrances hang on the region's own landmarks (see world.json `landmarks`)
and the rooms are built by `_toolkit/secretrooms.py`; `secrets_build.py`
composes them onto `amberwood_secrets`.
"""
from secretrooms import Secret

REGION = "amberwood"
NAME = "Amberwood Secrets"
PALETTE = {"floor": "forest_floor", "wall": "bark_dark", "ceil": "bark_dark", "rock": "cliff_rock",
           "stone": "ashlar", "timber": "timber_warm", "water": "water_pool", "crystal": "amber_glass",
           "node": "amber_resin", "turf": "meadow_grass"}
PROP_PALETTE = {"rock": "cliff_rock", "bark": "bark_oak", "stone": "ashlar", "timber": "timber_dark"}

SECRETS = [
    Secret("amber-resin-hollow", "The Resin Hollow", "grotto", "hollow_tree", "hollow-tree", (9.0, 4.0),
           resources=(("Resin", 5), ("Toadstool", 4)),
           note="The old hollow tree is hollow all the way down. Resin weeps from the root walls."),
    Secret("amber-beekeepers-garden", "The Beekeeper's Under-Garden", "garden", "cellar_hatch", "beekeeper", (8.0, -6.0),
           resources=(("Garden Sage", 4), ("Rosemary", 4), ("Hearthroot", 3), ("Sage", 3)),
           area=("harvest_speed", 2),
           note="Herbs the bees want, grown out of the wind. Sage and rosemary a step apart."),
    Secret("amber-charcoal-cache", "The Charcoal Burner's Cache", "cache", "cellar_hatch", "charcoal-camp", (7.0, 6.0),
           resources=(("Coal", 4), ("Bramble", 3)),
           note="A burner's cellar: coal by the sack, a bench, and a chest that opens your storage."),
    Secret("amber-moot-vault", "The Moot Vault", "vault", "cracked_slab", "moot-hall", (0.0, 14.0), key="Storage Token",
           texts=(("The moot's rule", "What is made under the moot is made twice: once in the hands and once in the record. Work here teaches double."),),
           note="The hall's own strongroom. The token of a stored account is the key it accepts."),
    Secret("amber-boar-run", "The Boar Run", "pen", "root_door", "coppice", (-6.0, 8.0), prefer_near=True,
           creatures=(("brambleback_boar", 4), ("berry_bramble_boar", 3)),
           note="A coppice pit where the woodsmen pen boar for the young to learn on."),
    Secret("amber-grove-school", "The Grove Reader's School", "school", "hollow_tree", "deep-grove", (17.0, 10.0), prefer_near=True,
           texts=(("Reading", "A book read here reads three times as fast. Sit; the grove is patient."),
                  ("Threads", "Nine watchers face east. The grove reader says the scar is older than the fire, and that both have a beginning in the same season."),
                  ("The hunt", "A fox on the steppe, a crab in the delta, a rimeclaw in the range: the register's hunting chain, in that order.")),
           note="Where the grove reader keeps the books the moot would rather she did not."),
    Secret("amber-warm-spring", "The Warm Spring", "spring", "loose_stone", "upper-falls", (-10.0, 8.0),
           note="Behind the falls the rock is warm and the water in it heals."),
    Secret("amber-lookout-butts", "The Lookout Butts", "range", "cellar_hatch", "lookout-2", (6.0, -6.0),
           creatures=(("mossback_boar", 3),),
           note="A gallery under the lookout with straw butts and slow boar at the far end."),
    Secret("amber-arch-reliquary", "The Arch Reliquary", "reliquary", "shrine_slab", "great-arch", (19.0, 19.0), key="Resin", prefer_near=True,
           texts=(("The arch", "The great arch was raised over a road that no longer runs under it. The road ran east."),
                  ("The ledger and the spore", "Root's tally and the daybook count the same wagons. Where they differ is where somebody is standing."),
                  ("The watchers", "Nine stones, nine reasons. The eighth reason is that the fire must never be let out.")),
           note="Sealed with resin, opened with resin: the arch's own reliquary."),
    Secret("amber-stone-ring-well", "The Stone Ring Well", "nullwell", "cairn", "stone-ring", (0.0, -10.0),
           creatures=(("thornhide_wolf", 3),),
           note="Inside the ring nothing casts. The wolves penned below do not care."),
    Secret("amber-wayshrine-focus", "The Wayshrine Focus", "focus", "shrine_slab", "wayshrine", (6.0, 0.0), key="Woven Charm",
           note="Under the wayshrine the ether pools; a spell costs half here."),
    Secret("amber-undercut", "The Undercut", "tunnel", "root_door", "boundary-stone", (-8.0, 16.0), prefer_near=True,
           resources=(("Coal", 3), ("Moss", 3)),
           links=(("grey_moors", "secret-moor-undercut-mouth", "Up into the Grey Moors"),),
           note="A charcoal burners' tunnel under the boundary, out onto the moors."),
    Secret("amber-waystone", "The Amber Waystone", "waystone", "loose_stone", "west-forest-arch", (14.0, -17.0), key="Iron Rune", prefer_near=True,
           links=(("whitehorn_range_secrets", "horn-waystone", "The Whitehorn Range"),
                  ("mirrorhold_secrets", "mirror-waystone", "Mirrorhold"),
                  ("grey_moors_secrets", "moor-waystone", "The Grey Moors"),
                  ("westhaven_secrets", "haven-waystone", "Westhaven")),
           note="Four stones for four roads. An iron rune wakes them."),
    Secret("amber-kelp-eyrie", "The Kelp Landing Eyrie", "eyrie", "ivy_arch", "kelp-landing", (10.0, -6.0),
           texts=(("Breath", "Rest here and the breath comes back twice as fast."),
                  ("Storage", "A wayfarer's cache beside every arrival opens the same storage as the civic chest. What you put in at one you take out at any.")),
           note="A cliff pocket over the landing where the kelp cutters rest."),
    # the far mouth of Westhaven's smugglers' run
    Secret("amber-smuggle-mouth", "The Smugglers' Mouth", "mouth", "tide_cave", "harbour", (12.0, 10.0),
           links=(("westhaven_secrets", "haven-smuggle-far", "Down the smugglers' run to Westhaven"),),
           note="Where Westhaven's smugglers come up in Amberwood."),
]
