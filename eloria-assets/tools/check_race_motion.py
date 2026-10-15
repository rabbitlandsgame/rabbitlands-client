#!/usr/bin/env python3
"""Sample real clips onto every race rig and check what moves.

A race rig can look perfect in bind pose and come apart the moment a clip
plays.  The shared animation library writes absolute rotation tracks for
nearly every joint, so anything a race stores in a rest rotation is
overwritten, and any integrated feature bound to the wrong joint slides off
the body it grows from.  Neither shows in a bind-pose contact sheet.

This poses each race with Idle, Walk, Run and Crouch out of
Universal_Animation_Library.glb, skins the mesh through that rig's own inverse
bind matrices, and reports:

  * ground contact -- the lowest body vertex over the clip.  Every race has to
    reach the floor at some point in every clip, and within a planted clip the
    races have to reach it at the same depth.  A race whose leg chain was
    divided differently otherwise punches through the floor or hangs over it.
  * shoulder plate ride -- how far a Stoneborn pauldron or a Mycelari shelf
    moves relative to the upper-arm bone it sits on.  A plate bound rigidly to
    the clavicle holds still while the arm swings out from under it; measured
    against the bone segment there is no nearest-neighbour partner to pick
    wrongly, which a body-surface search gets wrong across the midline.

Exits non-zero if the ground band is breached.

    python3 eloria-assets/tools/check_race_motion.py
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_native_nymara_glbs import COMPONENT_DTYPES, TYPE_WIDTHS

# There is no bare "Run" or "Idle" in the library; matching on a substring
# quietly picks Run_Jump and Crouch_Idle, which measure a jump and a crouch.
# Each entry is the clip name and whether it stays planted.  Run_Anime leaves
# the ground, and how high a race's foot rides while airborne depends on how
# its leg chain was divided -- legitimate variation that says nothing about
# whether the race plants correctly.  The band is enforced on the planted
# clips and reported for the rest.
CLIPS = {"Idle": ("Idle_A", True), "Walk": ("Walk", True),
         "Run": ("Run_Anime", False), "Crouch": ("Crouch_Walk", True)}
FRAMES = 12
# Ground contact within one clip must agree across the eight races to here.
GROUND_BAND = .03
# Every race must get at least this far below the floor at some point in every
# clip.  This is the check a bind pose cannot make: a race can plant perfectly
# in the A-pose and then hang in the air for a whole run cycle, because
# `solve_leg_scale` solves the rest pose and the clips move the leg somewhere
# the rest pose never goes.  The first digitigrade Ssarathi did exactly that.
PLANT_LIMIT = -.004
DEFAULT_RACES = Path("godot-client/assets/actors/native/races")
DEFAULT_LIBRARY = Path(
    "godot-client/assets/actors/native/shared/Universal_Animation_Library.glb")


def read_glb(path: Path) -> tuple[dict, bytes]:
    raw = Path(path).read_bytes()
    size, _ = struct.unpack_from("<II", raw, 12)
    offset = 20 + size
    length, _ = struct.unpack_from("<II", raw, offset)
    return json.loads(raw[20:20 + size]), raw[offset + 8:offset + 8 + length]


def accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]])
    width = TYPE_WIDTHS[spec["type"]]
    offset = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=binary, offset=offset,
                      strides=strides).copy().astype(np.float64)


def compose(translation, rotation, scale) -> np.ndarray:
    x, y, z, w = rotation
    matrix = np.eye(4)
    matrix[:3, :3] = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]) * np.asarray(scale)[None, :]
    matrix[:3, 3] = translation
    return matrix


def sample(times, values, when, quaternion):
    if len(times) == 1:
        return values[0]
    index = int(np.searchsorted(times, when, side="right") - 1)
    index = max(0, min(index, len(times) - 2))
    span = times[index + 1] - times[index]
    blend = 0. if span <= 0 else float((when - times[index]) / span)
    a, b = values[index], values[index + 1]
    if quaternion:
        if float(a @ b) < 0:
            b = -b
        out = a * (1 - blend) + b * blend
        return out / max(np.linalg.norm(out), 1e-12)
    return a * (1 - blend) + b * blend


def clip_tracks(document: dict, binary: bytes, animation: dict) -> dict:
    tracks: dict = {}
    for channel in animation["channels"]:
        target = channel["target"]
        if target.get("node") is None:
            continue
        name = document["nodes"][target["node"]].get("name")
        sampler = animation["samplers"][channel["sampler"]]
        tracks.setdefault(name, {})[target["path"]] = (
            accessor(document, binary, sampler["input"]),
            accessor(document, binary, sampler["output"]))
    return tracks


def pose(document: dict, tracks: dict, when: float) -> list[np.ndarray]:
    nodes = document["nodes"]
    parent: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parent[child] = index
    local = []
    for node in nodes:
        track = tracks.get(node.get("name"), {})
        translation = np.asarray(node.get("translation", [0., 0., 0.]), dtype=float)
        rotation = np.asarray(node.get("rotation", [0., 0., 0., 1.]), dtype=float)
        scale = np.asarray(node.get("scale", [1., 1., 1.]), dtype=float)
        if "translation" in track:
            translation = sample(*track["translation"], when, False)
        if "rotation" in track:
            rotation = sample(*track["rotation"], when, True)
        if "scale" in track:
            scale = sample(*track["scale"], when, False)
        local.append(compose(translation, rotation, scale))
    world: list[np.ndarray | None] = [None] * len(nodes)

    def resolve(index: int) -> np.ndarray:
        if world[index] is None:
            up = parent.get(index)
            world[index] = local[index] if up is None else resolve(up) @ local[index]
        return world[index]

    for index in range(len(nodes)):
        resolve(index)
    return world


def skinned(document: dict, binary: bytes, world: list) -> dict[str, np.ndarray]:
    skin = document["skins"][0]
    inverse = accessor(document, binary,
                       skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    palette = np.stack([world[n] for n in skin["joints"]]) @ inverse
    out = {}
    for mesh in document["meshes"]:
        parts = []
        for primitive in mesh["primitives"]:
            attributes = primitive["attributes"]
            if "JOINTS_0" not in attributes:
                continue
            points = accessor(document, binary, attributes["POSITION"])
            joints = accessor(document, binary, attributes["JOINTS_0"]).astype(np.int64)
            weights = accessor(document, binary, attributes["WEIGHTS_0"])
            total = weights.sum(axis=1, keepdims=True)
            weights = np.divide(weights, total, out=np.zeros_like(weights),
                                where=total > 1e-8)
            blended = np.einsum("nk,nkij->nij", weights, palette[joints])
            parts.append(np.einsum("nij,nj->ni", blended[:, :3, :3], points)
                         + blended[:, :3, 3])
        if parts:
            out[mesh["name"]] = np.concatenate(parts)
    return out


def segment_distance(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    axis = b - a
    along = np.clip(((points - a) @ axis) / max(float(axis @ axis), 1e-12), 0., 1.)
    return np.linalg.norm(points - (a + along[:, None] * axis), axis=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--races", type=Path, default=DEFAULT_RACES)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    parser.add_argument("--frames", type=int, default=FRAMES)
    args = parser.parse_args()

    library, library_binary = read_glb(args.library)
    by_name = {a.get("name"): a for a in library.get("animations", [])}
    missing = [name for name, _ in CLIPS.values() if name not in by_name]
    if missing:
        print(f"clips not in the library: {missing}", file=sys.stderr)
        return 1

    models = sorted(p.stem for p in args.races.glob("*.glb"))
    ground: dict[str, list[tuple[str, float]]] = {clip: [] for clip in CLIPS}
    print(f"{'race':22} {'clip':7} {'lowest body vertex':>19} {'plate ride':>12}")
    for model in models:
        document, binary = read_glb(args.races / f"{model}.glb")
        joints = document["skins"][0]["joints"]
        names = [document["nodes"][n].get("name") for n in joints]
        feature = next((m["name"] for m in document["meshes"]
                        if m["name"].startswith("Integrated_")), None)
        rest_world = pose(document, {}, 0.)
        rest_feature = skinned(document, binary, rest_world).get(feature) \
            if feature else None

        def bone(world, side):
            arm = np.asarray(world[joints[names.index(f"upperarm_{side}")]])[:3, 3]
            elbow = np.asarray(world[joints[names.index(f"lowerarm_{side}")]])[:3, 3]
            return arm, elbow

        seated = {}
        if rest_feature is not None:
            for side in ("l", "r"):
                arm, elbow = bone(rest_world, side)
                distance = segment_distance(rest_feature, arm, elbow)
                near = distance < .16
                if near.any():
                    seated[side] = (near, distance)

        for label, (clip, _) in CLIPS.items():
            tracks = clip_tracks(library, library_binary, by_name[clip])
            end = max((track[0][-1] for node in tracks.values()
                       for track in node.values()), default=1.)
            lowest = None
            ride = 0.
            for frame in range(args.frames):
                world = pose(document, tracks, end * frame / max(args.frames - 1, 1))
                meshes = skinned(document, binary, world)
                low = float(meshes["Body"][:, 1].min())
                lowest = low if lowest is None else min(lowest, low)
                for side, (near, rest_distance) in seated.items():
                    arm, elbow = bone(world, side)
                    moved = segment_distance(meshes[feature], arm, elbow)
                    ride = max(ride, float(np.abs(moved - rest_distance)[near].max()))
            ground[label].append((model, lowest))
            print(f"{model:22} {label:7} {lowest:19.4f} "
                  f"{(f'{ride:.4f}' if seated else '-'):>12}")

    print()
    failed = False
    floating = [(label, model, low) for label in CLIPS
                for model, low in ground[label] if low > PLANT_LIMIT]
    for label, model, low in floating:
        failed = True
        print(f"FLOATS: {model} never reaches the floor during {label} "
              f"(closest approach {low:+.4f} m)")
    if floating:
        print()
    for label, (_, planted) in CLIPS.items():
        values = [value for _, value in ground[label]]
        spread = max(values) - min(values)
        if not planted:
            status = "airborne, not enforced"
        elif spread <= GROUND_BAND:
            status = "ok"
        else:
            status = "OUT OF BAND"
            failed = True
        print(f"{label:8} ground contact across the races: "
              f"min {min(values):+.4f}  max {max(values):+.4f}  "
              f"spread {spread:.4f} m  [{status}]")
    if failed:
        print("\nA race either hangs above the floor for a whole clip, or a "
              "planted clip's\nground contact varies by more than "
              f"{GROUND_BAND} m between races.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
