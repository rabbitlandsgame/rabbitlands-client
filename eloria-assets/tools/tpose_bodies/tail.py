"""Ssarathi source-art tail mask and the existing 12-edge-hop feather policy.

Adapted from fix_ssarathi_tail_weights.py. Weld the adjacency graph only;
the exported vertices and faces remain intact. No cape/tail bones are added.
"""

from collections import deque
import io
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
from audit import g, retarget
from verify import sample_worlds


def lifted_shape(v, alpha, source_pelvis, target_pelvis, library, nodes):
    """Rigidly lift the source tail enough to clear ground over locomotion.

    This is a whole-part placement about pelvis, blended only at its existing
    attachment. Its curve/length are retained; the rig gains no new bones.
    """
    lib, blob = g.read(library)
    doc = {"nodes": nodes}
    pi = next(i for i, n in enumerate(nodes) if n["name"] == "pelvis")
    inverse = np.linalg.inv(g.globals_of(doc)[pi])
    mats = []
    for name in ("Idle_Subtle", "Walk", "Jog", "Run_Female", "Fighting_Idle"):
        clip = next(a for a in lib["animations"] if a["name"] == name)
        duration = float(
            retarget.clip_times(retarget.clip_channels(lib, blob, clip)).max()
        )
        for w in sample_worlds(
            doc, lib, blob, clip, np.linspace(0, duration, int(duration * 30) + 2)
        ):
            mats.append(w[pi] @ inverse)
    mats = np.array(mats)
    interior = alpha > 0.99
    relative = v - source_pelvis
    horizontal = np.mean(relative[interior], axis=0)
    horizontal[1] = 0
    horizontal /= np.linalg.norm(horizontal)
    axis = np.cross(horizontal, [0.0, 1.0, 0.0])
    for angle in np.arange(0.0, 60.5, 0.5):
        rot = Rotation.from_rotvec(axis * np.deg2rad(angle)).as_matrix()
        placed = relative @ rot.T + target_pelvis
        floor = (mats[:, 1, :3] @ placed[interior].T + mats[:, 1, 3, None]).min()
        if floor >= 0.015:
            return placed, {
                "lift_degrees": float(angle),
                "minimum_replayed_rigid_tail_y_m": float(floor),
            }
    raise ValueError("Tail placement did not clear the ground within 60 degrees")


def feather(d, b, p, v, uv, faces, anchors):
    material = d["materials"][p.get("material", 0)]
    ti = material["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    im = d["images"][d["textures"][ti]["source"]]
    view = d["bufferViews"][im["bufferView"]]
    start = 8 + view.get("byteOffset", 0)
    tex = (
        np.asarray(
            Image.open(
                io.BytesIO(bytes(b[start : start + view["byteLength"]]))
            ).convert("RGB")
        )
        / 255.0
    )
    q = uv[faces].mean(1)
    c = v[faces].mean(1)
    rgb = tex[
        np.clip((q[:, 1] * tex.shape[0]).astype(int), 0, tex.shape[0] - 1),
        np.clip((q[:, 0] * tex.shape[1]).astype(int), 0, tex.shape[1] - 1),
    ]
    green = (rgb[:, 1] > rgb[:, 0] + 0.008) & (rgb[:, 1] > rgb[:, 2] + 0.020)
    # Colour is useful for inspection, but stripes/highlights must never make
    # internal "boundaries" in a tail. Use the prior tool's distance-to-limb
    # policy for the whole tail region, including its lighter underside.
    distance = np.full(len(c), np.inf)
    for side in ("l", "r"):
        points = [
            anchors[n + "_" + side].copy() for n in ("thigh", "calf", "foot", "ball")
        ]
        points.append(points[-1] + np.array([0.0, 0.0, 0.15]))
        for a, z in zip(points, points[1:]):
            axis = z - a
            t = np.clip(((c - a) @ axis) / (axis @ axis), 0, 1)
            distance = np.minimum(
                distance, np.linalg.norm(c - a - t[:, None] * axis, axis=1)
            )
    selected = (
        (distance > 0.115)
        & ((c[:, 0] > 0.13) | (c[:, 2] < -0.11))
        & (c[:, 1] < anchors["pelvis"][1] + 0.02)
    )
    _, inverse = np.unique(np.round(v, 5), axis=0, return_inverse=True)
    ff = inverse[faces]
    total = np.bincount(ff.ravel())
    votes = np.bincount(ff[selected].ravel(), minlength=len(total))
    mask = votes / np.maximum(total, 1) > 0.45
    neighbours = [set() for _ in mask]
    for a, z, c in ff:
        for i, j in [(a, z), (z, c), (c, a)]:
            neighbours[i].add(j)
            neighbours[j].add(i)
    distance = np.full(len(mask), -1, dtype=int)
    queue = deque()
    for i in np.flatnonzero(mask):
        if any(not mask[j] for j in neighbours[i]):
            distance[i] = 0
            queue.append(i)
    while queue:
        i = queue.popleft()
        for j in neighbours[i]:
            if mask[j] and distance[j] < 0:
                distance[j] = distance[i] + 1
                queue.append(j)
    t = np.zeros(len(mask))
    t[mask & (distance < 0)] = 1
    used = mask & (distance >= 0)
    t[used] = np.minimum(1, distance[used] / 12.0)
    alpha = (t * t * (3 - 2 * t))[inverse]
    return alpha, {
        "selected_faces": int(selected.sum()),
        "feather_hops": 12,
        "feathered_vertices": int((alpha > 0).sum()),
        "rigid_vertices": int((alpha == 1).sum()),
        "binding": "pelvis",
    }
