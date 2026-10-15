"""Manymouth Delta's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`, and - via `camera-views.json`, which the build emits from
this same table - by the in-client capture harness `_toolkit/godot_capture.gd`.

One table, two consumers, so an offline preview and a real client frame are
always the same framing and can be compared honestly.

Coordinates are design-space (x, z) pairs, the same 192 m space `region.py` is
written in, so they scale with the region. Heights are metres **above the local
ground**, not absolute Y - a camera given an absolute height ends up underground
the moment the terrain changes. In this region "the local ground" is very often
the channel bed two or three metres under the water, so a camera meant to stand
on a walkway is given the `deck` lighting/height mode and a height measured from
the bed, exactly as Crownwater's causeway shots are.
"""
from __future__ import annotations

# (id, panel, eye_xz, eye_height, target_xz, target_height, fov, size,
#  shadow_radius, lighting)
VIEWS = [
    ("00-aerial-overview", "aerial", (38, -132), 200.0, (38, -38), 6.0, 46,
     (1400, 900), 210, "day"),

    # --- the ten detail-board panels -----------------------------------
    # 1. From a canoe in a mangrove channel, looking out along the water with
    #    root arches either side and the far spires on the horizon. Eye at
    #    0.9 m: this is a seated paddler, not a standing figure.
    ("01-mangrove-channel", 1, (-30.0, -44.0), 0.9, (-46.0, -56.0), 2.0, 58,
     (1280, 860), 34, "day"),
    # 2. The tiered hall from the walkway below it, looking up its west face.
    ("02-tide-hall", 2, (18.0, -11.0), 1.7, (10.0, -20.5), 7.0, 50,
     (1180, 880), 34, "deck"),
    # 3. The boardwalk junction: standing on one arm, sighting across the
    #    others. Panel 3 is a plan-ish three-quarter view, so the eye is high
    #    for a person - on the quay's upper deck rather than the walkway.
    ("03-walkway-junction", 3, (18.0, -11.0), 4.5, (12.0, -16.0), 1.2, 52,
     (1280, 840), 34, "deck"),
    # 4. Under the market hall's barrel, looking along it to the boats beyond.
    ("04-long-market", 4, (5.6, -11.2), 1.7, (3.4, -6.8), 1.6, 56,
     (1280, 840), 30, "deck"),
    # 5. Inside the banyan's roots, on the landing deck.
    # The eye is on the banyan deck itself, which sits (7.5, 4.0) world metres
    # off the anchor - that is 2.5, 1.33 in design space.
    ("05-root-landing", 5, (29.5, -58.67), 1.7, (23.33, -62.67), 6.0, 58,
     (1180, 880), 30, "deck"),
    # 6. Over the floating market from a deck above it, which is the panel's
    #    own elevated three-quarter view.
    ("06-floating-market", 6, (-12.0, -3.0), 3.0, (-15.5, -5.5), -0.4, 56,
     (1280, 860), 30, "deck"),
    # 7. Along the bamboo causeway across the lotus terraces, tower behind.
    ("07-paddy-causeway", 7, (-16.0, -86.0), 1.7, (-4.0, -92.0), 4.0, 54,
     (1280, 840), 40, "day"),
    # 8. Panel 8 is the *interior* of the flooded labyrinth, which is a
    #    separate server map. What this package can show is its threshold, so
    #    the framing is the cut arch from the water in front of it, with the
    #    glyph inlay lit. Recorded honestly as a partial answer to the panel.
    ("08-labyrinth-mouth", 8, (77.0, -0.5), 1.7, (69.0, -3.5), 4.5, 52,
     (1180, 880), 26, "day"),
    # 9. The overlook of panel 9: two figures on a plank deck with the whole
    #    fan beyond. Eye 1.7 m over a deck about 2.4 m up.
    ("09-long-look", 9, (52.0, 6.0), 6.5, (38.0, -38.0), 6.0, 52,
     (1400, 860), 90, "deck"),
    # 10. The material study: bamboo matting, rope and a bronze-headed staff on
    #     a wet deck. A macro, so a narrow field and a very short throw.
    # On the arch approach walkway, 4 m short of the ruin platform, which is
    # where the study is placed. Two metres of throw at 36 degrees is a macro.
    ("10-deck-macro", 10, (36.30, -36.94), 0.95, (36.87, -37.30), 0.28, 36,
     (1080, 880), 10, "deck"),

    # --- further coverage ----------------------------------------------
    ("11-great-arch", None, (24.0, -26.0), 4.0, (38.0, -38.0), 8.0, 50,
     (1400, 860), 70, "day"),
    ("12-arch-platform", None, (38.0, -38.0), 1.7, (27.0, -31.0), 2.0, 55,
     (1280, 860), 40, "deck"),
    ("13-green-temple", None, (86.0, -92.0), 3.0, (99.0, -103.0), 14.0, 50,
     (1280, 880), 60, "day"),
    ("14-temple-stair", None, (92.0, -103.0), 2.0, (99.0, -103.0), 10.0, 54,
     (1180, 880), 32, "day"),
    ("15-town-from-water", None, (24.0, -4.0), 1.2, (11.0, -18.0), 4.0, 52,
     (1280, 840), 44, "day"),
    ("16-stelae-court", None, (68.0, -70.0), 2.0, (76.0, -76.0), 3.0, 54,
     (1180, 860), 28, "day"),
    ("17-open-channel", None, (0.0, -60.0), 1.2, (-24.0, -80.0), 2.0, 52,
     (1400, 820), 70, "day"),
    ("18-sea-reach", None, (-36.0, -100.0), 3.0, (-52.0, -118.0), 1.0, 50,
     (1400, 820), 80, "day"),
    ("19-east-hamlet", None, (117.0, -58.0), 1.7, (121.0, -12.0), 3.0, 54,
     (1180, 840), 30, "deck"),
    ("20-spawn-grounding", None, (12.0, -16.0), 1.7, (18.0, -11.0), 2.0, 58,
     (1180, 800), 30, "deck"),
    ("21-boat-yard", None, (-6.0, 28.0), 1.7, (-43.0, 13.0), 3.0, 55,
     (1180, 840), 26, "deck"),
    ("22-upper-paddy", None, (10.0, -104.0), 3.0, (16.0, -110.0), 2.0, 52,
     (1180, 840), 34, "day"),
    ("23-water-level", None, (28.0, -20.0), 0.7, (38.0, -38.0), 8.0, 50,
     (1400, 800), 66, "day"),

    # --- golden hour ----------------------------------------------------
    ("40-golden-aerial", None, (38, -126), 180.0, (38, -38), 6.0, 46,
     (1400, 900), 200, "golden"),
    ("41-golden-arch", None, (24.0, -26.0), 4.0, (38.0, -38.0), 8.0, 50,
     (1400, 860), 70, "golden"),
    ("42-golden-town", None, (24.0, -4.0), 1.2, (11.0, -18.0), 4.0, 52,
     (1280, 840), 44, "golden"),
]

PANELS = {
    1: ("01-mangrove-channel",
        "Mangrove channel from the bow of a carved canoe, spires beyond"),
    2: ("02-tide-hall",
        "Tiered stilt hall with gilded finial over a plank village"),
    3: ("03-walkway-junction",
        "Boardwalk junction over turquoise shallows, thatched pavilions"),
    4: ("04-long-market",
        "Arched market hall on the walkway, lateen boats alongside"),
    5: ("05-root-landing",
        "Deck built inside the aerial roots of a great banyan"),
    6: ("06-floating-market",
        "Raft of moored canoes under awnings, produce in crates"),
    7: ("07-paddy-causeway",
        "Bamboo causeway across lotus pads and terraced rice"),
    8: ("08-labyrinth-mouth",
        "Flooded ruin with a glowing ring-portal (INTERIOR - this package "
        "ships only its threshold; the chamber is the "
        "manymouth_flooded_labyrinth map)"),
    9: ("09-long-look",
        "Two figures on a plank deck overlooking the whole delta"),
    10: ("10-deck-macro",
         "Macro: woven bamboo, coiled rope, verdigris bronze staff, blossom"),
}

# Verified player views, in world metres. These do not drift with bed height.
WORLD_VIEWS = {
    "02-tide-hall": ((38,3.9,-45),(30,6.8,-61.5)),
    "03-walkway-junction": ((54,6.7,-33),(36,3.4,-48)),
    "04-long-market": ((19.6,3.9,-29.2),(7.4,3.8,-24.8)),
    "05-root-landing": ((86,4.1,-177),(70,7,-188)),
    "06-floating-market": ((-26,5.5,-8),(-46,1,-10)),
    "07-paddy-causeway": ((-44,4.1,-261),(-4,6,-271)),
    "10-deck-macro": ((108.9,1.5,-110.4),(110.5,.83,-111.8)),
    "11-great-arch": ((65,4.3,-46),(114,10,-114)),
    "12-arch-platform": ((112,2.25,-114),(81,3,-93)),
    "13-green-temple": ((258,7,-269),(297,23,-309)),
    "14-temple-stair": ((277,16.6,-289),(297,24,-309)),
}
FIXED_VIEWS = set(WORLD_VIEWS)
