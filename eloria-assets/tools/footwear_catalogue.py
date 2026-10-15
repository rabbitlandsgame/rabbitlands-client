#!/usr/bin/env python3
"""The sixty-four designs, one per cell of the eight concept sheets.

Each entry is the silhouette, the finish and the layer stack that carry one
cell's look onto the measured body.  The geometry that realises them lives in
``footwear_authoring``; this file is the reading of the art.

**Every design is the outer layer.**  Inverted layering - an ankle boot the
trouser falls over - was specified and turns out to be unreachable: a shell that
actually contains the ankle and the instep cannot finish below world Y 0.164 on
the reference rig, and the inverted rule needs the shaft top at or below Y 0.102.
Y 0.164 also lands between the soft trouser hem (0.142) and the rigid one
(0.178), which is the ambiguous case both briefs forbid.  So the short designs
on sheet 7 are raised to the Y 0.240 floor and read as short boots rather than
ankle boots; that is a deliberate, recorded loss against the sheet, taken so no
pairing in the game ever has two garments each believing the other is outside.

Shaft heights are fractions along ``calf`` from the knee, because world Y does
not transfer: the same seam sits about 145 mm higher up the world on a
digitigrade leg.  ``TALL`` is the shared datum, Y 0.320.
"""
from __future__ import annotations

from footwear_authoring import (
    ANKLE_TOP_T, CUFF_DATUM_T, BootDesign, Cuff, Gem, Lames, Medallion, Relief,
    Sabaton, Scales, ShinPlate, Spikes, Strap, Studs, Tassels, ToeCap, Wrap)
from equipment_authoring import MATERIAL_BASE, MATERIAL_DETAIL, MATERIAL_TRIM

#: Shaft heights, as fractions along ``calf`` from the knee.
TALL = CUFF_DATUM_T   # cuff top edge at world Y 0.320 - the shared datum
MID = 0.590           # ~Y 0.283
LOW = 0.688           # ~Y 0.240 - the floor for an outer boot

#: The first visual id of the new block.  Chosen to clear the legacy generic run
#: at 6:0-6:12 and the culture pieces at 6:100-6:106, and to sit far above
#: anything the appearance byte can produce: an unequipped actor sends its
#: character-creation boot index in the same byte, and that slider tops out at 5.
FIRST_VISUAL = 128

STEEL = (188, 194, 202)
DARKSTEEL = (92, 96, 104)
GOLD = (214, 176, 96)
BRASS = (176, 142, 78)
LEATHER = (118, 84, 56)
DARKLEATHER = (74, 52, 36)
TANLEATHER = (156, 118, 78)
CRIMSON = (146, 44, 48)
BONE = (226, 216, 194)
MOSS = (92, 112, 68)
BARK = (96, 74, 52)
FROST = (196, 222, 236)
TEAL = (72, 158, 166)
IVORY = (232, 226, 208)
VOID = (58, 50, 78)
STONE = (128, 130, 122)
EMBER = (232, 112, 48)


def _sheet(number, rows):
    """Expand one sheet's eight cells into designs, numbering them by cell."""
    designs = []
    for index, entry in enumerate(rows):
        slug, label, kwargs = entry
        designs.append(BootDesign(
            slug=slug, label=label, sheet=number,
            cell=(index // 4, index % 4), **kwargs))
    return designs


# -- sheet 1: plate greaves, knightly ---------------------------------------
SHEET_1 = _sheet(1, [
    ("plate_fluted", "Fluted Greaves", dict(
        finish="plate", base=STEEL, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.22, sole="welt",
        layers=(Cuff(style="scallop", flare=.016, material=MATERIAL_TRIM),
                Lames(top=.56, bottom=.98, count=5, depth=.011),
                Sabaton(count=4), ToeCap(style="point"),
                Studs(travel=.62, count=10, radius=.005)))),
    ("plate_leaf", "Leafwork Greaves", dict(
        finish="plate", base=IVORY, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.18, sole="welt",
        layers=(Cuff(style="band", flare=.012),
                ShinPlate(top=.54, bottom=.94, span=.44, depth=.015),
                Relief(top=.58, bottom=.90, motif="scroll", strands=2,
                       radius=.006),
                Strap(travel=.74), Strap(travel=.92, buckle=False),
                Sabaton(count=3), ToeCap(style="round")))),
    ("plate_buckled", "Buckled Warplate", dict(
        finish="plate", base=STEEL, accent=BRASS, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.14, sole="lug",
        layers=(Cuff(style="band"), Lames(top=.55, bottom=.99, count=6),
                Strap(travel=.66), Strap(travel=.80), Strap(travel=.94),
                Sabaton(count=4), ToeCap(style="point")))),
    ("plate_gothic", "Gothic Sabatons", dict(
        finish="plate", base=IVORY, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.012, shaft_flare=1.26, sole="welt",
        layers=(Cuff(style="points", flare=.014),
                ShinPlate(top=.54, bottom=.92, span=.40, depth=.016),
                Relief(top=.58, bottom=.88, motif="runes", strands=3,
                       radius=.005),
                Sabaton(count=4), ToeCap(style="point")))),
    ("plate_heraldic", "Heraldic Greaves", dict(
        finish="plate", base=STEEL, accent=CRIMSON, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.20, sole="welt",
        layers=(Cuff(style="points", flare=.015),
                ShinPlate(top=.54, bottom=.96, span=.46, depth=.014),
                Medallion(travel=.70, radius=.024),
                Strap(travel=.84), Sabaton(count=3), ToeCap(style="point")))),
    ("plate_scroll", "Scrollwork Greaves", dict(
        finish="plate", base=IVORY, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.24, sole="welt",
        layers=(Cuff(style="scallop", flare=.016),
                Relief(top=.55, bottom=.95, motif="scroll", strands=4,
                       radius=.006),
                Medallion(travel=.66, radius=.020, facing="front"),
                Sabaton(count=3), ToeCap(style="round")))),
    ("plate_crimson", "Crimson Guard Greaves", dict(
        finish="plate", base=STEEL, accent=CRIMSON, shaft_top=TALL,
        shaft_thickness=.014, shaft_flare=1.16, sole="lug",
        layers=(Cuff(style="points", flare=.013),
                Lames(top=.55, bottom=.97, count=5),
                Strap(travel=.70), Strap(travel=.88),
                Spikes(travel=.62, count=3, length=.022),
                Sabaton(count=4), ToeCap(style="point")))),
    ("plate_blackened", "Blackened Greaves", dict(
        finish="plate", base=DARKSTEEL, accent=CRIMSON, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.12, sole="lug",
        layers=(Cuff(style="band", flare=.010),
                ShinPlate(top=.54, bottom=.98, span=.42, depth=.013),
                Strap(travel=.72), Strap(travel=.90),
                Sabaton(count=4), ToeCap(style="point")))),
])

# -- sheet 2: riveted steel over working leather ----------------------------
SHEET_2 = _sheet(2, [
    ("riveted_shin", "Riveted Marchboots", dict(
        finish="leather", base=LEATHER, accent=STEEL, shaft_top=MID,
        shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold"), ShinPlate(top=.62, bottom=.98, span=.36,
                                              depth=.011),
                Strap(travel=.74), Strap(travel=.90),
                Studs(travel=.68, count=8), ToeCap(style="round")))),
    ("riveted_banded", "Banded Trooper Boots", dict(
        finish="leather", base=DARKLEATHER, accent=STEEL, shaft_top=TALL,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="band"), Lames(top=.56, bottom=.98, count=5,
                                          depth=.009, span=.62),
                Strap(travel=.68), Strap(travel=.86),
                Studs(travel=.60, count=10), ToeCap(style="round")))),
    ("riveted_halfplate", "Halfplate Legguards", dict(
        finish="plate", base=STEEL, accent=DARKLEATHER, shaft_top=TALL,
        shaft_thickness=.012, shaft_flare=1.10, sole="lug",
        layers=(Cuff(style="band"),
                ShinPlate(top=.53, bottom=.99, span=.52, depth=.014),
                Strap(travel=.76), Strap(travel=.92),
                Sabaton(count=3), ToeCap(style="round")))),
    ("riveted_worn", "Worn Campaign Boots", dict(
        finish="leather", base=LEATHER, accent=BRASS, shaft_top=MID,
        shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold", flare=.014), Strap(travel=.70),
                Strap(travel=.88), Studs(travel=.94, count=6, onfoot=False),
                ToeCap(style="round", reach=.26)))),
    ("riveted_brass", "Brasswork Greaves", dict(
        finish="plate", base=BRASS, accent=GOLD, shaft_top=MID,
        shaft_thickness=.012, shaft_flare=1.08, sole="lug",
        layers=(Cuff(style="band"),
                ShinPlate(top=.62, bottom=.98, span=.48, depth=.015),
                Relief(top=.66, bottom=.94, motif="scroll", strands=2),
                Strap(travel=.84), ToeCap(style="round")))),
    ("riveted_lamellar", "Lamellar Marchboots", dict(
        finish="mail", base=STEEL, accent=DARKLEATHER, shaft_top=TALL,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="band"), Lames(top=.55, bottom=.99, count=7,
                                          depth=.008, span=.66),
                Strap(travel=.72), Strap(travel=.92), ToeCap(style="round")))),
    ("riveted_crimson", "Crimson Sashboots", dict(
        finish="leather", base=STEEL, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fold", flare=.016),
                ShinPlate(top=.62, bottom=.96, span=.34, depth=.012),
                Wrap(top=.66, bottom=.94, turns=2.0, radius=.010),
                Strap(travel=.90), ToeCap(style="round")))),
    ("riveted_furlined", "Furlined Marchboots", dict(
        finish="fur", base=DARKLEATHER, accent=STEEL, shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fur", flare=.012),
                ShinPlate(top=.64, bottom=.98, span=.34, depth=.011),
                Strap(travel=.78), Studs(travel=.86, count=8),
                ToeCap(style="round")))),
])

# -- sheet 3: druidic bark, moss and amber ----------------------------------
SHEET_3 = _sheet(3, [
    ("wild_bark", "Barkbound Boots", dict(
        finish="wood", base=BARK, accent=MOSS, shaft_top=TALL,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="scallop", flare=.014, material=MATERIAL_BASE),
                Relief(top=.53, bottom=.99, motif="branches", strands=5,
                       radius=.007, material=MATERIAL_BASE),
                Wrap(top=.60, bottom=.96, turns=1.6, radius=.008),
                Strap(travel=.90, buckle=False)))),
    ("wild_moss", "Mosscuff Boots", dict(
        finish="wood", base=BARK, accent=MOSS, shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fur", flare=.016, material=MATERIAL_TRIM),
                Wrap(top=.64, bottom=.98, turns=2.6, radius=.009),
                Strap(travel=.92, buckle=False), Studs(travel=.72, count=5)))),
    ("wild_vine", "Vinewrapped Boots", dict(
        finish="wood", base=LEATHER, accent=MOSS, shaft_top=TALL,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="band"),
                Wrap(top=.54, bottom=.99, turns=3.4, radius=.0085),
                Relief(top=.58, bottom=.94, motif="branches", strands=3,
                       radius=.006),
                Medallion(travel=.68, radius=.016)))),
    ("wild_leaf", "Leafplate Boots", dict(
        finish="wood", base=MOSS, accent=BARK, shaft_top=TALL,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="band"),
                Scales(top=.54, bottom=.98, rows=5, around=7, size=.022),
                Strap(travel=.86), Strap(travel=.97, buckle=False)))),
    ("wild_antler", "Antlerbound Boots", dict(
        finish="wood", base=BARK, accent=BONE, shaft_top=TALL,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="scallop", flare=.012),
                Relief(top=.53, bottom=.97, motif="branches", strands=4,
                       radius=.0075),
                Medallion(travel=.60, radius=.020, facing="front"),
                Strap(travel=.90, buckle=False)))),
    ("wild_winterfur", "Winterwood Boots", dict(
        finish="fur", base=BARK, accent=BONE, shaft_top=MID,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="fur", flare=.018),
                Wrap(top=.66, bottom=.96, turns=2.2, radius=.009),
                Strap(travel=.78), Strap(travel=.92),
                Studs(travel=.84, count=6)))),
    ("wild_amber", "Amberpanel Boots", dict(
        finish="crystal", base=MOSS, accent=(226, 154, 48), shaft_top=TALL,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="band"),
                ShinPlate(top=.54, bottom=.94, span=.40, depth=.015),
                Gem(travel=.62, size=.026), Gem(travel=.80, size=.020),
                Strap(travel=.72), Strap(travel=.90)))),
    ("wild_filigree", "Thornfiligree Boots", dict(
        finish="wood", base=MOSS, accent=BONE, shaft_top=TALL,
        shaft_thickness=.013, sole="lug",
        layers=(Cuff(style="fur", flare=.014),
                Relief(top=.53, bottom=.98, motif="branches", strands=6,
                       radius=.006),
                Gem(travel=.66, size=.022),
                Strap(travel=.92, buckle=False)))),
])

# -- sheet 4: tribal and nomadic wraps --------------------------------------
SHEET_4 = _sheet(4, [
    ("nomad_cord", "Corded Wanderers", dict(
        finish="leather", base=DARKLEATHER, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.012, sole="welt",
        layers=(Cuff(style="fold", flare=.014),
                Wrap(top=.62, bottom=.98, turns=2.4, radius=.009),
                Tassels(travel=.66, count=3), Medallion(travel=.74,
                                                        radius=.016)))),
    ("nomad_linen", "Linenwrap Boots", dict(
        finish="cloth", base=IVORY, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.012, sole="flat",
        layers=(Cuff(style="fold", flare=.018),
                Wrap(top=.60, bottom=.99, turns=4.0, radius=.011),
                Tassels(travel=.64, count=2, length=.045)))),
    ("nomad_sunplate", "Sunplate Striders", dict(
        finish="plate", base=BRASS, accent=GOLD, shaft_top=MID,
        shaft_thickness=.012, shaft_flare=1.10, sole="welt",
        layers=(Cuff(style="band"),
                ShinPlate(top=.62, bottom=.98, span=.46, depth=.015),
                Medallion(travel=.70, radius=.024, facing="front"),
                Strap(travel=.84), ToeCap(style="round")))),
    ("nomad_bone", "Bonetoggle Boots", dict(
        finish="shell", base=IVORY, accent=BONE, shaft_top=MID,
        shaft_thickness=.012, sole="welt",
        layers=(Cuff(style="fold"),
                Wrap(top=.62, bottom=.96, turns=2.0, radius=.008),
                Studs(travel=.68, count=4, radius=.008),
                Studs(travel=.80, count=4, radius=.008),
                Tassels(travel=.74, count=2)))),
    ("nomad_sunburst", "Sunburst Greaves", dict(
        finish="plate", base=GOLD, accent=BRASS, shaft_top=MID,
        shaft_thickness=.013, shaft_flare=1.12, sole="welt",
        layers=(Cuff(style="band"), Medallion(travel=.66, radius=.030,
                                              facing="side"),
                Relief(top=.62, bottom=.92, motif="scroll", strands=3),
                Strap(travel=.82), ToeCap(style="round")))),
    ("nomad_crimson", "Crimson Caravan Boots", dict(
        finish="cloth", base=CRIMSON, accent=GOLD, shaft_top=MID,
        shaft_thickness=.013, sole="welt",
        layers=(Cuff(style="fold", flare=.020),
                Wrap(top=.64, bottom=.96, turns=2.2, radius=.010),
                Tassels(travel=.68, count=3, length=.060),
                Medallion(travel=.76, radius=.018)))),
    ("nomad_lashed", "Lashed Trailboots", dict(
        finish="leather", base=TANLEATHER, accent=DARKLEATHER, shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fold"),
                Wrap(top=.60, bottom=.99, turns=3.6, radius=.0075),
                Studs(travel=.72, count=6), Tassels(travel=.66, count=2)))),
    ("nomad_ivory", "Ivory Wardboots", dict(
        finish="shell", base=IVORY, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.013, sole="welt",
        layers=(Cuff(style="band"),
                ShinPlate(top=.62, bottom=.96, span=.42, depth=.013),
                Medallion(travel=.68, radius=.020),
                Tassels(travel=.72, count=2), Strap(travel=.88)))),
])

# -- sheet 5: elemental and arcane ornate -----------------------------------
SHEET_5 = _sheet(5, [
    ("arcane_ember", "Emberwrought Greaves", dict(
        finish="fire", base=(96, 48, 32), accent=EMBER, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.20, sole="welt",
        layers=(Cuff(style="points", flare=.016),
                Relief(top=.54, bottom=.96, motif="flame", strands=5,
                       radius=.007),
                Gem(travel=.62, size=.024), Sabaton(count=3),
                ToeCap(style="claw")))),
    ("arcane_frostward", "Frostward Greaves", dict(
        finish="cold", base=FROST, accent=(120, 178, 214), shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.18, sole="welt",
        layers=(Cuff(style="fur", flare=.016),
                ShinPlate(top=.54, bottom=.94, span=.42, depth=.015),
                Relief(top=.58, bottom=.90, motif="runes", strands=3),
                Gem(travel=.66, size=.022), Sabaton(count=3)))),
    ("arcane_storm", "Stormcall Greaves", dict(
        finish="magic", base=(46, 58, 96), accent=(126, 172, 236),
        shaft_top=TALL, shaft_thickness=.013, shaft_flare=1.16, sole="welt",
        layers=(Cuff(style="points", flare=.014),
                Relief(top=.54, bottom=.96, motif="runes", strands=4,
                       radius=.006),
                Gem(travel=.60, size=.026), Sabaton(count=4),
                ToeCap(style="point")))),
    ("arcane_bone", "Bonewrought Greaves", dict(
        finish="shell", base=BONE, accent=CRIMSON, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.22, sole="welt",
        layers=(Cuff(style="spike"),
                Scales(top=.55, bottom=.97, rows=4, around=6, size=.024),
                Spikes(travel=.66, count=3, length=.026),
                Sabaton(count=3), ToeCap(style="claw")))),
    ("arcane_dawn", "Dawnward Greaves", dict(
        finish="plate", base=IVORY, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.24, sole="welt",
        layers=(Cuff(style="scallop", flare=.018),
                Relief(top=.54, bottom=.94, motif="scroll", strands=4),
                Medallion(travel=.62, radius=.022, facing="front"),
                Gem(travel=.74, size=.018), Sabaton(count=3),
                ToeCap(style="point")))),
    ("arcane_void", "Voidtouched Greaves", dict(
        finish="magic", base=VOID, accent=(158, 118, 226), shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.18, sole="welt",
        layers=(Cuff(style="points", flare=.015),
                Relief(top=.54, bottom=.96, motif="runes", strands=5),
                Gem(travel=.64, size=.024), Spikes(travel=.58, count=2,
                                                   length=.024),
                Sabaton(count=3), ToeCap(style="point")))),
    ("arcane_stone", "Runestone Greaves", dict(
        finish="crystal", base=STONE, accent=(126, 196, 178), shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.10, sole="lug",
        layers=(Cuff(style="band", flare=.012),
                ShinPlate(top=.54, bottom=.98, span=.50, depth=.016),
                Relief(top=.60, bottom=.92, motif="runes", strands=3),
                Strap(travel=.86), Sabaton(count=3)))),
    ("arcane_lion", "Lionheart Greaves", dict(
        finish="plate", base=GOLD, accent=CRIMSON, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.20, sole="welt",
        layers=(Cuff(style="scallop", flare=.016),
                ShinPlate(top=.54, bottom=.94, span=.44, depth=.015),
                Medallion(travel=.62, radius=.026, facing="front"),
                Strap(travel=.78), Strap(travel=.92),
                Sabaton(count=3), ToeCap(style="round")))),
])

# -- sheet 6: worn traveller's leather --------------------------------------
SHEET_6 = _sheet(6, [
    ("travel_folded", "Folded Roadboots", dict(
        finish="leather", base=(96, 96, 78), accent=DARKLEATHER,
        shaft_top=MID, shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold", flare=.020),
                Wrap(top=.66, bottom=.96, turns=1.8, radius=.008),
                Strap(travel=.86), Tassels(travel=.70, count=1)))),
    ("travel_fur", "Furcuff Roadboots", dict(
        finish="fur", base=LEATHER, accent=(196, 174, 140), shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fur", flare=.018), Strap(travel=.74),
                Strap(travel=.90), Studs(travel=.82, count=6)))),
    ("travel_buckled", "Buckled Roadboots", dict(
        finish="leather", base=LEATHER, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold", flare=.014), Strap(travel=.70),
                Strap(travel=.82), Strap(travel=.94),
                ToeCap(style="round", reach=.20)))),
    ("travel_fringed", "Fringed Scoutboots", dict(
        finish="leather", base=(104, 112, 84), accent=TANLEATHER,
        shaft_top=MID, shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="scallop", flare=.016, material=MATERIAL_BASE),
                Wrap(top=.64, bottom=.96, turns=2.6, radius=.008),
                Tassels(travel=.68, count=3, length=.048)))),
    ("travel_laced", "Laced Trailboots", dict(
        finish="leather", base=DARKLEATHER, accent=CRIMSON, shaft_top=MID,
        shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold"),
                Wrap(top=.62, bottom=.98, turns=4.2, radius=.0065),
                Strap(travel=.72), Studs(travel=.90, count=6)))),
    ("travel_canvas", "Canvaswrap Boots", dict(
        finish="cloth", base=(206, 196, 168), accent=DARKLEATHER,
        shaft_top=MID, shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="fold", flare=.022),
                Wrap(top=.62, bottom=.98, turns=3.0, radius=.010),
                Tassels(travel=.66, count=2)))),
    ("travel_tassel", "Tasselled Roadboots", dict(
        finish="leather", base=(126, 78, 52), accent=BRASS, shaft_top=MID,
        shaft_thickness=.012, sole="lug",
        layers=(Cuff(style="band"), Strap(travel=.72), Strap(travel=.88),
                Scales(top=.78, bottom=.98, rows=2, around=8, size=.016),
                Tassels(travel=.66, count=2)))),
    ("travel_darkcord", "Darkcord Roadboots", dict(
        finish="leather", base=(58, 54, 58), accent=(140, 132, 120),
        shaft_top=MID, shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fold", flare=.012),
                Wrap(top=.64, bottom=.98, turns=2.8, radius=.0085),
                Strap(travel=.80)))),
])

# -- sheet 7: plain leather, the commoner's boot -----------------------------
# Raised to the Y 0.240 floor: see the module docstring.
SHEET_7 = _sheet(7, [
    ("plain_chelsea", "Plain Boots", dict(
        finish="leather", base=(112, 82, 58), accent=(84, 60, 42),
        shaft_top=LOW, shaft_thickness=.010, sole="welt",
        layers=(Cuff(style="band", drop=.055, thickness=.008),))),
    ("plain_slouch", "Slouched Boots", dict(
        finish="leather", base=TANLEATHER, accent=(112, 82, 58),
        shaft_top=LOW, shaft_thickness=.012, shaft_flare=1.18, sole="welt",
        layers=(Cuff(style="fold", drop=.060, flare=.016),))),
    ("plain_laced", "Laced Workboots", dict(
        finish="leather", base=(120, 88, 60), accent=TANLEATHER,
        shaft_top=LOW, shaft_thickness=.010, sole="lug",
        layers=(Cuff(style="band", drop=.050),
                Wrap(top=.72, bottom=.98, turns=3.0, radius=.006),
                ToeCap(style="round", reach=.18, depth=.005)))),
    ("plain_burlap", "Burlapwrap Boots", dict(
        finish="cloth", base=(198, 184, 154), accent=(120, 88, 60),
        shaft_top=LOW, shaft_thickness=.012, sole="flat",
        layers=(Cuff(style="fold", drop=.055, flare=.018),
                Wrap(top=.72, bottom=.98, turns=2.4, radius=.009)))),
    ("plain_harness", "Harness Boots", dict(
        finish="leather", base=(104, 72, 48), accent=(70, 48, 34),
        shaft_top=LOW, shaft_thickness=.011, sole="welt",
        layers=(Cuff(style="band", drop=.050), Strap(travel=.78),
                Strap(travel=.94, buckle=False)))),
    ("plain_furlace", "Furlaced Boots", dict(
        finish="fur", base=(96, 68, 46), accent=(200, 184, 156),
        shaft_top=LOW, shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="fur", drop=.050, flare=.014),
                Wrap(top=.74, bottom=.98, turns=2.6, radius=.006),
                Studs(travel=.90, count=6, radius=.0045)))),
    ("plain_textile", "Textile Panel Boots", dict(
        finish="cloth", base=(206, 194, 166), accent=(126, 90, 62),
        shaft_top=LOW, shaft_thickness=.011, sole="lug",
        layers=(Cuff(style="band", drop=.050),
                ShinPlate(top=.72, bottom=.98, span=.40, depth=.008,
                          material=MATERIAL_BASE),
                Strap(travel=.86)))),
    ("plain_tiecuff", "Tiecuff Boots", dict(
        finish="leather", base=(118, 86, 58), accent=(86, 62, 42),
        shaft_top=LOW, shaft_thickness=.011, shaft_flare=1.12, sole="welt",
        layers=(Cuff(style="fold", drop=.055, flare=.014),
                Wrap(top=.74, bottom=.90, turns=1.2, radius=.007)))),
])

# -- sheet 8: enchanted frost and tideglass ---------------------------------
SHEET_8 = _sheet(8, [
    ("glass_tidecuff", "Tidecuff Boots", dict(
        finish="crystal", base=DARKLEATHER, accent=TEAL, shaft_top=TALL,
        shaft_thickness=.012, shaft_flare=1.14, sole="welt",
        layers=(Cuff(style="band", flare=.014),
                ShinPlate(top=.56, bottom=.94, span=.38, depth=.012),
                Gem(travel=.60, size=.022), Strap(travel=.80),
                ToeCap(style="round")))),
    ("glass_runed", "Runeglass Boots", dict(
        finish="magic", base=LEATHER, accent=TEAL, shaft_top=TALL,
        shaft_thickness=.012, sole="welt",
        layers=(Cuff(style="band"),
                Relief(top=.56, bottom=.96, motif="runes", strands=4,
                       radius=.005),
                Gem(travel=.66, size=.018), Tassels(travel=.72, count=2),
                Strap(travel=.88)))),
    ("glass_pale", "Paleglass Greaves", dict(
        finish="crystal", base=(222, 226, 228), accent=TEAL, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.16, sole="welt",
        layers=(Cuff(style="band", flare=.012),
                ShinPlate(top=.54, bottom=.96, span=.46, depth=.014),
                Gem(travel=.62, size=.022), Sabaton(count=3),
                ToeCap(style="round")))),
    ("glass_starfield", "Starfield Boots", dict(
        finish="magic", base=(48, 62, 104), accent=FROST, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.18, sole="welt",
        layers=(Cuff(style="scallop", flare=.014),
                Relief(top=.54, bottom=.94, motif="scroll", strands=4),
                Gem(travel=.60, size=.024), Studs(travel=.76, count=8,
                                                  radius=.004)))),
    ("glass_darkfacet", "Darkfacet Greaves", dict(
        finish="crystal", base=(62, 60, 74), accent=TEAL, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.14, sole="welt",
        layers=(Cuff(style="points", flare=.014),
                Scales(top=.55, bottom=.96, rows=4, around=6, size=.022),
                Gem(travel=.64, size=.020), Sabaton(count=3),
                ToeCap(style="point")))),
    ("glass_tideknot", "Tideknot Boots", dict(
        finish="crystal", base=TEAL, accent=IVORY, shaft_top=TALL,
        shaft_thickness=.013, sole="welt",
        layers=(Cuff(style="band"),
                Wrap(top=.54, bottom=.98, turns=3.2, radius=.0085),
                Gem(travel=.68, size=.020), Tassels(travel=.62, count=2)))),
    ("glass_ivory", "Ivorytide Boots", dict(
        finish="crystal", base=IVORY, accent=GOLD, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.16, sole="welt",
        layers=(Cuff(style="band", flare=.012),
                Relief(top=.56, bottom=.94, motif="scroll", strands=3),
                Medallion(travel=.64, radius=.020), Strap(travel=.84),
                ToeCap(style="round")))),
    ("glass_filigree", "Filigree Tideboots", dict(
        finish="crystal", base=(212, 218, 222), accent=TEAL, shaft_top=TALL,
        shaft_thickness=.013, shaft_flare=1.20, sole="welt",
        layers=(Cuff(style="scallop", flare=.016),
                Relief(top=.54, bottom=.96, motif="branches", strands=5,
                       radius=.006),
                Gem(travel=.62, size=.024), Sabaton(count=3),
                ToeCap(style="point")))),
])

SHEETS = (SHEET_1, SHEET_2, SHEET_3, SHEET_4, SHEET_5, SHEET_6, SHEET_7,
          SHEET_8)
DESIGNS = tuple(design for sheet in SHEETS for design in sheet)

#: ``visual id -> design``.  A single byte carries this over the wire, so the
#: block has to fit in 0-255 alongside everything already there.
VISUALS = {FIRST_VISUAL + index: design for index, design in enumerate(DESIGNS)}


def visual_of(design: BootDesign) -> int:
    for visual, entry in VISUALS.items():
        if entry.slug == design.slug:
            return visual
    raise KeyError(design.slug)


assert len(DESIGNS) == 64, f"expected 64 designs, got {len(DESIGNS)}"
assert len({d.slug for d in DESIGNS}) == 64, "duplicate slug"
assert len({d.label for d in DESIGNS}) == 64, "duplicate label"
assert max(VISUALS) <= 255, "the visual block does not fit in one byte"
