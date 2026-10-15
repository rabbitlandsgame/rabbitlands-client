"""Kit models placed into a trail gauntlet package.

A kit model (a region's `kit-*.glb` prototype, or one of a route's own Meshy
pieces) is read once, its meshes and textures are written into the package's
GLB once, and every placement is a node that instances those meshes, so the
client's static batching draws a forest of one tree as one MultiMesh per
cell. Each model also yields a footprint: the ground its body occupies, from
its own triangles that cross the band a walker's body fills (0.25-2.1 m),
with enclosed holes filled - a boulder is solid through, a keep with a
doorway keeps its open floor. Placing a model with `solid="footprint"`
closes that ground in the walk grids; `solid="trunk"` closes only a disc at
the model's origin (trees block at the trunk); `solid=None` is walk-through.
"""
from __future__ import annotations

import hashlib
import math
import struct
import sys
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TOOLKIT = HERE.parents[1] / "nymara-regions" / "_toolkit"
sys.path.insert(0, str(TOOLKIT))
import glb_reader  # noqa: E402
from amberwood import gltf as G, mesh as M  # noqa: E402

COMPONENT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
COLUMNS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
BAND = (0.25, 2.1)                 # the body a walker or creature occupies above its ground
FOOT_CELL = 0.25                   # metres per footprint cell (local frame)


def _accessor(doc, body, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    dtype = COMPONENT[acc["componentType"]]
    cols = COLUMNS[acc["type"]]
    count = acc["count"]
    offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0)
    item = np.dtype(dtype).itemsize * cols
    if stride and stride != item:
        raw = np.frombuffer(body, dtype=np.uint8, count=stride * (count - 1) + item, offset=offset)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(count, item), strides=(stride, 1))
        data = np.frombuffer(rows.copy().tobytes(), dtype=dtype).reshape(count, cols)
    else:
        data = np.frombuffer(body, dtype=dtype, count=count * cols, offset=offset).reshape(count, cols)
    data = data.astype(np.float64)
    if acc.get("normalized"):
        data /= float(np.iinfo(dtype).max)
    return data if cols > 1 else data[:, 0]


def _node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.eye(4)
    if "translation" in node:
        t[:3, 3] = node["translation"]
    r = np.eye(4)
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        r[:3, :3] = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    s = np.eye(4)
    if "scale" in node:
        s[0, 0], s[1, 1], s[2, 2] = node["scale"]
    return t @ r @ s


def _image_bytes(doc, body, glb_path, image_index):
    image = doc["images"][image_index]
    if "bufferView" in image:
        view = doc["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        return bytes(body[start:start + view["byteLength"]])
    return (Path(glb_path).parent / image["uri"]).read_bytes()


def _add_image(builder, blob):
    name = "img_" + hashlib.sha256(blob).hexdigest()[:20]
    index = builder.add_image(name, blob)
    builder._images[index]["mimeType"] = "image/jpeg" if blob[:2] == b"\xff\xd8" else "image/png"
    return name


class Kit:
    def __init__(self, key, meshes, footprint, origin_cell, bounds):
        self.key = key
        self.meshes = meshes            # [(mesh name, with_tangents)]
        self.footprint = footprint      # bool [rows (local z), cols (local x)]
        self.origin_cell = origin_cell  # (row, col) of local (0, 0)
        self.bounds = bounds            # (min xyz, max xyz) in kit metres


class KitLibrary:
    def __init__(self, builder):
        self.builder = builder
        self.kits: dict[str, Kit] = {}
        self.placements = 0
        self.triangles = 0
        self.solid_cells: list[tuple[float, float]] = []    # world plan points closed by footprints
        self.trunks: list[tuple[float, float, float]] = []  # (x, y, r) discs

    def load(self, key, path, prescale=1.0, tint=None):
        if key in self.kits:
            return self.kits[key]
        doc, body = glb_reader.load(Path(path))
        scene = doc.get("scenes", [{}])[doc.get("scene", 0)]
        roots = scene.get("nodes", list(range(len(doc["nodes"]))))
        prims = []

        def walk(index, parent):
            node = doc["nodes"][index]
            world = parent @ _node_matrix(node)
            if "mesh" in node:
                for prim in doc["meshes"][node["mesh"]]["primitives"]:
                    prims.append((prim, world))
            for child in node.get("children", []):
                walk(child, world)
        for root in roots:
            walk(root, np.diag([prescale, prescale, prescale, 1.0]))

        materials = {}
        meshes = []
        all_points = []
        tris_band = []
        for k, (prim, world) in enumerate(prims):
            attrs = prim["attributes"]
            pos = _accessor(doc, body, attrs["POSITION"])
            pos = (np.c_[pos, np.ones(len(pos))] @ world.T)[:, :3]
            if "NORMAL" in attrs:
                nrm = _accessor(doc, body, attrs["NORMAL"]) @ np.linalg.inv(world[:3, :3]).T
                nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
            else:
                nrm = np.zeros_like(pos)
            uv = _accessor(doc, body, attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else np.zeros((len(pos), 2))
            idx = (_accessor(doc, body, prim["indices"]).astype(np.int64) if "indices" in prim
                   else np.arange(len(pos), dtype=np.int64))
            mat_index = prim.get("material", -1)
            if mat_index not in materials:
                materials[mat_index] = self._material(doc, body, path, key, mat_index, tint)
            mat_name, tangents = materials[mat_index]
            mesh = M.Mesh(positions=pos, normals=nrm, uvs=uv, indices=idx, material=mat_name)
            if not np.any(nrm):
                mesh.recompute_normals(50.0)
            mesh = mesh.sanitise_normals()
            name = f"Kit_{key}_{k}"
            self.builder.add_mesh(name, mesh, with_tangents=tangents)
            meshes.append((name, tangents))
            all_points.append(pos)
            tri = pos[idx.reshape(-1, 3)]
            tris_band.append(tri)
            self.triangles += 0
        points = np.vstack(all_points)
        lo, hi = points.min(axis=0), points.max(axis=0)
        tris = np.vstack(tris_band)
        foot, origin = self._footprint(tris, lo, hi)
        kit = Kit(key, meshes, foot, origin, (lo, hi))
        kit.tris = int(sum(len(t) for t in tris_band))
        # the faces that look up, for finding a deck: centroid (x, y, z) and area of each
        normal = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        length = np.maximum(np.linalg.norm(normal, axis=1), 1e-12)
        up = normal[:, 1] / length > 0.85
        kit.up_faces = (tris[up].mean(axis=1), 0.5 * length[up])
        self.kits[key] = kit
        return kit

    def _material(self, doc, body, path, key, index, tint=None):
        if index < 0:
            name = f"KitMat_{key}_default"
            self.builder.add_material(G.Material(name, base_color=(0.7, 0.7, 0.7, 1)))
            return name, False
        mat = doc["materials"][index]
        pbr = mat.get("pbrMetallicRoughness", {})

        def tex(info):
            if not info:
                return None
            source = doc["textures"][info["index"]]["source"]
            return _add_image(self.builder, _image_bytes(doc, body, path, source))
        base = tex(pbr.get("baseColorTexture"))
        orm = tex(pbr.get("metallicRoughnessTexture"))
        normal = tex(mat.get("normalTexture"))
        name = f"KitMat_{key}_{index}"
        factor = list(pbr.get("baseColorFactor", (1, 1, 1, 1)))
        if tint:
            factor = [factor[0] * tint[0], factor[1] * tint[1], factor[2] * tint[2], factor[3]]
        self.builder.add_material(G.Material(
            name, base_color=tuple(factor),
            metallic=float(pbr.get("metallicFactor", 0.0 if base else 0.0)),
            roughness=float(pbr.get("roughnessFactor", 0.9)),
            base_color_texture=base, orm_texture=orm, normal_texture=normal,
            emissive=tuple(mat.get("emissiveFactor", (0, 0, 0))),
            alpha_mode=mat.get("alphaMode", "OPAQUE"), alpha_cutoff=float(mat.get("alphaCutoff", 0.5)),
            double_sided=bool(mat.get("doubleSided", False))))
        return name, normal is not None

    def _footprint(self, tris, lo, hi):
        """Cells (local x, z) the body band of the model covers, enclosed holes filled."""
        cols = int(math.ceil((hi[0] - lo[0]) / FOOT_CELL)) + 3
        rows = int(math.ceil((hi[2] - lo[2]) / FOOT_CELL)) + 3
        grid = np.zeros((rows, cols), bool)
        base = lo[1]
        y0, y1 = base + BAND[0], base + BAND[1]
        ymin = tris[:, :, 1].min(axis=1)
        ymax = tris[:, :, 1].max(axis=1)
        # walls, not floors: a raised rubble floor inside a ruin lies in the band too, and would
        # seal a courtyard a doorway opens onto; a solid's flat top is enclosed by its sides anyway
        normal = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        upright = np.abs(normal[:, 1]) < 0.75 * np.maximum(np.linalg.norm(normal, axis=1), 1e-12)
        keep = (ymax >= y0) & (ymin <= y1) & upright
        for a, b, c in tris[keep]:
            edge = max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b))
            n = max(2, int(edge / (FOOT_CELL * 0.5)) + 1)
            u, v = np.meshgrid(np.linspace(0, 1, n), np.linspace(0, 1, n))
            mask = u + v <= 1.0
            u, v = u[mask], v[mask]
            pts = a[None] + u[:, None] * (b - a)[None] + v[:, None] * (c - a)[None]
            inside = (pts[:, 1] >= y0) & (pts[:, 1] <= y1)
            pts = pts[inside]
            ci = ((pts[:, 0] - lo[0]) / FOOT_CELL).astype(int) + 1
            ri = ((pts[:, 2] - lo[2]) / FOOT_CELL).astype(int) + 1
            grid[ri, ci] = True
        # fill holes: whatever the border cannot reach without crossing the body is inside it
        outside = np.zeros_like(grid)
        queue = deque([(0, 0)])
        outside[0, 0] = True
        while queue:
            r, c = queue.popleft()
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and not outside[nr, nc] and not grid[nr, nc]:
                    outside[nr, nc] = True
                    queue.append((nr, nc))
        filled = ~outside
        origin = (int((0 - lo[2]) / FOOT_CELL) + 1, int((0 - lo[0]) / FOOT_CELL) + 1)
        return filled, origin

    def deck_top(self, key, max_fraction=1.0, central=0.3):
        """Height (kit metres above its base) of the walking surface: the level holding the most
        upward-facing area in the middle of the model (a bridge's deck, not its rails), below
        `max_fraction` of its height (a roofed bridge's roof is left out)."""
        kit = self.kits[key]
        lo, hi = kit.bounds
        centres, areas = kit.up_faces
        mid = (lo + hi) / 2
        span = hi - lo
        inner = ((np.abs(centres[:, 0] - mid[0]) <= central * span[0] + 0.5)
                 & (np.abs(centres[:, 2] - mid[2]) <= central * span[2] + 0.5)
                 & (centres[:, 1] <= lo[1] + max_fraction * span[1]))
        if not inner.any():
            return float(hi[1] - lo[1])
        heights = centres[inner, 1] - lo[1]
        bins = np.round(heights / 0.25).astype(int)
        weight = np.bincount(bins, weights=areas[inner])
        return float(np.argmax(weight) * 0.25)

    def extent(self, key):
        """(x length, height, z depth) of a model at scale 1."""
        lo, hi = self.kits[key].bounds
        return tuple(float(v) for v in hi - lo)

    def place(self, root, key, x, y, z, rot_deg=0.0, scale=1.0, solid="footprint", name=None):
        """One placement at plan (x, y) with its base at height z, turned rot_deg (plan degrees,
        x toward +y) about the vertical."""
        kit = self.kits[key]
        theta = math.radians(rot_deg)
        for mesh_name, _ in kit.meshes:
            root.add(G.Node(name or f"{mesh_name}_{self.placements}", mesh=mesh_name,
                            translation=(x, z, y), rotation_y=-theta, scale=(scale, scale, scale)))
        self.placements += 1
        self.triangles += kit.tris
        if solid == "footprint":
            rr, cc = np.nonzero(kit.footprint)
            lx = (cc - kit.origin_cell[1] + 0.5) * FOOT_CELL * scale
            lz = (rr - kit.origin_cell[0] + 0.5) * FOOT_CELL * scale
            wx = x + lx * math.cos(theta) - lz * math.sin(theta)
            wy = y + lx * math.sin(theta) + lz * math.cos(theta)
            self.solid_cells.extend(zip(wx.tolist(), wy.tolist()))
        elif solid == "trunk":
            self.trunks.append((x, y, 0.45 * scale))

    def solid_mask(self, cx, cy):
        """Half-metre cells (centres cx, cy, plan) a placed footprint or trunk closes."""
        mask = np.zeros(cx.shape, bool)
        if self.solid_cells:
            pts = np.array(self.solid_cells)
            ci = np.clip((pts[:, 0] / 0.5).astype(int), 0, cx.shape[1] - 1)
            ri = np.clip((pts[:, 1] / 0.5).astype(int), 0, cx.shape[0] - 1)
            mask[ri, ci] = True
        for x, y, r in self.trunks:
            mask |= (cx - x) ** 2 + (cy - y) ** 2 < (r + 0.3) ** 2
        return mask
