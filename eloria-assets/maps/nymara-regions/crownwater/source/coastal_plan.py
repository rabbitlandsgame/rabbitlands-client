"""396m Crownwater: inhabited shores around a navigable, open lagoon.

Distances between islands are re-authored; buildings, lamps, furniture and
existing secret rooms keep their human scale. Ferries are deliberate journeys.
Only the eastern stone causeway is a continuous exterior transition.
"""
import math

SERVER_CELLS = 396
SERVER_ORIGIN = (120.0, 120.0)
ANCHORS = {
    "crown_isle": (78,-78), "cathedral": (78,-96),
    "crown_plaza": (78,-51), "crown_campanile": (126,-114),
    "crown_garden": (45,-75), "crown_quay_south": (81,-24),
    "crown_quay_north": (72,-132),
    "pavilion_east": (178,-80), "pavilion_southeast": (155,5),
    "pavilion_south": (70,48), "harbour_isle": (0,0),
    "pavilion_west": (-42,-80), "pavilion_northwest": (0,-165),
    "pavilion_north": (89,-183), "pavilion_northeast": (172,-166),
    "outer_east": (210,-23), "outer_southeast": (153,90),
    "outer_south": (20,88), "outer_southwest": (-73,39),
    "outer_west": (-88,-143), "outer_northwest": (23,-251),
    "outer_north": (151,-239), "outer_northeast": (240,-158),
    "harbour_quay": (27,-21), "harbour_lamp_walk": (6,-33),
    "harbour_market": (-24,9), "customs_house": (23,8),
    "garden_isle": (-42,-80), "garden_fountain": (-42,-80),
    "sunken_court": (-28,-42), "watch_tower": (240,-158),
    "lighthouse": (-73,39),
}

# Each shore has a purpose and a different width/axis. Radius is the usable
# bank, not the full shallow shelf. The working harbour keeps its old footprint.
ISLANDS = {
    "crown_isle": (66,7.6,85,17), "harbour_isle": (42,4.5,55,10),
    "pavilion_east": (31,4.0,43,9), "pavilion_southeast": (26,4.1,38,9),
    "pavilion_south": (26,4.3,38,9), "pavilion_west": (29,4.5,43,10),
    "pavilion_northwest": (26,4.2,40,9), "pavilion_north": (27,4.3,40,9),
    "pavilion_northeast": (29,4.2,41,9),
    "outer_east": (23,4,32,8), "outer_southeast": (21,3.2,32,8),
    "outer_south": (22,4.1,31,8), "outer_southwest": (22,3.4,34,8),
    "outer_west": (23,2.8,33,8), "outer_northwest": (21,3.3,33,8),
    "outer_north": (23,3.8,34,8), "outer_northeast": (24,3.4,35,8),
}
SHORE_AXES = {
    "crown_isle": (1.06,.90,-.15), "harbour_isle": (1.08,.93,.15),
    "pavilion_east": (.90,1.10,.25), "pavilion_west": (1.07,.86,-.35),
    "outer_west": (.80,1.12,-.40), "outer_north": (1.16,.82,.20),
    "outer_northwest": (.78,1.07,.35), "outer_southwest": (1.1,.82,-.5),
    "outer_northeast": (.88,1.08,.40),
}
DOORS = {"basilica-undercroft":(103,-73), "campanile-door":(126,-110),
         "customs-door":(10,8), "cistern-stair":(-42,-72),
         "eleventh-bell-door":(172,-158), "case-room-door":(178,-72),
         "grating-mouth":(70,56)}
# route id -> (standing point, landward start, deck Y). Berths do not overlap.
FERRIES = {
    "north-quay":((145,-263),(145,-246),3.8),
    "north-quay-east":((155,-263),(155,-246),3.8),
    "west-quay":((-108,-145),(-94,-145),2.8),
    "west-quay-south":((-108,-135),(-94,-135),2.8),
    "south-quay":((12,108),(12,95),4.1),
    "south-quay-east":((22,108),(22,95),4.1),
}
EAST_JOIN = (228.5,4.0,-10.5)
HOUSES = [
    ("net-menders",-18,-17,math.pi,7,6), ("ferriers",18,-15,math.pi,7,6),
    ("market-cook",-20,28,math.pi,7,6),
    ("garden-tender",-56,-84,-math.pi/2,6,5),
    ("pearl-factors",190,-86,math.pi/2,7,6),
    ("chart-house",184,-98,0,7,6),
    ("north-packet-crew",141,-232,0,7,6),
    ("west-packet-crew",-88,-152,math.pi/2,7,6),
]

def map_world(x, z):
    """Migration seed only; authored NPC posts and portals supersede it.

    Preserve the harbour, move whole neighbourhoods with their named island,
    and compress open-water travel. This never scales building geometry.
    """
    if -36 <= x <= 38 and -39 <= z <= 32:
        return x,z
    old_centre=(114,-114)
    old={"crown_isle":old_centre}
    inner=["pavilion_east","pavilion_southeast","pavilion_south","harbour_isle",
           "pavilion_west","pavilion_northwest","pavilion_north","pavilion_northeast"]
    outer=["outer_east","outer_southeast","outer_south","outer_southwest",
           "outer_west","outer_northwest","outer_north","outer_northeast"]
    for names,radius,phase in ((inner,162,0),(outer,264,22.5)):
        for i,name in enumerate(names):
            a=math.radians(phase+45*i)
            old[name]=(114+radius*math.cos(a),-114+radius*math.sin(a))
    name=min(old,key=lambda n:math.hypot(x-old[n][0],z-old[n][1]))
    ox,oz=old[name];nx,nz=ANCHORS[name]
    ratio=.68 if name!="harbour_isle" else 1
    return nx+(x-ox)*ratio,nz+(z-oz)*ratio

def map_tile(tile):
    x,z=map_world(tile[0]-174,174-tile[1])
    return [max(0,min(395,math.floor(x+120))),max(0,min(395,math.floor(120-z)))]

# Interaction standing tiles beside the physical props, from the strict
# current collision flood. The prop positions and secret identities stay intact.
SECRET_STANDING_TILES = {'secret-crown-campanile-eyrie': [232, 238],
 'secret-crown-campanile-vault': [253, 220],
 'secret-crown-cathedral-school': [170, 216],
 'secret-crown-cistern-well': [117, 96],
 'secret-crown-court-reliquary': [92, 135],
 'secret-crown-crab-pit': [282, 267],
 'secret-crown-drain': [285, 210],
 'secret-crown-kelp-garden': [174, 69],
 'secret-crown-lake-focus': [285, 107],
 'secret-crown-pavilion-butts': [219, 292],
 'secret-crown-pearl-hollow': [309, 190],
 'secret-crown-warm-spring': [90, 206],
 'secret-crown-waystone': [136, 277]}
