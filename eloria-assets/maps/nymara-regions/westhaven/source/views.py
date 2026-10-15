"""Westhaven's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`, and - via `camera-views.json`, which the build emits from
this same table - by the in-engine capture harness
`_toolkit/godot_capture.gd`.

One table, two consumers, so an offline preview and a real client frame are
always the same framing and can be compared honestly.

Coordinates are design-space (x, z) pairs, the same 192 m space `region.py` is
written in, so they scale with the region. Heights are metres **above the local
ground**, not absolute Y - a camera given an absolute height ends up underground
the moment the terrain changes.

Design space maps to the painting's 8x8 reading grid through `region.cell()`:
design = (u * 24 - 58, v * 24 - 108.24). Every panel framing below is annotated
with the grid cell it is standing in, so a later pass can check a shot against
the painting rather than against somebody's memory of it.
"""
from __future__ import annotations

# (id, panel, eye_xz, eye_height, target_xz, target_height, fov, size,
#  shadow_radius, lighting)
VIEWS = [
    # The aerial. Centred on the playable square rather than on the city, and
    # high enough to hold the whole 576 m, because this is the shot that gets
    # compared against the concept aerial.
    # The eye is offset 0.1 design units *south* of the target rather than
    # sharing its XZ, for two reasons. `capture_views` nudges a coincident
    # target diagonally to avoid a degenerate look-at, and the resulting
    # up-vector rolls the whole aerial 45 degrees. And the offset has to be to
    # the south, so the view direction carries a -Z component and north comes
    # out at the top: offset north instead and the image arrives mirrored,
    # which is worse than useless for comparing against a north-up painting.
    # 200 design units is 600 m at SCALE 3, the distance a 52-degree field
    # needs to just hold the 576 m square.
    ("00-aerial-overview", "aerial", (38.0, -11.9), 200.0, (38.0, -12.0), 0.0,
     52, (1400, 1400), 340, "day"),

    # --- the ten detail-board panels -----------------------------------
    # Panel 1: the arched span over the west inlet, seen from the quayside
    # looking west. Eye on the quay at grid (1.55, 4.45), subject at (1.00,
    # 4.05). Standing height: the panel is a ground-level view up at the arch.
    ("01-harbour-gate", 1, (-20.8, -1.4), 1.7, (-34.0, -11.0), 14.0, 52,
     (1280, 880), 44, "day"),
    # Panel 2: the great lighthouse on Lamp Rock, from the seaward side where
    # the surf breaks. Eye is on the rock's own western shoulder at grid
    # (6.10, 6.05), 6 m up, so the tower stands clear of its own crown.
    # On Lamp Rock's south-west shoulder, low, looking up the slope at the
    # tower with the sound over the left shoulder. Two other framings were
    # tried: from the rock's crown the tower stands against bare sky, and from
    # the water 114 m out it is a distant silhouette over a foreground of flat
    # sea. Neither is panel 2, and this is the closest of the three - the sea
    # is present but the panel's breaking water is still mostly out of frame.
    ("02-lighthouse", 2, (88.0, 48.0), 4.0, (100.9, 40.1), 16.0, 46,
     (1180, 900), 48, "day"),
    # Panel 3: the cobbled street climbing from the quay through its arch.
    # Along the street's axis, not across it: framed across, the warehouse
    # walls fill the shot and the climb disappears.
    ("03-quay-street", 3, (11.6, -0.2), 1.7, (-2.8, -7.9), 4.0, 55,
     (1180, 860), 30, "day"),
    # Panel 4: a ship alongside the cargo pier with its gantry. Eye on the quay
    # apron at grid (3.30, 4.72), looking out along the pier.
    ("04-cargo-pier", 4, (21.2, 5.0), 1.7, (28.9, 9.4), 6.0, 54,
     (1280, 820), 34, "day"),
    # Panel 5: the timber cargo crane, from the quay beside it.
    ("05-harbour-crane", 5, (39.2, 5.0), 1.7, (46.2, 8.9), 9.0, 52,
     (1180, 880), 28, "day"),
    # Panel 6: the shipyard, a hull standing on the stocks over the slipway.
    # Aimed at the hull on the stocks at design (71.5, 5.4), not at the yard
    # anchor: aimed at the anchor the shot looked straight past the hull and
    # came back as a distant lighthouse over some roofs.
    # Back on the quay and west of the yard sheds, with a tighter field. From
    # inside the yard the two shed roofs filled the bottom half of the frame.
    ("06-shipyard", 6, (58.0, 0.5), 3.0, (71.5, 4.8), 5.0, 42,
     (1280, 860), 40, "day"),
    # Panel 7: the fish market under its awnings. Low and inside the stalls.
    # From the quay side of the stalls looking north into the arcade. The first
    # framing stood at design z -5, which is inside the warehouse row behind
    # the market, so the shot was two white gable walls and no market at all.
    # On the lower-town terrace among the stalls, looking north into the
    # arcade behind them. Standing on the quay below instead put a six-metre
    # terrace riser between the camera and the market.
    ("07-fish-market", 7, (-1.83, -4.0), 1.7, (-1.83, -6.5), 3.0, 56,
     (1180, 820), 24, "day"),
    # Panel 8: the mole bastion with its banner, surf on the outer face. The
    # eye stands on the mole deck, so this is a "deck" lighting mode: the deck
    # is a walk surface over water and a ground-relative height taken here is
    # measured from the harbour floor, not from the deck.
    # On the mole deck itself, looking along it at the bastion. "deck" mode
    # measures the eye height from the deck rather than from the harbour floor
    # 12.7 m below it - without that the camera stood underwater inside the
    # breakwater's own armour slope, which filled the frame with grey.
    # Along the mole at the bastion, with the weather side and its surf to the
    # left of frame. Aimed at the parapet rather than the platform: aimed high
    # the shot looked down onto the platform disc, which in shadow is a black
    # ellipse and not the subject.
    ("08-mole-bastion", 8, (-31.0, 3.6), 1.7, (-19.1, 12.4), 4.5, 54,
     (1280, 840), 40, "deck"),
    # Panel 9: the rooftop terrace looking over the brass dome to the harbour.
    # Standing *on* the crown terrace, which is at design (21.2, -71.8). The
    # first framing stood 31 m away on the citadel band below it and looked up
    # at the drum from underneath - the panel is a view across the dome, not up
    # at it.
    # 40 m back across the terrace, high enough to look over the dome rather
    # than up at its drum: at 17 m a 7 m dome on an 8 m drum is all there is.
    ("09-crown-terrace", 9, (17.0, -74.0), 3.0, (26.5, -64.6), 12.0, 52,
     (1400, 860), 56, "day"),
    # Panel 10: the dockside still-life - crate, rope, chain, fish, sailcloth.
    # A macro, 1.2 m from the subject and 0.85 m above the apron, not a wide
    # quay shot with the props a few pixels tall.
    ("10-chandlery-macro", 10, (37.4, -2.3), 1.2, (39.4, -0.2), 0.5, 38,
     (1080, 900), 12, "day"),

    # --- further coverage ----------------------------------------------
    ("11-spawn-grounding", None, (0.0, 0.0), 1.7, (6.0, -8.0), 1.7, 58,
     (1180, 820), 26, "day"),
    ("12-quayside-run", None, (-14.0, 2.0), 1.7, (52.0, 6.0), 2.0, 54,
     (1400, 800), 70, "day"),
    ("13-city-gate", None, (-7.0, -70.0), 1.7, (-7.0, -82.0), 8.0, 55,
     (1180, 880), 28, "day"),
    ("14-arcade", None, (0.0, -50.0), 1.7, (4.9, -64.6), 10.0, 54,
     (1280, 860), 34, "day"),
    ("15-cathedral-front", None, (14.0, -110.0), 2.0, (19.8, -125.4), 22.0, 52,
     (1280, 900), 46, "day"),
    ("16-campanile-base", None, (-8.0, -66.0), 1.7, (-2.8, -69.4), 26.0, 55,
     (1180, 900), 30, "day"),
    ("17-harbour-from-water", None, (20.0, 30.0), 1.2, (20.0, -20.0), 18.0, 50,
     (1400, 820), 80, "day"),
    ("18-gullstone", None, (-30.0, 30.0), 8.0, (-13.4, 43.9), 14.0, 50,
     (1280, 840), 52, "day"),
    ("19-east-bay", None, (86.0, 8.0), 4.0, (103.4, 9.8), 2.0, 52,
     (1280, 820), 44, "day"),
    ("20-upland-road", None, (72.0, -84.0), 2.0, (92.7, -94.3), 12.0, 52,
     (1280, 820), 48, "day"),

    # Eye-level evidence for the new circulation and working fields.
    ("21-cart-ascent", None, (53.7, -15.7), 1.7, (62.0, -24.0), 2.0, 58,
     (1280, 820), 55, "day"),
    ("22-gullscar-fields", None, (66.5, -74.7), 1.7, (72.0, -84.0), 3.0, 58,
     (1280, 820), 48, "day"),
    ("23-lamp-approach", None, (130.0, 12.0), 1.7, (126.8, 26.0), 2.0, 58,
     (1280, 820), 58, "deck"),
    ("24-yard-crossing", None, (79.0, 2.4), 1.7, (91.0, 7.3), 2.0, 58,
     (1280, 820), 42, "deck"),
    ("25-harbour-court", None, (20.0, 4.0), 1.7, (9.3, 0.0), 2.0, 58,
     (1280, 820), 40, "day"),

    # --- golden hour ----------------------------------------------------
    ("40-golden-harbour", None, (20.0, 30.0), 1.2, (20.0, -20.0), 18.0, 50,
     (1400, 840), 80, "golden"),
    ("41-golden-aerial", None, (38.0, -11.9), 200.0, (38.0, -12.0), 0.0, 52,
     (1400, 1400), 320, "golden"),
]

PANELS = {
    1: ("01-harbour-gate",
        "The arched harbour gate over the water, ships passing beneath"),
    2: ("02-lighthouse",
        "Lighthouse on a wave-battered rock, surf breaking below"),
    3: ("03-quay-street",
        "Cobbled quay street climbing through an arch between tall houses"),
    4: ("04-cargo-pier",
        "A ship alongside the quay with its gantry and dock hands"),
    5: ("05-harbour-crane",
        "Timber cargo crane swinging a laden net over the pier"),
    6: ("06-shipyard",
        "A hull under construction on the stocks, frames open to the sky"),
    7: ("07-fish-market",
        "Fish market stalls under awnings in a stone arcade"),
    8: ("08-mole-bastion",
        "Sea wall bastion with a hanging banner, waves against the outer face"),
    9: ("09-crown-terrace",
        "Rooftop terrace looking over a brass dome to the city and harbour"),
    10: ("10-chandlery-macro",
         "Dockside still-life: copper-bound crate, coiled rope, chain, fish"),
}

FIXED_VIEWS = {"21-cart-ascent", "22-gullscar-fields", "23-lamp-approach",
               "24-yard-crossing", "25-harbour-court"}

# Compact offline deck views use the new surveyed stations.
VIEWS = [tuple(list(v[:9]) + ["day"]) if v[9] == "deck" else v for v in VIEWS]
