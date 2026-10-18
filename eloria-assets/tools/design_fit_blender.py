"""Fit a generated armour set as one design: build rest-pose shell overrides in Blender.

    blender -b --factory-startup --python eloria-assets/tools/design_fit_blender.py -- \
        --spec eloria-assets/source/equipment-design-fit/phoenix.json \
        --body godot-client/assets/actors/native/races/luminous_male.glb \
        --sources <generate_models/meshy-armor-individual-glb> \
        --out eloria-assets/source/equipment-design-fit/luminous_male [--previews <dir>]

Added 2026-10-16.  The torso and limb remappers fit every piece on its own, so
pieces of one set are seated by different rules and lose the proportions the
concept gave them (a skirt flared to clear the legs, sleeves scaled with the
arm length).  This fits a set the way it was drawn, on the body that wears it:

1. Pose the body in the game's idle (the library ``Idle_Subtle``, copied as
   world deltas from ``Rest_Pose`` exactly as the client does; posekit.py).
2. Every vertex of a raw Meshy piece rides the design bone it belongs to (a
   skeleton read off the concept-pose mesh and recorded in the set spec).  Each
   design bone is carried onto its body bone by a similarity: rotate the bone
   direction onto the body's, scale the cross-section by the piece's one girth
   scale, stretch only along the bone to the body's segment length.  Weights
   blend bones by distance in units of each segment's radius.
3. Clearance is solved per bone, never per vertex.  Rays leave the posed body
   bone's axis through every body vertex the bone carries and meet the bone's
   own shell from outside; a ridge-damped least-squares shift centres the
   shell and one girth factor grows it until most skin sits `clear` inside.
   A shell far inside the skin is a designed opening or an inner lining and
   says nothing (growing over it would balloon the segment).
4. Skin weights come from the posed body surface nearest each vertex, scoped
   to the body bones the design bone may inherit from, smoothed over the
   shell; small welded plates are made rigid.  Rest positions invert linear
   blend skinning at the idle pose, so the client's own skinning returns the
   fitted shell exactly in idle.

Added 2026-10-17 for the class starter kits, whose boots are their own
sources; each is opt-in per spec, so the Phoenix fit is unchanged.  A torso's
``split_limbs`` gives sleeves hanging against the coat their surface, not the
nearest bone (split_limbs).  A bone's ``surfaces`` limits which body surfaces
its clearance clears (a boot shaft clears the default boot, not the trouser
leg it hides).  ``ground`` seats separate boots' soles in the rest pose where
limb_head_remap seats them (seat_soles).  ``tuck_into`` layers one piece
inside another of the same set, such as trouser legs inside the boots (tuck);
it may name several pieces, as trousers tucked into both coat and boots.
Later the same day, after the owner's review: ``conform`` lets a coat front
follow the chest it covers on the bodies it names (conform), and ``drape``
hangs tails from the belt instead of binding them to the leg behind (drape);
``collar`` brings a collar's back out of the neck it was fitted into (collar);
``twist`` lets a coat's waist turn with the chest (twist), and
``centre_cuffs`` puts each sleeve's end on its wrist (centre_cuffs).

The output per source is ``<source>.npz``: rest positions in glTF axes,
four joint names and weights per vertex, and a keep mask for triangles
(bridges that the rest pose would stretch are opened; the fitted backing closes
them).  ``design_fit.py`` hands these to torso_remap / limb_head_remap, which
still build the backings, normals, materials and GLB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

TOOLS = Path(__file__).resolve().parent
CLIENT = TOOLS.parent.parent
LIBRARY = CLIENT / "godot-client/assets/actors/native/shared/Universal_Animation_Library.glb"
POSEKIT = TOOLS / "shared_cape/posekit.py"
SURFACES = ("body", "wardrobe_shirt", "wardrobe_pants", "wardrobe_boots")
#: 2 (2026-10-17): adds arm_share and the idle skinning matrices (skin).
FORMAT = 2
#: Blender (x, y, z) -> glTF (x, z, -y), as a 4x4 change of basis.
AXES = np.array([[1., 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])


def args_after_dashes():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--body", type=Path, required=True)
    ap.add_argument("--sources", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--library", type=Path, default=LIBRARY)
    ap.add_argument("--pose", default="Idle_Subtle")
    ap.add_argument("--previews", type=Path)
    return ap.parse_args(argv)


def wipe():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)


def import_into(path, cname, keep_actions=False):
    scn = bpy.context.scene
    coll = bpy.data.collections.new(cname); scn.collection.children.link(coll)
    before = set(bpy.data.objects); acts = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    if not keep_actions:
        for a in list(bpy.data.actions):
            if a not in acts:
                bpy.data.actions.remove(a)
    # Background Blender adds its startup icosphere on the first import.
    for o in list(new):
        if o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o, do_unlink=True); new.remove(o)
    return new


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rot_between(a, b):
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(np.dot(a, b)); s = np.linalg.norm(v)
    if s < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def seg_proj(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return a + t[:, None] * ab, t


class Body:
    """The posed wearer: joints, skinning matrices and weighted surface samples."""

    def __init__(self, path, library, pose):
        import_into(library, "lib", keep_actions=True)
        new = import_into(path, "body")
        self.arm = next(o for o in new if o.type == "ARMATURE")
        self.arm.animation_data_clear()
        self.meshes = {o.name.split(".")[0]: o for o in new if o.type == "MESH"}
        bpy.context.view_layer.update()
        exec(compile(POSEKIT.read_text(), str(POSEKIT), "exec"), globals())
        pose_armature(self.arm, action=pose, frame=0, style=False)  # noqa: F821 (posekit)
        bpy.context.view_layer.update()
        self.bones = [b.name for b in self.arm.data.bones if b.use_deform]
        self.index = {n: i for i, n in enumerate(self.bones)}
        AW = np.array(self.arm.matrix_world); AWi = np.linalg.inv(AW)
        self.skin = np.zeros((len(self.bones), 4, 4))
        for n, i in self.index.items():
            pb = self.arm.pose.bones[n]
            self.skin[i] = AW @ np.array(pb.matrix) @ np.linalg.inv(np.array(pb.bone.matrix_local)) @ AWi
        dg = bpy.context.evaluated_depsgraph_get()
        pos, rows, surface, rest = [], [], [], []
        verts, polys = [], []
        for name in SURFACES:
            o = self.meshes[name]
            groups = [g.name for g in o.vertex_groups]
            ev = o.evaluated_get(dg); me = ev.to_mesh()
            P = [(o.matrix_world @ v.co)[:] for v in me.vertices]
            polys += [[len(verts) + i for i in f.vertices] for f in me.polygons]
            verts += [Vector(p) for p in P]
            ev.to_mesh_clear()
            for v, p in zip(o.data.vertices, P):
                r = (o.matrix_world @ v.co)[:]
                row = np.zeros(len(self.bones))
                for g in v.groups:
                    if groups[g.group] in self.index:
                        row[self.index[groups[g.group]]] += g.weight
                if row.sum() > 0:
                    pos.append(p); rows.append(row / row.sum()); surface.append(name); rest.append(r)
        self.points = np.array(pos)
        self.bvh = BVHTree.FromPolygons(verts, polys)
        self.rest_points = np.array(rest)
        self.surface = np.array(surface)
        self.weights = np.array(rows)
        self.dominant = np.array(self.bones)[self.weights.argmax(1)]

    def joint(self, ref):
        if "|" in ref:
            a, b, t = ref.split("|")
            return self.joint(a) * (1 - float(t)) + self.joint(b) * float(t)
        end = "tail" if ref.endswith(".tail") else "head"
        pb = self.arm.pose.bones[ref[:-5] if end == "tail" else ref]
        return np.array((self.arm.matrix_world @ (pb.tail if end == "tail" else pb.head))[:])


def split_limbs(P, tris, q, w, ps):
    """Give each limb the surface joined to it, not just the nearest design bone.

    Where a sleeve hangs against the coat, its inner wall can be nearer the
    trunk axis than the arm's, and the coat's side nearer the arm's: distance
    alone hands each to the wrong bone, so in a stride the sleeve wall stays
    with the chest and the coat's side swings with the arm.  As torso_remap's
    connected_sleeve does, surface (welded-graph) distance decides instead:
    seeds on each limb's outer wall and on the coat's middle strip
    (``trunk_seed_x``) grow over the mesh, each vertex joins the nearer seed
    set, and blending keeps to its own group's bones.  A few rounds of graph
    smoothing (``split_smooth``) soften the armhole seam.
    Bones carry ``"limb": "<name>"``; bones without one are the trunk.
    """
    import heapq
    bones = ps["bones"]
    group = [b.get("limb", "") for b in bones]
    names = sorted(set(group))
    canon, n, pairs = welded_graph(P, tris)
    first = np.zeros(n, int); first[canon] = np.arange(len(P))
    length = np.linalg.norm(P[first[pairs[:, 0]]] - P[first[pairs[:, 1]]], axis=1)
    adj = [[] for _ in range(n)]
    for (a, b), d in zip(pairs, length):
        adj[a].append((b, d)); adj[b].append((a, d))
    trunk_x = float(ps.get("trunk_seed_x", 0.12))
    dist = {}
    for g in names:
        cols = [i for i, x in enumerate(group) if x == g]
        own = w[:, cols].sum(1)
        if g == "":
            # the middle strip of the coat, front, back and collar
            seeds = (np.abs(P[:, 0]) < trunk_x) & (own > 0.98)
        else:
            # the limb's outer wall, which no coat panel reaches
            seeds = np.zeros(len(P), bool)
            for i in cols:
                dh = np.array(bones[i]["design"][0], float); dt = np.array(bones[i]["design"][1], float)
                foot, _ = seg_proj(P, dh, dt)
                out_x = np.sign(dh[0] + dt[0]) * (P[:, 0] - foot[:, 0])
                seeds |= (out_x > 0.3 * float(bones[i]["radius"])) & (q[:, i] < 2.0)
            seeds &= own > 0.9
        d = np.full(n, np.inf)
        heap = [(0.0, int(c)) for c in np.unique(canon[seeds])]
        for _, c in heap:
            d[c] = 0.0
        heapq.heapify(heap)
        while heap:
            dc, c = heapq.heappop(heap)
            if dc > d[c]:
                continue
            for nb, dl in adj[c]:
                if dc + dl < d[nb]:
                    d[nb] = dc + dl; heapq.heappush(heap, (dc + dl, nb))
        dist[g] = d[canon]
    owner = np.array(names)[np.argmin(np.stack([dist[g] for g in names], 1), 1)]
    tau = float(ps.get("tau", 0.15))
    out = np.zeros_like(w)
    for g in names:
        cols = np.array([i for i, x in enumerate(group) if x == g])
        rows = owner == g
        qq = q[np.ix_(rows, cols)]
        ww = np.exp(-(qq - qq.min(1, keepdims=True)) / tau)
        out[np.ix_(rows, cols)] = ww / ww.sum(1, keepdims=True)
    for _ in range(int(ps.get("split_smooth", 2))):
        acc = np.zeros((n, w.shape[1])); np.add.at(acc, canon, out)
        cnt = np.bincount(canon, minlength=n).astype(float)
        node = acc / cnt[:, None]
        nb_acc = node.copy(); nb_cnt = np.ones(n)
        np.add.at(nb_acc, pairs[:, 0], node[pairs[:, 1]]); np.add.at(nb_acc, pairs[:, 1], node[pairs[:, 0]])
        np.add.at(nb_cnt, pairs[:, 0], 1); np.add.at(nb_cnt, pairs[:, 1], 1)
        out = (nb_acc / nb_cnt[:, None])[canon]
    return out / out.sum(1, keepdims=True)


def fit_piece(body, P, tris, ps):
    """Carry one source piece onto the posed body; returns posed points, design weights, report."""
    s = float(ps["scale"])
    bones = ps["bones"]
    maps, q = [], []
    for b in bones:
        dh = np.array(b["design"][0], float); dt = np.array(b["design"][1], float)
        bh = body.joint(b["body"][0]) + np.array(b.get("offset", (0, 0, 0)), float)
        bt = body.joint(b["body"][1]) + np.array(b.get("offset_tail", b.get("offset", (0, 0, 0))), float)
        d_dir = dt - dh; b_dir = bt - bh
        sb = float(b.get("scale", s))
        k = float(np.clip(np.linalg.norm(b_dir) / (sb * np.linalg.norm(d_dir)),
                          b.get("kmin", 0.6), b.get("kmax", 1.6)))
        u = d_dir / np.linalg.norm(d_dir)
        M = rot_between(d_dir, b_dir) @ (sb * (np.eye(3) + (k - 1) * np.outer(u, u)))
        maps.append({"dh": dh, "bh": bh, "bt": bt, "M": M, "n": b_dir / np.linalg.norm(b_dir),
                     "t": np.zeros(3), "g": 1.0, "k": k})
        foot, _ = seg_proj(P, dh, dt)
        q.append(np.linalg.norm(P - foot, axis=1) / float(b["radius"]))
    q = np.stack(q, 1)
    w = np.exp(-(q - q.min(1, keepdims=True)) / float(ps.get("tau", 0.15)))
    w /= w.sum(1, keepdims=True)
    if ps.get("split_limbs"):
        w = split_limbs(P, tris, q, w, ps)
    dom = w.argmax(1)

    def place():
        out = np.zeros_like(P)
        for i, m in enumerate(maps):
            local = (m["M"] @ (P - m["dh"]).T).T
            radial = local - np.outer(local @ m["n"], m["n"])
            out += w[:, i:i + 1] * (m["bh"] + m["t"] + local + (m["g"] - 1) * radial)
        return out

    out = place()
    report = {}
    for _ in range(int(ps.get("iters", 3))):
        for i, (b, m) in enumerate(zip(bones, maps)):
            covers = b.get("covers")
            faces = tris[np.all(dom[tris] == i, axis=1)]
            if not covers or len(faces) < 8:
                report[b["name"]] = {"skipped": "no covers or own faces", "faces": int(len(faces))}
                continue
            bvh = BVHTree.FromPolygons([Vector(p) for p in out], faces.tolist())
            sel = np.isin(body.dominant, covers)
            if "surfaces" in b:
                # e.g. a boot shaft clears the default boot, not the trouser leg it hides
                sel &= np.isin(body.surface, b["surfaces"])
            if "zmin" in b:
                sel &= body.points[:, 2] >= b["zmin"]
            if "zmax" in b:
                sel &= body.points[:, 2] <= b["zmax"]
            pts = body.points[sel]
            if len(pts) < 10:
                report[b["name"]] = {"skipped": "body samples", "samples": int(len(pts))}
                continue
            axis_pt, tt = seg_proj(pts, m["bh"] + m["t"], m["bt"] + m["t"])
            rvec = pts - axis_pt; r = np.linalg.norm(rvec, axis=1)
            ok = (r > 1e-3) & ((tt > .02) & (tt < .98) if b.get("interior_only", True) else True)
            L = float(b.get("ray", .35)); c = float(b.get("clear", .012))
            U, RR, RB = [], [], []
            for p0, uvec, rr in zip(axis_pt[ok], rvec[ok] / r[ok, None], r[ok]):
                hit = bvh.ray_cast(Vector(p0 + uvec * L), Vector(-uvec), L)
                if hit[0] is not None:
                    U.append(uvec); RR.append(L - hit[3]); RB.append(rr)
            if len(U) < 10:
                report[b["name"]] = {"skipped": "ray hits", "hits": len(U), "samples": int(ok.sum())}
                continue
            U, RR, RB = np.array(U), np.array(RR), np.array(RB)
            keep = RR > RB - float(b.get("deep", .025))
            U, RR, RB = U[keep], RR[keep], RB[keep]
            if len(U) < 10:
                continue
            need = RB + c - RR
            Up = U - np.outer(U @ m["n"], m["n"])
            A = np.hstack([-Up, np.ones((len(U), 1))])
            lam = float(b.get("ridge", 40.)) * len(U) / 100.
            sol = np.linalg.solve(A.T @ A + np.diag([lam, lam, lam, 0.]), A.T @ need)
            tvec = -sol[:3]; tvec -= m["n"] * (tvec @ m["n"])
            if not b.get("shift", True):
                tvec[:] = 0
            # the bound is on the total shift across iterations, not each step
            tmax = float(b.get("tmax", .03))
            total = m["t"] + tvec
            if np.linalg.norm(total) > tmax:
                tvec = total * (tmax / np.linalg.norm(total)) - m["t"]
            gneed = float(np.percentile((RB + c) / np.maximum(RR + Up @ tvec, 1e-3), float(b.get("pct", 85))))
            m["t"] = m["t"] + tvec
            gmin, gmax = float(b.get("gmin", 1.)), float(b.get("gmax", 1.12))
            m["g"] = float(np.clip(m["g"] * max(gneed, gmin), gmin, gmax))
            report[b["name"]] = {"k": round(m["k"], 3), "rays": int(len(U)),
                                 "shift_mm": [round(1000 * x, 1) for x in m["t"]], "girth": round(m["g"], 3)}
        out = place()
    return out, w, dom, report


def conform(body, posed, tris, w, ps):
    """Let a coat front follow the chest under it instead of hanging flat off it.

    Added 2026-10-17 (owner review note 8: the female chest reads flat in every
    fit).  The girth and shift of a trunk bone are one similarity, so a coat
    drawn for a flat chest keeps its flat front: on the female body it clears
    the bust apex by nothing (the skin crosses it there) and stands 3-4 cm
    off the upper chest and the waist, and runs straight from the collar to the
    belt.  ``conform`` (opt-in, and only on the bodies it names) measures,
    on a 1 cm grid in front of the chest (``region``: x half-width, z from/to),
    the outermost trunk art against the skin, and moves the art front to back
    by the difference between that gap and the gap clamped to
    [``clear``, ``max_gap``] -- out at the apex, in above and below it --
    capped at ``max_out`` / ``max_in``, smoothed (``sigma``) and faded at the
    region's edges.  A plate that stands well off the body keeps its standoff:
    the clamp is taken above the quarter of the grid that is closest to the
    skin (its 25th-percentile gap, less ``clear``), so the plate takes the
    chest's shape instead of being drawn in by the cap all over.  Every layer
    at a grid point moves by the same amount, so straps stay on the coat;
    sleeves (the limb bones' share of ``w``) and the back do not move.
    Returns the conformed shell and a report.
    """
    c = ps["conform"]
    half, z0, z1 = (float(v) for v in c.get("region", (.17, 1.08, 1.44)))
    clear, gmax = float(c.get("clear", .012)), float(c.get("max_gap", .022))
    dmin, dmax = -float(c.get("max_in", .015)), float(c.get("max_out", .03))
    limb = np.array([bool(b.get("limb")) for b in ps["bones"]])
    trunk = w[:, ~limb].sum(1) if (~limb).any() else np.ones(len(posed))
    faces = tris[np.all(trunk[tris] > .5, axis=1)]
    art = BVHTree.FromPolygons([Vector(p) for p in posed], faces.tolist())
    xs = np.arange(-half, half + 1e-9, .01); zs = np.arange(z0, z1 + 1e-9, .01)
    G = np.zeros((len(zs), len(xs))); M = np.zeros_like(G)
    for i, z in enumerate(zs):
        for j, x in enumerate(xs):
            o = Vector((x, -.5, z)); d = Vector((0, 1, 0))
            ha, hs = art.ray_cast(o, d, 1.), body.bvh.ray_cast(o, d, 1.)
            if ha[0] is None or hs[0] is None:
                continue
            gap = hs[3] - ha[3]  # art in front of the skin by this much
            if gap < -.05 or gap > .12:
                continue  # an opening or something that is not the coat front
            G[i, j] = gap; M[i, j] = 1.
    base = max(0., float(np.percentile(G[M > 0], 25)) - clear) if M.any() else 0.
    D = np.where(M > 0, np.clip(np.clip(G - base, clear, gmax) + base - G, dmin, dmax), 0.)
    # normalised gaussian smoothing over the valid cells
    k = np.exp(-.5 * (np.arange(-6, 7) * .01 / float(c.get("sigma", .025))) ** 2)
    blur = lambda a: np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 0,
                                         np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, a))
    Ds = blur(D * M) / np.maximum(blur(M), 1e-6)
    sm = lambda x, e0, e1: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0., 1.))
    out = posed.copy()
    front = sm(.045 - posed[:, 1], .02, .06) * trunk  # body centre at y +.045 (glTF z -.045)
    edge = (sm(-np.abs(posed[:, 0]), -half, -half + .04) * sm(posed[:, 2], z0, z0 + .05)
            * (1 - sm(posed[:, 2], z1 - .05, z1)))
    ii = np.clip(np.round((posed[:, 2] - z0) / .01).astype(int), 0, len(zs) - 1)
    jj = np.clip(np.round((posed[:, 0] + half) / .01).astype(int), 0, len(xs) - 1)
    move = Ds[ii, jj] * front * edge
    out[:, 1] -= move  # forward is -Y
    return out, {"cells": int(M.sum()), "standoff_mm": round(1000 * base, 1),
                 "out_mm": round(1000 * float(move.max()), 1),
                 "in_mm": round(1000 * float(-move.min()), 1)}


def centre_cuffs(body, posed, w, ps):
    """Centre each sleeve's end on the wrist it ends at, in idle.

    Added 2026-10-17 (owner's second review, note 22: the Phoenix cuffs'
    openings were not aligned with the hands).  The forearm bone's similarity
    carries a cuff drawn off the middle of the concept's sleeve that far off
    the wrist, and the clearance shift moves it further: in idle the Phoenix
    cuff ring stood 4-5 cm in front of the wrist and the kit cuffs 1-3.6 cm
    to the side.  Each bone named in ``centre_cuffs`` is measured in the
    posed shell: the centre of the art it owns in the last 20% of the posed
    lowerarm -> hand segment, against the centre of the forearm surface there
    (skin and default shirt).  The difference across the forearm is taken
    off the bone's art, all of it at the cuff and fading to none at 35% of
    the way from the elbow, so the sleeve leans onto the wrist rather than
    stepping.  Twice, as a fit step.  Returns the shell and the offsets
    removed, per bone, in mm.
    """
    names = [b["name"] for b in ps["bones"]]
    sm = lambda x, e0, e1: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0., 1.))
    out, report = posed.copy(), {}
    for name in ps["centre_cuffs"]:
        i = names.index(name); side = name[-1]
        e, h = body.joint("lowerarm_" + side), body.joint("hand_" + side)
        ax = h - e; L = float(np.linalg.norm(ax)); ax = ax / L
        dom = np.isin(body.dominant, ["lowerarm_" + side, "hand_" + side])
        total = np.zeros(3)
        for _ in range(2):
            def band(P, t0, t1, rmax, mask):
                t = (P - e) @ ax / L; r = P - (e + np.outer(t * L, ax))
                return (t > t0) & (t < t1) & (np.linalg.norm(r, axis=1) < rmax) & mask, r
            ring, ra = band(out, .80, 1.02, .12, w[:, i] > .5)
            skin, rs = band(body.points, .80, 1.0, .06, dom)
            if ring.sum() < 6 or skin.sum() < 6:
                break
            off = ra[ring].mean(0) - rs[skin].mean(0)
            off -= ax * (off @ ax)
            t = (out - e) @ ax / L
            out -= np.outer(w[:, i] * sm(t, .35, .85), off)
            total += off
        report[name] = [round(1000 * float(x), 1) for x in total]
    return out, report


def collar(body, posed, tris, w, ps):
    """Bring a collar's back out of the neck it was fitted into.

    Added 2026-10-17 (owner review: the hoods could not reach the collars
    partly because the collars did not come far enough back).  A trunk
    bone's clearance clears the spine and clavicle skin, not the neck's, so a
    collar drawn round a slimmer neck stays where the design put it: in idle
    the back of every kit collar dropped inside the nape, from 1.46 m on the
    Studded Jack (5 cm deep by 1.56 m) and from 1.48-1.54 m on the others,
    and from the side the nape showed where the collar should wrap it.
    ``collar`` casts rays out of the posed neck_01 -> Head axis on a grid of
    heights (``from``-``to``, 1 cm) and bearings (10 degrees) and, where the
    outermost trunk art lies closer than the skin plus ``clear``, moves the
    art at that height and bearing out along the ray by the difference (at
    most ``max``), smoothed and faded in over the first 4 cm.  Every layer on
    the ray moves together, and nothing moves where the art already clears
    the neck, so the front of an open collar keeps its shape; only art within
    4 cm of the neck skin moves fully (fading out by 6 cm), so the smoothing
    round the ring never carries a shoulder plate with it.  Returns the shell
    and a report.
    """
    c = ps["collar"]
    z0, z1 = float(c.get("from", 1.40)), float(c.get("to", 1.64))
    clear, cap = float(c.get("clear", .008)), float(c.get("max", .07))
    limb = np.array([bool(b.get("limb")) for b in ps["bones"]])
    trunk = w[:, ~limb].sum(1) if (~limb).any() else np.ones(len(posed))
    faces = tris[np.all(trunk[tris] > .5, axis=1)]
    n0, n1 = np.array(body.joint("neck_01")), np.array(body.joint("Head"))
    axis = (n1 - n0) / np.linalg.norm(n1 - n0)
    centre = lambda z: n0 + (z - n0[2]) / axis[2] * axis
    zs = np.arange(z0, z1 + 1e-9, .01); bearings = np.radians(np.arange(0, 360, 10))
    kz = np.exp(-.5 * (np.arange(-3, 4) * .01 / .015) ** 2)
    ka = np.exp(-.5 * (np.arange(-3, 4) * 10. / 15.) ** 2)
    def blur(a):  # round the neck (wrapping) and up it
        a = np.apply_along_axis(lambda r: np.convolve(np.r_[r[-3:], r, r[:3]], ka, "valid"), 1, a)
        return np.apply_along_axis(lambda r: np.convolve(r, kz, "same"), 0, a)
    sm = lambda x, e0, e1: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0., 1.))
    out, total, cells = posed.copy(), np.zeros(len(posed)), 0
    # The smoothing undershoots a cell's own need at the collar's top edge, so
    # measure and push twice.
    for _ in range(int(c.get("passes", 2))):
        art = BVHTree.FromPolygons([Vector(p) for p in out], faces.tolist())
        D = np.zeros((len(zs), len(bearings))); M = np.zeros_like(D); S = np.full_like(D, np.inf)
        for i, z in enumerate(zs):
            o = Vector(centre(z))
            for j, a in enumerate(bearings):
                d = Vector((np.sin(a), -np.cos(a), 0.))  # bearing 0 is the front (-Y)
                skin = body.bvh.ray_cast(o, d, .3)
                outer, start = None, o
                for _ in range(12):
                    h = art.ray_cast(start, d, .3)
                    if h[0] is None or (h[0] - o).length > .3:
                        break
                    outer = (h[0] - o).length; start = h[0] + d * 1e-4
                if skin[0] is not None:
                    S[i, j] = skin[3]
                    if outer is not None:
                        D[i, j] = np.clip(skin[3] + clear - outer, 0., cap); M[i, j] = 1.
        cells = max(cells, int((D > 0).sum()))
        # smoothed over the cells whose ray met the art, never below a cell's own need
        norm = np.maximum(blur(M), 1e-6)
        Ds = blur(M * np.maximum(blur(D * M) / norm, D)) / norm
        rel = out - np.array([centre(z) for z in out[:, 2]])
        bearing = np.degrees(np.arctan2(rel[:, 0], -rel[:, 1])) % 360
        ii = np.clip(np.round((out[:, 2] - z0) / .01).astype(int), 0, len(zs) - 1)
        jj = np.round(bearing / 10).astype(int) % len(bearings)
        inside = (out[:, 2] >= z0) & (out[:, 2] <= z1 + .01)
        ring = 1 - sm(np.linalg.norm(rel[:, :2], axis=1) - S[ii, jj], .04, .06)
        move = np.where(inside, Ds[ii, jj], 0.) * sm(out[:, 2], z0, z0 + .04) * trunk * ring
        flat = rel * np.array([1., 1., 0.])
        flat /= np.maximum(np.linalg.norm(flat, axis=1, keepdims=True), 1e-6)
        out = out + flat * move[:, None]; total += move
    return out, {"cells": cells, "max_mm": round(1000 * float(total.max()), 1)}


def welded_graph(P, tris):
    """Coincident vertices as one node: (vertex -> node, node count, unique node edges)."""
    keys = np.round(P / 1e-5).astype(np.int64)
    canon = np.unique(keys, axis=0, return_inverse=True)[1].ravel()
    pairs = np.sort(canon[tris[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2)], axis=1)
    return canon, int(canon.max()) + 1, np.unique(pairs[pairs[:, 0] != pairs[:, 1]], axis=0)


def tuck(body, P, tris, posed, dom, ps, outer, outer_tris):
    """Tuck a garment's covered part inside another piece of the set.

    A set is worn together: trousers drawn to the ankle go inside boots drawn
    to the calf.  Fitted on their own, both clear the same body by about the
    same margin, so the two shells cross and flicker through each other.
    Rays leave each named bone's posed body axis (``tuck_into.bones``) through
    every vertex it owns; where they meet the outer piece's shell (``outer``,
    already posed and seated) closer than the vertex plus ``margin``, the
    vertex moves in along the ray to that shell less the margin, though never
    to within ``floor`` of the body surface (default clothes included, so the
    garment still covers them without the outer piece).  The move spreads a
    few rings (``ease``) over the welded mesh so the garment eases in at the
    cuff instead of stepping.  ``arc`` ([from, to] degrees round the bone,
    0 the front, 180 the back) limits the tuck to that side, and a vertex that
    would have to move more than ``max`` stays where it is: a belt, a flap or
    a tasset that far outside is a designed outer layer, not a poke-through
    (owner's second review: tucking trousers into the coat all round pushed
    the Ranger's belt under the vest and crushed the Warden's fur flaps by
    14 cm).  Returns the tucked posed shell and a report.
    """
    t = ps["tuck_into"]
    margin, floor = float(t.get("margin", .006)), float(t.get("floor", .002))
    arc = t.get("arc"); limit = float(t.get("max", np.inf))
    shell = BVHTree.FromPolygons([Vector(p) for p in outer], outer_tris.tolist())
    disp = np.zeros_like(posed); fixed = np.zeros(len(posed), bool)
    for i, b in enumerate(ps["bones"]):
        if b["name"] not in t["bones"]:
            continue
        a0 = body.joint(b["body"][0]) + np.array(b.get("offset", (0, 0, 0)), float)
        a1 = body.joint(b["body"][1]) + np.array(b.get("offset_tail", b.get("offset", (0, 0, 0))), float)
        own = np.flatnonzero(dom == i)
        foot, _ = seg_proj(posed[own], a0, a1)
        for v, p0 in zip(own, foot):
            u = posed[v] - p0; r = float(np.linalg.norm(u))
            if r < 1e-4:
                continue
            u /= r
            if arc is not None:
                bearing = float(np.degrees(np.arctan2(u[0], -u[1]))) % 360  # 0 is the front (-Y)
                if not (float(arc[0]) <= bearing <= float(arc[1])):
                    continue
            hit = shell.ray_cast(Vector(p0), Vector(u), r + .08)
            if hit[0] is None or r <= hit[3] - margin:
                continue
            reach = .4
            skin = body.bvh.ray_cast(Vector(p0 + u * reach), Vector(-u), reach)
            want = max(hit[3] - margin, (reach - skin[3] if skin[0] is not None else 0.) + floor)
            if want < r and r - want <= limit:
                disp[v] = (want - r) * u; fixed[v] = True
    canon, n, pairs = welded_graph(P, tris)
    node = np.zeros((n, 3)); np.add.at(node, canon, disp)
    node /= np.bincount(canon, minlength=n)[:, None]
    hold = np.zeros(n, bool); hold[canon[fixed]] = True
    held = node.copy()
    for _ in range(int(t.get("ease", 4))):
        acc = node.copy(); cnt = np.ones(n)
        np.add.at(acc, pairs[:, 0], node[pairs[:, 1]]); np.add.at(acc, pairs[:, 1], node[pairs[:, 0]])
        np.add.at(cnt, pairs[:, 0], 1); np.add.at(cnt, pairs[:, 1], 1)
        node = acc / cnt[:, None]; node[hold] = held[hold]
    move = node[canon]
    return posed + move, {"into": t["piece"], "tucked": int(fixed.sum()),
                          "max_mm": round(1000 * float(np.linalg.norm(move, axis=1).max()), 1)}


def seat_soles(body, P, rest, sink=0.004):
    """Stand a pair of separate boots where limb_head_remap seats boots.

    Clearance can lift or drop a boot whose insole does not sit where the
    foot's sole does, and the idle foot is not the rest foot.  As
    limb_head_remap does, each side (the source's x sign) moves whole in the
    rest pose so its sole is ``sink`` under the weighted sole: the lowest rest
    body point carried more than half by that foot chain
    (equipment_authoring.weighted_sole).  Returns the shifts (mm).
    """
    shifts = {}
    for side, sign in (("l", 1.), ("r", -1.)):
        own = P[:, 0] * sign >= 0
        cols = [body.index[b + "_" + side] for b in ("foot", "ball")]
        carried = body.weights[:, cols].sum(1) > .5
        if own.any() and carried.any():
            dz = float(body.rest_points[carried, 2].min()) - sink - float(rest[own, 2].min())
            rest[own, 2] += dz
            shifts[side] = round(1000 * dz, 1)
    return shifts


def components(P, tris):
    """Welded connected component of each vertex."""
    canon, n, pairs = welded_graph(P, tris)
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(c) for c in range(n)])[canon]


def drape(body, P, tris, top, tw, ps):
    """Weight hanging panels as cloth from the belt, not as the leg behind them.

    Bound from the nearest body surface, a tail hanging behind the legs takes
    thigh weights above the knee and calf weights below it, so it creases at
    the knee every stride as if sewn to the leg.  Each ``drape`` entry names a
    design-space ``box``; every welded component inside it hangs from
    ``hang`` (default pelvis) at the top and follows its side's thigh (the
    ``sides`` entry for the component's x sign) up to ``follow`` of the way by
    60% of the drop, with only ``calf`` of the calf at the hem, so it swings
    with the stride in one gentle curve.  The drop runs over all of a side's
    components together, so a trim strip at the hem weighs as the hem.
    Positions are untouched; the rest pose is solved from these weights.
    Returns the vertices draped per entry.
    """
    comp = components(P, tris)
    smooth = lambda x, e0, e1: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0., 1.))
    report = []
    for d in ps["drape"]:
        lo, hi = (np.array(v, float) for v in d["box"])
        hang = body.index[d.get("hang", "pelvis")]
        follow, calf = float(d.get("follow", .8)), float(d.get("calf", .15))
        side = {"+": np.zeros(len(P), bool), "-": np.zeros(len(P), bool)}
        for c in np.unique(comp):
            own = comp == c
            if np.all(P[own] >= lo) and np.all(P[own] <= hi):
                side["+" if P[own, 0].mean() >= 0 else "-"] |= own
        for sign, own in side.items():
            if not own.any():
                continue
            thigh, shin = (body.index[b] for b in d["sides"][sign])
            z = P[own, 2]
            a = (z.max() - z) / max(float(np.ptp(z)), 1e-6)
            ft, fc = follow * smooth(a, 0., .6), calf * smooth(a, .6, 1.)
            rows = np.flatnonzero(own)
            top[rows] = hang; tw[rows] = 0.
            tw[rows, 0] = 1 - ft - fc
            top[rows, 1], tw[rows, 1] = thigh, ft
            top[rows, 2], tw[rows, 2] = shin, fc
        report.append({s: int(o.sum()) for s, o in side.items()})
    return report


def twist(body, posed, top, tw, w, ps):
    """Let a coat's waist turn with the chest instead of shearing at the belt.

    Added 2026-10-17 (owner's second review, notes 13 and 15).  Weights from
    the nearest body surface give the coat what the skin has: the waist is
    pelvis up to about 1.12 m and spine above, with no spine_01 at all, so in
    a run or a drawn bow the chest turned and the belt and everything below
    it stayed with the hips, sheared along one line.  ``twist`` caps the
    pelvis share of trunk vertices on a smooth ramp, ``pelvis`` at the hip
    joint falling to none at spine_02 (``hip`` / ``waist`` override the two
    heights; with ``free_below`` the hem below that height is left alone and
    the cap ramps in over the next 4 cm), and gives the excess to the bones in ``to`` (shares; default
    spine_01 and spine_02 equally).  The clips turn the chest mostly at
    spine_03: in Bow_Pull_Back spine_03 turns 65 degrees while spine_01 turns
    the other way, so a belt meant to turn with the chest needs a spine_03
    share.  Thigh shares stay, so a skirt still follows the legs.  Returns the
    vertices changed.
    """
    c = ps["twist"]
    hip = float(c.get("hip", body.joint("thigh_l")[2]))
    waist = float(c.get("waist", body.joint("spine_02")[2]))
    cap0 = float(c.get("pelvis", .7))
    free = float(c.get("free_below", -1.))
    limb = np.array([bool(b.get("limb")) for b in ps["bones"]])
    trunk = (w[:, ~limb].sum(1) if (~limb).any() else np.ones(len(posed))) > .5
    sm = lambda x, e0, e1: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0., 1.))
    if free > 0:
        # The hem stays with the hips and legs (owner's third review: with the
        # whole coat turned toward the chest, the thighs came through its
        # skirt in a walk, notes 6, 13, 14); the cap starts at the belt.
        cap = (1 - (1 - cap0) * sm(posed[:, 2], free, free + .04)) * (1 - sm(posed[:, 2], free + .04, waist))
    else:
        cap = cap0 * (1 - sm(posed[:, 2], hip, waist))
    pelvis = body.index["pelvis"]
    to = {body.index[n]: float(v) for n, v in c.get("to", {"spine_01": .5, "spine_02": .5}).items()}
    total = sum(to.values())
    dense = np.zeros((len(posed), len(body.bones)))
    np.add.at(dense, (np.repeat(np.arange(len(posed)), top.shape[1]), top.ravel()), tw.ravel())
    excess = np.where(trunk, np.maximum(dense[:, pelvis] - cap, 0.), 0.)
    dense[:, pelvis] -= excess
    for col, share in to.items():
        dense[:, col] += excess * share / total
    changed = excess > 1e-6
    t4 = np.argsort(-dense, 1)[:, :4]
    w4 = np.take_along_axis(dense, t4, 1)
    w4 /= np.maximum(w4.sum(1, keepdims=True), 1e-12)
    top[changed], tw[changed] = t4[changed], w4[changed]
    return int(changed.sum())


def skin_weights(body, P, edges, canon, dom, ps, neighbours=2, smooth=3, rigid=250):
    """Nearest posed body surface weights, scoped per design bone, smoothed, plates rigid."""
    W = np.zeros((len(P), len(body.bones)))
    for i, b in enumerate(ps["bones"]):
        own = dom == i
        if not own.any():
            continue
        allowed = b.get("weights_from") or [b["body"][0].split(".")[0]]
        cols = [body.index[n] for n in allowed if n in body.index]
        rows = np.isin(body.dominant, allowed)
        pts, wts = body.points[rows], body.weights[rows][:, cols]
        good = wts.sum(1) > 0
        pts, wts = pts[good], wts[good] / wts[good].sum(1, keepdims=True)
        kd = KDTree(len(pts))
        for j, p in enumerate(pts):
            kd.insert(p, j)
        kd.balance()
        for v in np.nonzero(own)[0]:
            hits = kd.find_n(P[v], neighbours)
            d = np.array([h[2] for h in hits]) + 1e-4
            ww = 1 / d ** 4
            W[v, cols] = (ww[:, None] * wts[[h[1] for h in hits]]).sum(0) / ww.sum()
    for _ in range(smooth):
        acc = W.copy(); cnt = np.ones(len(P))
        np.add.at(acc, edges[:, 0], W[edges[:, 1]]); np.add.at(acc, edges[:, 1], W[edges[:, 0]])
        np.add.at(cnt, edges[:, 0], 1); np.add.at(cnt, edges[:, 1], 1)
        W = acc / cnt[:, None]
        sums = np.zeros((canon.max() + 1, W.shape[1])); np.add.at(sums, canon, W)
        W = (sums / np.bincount(canon)[:, None])[canon]
    parent = np.arange(canon.max() + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in canon[edges]:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comp = np.array([find(c) for c in canon])
    rigid_count = 0
    for cid in np.unique(comp):
        own = comp == cid
        if own.sum() <= rigid:
            W[own] = W[own].mean(0); rigid_count += 1
    top = np.argsort(-W, 1)[:, :4]
    tw = np.take_along_axis(W, top, 1)
    tw /= np.maximum(tw.sum(1, keepdims=True), 1e-12)
    return top, tw, rigid_count


def main():
    args = args_after_dashes()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    wipe()
    body = Body(args.body, args.library, args.pose)
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"format": FORMAT, "spec": args.spec.name, "spec_sha256": digest(args.spec),
               "body": args.body.name, "body_sha256": digest(args.body), "pose": args.pose,
               "tool_sha256": digest(__file__), "posekit_sha256": digest(POSEKIT), "pieces": {}}
    solved = {}
    for piece, ps in spec["pieces"].items():
        src_path = args.sources / (ps["source"] + ".orig")
        new = import_into(src_path, "src_" + piece)
        mesh_obj = next(o for o in new if o.type == "MESH")
        me = mesh_obj.data
        me.calc_loop_triangles()
        P = np.array([(mesh_obj.matrix_world @ v.co)[:] for v in me.vertices])
        tris = np.array([t.vertices[:] for t in me.loop_triangles])
        posed, w, dom, report = fit_piece(body, P, tris, ps)
        if "conform" in ps and args.body.stem in ps["conform"].get("bodies", []):
            posed, report["conform"] = conform(body, posed, tris, w, ps)
        if "centre_cuffs" in ps:
            posed, report["centre_cuffs"] = centre_cuffs(body, posed, w, ps)
        if "collar" in ps:
            posed, report["collar"] = collar(body, posed, tris, w, ps)
        if "tuck_sleeves" in ps:
            # A coat's own sleeves go under its shoulder panels (owner's second
            # review, note 9: the Scout Vest's shirt sleeves came through the
            # vest's back shoulder): the tuck, with the piece's trunk art as the
            # outer shell and the upper-arm bones' own art moving in.
            limb = np.array([bool(b.get("limb")) for b in ps["bones"]])
            trunk = w[:, ~limb].sum(1) > .5
            t = dict(ps["tuck_sleeves"], piece="self")
            posed, report["tuck_sleeves"] = tuck(body, P, tris, posed, w.argmax(1), dict(ps, tuck_into=t),
                                                 posed, tris[np.all(trunk[tris], axis=1)])
        edges = np.array([e.vertices[:] for e in me.edges])
        solved[piece] = {"src": src_path, "P": P, "tris": tris, "edges": edges, "posed": posed, "dom": dom,
                         "w": w, "report": report}

    def finish(piece):
        ps, sv = spec["pieces"][piece], solved[piece]
        posed, report = sv["posed"], sv["report"]
        canon = np.unique(np.round(posed / 1e-5).astype(np.int64), axis=0, return_inverse=True)[1].ravel()
        top, tw, rigid = skin_weights(body, posed, sv["edges"], canon, sv["dom"], ps)
        if ps.get("drape"):
            report["drape_vertices"] = drape(body, sv["P"], sv["tris"], top, tw, ps)
        if ps.get("twist"):
            report["twist_vertices"] = twist(body, posed, top, tw, sv["w"], ps)
        Mv = np.einsum("nk,nkij->nij", tw, body.skin[top])
        rest = np.einsum("nij,nj->ni", np.linalg.inv(Mv), np.c_[posed, np.ones(len(posed))])[:, :3]
        if ps.get("ground"):
            # seat the soles in the rest pose; the shell shown in idle follows
            report["sole_seat_mm"] = seat_soles(body, sv["P"], rest)
            posed = np.einsum("nij,nj->ni", Mv, np.c_[rest, np.ones(len(rest))])[:, :3]
        sv.update(posed=posed, rest=rest, top=top, tw=tw, rigid=rigid)

    # a garment tucked into another piece waits for that piece's final shell
    for piece in sorted(spec["pieces"], key=lambda p: "tuck_into" in spec["pieces"][p]):
        ps, sv = spec["pieces"][piece], solved[piece]
        tucks = ps.get("tuck_into", [])
        reports = []
        for t in [tucks] if isinstance(tucks, dict) else tucks:
            # Into a coat, only its trunk counts: a sleeve or hand hanging
            # beside the thigh is no shell to tuck under.
            outer = solved[t["piece"]]
            outer_ps = spec["pieces"][t["piece"]]
            limb = np.array([bool(b.get("limb")) for b in outer_ps["bones"]])
            tris = outer["tris"]
            if limb.any():
                trunk = outer["w"][:, ~limb].sum(1) > .5
                tris = tris[np.all(trunk[tris], axis=1)]
            sv["posed"], r = tuck(body, sv["P"], sv["tris"], sv["posed"], sv["dom"], dict(ps, tuck_into=t),
                                  outer["posed"], tris)
            reports.append(r)
        if reports:
            sv["report"]["tuck"] = reports if len(reports) > 1 else reports[0]
        finish(piece)
    for piece, ps in spec["pieces"].items():
        sv = solved[piece]
        P, tris, posed, rest, src_path = sv["P"], sv["tris"], sv["posed"], sv["rest"], sv["src"]
        # Bridges the rest pose stretches far past their posed length cannot open into
        # an armpit; the fitted backing closes what is dropped (as torso_remap does).
        stretch = np.ones(len(tris))
        for a, b in ((0, 1), (1, 2), (2, 0)):
            before = np.linalg.norm(posed[tris[:, a]] - posed[tris[:, b]], axis=1)
            after = np.linalg.norm(rest[tris[:, a]] - rest[tris[:, b]], axis=1)
            stretch = np.maximum(stretch, after / np.maximum(before, 1e-9))
        keep = stretch < float(ps.get("max_stretch", 2.5))
        # Blender Z-up -> glTF Y-up (the rig's axes)
        to_gltf = lambda a: np.c_[a[:, 0], a[:, 2], -a[:, 1]]
        # Each vertex's share of each arm: torso_remap re-binds sleeves on it
        # (design_fit.bind_sleeves), re-inverting the idle pose with `skin`.
        names = [b["name"] for b in ps["bones"]]
        arm_share = np.stack([sv["w"][:, [i for i, n in enumerate(names) if n.endswith("arm_" + side)]].sum(1)
                              for side in ("l", "r")], 1)
        out = args.out / (ps["source"] + ".npz")
        np.savez_compressed(out, format=FORMAT, positions=to_gltf(rest).astype(np.float64),
                            posed=to_gltf(posed), joint_names=np.array(body.bones),
                            joints=sv["top"].astype(np.uint16), weights=sv["tw"].astype(np.float64),
                            keep=keep, scale=float(ps["scale"]), arm_share=arm_share,
                            skin=np.einsum("ij,bjk,kl->bil", AXES, body.skin, AXES.T),
                            source_sha256=digest(src_path),
                            body_sha256=digest(args.body), spec_sha256=digest(args.spec))
        summary["pieces"][piece] = {"source": ps["source"], "vertices": len(P), "triangles": len(tris),
                                    "opened": int((~keep).sum()), "rigidPlates": sv["rigid"],
                                    "bones": sv["report"], "out": out.name, "sha256": digest(out)}
        print("DESIGN_FIT", piece, json.dumps(summary["pieces"][piece]))
    # LF on every platform (write_text would give CRLF on Windows)
    (args.out / (args.spec.stem + ".report.json")).write_bytes((json.dumps(summary, indent=1) + "\n").encode())


if __name__ == "__main__":
    main()
