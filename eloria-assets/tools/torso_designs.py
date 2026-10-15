#!/usr/bin/env python3
"""The sixty-four torso designs, read off the concept sheets.

Added 2026-08-29 for Eloria Client.  Eight sheets of eight, each cell one
garment.  What is written down here is the decision the sheet does not make for
you: which of the four kinds the pipeline builds - ``shirt``, ``cuirass``,
``coat`` or ``robe`` - each drawing actually is, and the handful of numbers that
make one differ from another.

The rules used to decide kind, applied in this order:

* nothing on the arms below the armhole -> ``cuirass`` (a leather jerkin and a
  steel breastplate are the same garment to this pipeline, and differ in finish)
* a skirt below the knee -> ``robe``
* a skirt below the waist with sleeves -> ``coat``
* everything else -> ``shirt``

A sheet that draws a sleeved shirt *under* a sleeveless jerkin is a cuirass: the
sleeves belong to the body's own wardrobe layer, which part 5 does not hide when
the garment does not cover it.

Colours are the two the runtime tints a piece with - base and accent - read from
the sheet cell.  Everything else about a design is in its ``Style``.
"""
from __future__ import annotations

from equipment_authoring import Style

#: Where part 5's new visual ids start.  0-21 are the generic material ladders
#: and 100-110 the culture pieces; character creation drives appearance shirt
#: 0-11, which resolve to the generic ladder, so the fallback path is untouched
#: by anything up here.  Sixty-four designs run 120-183 and leave 22-99, 111-119
#: and 184-255 free.
FIRST_VISUAL = 120


# --- the four constructions, as starting points ----------------------------
# Every design below is one of these with a few numbers moved.  Keeping the
# constructions shared is what makes the set checkable: the shoulder is a
# property of the construction, so a design cannot reintroduce a hole in it.

def shirt(**kwargs) -> Style:
    """Cloth, sleeves to mid upper arm, a seam at the shoulder rather than a pad."""
    return Style(**{"sleeve_end": .34, "sleeve_thickness": .013,
                    "cap_outboard": .46, "cap_swell": 1.38,
                    "thickness": .011, **kwargs})


def cuirass(**kwargs) -> Style:
    """Rigid, no sleeve; the cap is a pauldron and the armhole has a rim."""
    return Style(**{"sleeve_end": None, "facing_end": .22,
                    "cap_outboard": .44, "cap_swell": 1.62, "cap_trim": True,
                    "thickness": .017, "sleeve_thickness": .016, **kwargs})


def coat(**kwargs) -> Style:
    """Sleeves down most of the forearm, and a skirt from the waist."""
    return Style(**{"sleeve_end": .86, "sleeve_thickness": .020,
                    "cap_outboard": .50, "cap_swell": 1.44,
                    "skirt": (.660, .070), "lapel": True,
                    "thickness": .013, **kwargs})


def robe(**kwargs) -> Style:
    """Sleeves near the wrist, and a skirt to the shin."""
    return Style(**{"sleeve_end": .92, "sleeve_thickness": .026,
                    "cap_outboard": .48, "cap_swell": 1.40,
                    "skirt": (.280, .150), "hem_band": True,
                    "thickness": .016, **kwargs})


#: The narrowest shoulder cap each construction may draw.
#:
#: A cap is styling as well as fit - a linen shirt wants a seam and a pauldron
#: wants to be seen - so the sheets pull it in both directions and it is easy to
#: draw one too small.  Three did: two leather jerkins and a mail hauberk cut
#: theirs to 1.30-1.34 to read as close-fitting, and the audit found the deltoid
#: through all three, one of them in the bind pose.  Below these figures a cap
#: no longer reaches from the body shell to the armhole rim.
MIN_CAP_SWELL = {"shirt": 1.34, "cuirass": 1.50, "coat": 1.36, "robe": 1.32}


#: (slug, label, kind, finish, base rgb, accent rgb, style)
#: Ordered by sheet and then by cell, left to right and top to bottom, so a
#: visual id maps back to a place on a sheet: id = FIRST_VISUAL + index.
DESIGNS = (
    # -- sheet 1: outrider leathers -----------------------------------------
    ("outrider_ranger_coat", "Outrider Ranger Coat", "coat", "leather",
     (86, 66, 48), (196, 186, 158), coat(cap_trim=True)),
    ("outrider_laced_jerkin", "Outrider Laced Jerkin", "cuirass", "leather",
     (104, 74, 46), (214, 206, 184), cuirass(cap_swell=1.54, facing_end=.20)),
    ("outrider_oxblood_coat", "Outrider Oxblood Coat", "coat", "leather",
     (58, 44, 44), (122, 42, 44), coat(cap_trim=True, skirt=(.700, .060))),
    ("outrider_buckled_coat", "Outrider Buckled Coat", "coat", "leather",
     (96, 66, 42), (168, 128, 74), coat(belt=1.148, belt_thickness=.020)),
    ("outrider_scout_jerkin", "Outrider Scout Jerkin", "coat", "leather",
     (74, 78, 52), (150, 132, 96), coat(cap_trim=True, cap_swell=1.44,
                                        skirt=(.720, .086))),
    ("outrider_rope_jerkin", "Outrider Rope Jerkin", "coat", "leather",
     (92, 68, 44), (206, 196, 170), coat(skirt=(.740, .050), lapel=False)),
    ("outrider_brigandine", "Outrider Brigandine", "cuirass", "leather",
     (78, 54, 40), (128, 46, 44), cuirass(cap_swell=1.54, plate=(1.150, 1.410),
                                          skirt=(.860, .040))),
    ("outrider_fur_coat", "Outrider Fur-Collar Coat", "coat", "fur",
     (86, 62, 42), (198, 190, 174), coat(cap_trim=True, cap_swell=1.42,
                                         skirt=(.700, .078))),

    # -- sheet 2: knightly plate --------------------------------------------
    ("knight_fluted_cuirass", "Fluted Knight Cuirass", "cuirass", "plate",
     (176, 182, 190), (122, 44, 52), cuirass(plate=(1.140, 1.430), yoke=True,
                                             skirt=(.880, .034))),
    ("knight_etched_cuirass", "Etched Knight Cuirass", "cuirass", "plate",
     (182, 188, 196), (58, 64, 82), cuirass(plate=(1.130, 1.440), yoke=True,
                                            skirt=(.860, .040))),
    ("knight_gilded_cuirass", "Gilded Knight Cuirass", "cuirass", "plate",
     (150, 132, 88), (206, 172, 84), cuirass(plate=(1.120, 1.450), yoke=True,
                                             skirt=(.870, .046))),
    ("knight_scale_cuirass", "Scaled Knight Cuirass", "cuirass", "plate",
     (168, 176, 184), (198, 204, 212), cuirass(plate=(1.140, 1.420),
                                               skirt=(.860, .050))),
    ("knight_chased_cuirass", "Chased Knight Cuirass", "cuirass", "plate",
     (188, 192, 198), (206, 178, 96), cuirass(plate=(1.150, 1.440), yoke=True,
                                              skirt=(.900, .030))),
    ("knight_tourney_cuirass", "Tourney Knight Cuirass", "cuirass", "plate",
     (186, 190, 198), (196, 176, 108), cuirass(plate=(1.130, 1.450), yoke=True,
                                               skirt=(.840, .056))),
    ("knight_herald_cuirass", "Herald Knight Cuirass", "cuirass", "plate",
     (178, 184, 192), (134, 40, 44), cuirass(plate=(1.140, 1.460), yoke=True,
                                             cap_swell=1.58, skirt=(.850, .062))),
    ("knight_warden_cuirass", "Warden Knight Cuirass", "cuirass", "plate",
     (92, 96, 104), (72, 40, 54), cuirass(plate=(1.130, 1.430), yoke=True,
                                          skirt=(.880, .036))),

    # -- sheet 3: orun sun and desert ---------------------------------------
    ("orun_linen_tunic", "Orun Linen Tunic", "shirt", "cloth",
     (214, 204, 178), (162, 62, 48), shirt(sleeve_end=.60, belt=1.120)),
    ("orun_wrap_robe", "Orun Wrap Robe", "robe", "cloth",
     (216, 206, 180), (158, 66, 50), robe(skirt=(.560, .120), belt=1.118)),
    ("orun_rider_jerkin", "Orun Rider Jerkin", "cuirass", "leather",
     (110, 78, 50), (150, 108, 64), cuirass(cap_swell=1.54, facing_end=.20,
                                            skirt=(.880, .030))),
    ("orun_toggle_tunic", "Orun Toggle Tunic", "shirt", "cloth",
     (218, 208, 184), (176, 74, 56), shirt(sleeve_end=.62, belt=1.126)),
    ("orun_sunplate_cuirass", "Orun Sunplate Cuirass", "cuirass", "plate",
     (146, 112, 52), (216, 172, 72), cuirass(plate=(1.150, 1.430), yoke=True,
                                             cap_swell=1.56, skirt=(.870, .040))),
    ("orun_sash_robe", "Orun Sash Robe", "robe", "cloth",
     (206, 196, 172), (150, 52, 46), robe(skirt=(.520, .134), belt=1.130,
                                          belt_thickness=.026)),
    ("orun_ochre_coat", "Orun Ochre Coat", "coat", "leather",
     (162, 130, 74), (120, 84, 50), coat(skirt=(.720, .064))),
    ("orun_ceremonial_tunic", "Orun Ceremonial Tunic", "shirt", "cloth",
     (220, 212, 190), (198, 162, 78), shirt(sleeve_end=.58, cap_swell=1.52,
                                            cap_trim=True, belt=1.124)),

    # -- sheet 4: verdant leaf ----------------------------------------------
    ("verdant_leafscale_coat", "Verdant Leafscale Coat", "coat", "leather",
     (76, 68, 46), (92, 108, 62), coat(cap_trim=True, cap_swell=1.40,
                                       skirt=(.700, .066))),
    ("verdant_mantle_coat", "Verdant Mantle Coat", "coat", "leather",
     (62, 84, 58), (108, 124, 74), coat(cap_trim=True, cap_swell=1.50,
                                        skirt=(.660, .082))),
    ("verdant_bough_tunic", "Verdant Bough Tunic", "shirt", "cloth",
     (206, 198, 176), (94, 112, 66), shirt(sleeve_end=.56, cap_trim=True,
                                           cap_swell=1.44, belt=1.122)),
    ("verdant_leaf_cuirass", "Verdant Leaf Cuirass", "cuirass", "leather",
     (78, 100, 56), (120, 138, 78), cuirass(plate=(1.150, 1.420),
                                            skirt=(.850, .058))),
    ("verdant_bark_cuirass", "Verdant Bark Cuirass", "cuirass", "wood",
     (86, 70, 48), (188, 180, 158), cuirass(plate=(1.140, 1.440), yoke=True,
                                            cap_swell=1.60, skirt=(.870, .044))),
    ("verdant_toggle_coat", "Verdant Toggle Coat", "coat", "fur",
     (92, 72, 52), (204, 196, 178), coat(cap_swell=1.36, skirt=(.690, .074))),
    ("verdant_amber_cuirass", "Verdant Amber Cuirass", "cuirass", "crystal",
     (176, 116, 42), (214, 162, 66), cuirass(plate=(1.130, 1.440), yoke=True,
                                             skirt=(.860, .048))),
    ("verdant_warden_cuirass", "Verdant Warden Cuirass", "cuirass", "plate",
     (200, 194, 174), (94, 116, 68), cuirass(plate=(1.140, 1.450), yoke=True,
                                             skirt=(.840, .060))),

    # -- sheet 5: luminous arcane -------------------------------------------
    ("luminous_tabard_coat", "Luminous Tabard Coat", "coat", "cloth",
     (52, 62, 92), (208, 200, 176), coat(skirt=(.680, .068))),
    ("luminous_rune_coat", "Luminous Rune Coat", "coat", "leather",
     (74, 58, 44), (58, 178, 194), coat(skirt=(.700, .062))),
    ("luminous_silver_cuirass", "Luminous Silver Cuirass", "cuirass", "plate",
     (196, 198, 194), (66, 122, 166), cuirass(plate=(1.140, 1.440), yoke=True,
                                              skirt=(.860, .046))),
    ("luminous_crystal_cuirass", "Luminous Crystal Cuirass", "cuirass", "crystal",
     (104, 140, 178), (128, 202, 224), cuirass(plate=(1.130, 1.450), yoke=True,
                                               cap_swell=1.58, skirt=(.850, .054))),
    ("luminous_violet_coat", "Luminous Violet Coat", "coat", "cloth",
     (48, 42, 64), (96, 82, 132), coat(cap_trim=True, skirt=(.640, .086))),
    ("luminous_feather_robe", "Luminous Feather Robe", "robe", "cloth",
     (46, 128, 140), (206, 200, 180), robe(cap_trim=True, cap_swell=1.44,
                                           skirt=(.320, .142))),
    ("luminous_gilt_robe", "Luminous Gilt Robe", "robe", "cloth",
     (214, 208, 190), (198, 166, 82), robe(skirt=(.300, .148))),
    ("luminous_winged_cuirass", "Luminous Winged Cuirass", "cuirass", "crystal",
     (170, 196, 214), (96, 190, 216), cuirass(plate=(1.120, 1.460), yoke=True,
                                              cap_swell=1.66, skirt=(.840, .058))),

    # -- sheet 6: legendary ---------------------------------------------------
    ("legend_phoenix_plate", "Phoenix Plate", "cuirass", "plate",
     (156, 62, 34), (226, 158, 54), cuirass(plate=(1.120, 1.460), yoke=True,
                                            cap_swell=1.68, skirt=(.840, .062))),
    ("legend_frost_plate", "Rimeguard Plate", "cuirass", "crystal",
     (150, 176, 202), (104, 182, 220), cuirass(plate=(1.130, 1.450), yoke=True,
                                               cap_swell=1.62, skirt=(.850, .056))),
    ("legend_storm_plate", "Stormcall Plate", "cuirass", "plate",
     (56, 58, 82), (166, 138, 206), cuirass(plate=(1.120, 1.460), yoke=True,
                                            cap_swell=1.64, skirt=(.840, .060))),
    ("legend_drake_plate", "Bonedrake Plate", "cuirass", "shell",
     (214, 206, 186), (146, 44, 42), cuirass(plate=(1.130, 1.470), yoke=True,
                                             cap_swell=1.70, skirt=(.850, .054))),
    ("legend_radiant_plate", "Radiant Plate", "cuirass", "plate",
     (216, 210, 194), (204, 172, 84), cuirass(plate=(1.120, 1.450), yoke=True,
                                              cap_swell=1.60, skirt=(.850, .058))),
    ("legend_void_plate", "Voidsworn Plate", "cuirass", "plate",
     (42, 40, 56), (138, 96, 190), cuirass(plate=(1.120, 1.460), yoke=True,
                                           cap_swell=1.66, skirt=(.840, .062))),
    ("legend_runestone_plate", "Runestone Plate", "cuirass", "plate",
     (140, 146, 142), (108, 176, 74), cuirass(plate=(1.130, 1.450), yoke=True,
                                              cap_swell=1.64, skirt=(.850, .056))),
    ("legend_lion_plate", "Lionheart Plate", "cuirass", "plate",
     (132, 40, 44), (212, 176, 88), cuirass(plate=(1.120, 1.460), yoke=True,
                                            cap_swell=1.66, skirt=(.840, .060))),

    # -- sheet 7: peasant linen ---------------------------------------------
    ("peasant_linen_shirt", "Linen Shirt", "shirt", "cloth",
     (216, 210, 192), (168, 150, 116), shirt(sleeve_end=.72, belt=1.116)),
    ("peasant_short_tunic", "Short-Sleeve Tunic", "shirt", "cloth",
     (188, 166, 118), (144, 108, 68), shirt(sleeve_end=.26, belt=1.114)),
    ("peasant_patched_tunic", "Patched Tunic", "shirt", "cloth",
     (166, 160, 146), (118, 104, 88), shirt(sleeve_end=.66, belt=1.118)),
    ("peasant_button_tunic", "Buttoned Tunic", "shirt", "cloth",
     (214, 208, 188), (140, 96, 62), shirt(sleeve_end=.58, belt=1.120)),
    ("peasant_wrap_tunic", "Wrap Tunic", "shirt", "cloth",
     (212, 206, 186), (132, 92, 58), shirt(sleeve_end=.74, belt=1.122)),
    ("peasant_laced_tunic", "Laced Work Tunic", "shirt", "cloth",
     (146, 116, 76), (108, 82, 52), shirt(sleeve_end=.56, belt=1.118)),
    ("peasant_ragged_tunic", "Ragged Tunic", "shirt", "cloth",
     (118, 132, 148), (92, 100, 112), shirt(sleeve_end=.28, belt=1.112)),
    ("peasant_wool_tunic", "Wool Tunic", "shirt", "cloth",
     (128, 96, 74), (150, 62, 52), shirt(sleeve_end=.68, belt=1.116)),

    # -- sheet 8: gambeson, mail and breastplate -----------------------------
    ("levy_quilted_gambeson", "Quilted Gambeson", "coat", "cloth",
     (204, 194, 168), (128, 96, 62), coat(sleeve_end=.90, skirt=(.780, .048),
                                          lapel=False)),
    ("levy_studded_brigandine", "Studded Brigandine", "coat", "leather",
     (108, 66, 40), (156, 116, 68), coat(sleeve_end=.88, cap_trim=True,
                                         skirt=(.790, .044))),
    ("levy_splinted_corselet", "Splinted Corselet", "cuirass", "plate",
     (150, 152, 156), (120, 100, 72), cuirass(facing_end=.30, plate=(1.140, 1.430),
                                              skirt=(.820, .046))),
    ("levy_mail_hauberk", "Mail Hauberk", "cuirass", "mail",
     (128, 132, 138), (166, 170, 176), cuirass(facing_end=.34, cap_swell=1.54,
                                               skirt=(.800, .052))),
    ("levy_lamellar_corselet", "Lamellar Corselet", "cuirass", "plate",
     (138, 128, 112), (108, 88, 66), cuirass(facing_end=.26, plate=(1.150, 1.420),
                                             skirt=(.810, .050))),
    ("levy_steel_breastplate", "Steel Breastplate", "cuirass", "plate",
     (180, 186, 194), (198, 190, 168), cuirass(plate=(1.140, 1.440), yoke=True,
                                               skirt=(.830, .046))),
    ("levy_bronze_breastplate", "Bronze Breastplate", "cuirass", "plate",
     (166, 122, 58), (62, 70, 92), cuirass(plate=(1.140, 1.440), yoke=True,
                                           skirt=(.830, .046))),
    ("levy_spauldered_breastplate", "Spauldered Breastplate", "cuirass", "plate",
     (176, 182, 190), (146, 48, 46), cuirass(plate=(1.130, 1.450), yoke=True,
                                             cap_swell=1.62, skirt=(.830, .050))),
)


def entries():
    """``EQUIPMENT``-shaped rows for the builder.

    Seven fields, the same shape every other entry in that table has.  Finish
    and construction travel separately, keyed by slug, because that is how the
    authoring tool already looks them up - and it is also what lets a fit
    variant, built under a suffixed slug, find the construction of the piece it
    is a variant of.
    """
    return tuple((slug, label, 5, FIRST_VISUAL + index, kind, base, accent)
                 for index, (slug, label, kind, _finish, base, accent, _style)
                 in enumerate(DESIGNS))


def by_kind() -> dict:
    counts: dict[str, int] = {}
    for _, _, kind, *_ in DESIGNS:
        counts[kind] = counts.get(kind, 0) + 1
    return counts


if __name__ == "__main__":
    print(f"{len(DESIGNS)} designs, visuals 5:{FIRST_VISUAL}"
          f"-5:{FIRST_VISUAL + len(DESIGNS) - 1}")
    print(by_kind())
    slugs = [design[0] for design in DESIGNS]
    assert len(set(slugs)) == len(slugs), "duplicate slug"
    from equipment_authoring import SLEEVE_APEX, sleeve_clear
    for slug, _label, kind, _finish, _base, _accent, style in DESIGNS:
        assert style.sleeve_end is None or sleeve_clear(style.sleeve_end), (
            f"{slug} ends its sleeve at {style.sleeve_end}, inside the apex "
            f"band {SLEEVE_APEX}")
        assert style.cap_swell >= MIN_CAP_SWELL[kind], (
            f"{slug} draws a shoulder cap at {style.cap_swell}, under the "
            f"{MIN_CAP_SWELL[kind]} its construction needs")
    print(f"all sleeve lengths clear of the apex band {SLEEVE_APEX}")
    print("all shoulder caps at or above the measured minimum")
    for slug, label, kind, finish, base, accent, style in DESIGNS:
        print(f"  {slug:<32} {kind:<8} {finish:<8} {label}")
