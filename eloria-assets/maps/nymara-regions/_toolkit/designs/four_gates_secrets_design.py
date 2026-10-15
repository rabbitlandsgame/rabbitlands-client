"""The Four Gates' secrets: what the city keeps under its flags.

Four Gates is not rebuilt by this pass, so its entrances are declared by
hand in `four-gates/world.json` (`tools/four_gates_secret_doors.py` writes
them from this table); `at` is a city position, and no prop is placed - the
city's own street furniture at each spot is the thing a player uses.
"""
from secretrooms import Secret

REGION = "four_gates"
NAME = "Four Gates Secrets"
PALETTE = {"floor": "cobble_paving", "wall": "ashlar", "ceil": "timber_dark", "rock": "cliff_rock",
           "stone": "ashlar", "timber": "timber_dark", "water": "water_lake", "crystal": "blue_crystal",
           "node": "amber_resin", "turf": "meadow_grass"}
PROP_PALETTE = {"rock": "cliff_rock", "bark": "bark_oak", "stone": "ashlar", "timber": "timber_dark"}

SECRETS = [
    Secret("gates-sunleaf-hollow", "The Sunleaf Hollow", "grotto", "drain_grate", (120.0, 60.0),
           resources=(("Sunleaf", 5), ("Lavender", 4)),
           note="A dry cistern under the east quarter where sunleaf grows toward a grating."),
    Secret("gates-reedworks-garden", "The Reedworks Garden", "garden", "drain_grate", (-140.0, 90.0),
           resources=(("Flax", 4), ("Cotton", 4), ("Winter Wheat", 3), ("Garden Sage", 3)),
           area=("harvest_speed", 2),
           note="Beds under the reedworks where the weavers grow their own."),
    Secret("gates-lantern-cache", "The Lantern Row Cache", "cache", "cellar_hatch", (60.0, -120.0),
           resources=(("Rosemary", 3), ("Clear Quartz", 3)),
           note="A cellar off Lantern Row: chest, bench and the quartz the lamp-makers keep."),
    Secret("gates-deposit-vault", "The Deposit Vault", "vault", "cracked_slab", (-60.0, -60.0), key="Storage Token",
           texts=(("The four keys", "The deposit of the four keys keeps a copy of every account. What is made under it is entered twice and counts double."),),
           note="The bank's own strongroom, under the deposit of the four keys."),
    Secret("gates-otter-pit", "The Otter Pit", "pen", "drain_grate", (200.0, 200.0),
           creatures=(("riverglass_otter", 4), ("mirrorfin_otter", 3)),
           note="A flooded cellar off the south-east quay where the watch trains against otters."),
    Secret("gates-stormglass-school", "The Stormglass School", "school", "cracked_slab", (-200.0, -140.0),
           texts=(("Reading", "The stormglass house's under-room. Books read three times as fast."),
                  ("The city", "Four gates, four roads: north to Mirrorhold, east to the Sunmane Steppe, south to the Ssarathi Ruins, west across the causeway to Crownwater."),
                  ("The ledger", "Everything that walks through a gate is counted. Everything that rolls is weighed. Where the two disagree is where someone is standing.")),
           note="Where the stormglass house teaches its apprentices."),
    Secret("gates-plaza-spring", "The Plaza Spring", "spring", "cracked_slab", (30.0, 30.0),
           note="Under the plaza a warm spring the civic monument was built over."),
    Secret("gates-ferry-butts", "The Ferryman's Butts", "range", "cellar_hatch", (-250.0, 40.0),
           creatures=(("reedhorn_stag", 3),),
           note="A gallery under the ferryman's rest with stags at the far end."),
    Secret("gates-sanctuary-reliquary", "The Sanctuary Reliquary", "reliquary", "shrine_slab", (14.0, -318.0), key="Iron Rune",
           texts=(("The beacon", "The sanctuary beacon was lit for a ship that never came. It is still lit."),
                  ("The ninety candles", "Ninety candles were set for ninety names. One is still burning; nobody will say whose."),
                  ("The crossings", "Every road out of the city is a causeway or a stair, because the city is an island that decided not to be.")),
           note="Under the northern sanctuary, opened with an iron rune."),
    Secret("gates-mirrorsmith-well", "The Mirrorsmith's Well", "nullwell", "drain_grate", (180.0, -60.0),
           creatures=(("crown_antler_stag", 3),),
           note="The forge's cistern drinks every spell; the stags penned there are practice."),
    Secret("gates-civic-focus", "The Civic Focus", "focus", "cracked_slab", (-30.0, 60.0), key="Iron Rune",
           note="Under the civic monument the ether pools; spells cost half."),
    Secret("gates-waystone", "The Gates Waystone", "waystone", "cracked_slab", (0.0, 120.0), key="Iron Rune",
           links=(("mirrorhold_secrets", "mirror-waystone", "Mirrorhold"),
                  ("sunmane_steppe_secrets", "steppe-waystone", "The Sunmane Steppe"),
                  ("ssarathi_ruins_secrets", "ruins-waystone", "The Ssarathi Ruins"),
                  ("crownwater_secrets", "crown-waystone", "Crownwater")),
           note="Four stones under the south avenue. An iron rune wakes them."),
    Secret("gates-wall-eyrie", "The Wall Eyrie", "eyrie", "ivy_arch", (300.0, -200.0),
           texts=(("Breath", "Rest here and the breath comes back twice as fast."),
                  ("Storage", "The civic chest, every wayfarer's cache and every secret's chest open the same storage.")),
           note="A pocket in the east wall's footing."),
    Secret("gates-drain-mouth", "The Drain Mouth", "mouth", "drain_grate", (-300.0, 30.0),
           links=(("crownwater_secrets", "crown-drain-far", "Down the drain to Crownwater"),),
           note="Where Crownwater's drain comes up inside the west gate."),
]
