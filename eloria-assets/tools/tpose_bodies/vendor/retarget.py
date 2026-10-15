"""retarget.py -- move a clip from one skeleton onto another by bone name.

The sixteen meshy bodies each carry their own auto-fitted bind pose. They agree
on bone names (fourteen of them do) but not on where the bones rest: measured
against glasswarden_female, the other thirteen differ by up to 28 degrees per
bone, and glasswarden_male by 125 at Spine02.

That rules out copying curves across. A glTF rotation channel writes an
*absolute* local rotation onto a node, and skinning is
`global(joint) @ inverseBindMatrix(joint)`, so a curve authored against one
bind pose replayed against another carries the difference between the two in
as deformation. Twenty-eight degrees of it, per bone.

So each key is transferred as a delta from the bind pose, in world space:

    delta       = R_source(t) @ R_source_bind^-1
    R_target(t) = delta @ R_target_bind

World space rather than bone-local because the local frames are exactly what
disagree; the world delta is "the upper arm swung forward by this much", which
means the same thing on both rigs. The target's own bind pose is preserved, so
its mesh is undeformed whenever the source's is.

Bone lengths are never transferred -- every joint keeps its own local
translation. The one exception is the pelvis, the only joint either source
animates positionally, whose displacement is scaled by the ratio of the two
rigs' pelvis heights so a short body does not bob like a tall one.
"""

from __future__ import annotations

import numpy as np

import glbkit


class Rig:
    """A skeleton plus the canonical name of each of its joints."""

    def __init__(self, gltf: dict, blob: bytes, joints: list[int],
                 canonical: dict[str, str]) -> None:
        self.gltf = gltf
        self.blob = blob
        self.joints = joints
        self.nodes = gltf["nodes"]
        self.parent = glbkit.parents_of(gltf)
        self.bind_global = glbkit.globals_of(gltf)
        self.order = glbkit.topological(gltf, joints)
        self.by_canonical: dict[str, int] = {}
        for joint in joints:
            name = self.nodes[joint].get("name", "")
            if name in canonical:
                self.by_canonical[canonical[name]] = joint
        # The pose the rig's curves are authored against. For a skinned body
        # that is its bind pose; for the shared library it is the Rest_Pose
        # clip, because the library's node defaults are not a rest pose at all.
        self.reference_global = self.bind_global

    def bind_local(self, joint: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        node = self.nodes[joint]
        return (np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64),
                np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=np.float64),
                np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64))

    def set_reference_clip(self, clip: dict, at: float = 0.0) -> None:
        """Take the reference pose from one frame of `clip`."""
        channels = clip_channels(self.gltf, self.blob, clip)
        times = np.array([at])
        locals_ = {}
        for joint in self.joints:
            node_channels = channels.get(joint, {})
            bind_t, bind_r, bind_s = self.bind_local(joint)
            translation, rotation = bind_t, bind_r
            if "translation" in node_channels:
                keys, values, interp = node_channels["translation"]
                translation = _sample(times, keys, values, interp, False)[0]
            if "rotation" in node_channels:
                keys, values, interp = node_channels["rotation"]
                rotation = _sample(times, keys, values, interp, True)[0]
            locals_[joint] = glbkit.trs_matrix(translation, rotation, bind_s)
        self.reference_global = glbkit.globals_of(self.gltf, locals_)

    def pelvis_height(self) -> float:
        joint = self.by_canonical.get("pelvis")
        if joint is None:
            return 1.0
        return float(self.reference_global[joint][1, 3])

    def bone_direction(self, name: str) -> np.ndarray | None:
        """Unit vector from `name` to its primary child in the reference pose."""
        import bonemap
        child = bonemap.PRIMARY_CHILD.get(name)
        if child is None or name not in self.by_canonical or child not in self.by_canonical:
            return None
        head = self.reference_global[self.by_canonical[name]][:3, 3]
        tail = self.reference_global[self.by_canonical[child]][:3, 3]
        delta = tail - head
        length = float(np.linalg.norm(delta))
        return delta / length if length > 1e-9 else None


# --------------------------------------------------------------------------
# sampling
# --------------------------------------------------------------------------

def _sample(times: np.ndarray, keys: np.ndarray, values: np.ndarray,
            interpolation: str, rotation: bool) -> np.ndarray:
    """Evaluate one channel at `times`, honouring its interpolation."""
    if interpolation == "CUBICSPLINE":
        raise NotImplementedError("CUBICSPLINE channel")
    if len(keys) == 1:
        return np.repeat(values[:1], len(times), axis=0)

    index = np.searchsorted(keys, times, side="right") - 1
    index = np.clip(index, 0, len(keys) - 2)
    if interpolation == "STEP":
        at = np.searchsorted(keys, times, side="right") - 1
        return values[np.clip(at, 0, len(keys) - 1)]

    span = keys[index + 1] - keys[index]
    span[span == 0] = 1.0
    frac = np.clip((times - keys[index]) / span, 0.0, 1.0)
    a, b = values[index], values[index + 1]
    if not rotation:
        return a + (b - a) * frac[:, None]
    return glbkit.slerp_batch(a, b, frac)


def clip_channels(gltf: dict, blob: bytes, clip: dict) -> dict[int, dict[str, tuple]]:
    """{node: {path: (keys, values, interpolation)}} for one animation."""
    out: dict[int, dict[str, tuple]] = {}
    for channel in clip["channels"]:
        target = channel["target"]
        if "node" not in target:
            continue
        sampler = clip["samplers"][channel["sampler"]]
        keys = glbkit.accessor(gltf, blob, sampler["input"]).ravel()
        values = glbkit.accessor(gltf, blob, sampler["output"])
        out.setdefault(target["node"], {})[target["path"]] = (
            keys, values, sampler.get("interpolation", "LINEAR"))
    return out


def clip_times(channels: dict[int, dict[str, tuple]]) -> np.ndarray:
    """Every distinct key time in the clip, which is the timeline we resample to."""
    stack = [keys for paths in channels.values() for keys, _v, _i in paths.values()]
    if not stack:
        return np.zeros(1)
    times = np.unique(np.round(np.concatenate(stack), 6))
    return times if len(times) > 1 else np.array([0.0])


# --------------------------------------------------------------------------
# the transfer
# --------------------------------------------------------------------------

def _align(from_vector: np.ndarray, to_vector: np.ndarray) -> np.ndarray:
    """Smallest rotation taking `from_vector` onto `to_vector`."""
    axis = np.cross(from_vector, to_vector)
    length = float(np.linalg.norm(axis))
    dot = float(np.clip(np.dot(from_vector, to_vector), -1.0, 1.0))
    if length < 1e-9:
        if dot > 0:
            return np.eye(3)
        fallback = np.array([1.0, 0.0, 0.0])
        if abs(from_vector[0]) > 0.9:
            fallback = np.array([0.0, 1.0, 0.0])
        axis = np.cross(from_vector, fallback)
        axis /= np.linalg.norm(axis)
        angle = np.pi
    else:
        axis /= length
        angle = float(np.arctan2(length, dot))
    x, y, z = axis
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * (cross @ cross)


def alignment(source: Rig, target: Rig, names: list[str]) -> dict[str, np.ndarray]:
    """Per-bone rotation putting the target's reference pose in the source's.

    Both rigs rest in something like a T-pose, but not the same one: measured
    at the shoulder the sixteen bodies droop anywhere from 2.5 to 24.4 degrees,
    and the library rests at 18.2. Without this the delta transfer is faithful
    but reads wrong -- an idle that should hang its arms leaves ssarathi's out,
    by exactly the difference between the two rests.

    Bones with no primary child (a hand, the head, a toe leaf) inherit their
    parent's correction so they stay in line with the limb they cap.
    """
    import bonemap
    out: dict[str, np.ndarray] = {}
    ordered = [n for n in bonemap.CANONICAL_NAMES if n in names]
    for name in ordered:
        source_direction = source.bone_direction(name)
        target_direction = target.bone_direction(name)
        if source_direction is None or target_direction is None:
            parent = bonemap.CANONICAL_PARENT.get(name)
            out[name] = out.get(parent, np.eye(3)) if parent else np.eye(3)
        else:
            out[name] = _align(target_direction, source_direction)
    return out


def retarget(source: Rig, clip: dict, target: Rig) -> tuple[np.ndarray, dict[int, dict]]:
    """Return (times, {target node: {"rotation": quats, "translation": xyz}})."""
    channels = clip_channels(source.gltf, source.blob, clip)
    times = clip_times(channels)
    frames = len(times)

    # --- pose the source across the whole timeline, vectorised over frames ---
    local = {}
    for joint in source.order:
        node_channels = channels.get(joint, {})
        bind_t, bind_r, bind_s = source.bind_local(joint)
        if "translation" in node_channels:
            keys, values, interpolation = node_channels["translation"]
            translation = _sample(times, keys, values, interpolation, False)
        else:
            translation = np.repeat(bind_t[None, :], frames, axis=0)
        if "rotation" in node_channels:
            keys, values, interpolation = node_channels["rotation"]
            rotation = _sample(times, keys, values, interpolation, True)
        else:
            rotation = np.repeat(bind_r[None, :], frames, axis=0)
        matrices = np.repeat(np.eye(4)[None, :, :], frames, axis=0)
        matrices[:, :3, :3] = glbkit.quat_to_matrix(rotation) * bind_s
        matrices[:, :3, 3] = translation
        local[joint] = matrices

    source_global = {}
    for joint in source.order:
        parent = source.parent.get(joint)
        if parent in source_global:
            base = source_global[parent]
        else:
            outer = source.bind_global.get(parent, np.eye(4)) if parent is not None else np.eye(4)
            base = np.repeat(outer[None, :, :], frames, axis=0)
        source_global[joint] = base @ local[joint]

    # --- world-space delta per shared bone, onto the aligned reference ---
    shared = [name for name in source.by_canonical if name in target.by_canonical]
    corrections = alignment(source, target, shared)
    wanted: dict[str, np.ndarray] = {}
    for name in shared:
        joint = source.by_canonical[name]
        reference = glbkit.rotations_of(source.reference_global[joint])
        delta = glbkit.rotations_of(source_global[joint]) @ reference.T
        wanted[name] = delta @ corrections[name] @ glbkit.rotations_of(
            target.bind_global[target.by_canonical[name]])

    # --- pelvis displacement, scaled between the two rigs ---
    pelvis_track = None
    if "pelvis" in wanted:
        source_pelvis = source.by_canonical["pelvis"]
        reference_point = source.reference_global[source_pelvis][:3, 3]
        moved = source_global[source_pelvis][:, :3, 3] - reference_point
        scale = target.pelvis_height() / max(source.pelvis_height(), 1e-9)
        pelvis_track = target.bind_global[target.by_canonical["pelvis"]][:3, 3] + moved * scale

    # --- resolve target locals top-down ---
    canonical_of = {joint: name for name, joint in target.by_canonical.items()}
    target_global: dict[int, np.ndarray] = {}
    out: dict[int, dict] = {}
    for joint in target.order:
        parent = target.parent.get(joint)
        if parent in target_global:
            base = target_global[parent]
        else:
            outer = target.bind_global.get(parent, np.eye(4)) if parent is not None else np.eye(4)
            base = np.repeat(outer[None, :, :], frames, axis=0)

        bind_t, bind_r, bind_s = target.bind_local(joint)
        name = canonical_of.get(joint)
        matrices = np.repeat(np.eye(4)[None, :, :], frames, axis=0)

        if name in wanted:
            parent_rotation = glbkit.rotations_of(base)
            local_rotation = np.transpose(parent_rotation, (0, 2, 1)) @ wanted[name]
            quats = glbkit.unroll(glbkit.matrices_to_quats(local_rotation))
            out.setdefault(joint, {})["rotation"] = quats
            matrices[:, :3, :3] = glbkit.quat_to_matrix(quats) * bind_s
        else:
            matrices[:, :3, :3] = glbkit.quat_to_matrix(bind_r) * bind_s

        if name == "pelvis" and pelvis_track is not None:
            points = np.concatenate([pelvis_track, np.ones((frames, 1))], axis=1)
            localised = np.linalg.solve(base, points[:, :, None])[:, :3, 0]
            out.setdefault(joint, {})["translation"] = localised
            matrices[:, :3, 3] = localised
        else:
            matrices[:, :3, 3] = bind_t

        target_global[joint] = base @ matrices

    return times, out


def write_clip(builder: glbkit.BufferAppender, name: str, times: np.ndarray,
               tracks: dict[int, dict]) -> dict:
    """Turn retarget() output into a glTF animation."""
    time_accessor = builder.add(times.reshape(-1, 1), "SCALAR")
    samplers, channels = [], []
    for node, paths in sorted(tracks.items()):
        for path, values in sorted(paths.items()):
            samplers.append({
                "input": time_accessor,
                "output": builder.add(values, "VEC4" if path == "rotation" else "VEC3"),
                "interpolation": "LINEAR",
            })
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": node, "path": path}})
    return {"name": name, "samplers": samplers, "channels": channels}
