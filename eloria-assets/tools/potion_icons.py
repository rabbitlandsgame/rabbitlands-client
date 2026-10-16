#!/usr/bin/env python3
"""Define the potion shelf and paint each bottle its own icon.

Added 2026-09-02 for Eloria Client.

The server's potion effects are keyed by item name (dev-server
eloria/potions.py), so a profile without items of those names has working
potion machinery and nothing to drink.  This tool is the potion counterpart
of ``import_generated_equipment``: one roster that owns both halves of every
potion --

  the server item   dev-server/config/eloria/items.txt, an [item] block
  the icon pixels   painted here, packed by tools/build_item_icon_atlases.py

-- so the names the effects bind to, the ids the client draws by, and the
bottles the player tells apart are decided in one place.

There are no meshes to render: a potion's icon is painted, the way
``paint_material_icons`` paints the harvestables.  Every bottle is drawn from
its effect: red for health and blue for ether, a smaller vial for a smaller
draught and a full flask for a greater one, tall bottles for the practice
(skill) draughts, round-bellied flasks for the attribute tonics, stoppered
square bottles with a warded glow for the resistances, and a jug for the meal
in a bottle.  Shape, size, colour and trim never repeat as a set, so no two
icons read alike in the bag.

  python potion_icons.py                 write the server items
  python potion_icons.py --dry-run       say what would change
  python potion_icons.py --preview DIR   also save each icon as a PNG

Idempotent, like its siblings: the server block is marker-fenced and
rewritten whole.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import import_generated_equipment as armour

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parent.parent / "godot-client"
PROJECT = HERE.parent.parent.parent

#: The recovered empty-slot plate every icon composites onto -- the same one
#: the rendered equipment icons use, so the shelf sits in the same frames.
TEMPLATE = PROJECT / "generate_models" / "equipment_icons" / "template.png"

OPEN_ITEMS = "# --- potion and magic supplies (eloria-assets/tools/potion_icons.py) ---"
CLOSE_ITEMS = "# --- end potion and magic supplies ---"

#: Item ids leave the weapon roster room to grow (it ends at 1629 today), but
#: the image ids continue the atlas's single contiguous run directly after the
#: weapons' 473: the client pins that painted prefix, so a reserved gap would
#: read as unpainted cells.  A weapon added later simply takes its icon after
#: the shelf.
FIRST_ITEM_ID = 1650
FIRST_IMAGE_ID = 474


def _server_beside(client: Path) -> Path:
    """Same pairing rule as import_generated_weapons: a ``wt-<name>`` client
    worktree writes into ``wt-<name>-server`` beside it, anything else into
    the main dev-server checkout."""
    paired = client.parent.parent / (client.parent.name + "-server")
    return paired if paired.is_dir() else PROJECT / "dev-server"


SERVER = _server_beside(CLIENT)


class Potion:
    __slots__ = ("name", "category", "emu", "fields", "description",
                 "shape", "scale", "liquid", "accent", "motif", "glow",
                 "item_id", "image_id")

    def __init__(self, name, category, emu, fields, description,
                 shape, scale, liquid, accent=None, motif="", glow=False):
        self.name, self.category, self.emu = name, category, emu
        self.fields, self.description = fields, description
        self.shape, self.scale, self.liquid = shape, scale, liquid
        self.accent, self.motif, self.glow = accent or liquid, motif, glow
        self.item_id = self.image_id = 0  # assigned by roster order

    @property
    def slug(self) -> str:
        return self.name.casefold().replace(" ", "_")


#: The shelf.  Order is the id order, so a row added anywhere but the end
#: would renumber every potion below it; append only.
#:
#: The names are load-bearing: dev-server/eloria/potions.py binds effects by
#: exactly these strings.  ``Potion of Feasting`` is deliberately absent from
#: that table -- food restoration rides the item's own ``food`` field through
#: the eating path, cap and cooldown included.
SHELF = [
    # -- restoration: red for health, blue for ether; the vessel grows with
    #    the draught, and the small vials give their glass back.
    Potion("Potion of Minor Healing", "Potions", 1,
           {"cooldown": "4"},
           "A swallow of red tonic that closes small wounds. The vial is worth keeping.",
           "vial_small", 0.72, (204, 44, 56)),
    Potion("Potion of Body Restoration", "Potions", 1,
           {"cooldown": "6"},
           "A full measure of red tonic that knits flesh and bruise alike.",
           "flask_round", 0.9, (198, 36, 48)),
    Potion("Potion of Great Healing", "Potions", 2,
           {"cooldown": "6"},
           "A surgeon's flask of concentrated red tonic for wounds that should have been fatal.",
           "flask_large", 1.0, (216, 28, 44), glow=True),
    Potion("Potion of Mana", "Potions", 1,
           {"cooldown": "8"},
           "A sip of blue distillate that steadies the ethereal reserve. The vial is worth keeping.",
           "vial_small", 0.72, (52, 96, 220)),
    Potion("Potion of Spirit Restoration", "Potions", 1,
           {"cooldown": "17"},
           "A deep blue draught that refills a working caster's reserve.",
           "flask_round", 0.9, (44, 84, 210)),
    Potion("Potion of Extra Mana", "Potions", 2,
           {"cooldown": "15"},
           "A brimming flask of blue distillate for spellwork that will not wait.",
           "flask_large", 1.0, (64, 112, 240), glow=True),
    # -- sustenance and momentum.
    Potion("Potion of Feasting", "Potions", 2,
           {"food": "45", "cooldown": "10"},
           "A stew reduced to a jug: a full meal for a traveller who cannot stop to cook.",
           "jug", 1.0, (206, 132, 44)),
    Potion("Potion of Action Points", "Potions", 1,
           {"cooldown": "10"},
           "A sharp green tonic that lends a burst of fighting wind.",
           "vial_tall", 0.85, (36, 190, 148), motif="spark"),
    # -- attribute tonics: one round-bellied flask per attribute, told apart
    #    by the colour of what fills it.
    Potion("Potion of Might", "Potions", 1, {"cooldown": "10"},
           "A maroon tonic that briefly hardens muscle and frame.",
           "flask_round", 0.82, (152, 38, 46)),
    Potion("Potion of Dexterity", "Potions", 1, {"cooldown": "10"},
           "An orange tonic that briefly quickens hand and eye.",
           "flask_round", 0.82, (228, 138, 34)),
    Potion("Potion of Rationality", "Potions", 1, {"cooldown": "10"},
           "A clear azure tonic that briefly sharpens deliberate thought.",
           "flask_round", 0.82, (74, 158, 228)),
    Potion("Potion of Ethereality", "Potions", 1, {"cooldown": "10"},
           "A violet tonic that briefly widens the channel spellwork runs through.",
           "flask_round", 0.82, (142, 72, 202)),
    Potion("Potion of Toughness", "Potions", 1, {"cooldown": "10"},
           "A rose tonic that briefly thickens skin against a blow.",
           "flask_round", 0.82, (228, 92, 132)),
    Potion("Potion of Perception", "Potions", 1, {"cooldown": "10"},
           "A forest-green tonic that briefly wakes the older senses.",
           "flask_round", 0.82, (62, 158, 72)),
    # -- practice draughts: tall slim bottles, one hue per craft.
    Potion("Potion of Attack", "Potions", 1, {"cooldown": "10"},
           "A tall red draught that briefly recalls drilled strikes.",
           "vial_tall", 0.9, (190, 62, 50)),
    Potion("Potion of Defense", "Potions", 1, {"cooldown": "10"},
           "A tall slate draught that briefly recalls drilled guards.",
           "vial_tall", 0.9, (92, 110, 172)),
    Potion("Potion of Harvesting", "Potions", 1, {"cooldown": "10"},
           "A tall wheat-gold draught that briefly guides a gatherer's hands.",
           "vial_tall", 0.9, (212, 172, 62)),
    Potion("Potion of Manufacturing", "Potions", 1, {"cooldown": "10"},
           "A tall bronze draught that briefly guides a maker's measures.",
           "vial_tall", 0.9, (172, 122, 62)),
    Potion("Potion of Summoning", "Potions", 1, {"cooldown": "10"},
           "A tall indigo draught that briefly steadies a summoner's call.",
           "vial_tall", 0.9, (102, 82, 202)),
    Potion("Potion of Crafting", "Potions", 1, {"cooldown": "10"},
           "A tall copper draught that briefly steadies fine work.",
           "vial_tall", 0.9, (202, 112, 72)),
    Potion("Potion of Alchemy", "Potions", 1, {"cooldown": "10"},
           "A tall emerald draught that briefly clarifies an alchemist's eye.",
           "vial_tall", 0.9, (44, 182, 112)),
    Potion("Potion of Engineering", "Potions", 1, {"cooldown": "10"},
           "A tall gunmetal draught that briefly quiets an engineer's doubts.",
           "vial_tall", 0.9, (122, 132, 142)),
    Potion("Potion of Potion", "Potions", 1, {"cooldown": "10"},
           "A tall magenta draught that briefly perfects the brewer's pour.",
           "vial_tall", 0.9, (202, 72, 182)),
    Potion("Magic Potion", "Potions", 1, {"cooldown": "10"},
           "A tall arcane draught that briefly widens a caster's reach.",
           "vial_tall", 0.9, (152, 62, 222), glow=True),
    # -- combat edges.
    Potion("Potion of Accuracy", "Potions", 1, {"cooldown": "10"},
           "An amber tonic that briefly trues every swing.",
           "vial_tall", 0.85, (230, 182, 52), motif="spark"),
    Potion("Potion of Evasion", "Potions", 1, {"cooldown": "10"},
           "A quicksilver tonic that briefly makes a poor target of you.",
           "vial_tall", 0.85, (182, 192, 202)),
    # -- warding bottles: square-shouldered, stoppered, and lit from within.
    Potion("Potion of Cold Protection", "Potions", 1, {"cooldown": "10"},
           "A frosted ward in a bottle that turns aside deep cold for a time.",
           "square", 0.9, (122, 200, 240), motif="frost", glow=True),
    Potion("Potion of Heat Protection", "Potions", 1, {"cooldown": "10"},
           "An embered ward in a bottle that turns aside searing heat for a time.",
           "square", 0.9, (240, 92, 32), motif="spark", glow=True),
    Potion("Potion of Radiation Protection", "Potions", 1, {"cooldown": "10"},
           "A pale ward in a bottle that turns aside creeping corruption for a time.",
           "square", 0.9, (172, 210, 44), motif="dots", glow=True),
    Potion("Potion of Magic Protection", "Potions", 1, {"cooldown": "10"},
           "A dark ward in a bottle that blunts hostile spellwork for a time.",
           "square", 0.9, (122, 52, 200), glow=True),
    # -- remedies and glassware.
    Potion("Poison Antidote", "Potions", 1, {"cooldown": "10"},
           "A milky draught that drives venom out of the blood.",
           "vial_small", 0.8, (192, 228, 192)),
    Potion("Empty Vial", "Misc", 1, {},
           "Clean glass, ready for whatever is brewed next.",
           "vial_small", 0.72, None),
    # -- the six attributes the shelf had no draught for. Appended rather
    #    than filed beside the other tonics, because a row inserted anywhere
    #    but the end renumbers every potion below it.
    Potion("Potion of Matter", "Potions", 1, {"cooldown": "10"},
           "A slate tonic that briefly thickens what a body is made of.",
           "flask_round", 0.82, (128, 132, 140)),
    Potion("Potion of Carry", "Potions", 1, {"cooldown": "10"},
           "An amber tonic that briefly makes a heavy pack sit lighter.",
           "flask_round", 0.82, (196, 150, 60)),
    Potion("Potion of Charm", "Potions", 1, {"cooldown": "10"},
           "A blush tonic that briefly makes a stranger inclined to listen.",
           "flask_round", 0.82, (232, 132, 176)),
    Potion("Potion of Reaction", "Potions", 1, {"cooldown": "10"},
           "A pale citrine tonic that briefly shortens the gap between "
           "seeing and moving.",
           "flask_round", 0.82, (224, 210, 92)),
    Potion("Potion of Magic Offense", "Potions", 1, {"cooldown": "10"},
           "A tonic the colour of a struck spark, for spells that are "
           "meant to land.",
           "flask_round", 0.82, (236, 96, 40), glow=True),
    Potion("Potion of Magic Defense", "Potions", 1, {"cooldown": "10"},
           "A tonic the colour of deep water, for spells that are meant "
           "to hold.",
           "flask_round", 0.82, (48, 128, 176), glow=True),
    # -- the ten distillates spells are cast with, one per school. Narrow
    #    phials rather than bottles, because nobody drinks them; the colour
    #    names the school. Ids continue after the armour set's sabatons.
    Potion("Life Distillate", "Catalysts", 1, {},
           "Sage and hearthroot pressed down to a green drop that remembers growing.",
           "phial", 0.82, (86, 190, 82)),
    Potion("Fire Distillate", "Catalysts", 1, {},
           "Coal and flint reduced to an ember-bright drop that will not stay cool.",
           "phial", 0.82, (236, 104, 36), motif="spark"),
    Potion("Water Distillate", "Catalysts", 1, {},
           "Kelp and watercress drawn down to a clear blue drop that is always moving.",
           "phial", 0.82, (52, 132, 222)),
    Potion("Earth Distillate", "Catalysts", 1, {},
           "Clay and peat settled into a brown drop as heavy as a field.",
           "phial", 0.82, (150, 104, 58), motif="dots"),
    Potion("Matter Distillate", "Catalysts", 1, {},
           "Quartz and bog iron ground into a grey drop that holds its shape.",
           "phial", 0.82, (142, 148, 158), motif="dots"),
    Potion("Air Distillate", "Catalysts", 1, {},
           "Seed and reed winnowed to a pale drop that barely weighs the glass.",
           "phial", 0.82, (200, 226, 236)),
    Potion("Death Distillate", "Catalysts", 1, {},
           "Toadstool and thistle rotted down to a bruise-coloured drop. Stopper it.",
           "phial", 0.82, (104, 70, 112)),
    Potion("Energy Distillate", "Catalysts", 1, {},
           "Stormglass and verdigris charged into a yellow drop that hums.",
           "phial", 0.82, (238, 206, 52), motif="spark", glow=True),
    Potion("Spirit Distillate", "Catalysts", 1, {},
           "Silverleaf and lichen drawn into a pale violet drop that seems to look back.",
           "phial", 0.82, (190, 176, 246), glow=True),
    Potion("Magic Distillate", "Catalysts", 1, {},
           "Lotus and resin refined into a deep purple drop of pure working.",
           "phial", 0.82, (150, 66, 216), motif="frost", glow=True),
]

#: Where the shelf stopped when the torso designs took the ids and icons
#: directly after it -- items 1682-1745, icons 506-569. A row past that point
#: continues after that tail rather than into it, which is also why this
#: number is frozen: it is a fact about what was already handed out.
SHELF_BEFORE_TORSO = 32
#: The first id and icon after the torso designs' tail.
CONTINUED_ITEM_ID = 1746
CONTINUED_IMAGE_ID = 570
#: Where the shelf stopped the second time: the armour set's eight sabatons
#: took icons 576-583 and the practice items took item ids up to 1833. Frozen
#: for the same reason as SHELF_BEFORE_TORSO.
SHELF_BEFORE_SABATONS = 38
#: The distillates' first id and icon. Item ids leave the practice items room.
DISTILLATE_ITEM_ID = 1850
DISTILLATE_IMAGE_ID = 584
#: Where the shelf stopped the third time: the island crops (crop_icons.py)
#: took icons 594-595 directly after the distillates, and the server stream
#: gives their items the ids after Magic Distillate (crop_icons.SERVER_ITEM_IDS,
#: proposed 1860-1861). A distillate appended past this point would otherwise
#: be handed exactly those ids. Frozen for the same reason as the others.
SHELF_BEFORE_CROPS = 48
#: The first id and icon after the crops. The crop roster grew on 2026-10-14
#: (Grapes, Cabbage and Rosemary at icons 596-598, Grapes and Cabbage at items
#: 1892-1893, after Large Hide and the spell tomes took 1862-1891), and no
#: bottle had been appended here yet, so this moved with it. It moved once
#: more on 2026-10-16, still before any bottle: the server gave item 1894 to
#: the Watch Arming Sword. main() now refuses to write a potion whose item id
#: or icon an item outside this tool's fence already holds.
AFTER_CROPS_ITEM_ID = 1895
AFTER_CROPS_IMAGE_ID = 599

for index, potion in enumerate(SHELF):
    if index < SHELF_BEFORE_TORSO:
        potion.item_id = FIRST_ITEM_ID + index
        potion.image_id = FIRST_IMAGE_ID + index
    elif index >= SHELF_BEFORE_CROPS:
        potion.item_id = AFTER_CROPS_ITEM_ID + index - SHELF_BEFORE_CROPS
        potion.image_id = AFTER_CROPS_IMAGE_ID + index - SHELF_BEFORE_CROPS
    elif index >= SHELF_BEFORE_SABATONS:
        potion.item_id = DISTILLATE_ITEM_ID + index - SHELF_BEFORE_SABATONS
        potion.image_id = DISTILLATE_IMAGE_ID + index - SHELF_BEFORE_SABATONS
    else:
        potion.item_id = CONTINUED_ITEM_ID + index - SHELF_BEFORE_TORSO
        potion.image_id = CONTINUED_IMAGE_ID + index - SHELF_BEFORE_TORSO


def roster() -> list[Potion]:
    """Every potion, in the fixed order that owns its ids."""
    return list(SHELF)


# ---------------------------------------------------------------------------
# Painting
# ---------------------------------------------------------------------------

#: Icons are drawn at four times the cell and reduced, so the glass keeps a
#: smooth edge at 50 pixels.
SS = 4
CELL = 50


def _vessel_paths(shape: str, scale: float):
    """The vessel as (glass outline, liquid body, neck top y) in a unit box.

    Coordinates are in a 100x100 box, y down; the caller scales them.  Each
    shape returns the glass polygon and the y of the liquid's surface.
    """
    if shape == "vial_small":
        glass = [(42, 24), (58, 24), (58, 34), (60, 38), (60, 78),
                 (56, 86), (44, 86), (40, 78), (40, 38), (42, 34)]
        return glass, 44, (44, 56, 18, 26)
    if shape == "vial_tall":
        glass = [(44, 14), (56, 14), (56, 26), (58, 30), (58, 82),
                 (54, 90), (46, 90), (42, 82), (42, 30), (44, 26)]
        return glass, 34, (46, 54, 8, 16)
    if shape == "flask_round":
        glass = [(44, 16), (56, 16), (56, 30), (66, 38), (70, 50),
                 (70, 66), (62, 80), (50, 84), (38, 80), (30, 66),
                 (30, 50), (34, 38), (44, 30)]
        return glass, 42, (46, 54, 10, 18)
    if shape == "flask_large":
        glass = [(44, 10), (56, 10), (56, 24), (70, 34), (76, 48),
                 (76, 68), (66, 84), (50, 90), (34, 84), (24, 68),
                 (24, 48), (30, 34), (44, 24)]
        return glass, 34, (46, 54, 4, 12)
    if shape == "jug":
        glass = [(40, 16), (60, 16), (60, 24), (70, 30), (74, 44),
                 (74, 70), (66, 84), (34, 84), (26, 70), (26, 44),
                 (30, 30), (40, 24)]
        return glass, 36, (43, 57, 10, 18)
    if shape == "phial":
        glass = [(46, 20), (54, 20), (54, 34), (62, 50), (63, 68),
                 (56, 84), (50, 88), (44, 84), (37, 68), (38, 50),
                 (46, 34)]
        return glass, 52, (46, 54, 12, 22)
    if shape == "square":
        glass = [(42, 14), (58, 14), (58, 24), (68, 28), (68, 82),
                 (62, 88), (38, 88), (32, 82), (32, 28), (42, 24)]
        return glass, 36, (45, 55, 8, 16)
    raise ValueError(f"unknown vessel shape {shape!r}")


def _scaled(points, scale: float, size: int):
    """Unit-box points scaled about the box centre onto an image of `size`."""
    factor = size / 100.0
    cx = cy = size / 2.0
    return [(cx + (x - 50) * scale * factor, cy + (y - 50) * scale * factor)
            for x, y in points]


def paint(potion: Potion) -> Image.Image:
    """One 50x50 cell: the shared plate with this potion's bottle on it."""
    plate = Image.open(TEMPLATE).convert("RGBA")
    size = CELL * SS
    art = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(art)

    glass_points, surface_y, (neck_left, neck_right, top_y, mouth_y) = \
        _vessel_paths(potion.shape, 1.0)
    glass = _scaled(glass_points, potion.scale, size)

    # A warded or empowered bottle glows before anything else is drawn, so
    # the halo sits behind the glass.
    if potion.glow and potion.liquid:
        halo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(halo).polygon(glass, fill=potion.accent + (110,))
        art = Image.alpha_composite(
            art, halo.filter(ImageFilter.GaussianBlur(size * 0.045)))
        draw = ImageDraw.Draw(art)

    # The glass itself: a cool tint so an empty vessel still reads.
    draw.polygon(glass, fill=(196, 214, 224, 68))

    # The liquid: the glass polygon clipped below the surface line, shaded
    # darker toward the bottom in three bands so it reads as depth.
    if potion.liquid:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).polygon(glass, fill=255)
        level = _scaled([(0, surface_y)], potion.scale, size)[0][1]
        body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        body_draw = ImageDraw.Draw(body)
        red, green, blue = potion.liquid
        bottom = size
        for band, shade in ((0.0, 1.18), (0.45, 1.0), (0.75, 0.72)):
            top = level + (bottom - level) * band
            colour = (min(255, int(red * shade)), min(255, int(green * shade)),
                      min(255, int(blue * shade)), 235)
            body_draw.rectangle([0, top, size, bottom], fill=colour)
        body.putalpha(Image.composite(
            body.split()[3], Image.new("L", (size, size), 0), mask))
        art = Image.alpha_composite(art, body)
        draw = ImageDraw.Draw(art)
        # The meniscus: a lighter ellipse where the liquid meets the glass.
        half_width = potion.scale * size * 0.13
        draw.ellipse([size / 2 - half_width, level - size * 0.015,
                      size / 2 + half_width, level + size * 0.015],
                     fill=(min(255, red + 70), min(255, green + 70),
                           min(255, blue + 70), 200))

    # Glass rim and a short shine on the shoulder.
    draw.line(glass + [glass[0]], fill=(226, 238, 244, 150),
              width=max(2, int(size * 0.012)))
    shine = _scaled([(43, 30), (45.5, 30), (44, 52), (41.5, 52)],
                    potion.scale, size)
    draw.polygon(shine, fill=(255, 255, 255, 55))

    # The cork, seated in the mouth with a modest crown above it.
    neck = _scaled([(neck_left, top_y), (neck_right, top_y),
                    (neck_right, mouth_y + 2), (neck_left, mouth_y + 2)],
                   potion.scale, size)
    draw.polygon(neck, fill=(122, 86, 54, 255))
    cap_left, cap_top = neck[0]
    cap_right, cap_bottom = neck[2]
    crown = (cap_bottom - cap_top) * 0.35
    draw.ellipse([cap_left - crown * 0.4, cap_top - crown,
                  cap_right + crown * 0.4, cap_top + crown],
                 fill=(150, 108, 68, 255))

    # Motifs: a few accents floating over the liquid, per effect family.
    if potion.motif and potion.liquid:
        accent = potion.accent
        centre_x, centre_y = size / 2, size * 0.62
        spread = potion.scale * size * 0.11
        points = [(-1.1, -0.2), (0.9, -0.7), (0.2, 0.9), (-0.4, 0.5),
                  (1.0, 0.6)]
        for index, (dx, dy) in enumerate(points):
            x, y = centre_x + dx * spread, centre_y + dy * spread
            radius = size * (0.012 if index % 2 else 0.018)
            bright = tuple(min(255, channel + 90) for channel in accent)
            if potion.motif == "frost":
                arm = radius * 2.2
                for ax, ay in ((arm, 0), (0, arm), (arm * 0.7, arm * 0.7),
                               (arm * 0.7, -arm * 0.7)):
                    draw.line([x - ax, y - ay, x + ax, y + ay],
                              fill=bright + (190,),
                              width=max(1, int(size * 0.008)))
            elif potion.motif == "spark":
                draw.line([x, y - radius * 2.4, x, y + radius * 2.4],
                          fill=bright + (200,), width=max(1, int(size * 0.008)))
                draw.line([x - radius * 1.6, y, x + radius * 1.6, y],
                          fill=bright + (200,), width=max(1, int(size * 0.008)))
            else:  # dots
                draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                             fill=bright + (210,))

    art = art.resize((CELL, CELL), Image.LANCZOS)
    return Image.alpha_composite(plate, art)


# ---------------------------------------------------------------------------
# The server half
# ---------------------------------------------------------------------------

def item_block(potion: Potion) -> str:
    lines = ["", "[item]",
             "name: %s" % potion.name,
             "item_id: %d" % potion.item_id,
             "image_id: %d" % potion.image_id,
             "emu: %d" % potion.emu,
             "flags: 6",
             "category: %s" % potion.category,
             "description: %s" % potion.description]
    lines.extend("%s: %s" % (key, value)
                 for key, value in potion.fields.items())
    lines.append("[/item]")
    return "\n".join(lines)


def _outside_fence(catalogue: str) -> str:
    """The catalogue without the rows this tool owns."""
    if OPEN_ITEMS not in catalogue:
        return catalogue
    head, _, rest = catalogue.partition(OPEN_ITEMS)
    return head + rest.partition(CLOSE_ITEMS)[2]


def _values(catalogue: str, key: str) -> set[int]:
    """Every whole-number `key:` value (item_id, image_id) in the catalogue."""
    values = set()
    for line in catalogue.splitlines():
        field, _, value = line.partition(":")
        if field.strip() == key and value.strip().isdigit():
            values.add(int(value))
    return values


def id_collisions(potions: list[Potion], catalogue: str) -> list[str]:
    """The potions whose item id or icon another item already holds.

    The shelf's ids are frozen by roster order, so the server can hand out an
    id in a range no bottle has used yet; writing over it would give two items
    one id. This reads the catalogue at write time instead of trusting the
    boundaries above."""
    others = _outside_fence(catalogue)
    items, images = _values(others, "item_id"), _values(others, "image_id")
    clashes = ["%s: item %d" % (p.name, p.item_id) for p in potions
               if p.item_id in items]
    clashes += ["%s: icon %d" % (p.name, p.image_id) for p in potions
                if p.image_id in images]
    if clashes:
        clashes.append("next free outside the fence: item %d, icon %d; freeze "
                       "a new shelf boundary there (see SHELF_BEFORE_CROPS)"
                       % (max(items) + 1, max(images) + 1))
    return clashes


def main() -> int:
    ap = argparse.ArgumentParser(
        description="define the potion shelf and paint its icons")
    ap.add_argument("--server", type=Path, default=SERVER,
                    help="dev-server checkout to write the item definitions "
                         "into; defaults to the worktree pair or the main one")
    ap.add_argument("--preview", type=Path, default=None,
                    help="also write each painted icon to this directory")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    potions = roster()
    print("%d potions: items %d-%d, icons %d-%d"
          % (len(potions), potions[0].item_id, potions[-1].item_id,
             potions[0].image_id, potions[-1].image_id))
    if args.dry_run:
        for potion in potions:
            print("  %-32s %-8s item %d icon %d"
                  % (potion.name, potion.shape, potion.item_id,
                     potion.image_id))
        print("\nnothing written (--dry-run)")
        return 0

    if args.preview:
        args.preview.mkdir(parents=True, exist_ok=True)
        for potion in potions:
            paint(potion).save(args.preview / ("%s.png" % potion.slug))
        print("previews in %s" % args.preview)

    items_path = args.server / "config/eloria/items.txt"
    catalogue = items_path.read_text(encoding="utf-8")
    collisions = id_collisions(potions, catalogue)
    if collisions:
        print("these ids are already taken by other items:\n  %s"
              % "\n  ".join(collisions), file=sys.stderr)
        return 2
    catalogue = _outside_fence(catalogue)
    taken = {line.partition(":")[2].strip().casefold()
             for line in catalogue.splitlines() if line.startswith("name:")}
    clash = sorted(p.name for p in potions if p.name.casefold() in taken)
    if clash:
        print("these names are already in the catalogue: %s"
              % ", ".join(clash), file=sys.stderr)
        return 2

    body = "\n".join(item_block(potion) for potion in potions).lstrip("\n")
    items_path.write_text(
        armour.fence(items_path.read_text(encoding="utf-8"), OPEN_ITEMS,
                     CLOSE_ITEMS, body), encoding="utf-8")
    print("items    %s" % items_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
