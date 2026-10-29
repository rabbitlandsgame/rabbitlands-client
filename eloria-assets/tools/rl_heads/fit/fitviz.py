"""Preview images: reference (textured) | fitted RL head | signed-residual heat map,
for the front, profile and three-quarter views (CPU rasterised, ~512 px panels),
plus a segmentation view of the reference."""
import os
import numpy as np
from PIL import Image, ImageDraw

import raster
from raster import view_camera, rasterize
from fitcommon import unit

SEG_COL = np.array([[0.93, 0.76, 0.62], [0.55, 0.25, 0.08], [0.35, 0.55, 0.85], [0.15, 0.6, 0.2]])


def frame_of(model):
    c = np.array([0.0, model.C[1] - 0.035, model.C[2] + 0.01])
    return c, 0.175


def render_reference(cam, ref, sim, face_mask=None, face_rgb=None, shade=0.25):
    """Textured reference mesh in game space (via sim)."""
    V = sim(ref.V)
    F = ref.F if face_mask is None else ref.F[face_mask]
    fidx = np.arange(len(ref.F)) if face_mask is None else np.nonzero(face_mask)[0]
    P2, Z = cam.project(V)
    fid, bary, _ = rasterize(P2, Z, F, cam.size, cam.size)
    img = np.ones((cam.size, cam.size, 3))
    m = fid >= 0
    f = fidx[fid[m]]
    if face_rgb is not None:
        col = face_rgb[f]
    else:
        col = ref.colour(f, bary[m])
    n = sim.rot(ref.fn[f])
    lam = np.clip(n @ unit(cam.d * 0.8 + cam.up * 0.5 - cam.right * 0.3), 0, 1)
    img[m] = col * ((1 - shade) + shade * lam)[:, None]
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def render_head(cam, model, Pv, Nv, colour=None, vcolor=None):
    if vcolor is None:
        vcolor = np.tile(np.asarray(colour if colour is not None else [0.8, 0.8, 0.8]), (len(Pv), 1))
        vcolor[getattr(model, 'is_eye', np.zeros(len(Pv), bool))] = [0.9, 0.9, 0.88]
    T = model.Tv
    img, _ = raster.render_mesh(cam, Pv, T, vcolor=vcolor, vnormal=Nv)
    return img


NODATA = np.array([0.62, 0.70, 0.62])      # heat map: no skin data (hair, beard, clothing) - not white/grey


def hair_overlay_points(env):
    """Outer hair surface points of an envelope dict: C + dir * rho_outer per bin, plus the drape
    cylinder (outer radius per sector and slice)."""
    from headref import lonlat_dir
    C = np.asarray(env['C'])
    LO, LA = np.meshgrid(env['lon_deg'], env['lat_deg'])
    ro = env['rho_outer_m']
    m = np.isfinite(ro)
    P = [C + lonlat_dir(LO[m], LA[m]) * ro[m][:, None]]
    if 'drape_r_outer_m' in env:
        K = np.radians(env['drape_lon_deg']); Y = env['drape_y_m']
        R = env['drape_r_outer_m']
        KK, YY = np.meshgrid(K, Y)
        md = np.isfinite(R)
        P.append(np.stack([C[0] + R[md] * np.sin(KK[md]), YY[md], C[2] + R[md] * np.cos(KK[md])], 1))
    return np.concatenate(P) if P else np.zeros((0, 3))


def draw_points(img, cam, X, rgb, alpha=0.55, radius=2, zbuf=None):
    """Alpha-blend dots for points X (game space) into img (uint8), skipping dots hidden by zbuf."""
    if not len(X):
        return img
    P2, Z = cam.project(X)
    out = img.astype(np.float64) / 255.0
    H, W = img.shape[:2]
    col = np.asarray(rgb, np.float64)
    order = np.argsort(-Z)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            px = np.floor(P2[order, 0]).astype(int) + dx; py = np.floor(P2[order, 1]).astype(int) + dy
            ok = (px >= 0) & (px < W) & (py >= 0) & (py < H)
            if zbuf is not None:
                ok[ok] &= Z[order][ok] <= zbuf[py[ok], px[ok]] + 1e-4
            out[py[ok], px[ok]] = out[py[ok], px[ok]] * (1 - alpha) + col * alpha
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def label(img, text):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(text), 16], fill=(255, 255, 255))
    d.text((4, 2), text, fill=(20, 20, 20))
    return np.asarray(im)


def colourbar(img, lim_mm):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    H = img.shape[0]
    x0, y0, w, h = img.shape[1] - 28, 30, 12, 160
    for i in range(h):
        t = 1 - 2 * i / (h - 1)
        c = raster.diverging(np.array([t * lim_mm]), lim_mm)[0]
        d.line([x0, y0 + i, x0 + w, y0 + i], fill=tuple(int(255 * x) for x in c))
    d.text((x0 - 34, y0 - 12), f'+{lim_mm:.0f}mm', fill=(30, 30, 30))
    d.text((x0 - 34, y0 + h + 2), f'-{lim_mm:.0f}mm', fill=(30, 30, 30))
    d.text((4, H - 30), 'red: reference outside fitted skin', fill=(120, 20, 20))
    d.text((4, H - 16), 'blue: reference inside   green-grey: no skin data', fill=(20, 40, 120))
    return np.asarray(im)


def write_previews(out_dir, model, ref, sim, Pv, Nv, vres, vres_ok, skin_rgb, ref_face_mask, seg_face_rgb=None,
                   size=512, lim_mm=4.0, hair_env=None, hair_rgb=None):
    """vres: per RL vertex signed residual (mm, + = reference outside), vres_ok: where it is defined.
    hair_env: envelope dict; its outer surface (and drape) is drawn over the fitted head as dots."""
    c, half = frame_of(model)
    files = {}
    heat = raster.diverging(np.nan_to_num(vres), lim_mm)
    heat[~vres_ok] = NODATA
    hp = hair_overlay_points(hair_env) if hair_env is not None else np.zeros((0, 3))
    hcol = np.clip(np.asarray(hair_rgb if hair_rgb is not None else [0.35, 0.2, 0.1]) * 0.9, 0, 1)
    for view in ('front', 'profile', 'three_quarter'):
        cam = view_camera(view, c, half, size)
        a = render_reference(cam, ref, sim, ref_face_mask)
        b = render_head(cam, model, Pv, Nv, colour=np.clip(np.asarray(skin_rgb) * 1.05, 0, 1))
        if len(hp):
            P2, Z = cam.project(Pv)
            _, _, zb = rasterize(P2, Z, model.Tv, cam.size, cam.size)
            b = draw_points(b, cam, hp, hcol, alpha=0.6, radius=2, zbuf=zb)
        h = render_head(cam, model, Pv, Nv, vcolor=heat)
        a = label(a, 'reference'); b = label(b, 'fitted RL head + hair envelope' if len(hp) else 'fitted RL head')
        h = colourbar(label(h, 'residual'), lim_mm)
        img = np.concatenate([a, b, h], 1)
        p = os.path.join(out_dir, f'{view}.png')
        Image.fromarray(img).save(p)
        files[view] = p
    if seg_face_rgb is not None:
        ims = []
        for view in ('front', 'profile', 'three_quarter'):
            cam = view_camera(view, c, half, size // 2 * 2)
            ims.append(render_reference(cam, ref, sim, ref_face_mask, face_rgb=seg_face_rgb, shade=0.45))
        img = label(np.concatenate(ims, 1), 'segmentation: skin / hair (brown) / beard (green) / other (blue)')
        p = os.path.join(out_dir, 'segmentation.png')
        Image.fromarray(img).save(p)
        files['segmentation'] = p
    return files
