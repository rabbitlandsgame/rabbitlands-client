"""Grey Moors' camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`. Coordinates are design-space (x, z) pairs; heights are
metres above the local ground, not absolute Y - a camera given an absolute Y
ends up underground the moment the terrain changes.

Each row is:
    (id, panel or None, eye_xz, eye_height, target_xz, target_height,
     fov, (width, height), shadow_radius, mode)

The ten panels are the subjects recorded in `concept-generation-manifest.json`
for this region, in order:

    1 raised causeway        6 abandoned cottage
    2 turf barrow            7 wisp tree
    3 standing stones        8 peat and orchids
    4 bog boardwalk          9 coastal panorama
    5 crypt threshold       10 peat slate heather materials
"""
from __future__ import annotations

from amberwood import render as RENDER

# Grey Moors is under permanent overcast, and that is the whole look. The
# toolkit's default capture light is Amberwood's warm afternoon sun, which
# turns a drowned burial moor into a pleasant heath, so the region supplies its
# own: a weak high key, very strong cloud ambient, soft shadows, and saturation
# pulled below 1 so the heather and the votive flames are the only colour in
# the frame.
REGION_LIGHTING = {
    # Overcast is not the same as bright. The first pass had a white lid and
    # heavy haze, which washed the whole region out to a foggy beach: at 1.7 m
    # nothing 60 m away had any tone left. The key stays weak and the shadows
    # stay soft, but the sky, the ambient and the fog all come down hard.
    "day": RENDER.Lighting(sun_direction=(-0.30, 0.34, 0.62),
                           sun_color=(0.84, 0.86, 0.92),
                           sky_color=(0.32, 0.34, 0.36),
                           ground_color=(0.09, 0.09, 0.08),
                           fog_color=(0.42, 0.45, 0.46),
                           fog_density=0.00115, fog_height_falloff=0.0042,
                           ambient_strength=0.44, shadow_strength=0.42,
                           exposure=0.92, saturation=0.86,
                           sky_zenith=(0.20, 0.22, 0.26),
                           sky_horizon=(0.44, 0.46, 0.47)),
    "golden": RENDER.Lighting(sun_direction=(-0.88, 0.14, 0.44),
                              sun_color=(1.18, 0.92, 0.74),
                              sky_color=(0.44, 0.42, 0.42),
                              ground_color=(0.12, 0.11, 0.09),
                              fog_color=(0.54, 0.46, 0.40),
                              fog_density=0.00120, fog_height_falloff=0.0042,
                              ambient_strength=0.38, shadow_strength=0.66,
                              exposure=0.96, saturation=0.98,
                              sky_zenith=(0.18, 0.18, 0.23),
                              sky_horizon=(0.70, 0.56, 0.45)),
}

VIEWS = [
    # The eye must stay OVER the map: design-space z beyond about 58 is off the
    # terrain, and the region then sits as a small island ringed by backdrop.
    # Kept just inside the south edge, high, looking north across the moor to
    # the barrow ridge - the direction the concept aerial looks.
    ("00-aerial-overview", "aerial", (40, 50), 100.0, (38, -70), 6.0, 50,
     (1400, 900), 210, "day"),

    # -- the ten detail-board panels ---------------------------------------
    # The panel cameras below are derived from where the landmarks actually
    # ended up, not guessed in design space: each eye is a few metres off its
    # subject on the subject's open side. The first pass was hand-written and
    # left most panels framing the middle distance with the subject as a speck.
    # 1: raised causeway - standing on the track, looking along it
    ("01-raised-causeway", 1, (4.0, -6.0), 1.7, (20.0, -26.0), 1.8, 52,
     (1180, 760), 48, "day"),
    # 2: turf barrow - the mound face and its lintelled doorway
    ("02-turf-barrow", 2, (38.8,-77.0), 1.7, (38.0,-80.3), 2.2, 50,
     (1180, 900), 46, "day"),
    # 3: standing stones - inside the central ring, altar in frame
    ("03-standing-stones", 3, (30.9, -30.7), 1.7, (28.0, -33.0), 1.9, 54,
     (1180, 780), 40, "day"),
    # 4: bog boardwalk - standing at the near end of a span, looking across
    ("04-bog-boardwalk", 4, (9.3, -13.3), 1.7, (25.0, -27.0), 1.5, 52,
     (1180, 760), 36, "day"),
    # 5: crypt threshold - square on to a runed doorway with the light in it
    ("05-crypt-threshold", 5, (34.6, 8.4), 1.7, (34.0, 6.0), 1.9, 46,
     (1180, 900), 30, "day"),
    # 6: abandoned cottage - the standing gable and its fallen end
    ("06-abandoned-cottage", 6, (-20.5, 14.0), 1.8, (-24.0, 16.0), 2.0, 52,
     (1180, 780), 38, "day"),
    # 7: wisp tree - the Hanged Oak with its marsh lights below
    ("07-wisp-tree", 7, (32.5, -52.0), 1.8, (22.0, -56.0), 5.5, 52,
     (1180, 860), 44, "day"),
    # 8: peat and orchids - down into a cutting, bank and winch in frame
    ("08-peat-and-orchids", 8, (49.6, -4.3), 2.2, (48.0, -8.0), 1.2, 52,
     (1180, 780), 34, "day"),
    # 9: coastal panorama - from the headland over the corner sea
    ("09-coastal-panorama", 9, (-24.0, 24.0), 9.0, (-54.0, 48.0), -2.0, 64,
     (1400, 800), 150, "day"),
    # 10: materials - close on peat, slate and heather beside a fallen stone
    ("10-material-study", 10, (28.9, -30.9), 0.55, (28.3, -32.4), 0.15, 32,
     (1180, 780), 22, "day"),

    # -- composition and coverage ------------------------------------------
    ("11-barrow-ridge", None, (38.0, -58.0), 3.0, (38.0, -91.0), 8.0, 52,
     (1400, 800), 150, "day"),
    ("12-barrow-court", None, (38.0, -70.0), 2.0, (38.0, -84.0), 3.0, 54,
     (1180, 800), 50, "day"),
    ("13-arrival", None, (-6.0, 8.0), 1.7, (8.0, -10.0), 2.0, 58,
     (1180, 780), 46, "day"),
    ("14-south-west-coast", None, (-18.0, 16.0), 16.0, (-56.0, 50.0), -2.0, 58,
     (1400, 800), 160, "day"),
    ("15-west-moor", None, (-24.0, -40.0), 2.4, (-40.0, -56.0), 3.0, 56,
     (1180, 780), 60, "day"),
    ("16-east-road", None, (70.0, -24.0), 2.0, (90.0, -48.0), 3.0, 56,
     (1180, 780), 70, "day"),
    ("17-north-fen", None, (8.0, -92.0), 2.2, (2.0, -108.0), 3.0, 56,
     (1180, 780), 60, "day"),
    ("18-tower-east", None, (112.0, -56.0), 2.4, (126.0, -63.0), 6.0, 54,
     (1180, 800), 50, "day"),
    ("19-far-east-ring", None, (104.0, -18.0), 2.0, (114.0, -24.0), 2.4, 56,
     (1180, 780), 44, "day"),
    ("20-croft-yard", None, (64.0, -8.0), 1.8, (60.0, -14.0), 2.2, 56,
     (1180, 780), 36, "day"),

    # -- grounding proofs: eye at 1.7 m, the height an actor stands at ------
    ("30-spawn-grounding", None, (-4.0, 4.0), 1.7, (6.0, -8.0), 1.7, 58,
     (1180, 760), 40, "day"),
    ("31-boardwalk-deck", None, (21.3,16.1), 1.7, (43.7,20.9), 1.7, 58,
     (1180, 760), 34, "day"),
    ("32-bridge-deck", None, (48.0, -4.0), 1.7, (60.0, 4.0), 1.7, 58,
     (1180, 760), 34, "day"),

    ("21-road-refuge", None, (-3,5), 1.7, (-5.3,-3.6), 1.5, 58,
     (1280,820), 50, "day!"),
    ("22-refuge-barrow-view", None, (-1,1), 1.7, (38,-91), 4.0, 54,
     (1280,820), 180, "day!"),
    ("23-cove-jetty", None, (-20,24.5), 1.7, (-20,29), 1.7, 54,
     (1280,820), 55, "day!"),
    ("24-coast-beacon", None, (-32,16), 1.7, (-31,20), 1.7, 54,
     (1280,820), 60, "day!"),
    ("25-barrow-crown", None, (42,-83), 1.7, (38,-91), 3.3, 54,
     (1280,820), 65, "day!"),
    # -- the rare break in the cloud ---------------------------------------
    ("40-golden-barrow", None, (38.0, -60.0), 3.0, (38.0, -91.0), 8.0, 52,
     (1400, 800), 150, "golden"),
    ("41-golden-coast", None, (-22.0, 20.0), 12.0, (-54.0, 48.0), -2.0, 58,
     (1400, 800), 150, "golden"),
    ("42-golden-stones", None, (20.0, -26.0), 1.7, (28.0, -33.0), 2.2, 56,
     (1180, 780), 40, "golden"),
]

# Which board panel each capture is compared against, for `make_comparison.py`.
PANELS = {
    1: ("01-raised-causeway", "Laid stone causeway across the wet moor, "
                              "lit markers and standing stones beyond"),
    2: ("02-turf-barrow", "Turf barrow with its lintelled megalithic doorway"),
    3: ("03-standing-stones", "Field of standing stones round a low altar slab"),
    4: ("04-bog-boardwalk", "Plank boardwalk on driven posts over the bog"),
    5: ("05-crypt-threshold", "Runed crypt doorway with warm light behind it"),
    6: ("06-abandoned-cottage", "Abandoned croft: drystone walls, fallen roof"),
    7: ("07-wisp-tree", "The great dead tree, with marsh lights beneath it"),
    8: ("08-peat-and-orchids", "Cut peat banks, winch, and bog cotton in flower"),
    9: ("09-coastal-panorama", "The moor running out to the south-west sea"),
    10: ("10-material-study", "Material study: peat, wet stone, timber, heather"),
}


FIXED_VIEWS={"21-road-refuge","22-refuge-barrow-view","23-cove-jetty",
             "24-coast-beacon","25-barrow-crown","04-bog-boardwalk","31-boardwalk-deck"}
VIEWS=[(*v[:-1],"deck!" if v[0] in {"04-bog-boardwalk","31-boardwalk-deck","23-cove-jetty"} else v[-1])
       for v in VIEWS]

REGION_LIGHTING["deck"]=REGION_LIGHTING["day"]
