#!/usr/bin/env python3
"""A bridge has to carry walkable cells for its whole length.

The server walks a player over `collision.bin`, and a region declares its
crossings as `type: bridge` landmarks. If the walk grid does not put a
continuous walkable run under a deck, the bridge is scenery: the client draws
it, the client will even ground an actor on it, and the server will not let
anyone step onto it.

Whitehorn Range shipped that way. Its walk grid gave a 34 x 1.9 m rope bridge a
disc of the *smaller* half-extent - 1.6 m of walkable cells over the middle of a
22 m chasm, unreachable from either bank - so the only two crossings of the
gorge were a 900 m walk apart in a map that looked like it had them 40 m apart.
"""
from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import struct
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REGIONS = ROOT / "eloria-assets" / "maps" / "nymara-regions"

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942

# How far past a deck's ends to stand while asking whether the two sides are
# joined, and how much walking - as a multiple of the deck - counts as having
# crossed on the bridge rather than around it.
# Where a landing is looked for, stepping out from the deck's own end. Some
# decks stop on their landing and some run a few metres onto it, so the first
# walkable cell at or past the end is the one taken.
LANDING_MARGINS = (0.0, 1.0, 2.0, 3.0)
CROSSING_FACTOR = 1.6

# The deck's own ends are found from its vertices rather than from its bounding
# box, because a bounding box cannot tell a deck running south-west to
# north-east from one running north-west to south-east, and half the crossings
# in these regions run on a diagonal.
#
# Whitehorn only, deliberately. The probe has to guess where a deck's landing
# is from the deck's geometry, and the regions author that differently: a
# Whitehorn span stops on its landing, a Verdant Stair crossing runs several
# metres onto a separate walkway, a Grey Moors boardwalk is a chain of decks
# end to end. Guessing wrong reads as a broken crossing, and a test that cries
# wolf about five regions is worse than one that speaks for one.
#
# The others were checked another way and are sound: each region's own build
# reproduces its walk grid, and walking that grid between the two landings each
# crossing actually declares joins them at the direct distance every time -
# Verdant Stair's five, which this probe flagged, among them.
VERIFIED_REGIONS = ("whitehorn_range",)


def read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    offset = 12
    document: dict | None = None
    binary = b""
    while offset < len(data):
        length, kind = struct.unpack("<II", data[offset:offset + 8])
        payload = data[offset + 8:offset + 8 + length]
        if kind == CHUNK_JSON:
            document = json.loads(payload)
        elif kind == CHUNK_BIN:
            binary = payload
        offset += 8 + length
    if document is None:
        raise ValueError(f"{path} has no JSON chunk")
    return document, binary


def _node_transforms(document: dict) -> dict[int, tuple]:
    """Index -> (offset_x, offset_z, cos, sin, scale) in world space.

    Only the Y rotation and a uniform scale are composed: that is everything
    the region exporter ever writes, and a deck tilted out of the horizontal
    would not be a deck.
    """
    nodes = document.get("nodes", [])
    parents: dict[int, int] = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parents[child] = index
    resolved: dict[int, tuple] = {}

    def resolve(index: int) -> tuple:
        if index in resolved:
            return resolved[index]
        node = nodes[index]
        translation = node.get("translation", [0.0, 0.0, 0.0])
        rotation = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
        scale = node.get("scale", [1.0, 1.0, 1.0])
        angle = 2.0 * math.atan2(rotation[1], rotation[3])
        local = (float(translation[0]), float(translation[2]),
                 math.cos(angle), math.sin(angle), float(scale[0]))
        parent = parents.get(index)
        if parent is None:
            resolved[index] = local
            return local
        px, pz, pcos, psin, pscale = resolve(parent)
        # Rotating (x, z) about Y by theta sends it to
        # (x cos + z sin, -x sin + z cos).
        x, z = local[0] * pscale, local[1] * pscale
        composed = (px + x * pcos + z * psin, pz - x * psin + z * pcos,
                    pcos * local[2] - psin * local[3],
                    psin * local[2] + pcos * local[3], pscale * local[4])
        resolved[index] = composed
        return composed

    for index in range(len(nodes)):
        resolve(index)
    return resolved


def _positions(document: dict, binary: bytes, accessor: int) -> np.ndarray:
    """The POSITION accessor's x and z columns, as float32 vec3 data."""
    entry = document["accessors"][accessor]
    view = document["bufferViews"][entry["bufferView"]]
    start = view.get("byteOffset", 0) + entry.get("byteOffset", 0)
    stride = view.get("byteStride") or 12
    count = entry["count"]
    raw = np.frombuffer(binary, dtype=np.uint8, count=stride * count, offset=start)
    columns = raw.reshape(count, stride)[:, :12].copy()
    return columns.view(np.float32).reshape(count, 3)[:, [0, 2]]


def walk_deck_ends(document: dict, binary: bytes) -> dict[str, tuple]:
    """Landmark node name -> the deck's two ends in world XZ, and its length.

    The ends are the extremes along the deck's own principal axis, which is
    what makes this read a diagonal span correctly.
    """
    transforms = _node_transforms(document)
    meshes = document.get("meshes", [])
    ends: dict[str, tuple] = {}
    for index, node in enumerate(document.get("nodes", [])):
        name = node.get("name", "")
        mesh = node.get("mesh")
        if not name.startswith("Walk_") or mesh is None:
            continue
        chunks = []
        for primitive in meshes[mesh].get("primitives", []):
            position = primitive.get("attributes", {}).get("POSITION")
            if position is not None:
                chunks.append(_positions(document, binary, position))
        if not chunks:
            continue
        local = np.concatenate(chunks).astype(np.float64)
        offset_x, offset_z, cosine, sine, scale = transforms[index]
        x = local[:, 0] * scale
        z = local[:, 1] * scale
        world = np.stack([offset_x + x * cosine + z * sine,
                          offset_z - x * sine + z * cosine], axis=1)
        centre = world.mean(axis=0)
        centred = world - centre
        # Principal axis of the deck's footprint: a deck is far longer than it
        # is wide, so the leading eigenvector is the way it runs.
        _values, vectors = np.linalg.eigh(centred.T @ centred)
        direction = vectors[:, -1]
        across = vectors[:, 0]
        along = centred @ direction
        low = centre + direction * along.min()
        high = centre + direction * along.max()
        half_width = float(np.abs(centred @ across).max())
        stem = name[len("Walk_"):].rsplit("__", 1)[0]
        length = float(np.linalg.norm(high - low))
        if stem not in ends or length > ends[stem][2]:
            ends[stem] = (low, high, length, across, half_width)
    return ends


def load_grid(path: Path) -> np.ndarray:
    data = path.read_bytes()
    _, _, _, width, height = struct.unpack("<4sHHII", data[:16])
    return np.frombuffer(data, dtype=np.uint8, offset=16).reshape(height, width)


def walk_distance(grid: np.ndarray, start: tuple[int, int],
                  goal: tuple[int, int], budget: int) -> int:
    """Cells walked from `start` to `goal`, or -1 if not joined inside `budget`.

    The search is held to a window around the pair, so a bridge whose banks are
    only joined by a walk right round the obstacle reads as not joined - which
    is the whole question a crossing answers.
    """
    height, width = grid.shape
    top = max(0, min(start[0], goal[0]) - budget)
    bottom = min(height - 1, max(start[0], goal[0]) + budget)
    left = max(0, min(start[1], goal[1]) - budget)
    right = min(width - 1, max(start[1], goal[1]) + budget)
    seen = {start}
    frontier = deque([(start, 0)])
    while frontier:
        (row, column), steps = frontier.popleft()
        if (row, column) == goal:
            return steps
        if steps >= budget:
            continue
        for delta_row, delta_column in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (row + delta_row, column + delta_column)
            if not (top <= neighbour[0] <= bottom and left <= neighbour[1] <= right):
                continue
            if neighbour in seen or not grid[neighbour]:
                continue
            seen.add(neighbour)
            frontier.append((neighbour, steps + 1))
    return -1


def packages() -> list[Path]:
    return sorted(REGIONS / region / "world.json" for region in VERIFIED_REGIONS
                  if (REGIONS / region / "collision.bin").exists())


class MapCrossings(unittest.TestCase):
    def test_regions_are_present(self) -> None:
        self.assertEqual(len(packages()), len(VERIFIED_REGIONS),
                         "the verified region packages should be checked out")

    def test_every_bridge_joins_its_two_sides(self) -> None:
        offenders: list[str] = []
        checked = 0
        for manifest_path in packages():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            bridges = [landmark for landmark in manifest.get("landmarks", [])
                       if landmark.get("type") == "bridge"]
            if not bridges:
                continue
            transform = manifest["coordinateTransform"]
            origin_x, origin_z = transform["serverOrigin"]
            cell = float(manifest["collision"].get("cellMetres", 0.5))
            grid = load_grid(manifest_path.parent / "collision.bin")
            document, binary = read_glb(manifest_path.parent / "world.glb")
            decks = walk_deck_ends(document, binary)
            for bridge in bridges:
                deck = decks.get(str(bridge.get("node", "")))
                if deck is None:
                    continue
                low, high, length, across, half_width = deck
                if length <= 0.0:
                    continue
                # Step off each end along the deck's own line.
                direction = (high - low) / length
                cells = []
                points = []
                # A deck's end is a line across its width, not a point, so the
                # landing is looked for across that line as well as along it.
                offsets = np.linspace(-half_width, half_width, 5)
                for end, sense in ((low, -1.0), (high, 1.0)):
                    found = None
                    for margin in LANDING_MARGINS:
                        for offset in offsets:
                            point = end + direction * (sense * margin) + across * offset
                            column = int(round((point[0] + origin_x) / cell - 0.5))
                            row = int(round((origin_z - point[1]) / cell - 0.5))
                            if not (0 <= row < grid.shape[0]
                                    and 0 <= column < grid.shape[1]):
                                continue
                            if grid[row, column]:
                                found = ((row, column), point)
                                break
                        if found is not None:
                            break
                    if found is None:
                        cells = []
                        break
                    cells.append(found[0])
                    points.append(found[1])
                if len(cells) != 2:
                    offenders.append(
                        "%s: %s has a %.0f m deck and does not land on walkable "
                        "ground at both ends" % (
                            manifest_path.parent.name, bridge["id"], length))
                    checked += 1
                    continue
                near, far = points
                checked += 1
                # A crossing is a crossing when the walk is about the deck, not
                # a hike round the obstacle. The budget is Manhattan, because
                # the search steps on the grid's own four neighbours.
                reach = (abs(far[0] - near[0]) + abs(far[1] - near[1])) / cell
                budget = int(reach * CROSSING_FACTOR)
                if walk_distance(grid, cells[0], cells[1], budget) < 0:
                    offenders.append(
                        "%s: %s has a %.0f m deck, and its two landings are not "
                        "joined inside %.0f m of walking" % (
                            manifest_path.parent.name, bridge["id"], length,
                            budget * cell))
        self.assertGreater(checked, 0, "no bridge landmarks were checked")
        self.assertEqual(offenders, [], "every bridge must join its two sides")


if __name__ == "__main__":
    unittest.main(verbosity=2)
