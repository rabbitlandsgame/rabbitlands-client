"""Synthetic Meshy-like reference busts with exact ground truth, for fitter acceptance.

    python RL/scripts/fit/synth/make_synthetic.py [--cases id,id|all] [--out RL/fit/synth/cases] [--list]

Each case writes RL/fit/synth/cases/<id>/:
  reference.glb        ONE fused closed surface (new topology), 2K baseColorTexture or COLOR_0, posed by a
                       random similarity (scale, yaw quadrant + tilt, translation, Y-up or Z-up)
  truth.json           ground truth (controls, transform, orientation, hair/beard, colours, observability)
  truth_envelope.npz   hair thickness envelope on headref's lon/lat grid + drape arrays + hair points
  preview.png          texel point-splat front | left | back | three-quarter (game space), for eyeballing

Ground truth definitions (also written into every truth.json under "definitions"):
  * controls: the 21 identity controls, applied to the RL LOD0 skin with the runtime semantics
    (id_<c>_p weight max(v,0), id_<c>_n weight max(-v,0)), from RL/build/v1 via headref.Head.
  * transform: x_game = scale * R @ x_ref + t maps reference-file coordinates (the GLB's POSITION values;
    every node transform is identity) to RL game space (metres, Y up, face toward +Z) -- the fit.json
    convention. The morphed RL skin in game space is exactly where the reference skin was generated.
  * envelope: rays from headref's cranium centre C (base head, h.C) in direction lonlat_dir(lon, lat);
    skin_r = outermost hit on the GT-morphed RL skin without ears (headref 'noear' surface, the one
    frame_point() uses); outer_r = outermost hit on the final reference surface mapped to game space;
    thickness_m = outer_r - skin_r where that outermost reference hit belongs to hair (the hair/drape
    component owns it), NaN otherwise or when the skin ray misses.
    drape_lowest_y[k] = lowest game-space y of hair-owned reference vertices whose horizontal azimuth
    atan2(x - C.x, z - C.z) (degrees, same lon convention) falls in the 10-degree bin centred on
    drape_lon_deg[k]; NaN where no hair. hair_points = up to 20000 hair-owned vertices (game space).
  * colours: albedo (before painterly variation and baked light) in sRGB 0-1; colours_texel_median are
    medians of the generated texels per class (what a perfect segmenter would measure).
  * observability: per control, the |delta|-weighted fraction of skin vertices that remain visible
    (not inside hair, beard, drape, eyeball or bust); controls with < 50 % visible are 'occluded' and
    are excluded from the control gates (reported separately).
"""
import os, sys, json, time, argparse, math
import numpy as np
from scipy.spatial import cKDTree
from scipy import ndimage
from scipy.interpolate import PchipInterpolator

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import synthlib as S  # noqa: E402

CONTROLS = S.controls_order()
EYE_R_FALLBACK = 0.0125

# ============================================================================ case table
PAL = {
    'pale': (0.93, 0.76, 0.65), 'fair': (0.91, 0.8, 0.729), 'tan': (0.8, 0.585, 0.42),
    'olive': (0.769, 0.592, 0.431), 'brown': (0.55, 0.37, 0.26), 'dark': (0.404, 0.259, 0.184),
}


def _case(**k):
    base = dict(controls='zero', seed=0, hair=None, beard=None, up='y', yaw=0, tilt=0.0, scale=1.0,
                voxel=0.002, post=None, noise_mm=0.0, texture='png', light=0.0, extra_maps=False,
                split=False, neckline='crew', stresses=[])
    base.update(k)
    return base


CASES = [
    _case(id='c00_m_zero_crop', sex='male', controls='zero', seed=100, hair='crop', yaw=0, scale=1.0,
          skin=PAL['tan'], hair_c=(0.36, 0.22, 0.12), brow_c=(0.2, 0.12, 0.07), lip_c=(0.66, 0.38, 0.32),
          eye_c=(0.3, 0.19, 0.1), cloth=(0.25, 0.32, 0.45),
          stresses=['baseline: all controls 0', 'identity pose (scale 1, yaw 0)', 'clean']),
    _case(id='c01_f_sparse_bun', sex='female', seed=101, hair='bun', yaw=90, tilt=5.0, scale=0.35,
          controls={'jaw_width': -0.8, 'chin_length': 0.6, 'nose_length': 0.7},
          skin=PAL['pale'], hair_c=(0.78, 0.3, 0.12), brow_c=(0.5, 0.22, 0.12), lip_c=(0.78, 0.4, 0.36),
          eye_c=(0.36, 0.55, 0.3), cloth=(0.32, 0.42, 0.22), light=0.6,
          stresses=['sparse controls', 'yaw 90 + 5 deg tilt', 'small scale 0.35', 'bun (tall envelope)', 'soft baked light']),
    _case(id='c02_m_sparse_fullbeard', sex='male', seed=102, hair='shag', beard='full', yaw=180, scale=2.2,
          controls={'cheekbones': 0.9, 'brow_ridge': 0.7, 'nose_width': -0.6, 'ear_size': 0.8},
          skin=PAL['fair'], hair_c=(0.62, 0.32, 0.13), brow_c=(0.5, 0.25, 0.1), lip_c=(0.72, 0.46, 0.42),
          eye_c=(0.4, 0.5, 0.6), cloth=(0.5, 0.18, 0.15), noise_mm=0.3, texture='jpeg',
          stresses=['full beard hides jaw/chin', 'yaw 180', 'large scale 2.2', 'surface noise 0.3 mm', 'JPEG texture']),
    _case(id='c03_f_dense_long', sex='female', seed=103, controls='dense', hair='long', yaw=270, tilt=-8.0,
          scale=1.4, skin=PAL['olive'], hair_c=(0.17, 0.1, 0.06), brow_c=(0.14, 0.08, 0.05),
          lip_c=(0.62, 0.36, 0.33), eye_c=(0.3, 0.2, 0.12), cloth=(0.82, 0.78, 0.66), noise_mm=0.4, light=0.6,
          neckline='v',
          stresses=['dense controls', 'long hair past the shoulders (drape)', 'yaw 270 - 8 deg tilt', 'noise 0.4 mm', 'baked light']),
    _case(id='c04_m_dense_fringe', sex='male', seed=104, controls='dense', hair='fringe', yaw=0, tilt=10.0,
          scale=0.6, skin=PAL['pale'], hair_c=(0.42, 0.3, 0.17), brow_c=(0.3, 0.2, 0.1), lip_c=(0.72, 0.45, 0.4),
          eye_c=(0.35, 0.45, 0.55), cloth=(0.2, 0.2, 0.22),
          stresses=['dense controls', 'side fringe over the forehead', '10 deg tilt', 'clean']),
    _case(id='c05_f_dense_zup_bob', sex='female', seed=105, controls='dense', hair='bob', up='z', yaw=90,
          tilt=4.0, scale=1.0, skin=PAL['brown'], hair_c=(0.08, 0.06, 0.05), brow_c=(0.07, 0.05, 0.04),
          lip_c=(0.45, 0.25, 0.22), eye_c=(0.25, 0.15, 0.08), cloth=(0.6, 0.15, 0.35),
          stresses=['Z-up export', 'yaw 90 + 4 deg tilt', 'bob covers the ears (ear_size occluded)', 'clean']),
    _case(id='c06_m_extreme', sex='male', seed=106, controls='extreme', hair='crop', yaw=270, scale=0.25,
          skin=PAL['olive'], hair_c=(0.22, 0.13, 0.07), brow_c=(0.16, 0.1, 0.06), lip_c=(0.66, 0.42, 0.36),
          eye_c=(0.3, 0.19, 0.1), cloth=(0.35, 0.3, 0.25),
          stresses=['extreme controls at +/-1 (reported, not RMSE-gated)', 'yaw 270', 'scale 0.25']),
    _case(id='c07_f_lite30k', sex='female', seed=107, controls='dense', hair='bun', yaw=180, scale=0.8,
          voxel=0.0024, post=('decimate', 30000), noise_mm=0.3, texture='jpeg', light=1.0,
          skin=PAL['fair'], hair_c=(0.86, 0.8, 0.64), brow_c=(0.55, 0.48, 0.36), lip_c=(0.76, 0.52, 0.52),
          eye_c=(0.45, 0.55, 0.62), cloth=(0.3, 0.35, 0.5),
          stresses=['meshy-6-lite density (~30k tris, decimated)', 'blonde on fair skin (low contrast)',
                    'strong baked light', 'noise 0.3 mm', 'yaw 180']),
    _case(id='c08_m_dense_1m_long', sex='male', seed=108, controls='dense', hair='long', beard='short',
          yaw=0, tilt=-12.0, scale=2.9, voxel=0.0025, post=('subdivide', 1), noise_mm=0.25, extra_maps=True,
          skin=PAL['tan'], hair_c=(0.05, 0.04, 0.035), brow_c=(0.05, 0.04, 0.035), lip_c=(0.6, 0.38, 0.32),
          eye_c=(0.28, 0.18, 0.1), cloth=(0.45, 0.42, 0.38),
          stresses=['meshy-7.1 density (~700k+ tris)', 'max tilt 12 deg', 'scale 2.9', 'long hair drape',
                    'short beard (3.5 mm)', 'normal + metallicRoughness maps (baseColor is image 2)']),
    _case(id='c09_f_vcolor_pixie', sex='female', seed=109, hair='pixie', texture='vcolor', yaw=90, scale=1.7,
          controls={'eye_spacing': 0.8, 'mouth_width': -0.7, 'chin_projection': 0.9},
          skin=PAL['dark'], hair_c=(0.05, 0.04, 0.035), brow_c=(0.05, 0.04, 0.035), lip_c=(0.42, 0.24, 0.22),
          eye_c=(0.22, 0.13, 0.07), cloth=(0.85, 0.6, 0.2),
          stresses=['COLOR_0 vertex colours (linear, glTF spec), no texture', 'dark skin', 'yaw 90', 'clean']),
    _case(id='c10_m_bald_goatee', sex='male', seed=110, hair=None, beard='goatee', yaw=180, tilt=6.0, scale=0.5,
          controls={'nose_depth': -0.7, 'brow_height': 0.6, 'cheek_fullness': 0.8, 'jaw_width': 0.6},
          skin=PAL['brown'], hair_c=(0.1, 0.07, 0.05), brow_c=(0.1, 0.07, 0.05), lip_c=(0.5, 0.3, 0.26),
          eye_c=(0.25, 0.15, 0.08), cloth=(0.3, 0.5, 0.45), noise_mm=0.2,
          stresses=['bald (hair absent)', 'goatee hides the chin', 'yaw 180 + 6 deg tilt', 'noise 0.2 mm']),
    _case(id='c11_f_dense_multimesh', sex='female', seed=111, controls='dense', hair='shag', yaw=0, tilt=3.0,
          scale=1.15, split=True, light=1.0, skin=PAL['fair'], hair_c=(0.62, 0.45, 0.25),
          brow_c=(0.45, 0.32, 0.2), lip_c=(0.78, 0.5, 0.48), eye_c=(0.4, 0.55, 0.35), cloth=(0.55, 0.4, 0.28),
          stresses=['two meshes / nodes', 'strong baked light', 'clothing close to hair colour', 'clean']),
    _case(id='c12_m_dense_clean', sex='male', seed=112, controls='dense', hair='shag', yaw=90, tilt=-5.0,
          scale=0.9, skin=PAL['olive'], hair_c=(0.3, 0.2, 0.12), brow_c=(0.2, 0.13, 0.08), lip_c=(0.66, 0.42, 0.36),
          eye_c=(0.3, 0.42, 0.25), cloth=(0.15, 0.25, 0.4), light=0.6,
          stresses=['dense controls', 'yaw 90 - 5 deg tilt', 'clean']),
]

EXPECTED_STYLE = {'crop': ['legacy:buzzed', 'rowan_shag'], 'shag': ['rowan_shag', 'legacy:parted'],
                  'fringe': ['rowan_shag', 'legacy:parted'], 'bun': ['mira_bun', 'legacy:buns', 'legacy:topknot'],
                  'long': ['legacy:long', 'legacy:braid', 'legacy:ponytail'], 'bob': ['legacy:bob'],
                  'pixie': ['legacy:buzzed', 'rowan_shag']}
EXPECTED_BEARD = {'full': ['full_beard'], 'goatee': ['goatee'], 'short': ['short_beard', 'stubble']}


def case_controls(case):
    c = case['controls']
    r = np.random.default_rng(case['seed'])
    if c == 'zero':
        v = {n: 0.0 for n in CONTROLS}
    elif c == 'dense':
        v = {n: float(np.round(r.uniform(-0.8, 0.8), 2)) for n in CONTROLS}
    elif c == 'extreme':
        v = {n: float(r.choice([-1.0, 1.0])) for n in CONTROLS}
    else:
        v = {n: float(c.get(n, 0.0)) for n in CONTROLS}
    return v


# ============================================================================ hair styles
_HL_K = np.array([0, 20, 35, 48, 58, 70, 100, 112, 125, 145, 180.0])
_HL_V = np.array([33, 29, 20, 6, -4, -6, -6, -22, -38, -48, -50.0])
_hl_base = PchipInterpolator(_HL_K, _HL_V)
_BOB_K = np.array([0, 20, 35, 45, 54, 150, 165, 180.0])
_BOB_V = np.array([33, 29, 20, 2, -36, -40, -44, -46.0])
_hl_bob = PchipInterpolator(_BOB_K, _BOB_V)


def wrap180(a):
    return (np.asarray(a, np.float64) + 180.0) % 360.0 - 180.0


def style_thickness(style, lon, lat):
    """Designed hair thickness (m) above the skin along headref's radial ray, as a smooth field of
    (lon, lat) in degrees. 0 where there is no hair."""
    lon = wrap180(lon); lat = np.asarray(lat, np.float64)
    al = np.abs(lon)
    if style is None:
        return np.zeros(np.broadcast(lon, lat).shape)
    if style == 'bob':
        hl = _hl_bob(al)
    else:
        hl = _hl_base(al)
    if style in ('crop', 'pixie'):
        hl = hl + 2.0
    if style == 'fringe':
        f = np.clip(np.abs(lon + 16.0) / 26.0, 0, 1)
        hl = np.minimum(hl, 12.0 + 22.0 * f * f)
    m = S.smoothstep(hl - 1.0, hl + 2.5, lat)
    up = S.smoothstep(-30, 70, lat)
    back = S.smoothstep(100, 150, al)
    if style == 'crop':
        t = 0.006 + 0.003 * up - 0.0015 * back * (1 - up)
    elif style == 'pixie':
        t = 0.006 + 0.006 * up
    elif style in ('shag', 'fringe'):
        t = 0.010 + 0.007 * up + 0.003 * back
        if style == 'fringe':
            fr = (1 - S.smoothstep(18, 30, np.abs(lon + 16))) * (1 - S.smoothstep(25, 40, lat))
            t = t * (1 - fr) + 0.009 * fr
    elif style == 'bun':
        t = 0.008 + 0.002 * up
        cdir = S.lonlat_dir(180.0, 38.0)
        d = S.lonlat_dir(lon, lat)
        th = np.degrees(np.arccos(np.clip((d * cdir).sum(-1), -1, 1)))
        th0 = 27.0
        t = t + 0.046 * np.clip(1 - (th / th0) ** 2, 0, 1) ** 0.6
    elif style == 'long':
        t = 0.011 + 0.004 * up + 0.008 * back * S.smoothstep(30, -25, lat)
    elif style == 'bob':
        side = S.smoothstep(40, 60, al) * (1 - S.smoothstep(150, 175, al))
        t = 0.011 + 0.004 * up + 0.017 * side * S.smoothstep(15, -20, lat) + 0.006 * back
    else:
        raise ValueError(style)
    return np.where(m > 0, t * m, 0.0)


# ============================================================================ the synthetic scene
class Scene:
    """Signed-distance components (metres, negative inside) of one synthetic bust in game space."""

    def __init__(self, case, h):
        self.case = case; self.h = h
        self.sex = case['sex']
        self.v = case_controls(case)
        D = np.zeros_like(h.P)
        for n, val in self.v.items():
            if val > 0:
                D += val * h.deltas[f'id_{n}_p']
            elif val < 0:
                D += (-val) * h.deltas[f'id_{n}_n']
        self.D = D
        self.Pm = h.P + D
        self.C = h.C.copy()
        self._weld_graph()
        self._landmarks()
        self._eyes()
        self._vertex_fields()
        self._samples()
        self._radial_skin()
        self._bust_params()
        self._drape_params()

    # ---------------------------------------------------------------- helpers
    def _weld_graph(self):
        h = self.h
        import scipy.sparse as sp
        self.nw = int(h.weld.max()) + 1
        Tw = h.weld[h.T]
        self.Aw = S.vertex_adjacency(self.nw, Tw)
        deg = np.asarray(self.Aw.sum(1)).ravel()
        self.Mw = sp.diags(1.0 / np.maximum(deg, 1)) @ self.Aw
        # representative position per weld id (morphed / base)
        self.Pw = np.zeros((self.nw, 3)); self.Pw[h.weld] = self.Pm
        self.Bw = np.zeros((self.nw, 3)); self.Bw[h.weld] = h.P
        self.Nw = np.zeros((self.nw, 3)); self.Nw[h.weld] = h.N

    def smooth_w(self, f, iters):
        f = np.asarray(f, np.float64)
        for _ in range(iters):
            f = 0.5 * f + 0.5 * (self.Mw @ f)
        return f

    def _landmarks(self):
        h = self.h; P = h.P
        lips = h.vgroups['lips']
        self.lips_top = float(P[lips, 1].max()); self.lips_bot = float(P[lips, 1].min())
        self.lip_hw = float(np.abs(P[lips, 0]).max())
        self.nose_tip = P[np.argmax(P[:, 2])]
        self.y_nb = self.lips_top + 0.6 * (self.nose_tip[1] - self.lips_top)
        front = P[:, 2] > 0.02
        self.chin = P[front][np.argmin(P[front][:, 1])]

    def _eyes(self):
        """Eyeball spheres from the rl_eye proxy primitive (+ its eye_spacing morphs)."""
        h = self.h
        sys.dont_write_bytecode = True
        import rlglb
        mesh = h.gltf['meshes'][h.mesh_index]
        prim = None
        for p in mesh['primitives']:
            if 'material' in p and h.gltf['materials'][p['material']].get('name') == 'rl_eye':
                prim = p
        self.eye_c = []; self.eye_r = []; self.eye_c_base = []
        if prim is None:
            E = h.eyes
            for sd in (1, -1):
                X = E[np.sign(E[:, 0]) == sd]
                self.eye_c.append(X.mean(0) - [0, 0, EYE_R_FALLBACK]); self.eye_r.append(EYE_R_FALLBACK)
            self.eye_c_base = list(self.eye_c)
            return
        Pe = rlglb.accessor(h.gltf, h.blob, prim['attributes']['POSITION'])
        De = np.zeros_like(Pe)
        for nm, t in zip(h.target_names, prim['targets']):
            if nm.startswith('id_'):
                c = nm[3:-2]; sgn = nm[-1]
                val = self.v.get(c, 0.0)
                w = max(val, 0) if sgn == 'p' else max(-val, 0)
                if w:
                    De += w * rlglb.accessor(h.gltf, h.blob, t['POSITION'])
        for sd in (1, -1):
            sel = np.sign(Pe[:, 0]) == sd
            for base in (True, False):
                X = Pe[sel] + (0 if base else De[sel])
                A = np.c_[2 * X, np.ones(len(X))]; f = (X * X).sum(1)
                sol, *_ = np.linalg.lstsq(A, f, rcond=None)
                c = sol[:3]; r = float(np.sqrt(sol[3] + c @ c))
                if base:
                    self.eye_c_base.append(c)
                else:
                    self.eye_c.append(c); self.eye_r.append(r)

    def _vertex_fields(self):
        """Per welded vertex masks/fields defined on the BASE head, carried by the morph."""
        h = self.h; B = self.Bw; nw = self.nw
        # rim
        rim = np.zeros(nw); rim[h.weld[h.rim]] = 1.0
        self.rim_w = rim
        # vertices used only by mouth-interior faces
        used_out = np.zeros(nw, bool); used_out[h.weld[h.T[~h.mouth_interior]].ravel()] = True
        self.mouth_only = ~used_out
        # lips
        lips = np.zeros(nw); lips[h.weld[h.vgroups['lips']]] = 1.0
        lips[self.mouth_only] = 0
        self.lips_m = np.clip(self.smooth_w(lips, 1) * 1.25 - 0.1, 0, 1)
        # brows: evaluated per dense sample at its base (undeformed) position, see brow_mask()
        # blush (cheeks)
        bl = np.zeros(nw)
        for c in self.eye_c_base:
            g = np.exp(-(((B[:, 0] - c[0] * 1.5) / 0.016) ** 2 + ((B[:, 1] - (c[1] - 0.03)) / 0.014) ** 2))
            bl = np.maximum(bl, g * (B[:, 2] > 0.0))
        self.blush_m = bl
        # beard thickness (male only)
        self.beard_t = np.zeros(nw)
        self.beard_zone = self._beard_zone('full')
        st = self.case['beard']
        if st:
            zone = self._beard_zone('goatee' if st == 'goatee' else 'full')
            chin = np.exp(-((B[:, 0] / 0.03) ** 2 + ((B[:, 1] - self.chin[1]) / 0.025) ** 2))
            if st == 'full':
                t = 0.007 + 0.006 * chin
            elif st == 'goatee':
                t = 0.006 + 0.002 * chin
            else:
                t = 0.0035 + 0.0 * chin
            must = (B[:, 1] > self.lips_top - 0.002)
            t = np.where(must, np.minimum(t, 0.005 if st != 'short' else 0.003), t)
            self.beard_t = self.smooth_w(t * self.smooth_w(zone, 3), 5)
            self.beard_t[self.beard_t < 0.0008] = 0.0

    def brow_mask(self, B, Nb):
        """Painted brow band (0..1) as a function of BASE head position/normal (carried by the morph)."""
        bm = np.zeros(len(B))
        for c in self.eye_c_base:
            ex, ey, ez = c
            u = np.abs(B[:, 0]) - abs(ex)
            yc = ey + 0.0165 + 0.0035 * (1 - ((u - 0.002) / 0.019) ** 2)
            hh = 0.0036 * (1 - 0.45 * S.smoothstep(0.004, 0.022, u))
            m = (1 - S.smoothstep(hh - 0.0004, hh + 0.0006, np.abs(B[:, 1] - yc)))
            m *= S.smoothstep(-0.019, -0.013, u) * (1 - S.smoothstep(0.019, 0.026, u))
            m *= (B[:, 2] > ez - 0.012) & (Nb[:, 2] > 0.15) & (np.sign(B[:, 0]) == np.sign(ex))
            bm = np.maximum(bm, m)
        return bm

    def _beard_zone(self, style):
        h = self.h; B = self.Bw
        lon, lat = S.dir_lonlat(B - self.C)
        lipsP = h.P[h.vgroups['lips']]
        dl, _ = cKDTree(lipsP).query(B)
        ax = np.abs(B[:, 0])
        eye_y = float(np.mean([c[1] for c in self.eye_c_base]))
        rimP = h.P[h.rim]
        dr, _ = cKDTree(rimP).query(B)
        if style == 'goatee':
            z = (ax < self.lip_hw + 0.006) & (B[:, 1] < self.y_nb - 0.001) & (np.abs(lon) < 55)
        else:
            a0 = self.lip_hw + 0.004
            # cheek line: mouth corner -> front of the ear (below the cheekbone), then a sideburn
            yb = self.y_nb - 0.001 + np.clip((ax - a0) / (0.07 - a0), 0, 1) * (eye_y - 0.032 - self.y_nb)
            yb = yb + S.smoothstep(0.066, 0.076, ax) * 0.024
            z = (np.abs(lon) < 84) & (B[:, 1] < yb)
        z = z & (dl > 0.003) & ~self.mouth_only
        zone = z.astype(np.float64) * S.smoothstep(0.003, 0.014, dr)
        return zone

    def _samples(self):
        """Dense samples of the morphed skin (mouth interior removed): centroids of a <=0.7 mm
        subdivision, with source face, barycentrics, face normal and interpolated vertex fields."""
        import trimesh
        h = self.h
        Tk = h.T[~h.mouth_interior]
        V2, F2, idx = trimesh.remesh.subdivide_to_size(self.Pm, Tk, max_edge=0.0009, max_iter=14, return_index=True)
        cen = V2[F2].mean(1)
        src = Tk[idx]
        bc = S.headref_module().barycentric(cen, self.Pm[src[:, 0]], self.Pm[src[:, 1]], self.Pm[src[:, 2]])
        fn = np.cross(self.Pm[src[:, 1]] - self.Pm[src[:, 0]], self.Pm[src[:, 2]] - self.Pm[src[:, 0]])
        self.sP = cen; self.sN = S.unit(fn)
        sw = h.weld[src]

        def interp(f):
            return (f[sw] * bc).sum(1)
        self.s_rim = interp(self.rim_w)
        self.s_beard = interp(self.beard_t)
        self.s_lips = interp(self.lips_m)
        sB = (h.P[src] * bc[:, :, None]).sum(1)
        sNb = S.unit((h.N[src] * bc[:, :, None]).sum(1))
        self.s_brow = self.brow_mask(sB, sNb)
        self.s_blush = interp(self.blush_m)
        self.s_zone = interp(self.beard_zone)
        self.tree = cKDTree(self.sP)
        self.band = 0.006 + float(self.beard_t.max())
        lo = self.Pm.min(0); hi = self.Pm.max(0)
        self.head_lo = lo - 0.03; self.head_hi = hi + 0.03

    def _radial_skin(self):
        """Radial skin distance r_s(lon, lat) from C on the morphed noear skin (1 deg grid), with holes
        (ear base, neck opening) filled from the nearest valid cell for the hair shell construction."""
        h = self.h
        lon = np.arange(-181.0, 181.5, 1.0); lat = np.arange(-89.0, 89.5, 1.0)
        LO, LA = np.meshgrid(lon, lat)
        t, f = S.radial_cast(self.Pm, h.T_noear, self.C, S.lonlat_dir(LO.ravel(), LA.ravel()), 'outer')
        R = t.reshape(LA.shape)
        miss = ~np.isfinite(R)
        if miss.any():
            _, (ii, jj) = ndimage.distance_transform_edt(miss, return_indices=True)
            Rf = R[ii, jj]
            Rs = ndimage.gaussian_filter(Rf, 1.5)
            R = np.where(miss, Rs, R)
        self.rs_lon = lon; self.rs_lat = lat; self.rs_map = R

    def rs(self, lon, lat):
        fi = (np.asarray(lat) - self.rs_lat[0]) / 1.0
        fj = (wrap180(lon) - self.rs_lon[0]) / 1.0
        return ndimage.map_coordinates(self.rs_map, [fi.ravel(), fj.ravel()], order=1, mode='nearest').reshape(np.shape(lon))

    def _bust_params(self):
        h = self.h
        rim = self.Pm[h.rim]
        c = rim[:, [0, 2]].mean(0)
        self.neck_c = np.array([0.0, c[1]])          # (x, z) symmetric
        phi = np.degrees(np.arctan2(rim[:, 0] - self.neck_c[0], rim[:, 2] - self.neck_c[1]))
        rho = np.hypot(rim[:, 0] - self.neck_c[0], rim[:, 2] - self.neck_c[1])
        o = np.argsort(phi)
        phi, rho, ry = phi[o], rho[o], rim[o, 1]
        grid = np.arange(-180, 181, 2.0)
        pp = np.r_[phi - 360, phi, phi + 360]
        self.neck_phi = grid
        self.neck_rho = np.interp(grid, pp, np.r_[rho, rho, rho])
        self.neck_y = np.interp(grid, pp, np.r_[ry, ry, ry])
        self.rim_lo = float(rim[:, 1].min()); self.rim_hi = float(rim[:, 1].max())
        male = self.sex == 'male'
        self.sh_w = 0.170 if male else 0.150
        self.chest = dict(c=np.array([0.0, 1.31, self.neck_c[1] + 0.01]),
                          r=np.array([0.158 if male else 0.142, 0.15, 0.10 if male else 0.095]))
        self.y_cut = 1.24 if male else 1.25
        self.neck_base = 1.43

    def bust(self, X):
        x, y, z = X[:, 0], X[:, 1], X[:, 2]
        dx = x - self.neck_c[0]; dz = z - self.neck_c[1]
        phi = np.degrees(np.arctan2(dx, dz)); rho = np.hypot(dx, dz)
        nr = np.interp(phi, self.neck_phi, self.neck_rho) - 0.0015
        ny_ = np.interp(phi, self.neck_phi, self.neck_y)
        k = 1 - 0.3 * S.smoothstep(ny_, ny_ + 0.025, y)
        d_neck = np.maximum(rho - nr * k, y - (self.rim_hi + 0.03))
        d_neck = np.maximum(d_neck, (self.neck_base - 0.08) - y)
        # trapezius capsules (neck base -> acromion), chest ellipsoid
        d_tr = np.full(len(X), 1.0)
        for sd in (1, -1):
            a = np.array([sd * 0.04, 1.462, self.neck_c[1] - 0.005]); b = np.array([sd * self.sh_w, 1.418, self.neck_c[1] - 0.005])
            ab = b - a; t = np.clip(((X - a) @ ab) / (ab @ ab), 0, 1)
            d_tr = np.minimum(d_tr, np.linalg.norm(X - (a + t[:, None] * ab), axis=1) - (0.045 + 0.01 * t))
        q = (X - self.chest['c']) / self.chest['r']
        lq = np.linalg.norm(q, axis=1)
        d_ch = (lq - 1) * np.min(self.chest['r'])
        d_body = smin(d_tr, d_ch, 0.03)
        d = smin(d_neck, d_body, 0.03)
        return np.maximum(d, self.y_cut - y)

    def _drape_params(self):
        """For long hair: body radius map rho_body(y, phi) about the vertical axis through C."""
        self.has_drape = self.case['hair'] == 'long'
        if not self.has_drape:
            return
        ys = np.arange(self.y_cut, self.C[1] + 0.001, 0.002)
        ph = np.arange(-180, 181, 3.0)
        rr = np.arange(0.0, 0.32, 0.001)
        Y, PH = np.meshgrid(ys, ph, indexing='ij')
        out = np.zeros(Y.shape)
        for i in range(len(ys)):
            X = np.stack([self.C[0] + rr[None, :] * np.sin(np.radians(ph))[:, None],
                          np.full((len(ph), len(rr)), ys[i]),
                          self.C[2] + rr[None, :] * np.cos(np.radians(ph))[:, None]], -1).reshape(-1, 3)
            d = np.minimum(self.bust(X), self.head_sd_coarse(X)).reshape(len(ph), len(rr))
            inside = d < 0
            last = np.where(inside.any(1), len(rr) - 1 - np.argmax(inside[:, ::-1], 1), 0)
            out[i] = rr[last]
        self.dr_y = ys; self.dr_phi = ph; self.dr_rho = ndimage.gaussian_filter(out, (2, 1))
        # skin radius behind the head at C height (hair hangs from there)
        sel = (self.Pm[:, 1] > self.C[1] - 0.06) & (self.Pm[:, 1] < self.C[1])
        self.rho_back = float(np.max(np.hypot(self.Pm[sel, 0] - self.C[0], self.Pm[sel, 2] - self.C[2])[self.Pm[sel, 2] < self.C[2]]))
        r = np.random.default_rng(self.case['seed'] + 7)
        self.dr_ylow = float(r.uniform(1.30, 1.34))
        self.dr_phi0 = 95.0
        self.dr_th = 0.016
        self.dr_w = 0.088

    def head_sd_coarse(self, X):
        return self.head(X)[0]

    # ---------------------------------------------------------------- components
    def head(self, X):
        """Tangent-plane signed distance to the morphed skin (nearest dense sample) inside a band of
        self.band metres; points beyond the open neck rim count as outside (the bust neck closes it).
        Outside the band only the sign matters: inside iff closer to C than the radial noear skin and
        not below the local rim height; the value is clamped to +/-band.
        Returns (d, sample index (0 where beyond the band), far mask)."""
        d, i = self.tree.query(X, workers=-1, distance_upper_bound=self.band)
        far = ~np.isfinite(d)
        i = np.where(far, 0, i)
        d = np.where(far, self.band, d)
        dot = ((X - self.sP[i]) * self.sN[i]).sum(1)
        s = np.sign(dot); s[s == 0] = 1
        out = np.where(d < 0.0015, dot, s * d)
        below = ~far & (self.s_rim[i] > 0.5) & (X[:, 1] < self.sP[i, 1] + 0.001)
        out[below] = d[below]
        if far.any():
            V = X[far] - self.C
            r = np.linalg.norm(V, axis=1)
            lon, lat = S.dir_lonlat(V)
            phi = np.degrees(np.arctan2(X[far, 0] - self.neck_c[0], X[far, 2] - self.neck_c[1]))
            above = X[far, 1] > np.interp(phi, self.neck_phi, self.neck_y) - 0.003
            inside = (r < self.rs(lon, lat)) & above
            out[far] = np.where(inside, -self.band, self.band)
        return out, i, far

    def eyes(self, X):
        d = np.full(len(X), 1.0)
        for c, r in zip(self.eye_c, self.eye_r):
            d = np.minimum(d, np.linalg.norm(X - c, axis=1) - r)
        return d

    def hair(self, X):
        st = self.case['hair']
        if st is None:
            return np.full(len(X), 1.0)
        V = X - self.C
        r = np.linalg.norm(V, axis=1)
        lon, lat = S.dir_lonlat(V)
        t = style_thickness(st, lon, lat)
        rs = self.rs(lon, lat)
        d = np.maximum(r - (rs + t), (rs - 0.005) - r)
        d = np.where(t > 0.0004, d, 1.0)
        return d

    def drape(self, X):
        if not self.has_drape:
            return np.full(len(X), 1.0)
        x, y, z = X[:, 0] - self.C[0], X[:, 1], X[:, 2] - self.C[2]
        phi = np.degrees(np.arctan2(x, z)); rho = np.hypot(x, z)
        fi = (y - self.dr_y[0]) / 0.002; fj = (phi - self.dr_phi[0]) / 3.0
        rb = ndimage.map_coordinates(self.dr_rho, [fi, fj], order=1, mode='nearest')
        top = self.C[1] - 0.01
        span = max(top - self.dr_ylow, 1e-3)
        th = self.dr_th * (0.55 + 0.45 * np.clip((y - self.dr_ylow) / span, 0, 1))
        rin = np.maximum(self.rho_back + 0.003, rb - 0.003)
        rout = rin + th
        d = np.maximum(rho - rout, rin - rho)
        aphi = np.abs(phi)
        d = np.maximum(d, np.radians(self.dr_phi0 - aphi) * rho)
        frac = np.clip((y - self.dr_ylow) / span, 0, 1)
        w = self.dr_w * (0.85 + 0.15 * frac)
        d = np.maximum(d, np.abs(x) - w)
        ylow = self.dr_ylow + 0.045 * (np.clip(np.abs(x) / self.dr_w, 0, 1)) ** 2
        d = np.maximum(d, ylow - y)
        d = np.maximum(d, y - top)
        return d

    def beard(self, dh, idx):
        tb = self.s_beard[idx]
        d = np.maximum(dh - tb, -dh - 0.004)
        return np.where(tb > 0.0004, d, 1.0)

    def components(self, X):
        """(n, 6) signed distances: head, eyes, hair, drape, beard, bust."""
        X = np.asarray(X, np.float64)
        n = len(X)
        out = np.full((n, 6), 1.0)
        sidx = np.zeros(n, np.int64)
        inb = np.all((X > self.head_lo - 0.03) & (X < self.head_hi + 0.03), 1)
        if inb.any():
            Xi = X[inb]
            dh, idx, far = self.head(Xi)
            out[inb, 0] = dh
            out[inb, 1] = self.eyes(Xi)
            bd = self.beard(dh, idx); bd[far] = 1.0
            out[inb, 4] = bd
            sidx[inb] = idx
            hb = np.linalg.norm(Xi - self.C, axis=1) < self.h.R + 0.12
            if hb.any():
                tmp = np.full(len(Xi), 1.0); tmp[hb] = self.hair(Xi[hb]); out[np.nonzero(inb)[0], 2] = tmp
        if self.has_drape:
            m = (X[:, 1] < self.C[1] + 0.005) & (X[:, 1] > self.y_cut) & (X[:, 2] < self.C[2] + 0.05)
            if m.any():
                out[m, 3] = self.drape(X[m])
        out[:, 5] = self.bust(X)
        self._last_idx = sidx
        return out

    def owner_info(self, X):
        """Component owner (argmin) and the head-sample index (valid for head-owned points)."""
        X = np.asarray(X, np.float64)
        comp = self.components(X)
        own = np.argmin(comp, 1)
        return own, self._last_idx, comp


def smin(a, b, k):
    hh = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - hh) + a * hh - k * hh * (1 - hh)


# ============================================================================ geometry
def build_surface(sc, h_vox, log):
    """Union SDF on a grid -> cavities filled -> largest solid -> surface nets -> Taubin."""
    lo = np.minimum(sc.head_lo - 0.07, [-(sc.sh_w + 0.07), sc.y_cut - 0.01, -0.20])
    hi = np.maximum(sc.head_hi + 0.075, [sc.sh_w + 0.07, sc.head_hi[1] + 0.075, 0.16])
    lo[1] = sc.y_cut - 3 * h_vox
    nx, ny, nz = (np.ceil((hi - lo) / h_vox).astype(int) + 1)
    log(f'  grid {nx}x{ny}x{nz} = {nx * ny * nz / 1e6:.1f} M voxels @ {h_vox * 1000:.1f} mm')
    t0 = time.time()
    xs = lo[0] + h_vox * np.arange(nx); ys = lo[1] + h_vox * np.arange(ny); zs = lo[2] + h_vox * np.arange(nz)
    Fg = np.empty((nx, ny, nz), np.float32)
    YY, ZZ = np.meshgrid(ys, zs, indexing='ij')
    slab = max(1, int(1.5e6 // (ny * nz)))
    for i0 in range(0, nx, slab):
        i1 = min(nx, i0 + slab)
        X = np.stack(np.broadcast_arrays(xs[i0:i1, None, None], YY[None], ZZ[None]), -1).reshape(-1, 3)
        comp = sc.components(X)
        Fg[i0:i1] = comp.min(1).reshape(i1 - i0, ny, nz)
    Fg[0] = Fg[-1] = 1; Fg[:, 0] = Fg[:, -1] = 1; Fg[:, :, 0] = Fg[:, :, -1] = 1
    solid = Fg < 0
    filled = ndimage.binary_fill_holes(solid)
    nfill = int((filled & ~solid).sum())
    Fg[filled & ~solid] = -0.5 * h_vox
    lab, nl = ndimage.label(filled)
    if nl > 1:
        sizes = ndimage.sum_labels(filled, lab, np.arange(1, nl + 1))
        keep = 1 + int(np.argmax(sizes))
        drop = filled & (lab != keep)
        Fg[drop] = np.abs(Fg[drop]) + 0.5 * h_vox
    del lab, filled, solid
    log(f'  cavity voxels filled {nfill}, solid islands {nl}')
    log(f'  union SDF + fill {time.time() - t0:.1f} s')
    V, T = S.surface_nets(Fg, lo, h_vox)
    T, ncomp = S.largest_component_faces(len(V), T)
    V, T, _ = S.compact(V, T)
    V = S.taubin(V, T, iters=2)
    log(f'  surface nets: {len(V)} verts {len(T)} tris (components {ncomp}) {time.time() - t0:.1f} s')
    return V, T, (Fg, lo, h_vox)


def grid_value(grid, X):
    Fg, lo, hv = grid
    f = (np.asarray(X) - lo) / hv
    return ndimage.map_coordinates(Fg, [f[:, 0], f[:, 1], f[:, 2]], order=1, mode='constant', cval=1.0)


def add_noise(V, T, mm, seed):
    if mm <= 0:
        return V
    N = S.vertex_normals(V, T)
    n1 = S.Noise3(seed, 0.003, 0.014, 40)(V)
    r = np.random.default_rng(seed + 1)
    w = r.normal(size=len(V))
    f = 0.8 * n1 + 0.6 * w
    f = f / np.sqrt((f ** 2).mean())
    return V + N * (f * mm / 1000.0)[:, None]


def blender_post(V, T, post, want_uv, log):
    """Optional decimate (collapse) and Smart UV Project in Blender (bpy). Returns V, T, corner UV (m,3,2)
    in Blender convention (v up) or None."""
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new('ref')
    me.vertices.add(len(V)); me.vertices.foreach_set('co', V.astype(np.float32).ravel())
    me.loops.add(len(T) * 3); me.loops.foreach_set('vertex_index', T.astype(np.int32).ravel())
    me.polygons.add(len(T)); me.polygons.foreach_set('loop_start', np.arange(0, len(T) * 3, 3, dtype=np.int32))
    me.update(); me.validate()
    ob = bpy.data.objects.new('ref', me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    if post and post[0] == 'decimate':
        mod = ob.modifiers.new('dec', 'DECIMATE')
        mod.ratio = float(post[1]) / max(len(T), 1)
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
        log(f'  decimated to {len(ob.data.polygons)} faces')
    if want_uv:
        t0 = time.time()
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris()
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.001)
        bpy.ops.object.mode_set(mode='OBJECT')
        log(f'  smart UV project {time.time() - t0:.1f} s')
    me = ob.data
    me.calc_loop_triangles()
    nv = len(me.vertices)
    co = np.zeros(nv * 3, np.float32); me.vertices.foreach_get('co', co)
    nt = len(me.loop_triangles)
    tv = np.zeros(nt * 3, np.int32); me.loop_triangles.foreach_get('vertices', tv)
    tl = np.zeros(nt * 3, np.int32); me.loop_triangles.foreach_get('loops', tl)
    UVc = None
    if want_uv:
        uv = np.zeros(len(me.loops) * 2, np.float32); me.uv_layers.active.data.foreach_get('uv', uv)
        UVc = uv.reshape(-1, 2)[tl].reshape(nt, 3, 2).astype(np.float64)
    V2 = co.reshape(-1, 3).astype(np.float64); T2 = tv.reshape(-1, 3).astype(np.int64)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return V2, T2, UVc


def split_by_uv(V, T, UVc):
    """Unique (vertex, uv) pairs -> render vertices. Returns (P, UV (gltf, v down), T, src vertex)."""
    m = len(T)
    cv = T.reshape(-1)
    cu = UVc.reshape(-1, 2)
    key = np.c_[cv, np.round(cu[:, 0] * 2 ** 20), np.round(cu[:, 1] * 2 ** 20)].astype(np.int64)
    uk, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    first = np.zeros(len(uk), np.int64); first[inv] = np.arange(len(cv))
    src = cv[first]
    UV = cu[first].copy(); UV[:, 1] = 1.0 - UV[:, 1]
    return V[src], UV, inv.reshape(m, 3), src


# ============================================================================ texture
def raster_uv(UVt, res):
    """Texel centres covered by UV triangles (glTF uv, v down). UVt (m,3,2).
    Returns tri index, barycentrics (k,3), row, col."""
    x = UVt[..., 0] * res - 0.5; y = UVt[..., 1] * res - 0.5
    x0 = np.ceil(x.min(1)).astype(np.int64); x1 = np.floor(x.max(1)).astype(np.int64)
    y0 = np.ceil(y.min(1)).astype(np.int64); y1 = np.floor(y.max(1)).astype(np.int64)
    x0 = np.clip(x0, 0, res - 1); y0 = np.clip(y0, 0, res - 1); x1 = np.clip(x1, -1, res - 1); y1 = np.clip(y1, -1, res - 1)
    w = x1 - x0 + 1; hgt = y1 - y0 + 1
    ok = (w > 0) & (hgt > 0)
    size = np.maximum(w, hgt)
    out_t, out_b, out_r, out_c = [], [], [], []
    B = 1
    tri_all = np.nonzero(ok)[0]
    while len(tri_all):
        sel = tri_all[size[tri_all] <= B]
        tri_all = tri_all[size[tri_all] > B]
        if len(sel):
            oy, ox = np.meshgrid(np.arange(B), np.arange(B), indexing='ij')
            oy = oy.ravel(); ox = ox.ravel()
            step = max(1, int(4e6 // (B * B)))
            for s0 in range(0, len(sel), step):
                tt = sel[s0:s0 + step]
                cx = x0[tt][:, None] + ox[None]; cy = y0[tt][:, None] + oy[None]
                ax, ay = x[tt, 0][:, None], y[tt, 0][:, None]
                bx, by = x[tt, 1][:, None], y[tt, 1][:, None]
                qx, qy = x[tt, 2][:, None], y[tt, 2][:, None]
                det = (bx - ax) * (qy - ay) - (qx - ax) * (by - ay)
                det = np.where(np.abs(det) < 1e-12, 1e-12, det)
                l1 = ((cx - ax) * (qy - ay) - (qx - ax) * (cy - ay)) / det
                l2 = ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / det
                l0 = 1 - l1 - l2
                e = -1e-6
                ins = (l0 >= e) & (l1 >= e) & (l2 >= e) & (cx <= x1[tt][:, None]) & (cy <= y1[tt][:, None])
                ti, ki = np.nonzero(ins)
                out_t.append(tt[ti]); out_b.append(np.stack([l0[ti, ki], l1[ti, ki], l2[ti, ki]], 1))
                out_r.append(cy[ti, ki]); out_c.append(cx[ti, ki])
        B *= 2
    t = np.concatenate(out_t); b = np.concatenate(out_b); r = np.concatenate(out_r); c = np.concatenate(out_c)
    # one triangle per texel (first wins)
    lin = r * res + c
    _, first = np.unique(lin, return_index=True)
    return t[first], b[first], r[first], c[first]


def dilate_texture(img, mask, iters=12):
    import cv2
    img = img.astype(np.float32).copy(); m = mask.astype(np.float32)
    k = np.ones((3, 3), np.float32)
    for _ in range(iters):
        if m.min() > 0:
            break
        s = cv2.filter2D(img * m[..., None], -1, k, borderType=cv2.BORDER_REPLICATE)
        w = cv2.filter2D(m, -1, k, borderType=cv2.BORDER_REPLICATE)
        new = (m == 0) & (w > 0)
        img[new] = s[new] / w[new][:, None]
        m = np.where(new, 1.0, m)
    if m.min() == 0:
        img[m == 0] = img[m > 0].mean(0)
    return img


LABELS = ['skin', 'lips', 'brows', 'iris', 'sclera', 'hair', 'beard', 'clothing', 'neck_skin', 'pupil', 'brow_edge']


class Painter:
    def __init__(self, sc, case):
        self.sc = sc; self.case = case
        self.alb = {k: S.srgb_to_linear(np.array(case[k2], np.float64)) for k, k2 in
                    (('skin', 'skin'), ('hair', 'hair_c'), ('brow', 'brow_c'), ('lip', 'lip_c'), ('eye', 'eye_c'),
                     ('cloth', 'cloth'))}
        self.alb['beard'] = self.alb['hair'] * 0.92
        self.n_skin = S.Noise3(case['seed'] + 11, 0.008, 0.05, 32)
        self.n_fine = S.Noise3(case['seed'] + 12, 0.002, 0.008, 32)
        self.n_hair = S.Noise3(case['seed'] + 13, 0.0015, 0.006, 40)
        self.n_cloth = S.Noise3(case['seed'] + 14, 0.01, 0.06, 24)
        self.L = S.unit(np.array([0.45, 0.7, 0.55]))
        self.H = S.unit(self.L + np.array([0, 0, 1.0]))
        self.light = case['light']
        Nm = S.vertex_normals(sc.Pm, sc.h.T)
        lon, _ = S.dir_lonlat(sc.Pm - sc.C)
        self.ndl_ref = float(np.median(Nm[np.abs(lon) < 90] @ self.L))

    def paint(self, X, N):
        """Linear RGB colours and hard labels for surface points X (game space) with normals N."""
        sc = self.sc
        own, idx, comp = sc.owner_info(X)
        n = len(X)
        col = np.zeros((n, 3)); lab = np.zeros(n, np.int64)
        # head skin family
        hd = own == 0
        sk = self.alb['skin'][None] * (1 + 0.05 * self.n_skin(X) + 0.025 * self.n_fine(X))[:, None]
        bl = sc.s_blush[idx][:, None]
        sk = sk * (1 + bl * np.array([0.05, -0.03, -0.04])[None])
        lipw = np.clip(sc.s_lips[idx], 0, 1)[:, None]
        broww = np.clip(1.5 * sc.s_brow[idx] - 0.15 + 0.1 * np.clip(self.n_hair(X * [1, 0.3, 1]), -1, 1), 0, 1)[:, None]
        lipc = self.alb['lip'][None] * (1 + 0.04 * self.n_fine(X))[:, None]
        browc = self.alb['brow'][None] * (1 + 0.06 * self.n_hair(X))[:, None]
        c_head = sk * (1 - lipw) + lipc * lipw
        c_head = c_head * (1 - broww) + browc * broww
        col[hd] = c_head[hd]
        lab[hd] = np.where(sc.s_lips[idx][hd] > 0.5, 1, np.where(sc.s_brow[idx][hd] > 0.8, 2, np.where(sc.s_brow[idx][hd] > 0.2, 10, 0)))
        # eyes
        ey = own == 1
        if ey.any():
            Xe = X[ey]
            cs = np.array(sc.eye_c)
            which = np.argmin(np.linalg.norm(Xe[:, None] - cs[None], axis=2), 1)
            dirs = S.unit(Xe - cs[which])
            fwd = S.unit(np.array([0.0, 0.0, 1.0]))
            ang = np.degrees(np.arccos(np.clip(dirs @ fwd, -1, 1)))
            ce = np.where(ang[:, None] < 9.5, np.array([0.02, 0.02, 0.02])[None],
                          np.where(ang[:, None] < 23.0, self.alb['eye'][None] * (1 + 0.08 * self.n_fine(Xe))[:, None],
                                   np.array([0.78, 0.74, 0.68])[None]))
            col[ey] = ce
            lab[ey] = np.where(ang < 9.5, 9, np.where(ang < 23.0, 3, 4))
        # hair + drape
        hr = (own == 2) | (own == 3)
        if hr.any():
            Xh = X[hr]
            V = Xh - sc.C
            lon, lat = S.dir_lonlat(V)
            streak = self.n_hair(np.c_[np.radians(lon) * 0.09, Xh[:, 1] * 0.25, np.radians(lat) * 0.02 + Xh[:, 2] * 0.3])
            col[hr] = self.alb['hair'][None] * (1 + 0.14 * streak + 0.04 * self.n_fine(Xh))[:, None]
            lab[hr] = 5
        bd = own == 4
        if bd.any():
            col[bd] = self.alb['beard'][None] * (1 + 0.12 * self.n_hair(X[bd]))[:, None]
            lab[bd] = 6
        bu = own == 5
        if bu.any():
            Xb = X[bu]
            drop = 0.03 if self.case['neckline'] == 'crew' else 0.07
            ycol = 1.445 - drop * S.smoothstep(sc.neck_c[1] - 0.02, sc.neck_c[1] + 0.06, Xb[:, 2]) * (1 - S.smoothstep(0.0, 0.07, np.abs(Xb[:, 0])))
            isc = Xb[:, 1] < ycol
            cc = self.alb['cloth'][None] * (1 + 0.1 * self.n_cloth(Xb))[:, None]
            ns = self.alb['skin'][None] * (1 + 0.05 * self.n_skin(Xb))[:, None]
            col[bu] = np.where(isc[:, None], cc, ns)
            lab[bu] = np.where(isc, 7, 8)
        # baked light
        if self.light > 0:
            ndl = N @ self.L
            shade = 1 + self.light * 0.4 * (ndl - self.ndl_ref)
            spec = self.light * 0.25 * np.clip(N @ self.H, 0, 1) ** 60
            col = col * np.clip(shade, 0.5, 1.6)[:, None] + spec[:, None]
        return np.clip(col, 0, 1), lab, own


# ============================================================================ ground truth measures
def envelope_truth(sc, Vg, Tg, own_v):
    h = sc.h
    lon = np.arange(-180.0, 180.0, 2.5); lat = np.arange(-75.0, 90.01, 2.5)
    LO, LA = np.meshgrid(lon, lat)
    d = S.lonlat_dir(LO.ravel(), LA.ravel())
    rs, _ = S.radial_cast(sc.Pm, h.T_noear, sc.C, d, 'outer')
    ro, fo = S.radial_cast(Vg, Tg, sc.C, d, 'outer')
    hit = np.isfinite(ro)
    hp = sc.C + d * np.where(hit, ro, 0)[:, None]
    own_hit = np.full(len(d), -1)
    if hit.any():
        o, _, _ = sc.owner_info(hp[hit])
        own_hit[hit] = o
    hairy = (own_hit == 2) | (own_hit == 3)
    skin_hit = np.isfinite(rs)
    th_all = np.where(hairy & skin_hit, ro - rs, np.nan)
    # hair hits below the local neck-rim height belong to the drape (contract: drape arrays), not the shell
    phi = np.degrees(np.arctan2(hp[:, 0] - sc.neck_c[0], hp[:, 2] - sc.neck_c[1]))
    below = hit & (hp[:, 1] < np.interp(phi, sc.neck_phi, sc.neck_y))
    shell = hairy & skin_hit & ~below
    th = np.where(shell, ro - rs, np.nan)
    design = style_thickness(sc.case['hair'], LO.ravel(), LA.ravel())
    M, L = LA.shape
    env = dict(lon_deg=lon, lat_deg=lat, thickness_m=th.reshape(M, L), thickness_all_m=th_all.reshape(M, L),
               skin_r_m=rs.reshape(M, L), outer_r_m=ro.reshape(M, L), hair_mask=shell.reshape(M, L),
               drape_hit=(hairy & skin_hit & below).reshape(M, L), skin_hit=skin_hit.reshape(M, L),
               design_thickness_m=design.reshape(M, L), C=sc.C)
    # drape / lowest hair
    hv = (own_v == 2) | (own_v == 3)
    dl = np.arange(-175.0, 180.0, 10.0)
    low = np.full(len(dl), np.nan)
    if hv.any():
        P = Vg[hv]
        az = np.degrees(np.arctan2(P[:, 0] - sc.C[0], P[:, 2] - sc.C[2]))
        b = np.clip(((az + 180.0) // 10).astype(int), 0, len(dl) - 1)
        for k in range(len(dl)):
            m = b == k
            if m.any():
                low[k] = P[m, 1].min()
        r = np.random.default_rng(0)
        pts = P if len(P) <= 20000 else P[r.choice(len(P), 20000, replace=False)]
    else:
        pts = np.zeros((0, 3))
    env.update(drape_lon_deg=dl, drape_lowest_y=low, hair_points=pts)
    return env


def visibility(sc, grid):
    """Per welded skin vertex: visible iff the point 1 mm outside the GT skin is outside the final fused solid
    (the union SDF grid after cavity filling): hair, beard, drape, eyeballs, bust and filled interior
    surfaces (mouth bag, nasal pockets) all hide skin."""
    h = sc.h
    Nm = S.vertex_normals(sc.Pm, h.T)
    Nw = np.zeros((sc.nw, 3)); Nw[h.weld] = Nm
    X = sc.Pw + 0.001 * S.unit(Nw)
    vis = (grid_value(grid, X) > 0) & ~sc.mouth_only
    return vis, None


def observability(sc, vis):
    h = sc.h
    out = {}
    for c in CONTROLS:
        v = sc.v[c]
        Dp = np.zeros((sc.nw, 3)); Dp[h.weld] = h.deltas[f'id_{c}_p']
        Dn = np.zeros((sc.nw, 3)); Dn[h.weld] = h.deltas[f'id_{c}_n']
        wp = np.linalg.norm(Dp, axis=1); wn = np.linalg.norm(Dn, axis=1)
        w = wp if v > 0 else (wn if v < 0 else np.maximum(wp, wn))
        tot = w.sum()
        frac = float((w * vis).sum() / tot) if tot > 0 else 0.0
        sig = np.abs(v) * w
        vis_rms = float(np.sqrt((sig[vis & (w > 1e-4)] ** 2).mean()) * 1000) if (vis & (w > 1e-4)).any() else 0.0
        out[c] = {'visible_fraction': round(frac, 3), 'visible_rms_mm': round(vis_rms, 3),
                  'max_delta_mm_at_1': round(float(w.max() * 1000), 2),
                  'max_delta_mm_p': round(float(wp.max() * 1000), 2), 'max_delta_mm_n': round(float(wn.max() * 1000), 2),
                  'occluded': bool(frac < 0.5),
                  'partial': bool(0.5 <= frac < 0.8)}
    return out


def fidelity(sc, vis, Vg, Tg):
    """Distance from visible face-region GT skin vertices to the final reference surface (mm)."""
    import trimesh
    lon, lat = S.dir_lonlat(sc.Pw - sc.C)
    sel = vis & (np.abs(lon) < 75) & (lat < 40) & (lat > -75)
    idx = np.nonzero(sel)[0]
    if len(idx) > 2500:
        idx = idx[np.linspace(0, len(idx) - 1, 2500).astype(int)]
    lo = sc.Pw[idx].min(0) - 0.01; hi = sc.Pw[idx].max(0) + 0.01
    cen = Vg[Tg].mean(1)
    keep = np.all((cen > lo) & (cen < hi), 1)
    m = trimesh.Trimesh(Vg, Tg[keep], process=False)
    cp, dist, tri = trimesh.proximity.closest_point(m, sc.Pw[idx])
    return {'face_rms_mm': round(float(np.sqrt((dist ** 2).mean()) * 1000), 3),
            'face_p90_mm': round(float(np.percentile(dist, 90) * 1000), 3), 'n': int(len(idx))}


# ============================================================================ preview
def splat_preview(points, colors, path, size=420):
    from PIL import Image
    views = [('front', np.eye(3)), ('left', S.rot_y(-90)), ('back', S.rot_y(180)), ('3q', S.rot_y(-35))]
    lo = points.min(0); hi = points.max(0); ctr = (lo + hi) / 2
    ext = float(np.max(hi - lo)) * 0.55
    panels = []
    for name, R in views:
        Q = (points - ctr) @ R.T
        px = ((Q[:, 0] / ext + 1) * 0.5 * (size - 1)).astype(int)
        py = ((1 - (Q[:, 1] / ext + 1) * 0.5) * (size - 1)).astype(int)
        ok = (px >= 0) & (px < size) & (py >= 0) & (py < size)
        lin = py[ok] * size + px[ok]
        z = Q[ok, 2]
        o = np.lexsort((z, lin))
        lin, zc = lin[o], colors[ok][o]
        last = np.r_[lin[1:] != lin[:-1], True]
        img = np.full((size * size, 3), 40, np.uint8)
        img[lin[last]] = (zc[last] * 255).astype(np.uint8)
        panels.append(img.reshape(size, size, 3))
    Image.fromarray(np.concatenate(panels, 1)).save(path)


# ============================================================================ main per case
def pose(case, Vg):
    """Reference pose: Q (ref_from_game rotation), scale s (ref->game), offsets. Returns (Q, s, ctr, o_ref)."""
    r = np.random.default_rng(case['seed'] + 3)
    tilt = case['tilt']
    ax = S.unit(np.array([r.normal(), 0.0, r.normal()]))
    Rt = S.rot_axis(ax, tilt) if tilt else np.eye(3)
    Q = S.rot_y(case['yaw']) @ Rt
    if case['up'] == 'z':
        Q = S.YUP_TO_ZUP @ Q
    s = float(case['scale'])
    ctr = (Vg.min(0) + Vg.max(0)) / 2
    size_ref = float(np.max(Vg.max(0) - Vg.min(0))) / s
    o_ref = r.uniform(-0.25, 0.25, 3) * size_ref
    return Q, s, ctr, o_ref, ax


def make_case(case, out_root, log=print):
    t_start = time.time()
    cid = case['id']
    od = os.path.join(out_root, cid)
    os.makedirs(od, exist_ok=True)
    log(f'[{cid}] sex={case["sex"]} hair={case["hair"]} beard={case["beard"]} controls={case["controls"] if isinstance(case["controls"], str) else "sparse"}')
    h = S.load_head(case['sex'])
    sc = Scene(case, h)
    log(f'  scene ready ({len(sc.sP)} skin samples) {time.time() - t_start:.1f} s')
    V, T, grid = build_surface(sc, case['voxel'], log)
    want_uv = case['texture'] != 'vcolor'
    post = case['post']
    if post and post[0] == 'subdivide':
        import trimesh
        for _ in range(int(post[1])):
            V, T = trimesh.remesh.subdivide(V, T)
        log(f'  subdivided to {len(T)} tris')
        post_b = None
    else:
        post_b = post
    if want_uv or post_b:
        V, T, UVc = blender_post(V, T, post_b, want_uv, log)
    else:
        UVc = None
    # noise after the UV unwrap (the atlas is laid out on the smooth surface)
    V = add_noise(V, T, case['noise_mm'], case['seed'] + 5)
    measure_V, measure_T = V, T
    Nv = S.vertex_normals(V, T)
    painter = Painter(sc, case)
    images = []; materials = []
    res = 2048
    colours_texel = {}
    if want_uv:
        P_r, UV, T_r, src = split_by_uv(V, T, UVc)
        N_r = Nv[src]
        t0 = time.time()
        ti, bc, rr, cc = raster_uv(UV[T_r], res)
        tri = T_r[ti]
        Xt = (P_r[tri] * bc[:, :, None]).sum(1)
        Nt = S.unit((N_r[tri] * bc[:, :, None]).sum(1))
        col = np.zeros((len(Xt), 3)); lab = np.zeros(len(Xt), np.int64)
        for s0 in range(0, len(Xt), 600000):
            c_, l_, _ = painter.paint(Xt[s0:s0 + 600000], Nt[s0:s0 + 600000])
            col[s0:s0 + 600000] = c_; lab[s0:s0 + 600000] = l_
        srgb = S.linear_to_srgb(col)
        img = np.zeros((res, res, 3), np.float32); mask = np.zeros((res, res), np.float32)
        img[rr, cc] = srgb; mask[rr, cc] = 1
        log(f'  texture: {len(Xt)} texels ({len(Xt) / res / res * 100:.0f} % of 2K) {time.time() - t0:.1f} s')
        img = dilate_texture(img, mask)
        img8 = np.clip(np.round(img * 255), 0, 255).astype(np.uint8)
        fmt = 'JPEG' if case['texture'] == 'jpeg' else 'PNG'
        base_img = (S.png_bytes(img8, fmt, 90), 'image/jpeg' if fmt == 'JPEG' else 'image/png')
        from PIL import Image
        Image.fromarray(img8).save(os.path.join(od, 'texture_debug.' + ('jpg' if fmt == 'JPEG' else 'png')))
        prev_pts, prev_col = Xt, srgb
        texel_lab, texel_srgb = lab, srgb
        if case['extra_maps']:
            r = np.random.default_rng(case['seed'] + 9)
            nm = np.zeros((1024, 1024, 3), np.uint8); nm[..., 0] = 128; nm[..., 1] = 128; nm[..., 2] = 255
            nm[..., :2] = np.clip(128 + r.normal(0, 6, (1024, 1024, 2)), 0, 255)
            mr = np.zeros((1024, 1024, 3), np.uint8); mr[..., 1] = np.clip(200 + r.normal(0, 10, (1024, 1024)), 0, 255)
            images = [(S.png_bytes(nm), 'image/png'), (S.png_bytes(mr), 'image/png'), base_img]
            materials = [{'name': 'Material_0', 'pbrMetallicRoughness': {
                'baseColorTexture': {'index': 2}, 'metallicRoughnessTexture': {'index': 1},
                'metallicFactor': 1.0, 'roughnessFactor': 1.0}, 'normalTexture': {'index': 0}}]
        else:
            images = [base_img]
            materials = [{'name': 'Material_0', 'pbrMetallicRoughness': {
                'baseColorTexture': {'index': 0}, 'metallicFactor': 0.0, 'roughnessFactor': 1.0}}]
        VC = None
        P_out, N_out, UV_out, T_out = P_r, N_r, UV, T_r
    else:
        col, lab, _ = painter.paint(V, Nv)
        VC = np.c_[col, np.ones(len(col))]          # linear, per glTF COLOR_0
        materials = [{'name': 'Material_0', 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1],
                                                                       'metallicFactor': 0.0, 'roughnessFactor': 1.0}}]
        P_out, N_out, UV_out, T_out = V, Nv, None, T
        prev_pts, prev_col = V, S.linear_to_srgb(col)
        texel_lab, texel_srgb = lab, S.linear_to_srgb(col)
    # texel medians per class
    groups = {'skin_srgb': [0, 8], 'hair_srgb': [5], 'lip_srgb': [1], 'brow_srgb': [2], 'eye_srgb': [3],
              'clothing_srgb': [7], 'beard_srgb': [6], 'face_skin_srgb': [0]}
    for k, ids in groups.items():
        m = np.isin(texel_lab, ids)
        colours_texel[k] = [round(float(x), 4) for x in np.median(texel_srgb[m], 0)] if m.sum() > 20 else None
    # ---------------- pose into reference coordinates
    Q, s, ctr, o_ref, tilt_ax = pose(case, V)
    to_ref = lambda X: (X - ctr) @ Q.T / s + o_ref
    R_gt = Q.T
    t_gt = ctr - s * Q.T @ o_ref
    prims = []
    if case['split']:
        cen_y = P_out[T_out].mean(1)[:, 1]
        cut = sc.rim_lo - 0.02
        for name, sel in (('Mesh_head', cen_y >= cut), ('Mesh_body', cen_y < cut)):
            Ts = T_out[sel]
            Pv, Ts2, used = S.compact(P_out, Ts)
            prims.append({'name': name, 'P': to_ref(Pv), 'N': N_out[used] @ Q.T,
                          'UV': UV_out[used] if UV_out is not None else None,
                          'COL': VC[used] if VC is not None else None, 'T': Ts2, 'material': 0})
    else:
        prims.append({'name': 'Mesh_0', 'P': to_ref(P_out), 'N': N_out @ Q.T, 'UV': UV_out, 'COL': VC,
                      'T': T_out, 'material': 0})
    glb = os.path.join(od, 'reference.glb')
    nbytes = S.write_glb(glb, prims, images, materials, generator='RL synthetic Meshy-like reference')
    log(f'  wrote {glb} ({nbytes / 1e6:.1f} MB, {len(T_out)} tris)')
    # check the mapping on the written data (float32 round trip)
    map_err = 0.0
    if not case['split']:
        chk = s * (np.asarray(prims[0]['P'], np.float32).astype(np.float64) @ R_gt.T) + t_gt
        map_err = float(np.abs(chk - P_out).max())
    # ---------------- ground truth measures (game space)
    own_v, _, _ = sc.owner_info(measure_V)
    env = envelope_truth(sc, measure_V, measure_T, own_v)
    t0 = time.time()
    vis, _ = visibility(sc, grid)
    del grid
    obs = observability(sc, vis)
    fid = fidelity(sc, vis, measure_V, measure_T)
    log(f'  truth measures {time.time() - t0:.1f} s')
    hair_present = case['hair'] is not None
    thick = env['thickness_m']
    scalp_w = np.zeros(sc.nw, bool); scalp_w[h.weld[h.vgroups['scalp']]] = True
    lon_s, lat_s = S.dir_lonlat(sc.Bw[scalp_w] - sc.C)
    li = np.clip(np.round((wrap180(lon_s) + 180) / 2.5).astype(int) % len(env['lon_deg']), 0, len(env['lon_deg']) - 1)
    la = np.clip(np.round((lat_s + 75) / 2.5).astype(int), 0, len(env['lat_deg']) - 1)
    coverage = float(env['hair_mask'][la, li].mean()) if hair_present else 0.0
    hv = (own_v == 2) | (own_v == 3)
    beard_present = case['beard'] is not None
    zone = sc.beard_zone > 0.5
    beard_cov = 0.0
    if beard_present:
        bt = np.zeros(sc.nw); bt[:] = sc.beard_t
        beard_cov = float(((bt > 0.001) & zone).sum() / max(zone.sum(), 1))
    occluded = [c for c in CONTROLS if obs[c]['occluded']]
    truth = {
        'case': cid, 'sex': case['sex'], 'reference': 'reference.glb',
        'stresses': case['stresses'],
        'clean': bool(case['noise_mm'] == 0 and not (post and post[0] == 'decimate')),
        'extreme': case['controls'] == 'extreme',
        'controls_kind': case['controls'] if isinstance(case['controls'], str) else 'sparse',
        'controls': {c: round(sc.v[c], 4) for c in CONTROLS},
        'transform': {'scale': s, 'R': R_gt.tolist(), 't': [float(x) for x in t_gt]},
        'orientation': {'up': case['up'], 'yaw_deg': float(case['yaw']), 'tilt_deg': float(case['tilt']),
                        'tilt_axis_game': [float(x) for x in tilt_ax],
                        'face_dir_ref': [float(x) for x in Q @ [0, 0, 1.0]],
                        'up_dir_ref': [float(x) for x in Q @ [0, 1.0, 0]],
                        'note': 'yaw_deg: the game-space model was rotated by +yaw about game Y (face +Z -> '
                                '(sin yaw, 0, cos yaw)) before the tilt and, for up=z, the Y-up->Z-up conversion '
                                '(x, y, z) -> (x, -z, y). Compare rotations through R, not yaw conventions.'},
        'generation': {'voxel_mm': case['voxel'] * 1000, 'post': list(post) if post else None,
                       'noise_mm': case['noise_mm'], 'texture': case['texture'], 'baked_light': case['light'],
                       'extra_maps': case['extra_maps'], 'split_meshes': case['split'], 'tris': int(len(T_out)),
                       'verts': int(len(P_out)), 'glb_bytes': int(nbytes), 'seconds': None,
                       'max_map_error_m': map_err},
        'hair': {'present': hair_present, 'style': case['hair'], 'coverage': round(coverage, 3),
                 'max_thickness_mm': round(float(np.nanmax(thick) * 1000), 2) if np.isfinite(thick).any() else 0.0,
                 'lowest_y': round(float(measure_V[hv, 1].min()), 4) if hv.any() else None,
                 'below_rim': bool(hv.any() and measure_V[hv, 1].min() < sc.rim_lo),
                 'expected_nearest_style': EXPECTED_STYLE.get(case['hair'], ['none'])},
        'beard': {'present': beard_present, 'style': case['beard'], 'coverage': round(beard_cov, 3),
                  'expected_nearest_style': EXPECTED_BEARD.get(case['beard'], ['none'])},
        'colours': {'skin_srgb': list(case['skin']), 'hair_srgb': list(case['hair_c']) if hair_present else None,
                    'lip_srgb': list(case['lip_c']), 'brow_srgb': list(case['brow_c']), 'eye_srgb': list(case['eye_c']),
                    'clothing_srgb': list(case['cloth']),
                    'beard_srgb': [round(float(x), 4) for x in S.linear_to_srgb(painter.alb['beard'])] if beard_present else None},
        'colours_texel_median': colours_texel,
        'observability': obs, 'occluded_controls': occluded,
        'fidelity': fid,
        'envelope_file': 'truth_envelope.npz',
        'head': {'C': [float(x) for x in sc.C], 'R': float(h.R), 'rim_y_min': sc.rim_lo, 'rim_y_max': sc.rim_hi},
        'definitions': DEFINITIONS,
    }
    np.savez_compressed(os.path.join(od, 'truth_envelope.npz'), **env)
    splat_preview(prev_pts[:: max(1, len(prev_pts) // 1500000)], prev_col[:: max(1, len(prev_pts) // 1500000)],
                  os.path.join(od, 'preview.png'))
    truth['generation']['seconds'] = round(time.time() - t_start, 1)
    with open(os.path.join(od, 'truth.json'), 'w', encoding='utf-8') as f:
        json.dump(truth, f, indent=1)
    log(f'  done in {time.time() - t_start:.1f} s; occluded={occluded}; fidelity={fid}; '
        f'hair max {truth["hair"]["max_thickness_mm"]} mm lowest_y {truth["hair"]["lowest_y"]}')
    return truth


DEFINITIONS = {
    'transform': 'x_game = scale * R @ x_ref + t; x_ref = GLB POSITION (all node transforms identity); game space = '
                 'RL head module space (metres, Y up, face +Z).',
    'controls': 'id_<c>_p weight max(v,0), id_<c>_n weight max(-v,0) on the RL LOD0 skin (build/v1, headref.Head).',
    'envelope': 'rays from headref h.C (base head) along lonlat_dir(lon,lat); skin_r = outermost hit on the GT-morphed '
                'skin without ears (headref noear); outer_r = outermost hit on the reference surface in game space; '
                'thickness_m = outer_r - skin_r where the outer hit is hair-owned, NaN otherwise or if the skin ray misses.',
    'drape': 'drape_lowest_y[k] = min game y of hair-owned reference vertices with azimuth atan2(x-C.x, z-C.z) in the '
             '10 deg bin centred on drape_lon_deg[k] (NaN if none).',
    'colours': 'albedo sRGB 0-1 before painterly variation / baked light (colours); colours_texel_median = per-class '
               'median of generated texels (COLOR_0 case: of vertex colours converted to sRGB).',
    'COLOR_0': 'vertex colours are written LINEAR (glTF spec); convert to sRGB before comparing.',
    'observability': 'visible_fraction = |delta|-weighted share of skin vertices not covered by hair/beard/drape/eyes/'
                     'bust; < 0.5 => occluded (excluded from control gates for that case).',
    'fidelity': 'distance from visible face-region GT skin vertices to the reference surface (remesh/noise floor).',
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cases', default='all')
    ap.add_argument('--out', default=S.CASES_DIR)
    ap.add_argument('--list', action='store_true')
    a = ap.parse_args()
    if a.list:
        for c in CASES:
            print(c['id'], c['sex'], '|', '; '.join(c['stresses']))
        return 0
    sel = CASES if a.cases == 'all' else [c for c in CASES if c['id'] in a.cases.split(',') or
                                           any(c['id'].startswith(x) for x in a.cases.split(','))]
    os.makedirs(a.out, exist_ok=True)
    index = []
    for c in sel:
        t = make_case(c, a.out)
        index.append({'case': t['case'], 'sex': t['sex'], 'clean': t['clean'], 'extreme': t['extreme'],
                      'stresses': t['stresses']})
    # merge the index with existing cases
    ip = os.path.join(a.out, 'index.json')
    old = json.load(open(ip)) if os.path.exists(ip) else []
    keep = {e['case']: e for e in old}
    for e in index:
        keep[e['case']] = e
    json.dump(sorted(keep.values(), key=lambda e: e['case']), open(ip, 'w'), indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
