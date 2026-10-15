"""Sample each creature's palette from the concept figure it was authored from.

Hand-guessed palettes drifted from the artwork, so the roster's colours are
taken from the art itself.  The sampling has to be deliberate: concept art is
dramatically lit, so both the brightest highlight and the largest colour
cluster lie about a creature's own colour.  This takes the median of the
figure's mid-tone band as the hide, lifts it toward an albedo value by a
single factor across all three channels so the hue survives, and picks the
accent from the most saturated cluster that is genuinely distinct from it.

    ELORIA_CONCEPT_DIR=/path/to/sheets \
        python3 eloria-assets/tools/extract_concept_palettes.py
"""
import sys, json, os, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
from scipy import ndimage
import creature_roster as RO

U = Path(os.environ.get('ELORIA_CONCEPT_DIR', 'concept-art'))
os.environ["ELORIA_CONCEPT_DIR"] = str(U)
sheets = sorted({e[7] for e in RO.ROSTER} & set(RO.CONCEPT_SHEETS))
boxes = json.loads(subprocess.run([sys.executable, str(Path(__file__).resolve().parent
                                              / "concept_sheet_index.py"), "--json"] + sheets,
                                  capture_output=True, text=True).stdout)

def figure_pixels(stem, row, col):
    im = Image.open(U/f"{stem}-image.png")
    bx = boxes[stem][row*4+col]
    crop = im.crop(tuple(bx))
    arr = np.asarray(crop.convert("RGBA"), dtype=float)
    rgb, a = arr[..., :3], arr[..., 3]
    if a.min() < 250:
        mask = a > 60
    else:
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        mask = np.linalg.norm(rgb - bg, axis=-1) > 40
    mask = ndimage.binary_opening(mask, np.ones((3, 3)))
    px = rgb[mask]
    # Drop near-black rim/shadow pixels; they bias every palette toward mud.
    lum = px.mean(axis=1)
    px = px[(lum > 20) & (lum < 252)]
    return px

def mid_median(px):
    """The hide colour: median of the middle two luminance quartiles.

    Highlights and cast shadow both lie about a creature's own colour, and a
    mean is dragged around by whichever of the two dominates the crop."""
    lum = px.mean(axis=1)
    lo, hi = np.percentile(lum, [25, 75])
    band = px[(lum >= lo) & (lum <= hi)]
    return np.median(band if len(band) > 50 else px, axis=0)


def kmeans(px, k=6, iters=18, seed=3):
    rng = np.random.default_rng(seed)
    if len(px) > 24000:
        px = px[rng.choice(len(px), 24000, replace=False)]
    c = px[rng.choice(len(px), k, replace=False)]
    for _ in range(iters):
        d = ((px[:, None, :] - c[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(k):
            sel = px[lab == j]
            if len(sel): c[j] = sel.mean(0)
    counts = np.bincount(lab, minlength=k)
    return c, counts

def saturate(c, gain=1.10):
    """Averaging a cluster washes colour out; push it back from grey."""
    c = np.asarray(c, dtype=float)
    grey = c.mean()
    return np.clip(grey + (c - grey) * gain, 0, 255)


def normalise(c, target=155.0, ceiling=205.0, lift=1.30, floor=58.0):
    """Lift a shaded sample toward albedo without inventing a new colour.

    The channel ratios *are* the hue, so scale all three by one factor and
    never let a single channel saturate: clipping one channel at 255 while the
    others stay put is what turned a brown bear into a gold one.  The lift is
    bounded so a near-black revenant stays dark and a chalk-white hare stays
    pale.
    """
    c = np.asarray(c, dtype=float)
    lum = max(float(c.mean()), 1.0)
    goal = min(max(lum * lift, floor), target)
    scaled = c * (goal / lum)
    if scaled.max() > ceiling:
        scaled *= ceiling / scaled.max()
    return np.clip(scaled, 8, 255)


def sat(c):
    mx, mn = c.max(), c.min()
    return 0.0 if mx <= 0 else (mx - mn) / mx

out = {}
for e in RO.ROSTER:
    slug, name, fam, plan, base, accent, scale, stem, row, col = e
    px = figure_pixels(stem, row, col)
    if len(px) < 200:
        out[slug] = (base, accent); continue
    c, n = kmeans(px)
    order = np.argsort(-n)
    # Body: the median of the figure's mid-tone band.  The largest k-means
    # cluster latches onto whichever prop happens to cover the most pixels;
    # the median of the middle two quartiles is the hide itself.
    body = mid_median(px)
    # Accent: the most saturated cluster that is clearly distinct from the body.
    best, score = None, -1
    for j in order:
        cand = c[j]
        dist = float(np.linalg.norm(cand - body))
        if dist <= 45:
            continue
        # Reward clusters that differ from the body in hue *or* in value: a
        # fox's accent is its white chest, not a second shade of orange.
        weight = dist * (0.55 + sat(cand)) * (0.5 + 0.5 * n[j] / max(n.max(), 1))
        if weight > score:
            best, score = cand, weight
    if best is None:
        best = np.clip(body * 1.5 + 30, 0, 255)
    body_n = normalise(saturate(body), target=155.0, lift=1.30, floor=58.0)
    # Keep the accent brighter and more saturated than the body so markings,
    # horn and glow still separate from the hide.
    accent_n = normalise(saturate(best, 1.22), target=196.0, ceiling=224.0,
                         lift=1.62, floor=84.0)
    if np.linalg.norm(accent_n - body_n) < 40:
        accent_n = np.clip(body_n * 1.42 + 34, 0, 246)
    out[slug] = (tuple(int(round(v)) for v in body_n),
                 tuple(int(round(v)) for v in accent_n))
legacy = {}
for (stem, row, col), slug in RO.ALIAS_CELLS.items():
    if slug in out or slug in legacy:
        continue
    try:
        px = figure_pixels(stem, row, col)
    except Exception:
        continue
    if len(px) < 200:
        continue
    c, n = kmeans(px)
    order = np.argsort(-n)
    body = mid_median(px)
    best, score = None, -1
    for j in order:
        cand = c[j]
        dist = float(np.linalg.norm(cand - body))
        if dist <= 45:
            continue
        weight = dist * (0.55 + sat(cand)) * (0.5 + 0.5 * n[j] / max(n.max(), 1))
        if weight > score:
            best, score = cand, weight
    if best is None:
        best = np.clip(body * 1.5 + 30, 0, 255)
    body_n = normalise(saturate(body), 155.0, lift=1.30, floor=58.0)
    accent_n = normalise(saturate(best, 1.22), 196.0, ceiling=224.0,
                     lift=1.62, floor=84.0)
    if np.linalg.norm(accent_n - body_n) < 40:
        accent_n = np.clip(body_n * 1.42 + 34, 0, 246)
    legacy[slug] = (tuple(int(round(v)) for v in body_n),
                    tuple(int(round(v)) for v in accent_n))
Path(os.environ.get("ELORIA_PALETTE_OUT_LEGACY", "palettes_legacy.json")).write_text(
    json.dumps(legacy, indent=1))
print("legacy palettes:", len(legacy))
Path(os.environ.get("ELORIA_PALETTE_OUT", "palettes.json")).write_text(
    json.dumps(out, indent=1))
print("extracted", len(out))
print("sampled", len(out), "roster palettes and", len(legacy), "legacy palettes")
