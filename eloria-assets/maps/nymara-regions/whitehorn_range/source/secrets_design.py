"""The Whitehorn Range's secrets: what the ice keeps."""
from secretrooms import Secret

REGION = "whitehorn_range"
NAME = "Whitehorn Range Secrets"
PALETTE = {"floor": "pale_ashlar", "wall": "cliff_rock", "ceil": "glacier_ice", "rock": "cliff_rock",
           "stone": "pale_ashlar", "timber": "timber_dark", "water": "water_pool", "crystal": "glacier_ice",
           "node": "whitehorn_silver", "turf": "snow_pack"}
PROP_PALETTE = {"rock": "cliff_rock", "bark": "bark_dark", "stone": "pale_ashlar", "timber": "timber_dark",
                "ice": "glacier_ice"}

SECRETS = [
    Secret("horn-silver-hollow", "The Silverleaf Hollow", "grotto", "ice_crack", "whitehorn-frozen-cascade-00", (10.0, 8.0),
           resources=(("Silverleaf", 5), ("Salt", 4)),
           note="A hollow behind the frozen cascade where the silverleaf grows out of the wind."),
    Secret("horn-cairn-garden", "The Cairn Garden", "garden", "cairn", "whitehorn-cairn-field-lower_cairns", (10.0, 8.0),
           resources=(("Frost Reed", 4), ("Copper", 4), ("Slate", 3), ("Salt", 3)),
           area=("harvest_speed", 2),
           note="A walled garden under the lower cairns, warmer than the field it hides in."),
    Secret("horn-gate-cache", "The South Gate Cache", "cache", "cellar_hatch", "whitehorn-south-gate", (10.0, -8.0),
           resources=(("Iron Ore", 3), ("Slate", 3)),
           note="The gate's cellar: chest, bench and the ore the gate-keepers trade on the side."),
    Secret("horn-temple-vault", "The Glacier Temple Vault", "vault", "cracked_slab", "whitehorn-glacier-temple", (14.0, 8.0), key="Storage Token",
           texts=(("The snowline", "The snowline is read against stones the votaries set. What is made under the temple is measured before it is trusted, and counts double."),),
           note="The votaries' strongroom under the temple."),
    Secret("horn-ram-pit", "The Ram Pit", "pen", "ice_crack", "whitehorn-rope-bridge-01", (10.0, 8.0),
           creatures=(("glacier_ram", 4), ("whitehorn_yak", 3)),
           note="A crevasse floor where the rangers pen rams for the young to learn horn on."),
    Secret("horn-shrine-school", "The Snowline School", "school", "cracked_slab", "whitehorn-shrine-02", (-10.0, 8.0),
           texts=(("Reading", "The shrine's under-room. Books read three times as fast in the cold quiet."),
                  ("The snowline", "The snowline moved uphill nineteen days in one year. The cascade froze on the twentieth."),
                  ("Passes", "Three passes leave the range, each cut level through the rim. The floor is walkable to the edge; the walls are not.")),
           note="Where the snowline rangers learn the stones."),
    Secret("horn-cascade-spring", "The Cascade Spring", "spring", "ice_crack", "whitehorn-frozen-cascade-01", (-10.0, 8.0),
           note="Behind the second cascade the rock is warm; the votaries call it the range's one kindness."),
    Secret("horn-bridge-butts", "The Rope Bridge Butts", "range", "cellar_hatch", "whitehorn-rope-bridge-00", (10.0, 8.0),
           creatures=(("glacier_crab", 3),),
           note="A gallery under the bridgehead with crabs at the far end."),
    Secret("horn-mine-reliquary", "The Mine Reliquary", "reliquary", "shrine_slab", None, (3.0, 2.0), key="Salt",
           door_map="whitehorn_glacier_temple", door_space="whitehorn_mine.pump_room",
           texts=(("Nineteen days", "The cascade watcher counted nineteen days of the snowline climbing. The aqueduct warden counted twenty."),
                  ("The mine", "The mine was sunk for silver and found ice. The ice was worth more."),
                  ("The temple", "The glacier temple's altar is a block of the glacier. It has not moved in a century; the glacier has.")),
           note="The miners' relic room, opened with glacier salt."),
    Secret("horn-ice-well", "The Ice Well", "nullwell", "ice_crack", "whitehorn-ice-cave", (10.0, 8.0),
           creatures=(("thornhide_wolf", 3),),
           note="Blue ice swallows every spell; the wolves penned here hunt without one."),
    Secret("horn-cairn-focus", "The Cairn Ridge Focus", "focus", "cairn", "whitehorn-cairn-field-cairn_ridge", (10.0, 8.0), key="Iron Rune",
           note="Under the ridge cairns the ether pools; spells cost half."),
    Secret("horn-icebore", "The Ice-Bore", "tunnel", "ice_crack", "whitehorn-shrine-01", (10.0, 8.0),
           resources=(("Salt", 3), ("Frost Reed", 3)),
           links=(("mirrorhold", "secret-mirror-icebore-mouth", "Down into Mirrorhold"),),
           note="A bore the miners drove under the rim, out above Mirrorhold's north post."),
    Secret("horn-waystone", "The Horn Waystone", "waystone", "cairn", "whitehorn-cairn-field-west_watch", (10.0, 8.0), key="Iron Rune",
           links=(("mirrorhold_secrets", "mirror-waystone", "Mirrorhold"),
                  ("amberwood_secrets", "amber-waystone", "Amberwood"),
                  ("amethyst_barrens_secrets", "barrens-waystone", "The Amethyst Barrens")),
           note="Three stones under the west watch cairns. An iron rune wakes them."),
    Secret("horn-temple-eyrie", "The Temple Eyrie", "eyrie", "ice_crack", "whitehorn-glacier-temple", (-14.0, -8.0),
           texts=(("Breath", "Rest here and the breath comes back twice as fast."),
                  ("Cold", "Cold protection is a spell and a cape. The range takes a point of health an hour from anyone with neither.")),
           note="A pocket in the temple's cliff over the glacier."),
    Secret("horn-adit-mouth", "The Adit Mouth", "mouth", "loose_stone", "whitehorn-mine", (-12.0, 10.0),
           links=(("mirrorhold_secrets", "mirror-adit-far", "Down the quarry adit to Mirrorhold"),),
           note="Where Mirrorhold's quarry adit comes up in the range."),
]

# Route-side sites keep their authored approaches; never search to a far ridge.
for secret in SECRETS:
    if not secret.door_map:
        secret.prefer_near = True
    if secret.id == "horn-bridge-butts":
        secret.at,secret.offset=(44.0,-51.0),(0.0,0.0)
    elif secret.id == "horn-ram-pit":
        secret.at,secret.offset=(190.0,-70.0),(0.0,0.0)
    elif secret.id == "horn-temple-vault":
        secret.at,secret.offset=(125.0,-302.0),(0.0,0.0)
    elif secret.id == "horn-temple-eyrie":
        secret.at,secret.offset=(78.0,-314.0),(0.0,0.0)

# The cascade pocket opens beside the watcher path, below the icefall lip.
for secret in SECRETS:
    if secret.id == "horn-cascade-spring":
        secret.at,secret.offset=(114.0,-215.0),(0.0,0.0)
