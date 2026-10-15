"""Amethyst Barrens' camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`. Coordinates are design-space (x, z) pairs; heights are
metres above the local ground, not absolute Y - a camera given an absolute Y
ends up underground the moment the terrain changes.

Each row is:
    (id, panel or None, eye_xz, eye_height, target_xz, target_height,
     fov, (width, height), shadow_radius, mode)
"""
from __future__ import annotations

from amberwood import render as RENDER

# Amethyst Barrens is under permanent storm. The toolkit's default capture light
# is Amberwood's warm afternoon sun, which turns a bruised violet basin into a
# pleasant summer field, so the region supplies its own: a cold, low, blue-white
# key with heavy cloud ambient and the crystal doing most of the colouring.
REGION_LIGHTING = {
    "day": RENDER.Lighting(sun_direction=(-0.38, 0.42, 0.82),
                           sun_color=(0.92, 0.86, 1.06),
                           sky_color=(0.20, 0.17, 0.30),
                           ground_color=(0.09, 0.07, 0.05),
                           fog_color=(0.30, 0.27, 0.36),
                           fog_density=0.00110, fog_height_falloff=0.0026,
                           ambient_strength=0.30, shadow_strength=0.72,
                           exposure=1.06, saturation=1.30,
                           sky_zenith=(0.10, 0.09, 0.16),
                           sky_horizon=(0.34, 0.30, 0.38)),
    "golden": RENDER.Lighting(sun_direction=(-0.86, 0.16, 0.48),
                              sun_color=(1.34, 0.84, 0.70),
                              sky_color=(0.26, 0.20, 0.28),
                              ground_color=(0.10, 0.07, 0.05),
                              fog_color=(0.50, 0.38, 0.42),
                              fog_density=0.00260, fog_height_falloff=0.0044,
                              ambient_strength=0.32, shadow_strength=0.80,
                              exposure=1.04, saturation=1.34,
                              sky_zenith=(0.16, 0.13, 0.22),
                              sky_horizon=(0.72, 0.48, 0.42)),
}

VIEWS = [
    # The eye must stay OVER the map. Design-space z=200 is 600 m south of the
    # datum once scaled, which is off the terrain entirely: the region then sits
    # as a small island in the middle of the frame with the boundary rim and the
    # distant backdrop filling everything around it. Kept just inside the south
    # edge, high, looking north across the basin to the massif - the direction
    # the concept aerial looks.
    ("00-aerial-overview", "aerial", (36, 54), 104.0, (36, -62), 6.0, 50,
     (1400, 900), 210, "day"),

    # -- the ten detail-board panels ---------------------------------------
    ("01-barrens-road", 1, (-4.0, -18.0), 1.7, (-16.0, -34.0), 3.0, 58,
     (1180, 760), 48, "day"),
    ("02-observatory", 2, (-26.0, -44.0), 3.0, (-26.0, -68.0), 14.0, 52,
     (1180, 900), 46, "day"),
    ("03-crystal-bridge", 3, (36.0, -66.0), 5.0, (46.0, -58.0), 5.0, 54,
     (1180, 780), 40, "day"),
    ("04-geode-cave", 4, (100.0, -26.0), 2.4, (106.0, -34.0), 4.0, 56,
     (1080, 920), 26, "day"),
    ("05-levitating-shards", 5, (32.0, -32.0), 2.4, (40.0, -40.0), 12.0, 58,
     (1180, 900), 34, "day"),
    ("06-storm-ruin", 6, (64.0, -46.0), 2.6, (72.0, -56.0), 4.0, 55,
     (1180, 800), 34, "day"),
    ("07-resonant-digging", 7, (38.0, -8.0), 3.2, (46.0, -14.0), 2.0, 55,
     (1180, 820), 30, "day"),
    ("08-field-station", 8, (-12.0, -4.0), 1.7, (-8.0, -8.0), 1.6, 52,
     (1180, 820), 26, "day"),
    ("09-cliff-overlook", 9, (80.0, -80.0), 6.0, (40.0, -50.0), 4.0, 50,
     (1400, 800), 150, "day"),
    ("10-material-study", 10, (44.0, -11.0), 1.1, (46.0, -14.0), 0.6, 40,
     (1080, 880), 14, "day"),

    # -- supporting coverage ------------------------------------------------
    ("11-massif", None, (44.0, -86.0), 6.0, (56.0, -110.0), 30.0, 50,
     (1400, 880), 90, "day"),
    ("12-observatory-court", None, (-24.0, -36.0), 2.0, (-24.0, -48.0), 2.0, 56,
     (1180, 800), 30, "day"),
    ("13-arrival", None, (8.0, 12.0), 2.0, (0.0, 0.0), 1.4, 58, (1180, 780), 32, "day"),
    ("14-north-east-coast", None, (100.0, -108.0), 8.0, (118.0, -124.0), 0.0, 54,
     (1280, 780), 60, "day"),
    ("15-stone-ring", None, (94.0, 26.0), 3.0, (102.0, 32.0), 2.0, 54,
     (1180, 780), 30, "day"),
    ("16-watchtower-east", None, (112.0, -10.0), 3.0, (120.0, -16.0), 8.0, 52,
     (1080, 880), 32, "day"),
    ("17-resonant-river", None, (58.0, -30.0), 3.0, (66.0, -18.0), 0.5, 55,
     (1280, 780), 40, "day"),
    ("18-south-road", None, (18.0, 8.0), 2.4, (26.0, 14.0), 1.6, 56,
     (1180, 780), 30, "day"),
    ("19-ruin-basin", None, (46.0, -18.0), 2.6, (54.0, -24.0), 3.0, 55,
     (1180, 780), 32, "day"),
    ("20-massif-foot", None, (40.0, -80.0), 3.0, (50.0, -90.0), 10.0, 54,
     (1180, 820), 44, "day"),
    ("21-geode-north", None, (-32.0, -94.0), 2.6, (-38.0, -102.0), 4.0, 55,
     (1080, 880), 28, "day"),
    ("22-west-road", None, (-34.0, -14.0), 2.4, (-46.0, -20.0), 2.0, 55,
     (1180, 780), 34, "day"),
    ("23-south-east-inlet", None, (100.0, 40.0), 6.0, (116.0, 48.0), 0.0, 54,
     (1280, 780), 50, "day"),
    ("30-spawn-grounding", None, (-8.0, 8.0), 1.7, (2.0, -2.0), 1.6, 58,
     (1180, 780), 30, "day"),
    ("31-bridge-deck", None, (40.0, -87.0), 1.7, (50.0, -87.0), 1.7, 58,
     (1180, 780), 30, "day"),
    ("32-observatory-deck", None, (-23.0, -65.2), 1.7, (-26.0, -65.9), 1.7, 56,
     (1180, 820), 32, "day"),

    # -- storm-light variants ----------------------------------------------
    ("40-golden-massif", None, (30.0, -84.0), 8.0, (56.0, -110.0), 30.0, 50,
     (1400, 820), 90, "golden"),
    ("41-golden-observatory", None, (-8.0, -46.0), 6.0, (-26.0, -68.0), 14.0, 50,
     (1400, 820), 60, "golden"),
    ("42-golden-barrens", None, (10.0, -4.0), 4.0, (46.0, -14.0), 2.0, 52,
     (1400, 820), 70, "golden"),
]

PANELS = {
    1: ("01-barrens-road", "Ochre barrens track between crystal outcrops, "
                           "watchtowers beyond"),
    2: ("02-observatory", "The Glasswarden Observatory and its armillary sphere"),
    3: ("03-crystal-bridge", "Arched bridge with a resonant crystal deck"),
    4: ("04-geode-cave", "Crystal-lined geode cave mouth"),
    5: ("05-levitating-shards", "Levitating amethyst shards over the basin"),
    6: ("06-storm-ruin", "Storm-struck colonnade with a Glasswarden standard"),
    7: ("07-resonant-digging", "Worked crystal digging: crane, scale pan, steps"),
    8: ("08-field-station", "Glasswarden field station: canopy, bench, orbs"),
    9: ("09-cliff-overlook", "Overlook across the barrens toward the massif"),
    10: ("10-material-study", "Material study: amethyst, brass, pale stone, dust"),
}


VIEWS.extend([
 ("24-assay-yard",None,(0,3),1.7,(3.7,-7.7),2.0,58,(1280,820),55,"day!"),
 ("25-packet-jetty",None,(111.6667,33.7451),1.7,(116.0,38.5882),1.7,58,(1280,820),60,"deck!"),
 ("26-survey-bridge",None,(42.7,-57),1.7,(55,-57),1.7,56,(1280,820),80,"deck!"),
 ("27-observatory-stair",None,(-26,-60.3),1.7,(-26,-68),7.0,54,(1280,820),80,"day!"),
 ("28-massif-camp",None,(53.6667,-76.6667),1.7,(57,-83),4.0,68,(1280,820),140,"day!"),
])
FIXED_VIEWS={"24-assay-yard","25-packet-jetty","26-survey-bridge","27-observatory-stair","28-massif-camp"}
REGION_LIGHTING["deck"]=REGION_LIGHTING["day"]


FIXED_VIEWS.update({"08-field-station","31-bridge-deck","32-observatory-deck"})
VIEWS=[(*v[:-1],"deck!" if v[0] in {"31-bridge-deck","32-observatory-deck"} else v[-1]) for v in VIEWS]
