"""Island ground for Landfall A3 from the continent-v2 Meshy GLB, on the frozen grid's 2 m odd-metre lattice.

python island_ground.py <north|southeast> [--preview]

Recipe (as close as the lost 24 km chain allows to source-data/sw_island/heightfield_sw_2m_meta.json):
  * the Meshy mesh rasterised at exactly 2 m (top surface, z-buffer), source window = destination + offset;
  * heights on the plan's vertical curve h = A ln(1 + u/u0), u = (Y - sea_model_Y) * U (sea level 0 m);
  * objects removed with a grey opening (disc 8 m) where the top surface stands > 1 m above it, then a 2 m blend;
  * an island mask (the drafts' polygon, noise-warped) with a coastal profile: land ramps to a 0.5-1.5 m beach band,
    sea floor falls to -4 m over ~60 m; pits < 800 m2 filled;
  * edits: pads for the rebuilt landmarks (SE temple plaza, north citadel terrace);
  * detail: band-limited noise 0.22 m on gentle ground, up to 1.2 m on cliffs, none below 1 m or on pads.
Colour = the mesh texture at the top surface. Outputs heights (f32), colours (rgba8) and masks on the destination
window, plus a hillshade preview. Nothing is written into either repository.
"""
import json, sys, math
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy import ndimage

GLB = r'C:\rabbitlands\rabbitlands-client\.local\asset-authoring\workspace\nymara_map_4x4_overlap_tiles\Meshy_AI_Isles_of_Enchantment_1001145324_texture.glb'
BASE = Path(__file__).resolve().parents[1] / 'v2-base'
OUT = Path(__file__).resolve().parents[1] / 'island-ground'
U = 4667.9267244824205; X0 = -0.8714030; Z0 = -0.9505840; SEA_Y = -0.074
A = 259.0078328433769; U0 = 259.0078328433769
CELL = 2.0

ISLANDS = {
    # destination window (odd-metre lattice), source offset (src = dst + offset), polygon (dst metres), pads
    'north': {
        'window': [651, 5051, 1989, 6061],
        'offset': [3560, -1650],
        'polygon': [(820, 5560), (980, 5330), (1300, 5250), (1640, 5300), (1830, 5470), (1800, 5720), (1600, 5890),
                    (1260, 5930), (950, 5860), (800, 5720)],
        'warp': 18, 'seed': 31, 'taper': 230, 'vscale': 1.0, 'join': None, 'mask': 'draft',
        # citadel terrace: centre of the model's Mirrorhold citadel (4767,3967) in destination coords
        'pads': [{'name': 'citadel terrace', 'centre': [1250, 5465], 'radius': 30, 'blend': 18, 'level': 'median', 'repaint': True}],
    },
    'southeast': {
        # wide enough for the polygon's south-west arm round Tollholm and Spindle Hill (to x 2580) plus a shelf
        'window': [2551, 7451, 4051, 8751],
        'offset': [3000, -1620],
        'polygon': [(3080, 7700), (3280, 7580), (3560, 7550), (3820, 7640), (3950, 7900), (3920, 8220), (3740, 8460),
                    (3460, 8580), (3150, 8590), (2880, 8520), (2640, 8430), (2580, 8340), (2800, 8370), (3050, 8340),
                    (3120, 8100)],
        'warp': 16, 'seed': 33, 'taper': 160, 'vscale': 0.5, 'mask': 'draft',
        'join': {'lowland_m': 260, 'close_m': 10, 'lagoon_m2': 6000},
        # temple plaza: the model's step pyramid (6700,6347) flattened to a terrace for the game-scale temple kit
        'pads': [{'name': 'temple summit', 'centre': [6700 - 3000, 6347 + 1620], 'radius': 22, 'blend': 10, 'level': 'p90', 'repaint': False}],
    },
}


def rasterise(win, offset):
    """Top surface (model Y) and colour of the Meshy mesh on destination lattice points, z-buffered."""
    x0, z0, x1, z1 = win
    xs = np.arange(x0, x1 + 1, CELL); zs = np.arange(z0, z1 + 1, CELL)
    W, H = len(xs), len(zs)
    s = trimesh.load(GLB, force='scene'); g = list(s.geometry.values())[0]
    V = np.asarray(g.vertices, np.float64); F = np.asarray(g.faces); UV = np.asarray(g.visual.uv, np.float64)
    tex = np.asarray(g.visual.material.baseColorTexture.convert('RGB')); th, tw = tex.shape[:2]
    # source-frame metres of vertices
    vx = (V[:, 0] - X0) * U; vz = (V[:, 2] - Z0) * U
    sx0, sz0 = x0 + offset[0], z0 + offset[1]
    sx1, sz1 = x1 + offset[0], z1 + offset[1]
    fx = vx[F]; fz = vz[F]
    keep = (fx.max(1) >= sx0 - 4) & (fx.min(1) <= sx1 + 4) & (fz.max(1) >= sz0 - 4) & (fz.min(1) <= sz1 + 4)
    F = F[keep]; fx = fx[keep]; fz = fz[keep]
    fy = V[F][:, :, 1]; fu = UV[F]
    top = np.full((H, W), -np.inf); col = np.zeros((H, W, 3), np.uint8)
    # candidate cells per face: bbox in lattice indices (faces are ~5-7 m: <= 5 cells wide)
    ci0 = np.floor((fx.min(1) - sx0) / CELL).astype(int); ci1 = np.ceil((fx.max(1) - sx0) / CELL).astype(int)
    ri0 = np.floor((fz.min(1) - sz0) / CELL).astype(int); ri1 = np.ceil((fz.max(1) - sz0) / CELL).astype(int)
    span = int(max((ci1 - ci0).max(), (ri1 - ri0).max())) + 1
    a = np.stack([fx[:, 0], fz[:, 0]], 1); b = np.stack([fx[:, 1], fz[:, 1]], 1); c = np.stack([fx[:, 2], fz[:, 2]], 1)
    v0 = b - a; v1 = c - a
    d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1)
    den = d00 * d11 - d01 * d01; den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    for dr in range(span):
        for dc in range(span):
            r = ri0 + dr; cidx = ci0 + dc
            ok = (r <= ri1) & (cidx <= ci1) & (r >= 0) & (r < H) & (cidx >= 0) & (cidx < W)
            if not ok.any():
                continue
            px = sx0 + cidx * CELL; pz = sz0 + r * CELL
            v2x = px - a[:, 0]; v2z = pz - a[:, 1]
            d20 = v2x * v0[:, 0] + v2z * v0[:, 1]; d21 = v2x * v1[:, 0] + v2z * v1[:, 1]
            wv = (d11 * d20 - d01 * d21) / den; ww = (d00 * d21 - d01 * d20) / den; wu = 1 - wv - ww
            inside = ok & (wu >= -1e-6) & (wv >= -1e-6) & (ww >= -1e-6)
            if not inside.any():
                continue
            yy = wu * fy[:, 0] + wv * fy[:, 1] + ww * fy[:, 2]
            idx = np.nonzero(inside)[0]
            rr = r[idx]; cc = cidx[idx]; yv = yy[idx]
            order = np.argsort(yv)
            rr, cc, yv, idx = rr[order], cc[order], yv[order], idx[order]
            better = yv > top[rr, cc]
            rr, cc, yv, idx = rr[better], cc[better], yv[better], idx[better]
            top[rr, cc] = yv
            uvx = wu[idx] * fu[idx, 0, 0] + wv[idx] * fu[idx, 1, 0] + ww[idx] * fu[idx, 2, 0]
            uvy = wu[idx] * fu[idx, 0, 1] + wv[idx] * fu[idx, 1, 1] + ww[idx] * fu[idx, 2, 1]
            tu = np.clip((uvx % 1.0) * tw, 0, tw - 1).astype(int); tv = np.clip((1 - (uvy % 1.0)) * th, 0, th - 1).astype(int)
            col[rr, cc] = tex[tv, tu]
    holes = ~np.isfinite(top)
    np.save(str(OUT / 'last-raster-holes.npy'), holes)
    if holes.any():
        ii = ndimage.distance_transform_edt(holes, return_distances=False, return_indices=True)
        top = top[tuple(ii)]; col = col[tuple(ii)]
    u = (top - SEA_Y) * U
    h = np.where(u >= 0, A * np.log1p(np.maximum(u, 0) / U0), u)
    return xs, zs, h.astype(np.float64), col, int(holes.sum())


def noise(shape, scale_px, octaves, seed):
    r = np.random.default_rng(seed); out = np.zeros(shape); amp = 1.0; tot = 0
    for o in range(octaves):
        s = max(2, int(scale_px / 2 ** o))
        sm = r.standard_normal((shape[0] // s + 3, shape[1] // s + 3))
        out += amp * ndimage.zoom(sm, s, order=3)[:shape[0], :shape[1]]; tot += amp; amp *= 0.5
    return out / tot


def polygon_mask(xs, zs, poly, warp, seed):
    W, H = len(xs), len(zs)
    im = Image.new('L', (W, H), 0)
    ImageDraw.Draw(im).polygon([((x - xs[0]) / CELL, (z - zs[0]) / CELL) for x, z in poly], fill=255)
    m = np.array(im) > 127
    din = ndimage.distance_transform_edt(m) * CELL; dout = ndimage.distance_transform_edt(~m) * CELL
    sd = np.where(m, din, -dout) + noise(m.shape, 30, 4, seed) * warp * 1.6
    return sd  # signed distance to the warped coast (m), positive on land


def draft_sd(xs, zs, poly, seed):
    """Signed distance (m) to the approved A3 draft's new-land coast, limited to 150 m round this isle's polygon."""
    d = np.load(OUT / 'a3-draft-newland.npz')
    fx0, fz0, _, _, fc = d['frame']
    jj = (np.asarray(xs) - fx0) / fc - 0.5; ii = (np.asarray(zs) - fz0) / fc - 0.5
    I, J = np.meshgrid(ii, jj, indexing='ij')
    m = ndimage.map_coordinates(ndimage.gaussian_filter(d['newland'].astype(float), 0.7), [I, J], order=1) > 0.5
    im = Image.new('L', (len(xs), len(zs)), 0)
    ImageDraw.Draw(im).polygon([((x - xs[0]) / CELL, (z - zs[0]) / CELL) for x, z in poly], fill=255)
    near = ndimage.distance_transform_edt(~(np.array(im) > 127)) * CELL < 150
    m &= near
    din = ndimage.distance_transform_edt(m) * CELL; dout = ndimage.distance_transform_edt(~m) * CELL
    return np.where(m, din, -dout) + noise(m.shape, 12, 3, seed + 40) * 7


def build(name):
    I = ISLANDS[name]
    xs, zs, top, col, holes = rasterise(I['window'], I['offset'])
    disc = ndimage.generate_binary_structure(2, 1)
    r = int(round(8 / CELL))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]; fp = (xx * xx + yy * yy) <= r * r
    ground = ndimage.grey_opening(top, footprint=fp)
    obj = (top - ground) > 1.0
    obj = ndimage.binary_dilation(obj, iterations=1)
    h = np.where(obj, ground, top)
    h = ndimage.gaussian_filter(h, 0.8)
    h = h * I['vscale']
    # the coast: the approved A3 draft's own new-land outline (fine warp added); the polygon only bounds it
    sd = draft_sd(xs, zs, I['polygon'], I['seed']) if I.get('mask') == 'draft' else polygon_mask(xs, zs, I['polygon'], I['warp'], I['seed'])
    # the staged v2 base (build_continent_v2_ground.py --base) and its recorded exclusions under this window
    bmeta = json.load(open(BASE / 'base.json'))
    GW, GH = bmeta['grid']['gridSize']; gx0, gz0 = bmeta['grid']['continentFirstVertex']
    ci = np.round((xs - gx0) / CELL).astype(int); ri = np.round((zs - gz0) / CELL).astype(int)
    assert ci.min() >= 0 and ri.min() >= 0 and ci.max() < GW and ri.max() < GH, 'window outside the v2 grid'
    G = np.fromfile(BASE / 'base-heights.f32le', '<f4').reshape(GH, GW)
    EX = np.unpackbits(np.fromfile(BASE / 'exclusions.bits', np.uint8), count=GW * GH).reshape(GH, GW).astype(bool)
    existing = G[np.ix_(ri, ci)].astype(np.float64)
    excl = EX[np.ix_(ri, ci)]
    forbid = ndimage.binary_dilation(excl, iterations=4)  # new coast stays 8 m clear of every exclusion
    old_land = existing > 0
    sd = np.where(forbid, np.minimum(sd, -1.0), sd)
    if I['join']:
        # keep the base's land, and keep new ground low near it (lagoon lowland)
        d_old = ndimage.distance_transform_edt(~old_land) * CELL
        low = np.clip(d_old / I['join']['lowland_m'], 0, 1) ** 1.3
        h = h * (0.08 + 0.92 * low)
        sd = np.where(old_land, -1.0, sd)  # never overwrite existing land
        # one island: close sea gaps under ~2 x close_m between the new ground and the old coast (a walkable neck),
        # fill sea pockets this encloses unless they are lagoons over lagoon_m2
        rc = int(round(I['join'].get('close_m', 0) / CELL))
        if rc:
            yy, xx = np.mgrid[-rc:rc + 1, -rc:rc + 1]; disc_c = (xx * xx + yy * yy) <= rc * rc
            both = old_land | (sd > 0)
            closed = ndimage.binary_closing(np.pad(both, rc), structure=disc_c)[rc:-rc, rc:-rc]
            add = closed & ~both
            sea = ~(both | add)
            lab, n = ndimage.label(sea)
            edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
            sizes = ndimage.sum(np.ones_like(lab), lab, index=np.arange(n + 1)) * CELL * CELL
            for k in range(1, n + 1):
                if k not in edge and sizes[k] < I['join'].get('lagoon_m2', 0):
                    add |= lab == k
            sd = np.where(add & ~forbid, np.maximum(sd, 1.0), sd)
    land = sd > 0
    # one island: keep the main landmass and any islet over 2,000 m2; drop the rest to sea
    lab, n = ndimage.label(land)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)) * CELL * CELL
        keep_ids = [i + 1 for i, a in enumerate(sizes) if a >= 2000 or a == sizes.max()]
        land = np.isin(lab, keep_ids)
        sd = np.where(land, np.maximum(sd, 0.01), np.minimum(sd, -0.01))
    # taper heights toward the coast so the island rises from its beaches
    env = np.clip(sd / I['taper'], 0, 1); env = env * env * (3 - 2 * env)
    h = h * (0.06 + 0.94 * env)
    # coastal profile: inland ramp to a beach band, offshore shelf to -4 m
    inland = np.clip(sd / 40.0, 0, 1)
    beach = 0.5 + 1.0 * np.clip(sd / 12.0, 0, 1)
    h_land = np.maximum(h, 0.4) * inland + beach * (1 - inland)
    off = np.clip(-sd / 60.0, 0, 1)
    h_sea = -0.6 - 1.9 * off
    h = np.where(land, h_land, h_sea)
    # pads
    pads_rep = []
    for p in I['pads']:
        cx, cz = p['centre']
        X, Z = np.meshgrid(xs, zs)
        d = np.hypot(X - cx, Z - cz)
        core = d <= p['radius']
        if p['level'] == 'p90':
            level = float(np.percentile(h[core], 90))
        elif p['level'] == 'ring':
            ring = (d > p['radius'] + 10) & (d <= p['radius'] + 50) & land
            level = float(np.median(h[ring]))
        else:
            level = float(np.median(h[core])) if p['level'] == 'median' else float(p['level'])
        w = np.clip((p['radius'] + p['blend'] - d) / p['blend'], 0, 1)
        h = np.where(land, h * (1 - w) + level * w, h)
        # repaint the pad with the surrounding ground colour (the model painted the old landmark there)
        ringc = (d > p['radius'] + 10) & (d <= p['radius'] + 50) & land
        if ringc.any() and p.get('repaint', True):
            mc = np.median(col[ringc].reshape(-1, 3), axis=0)
            col = (col.astype(float) * (1 - w[..., None] * 0.85) + mc * w[..., None] * 0.85).astype(np.uint8)
        pads_rep.append({'name': p['name'], 'centre': [cx, cz], 'radius': p['radius'], 'level_m': round(level, 2)})
    # fill pits < 800 m2 on land
    filled = h.copy()
    lab, n = ndimage.label(land & (h < ndimage.grey_closing(h, size=(9, 9)) - 0.3))
    small = 0
    for k in range(1, n + 1):
        cells = lab == k
        if cells.sum() * CELL * CELL < 800:
            filled[cells] = ndimage.grey_closing(h, size=(9, 9))[cells]; small += 1
    h = filled
    # detail noise
    gz, gx = np.gradient(h, CELL); slope = np.hypot(gx, gz)
    amp = np.where(slope > 0.9, 1.2, np.where(slope > 0.5, 0.22 + (slope - 0.5) / 0.4 * 0.98, 0.22))
    padmask = np.zeros_like(land)
    for p in I['pads']:
        X, Z = np.meshgrid(xs, zs); padmask |= np.hypot(X - p['centre'][0], Z - p['centre'][1]) <= p['radius'] + p['blend']
    amp = np.where(land & (h > 1.0) & ~padmask, amp, 0.0)
    det = noise(h.shape, 6, 3, I['seed'] + 7)
    h = h + det * amp * 0.5
    rgba = np.concatenate([col, np.full(col.shape[:2] + (1,), 255, np.uint8)], 2)
    # weights for build_continent_v2_ground.py: the island's land in full; its shelf fades into the base's seabed
    # over 80 m (heights) and 30 m (colours); never the base's own land, never an exclusion
    d_new = ndimage.distance_transform_edt(~land) * CELL
    wh = np.where(land, 255, np.round(255 * np.clip(1 - d_new / 80.0, 0, 1)))
    wc = np.where(land, 255, np.round(255 * np.clip(1 - d_new / 30.0, 0, 1)))
    wh[old_land | excl] = 0; wc[old_land | excl] = 0
    assert not (land & (old_land | excl)).any()
    OUT.mkdir(parents=True, exist_ok=True)
    stem = OUT / name
    h.astype('<f4').tofile(str(stem) + '-heights.f32le')
    rgba.tofile(str(stem) + '-colors.rgba8')
    wh.astype(np.uint8).tofile(str(stem) + '-wh.u8')
    wc.astype(np.uint8).tofile(str(stem) + '-wc.u8')
    land.astype(np.uint8).tofile(str(stem) + '-land.u8')
    meta = {'island': name, 'firstVertex': [float(xs[0]), float(zs[0])], 'gridSize': [len(xs), len(zs)], 'cellMetres': CELL,
            'sourceOffset': I['offset'], 'sourceGlbSha256': '42c887398a86d6f3675cf1e5396234d972b3544fb795e877d6cfa4771f155d30',
            'land_km2': round(float(land.sum()) * CELL * CELL / 1e6, 3), 'h_max': round(float(h[land].max()), 1),
            'h_median_land': round(float(np.median(h[land])), 1), 'objects_removed_share': round(float((obj & land).mean()), 3),
            'pits_filled': small, 'raster_holes_filled': holes, 'pads': pads_rep}
    json.dump(meta, open(str(stem) + '-meta.json', 'w'), indent=1)
    if '--preview' in sys.argv:
        light = np.clip(0.55 + 0.6 * (-gx * 0.7 - gz * 0.7) / np.sqrt(gx * gx + gz * gz + 1), 0.3, 1.2)
        gz2, gx2 = np.gradient(h, CELL)
        light = np.clip(0.6 + 0.5 * (-gx2 - gz2) / np.sqrt(gx2 * gx2 + gz2 * gz2 + 1), 0.25, 1.25)
        img = col.astype(float) * light[..., None]
        sea = np.array([30, 80, 120.0]) * (0.6 + 0.4 * np.clip(1 + h / 4, 0, 1))[..., None]
        img = np.where(land[..., None], img, sea)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(str(stem) + '-preview.png')
    print(json.dumps(meta))


if __name__ == '__main__':
    build(sys.argv[1])
