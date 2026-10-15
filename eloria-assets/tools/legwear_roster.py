#!/usr/bin/env python3
"""The sixty-four leg garments, read off the concept sheets.

Eight sheets of eight.  Each entry names the design, the sheet tile it came
from, and - the decision that matters most downstream - which of the three
kinds it is built as.

``pants``  soft.  Hip shell from .902, leg tubes to .93 of the thigh+calf
           chain.  The trouser tucks into the boot.
``legs``   rigid.  Hip shell from .914, tubes to .89, plus knee and cuff trim.
``kilt``   a hanging panel.  Skinned to the ``skirt`` region so it carries
           ``spine_01`` and hangs from the torso rather than folding with the
           hips.  Everything in this kind also builds a soft trouser under the
           panel, because a kilt alone leaves the leg bare.

The kind is not a re-description of the picture, it is a promise about the
seam: a ``pants`` hem lands at world Y .142 on the reference rig and tucks into
the boot, a ``legs`` hem at .178.  A design that reads as plate but is built
soft will not meet the boot where the footwear brief expects it.
"""
from __future__ import annotations

#: slug, display name, sheet, tile, kind, features
ROSTER = [
    # -- sheet 1: legendary -------------------------------------------------
    ("emberforge_cuisses", "Emberforge Cuisses", "legendary", 1, "legs",
     ("tasset", "kneecop", "greave", "flare")),
    ("rimeguard_cuisses", "Rimeguard Cuisses", "legendary", 2, "legs",
     ("tasset", "fur", "kneecop", "greave")),
    ("voidplate_legs", "Voidplate Leggings", "legendary", 3, "legs",
     ("tasset", "scale", "kneecop", "greave")),
    ("ossuary_cuisses", "Ossuary Cuisses", "legendary", 4, "legs",
     ("bone", "tasset", "kneecop", "greave")),
    ("dawnward_cuisses", "Dawnward Cuisses", "legendary", 5, "kilt",
     ("tasset", "kneecop", "greave", "panel")),
    ("umbral_drapes", "Umbral Drapes", "legendary", 6, "kilt",
     ("panel", "tatter", "scale", "greave")),
    ("mosswarden_legs", "Mosswarden Leggings", "legendary", 7, "legs",
     ("stone", "kneecop", "greave", "flare")),
    ("lionheart_cuisses", "Lionheart Cuisses", "legendary", 8, "kilt",
     ("panel", "tasset", "kneecop", "greave")),
    # -- sheet 2: arcane ----------------------------------------------------
    ("astral_robe_legs", "Astral Robe Leggings", "arcane", 1, "kilt",
     ("panel", "sash", "trim")),
    ("runebound_breeches", "Runebound Breeches", "arcane", 2, "pants",
     ("strap", "gem", "buckle")),
    ("tidewarden_cuisses", "Tidewarden Cuisses", "arcane", 3, "kilt",
     ("tasset", "panel", "trim")),
    ("prismscale_legs", "Prismscale Leggings", "arcane", 4, "legs",
     ("scale", "gem", "greave")),
    ("starfall_drapes", "Starfall Drapes", "arcane", 5, "kilt",
     ("panel", "tatter", "gem")),
    ("tidesilk_wrap", "Tidesilk Wrap", "arcane", 6, "kilt",
     ("panel", "sash", "bead")),
    ("oracle_drapes", "Oracle Drapes", "arcane", 7, "kilt",
     ("panel", "sash", "trim")),
    ("mooncast_cuisses", "Mooncast Cuisses", "arcane", 8, "legs",
     ("tasset", "kneecop", "greave", "gem")),
    # -- sheet 3: amberwood -------------------------------------------------
    ("barkplate_legs", "Barkplate Leggings", "amberwood", 1, "legs",
     ("bark", "tooth", "wrap", "greave")),
    ("thicket_breeches", "Thicket Breeches", "amberwood", 2, "pants",
     ("patch", "fur", "tooth", "wrap")),
    ("bramblebound_pants", "Bramblebound Trousers", "amberwood", 3, "pants",
     ("vine", "wrap", "gem")),
    ("leafmail_legs", "Leafmail Leggings", "amberwood", 4, "legs",
     ("leaf", "scale", "greave")),
    ("heartwood_cuisses", "Heartwood Cuisses", "amberwood", 5, "legs",
     ("bark", "panel", "greave")),
    ("trapper_breeches", "Trapper Breeches", "amberwood", 6, "pants",
     ("fur", "tooth", "strap", "wrap")),
    ("amberglass_legs", "Amberglass Leggings", "amberwood", 7, "legs",
     ("gem", "tasset", "greave", "strap")),
    ("antlerward_legs", "Antlerward Leggings", "amberwood", 8, "kilt",
     ("panel", "vine", "bone", "greave")),
    # -- sheet 4: sunmane ---------------------------------------------------
    ("steppe_riding_pants", "Steppe Riding Trousers", "sunmane", 1, "pants",
     ("stitch", "buckle", "tassel")),
    ("sunmane_sarong", "Sunmane Sarong", "sunmane", 2, "kilt",
     ("panel", "sash", "wrap")),
    ("fringed_chaps", "Fringed Chaps", "sunmane", 3, "pants",
     ("fringe", "buckle", "strap")),
    ("bonetoggle_breeches", "Bonetoggle Breeches", "sunmane", 4, "pants",
     ("bone", "tassel", "wrap")),
    ("sundisc_tassets", "Sundisc Tassets", "sunmane", 5, "kilt",
     ("tasset", "panel", "disc")),
    ("caravan_wrap", "Caravan Wrap", "sunmane", 6, "kilt",
     ("panel", "sash", "tassel")),
    ("outrider_canvas", "Outrider Canvas", "sunmane", 7, "pants",
     ("pouch", "strap", "buckle")),
    ("sunplate_cuisses", "Sunplate Cuisses", "sunmane", 8, "legs",
     ("tasset", "disc", "greave", "sash")),
    # -- sheet 5: ceremonial ------------------------------------------------
    ("argent_cuisses", "Argent Cuisses", "ceremonial", 1, "legs",
     ("tasset", "kneecop", "greave")),
    ("vigil_cuisses", "Vigil Cuisses", "ceremonial", 2, "legs",
     ("tasset", "quilt", "kneecop", "greave")),
    ("chapel_cuisses", "Chapel Cuisses", "ceremonial", 3, "legs",
     ("tasset", "quilt", "kneecop", "greave")),
    ("pilgrim_cuisses", "Pilgrim Cuisses", "ceremonial", 4, "legs",
     ("tasset", "kneecop", "greave")),
    ("crimson_guard_legs", "Crimson Guard Cuisses", "ceremonial", 5, "kilt",
     ("panel", "tasset", "kneecop", "greave")),
    ("cathedral_cuisses", "Cathedral Cuisses", "ceremonial", 6, "legs",
     ("tasset", "kneecop", "greave", "trim")),
    ("standard_bearer_legs", "Standard Bearer Cuisses", "ceremonial", 7, "kilt",
     ("panel", "tasset", "kneecop", "greave")),
    ("nightwatch_cuisses", "Nightwatch Cuisses", "ceremonial", 8, "legs",
     ("tasset", "kneecop", "greave", "scale")),
    # -- sheet 6: militia ---------------------------------------------------
    ("quilted_chausses", "Quilted Chausses", "militia", 1, "pants",
     ("quilt", "lace")),
    ("padded_leathers", "Padded Leathers", "militia", 2, "pants",
     ("kneecop", "buckle", "lace")),
    ("splinted_cuisses", "Splinted Cuisses", "militia", 3, "legs",
     ("splint", "buckle", "greave")),
    ("mail_chausses", "Mail Chausses", "militia", 4, "legs",
     ("mail", "buckle", "greave")),
    ("brigandine_legs", "Brigandine Leggings", "militia", 5, "legs",
     ("stud", "tasset", "buckle", "greave")),
    ("levy_breeches", "Levy Breeches", "militia", 6, "pants",
     ("kneecop", "buckle")),
    ("brass_cuisses", "Brass Cuisses", "militia", 7, "legs",
     ("tasset", "kneecop", "greave", "trim")),
    ("sergeant_cuisses", "Sergeant Cuisses", "militia", 8, "legs",
     ("tasset", "stud", "kneecop", "greave")),
    # -- sheet 7: ranger ----------------------------------------------------
    ("scout_leathers", "Scout Leathers", "ranger", 1, "pants",
     ("pouch", "strap", "wrap", "buckle")),
    ("poacher_breeches", "Poacher Breeches", "ranger", 2, "pants",
     ("pouch", "tooth", "patch", "wrap")),
    ("stalker_leathers", "Stalker Leathers", "ranger", 3, "pants",
     ("strap", "buckle", "wrap")),
    ("waylayer_breeches", "Waylayer Breeches", "ranger", 4, "pants",
     ("pouch", "lace", "strap")),
    ("forager_leathers", "Forager Leathers", "ranger", 5, "pants",
     ("pouch", "tassel", "wrap", "panel")),
    ("ropewalker_leathers", "Ropewalker Leathers", "ranger", 6, "pants",
     ("strap", "buckle", "coil", "wrap")),
    ("longcoat_leathers", "Longcoat Leathers", "ranger", 7, "kilt",
     ("panel", "stud", "pouch", "strap")),
    ("winterhide_breeches", "Winterhide Breeches", "ranger", 8, "pants",
     ("fur", "tooth", "pouch", "wrap")),
    # -- sheet 8: frontier --------------------------------------------------
    ("homespun_trousers", "Homespun Trousers", "frontier", 1, "pants",
     ("patch", "cord")),
    ("drover_trousers", "Drover Trousers", "frontier", 2, "pants",
     ("patch", "buckle")),
    ("mended_trousers", "Mended Trousers", "frontier", 3, "pants",
     ("patch", "pouch", "cord")),
    ("linen_trousers", "Linen Trousers", "frontier", 4, "pants",
     ("pouch", "trim", "cord")),
    ("sashed_trousers", "Sashed Trousers", "frontier", 5, "pants",
     ("sash", "wrap")),
    ("kneepatch_trousers", "Kneepatch Trousers", "frontier", 6, "pants",
     ("patch", "lace", "buckle")),
    ("dyer_trousers", "Dyer Trousers", "frontier", 7, "pants",
     ("patch", "cord", "cuffroll")),
    ("crofter_trousers", "Crofter Trousers", "frontier", 8, "pants",
     ("patch", "cord", "wrap")),
]

SHEETS = ("legendary", "arcane", "amberwood", "sunmane",
          "ceremonial", "militia", "ranger", "frontier")

KIND_COUNTS: dict[str, int] = {}
for _entry in ROSTER:
    KIND_COUNTS[_entry[4]] = KIND_COUNTS.get(_entry[4], 0) + 1


def tile(slug: str) -> str:
    """The concept tile a design was read from."""
    for entry in ROSTER:
        if entry[0] == slug:
            return f"{entry[2]}_{entry[3]}.png"
    raise KeyError(slug)


if __name__ == "__main__":
    print(f"{len(ROSTER)} designs")
    for kind, count in sorted(KIND_COUNTS.items()):
        print(f"  {kind:6s} {count}")
    slugs = [entry[0] for entry in ROSTER]
    assert len(set(slugs)) == len(slugs), "duplicate slug"
    for sheet in SHEETS:
        rows = [e for e in ROSTER if e[2] == sheet]
        assert len(rows) == 8, f"{sheet} has {len(rows)}"
        assert sorted(e[3] for e in rows) == list(range(1, 9)), sheet
    features = sorted({f for e in ROSTER for f in e[5]})
    print(f"  features ({len(features)}): {' '.join(features)}")
