"""Background Blender worker for lining_visibility.py (actor LOD plan, chunk C3).

    blender -b --factory-startup -noaudio -t 1 --python eloria-assets/tools/lining_visibility_blender.py -- \
        --job <job.json>

Added 2026-11-02.  Run through ``lining_visibility.py``, which writes the job
file, runs at most four of these at once and turns their output into mask
files.  Modes (``job["mode"]``):

``visibility``  pose every garment of the job, ray cast which lining triangles
                are visible (``lining_visibility.py`` has the method), and
                write ``<stem>.visibility.json``.
``review``      for poses and camera directions the mask did not sample,
                count the pixels that would change if the mask's removed faces
                were dropped (and the same for comparison masks), and render
                contact-sheet panels.
``selfcheck``   compare the numpy linear blend skinning used here with
                Blender's own armature deformation of the imported garment.

Everything geometric is in glTF axes (+Y up, metres).  Blender is used for the
animation library, the posekit retarget, the rider IK and BVH ray casts.  The
posed vertices come from the glTF positions, joints and weights directly, so
triangle order and numbering are the file's own.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import lining_visibility as lv  # noqa: E402

#: glTF (x, y, z) -> Blender (x, -z, y), as the glTF importer converts axes.
TO_BLENDER = np.array([[1.0, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]])
TO_GLTF = TO_BLENDER.T
IDENTITY = np.eye(4)


# ------------------------------------------------------------------- scene

def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def purge_unused():
    for blocks in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images,
                   bpy.data.textures, bpy.data.node_groups, bpy.data.cameras, bpy.data.lights):
        for block in list(blocks):
            if block.users == 0:
                blocks.remove(block)


def import_into(path, name, keep_actions=False):
    scene = bpy.context.scene
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    before, actions = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [obj for obj in bpy.data.objects if obj not in before]
    for obj in new:
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
    if not keep_actions:
        for action in list(bpy.data.actions):
            if action not in actions:
                bpy.data.actions.remove(action)
    for obj in list(new):
        if obj.name.startswith("Icosphere"):
            new.remove(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
    return new


def remove_collection(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        return
    for obj in list(collection.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(collection)
    purge_unused()


# ------------------------------------------------------------------- posing

class Poser:
    """Library clips through the shared posekit, plus the rider straddle."""

    def __init__(self, library, posekit, needed):
        self.ns = None
        if needed:
            import_into(library, "lib", keep_actions=True)
            for action in bpy.data.actions:
                action.use_fake_user = True
            self.ns = {"__name__": "posekit"}
            exec(compile(Path(posekit).read_text(encoding="utf-8"), str(posekit), "exec"), self.ns)

    @staticmethod
    def reset(arm):
        for bone in arm.pose.bones:
            bone.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()

    def frame(self, clip, at):
        start, end = bpy.data.actions[clip].frame_range
        return int(round(start + at * (end - start)))

    def pose(self, arm, recipe):
        """Pose ``arm`` and return glTF-space vertex deltas per bone name."""
        if arm is None:
            if recipe["kind"] != "bind":
                raise ValueError(f"pose {recipe['name']} needs an armature")
            return {}
        self.reset(arm)
        if recipe["kind"] in ("clip", "mount"):
            self.ns["pose_armature"](arm, action=recipe["clip"], frame=self.frame(recipe["clip"], recipe["at"]),
                                     style=False)
        if recipe["kind"] == "mount":
            apply_rider(arm, recipe["rider"])
        return joint_deltas(arm)


def joint_deltas(arm):
    world = np.array(arm.matrix_world)
    inverse = np.linalg.inv(world)
    out = {}
    for bone in arm.pose.bones:
        delta = world @ np.array(bone.matrix) @ np.linalg.inv(np.array(bone.bone.matrix_local)) @ inverse
        out[bone.name] = TO_GLTF @ delta @ TO_BLENDER
    return out


def _head(arm, name):
    return arm.matrix_world @ arm.pose.bones[name].head


def _rotate_about(arm, name, pivot, rotation):
    bone = arm.pose.bones[name]
    world = arm.matrix_world
    turn = Matrix.Translation(pivot) @ rotation.to_4x4() @ Matrix.Translation(-pivot)
    bone.matrix = world.inverted() @ turn @ world @ bone.matrix
    bpy.context.view_layer.update()


def _aim(arm, name, child, target):
    start = _head(arm, name)
    before, after = _head(arm, child) - start, target - start
    if before.length_squared < 1e-10 or after.length_squared < 1e-10:
        return
    _rotate_about(arm, name, start, before.rotation_difference(after).to_matrix())


def _solve(arm, upper, lower, end, target, pole):
    """The rider seat solver's two-bone IK (src/mounts/rider_seat_pose.gd _solve)."""
    a, b, c = _head(arm, upper), _head(arm, lower), _head(arm, end)
    first, second = (b - a).length, (c - b).length
    direction = (target - a).normalized()
    reach = min(max((target - a).length, abs(first - second) + 1e-4), first + second - 1e-4)
    along = (first * first + reach * reach - second * second) / (2.0 * reach)
    bend = (pole - a) - direction * direction.dot(pole - a)
    if bend.length_squared < 1e-8:
        bend = direction.cross(Vector((1.0, 0.0, 0.0)))
    elbow = a + direction * along + bend.normalized() * math.sqrt(max(0.0, first * first - along * along))
    _aim(arm, upper, lower, elbow)
    _aim(arm, lower, end, a + direction * reach)


def character_frame(arm):
    """(up, forward, left) in Blender world from the rest skeleton."""
    up = Vector((0.0, 0.0, 1.0))
    bones = arm.data.bones
    world = arm.matrix_world
    if "ball_l" in bones and "foot_l" in bones:
        forward = world @ bones["ball_l"].head_local - world @ bones["foot_l"].head_local
    else:
        forward = world.to_3x3() @ Vector((0.0, -1.0, 0.0))
    forward -= up * forward.dot(up)
    forward.normalize()
    left = up.cross(forward)
    if "thigh_l" in bones and "pelvis" in bones:
        side = world @ bones["thigh_l"].head_local - world @ bones["pelvis"].head_local
        if side.dot(left) < 0.0:
            left = -left
    return up, forward, left


def apply_rider(arm, rider):
    """Straddle like rider_seat_pose.gd fit(): pelvis lean, then leg and arm IK.

    Targets are offsets from the pelvis in the rider frame (x outward per side,
    y up, z forward), as the mount profiles give them.  The torso
    stabilisation, thumb grip and gait sway are not reproduced (the margin
    covers them).
    """
    up, forward, left = character_frame(arm)
    pelvis = _head(arm, "pelvis")
    _rotate_about(arm, "pelvis", pelvis, Matrix.Rotation(math.radians(rider["lean_deg"]), 3, left))

    def at(offset, sign):
        return pelvis + left * (offset[0] * sign) + up * offset[1] + forward * offset[2]

    for side, sign in (("l", 1.0), ("r", -1.0)):
        _solve(arm, "thigh_" + side, "calf_" + side, "foot_" + side, at(rider["foot"], sign), at(rider["knee"], sign))
        _solve(arm, "upperarm_" + side, "lowerarm_" + side, "hand_" + side, at(rider["hand"], sign),
               at(rider["elbow"], sign))


def pose_part(part, deltas, missing):
    """Posed positions of one part (n, 3) in glTF space."""
    positions = part["positions"]
    homogeneous = np.c_[positions, np.ones(len(positions))]
    if "joints" in part:
        matrices = []
        for name in part["skin_joints"]:
            if name in deltas:
                matrices.append(deltas[name])
            else:
                matrices.append(IDENTITY)
                if deltas:
                    missing.add(name)
        matrices = np.stack(matrices)
        out = np.zeros_like(positions)
        weights, joints = part["weights"], part["joints"]
        for slot in range(joints.shape[1]):
            used = weights[:, slot] > 0.0
            if not used.any():
                continue
            transform = matrices[joints[used, slot]]
            out[used] += weights[used, slot, None] * np.einsum("nij,nj->ni", transform[:, :3, :], homogeneous[used])
        unweighted = weights.sum(axis=1) <= 0.0
        out[unweighted] = positions[unweighted]
        return out
    delta = deltas.get(part.get("rigid"), IDENTITY) if part.get("rigid") else IDENTITY
    return (homogeneous @ (delta @ part["matrix"]).T)[:, :3]


def import_armature(path):
    new = import_into(path, "garment")
    arms = [obj for obj in new if obj.type == "ARMATURE"]
    if not arms:
        return None, new
    arm = arms[0]
    arm.animation_data_clear()
    bpy.context.view_layer.update()
    return arm, new


# --------------------------------------------------------------- ray casting

def build_bvh(parts_posed):
    """BVH over (part, posed) pairs; returns bvh, per-face double-sided list, offsets."""
    vertices, faces, double_sided, offsets = [], [], [], []
    base = 0
    face_base = 0
    for part, posed in parts_posed:
        vertices.append(posed)
        faces.append(part["triangles"] + base)
        double_sided.extend([part["double_sided"]] * len(part["triangles"]))
        offsets.append(face_base)
        base += len(posed)
        face_base += len(part["triangles"])
    verts = np.concatenate(vertices).tolist()
    tris = np.concatenate(faces).tolist()
    return BVHTree.FromPolygons(verts, tris, all_triangles=True), double_sided, offsets


def cast_pose(state, lining, lining_posed, bvh, double_sided, lining_offset, directions, settings):
    """Ray cast the not-yet-proven triangles of one lining in one pose."""
    vis, vis_up = state["visible"], state["visible_upper"]
    pending = np.nonzero(~vis_up)[0]
    if not len(pending):
        return 0, 0
    corners_all = lv.triangle_corners(lining_posed, lining["triangles"])
    normals = lv.face_normals(corners_all[pending])
    dirs, upper = directions["dirs"], directions["upper"]
    score = normals @ dirs.T
    if lining["double_sided"]:
        allowed = np.ones_like(score, dtype=bool)
        rank = -np.abs(score)
    else:
        allowed = score > 1e-9
        rank = -score
    key = np.where(upper[None, :], 0.0, 10.0) + rank
    key[~allowed] = 100.0
    order = np.argsort(key, axis=1, kind="stable")
    n_all = allowed.sum(axis=1)
    n_up = (allowed & upper[None, :]).sum(axis=1)
    samples = lv.apply_samples(corners_all, state["owner"], state["bary"])
    start, count = state["sample_start"], state["sample_count"]
    dvec, devec, upper_list = directions["dvec"], directions["devec"], directions["upper_list"]
    ray_cast = bvh.ray_cast
    max_layers = int(settings["max_layers"])
    ds = double_sided
    rays = 0
    found = 0
    for row in range(len(pending)):
        face = int(pending[row])
        already = bool(vis[face])
        limit = int(n_up[row] if already else n_all[row])
        if limit == 0:
            continue
        points = [Vector(p) for p in samples[start[face]:start[face] + count[face]].tolist()]
        self_index = lining_offset + face
        hit_upper = hit_any = False
        for j in order[row, :limit].tolist():
            d, step = dvec[j], devec[j]
            escaped = False
            for point in points:
                origin = point + step
                layers = 0
                while True:
                    rays += 1
                    location, normal, index, _ = ray_cast(origin, d)
                    if location is None:
                        escaped = True
                        break
                    if index != self_index and (ds[index] or normal.dot(d) > 0.0):
                        break
                    layers += 1
                    if layers >= max_layers:
                        escaped = True
                        break
                    origin = location + step
                if escaped:
                    break
            if escaped:
                hit_any = True
                hit_upper = upper_list[j]
                break
        if hit_any and not already:
            vis[face] = True
            found += 1
        if hit_upper:
            vis_up[face] = True
    return rays, found


def direction_set(settings):
    dirs = lv.fibonacci_directions(int(settings["directions"]))
    upper = lv.upper_flags(dirs, float(settings["upper_min_elevation_deg"]))
    eps = float(settings["eps_m"])
    return {"dirs": dirs, "upper": upper, "upper_list": upper.tolist(),
            "dvec": [Vector(d) for d in dirs.tolist()], "devec": [Vector(d) for d in (dirs * eps).tolist()]}


def ordered_poses(poses):
    return sorted(poses, key=lambda p: 0 if p["kind"] == "bind" else 1)


def visibility_job(entry, job, poser):
    started = time.perf_counter()
    settings, poses = job["settings"], ordered_poses(job["poses"])
    document, blob = lv.read_glb(entry["path"])
    parts = lv.garment_parts(document, blob)
    linings = [p for p in parts if p["lining"]]
    occluders = [p for p in parts if not p["lining"] and p["occludes"]]
    needs_arm = any(p["kind"] != "bind" for p in poses)
    arm = None
    if needs_arm:
        arm, _ = import_armature(entry["path"])
        if arm is None:
            raise ValueError("garment has no armature to pose")
    directions = direction_set(settings)
    states = []
    for lining in linings:
        corners = lv.triangle_corners(lining["positions"], lining["triangles"])
        owner, bary = lv.sample_plan(corners, float(settings["spacing_m"]), int(settings["max_subdivision"]))
        n = len(corners)
        sample_count = np.bincount(owner, minlength=n)
        states.append({"visible": np.zeros(n, bool), "visible_upper": np.zeros(n, bool), "owner": owner,
                       "bary": bary, "sample_count": sample_count,
                       "sample_start": np.r_[0, np.cumsum(sample_count)[:-1]],
                       "new": {}, "rays": 0, "seconds": {}})
    missing = set()
    timings = {}
    for recipe in poses:
        pose_started = time.perf_counter()
        deltas = poser.pose(arm, recipe)
        posed = {id(p): pose_part(p, deltas, missing) for p in parts}
        for lining, state in zip(linings, states):
            if state["visible_upper"].all():
                state["new"][recipe["name"]] = 0
                continue
            bvh, ds, offsets = build_bvh([(p, posed[id(p)]) for p in occluders] + [(lining, posed[id(lining)])])
            rays, found = cast_pose(state, lining, posed[id(lining)], bvh, ds, offsets[-1], directions, settings)
            state["rays"] += rays
            state["new"][recipe["name"]] = found
            if recipe["kind"] == "bind":
                state["visible_bind"] = state["visible"].copy()
                state["visible_upper_bind"] = state["visible_upper"].copy()
        timings[recipe["name"]] = round(time.perf_counter() - pose_started, 3)
    out_linings = {}
    for lining, state in zip(linings, states):
        corners = lv.triangle_corners(lining["positions"], lining["triangles"])
        n = len(corners)
        record = {"mesh": lining["mesh"], "primitive": lining["primitive"], "triangles": n,
                  "vertices": len(lining["positions"]), "double_sided": lining["double_sided"],
                  "material": lining["material"], "gltf_index_sha256": lv.index_digest(lining["triangles"]),
                  "check": lv.check_centroids(corners), "samples": int(len(state["owner"])),
                  "rays": int(state["rays"]), "new_visible_by_pose": state["new"],
                  "visible": lv.pack_bits(state["visible"]), "visible_upper": lv.pack_bits(state["visible_upper"]),
                  "counts": {"visible": int(state["visible"].sum()),
                             "visible_upper": int(state["visible_upper"].sum())},
                  "runs": {}}
        if "visible_bind" in state:
            record["visible_bind"] = lv.pack_bits(state["visible_bind"])
            record["counts"]["visible_bind"] = int(state["visible_bind"].sum())
            record["counts"]["visible_upper_bind"] = int(state["visible_upper_bind"].sum())
        name = lining["mesh"] if lining["primitive"] == 0 else f"{lining['mesh']}#{lining['primitive']}"
        out_linings[name] = record
    occluder_rows = [{"mesh": p["mesh"], "primitive": p["primitive"], "triangles": len(p["triangles"]),
                      "double_sided": p["double_sided"], "alpha": p["alpha"], "occludes": p["occludes"]}
                     for p in parts if not p["lining"]]
    if arm is not None:
        remove_collection("garment")
    doc = {"schema": lv.SCHEMA, "policy": lv.POLICY,
           "source": {"path": entry["res_path"], "sha256": entry["sha256"], "bytes": entry["bytes"]},
           "inputs": job["inputs"], "settings": settings,
           "settings_sha256": lv.json_sha256({"settings": settings, "poses": job["poses"]}),
           "poses": [p["name"] for p in poses], "occluders": occluder_rows, "linings": out_linings,
           "blender": bpy.app.version_string}
    if missing:
        doc["errors"] = [f"skin joints missing from the armature: {sorted(missing)}"]
    log = {"seconds": round(time.perf_counter() - started, 2), "pose_seconds": timings,
           "rays": {name: rec["rays"] for name, rec in out_linings.items()}}
    return doc, log


# ------------------------------------------------------------------- review

def camera_basis(d, up_hint):
    d = d / np.linalg.norm(d)
    up = up_hint - d * float(up_hint @ d)
    if np.linalg.norm(up) < 1e-6:
        up = np.array([0.0, 0.0, 1.0]) - d * d[2]
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    return right / np.linalg.norm(right), up


def first_hits(bvh, double_sided, points, d, pixel, max_layers, size=None):
    """Orthographic first drawn face per pixel; -1 where nothing is hit.

    ``d`` points towards the camera.  Returns (hits, normals_dot) arrays.
    """
    right, up = camera_basis(d, np.array([0.0, 1.0, 0.0]))
    centre = points.mean(axis=0)
    rel = points - centre
    xs, ys = rel @ right, rel @ up
    radius = float(np.linalg.norm(rel, axis=1).max()) + 0.5
    if size is None:
        width = int(math.ceil((xs.max() - xs.min()) / pixel)) + 2
        height = int(math.ceil((ys.max() - ys.min()) / pixel)) + 2
        x0, y1 = xs.min() - pixel, ys.max() + pixel
    else:
        width, height = size
        pixel = max((xs.max() - xs.min()) / (width - 4), (ys.max() - ys.min()) / (height - 4))
        x0 = (xs.max() + xs.min()) / 2 - pixel * width / 2
        y1 = (ys.max() + ys.min()) / 2 + pixel * height / 2
    hits = np.full((height, width), -1, dtype=np.int64)
    shade = np.zeros((height, width))
    ray = Vector((-d).tolist())
    step = ray * 1e-5
    dv = Vector(d.tolist())
    ray_cast = bvh.ray_cast
    start = centre + d * radius
    offsets = right[None, :] * (x0 + (np.arange(width) + 0.5) * pixel)[:, None]
    for row in range(height):
        base = start + up * (y1 - (row + 0.5) * pixel)
        for col, value in enumerate((base[None, :] + offsets).tolist()):
            origin = Vector(value)
            layers = 0
            while True:
                location, normal, index, _ = ray_cast(origin, ray)
                if location is None:
                    break
                facing = normal.dot(dv)
                if double_sided[index] or facing > 0.0:
                    hits[row, col] = index
                    shade[row, col] = abs(facing)
                    break
                layers += 1
                if layers >= max_layers:
                    break
                origin = location + step
    return hits, shade


def view_direction(frame, azimuth_deg, elevation_deg):
    up, forward, right = frame
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    d = math.cos(e) * (math.cos(a) * forward + math.sin(a) * right) + math.sin(e) * up
    return d / np.linalg.norm(d)


def gltf_frame(document):
    """(up, forward, right) of the character in glTF axes from the rest skeleton."""
    worlds, _ = lv.node_world_matrices(document)
    names = {node.get("name", ""): i for i, node in enumerate(document.get("nodes", []))}
    up = np.array([0.0, 1.0, 0.0])
    forward = np.array([0.0, 0.0, 1.0])
    if "ball_l" in names and "foot_l" in names:
        forward = worlds[names["ball_l"]][:3, 3] - worlds[names["foot_l"]][:3, 3]
        forward -= up * (forward @ up)
        forward /= np.linalg.norm(forward)
    return up, forward, np.cross(forward, up)


SHEET_VIEWS = (("worn_front_high", 30.0, 35.0, "worn"), ("worn_back_high", 210.0, 35.0, "worn"),
               ("worn_front_low", 20.0, -12.0, "worn"), ("lining_front", 30.0, 35.0, "lining"),
               ("lining_back", 210.0, 35.0, "lining"))


def _safe(name):
    return name.replace(":", "-").replace("@", "_").replace("/", "_")


def colour_panel(hits, shade, lining_offset, keep, lining_only):
    grey = np.array([170, 170, 170.0])
    kept = np.array([95, 140, 200.0]) if not lining_only else np.array([120, 200, 190.0])
    removed = np.array([230, 30, 30.0])
    image = np.full(hits.shape + (3,), 250.0)
    light = (0.35 + 0.65 * shade)[..., None]
    any_hit = hits >= 0
    is_lining = hits >= lining_offset
    face = np.where(is_lining, hits - lining_offset, 0)
    kept_mask = is_lining & keep[face]
    removed_mask = is_lining & ~keep[face]
    image[any_hit & ~is_lining] = (grey * light)[any_hit & ~is_lining]
    image[kept_mask] = (kept * light)[kept_mask]
    image[removed_mask] = removed
    return np.clip(image, 0, 255).astype(np.uint8)


def review_job(entry, job, poser):
    started = time.perf_counter()
    settings = job["settings"]
    mask = json.loads(Path(entry["mask"]).read_text(encoding="utf-8"))
    document, blob = lv.read_glb(entry["path"])
    parts = lv.garment_parts(document, blob)
    frame = gltf_frame(document)
    occluders = [p for p in parts if not p["lining"] and p["occludes"]]
    by_name = {}
    for p in parts:
        if p["lining"]:
            by_name[p["mesh"] if p["primitive"] == 0 else f"{p['mesh']}#{p['primitive']}"] = p
    arm, _ = import_armature(entry["path"])
    pixel = float(settings["review_pixel_m"])
    views = int(settings["review_views"])
    max_layers = int(settings["max_layers"])
    variants = {}
    for name, record in mask["linings"].items():
        n = record["triangles"]
        variants[name] = {"mask": lv.unpack_bits(record["keep"], n)}
        for label, bits in entry.get("compare", {}).items():
            if name in bits:
                variants[name][label] = lv.unpack_bits(bits[name], n)
    out = {"source": mask["source"], "mask_settings_sha256": mask["settings_sha256"],
           "review": {"views": views, "pixel_m": pixel, "seed": settings["review_seed"],
                      "poses": [p["name"] for p in job["poses"]]}, "linings": {}}
    missing = set()
    for name, lining in by_name.items():
        totals = {"views": 0, "garment_px": 0, "lining_px": 0,
                  "changed_px": {label: 0 for label in variants[name]}}
        per_pose, worst = {}, {label: [] for label in variants[name]}
        for pose_index, recipe in enumerate(job["poses"]):
            deltas = poser.pose(arm, recipe)
            posed = {id(p): pose_part(p, deltas, missing) for p in occluders + [lining]}
            bvh, ds, offsets = build_bvh([(p, posed[id(p)]) for p in occluders] + [(lining, posed[id(lining)])])
            points = np.concatenate([posed[id(p)][np.unique(p["triangles"])] for p in occluders + [lining]])
            rng = np.random.default_rng(int(settings["review_seed"]) + pose_index)
            dirs = rng.normal(size=(views, 3))
            dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
            row = {"garment_px": 0, "lining_px": 0, "changed_px": {label: 0 for label in variants[name]}}
            for v, d in enumerate(dirs):
                hits, _ = first_hits(bvh, ds, points, d, pixel, max_layers)
                lining_hits = hits[hits >= offsets[-1]] - offsets[-1]
                row["garment_px"] += int((hits >= 0).sum())
                row["lining_px"] += int(len(lining_hits))
                for label, keep in variants[name].items():
                    changed = int((~keep[lining_hits]).sum())
                    row["changed_px"][label] += changed
                    if changed:
                        worst[label].append([changed, recipe["name"], [round(float(x), 3) for x in d]])
            per_pose[recipe["name"]] = row
            totals["views"] += views
            totals["garment_px"] += row["garment_px"]
            totals["lining_px"] += row["lining_px"]
            for label in variants[name]:
                totals["changed_px"][label] += row["changed_px"][label]
        out["linings"][name] = {"totals": totals, "per_pose": per_pose,
                                "worst": {label: sorted(rows, key=lambda r: -r[0])[:5] for label, rows in worst.items()}}
    if "sheet" in entry:
        out["sheet"] = render_sheet(entry, by_name, occluders, variants, arm, poser, frame, max_layers, missing)
    if missing:
        out["errors"] = [f"skin joints missing from the armature: {sorted(missing)}"]
    remove_collection("garment")
    return out, {"seconds": round(time.perf_counter() - started, 2)}


def render_sheet(entry, by_name, occluders, variants, arm, poser, frame, max_layers, missing):
    sheet = {}
    columns = [view[0] for view in SHEET_VIEWS]
    for name, lining in by_name.items():
        folder = Path(entry["sheet"]["dir"]) / _safe(name)
        rows = []
        keep = variants[name]["mask"]
        for recipe in entry["sheet"]["poses"]:
            deltas = poser.pose(arm, recipe)
            posed = {id(p): pose_part(p, deltas, missing) for p in occluders + [lining]}
            worn = build_bvh([(p, posed[id(p)]) for p in occluders] + [(lining, posed[id(lining)])])
            alone = build_bvh([(lining, posed[id(lining)])])
            points = np.concatenate([posed[id(p)][np.unique(p["triangles"])] for p in occluders + [lining]])
            row = _safe(recipe["name"])
            rows.append(row)
            for column, azimuth, elevation, kind in SHEET_VIEWS:
                d = view_direction(frame, azimuth, elevation)
                bvh, ds, offsets = worn if kind == "worn" else alone
                hits, shade = first_hits(bvh, ds, points, d, 0.0, max_layers, size=(260, 340))
                lv.write_png(folder / f"{row}__{column}.png",
                             colour_panel(hits, shade, offsets[-1], keep, kind == "lining"))
        sheet[name] = {"dir": str(folder), "rows": rows, "columns": columns}
    return sheet


# ---------------------------------------------------------------- selfcheck

def selfcheck_job(entry, job, poser):
    """numpy LBS vs Blender's armature modifier, per part, in each job pose."""
    document, blob = lv.read_glb(entry["path"])
    parts = lv.garment_parts(document, blob)
    arm, new = import_armature(entry["path"])
    objects = {obj.name.split(".")[0]: obj for obj in new if obj.type == "MESH"}
    result = {"poses": {}}
    missing = set()
    for recipe in job["poses"]:
        deltas = poser.pose(arm, recipe)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        rows = {}
        for part in parts:
            obj = objects.get(part["node"]) or objects.get(part["mesh"])
            if obj is None:
                rows[part["mesh"]] = {"error": "no Blender object"}
                continue
            world = np.array(obj.matrix_world)
            rest = np.array([v.co[:] for v in obj.data.vertices])
            rest = (np.c_[rest, np.ones(len(rest))] @ (TO_GLTF @ world).T)[:, :3]
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            posed_b = np.array([v.co[:] for v in mesh.vertices])
            evaluated.to_mesh_clear()
            posed_b = (np.c_[posed_b, np.ones(len(posed_b))] @ (TO_GLTF @ world).T)[:, :3]
            tree = KDTree(len(rest))
            for i, p in enumerate(rest.tolist()):
                tree.insert(p, i)
            tree.balance()
            ours = pose_part(part, deltas, missing)
            rest_error, pose_error = 0.0, 0.0
            used = np.unique(part["triangles"])
            positions = part["positions"].tolist()
            for i in used.tolist():
                near = tree.find_range(positions[i], 1e-5)
                if not near:
                    rest_error = max(rest_error, tree.find(positions[i])[2])
                    continue
                pose_error = max(pose_error, min(float(np.linalg.norm(ours[i] - posed_b[k])) for _, k, _ in near))
            moved = float(np.linalg.norm(ours[used] - part["positions"][used], axis=1).max()) if len(used) else 0.0
            rows[part["mesh"]] = {"vertices": int(len(used)), "blender_vertices": len(rest),
                                  "max_rest_mismatch_m": rest_error, "max_pose_error_m": pose_error,
                                  "max_displacement_m": moved}
        result["poses"][recipe["name"]] = rows
    if missing:
        result["errors"] = [f"skin joints missing: {sorted(missing)}"]
    remove_collection("garment")
    return result, {}


# --------------------------------------------------------------------- main

MODES = {"visibility": visibility_job, "review": review_job, "selfcheck": selfcheck_job}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    run = MODES[job["mode"]]
    clear_scene()
    poses = list(job["poses"]) + [p for e in job["glbs"] for p in e.get("sheet", {}).get("poses", [])]
    poser = Poser(job["library"], job["posekit"], any(p["kind"] != "bind" for p in poses))
    failures = 0
    for entry in job["glbs"]:
        print(f"[lining_visibility] {job['mode']} {entry['path']}", flush=True)
        try:
            doc, log = run(entry, job, poser)
        except Exception:  # one bad garment must not stop the batch
            failures += 1
            doc, log = {"errors": [traceback.format_exc()], "source": {"path": entry["path"]}}, {}
            traceback.print_exc()
            remove_collection("garment")
        target = Path(entry["out"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(doc, sort_keys=True, indent=1) + "\n", encoding="utf-8")
        temporary.replace(target)
        if log:
            target.with_suffix(".log.json").write_text(json.dumps(log, sort_keys=True, indent=1) + "\n",
                                                       encoding="utf-8")
        print(f"[lining_visibility] done {entry['path']} {json.dumps(log)[:400]}", flush=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
