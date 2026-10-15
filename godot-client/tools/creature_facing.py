#!/usr/bin/env python3
"""Which way a creature model is authored to face, read from its own rig.

Added 2026-09-02 for Eloria Client.

The client turns an actor's visual root by `forwardAxisCorrectionDegreesY` so
that the body's front points down -Z, the axis everything else in the client
means by forward: server yaw, click targeting and equipment sockets all share
it. Get that number wrong and the creature runs backwards - it slides along its
heading with its tail leading.

The number is not a matter of taste, and it is not one value for a whole
library: these bodies come from several rigs authored facing different ways. It
can be measured. Each cue below is a pair of rig landmarks whose order along
the body is known - front legs ahead of back legs, head ahead of tail, mouth
ahead of skull, and for an upright body with none of those, the knee ahead of
the line from hip to ankle. Each pair gives one reading of the model-space
forward direction, weighted by how far apart the landmarks sit relative to the
whole rig, and the weighted sum is the heading. Landmarks that nearly coincide
carry no bearing and are dropped rather than voting noise: a head directly
above a pelvis says nothing about which way the body looks.

Bodies with no usable landmark - a wisp, a swarm, a floating orb - measure as
None. They are near enough radially symmetric that no correction is right or
wrong for them, and the config leaves them at 0.

    python tools/creature_facing.py [--json] [creature.glb ...]
"""
from __future__ import annotations

import json
import math
import re
import struct
import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1]
CREATURES = CLIENT / "assets/actors/native/creatures"

# Landmark pairs, the front of the body first.
CUES = (
    ("legs", r"(front|fore)[_ ]?(leg|paw|foot|hoof|humerus|scapula)|leg.*front",
     r"(back|rear|hind)[_ ]?(leg|paw|foot|hoof)|leg.*back"),
    ("head_tail", r"^(head|skull|neck)", r"^tail"),
    ("head_hips", r"^(head|skull)", r"hip|pelvis|^body$|^spine[_ ]?0?1$"),
    ("mouth", r"mouth|jaw|snout|muzzle|beak|teeth|tusk|nose",
     r"^(head|skull)|^spine|^chest|^body$|^root$"),
)
# Two landmarks closer together than this, on a rig scaled to 1, are one place
# under two names. Their difference is rig noise rather than a bearing.
MINIMUM_SEPARATION = 0.06

GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A


def gltf_json(path: Path) -> dict:
    """The JSON chunk of a .glb. The node hierarchy is all this reads."""
    raw = Path(path).read_bytes()
    magic, _version, _length = struct.unpack_from("<III", raw, 0)
    if magic != GLB_MAGIC:
        raise ValueError("%s is not a glb" % path)
    offset = 12
    while offset < len(raw):
        size, kind = struct.unpack_from("<II", raw, offset)
        if kind == JSON_CHUNK:
            return json.loads(raw[offset + 8:offset + 8 + size].decode("utf-8"))
        offset += 8 + size + (-size % 4)
    raise ValueError("%s has no JSON chunk" % path)


def _multiply(a: list, b: list) -> list:
    return [[sum(a[row][k] * b[k][column] for k in range(4))
             for column in range(4)] for row in range(4)]


def _node_matrix(node: dict) -> list:
    if "matrix" in node:  # glTF writes a matrix column-major
        m = node["matrix"]
        return [[m[column * 4 + row] for column in range(4)] for row in range(4)]
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    scale = node.get("scale", [1.0, 1.0, 1.0])
    translation = node.get("translation", [0.0, 0.0, 0.0])
    rotation = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [[rotation[row][column] * scale[column] for column in range(3)]
            + [translation[row]] for row in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def bone_positions(gltf: dict) -> dict:
    """Rest-pose scene-space position of every node, by lowercased name."""
    nodes = gltf.get("nodes", [])
    found: dict[str, list] = {}

    def walk(index: int, parent: list) -> None:
        node = nodes[index]
        world = _multiply(parent, _node_matrix(node))
        found.setdefault(str(node.get("name", "")).lower(), []).append(
            (world[0][3], world[1][3], world[2][3]))
        for child in node.get("children", []):
            walk(child, world)

    identity = [[float(row == column) for column in range(4)] for row in range(4)]
    for scene in gltf.get("scenes", []):
        for index in scene.get("nodes", []):
            walk(index, identity)
    return {name: tuple(sum(axis) / len(places) for axis in zip(*places))
            for name, places in found.items()}


def _group(positions: dict, pattern: str):
    hits = [p for name, p in positions.items() if re.search(pattern, name)]
    if not hits:
        return None
    return tuple(sum(axis) / len(hits) for axis in zip(*hits))


def _rig_size(positions: dict) -> float:
    points = list(positions.values())
    if not points:
        return 1.0
    reach = math.dist([max(p[axis] for p in points) for axis in range(3)],
                      [min(p[axis] for p in points) for axis in range(3)])
    return reach if reach > 1e-6 else 1.0


def yaw_of(x: float, z: float) -> float:
    """The Y rotation in degrees that puts this forward vector onto -Z."""
    return math.degrees(math.atan2(x, -z))


def _knee_reading(positions: dict, size: float):
    """A standing leg bows forward at the knee, which is a heading on its own.

    A last resort, for an upright body whose head sits over its hips and whose
    rig names no front and back legs, so nothing else in it points anywhere. A
    quadruped's hock and a bird's ankle bend the other way, which is why this
    never gets to argue with a cue that read the body itself.
    """
    readings = []
    for side in ("_l", "_r"):
        hip = _group(positions, r"^(thigh|upperleg|upper_leg|leg_upper)%s$" % side)
        knee = _group(positions, r"^(calf|shin|lowerleg|lower_leg|leg_lower)%s$" % side)
        ankle = _group(positions, r"^(foot|ankle)%s$" % side)
        if hip is None or knee is None or ankle is None:
            continue
        readings.append(((knee[0] - (hip[0] + ankle[0]) / 2) / size,
                         (knee[2] - (hip[2] + ankle[2]) / 2) / size))
    if not readings:
        return None
    return (sum(r[0] for r in readings) / len(readings),
            sum(r[1] for r in readings) / len(readings))


def _jaw_reading(gltf: dict):
    """Where a jaw hangs in its own parent's frame, which is forward of it.

    The other last resort, for a body with no legs to read: an orb on
    tendrils, a swarm, a floating skull. These rigs put the head's axes on
    the model's, so the jaw's local translation states the heading even when
    the head and the body sit on top of each other in world space.
    """
    for node in gltf.get("nodes", []):
        if str(node.get("name", "")).lower() == "jaw":
            x, _y, z = node.get("translation", [0.0, 0.0, 0.0])
            return (x, z)
    return None


def measure(path: Path) -> dict:
    """The heading of one model, with every reading that voted for it."""
    gltf = gltf_json(path)
    positions = bone_positions(gltf)
    size = _rig_size(positions)
    readings: dict[str, list] = {}
    total_x = total_z = 0.0
    for label, front_pattern, back_pattern in CUES:
        front = _group(positions, front_pattern)
        back = _group(positions, back_pattern)
        if front is None or back is None:
            continue
        x, z = (front[0] - back[0]) / size, (front[2] - back[2]) / size
        weight = math.hypot(x, z)
        if weight < MINIMUM_SEPARATION:
            continue
        readings[label] = [round(yaw_of(x / weight, z / weight), 1), round(weight, 3)]
        total_x, total_z = total_x + x, total_z + z
    if not readings:
        for label, reading in (("knee", _knee_reading(positions, size)),
                               ("jaw", _jaw_reading(gltf))):
            if reading is None:
                continue
            weight = math.hypot(*reading)
            if weight < 1e-6:
                continue
            readings[label] = [
                round(yaw_of(reading[0] / weight, reading[1] / weight), 1),
                round(weight, 3)]
            total_x, total_z = total_x + reading[0] / weight, total_z + reading[1] / weight
            break
    length = math.hypot(total_x, total_z)
    if length < 1e-6:
        return {"heading": None, "spread": None, "readings": readings}
    heading = yaw_of(total_x / length, total_z / length)
    spread = max(abs((yaw - heading + 180) % 360 - 180)
                 for yaw, _weight in readings.values())
    return {"heading": round(heading, 1), "spread": round(spread, 1),
            "readings": readings}


def correction(path: Path):
    """The forwardAxisCorrectionDegreesY this model wants, or None if unreadable."""
    heading = measure(path)["heading"]
    if heading is None:
        return None
    return int(round(heading / 90.0) * 90) % 360


def main(argv: list) -> int:
    as_json = "--json" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")]
    paths = paths or sorted(CREATURES.glob("*.glb"))
    if as_json:
        print(json.dumps({path.stem: measure(path) for path in paths}, indent=1))
        return 0
    for path in paths:
        result = measure(path)
        print("%-32s %-7s %s" % (path.stem, result["heading"], result["readings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
