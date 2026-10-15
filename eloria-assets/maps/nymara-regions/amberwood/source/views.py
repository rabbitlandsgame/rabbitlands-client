"""Amberwood's camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`. Coordinates are design-space (x, z) pairs; heights are
metres above the local ground, not absolute Y.
"""
from __future__ import annotations

VIEWS = [
    ("00-aerial-overview", "aerial", (-118, 168), 168.0, (52, -54), 0.0, 44,
     (1400, 900), 190, "day"),
    ("01-forest-road", 1, (2.0, -6.0), 1.7, (24.0, -22.0), 3.0, 60, (1180, 760), 46, "day"),
    ("02-moot-hall", 2, (8.0, -50.0), 4.0, (-4.0, -64.0), 8.0, 52, (1180, 900), 40, "day"),
    ("03-forest-lodge", 3, (-8.0, 18.0), 2.6, (-15.0, 7.0), 4.0, 56, (1180, 800), 28, "day"),
    ("04-hollow-tree", 4, (-16.0, -78.0), 3.0, (-26.0, -86.0), 7.0, 58, (1080, 920), 32, "day"),
    ("05-high-bridge", 5, (48.0, -52.0), 6.0, (40.0, -66.0), 7.0, 54, (1180, 780), 40, "day"),
    ("06-root-arch", 6, (-26.0, -24.0), 2.6, (-16.0, -34.0), 3.6, 55, (1080, 880), 24, "day"),
    ("07-garden-terrace", 7, (52.0, 30.0), 4.0, (52.0, 8.0), 3.6, 54, (1180, 820), 38, "day"),
    ("08-canopy-amber", 8, (29.0, -64.0), 12.2, (22.0, -70.0), 11.8, 62, (1080, 880), 24, "day"),
    ("09-high-overlook", 9, (76.0, -60.0), 6.0, (12.0, -62.0), 20.0, 50, (1400, 800), 130, "day"),
    ("10-material-study", 10, (6.4, -45.4), 1.2, (4.4, -49.0), 0.9, 40, (1080, 880), 14, "day"),
    ("11-great-arch", None, (58.0, -2.0), 7.0, (58.0, -34.0), 9.0, 48, (1280, 880), 48, "day"),
    ("12-harbour", None, (-44.0, 24.0), 9.0, (-28.0, 6.0), 2.0, 54, (1280, 780), 44, "day"),
    ("13-great-tree", None, (48.0, -76.0), 4.0, (26.0, -88.0), 16.0, 50, (1080, 920), 44, "day"),
    ("14-market", None, (-12.0, -38.0), 4.6, (4.0, -50.0), 3.0, 55, (1280, 780), 30, "day"),
    ("15-forest-gate", None, (74.0, -14.0), 2.4, (74.0, -30.0), 3.6, 54, (1080, 820), 26, "day"),
    ("16-timber-yard", None, (54.0, 48.0), 5.0, (72.0, 34.0), 2.5, 54, (1280, 780), 38, "day"),
    ("17-ash-transition", None, (84.0, -4.0), 5.0, (116.0, -18.0), 2.0, 54, (1280, 780), 70, "day"),
    ("18-watchtower", None, (72.0, -54.0), 4.0, (86.0, -70.0), 8.0, 52, (1080, 880), 38, "day"),
    ("19-coast-waterfall", None, (-34.0, -10.0), 8.0, (-17.5, -22.0), 3.0, 54,
     (1280, 780), 40, "day"),
    ("20-north-gate", None, (24.0, -90.0), 3.0, (24.0, -104.0), 6.0, 54, (1080, 820), 30, "day"),
    ("21-hill-hamlet", None, (90.0, 46.0), 5.0, (108.0, 30.0), 3.0, 54, (1280, 780), 38, "day"),
    ("22-mill-pool", None, (-18.0, -32.0), 3.4, (-2.0, -44.0), 1.5, 56, (1180, 780), 32, "day"),
    ("23-old-bridge", None, (-2.0, -36.0), 3.0, (10.0, -44.0), 4.0, 55, (1080, 820), 28, "day"),
    ("24-canopy-walkway", None, (14.0, -80.0), 13.5, (24.0, -70.0), 12.0, 58,
     (1180, 780), 36, "day"),
    ("30-spawn-grounding", None, (-10.0, 10.0), 2.4, (4.0, -6.0), 1.6, 58, (1180, 780), 32, "day"),
    ("31-arch-stair", None, (66.0, -14.0), 2.2, (58.0, -30.0), 5.0, 56, (1180, 780), 30, "day"),
    ("32-shore-walk", None, (-38.0, 18.0), 3.0, (-26.0, 6.0), 1.2, 56, (1180, 780), 34, "day"),
    ("33-ravine-edge", None, (30.0, -54.0), 3.0, (44.0, -72.0), 2.0, 56, (1180, 780), 40, "day"),
    ("25-forest-lake", None, (-6.0, -72.0), 4.0, (-15.0, -85.0), 1.0, 55,
     (1280, 780), 40, "day"),
    ("26-west-cove", None, (-30.0, -50.0), 6.0, (-42.0, -60.0), 1.0, 55,
     (1280, 780), 40, "day"),
    ("27-north-hamlet", None, (20.0, -110.0), 4.0, (30.0, -118.0), 3.0, 55,
     (1280, 780), 36, "day"),
    ("28-quarry", None, (62.0, 44.0), 5.0, (75.0, 52.0), 2.0, 55, (1280, 780), 36, "day"),
    ("29-old-battle", None, (100.0, -48.0), 4.0, (115.0, -40.0), 2.0, 55,
     (1280, 780), 44, "day"),
    ("34-ridge-bridge", None, (40.0, -94.0), 5.0, (52.0, -100.0), 6.0, 54,
     (1180, 780), 38, "day"),
    ("40-golden-settlement", None, (-18.0, -36.0), 7.0, (12.0, -60.0), 6.0, 50,
     (1400, 820), 70, "golden"),
    ("41-golden-arch", None, (30.0, -18.0), 5.0, (58.0, -34.0), 10.0, 50,
     (1400, 820), 56, "golden"),
    ("42-golden-coast", None, (-8.0, 26.0), 11.0, (-40.0, 2.0), 1.0, 52,
     (1400, 820), 70, "golden"),
]

PANELS = {
    1: ("01-forest-road", "Leaf-covered forest road under the amber canopy"),
    2: ("02-moot-hall", "Multi-storey timber-and-stone civic hall"),
    3: ("03-forest-lodge", "Player-scale forest lodge with porch and workshop"),
    4: ("04-hollow-tree", "Colossal hollow-tree entrance"),
    5: ("05-high-bridge", "High stone bridge over a rocky watercourse"),
    6: ("06-root-arch", "Root-overgrown ancient stone arch"),
    7: ("07-garden-terrace", "Formal garden: fountain, statues, rotunda, terrace"),
    8: ("08-canopy-amber", "Canopy platform and amber working"),
    9: ("09-high-overlook", "High overlook toward the settlement"),
    10: ("10-material-study", "Material study: amber, carved wood, moss, leaves"),
}

# Player-height reviews of the September circulation pass. X/Z are still
# design-space; fixed views preserve the surveyed eye instead of moving uphill.
FIXED_VIEWS={"02-moot-hall","05-high-bridge","12-harbour","14-market","22-mill-pool",
             "23-old-bridge","30-spawn-grounding","35-quay-approach","36-dry-cove",
             "37-quarry-haul","38-mother-sightline"}
def _world_view(name,panel,eye,eye_h,target,target_h,fov=58,mode="day!"):
    return (name,panel,(eye[0]/3,eye[1]/3),eye_h,(target[0]/3,target[1]/3),target_h,
            fov,(1180,780),48,mode)
_REVIEW_VIEWS=[
 _world_view("02-moot-hall",2,(18,-169),1.7,(-12,-192),8,55),
 _world_view("05-high-bridge",5,(100,-206),1.7,(136,-188),1.4,58,"deck!"),
 _world_view("12-harbour",None,(-94,24),1.7,(-128,24),1,57),
 _world_view("14-market",None,(24,-164),1.7,(24,-185),2,65),
 _world_view("22-mill-pool",None,(-21,-114),1.7,(-30,-118),2.6,58),
 _world_view("23-old-bridge",None,(42.5,-138),1.7,(39,-159),1.7,58,"deck!"),
 _world_view("30-spawn-grounding",None,(24,-171),1.7,(34,-190),2,66),
 _world_view("35-quay-approach",None,(-103,24),1.7,(-82,31),2.5,58,"deck!"),
 _world_view("36-dry-cove",None,(-58,-157),1.7,(-63,-176),2.5,60),
 _world_view("37-quarry-haul",None,(219,126),1.7,(225,155),3.5,58),
 _world_view("38-mother-sightline",None,(45,-218),1.7,(78,-264),32,58),
]
_changed={v[0] for v in _REVIEW_VIEWS}
VIEWS=[v for v in VIEWS if v[0] not in _changed]+_REVIEW_VIEWS
VIEWS.sort(key=lambda v:v[0])
