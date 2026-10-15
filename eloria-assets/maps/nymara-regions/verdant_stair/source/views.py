"""Verdant Stair's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`. Coordinates are design-space (x, z) pairs; heights are
metres above the local ground, not absolute Y, so a camera stays where a
player's eye would be when the terrain is re-sculpted.

Each view is

    (id, panel, (eye_x, eye_z), eye_height, (target_x, target_z),
     target_height, fov, (width, height), shadow_radius, lighting)

Design space is the 192 m frame `region.SCALE` maps onto the real extent, and
the region is written in stair coordinates, so the comment after each camera
gives the (s, c) it sits at - `s` is which terrace, `c` is where along it.
"""
from __future__ import annotations

# Verdant Stair is a wet equatorial jungle under a high sun, not Amberwood's
# low autumn one. Left on the default the captures come back brown, and the
# captures are the only visual evidence a reviewer has.
DAY_LIGHTING = {
    "sun_direction": (-0.34, 0.82, 0.46),
    "sun_color": (1.16, 1.10, 0.90),
    "sky_color": (0.34, 0.48, 0.46),
    "ground_color": (0.06, 0.10, 0.05),
    "fog_color": (0.64, 0.74, 0.70),
    "fog_density": 0.00085,
    "fog_height_falloff": 0.0022,
    "ambient_strength": 0.34,
    "shadow_strength": 0.88,
    "exposure": 1.12,
    "saturation": 1.22,
    "sky_zenith": (0.30, 0.52, 0.66),
    "sky_horizon": (0.72, 0.78, 0.72),
}

GOLDEN_LIGHTING = {
    "sun_direction": (-0.80, 0.24, 0.55),
    "sun_color": (1.48, 1.06, 0.66),
    "sky_color": (0.34, 0.32, 0.28),
    "ground_color": (0.09, 0.09, 0.05),
    "fog_color": (0.76, 0.68, 0.52),
    "fog_density": 0.0030,
    "fog_height_falloff": 0.0042,
    "ambient_strength": 0.36,
    "shadow_strength": 0.86,
    "exposure": 1.10,
    "saturation": 1.28,
    "sky_zenith": (0.24, 0.32, 0.46),
    "sky_horizon": (0.88, 0.66, 0.40),
}

VIEWS = [
    # -- the aerial, framed on the same diagonal the concept is painted on
    # Framed from inside the south-west corner along the stair diagonal, the
    # way the concept is painted. The first attempt sat 780 m up and 450 m
    # outside the map and photographed the region as an object in a void.
    ("00-aerial-overview", "aerial", (-40, 62), 85.0, (30, -40), 25.0, 52,
     (1400, 900), 240, "day"),

    # -- the ten board panels -------------------------------------------
    # 1  the lagoon from the strand: boat, turquoise water, the city above
    ("01-lagoon-landing", 1, (-40.0, 34.0), 3.0, (-26.0, 14.0), 22.0, 52,
     (1280, 820), 60, "day"),      # on the strand, the inlet in the foreground
    # 2  the Grand Stair, looked up from its foot
    ("02-grand-stair", 2, (-6.4, 3.7), 1.7, (3.0, -15.0), 10.0, 50,
     (1080, 940), 34, "day"),            # on the flight's axis, below its foot
    # 3  down into the cenote from its rim
    ("03-cenote", 3, (1.0, -29.0), 2.5, (-6.0, -34.0), 1.0, 62,
     (1080, 940), 34, "day"),         # on the rim; the target is the water, so
                                       # its height is above the shaft floor
    # 4  the root bridge over its gorge, from the bank
    ("04-root-bridge", 4, (22.0, -11.0), 2.2, (30.0, -18.0), 2.0, 56,
     (1280, 820), 40, "day"),                       # the near bank
    # 5  the high rope crossing, from the deck itself
    ("05-rope-bridge", 5, (60.0, 8.0), 3.0, (67.0, 1.0), 17.0, 54,
     (1280, 800), 46, "day"),          # deck height above the gorge floor
    # 6  the canopy village among its banyans
    ("06-canopy-village", 6, (-12.0, -34.0), 3.5, (-22.0, -42.0), 5.0, 58,
     (1180, 900), 32, "day"),                       # s 11 c -23 -> middle
    # 7  the jade gate above its reflecting pool
    ("07-water-shrine", 7, (32.0, -44.0), 2.0, (38.0, -50.0), 4.5, 52,
     (1180, 900), 32, "day"),                # across the pool from the gateway
    # 8  a jungle trail under the understory
    ("08-jungle-trail", 8, (-20.0, -44.0), 1.7, (-31.0, -53.0), 1.7, 58,
     (1080, 900), 26, "day"),        # on the trail itself, looking along it
    # 9  the terraces from the air, the panel's own overview framing
    ("09-terrace-overview", 9, (-14.0, 2.0), 38.0, (34.0, -44.0), 18.0, 52,
     (1400, 860), 170, "day"),
    # 10 the carved relief at reading distance
    ("10-relief-study", 10, (0.5, -1.0), 1.3, (0.0, 0.0), 1.6, 38,
     (1080, 900), 12, "day"),                       # the waygate's own panels

    # -- the rest of the region's places ---------------------------------
    ("11-great-temple", None, (48.0, -62.0), 2.5, (70.0, -66.0), 16.0, 46,
     (1400, 880), 60, "day"),        # from the processional way, looking up
    ("12-temple-court", None, (46.0, -58.0), 3.0, (60.0, -64.0), 4.0, 54,
     (1280, 820), 40, "day"),
    ("13-west-quay", None, (-38.0, 20.0), 3.6, (-29.0, 13.0), 2.0, 56,
     (1280, 800), 34, "day"),
    ("14-waygate", None, (-8.0, 6.0), 2.0, (0.0, 0.0), 3.0, 56,
     (1180, 860), 28, "day"),
    ("15-lower-town", None, (-8.0, -8.0), 4.0, (2.0, -2.0), 2.0, 58,
     (1280, 800), 32, "day"),
    ("16-aqueduct", None, (-14.0, -100.0), 5.0, (-19.0, -111.0), 10.0, 52,
     (1280, 820), 48, "day"),          # the arcade moved onto the north gorge
    ("17-upper-court", None, (42.0, -18.0), 3.2, (52.0, -28.0), 4.0, 52,
     (1280, 800), 34, "day"),
    ("18-east-pass", None, (114.0, -42.0), 3.0, (130.0, -50.0), 3.0, 54,
     (1280, 800), 40, "day"),
    ("19-hanging-gardens", None, (50.0, -2.0), 3.4, (61.0, -9.0), 2.0, 56,
     (1280, 800), 34, "day"),
    ("20-old-terrace", None, (24.0, -70.0), 3.0, (12.0, -80.0), 2.0, 56,
     (1280, 800), 36, "day"),
    ("21-fern-hollow", None, (-38.0, -48.0), 2.4, (-31.0, -55.0), 1.6, 58,
     (1180, 820), 26, "day"),
    ("22-north-glade", None, (-6.0, -72.0), 3.0, (-18.0, -82.0), 2.0, 56,
     (1280, 800), 36, "day"),
    ("23-lotus-pools", None, (22.0, 26.0), 3.4, (33.0, 35.0), 1.0, 56,
     (1280, 800), 36, "day"),
    ("24-mangrove-strand", None, (-12.0, 46.0), 2.6, (0.0, 56.0), 0.8, 56,
     (1280, 800), 34, "day"),
    ("25-cloud-terrace", None, (56.0, -108.0), 4.0, (70.0, -122.0), 2.0, 54,
     (1280, 800), 40, "day"),
    ("26-deep-jungle", None, (14.0, -108.0), 2.0, (2.0, -122.0), 2.0, 60,
     (1180, 820), 28, "day"),
    ("27-stone-ring", None, (-20.0, -98.0), 3.0, (-34.0, -110.0), 2.0, 56,
     (1280, 800), 36, "day"),
    ("28-ridge-shrine", None, (96.0, -60.0), 3.0, (104.0, -68.0), 4.0, 52,
     (1280, 800), 36, "day"),
    ("29-sun-pavilion", None, (50.0, -72.0), 4.0, (62.0, -82.0), 4.0, 54,
     (1280, 800), 36, "day"),
    ("30-east-lookout", None, (6.0, -24.0), 3.0, (17.0, -33.0), 3.0, 56,
     (1280, 800), 34, "day"),

    # -- grounding and traversal checks ----------------------------------
    ("40-spawn-grounding", None, (-9.0, 8.0), 2.2, (0.0, 0.0), 1.6, 58,
     (1180, 780), 30, "day"),
    ("41-stair-head", None, (-4.0, -22.0), 2.2, (3.0, -15.0), 1.6, 58,
     (1180, 780), 30, "day"),
    ("42-riser-face", None, (14.0, -14.0), 3.0, (3.0, -15.0), -6.0, 56,
     (1280, 800), 40, "day"),
    ("43-quay-climb", None, (-22.0, 18.0), 2.4, (-15.0, 23.0), 4.0, 56,
     (1180, 800), 30, "day"),

    # -- golden hour -----------------------------------------------------
    ("50-golden-terraces", None, (-44.0, 20.0), 44.0, (40.0, -50.0), 28.0, 50,
     (1400, 840), 150, "golden"),
    ("51-golden-temple", None, (46.0, -60.0), 4.0, (70.0, -66.0), 16.0, 48,
     (1400, 840), 70, "golden"),
    ("52-golden-lagoon", None, (-26.0, 30.0), 14.0, (-52.0, 24.0), 1.0, 52,
     (1400, 840), 80, "golden"),
]


# Grounded verification views follow the designed processional route.
VIEWS = [
    (name, panel, (-13.1, -10.9), 1.7, (-4.8, -19.2), 1.7,
     60, (1400, 900), 70, "deck!")
    if name == "02-grand-stair" else (name, panel, eye, eh, target, th, fov, size, radius, mode)
    for name, panel, eye, eh, target, th, fov, size, radius, mode in VIEWS
]
VIEWS += [
    ("53-temple-road-arrival", None, (-56, 0), 1.7, (-47.3, 0), 1.7,
     60, (1400, 900), 55, "day!"),
    ("54-middle-landing", None, (3.3, -27.3), 1.7, (13, -29), 1.7,
     60, (1400, 900), 55, "day!"),
    ("55-shrine-ascent", None, (14.7, -30.7), 1.7, (27, -43), 1.7,
     60, (1400, 900), 65, "deck!"),
    ("56-temple-procession", None, (55.3, -39.3), 1.7, (67.3, -51.3), 1.7,
     60, (1400, 900), 70, "deck!"),
    ("57-quarry-road", None, (113.3, -62), 1.7, (118, -58), 2.0,
     60, (1400, 900), 45, "day!"),
]
VIEWS += [
    ("58-market-court", None, (2.33, 6), 1.7, (4.3, -4.3), 3,
     65, (1400, 900), 45, "day!"),
    ("59-cenote-landing", None, (2, -29), 1.7, (-2.1, -34), 1,
     65, (1400, 900), 40, "deck!"),
    ("60-sanctum-entry", None, (75.7, -59), 1.7, (72.45, -64.49), 2,
     65, (1400, 900), 45, "day!"),
]
VIEWS += [
    ("61-western-ravine", None, (-45.75, -72.75), 1.7, (-53.25, -71.25), 1,
     65, (1400, 900), 45, "deck!"),
    ("62-middle-rope-descent", None, (45.0833, -12.4167), 1.7, (43.75, -6.4167), 1,
     65, (1400, 900), 45, "deck!"),
]
FIXED_VIEWS = {view[0] for view in VIEWS if view[-1].endswith("!")}

PANELS = {
    1: ("01-lagoon-landing", "Turquoise lagoon at the cliff foot, boat and landing"),
    2: ("02-grand-stair", "The monumental balustraded stair between terraces"),
    3: ("03-cenote", "Helical stair descending into a green sink pool"),
    4: ("04-root-bridge", "Banyan-root and plank bridge over a gorge"),
    5: ("05-rope-bridge", "Rope suspension crossing high in the canopy"),
    6: ("06-canopy-village", "Stilt huts and plank walkways among great banyans"),
    7: ("07-water-shrine", "Jade gateway and statues above a reflecting pool"),
    8: ("08-jungle-trail", "Narrow trail through tree ferns and understory"),
    9: ("09-terrace-overview", "The stacked terraces, aqueducts and pools from above"),
    10: ("10-relief-study", "Material study: carved jade meander, mossy stone, rope, water"),
}
