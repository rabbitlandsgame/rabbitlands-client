"""Index the concept-art sheets by locating each figure's true bounding box.

The sheets are laid out in loose rows of twelve subjects, but the subjects are
not evenly sized or spaced, so slicing a uniform 4x3 grid clips wings, antlers,
tails and trailing effects.  This finds the real figures: connected components
separate most of them, an XY-cut splits any component that fused two touching
neighbours, and a narrow-bridge cut handles subjects whose silhouettes actually
overlap.  Every sheet carries exactly twelve subjects, which is used as the
stopping condition.

    python3 eloria-assets/tools/concept_sheet_index.py --json <stem>...
    python3 eloria-assets/tools/concept_sheet_index.py <stem>... out.png
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import numpy as np
from scipy import ndimage
import os
import sys, json

# Concept sheets live outside the repository; point CONCEPT_DIR at them.
U = Path(os.environ.get("ELORIA_CONCEPT_DIR", "concept-art"))


def subject_mask(im):
    arr = np.asarray(im)
    if im.mode == "RGBA" and arr[..., 3].min() < 250:
        mask = arr[..., 3] > 40
    else:
        rgb = arr[..., :3].astype(float)
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        dist = np.linalg.norm(rgb - bg, axis=-1)
        # Vignetted backdrops drift, so compare to a locally blurred background.
        mask = dist > max(30.0, float(np.percentile(dist, 55)) * 1.9)
    return ndimage.binary_closing(mask, np.ones((11, 11)))


def runs(profile, threshold, min_len):
    on = profile > threshold
    out, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    if start is not None and len(on) - start >= min_len:
        out.append((start, len(on)))
    return out


def _tighten(mask, box):
    sub = mask[box[1]:box[3], box[0]:box[2]]
    ys = np.where(sub.any(axis=1))[0]
    xs = np.where(sub.any(axis=0))[0]
    if not len(ys) or not len(xs):
        return None
    return [box[0] + int(xs[0]), box[1] + int(ys[0]),
            box[0] + int(xs[-1]) + 1, box[1] + int(ys[-1]) + 1]


def _widest_gap(profile, min_gap, margin, tolerance=0):
    """Longest interior run of (near-)empty background, as (start, end)."""
    best = None
    start = None
    for i in range(margin, len(profile) - margin):
        if profile[i] <= tolerance:
            if start is None:
                start = i
        elif start is not None:
            if i - start >= min_gap and (best is None or i - start > best[1] - best[0]):
                best = (start, i)
            start = None
    if start is not None and len(profile) - margin - start >= min_gap:
        if best is None or (len(profile) - margin) - start > best[1] - best[0]:
            best = (start, len(profile) - margin)
    return best


def _clean_mask(im):
    mask = subject_mask(im)
    mask = ndimage.binary_opening(mask, np.ones((3, 3)))
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        keep = np.zeros(n + 1, dtype=bool)
        keep[1:] = sizes >= mask.size * 0.00035
        mask = keep[lab]
    return mask


def _bridge_cut(sub, bw, bh, min_side, limit=0.16):
    best = None
    for axis, profile, span, other in (("x", sub.sum(axis=0), bw, bh),
                                       ("y", sub.sum(axis=1), bh, bw)):
        if span < min_side * 1.8:
            continue
        margin = max(int(span * 0.28), 4)
        interior = profile[margin:span - margin]
        if not len(interior):
            continue
        index = int(np.argmin(interior)) + margin
        value = float(profile[index])
        peak = float(profile.max())
        if peak <= 0 or value > peak * limit:
            continue
        score = value / peak
        if best is None or score < best[0]:
            best = (score, axis, (index, index + 1))
    return None if best is None else (best[1], best[2])


def _one_cut(mask, box, min_gap, min_side, bridge_limit):
    """Split a box exactly once on its best interior separation, or not at all."""
    box = _tighten(mask, box)
    if box is None:
        return []
    bw, bh = box[2] - box[0], box[3] - box[1]
    sub = mask[box[1]:box[3], box[0]:box[2]]
    margin = max(int(min(bw, bh) * 0.10), 4)
    col_gap = _widest_gap(sub.sum(axis=0), min_gap, margin, 0) if bw > min_side else None
    row_gap = _widest_gap(sub.sum(axis=1), min_gap, margin, 0) if bh > min_side else None
    pick = None
    if col_gap and row_gap:
        pick = ("x", col_gap) if (col_gap[1] - col_gap[0]) >= (row_gap[1] - row_gap[0]) else ("y", row_gap)
    elif col_gap:
        pick = ("x", col_gap)
    elif row_gap:
        pick = ("y", row_gap)
    if pick is None:
        pick = _bridge_cut(sub, bw, bh, min_side, bridge_limit)
    if pick is None:
        return [box]
    axis, (g0, g1) = pick
    if axis == "x":
        parts = ([box[0], box[1], box[0] + g0, box[3]],
                 [box[0] + g1, box[1], box[2], box[3]])
    else:
        parts = ([box[0], box[1], box[2], box[1] + g0],
                 [box[0], box[1] + g1, box[2], box[3]])
    out = [b for b in (_tighten(mask, parts[0]), _tighten(mask, parts[1])) if b]
    return out if len(out) == 2 else [box]


def _xy_cut(mask, box, min_gap, min_side, depth=0, bridge_limit=0.16):
    """Split one blob on interior background gaps, either axis, recursively."""
    box = _tighten(mask, box)
    if box is None:
        return []
    bw, bh = box[2] - box[0], box[3] - box[1]
    if depth > 8 or (bw < min_side and bh < min_side):
        return [box]
    sub = mask[box[1]:box[3], box[0]:box[2]]
    margin = max(int(min(bw, bh) * 0.10), 4)
    col_gap = _widest_gap(sub.sum(axis=0), min_gap, margin, 0) if bw > min_side else None
    row_gap = _widest_gap(sub.sum(axis=1), min_gap, margin, 0) if bh > min_side else None
    pick = None
    if col_gap and row_gap:
        pick = ("x", col_gap) if (col_gap[1] - col_gap[0]) >= (row_gap[1] - row_gap[0]) else ("y", row_gap)
    elif col_gap:
        pick = ("x", col_gap)
    elif row_gap:
        pick = ("y", row_gap)
    if pick is None:
        # No clean gap: two subjects actually touch.  Cut the narrowest bridge
        # instead, but only where the join is genuinely thin compared with the
        # blob, so a single creature is never sliced in half.
        pick = _bridge_cut(sub, bw, bh, min_side, bridge_limit)
        if pick is None:
            return [box]
    axis, (g0, g1) = pick
    if axis == "x":
        parts = ([box[0], box[1], box[0] + g0, box[3]],
                 [box[0] + g1, box[1], box[2], box[3]])
    else:
        parts = ([box[0], box[1], box[2], box[1] + g0],
                 [box[0], box[1] + g1, box[2], box[3]])
    return (_xy_cut(mask, parts[0], min_gap, min_side, depth + 1, bridge_limit)
            + _xy_cut(mask, parts[1], min_gap, min_side, depth + 1, bridge_limit))


def figure_boxes(stem, expect=12):
    """Connected components, then an XY-cut inside any blob that fused neighbours.

    A fixed 4x3 grid clips wings, antlers and tails because the subjects are not
    evenly sized or spaced.  Components isolate most figures; where two touch,
    splitting that component on its own interior background gap separates them.
    """
    im = Image.open(U / f"{stem}-image.png")
    mask = _clean_mask(im)
    h, w = mask.shape
    lab, _ = ndimage.label(mask, structure=np.ones((3, 3)))
    boxes = []
    for sl in ndimage.find_objects(lab):
        if sl is None:
            continue
        box = [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop]
        if _area(box) < 0.0016 * h * w:
            continue
        boxes.append(box)
    # Re-unite a figure split into pieces (a detached wing tip, floating shards).
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                small = min(_area(a), _area(b))
                if small and _overlap(a, b) / small > 0.55:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])]
                    boxes.pop(j)
                    changed = True
                    break
            if changed:
                break
    # Every sheet carries exactly twelve subjects, so keep splitting the
    # largest still-divisible blob until the count is reached.  Two touching
    # creatures fuse into one component that is not always much larger than
    # its neighbours, which a pure size threshold misses.
    min_gap = max(int(min(h, w) * 0.012), 5)
    min_side = int(min(h, w) * 0.085)
    guard = 0
    # Overlapping subjects need a more permissive bridge before they separate,
    # so widen the tolerance only once the strict pass has stopped making
    # progress - that keeps a single creature from being sliced in two.
    for bridge_limit in (0.16, 0.34, 0.52):
        while len(boxes) < expect and guard < 96:
            guard += 1
            candidates = sorted(range(len(boxes)), key=lambda i: -_area(boxes[i]))
            for index in candidates:
                # One cut at a time: a recursive split can overshoot twelve and
                # slice a single creature in half.
                pieces = _one_cut(mask, boxes[index], min_gap, min_side, bridge_limit)
                pieces = [b for b in pieces if _area(b) >= 0.0016 * h * w]
                if len(pieces) == 2:
                    boxes.pop(index)
                    boxes.extend(pieces)
                    break
            else:
                break
        if len(boxes) >= expect:
            break
    rows, current = [], []
    for box in sorted(boxes, key=lambda b: b[1]):
        if current:
            ref = current[0]
            if box[1] > ref[1] + (ref[3] - ref[1]) * .62:
                rows.append(sorted(current, key=lambda x: x[0]))
                current = []
        current.append(box)
    if current:
        rows.append(sorted(current, key=lambda x: x[0]))
    return im, [b for row in rows for b in row]


def _overlap(a, b):
    return (max(min(a[2], b[2]) - max(a[0], b[0]), 0)
            * max(min(a[3], b[3]) - max(a[1], b[1]), 0))


def _area(b):
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def render(stem, width=700):
    im, boxes = figure_boxes(stem)
    bg = Image.new("RGB", im.size, (46, 50, 56))
    bg.paste(im, (0, 0), im if im.mode == "RGBA" else None)
    d = ImageDraw.Draw(bg)
    f = ImageFont.load_default(size=max(26, im.width // 42))
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        d.rectangle((x0, y0, x1, y1), outline=(255, 214, 64), width=4)
        d.text((x0 + 6, y0 + 4), str(i), fill=(255, 236, 120), font=f,
               stroke_width=4, stroke_fill=(0, 0, 0))
    s = width / bg.width
    bg = bg.resize((width, int(bg.height * s)), Image.LANCZOS)
    lab = Image.new("RGB", (bg.width, bg.height + 26), (16, 18, 21))
    lab.paste(bg, (0, 26))
    ImageDraw.Draw(lab).text((6, 5), f"{stem}  n={len(boxes)}", fill=(240, 240, 240),
                             font=ImageFont.load_default(size=17))
    return lab


if __name__ == "__main__":
    if sys.argv[1] == "--json":
        out = {s: figure_boxes(s)[1] for s in sys.argv[2:]}
        print(json.dumps(out))
    else:
        panels = [render(s) for s in sys.argv[1:-1]]
        W = sum(p.width for p in panels); H = max(p.height for p in panels)
        comb = Image.new("RGB", (W, H), (16, 18, 21)); x = 0
        for p in panels: comb.paste(p, (x, 0)); x += p.width
        comb.save(sys.argv[-1]); print(comb.size)
