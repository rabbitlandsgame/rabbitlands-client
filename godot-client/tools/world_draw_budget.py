"""World draw budget: an offline frustum estimate of world draws and primitives (wave 2 WD-C0).

Reads a continent-v2 territory's resident chunk GLBs (JSON chunk only: node transforms,
mesh bounds, triangle counts, materials) and the shared prototype GLBs they place,
reproduces WorldLoader._batch_static_instances (per chunk package, key = prototype x 3D
cell, >= 4 members, opaque materials only) and counts what a Godot camera frustum would
submit at the camera rig's poses (focus + offset(yaw, pitch, distance), look-at focus +
1.2 m, vertical FOV 50, near = clamp(0.25 x distance, 0.2, 1.0)), averaged over four yaws.
Visibility ranges are measured to the unit's AABB centre, as Godot does.

Variants (the world-distance plan's section 2.2):
- today: one batch per prototype per 180 m cell (WorldLoader.BATCH_CELL_METRES);
- cells: size-class cells (C2);
- ranges_keep_terrain: cells + per-class reach from the focus (C3), the LOW far plane (C4
  estimate) and no shadow on ground/flat decks and small props - the C2+C3(+C4) yardstick;
- ranges: the same with every Terrain_ hidden, as section 2.2's "+ranges" columns assume.
  That is the C1 upper bound: the real C1 hides only proven chunks (81 % of them);
- far_proxies: ranges + trees (r >= 1.5 m) drawn as 4-triangle proxies beyond 100 m from
  the camera (an upper bound for C5/C8).
`--shadows` adds the rough per-cascade caster estimate (section 2.3; Wave 1's ground-sampled
fit is approximated as 1.4 x distance + 12 m). These are estimates for ordering and budgets;
the rendered `camera_rotation_probe.gd` measures the real visible and shadow passes.

The class table (radius limits, batch cells, reach, tier scale, far-proxy distance) comes
from the plan unless the client defines it. When src/world/world_distance_classes.gd or
src/world/world_distance.gd exists, these constants are read from it (string keys):
CLASS_RADIUS_LIMITS [1.5, 4.0, 10.0]; CELL_METRES / REACH_METRES {"S","M","L","XL"};
TIER_REACH_SCALE {"HIGH","MEDIUM","LOW"}; FAR_PROXY_METRES; LOW_FAR_METRES. The report's
`table.source` says which file each value came from.

Usage:
    python -I tools/world_draw_budget.py landfall [--json out.json] [--shadows]
    python -I tools/world_draw_budget.py --check-reference   # section 2.2/2.3 within 1 %
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import struct
import sys

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_MAPS = PROJECT.parent / "eloria-assets" / "maps"
TABLE_FILES = ("src/world/world_distance_classes.gd", "src/world/world_distance.gd")
SCHEMA = 1
FIELD_OF_VIEW = 50.0
PRELOAD_METRES = 240.0
RESIDENT_LIMIT = 64
YAWS = (0, 90, 180, 270)
CLASSES = ("S", "M", "L", "XL")
PLAN_TABLE = {
    "CLASS_RADIUS_LIMITS": [1.5, 4.0, 10.0],
    "CELL_METRES": {"S": 32.0, "M": 48.0, "L": 64.0, "XL": 96.0},
    "REACH_METRES": {"S": 30.0, "M": 70.0, "L": 160.0, "XL": 0.0},
    "TIER_REACH_SCALE": {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.6},
    "FAR_PROXY_METRES": 100.0,
    "LOW_FAR_METRES": 260.0,
    "TODAY_CELL_METRES": 180.0,
}
POSES = (("default 26m -60", 26.0, -60.0), ("max zoom 90m -60", 90.0, -60.0),
         ("26m -15", 26.0, -15.0), ("max zoom 90m -15", 90.0, -15.0), ("90m -35", 90.0, -35.0))
ASPECTS = {"16:9": 16 / 9, "k620": 941 / 1030}
VARIANTS = ("today", "cells", "ranges_keep_terrain", "ranges", "far_proxies")
SHADOW_TIERS = {"HIGH": (0.1, 0.2, 0.5), "LOW": (0.1,)}
SUN_DEGREES = (-55.0, -30.0)
CATEGORIES = (
    ("tree", r"tree|palm|pine|fir|larch|beech|oak|maple|chestnut|birch|willow|cypress|banyan|broadleaf|mangrove"
             r"|conifer|spruce|cedar|ash|elm|yew|alder|aspen"),
    ("undergrowth", r"undergrowth|fern|shrub|bush|grass|reed|flower|tussock|bracken|gorse|heather|meadow|weed|plant"
                    r"|hedge|topiary|vine|bougainvillea|lily|moss|mushroom|planter|crop|cattail"),
    ("rock", r"rock|boulder|stone(?!-bench)|cliff|crag|pebble|scree"),
    ("building", r"house|wall|tower|keep|gate|temple|hall|arcade|revetment|ruin|bridge|dock|pier|stair|terrace"
                 r"|column|arch|roof|shrine|mill|barn|cottage|inn|church|chapel|castle|fort|tent|hut|shed|balustrade"),
)
# Section 2.2 (16:9, own territory, spawn focus): pose -> variant/tier -> (draws, thousand primitives).
REFERENCE = {
    "landfall": {
        "default 26m -60": [(62, 245), (62, 181), (60, 168), (60, 168), (60, 168), (60, 168)],
        "max zoom 90m -60": [(201, 1023), (250, 853), (236, 816), (222, 758), (203, 624), (177, 525)],
        "26m -15": [(347, 1506), (446, 1383), (231, 813), (178, 584), (189, 582), (154, 420)],
        "max zoom 90m -15": [(486, 2085), (648, 1976), (377, 1315), (284, 964), (284, 842), (223, 641)],
        "90m -35": [(440, 1928), (584, 1803), (367, 1286), (292, 970), (273, 806), (224, 621)]},
    "suncoil": {
        "default 26m -60": [(44, 424), (38, 110), (33, 88), (32, 81), (33, 88), (32, 80)],
        "max zoom 90m -60": [(180, 992), (260, 635), (230, 535), (204, 467), (192, 367), (152, 238)],
        "26m -15": [(440, 1751), (627, 1437), (322, 578), (243, 380), (274, 292), (210, 166)],
        "max zoom 90m -15": [(611, 2284), (888, 1955), (516, 917), (340, 614), (430, 455), (282, 291)]},
    "coilmere": {
        "default 26m -60": [(95, 471), (105, 275), (70, 166), (60, 141), (68, 154), (59, 127)],
        "max zoom 90m -60": [(262, 1089), (365, 855), (254, 583), (204, 460), (235, 464), (177, 303)],
        "26m -15": [(473, 1729), (662, 1456), (263, 552), (186, 348), (228, 315), (172, 207)],
        "max zoom 90m -15": [(660, 2340), (947, 2099), (429, 941), (278, 600), (368, 562), (244, 366)]},
}
REFERENCE_COLUMNS = (("today", "HIGH"), ("cells", "HIGH"), ("ranges", "HIGH"), ("ranges", "LOW"),
                     ("far_proxies", "HIGH"), ("far_proxies", "LOW"))
# Section 2.3, Landfall: pose -> tier -> label -> (draws, million caster primitives).
SHADOW_REFERENCE = {
    "default 26m -60": {"HIGH": {"today_100m": (554, 2.76), "today_fitted": (272, 1.40), "rules_fitted": (192, 0.76)},
                        "LOW": {"today_100m": (397, 2.00), "today_fitted": (172, 0.89), "rules_fitted": (122, 0.43)}},
    "max zoom 90m -60": {"HIGH": {"today_100m": (496, 2.60), "today_fitted": (741, 3.76), "rules_fitted": (486, 1.86)}},
    "26m -15": {"HIGH": {"today_100m": (579, 2.89), "today_fitted": (282, 1.40), "rules_fitted": (202, 0.81)}},
}


# --------------------------------------------------------------------------- table

def _gd_literal(text: str, start: int) -> str | None:
    """The literal after `=` at `start`: a balanced {...}/[...] or the rest of the line."""
    index = start
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text):
        return None
    if text[index] not in "{[":
        end = text.find("\n", index)
        return text[index:end if end >= 0 else len(text)]
    depth = 0
    for cursor in range(index, len(text)):
        if text[cursor] in "{[":
            depth += 1
        elif text[cursor] in "}]":
            depth -= 1
            if depth == 0:
                return text[index:cursor + 1]
    return None


def read_gd_constants(source: str, names: list[str]) -> dict:
    """Literal constants `const NAME[: Type] := <JSON-like literal>` among `names`."""
    found: dict = {}
    for name in names:
        match = re.search(rf"^const\s+{name}\s*(?::\s*[^=\n]*?)?\s*:?=", source, re.M)
        if not match:
            continue
        literal = _gd_literal(source, match.end())
        if literal is None:
            continue
        literal = re.sub(r"#[^\n]*", "", literal)
        literal = re.sub(r"&\"", "\"", literal)
        literal = re.sub(r",(\s*[}\]])", r"\1", literal).strip()
        try:
            found[name] = json.loads(literal)
        except json.JSONDecodeError:
            continue
    return found


def load_table(project: Path = PROJECT) -> dict:
    """The class table and where each value came from (client file or plan default)."""
    table = json.loads(json.dumps(PLAN_TABLE))
    source = {name: "plan" for name in table}
    names = [name for name in PLAN_TABLE if name != "TODAY_CELL_METRES"]
    for relative in TABLE_FILES:
        path = project / relative
        if path.is_file():
            for name, value in read_gd_constants(path.read_text(encoding="utf-8"), names).items():
                if _valid_entry(name, value):
                    table[name] = {str(k).upper(): float(v) for k, v in value.items()} \
                        if isinstance(value, dict) else value
                    source[name] = relative
    loader = project / "src/world/world_loader.gd"
    if loader.is_file():
        found = read_gd_constants(loader.read_text(encoding="utf-8"), ["BATCH_CELL_METRES"])
        if isinstance(found.get("BATCH_CELL_METRES"), (int, float)):
            table["TODAY_CELL_METRES"] = float(found["BATCH_CELL_METRES"])
            source["TODAY_CELL_METRES"] = "src/world/world_loader.gd"
    table["source"] = source
    return table


def _valid_entry(name: str, value) -> bool:
    if name == "CLASS_RADIUS_LIMITS":
        return isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) for v in value) \
            and value == sorted(value)
    if name in ("CELL_METRES", "REACH_METRES"):
        return isinstance(value, dict) and {str(k).upper() for k in value} == set(CLASSES)
    if name == "TIER_REACH_SCALE":
        return isinstance(value, dict) and {"HIGH", "LOW"} <= {str(k).upper() for k in value}
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def size_class(radius: float, table: dict) -> str:
    for limit, name in zip(table["CLASS_RADIUS_LIMITS"], CLASSES):
        if radius < limit:
            return name
    return "XL"


# --------------------------------------------------------------------------- glTF

def category(name: str) -> str:
    lowered = name.lower()
    for label, pattern in CATEGORIES:
        if re.search(pattern, lowered):
            return label
    return "prop"


def glb_json(path: Path) -> dict:
    with open(path, "rb") as handle:
        head = handle.read(20)
        if len(head) < 20 or head[:4] != b"glTF":
            raise ValueError(f"{path}: not a binary glTF")
        length = struct.unpack("<I", head[12:16])[0]
        return json.loads(handle.read(length))


def node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape(4, 4).T
    matrix = np.eye(4)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    rotation = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    matrix[:3, :3] = rotation * np.array(node.get("scale", [1, 1, 1]))
    matrix[:3, 3] = node.get("translation", [0, 0, 0])
    return matrix


def mesh_info(gltf: dict, mesh_index: int) -> dict:
    triangles = 0
    low = np.full(3, 1e18)
    high = np.full(3, -1e18)
    alpha = []
    primitives = gltf["meshes"][mesh_index]["primitives"]
    for primitive in primitives:
        counted = primitive["indices"] if "indices" in primitive else primitive["attributes"]["POSITION"]
        triangles += gltf["accessors"][counted]["count"] // 3
        position = gltf["accessors"][primitive["attributes"]["POSITION"]]
        low = np.minimum(low, position["min"])
        high = np.maximum(high, position["max"])
        material = gltf.get("materials", [{}])[primitive["material"]] if "material" in primitive else {}
        alpha.append(material.get("alphaMode", "OPAQUE"))
    return {"tris": triangles, "prims": len(primitives), "lo": low, "hi": high, "alpha": alpha}


def aabb_transform(matrix: np.ndarray, low: np.ndarray, high: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    corners = np.array([[x, y, z, 1] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
    world = (matrix @ corners.T).T[:, :3]
    return world.min(0), world.max(0)


def ground_kind(name: str) -> str:
    if name.startswith("Terrain_"):
        return "terrain"
    if name.startswith("AuthoredGround_") and "Base" in name.split("_")[1]:
        return "base"
    if name.startswith("AuthoredGround_"):
        return "patch"
    if name.startswith("Walk_"):
        return "deck"
    return "own"


class Territory:
    """The resident chunks of one territory around a focus, parsed once."""

    def __init__(self, maps: Path, territory: str, focus: list[float] | None = None):
        self.maps = maps
        self.name = territory
        self.directory = maps / "continent-v2" / territory / "client"
        manifest = json.loads((self.directory / "world.json").read_text(encoding="utf-8"))
        spawns = manifest.get("spawnPoints") or [{}]
        spawn = next((point for point in spawns if point.get("default")), spawns[0])
        self.spawn = spawn
        self.focus = np.array(focus if focus is not None else spawn["position"], dtype=float)
        self._prototypes: dict = {}
        self.chunks: dict = {}
        rows = []
        for chunk in manifest["streamingChunks"]["chunks"]:
            low, high = np.array(chunk["bounds"]["min"]), np.array(chunk["bounds"]["max"])
            gap = np.linalg.norm(np.maximum(np.maximum(low - self.focus, 0), self.focus - high)[[0, 2]])
            if gap <= PRELOAD_METRES:
                rows.append((gap, chunk["id"], self.directory / chunk["manifest"].replace("world.json", "world.glb")))
        rows.sort()
        for _, chunk_id, path in rows[:RESIDENT_LIMIT]:
            self.chunks[chunk_id] = self._parse_chunk(path)

    def _prototype(self, key: str) -> dict | None:
        if key not in self._prototypes:
            path = self.maps / "_shared" / "meshes" / f"{key}.glb"
            self._prototypes[key] = mesh_info(glb_json(path), 0) if path.is_file() else None
        return self._prototypes[key]

    def _parse_chunk(self, path: Path) -> tuple[list, list]:
        gltf = glb_json(path)
        own, placements = [], []
        scene = gltf["scenes"][gltf.get("scene", 0)]
        stack = [(index, np.eye(4)) for index in scene["nodes"]]
        while stack:
            index, parent = stack.pop()
            node = gltf["nodes"][index]
            matrix = parent @ node_matrix(node)
            name = node.get("name", "")
            if "mesh" in node:
                info = mesh_info(gltf, node["mesh"])
                low, high = aabb_transform(matrix, info["lo"], info["hi"])
                own.append({"name": name, "kind": ground_kind(name), "tris": info["tris"], "prims": info["prims"],
                            "lo": low, "hi": high})
            extras = node.get("extras", {})
            eloria = extras.get("eloria") if isinstance(extras, dict) else None
            if isinstance(eloria, dict) and eloria.get("prototype"):
                info = self._prototype(eloria["prototype"])
                if info is not None:
                    low, high = aabb_transform(matrix, info["lo"], info["hi"])
                    placements.append({"key": eloria["prototype"], "cat": category(name), "tris": info["tris"],
                                       "prims": info["prims"], "lo": low, "hi": high,
                                       "opaque": all(mode == "OPAQUE" for mode in info["alpha"]),
                                       "origin": matrix[:3, 3].copy(),
                                       "radius": float(np.linalg.norm(high - low) / 2)})
            for child in node.get("children", []):
                stack.append((child, matrix))
        return own, placements

    def summary(self, table: dict) -> dict:
        placements = [p for _, chunk in self.chunks.values() for p in chunk]
        by_class = Counter()
        for p in placements:
            by_class[f"{p['cat']}/{size_class(p['radius'], table)}"] += p["tris"]
        return {"territory": self.name, "focus": self.focus.tolist(), "serverTile": self.spawn.get("serverTile"),
                "spawn": self.spawn.get("id"), "residentChunks": len(self.chunks), "placements": len(placements),
                "prototypeTriangles": sum(p["tris"] for p in placements),
                "ownTriangles": sum(o["tris"] for own, _ in self.chunks.values() for o in own),
                "trianglesByCategoryClass": dict(by_class.most_common())}


# --------------------------------------------------------------------------- units and culling

def variant_rules(variant: str, table: dict) -> dict:
    if variant == "today":
        return {"cell": lambda p: table["TODAY_CELL_METRES"]}
    rules = {"cell": lambda p: table["CELL_METRES"][size_class(p["radius"], table)], "split_class": True}
    if variant == "cells":
        return rules
    def reach(p):
        end = table["REACH_METRES"][size_class(p["radius"], table)]
        return (0.0, end) if end > 0 else None
    rules.update(range=reach, hide_terrain=variant != "ranges_keep_terrain", ground_no_shadow=True,
                 small_no_shadow=True)
    if variant == "far_proxies":
        limit = table["CLASS_RADIUS_LIMITS"][0]
        rules.update(impostor=lambda p: table["FAR_PROXY_METRES"] if p["cat"] == "tree" and p["radius"] >= limit
                     else None, imp_abs=True)
    return rules


def build_units(chunks: dict, rules: dict, table: dict) -> list[dict]:
    """What the renderer culls: one MeshInstance3D or one MultiMeshInstance3D each."""
    small = table["CLASS_RADIUS_LIMITS"][0]
    units = []
    for chunk_id, (own, placements) in chunks.items():
        for o in own:
            if rules.get("hide_terrain") and o["kind"] == "terrain":
                continue
            units.append({"chunk": chunk_id, "kind": o["kind"], "lo": o["lo"], "hi": o["hi"], "tris": o["tris"],
                          "draws": o["prims"], "end": 0.0, "begin": 0.0,
                          "shadow": not (rules.get("ground_no_shadow")
                                         and o["kind"] in ("terrain", "base", "patch", "deck"))})
        groups = defaultdict(list)
        singles = []
        for p in placements:
            if not p["opaque"]:
                singles.append(p)
                continue
            cell = rules["cell"](p)
            klass = size_class(p["radius"], table) if rules.get("split_class") else ""
            origin = p["origin"]
            groups[(p["key"], klass) + tuple(math.floor(origin[axis] / cell) for axis in range(3))].append(p)
        batches = []
        for members in groups.values():
            if len(members) < 4:
                singles.extend(members)
            else:
                batches.append(members)
        for members in batches + [[p] for p in singles]:
            first = members[0]
            batch = len(members) > 1  # Groups batch at four or more members.
            low = np.min([m["lo"] for m in members], 0)
            high = np.max([m["hi"] for m in members], 0)
            reach = rules["range"](first) if rules.get("range") else None
            proxy = rules["impostor"](first) if rules.get("impostor") else None
            absolute = bool(proxy) and rules.get("imp_abs", False)
            units.append({"chunk": chunk_id, "kind": ("batch:" if batch else "single:") + first["cat"],
                          "lo": low, "hi": high, "tris": sum(m["tris"] for m in members), "draws": first["prims"],
                          "end": proxy if proxy else (reach[1] if reach else 0.0), "begin": 0.0,
                          "shadow": not (rules.get("small_no_shadow") and first["radius"] < small), "abs": absolute})
            if proxy:
                units.append({"chunk": chunk_id, "kind": "impostor", "lo": low, "hi": high, "tris": 4 * len(members),
                              "draws": 0, "end": 0.0, "begin": proxy, "shadow": False,
                              "abs": rules.get("imp_abs", False)})
    return units


def camera(focus: np.ndarray, distance: float, pitch: float, yaw: float):
    yaw_r, pitch_r = math.radians(yaw), math.radians(pitch)
    offset = np.array([math.sin(yaw_r) * math.cos(pitch_r), -math.sin(pitch_r),
                       math.cos(yaw_r) * math.cos(pitch_r)]) * distance
    position = focus + offset
    forward = focus + np.array([0, 1.2, 0]) - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return position, forward, right, up, min(max(distance * 0.25, 0.2), 1.0)


def frustum_planes(position, forward, right, up, near, far, aspect):
    """Inward planes (normal, d): inside when normal . x + d >= 0."""
    tan_v = math.tan(math.radians(FIELD_OF_VIEW) / 2)
    tan_h = tan_v * aspect
    planes = [(forward, -np.dot(forward, position + forward * near)),
              (-forward, np.dot(forward, position + forward * far))]
    for sign in (1, -1):
        for normal in (np.cross(up, forward + right * tan_h * sign) * sign,
                       np.cross(forward + up * tan_v * sign, right) * sign):
            normal = normal / np.linalg.norm(normal)
            if np.dot(normal, forward) < 0:
                normal = -normal
            planes.append((normal, -np.dot(normal, position)))
    return planes


def visible(unit: dict, planes) -> bool:
    for normal, offset in planes:
        if np.dot(normal, np.where(normal >= 0, unit["hi"], unit["lo"])) + offset < 0:
            return False
    return True


def _in_range(unit: dict, position, scale: float, camera_distance: float) -> bool:
    distance = float(np.linalg.norm((unit["lo"] + unit["hi"]) / 2 - position))
    relative = 0.0 if unit.get("abs") else camera_distance
    if unit["end"] > 0 and distance > relative + unit["end"] * scale:
        return False
    return not (unit["begin"] > 0 and distance < relative + unit["begin"] * scale)


def count(units, position, planes, scale: float, camera_distance: float):
    draws = primitives = 0
    by_primitives, by_draws = Counter(), Counter()
    proxy_chunks = set()
    for unit in units:
        if not visible(unit, planes) or not _in_range(unit, position, scale, camera_distance):
            continue
        if unit["kind"] == "impostor":
            proxy_chunks.add(unit["chunk"])
            primitives += unit["tris"]
            by_primitives["impostor"] += unit["tris"]
            continue
        kind = unit["kind"].split(":")[-1]
        draws += unit["draws"]
        primitives += unit["tris"]
        by_primitives[kind] += unit["tris"]
        by_draws[kind] += unit["draws"]
    draws += len(proxy_chunks)  # One proxy MultiMesh per chunk.
    by_draws["impostor"] = len(proxy_chunks)
    return draws, primitives, by_primitives, by_draws


def _sun() -> np.ndarray:
    pitch, yaw = (math.radians(value) for value in SUN_DEGREES)
    direction = np.array([-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch)])
    return direction / np.linalg.norm(direction)


def cascade_slices(position, forward, right, up, near, maximum, splits, aspect):
    tan_v = math.tan(math.radians(FIELD_OF_VIEW) / 2)
    tan_h = tan_v * aspect
    bounds = [near] + [maximum * split for split in splits] + [maximum]
    slices = []
    for start, end in zip(bounds[:-1], bounds[1:]):
        points = np.array([position + forward * depth + right * tan_h * depth * sx + up * tan_v * depth * sy
                           for depth in (start, end) for sx in (-1, 1) for sy in (-1, 1)])
        centre = points.mean(0)
        slices.append((centre, max(np.linalg.norm(points - centre, axis=1))))
    return slices


def casters(units, slices, position, camera_distance: float, scale: float, use_rules: bool):
    """Units whose AABB, projected along the sun, overlaps each cascade's bounding sphere."""
    sun = _sun()
    draws = primitives = 0
    for centre, radius in slices:
        for unit in units:
            if (use_rules and not unit.get("shadow", True)) or unit["kind"] == "impostor":
                continue
            if not _in_range(unit, position, scale, camera_distance):
                continue
            middle = (unit["lo"] + unit["hi"]) / 2
            half = np.linalg.norm(unit["hi"] - unit["lo"]) / 2
            offset = middle - centre
            across = offset - np.dot(offset, sun) * sun
            if np.linalg.norm(across) <= radius + half and np.dot(offset, sun) < radius + half:
                draws += unit["draws"]
                primitives += unit["tris"]
    return draws, primitives


# --------------------------------------------------------------------------- reports

def budget(territory: Territory, table: dict, aspects=None, poses=POSES, shadows: bool = False) -> dict:
    aspects = aspects or ASPECTS
    units = {variant: build_units(territory.chunks, variant_rules(variant, table), table) for variant in VARIANTS}
    rows = []
    for aspect_name, aspect in aspects.items():
        for pose, distance, pitch in poses:
            for variant in VARIANTS:
                for tier in ("HIGH", "LOW"):
                    scale = 1.0 if variant == "today" else table["TIER_REACH_SCALE"][tier]
                    far = table["LOW_FAR_METRES"] if tier == "LOW" and variant != "today" else 1800.0
                    totals = [0, 0, Counter(), Counter()]
                    for yaw in YAWS:
                        position, forward, right, up, near = camera(territory.focus, distance, pitch, yaw)
                        planes = frustum_planes(position, forward, right, up, near, far, aspect)
                        result = count(units[variant], position, planes, scale, distance)
                        for index in range(2):
                            totals[index] += result[index]
                        totals[2].update(result[2])
                        totals[3].update(result[3])
                    count_yaws = len(YAWS)
                    rows.append({"aspect": aspect_name, "pose": pose, "distance": distance, "pitch": pitch,
                                 "variant": variant, "tier": tier, "farMetres": far, "reachScale": scale,
                                 "draws": totals[0] / count_yaws, "primitives": totals[1] / count_yaws,
                                 "primitivesBy": {k: v / count_yaws for k, v in totals[2].most_common()},
                                 "drawsBy": {k: v / count_yaws for k, v in totals[3].most_common()}})
    out = {"schema": SCHEMA, "tool": "world_draw_budget", **territory.summary(table),
           "table": table, "yaws": list(YAWS), "fieldOfView": FIELD_OF_VIEW,
           "assumptions": ["own territory only (resident neighbour territories are not drawn)",
                           "ranges/far_proxies hide every Terrain_ (C1 upper bound); ranges_keep_terrain does not",
                           f"LOW far plane {table['LOW_FAR_METRES']} m flat (C4 estimate)",
                           "Godot culls a MultiMesh as one AABB; ranges measure to the AABB centre"],
           "rows": rows}
    if shadows:
        out["shadows"] = shadow_budget(territory, table, units)
    return out


def shadow_budget(territory: Territory, table: dict, units: dict, poses=POSES) -> list[dict]:
    rows = []
    for pose, distance, pitch in poses:
        for tier, splits in SHADOW_TIERS.items():
            fitted = 1.4 * distance + 12.0
            for label, variant, maximum, rules in (("today_100m", "today", 100.0, False),
                                                    ("today_fitted", "today", fitted, False),
                                                    ("rules_fitted", "far_proxies", fitted, True)):
                scale = table["TIER_REACH_SCALE"][tier] if rules else 1.0
                draws = primitives = 0
                for yaw in YAWS:
                    position, forward, right, up, near = camera(territory.focus, distance, pitch, yaw)
                    slices = cascade_slices(position, forward, right, up, near, maximum, splits, ASPECTS["16:9"])
                    d, p = casters(units[variant], slices, position, distance, scale, rules)
                    draws += d
                    primitives += p
                rows.append({"pose": pose, "distance": distance, "pitch": pitch, "tier": tier,
                             "cascades": len(splits) + 1, "label": label, "shadowMaxDistance": maximum,
                             "draws": draws / len(YAWS), "casterPrimitives": primitives / len(YAWS)})
    return rows


def _close(actual: float, expected: float, rounding: float) -> bool:
    """Within 1 %, or within the reference table's own rounding."""
    return abs(actual - expected) <= max(0.01 * abs(expected), rounding)


def check_reference(maps: Path = DEFAULT_MAPS, table: dict | None = None) -> list[str]:
    """Differences from the plan's section 2.2 (and Landfall's 2.3); empty when reproduced."""
    table = table or {**PLAN_TABLE, "source": {}}
    problems = []
    for name, poses in REFERENCE.items():
        territory = Territory(maps, name)
        pose_rows = tuple(row for row in POSES if row[0] in poses)
        report = budget(territory, table, {"16:9": ASPECTS["16:9"]}, pose_rows, shadows=name == "landfall")
        index = {(r["pose"], r["variant"], r["tier"]): r for r in report["rows"]}
        for pose, expected in poses.items():
            for (variant, tier), (draws, kilo) in zip(REFERENCE_COLUMNS, expected):
                row = index[(pose, variant, tier)]
                if not _close(row["draws"], draws, 0.5) or not _close(row["primitives"] / 1000, kilo, 0.5):
                    problems.append(f"{name} {pose} {variant} {tier}: {row['draws']:.1f} / "
                                    f"{row['primitives'] / 1000:.1f}k, expected {draws} / {kilo}k")
        if name == "landfall":
            shadows = {(r["pose"], r["tier"], r["label"]): r for r in report["shadows"]}
            for pose, tiers in SHADOW_REFERENCE.items():
                for tier, labels in tiers.items():
                    for label, (draws, mega) in labels.items():
                        row = shadows[(pose, tier, label)]
                        if not _close(row["draws"], draws, 0.5) or \
                                not _close(row["casterPrimitives"] / 1e6, mega, 0.005):
                            problems.append(f"landfall shadows {pose} {tier} {label}: {row['draws']:.1f} / "
                                            f"{row['casterPrimitives'] / 1e6:.3f} M, expected {draws} / {mega} M")
    return problems


def markdown(report: dict) -> str:
    lines = [f"{report['territory']}: focus {report['focus']} (tile {report['serverTile']}), "
             f"{report['residentChunks']} chunks, {report['placements']} placements", "",
             "| Aspect | Pose | " + " | ".join(f"{v} {t}" for v in VARIANTS for t in ("HIGH", "LOW")) + " |",
             "| --- | --- | " + " | ".join("---:" for _ in range(2 * len(VARIANTS))) + " |"]
    index = {(r["aspect"], r["pose"], r["variant"], r["tier"]): r for r in report["rows"]}
    for aspect in dict.fromkeys(r["aspect"] for r in report["rows"]):
        for pose in dict.fromkeys(r["pose"] for r in report["rows"]):
            cells = []
            for variant in VARIANTS:
                for tier in ("HIGH", "LOW"):
                    row = index[(aspect, pose, variant, tier)]
                    cells.append(f"{row['draws']:.0f} / {row['primitives'] / 1000:,.0f}k")
            lines.append(f"| {aspect} | {pose} | " + " | ".join(cells) + " |")
    for row in report.get("shadows", []):
        if row is report["shadows"][0]:
            lines += ["", "| Pose | Tier | Casters | Shadow max m | Draws | Caster primitives |",
                      "| --- | --- | --- | ---: | ---: | ---: |"]
        lines.append(f"| {row['pose']} | {row['tier']} | {row['label']} | {row['shadowMaxDistance']:.0f} | "
                     f"{row['draws']:.0f} | {row['casterPrimitives']:,.0f} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("territory", nargs="?", help="continent-v2 territory, e.g. landfall")
    parser.add_argument("--maps", type=Path, default=DEFAULT_MAPS, help="eloria-assets/maps directory")
    parser.add_argument("--focus", help="x,y,z world focus (default: the territory's default spawn)")
    parser.add_argument("--shadows", action="store_true", help="add the cascade caster estimate")
    parser.add_argument("--plan-table", action="store_true", help="ignore the client's class table")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--check-reference", action="store_true",
                        help="reproduce the plan's section 2.2/2.3 numbers (plan table) within 1 %%")
    args = parser.parse_args(argv)
    if args.check_reference:
        problems = check_reference(args.maps)
        print("\n".join(problems) if problems else "world_draw_budget: section 2.2/2.3 reproduced within 1 %")
        return 1 if problems else 0
    if not args.territory:
        parser.error("a territory (or --check-reference) is required")
    focus = [float(value) for value in args.focus.split(",")] if args.focus else None
    if focus is not None and len(focus) != 3:
        parser.error("--focus takes x,y,z")
    table = {**PLAN_TABLE, "source": {name: "plan" for name in PLAN_TABLE}} if args.plan_table else load_table()
    report = budget(Territory(args.maps, args.territory, focus), table, shadows=args.shadows)
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
