"""Build an RL beard / moustache module GLB from a definition.

    python build_beard.py <beard.json> <sex> <out.glb> [--chart out.png] [--no-check] [--embed-textures]

Output contract (agreed with the runtime):
  * skinned like the head: joints [spine_03, neck_01, Head] with the body's inverse
    binds (the head module's skeleton chain BodyRoot..Head is copied verbatim)
  * meshes beard_lod0 / beard_lod1 / beard_lod2, material rl_beard
    (alpha-tested strand cards + a short "mass" shell), UV v root(0)->tip(1) on
    cards, COLOR_0 = (lock random, position along the hair, ao, 1)
  * morph targets: ALL head shapes (id_* and ex_*) transferred by surface binding
    (beard hairs follow jaw_open, smile, ...); target names in mesh extras
  * asset.extras.rlBeard = {style, tris, region, ...}

BEARD FRAME. Regions are authored in (lon, lat) degrees seen from a point behind
the mouth: B = (0, lip-centre y + 8 mm, Head-joint z - 42 mm). lon 0 = the
midline of the face, |lon| grows toward the ears (regions are mirrored, so give
lon >= 0 only); lat 0 ~ mouth level, + up (subnasale ~ +6), - down (chin front
~ -18, under the chin ~ -45, throat ~ -60). `--chart` writes a picture of the
skin in this frame with the region, lips and landmarks to author against.

DEFINITION KEYS (see beards/*.json for commented examples):
  region.top / region.bottom : [[lon, lat], ...] upper / lower boundary as a
      function of |lon| (linear, clamped); region.lon_max; region.mouth_mm =
      clearance kept round the lips group (mouth_soft_mm: its fade width);
      region.soft_deg = edge softness
      (the mass thins to edge_mm and cards get shorter/sparser toward edges).
  mass   : shell offset thickness_mm (interior) / edge_mm, bulges
           [{"at": [lon, lat], "deg": r, "mm": extra}], strip_mm = UV strip width,
           fade_deg = width of the soft (alpha-thinned) band at the cheek / neck lines
  keep_out [{"at": [lon, lat], "deg": r}] : bands no card may enter (truncated at the
           first point inside, dropped if less than half remains), e.g. the mouth
           corners, so open-mouth / smile expressions never fold skin over them
  shade  : ao_shell [lo, hi] (COLOR_0.B on the mass, top -> bottom), ao_card_floor,
           v_start (cards start past the root-darkening ramp: v and COLOR_0.G =
           v_start + (1 - v_start) * t) -- short beards should be as light as the hair
  morph  : follow_mm / fade_mm defaults, lip_follow_mm [full, fade]: vertices within
           `full` mm of the lips (+ fade) follow their own bound skin fully;
           mouth_line [[lon, lat], ...]: hair is bound only to skin on its root's side
           of this line (card groups: mouth_side upper|lower|auto, default upper for
           groups named *moustache*; mass.mouth_side for the shell)
  cards  : list of card groups: count, region (optional own top/bottom/lon_max),
           length [min, max] (m) or length_table by lat, width (m), lift (deg off
           the skin), flow (hairgen flow spec), gravity, col (atlas columns 0..2),
           follow_mm/fade_mm (morph follow, small = rigid with the root),
           lod {"1": {"keep": f}, "2": {...}}
"""
import os, sys, json, math, time, argparse
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rlglb  # noqa: E402
import headref, hairgen, assemble  # noqa: E402
from headref import unit, dir_lonlat  # noqa: E402
from hairgen import MeshPart  # noqa: E402

import paths  # noqa: E402
TEX = os.path.join(paths.BEARD_TEX, 'beard.png')
NCOLS = 4
SHELL_COL = 3
SHELL_PERIOD, SHELL_MARGIN, COL_PX = 192, 32, 256
LODS = (0, 1, 2)


def beard_center(head):
    lips = head.P[head.vgroups['lips']]
    return np.array([0.0, lips[:, 1].mean() + 0.008, head.head_joint[2] - 0.042])


def frame_lonlat(B, P):
    lon, lat = dir_lonlat(P - B)
    return lon, lat


def boundary_fn(pts):
    a = np.array(pts, np.float64)
    o = np.argsort(a[:, 0])
    return lambda x: np.interp(np.abs(x), a[o, 0], a[o, 1])


class Region:
    """Beard region on the head skin in the beard frame + soft edge weight."""

    def __init__(self, head, B, spec):
        self.head = head; self.B = B
        self.top = boundary_fn(spec['top']); self.bot = boundary_fn(spec['bottom'])
        self.lon_max = spec.get('lon_max', 120.0)
        self.soft = spec.get('soft_deg', 4.0)
        lips = head.P[head.vgroups['lips']]
        from scipy.spatial import cKDTree
        self.lips_tree = cKDTree(lips)
        self.mouth = spec.get('mouth_mm', 3.0) * 1e-3
        self.mouth_soft = spec.get('mouth_soft_mm', 1.5) * 1e-3
        self.exclude = spec.get('exclude', [])

    def weight(self, P):
        """0 outside, rising to 1 a `soft_deg` inside the boundary."""
        lon, lat = frame_lonlat(self.B, P)
        alon = np.abs(lon)
        d_top = self.top(alon) - lat
        d_bot = lat - self.bot(alon)
        d_side = self.lon_max - alon
        d = np.minimum(np.minimum(d_top, d_bot), d_side)
        dl, _ = self.lips_tree.query(P)
        dm = (dl - self.mouth) / max(self.mouth_soft, 1e-4) * self.soft   # past the mouth margin, in soft units
        d = np.minimum(d, dm)
        for ex in self.exclude:
            c = np.radians(ex['at'])
            dd = np.degrees(np.arccos(np.clip(
                np.cos(np.radians(lat)) * np.cos(c[1]) * np.cos(np.radians(alon) - c[0]) + np.sin(np.radians(lat)) * np.sin(c[1]), -1, 1)))
            d = np.minimum(d, dd - ex['deg'])
        w = hairgen.smoothstep(d / max(self.soft, 1e-3))
        w[self.head.vgroups['ears'][:len(w)] if len(w) == len(self.head.P) else np.zeros(len(w), bool)] = 0
        return w, lon, lat


# ===================================================================== mass shell
def mass_shell(head, region, spec, Psk, Tsk, Nsk):
    """Offset shell over the region triangles of a skin mesh (any head LOD)."""
    w, lon, lat = region.weight(Psk)
    keep = (w[Tsk] > 0.02).all(1)
    T = Tsk[keep]
    if not len(T):
        return None
    used = np.unique(T)
    remap = -np.ones(len(Psk), np.int64); remap[used] = np.arange(len(used))
    T = remap[T]; P0 = Psk[used]; N0 = Nsk[used]; w = w[used]; lon = lon[used]; lat = lat[used]
    th_in = spec.get('thickness_mm', 6.0) * 1e-3; th_edge = spec.get('edge_mm', 2.4) * 1e-3
    th = th_edge + (th_in - th_edge) * w
    for bg in spec.get('bulges', []):
        c = np.radians(bg['at'])
        dd = np.degrees(np.arccos(np.clip(np.cos(np.radians(lat)) * np.cos(c[1]) * np.cos(np.radians(np.abs(lon)) - c[0])
                                          + np.sin(np.radians(lat)) * np.sin(c[1]), -1, 1)))
        th = th + bg['mm'] * 1e-3 * w * (1 - hairgen.smoothstep(dd / bg['deg']))
    P = P0 + N0 * th[:, None]
    # smooth the offset surface a little (thickness changes make ridges)
    adj = assemble.adjacency(T, len(P))
    for _ in range(spec.get('smooth', 2)):
        avg = (adj[0] @ P) / adj[1][:, None]
        P = P + 0.5 * (avg - P) * (w[:, None] > 0.1)
    # UVs: v from the top boundary (0) to the bottom (1); u in periodic strips of
    # strip_mm in the shell column (see textures.py), duplicated vertices per strip
    alon = np.abs(lon)
    # v: the first fade_deg below the top boundary (cheek line, ~1 cm) maps onto the
    # texture's 12% top fade band, the last fade_deg above the bottom onto its 8%
    # bottom band; the interior spreads linearly in between (see textures.py)
    fd = spec.get('fade_deg', 6.0)
    dtop = np.maximum(region.top(alon) - lat, 0); dbot = np.maximum(lat - region.bot(alon), 0)
    span = np.maximum(dtop + dbot, 1e-3)
    f_t = np.minimum(fd, span * 0.4); f_b = np.minimum(fd, span * 0.3)
    mid = np.clip((dtop - f_t) / np.maximum(span - f_t - f_b, 1e-3), 0, 1)
    v = np.where(dtop < f_t, 0.12 * dtop / np.maximum(f_t, 1e-3),
                 np.where(dbot < f_b, 1 - 0.08 * dbot / np.maximum(f_b, 1e-3), 0.12 + 0.8 * mid))
    strip = spec.get('strip_mm', 28.0) * 1e-3
    uw = np.radians(lon) * 0.075 / strip                  # world u in strip units (signed lon)
    tri_strip = np.floor(uw[T].mean(1)).astype(np.int64)
    Pn, Nn, UVn, Tn, tn, vid = [], [], [], [], [], []
    for k in np.unique(tri_strip):
        tt = T[tri_strip == k]
        vs = np.unique(tt)
        rm = -np.ones(len(P), np.int64); rm[vs] = np.arange(len(vs)) + sum(len(x) for x in Pn)
        local = (uw[vs] - k)                             # ~[0, 1] (+ overhang)
        u = (SHELL_COL * COL_PX + SHELL_MARGIN + local * SHELL_PERIOD) / (NCOLS * COL_PX)
        u = np.clip(u, (SHELL_COL * COL_PX + 2) / (NCOLS * COL_PX), ((SHELL_COL + 1) * COL_PX - 2) / (NCOLS * COL_PX))
        Pn.append(P[vs]); UVn.append(np.stack([u, v[vs]], 1)); Tn.append(rm[tt]); tn.append(v[vs]); vid.append(vs)
    Pn = np.concatenate(Pn); UVn = np.concatenate(UVn); Tn = np.concatenate(Tn); tn = np.concatenate(tn); vid = np.concatenate(vid)
    Nn = headref.vertex_normals(Pn, Tn, vid)
    return Pn, Nn, UVn, Tn, tn


# ===================================================================== cards
def sample_region(head, region, count, rng, sub=None):
    """Area-weighted blue-noise root points on the head skin inside the region."""
    w, lon, lat = region.weight(head.P)
    if sub is not None:
        w2, _, _ = sub.weight(head.P); w = np.minimum(w, w2)
    T = head.T
    wt = w[T].mean(1)
    A = np.linalg.norm(np.cross(head.P[T[:, 1]] - head.P[T[:, 0]], head.P[T[:, 2]] - head.P[T[:, 0]]), axis=1) / 2
    pdf = A * (wt > 0.3) * wt
    if pdf.sum() <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0)
    pdf = pdf / pdf.sum()
    out = []
    for _ in range(count):
        cand_t = rng.choice(len(T), size=10, p=pdf)
        r1 = np.sqrt(rng.random(10)); r2 = rng.random(10)
        bc = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], 1)
        X = (head.P[T[cand_t]] * bc[:, :, None]).sum(1)
        if out:
            E = np.array(out)
            dmin = np.linalg.norm(X[:, None] - E[None], axis=2).min(1)
            X = X[np.argmax(dmin)]
        else:
            X = X[0]
        out.append(X)
    X = np.array(out)
    cp, _, tri, bc = head.closest(X)
    n = unit((head.N[head.T[tri]] * bc[:, :, None]).sum(1))
    ww, _, lat = region.weight(cp)
    return cp, n, ww


class SubRegion(Region):
    pass


# ===================================================================== build
def build(spec_path, sex, out_path, chart=None, check=True, embed=False, surface=None):
    t0 = time.time()
    spec = json.load(open(spec_path))
    head = headref.Head(sex)
    B = beard_center(head)
    region = Region(head, B, spec['region'])
    seed = spec.get('seed', 1)
    scalp = hairgen.Scalp(head, {})
    if chart:
        write_chart(head, B, region, chart)

    # ---------------- head LOD skins for the mass shell
    g, b = head.gltf, head.blob
    skins = {}
    names = [m.get('name') for m in g['meshes']]
    for lod in LODS:
        nm = f'rl_head_lod{lod}'
        if nm in names:
            pr = g['meshes'][names.index(nm)]['primitives'][0]
            Pl = rlglb.accessor(g, b, pr['attributes']['POSITION'])
            Tl = rlglb.accessor(g, b, pr['indices'], normalize=False).astype(np.int64).reshape(-1, 3)
        else:
            Pl, Tl = head.P, head.T
        q = np.round(Pl / 1e-6).astype(np.int64)
        _, weld = np.unique(q, axis=0, return_inverse=True)
        skins[lod] = (Pl, Tl, headref.vertex_normals(Pl, Tl, weld.ravel()))

    # ---------------- card groups -> locks
    locks = []
    card_groups = []
    for gi, cg in enumerate(spec.get('cards', [])):
        rng = hairgen.rng_for(seed, cg['name'])
        sub = None
        if 'region' in cg:
            rs = dict(spec['region']); rs.update(cg['region'])
            sub = Region(head, B, rs)
        X, n, ww = sample_region(head, region, int(cg['count']), rng, sub)
        if not len(X):
            continue
        if 'length_table' in cg:
            _, lat = frame_lonlat(B, X)
            lt = cg['length_table']
            L = np.interp(lat, *np.array(lt['points']).T) * rng.uniform(0.85, 1.15, len(X))
        else:
            L = rng.uniform(*cg.get('length', [0.012, 0.02]), len(X))
        L = L * (0.55 + 0.45 * ww)                       # shorter toward the region edge
        flow = hairgen.make_flow(cg.get('flow', {'type': 'down'}), scalp)
        params = {'hug': 0.0, 'lift': cg.get('lift', 20), 'gravity': cg.get('gravity', 0.5),
                  'stiffness': cg.get('stiffness', 0.6), 'jitter': cg.get('jitter', 12), 'steps': cg.get('steps', 6),
                  'height_mm': [cg.get('root_mm', 2.0), cg.get('root_mm', 2.0)], 'min_mm': cg.get('min_mm', 2.6)}
        curves = hairgen.grow(scalp, X, n, L, params, rng, flow)
        glocks = []
        keep_out = spec.get('keep_out', [])
        for i, C in enumerate(curves):
            C = hairgen.shape_curve(C, cg.get('shape', {}), rng, B)
            C = head.push_out(C, 0.0028, iters=2)
            if keep_out:
                # cards must not reach into keep-out bands (mouth corners): truncate, or drop
                clon, clat = frame_lonlat(B, C)
                inside = np.zeros(len(C), bool)
                for ko in keep_out:
                    inside |= np.hypot(np.abs(clon) - ko['at'][0], clat - ko['at'][1]) < ko['deg']
                if inside.any():
                    j = int(np.argmax(inside))
                    if j < spec.get('keep_out_min', 0.5) * len(C):
                        continue
                    C = hairgen.resample(C[:j], len(C))
            sec = {'width': cg.get('width', 0.008) * rng.uniform(0.8, 1.2), 'segs': cg.get('segs', 3)}
            lk = hairgen.Lock(C, 'card', sec, rng.random(), X[i], B, cg['name'], col=int(rng.choice(cg.get('col', [0, 1]))))
            glocks.append(lk)
        mids = np.array([lk.pts[len(lk.pts) // 2] for lk in glocks])
        for rank, i in enumerate(hairgen.farthest_order(mids)):
            glocks[i].order = rank
        for lk in glocks:
            lk.idx = len(locks); locks.append(lk)
        card_groups.append((cg, glocks))

    # ---------------- meshes per LOD
    ms = spec.get('mass', {})
    shade = spec.get('shade', {})
    lod_data = {}
    for lod in LODS:
        part = MeshPart()
        if ms.get('enabled', True):
            Pl, Tl, Nl = skins[lod]
            res = mass_shell(head, region, ms, Pl, Tl, Nl)
            if res is not None:
                P, N, UV, T, t = res
                part.add(P, N, UV, T, t, 0.5, -1)
        for cg, glocks in card_groups:
            ls = cg.get('lod', {})
            if (ls.get(str(lod)) or {}).get('drop'):
                continue
            for lk in hairgen.lock_lod_keep(glocks, lod, ls):
                r = ls.get(str(lod)) or {}
                n = max(2, int(round(lk.sec['segs'] * r.get('segs', 1.0)))) + 1
                C = hairgen.resample(lk.pts, n)
                tt = np.linspace(0, 1, n)
                wdt = hairgen.width_profile(tt, lk.sec['width'] * r.get('width_mul', 1.0), root=0.9, tip_start=0.6, tip_pow=0.7, tip_min=0.3)
                P, N, UV, T, t = hairgen.card_mesh(C, C - B, wdt, lk.col, ncols=NCOLS, inset=0.006)
                # short beards: start past the runtime's root-darkening ramp (v and COLOR_0.G)
                vs = shade.get('v_start', 0.0)
                if vs:
                    UV = UV.copy(); UV[:, 1] = vs + (1 - vs) * UV[:, 1]; t = vs + (1 - vs) * t
                part.add(P, N, UV, T, t, lk.rand, lk.idx)
        lod_data[lod] = part.arrays()
        if lod_data[lod] is None and lod > 0:
            # nothing survived this LOD's rules (tiny regions): reuse the previous LOD
            lod_data[lod] = lod_data[lod - 1]

    if surface:
        from pathlib import Path
        for lod in LODS:
            source=np.load(Path(surface)/f'lod{lod}.npz');count=len(source['P'])
            lod_data[lod]={k:source[k] for k in ('P','N','UV','T')}
            lod_data[lod].update(t=np.full(count,.65),rand=np.full(count,.5),lock=np.full(count,-1,dtype=int))
    # ---------------- output
    names_all = list(head.target_names)
    W = assemble.Writer('RL beard build (scripts/hair/build_beard.py)')
    col = spec.get('color', [0.12, 0.07, 0.04])
    texture=os.path.join(surface,'surface.png') if surface else TEX
    texture_name=spec['name']+'.png' if surface else 'beard.png'
    mat = W.material('rl_beard', col + [1.0], alpha='MASK', cutoff=0.4, double=True,
                     extras={'texture': texture_name, 'atlasColumns': NCOLS, 'shellColumn': SHELL_COL, 'tint': col,'referenceSurface':bool(surface)})
    if embed:
        W.embed_texture(mat, texture)
    report = {'style': spec.get('name'), 'sex': sex, 'lods': {}}
    if surface:report['source']=json.load(open(os.path.join(surface,'source.json')))
    clearance_rep = {}
    lock_root = np.array([lk.root for lk in locks]) if locks else np.zeros((0, 3))
    follow_of = {}
    side_of = {}
    for cg, glocks in card_groups:
        for lk in glocks:
            follow_of[lk.idx] = (cg.get('follow_mm', 8) * 1e-3, cg.get('fade_mm', 8) * 1e-3)
            side_of[lk.idx] = cg.get('mouth_side', 'upper' if 'moustache' in cg['name'] else 'auto')
    gm = spec.get('morph', {})
    mesh_ids = []
    for lod in LODS:
        d = lod_data[lod]
        extra = assemble.headroom(head, d['P'], [n for n in names_all if n.startswith('id_')], frac=gm.get('headroom', 0.35), cap=0.004)
        P = assemble.push_out_var(head, d['P'], 0.0026 + extra, iters=6)
        roots = np.where(d['lock'][:, None] >= 0, lock_root[np.maximum(d['lock'], 0)], P) if len(lock_root) else P.copy()
        # per-vertex follow distances: shell follows fully, card groups as configured
        fol = np.full(len(P), gm.get('follow_mm', 15) * 1e-3); fad = np.full(len(P), gm.get('fade_mm', 10) * 1e-3)
        for li, (f1, f2) in follow_of.items():
            sel = d['lock'] == li
            fol[sel] = f1; fad[sel] = f2
        bind = assemble.Binding(head, P, roots, fol, fad, T=d['T'], stretch=0.0, no_ears=False)
        # split binding at the mouth line: hair whose root is above it (moustache) binds
        # only to skin above it, chin hair only below -- an open mouth never drags a
        # moustache tip down with the lower lip, nor chin hair up with the upper lip
        # mouth line in the beard frame: the lip seam (~ lat -5) out to the corners, then
        # sloping down the cheeks (skin below it moves with the jaw)
        ml = np.array(gm.get('mouth_line', [[0, -5.0], [17, -5.0], [32, -22.0], [180, -22.0]]))
        mline = lambda lo: np.interp(np.abs(lo), ml[:, 0], ml[:, 1])
        rlon, rlat = frame_lonlat(B, roots)
        side = (rlat > mline(rlon)).astype(np.int64)
        # groups marked mouth_side "upper" (moustaches) always ride the upper lip
        for li, ms in side_of.items():
            if ms in ('upper', 'lower'):
                side[d['lock'] == li] = 1 if ms == 'upper' else 0
        ms = spec.get('mass', {}).get('mouth_side', 'auto')
        if ms in ('upper', 'lower'):
            side[d['lock'] < 0] = 1 if ms == 'upper' else 0
        tlon, tlat = frame_lonlat(B, head.P[head.T].mean(1))
        tri_side = (tlat > mline(tlon)).astype(np.int64)
        bind.v = head.bind_split(P, side, tri_side)
        bind.r = head.bind_split(roots, side, tri_side)
        bind.dist = bind.v['dist']; bind.n = head.bound_normal(bind.v)
        # beard near the lips follows the lip-region skin it is bound to (full follow,
        # linear in the shapes, so jaw_open / smile and their mixes stay consistent)
        dl, _ = region.lips_tree.query(P)
        ln = gm.get('lip_follow_mm', [6.0, 6.0])
        bind.force = 1.0 - hairgen.smoothstep((dl - ln[0] * 1e-3) / (ln[1] * 1e-3))
        ao = np.clip((bind.dist - 0.002) / 0.012, 0, 1) ** 0.7
        a0, a1 = shade.get('ao_shell', [0.45, 0.75])
        ao = np.where(d['lock'] < 0, a0 + (a1 - a0) * np.clip(d['t'], 0, 1), np.maximum(ao, shade.get('ao_card_floor', 0.3)))
        colr = assemble.colors_u8(d['rand'], np.clip(d['t'], 0, 1), ao)
        # skin weights: shell from its own binding, cards rigid with their root
        Wv = head.bound_weights(bind.v)
        Wr = head.bound_weights(bind.r)
        Wd = np.where((d['lock'] >= 0)[:, None], Wr, Wv)
        J4 = np.zeros((len(P), 4), np.uint16); J4[:, :3] = [0, 1, 2]
        W4 = np.zeros((len(P), 4), np.float32); W4[:, :3] = Wd / np.maximum(Wd.sum(1, keepdims=True), 1e-9)
        targets = []; hair_d = {}
        for nm in names_all:
            dP = bind.delta(head.delta(nm), keep_clear=True, margin=0.0026)
            if surface:
                delta=head.delta(nm)
                mesh=assemble.trimesh.Trimesh(head.P+delta,head.T,process=False)
                for _ in range(4):
                    sd,cp,normal,rim=head.signed(P+dP,D=delta,mesh=mesh,with_rim=True)
                    bad=(sd<.0028)&~rim
                    if not bad.any():break
                    dP[bad]=cp[bad]+normal[bad]*.0032-P[bad]
            dP[np.abs(dP).max(1) < 2e-6] = 0
            dN = None
            targets.append((dP, dN)); hair_d[nm] = dP
        if surface:
            from reference_surface import joint_groom_clearance
            ids=[n for n in names_all if n.startswith('id_')]
            combos=None
            if spec['name']=='full_beard':
                combos=assemble.default_combos(ids)
                combos['jaw_open+smile']={'ex_jaw_open':1,'ex_smile':1}
            P=joint_groom_clearance(head,P,hair_d,ids,.0032 if combos else .003,combos)
        prim = W.primitive(P.astype(np.float32), d['N'].astype(np.float32), d['UV'].astype(np.float32), d['T'],
                           colr, J4, W4, mat, targets)
        mesh_ids.append(W.mesh(f'beard_lod{lod}', [prim], names_all))
        nshell = int(sum(1 for _ in [0]))
        report['lods'][f'lod{lod}'] = {'tris': int(len(d['T'])), 'verts': int(len(P)),
                                       'shellTris': int(((d['lock'][d['T'][:, 0]]) < 0).sum())}
        if check:
            ids = [n for n in names_all if n.startswith('id_')]
            exs = [n for n in names_all if n.startswith('ex_')]
            combos = assemble.default_combos(ids)
            combos['jaw_open+smile'] = {'ex_jaw_open': 1.0, 'ex_smile': 1.0}
            clearance_rep[f'lod{lod}'] = assemble.clearance(head, P, head.deltas, hair_d, ids + exs, margin=0.002, combos=combos)

    # ---------------- skeleton: copy the head chain BodyRoot..Head, joints + inverse binds
    gg = W.g
    hn = head.gltf['nodes']
    chain = []
    for i, nd in enumerate(hn):
        if 'mesh' in nd:
            continue
        chain.append(i)
    newid = {}
    for i in chain:
        nd = hn[i]
        newid[i] = gg.node(**{k: nd[k] for k in ('name', 'translation', 'rotation', 'scale', 'matrix') if k in nd})
    for i in chain:
        ch = [newid[c] for c in hn[i].get('children', []) if c in newid]
        if ch:
            gg.g['nodes'][newid[i]]['children'] = ch
    child = {c for i in chain for c in hn[i].get('children', [])}
    for i in chain:
        if i not in child:
            gg.g['scenes'][0]['nodes'].append(newid[i])
    hskin = head.gltf['skins'][0]
    ibm_acc = gg.accessor(head.ibm_flat, 'MAT4')
    gg.g['skins'].append({'joints': [newid[j] for j in hskin['joints']], 'inverseBindMatrices': ibm_acc,
                          'skeleton': newid[hskin.get('skeleton', chain[0])], 'name': 'RLBeardSkin'})
    for lod, mid in zip(LODS, mesh_ids):
        gg.g['scenes'][0]['nodes'].append(gg.node(name=f'beard_lod{lod}', mesh=mid, skin=0))
    tris = {k: v['tris'] for k, v in report['lods'].items()}
    gg.g['asset']['extras'] = {'rlBeard': {
        'version': 1, 'style': spec.get('name'), 'sex': sex, 'tris': tris,
        'joints': [hn[j]['name'] for j in hskin['joints']],
        'colour': {'R': 'per-hair-card random', 'G': 'position along the card (0 root .. 1 tip); shell: 0 top edge .. 1 bottom edge',
                   'B': 'ao'},
        'texture': {'file': texture_name, 'columns': 1 if surface else NCOLS, 'cards': [] if surface else [0, 1, 2], 'shell': 0 if surface else SHELL_COL,
                    'shellPeriodPx': SHELL_PERIOD, 'shellMarginPx': SHELL_MARGIN},
        'morphTransfer': {'source': os.path.basename(head.glb_path), 'targets': 'all head shapes (id_* and ex_*)'},
        'headSHA256': assemble.file_sha(head.glb_path)}}
    size = W.save(out_path)
    report['bytes'] = size
    report['clearance'] = clearance_rep
    report['seconds'] = round(time.time() - t0, 1)
    json.dump(report, open(os.path.splitext(out_path)[0] + '.report.json', 'w'), indent=1)
    return report


# ===================================================================== chart
def write_chart(head, B, region, path, scale=6):
    """Authoring chart: the skin in the beard frame (lon right = toward the ears),
    region weight in green, lips red, ears blue, grid every 10 degrees."""
    from PIL import Image, ImageDraw
    w, lon, lat = region.weight(head.P)
    W_, H_ = 140 * scale, 150 * scale
    im = Image.new('RGB', (W_, H_), (250, 250, 250)); d = ImageDraw.Draw(im)
    X = lambda lo: (lo + 10) * scale
    Y = lambda la: (60 - la) * scale
    for g in range(-10, 131, 10):
        d.line([X(g), 0, X(g), H_], fill=(225, 225, 225)); d.text((X(g) + 2, 2), str(g), fill=(120, 120, 120))
    for g in range(-90, 61, 10):
        d.line([0, Y(g), W_, Y(g)], fill=(225, 225, 225)); d.text((2, Y(g) + 2), str(g), fill=(120, 120, 120))
    front = lon >= -2
    for i in np.nonzero(front)[0]:
        c = (int(200 - 150 * w[i]), int(200 + 40 * w[i]), int(200 - 150 * w[i]))
        if head.vgroups['lips'][i]:
            c = (220, 60, 60)
        if head.vgroups['ears'][i]:
            c = (80, 80, 220)
        x, y = X(lon[i]), Y(lat[i])
        d.ellipse([x - 1.5, y - 1.5, x + 1.5, y + 1.5], fill=c)
    xs = np.arange(0, 130, 1.0)
    d.line([(X(x), Y(region.top(x))) for x in xs], fill=(0, 120, 0), width=2)
    d.line([(X(x), Y(region.bot(x))) for x in xs], fill=(0, 0, 160), width=2)
    d.line([X(region.lon_max), 0, X(region.lon_max), H_], fill=(160, 0, 160))
    d.text((8, H_ - 30), 'beard frame: lon -> ears, lat up; green = top boundary, blue = bottom, magenta = lon_max', fill=(0, 0, 0))
    im.save(path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('spec'); ap.add_argument('sex'); ap.add_argument('out')
    ap.add_argument('--chart', default='')
    ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--embed-textures', action='store_true')
    ap.add_argument('--surface', help='Ignored reference-derived NPZ LOD stage, already neutralized to the head')
    a = ap.parse_args()
    rep = build(a.spec, a.sex, a.out, chart=a.chart or None, check=not a.no_check, embed=a.embed_textures, surface=a.surface)
    out = {'style': rep['style'], 'bytes': rep['bytes'], 'seconds': rep['seconds'], 'lods': rep['lods']}
    if rep['clearance']:
        out['clearance'] = {k: {'restMinMM': round(v['rest']['minMM'], 2), 'restViol': v['rest']['violations'],
                                'morphMinMM': None if v['morphs']['minMM'] is None else round(v['morphs']['minMM'], 2),
                                'violatingCases': v['morphs']['violatingCases'][:6]} for k, v in rep['clearance'].items()}
    print(json.dumps(out, indent=1))
