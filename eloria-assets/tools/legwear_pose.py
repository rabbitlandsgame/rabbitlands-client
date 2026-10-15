#!/usr/bin/env python3
"""Fit-check a leg garment in motion, not only in bind pose.

Bind-pose coverage proves nothing about a knee at full flexion.  A trouser that
contains the leg standing up can open along the back of the thigh the moment the
knee bends, and a plate cuisse can drive straight through the calf it is meant
to sit over - neither is visible in the file and both are obvious on a player.

The clips are sampled out of the shared library and applied to the race rig by
bone name, which is how the runtime retargets them - **rotation only**.  The
library carries its own skeleton and its bone offsets are not the rig's: its
pelvis sits 114 mm from `luminous_male`'s and its thigh 52 mm.  Substituting the
library's local translation into the rig, which was the first thing tried here,
does not pose the character so much as rebuild it as a different one, and the
fit check then reported two thirds of the body outside its own trousers.  A bone
keeps its own rest translation and scale and takes only the clip's orientation.

Body and garment are then
skinned with the same joint matrices and handed to the same ray-parity check
that measures the bind pose, so a posed number and a rest number mean the same
thing and can be put in the same table.

Sampling is deliberately sparse.  A clip is a loop and neighbouring frames say
almost the same thing; what matters is the extremes, so the default is a handful
of evenly spaced frames per clip rather than all of them.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from footwear_refit import (_accessor, _document, _node_matrix, skeleton,
                            skinned_primitives)
from garment_fit import components

SHARED = "assets/actors/native/shared/Universal_Animation_Library.glb"

#: The clips the brief names.  `Meditate` is the cross-legged floor pose and is
#: the hardest flexion any of these garments will ever see; `Sitting_Exit` is
#: the transition out of it, which passes through a deeper hip angle than the
#: sit itself.
CLIPS = ("Jog", "Sprint", "Meditate", "Sitting_Exit")


@lru_cache(maxsize=4)
def _library(path: str) -> tuple[dict, bytes]:
    return _document(Path(path))


def clip_samples(library: Path, clip: str, count: int = 5) -> list[dict]:
    """`count` evenly spaced frames of one clip, as bone -> local matrix."""
    document, binary = _library(str(library))
    nodes = document.get("nodes", [])
    animation = next((a for a in document.get("animations", [])
                      if a.get("name") == clip), None)
    if animation is None:
        raise KeyError(f"{clip} is not in {library.name}")
    tracks: dict[str, dict[str, tuple[np.ndarray, np.ndarray]]] = {}
    span = 0.0
    for channel in animation["channels"]:
        target = channel.get("target", {})
        node = target.get("node")
        path = target.get("path")
        # Rotation only; see the module docstring.  A translation track would
        # carry the library skeleton's proportions across with the pose.
        if node is None or path != "rotation":
            continue
        name = nodes[node].get("name")
        if not name:
            continue
        sampler = animation["samplers"][channel["sampler"]]
        times = _accessor(document, binary, sampler["input"]).astype(float)
        values = _accessor(document, binary, sampler["output"]).astype(float)
        tracks.setdefault(name, {})[path] = (times, values)
        span = max(span, float(times[-1]) if len(times) else 0.0)
    out = []
    for index in range(count):
        moment = span * index / max(count - 1, 1)
        frame = {name: _sample(paths.get("rotation"), moment)
                 for name, paths in tracks.items()}
        out.append({k: v for k, v in frame.items() if v is not None})
    return out


def _sample(track, moment: float):
    if track is None:
        return None
    times, values = track
    if not len(times):
        return None
    index = int(np.searchsorted(times, moment, side="right")) - 1
    index = max(0, min(index, len(times) - 2)) if len(times) > 1 else 0
    if len(times) == 1:
        return values[0]
    span = max(float(times[index + 1] - times[index]), 1e-9)
    blend = float(np.clip((moment - times[index]) / span, 0.0, 1.0))
    low, high = values[index], values[index + 1]
    if len(low) == 4:  # a quaternion: shortest arc, then renormalise
        if float(low @ high) < 0.0:
            high = -high
        mixed = low * (1.0 - blend) + high * blend
        return mixed / max(float(np.linalg.norm(mixed)), 1e-9)
    return low * (1.0 - blend) + high * blend


def _posed_local(node: dict, rotation) -> np.ndarray:
    """The rig's own local transform with the clip's orientation swapped in."""
    return _node_matrix({
        "translation": node.get("translation", [0.0, 0.0, 0.0]),
        "rotation": list(rotation),
        "scale": node.get("scale", [1.0, 1.0, 1.0])})


def posed_joints(rig_path: Path, frame: dict) -> dict[str, np.ndarray]:
    """World matrix per bone with the clip's local transforms substituted in.

    Bones the clip does not animate keep their rest pose, which is what the
    runtime does too - the library is retargeted by name and carries no track
    for a bone a given rig does not share.
    """
    document, _ = _document(rig_path)
    nodes = document.get("nodes", [])
    world: dict[str, np.ndarray] = {}

    def walk(index: int, parent: np.ndarray) -> None:
        node = nodes[index]
        name = node.get("name", "")
        rotation = frame.get(name)
        matrix = parent @ (_posed_local(node, rotation) if rotation is not None
                           else _node_matrix(node))
        if name:
            world[name] = matrix
        for child in node.get("children", []):
            walk(child, matrix)

    roots = set(range(len(nodes)))
    for node in nodes:
        for child in node.get("children", []):
            roots.discard(child)
    for root in sorted(roots):
        walk(root, np.eye(4))
    return world


def pose_mesh(pieces, rig_path: Path, frame: dict):
    """Skin every primitive of a mesh onto one animation frame."""
    rest = skeleton(str(rig_path))
    world = posed_joints(rig_path, frame)
    out = []
    for piece in pieces:
        homogeneous = np.concatenate(
            [piece.positions, np.ones((len(piece.positions), 1))], axis=1)
        weights = piece.weights.astype(np.float64)
        total = weights.sum(axis=1, keepdims=True)
        weights = weights / np.where(total > 0, total, 1.0)
        moved = np.zeros((len(piece.positions), 3))
        for slot in range(weights.shape[1]):
            share = weights[:, slot]
            if not share.any():
                continue
            for index in np.unique(piece.joints[:, slot]):
                bone = piece.bones[int(index)]
                if bone not in world or bone not in rest.rest:
                    continue
                mask = (piece.joints[:, slot] == index) & (share > 0)
                if not mask.any():
                    continue
                matrix = world[bone] @ np.linalg.inv(rest.rest[bone])
                moved[mask] += (homogeneous[mask] @ matrix.T)[:, :3] * \
                    share[mask][:, None]
        out.append((moved, piece.triangles))
    return out


def posed_components(garment: Path, rig_path: Path, frame: dict):
    shells = []
    for points, triangles in pose_mesh(skinned_primitives(garment),
                                       rig_path, frame):
        shells.extend(components(points, triangles))
    return shells


def _body_slots(rig_path: Path) -> list[int]:
    """Which skinned primitives are the body, in `skinned_primitives` order.

    `skinned_primitives` drops the mesh names, and a race GLB carries painted-on
    wardrobe surfaces beside the body.  Measuring a garment against the wardrobe
    it hides would count cloth as skin, so the same `Body`-only rule
    `garment_fit.body_points` follows is reproduced by walking the document in
    the same order and remembering which primitives came from that mesh.
    """
    document, _ = _document(Path(rig_path))
    slots, index = [], 0
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            if "JOINTS_0" not in primitive.get("attributes", {}):
                continue
            if str(mesh.get("name", "")).lower() == "body":
                slots.append(index)
            index += 1
    return slots


def posed_body(rig_path: Path, frame: dict) -> np.ndarray:
    pieces = skinned_primitives(rig_path)
    slots = _body_slots(rig_path)
    chosen = [pieces[i] for i in slots] if slots else pieces
    moved = pose_mesh(chosen, rig_path, frame)
    return np.concatenate([points for points, _ in moved])


def posed_report(garment: Path, rig_path: Path, frame: dict,
                 rest_region: np.ndarray, rest_body: np.ndarray):
    """Exposed count for one frame, over the region fixed in the bind pose.

    The region has to be chosen at rest and then carried by vertex index.
    Choosing it again in the posed frame is meaningless: the region is the band
    between the garment's hem and its waist, and in `Meditate` - sitting
    cross-legged on the floor - that band contains the entire character, arms
    and head included, so the check asks a trouser to cover a face.  Measured
    that way `Sprint` reported 1881 vertices exposed out of 3033 and the number
    said nothing about the garment.

    Posing is a bijection on vertices, so the honest question is whether the
    *same* skin the garment covers standing up is still covered with the knee
    bent, and that is answered by keeping the mask and moving the points.
    """
    from garment_fit import enclosed_by_any

    body = posed_body(rig_path, frame)
    if len(body) != len(rest_body):
        raise ValueError("posed body does not match the rest body vertex for vertex")
    shells = posed_components(garment, rig_path, frame)
    subject = body[rest_region]
    if not len(subject):
        return 0, 0
    held = enclosed_by_any(subject, shells)
    return int((~held).sum()), int(rest_region.sum())


def rest_region_mask(garment: Path, rig_path: Path):
    """The bind-pose region and body, to be reused for every frame."""
    from garment_fit import garment_components
    from legwear_fit import leg_region

    body = posed_body(rig_path, {})
    shells = garment_components(garment)
    return leg_region(body, shells), body
