#!/usr/bin/env python3
"""Extend the HUD action icon atlas with eleven new glyphs (cells 13-23).

The script derives a clean blank tile from the thirteen existing icons,
samples the established palette from their glyph pixels, draws the new
glyphs at 4x resolution, downscales them with premultiplied LANCZOS, and
re-emits the atlas with cells 0-12 byte-identical to the source. It then
regenerates the inactive companion atlas and writes a 4x contact sheet
for human review.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "assets" / "ui" / "eloria_gamebuttons.png"
INACTIVE_TOOL = ROOT / "tools" / "generate_inactive_hud_atlas.py"
PREVIEW = ROOT / "test-artifacts" / "hud-icon-preview.png"

CELL = 32
SCALE = 4
BIG = CELL * SCALE  # 128
EXISTING = 13
NEW_FIRST = 13
NEW_COUNT = 12
LUMA = np.array([0.2126, 0.7152, 0.0722])


# --------------------------------------------------------------------------
# blank tile derivation
# --------------------------------------------------------------------------

def load_cells(atlas: np.ndarray, count: int) -> np.ndarray:
    cells = [atlas[(i // 8) * CELL:(i // 8 + 1) * CELL,
                   (i % 8) * CELL:(i % 8 + 1) * CELL] for i in range(count)]
    return np.stack(cells)


def center_std(tile: np.ndarray) -> float:
    return float(tile[9:23, 9:23, :3].std(axis=(0, 1)).mean())


def composite_background_tile(cells: np.ndarray) -> np.ndarray:
    """Composite a glyph-free tile from the flattest per-pixel samples.

    For every pixel we keep the darkest few samples across the cells (the
    bright glyph strokes never survive that cut), then repair the remaining
    contaminated interior pixels with a smooth polynomial fit of the clean
    background plus a whisper of matched noise.
    """
    stack = cells.astype(np.float64)
    lum = stack[:, :, :, :3] @ LUMA
    order = np.argsort(lum, axis=0)[:4]
    picked = np.stack(
        [np.take_along_axis(stack[:, :, :, ch], order, axis=0) for ch in range(4)],
        axis=-1)
    tile = picked.mean(axis=0)
    spread = picked[:, :, :, :3].std(axis=0).mean(axis=-1)

    clean = spread < 6.0
    yy, xx = np.mgrid[0:CELL, 0:CELL]
    interior = (xx >= 4) & (xx <= 27) & (yy >= 4) & (yy <= 27)
    contaminated = (~clean) & interior

    columns = [np.ones(CELL * CELL), xx.ravel(), yy.ravel(),
               (xx * xx).ravel(), (xx * yy).ravel(), (yy * yy).ravel(),
               (xx ** 3).ravel(), (yy ** 3).ravel(),
               (xx * xx * yy).ravel(), (xx * yy * yy).ravel()]
    design = np.column_stack(columns)
    keep = (clean & interior).ravel()
    rng = np.random.default_rng(1307)
    noise = rng.normal(0.0, 2.0, size=(CELL, CELL))
    for ch in range(3):
        values = tile[:, :, ch].ravel()
        coefficients, *_ = np.linalg.lstsq(design[keep], values[keep], rcond=None)
        fitted = (design @ coefficients).reshape(CELL, CELL)
        tile[:, :, ch][contaminated] = (fitted + noise)[contaminated]
    tile[:, :, :3] = np.clip(tile[:, :, :3], 0, 255)
    tile[:, :, 3] = 255
    return tile.astype(np.uint8)


def derive_blank_tile(cells: np.ndarray) -> np.ndarray:
    median = np.median(cells.astype(np.float64), axis=0)
    median[:, :, 3] = 255
    tile = np.clip(median, 0, 255).astype(np.uint8)
    if center_std(tile) <= 12.0:
        return tile
    tile = composite_background_tile(cells)
    if center_std(tile) > 15.0:
        raise RuntimeError(
            f"blank tile still shows glyph artifacts (center std {center_std(tile):.1f})")
    return tile


# --------------------------------------------------------------------------
# palette sampling
# --------------------------------------------------------------------------

def sample_palette(cells: np.ndarray, blank: np.ndarray) -> dict[str, tuple[int, int, int]]:
    stack = cells.astype(np.int64)
    diff = np.abs(stack[:, :, :, :3] - blank[None, :, :, :3].astype(np.int64)).sum(axis=3)
    glyph = stack[:, :, :, :3][diff > 100]

    def median_of(mask: np.ndarray, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
        chosen = glyph[mask]
        if len(chosen) < 8:
            return fallback
        return tuple(int(v) for v in np.median(chosen, axis=0))

    gold_hi = median_of((glyph[:, 0] > 170) & (glyph[:, 0] > glyph[:, 2] + 40),
                        (208, 180, 125))
    gold_mid = median_of((glyph[:, 0] > 140) & (glyph[:, 0] <= 190)
                         & (glyph[:, 0] > glyph[:, 2] + 30), (169, 143, 92))

    lum = glyph @ LUMA
    sat = glyph.max(axis=1) - glyph.min(axis=1)
    pale_hi = median_of((lum > 170) & (sat < 40), (190, 192, 168))
    pale_mid = median_of((lum > 120) & (lum <= 170) & (sat < 40), (139, 149, 130))
    pale_dark = median_of((lum > 70) & (lum <= 120) & (sat < 45), (89, 89, 79))

    everything = stack[:, :, :, :3].reshape(-1, 3)
    teal_score = np.minimum(everything[:, 1], everything[:, 2]) - everything[:, 0]
    teal_pool = everything[np.argsort(teal_score)[-30:]]
    teal = tuple(int(v) for v in np.median(teal_pool, axis=0))

    interior = blank[10:22, 10:22, :3].astype(np.int64)
    navy = tuple(int(v) for v in np.percentile(interior.reshape(-1, 3), 15, axis=0))

    return {"gold_hi": gold_hi, "gold_mid": gold_mid, "pale_hi": pale_hi,
            "pale_mid": pale_mid, "pale_dark": pale_dark, "teal": teal,
            "navy": navy}


# --------------------------------------------------------------------------
# glyph drawing (all coordinates in 128px space, safe area roughly 20..108)
# --------------------------------------------------------------------------

def star(d: ImageDraw.ImageDraw, cx: float, cy: float, size: float, color) -> None:
    pinch = size / 3.2
    d.polygon([(cx, cy - size), (cx + pinch, cy - pinch), (cx + size, cy),
               (cx + pinch, cy + pinch), (cx, cy + size), (cx - pinch, cy + pinch),
               (cx - size, cy), (cx - pinch, cy - pinch)], fill=color)


def bezier(p0, p1, p2, steps: int = 24) -> list[tuple[float, float]]:
    points = []
    for i in range(steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        points.append((x, y))
    return points


def glyph_use(d, e, p) -> None:
    """Pointing hand, index finger extended upward."""
    d.rounded_rectangle((36, 56, 94, 100), radius=15, fill=p["pale_mid"])  # fist
    for x0 in (64, 78):  # curled fingers along the top of the fist
        d.rounded_rectangle((x0, 52, x0 + 12, 80), radius=6, fill=p["pale_hi"],
                            outline=p["pale_dark"], width=2)
    d.rounded_rectangle((44, 20, 62, 72), radius=9, fill=p["pale_hi"],
                        outline=p["pale_dark"], width=2)  # index finger
    d.line((38, 72, 52, 90), fill=p["pale_hi"], width=15)  # thumb across fist
    d.rounded_rectangle((40, 92, 92, 106), radius=5, fill=p["gold_mid"])  # cuff
    d.line((44, 99, 88, 99), fill=p["gold_hi"], width=4)


def glyph_spells(d, e, p) -> None:
    """Wand with three sparkle stars."""
    d.line((38, 98, 84, 46), fill=p["pale_mid"], width=10)
    d.line((36, 100, 52, 82), fill=p["pale_dark"], width=10)  # grip
    d.line((78, 52, 88, 40), fill=p["gold_hi"], width=10)  # glowing tip
    star(d, 94, 30, 13, p["gold_hi"])
    star(d, 70, 26, 8, p["teal"])
    star(d, 102, 56, 8, p["gold_mid"])


def glyph_emotes(d, e, p) -> None:
    """Round smiling face."""
    d.ellipse((32, 32, 96, 96), fill=p["pale_hi"], outline=p["gold_mid"], width=4)
    d.chord((32, 32, 96, 96), 25, 155, fill=p["pale_mid"])  # lower shading
    d.ellipse((47, 50, 57, 64), fill=p["navy"])
    d.ellipse((71, 50, 81, 64), fill=p["navy"])
    d.arc((44, 48, 84, 84), 25, 155, fill=p["navy"], width=6)


def glyph_quest(d, e, p) -> None:
    """Scroll with two written lines."""
    d.rectangle((40, 34, 88, 94), fill=p["pale_hi"])
    d.rectangle((80, 34, 88, 94), fill=p["pale_mid"])  # curl shading
    d.ellipse((34, 22, 94, 42), fill=p["pale_mid"], outline=p["pale_dark"], width=3)
    d.ellipse((34, 86, 94, 106), fill=p["pale_mid"], outline=p["pale_dark"], width=3)
    d.ellipse((30, 24, 44, 40), fill=p["gold_mid"])  # rolled end caps
    d.ellipse((84, 88, 98, 104), fill=p["gold_mid"])
    d.line((48, 56, 80, 56), fill=p["gold_mid"], width=5)
    d.line((48, 70, 74, 70), fill=p["gold_mid"], width=5)


def glyph_info(d, e, p) -> None:
    """Notepad page with folded corner and pencil lines."""
    d.polygon([(38, 26), (74, 26), (90, 42), (90, 102), (38, 102)],
              fill=p["pale_hi"])
    d.polygon([(74, 26), (74, 42), (90, 42)], fill=p["pale_mid"])  # fold
    d.line((74, 26, 74, 42), fill=p["pale_dark"], width=3)
    d.line((74, 42, 90, 42), fill=p["pale_dark"], width=3)
    d.line((46, 56, 82, 56), fill=p["gold_mid"], width=5)
    d.line((46, 70, 82, 70), fill=p["teal"], width=5)
    d.line((46, 84, 68, 84), fill=p["gold_mid"], width=5)


def glyph_buddy(d, e, p) -> None:
    """Two person silhouettes side by side."""
    back = tuple((np.array(p["pale_mid"]) * 2 + np.array(p["teal"])) // 3)
    d.ellipse((62, 30, 88, 56), fill=back)
    d.polygon([(52, 92), (56, 66), (66, 58), (84, 58), (94, 66), (98, 92)],
              fill=back)
    d.ellipse((36, 40, 64, 68), fill=p["pale_hi"], outline=p["navy"], width=3)
    d.polygon([(24, 104), (28, 78), (39, 70), (61, 70), (72, 78), (76, 104)],
              fill=p["pale_hi"], outline=p["navy"], width=3)
    d.line((30, 100, 70, 100), fill=p["gold_mid"], width=5)  # front collar trim


def glyph_console(d, e, p) -> None:
    """Monitor with a >_ prompt."""
    d.rounded_rectangle((26, 28, 102, 86), radius=8, fill=p["pale_mid"])
    d.rectangle((34, 36, 94, 78), fill=p["navy"])
    d.rectangle((34, 36, 94, 78), outline=p["gold_mid"], width=3)
    d.line((44, 48, 56, 57), fill=p["teal"], width=6)
    d.line((56, 57, 44, 66), fill=p["teal"], width=6)
    d.line((63, 66, 78, 66), fill=p["teal"], width=6)
    d.rectangle((56, 86, 72, 96), fill=p["pale_dark"])
    d.rounded_rectangle((42, 94, 86, 104), radius=4, fill=p["pale_mid"])


def glyph_help(d, e, p) -> None:
    """Bold question mark."""
    d.arc((40, 25, 92, 73), 150, 65, fill=p["gold_mid"], width=13)  # depth
    d.line((77, 67, 67, 79), fill=p["gold_mid"], width=13)
    d.line((66, 75, 66, 87), fill=p["gold_mid"], width=13)
    d.ellipse((58, 94, 75, 110), fill=p["gold_mid"])
    d.arc((38, 22, 90, 70), 150, 65, fill=p["gold_hi"], width=11)
    d.line((75, 64, 65, 76), fill=p["gold_hi"], width=11)
    d.line((64, 72, 64, 84), fill=p["gold_hi"], width=11)
    d.ellipse((56, 92, 72, 107), fill=p["gold_hi"])


def glyph_options(d, e, p) -> None:
    """Eight-tooth gear with a hub hole."""
    cx = cy = 64.0
    outer, root, hole = 42.0, 31.0, 13.0
    points: list[tuple[float, float]] = []
    for tooth in range(8):
        base = tooth * 45.0
        for angle, radius in ((base - 16, root), (base - 9, outer),
                              (base + 9, outer), (base + 16, root)):
            rad = np.deg2rad(angle)
            points.append((cx + radius * np.cos(rad), cy + radius * np.sin(rad)))
    d.polygon(points, fill=p["pale_mid"], outline=p["pale_dark"], width=3)
    d.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=p["pale_hi"], width=4)
    d.ellipse((cx - hole - 4, cy - hole - 4, cx + hole + 4, cy + hole + 4),
              outline=p["gold_mid"], width=5)
    e.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=255)


def glyph_ranging(d, e, p) -> None:
    """Drawn bow with a nocked arrow."""
    d.line(bezier((46, 24), (18, 64), (46, 104)), fill=p["gold_mid"], width=8,
           joint="curve")
    d.line((44, 22, 52, 30), fill=p["gold_hi"], width=7)  # recurve tips
    d.line((44, 106, 52, 98), fill=p["gold_hi"], width=7)
    d.line((46, 26, 86, 64), fill=p["pale_hi"], width=3)  # drawn string
    d.line((86, 64, 46, 102), fill=p["pale_hi"], width=3)
    d.line((26, 64, 92, 64), fill=p["pale_hi"], width=6)  # shaft
    d.polygon([(16, 64), (36, 53), (36, 75)], fill=p["pale_hi"])  # head
    d.line((88, 62, 100, 52), fill=p["gold_hi"], width=6)  # fletching
    d.line((88, 66, 100, 76), fill=p["gold_hi"], width=6)


def glyph_minimap(d, e, p) -> None:
    """Magnifier over a small map square."""
    d.rounded_rectangle((24, 24, 74, 74), radius=6, fill=p["pale_hi"])
    d.line((41, 26, 41, 72), fill=p["pale_mid"], width=4)  # fold creases
    d.line((58, 26, 58, 72), fill=p["pale_mid"], width=4)
    d.line([(30, 62), (41, 46), (54, 56), (66, 36)], fill=p["teal"], width=5,
           joint="curve")
    d.ellipse((54, 50, 96, 92), outline=p["gold_hi"], width=8)
    d.line((92, 88, 104, 100), fill=p["gold_mid"], width=10)


def glyph_stand(d, e, p) -> None:
    """A figure under a rising chevron. Eternal Lands swaps its sit icon for a
    stand icon while you are seated, so this is the pair to the seated one in
    cell 7: it says what the click does, not what you are doing."""
    d.polygon([(64, 14), (80, 30), (71, 30), (71, 36), (57, 36), (57, 30),
               (48, 30)], fill=p["gold_hi"])
    d.ellipse((55, 40, 73, 58), fill=p["pale_hi"], outline=p["pale_dark"], width=3)
    d.line((59, 88, 57, 106), fill=p["pale_mid"], width=10)
    d.line((69, 88, 71, 106), fill=p["pale_mid"], width=10)
    d.line((57, 66, 47, 84), fill=p["pale_mid"], width=9)
    d.line((71, 66, 81, 84), fill=p["pale_mid"], width=9)
    d.rounded_rectangle((54, 60, 74, 92), radius=9, fill=p["pale_hi"],
                        outline=p["pale_dark"], width=2)


GLYPHS = [
    ("use", glyph_use), ("spells", glyph_spells), ("emotes", glyph_emotes),
    ("quest", glyph_quest), ("info", glyph_info), ("buddy", glyph_buddy),
    ("console", glyph_console), ("help", glyph_help), ("options", glyph_options),
    ("ranging", glyph_ranging), ("minimap", glyph_minimap),
    ("stand", glyph_stand),
]


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def downscale_premultiplied(overlay: Image.Image) -> np.ndarray:
    """LANCZOS-downscale an RGBA overlay without dark fringing."""
    data = np.asarray(overlay).astype(np.float64)
    alpha = data[:, :, 3:4] / 255.0
    channels = [data[:, :, ch] * alpha[:, :, 0] for ch in range(3)]
    channels.append(data[:, :, 3])
    small = []
    for channel in channels:
        image = Image.fromarray(channel.astype(np.float32), mode="F")
        small.append(np.asarray(image.resize((CELL, CELL), Image.LANCZOS)))
    result = np.stack(small, axis=-1).astype(np.float64)
    out_alpha = np.clip(result[:, :, 3], 0, 255)
    safe = np.maximum(out_alpha / 255.0, 1e-6)
    for ch in range(3):
        result[:, :, ch] = np.clip(result[:, :, ch] / safe, 0, 255)
    result[:, :, 3] = out_alpha
    return result


def render_icon(blank: np.ndarray, palette: dict, draw_glyph) -> np.ndarray:
    overlay = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    erase = Image.new("L", (BIG, BIG), 0)
    draw_glyph(ImageDraw.Draw(overlay), ImageDraw.Draw(erase), palette)
    if np.asarray(erase).any():
        cleared = np.array(overlay)
        cleared[np.asarray(erase) > 127] = 0
        overlay = Image.fromarray(cleared)

    glyph = downscale_premultiplied(overlay)
    tile = blank.astype(np.float64).copy()

    shadow_alpha = np.zeros((CELL, CELL))
    shadow_alpha[1:, 1:] = glyph[:-1, :-1, 3] * 0.85 / 255.0
    navy = np.array(palette["navy"], dtype=np.float64)
    tile[:, :, :3] = (tile[:, :, :3] * (1 - shadow_alpha[:, :, None])
                      + navy[None, None, :] * shadow_alpha[:, :, None])

    glyph_alpha = glyph[:, :, 3:4] / 255.0
    tile[:, :, :3] = (tile[:, :, :3] * (1 - glyph_alpha)
                      + glyph[:, :, :3] * glyph_alpha)
    tile[:, :, 3] = 255
    return np.clip(np.round(tile), 0, 255).astype(np.uint8)


def main() -> None:
    atlas = np.asarray(Image.open(ATLAS).convert("RGBA"))
    cells = load_cells(atlas, EXISTING)

    blank = derive_blank_tile(cells)
    print(f"blank tile center std: {center_std(blank):.1f}")
    palette = sample_palette(cells, blank)
    for name, value in palette.items():
        print(f"palette {name}: {value}")

    output = np.zeros_like(atlas)
    for index in range(EXISTING):  # byte-identical re-paste of the originals
        row, column = divmod(index, 8)
        output[row * CELL:(row + 1) * CELL, column * CELL:(column + 1) * CELL] = \
            atlas[row * CELL:(row + 1) * CELL, column * CELL:(column + 1) * CELL]

    for offset, (name, draw_glyph) in enumerate(GLYPHS):
        index = NEW_FIRST + offset
        icon = render_icon(blank, palette, draw_glyph)
        unique = len(np.unique(icon.reshape(-1, 4), axis=0))
        print(f"cell {index} ({name}): {unique} unique colours")
        row, column = divmod(index, 8)
        output[row * CELL:(row + 1) * CELL, column * CELL:(column + 1) * CELL] = icon

    Image.fromarray(output).save(ATLAS, optimize=True)
    print(f"wrote {ATLAS}")

    subprocess.run([sys.executable, str(INACTIVE_TOOL)], check=True)
    print(f"regenerated inactive atlas via {INACTIVE_TOOL.name}")

    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    total = NEW_FIRST + NEW_COUNT
    rows = (total + 7) // 8
    sheet = output[:rows * CELL, :]
    Image.fromarray(sheet).resize(
        (sheet.shape[1] * 4, sheet.shape[0] * 4), Image.NEAREST).save(PREVIEW)
    print(f"wrote {PREVIEW}")


if __name__ == "__main__":
    main()
