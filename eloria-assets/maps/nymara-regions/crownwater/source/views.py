"""Crownwater's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`, and - via `camera-views.json`, which the build emits from
this same table - by the in-client capture harness
`godot-client/tests/integration/rendered_crownwater.gd`.

One table, two consumers, so an offline preview and a real client frame are
always the same framing and can be compared honestly.

Coordinates are design-space (x, z) pairs, the same 192 m space `region.py` is
written in, so they scale with the region. Heights are metres **above the local
ground**, not absolute Y - a camera given an absolute height ends up underground
the moment the terrain changes.
"""
from __future__ import annotations

# (id, panel, eye_xz, eye_height, target_xz, target_height, fov, size,
#  shadow_radius, lighting)
VIEWS = [
    ("00-aerial-overview", "aerial", (38, -128), 190.0, (38, -38), 8.0, 46,
     (1400, 900), 200, "day"),

    # --- the ten detail-board panels -----------------------------------
    # off the crown-isle causeway spokes, which lie on x + z = 0 and x = 38:
    # the first framing here put the camera directly under a deck
    # In the moat ring at 112.5 degrees - between the 90 and 135 degree spokes,
    # so clear of every causeway, and inside the ring so the pavilions do not
    # stand between the camera and the cathedral.
    # r = 42 in design space, beyond the crown isle plateau's 22.9 m edge
    # falloff: at r = 35 the camera came out standing on the shelf rather than
    # afloat, because the plateau overwrites the moat where the two overlap.
    # The eye is 15 m up rather than at barge height because the crown isle
    # rises 8 m out of the water: from 3 m the island's own edge occludes the
    # cathedral standing on it, which is not a framing the concept has.
    ("01-crown-approach", 1, (30.0, -6.0), 12.0, (38.0, -44.0), 22.0, 46,
     (1280, 860), 70, "day"),
    # Low and just behind the first bollard, sighting along the line to the
    # fifth. Standing height rather than the 3.2 m first tried: from higher up
    # the reach causeway crosses the top of the frame and takes the shot over.
    ("02-harbour-quay", 2, (1.33, -4.07), 1.6, (12.10, -8.02), 0.40, 55,
     (1180, 800), 26, "day"),
    ("03-crown-plaza", 3, (38.0, -19.0), 1.7, (38.0, -31.0), 2.2, 56,
     (1280, 820), 34, "day"),
    # On the spoke deck, at its harbour end, looking along it to the crown isle.
    # The deck is at world y 8.07 over a lagoon floor at about -6.6, so the
    # ground-relative eye height is 16.4 to stand 1.7 m above the deck. Aimed
    # at the deck's far end, not at the cathedral: targeting the far landmark
    # tips the deck out of frame and the shot becomes a distant island.
    # The eye must also be far enough along the span to be over WATER: the
    # causeway's first few metres overlap the harbour islet, and a
    # ground-relative height taken there is measured from the islet, not the
    # lagoon, which put the camera 10 m above the deck instead of 1.7 m.
    ("04-causeway", 4, (12.0, -12.0), 1.7, (16.2, -16.2), 1.2, 54,
     (1280, 800), 46, "deck"),
    ("05-pavilion-islet", 5, (83.0, -30.0), 30.0, (92.0, -38.0), 4.0, 46,
     (1180, 860), 44, "day"),
    # along the walk's own axis (its quay run faces +X), not across it: framed
    # across, the quay's own back wall fills the shot
    ("06-lamp-walk", 6, (-3.5, -10.8), 1.7, (7.0, -10.8), 1.7, 55,
     (1280, 800), 28, "day"),
    # Above the water looking down through it, which is what the concept panel
    # is. This only works because the lagoon material's alpha was lowered to
    # 0.70: the concept's water is clear enough to read the seabed everywhere,
    # and at 0.82 nothing submerged came through at all.
    ("07-sunken-court", 7, (-2.0, -29.6), 9.0, (-2.0, -26.0), -1.05, 40,
     (1180, 860), 26, "day"),
    ("08-garden-isle", 8, (-27.0, -25.0), 32.0, (-16.0, -38.0), 4.0, 48,
     (1180, 860), 42, "day"),
    ("09-dome-overlook", 9, (52.0, -49.0), 26.0, (38.0, -44.0), 24.0, 52,
     (1400, 820), 60, "day"),
    # 1.7 m from Prop_Bollard_harbour_quay_2 at world (23.2, 3.95, -19.2),
    # eye 0.85 m above the apron. The previous framing was a wide quay shot with
    # the bollards a few pixels tall; this is the macro the panel actually is.
    ("10-bollard-macro", 10, (7.33, -6.00), 0.85, (7.73, -6.40), 0.42, 34,
     (1080, 880), 12, "day"),

    # --- further coverage ----------------------------------------------
    ("11-cathedral-front", None, (38.0, -22.0), 2.0, (38.0, -40.0), 14.0, 52,
     (1280, 880), 46, "day"),
    ("12-cathedral-stair", None, (38.0, -26.0), 1.7, (38.0, -35.0), 6.0, 55,
     (1180, 860), 26, "day"),
    ("13-ring-causeway", None, (64.0, -1.0), 4.0, (78.0, -18.0), 5.0, 54,
     (1280, 800), 46, "day"),
    ("14-harbour-market", None, (-4.0, 4.0), 1.7, (-8.0, -1.0), 1.6, 56,
     (1180, 800), 24, "day"),
    ("15-outer-islet", None, (104.0, 8.0), 4.0, (119.0, -4.0), 4.0, 52,
     (1280, 800), 42, "day"),
    ("16-lighthouse", None, (-32.0, -62.0), 5.0, (-43.0, -72.0), 10.0, 50,
     (1180, 860), 40, "day"),
    ("17-plaza-fountain", None, (38.0, -24.0), 1.7, (38.0, -29.0), 1.4, 55,
     (1180, 820), 20, "day"),
    ("18-water-level", None, (20.0, -18.0), 0.8, (38.0, -40.0), 16.0, 50,
     (1400, 800), 64, "day"),
    ("19-campanile-base", None, (50.0, -44.0), 1.7, (54.0, -50.0), 12.0, 55,
     (1180, 880), 26, "day"),
    ("20-spawn-grounding", None, (2.0, 3.0), 1.7, (10.0, -6.0), 1.7, 58,
     (1180, 800), 28, "day"),

    # --- golden hour ----------------------------------------------------
    ("40-golden-approach", None, (30.0, -6.0), 12.0, (38.0, -44.0), 22.0, 46,
     (1400, 820), 74, "golden"),
    ("41-golden-aerial", None, (38, -122), 170.0, (38, -38), 8.0, 46,
     (1400, 900), 190, "golden"),
]

VIEWS += [
    ("21-service-court",None,(0,3),1.7,(-5,3),2.1,62,(1280,850),28,"day!"),
    ("22-customs-ramp",None,(1.3,2.7),1.7,(8,2.7),2.7,60,(1280,850),28,"day!"),
    ("23-undercroft-approach",None,(45,-31),1.7,(46.33,-37),1.5,58,(1280,850),28,"day!"),
    ("24-bridge-landing",None,(12,-12),1.7,(19,-19),1.7,58,(1280,850),55,"deck!"),
    ("25-basilica-procession",None,(38,-31),1.7,(38,-40),9.0,58,(1280,850),50,"day!"),
]
FIXED_VIEWS = {v[0] for v in VIEWS if v[-1].endswith("!")}
# Keep legacy review panel IDs while surveying their compact neighbourhoods.
# The two bridge cameras explicitly stand on the newly surveyed harbour span.
from coastal_plan import map_world
_compact_views=[]
for _id,_panel,_eye,_eh,_target,_th,_fov,_size,_radius,_mode in VIEWS:
    _e=map_world(_eye[0]*3,_eye[1]*3)
    _t=map_world(_target[0]*3,_target[1]*3)
    if _mode.rstrip('!')=='deck':_e,_t=(29,-29),(34,-34)
    _compact_views.append((_id,_panel,(_e[0]/2,_e[1]/2),_eh,
        (_t[0]/2,_t[1]/2),_th,_fov,_size,_radius,_mode))
VIEWS=_compact_views
DAY_LIGHTING = {
    "sun_direction": (0.30,0.84,-0.45), "sun_color": (1.12,1.05,0.95),
    "sky_color": (0.52,0.68,0.78), "ambient_strength": 0.52,
    "fog_color": (0.62,0.80,0.86), "fog_density": 0.00035,
    "fog_height_falloff": 0.0022, "saturation": 1.34,
}
REGION_LIGHTING = {"day":DAY_LIGHTING,"deck":DAY_LIGHTING}

PANELS = {
    1: ("01-crown-approach",
        "The domed palace complex seen across open water from a barge"),
    2: ("02-harbour-quay",
        "Quayside: brass bollards, mooring rope, a moored boat"),
    3: ("03-crown-plaza",
        "Plaza with compass-rose mosaic, fountain and domed buildings"),
    4: ("04-causeway",
        "Long arched causeway over clear shallow water"),
    5: ("05-pavilion-islet",
        "Islet with domed pavilion, planting and stairs down to the water"),
    6: ("06-lamp-walk",
        "Waterfront walk with lamp standards and banner poles"),
    7: ("07-sunken-court",
        "Submerged tiled platform with an inlaid glyph, seen through water"),
    8: ("08-garden-isle",
        "Garden plaza: central fountain, concentric planting beds, palms"),
    9: ("09-dome-overlook",
        "Rooftop view across a gilt-finialled dome to the city beyond"),
    10: ("10-bollard-macro",
         "Macro: brass bollard and rope on a stone quay edge"),
}
