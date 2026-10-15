"""Ssarathi Ruins' camera set and detail-board panel mapping.

Per-region data used by the shared toolkit's `capture_views.py` and
`make_comparison.py`, and - via `camera-views.json`, which the build emits from
this same table - by the in-client Godot capture harness. One table, two
consumers, so an offline preview and a real client frame are always the same
framing and can be compared honestly.

Coordinates are design-space (x, z) pairs, the same 192 m space `region.py` is
written in, so they scale with the region. Heights are metres **above the local
ground**, not absolute Y - a camera given an absolute height ends up underground
the moment the terrain changes, which is the trap the production guide names.

Two things specific to a flooded region:

* An eye height measured over water is measured from the *basin floor*, which
  is 1.5 to 4.6 m below the surface. A "1.7 m" camera standing on a causeway
  and a "1.7 m" camera out over the channel are three metres apart in world Y.
  Every over-water framing here therefore has its height set from the floor it
  actually stands on, not copied from a land framing.
* The great axis runs north at design x = 20, so a panel-1 framing is a low
  camera *on* the causeway looking up it - not across it.
"""
from __future__ import annotations

AXIS = 20.0

# The toolkit's capture presets are Amberwood's warm autumn-forest sun, which
# renders a green basin brown and puts a grey autumn sky over it. `DAY_LIGHTING`
# and `GOLDEN_LIGHTING` override any field of `capture_views.DAY` / `.GOLDEN`;
# this is the documented per-region hook, not a fork of the presets.
#
# What the concept needs: a high near-white tropical sun, a saturated blue
# zenith over a pale hazy horizon, and green-lifted ambient so shadows fill with
# bounced leaf light instead of going grey-blue.
DAY_LIGHTING = {
    "sun_direction": (-0.30, 0.86, 0.41),
    "sun_color": (1.30, 1.24, 1.06),
    "sky_color": (0.30, 0.44, 0.52),
    "ground_color": (0.10, 0.13, 0.07),
    "fog_color": (0.66, 0.76, 0.70),
    "fog_density": 0.00042,
    "fog_height_falloff": 0.0038,
    "ambient_strength": 0.36,
    "shadow_strength": 0.82,
    "exposure": 1.06,
    "saturation": 1.46,
    "sky_zenith": (0.20, 0.42, 0.68),
    "sky_horizon": (0.78, 0.84, 0.78),
}

GOLDEN_LIGHTING = {
    "sun_direction": (-0.82, 0.26, 0.50),
    "sun_color": (1.58, 1.06, 0.58),
    "sky_color": (0.34, 0.30, 0.26),
    "ground_color": (0.10, 0.09, 0.05),
    "fog_color": (0.72, 0.64, 0.46),
    "fog_density": 0.0017,
    "fog_height_falloff": 0.0046,
    "ambient_strength": 0.40,
    "shadow_strength": 0.84,
    "exposure": 1.12,
    "saturation": 1.34,
    "sky_zenith": (0.24, 0.30, 0.46),
    "sky_horizon": (0.90, 0.68, 0.40),
}

# Framings pinned against the toolkit's camera search. That search keeps a
# camera out of a trunk or an eave by requiring most of the frame to sit beyond
# 55% of the subject distance - a test no ground-level camera on a 200 m axial
# street through a dense ruin city can pass, so it fell back to the best it
# found, which was 13 m up and 57 m back. Every framing here is on open paved
# ground and has been checked; the ones that are not pinned still use the search.
FIXED_VIEWS = frozenset({
    "01-great-causeway", "02-temple-facade",
    "06-lily-court", "08-root-arch", "10-relic-macro",
    "20-water-gate", "22-serpent-gate", "26-temple-summit",
    "29-street-courts", "40-golden-causeway",
})

# (id, panel, eye_xz, eye_height, target_xz, target_height, fov, size,
#  shadow_radius, lighting)
VIEWS = [
    # The aerial concept is a view of the *city*, not of the whole 576 m
    # region: the composition is written in a 192 m design space and scaled by
    # region.SCALE, so a camera that frames the entire map is comparing the
    # painting against three times its own extent. This one covers the core.
    ("00-aerial-overview", "aerial", (26, 30), 118.0, (26, -50), 12.0, 50,
     (1400, 900), 190, "day"),
    # ... and the whole region, for the record.
    ("30-region-overview", None, (30, 44), 235.0, (30, -62), 10.0, 48,
     (1400, 900), 240, "day"),

    # --- the ten detail-board panels -----------------------------------
    # Panel 1: standing on the great causeway south of the serpent gate,
    # sighting due north up the axis at the temple. The whole composition is
    # this shot, so it is the one framing everything else was arranged around.
    ("01-great-causeway", 1, (AXIS, 2.0), 1.7, (AXIS, -88.0), 40.0, 52,
     (1280, 860), 110, "day"),
    # Panel 2: the temple facade from the terrace at the foot of its stair.
    # Low and close, so the stepped mass fills the frame the way the panel's
    # does rather than sitting in the middle distance.
    ("02-temple-facade", 2, (AXIS, -46.0), 2.0, (AXIS, -88.0), 44.0, 54,
     (1180, 900), 110, "day"),
    # Panel 3: the vault door, straight on from the tier-2 forecourt. The
    # target is the disc's own centre, which sits at about half the portal's
    # height - aimed at the portal's base the shot is of a staircase.
    ("03-sun-vault", 3, (AXIS, -62.0), 1.8, (AXIS, -70.0), 5.4, 50,
     (1100, 880), 30, "day"),
    # Panel 4: the arch bridge where the great causeway crosses the main
    # channel. From the south-west bank at a three-quarter angle, so the arch
    # reads as an arch rather than as a wall seen end-on. The first framing put
    # the camera on the deck looking along it, which is a shot of a road.
    ("04-channel-bridge", 4, (10.0, -23.0), 1.9, (AXIS, -34.5), 1.4, 50,
     (1280, 820), 46, "day"),
    # Panel 5: the ritual plaza, across the pool on the diagonal. Straight
    # across from the south the near colonnade occludes the far one and the
    # ring stops reading as a ring - and (56, -6) is not on the plaza at all,
    # it is standing in open water two metres south of the rim.
    ("05-ritual-plaza", 5, (47.0, -15.0), 2.6, (63.0, -33.0), 1.2, 52,
     (1280, 860), 56, "day"),
    # Panel 6: the lily court, from the paved south rim across the pool at the
    # north colonnade. Low, so the pads are foreground - the panel is about the
    # pads as much as the columns.
    ("06-lily-court", 6, (-16.0, -20.0), 1.7, (-16.0, -35.0), 1.6, 52,
     (1180, 860), 44, "day"),
    # Panel 7: the sun stela on its knoll, from below and to the south so the
    # slab stands against sky. Standing at the stela's own level flattens it,
    # and the approach spur is the only clear sightline - everything else is
    # canopy.
    # Inside the stela knoll's own cleared disc: at 39 m the camera was
    # outside it and stood in the canopy that the clearance stops one metre
    # further in.
    ("07-sun-stela", 7, (62.0, -55.0), 1.9, (62.0, -66.0), 15.0, 46,
     (1100, 900), 42, "day"),
    # Panel 8: the root-grown arch, close and low from the south-west so the
    # roots cross the opening the way they do in the panel.
    # Along the arch's own axis. `mesh.arch` extrudes along Z and the
    # placement turns it 24 degrees, so the opening faces (sin 24, cos 24);
    # standing anywhere else shows the barrel end, which is the whole trap.
    ("08-root-arch", 8, (82.7, 32.7), 1.8, (78.0, 22.0), 7.0, 50,
     (1240, 860), 34, "day"),
    # Panel 9: the high overview with the north falls in it. The panel is an
    # elevated three-quarter view of the causeway network, not a plan.
    ("09-falls-overlook", 9, (-32.0, -96.0), 62.0, (20.0, -50.0), 4.0, 50,
     (1400, 880), 150, "day"),
    # Panel 10 is a material close-up, so it is framed on the relics staged on
    # the temple terrace: scale tiling, a gilt sun boss and a carved face.
    ("10-relic-macro", 10, (AXIS, -41.6), 1.2, (AXIS, -44.4), 0.7,
     40, (1100, 900), 16, "day"),

    # --- further landmark and movement captures -------------------------
    ("20-water-gate", None, (AXIS, 26.0), 1.7, (AXIS, 16.0), 6.0, 54,
     (1180, 820), 26, "deck"),
    ("21-arrival-quay", None, (-8.0, 6.0), 1.7, (6.0, 0.0), 1.6, 55,
     (1180, 800), 26, "day"),
    ("22-serpent-gate", None, (AXIS, 4.0), 1.7, (AXIS, -8.0), 4.0, 52,
     (1180, 820), 24, "day"),
    ("23-market", None, (58.0, 12.0), 1.7, (66.0, 4.0), 2.0, 56,
     (1180, 800), 28, "day"),
    ("24-east-dock", None, (76.0, -4.0), 1.7, (88.0, -8.0), 0.8, 55,
     (1180, 800), 26, "day"),
    ("25-drowned-quarter", None, (-24.0, -14.0), 2.6, (-36.0, -22.0), 0.6, 52,
     (1240, 820), 44, "day"),
    ("26-temple-summit", None, (AXIS, -88.0), 74.0, (AXIS, -10.0), 2.0, 52,
     (1400, 860), 170, "day"),
    ("27-north-falls", None, (-14.0, -92.0), 6.0, (-14.0, -112.0), 12.0, 50,
     (1240, 860), 60, "day"),
    ("28-jungle-rim", None, (96.0, 34.0), 2.0, (76.0, 16.0), 3.0, 55,
     (1180, 820), 46, "day"),
    ("29-street-courts", None, (0.0, -28.0), 1.7, (44.0, -27.0), 2.0, 54,
     (1280, 800), 70, "day"),

    # --- golden hour ----------------------------------------------------
    ("40-golden-causeway", None, (AXIS, 2.0), 1.7, (AXIS, -88.0), 40.0, 52,
     (1400, 860), 112, "golden"),
    ("41-golden-aerial", None, (26, 26), 112.0, (26, -50), 12.0, 50,
     (1400, 900), 190, "golden"),
]

PANELS = {
    1: ("01-great-causeway",
        "Long paved causeway receding north between drowned ruins to a distant "
        "temple"),
    2: ("02-temple-facade",
        "Stepped jade-and-gold temple front with flanking waterfalls and "
        "serpent volutes"),
    3: ("03-sun-vault",
        "Recessed portal closed by a great circular sun-disc door, steps below"),
    4: ("04-channel-bridge",
        "Arched stone bridge over a clear flowing channel, lily pads at the "
        "banks"),
    5: ("05-ritual-plaza",
        "Circular terraced court with concentric pools, ringed by broken "
        "columns"),
    6: ("06-lily-court",
        "Lily-covered pool court with tall paired columns and a stepped rim"),
    7: ("07-sun-stela",
        "Tall stele carrying a gold sun face, standing high above the ruins"),
    8: ("08-root-arch",
        "Broken overgrown arch with massive tree roots over it and rubble "
        "below"),
    9: ("09-falls-overlook",
        "Elevated view over the causeway network with a waterfall on the left"),
    10: ("10-relic-macro",
         "Macro: jade scale tiling, gilt scrollwork, a shell boss and a carved "
         "stone face"),
}


# Ground-level evidence for the inhabited quay and surveyed water routes.
VIEWS.extend([
    ("50-quay-services",None,(0,4),1.7,(0,-2),2.0,62,(1280,820),50,"day!"),
    ("51-cistern-walk",None,(-38,-22),1.7,(-39.2,-22),1.7,58,(1280,820),80,"deck"),
    ("52-sounding-stage",None,(-40,-22),1.7,(-42.5,-22),1.7,62,(1280,820),25,"deck"),
    ("53-packet-berth",None,(4,41),1.7,(4,35),1.7,60,(1280,820),45,"deck"),
    ("54-market-aisle",None,(69,10),1.7,(77,10),2.0,58,(1280,820),50,"day!"),
    ("55-coil-bridge-walk",None,(20,-29),1.7,(20,-39),1.7,58,(1280,820),65,"deck"),
])
FIXED_VIEWS=FIXED_VIEWS|{v[0] for v in VIEWS if v[0].startswith(("50-","51-","52-","53-","54-","55-"))}
