# Deterministic rebuild of NC_cape from the raw Meshy cape (collection 'cape_back'), on M_BodyRoot (canonical rig, rest).
import bpy, bmesh, numpy as np, math
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
exec(open(SCR + "/cape_weights_blender.py").read())
arm = bpy.data.objects['M_BodyRoot']
for cn in ('dev_male', 'dev_female'):
    a = next(o for o in bpy.data.collections[cn].objects if o.type == 'ARMATURE'); a.data.pose_position = 'REST'
bpy.context.view_layer.update()
Y0 = 0.02
src = bpy.data.collections['cape_back'].objects[0]
coll = bpy.data.collections['new_cape']
old = bpy.data.objects.get('NC_cape')
mats = list(old.data.materials) if old else []
if old:
    bpy.data.objects.remove(old, do_unlink=True)
nc = src.copy(); nc.data = src.data.copy(); nc.name = 'NC_cape'; coll.objects.link(nc)
for c in list(nc.users_collection):
    if c != coll:
        c.objects.unlink(nc)
me = nc.data; me.transform(src.matrix_world); nc.matrix_world = Matrix.Identity(4)
for m in nc.modifiers[:]:
    nc.modifiers.remove(m)

# 1. weld, centre, scale to 1.30 m, collar top 1.60, collar ring centred on the neck
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5); bm.to_mesh(me); bm.free()
co = np.array([tuple(v.co) for v in me.vertices]); me.transform(Matrix.Translation((-(co[:, 0].min() + co[:, 0].max()) / 2, 0, 0)))
co = np.array([tuple(v.co) for v in me.vertices]); me.transform(Matrix.Scale(1.30 / (co[:, 2].max() - co[:, 2].min()), 4))
co = np.array([tuple(v.co) for v in me.vertices]); top = co[:, 2].max(); rc = co[co[:, 2] > top - 0.06].mean(0)
me.transform(Matrix.Translation((-rc[0], 0.035 - rc[1], 1.60 - top)))

# 2. collar -> back arc of +-105 degrees, blended in from z 1.43 to 1.48
for v in me.vertices:
    if v.co.z < 1.43:
        continue
    t = min(1.0, (v.co.z - 1.43) / 0.05); t = t * t * (3 - 2 * t)
    th = math.atan2(v.co.x, v.co.y - Y0); r = math.hypot(v.co.x, v.co.y - Y0); th2 = th * (1 - t + t * 105 / 180)
    v.co.x = r * math.sin(th2); v.co.y = Y0 + r * math.cos(th2)

# 3. planar cut in front of the neck (collar band only), flat caps on the cut
bm = bmesh.new(); bm.from_mesh(me)
# faces that crossed the ring's front seam now span the remapped ends through the neck
chords = []
for f in bm.faces:
    if min(v.co.z for v in f.verts) < 1.40:
        continue
    th = [math.degrees(math.atan2(v.co.x, v.co.y - Y0)) for v in f.verts]
    if max(th) - min(th) > 120 and max(th) > 60 and min(th) < -60:
        chords.append(f)
bmesh.ops.delete(bm, geom=chords, context='FACES')
band = [f for f in bm.faces if max(v.co.z for v in f.verts) > 1.38]
geom = list({v for f in band for v in f.verts}) + list({e for f in band for e in f.edges}) + band
res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=(0, Y0 - 0.03, 0), plane_no=(0, -1, 0), clear_outer=True)
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context='VERTS')
# Each collar end is its own boundary loop; cap a loop only if it stays on one
# side of the neck (a loop crossing x = 0 would put a sheet through the neck).
boundary = {e for e in bm.edges if e.is_boundary and min(v.co.z for v in e.verts) > 1.36}
filled = []
while boundary:
    loop = []; stack = [boundary.pop()]
    while stack:
        e = stack.pop(); loop.append(e)
        for v in e.verts:
            for e2 in v.link_edges:
                if e2 in boundary:
                    boundary.discard(e2); stack.append(e2)
    xs_ = [v.co.x for e in loop for v in e.verts]
    if min(xs_) > 0.02 or max(xs_) < -0.02:
        filled += bmesh.ops.holes_fill(bm, edges=loop, sides=0)['faces']
bmesh.ops.triangulate(bm, faces=filled)
bm.to_mesh(me); bm.free(); me.update()

# 4. clearance: behind the old (armour-safe) cape's inner line, full below 1.44, 35% in the collar band
oc = bpy.data.objects['OC_Cape']; OM = np.array(oc.matrix_world)
oco = np.array([tuple(v.co) for v in oc.data.vertices]) @ OM[:3, :3].T + OM[:3, 3]
oco[:, 0] -= bpy.data.objects['OC_rig'].location.x
co = np.array([tuple(v.co) for v in me.vertices])
xs = np.linspace(-0.30, 0.30, 13); zs = np.arange(0.86, 1.50, 0.03); need = np.zeros((len(zs), len(xs)))
for i, z in enumerate(zs):
    for j, x in enumerate(xs):
        o_ = oco[(np.abs(oco[:, 0] - x) < 0.035) & (np.abs(oco[:, 2] - z) < 0.035)]
        c_ = co[(np.abs(co[:, 0] - x) < 0.035) & (np.abs(co[:, 2] - z) < 0.035) & (co[:, 1] > Y0) & (co[:, 2] < 1.47)]
        if len(o_) and len(c_):
            need[i, j] = max(0.0, o_[:, 1].min() - c_[:, 1].min())
dil = np.array([[need[max(0, i - 1):i + 2, max(0, j - 1):j + 2].max() for j in range(len(xs))] for i in range(len(zs))])


def field(x, z):
    w = np.exp(-(((xs[None, :] - x) / 0.06) ** 2 + ((zs[:, None] - z) / 0.06) ** 2))
    return float((w * dil).sum() / max(w.sum(), 1e-9))


def ramp(z):
    return 1.0 if z <= 1.44 else 1.0 - 0.65 * min(1.0, (z - 1.44) / 0.08)


for v in me.vertices:
    x, y, z = v.co
    if y > Y0 - 0.06:
        d = field(x, min(z, 1.47)) * ramp(z)
        if z < 0.95:
            d *= max(0.0, min(1.0, (z - 0.80) / 0.15))
        v.co.y += d

# 5. shoulder taper: cloth beyond 12 cm from the centre line drawn in over the shoulders
for v in me.vertices:
    ax = abs(v.co.x)
    if ax > 0.12 and v.co.z > 1.22:
        t = min(1.0, (v.co.z - 1.22) / 0.20); t = t * t * (3 - 2 * t)
        v.co.x = math.copysign(0.12 + (ax - 0.12) * (1.0 - 0.30 * t), v.co.x)
me.update()
nc.parent = arm; nc.matrix_parent_inverse = Matrix.Identity(4); nc.matrix_basis = Matrix.Identity(4)

# 6. decimate to ~6k triangles, keeping UV islands
bpy.context.view_layer.objects.active = nc
dec = nc.modifiers.new('Decimate', 'DECIMATE'); dec.decimate_type = 'COLLAPSE'; dec.ratio = 0.40
dec.use_collapse_triangulate = True; dec.delimit = {'UV', 'SEAM'}
area = next(a for a in bpy.context.window.screen.areas if a.type == 'VIEW_3D')
with bpy.context.temp_override(area=area, object=nc, active_object=nc, selected_objects=[nc]):
    bpy.ops.object.modifier_apply(modifier='Decimate')

# 7. materials: trim by texture darkness (smoothed), lining by outward occlusion, cleaned
img = next(n.image for n in src.data.materials[0].node_tree.nodes if n.type == 'TEX_IMAGE')
W, H = img.size; px = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(px); lum = px.reshape(H, W, 4)[..., :3].mean(2)
uvl = me.uv_layers.active.data; uv = np.empty(len(uvl) * 2, np.float32); uvl.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
nf = len(me.polygons); face_lum = np.zeros(nf)
for p in me.polygons:
    t = uv[p.loop_start:p.loop_start + p.loop_total]
    pts = np.concatenate([t, t.mean(0, keepdims=True), (t + t.mean(0)) / 2])
    xx = np.clip((pts[:, 0] % 1) * (W - 1), 0, W - 1).astype(int); yy = np.clip((pts[:, 1] % 1) * (H - 1), 0, H - 1).astype(int)
    face_lum[p.index] = lum[yy, xx].mean()
bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
nb = [[f2.index for e in f.edges for f2 in e.link_faces if f2.index != f.index] for f in bm.faces]; bm.free()
dark = face_lum < np.percentile(face_lum, 50) * 0.80
for _ in range(2):
    new = dark.copy()
    for k in range(nf):
        if nb[k]:
            fr = np.mean([dark[j] for j in nb[k]])
            new[k] = True if fr > 0.6 else (False if fr < 0.25 else dark[k])
    dark = new
bvh = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
inner = np.zeros(nf, bool)
for p in me.polygons:
    c = p.center; r = Vector((c.x, c.y - Y0, 0.0))
    if r.length < 1e-4 or c.z > 1.47:
        continue
    d = r.normalized(); hit = bvh.ray_cast(c + d * 0.002, d, 0.25)
    if hit[0] is not None and hit[2] != p.index:
        inner[p.index] = True
lab = np.where(dark, 1, np.where(inner, 2, 0))
for _ in range(3):
    new = lab.copy()
    for k in range(nf):
        if not nb[k]:
            continue
        f2 = np.mean([lab[j] == 2 for j in nb[k]])
        if lab[k] == 2 and f2 < 0.34:
            new[k] = 0
        elif lab[k] == 0 and f2 > 0.67:
            new[k] = 2
    lab = new
seen = np.zeros(nf, bool)
for s in range(nf):
    if lab[s] != 2 or seen[s]:
        continue
    comp = [s]; seen[s] = True; i = 0
    while i < len(comp):
        for j in nb[comp[i]]:
            if lab[j] == 2 and not seen[j]:
                seen[j] = True; comp.append(j)
        i += 1
    if len(comp) < 150:
        lab[comp] = 0
dirs = [Vector((math.sin(a), math.cos(a), e)).normalized() for a in np.radians([-60, -30, 0, 30, 60]) for e in (0.0, 0.4)]
for p in me.polygons:
    if lab[p.index] == 2 and sum(bvh.ray_cast(p.center + d * 2.0, -d, 2.5)[2] == p.index for d in dirs) >= 2:
        lab[p.index] = 0
# cap faces (no UVs) take the cloth material and their neighbours' UVs
bm = bmesh.new(); bm.from_mesh(me); uvb = bm.loops.layers.uv.active; bm.faces.ensure_lookup_table()
caps = 0
for f in bm.faces:
    if all(l[uvb].uv.length < 1e-9 for l in f.loops):
        lab[f.index] = 0; caps += 1
        for l in f.loops:
            o = [ol for ol in l.vert.link_loops if ol.face is not f and ol[uvb].uv.length > 1e-9]
            if o:
                l[uvb].uv = o[0][uvb].uv.copy()
bm.to_mesh(me); bm.free()
me.materials.clear()
for m in mats:
    me.materials.append(m)
me.polygons.foreach_set('material_index', lab.astype(np.int32)); me.update()

# 8. shoulder ledge: the collar remap (1.43-1.48) meets full-width cloth, leaving a
# 2.5 cm step in the outline at z 1.44-1.46 that reads as a spike from behind.
# Scale the outer cloth (|x| > 10 cm) across to a smooth envelope, 19.5 -> 16 cm
# half-width over z 1.34-1.46.
co = np.array([tuple(v.co) for v in me.vertices])
zs = np.arange(1.25, 1.62, 0.005)
sm = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))
env = 0.195 - 0.035 * sm((zs - 1.34) / 0.12)
for side in (-1, 1):
    mw = np.array([np.abs(co[(np.abs(co[:, 2] - z) < 0.015) & (np.sign(co[:, 0]) == side), 0]).max(initial=0.10) for z in zs])
    s = np.minimum(1.0, (env - 0.10) / np.maximum(mw - 0.10, 1e-6)); s[zs < 1.33] = 1.0
    for v in me.vertices:
        x, y, z = v.co
        if np.sign(x) == side and abs(x) > 0.10 and 1.30 <= z <= 1.50:
            v.co.x = side * (0.10 + (abs(x) - 0.10) * min(1.0, float(np.interp(z, zs, s))))
me.update()
# 9. one consistent winding over the whole shell (decimation leaves a few faces turned)
bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(me); bm.free(); me.update()
# 10. weights last, on the final positions (cape_weights_blender.py: continuous across the chains)
cape_weight(nc, arm)
for cn in ('dev_male', 'dev_female'):
    a = next(o for o in bpy.data.collections[cn].objects if o.type == 'ARMATURE'); a.data.pose_position = 'POSE'
bm = bmesh.new(); bm.from_mesh(me)
longest = sorted(((round(e.calc_length(), 3), tuple(round(x, 3) for x in (e.verts[0].co + e.verts[1].co) / 2))
                  for e in bm.edges if min(v.co.z for v in e.verts) > 1.3), reverse=True)[:5]
boundary = sum(1 for e in bm.edges if e.is_boundary); bm.free()
result = {"faces": nf, "base": int((lab == 0).sum()), "trim": int((lab == 1).sum()), "lining": int((lab == 2).sum()),
          "caps": caps, "boundary": boundary, "longest_top_edges": longest}
