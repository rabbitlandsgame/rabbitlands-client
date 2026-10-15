#!/usr/bin/env python3
"""Repaint the Nymara material item icons in the authored inventory style.

Added 2026-08-28 for Eloria Client.

``ItemAtlas`` slices every icon at ``(id % 5) * 50, (id / 5) * 50``.  Measured
against that grid the shipped atlases have three separate defects:

* Atlases 2, 3 and 4 were pasted 5, 11 and 19 pixels low, so every icon from id
  25 upwards renders with a slice of its neighbour along the top edge and loses
  the same amount off its own bottom.
* Pasting the placeholder block into atlas 4 overwrote the lower 19 rows of ids
  80-84, which now end in a hard transparent cut instead of a frame.
* Ids 85-100, the sixteen Nymara materials, are flat vector polygons on an empty
  cell, so half the harvestable economy reads as placeholder art in the bag.

This tool rebuilds all five atlases on the grid the client actually samples.  It
lifts each painted icon from its true position, restores the plate behind the
truncated ones, paints the sixteen materials with a small height-field shader,
and adds an explicit unknown-item glyph at id 101 so the atlas has something
honest to fall back to.  The plate itself is recovered from the authored art as
the per-pixel mode of the painted cells, so the frame and its lighting are the
real ones rather than a redrawn imitation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

CELL = 50
COLUMNS = 5
PER_ATLAS = 25
ATLAS_COUNT = 5
PAINTED_IDS = range(0, 85)
UNKNOWN_ID = 101
IMAGE_COUNT = 117

# How far below the sampling grid each shipped atlas was pasted, measured by
# folding every atlas's row-brightness profile onto one 50-pixel cell and
# correlating it against atlas 1, which is aligned.  Atlas 5 holds a single
# placeholder and is repainted from scratch.
ATLAS_ROW_OFFSETS = (0, 5, 11, 19, 0)

# Records how much of the paste offset is still baked into the authored art.
# It belongs with the rest of the client's item data rather than beside the
# pixels, which is where the retired DDS twins used to keep it.
LAYOUT_MANIFEST = "atlas_layout.json"


def layout_path(source: Path) -> Path:
    """`atlas_layout.json` for atlases living in `source`."""
    return source.parents[2] / "data" / "items" / LAYOUT_MANIFEST

# Ids whose lower rows are missing from the source: the last row of atlases 2
# and 3 runs past the 250-pixel canvas once the paste offset is undone, and the
# placeholder block was pasted straight over ids 80-84.  Their plate is restored
# and the surviving art is seated back onto it.
TRUNCATED_IDS = (45, 46, 47, 48, 49, 70, 71, 72, 73, 74, 80, 81, 82, 83, 84)

MATERIALS = [
    (85, "Pearl", "pearl", (232, 231, 226), (176, 205, 214)),
    (86, "Reed", "reed", (176, 199, 196), (226, 238, 236)),
    (87, "Salt", "grains", (226, 236, 240), (168, 199, 214)),
    (88, "Silverleaf", "leaf", (196, 212, 205), (232, 240, 235)),
    (89, "Crystal", "cluster", (126, 196, 214), (206, 246, 252)),
    (90, "Stormglass", "shard", (66, 96, 138), (150, 194, 236)),
    (91, "Seed", "seed", (206, 158, 68), (240, 208, 122)),
    (92, "Resin", "resin", (198, 124, 44), (244, 190, 106)),
    (93, "Peat", "brick", (86, 66, 50), (128, 102, 74)),
    (94, "Orchid", "flower", (226, 224, 216), (198, 214, 220)),
    (95, "Sap", "resin", (150, 104, 54), (216, 168, 92)),
    (96, "Lichen", "moss", (84, 122, 78), (150, 182, 104)),
    (97, "Venom Bulb", "bulb", (96, 148, 82), (176, 206, 96)),
    (98, "Lotus", "flower", (226, 158, 184), (246, 214, 226)),
    (99, "Clay", "brick", (108, 116, 122), (156, 166, 170)),
    (100, "Geode", "geode", (92, 84, 116), (146, 130, 216)),
    (101, "Unknown Item", "unknown", (128, 124, 118), (196, 190, 178)),
    # The regional harvest resources added after the first sixteen. Their item
    # ids run past the range the atlas declared, so every one of them drew the
    # unknown-item glyph in the bag while its node stood in the world.
    (102, "Wheat", "reed", (198, 162, 86), (238, 214, 140)),
    (103, "Riverflax", "reed", (118, 152, 138), (188, 214, 196)),
    (104, "Cotton", "bulb", (206, 202, 190), (244, 242, 236)),
    (105, "Hearthroot", "bulb", (156, 96, 62), (212, 156, 104)),
    (106, "Bramble", "leaf", (72, 88, 66), (128, 148, 104)),
    (107, "Toadstool", "bulb", (204, 146, 62), (244, 206, 128)),
    (108, "Kelp", "reed", (62, 92, 74), (118, 152, 106)),
    (109, "Shell", "pearl", (226, 214, 196), (188, 176, 158)),
    (110, "Verdigris", "flower", (96, 172, 152), (188, 228, 210)),
    (111, "Bog Iron", "brick", (104, 74, 56), (158, 118, 82)),
    (112, "Coal", "brick", (56, 50, 48), (168, 92, 48)),
    (113, "Quartz", "cluster", (206, 206, 210), (244, 246, 248)),
    (114, "Flint", "shard", (176, 106, 52), (238, 178, 96)),
    (115, "Thistle", "flower", (92, 92, 158), (166, 168, 226)),
    (116, "Watercress", "moss", (74, 138, 102), (152, 200, 138)),
]

LIGHT = np.array([-.42, -.60, .68])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


# ---------------------------------------------------------------------------
# Atlas io
# ---------------------------------------------------------------------------

def read_atlas(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8).copy()


def write_atlas(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image.astype(np.uint8), "RGBA").save(path, optimize=True)


def cell_slice(image: np.ndarray, local_id: int) -> np.ndarray:
    row, column = divmod(local_id, COLUMNS)
    return image[row * CELL:(row + 1) * CELL, column * CELL:(column + 1) * CELL]


def paste_offsets(source: Path) -> list[int]:
    """How far below the sampling grid the art in ``source`` currently sits.

    The correction is a one-time migration, so the offsets that are still baked
    into the art are recorded beside it rather than inferred.  Re-deriving them
    from the pixels is not reliable - at the wrong offset the cells are still
    fully opaque, they simply contain a slice of the neighbouring icon - and
    guessing wrong would skew corrected art straight back out.
    """
    manifest = layout_path(source)
    if manifest.is_file():
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        offsets = [int(value) for value in recorded.get("rowOffsets", [])]
        if len(offsets) == ATLAS_COUNT:
            return offsets
    return list(ATLAS_ROW_OFFSETS)


def write_paste_offsets(source: Path) -> None:
    layout_path(source).write_text(json.dumps({
        "cellSize": [CELL, CELL],
        "columns": COLUMNS,
        "imagesPerAtlas": PER_ATLAS,
        "imageCount": IMAGE_COUNT,
        "rowOffsets": [0] * ATLAS_COUNT,
        "note": ("Rows each atlas sits below the grid ItemAtlas samples. "
                 "Zero once paint_material_icons.py has corrected the art; the "
                 "shipped values were " + repr(list(ATLAS_ROW_OFFSETS)) + "."),
    }, indent=2) + "\n", encoding="utf-8")


def source_cell(atlases: list[np.ndarray], image_id: int,
                offsets: list[int] | None = None) -> np.ndarray:
    """Lift one painted icon from where it actually sits in the shipped atlas."""
    atlas, local = divmod(image_id, PER_ATLAS)
    row, column = divmod(local, COLUMNS)
    offset = (ATLAS_ROW_OFFSETS[atlas] if offsets is None else offsets[atlas])
    image = atlases[atlas]
    cell = np.zeros((CELL, CELL, 4), dtype=np.float64)
    top = row * CELL + offset
    available = max(0, min(CELL, image.shape[0] - top))
    if available > 0:
        cell[:available] = image[top:top + available,
                                 column * CELL:(column + 1) * CELL]
    return cell


def authored_plate(atlases: list[np.ndarray],
                   offsets: list[int] | None = None) -> np.ndarray:
    """Recover the shared frame and background from the painted icons.

    Frame and background pixels are identical in every painted cell while the
    object pixels scatter, so the per-pixel mode recovers the plate exactly.  A
    median or a percentile instead leaves a smear where most objects sit.
    """
    samples = [source_cell(atlases, image_id, offsets) for image_id in PAINTED_IDS
               if image_id not in TRUNCATED_IDS]
    stack = np.stack([cell for cell in samples if (cell[:, :, 3] > 8).all()])
    # Objects are brighter than the slate they sit on, so a low percentile is
    # the background.  The frame is brighter still and objects rarely reach the
    # corners, so the ring is taken from a higher percentile and blended in.
    interior = np.percentile(stack, 20.0, axis=0)
    ring = np.percentile(stack, 42.0, axis=0)
    axis = np.arange(CELL)
    border = np.minimum(np.minimum(axis, CELL - 1 - axis)[:, None],
                        np.minimum(axis, CELL - 1 - axis)[None, :])
    weight = np.clip((9.0 - border) / 5.0, 0., 1.)[..., None]
    plate = interior * (1. - weight) + ring * weight
    # Relax the interior so the faint ghost of the sampled objects does not
    # print through behind the newly painted ones.
    smooth = plate.copy()
    for _ in range(6):
        smooth[:, :, :3] = (smooth[:, :, :3]
                            + np.roll(smooth[:, :, :3], 1, 0)
                            + np.roll(smooth[:, :, :3], -1, 0)
                            + np.roll(smooth[:, :, :3], 1, 1)
                            + np.roll(smooth[:, :, :3], -1, 1)) / 5.
    interior_weight = np.clip((border - 10.) / 4., 0., 1.)[..., None]
    plate[:, :, :3] = (plate[:, :, :3] * (1. - interior_weight)
                       + smooth[:, :, :3] * interior_weight)
    plate[:, :, 3] = np.percentile(stack[:, :, :, 3], 88.0, axis=0)
    return plate


def repair_cell(cell: np.ndarray, plate: np.ndarray) -> np.ndarray:
    """Seat a truncated icon back on a full plate.

    The lost rows cannot be recovered, but restoring the plate and fading the
    surviving art into it reads as an icon rather than as a cut-off one.
    """
    repaired = plate.copy()
    empty = np.where(cell[:, :, 3].max(axis=1) <= 8)[0]
    # Everything from the first blank row down was overwritten, including the
    # placeholder art that replaced it, so none of it may be carried over.
    cut = int(empty[0]) if len(empty) else CELL
    if cut <= 0:
        return repaired
    fade = np.ones(CELL)
    for row in range(max(cut - 6, 0), CELL):
        fade[row] = max(0., 1. - (row - max(cut - 6, 0)) / 6.)
    alpha = (cell[:, :, 3] / 255.) * fade[:, None]
    alpha[cut:] = 0.
    repaired[:, :, :3] = (repaired[:, :, :3] * (1. - alpha[..., None])
                          + cell[:, :, :3] * alpha[..., None])
    return repaired


# ---------------------------------------------------------------------------
# Shading
# ---------------------------------------------------------------------------

def _grid(size: int = CELL):
    axis = (np.arange(size) + .5) / size * 2. - 1.
    return np.meshgrid(axis, axis)


def _shade(height: np.ndarray, mask: np.ndarray, base, accent,
           *, gloss: float = .38, shininess: float = 26.,
           rim: float = .22, emissive: float = 0.) -> np.ndarray:
    """Light a height field as a rounded solid, in the painted icons' key light."""
    dy, dx = np.gradient(height)
    normal = np.dstack((-dx * 6., -dy * 6., np.ones_like(height)))
    normal /= np.maximum(np.linalg.norm(normal, axis=2, keepdims=True), 1e-9)
    lambert = np.clip(normal @ LIGHT, 0., 1.)
    view = np.array([0., 0., 1.])
    half = LIGHT + view
    half /= np.linalg.norm(half)
    specular = np.clip(normal @ half, 0., 1.) ** shininess
    facing = np.clip(1. - normal[:, :, 2], 0., 1.) ** 2.2
    base = np.asarray(base, dtype=np.float64)
    accent = np.asarray(accent, dtype=np.float64)
    colour = (base[None, None, :] * (.30 + .78 * lambert[..., None])
              + accent[None, None, :] * (gloss * specular[..., None]
                                         + rim * facing[..., None])
              + accent[None, None, :] * emissive)
    colour = np.clip(colour, 0., 255.)
    return np.dstack((colour, np.where(mask, 255., 0.)))


def _blob(cx: float, cy: float, rx: float, ry: float, power: float = 2.0):
    x, y = _grid()
    radial = (np.abs((x - cx) / rx) ** power + np.abs((y - cy) / ry) ** power)
    mask = radial <= 1.
    height = np.where(mask, np.sqrt(np.clip(1. - radial, 0., 1.)) * min(rx, ry), 0.)
    return height, mask


def _polygon(points: np.ndarray, feather: float = .04):
    x, y = _grid()
    inside = np.ones_like(x, dtype=bool)
    distance = np.full_like(x, 1e9)
    count = len(points)
    for index in range(count):
        a = points[index]
        b = points[(index + 1) % count]
        edge = b - a
        normal = np.array([edge[1], -edge[0]])
        normal /= max(np.linalg.norm(normal), 1e-9)
        signed = (x - a[0]) * normal[0] + (y - a[1]) * normal[1]
        inside &= signed <= 0
        distance = np.minimum(distance, -signed)
    height = np.where(inside, np.clip(distance, 0., feather) / feather, 0.)
    return height * .10, inside


def _rotate(points: np.ndarray, angle: float) -> np.ndarray:
    cos, sin = math.cos(angle), math.sin(angle)
    return points @ np.array([[cos, -sin], [sin, cos]])


def _over(target: np.ndarray, layer: np.ndarray) -> np.ndarray:
    alpha = layer[:, :, 3:4] / 255.
    target[:, :, :3] = target[:, :, :3] * (1. - alpha) + layer[:, :, :3] * alpha
    target[:, :, 3] = np.maximum(target[:, :, 3], layer[:, :, 3])
    return target


# ---------------------------------------------------------------------------
# Material shapes
# ---------------------------------------------------------------------------

def paint_material(shape: str, base, accent) -> np.ndarray:
    layer = np.zeros((CELL, CELL, 4))
    if shape == "pearl":
        height, mask = _blob(.0, .04, .46, .46)
        layer = _over(layer, _shade(height, mask, base, accent,
                                    gloss=.95, shininess=48., rim=.34))
        glint, glint_mask = _blob(-.17, -.16, .12, .10)
        layer = _over(layer, _shade(glint, glint_mask, (255, 255, 255),
                                    (255, 255, 255), gloss=.4, rim=.0))
    elif shape == "reed":
        for offset, tilt, length in ((-.34, -.16, .78), (-.02, .04, .92), (.30, .18, .70)):
            stalk = np.array([[-.055, -length], [.055, -length],
                              [.075, length], [-.075, length]])
            stalk = _rotate(stalk, tilt) + np.array([offset, .08])
            height, mask = _polygon(stalk, feather=.06)
            layer = _over(layer, _shade(height, mask, base, accent,
                                        gloss=.62, shininess=34.))
            head, head_mask = _blob(offset + math.sin(tilt) * length * .9,
                                    .08 - math.cos(tilt) * length * .9, .09, .17)
            layer = _over(layer, _shade(head, head_mask, accent, (255, 255, 255),
                                        gloss=.5))
    elif shape == "grains":
        for cx, cy, radius, angle in ((-.24, .22, .20, .3), (.20, .26, .17, -.5),
                                      (-.02, .08, .26, .1), (.30, -.06, .15, .9),
                                      (-.30, -.06, .14, -.8), (.04, -.28, .18, .4)):
            crystal = _rotate(np.array([[0., -1.], [.62, -.18], [.42, .92],
                                        [-.42, .92], [-.62, -.18]]) * radius, angle)
            crystal = crystal + np.array([cx, cy])
            height, mask = _polygon(crystal, feather=.05)
            layer = _over(layer, _shade(height, mask, base, accent,
                                        gloss=.85, shininess=42., rim=.30))
    elif shape == "leaf":
        height, mask = _blob(.0, .0, .27, .58, power=1.6)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.55))
        vein = np.array([[-.03, -.56], [.03, -.56], [.05, .50], [-.05, .50]])
        vein_height, vein_mask = _polygon(vein, feather=.03)
        layer = _over(layer, _shade(vein_height, vein_mask & mask, accent,
                                    (255, 255, 255), gloss=.4))
        stem = np.array([[-.035, .44], [.035, .44], [.05, .84], [-.05, .84]])
        stem_height, stem_mask = _polygon(stem, feather=.03)
        layer = _over(layer, _shade(stem_height, stem_mask,
                                    tuple(int(c * .62) for c in base), accent))
    elif shape == "cluster":
        for cx, cy, scale, angle in ((-.26, .16, .52, -.24), (.24, .22, .44, .28),
                                      (.0, -.06, .74, .04), (-.06, .30, .34, .5)):
            spire = _rotate(np.array([[0., -1.], [.34, -.30], [.26, .96],
                                      [-.26, .96], [-.34, -.30]]) * scale, angle)
            spire = spire + np.array([cx, cy])
            height, mask = _polygon(spire, feather=.05)
            layer = _over(layer, _shade(height, mask, base, accent, gloss=.90,
                                        shininess=40., rim=.34, emissive=.16))
    elif shape == "shard":
        points = np.array([[-.10, -.86], [.36, -.24], [.28, .48], [-.02, .84],
                           [-.34, .30], [-.40, -.32]])
        height, mask = _polygon(points, feather=.07)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.92,
                                    shininess=52., rim=.40))
        facet = np.array([[-.10, -.80], [.28, -.20], [-.02, .40]])
        facet_height, facet_mask = _polygon(facet, feather=.05)
        layer = _over(layer, _shade(facet_height, facet_mask & mask, accent,
                                    (255, 255, 255), gloss=.5, rim=.1))
    elif shape == "seed":
        height, mask = _blob(.0, .04, .34, .52, power=1.8)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.66,
                                    shininess=30.))
        for side in (-1., 1.):
            husk = np.array([[0., -.52], [side * .34, -.10], [side * .26, .46],
                             [0., .54]])
            husk_height, husk_mask = _polygon(husk, feather=.05)
            layer = _over(layer, _shade(husk_height, husk_mask & mask, accent,
                                        (255, 255, 255), gloss=.42))
    elif shape == "resin":
        height, mask = _blob(.0, .10, .44, .48, power=2.4)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.88,
                                    shininess=36., rim=.34, emissive=.10))
        drip, drip_mask = _blob(.16, -.42, .13, .28, power=2.6)
        layer = _over(layer, _shade(drip, drip_mask, base, accent, gloss=.88,
                                    shininess=36., rim=.30))
        bubble, bubble_mask = _blob(-.14, .0, .10, .10)
        layer = _over(layer, _shade(bubble, bubble_mask & mask, accent,
                                    (255, 255, 255), gloss=.6))
    elif shape == "brick":
        top = np.array([[-.52, -.20], [.0, -.46], [.52, -.20], [.0, .04]])
        side_l = np.array([[-.52, -.20], [.0, .04], [.0, .58], [-.52, .32]])
        side_r = np.array([[.52, -.20], [.52, .32], [.0, .58], [.0, .04]])
        for points, tint, lift in ((side_l, .58, .04), (side_r, .78, .05),
                                    (top, 1.0, .10)):
            height, mask = _polygon(points, feather=.08)
            layer = _over(layer, _shade(height + lift * mask, mask,
                                        tuple(c * tint for c in base), accent,
                                        gloss=.24, shininess=18.))
    elif shape == "flower":
        for index in range(6):
            angle = 2 * math.pi * index / 6 + .3
            petal, petal_mask = _blob(math.cos(angle) * .30, math.sin(angle) * .30,
                                      .28, .21, power=1.7)
            layer = _over(layer, _shade(petal, petal_mask, base, accent,
                                        gloss=.44, rim=.28))
        heart, heart_mask = _blob(.0, .0, .19, .19)
        layer = _over(layer, _shade(heart, heart_mask, accent, (255, 255, 255),
                                    gloss=.62, shininess=34.))
    elif shape == "moss":
        for cx, cy, radius in ((-.26, .18, .30), (.22, .24, .26), (.0, -.02, .36),
                                (.30, -.20, .22), (-.28, -.16, .24), (.02, -.36, .22)):
            clump, clump_mask = _blob(cx, cy, radius, radius * .82)
            layer = _over(layer, _shade(clump, clump_mask, base, accent,
                                        gloss=.30, shininess=16., rim=.26))
        x, y = _grid()
        scales = ((np.sin(x * 26.) * np.sin(y * 22.)) > .45)
        layer = _over(layer, _shade(np.zeros((CELL, CELL)),
                                    scales & (layer[:, :, 3] > 0), accent, accent,
                                    gloss=.0, rim=.0))
    elif shape == "bulb":
        height, mask = _blob(.0, .12, .42, .46, power=2.2)
        layer = _over(layer, _shade(height, mask, base, accent, gloss=.52,
                                    shininess=26., rim=.30))
        for side in (-1., 0., 1.):
            rib = np.array([[side * .30 - .035, -.34], [side * .30 + .035, -.34],
                            [side * .22 + .045, .50], [side * .22 - .045, .50]])
            rib_height, rib_mask = _polygon(rib, feather=.04)
            layer = _over(layer, _shade(rib_height, rib_mask & mask, accent,
                                        (255, 255, 255), gloss=.34))
        neck = np.array([[-.11, -.62], [.11, -.62], [.15, -.28], [-.15, -.28]])
        neck_height, neck_mask = _polygon(neck, feather=.04)
        layer = _over(layer, _shade(neck_height, neck_mask,
                                    tuple(int(c * .70) for c in base), accent))
    elif shape == "geode":
        outer, outer_mask = _blob(.0, .0, .50, .46, power=2.2)
        layer = _over(layer, _shade(outer, outer_mask,
                                    tuple(int(c * .70) for c in base), base,
                                    gloss=.22, shininess=14.))
        hollow, hollow_mask = _blob(.04, .0, .30, .28, power=2.0)
        layer = _over(layer, _shade(-hollow, hollow_mask,
                                    tuple(int(c * .45) for c in base), accent,
                                    gloss=.20, rim=.10))
        for index in range(9):
            angle = 2 * math.pi * index / 9 + .2
            spike = _rotate(np.array([[0., -1.], [.34, .10], [-.34, .10]]) * .17,
                            angle + math.pi)
            spike = spike + np.array([.04 + math.cos(angle) * .17,
                                      math.sin(angle) * .16])
            height, mask = _polygon(spike, feather=.04)
            layer = _over(layer, _shade(height, mask & hollow_mask, accent,
                                        (255, 255, 255), gloss=.80, shininess=44.,
                                        emissive=.20))
    elif shape == "unknown":
        ring, ring_mask = _blob(.0, .0, .50, .50)
        inner, inner_mask = _blob(.0, .0, .38, .38)
        band = ring_mask & ~inner_mask
        layer = _over(layer, _shade(ring, band, base, accent, gloss=.30))
        stem = np.array([[-.09, -.30], [.09, -.30], [.09, .10], [-.09, .10]])
        height, mask = _polygon(stem, feather=.04)
        layer = _over(layer, _shade(height, mask, accent, (255, 255, 255), gloss=.4))
        dot, dot_mask = _blob(.0, .28, .10, .10)
        layer = _over(layer, _shade(dot, dot_mask, accent, (255, 255, 255), gloss=.4))
    else:
        raise ValueError(f"unknown material shape: {shape}")
    return layer


def compose(plate: np.ndarray, shape: str, base, accent) -> np.ndarray:
    """Drop a painted material onto the authored plate, inside its frame."""
    icon = plate.copy()
    layer = paint_material(shape, base, accent)
    inset = np.zeros_like(layer)
    scale = 0.78
    size = max(int(CELL * scale), 8)
    resized = np.asarray(Image.fromarray(
        np.clip(layer, 0, 255).astype(np.uint8), "RGBA").resize(
            (size, size), Image.Resampling.LANCZOS), dtype=np.float64)
    origin = (CELL - size) // 2
    inset[origin:origin + size, origin:origin + size] = resized
    # A soft contact shadow seats the object on the plate the way the painted
    # icons do, instead of leaving it floating.
    shadow = np.clip(inset[:, :, 3] / 255., 0., 1.)
    for _ in range(3):
        shadow = (shadow + np.roll(shadow, 1, 0) + np.roll(shadow, -1, 0)
                  + np.roll(shadow, 1, 1) + np.roll(shadow, -1, 1)) / 5.
    shadow = np.roll(np.roll(shadow, 3, 0), 2, 1) * .55
    frame = plate[:, :, 3] > 8
    icon[:, :, :3] *= (1. - shadow[..., None] * frame[..., None])
    return _over(icon, inset)


# ---------------------------------------------------------------------------
# Atlas rebuild
# ---------------------------------------------------------------------------

def rebuild_atlases(source: Path) -> list[np.ndarray]:
    """Rebuild every atlas on the grid ``ItemAtlas`` samples."""
    atlases = [read_atlas(source / f"items{index + 1}.png")
               for index in range(ATLAS_COUNT)]
    offsets = paste_offsets(source)
    print(f"correcting paste offsets: {offsets}")
    plate = authored_plate(atlases, offsets)
    icons: dict[int, np.ndarray] = {}
    for image_id in PAINTED_IDS:
        cell = source_cell(atlases, image_id, offsets)
        # Repair on evidence rather than on a list: any cell that is not fully
        # opaque lost rows to the paste offset or to the placeholder block.
        icons[image_id] = cell if (cell[:, :, 3] > 8).all() else repair_cell(cell, plate)
    for image_id, _name, shape, base, accent in MATERIALS:
        icons[image_id] = compose(plate, shape, base, accent)
    rebuilt = []
    for atlas in range(ATLAS_COUNT):
        canvas = np.zeros((CELL * COLUMNS + 6, CELL * COLUMNS + 6, 4))
        for local in range(PER_ATLAS):
            image_id = atlas * PER_ATLAS + local
            if image_id not in icons:
                continue
            row, column = divmod(local, COLUMNS)
            canvas[row * CELL:(row + 1) * CELL,
                   column * CELL:(column + 1) * CELL] = icons[image_id]
        rebuilt.append(np.clip(canvas, 0, 255).astype(np.uint8))
    return rebuilt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    assets_root = Path(__file__).resolve().parents[1]
    repo_root = assets_root.parent
    parser.add_argument("--source", type=Path,
                        default=repo_root / "godot-client/assets/ui/items",
                        help="the atlas PNGs the client samples, rewritten "
                             "in place")
    arguments = parser.parse_args()
    rebuilt = rebuild_atlases(arguments.source)
    for index, image in enumerate(rebuilt):
        write_atlas(arguments.source / f"items{index + 1}.png", image)
        print(f"items{index + 1}: rewrote {(image[:, :, 3] > 8).sum()} opaque pixels")
    write_paste_offsets(arguments.source)
    print(f"{IMAGE_COUNT} icons aligned to the {CELL}px grid")


if __name__ == "__main__":
    main()
