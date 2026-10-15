#!/usr/bin/env python3
"""Checks across the continent-v2 territories: ownership, shared seam vertices, mirrored seam patches.

The active island group is derived from the recorded section partition. Each active map is a byte crop of the
external, hash-pinned frozen group terrain (bootstrap_continent_v2_territory.py), so the vertices two neighbours share are bit-identical by construction. These
checks keep that true while the maps are edited:

- ownership: no two polygons overlap (no 2 m cell centre strictly inside two of them), and every vertex of every
  island land component (base > 0 m, 8-connected) that stays inside the group grid lies in one polygon. The one
  component that reaches the group grid's edge is the mainland, which a future map owns.
- shared vertices: a territory's authority is its owned cells' vertices plus one 3x3 ring
  (eloria-assets/maps/nymara-regions/_continent/authoring.py required_terrain_vertices); where two authorities
  overlap, both base height files hold the same float32 bytes;
- crops: a territory whose provenance names a crop holds exactly that sub-array of the parent's base heights and
  colours;
- what the editor adds on top of the base: no sculpt delta on a shared vertex, every terrain patch that touches a
  shared vertex declared identically (continent rectangle, height, shape, operation, feather) in both scenes, no
  sculpt delta anywhere under such a mirrored patch (a seam mole: its Set hides a delta, which would come back if the
  mole were disabled, feathered or resized), no path that shapes the terrain (terrainConform is false everywhere,
  the v2 convention), and no river path or water region within 2 m of a shared vertex (a river carves the terrain
  and a water region draws water, so either would make the two sides of a seam differ);
- frames: each scene root's ownership sha, server origin and cells and its Terrain origin and grid agree with its
  manifest and authoring spec;
- published: each catalog entry names its client package (publishedManifestPath, the registry row's manifest), and a
  served territory (its package ships a served grid, or its registry row is continent-v2-served) keeps the frame it
  was served in: served_frame_problems, which the bootstrap also runs before it writes.

Usage: python godot-client/tools/continent_v2_territories.py  (prints a JSON report; exit 1 on any problem).
The pytest godot-client/tests/test_continent_v2_territories.py runs the same checks.
"""
from __future__ import annotations

import functools
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CHECKOUT = Path(__file__).resolve().parents[2]
CLIENT = CHECKOUT / "godot-client"
CATALOG = CLIENT / "world_authoring" / "continent-v2" / "territories.json"
CELL = 2.0
PATCH_SCRIPT = "res://src/dev/map_authoring_region/terrain_patch.gd"
PATH_SCRIPT = "res://src/dev/map_authoring_region/path_control.gd"
TERRAIN_SCRIPT = "res://src/dev/map_authoring_region/terrain_control.gd"
WATER_SCRIPT = "res://src/dev/map_authoring_region/water_region_control.gd"
# How close (metres) a river's edge or a water region's rim may come to a shared vertex.
SEAM_WATER_CLEARANCE = 2.0


def res_to_path(resource: str, checkout: Path = CHECKOUT) -> Path:
    if resource.startswith("res://../"):
        return checkout / resource[len("res://../"):]
    if resource.startswith("res://"):
        return checkout / "godot-client" / resource[len("res://"):]
    return checkout / resource


def polygon_sha(polygon) -> str:
    """territory_catalog.gd: JSON.stringify of the float polygon, sha256 of the text."""
    text = "[" + ",".join("[%s,%s]" % (repr(float(x)), repr(float(z))) for x, z in polygon) + "]"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def polygons_sha(polygons) -> str:
    """Single-ring hashes retain the existing contract; multipart hashes include every ordered ring."""
    if len(polygons) == 1:
        return polygon_sha(polygons[0])
    text = json.dumps([[[float(x), float(z)] for x, z in ring] for ring in polygons], separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def territory_classify(px, pz, territory):
    rings = territory.polygons if territory.polygons is not None else [territory.polygon]
    result = np.zeros(np.broadcast(np.asarray(px), np.asarray(pz)).shape, np.uint8)
    for ring in rings:
        result = np.maximum(result, classify(px, pz, ring))
    return result


def classify(px, pz, polygon) -> np.ndarray:
    """0 outside, 1 strictly inside, 2 on the boundary. Exact for integer coordinates (every v2 polygon vertex and
    terrain vertex lies on whole metres)."""
    px = np.asarray(px, np.float64)
    pz = np.asarray(pz, np.float64)
    inside = np.zeros(np.broadcast(px, pz).shape, bool)
    edge = np.zeros_like(inside)
    count = len(polygon)
    for index in range(count):
        ax, az = map(float, polygon[index])
        bx, bz = map(float, polygon[(index + 1) % count])
        cross = (bx - ax) * (pz - az) - (bz - az) * (px - ax)
        within = (px >= min(ax, bx)) & (px <= max(ax, bx)) & (pz >= min(az, bz)) & (pz <= max(az, bz))
        edge |= (cross == 0.0) & within
        crosses = (az > pz) != (bz > pz)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = ax + (pz - az) * (bx - ax) / (bz - az)
        inside ^= crosses & (px < x_at)
    return np.where(edge, 2, np.where(inside, 1, 0))


# --- a small .tscn reader -------------------------------------------------------------------------------------------

_HEADER = re.compile(r'^\[(gd_scene|ext_resource|sub_resource|node|editable|connection)\b(.*)\]\s*$')
_ATTRIBUTE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\[[^\]]*\]|ExtResource\("[^"]*"\)|\S+)')
_PROPERTY = re.compile(r'^([A-Za-z_][A-Za-z0-9_/:]*) = (.*)$')


@dataclass
class Section:
    kind: str
    attributes: dict
    properties: dict = field(default_factory=dict)


def _attribute_value(text: str):
    if text.startswith('"') and text.endswith('"'):
        return json.loads(text)
    return text


def read_tscn(path: Path) -> list[Section]:
    sections: list[Section] = []
    current: Section | None = None
    key = None
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            header = _HEADER.match(line)
            if header:
                attributes = {name: _attribute_value(value) for name, value in _ATTRIBUTE.findall(header.group(2))}
                current = Section(header.group(1), attributes)
                sections.append(current)
                key = None
                continue
            if current is None:
                continue
            prop = _PROPERTY.match(line)
            if prop:
                key = prop.group(1)
                current.properties[key] = prop.group(2)
            elif key is not None and line:
                current.properties[key] += "\n" + line
    return sections


def _numbers(text: str, kind: str) -> list[float]:
    match = re.fullmatch(kind + r"\((.*)\)", text.strip(), re.S)
    if not match:
        raise ValueError(f"not a {kind}: {text[:80]}")
    body = match.group(1).strip()
    return [float(value) for value in body.split(",")] if body else []


def transform(text: str | None) -> np.ndarray:
    """A 4x4 matrix from Godot's Transform3D text (basis columns, then the origin)."""
    matrix = np.eye(4)
    if text is None:
        return matrix
    values = _numbers(text, "Transform3D")
    matrix[:3, :3] = np.asarray(values[:9]).reshape(3, 3).T
    matrix[:3, 3] = values[9:12]
    return matrix


def nums(s):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", s)]


def _property(body, name, kind):
    match = re.search(r"^" + re.escape(name) + r" = " + kind + r"\(([^)]*)\)", body, re.M)
    return np.asarray(nums(match.group(1))) if match else None


def transform_matrix(body):
    """Godot Transform3D stores three basis columns, followed by the origin.

    Otherwise compose Node3D's position, Euler rotation (Godot's intrinsic
    rotation_order, default YXZ), or quaternion, and scale.
    """
    result = np.eye(4)
    values = _property(body, "transform", "Transform3D")
    if values is not None:
        if len(values) != 12:
            raise ValueError("Transform3D needs 12 values")
        result[:3, :3] = values[:9].reshape(3, 3).T
        result[:3, 3] = values[9:]
        return result
    position = _property(body, "position", "Vector3")
    scale = _property(body, "scale", "Vector3")
    quaternion = _property(body, "quaternion", "Quaternion")
    if quaternion is not None:
        quaternion = quaternion / np.linalg.norm(quaternion)
        x, y, z, w = quaternion
        result[:3, :3] = [[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
                          [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
                          [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)]]
    else:
        rotation = _property(body, "rotation", "Vector3")
        degrees = _property(body, "rotation_degrees", "Vector3")
        if rotation is None and degrees is not None:
            rotation = np.radians(degrees)
        if rotation is not None:
            order_match = re.search(r"^rotation_order = (\d+)", body, re.M)
            order = ("xyz", "xzy", "yxz", "yzx", "zxy", "zyx")[int(order_match.group(1)) if order_match else 2]
            x, y, z = rotation
            cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
            axes = {"x": np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]]),
                    "y": np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]]),
                    "z": np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]])}
            for axis in order:
                result[:3, :3] = result[:3, :3] @ axes[axis]
    if scale is not None:
        result[:3, :3] = result[:3, :3] @ np.diag(scale)
    if position is not None:
        result[:3, 3] = position
    return result



@dataclass
class Scene:
    path: Path
    ext: dict
    sub: dict
    nodes: dict  # node path ("." for the root) -> Section

    def node(self, path: str) -> Section | None:
        return self.nodes.get(path)

    def script_of(self, section: Section) -> str:
        text = section.properties.get("script", "")
        match = re.fullmatch(r'ExtResource\("([^"]+)"\)', text.strip())
        return self.ext.get(match.group(1), "") if match else ""

    def world(self, path: str) -> np.ndarray:
        """The node's transform relative to the scene root."""
        matrix = np.eye(4)
        parts = [] if path == "." else path.split("/")
        for depth in range(1, len(parts) + 1):
            section = self.nodes.get("/".join(parts[:depth]))
            matrix = matrix @ transform_matrix("\n".join(f"{k} = {v}" for k,v in section.properties.items()) if section else "")
        return matrix


@functools.lru_cache(maxsize=None)
def load_scene(path: Path) -> Scene:
    sections = read_tscn(path)
    ext = {s.attributes["id"]: s.attributes.get("path", "") for s in sections if s.kind == "ext_resource"}
    sub = {s.attributes["id"]: s for s in sections if s.kind == "sub_resource"}
    nodes = {}
    for section in sections:
        if section.kind != "node":
            continue
        parent = section.attributes.get("parent")
        name = section.attributes["name"]
        key = "." if parent is None else (name if parent == "." else f"{parent}/{name}")
        nodes[key] = section
    return Scene(path, ext, sub, nodes)


# --- territories ----------------------------------------------------------------------------------------------------

@dataclass
class Territory:
    id: str
    label: str
    translation: np.ndarray
    polygon: list
    manifest: dict
    spec: dict
    scene: Scene
    first_vertex: np.ndarray  # continent x, z of vertex (0, 0)
    width: int
    height: int
    heights: np.ndarray  # (height, width) float32
    colors_path: Path
    provenance: dict
    polygons: list | None = None  # appended to preserve the frozen-source positional API

    def vertex_xz(self) -> tuple[np.ndarray, np.ndarray]:
        return (self.first_vertex[0] + CELL * np.arange(self.width),
                self.first_vertex[1] + CELL * np.arange(self.height))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _vector(text: str, kind: str) -> list[float]:
    return _numbers(text, kind)


def load_territories(catalog: Path = CATALOG) -> list[Territory]:
    result = []
    for entry in _json(catalog)["entries"]:
        manifest = _json(res_to_path(entry["manifestPath"]))
        spec = _json(res_to_path(entry["authoringSpecPath"]))
        scene = load_scene(res_to_path(entry["scenePath"]))
        geography = manifest["continentGeography"]
        translation = np.asarray(geography["translation"], np.float64)
        terrain = scene.node("Terrain")
        origin = _vector(terrain.properties["origin"], "Vector2")
        width, height = (int(v) for v in _vector(terrain.properties["grid_size"], "Vector2i"))
        heights_path = res_to_path(json.loads(terrain.properties["base_heights_path"]))
        colors_path = res_to_path(json.loads(terrain.properties["base_colors_path"]))
        heights = np.fromfile(heights_path, "<f4")
        if heights.size != width * height:
            raise ValueError(f"{entry['id']}: base heights hold {heights.size} values, the grid {width}x{height}")
        provenance_path = heights_path.parent / "terrain-provenance.json"
        result.append(Territory(
            id=entry["id"], label=entry["label"], translation=translation,
            polygon=[[float(x), float(z)] for x, z in geography["ownershipPolygon"]],
            manifest=manifest, spec=spec, scene=scene,
            first_vertex=np.array([origin[0] + translation[0], origin[1] + translation[2]]),
            width=width, height=height, heights=heights.reshape(height, width), colors_path=colors_path,
            provenance=_json(provenance_path) if provenance_path.exists() else {},
            polygons=geography.get("ownershipPolygons")))
    return result


@dataclass
class Lattice:
    """The union of the territories' grids, on the shared 2 m vertex lattice."""
    first: np.ndarray
    width: int
    height: int

    @staticmethod
    def of(territories: list[Territory]) -> "Lattice":
        lo = np.min([t.first_vertex for t in territories], axis=0)
        hi = np.max([t.first_vertex + CELL * np.array([t.width - 1, t.height - 1]) for t in territories], axis=0)
        for t in territories:
            if np.any((t.first_vertex - lo) % CELL):
                raise ValueError(f"{t.id}: terrain vertices are off the shared 2 m lattice")
        size = ((hi - lo) / CELL).astype(int) + 1
        return Lattice(lo, int(size[0]), int(size[1]))

    def window(self, t: Territory) -> tuple[slice, slice]:
        c0, r0 = ((t.first_vertex - self.first) / CELL).astype(int)
        return slice(r0, r0 + t.height), slice(c0, c0 + t.width)

    def xz(self) -> tuple[np.ndarray, np.ndarray]:
        return self.first[0] + CELL * np.arange(self.width), self.first[1] + CELL * np.arange(self.height)


def authority(t: Territory, lattice: Lattice) -> np.ndarray:
    """Owned cells' vertices plus one 3x3 ring, on the lattice (authoring.required_terrain_vertices). Cells are owned
    when their centre is inside the polygon or on its edge."""
    from scipy.ndimage import binary_dilation

    x, z = lattice.xz()
    owned_cells = territory_classify((x[:-1] + CELL / 2)[None, :], (z[:-1] + CELL / 2)[:, None], t) > 0
    vertices = np.zeros((lattice.height, lattice.width), bool)
    vertices[:-1, :-1] |= owned_cells
    vertices[1:, :-1] |= owned_cells
    vertices[:-1, 1:] |= owned_cells
    vertices[1:, 1:] |= owned_cells
    return binary_dilation(vertices, structure=np.ones((3, 3), bool))


def _on_lattice(t: Territory, lattice: Lattice, values: np.ndarray, fill) -> np.ndarray:
    out = np.full((lattice.height, lattice.width) + values.shape[2:], fill, values.dtype)
    out[lattice.window(t)] = values
    return out


def _covered(t: Territory, lattice: Lattice) -> np.ndarray:
    mask = np.zeros((lattice.height, lattice.width), bool)
    mask[lattice.window(t)] = True
    return mask


# --- the editor's additions ----------------------------------------------------------------------------------------

def patches(t: Territory) -> list[dict]:
    """Terrain patches in continent metres, in the order terrain_control applies them (by patch id)."""
    scene = t.scene
    result = []
    for path, section in scene.nodes.items():
        if section.attributes.get("parent") != "Terrain/Patches" or scene.script_of(section) != PATCH_SCRIPT:
            continue
        props = section.properties
        matrix = scene.world(path)
        matrix[:3, 3] += t.translation
        size = _vector(props["size"], "Vector2") if "size" in props else [24.0, 24.0]
        result.append({
            "id": json.loads(props.get("patch_id", '""')),
            "shape": int(props.get("shape", "0")),
            "operation": int(props.get("operation", "0")),
            "size": [max(size[0], 0.1), max(size[1], 0.1)],
            "feather": float(props.get("feather", "6.0")),
            "enabled": props.get("enabled", "true") == "true",
            "basis": [round(float(v), 9) for v in matrix[:3, :3].ravel()],
            "continentOrigin": [round(float(v), 9) for v in matrix[:3, 3]],
        })
    result.sort(key=lambda record: record["id"])
    return result


def patch_weight(record: dict, x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """terrain_patch.gd weight_at_transform, in continent metres."""
    if not record["enabled"]:
        return np.zeros(np.broadcast(x, z).shape)
    basis = np.asarray(record["basis"]).reshape(3, 3)
    projected = np.array([[basis[0, 0], basis[0, 2]], [basis[2, 0], basis[2, 2]]])
    if abs(np.linalg.det(projected)) <= 1e-6:
        return np.zeros(np.broadcast(x, z).shape)
    inverse = np.linalg.inv(projected)
    dx = np.asarray(x, np.float64) - record["continentOrigin"][0]
    dz = np.asarray(z, np.float64) - record["continentOrigin"][2]
    ox = inverse[0, 0] * dx + inverse[0, 1] * dz
    oz = inverse[1, 0] * dx + inverse[1, 1] * dz
    half = np.asarray(record["size"]) / 2.0
    if record["shape"] == 1:
        distance = np.minimum(half[0] - np.abs(ox), half[1] - np.abs(oz))
    else:
        distance = (1.0 - np.hypot(ox / half[0], oz / half[1])) * min(half)
    if record["feather"] <= 1e-6:
        return (distance > 0).astype(np.float64)
    amount = np.clip(distance / record["feather"], 0.0, 1.0)
    return np.where(distance > 0, amount * amount * (3.0 - 2.0 * amount), 0.0)


def sculpt_deltas(t: Territory) -> tuple[np.ndarray, list[str]]:
    """The sculpt layer's deltas on the territory's grid (zeros without a layer), and binding problems."""
    deltas = np.zeros(t.width * t.height, np.float32)
    problems = []
    terrain = t.scene.node("Terrain")
    reference = terrain.properties.get("sculpt_layer")
    if reference is None:
        return deltas.reshape(t.height, t.width), problems
    match = re.fullmatch(r'SubResource\("([^"]+)"\)', reference.strip())
    layer = t.scene.sub[match.group(1)].properties
    origin = _vector(layer["origin"], "Vector2")
    grid = [int(v) for v in _vector(layer["grid_size"], "Vector2i")]
    if origin != _vector(terrain.properties["origin"], "Vector2") or grid != [t.width, t.height]:
        problems.append(f"{t.id}: the sculpt layer is bound to another grid")
    indices = np.asarray(_numbers(layer.get("indices", "PackedInt32Array()"), "PackedInt32Array"), np.int64)
    values = np.asarray(_numbers(layer.get("deltas", "PackedFloat32Array()"), "PackedFloat32Array"), np.float32)
    if indices.size != values.size:
        problems.append(f"{t.id}: sculpt indices and deltas differ in length")
        return deltas.reshape(t.height, t.width), problems
    if np.any(indices < 0) or np.any(indices >= deltas.size) or not np.isfinite(values).all():
        problems.append(f"{t.id}: invalid sculpt index or nonfinite delta")
        return deltas.reshape(t.height, t.width), problems
    deltas[indices] = values
    return deltas.reshape(t.height, t.width), problems


def shaping_paths(t: Territory) -> list[str]:
    """Paths whose terrainConform is not false (they would reshape the terrain under them)."""
    found = []
    for path, section in t.scene.nodes.items():
        if t.scene.script_of(section) != PATH_SCRIPT:
            continue
        if not re.search(r'"terrainConform":\s*false', section.properties.get("properties", "")):
            found.append(path)
    return found


def water_features(t: Territory) -> list[dict]:
    """River centre lines and the actual transformed elliptical water footprints."""
    scene = t.scene
    found = []
    for path, section in scene.nodes.items():
        script = scene.script_of(section)
        props = section.properties
        matrix = scene.world(path)
        matrix[:3, 3] += t.translation
        if script == PATH_SCRIPT and json.loads(props.get("kind", '"road"')) == "river":
            match = re.fullmatch(r'SubResource\("([^"]+)"\)', props.get("curve", "").strip())
            if match is None:
                continue
            curve = scene.sub[match.group(1)].properties.get("_data", "")
            listed = re.search(r'"points":\s*PackedVector3Array\(([^)]*)\)', curve)
            values = [float(v) for v in listed.group(1).split(",")] if listed and listed.group(1).strip() else []
            local = np.asarray([values[i + 6:i + 9] for i in range(0, len(values), 9)], np.float64).reshape(-1, 3)
            points = (matrix[:3, :3] @ local.T).T + matrix[:3, 3]
            widths = _numbers(props.get("point_widths", "PackedFloat32Array()"), "PackedFloat32Array")
            width = max([float(props.get("default_width", "4.0"))] + [float(w) for w in widths if w > 0])
            found.append({"kind": "river", "path": path, "xz": points[:, [0, 2]], "reach": width / 2.0})
        elif script == WATER_SCRIPT:
            radii = _vector(props["radii"], "Vector2") if "radii" in props else [1.0, 1.0]
            found.append({"kind": "water region", "path": path, "xz": matrix[[0, 2], 3].reshape(1, 2),
                          "ellipse": matrix[np.ix_([0, 2], [0, 2])] @ np.diag(radii)})
    return found


def _distance_to_water(feature: dict, x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Exact plan distance to an ellipse, including rotation and unequal scale; rivers retain their ribbon width."""
    if "ellipse" not in feature:
        return _distance_to_polyline(feature["xz"], x, z) - feature["reach"]
    axes, radii, _ = np.linalg.svd(feature["ellipse"])
    if np.any(radii <= 0):
        raise ValueError(f"{feature['path']}: water footprint has a degenerate transform")
    x, z = np.broadcast_arrays(x, z)
    points = np.stack([x-feature["xz"][0, 0], z-feature["xz"][0, 1]], axis=-1) @ axes
    squared = radii*radii
    inside = np.sum(points*points/squared, axis=-1) <= 1
    # The closest outside point is a^2*p/(lambda+a^2), with lambda >= 0.
    lower = np.zeros(x.shape)
    upper = np.linalg.norm(points*radii, axis=-1)
    for _ in range(56):
        middle = (lower+upper)/2
        outside = np.sum(squared*points*points/(middle[..., None]+squared)**2, axis=-1) > 1
        lower = np.where(outside, middle, lower)
        upper = np.where(outside, upper, middle)
    nearest = squared*points/(upper[..., None]+squared)
    return np.where(inside, 0, np.linalg.norm(points-nearest, axis=-1))


def _distance_to_polyline(points: np.ndarray, x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Plan distance from each (x, z) to a polyline (a single point is a point)."""
    if len(points) == 0:
        return np.full(np.broadcast(x, z).shape, np.inf)
    if len(points) == 1:
        return np.hypot(x - points[0, 0], z - points[0, 1])
    best = np.full(np.broadcast(x, z).shape, np.inf)
    for (x1, z1), (x2, z2) in zip(points[:-1], points[1:]):
        sx, sz = x2 - x1, z2 - z1
        length = max(sx * sx + sz * sz, 1e-12)
        u = np.clip(((x - x1) * sx + (z - z1) * sz) / length, 0.0, 1.0)
        best = np.minimum(best, np.hypot(x - (x1 + u * sx), z - (z1 + u * sz)))
    return best


# --- the checks -----------------------------------------------------------------------------------------------------

def check_frames(territories: list[Territory]) -> tuple[list[str], dict]:
    problems, report = [], {}
    for t in territories:
        root = t.scene.node(".").properties
        spec = t.spec
        sha = polygons_sha(t.polygons if t.polygons is not None else [t.polygon])
        terrain_origin = _vector(t.scene.node("Terrain").properties["origin"], "Vector2")
        values = {
            "ownership sha": (json.loads(root["ownership_polygon_sha256"]), sha),
            "region id": (json.loads(root["region_id"]), t.id),
            "spec region id": (spec["regionId"], t.id),
            "translation": (_vector(root["continent_translation"], "Vector3"), [float(v) for v in t.translation]),
            "spec translation": (spec["continentTranslation"], [float(v) for v in t.translation]),
            "server origin": ([int(v) for v in _vector(root["server_origin"], "Vector2i")], spec["server"]["origin"]),
            "server cells": ([int(v) for v in _vector(root["server_cells"], "Vector2i")], spec["server"]["cells"]),
            "collision origin": (_vector(root["collision_origin_metres"], "Vector2"),
                                 spec["server"]["collisionOriginMetres"]),
            "manifest server": (t.manifest["server"], spec["server"]),
            "terrain origin": (terrain_origin, spec["terrain"]["origin"]),
            "terrain vertices": ([t.width, t.height], spec["terrain"]["vertices"]),
        }
        for name, (have, want) in values.items():
            if have != want:
                problems.append(f"{t.id}: {name} {have} differs from {want}")
        if any(type(v) is not int or v <= 0 or v % 6 for v in spec["server"]["cells"]):
            problems.append(f"{t.id}: server cells must be positive integer multiples of six")
        if any(not float(v).is_integer() for v in t.translation):
            problems.append(f"{t.id}: translation must fall on whole continent metres")
        if max(spec["server"]["cells"]) > 2048:
            problems.append(f"{t.id}: the server map exceeds 2,048 tiles")
        report[t.id] = {"ownershipSha256": sha, "server": spec["server"], "terrainVertices": [t.width, t.height]}
    return problems, report


def check_ownership(territories: list[Territory], lattice: Lattice) -> tuple[list[str], dict]:
    from scipy import ndimage

    problems = []
    x, z = lattice.xz()
    cx, cz = (x[:-1] + CELL / 2)[None, :], (z[:-1] + CELL / 2)[:, None]
    strictly = {t.id: territory_classify(cx, cz, t) == 1 for t in territories}
    count = sum(mask.astype(np.int32) for mask in strictly.values())
    overlaps = {}
    for i, a in enumerate(territories):
        for b in territories[i + 1:]:
            both = int((strictly[a.id] & strictly[b.id]).sum())
            overlaps[f"{a.id}|{b.id}"] = both
            if both:
                problems.append(f"{a.id} and {b.id} overlap on {both} cells")
    # island land: the group's base heights (every territory's values agree where they overlap; checked below)
    heights = np.full((lattice.height, lattice.width), np.nan, np.float32)
    for t in territories:
        window = lattice.window(t)
        heights[window] = np.where(np.isnan(heights[window]), t.heights, heights[window])
    land = np.nan_to_num(heights, nan=-1.0) > 0.0
    labels, components = ndimage.label(land, structure=np.ones((3, 3), bool))
    edge_labels = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))) - {0}
    owned = np.zeros_like(land)
    for t in territories:
        owned |= territory_classify(x[None, :], z[:, None], t) > 0
    island = land & ~np.isin(labels, list(edge_labels))
    unowned = island & ~owned
    if unowned.any():
        rows, cols = np.nonzero(unowned)
        problems.append(f"{int(unowned.sum())} island land vertices are unowned, e.g. continent "
                        f"({x[cols[0]]:.0f}, {z[rows[0]]:.0f})")
    mainland = land & np.isin(labels, list(edge_labels))
    report = {
        "overlappingCells": overlaps,
        "cellsInNoPolygonShare": round(float((count == 0).mean()), 4),
        "landComponents": int(components),
        "islandLandM2": int(island.sum() * CELL * CELL),
        "unownedIslandLandM2": int(unowned.sum() * CELL * CELL),
        "mainlandComponents": len(edge_labels),
        "mainlandM2": {"inGrid": int(mainland.sum() * CELL * CELL),
                       "owned": int((mainland & owned).sum() * CELL * CELL)},
    }
    return problems, report


def check_seams(territories: list[Territory], lattice: Lattice) -> tuple[list[str], dict]:
    problems, report = [], {}
    x, z = lattice.xz()
    authorities = {t.id: authority(t, lattice) for t in territories}
    for t in territories:
        missing = authorities[t.id] & ~_covered(t, lattice)
        if missing.any():
            problems.append(f"{t.id}: its terrain grid omits {int(missing.sum())} owned or ring vertices")
    bits = {t.id: _on_lattice(t, lattice, t.heights.view(np.uint32), np.uint32(0)) for t in territories}
    sculpt = {}
    for t in territories:
        deltas, binding = sculpt_deltas(t)
        problems += binding
        sculpt[t.id] = _on_lattice(t, lattice, deltas, np.float32(0))
    patch_records = {t.id: patches(t) for t in territories}
    for t in territories:
        for path in shaping_paths(t):
            problems.append(f"{t.id}: {path} shapes the terrain (terrainConform is not false)")
    for i, a in enumerate(territories):
        for b in territories[i + 1:]:
            pair = f"{a.id}|{b.id}"
            shared = authorities[a.id] & authorities[b.id] & _covered(a, lattice) & _covered(b, lattice)
            entry = {"sharedVertices": int(shared.sum())}
            if not shared.any():
                report[pair] = entry
                continue
            rows, cols = np.nonzero(shared)
            entry["sharedLandVertices"] = int((_on_lattice(a, lattice, a.heights, np.float32(np.nan))[shared]
                                               > 0).sum())
            entry["x"] = [float(x[cols].min()), float(x[cols].max())]
            entry["z"] = [float(z[rows].min()), float(z[rows].max())]
            differing = shared & (bits[a.id] != bits[b.id])
            entry["baseDifferences"] = int(differing.sum())
            if differing.any():
                r, c = np.argwhere(differing)[0]
                problems.append(f"{pair}: {int(differing.sum())} shared vertices differ in the base, e.g. "
                                f"({x[c]:.0f}, {z[r]:.0f})")
            for t in (a, b):
                touched = shared & (sculpt[t.id] != 0)
                entry[f"sculptedShared_{t.id}"] = int(touched.sum())
                if touched.any():
                    r, c = np.argwhere(touched)[0]
                    problems.append(f"{pair}: {t.id} sculpts {int(touched.sum())} shared vertices, e.g. "
                                    f"({x[c]:.0f}, {z[r]:.0f})")
            sx, sz = x[cols], z[rows]
            touching = {}
            for t in (a, b):
                touching[t.id] = {record["id"]: record for record in patch_records[t.id]
                                  if patch_weight(record, sx, sz).max() > 0.0}
            mirrored = []
            for patch_id in sorted(set(touching[a.id]) | set(touching[b.id])):
                first, second = touching[a.id].get(patch_id), touching[b.id].get(patch_id)
                if first is None or second is None:
                    holder = a.id if first is not None else b.id
                    problems.append(f"{pair}: patch {patch_id} touches shared vertices but only {holder} declares it")
                elif first != second:
                    problems.append(f"{pair}: patch {patch_id} is declared differently ({first} vs {second})")
                else:
                    mirrored.append(patch_id)
            entry["mirroredPatches"] = mirrored
            for t in (a, b):
                entry[f"sculptUnderMoles_{t.id}"] = 0
                for patch_id in mirrored:
                    under = (patch_weight(touching[t.id][patch_id], x[None, :], z[:, None]) > 0.0) & \
                        (sculpt[t.id] != 0)
                    entry[f"sculptUnderMoles_{t.id}"] += int(under.sum())
                    if under.any():
                        r, c = np.argwhere(under)[0]
                        problems.append(f"{pair}: {t.id} sculpts {int(under.sum())} vertices under seam patch "
                                        f"{patch_id}, e.g. ({x[c]:.0f}, {z[r]:.0f})")
            near_water = []
            for t in (a, b):
                for feature in water_features(t):
                    distance = _distance_to_water(feature, sx, sz)
                    if distance.min() < SEAM_WATER_CLEARANCE:
                        near_water.append(feature["path"])
                        problems.append(f"{pair}: {t.id}'s {feature['kind']} {feature['path']} comes within "
                                        f"{max(float(distance.min()), 0.0):.1f} m of a shared vertex")
            entry["waterNearShared"] = near_water
            report[pair] = entry
    return problems, report


def check_crops(territories: list[Territory]) -> tuple[list[str], dict]:
    """Validate exact crops, including an external frozen parent with hash-pinned files and grid."""
    problems, report = [], {}
    by_id = {t.id: t for t in territories}
    parents = {}
    for t in territories:
        crop = t.provenance.get("crop")
        if not crop:
            continue
        try:
            if "parentFiles" in crop:
                key = json.dumps(crop["parentFiles"], sort_keys=True)
                if key not in parents:
                    files = {}
                    for kind, record in crop["parentFiles"].items():
                        path = (CHECKOUT / record["path"]).resolve()
                        if not path.is_relative_to(CHECKOUT.resolve()):
                            raise ValueError("parent file escapes checkout")
                        raw = path.read_bytes()
                        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
                            raise ValueError(f"{kind} parent hash differs")
                        files[kind] = raw
                    meta = json.loads(files["provenance"])
                    grid = crop["parentGrid"]
                    if meta["schema"] != "eloria-continent-v2-frozen-group-terrain-v1" or meta["grid"] != grid or meta["sourceCommit"] != crop["sourceCommit"]:
                        raise ValueError("parent provenance/grid/source differs")
                    w, h = grid["gridSize"]
                    if grid["cellMetres"] != CELL or len(files["heights"]) != w*h*4 or len(files["colors"]) != w*h*4:
                        raise ValueError("parent dimensions/cell size differ")
                    for kind, output in (("heights", "base-heights.f32le"), ("colors", "base-colors.rgba8")):
                        if meta["outputs"][output]["sha256"] != crop["parentFiles"][kind]["sha256"]:
                            raise ValueError("parent output binding differs")
                    heights = np.frombuffer(files["heights"], "<f4").reshape(h,w)
                    if not np.isfinite(heights).all():
                        raise ValueError("nonfinite parent heights")
                    parents[key] = (heights, np.frombuffer(files["colors"],np.uint8).reshape(h,w,4), np.asarray(grid["continentFirstVertex"]))
                heights, colors, first = parents[key]
            else:
                parent = by_id.get(crop["parent"])
                if parent is None:
                    raise ValueError(f"crop parent {crop['parent']} is not catalogued")
                heights, first = parent.heights, parent.first_vertex
                colors = np.fromfile(parent.colors_path,np.uint8).reshape(parent.height,parent.width,4)
            r,c,h,w = (crop[k] for k in ("row0","col0","rows","cols"))
            if any(type(v) is not int for v in (r,c,h,w)) or r<0 or c<0 or (h,w)!=(t.height,t.width) or r+h>heights.shape[0] or c+w>heights.shape[1]:
                raise ValueError("crop bounds/size differ")
            same_heights = heights[r:r+h,c:c+w].tobytes() == t.heights.tobytes()
            same_colors = colors[r:r+h,c:c+w].tobytes() == t.colors_path.read_bytes()
            same_frame = bool(np.all(first + CELL*np.array([c,r]) == t.first_vertex))
            if not (same_heights and same_colors and same_frame):
                raise ValueError(f"not a byte crop (heights {same_heights}, colours {same_colors}, frame {same_frame})")
            report[t.id] = {"parent":crop["parent"],"heights":same_heights,"colors":same_colors,"frame":same_frame}
        except (KeyError, ValueError, OSError, TypeError) as error:
            problems.append(f"{t.id}: invalid crop: {error}")
    return problems, report


# --- the published packages and the served frames (serve plan CV9) -------------------------------------------------

# The registry status of a continent-v2 map the server serves (serve plan CV11 sets it).
SERVED_STATUS = "continent-v2-served"


def _catalog_checkout(catalog: Path) -> Path:
    """The checkout a catalog at <checkout>/godot-client/world_authoring/continent-v2/territories.json belongs to."""
    return Path(catalog).resolve().parents[3]


def served_frames(catalog: Path = CATALOG, entries: list | None = None) -> dict[str, dict]:
    """The catalog's territories that the server serves, or that are published to be, with the frame saved positions
    are kept in: {region: {"origin": [x, y], "cells": [w, h], "translation": [x, y, z], "why": str}}.

    A territory counts as served once its client package ships a served grid (collision.servedGrid in the package's
    world.json, which _continent_v2/export_collision.py exports for the server's sync to vendor), or once its registry
    row has the status continent-v2-served. Its frame is the one its package states (coordinateTransform serverOrigin
    and serverCells, continentGeography translation), else its registry row's. The package is the catalog entry's
    publishedManifestPath, else the registry row's manifest."""
    checkout = _catalog_checkout(catalog)
    rows = _json(checkout / "godot-client" / "data" / "maps" / "registry.json").get("maps", {})
    result = {}
    for entry in (_json(catalog)["entries"] if entries is None else entries):
        region = entry["id"]
        row = rows.get(region, {})
        resource = entry.get("publishedManifestPath") or row.get("manifest", "")
        package = res_to_path(resource, checkout) if resource else None
        manifest = _json(package) if package is not None and package.is_file() else {}
        why = []
        if (manifest.get("collision") or {}).get("servedGrid"):
            why.append(f"its package {resource} ships a served grid")
        if row.get("status") == SERVED_STATUS:
            why.append(f"its registry row is {SERVED_STATUS}")
        if not why:
            continue
        source = manifest if "coordinateTransform" in manifest else row
        transform = source.get("coordinateTransform") or {}
        result[region] = {"origin": list(transform.get("serverOrigin") or []),
                          "cells": list(transform.get("serverCells") or []),
                          "translation": list((source.get("continentGeography") or {}).get("translation") or []),
                          "why": " and ".join(why)}
    return result


def served_frame_problems(frames: dict[str, dict], catalog: Path = CATALOG, entries: list | None = None) -> list[str]:
    """Why `frames` ({region: {"origin", "cells", "translation"}}: what a bootstrap would write, or what the stubs say)
    would move a served territory, or []. Saved characters stand on a served map's tiles and the server's lanes,
    landings and home points are written in its frame, so its origin, its size and its continent translation stay as
    the package states them until a position migration on the server moves them; no client tool does that."""
    problems = []
    for region, served in served_frames(catalog, entries).items():
        frame = frames.get(region)
        if frame is None:
            problems.append(f"{region} is served ({served['why']}) but has no frame here")
            continue
        for key, name in (("origin", "server origin"), ("cells", "server cells"),
                          ("translation", "continent translation")):
            have = [float(value) for value in frame.get(key) or []]
            want = [float(value) for value in served[key]]
            if not want or have != want:
                problems.append(f"{region}: its {name} would move from {served[key]} to {frame.get(key)}, but it is "
                                f"served ({served['why']}); a served frame moves only with a server position "
                                f"migration")
    return problems


def served_group_problems(catalog: Path = CATALOG) -> list[str]:
    """Why the packages that ship a served grid do not come from one _continent_v2/export_collision.py run, or []. A
    map's one-tile seam collar is its neighbour's export, so each such package's collision.groupExport must name
    every served package with the snapshot and served grid that package carries; a package republished from another
    run would keep its neighbour's old ground along the border."""
    checkout = _catalog_checkout(catalog)
    rows = _json(checkout / "godot-client" / "data" / "maps" / "registry.json").get("maps", {})
    blocks = {}
    for entry in _json(catalog)["entries"]:
        region = entry["id"]
        resource = entry.get("publishedManifestPath") or (rows.get(region) or {}).get("manifest", "")
        package = res_to_path(resource, checkout) if resource else None
        collision = (_json(package).get("collision") or {}) if package is not None and package.is_file() else {}
        if collision.get("servedGrid"):
            blocks[region] = collision
    expected = {region: {"snapshotSha256": block.get("sourceSnapshotSha256"),
                         "servedGridSha256": (block.get("servedGrid") or {}).get("sha256")}
                for region, block in blocks.items()}
    return [f"{region}: its served grid comes from another export run than the other served packages' (collision."
            f"groupExport); re-run export_collision.py over the whole group and republish every map"
            for region, block in blocks.items() if (block.get("groupExport") or {}).get("maps") != expected]


def served_row_problems(catalog: Path = CATALOG) -> list[str]:
    """Why a served registry row (status continent-v2-served, serve plan CV11) is not one the client can travel to as
    a served map, or []: its label must be the catalog's label (the name publish_server.py gives the server's map row,
    so the client and the server name the map alike), it crosses its land seams as landscape (landscapeTransitions
    true), and it no longer says it waits for a server map (requiresServerMap)."""
    checkout = _catalog_checkout(catalog)
    rows = _json(checkout / "godot-client" / "data" / "maps" / "registry.json").get("maps", {})
    problems = []
    for entry in _json(catalog)["entries"]:
        region, row = entry["id"], rows.get(entry["id"]) or {}
        if row.get("status") != SERVED_STATUS:
            continue
        if row.get("label") != entry.get("label"):
            problems.append(f"{region}: the served registry row's label {row.get('label')!r} is not the catalog's "
                            f"{entry.get('label')!r}")
        if row.get("landscapeTransitions") is not True:
            problems.append(f"{region}: the served registry row does not cross its seams as landscape "
                            f"(landscapeTransitions is {row.get('landscapeTransitions')!r})")
        if "requiresServerMap" in row:
            problems.append(f"{region}: the served registry row still says it requires a server map")
    return problems


def check_published(territories: list[Territory], catalog: Path = CATALOG) -> tuple[list[str], dict]:
    """Each catalog entry names its published package, the one its registry row names; a served row names the map as
    the catalog does; no served territory's stub has moved off the frame its package was served in; and the served
    packages come from one collision export run."""
    checkout = _catalog_checkout(catalog)
    rows = _json(checkout / "godot-client" / "data" / "maps" / "registry.json").get("maps", {})
    problems, report = [], {}
    for entry in _json(catalog)["entries"]:
        region, published = entry["id"], entry.get("publishedManifestPath")
        row = rows.get(region)
        if not published:
            problems.append(f"{region}: the catalog entry names no publishedManifestPath")
        elif row is not None and row.get("manifest") != published:
            problems.append(f"{region}: the catalog's publishedManifestPath {published} is not the registry row's "
                            f"manifest {row.get('manifest')}")
        report[region] = {"publishedManifestPath": published,
                          "published": bool(published) and res_to_path(published, checkout).is_file()}
    stubs = {t.id: {"origin": t.manifest["server"]["origin"], "cells": t.manifest["server"]["cells"],
                    "translation": [float(v) for v in t.translation]} for t in territories}
    problems += served_row_problems(catalog)
    problems += served_frame_problems(stubs, catalog)
    problems += served_group_problems(catalog)
    report["served"] = sorted(served_frames(catalog))
    return problems, report


def check_all(catalog: Path = CATALOG) -> tuple[list[str], dict]:
    territories = load_territories(catalog)
    lattice = Lattice.of(territories)
    problems, report = [], {"territories": [t.id for t in territories]}
    for name, check in (("frames", lambda: check_frames(territories)),
                        ("published", lambda: check_published(territories, catalog)),
                        ("crops", lambda: check_crops(territories)),
                        ("ownership", lambda: check_ownership(territories, lattice)),
                        ("seams", lambda: check_seams(territories, lattice))):
        found, report[name] = check()
        problems += found
    return problems, report


def main() -> int:
    problems, report = check_all()
    print(json.dumps({"problems": problems, "report": report}, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
