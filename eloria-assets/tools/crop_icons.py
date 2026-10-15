#!/usr/bin/env python3
"""The island crops' inventory icons: the fifth set packed into the atlases.

Added 2026-10-02 for Eloria Client.

The south-west isle grows two signature crops the server does not ship yet,
Olive and Lemon (island content plan, harvest plan section 5). A harvested
item reaches the bag as its `image_id` and nothing else, so each crop needs a
painted cell before the server hands one out - otherwise the bag draws the
unknown-item glyph for it, which is what happened to the regional harvest
resources until `paint_material_icons.py` painted them.

Like the potion shelf, the crops have no mesh worth rendering at 50 pixels (a
harvest node is a shrub, the item is the fruit), so they are painted here, in
the same height-field light as the Nymara material icons and on the same
empty-slot plate as every generated set since 118.

Ids follow the ledger's rules (memory `eloria-item-economy`): image ids
continue the atlas's single contiguous run after the distillates' 593, and
this roster is append only.

Appended 2026-10-14 (Landfall liveliness H5/H6): Grapes and Cabbage, the
crops of the Tollholm vineyards and the Tollholm and Spindle Hill cabbage
fields, at 596 and 597, and Rosemary at 598. Rosemary is an old bootstrap
herb, item 30, released from testing for Ringholm and Spindle Hill; it had
always borrowed Sage's cell 101, so on a map where both grow the bag could
not tell them apart. It is painted here because it is the same kind of
picture - a plant, not a mesh - and this is the roster that appends. The roster owns IMAGE ids only. The server's
items.txt owns the item ids; the island content plan proposes Olive = item
1860 and Lemon = item 1861, recorded in SERVER_ITEM_IDS so potion_icons.py
continues after them instead of handing the next distillate the same ids.
The server stream appends the two [item] blocks AFTER the
`# --- end potion and magic supplies ---` marker, never inside that fence:
potion_icons.py rewrites the fenced block whole and would delete them.
Nothing here writes into the server checkout.

  python crop_icons.py --preview <dir>   paint the icons to a directory
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from paint_material_icons import _over, _rotate, _shade
import potion_icons

#: The first icon after the distillates (potion_icons.DISTILLATE_IMAGE_ID + 10).
FIRST_IMAGE_ID = 594
#: The item ids the server stream gives the crops (island content plan; the
#: server's items.txt owns them). Recorded so the potion shelf, which writes
#: item ids into the server's fence, never hands one out again. Grapes and
#: Cabbage follow the spell tomes (1863-1891); Rosemary keeps its old id.
SERVER_ITEM_IDS = {"Olive": 1860, "Lemon": 1861, "Grapes": 1892,
                   "Cabbage": 1893, "Rosemary": 30}

CELL = 50
#: Painted at four times the cell and reduced, as the potion shelf is.
SS = 4


class Crop:
    """A crop's icon. Its item - name, item id, food value, description - is
    the server's; the client owns only the picture and the id it sits at."""
    __slots__ = ("name", "shape", "image_id")

    def __init__(self, name: str, shape: str):
        self.name, self.shape = name, shape
        self.image_id = 0  # assigned by roster order

    @property
    def slug(self) -> str:
        return self.name.casefold().replace(" ", "_")


#: Order is the id order: append only.
CROPS = [
    Crop("Olive", "olive_sprig"),
    Crop("Lemon", "lemon"),
    Crop("Grapes", "grape_bunch"),
    Crop("Cabbage", "cabbage"),
    Crop("Rosemary", "rosemary_sprig"),
]

for index, crop in enumerate(CROPS):
    crop.image_id = FIRST_IMAGE_ID + index


def roster() -> list[Crop]:
    """Every crop, in the fixed order that owns its icon ids."""
    return list(CROPS)


# ---------------------------------------------------------------------------
# painting
# ---------------------------------------------------------------------------

def _grid(size: int):
    axis = (np.arange(size) + .5) / size * 2. - 1.
    return np.meshgrid(axis, axis)


def _ellipse(size: int, cx: float, cy: float, rx: float, ry: float,
             angle: float = 0., power: float = 2.):
    """A rounded solid's height field, rotated by `angle` (radians)."""
    x, y = _grid(size)
    x, y = x - cx, y - cy
    cos, sin = math.cos(angle), math.sin(angle)
    u, v = x * cos + y * sin, -x * sin + y * cos
    radial = np.abs(u / rx) ** power + np.abs(v / ry) ** power
    mask = radial <= 1.
    # Heights scale with the canvas so `_shade`'s per-pixel gradient lights a
    # supersampled solid the way it lights one painted at cell size.
    height = np.where(mask, np.sqrt(np.clip(1. - radial, 0., 1.)) * min(rx, ry), 0.)
    return height * (size / CELL), mask


def _stroke(size: int, start, end, width: float):
    """A twig: a flat-topped band from `start` to `end` in unit coordinates."""
    x, y = _grid(size)
    a, b = np.asarray(start), np.asarray(end)
    along = b - a
    length = float(np.linalg.norm(along))
    t = np.clip(((x - a[0]) * along[0] + (y - a[1]) * along[1]) / length ** 2, 0., 1.)
    distance = np.hypot(x - (a[0] + t * along[0]), y - (a[1] + t * along[1]))
    mask = distance <= width / 2.
    height = np.where(mask, np.sqrt(np.clip(1. - (distance / (width / 2.)) ** 2, 0., 1.))
                      * width * .5, 0.)
    return height * (size / CELL), mask


def _leaf(layer, size, cx, cy, angle, length, width, base, accent):
    height, mask = _ellipse(size, cx, cy, width, length, angle, power=1.5)
    layer = _over(layer, _shade(height, mask, base, accent, gloss=.45, rim=.24))
    # The midrib catches the light along the leaf's long axis.
    tip = _rotate(np.array([[0., -length * .85], [0., length * .85]]), -angle)
    rib, rib_mask = _stroke(size, tip[0] + (cx, cy), tip[1] + (cx, cy), .022)
    return _over(layer, _shade(rib, rib_mask & mask, accent, (255, 255, 255),
                               gloss=.3, rim=.0))


def _olive_sprig(size: int) -> np.ndarray:
    layer = np.zeros((size, size, 4))
    twig = (88, 66, 46), (150, 118, 84)
    layer = _over(layer, _shade(*_stroke(size, (-.70, -.54), (.46, .36), .065),
                                *twig, gloss=.2))
    silver = (112, 132, 92), (196, 210, 178)
    for cx, cy, angle in ((-.34, -.50, -1.05), (.07, -.25, -.80), (.48, -.04, -1.30)):
        layer = _leaf(layer, size, cx, cy, angle, .42, .10, *silver)
    # Three ripe olives and one still green: ripe ones are the isle's harvest,
    # the green one keeps a dark cluster from reading as grapes.
    for cx, cy, angle, base, accent in (
            (-.36, .09, .5, (70, 38, 64), (176, 132, 170)),
            (.00, .32, .2, (62, 34, 58), (170, 128, 166)),
            (.36, .56, .4, (78, 44, 70), (182, 140, 176)),
            (-.05, -.05, .3, (120, 134, 50), (214, 222, 140))):
        height, mask = _ellipse(size, cx, cy, .20, .26, angle)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.95,
                                    shininess=44., rim=.30))
    return layer


def _lemon(size: int) -> np.ndarray:
    layer = np.zeros((size, size, 4))
    angle = -.55
    yellow, highlight = (236, 196, 46), (255, 244, 170)
    body, body_mask = _ellipse(size, .02, .10, .62, .43, angle, power=2.1)
    axis = np.array([math.cos(angle), math.sin(angle)])
    for side in (-1., 1.):
        nub_x, nub_y = np.array([.02, .10]) + axis * side * .65
        nub, nub_mask = _ellipse(size, nub_x, nub_y, .11, .085, angle)
        body, body_mask = np.maximum(body, nub * .9), body_mask | nub_mask
    layer = _over(layer, _shade(body, body_mask, yellow, highlight, gloss=.70,
                                shininess=30., rim=.30))
    # Pitted rind: a fine stipple the light picks out on the lit side.
    x, y = _grid(size)
    pits = (np.sin(x * 90.) * np.sin(y * 84.)) > .82
    layer = _over(layer, _shade(np.zeros((size, size)), pits & body_mask,
                                (214, 170, 34), (214, 170, 34), gloss=0., rim=0.))
    stem_end = np.array([.02, .10]) + axis * .74
    layer = _over(layer, _shade(*_stroke(size, stem_end, stem_end + (.06, -.12), .05),
                                (96, 78, 48), (150, 128, 82), gloss=.2))
    return _leaf(layer, size, stem_end[0] - .24, stem_end[1] - .20, .95, .30, .13,
                 (70, 116, 50), (156, 196, 112))


def _grape_bunch(size: int) -> np.ndarray:
    layer = np.zeros((size, size, 4))
    # The cane the bunch hangs from, and the stalk down into it.
    cane = (92, 70, 46), (152, 122, 86)
    layer = _over(layer, _shade(*_stroke(size, (-.74, -.62), (.64, -.52), .065),
                                *cane, gloss=.2))
    layer = _over(layer, _shade(*_stroke(size, (.04, -.56), (.00, -.30), .05),
                                *cane, gloss=.2))
    # A vine leaf behind the cane: three lobes fanned from one base.
    green = (66, 112, 50), (150, 192, 108)
    base = np.array([-.26, -.54])
    for angle, length in ((2.45, .30), (3.20, .36), (3.95, .30)):
        direction = np.array([-math.sin(angle), math.cos(angle)])
        cx, cy = base + direction * length * .85
        layer = _leaf(layer, size, cx, cy, angle, length, .19, *green)
    # A tendril curling off the cane.
    points = [(.36 + .12 * math.cos(t) * (1 - t / 9), -.64 + .12 * math.sin(t) * (1 - t / 9))
              for t in np.linspace(0., 7., 12)]
    for a, b in zip(points, points[1:]):
        layer = _over(layer, _shade(*_stroke(size, a, b, .024), *cane, gloss=.2))
    # The bunch: a hanging cone of berries, painted top to bottom so each
    # lower berry sits in front of the row above; two dusks alternate.
    rows = ((-.28, (-.36, -.12, .12, .36)),
            (-.09, (-.44, -.22, .01, .24, .46)),
            (.11, (-.32, -.09, .14, .37)),
            (.31, (-.21, .03, .26)),
            (.50, (-.09, .15)),
            (.68, (.03,)))
    dusk = ((60, 46, 98), (168, 156, 214)), ((76, 44, 94), (190, 152, 210))
    for index, (cy, xs) in enumerate(rows):
        for k, cx in enumerate(xs):
            body, light = dusk[(index + k) % 2]
            radius = .125 + .014 * ((index * 3 + k) % 3) / 2.
            height, mask = _ellipse(size, cx, cy, radius, radius * 1.08, .3)
            layer = _over(layer, _shade(height, mask, body, light, gloss=.95,
                                        shininess=40., rim=.32))
    return layer


def _cabbage(size: int) -> np.ndarray:
    layer = np.zeros((size, size, 4))
    outer = (56, 106, 56), (146, 192, 118)
    rib = (176, 210, 150), (236, 248, 214)
    # The loose outer leaves, splayed behind and under the head, each with a
    # pale midrib and a wavy rim.
    centre = np.array([.0, .14])
    for angle, length, width in ((1.25, .40, .30), (-1.25, .40, .30),
                                 (2.45, .36, .28), (-2.45, .36, .28),
                                 (0., .34, .34)):
        direction = np.array([-math.sin(angle), math.cos(angle)])
        cx, cy = centre + direction * .42
        height, mask = _ellipse(size, cx, cy, width, length, angle, power=1.7)
        x, y = _grid(size)
        wave = .5 + .5 * np.sin(np.arctan2(y - cy, x - cx) * 9.)
        height = height * (.82 + .18 * wave)
        layer = _over(layer, _shade(height, mask, *outer, gloss=.35, rim=.30))
        tip = (cx + direction[0] * length * .85, cy + direction[1] * length * .85)
        stem, stem_mask = _stroke(size, tuple(centre), tip, .03)
        layer = _over(layer, _shade(stem, stem_mask & mask, *rib, gloss=.2, rim=0.))
    # The head, pale and tight.
    head, head_mask = _ellipse(size, .00, .08, .48, .44, 0.)
    pale = (138, 182, 96), (228, 242, 176)
    layer = _over(layer, _shade(head, head_mask, *pale, gloss=.55, shininess=18.,
                                rim=.26))
    # Two wrapper leaves folded round it, a little darker than the head.
    for cx, cy, rx, ry, angle in ((-.24, .14, .32, .42, .35), (.25, .16, .30, .40, -.35)):
        height, mask = _ellipse(size, cx, cy, rx, ry, angle)
        mask = mask & head_mask
        layer = _over(layer, _shade(head * .6 + height, mask, (108, 158, 80),
                                    (210, 232, 160), gloss=.45, shininess=18.,
                                    rim=.30))
    # Pale ribs fanning up from the stalk end.
    for end in ((-.40, -.10), (-.18, -.28), (.10, -.30), (.36, -.12), (-.30, .30), (.32, .32)):
        stem, stem_mask = _stroke(size, (.0, .48), end, .03)
        layer = _over(layer, _shade(stem, stem_mask & head_mask, *rib, gloss=.2, rim=0.))
    return layer


def _rosemary(size: int) -> np.ndarray:
    layer = np.zeros((size, size, 4))
    wood = (112, 94, 70), (176, 156, 126)
    needle = (70, 116, 82), (176, 214, 186)
    silver = (104, 140, 116), (214, 232, 220)
    # Two sprigs crossed at the cut end, the longer one forked.
    sprigs = (((-.56, .70), (.48, -.66), 11),
              ((-.48, .66), (-.50, -.52), 9),
              ((-.08, .16), (.62, -.04), 6))
    for start, end, count in sprigs:
        layer = _over(layer, _shade(*_stroke(size, start, end, .06), *wood, gloss=.2))
    for start, end, count in sprigs:
        a, b = np.asarray(start), np.asarray(end)
        along = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-along[1], along[0]])
        for step, t in enumerate(np.linspace(.14, .94, count)):
            point = a + (b - a) * t
            reach = .17 * (1. - .40 * t)
            for side in (-1., 1.):
                out = along * .45 + normal * side
                out /= np.linalg.norm(out)
                angle = math.atan2(-out[0], out[1])
                cx, cy = point + out * reach * .80
                body, light = needle if (step + (side > 0)) % 2 else silver
                height, mask = _ellipse(size, cx, cy, .040, reach, angle, power=1.6)
                layer = _over(layer, _shade(height, mask, body, light, gloss=.45, rim=.30))
        # The tip: a tuft of short needles round the end.
        for k in range(5):
            angle = math.atan2(-along[0], along[1]) + (k - 2) * .38
            direction = np.array([-math.sin(angle), math.cos(angle)])
            cx, cy = b + direction * .07
            height, mask = _ellipse(size, cx, cy, .036, .09, angle, power=1.6)
            layer = _over(layer, _shade(height, mask, *needle, gloss=.45, rim=.30))
    # Pale blue flowers in the axils of the main sprig.
    for cx, cy in ((-.26, .26), (.00, -.06), (.22, -.34), (-.56, .06), (.30, .02)):
        height, mask = _ellipse(size, cx, cy, .075, .060, .4)
        layer = _over(layer, _shade(height, mask, (136, 148, 214), (232, 236, 255),
                                    gloss=.7, rim=.3))
    return layer


PAINTERS = {"olive_sprig": _olive_sprig, "lemon": _lemon,
            "grape_bunch": _grape_bunch, "cabbage": _cabbage,
            "rosemary_sprig": _rosemary}


def paint(crop: Crop) -> Image.Image:
    """One 50x50 cell: the shared plate with this crop on it."""
    plate = Image.open(potion_icons.TEMPLATE).convert("RGBA")
    size = CELL * SS
    art = PAINTERS[crop.shape](size)
    art = Image.fromarray(np.clip(art, 0, 255).astype(np.uint8), "RGBA")
    inset = int(CELL * .86)
    art = art.resize((inset, inset), Image.LANCZOS)
    layer = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    origin = (CELL - inset) // 2
    layer.paste(art, (origin, origin))
    # A soft contact shadow seats the crop on the plate, as on the materials.
    alpha = np.asarray(layer.split()[3], dtype=np.float64) / 255.
    shadow = alpha
    for _ in range(3):
        shadow = (shadow + np.roll(shadow, 1, 0) + np.roll(shadow, -1, 0)
                  + np.roll(shadow, 1, 1) + np.roll(shadow, -1, 1)) / 5.
    shadow = np.roll(np.roll(shadow, 2, 0), 2, 1) * .5
    base = np.asarray(plate, dtype=np.float64)
    frame = base[:, :, 3] > 8
    base[:, :, :3] *= (1. - shadow[..., None] * frame[..., None])
    plate = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGBA")
    return Image.alpha_composite(plate, layer)


def main() -> int:
    ap = argparse.ArgumentParser(description="paint the island crops' icons")
    ap.add_argument("--preview", type=Path, required=True,
                    help="write each painted icon to this directory")
    args = ap.parse_args()
    crops = roster()
    args.preview.mkdir(parents=True, exist_ok=True)
    for crop in crops:
        paint(crop).save(args.preview / ("%s.png" % crop.slug))
        print("  %-8s icon %d" % (crop.name, crop.image_id))
    print("previews in %s" % args.preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
