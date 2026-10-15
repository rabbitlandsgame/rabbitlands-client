#!/usr/bin/env python3
"""Structural, skinning and animation validation for creature GLBs.

Checks the exact checked-in binaries rather than any authoring source, and
fails loudly so a broken export cannot reach the client.  Run:

    python3 eloria-assets/tools/validate_creature_glbs.py \
        --catalog godot-client/data/actors/native_asset_catalog.json \
        --models godot-client/data/actors/models.json \
        --animations godot-client/data/animations/creature.json
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

COMPONENT_DTYPES = {5120: "int8", 5121: "uint8", 5122: "int16",
                    5123: "uint16", 5125: "uint32", 5126: "float32"}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

ANIMATION_SAMPLES = 12
GROUND_PENETRATION = .05      # metres a posed mesh may dip below y = 0
MAX_INFLUENCES = 4
MAX_ROOT_DRIFT = .02          # metres of horizontal travel in an in-place clip
MAX_BOUND = 12.0              # metres; anything larger is a scale accident
GROUND_TOLERANCE = .06


def read_glb(path: Path):
    raw = path.read_bytes()
    if raw[:4] != b"glTF":
        raise ValueError("not a glTF 2.0 binary container")
    version, total = struct.unpack_from("<II", raw, 4)
    if version != 2:
        raise ValueError(f"unexpected glTF version {version}")
    if total != len(raw):
        raise ValueError(f"header length {total} != file length {len(raw)}")
    json_size, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != 0x4E4F534A:
        raise ValueError("first chunk is not JSON")
    document = json.loads(raw[20:20 + json_size])
    offset = 20 + json_size
    bin_size, bin_type = struct.unpack_from("<II", raw, offset)
    if bin_type != 0x004E4942:
        raise ValueError("second chunk is not BIN")
    return document, raw[offset + 8:offset + 8 + bin_size]


def accessor(document, binary, index):
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]])
    width = TYPE_WIDTHS[spec["type"]]
    offset = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=binary, offset=offset,
                      strides=strides).copy()


def _quat_matrix(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _local_matrix(node, override):
    matrix = np.eye(4)
    rotation = override.get("rotation", node.get("rotation"))
    scale = override.get("scale", node.get("scale"))
    translation = override.get("translation", node.get("translation"))
    if rotation is not None:
        matrix[:3, :3] = _quat_matrix(rotation)
    if scale is not None:
        matrix[:3, :3] = matrix[:3, :3] @ np.diag(scale)
    if translation is not None:
        matrix[:3, 3] = translation
    return matrix


def _sample(document, binary, animation, time):
    """Sample one clip the way the runtime plays it: linear between keys."""
    pose = {}
    for channel in animation["channels"]:
        sampler = animation["samplers"][channel["sampler"]]
        times = accessor(document, binary, sampler["input"]).astype(float).reshape(-1)
        values = accessor(document, binary, sampler["output"]).astype(float)
        path = channel["target"]["path"]
        if len(times) == 1:
            value = values[0]
        else:
            clamped = float(np.clip(time, times[0], times[-1]))
            index = int(np.clip(np.searchsorted(times, clamped, side="right") - 1,
                                0, len(times) - 2))
            span = max(float(times[index + 1] - times[index]), 1e-9)
            frac = (clamped - float(times[index])) / span
            a, b = values[index].astype(float), values[index + 1].astype(float)
            if path == "rotation":
                if float(np.dot(a, b)) < 0:
                    b = -b
                value = a * (1 - frac) + b * frac
                value = value / max(float(np.linalg.norm(value)), 1e-9)
            else:
                value = a * (1 - frac) + b * frac
        pose.setdefault(channel["target"]["node"], {})[path] = np.asarray(value).tolist()
    return pose


def final_pose_lowest(document, binary, animation):
    """Lowest skinned vertex in the clip's held final pose."""
    result = posed_bounds(document, binary, animation, final_only=True)
    return None if result is None else result[0]


def posed_bounds(document, binary, animation, final_only: bool = False):
    """Lowest posed vertex and largest posed extent across a clip."""
    nodes = document.get("nodes", [])
    skins = document.get("skins", [])
    if not skins:
        return None
    joints = skins[0]["joints"]
    ibm = accessor(document, binary, skins[0]["inverseBindMatrices"]).astype(float)
    ibm = ibm.reshape(-1, 4, 4).transpose(0, 2, 1)
    duration = 0.0
    for channel in animation["channels"]:
        times = accessor(document, binary,
                         animation["samplers"][channel["sampler"]]["input"]).astype(float)
        duration = max(duration, float(times.max()))
    meshes = document.get("meshes", [])
    lowest, widest = float("inf"), 0.0
    if final_only:
        stamps = [duration]
    else:
        stamps = {duration * s / ANIMATION_SAMPLES for s in range(ANIMATION_SAMPLES + 1)}
        for channel in animation["channels"]:
            times = accessor(document, binary,
                             animation["samplers"][channel["sampler"]]["input"]).astype(float)
            stamps.update(float(x) for x in times.reshape(-1))
        stamps = sorted(stamps)
    for time in stamps:
        pose = _sample(document, binary, animation, time)
        world = {}

        def walk(index, parent):
            current = parent @ _local_matrix(nodes[index], pose.get(index, {}))
            world[index] = current
            for child in nodes[index].get("children", []):
                walk(child, current)

        scene = document.get("scenes", [{}])[document.get("scene", 0)]
        for root in scene.get("nodes", range(len(nodes))):
            walk(root, np.eye(4))
        matrices = np.stack([world.get(j, np.eye(4)) @ ibm[i]
                             for i, j in enumerate(joints)])
        for node_index, node in enumerate(nodes):
            if "mesh" not in node or "skin" not in node:
                continue
            for primitive in meshes[node["mesh"]].get("primitives", []):
                attributes = primitive["attributes"]
                if "JOINTS_0" not in attributes:
                    continue
                positions = accessor(document, binary, attributes["POSITION"]).astype(float)
                joint_ids = accessor(document, binary, attributes["JOINTS_0"]).astype(int)
                weights = accessor(document, binary, attributes["WEIGHTS_0"]).astype(float)
                homogeneous = np.concatenate([positions, np.ones((len(positions), 1))], 1)
                skinned = np.zeros_like(positions)
                for slot in range(joint_ids.shape[1]):
                    weight = weights[:, slot:slot + 1]
                    if not weight.any():
                        continue
                    picked = matrices[np.clip(joint_ids[:, slot], 0, len(matrices) - 1)]
                    skinned += weight * np.einsum("nij,nj->ni", picked, homogeneous)[:, :3]
                if not np.isfinite(skinned).all():
                    return ("non-finite", 0.0)
                lowest = min(lowest, float(skinned[:, 1].min()))
                widest = max(widest, float((skinned.max(0) - skinned.min(0)).max()))
    return (lowest, widest)


def check(document, binary, path: Path, required_clips, attachment_bones,
          hovers: bool = False):
    """``hovers`` exempts wisps, elementals and swarms from ground contact:
    a floating creature legitimately never touches y = 0."""
    problems: list[str] = []
    nodes = document.get("nodes", [])
    names = [n.get("name", "") for n in nodes]

    # ---- container / external dependencies ------------------------------
    for image in document.get("images", []):
        if "uri" in image:
            problems.append(f"image '{image.get('name')}' depends on external URI {image['uri']}")
    for buffer in document.get("buffers", []):
        if "uri" in buffer:
            problems.append("buffer depends on an external .bin file")
    if not document.get("meshes"):
        problems.append("no meshes")
    for extra in ("cameras", "KHR_lights_punctual"):
        if document.get(extra):
            problems.append(f"unexpected {extra} in a creature asset")

    # ---- surfaces --------------------------------------------------------
    # Every creature carries an embedded colour map and a matching normal map;
    # a flat, untextured material is the defect this library started with.
    materials = document.get("materials", [])
    if not materials:
        problems.append("no materials")
    textured = False
    normalled = False
    for material in materials:
        pbr = material.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            textured = True
        if "normalTexture" in material:
            normalled = True
        factor = pbr.get("baseColorFactor")
        if factor and len(factor) >= 3:
            r, g, b = factor[:3]
            if r > .9 and b > .9 and g < .2:
                problems.append(f"material '{material.get('name')}' is magenta")
    if not textured:
        problems.append("no material carries a base colour texture")
    if not normalled:
        problems.append("no material carries a normal map")

    # ---- skin / skeleton -------------------------------------------------
    skins = document.get("skins", [])
    if len(skins) != 1:
        problems.append(f"expected exactly one skin, found {len(skins)}")
    joint_set: set[int] = set()
    for skin in skins:
        joints = skin.get("joints", [])
        if not joints:
            problems.append("skin has no joints")
        joint_set.update(joints)
        if "inverseBindMatrices" not in skin:
            problems.append("skin has no inverseBindMatrices")
        else:
            ibm = accessor(document, binary, skin["inverseBindMatrices"])
            if len(ibm) != len(joints):
                problems.append(f"inverseBindMatrices count {len(ibm)} != joints {len(joints)}")
            if not np.isfinite(ibm).all():
                problems.append("inverseBindMatrices contain non-finite values")
        joint_names = [names[j] for j in joints]
        duplicates = {n for n in joint_names if joint_names.count(n) > 1}
        if duplicates:
            problems.append(f"duplicate bone names: {sorted(duplicates)}")
        if "" in joint_names:
            problems.append("unnamed bone in skin")
        missing = [b for b in attachment_bones if b not in joint_names]
        if missing:
            problems.append(f"runtime attachment bones absent from rig: {missing}")
        # exactly one root among the joints
        parents = {child for node in nodes for child in node.get("children", [])}
        roots = [j for j in joints if j not in parents]
        if len(roots) != 1:
            problems.append(f"expected 1 root bone, found {len(roots)}: "
                            f"{[names[r] for r in roots]}")

    # ---- meshes / skinning ----------------------------------------------
    total_tris = 0
    all_positions = []
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            attributes = primitive["attributes"]
            positions = accessor(document, binary, attributes["POSITION"])
            all_positions.append(positions)
            if not np.isfinite(positions).all():
                problems.append("non-finite vertex positions")
            if "indices" not in primitive:
                problems.append("primitive without indices")
                continue
            indices = accessor(document, binary, primitive["indices"])
            total_tris += len(indices) // 3
            if len(indices) % 3:
                problems.append("index count is not a multiple of 3")
            if indices.max(initial=0) >= len(positions):
                problems.append("index out of range")
            if "NORMAL" not in attributes:
                problems.append("primitive missing NORMAL")
            else:
                normals = accessor(document, binary, attributes["NORMAL"])
                lengths = np.linalg.norm(normals, axis=1)
                if not np.isfinite(lengths).all() or (lengths < .5).any():
                    problems.append("degenerate or unnormalised normals")
            if "TEXCOORD_0" not in attributes:
                problems.append("primitive missing TEXCOORD_0")
            if primitive.get("material") is None:
                problems.append("primitive without a material")
            if skins:
                if "JOINTS_0" not in attributes or "WEIGHTS_0" not in attributes:
                    problems.append("skinned asset has a primitive without skin attributes")
                    continue
                joints = accessor(document, binary, attributes["JOINTS_0"])
                weights = accessor(document, binary, attributes["WEIGHTS_0"]).astype(float)
                sums = weights.sum(axis=1)
                if (sums < .999).any() or (sums > 1.001).any():
                    problems.append(f"weights not normalised (min {sums.min():.3f}, "
                                    f"max {sums.max():.3f})")
                if (sums <= 0).any():
                    problems.append("unweighted vertices present")
                influences = (weights > 0).sum(axis=1)
                if influences.max(initial=0) > MAX_INFLUENCES:
                    problems.append(f"{influences.max()} influences per vertex exceeds "
                                    f"{MAX_INFLUENCES}")
                referenced = np.unique(joints[weights > 0])
                joint_count = len(skins[0]["joints"])
                if referenced.size and referenced.max() >= joint_count:
                    problems.append("skin references a joint index outside the skin")

    if all_positions:
        stacked = np.concatenate(all_positions)
        low, high = stacked.min(axis=0), stacked.max(axis=0)
        span = float((high - low).max())
        if span > MAX_BOUND:
            problems.append(f"implausible bounds: {span:.2f}m across")
        if span < .05:
            problems.append(f"degenerate bounds: {span:.3f}m across")
        if hovers:
            if float(low[1]) < -GROUND_TOLERANCE:
                problems.append(f"hovering creature dips below the floor at "
                                f"y={float(low[1]):.3f}")
        elif abs(float(low[1])) > GROUND_TOLERANCE:
            problems.append(f"not grounded: lowest vertex at y={float(low[1]):.3f}")

    # ---- animations ------------------------------------------------------
    animations = document.get("animations", [])
    clip_names = [a.get("name", "") for a in animations]
    duplicates = {n for n in clip_names if clip_names.count(n) > 1}
    if duplicates:
        problems.append(f"duplicate animation names: {sorted(duplicates)}")
    missing = [c for c in required_clips if c not in clip_names]
    if missing:
        problems.append(f"missing required clips: {missing}")
    for animation in animations:
        name = animation.get("name", "<unnamed>")
        if not animation.get("channels"):
            problems.append(f"clip '{name}' has no channels")
            continue
        duration = 0.0
        for channel in animation["channels"]:
            target = channel["target"]
            node = target.get("node")
            if node is None or node >= len(nodes):
                problems.append(f"clip '{name}' targets a nonexistent node")
                continue
            if joint_set and node not in joint_set:
                problems.append(f"clip '{name}' targets non-joint node '{names[node]}'")
            if target["path"] == "scale":
                problems.append(f"clip '{name}' animates scale on '{names[node]}'")
            sampler = animation["samplers"][channel["sampler"]]
            times = accessor(document, binary, sampler["input"])
            values = accessor(document, binary, sampler["output"])
            if len(times) == 0:
                problems.append(f"clip '{name}' has an empty sampler")
                continue
            if not np.isfinite(times).all() or not np.isfinite(values).all():
                problems.append(f"clip '{name}' has non-finite keys")
            if float(times.min()) < -1e-4:
                problems.append(f"clip '{name}' has negative key times")
            duration = max(duration, float(times.max()))
            if target["path"] == "translation" and names[node] == "root":
                travel = values[:, [0, 2]]
                drift = float(np.abs(travel).max())
                if drift > MAX_ROOT_DRIFT:
                    problems.append(f"clip '{name}' drifts the root {drift:.3f}m "
                                    "horizontally (locomotion must be in place)")
        if duration <= 0:
            problems.append(f"clip '{name}' has zero duration")
        if duration > 12:
            problems.append(f"clip '{name}' is implausibly long ({duration:.1f}s)")
        posed = posed_bounds(document, binary, animation)
        if posed is not None:
            lowest, widest = posed
            if lowest == "non-finite":
                problems.append(f"clip '{name}' produces non-finite skinned vertices")
            else:
                if lowest < -GROUND_PENETRATION and not (hovers and name != "Death_A"):
                    problems.append(f"clip '{name}' drives the mesh {abs(lowest):.3f}m "
                                    "below the ground plane")
                if widest > MAX_BOUND:
                    problems.append(f"clip '{name}' explodes the bounds to {widest:.1f}m")
        if name == "Death_A":
            resting = final_pose_lowest(document, binary, animation)
            if resting is not None and not isinstance(resting, str) and resting > .06:
                problems.append(f"clip '{name}' ends with the body floating "
                                f"{resting:.3f}m above the ground")
    return problems, total_tris


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--animations", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    models = json.loads(args.models.read_text())
    animation_map = json.loads(args.animations.read_text())
    required_clips = sorted(set(animation_map.get("actions", {}).values()))

    creature_models = {key: value for key, value in models.get("models", {}).items()
                       if str(value.get("animationMap", "")).endswith("creature.json")}
    attachment_bones = sorted({bone for value in creature_models.values()
                               for bone in value.get("attachments", {}).values()})

    entries = dict(catalog.get("creatures", {}))
    entries.update(catalog.get("ambientCreatures", {}))

    failures = 0
    checked = 0
    print(f"required clips: {required_clips}")
    print(f"runtime attachment bones: {attachment_bones}\n")

    # every creature model in models.json must have a catalog entry and a file
    for model_id, config in sorted(creature_models.items()):
        scene = str(config.get("scene", ""))
        relative = scene.replace("res://", "godot-client/")
        path = args.root / relative
        if model_id not in entries:
            print(f"FAIL {model_id}: referenced by models.json but absent from the catalog")
            failures += 1
            continue
        if not path.exists():
            print(f"FAIL {model_id}: missing GLB at {relative}")
            failures += 1
            continue
        library = str(config.get("animationLibrary", ""))
        if library and library != scene:
            print(f"WARN {model_id}: animationLibrary differs from scene ({library})")
        try:
            document, binary = read_glb(path)
            problems, tris = check(document, binary, path, required_clips,
                                   attachment_bones, bool(entries[model_id].get("hovers")))
        except Exception as error:  # noqa: BLE001 - report and keep scanning
            print(f"FAIL {model_id}: unreadable ({error})")
            failures += 1
            continue
        checked += 1
        if problems:
            failures += 1
            print(f"FAIL {model_id} ({relative}) [{tris} tris]")
            for problem in problems:
                print(f"       - {problem}")
        else:
            print(f"ok   {model_id:<22} {tris:>6} tris")

    # actor-type coverage
    actor_types = models.get("actorTypes", {})
    for actor_type, model_id in sorted(actor_types.items(), key=lambda kv: str(kv[0])):
        if model_id in creature_models and model_id not in entries:
            print(f"FAIL actorType {actor_type} -> {model_id}: no catalog entry")
            failures += 1

    print(f"\n{checked} creature GLBs validated, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
