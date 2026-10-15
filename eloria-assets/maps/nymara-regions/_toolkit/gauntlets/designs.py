"""The eight gauntlets: route, theme, rosters, bosses and rewards.

Everything a run needs is declared here once. The map builder reads the
route and the theme; the server tool reads the rosters, bosses, caches and
keepers and writes the instance, spawn-group and drop files from them, so a
change to a wave is a change to one line here followed by one tool run.

Kinds of leg (see rooms.py for the geometry):
    hall      a pillared room, the plain fight
    cavern    a wide rough chamber with the region's rock and growth in it
    bridge    a narrow span: the party fights on a front two abreast
    stair     a climb; the fight is at the top landing, on the high ground
    gallery   a long room with alcoves, one of which holds a bonus
    fork      a hub with two gates; the party picks a way, and the way
              not taken seals behind the choice
    court     the boss room, always last

A leg's `advance` is what opens the gate after it: `cleared` (everything in
the room is dead), `time:N` (N seconds after the wave lands, dead or not, so
the route keeps moving), `open` (never barred - a breather). Its `trigger` is
what lands the wave: `enter` (the first participant to step into the room)
or `at_gate` (the moment the gate before it opens, so the room is already
full when the party comes through).

A band is one difficulty of the same route: an a/d bracket, a roster to
draw waves from, a boss. Waves are generated per leg from the roster by the
server tool: every wave is one kind of creature - a pack of badgers, a
swarm of mites, three bears - drawn from round the slice of the roster the
leg's `late` names, in one of the shapes below (WAVE_SHAPES) that the leg's
kind calls for (KIND_SHAPES, or the leg's own `shapes`). Each leg gets one
wave per shape, all of a different kind, and no shape's wave has the kind
the same shape had in the leg before, so a run that picks one wave per leg
(never the kind the last room had) meets a different creature, in a
different number, at every gate. `pressure` on a leg scales how many.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Leg:
    id: str
    name: str
    kind: str
    pressure: float = 1.0          # multiplies the wave size
    advance: str = "cleared"
    trigger: str = "enter"
    gate: str = "portcullis"       # portcullis | bars | roots | ice | jade | slab
    bonus: str = ""                # "node:<Resource>" in a gallery alcove, or "cache"
    plaque: tuple = ()             # (title, text)
    branches: tuple = ()           # fork only: two (id, name, kind) ways
    late: float = 0.0              # 0..1: how far up the roster this leg draws
    shapes: tuple = ()             # WAVE_SHAPES names, one wave each; empty = the kind's (KIND_SHAPES)


# How a wave is drawn: (how many of the kind, against the band's size and
# the leg's pressure; the level each stands at, against the road's; what
# else is in the room). Every wave is one kind. A swarm is more of a smaller
# kind, each a little under the road's level; heavies are a few of a bigger
# kind, each over it; an escort is a pack with one of the next kind up at
# its head, standing over the road's level; a pair is two kinds in equal
# number, the shape a bridge takes so that something comes at the heads and
# something at the knees.
WAVE_SHAPES: dict[str, tuple[float, float, str]] = {
    "pack": (1.0, 1.0, ""),
    "swarm": (1.5, 0.8, ""),
    "heavies": (0.6, 1.25, ""),
    "escort": (0.85, 1.0, "leader"),
    "pair": (1.0, 1.0, "half"),
}
# The shapes a kind of room takes when its leg names none: one wave of each.
KIND_SHAPES: dict[str, tuple[str, ...]] = {
    "hall": ("pack", "escort", "heavies"),
    "cavern": ("swarm", "pack", "escort"),
    "bridge": ("pack", "pair", "swarm"),
    "stair": ("heavies", "pack", "escort"),
    "gallery": ("swarm", "escort", "pack"),
    "fork": ("pack", "heavies", "swarm"),
}
# How far off the leg's slice of the roster a shape draws its kind: a swarm
# from the smaller kinds below it, heavies from the bigger kinds above.
SHAPE_REACH: dict[str, float] = {"swarm": -1.0, "heavies": 1.0}
# The level a wave's leader stands at, against the road's.
LEADER_LEVEL = 1.25


@dataclass(frozen=True)
class Boss:
    creature: str                  # a creatures.txt type; a `boss: 1` one for a bosses.def fight
    name: str
    health: float = 4.0            # inline boss health multiplier (ignored for bosses.def bosses)
    strength: tuple = (0.9, 1.4)
    adds: tuple = ()               # ((creature, count), ...) in the court with it
    block: str = ""                # bosses.def block name when the boss is its own animal
    delay: int = 6                 # seconds after the adds land


@dataclass(frozen=True)
class Band:
    id: str
    label: str
    min_ad: int
    max_ad: int
    roster: tuple                  # ((creature, weight), ...) low to high
    boss: Boss
    size: int = 6                  # base wave size before pressure
    time_limit: int = 2400
    cooldown_hours: int = 6


@dataclass(frozen=True)
class Keeper:
    name: str
    at: object                     # landmark id or (x, z) on the region
    offset: tuple = (4.0, 4.0)
    actor_type: int = 340
    race: str = "greyhaven"        # a people of the region, as npc_dialogue.txt declares them
    greeting: str = ""
    lines: tuple = ()              # (title, text) topics shown by the keeper


@dataclass(frozen=True)
class Theme:
    region: str
    id: str
    name: str
    short: str
    palette: dict
    props: dict
    flavour: str
    legs: tuple
    bands: tuple
    cache: tuple                   # ((item, "min-max", chance), ...) normal lines
    cache_rare: tuple = ()         # ((item, "min-max", chance), ...) rare lines
    keeper: Keeper = None
    max_players: int = 6
    mutators: tuple = (("none", 5), ("frenzy", 2), ("hunted", 2), ("bounty", 1), ("swift", 1))
    lore: tuple = ()               # (title, text) plaques in the staging hall


# ---------------------------------------------------------------- palettes
def _pal(**kw):
    base = {"floor": "packed_earth", "wall": "cliff_rock", "ceil": "cliff_rock", "rock": "cliff_rock",
            "stone": "ashlar", "timber": "timber_dark", "water": "water_pool", "crystal": "amethyst_crystal",
            "node": "amber_resin", "turf": "meadow_grass", "metal": "dark_iron", "cloth": "woven_cloth"}
    base.update(kw)
    return base


AMBERWOOD = _pal(floor="forest_floor", wall="bark_dark", ceil="bark_dark", rock="cliff_rock", stone="ashlar",
                 timber="timber_warm", water="water_pool", crystal="amber_glass", node="amber_resin",
                 turf="meadow_grass")
WHITEHORN = _pal(floor="pale_ashlar", wall="cliff_rock", ceil="glacier_ice", rock="cliff_rock", stone="pale_ashlar",
                 timber="timber_dark", water="water_pool", crystal="glacier_ice", node="whitehorn_silver",
                 turf="snow_pack")
SSARATHI = _pal(floor="verdant_mossy_stone", wall="verdant_carved_jade", ceil="verdant_terrace_stone",
                rock="verdant_wet_limestone", stone="verdant_terrace_stone", timber="timber_dark",
                water="water_lagoon", crystal="verdant_jade", node="verdant_frond", turf="verdant_jungle_floor")
GREY_MOORS = _pal(floor="grey_moor_track", wall="grey_drystone", ceil="grey_bog_timber", rock="grey_moor_granite",
                  stone="grey_carved_stone", timber="grey_bog_timber", water="grey_bog_water", crystal="grey_wisp",
                  node="grey_votive_flame", turf="grey_heather_moor")
CROWNWATER = _pal(floor="cobble_paving", wall="ashlar", ceil="ashlar", rock="cliff_rock", stone="ashlar",
                  timber="timber_grey", water="water_lake", crystal="blue_crystal", node="blue_crystal",
                  turf="shore_shingle")
SUNMANE = _pal(floor="packed_earth", wall="rubble_stone", ceil="timber_warm", rock="cliff_rock", stone="ashlar",
               timber="timber_warm", water="water_pool", crystal="amethyst_crystal", node="amber_resin",
               turf="meadow_grass")
AMETHYST = _pal(floor="amethyst_vault_floor", wall="amethyst_storm_rock", ceil="amethyst_storm_rock",
                rock="amethyst_storm_rock", stone="amethyst_pale_stone", timber="timber_dark", water="water_pool",
                crystal="amethyst_crystal", node="amethyst_crystal", turf="amethyst_barrens_dust")
MANYMOUTH = _pal(floor="packed_earth", wall="rubble_stone", ceil="timber_grey", rock="cliff_rock", stone="ashlar",
                 timber="timber_grey", water="water_lagoon", crystal="blue_crystal", node="amber_resin",
                 turf="verdant_fern_glade")


# ---------------------------------------------------------------- the eight
THEMES: dict[str, Theme] = {}


def _theme(theme: Theme) -> Theme:
    THEMES[theme.region] = theme
    return theme


_theme(Theme(
    region="amberwood", id="amberwood_gauntlet", name="The Resin Road", short="resin",
    palette=AMBERWOOD, props={"kit": "forest_haul", "wayLength": 8.0,
                               "roomFloors": {key: "packed_earth" for key in (
                                   "staging", "undercut", "stump-stair", "twin-hollows-hub",
                                   "twin-hollows-dry-hollow", "twin-hollows-merge", "lantern-walk")}},
    flavour="The charcoal burners cut a road under the forest to move resin in the wet months. "
            "The forest moved in behind them.",
    legs=(
        Leg("undercut", "The Undercut", "hall", pressure=0.8, gate="roots",
            plaque=("The charcoal road", "Burners cut this road so the carts could run under the canopy in "
                                         "the rains. The boars found it before the carts did.")),
        Leg("root-cellar", "The Root Cellar", "cavern", pressure=1.0, gate="roots", late=0.2),
        Leg("sap-bridge", "The Sap Bridge", "bridge", pressure=0.9, gate="bars", late=0.3, advance="time:150"),
        Leg("stump-stair", "The Stump Stair", "stair", pressure=1.0, gate="roots", late=0.45),
        Leg("twin-hollows", "The Twin Hollows", "fork", pressure=1.1, gate="roots", late=0.55,
            branches=(("wet-hollow", "The Wet Hollow", "cavern"), ("dry-hollow", "The Dry Hollow", "hall"))),
        Leg("lantern-walk", "The Lantern Walk", "gallery", pressure=1.2, gate="bars", late=0.75,
            bonus="node:Toadstool", trigger="at_gate"),
        Leg("boar-court", "The Boar King's Court", "court", pressure=1.0, gate="roots", late=1.0),
    ),
    bands=(
        Band("low", "The Resin Road (8-30)", 8, 30,
             roster=(("mossback_badger", 3), ("amberwood_owl", 2), ("sapling_sprite", 2), ("berry_bramble_boar", 3),
                     ("brambleback_boar", 3), ("thornhide_wolf", 2), ("briarhide_wolf", 2), ("amberhart", 1),
                     ("giant_amber_moth", 1)),
             boss=Boss("brambleback_boar", "the Boar King", health=5.0, strength=(0.9, 1.4),
                       adds=(("berry_bramble_boar", 3),))),
        Band("mid", "The Resin Road (24-55)", 24, 55,
             roster=(("thornhide_wolf", 2), ("giant_amber_moth", 2), ("mossbound_stone_golem", 2),
                     ("moonshadow_lynx", 2), ("rootback_boar", 3), ("thornwood_dryad_queen", 1),
                     ("amberwood_great_owl", 1), ("lantern_stag", 1), ("spectral_forest_knight", 1)),
             boss=Boss("boar_king", "the Boar King", block="Boar King of the Resin Road",
                       adds=(("rootback_boar", 2), ("brambleback_boar", 2))), size=6, time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Bones", "6-12", "1"), ("Large Hide", "2-5", "1"),
           ("Wolf Fur", "1-3", "1/2"), ("Berries", "4-8", "1/2")),
    cache_rare=(("Woven Charm", "1", "1/6"), ("Hearthroot", "1-2", "1/4")),
    keeper=Keeper("Old Pyke", "charcoal-camp", (5.0, 3.0), actor_type=377, race="mycelari",
                  greeting="The road under the trees is open again, if you have the stomach for what took it.",
                  lines=(("The Resin Road", "Burners cut it, boars keep it. Go in as a party, and go in through the "
                                            "gate by me; I hold the key to the yard door."),
                         ("The gates", "Each gate along the road is barred until the stretch behind it is quiet. "
                                       "At the twin hollows you choose a way, and the other way seals."),
                         ("The Boar King", "Something old and rooted at the end. It calls its sounder when it "
                                           "bleeds. Bring people who can hold a line."))),
    lore=(("Rules of the road", "One party at a time on each road. Die and you wake outside; leave by a "
                                "waystone and the road counts you out. The court is the end of it."),),
))

_theme(Theme(
    region="whitehorn_range", id="whitehorn_gauntlet", name="The Ice Stair", short="icestair",
    palette=WHITEHORN, props={
        "kit": "ice_mine", "wayLength": 8.0, "bridgeDeck": "rope",
        "clipCoplanar": True, "localBatches": True, "rearDaisStep": True,
        "roomFloors": {"twin-crevasses-blue-crevasse": "glacier_ice",
                       "twin-crevasses-white-crevasse": "snow_pack"},
        "environment": {
            "sky": "none", "backgroundColor": [.025, .04, .065],
            "sun": {"enabled": False},
            "ambient": {"color": [.44, .56, .69], "energy": 1.0},
            "fog": {"enabled": True, "color": [.045, .065, .085], "density": .004},
            "tonemap": {"mode": "filmic", "exposure": 1.2, "white": 3.5}}},
    flavour="A miners' stair up the inside of the glacier, cut for the silver and abandoned to what "
            "lives in the ice.",
    legs=(
        Leg("cascade-cave", "The Cascade Cave", "cavern", pressure=0.8, gate="ice",
            plaque=("The miners' stair", "Two hundred steps were cut into the ice so the silver could come "
                                         "down in winter. The silver still comes down. The miners do not.")),
        Leg("first-riser", "The First Riser", "stair", pressure=0.9, gate="ice", late=0.15),
        Leg("icefall-span", "The Icefall Span", "bridge", pressure=1.0, gate="bars", late=0.3, advance="time:150"),
        Leg("snowline-hall", "The Snowline Hall", "hall", pressure=1.0, gate="ice", late=0.45),
        Leg("twin-crevasses", "The Twin Crevasses", "fork", pressure=1.1, gate="ice", late=0.6,
            branches=(("blue-crevasse", "The Blue Crevasse", "cavern"), ("white-crevasse", "The White Crevasse", "hall"))),
        Leg("last-riser", "The Last Riser", "stair", pressure=1.2, gate="bars", late=0.8, trigger="at_gate",
            bonus="node:Silverleaf"),
        Leg("rime-court", "The Rime Court", "court", pressure=1.0, gate="ice", late=1.0),
    ),
    bands=(
        Band("low", "The Ice Stair (10-35)", 10, 35,
             roster=(("glacier_crab", 3), ("thornhide_wolf", 2), ("whitehorn_yak", 2), ("cobalt_ibex", 2),
                     ("crystal_cave_spider", 2), ("frosthorn_elk", 2), ("glacier_ram", 2), ("whitehorn_ice_ram", 2),
                     ("moonshadow_lynx", 1)),
             boss=Boss("whitehorn_ice_ram", "the Old Ram of the Stair", health=5.0, strength=(0.9, 1.5),
                       adds=(("glacier_ram", 3),))),
        Band("high", "The Ice Stair (28-65)", 28, 65,
             roster=(("moonshadow_lynx", 2), ("glacier_harpy", 3), ("ice_snow_leopard", 3), ("iceback_ursid", 2),
                     ("whitehorn_ice_griffin", 1), ("crystal_polar_bear", 1), ("rimeclaw", 1)),
             boss=Boss("rime_matriarch", "the Rime Matriarch", block="Rime Matriarch",
                       adds=(("ice_snow_leopard", 2), ("glacier_harpy", 2))), time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Frost Distillate", "2-4", "1"), ("Bones", "6-12", "1"),
           ("Bear Fur", "1-2", "1/2"), ("Salt", "1-3", "1/2")),
    cache_rare=(("Riftglass Focus", "1", "1/6"), ("Quartz Lens", "1", "1/4")),
    keeper=Keeper("Hesk Varne", "whitehorn-mine", (5.0, -3.0), actor_type=318, race="votary",
                  greeting="The stair is iced shut to anyone without the key, and I have the key.",
                  lines=(("The Ice Stair", "Silver came down it once. Now the stair is what lives in the ice, "
                                           "one riser at a time, and the court at the top belongs to her."),
                         ("The spans", "The icefall span will not wait for you: what is on it comes off it, "
                                       "or you go on with it still coming."),
                         ("The Matriarch", "A white bear the size of a hut, and old enough to know what a "
                                           "party is. She calls the leopards when she bleeds."))),
    lore=(("Rules of the stair", "One party at a time. The dead wake at the mine mouth. The waystones "
                                 "count you out. The court at the top is the end of it."),),
))

_theme(Theme(
    region="ssarathi_ruins", id="ssarathi_gauntlet", name="The Coil Causeway", short="coil",
    palette=SSARATHI, props={
        "kit": "temple_procession", "wayLength": 8.0, "clipCoplanar": True,
        "localBatches": True, "rearDaisStep": True,
        "roomFloors": {"two-mouths-wet-mouth": "verdant_jungle_floor",
                       "two-mouths-carved-mouth": "verdant_terrace_stone"},
        "environment": {
            "sky": "none", "backgroundColor": [.025, .04, .035], "sun": {"enabled": False},
            "ambient": {"color": [.54, .60, .47], "energy": 1.1},
            "fog": {"enabled": True, "color": [.04, .06, .045], "density": .003},
            "tonemap": {"mode": "filmic", "exposure": 1.25, "white": 3.5}}},
    flavour="A processional causeway under the temple, walked once a year when the sun stood on the "
            "stela. The hatchery kept the rest of the year.",
    legs=(
        Leg("water-gate", "The Water Gate", "hall", pressure=0.8, gate="jade",
            plaque=("The procession", "Once a year the lineage walked the causeway with the sun. The rest of "
                                      "the year the causeway belonged to what they fed.")),
        Leg("lily-causeway", "The Lily Causeway", "bridge", pressure=0.9, gate="bars", late=0.2, advance="time:150"),
        Leg("hatchery", "The Hatchery", "cavern", pressure=1.1, gate="jade", late=0.4),
        Leg("serpent-gallery", "The Serpent Gallery", "gallery", pressure=1.0, gate="jade", late=0.5,
            bonus="node:Lichen"),
        Leg("two-mouths", "The Two Mouths", "fork", pressure=1.1, gate="jade", late=0.65,
            branches=(("wet-mouth", "The Wet Mouth", "cavern"), ("carved-mouth", "The Carved Mouth", "hall"))),
        Leg("sun-stair", "The Sun Stair", "stair", pressure=1.2, gate="bars", late=0.85, trigger="at_gate"),
        Leg("coiled-court", "The Coiled Court", "court", pressure=1.0, gate="jade", late=1.0),
    ),
    bands=(
        Band("mid", "The Coil Causeway (20-50)", 20, 50,
             roster=(("swamp_heron", 2), ("delta_mud_crab", 3), ("canopy_glider", 3), ("saltmarsh_crocodile", 3),
                     ("scalevine_stalker", 2)),
             boss=Boss("saltmarsh_crocodile", "the Broodmother", health=5.0, strength=(0.9, 1.5),
                       adds=(("delta_mud_crab", 4),))),
        Band("high", "The Coil Causeway (40-80)", 40, 80,
             roster=(("saltmarsh_crocodile", 2), ("scalevine_stalker", 4), ("emerald_canopy_dragon", 2),
                     ("sunscale_basilisk", 1)),
             boss=Boss("sunscale_sovereign", "the Sunscale Sovereign", block="Sunscale Sovereign",
                       adds=(("scalevine_stalker", 3),)), time_limit=3000),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Large Hide", "2-4", "1"), ("Small Dragon Scale", "2-5", "1"),
           ("Verdant Tincture", "1-2", "1/2"), ("Bones", "6-12", "1")),
    cache_rare=(("Tempest Focus", "1", "1/6"), ("Attunement Charge", "1-2", "1/4")),
    keeper=Keeper("Ssethis the Doorkeeper", "south-water-gate", (6.0, 4.0), actor_type=357, race="ssarathi",
                  greeting="The causeway is walked by the lineage or by no one. You are not the lineage. Pay "
                           "attention and you may walk it anyway.",
                  lines=(("The Coil Causeway", "It runs under the temple to the court where the sun was kept. "
                                                "The hatchery is on the way. It is always on the way."),
                         ("The mouths", "Two mouths, one court. The wet mouth is shorter and worse."),
                         ("The Sovereign", "A basilisk that has eaten a hundred years of offerings. Do not "
                                           "look for a clever way. There is only the hard one."))),
    lore=(("Rules of the causeway", "One party at a time. The dead wake at the water gate. Waystones count "
                                    "you out. The court is the end of it."),),
))

_theme(Theme(
    region="grey_moors", id="grey_moors_gauntlet", name="The Barrow Run", short="barrow",
    palette=GREY_MOORS, props={
        "kit": "barrow_visitation", "wayLength": 8.0, "clipCoplanar": True,
        "localBatches": True, "rearDaisStep": True, "bridgeDeck": "piles",
        "roomFloors": {"split-barrow-east-passage": "grey_carved_stone",
                       "split-barrow-west-passage": "grey_barrow_turf"},
        "environment": {
            "sky": "none", "backgroundColor": [.025, .03, .034], "sun": {"enabled": False},
            "ambient": {"color": [.43, .47, .50], "energy": 1.05},
            "fog": {"enabled": True, "color": [.04, .05, .055], "density": .004},
            "tonemap": {"mode": "filmic", "exposure": 1.3, "white": 3.5}}},
    flavour="Nine barrows joined under the peat by the people who dug them, so the dead could visit. "
            "They still do.",
    legs=(
        Leg("peat-cut", "The Peat Cut", "gallery", pressure=0.8, gate="slab", bonus="node:Moss",
            plaque=("The joined barrows", "Nine barrows and one road between them under the peat, dug so the "
                                          "families could visit their dead without crossing the moor at night.")),
        Leg("first-barrow", "The First Barrow", "cavern", pressure=1.0, gate="slab", late=0.2),
        Leg("bog-board", "The Bog Board", "bridge", pressure=0.9, gate="bars", late=0.3, advance="time:150"),
        Leg("fifth-chamber", "The Fifth Chamber", "hall", pressure=1.1, gate="slab", late=0.5),
        Leg("split-barrow", "The Split Barrow", "fork", pressure=1.1, gate="slab", late=0.6,
            branches=(("east-passage", "The East Passage", "hall"), ("west-passage", "The West Passage", "cavern"))),
        Leg("reeve-stair", "The Reeve's Stair", "stair", pressure=1.2, gate="bars", late=0.85, trigger="at_gate"),
        Leg("reeve-hall", "The Reeve's Hall", "court", pressure=1.0, gate="slab", late=1.0),
    ),
    bands=(
        Band("low", "The Barrow Run (8-30)", 8, 30,
             roster=(("giant_mole", 3), ("mossback_badger", 2), ("moss_horn_ram", 2), ("briarhide_wolf", 2),
                     ("mossbound_hound", 3), ("moss_armored_hound", 2), ("moor_heron", 1), ("cobalt_ibex", 1),
                     ("frosthorn_elk", 1)),
             boss=Boss("moss_armored_hound", "the Barrow Hound", health=5.0, strength=(0.9, 1.4),
                       adds=(("mossbound_hound", 3),))),
        Band("mid", "The Barrow Run (25-60)", 25, 60,
             roster=(("frosthorn_elk", 2), ("mossbound_stone_golem", 2), ("moorland_dire_wolf", 3),
                     ("moor_wisp_hound", 3), ("spectral_forest_knight", 2)),
             boss=Boss("barrow_reeve", "the Barrow Reeve", block="Barrow Reeve",
                       adds=(("moor_wisp_hound", 3),)), time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Moss", "3-6", "1"), ("Bones", "8-14", "1"),
           ("Wolf Fur", "1-3", "1/2"), ("Slate", "2-4", "1/2")),
    cache_rare=(("Gloam Focus", "1", "1/6"), ("Gloam Wax", "1-2", "1/4")),
    keeper=Keeper("Widow Carrow", "breached-barrows", (6.0, 2.0), actor_type=341, race="greyhaven",
                  greeting="My family dug the road between the barrows. I keep the door. Nobody else wanted to.",
                  lines=(("The Barrow Run", "Under the peat from the first barrow to the ninth. The Reeve keeps "
                                            "the ninth, and the Reeve was a magistrate, so expect to be judged."),
                         ("The bog board", "A plank road over black water. Do not stop to fight everything on "
                                           "it; some of it you outwalk."),
                         ("The Reeve", "A knight of the old moor court, still in his mail, still holding "
                                       "sessions. He calls the hounds when he is hurt."))),
    lore=(("Rules of the run", "One party at a time. The dead wake at the barrow field. Waystones count "
                               "you out. The hall is the end of it."),),
))

_theme(Theme(
    region="crownwater", id="crownwater_gauntlet", name="The Drowned Arcades", short="arcades",
    palette=dict(CROWNWATER, floor="crownwater_mosaic", stone="crownwater_marble",
                 ceil="crownwater_marble", water="crownwater_lagoon", timber="timber_warm"),
    props={"kit": "drowned_customs", "wayLength": 8.0, "materialSet": "crownwater",
           "clipCoplanar": True, "localBatches": True, "rearDaisStep": True,
           "bridgeDeck": "arcaded", "nonBlockingMaterials": ("crownwater_lagoon",),
           "floodRooms": ("customs-arcade", "cistern", "long-arcade", "long-arcade-alcove-1",
                          "two-sluices-hub", "two-sluices-north-sluice",
                          "two-sluices-south-sluice", "two-sluices-merge"),
           "roomFloors": {"two-sluices-south-sluice": "crownwater_sand"},
           "environment": {
               "sky": "none", "backgroundColor": [.025, .045, .05], "sun": {"enabled": False},
               "ambient": {"color": [.45, .57, .59], "energy": 1.15},
               "fog": {"enabled": True, "color": [.045, .075, .08], "density": .003},
               "tonemap": {"mode": "filmic", "exposure": 1.2, "white": 3.5}}},
    flavour="The customs arcades of the old city, flooded to the knee since the crown went under, and "
            "full of what came up with the water.",
    legs=(
        Leg("customs-arcade", "The Customs Arcade", "hall", pressure=0.8, gate="bars",
            plaque=("The arcades", "The customs house kept its arcades dry for three hundred years. The "
                                   "eleventh bell rang, the crown went under, and the arcades went with it.")),
        Leg("bell-walk", "The Bell Walk", "bridge", pressure=0.9, gate="bars", late=0.25, advance="time:150"),
        Leg("cistern", "The Cistern", "cavern", pressure=1.0, gate="portcullis", late=0.4),
        Leg("long-arcade", "The Long Arcade", "gallery", pressure=1.0, gate="portcullis", late=0.5,
            bonus="node:Kelp"),
        Leg("two-sluices", "The Two Sluices", "fork", pressure=1.1, gate="portcullis", late=0.65,
            branches=(("north-sluice", "The North Sluice", "hall"), ("south-sluice", "The South Sluice", "cavern"))),
        Leg("campanile-stair", "The Campanile Stair", "stair", pressure=1.2, gate="bars", late=0.85, trigger="at_gate"),
        Leg("bell-court", "The Bell Court", "court", pressure=1.0, gate="portcullis", late=1.0),
    ),
    bands=(
        Band("low", "The Drowned Arcades (5-30)", 5, 30,
             roster=(("riverglass_otter", 2), ("coralcrest_heron", 2), ("bronze_diving_beetle", 3),
                     ("bronze_tide_crab", 3), ("crystal_shore_crab", 2), ("luminous_manta_ray", 2),
                     ("tidecoil_serpent", 1)),
             boss=Boss("tidecoil_serpent", "the Sluice Serpent", health=4.5, strength=(0.9, 1.4),
                       adds=(("bronze_tide_crab", 3),))),
        Band("mid", "The Drowned Arcades (24-55)", 24, 55,
             roster=(("luminous_manta_ray", 2), ("tidecoil_serpent", 3), ("abyssal_armored_fish", 3),
                     ("saltmarsh_crocodile", 2), ("tidal_crystal_lion", 1)),
             boss=Boss("bell_warden", "the Bell Warden", block="Bell Warden",
                       adds=(("tidecoil_serpent", 3),)), time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Moon Salt", "2-4", "1"), ("Bones", "6-12", "1"),
           ("Bright Feather", "2-4", "1/2"), ("Clear Quartz", "2-4", "1/2")),
    cache_rare=(("Hearthstone Focus", "1", "1/6"), ("Aether Salt", "1-2", "1/4")),
    keeper=Keeper("Tollmaster Quent", "crownwater-customs-hall", (6.0, 3.0), actor_type=307, race="luminous",
                  greeting="The arcades are closed by order of a customs house that no longer exists. I still "
                           "hold the order, and the key.",
                  lines=(("The Drowned Arcades", "The customs road under the old city, knee-deep. The Bell "
                                                 "Warden holds the court at the end and rings for help."),
                         ("The bell walk", "A causeway over the flooded hall. What is in the water climbs out "
                                           "onto it while you cross."),
                         ("The Warden", "An armoured fish the size of a barge that learned to leave the water. "
                                        "It rings, and the serpents answer."))),
    lore=(("Rules of the arcades", "One party at a time. The dead wake at the customs hall. Waystones "
                                   "count you out. The court is the end of it."),),
))

_theme(Theme(
    region="sunmane_steppe", id="sunmane_gauntlet", name="The Red Canyon", short="canyon",
    palette=dict(SUNMANE, floor="sunmane_wash_sand", wall="sunmane_red_sandstone",
                 ceil="sunmane_red_sandstone", rock="sunmane_red_sandstone",
                 stone="sunmane_red_sandstone", water="sunmane_wash_sand", cloth="woven_cloth"),
    props={"kit":"canyon_wash", "wayLength":8.0, "openCanyon":True,
           "materialSet":"sunmane_canyon", "clipCoplanar":True, "localBatches":True,
           "rearDaisStep":True, "bridgeDeck":"rock_spine",
           "environment":{
               "sky":{"topColor":[.27,.43,.58],"horizonColor":[.74,.70,.56],
                      "groundBottomColor":[.25,.19,.13],"groundHorizonColor":[.63,.49,.31]},
               "sun":{"enabled":True,"direction":[.52,-.8,.28],"color":[1,.94,.85],"energy":1.15},
               "ambient":{"color":[.65,.65,.63],"energy":.7,"skyContribution":.3},
               "fog":{"enabled":True,"color":[.65,.51,.35],"density":.0014},
               "tonemap":{"mode":"filmic","exposure":1.0,"white":4.0}}},
    flavour="A dry wash that cuts through the red rock east of the camp. The herds shelter in it and "
            "the things that eat the herds follow them in.",
    legs=(
        Leg("wind-cut", "The Wind Cut", "hall", pressure=0.8, gate="bars",
            plaque=("The wash", "When the rains come the wash runs a horse deep for an hour. The rest of "
                                "the year it is the only shade for a day's ride, and everything knows it.")),
        Leg("horse-cave", "The Horse Cave", "cavern", pressure=1.0, gate="slab", late=0.2),
        Leg("ridge-path", "The Ridge Path", "bridge", pressure=0.9, gate="bars", late=0.3, advance="time:150"),
        Leg("scree-stair", "The Scree Stair", "stair", pressure=1.0, gate="slab", late=0.45),
        Leg("forked-wash", "The Forked Wash", "fork", pressure=1.1, gate="slab", late=0.6,
            branches=(("shade-fork", "The Shade Fork", "cavern"), ("sun-fork", "The Sun Fork", "hall"))),
        Leg("long-wash", "The Long Wash", "gallery", pressure=1.2, gate="bars", late=0.8, trigger="at_gate",
            bonus="node:Seed"),
        Leg("sun-court", "The Sun Court", "court", pressure=1.0, gate="slab", late=1.0),
    ),
    bands=(
        Band("low", "The Red Canyon (1-25)", 1, 25,
             roster=(("red_fox", 3), ("dunrunner", 3), ("suncrest_heron", 2), ("giant_mole", 2),
                     ("golden_plains_horse", 2), ("steppe_aurochs", 1), ("stormmane_lion", 1)),
             boss=Boss("stormmane_lion", "Duskmane", health=4.5, strength=(0.9, 1.4),
                       adds=(("dunrunner", 4),)), size=6, cooldown_hours=4),
        Band("mid", "The Red Canyon (20-50)", 20, 50,
             roster=(("steppe_aurochs", 3), ("stormmane_lion", 3), ("golden_bison", 2), ("plains_griffin", 2),
                     ("sunmane_cat", 2)),
             boss=Boss("duskmane", "Duskmane", block="Duskmane",
                       adds=(("stormmane_lion", 3),)), time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Fox Fur", "2-4", "1"), ("Bones", "6-12", "1"),
           ("Raw Meat", "6-12", "1"), ("Sunleaf", "2-4", "1/2")),
    cache_rare=(("Woven Charm", "1", "1/6"), ("Portal Shard", "1", "1/6")),
    keeper=Keeper("Rider Anse", "Gate_East", (6.0, 4.0), actor_type=333, race="orun",
                  greeting="The wash is not a place. It is a thing that happens to riders who go in without "
                           "counting each other first.",
                  lines=(("The Red Canyon", "A dry wash east of the camp, walled in red rock. Duskmane hunts "
                                            "it, and Duskmane is why the herds come out fewer than they went in."),
                         ("The ridge path", "Narrow. Two abreast. The herons come at your heads and the "
                                            "aurochs come at your knees."),
                         ("Duskmane", "A cat, at first. Bigger each time it is seen. It calls the pride when "
                                      "it is hurt and it is never alone for long."))),
    lore=(("Rules of the wash", "One party at a time. The dead wake at the east gate. Waystones count "
                                "you out. The court is the end of it."),),
))

_theme(Theme(
    region="amethyst_barrens", id="amethyst_gauntlet", name="The Resonant Cut", short="cut",
    palette=AMETHYST, props={"kit": "crystal"},
    flavour="A quarry cut into the singing rock and abandoned when the rock sang back.",
    legs=(
        Leg("mite-cut", "The Mite Cut", "cavern", pressure=0.8, gate="slab",
            plaque=("The quarry", "The lens grinders cut here for songstone until the cut began to answer "
                                  "the hammers. Nobody has quarried since. Everything else has.")),
        Leg("shard-gallery", "The Shard Gallery", "gallery", pressure=1.0, gate="slab", late=0.2,
            bonus="node:Crystal"),
        Leg("hum-bridge", "The Hum Bridge", "bridge", pressure=0.9, gate="bars", late=0.3, advance="time:150"),
        Leg("resonant-hall", "The Resonant Hall", "hall", pressure=1.1, gate="slab", late=0.5),
        Leg("split-seam", "The Split Seam", "fork", pressure=1.1, gate="slab", late=0.65,
            branches=(("bright-seam", "The Bright Seam", "cavern"), ("dark-seam", "The Dark Seam", "hall"))),
        Leg("storm-stair", "The Storm Stair", "stair", pressure=1.2, gate="bars", late=0.85, trigger="at_gate"),
        Leg("prism-court", "The Prism Court", "court", pressure=1.0, gate="slab", late=1.0),
    ),
    bands=(
        Band("low", "The Resonant Cut (5-30)", 5, 30,
             roster=(("amethyst_scorpion", 3), ("crystal_mite", 3), ("crystal_shore_crab", 2), ("cobalt_ibex", 1),
                     ("crystal_carapace_beetle", 2), ("crystal_cave_spider", 3), ("amethyst_stag_beetle", 2),
                     ("barrens_wisp", 2), ("resonant_hound", 2)),
             boss=Boss("resonant_hound", "the Chord", health=5.0, strength=(0.9, 1.5),
                       adds=(("crystal_mite", 4),))),
        Band("high", "The Resonant Cut (25-65)", 25, 65,
             roster=(("resonant_hound", 2), ("crystal_dire_wolf", 3), ("crystal_wing_griffin", 2),
                     ("stormglass_grazer", 3), ("prism_wyrm", 1)),
             boss=Boss("songstone_tyrant", "the Songstone Tyrant", block="Songstone Tyrant",
                       adds=(("crystal_dire_wolf", 3),)), time_limit=2700),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Storm Crystal", "2-5", "1"), ("Bones", "6-12", "1"),
           ("Clear Quartz", "2-4", "1/2"), ("Crystal", "1-2", "1/2")),
    cache_rare=(("Riftglass Focus", "1", "1/5"), ("Attunement Charge", "1-2", "1/4")),
    keeper=Keeper("Grinder Vell", "amethyst-geode-cave-0", (5.0, 3.0), actor_type=326, race="glasswarden",
                  greeting="The cut is shut. I shut it. I can open it for a party that understands why I shut it.",
                  lines=(("The Resonant Cut", "The old songstone quarry. The rock sings when it is struck, and "
                                              "the things in it have learned to strike it."),
                         ("The hum bridge", "A span over the deep cut. Everything on it hums; do not stand "
                                            "still on it long enough to find out why."),
                         ("The Tyrant", "A wyrm that grew up inside the singing rock. It calls the wolves "
                                        "when it is hurt, and it hurts slowly."))),
    lore=(("Rules of the cut", "One party at a time. The dead wake at the quarry mouth. Waystones count "
                               "you out. The court is the end of it."),),
))

_theme(Theme(
    region="manymouth_delta", id="manymouth_gauntlet", name="The Bund Run", short="bund",
    palette=MANYMOUTH, props={"kit": "reed"},
    flavour="The great bund that holds the paddies back from the river, hollow inside where the "
            "sluice houses join, and never quite dry.",
    legs=(
        Leg("sluice-house", "The Sluice House", "hall", pressure=0.8, gate="bars",
            plaque=("The bund", "The bund keeps the river out of the paddies and the sluice houses keep the "
                                "bund honest. Between the houses the bund is hollow. Things like a hollow.")),
        Leg("the-bund", "The Bund", "bridge", pressure=0.9, gate="bars", late=0.2, advance="time:150"),
        Leg("paddy-sump", "The Paddy Sump", "cavern", pressure=1.0, gate="slab", late=0.35),
        Leg("reed-gallery", "The Reed Gallery", "gallery", pressure=1.0, gate="slab", late=0.5,
            bonus="node:Riverflax"),
        Leg("two-channels", "The Two Channels", "fork", pressure=1.1, gate="slab", late=0.65,
            branches=(("deep-channel", "The Deep Channel", "cavern"), ("dry-channel", "The Dry Channel", "hall"))),
        Leg("weir-stair", "The Weir Stair", "stair", pressure=1.2, gate="bars", late=0.85, trigger="at_gate"),
        Leg("floodmaw-pool", "The Floodmaw's Pool", "court", pressure=1.0, gate="slab", late=1.0),
    ),
    bands=(
        Band("low", "The Bund Run (8-30)", 8, 30,
             roster=(("swamp_heron", 2), ("bronze_diving_beetle", 3), ("delta_mud_crab", 3), ("mangrove_crab", 3),
                     ("manymouth_crab", 3), ("saltmarsh_crocodile", 1)),
             boss=Boss("saltmarsh_crocodile", "the Sump Mother", health=5.0, strength=(0.9, 1.4),
                       adds=(("delta_mud_crab", 4),))),
        Band("high", "The Bund Run (30-70)", 30, 70,
             roster=(("manymouth_crab", 2), ("saltmarsh_crocodile", 3), ("delta_crocodile", 3), ("floodmaw", 1)),
             boss=Boss("bund_tyrant", "the Bund Tyrant", block="Bund Tyrant",
                       adds=(("delta_crocodile", 2), ("saltmarsh_crocodile", 2))), time_limit=3000),
    ),
    cache=(("Potion of Great Healing", "2-4", "1"), ("Large Hide", "2-4", "1"), ("Bones", "6-12", "1"),
           ("Mushroom", "4-8", "1/2"), ("Sulfur", "1-3", "1/2")),
    cache_rare=(("Tempest Focus", "1", "1/6"), ("Antidote", "2-3", "1/3")),
    keeper=Keeper("Bund Warden Ilse", "paddy-watchtower", (6.0, 3.0), actor_type=352, race="ssarathi",
                  greeting="The bund is hollow from here to the weir, and what is in the hollow is my "
                           "problem until you make it yours.",
                  lines=(("The Bund Run", "Inside the bund from the sluice house to the weir pool. The "
                                          "Floodmaw took the pool when the river last came over."),
                         ("The bund", "Out on top of it, in the open, with the paddies on one side and the "
                                      "river on the other. The herons do not care which."),
                         ("The Tyrant", "A floodmaw grown fat on a decade of drowned paddies. It calls the "
                                        "crocodiles, and there is no shortage of crocodiles."))),
    lore=(("Rules of the run", "One party at a time. The dead wake at the warden's house. Waystones count "
                               "you out. The pool is the end of it."),),
))


def theme(region: str) -> Theme:
    return THEMES[region]


def all_themes() -> list[Theme]:
    return [THEMES[r] for r in ("amberwood", "whitehorn_range", "ssarathi_ruins", "grey_moors", "crownwater",
                                "sunmane_steppe", "amethyst_barrens", "manymouth_delta")]
