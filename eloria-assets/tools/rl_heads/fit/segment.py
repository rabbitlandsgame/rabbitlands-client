"""Skin / hair / other (+ beard) classification of reference points.

Colour: one robust Gaussian per class in a lighting-tolerant Lab space
(L* down-weighted, since baked lighting mostly moves luminance), seeded from
the registered RL head: skin from the nose and upper cheeks (close to the RL
skin, normal-compatible), hair from the crown (well outside the RL cranium),
other from the body below the RL neck rim when it is neither skin- nor
hair-coloured.

Geometry (log prior per class): signed distance to the registered RL skin
(+ outside), the RL region of the nearest skin point, and whether the point
lies past the RL neck rim. Hair needs to stand off the skin, more so on the
face; points far from the head are other.

The per-point posteriors are smoothed over the surface (k nearest neighbours,
a few passes), then arg-maxed. Beard = hair over the RL beard region (upper
lip, chin, jaw, lower cheeks, front neck) close to the face.
"""
import numpy as np
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from fitcommon import kdq, srgb_to_lab, srgb_to_linear, unit, log
from rlmodel import REGIONS
from headref import dir_lonlat

SKIN, HAIR, OTHER, BEARD = 0, 1, 2, 3
LABEL_NAMES = {SKIN: 'skin', HAIR: 'hair', OTHER: 'other', BEARD: 'beard'}
FEAT_W = np.array([0.45, 1.0, 1.0])       # L*, a*, b* weights


def feats(C):
    return srgb_to_lab(C) * FEAT_W


class Gauss:
    def __init__(self, F, trim=0.85, reg=6.0):
        mu = np.median(F, 0)
        cov = np.cov((F - mu).T) + np.eye(3) * reg
        for _ in range(3):
            d = self._md(F, mu, cov)
            keep = d <= np.quantile(d, trim)
            mu = F[keep].mean(0)
            cov = np.cov(F[keep].T) + np.eye(3) * reg
        self.mu, self.cov = mu, cov
        self.icov = np.linalg.inv(cov)
        self.logdet = float(np.linalg.slogdet(cov)[1])
        self.n = len(F)

    @staticmethod
    def _md(F, mu, cov):
        D = F - mu
        return np.einsum('ij,jk,ik->i', D, np.linalg.inv(cov), D)

    def md(self, F):
        D = F - self.mu
        return np.einsum('ij,jk,ik->i', D, self.icov, D)

    def loglik(self, F):
        # Student-t like tail (robust to texture detail / lighting): -0.5*(nu+3)*log(1+md/nu)
        nu = 4.0
        return -0.5 * (nu + 3) * np.log1p(self.md(F) / nu) - 0.5 * self.logdet


def radial_excess(model, Pv, X, step=4.0):
    """|X - C| minus the outermost RL skin radius in X's direction from the cranium centre C
    (negative = inside the head; NaN where the ray misses the skin, e.g. below the neck rim)."""
    import envelope
    lon = np.arange(-180.0, 180.0, step) + step / 2
    lat = np.arange(-90.0, 90.0, step) + step / 2
    rho = envelope.skin_radius(Pv, model.Tv, model.C, lon, lat)
    lo, la = dir_lonlat(X - model.C)
    i = np.floor((lo + 180.0) / step).astype(int) % len(lon)
    j = np.clip(np.floor((la + 90.0) / step).astype(int), 0, len(lat) - 1)
    return np.linalg.norm(X - model.C, axis=1) - rho[j, i]


def geometry(cloud_Xg, cloud_Ng, model, surf):
    """Per-point geometry relative to the (morphed) RL skin."""
    pr = model.project(surf, cloud_Xg, max_dist=0.3)
    ok = pr['ok']
    reg = np.full(len(cloud_Xg), -1)
    reg[ok] = model.region_at({k: v[ok] for k, v in pr.items() if isinstance(v, np.ndarray)})
    rimw = (model.rim[pr['tv']] * pr['bary']).sum(1)
    past_rim = ok & (pr['off'] > 0.002) & (rimw > 0.3) & (cloud_Xg[:, 1] < pr['p'][:, 1] + 0.002)
    past_rim |= cloud_Xg[:, 1] < model.h.P[model.h.rim, 1].min() - 0.01
    cosn = (cloud_Ng * pr['n']).sum(1)
    beard = np.zeros(len(cloud_Xg), bool)
    k = np.argmax(pr['bary'], 1)
    vnear = pr['tv'][np.arange(len(k)), k]
    beard = model.beard_region[vnear] & ok
    lon, lat = dir_lonlat(cloud_Xg - model.C)
    rex = radial_excess(model, surf.P, cloud_Xg)
    return {'rex': rex, 'pr': pr, 'ok': ok, 'd': np.where(ok, pr['d'], np.inf), 'dist': np.where(ok, pr['dist'], np.inf),
            'reg': reg, 'past_rim': past_rim, 'cos': cosn, 'beard_reg': beard, 'vnear': vnear, 'lon': lon, 'lat': lat}


def chromaticity(C):
    """Linear-RGB chromaticity (r, g) = (R, G) / (R + G + B): unchanged by a (grey) shading factor, so
    shadowed skin keeps the chromaticity of lit skin while hair/beard pigment usually differs."""
    L = srgb_to_linear(C)
    return L[:, :2] / np.maximum(L.sum(1, keepdims=True), 0.02)


def components_kept(X, mask, seeds, zone, link_r, k=8):
    """Connected components (k nearest neighbours closer than link_r) of the points in mask. A component
    is kept when it contains a seed point or when at least half of its points lie in `zone`.
    Returns the kept mask and the component stats."""
    idx = np.nonzero(mask)[0]
    keep = np.zeros(len(X), bool)
    if len(idx) == 0:
        # no hair-labelled point at all (bald, clean-shaven reference): a valid outcome, same keys
        return keep, {'components': 0, 'kept': 0, 'dropped_points': 0, 'in_seeded': np.zeros(len(X), bool)}
    kk = min(k + 1, len(idx))
    d, j = kdq(cKDTree(X[idx]), X[idx], k=kk, distance_upper_bound=link_r)
    rows = np.repeat(np.arange(len(idx)), kk)
    cols = j.ravel()
    ok = np.isfinite(d.ravel()) & (cols < len(idx))
    G = coo_matrix((np.ones(int(ok.sum())), (rows[ok], cols[ok])), shape=(len(idx), len(idx)))
    nc, comp = connected_components(G, directed=False)
    seeded = np.zeros(nc, bool)
    seeded[comp[seeds[idx]]] = True
    cnt = np.bincount(comp, minlength=nc)
    zf = np.bincount(comp, weights=zone[idx].astype(float), minlength=nc) / np.maximum(cnt, 1)
    kc = seeded | (zf >= 0.5)
    keep[idx] = kc[comp]
    in_seeded = np.zeros(len(X), bool)
    in_seeded[idx] = seeded[comp]
    return keep, {'components': int(nc), 'kept': int(kc.sum()), 'dropped_points': int((~kc[comp]).sum()),
                  'in_seeded': in_seeded}


def occluded_along_normal(X, N, kd, sel, r, reach=0.015):
    """True for the points in sel whose outward normal ray (from r + 1 mm to `reach`) passes within r
    of another reference point: surfaces facing into a cavity (fused mouth / nostril / lip-seam
    interiors, skin behind an ear, skin under an overhanging fringe). Never true for open skin."""
    idx = np.nonzero(sel)[0]
    out = np.zeros(len(X), bool)
    if not len(idx):
        return out
    hit = np.zeros(len(idx), bool)
    h = r + 0.001
    while h <= reach:
        q = X[idx] + N[idx] * h
        d, _ = kdq(kd, q, k=1, distance_upper_bound=r)
        hit |= np.isfinite(d)
        h += r
    out[idx] = hit
    return out


def classify(cloud, Xg, Ng, model, surf, smooth_iters=3, k=10, log_fn=log, final=False, link_r=0.004, occ_r=0.0015):
    """final=True: the skin is the fitted one (distances are trustworthy), so a beard lying on the
    skin can be called stubble. link_r: neighbour distance (game m) linking hair points into connected
    pieces; occ_r: probe radius of the cavity/occlusion test (about 1.5 x the point spacing)."""
    G = geometry(Xg, Ng, model, surf)
    F = feats(cloud.C)
    d = G['d']; reg = G['reg']
    R = {r: REGIONS.index(r) for r in REGIONS}
    ny = model.lm['nose_tip'][1]
    face_core = np.isin(reg, [R['nose'], R['eyes'], R['mouth']]) | ((reg == R['cheeks']) & (Xg[:, 1] > ny - 0.005))
    head = ~G['past_rim'] & (G['dist'] < 0.08)
    info = {}
    # --- seeds
    skin_seed = head & (np.abs(d) < 0.003) & (G['cos'] > 0.7) & (G['pr']['off'] < 0.001) & \
        (np.isin(reg, [R['nose']]) | ((reg == R['cheeks']) & (Xg[:, 1] > ny - 0.008)) | (reg == R['forehead']))
    if skin_seed.sum() < 150:
        skin_seed = head & (np.abs(d) < 0.004) & np.isin(reg, [R[r] for r in ('nose', 'cheeks', 'forehead', 'brow')])
    gs = Gauss(F[skin_seed]) if skin_seed.sum() >= 30 else Gauss(F[head & (np.abs(d) < 0.006)])
    crown = (G['lat'] > 25) & (reg == R['cranium'])
    md_skin = gs.md(F)
    hair_seed = head & (d > 0.006) & (crown | ((reg == R['cranium']) & (d > 0.012)))
    # reject seed points that look exactly like skin (e.g. a bald scalp bump)
    hair_seed &= md_skin > 9.0
    src = 'crown'
    if hair_seed.sum() < 80:
        # registration may still be off (hair pulled the scale): crown points clearly not skin-coloured
        alt = head & crown & (d > -0.004) & (md_skin > 25.0)
        if alt.sum() >= 200:
            hair_seed = alt; src = 'crown colour'
    # beard seed: off the skin over the jaw/chin/upper lip and not skin-coloured (also for bald heads).
    # Baked shading (the shadowed underside of the jaw, a darker neck) changes luminance, not the linear
    # chromaticity, so a seed must differ from the skin in chromaticity or be far darker than shading
    # makes skin; downward-facing surfaces (under the jaw, mostly shadow) never seed.
    chrom = chromaticity(cloud.C)
    ch_skin = np.median(chrom[skin_seed], 0) if skin_seed.sum() >= 30 else np.median(chrom[head & (np.abs(d) < 0.006)], 0)
    dch = np.linalg.norm(chrom - ch_skin, axis=1)
    L_all = F[:, 0] / FEAT_W[0]
    L_skin = float(np.median(L_all[skin_seed])) if skin_seed.sum() >= 30 else float(np.median(L_all))
    pigment = (dch > 0.03) | (L_all < L_skin - 38.0)
    beard_seed = head & G['beard_reg'] & (d > 0.0025) & (md_skin > 16.0) & (np.abs(G['lon']) < 100) &         (Ng[:, 1] > -0.4) & pigment
    info['skin_chromaticity'] = [round(float(x), 4) for x in ch_skin]
    has_hair = hair_seed.sum() >= 80
    has_beard_seed = beard_seed.sum() >= 80
    ghs = []
    if has_hair:
        ghs.append(Gauss(F[hair_seed]))
    if has_beard_seed:
        gb = Gauss(F[beard_seed])
        if not ghs or ghs[0].md(gb.mu[None])[0] > 9.0:
            ghs.append(gb)
    gh = ghs[0] if ghs else None
    info['hair_seed_source'] = src if has_hair else None
    below = G['past_rim'] & (Xg[:, 1] < model.h.P[model.h.rim, 1].min() - 0.03)
    other_seed = below & (gs.md(F) > 16)
    if gh is not None:
        other_seed &= gh.md(F) > 16
    go = Gauss(F[other_seed]) if other_seed.sum() >= 80 else None
    info['seeds'] = {'skin': int(skin_seed.sum()), 'hair': int(hair_seed.sum()), 'beard': int(beard_seed.sum()),
                     'other': int(other_seed.sum())}
    # --- log likelihoods
    n = len(F)
    L = np.full((n, 3), -1e3)
    L[:, SKIN] = gs.loglik(F)
    if ghs:
        L[:, HAIR] = np.max(np.stack([g_.loglik(F) for g_ in ghs]), 0)
    if go is not None:
        L[:, OTHER] = go.loglik(F)
    else:
        L[:, OTHER] = np.maximum(L[:, SKIN], L[:, HAIR]) - 6.0      # flat: only geometry can make 'other'
    # --- geometric priors (nats); distances in mm
    dm = np.clip(d * 1000, -200, 200)
    g = np.zeros((n, 3))
    g[:, SKIN] = -np.maximum(0, dm - 2.5) / 2.0 - np.maximum(0, -dm - 6.0) / 3.0
    hair_need = np.where(face_core, 5.0, 3.0)
    g[:, HAIR] = -np.maximum(0, hair_need - dm) / np.where(face_core, 0.8, 1.6)
    g[:, OTHER] = -4.0
    far = G['dist'] > 0.06
    g[far, OTHER] += 3.0
    g[far, SKIN] -= 3.0
    pr = G['past_rim']
    rim_lo = float(model.h.P[model.h.rim, 1].min())
    g[pr, SKIN] = -1.0
    # hair hanging past the neck rim is allowed (long hair) but becomes less likely the further down it
    # is (clothing / dark texture creases on the torso); connectivity to the scalp hair decides below
    g[pr, HAIR] = -np.maximum(0.0, rim_lo - 0.04 - Xg[pr, 1]) / 0.08
    g[pr, OTHER] = 0.0
    if gh is None:
        g[:, HAIR] = -1e3
    elif not has_hair:
        # only a beard was seeded: hair-coloured points are beard candidates near the face only
        g[~G['beard_reg'] | (d > 0.045), HAIR] -= 6.0
    lp = L + g
    lp -= lp.max(1, keepdims=True)
    p = np.exp(lp); p /= p.sum(1, keepdims=True)
    # --- smoothing on the surface
    kd = cKDTree(Xg)
    _, nb = kdq(kd, Xg, k=k)
    for _ in range(smooth_iters):
        p = 0.5 * p + 0.5 * p[nb].mean(1)
    lab = np.argmax(p, 1)
    # inside the RL head along the ray from its centre: interior geometry (never the outer hair or skin)
    interior = (G['rex'] < -0.004) & ~G['past_rim'] & (d > 0.003)
    lab[interior] = OTHER
    info['interior_points'] = int(interior.sum())
    # painted features lying on the face skin (brows, lashes, stubble lines) are skin geometry, not hair
    painted = (lab == HAIR) & (np.abs(d) < 0.0025) & np.isin(reg, [R['brow'], R['eyes'], R['nose'], R['cheeks'], R['mouth']]) &         ~G['beard_reg']
    lab[painted] = SKIN
    info['painted_features'] = int(painted.sum())
    # below the ears, hair-labelled geometry standing well off the skin must have the scalp hair's colour:
    # a dark collar or scarf can win the hair likelihood through the beard-seeded colour model, long
    # hair cannot differ from the crown (measured: hair below the rim md 1-9 to the crown model, a dark
    # collar 31-64)
    if has_hair:
        md_crown = ghs[0].md(F)
        offc = (lab == HAIR) & (md_crown > 16.0) & (d > 0.015) & (Xg[:, 1] < model.ear_bottom_y)
        lab[offc] = OTHER
        info['hair_colour_rejected'] = int(offc.sum())
    # hair must be one piece with the scalp hair (or lie on the head, e.g. a beard on a bald head):
    # hair-coloured texture creases, clothing and the bust cut below the neck are not
    zone = head & ~((G['dist'] > 0.045) & (Xg[:, 1] < rim_lo))
    keep, cstat = components_kept(Xg, lab == HAIR, hair_seed, zone, link_r)
    drop = (lab == HAIR) & ~keep
    lab[drop] = OTHER
    # sculpted eyebrows: hair-coloured pieces on the brow / eyelids, not part of the scalp hair, close
    # to the skin - neither scalp hair (no envelope there) nor reliable skin shape
    in_seeded = cstat.pop('in_seeded', None)
    if in_seeded is None:
        in_seeded = np.zeros(len(Xg), bool)
    brows = (lab == HAIR) & ~in_seeded & np.isin(reg, [R['brow'], R['eyes']]) & (d < 0.006)
    lab[brows] = OTHER
    cstat['brow_points'] = int(brows.sum())
    info['hair_components'] = cstat
    # cavity / occluded surfaces are not skin evidence (mouth and nostril interiors, fused lip seams,
    # skin behind the ears or under a fringe)
    kd_all = cKDTree(Xg)
    occ = occluded_along_normal(Xg, Ng, kd_all, (lab == SKIN) & head, occ_r)
    lab[occ] = OTHER
    info['occluded_skin'] = int(occ.sum())
    # beard: hair close to the face over the RL beard region
    lon = G['lon']
    near_face = (d < 0.045) & (np.abs(lon) < 100) & ~(G['past_rim'] & (Xg[:, 1] < model.lm['chin'][1] - 0.06))
    beard = (lab == HAIR) & G['beard_reg'] & near_face
    lab = lab.copy()
    lab[beard] = BEARD
    hairy = np.isin(lab, [HAIR, BEARD]).astype(float)
    # a beard is a contiguous patch: among hair-like neighbours, beard must dominate
    for _ in range(2):
        fb = (lab == BEARD).astype(float)[nb].mean(1) / np.maximum(hairy[nb].mean(1), 1e-9)
        lab[(lab == BEARD) & (fb < 0.35)] = HAIR
    # grow the beard into adjacent hair that hugs the lower face/neck (edges of the beard region),
    # below the ear bottom and in front of the ears; scalp hair (sideburns above) stays hair
    low_front = (Xg[:, 1] < model.lm['nose_tip'][1] + 0.004) & (np.abs(lon) < 100) & (d < 0.03) & ~G['past_rim']
    # a beard also wraps the sides of the jaw/neck below the ears, hugging the skin (scalp hair hanging
    # there - long hair - stands off it); the growth runs until it stops (the dense head-zone sample
    # makes each step ~1 mm, so a fixed small number of steps stopped short)
    low_side = (Xg[:, 1] < model.ear_bottom_y + 0.004) & (np.abs(lon) < 120) & (d < 0.012) &         (~G['past_rim'] | (Xg[:, 1] > rim_lo - 0.03))
    low_front = low_front | low_side
    if (lab == BEARD).sum() > 50:
        for _ in range(40):
            cand = (lab == HAIR) & low_front
            if not cand.any():
                break
            fbn = (lab[nb] == BEARD).mean(1)
            grow = cand & (fbn >= 0.2)
            if not grow.any():
                break
            lab[grow] = BEARD
    # stubble: 'beard' that lies on the skin (painted, < 1.2 mm off) is skin geometry
    bm = lab == BEARD
    info['stubble'] = False
    if final and bm.sum() >= 50 and np.median(d[bm]) < 0.0009 and np.percentile(d[bm], 80) < 0.0016:
        lab[bm] = SKIN
        info['stubble'] = True
    info['counts'] = {LABEL_NAMES[c]: int((lab == c).sum()) for c in LABEL_NAMES}
    info['has_hair_seed'] = bool(has_hair)
    info['colour_models'] = {'skin_lab': (gs.mu / FEAT_W).round(2).tolist(),
                             'hair_lab': None if gh is None else (gh.mu / FEAT_W).round(2).tolist(),
                             'other_lab': None if go is None else (go.mu / FEAT_W).round(2).tolist()}
    info['skin_confidence'] = p[:, SKIN]
    info['hair_gauss'] = ghs
    info['skin_gauss'] = gs
    return lab, p, G, info
