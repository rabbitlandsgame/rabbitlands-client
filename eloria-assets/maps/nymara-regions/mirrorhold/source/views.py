"""Mirrorhold's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`. Coordinates are design-space (x, z) pairs; heights are
metres above the local ground, not absolute Y, so a camera cannot end up
underground when the terrain changes.

Each view is (id, panel, (eye_x, eye_z), eye_height_above_ground,
              (target_x, target_z), target_height_above_ground,
              fov_degrees, (width, height), shadow_radius, lighting_mode).
`panel` is the detail-board panel the shot answers, or None for coverage
views, or "aerial" for the overview.
"""
from __future__ import annotations

VIEWS = [
    ("00-aerial-overview", "aerial", (44.0, 150.0), 300.0, (46.0, -46.0), 40.0,
     46, (1600, 1000), 150, "day"),

    # -- the ten board panels ------------------------------------------------
    # 1. the grand causeway rising to the monumental gate
    ("01-great-causeway", 1, (46.0, -34.0), 1.7, (51.0, -50.0), 12.0,
     58, (1180, 820), 40, "day"),
    # 2. the canal and waterfall district
    ("02-canal-district", 2, (16.0, -22.0), 12.0, (28.0, -36.0), 3.0,
     52, (1180, 820), 44, "day"),
    # 3. the fountain plaza
    ("03-fountain-plaza", 3, (38.0, -24.0), 1.8, (44.0, -31.0), 3.6,
     55, (1180, 860), 28, "day"),
    # 4. the ring on the mirror lake, seen from the shore road
    ("04-ring-lake", 4, (18.0, 14.0), 14.0, (52.0, 20.0), 2.0,
     50, (1400, 840), 90, "day"),
    # 5. the orrery: mirror-sphere in its armillary mount
    ("05-orrery", 5, (54.0, -71.0), 6.0, (54.0, -89.0), 15.0,
     46, (1080, 920), 40, "day"),
    # 6. the rose-window gallery
    ("06-rose-gallery", 6, (40.0, -42.0), 5.0, (40.0, -53.0), 8.0,
     48, (1080, 900), 30, "day"),
    # 7. the stepped cliff town
    ("07-cliff-town", 7, (12.0, 2.0), 16.0, (-6.0, -16.0), 10.0,
     50, (1180, 880), 48, "day"),
    # 8. the harbour and its docks
    ("08-harbour", 8, (54.0, 12.0), 11.0, (66.0, -4.0), 2.0,
     52, (1280, 800), 44, "day"),
    # 9. the terrace overlook, north toward the peaks
    ("09-terrace-overlook", 9, (72.0, -32.0), 2.0, (60.0, -76.0), 40.0,
     50, (1400, 840), 120, "day"),
    # 10. the gate wall: banner, crystal panels, snow on the ledges
    ("10-gate-wall", 10, (49.0, -46.0), 1.6, (52.0, -52.0), 2.4,
     42, (1080, 900), 16, "day"),

    # -- coverage ------------------------------------------------------------
    ("11-arrival", None, (0.0, 0.0), 1.7, (24.0, -18.0), 20.0,
     58, (1280, 800), 60, "day"),
    ("12-lake-shore", None, (28.0, 34.0), 1.7, (52.0, 22.0), 2.0,
     56, (1280, 780), 60, "day"),
    ("13-citadel-court", None, (54.0, -60.0), 2.0, (54.0, -72.0), 10.0,
     54, (1180, 860), 30, "day"),
    ("14-aqueduct", None, (92.0, -22.0), 2.4, (98.0, -30.0), 8.0,
     55, (1180, 800), 30, "day"),
    ("15-glacier-east", None, (94.0, -88.0), 2.2, (100.0, -100.0), 8.0,
     54, (1280, 780), 50, "day"),
    ("16-west-gorge", None, (-20.0, 8.0), 2.6, (-28.0, 4.0), 2.0,
     56, (1180, 800), 34, "day"),
    ("17-upper-falls", None, (20.0, -42.0), 2.4, (18.0, -50.0), 6.0,
     56, (1080, 880), 26, "day"),
    ("18-south-watch", None, (36.0, 44.0), 2.0, (36.0, 52.0), 5.0,
     54, (1180, 780), 26, "day"),
    ("19-east-stair", None, (78.0, -12.0), 2.0, (80.0, -20.0), 8.0,
     55, (1080, 860), 26, "day"),
    ("20-summit-golden", None, (46.0, -80.0), 4.0, (54.0, -89.0), 14.0,
     50, (1400, 840), 60, "golden"),
]

VIEWS += [
    ("21-sanctuary-arrival", None, (40, 55), 1.7, (51, 42), 2.0,
     60, (1400, 900), 80, "day!"),
    ("22-lake-promenade", None, (52, 33), 1.7, (52, 26), 1.8,
     60, (1400, 900), 80, "deck!"),
    ("23-cellar-lane", None, (-14, -13.8), 1.7, (-16.3, -17), 1.5,
     58, (1200, 850), 24, "day!"),
    ("24-lens-vault-entry", None, (45.7, -81.3), 1.7, (45.7, -85.3), 1.5,
     58, (1200, 850), 24, "day!"),
    ("25-cistern-court", None, (47.7, -23.8), 1.7, (50.3, -28), 1.5,
     60, (1200, 850), 26, "day!"),
]
FIXED_VIEWS = {view[0] for view in VIEWS if view[-1].endswith("!")}

PANELS = {
    1: ("01-great-causeway", "Grand causeway rising to the monumental gate"),
    2: ("02-canal-district", "Canal and waterfall district on the south face"),
    3: ("03-fountain-plaza", "Tiered fountain plaza with gilded domes behind"),
    4: ("04-ring-lake", "The ring on the mirror lake, radial causeways"),
    5: ("05-orrery", "Mirror-sphere in its armillary mount above the citadel"),
    6: ("06-rose-gallery", "Blue rose window and colonnaded gallery"),
    7: ("07-cliff-town", "Stepped cliff town stacked on the west shoulder"),
    8: ("08-harbour", "Harbour quay, piers and moored boats"),
    9: ("09-terrace-overlook", "Terrace overlook north toward the snow peaks"),
    10: ("10-gate-wall", "Gate wall: banner, crystal panels, snow on the ledges"),
}
