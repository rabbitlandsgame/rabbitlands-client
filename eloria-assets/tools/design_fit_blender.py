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
FORMAT = 1


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
        pos, rows = [], []
        for name in SURFACES:
            o = self.meshes[name]
            groups = [g.name for g in o.vertex_groups]
            ev = o.evaluated_get(dg); me = ev.to_mesh()
            P = [(o.matrix_world @ v.co)[:] for v in me.vertices]
            ev.to_mesh_clear()
            for v, p in zip(o.data.vertices, P):
                row = np.zeros(len(self.bones))
                for g in v.groups:
                    if groups[g.group] in self.index:
                        row[self.index[groups[g.group]]] += g.weight
                if row.sum() > 0:
                    pos.append(p); rows.append(row / row.sum())
        self.points = np.array(pos)
        self.weights = np.array(rows)
        self.dominant = np.array(self.bones)[self.weights.argmax(1)]

    def joint(self, ref):
        if "|" in ref:
            a, b, t = ref.split("|")
            return self.joint(a) * (1 - float(t)) + self.joint(b) * float(t)
        end = "tail" if ref.endswith(".tail") else "head"
        pb = self.arm.pose.bones[ref[:-5] if end == "tail" else ref]
        return np.array((self.arm.matrix_world @ (pb.tail if end == "tail" else pb.head))[:])


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
    for piece, ps in spec["pieces"].items():
        src_path = args.sources / (ps["source"] + ".orig")
        new = import_into(src_path, "src_" + piece)
        mesh_obj = next(o for o in new if o.type == "MESH")
        me = mesh_obj.data
        me.calc_loop_triangles()
        P = np.array([(mesh_obj.matrix_world @ v.co)[:] for v in me.vertices])
        tris = np.array([t.vertices[:] for t in me.loop_triangles])
        posed, w, dom, report = fit_piece(body, P, tris, ps)
        edges = np.array([e.vertices[:] for e in me.edges])
        canon = np.unique(np.round(posed / 1e-5).astype(np.int64), axis=0, return_inverse=True)[1].ravel()
        top, tw, rigid = skin_weights(body, posed, edges, canon, dom, ps)
        Mv = np.einsum("nk,nkij->nij", tw, body.skin[top])
        rest = np.einsum("nij,nj->ni", np.linalg.inv(Mv), np.c_[posed, np.ones(len(posed))])[:, :3]
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
        out = args.out / (ps["source"] + ".npz")
        np.savez_compressed(out, format=FORMAT, positions=to_gltf(rest).astype(np.float64),
                            posed=to_gltf(posed), joint_names=np.array(body.bones), joints=top.astype(np.uint16),
                            weights=tw.astype(np.float64), keep=keep, scale=float(ps["scale"]),
                            source_sha256=digest(src_path),
                            body_sha256=digest(args.body), spec_sha256=digest(args.spec))
        summary["pieces"][piece] = {"source": ps["source"], "vertices": len(P), "triangles": len(tris),
                                    "opened": int((~keep).sum()), "rigidPlates": rigid,
                                    "bones": report, "out": out.name, "sha256": digest(out)}
        print("DESIGN_FIT", piece, json.dumps(summary["pieces"][piece]))
    (args.out / (args.spec.stem + ".report.json")).write_text(json.dumps(summary, indent=1) + "\n")


if __name__ == "__main__":
    main()
