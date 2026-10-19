"""Landfall A3 strait fills: weighted 2 m edit rasters for build_continent_v2_ground.py.

python strait_fills.py [--preview]

Reads the staged v2 base (v2-base/: build_continent_v2_ground.py --base) and its recorded exclusions. The new land is
the approved A3 draft's own new-land mask (drafts.py compose('A3'), exported to island-ground/a3-draft-newland.npz at
4 m), restricted to the north-coast and B22 windows (the isles come from island_ground.py; B24 stays sea because the
south-east isle is boat-only). It is resampled to 2 m with a fine coastline warp; sea slivers under ~24 m wide
against the old coast are closed and enclosed sea ponds filled; the coast keeps 8 m clear of every exclusion.

  * heights: near the old coast they join the old land (harmonic fill pinned to at most 6 m of the old height, so old
    sea cliffs stay as inland escarpments); away from it they follow each area's plain band (low hummocks rising
    from a beach at the new coast); a 40 m shelf fades into the base's seabed;
  * colours: harmonic inpaint from inland land (the old beach band excluded) plus low variation; the old beach band
    next to the new land is repainted (colour weight only), so no sand stripe runs through the new land;
  * the base's land heights are never changed (height weight 0 there).
Writes island-ground/fills-<window>-{heights.f32le,colors.rgba8,wh.u8,wc.u8} and fills-meta.json (+ preview).
Nothing is written into either repository.
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'v2-base'
OUT = ROOT / 'island-ground'
CELL = 2.0

# windows (continent metres x1, z1, x2, z2) of the A3 draft new land that this tool builds
WINDOWS = [('north-coast', (1400, 6300, 3300, 7320)), ('b22-bars', (1540, 7470, 2120, 8020))]
PAD = 160
# plain bands by area, as in the draft: (centre, radius, (min, max) metres, hummock amplitude)
BANDS = [((1720, 6480), 220, (2, 6), 0.6),      # Saltsound islet join
         ((1950, 6650), 420, (4, 12), 1.4),     # Saltsound bay (Amethyst)
         ((2650, 6560), 380, (4, 14), 1.4),     # Ringholm north shelf
         ((2100, 6820), 200, (3, 10), 1.0),     # B14 strait
         ((2400, 7060), 330, (2, 5), 0.5),      # Ringholm-Ravenhead sound (salt pans)
         ((3020, 6850), 220, (4, 12), 1.0),     # Ringholm east
         ((1800, 7740), 300, (1.0, 2.2), 0.2)]  # sand bars


def noise(shape, scale_px, octaves, seed):
    r = np.random.default_rng(seed); out = np.zeros(shape); amp = 1.0; tot = 0
    for o in range(octaves):
        s = max(2, int(scale_px / 2 ** o))
        sm = r.standard_normal((shape[0] // s + 3, shape[1] // s + 3))
        out += amp * ndimage.zoom(sm, s, order=3)[:shape[0], :shape[1]]; tot += amp; amp *= 0.5
    return out / tot


def harmonic(values, known, iters=300):
    """Fill unknown cells by Jacobi relaxation of the Laplace equation (values fixed where known); edges replicate."""
    idx = ndimage.distance_transform_edt(~known, return_distances=False, return_indices=True)
    v = np.where(known, values, values[tuple(idx)]).astype(np.float64)
    for _ in range(iters):
        p = np.pad(v, 1, mode='edge')
        avg = 0.25 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
        v = np.where(known, values, avg)
    return v


def main():
    bmeta = json.load(open(BASE / 'base.json'))
    W, H = bmeta['grid']['gridSize']; x0, z0 = bmeta['grid']['continentFirstVertex']
    hts = np.fromfile(BASE / 'base-heights.f32le', '<f4').reshape(H, W).astype(np.float64)
    cols = np.fromfile(BASE / 'base-colors.rgba8', np.uint8).reshape(H, W, 4)
    EX = np.unpackbits(np.fromfile(BASE / 'exclusions.bits', np.uint8), count=W * H).reshape(H, W).astype(bool)
    d = np.load(OUT / 'a3-draft-newland.npz')
    fx0, fz0, _, _, fc = d['frame']
    draft = ndimage.gaussian_filter(d['newland'].astype(np.float64), 0.7)
    report = []
    previews = []
    for wi, (wname, (wx1, wz1, wx2, wz2)) in enumerate(WINDOWS):
        c0 = int((wx1 - PAD - x0) // CELL); c1 = int((wx2 + PAD - x0) // CELL) + 1
        r0 = int((wz1 - PAD - z0) // CELL); r1 = int((wz2 + PAD - z0) // CELL) + 1
        sub = (slice(r0, r1), slice(c0, c1))
        gx = x0 + CELL * np.arange(c0, c1); gz = z0 + CELL * np.arange(r0, r1)
        inwin = ((gx >= wx1) & (gx <= wx2))[None, :] & ((gz >= wz1) & (gz <= wz2))[:, None]
        L0 = hts[sub] > 0
        excl = EX[sub]
        forbid = ndimage.binary_dilation(excl, iterations=4)
        # draft mask (4 m cell centres) resampled at the 2 m vertices, then a fine coastline warp
        I, J = np.meshgrid((gz - fz0) / fc - 0.5, (gx - fx0) / fc - 0.5, indexing='ij')
        m = (ndimage.map_coordinates(draft, [I, J], order=1) > 0.5) & inwin
        din = ndimage.distance_transform_edt(m) * CELL; dout = ndimage.distance_transform_edt(~m) * CELL
        sd = np.where(m, din, -dout) + noise(m.shape, 12, 3, 60 + wi) * 7
        new = (sd > 0) & ~L0 & inwin & ~forbid
        # close slivers of sea between new and old land; fill enclosed ponds
        closed = ndimage.binary_closing(L0 | new, structure=np.ones((3, 3)), iterations=6, border_value=0)
        new |= closed & ~L0 & inwin & ~forbid
        lab, n = ndimage.label(~(L0 | new))
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        ponds = [k for k in range(1, n + 1) if k not in edge]
        for k in ponds:
            new |= (lab == k) & inwin & ~forbid
        # small islets of new land touching nothing: drop
        labn, nn = ndimage.label(new | L0)
        keep = np.zeros(nn + 1, bool)
        keep[np.unique(labn[L0])] = True
        keep |= ndimage.sum(np.ones_like(labn), labn, index=np.arange(nn + 1)) * CELL * CELL >= 2000
        keep[0] = False
        new &= keep[labn]
        # ---- heights
        coastd = ndimage.distance_transform_edt(new | L0) * CELL          # distance to the (new) sea
        oldd = ndimage.distance_transform_edt(~L0) * CELL                  # distance to old land
        newd = ndimage.distance_transform_edt(~new) * CELL                 # distance to new land
        lo = np.zeros(m.shape); hi = np.zeros(m.shape); hum = np.zeros(m.shape); wsum = np.zeros(m.shape)
        for (bx, bz), rad, (blo, bhi), bh in BANDS:
            w = np.exp(-(((gx[None, :] - bx) ** 2 + (gz[:, None] - bz) ** 2) / (2 * (rad * 0.6) ** 2)))
            lo += w * blo; hi += w * bhi; hum += w * bh; wsum += w
        wsum = np.maximum(wsum, 1e-6); lo /= wsum; hi /= wsum; hum /= wsum
        n1 = noise(m.shape, 50, 4, 70 + wi) * 0.5 + 0.5
        plain = lo + (hi - lo) * np.clip(n1, 0, 1) + noise(m.shape, 10, 3, 80 + wi) * hum
        ramp = np.clip(coastd / 140.0, 0, 1) ** 0.8
        prof = 0.5 + (plain - 0.5) * ramp
        base_h = hts[sub]
        # old sea cliffs stay as inland escarpments: the join is pinned to at most 6 m of the old coast's height
        join = harmonic(np.where(L0, np.minimum(base_h, 6.0), 0.0), L0 | ~ndimage.binary_dilation(new, iterations=4))
        wj = np.clip(oldd / 90.0, 0, 1) ** 1.5
        hh = join * (1 - wj) + prof * wj
        hh = np.minimum(hh, prof + np.maximum(join, 0) * (1 - wj))
        hh = np.maximum(hh, 0.35 + 0.25 * np.clip(coastd / 20, 0, 1))
        eh = base_h.copy()
        eh[new] = hh[new]
        shelf = ~(L0 | new) & (newd < 40)
        eh[shelf] = -0.4 - 2.1 * newd[shelf] / 40.0
        wh = np.zeros(m.shape)
        wh[new] = 255
        wh[shelf] = np.round(255 * np.clip(1 - newd[shelf] / 40.0, 0, 1))
        # ---- colours: inpaint from inland old land, repaint the old beach band next to the new land
        old_coastd = ndimage.distance_transform_edt(L0) * CELL
        beach = L0 & (old_coastd < 36) & (newd < 60) & (base_h < 4.0)
        known = L0 & ~beach & (old_coastd >= 36)
        c_sub = cols[sub].astype(np.float64)
        ec = c_sub.copy()
        vary = 1 + 0.10 * noise(m.shape, 30, 2, 95 + wi)
        for k in range(3):
            ch = harmonic(c_sub[..., k], known, iters=300)
            ec[..., k] = ch * (vary + 0.07 * noise(m.shape, 3, 2, 90 + k + wi))
        sand = np.array([196, 176, 128.0])
        t = (np.clip((14 - coastd) / 14, 0, 1) * 0.8)[..., None]
        ec[..., :3] = np.where((new & (coastd < 14))[..., None], ec[..., :3] * (1 - t) + sand * t, ec[..., :3])
        ec[..., 3] = 255
        ec = np.clip(np.round(ec), 0, 255).astype(np.uint8)
        wc = np.zeros(m.shape)
        wc[new] = 255
        wb = np.clip((36 - old_coastd) / 36, 0, 1) * np.clip((60 - newd) / 60, 0, 1)
        wc[beach] = np.round(255 * wb[beach])
        wh[excl] = 0; wc[excl] = 0
        assert not (new & excl).any() and not ((wh > 0) & L0).any()
        stem = OUT / f'fills-{wname}'
        eh.astype('<f4').tofile(str(stem) + '-heights.f32le')
        ec.tofile(str(stem) + '-colors.rgba8')
        wh.astype(np.uint8).tofile(str(stem) + '-wh.u8')
        wc.astype(np.uint8).tofile(str(stem) + '-wc.u8')
        report.append({'window': wname, 'firstVertex': [float(gx[0]), float(gz[0])], 'gridSize': [len(gx), len(gz)],
                       'new_land_m2': int(new.sum() * CELL * CELL), 'ponds_filled': len(ponds),
                       'h_range': [round(float(hh[new].min()), 2), round(float(hh[new].max()), 2)],
                       'beach_repainted_m2': int((wc[beach] > 0).sum() * CELL * CELL),
                       'forbidden_in_draft_m2': int(((sd > 0) & ~L0 & inwin & forbid).sum() * CELL * CELL)})
        previews.append((sub, eh, ec, wh, wc, new))
    total = sum(r['new_land_m2'] for r in report)
    json.dump({'base': bmeta, 'windows': report, 'new_land_m2': total}, open(OUT / 'fills-meta.json', 'w'), indent=1)
    for r in report:
        print(r)
    print('new land km2 %.3f' % (total / 1e6))
    if '--preview' in sys.argv:
        for (sub, eh, ec, wh, wc, new), r in zip(previews, report):
            a = wh / 255.0; b = (wc / 255.0)[..., None]
            h = hts[sub] * (1 - a) + eh * a
            c = cols[sub][..., :3] * (1 - b) + ec[..., :3] * b
            gz_, gx_ = np.gradient(h, CELL)
            light = np.clip(0.6 + 0.5 * (-gx_ - gz_) / np.sqrt(gx_ * gx_ + gz_ * gz_ + 1), 0.25, 1.25)
            img = c * light[..., None]
            dpt = np.clip(-h / 14, 0, 1)[..., None]
            img = np.where((h > 0)[..., None], img, np.array([70, 150, 180.0]) * (1 - dpt) + np.array([15, 40, 90.0]) * dpt)
            img[new & ~ndimage.binary_erosion(new)] = (255, 220, 60)
            img[EX[sub]] = img[EX[sub]] * 0.5 + np.array([255, 40, 40.0]) * 0.5
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(OUT / f"fills-{r['window']}-preview.png")


if __name__ == '__main__':
    main()
