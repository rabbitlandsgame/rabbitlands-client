"""Apply the local seating fixes to copies of the south-west isle's accepted Meshy kit.

The batch-1 reviews (work-output/continent-v2/meshy/batch1/batch1_summary.md, "Fixes still to apply at
seating") and the N8 redesign review list local fixes that cost no credits. This tool applies the mechanical
ones to COPIES of the accepted, normalised kit GLBs and writes them to an output folder, which
prepare_meshy_kit.py then seats in the territory kit. The accepted kits under meshy/batch1/*/kit and
meshy/n8_redesign/kit are only read.

What it does, per piece (ASSETS below):
- geometry: deletes named faces (N9's four needle triangles), coincident duplicate faces (N19's 15 pairs,
  and any others: keeping the twin whose texel matches its neighbours), snaps the floating fragments the
  reviews name (N1 gable trim, N13 under-deck part), re-cuts and rescales N12 to a 12.0 m module that
  closes the joint slit, stretches the underwater feet of N12 (to -8 m) and N13 (to -6 m), flattens N3's
  melted slit notch, and widens N10's +-X kerb openings to about 8 m;
- texture: repaints colour defects inside a face zone (blue on stone, pale on cobalt, grey streaks on stone,
  brown smudges in the blossom), pulls palette zones (N4 gold lightness, N16 bark and foliage, N17 blossom
  saturation, N18/N19 turf), moves the N18/N19 rock to the warm grey of the reuse coastal rocks (slice-2
  visual review: it read as a pale sugar cube), and gives the tree crowns a top-light gradient driven by
  height in the crown;
- walk surfaces: splits the deck and platform tops of N10, N12 and N13, and N5's raised passage paving, into a
  child node named `Walk_...`, so the bake and the client treat them as walk surfaces (the spec's `Walk_`
  family);
- records: writes the collider primitives from the reviews into the root node's glTF extras
  (`extras.eloria`), with the piece id, origin kind and seating notes;
- light: the landing beacon (N20, meshy/beacon, its review passed with fixes) gets its crystal as a second,
  emissive primitive and a point-light record (`extras.eloria.light`) at its measured light anchor.

Owner's-call and optional items are left as delivered and listed in the report (`seat_fixes_report.json`).

    python seat_fixes.py --batch1 <meshy/batch1> --n8 <meshy/n8_redesign/kit> [--beacon <meshy/beacon>] --out <folder>
                         [--only N20] [--check]

`--check` rebuilds every piece in memory and compares it with the files in --out.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import cv2
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, gaussian_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


# --------------------------------------------------------------------------- GLB in / out

def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError(f"{path.name} is not a binary glTF")
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    offset = 20 + json_length
    binary_length = struct.unpack_from("<I", data, offset)[0]
    return document, data[offset + 8:offset + 8 + binary_length]


def _accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = {5126: "<f4", 5125: "<u4", 5123: "<u2", 5121: "u1"}[accessor["componentType"]]
    width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor["type"]]
    if view.get("byteStride") and view["byteStride"] != width * np.dtype(dtype).itemsize:
        raise ValueError("strided accessors are not expected in a normalised kit")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    values = np.frombuffer(binary, dtype=dtype, count=accessor["count"] * width, offset=start).copy()
    return values.reshape(-1, width) if width > 1 else values


class Kit:
    """A normalised kit GLB: one node without a transform, one mesh, one primitive, one embedded image."""

    def __init__(self, path: Path):
        document, binary = _read_glb(path)
        self.source = path
        if len(document["nodes"]) != 1 or len(document["meshes"]) != 1 or \
                len(document["meshes"][0]["primitives"]) != 1:
            raise ValueError(f"{path.name}: expected one node, one mesh and one primitive")
        node = document["nodes"][0]
        if any(key in node for key in ("matrix", "translation", "rotation", "scale")):
            raise ValueError(f"{path.name}: the node carries a transform")
        primitive = document["meshes"][0]["primitives"][0]
        self.name = node.get("name", path.stem)
        self.pos = _accessor(document, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
        self.nrm = _accessor(document, binary, primitive["attributes"]["NORMAL"]).astype(np.float64)
        self.uv = _accessor(document, binary, primitive["attributes"]["TEXCOORD_0"]).astype(np.float64)
        self.idx = _accessor(document, binary, primitive["indices"]).astype(np.int64).reshape(-1, 3)
        image = document["images"][0]
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        self.image_bytes = binary[start:start + view["byteLength"]]
        self.mime = image.get("mimeType", "image/jpeg")
        self.image = np.array(Image.open(io.BytesIO(self.image_bytes)).convert("RGB"))
        self.image_changed = False
        self.material = document["materials"][0]
        self.samplers = document.get("samplers")
        self.walk_faces = np.zeros(len(self.idx), bool)
        self.walk_name = ""
        # faces drawn with a second, emissive material (the landing beacon's crystal); none on other pieces
        self.glow_faces = np.zeros(len(self.idx), bool)
        self.glow_material: dict | None = None
        self.extras: dict = {}

    # faces
    def tri(self) -> np.ndarray:
        return self.pos[self.idx]

    def centroids(self) -> np.ndarray:
        return self.tri().mean(axis=1)

    def face_normals(self) -> tuple[np.ndarray, np.ndarray]:
        t = self.tri()
        cross = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        length = np.linalg.norm(cross, axis=1)
        return cross / np.maximum(length[:, None], 1e-12), length / 2

    def keep_faces(self, keep: np.ndarray) -> None:
        """Keeps the chosen faces and drops the vertices no face uses any more."""
        self.idx = self.idx[keep]
        self.walk_faces = self.walk_faces[keep]
        self.glow_faces = self.glow_faces[keep]
        used, inverse = np.unique(self.idx.ravel(), return_inverse=True)
        self.pos, self.nrm, self.uv = self.pos[used], self.nrm[used], self.uv[used]
        self.idx = inverse.reshape(-1, 3)

    def add_faces(self, positions: np.ndarray, normals: np.ndarray, uvs: np.ndarray) -> None:
        base = len(self.pos)
        self.pos = np.vstack([self.pos, positions])
        self.nrm = np.vstack([self.nrm, normals])
        self.uv = np.vstack([self.uv, uvs])
        count = len(positions) // 3
        self.idx = np.vstack([self.idx, base + np.arange(count * 3).reshape(-1, 3)])
        self.walk_faces = np.concatenate([self.walk_faces, np.zeros(count, bool)])
        self.glow_faces = np.concatenate([self.glow_faces, np.zeros(count, bool)])

    def uv_px(self) -> np.ndarray:
        height, width = self.image.shape[:2]
        uv = self.uv[self.idx]
        return np.stack([uv[..., 0] * width, uv[..., 1] * height], axis=-1)

    def texel_at_centroid(self) -> np.ndarray:
        """RGB (0-1) sampled at three interior points of each face, averaged."""
        height, width = self.image.shape[:2]
        uv = self.uv[self.idx]
        samples = []
        for weights in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
            point = (uv * np.array(weights)[None, :, None]).sum(axis=1)
            x = np.clip((point[:, 0] * width).astype(int), 0, width - 1)
            y = np.clip((point[:, 1] * height).astype(int), 0, height - 1)
            samples.append(self.image[y, x] / 255.0)
        return np.median(np.stack(samples), axis=0)

    def write(self, quality: int = 95) -> bytes:
        glowing = bool(self.glow_faces.any())
        document = {"asset": {"version": "2.0", "generator": "Eloria sw_isle seat_fixes"},
                    "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [], "meshes": [],
                    "materials": [self.material] + ([self.glow_material] if glowing else []),
                    "textures": [{"source": 0}], "images": [],
                    "accessors": [], "bufferViews": []}
        if self.samplers:
            document["samplers"] = self.samplers
            document["textures"] = [{"sampler": 0, "source": 0}]
        out = bytearray()

        def add_view(payload: bytes, target: int | None = None) -> int:
            while len(out) % 4:
                out.append(0)
            view = {"buffer": 0, "byteOffset": len(out), "byteLength": len(payload)}
            if target:
                view["target"] = target
            out.extend(payload)
            document["bufferViews"].append(view)
            return len(document["bufferViews"]) - 1

        def add_accessor(values: np.ndarray, component: int, kind: str, target: int, bounds: bool = False) -> int:
            accessor = {"bufferView": add_view(values.tobytes(), target), "componentType": component,
                        "count": int(values.shape[0]), "type": kind}
            if bounds:
                accessor["min"] = [float(v) for v in values.min(axis=0)]
                accessor["max"] = [float(v) for v in values.max(axis=0)]
            document["accessors"].append(accessor)
            return len(document["accessors"]) - 1

        groups = [(self.name, ~self.walk_faces)]
        if self.walk_faces.any():
            groups.append((self.walk_name, self.walk_faces))
        for number, (group_name, mask) in enumerate(groups):
            # the root mesh's glowing faces are a second primitive drawn with the emissive material
            parts = [(mask & ~self.glow_faces, 0), (mask & self.glow_faces, 1)] if number == 0 and glowing \
                else [(mask, 0)]
            primitives = []
            for part, material in parts:
                faces = self.idx[part]
                used, inverse = np.unique(faces.ravel(), return_inverse=True)
                attributes = {
                    "POSITION": add_accessor(self.pos[used].astype("<f4"), 5126, "VEC3", 34962, True),
                    "NORMAL": add_accessor(self.nrm[used].astype("<f4"), 5126, "VEC3", 34962),
                    "TEXCOORD_0": add_accessor(self.uv[used].astype("<f4"), 5126, "VEC2", 34962)}
                indices = add_accessor(inverse.reshape(-1).astype("<u4"), 5125, "SCALAR", 34963)
                primitives.append({"attributes": attributes, "indices": indices, "material": material})
            document["meshes"].append({"name": group_name, "primitives": primitives})
            document["nodes"].append({"name": group_name, "mesh": number})
        if len(groups) > 1:
            document["nodes"][0]["children"] = list(range(1, len(groups)))
        if self.extras:
            document["nodes"][0]["extras"] = {"eloria": self.extras}
        if self.image_changed:
            buffer = io.BytesIO()
            Image.fromarray(self.image).save(buffer, "JPEG", quality=quality, optimize=True)
            payload, mime = buffer.getvalue(), "image/jpeg"
        else:
            payload, mime = self.image_bytes, self.mime
        document["images"].append({"bufferView": add_view(payload), "mimeType": mime, "name": self.name})
        if glowing and self.glow_material.get("extensions"):
            document["extensionsUsed"] = sorted(self.glow_material["extensions"])
        while len(out) % 4:
            out.append(0)
        document["buffers"] = [{"byteLength": len(out)}]
        encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
        encoded += b" " * (-len(encoded) % 4)
        total = 12 + 8 + len(encoded) + 8 + len(out)
        return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                + struct.pack("<II", len(out), 0x004E4942) + bytes(out))


# --------------------------------------------------------------------------- colour helpers

def rgb_to_hsl(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """rgb in 0-1 (..., 3) -> H in degrees, S and L in 0-1."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    high = rgb.max(axis=-1)
    low = rgb.min(axis=-1)
    lightness = (high + low) / 2
    delta = high - low
    saturation = np.where(delta == 0, 0.0, delta / np.maximum(1e-9, 1 - np.abs(2 * lightness - 1)))
    hue = np.zeros_like(lightness)
    safe = np.maximum(delta, 1e-12)
    red = (high == r) & (delta > 0)
    green = (high == g) & (delta > 0) & ~red
    blue = (delta > 0) & ~red & ~green
    hue = np.where(red, ((g - b) / safe) % 6, hue)
    hue = np.where(green, (b - r) / safe + 2, hue)
    hue = np.where(blue, (r - g) / safe + 4, hue)
    return hue * 60.0, np.clip(saturation, 0, 1), lightness


def hsl_to_rgb(hue: np.ndarray, saturation: np.ndarray, lightness: np.ndarray) -> np.ndarray:
    chroma = (1 - np.abs(2 * lightness - 1)) * saturation
    h = (hue % 360) / 60.0
    x = chroma * (1 - np.abs(h % 2 - 1))
    zeros = np.zeros_like(h)
    sector = np.floor(h).astype(int) % 6
    r = np.choose(sector, [chroma, x, zeros, zeros, x, chroma])
    g = np.choose(sector, [x, chroma, chroma, x, zeros, zeros])
    b = np.choose(sector, [zeros, zeros, x, chroma, chroma, x])
    m = lightness - chroma / 2
    return np.clip(np.stack([r + m, g + m, b + m], axis=-1), 0, 1)


def hue_in(hue: np.ndarray, low: float, high: float) -> np.ndarray:
    hue = hue % 360
    return (hue >= low) & (hue <= high) if low <= high else (hue >= low) | (hue <= high)


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


# --------------------------------------------------------------------------- texture operations

def zone_mask(kit: Kit, faces: np.ndarray, value: np.ndarray | None = None) -> np.ndarray:
    """Boolean texel mask of the faces' UV triangles (edges included), or with `value` (0-1 per face) a
    float map holding each face's value (NaN outside)."""
    height, width = kit.image.shape[:2]
    canvas = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(canvas)
    uv = kit.uv_px()
    order = np.where(faces)[0]
    if value is None:
        for face in order:
            points = [tuple(p) for p in uv[face]]
            draw.polygon(points, fill=255, outline=255)
        return np.array(canvas) > 0
    coverage = Image.new("L", (width, height), 0)
    cover = ImageDraw.Draw(coverage)
    for face in order:
        points = [tuple(p) for p in uv[face]]
        level = int(round(np.clip(value[face], 0, 1) * 254)) + 1
        draw.polygon(points, fill=level, outline=level)
        cover.polygon(points, fill=255, outline=255)
    result = (np.array(canvas).astype(np.float64) - 1) / 254.0
    result[np.array(coverage) == 0] = np.nan
    return result


def texel_positions(kit: Kit, faces: np.ndarray) -> np.ndarray:
    """(H, W, 3): the model-space point each texel of the chosen faces paints (NaN elsewhere), so a defect
    can be picked by where it is on the model as well as by its colour."""
    height, width = kit.image.shape[:2]
    out = np.full((height, width, 3), np.nan)
    uv = kit.uv_px()
    tri = kit.tri()
    for face in np.where(faces)[0]:
        x, y = uv[face, :, 0], uv[face, :, 1]
        x0, x1 = max(int(np.floor(x.min())), 0), min(int(np.ceil(x.max())), width - 1)
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), height - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        det = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(det) < 1e-12:
            continue
        a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / det
        b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / det
        c = 1 - a - b
        inside = (a >= -0.02) & (b >= -0.02) & (c >= -0.02)
        point = a[..., None] * tri[face, 0] + b[..., None] * tri[face, 1] + c[..., None] * tri[face, 2]
        out[y0:y1 + 1, x0:x1 + 1][inside] = point[inside]
    return out


def in_box(points: np.ndarray, low: tuple, high: tuple) -> np.ndarray:
    """Texels whose model-space point lies in the box (NaN points never do)."""
    with np.errstate(invalid="ignore"):
        return np.all((points >= np.array(low)) & (points <= np.array(high)), axis=-1)


def pixels(kit: Kit) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rgb = kit.image / 255.0
    hue, saturation, lightness = rgb_to_hsl(rgb)
    return rgb, hue, saturation, lightness


def _blend(kit: Kit, new_rgb: np.ndarray, select: np.ndarray, zone: np.ndarray) -> int:
    """Writes new_rgb where `select` is (grown one texel inside the zone, edges feathered)."""
    grown = binary_dilation(select, iterations=1) & zone
    alpha = np.clip(gaussian_filter(grown.astype(np.float64), 0.7) * 1.6, 0, 1) * grown
    old = kit.image / 255.0
    mixed = old * (1 - alpha[..., None]) + new_rgb * alpha[..., None]
    kit.image = np.clip(np.round(mixed * 255), 0, 255).astype(np.uint8)
    kit.image_changed = True
    return int(grown.sum())


def recolour(kit: Kit, zone: np.ndarray, select: np.ndarray, target: np.ndarray,
             clamp: tuple[float, float] = (0.8, 1.2)) -> int:
    """Moves the selected texels to `target` (rgb 0-1), keeping their relative lightness (clamped)."""
    if not select.any():
        return 0
    rgb = kit.image / 255.0
    lum = luma(rgb)
    reference = float(np.median(lum[select]))
    ratio = np.clip(lum / max(reference, 1e-6), *clamp)
    new = np.clip(target[None, None, :] * ratio[..., None], 0, 1)
    return _blend(kit, new, select, zone)


def inpaint(kit: Kit, zone: np.ndarray, select: np.ndarray, radius: int = 5) -> int:
    """Refills the selected texels from the good texels of the same zone (Telea inpainting). Texels outside
    the zone are replaced by the zone's median first, so nothing bleeds in from neighbouring UV islands."""
    if not select.any():
        return 0
    work = kit.image.copy()
    good = zone & ~select
    median = np.median(kit.image[good], axis=0) if good.any() else np.median(kit.image[zone], axis=0)
    work[~zone] = median.astype(np.uint8)
    hole = (binary_dilation(select, iterations=1) & zone).astype(np.uint8) * 255
    filled = cv2.inpaint(cv2.cvtColor(work, cv2.COLOR_RGB2BGR), hole, radius, cv2.INPAINT_TELEA)
    filled = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB) / 255.0
    return _blend(kit, filled, select, zone)


def hsl_shift(kit: Kit, select: np.ndarray, hue_to: float | None = None, saturation_to: float | None = None,
              lightness_to: float | None = None, lightness_add: float = 0.0) -> dict:
    """Pulls the selected texels' median H/S/L to the targets (H shifted, S and L scaled)."""
    rgb, hue, saturation, lightness = pixels(kit)
    if not select.any():
        return {"texels": 0}
    before = [float(np.median(hue[select])), float(np.median(saturation[select])),
              float(np.median(lightness[select]))]
    new_h, new_s, new_l = hue.copy(), saturation.copy(), lightness.copy()
    if hue_to is not None:
        new_h = np.where(select, hue + (hue_to - before[0]), hue)
    if saturation_to is not None:
        new_s = np.where(select, np.clip(saturation * saturation_to / max(before[1], 1e-6), 0, 1), saturation)
    if lightness_to is not None:
        new_l = np.where(select, np.clip(lightness * lightness_to / max(before[2], 1e-6), 0, 1), lightness)
    new_l = np.where(select, np.clip(new_l + lightness_add, 0, 1), new_l)
    new = hsl_to_rgb(new_h, new_s, new_l)
    zone = np.ones(select.shape, bool)
    count = _blend(kit, new, select, zone)
    after_h, after_s, after_l = rgb_to_hsl(kit.image / 255.0)
    return {"texels": count, "before_hsl": [round(v, 3) for v in before],
            "after_hsl": [round(float(np.median(a[select])), 3) for a in (after_h, after_s, after_l)]}


def crown_tint(kit: Kit, faces: np.ndarray, value: np.ndarray, lightness_low: float, lightness_high: float,
               hue_top: float = 0.0, saturation_top: float = 0.0, extra_dark: np.ndarray | None = None) -> dict:
    """Top-light by height within the crown: each foliage face's texels get L x (low..high) by its height t
    (0 at the crown's underside, 1 at its top), a hue shift of hue_top x t and S + saturation_top x t.
    extra_dark (0-1 per face) multiplies L further (crevice darkening)."""
    t_map = zone_mask(kit, faces, value)
    covered = ~np.isnan(t_map)
    t = np.nan_to_num(t_map)
    dark = np.ones_like(t)
    if extra_dark is not None:
        dark_map = zone_mask(kit, faces, extra_dark)
        dark = np.where(np.isnan(dark_map), 1.0, 1.0 - np.nan_to_num(dark_map))
    rgb, hue, saturation, lightness = pixels(kit)
    before = float(np.median(lightness[covered]))
    factor = (lightness_low + (lightness_high - lightness_low) * t) * dark
    new = hsl_to_rgb(np.where(covered, hue + hue_top * t, hue),
                     np.where(covered, np.clip(saturation + saturation_top * t, 0, 1), saturation),
                     np.where(covered, np.clip(lightness * factor, 0, 1), lightness))
    kit.image = np.where(covered[..., None], np.round(new * 255), kit.image).astype(np.uint8)
    kit.image_changed = True
    after = float(np.median(rgb_to_hsl(kit.image / 255.0)[2][covered]))
    return {"texels": int(covered.sum()), "crown_L_before": round(before, 3), "crown_L_after": round(after, 3)}


# --------------------------------------------------------------------------- geometry operations

def welded_islands(kit: Kit, tolerance: float = 1e-4) -> tuple[int, np.ndarray]:
    keys = np.round(kit.pos / tolerance).astype(np.int64)
    _, weld = np.unique(keys, axis=0, return_inverse=True)
    weld = weld.reshape(-1)
    faces = weld[kit.idx]
    count = len(faces)
    rows = np.repeat(np.arange(count), 3)
    graph = coo_matrix((np.ones(count * 3), (rows, faces.ravel())), shape=(count, weld.max() + 1)).tocsr()
    adjacency = graph @ graph.T
    return connected_components(adjacency, directed=False)


def snap_island(kit: Kit, faces: int, area: float, near: tuple[float, float, float] | None = None,
                leave: float = 0.004) -> dict:
    """Moves the floating island with this face count and area (closest to `near`) onto the rest of the mesh
    along its shortest gap, leaving `leave` metres."""
    count, label = welded_islands(kit)
    _, areas = kit.face_normals()
    centroids = kit.centroids()
    best, best_score = None, np.inf
    for island in range(count):
        members = label == island
        if members.sum() != faces:
            continue
        score = abs(areas[members].sum() - area)
        if near is not None:
            score += np.linalg.norm(centroids[members].mean(axis=0) - np.array(near))
        if score < best_score:
            best, best_score = island, score
    if best is None:
        raise ValueError(f"no island with {faces} faces")
    members = label == best
    rest = trimesh.Trimesh(kit.pos, kit.idx[~members], process=False)
    vertices = np.unique(kit.idx[members])
    closest, distance, _ = trimesh.proximity.closest_point(rest, kit.pos[vertices])
    nearest = int(np.argmin(distance))
    gap = float(distance[nearest])
    direction = (closest[nearest] - kit.pos[vertices[nearest]]) / max(gap, 1e-9)
    move = direction * max(gap - leave, 0.0)
    kit.pos[vertices] += move
    return {"island_faces": int(members.sum()), "island_area_m2": round(float(areas[members].sum()), 3),
            "gap_m": round(gap, 4), "moved_m": [round(float(v), 4) for v in move]}


def delete_duplicate_faces(kit: Kit) -> dict:
    """Deletes one face of every coincident pair (same three corners), keeping the twin whose texel is
    closest to the median texel of the faces that share its corners."""
    corners = np.round(kit.tri() / 1e-5).astype(np.int64).reshape(-1, 3)
    _, corner_id = np.unique(corners, axis=0, return_inverse=True)
    face_key = np.sort(corner_id.reshape(-1, 3), axis=1)
    _, inverse, counts = np.unique(face_key, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    if counts.max() < 2:
        return {"pairs": 0, "deleted": 0, "area_m2": 0.0}
    _, areas = kit.face_normals()
    colour = kit.texel_at_centroid()
    welded = np.unique(np.round(kit.pos / 1e-4).astype(np.int64), axis=0, return_inverse=True)[1].reshape(-1)
    corner = welded[kit.idx]
    by_vertex: dict[int, list[int]] = {}
    for face, corners in enumerate(corner):
        for v in corners:
            by_vertex.setdefault(int(v), []).append(face)
    drop = np.zeros(len(kit.idx), bool)
    pairs, area = 0, 0.0
    for group in np.where(counts > 1)[0]:
        twins = np.where(inverse == group)[0]
        pairs += 1
        neighbours = {f for v in corner[twins[0]] for f in by_vertex[int(v)]} - set(twins.tolist())
        reference = np.median(colour[list(neighbours)], axis=0) if neighbours else colour[twins].mean(axis=0)
        keep = twins[np.argmin(np.abs(colour[twins] - reference).sum(axis=1))]
        for face in twins:
            if face != keep:
                drop[face] = True
                area += float(areas[face])
    kit.keep_faces(~drop)
    return {"pairs": pairs, "deleted": int(drop.sum()), "area_m2": round(area, 2)}


def clip_x(kit: Kit, limit: float) -> dict:
    """Cuts the mesh at x = +-limit, keeping |x| <= limit (no caps): faces crossing a plane are clipped and
    their corners' normals and UVs interpolated."""
    removed = clipped = 0
    for sign in (1.0, -1.0):
        tri = kit.tri()
        side = sign * tri[..., 0] - limit          # > 0 is outside
        outside = side > 1e-9
        all_out = outside.all(axis=1)
        crossing = outside.any(axis=1) & ~all_out
        new_p, new_n, new_t = [], [], []
        for face in np.where(crossing)[0]:
            corners = kit.idx[face]
            polygon = []
            for k in range(3):
                a, b = corners[k], corners[(k + 1) % 3]
                da, db = side[face, k], side[face, (k + 1) % 3]
                if da <= 1e-9:
                    polygon.append((kit.pos[a], kit.nrm[a], kit.uv[a]))
                if (da <= 1e-9) != (db <= 1e-9):
                    s = da / (da - db)
                    normal = kit.nrm[a] + s * (kit.nrm[b] - kit.nrm[a])
                    polygon.append((kit.pos[a] + s * (kit.pos[b] - kit.pos[a]),
                                    normal / max(np.linalg.norm(normal), 1e-12),
                                    kit.uv[a] + s * (kit.uv[b] - kit.uv[a])))
            for k in range(1, len(polygon) - 1):
                for corner in (polygon[0], polygon[k], polygon[k + 1]):
                    new_p.append(corner[0]); new_n.append(corner[1]); new_t.append(corner[2])
        kit.keep_faces(~(all_out | crossing))
        removed += int(all_out.sum())
        clipped += int(crossing.sum())
        if new_p:
            kit.add_faces(np.array(new_p), np.array(new_n), np.array(new_t))
    return {"limit_m": limit, "faces_removed": removed, "faces_clipped": clipped}


def stretch_below(kit: Kit, threshold: float, new_bottom: float) -> dict:
    """Stretches every vertex below `threshold` so the lowest one lands on `new_bottom` (normals follow)."""
    bottom = float(kit.pos[:, 1].min())
    factor = (threshold - new_bottom) / (threshold - bottom)
    below = kit.pos[:, 1] < threshold
    kit.pos[below, 1] = threshold + (kit.pos[below, 1] - threshold) * factor
    normals = kit.nrm[below].copy()
    normals[:, 1] /= factor
    kit.nrm[below] = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    return {"threshold_m": threshold, "bottom_before_m": round(bottom, 3), "bottom_after_m": new_bottom,
            "factor": round(factor, 3), "vertices": int(below.sum())}


def mark_walk(kit: Kit, faces: np.ndarray, node_name: str) -> dict:
    kit.walk_faces = faces.copy()
    kit.walk_name = node_name
    _, areas = kit.face_normals()
    tri = kit.tri()[faces]
    return {"node": node_name, "faces": int(faces.sum()), "area_m2": round(float(areas[faces].sum()), 2),
            "top_y_m": [round(float(tri[..., 1].min()), 3), round(float(tri[..., 1].max()), 3)]}


def deck_continuity(kit: Kit, walk_half_width: float, top: float = 0.0, band: float = 0.05) -> dict:
    """Downward rays within `band` of each cut end, across the walk band: the share that meets the deck
    top (within 5 cm of `top`). The review's check for N12's joint slit."""
    mesh = trimesh.Trimesh(kit.pos, kit.idx, process=False)
    low, high = kit.pos[:, 0].min(), kit.pos[:, 0].max()
    result = {}
    for label, x in (("minus_x", low + band / 2), ("plus_x", high - band / 2)):
        zs = np.arange(-walk_half_width + 0.1, walk_half_width - 0.1, 0.1)
        origins = np.stack([np.full(zs.size, x), np.full(zs.size, top + 5.0), zs], axis=1)
        locations, rays, _ = mesh.ray.intersects_location(origins, np.tile([0, -1.0, 0], (zs.size, 1)),
                                                           multiple_hits=False)
        hit = np.zeros(zs.size, bool)
        hit[rays[np.abs(locations[:, 1] - top) < 0.05]] = True
        result[label] = round(float(hit.mean()), 3)
    return result


# --------------------------------------------------------------------------- per-piece fixes

def _faces_by_colour(kit: Kit, test) -> np.ndarray:
    hue, saturation, lightness = rgb_to_hsl(kit.texel_at_centroid())
    return test(hue, saturation, lightness)


def fix_keep(kit: Kit, log: dict) -> None:            # N1
    log["snap_gable_trim"] = snap_island(kit, 10, 0.4132, near=(-0.91, 11.11, 11.83))
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    rgb, hue, saturation, lightness = pixels(kit)
    cobalt_faces = _faces_by_colour(kit, lambda h, s, l: hue_in(h, 200, 240) & (s > 0.35))
    roof = zone_mask(kit, cobalt_faces)
    cobalt = roof & hue_in(hue, 200, 240) & (saturation > 0.35)
    pale = roof & (saturation < 0.3) & (lightness > 0.5)
    log["roof_pale_to_cobalt_texels"] = recolour(kit, roof, pale, np.median(rgb[cobalt], axis=0))
    rgb, hue, saturation, lightness = pixels(kit)
    stone_faces = (np.abs(normals[:, 1]) < 0.6) & ~cobalt_faces & _faces_by_colour(
        kit, lambda h, s, l: (l > 0.45) & ~hue_in(h, 180, 260))
    walls = zone_mask(kit, stone_faces)
    gold = hue_in(hue, 30, 56) & (saturation >= 0.45)
    defect = walls & ~gold & (((saturation < 0.13) & (lightness > 0.45)) |
                              (hue_in(hue, 180, 260) & (saturation < 0.45) & (lightness > 0.5)))
    log["walls_pale_grey_inpainted_texels"] = inpaint(kit, walls, defect)
    log["wall_faces"] = int(stone_faces.sum())


def fix_curtain_wall(kit: Kit, log: dict) -> None:     # N3
    # The field-face (+Z) slit's bottom ends in a melted V (x -0.66..-0.18, y 2.62..2.86): its corners are
    # pushed flush with the face plane fitted to the outer face, and the flattened faces repainted stone.
    normals, _ = kit.face_normals()
    centroids = kit.centroids()
    front = (normals[:, 2] > 0.6) & (centroids[:, 2] > 0.9) & (centroids[:, 1] > 1.2) & (centroids[:, 1] < 5.0)
    front_vertices = np.unique(kit.idx[front])
    y, z = kit.pos[front_vertices, 1], kit.pos[front_vertices, 2]
    slope, offset = np.polyfit(y, z, 1)
    plane = slope * kit.pos[:, 1] + offset
    region = ((kit.pos[:, 0] > -0.70) & (kit.pos[:, 0] < -0.14) & (kit.pos[:, 1] > 2.55) &
              (kit.pos[:, 1] < 2.86) & (kit.pos[:, 2] > 0.6) & (plane - kit.pos[:, 2] > 0.02))
    before = kit.pos[region, 2].copy()
    kit.pos[region, 2] = plane[region]
    moved = np.isin(kit.idx, np.where(region)[0]).any(axis=1)
    rgb, hue, saturation, lightness = pixels(kit)
    face_zone = zone_mask(kit, front & ~moved)
    stone = np.median(rgb[face_zone & (lightness > 0.6)], axis=0)
    notch = zone_mask(kit, moved)
    log["slit_notch"] = {"vertices_flattened": int(region.sum()),
                         "max_push_m": round(float((plane[region] - before).max()), 3) if region.any() else 0,
                         "faces_repainted": int(moved.sum()),
                         "texels": recolour(kit, notch, notch, stone, clamp=(0.92, 1.06))}


def fix_bastion(kit: Kit, log: dict) -> None:          # N4
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    rgb, hue, saturation, lightness = pixels(kit)
    gold_faces = _faces_by_colour(kit, lambda h, s, l: hue_in(h, 30, 56) & (s >= 0.45))
    # the bartizan cone: upward-sloping faces above its eave on the field (+Z) side
    cone_faces = (centroids[:, 1] > 8.4) & (centroids[:, 1] < 11.4) & (centroids[:, 2] > 2.0) & \
        (normals[:, 1] > 0.2) & (normals[:, 1] < 0.97) & ~gold_faces
    log["cone_faces"] = int(cone_faces.sum())
    cone = zone_mask(kit, cone_faces)
    gold = hue_in(hue, 30, 56) & (saturation >= 0.45)
    cobalt = cone & hue_in(hue, 200, 240) & (saturation > 0.4)
    pale = cone & ~gold & ~cobalt & (lightness > 0.42)
    log["cone_share_pale_before"] = round(float(pale.sum() / max(cone.sum(), 1)), 3)
    log["cone_pale_to_cobalt_texels"] = recolour(kit, cone, pale, np.median(rgb[cobalt], axis=0))
    rgb, hue, saturation, lightness = pixels(kit)
    gold = hue_in(hue, 30, 56) & (saturation >= 0.45) & (lightness > 0.15) & (lightness < 0.7)
    log["gold_lightness_lift"] = hsl_shift(kit, gold, lightness_add=0.04)


def fix_temple(kit: Kit, log: dict) -> None:           # N6
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    rgb, hue, saturation, lightness = pixels(kit)
    hall = (centroids[:, 1] > 0.6) & (centroids[:, 1] < 7.4)
    back = zone_mask(kit, hall & (normals[:, 2] < -0.6))
    marks = back & ((hue_in(hue, 180, 270) & (saturation > 0.03)) | ((saturation < 0.1) & (lightness > 0.4)) |
                    ((saturation < 0.16) & (lightness > 0.62)))
    log["back_wall_marks_inpainted_texels"] = inpaint(kit, back, marks)
    rgb, hue, saturation, lightness = pixels(kit)
    right = zone_mask(kit, hall & (normals[:, 0] > 0.6))
    streak = right & (saturation < 0.16) & (lightness > 0.62)
    log["right_wall_streak_inpainted_texels"] = inpaint(kit, right, streak)
    # the left-side window (x -5.8, z -1.85..-0.75, y 3.2..4.8) is filled with pale grey-blue: paint it the
    # blue of the right-side window
    rgb, hue, saturation, lightness = pixels(kit)
    sides = (np.abs(centroids[:, 0]) > 4.5) & (centroids[:, 1] > 1.5) & (centroids[:, 1] < 5.5) & \
        (np.abs(normals[:, 1]) < 0.6)
    where = texel_positions(kit, sides)
    window_blue = in_box(where, (4.5, 2.0, -3.0), (7.0, 5.5, 3.0)) & hue_in(hue, 200, 240) & (saturation > 0.3)
    left_window = in_box(where, (-7.0, 3.1, -1.95), (-4.5, 4.9, -0.65))
    fill = left_window & hue_in(hue, 180, 260) & (lightness > 0.5)
    log["left_window_fill_to_window_blue_texels"] = recolour(
        kit, left_window | fill, fill,
        np.median(rgb[window_blue], axis=0) if window_blue.any() else np.array([0.15, 0.3, 0.7]))
    # the wedge where the drum meets the portico roof (front right): a coincident pair of 11 m2 triangles
    # (faces 39 and 6501, one is deleted with the duplicates) painted pale grey-blue: darken it to the
    # roof's shaded cobalt; pale texels on the two roof faces under it go to the roof cobalt
    rgb, hue, saturation, lightness = pixels(kit)
    wedge_faces = np.zeros(len(kit.idx), bool)
    wedge_faces[[39, 6501]] = True
    roof_faces = np.zeros(len(kit.idx), bool)
    roof_faces[[4684, 6295]] = True
    roof = zone_mask(kit, roof_faces)
    roof_cobalt = roof & hue_in(hue, 200, 240) & (saturation > 0.4)
    cobalt = np.median(rgb[roof_cobalt], axis=0) if roof_cobalt.any() else np.array([0.16, 0.33, 0.66])
    wedge = zone_mask(kit, wedge_faces)
    log["drum_roof_wedge"] = {"faces": [39, 6501], "centroid_m": [round(float(v), 2) for v in centroids[39]],
                              "texels": recolour(kit, wedge, wedge, cobalt * 0.7, clamp=(0.85, 1.1))}
    rgb, hue, saturation, lightness = pixels(kit)
    pale = roof & ~wedge & hue_in(hue, 180, 260) & (saturation < 0.45) & (lightness > 0.55)
    log["portico_roof_pale_to_cobalt_texels"] = recolour(kit, roof, pale, cobalt)


def fix_townhouse_blue(kit: Kit, log: dict) -> None:   # N7
    # the pale diagonal mark across the lower door leaf (leaf x -0.52..0.74, the mark below 1.3 m)
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    front = (normals[:, 2] > 0.6) & (np.abs(centroids[:, 0]) < 1.2) & (centroids[:, 1] < 3.0)
    where = texel_positions(kit, front)
    rgb, hue, saturation, lightness = pixels(kit)
    leaf = in_box(where, (-0.52, 0.26, 0.0), (0.74, 2.0, 10.0))
    # the mark is a check-shaped stroke: (-0.12, 0.62) -> (0.06, 0.36) -> (0.70, 1.22) on the leaf
    near = np.full(leaf.shape, np.inf)
    xy = where[..., :2]
    for start, end in (((-0.12, 0.62), (0.06, 0.36)), ((0.06, 0.36), (0.70, 1.22))):
        a, b = np.array(start), np.array(end)
        t = np.clip(((xy - a) @ (b - a)) / ((b - a) @ (b - a)), 0, 1)
        with np.errstate(invalid="ignore"):
            near = np.fmin(near, np.linalg.norm(xy - (a + t[..., None] * (b - a)), axis=-1))
    with np.errstate(invalid="ignore"):
        mark = leaf & (((near < 0.11) & (lightness > 0.29)) | (in_box(where, (-0.52, 0.26, 0.0), (0.74, 1.3, 10.0))
                                                               & (lightness > 0.40)))
    log["door_mark_inpainted_texels"] = inpaint(kit, leaf, mark)
    # most of the mark is face 3134, a sliver folded 8 deg out of the leaf from (-0.32, 0.13) to (0.70, 1.24)
    # whose texels are pale: paint the whole face the leaf's wood
    rgb, hue, saturation, lightness = pixels(kit)
    wood = leaf & hue_in(hue, 8, 45) & (saturation > 0.3) & (lightness < 0.4)
    sliver_faces = np.zeros(len(kit.idx), bool)
    sliver_faces[3134] = True
    sliver = zone_mask(kit, sliver_faces)
    log["door_sliver_face_3134_texels"] = recolour(kit, sliver, sliver, np.median(rgb[wood], axis=0),
                                                   clamp=(0.85, 1.15))


def fix_townhouse_dome(kit: Kit, log: dict) -> None:   # N8
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    stone_faces = _faces_by_colour(kit, lambda h, s, l: hue_in(h, 18, 55) & (l > 0.6))
    # the blue brush streak on the back (-Z) wall between the first two ground-floor window heads
    # (x -2.05..-0.85, y 2.1..2.45); the painted shutters beside it are left alone
    where = texel_positions(kit, normals[:, 2] < -0.6)
    rgb, hue, saturation, lightness = pixels(kit)
    blue = hue_in(hue, 180, 260) & (saturation > 0.15)
    streak = in_box(where, (-2.05, 2.1, -10.0), (-0.85, 2.45, 0.0)) & blue
    back = in_box(where, (-4.4, 1.6, -10.0), (4.4, 3.2, 0.0)) & (~blue | streak)
    log["back_blue_streak_inpainted_texels"] = inpaint(kit, back, streak)
    quoin = zone_mask(kit, stone_faces & (centroids[:, 0] < -3.4) & (centroids[:, 1] < 1.6) & (centroids[:, 2] > 2.0))
    rgb, hue, saturation, lightness = pixels(kit)
    sliver = quoin & (lightness > 0.9) & (saturation < 0.3)
    log["front_left_quoin_sliver_inpainted_texels"] = inpaint(kit, quoin, sliver)


def fix_lighthouse_red(kit: Kit, log: dict) -> None:   # N9
    needles = [899, 5315, 5826, 6913]
    tri = kit.tri()[needles]
    log["needles"] = [{"face": f, "y_m": [round(float(t[:, 1].min()), 2), round(float(t[:, 1].max()), 2)]}
                      for f, t in zip(needles, tri)]
    keep = np.ones(len(kit.idx), bool)
    keep[needles] = False
    kit.keep_faces(keep)


def fix_lighthouse_green(kit: Kit, log: dict) -> None:  # N10
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    radius = np.hypot(centroids[:, 0], centroids[:, 2])
    shaft_faces = (radius < 4.6) & (centroids[:, 1] > 3.6) & (centroids[:, 1] < 12.4) & (np.abs(normals[:, 1]) < 0.5)
    shaft = zone_mask(kit, shaft_faces)
    where = texel_positions(kit, shaft_faces)
    azimuth = np.degrees(np.arctan2(where[..., 0], where[..., 2]))
    rgb, hue, saturation, lightness = pixels(kit)
    # the deleted spiral band left a greyer (S < 0.3) diagonal across the shaft between 7.6 and 10.3 m;
    # the shaft window at azimuth -25 deg (y 9.3-9.9) is kept
    with np.errstate(invalid="ignore"):
        band = in_box(where, (-10, 7.6, -10), (10, 10.3, 10)) & ~((azimuth > -40) & (azimuth < -10) & (where[..., 1] > 9.1))
    stripe = shaft & band & (saturation < 0.3) & hue_in(hue, 0, 80)
    log["shaft_stripe_share"] = round(float(stripe.sum() / max(shaft.sum(), 1)), 3)
    log["shaft_stripe_inpainted_texels"] = inpaint(kit, shaft, stripe)
    # widen the +-X kerb openings from 4.6 m to about 8.4 m: delete the kerb posts and blocks within
    # |z| < 4.2 at the rim; the paving runs on under them at +2.96 m (probed below)
    kerb = (centroids[:, 1] > 3.02) & (centroids[:, 1] < 4.4) & (np.abs(centroids[:, 2]) < 4.2) & \
        (np.abs(centroids[:, 0]) > 9.3)
    log["kerb_faces_deleted"] = int(kerb.sum())
    kit.keep_faces(~kerb)
    mesh = trimesh.Trimesh(kit.pos, kit.idx, process=False)
    probes = np.array([[sign * x, 8.0, z] for sign in (1.0, -1.0) for x in np.arange(9.4, 11.81, 0.2)
                       for z in np.arange(-4.0, 4.01, 0.2) if np.hypot(x, z) <= 11.3])
    locations, rays, _ = mesh.ray.intersects_location(probes, np.tile([0, -1.0, 0], (len(probes), 1)),
                                                       multiple_hits=False)
    top = np.full(len(probes), np.nan)
    top[rays] = locations[:, 1]
    log["kerb_opening_floor_y_m"] = {"probes": len(probes), "min": round(float(np.nanmin(top)), 3),
                                     "max": round(float(np.nanmax(top)), 3),
                                     "off_paving": int(((top < 2.75) | (top > 3.05) | np.isnan(top)).sum())}
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    walk = (normals[:, 1] > 0.9) & (centroids[:, 1] < 3.12) & (np.hypot(centroids[:, 0], centroids[:, 2]) < 12.3)
    log["walk"] = mark_walk(kit, walk, "Walk_sw-lighthouse-green-platform")


def fix_arch_span(kit: Kit, log: dict) -> None:        # N12
    log["clip"] = clip_x(kit, 5.55)
    factor = 12.0 / (2 * 5.55)
    kit.pos *= factor
    log["uniform_scale"] = round(factor, 4)
    log["stretch"] = stretch_below(kit, -3.0, -8.0)
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    walk = (normals[:, 1] > 0.9) & (np.abs(centroids[:, 1]) < 0.08) & (np.abs(centroids[:, 2]) <= 5.05)
    log["walk"] = mark_walk(kit, walk, "Walk_sw-causeway-arch-span-deck")
    log["deck_continuity"] = deck_continuity(kit, 5.0)


def fix_gatehouse(kit: Kit, log: dict) -> None:        # N5
    # The passage is paved with a slab 0.08-0.17 m above the base. Left solid, its top and edges lie inside
    # the served actor volume (standing + 0.06 m) and close the whole 5 m passage (found by the castle-town
    # build's served reach, slice 2). As a walk surface the paving is what an actor stands on in the gate.
    centroids = kit.centroids()
    tri = kit.tri()
    paving = (tri[..., 1].max(axis=1) < 0.25) & (np.abs(centroids[:, 0]) < 3.4)
    log["walk"] = mark_walk(kit, paving, "Walk_sw-gatehouse-passage")


def fix_trestle(kit: Kit, log: dict) -> None:          # N13
    log["snap_floating_part"] = snap_island(kit, 46, 17.323)
    log["stretch"] = stretch_below(kit, -2.5, -6.0)
    centroids = kit.centroids()
    normals, _ = kit.face_normals()
    walk = (normals[:, 1] > 0.9) & (np.abs(centroids[:, 1]) < 0.12) & (np.abs(centroids[:, 2]) <= 5.25)
    log["walk"] = mark_walk(kit, walk, "Walk_sw-trestle-pier-span-deck")
    log["deck_continuity"] = deck_continuity(kit, 4.8)


def _crown(kit: Kit, foliage: np.ndarray) -> np.ndarray:
    centroids = kit.centroids()
    low, high = np.percentile(centroids[foliage, 1], [2, 98])
    return np.clip((centroids[:, 1] - low) / max(high - low, 1e-6), 0, 1)


def fix_tree_a(kit: Kit, log: dict) -> None:           # N15
    foliage = _faces_by_colour(kit, lambda h, s, l: hue_in(h, 55, 150) & (s > 0.15))
    log["foliage_faces"] = int(foliage.sum())
    log["top_light"] = crown_tint(kit, foliage, _crown(kit, foliage), 0.92, 1.32, hue_top=-8.0, saturation_top=0.04)


def fix_tree_b(kit: Kit, log: dict) -> None:           # N16
    foliage = _faces_by_colour(kit, lambda h, s, l: hue_in(h, 55, 150) & (s > 0.15))
    bark = ~foliage
    rgb, hue, saturation, lightness = pixels(kit)
    bark_zone = zone_mask(kit, bark) & ~(hue_in(hue, 55, 150) & (saturation > 0.2))
    median = np.median(rgb[bark_zone], axis=0)
    target = np.array([150, 140, 125]) / 255.0
    new = np.clip(rgb * (target / np.maximum(median, 1e-6))[None, None, :], 0, 1)
    log["bark"] = {"faces": int(bark.sum()), "median_before": [int(round(v * 255)) for v in median],
                   "texels": _blend(kit, new, bark_zone, bark_zone)}
    rgb, hue, saturation, lightness = pixels(kit)
    leaves = zone_mask(kit, foliage) & hue_in(hue, 50, 150) & (saturation > 0.12)
    log["foliage_pull"] = hsl_shift(kit, leaves, hue_to=84.0, saturation_to=0.50)
    log["top_light"] = crown_tint(kit, foliage, _crown(kit, foliage), 0.92, 1.25, hue_top=-6.0, saturation_top=0.03)


def fix_blossom(kit: Kit, log: dict) -> None:          # N17
    centroids = kit.centroids()
    puffs = _faces_by_colour(kit, lambda h, s, l: (hue_in(h, 330, 22) & (s > 0.3))) & (centroids[:, 1] > 2.0)
    zone = zone_mask(kit, puffs)
    rgb, hue, saturation, lightness = pixels(kit)
    blossom = zone & hue_in(hue, 330, 22) & (saturation > 0.3)
    smudge = zone & hue_in(hue, 20, 80)
    log["smudge_share"] = round(float(smudge.sum() / max(zone.sum(), 1)), 3)
    rose = np.median(rgb[blossom], axis=0) * 0.82
    log["smudges_to_rose_texels"] = recolour(kit, zone, smudge, rose)
    rgb, hue, saturation, lightness = pixels(kit)
    blossom = zone & hue_in(hue, 330, 22) & (saturation > 0.2)
    log["saturation_pull"] = hsl_shift(kit, blossom, saturation_to=0.62)
    # crevice darkening: how far each puff face sits inside the crown's convex hull
    crown_vertices = kit.pos[np.unique(kit.idx[puffs])]
    hull = trimesh.convex.convex_hull(crown_vertices)
    depth = np.zeros(len(kit.idx))
    depth[puffs] = trimesh.proximity.closest_point(hull, centroids[puffs])[1]
    log["crevice_depth_m_p50_p95"] = [round(float(v), 2) for v in np.percentile(depth[puffs], [50, 95])]
    log["gradient"] = crown_tint(kit, puffs, _crown(kit, puffs), 0.86, 1.06,
                                 extra_dark=np.clip(depth / 1.6, 0, 1) * 0.12)


def fix_turf(kit: Kit, log: dict) -> None:             # N18 r1, N19
    rgb, hue, saturation, lightness = pixels(kit)
    turf = hue_in(hue, 50, 140) & (saturation > 0.25) & (lightness > 0.06)
    log["turf_pull"] = hsl_shift(kit, turf, hue_to=85.0, saturation_to=0.50, lightness_to=0.33)
    # Slice-2 visual review: the delivered rock (median rgb 0.576, 0.573, 0.576, L 0.58) read as a pale sugar
    # cube beside the reuse coastal rocks it is placed with (kit-coastal-rock-1/2 median rgb about 0.365, 0.347,
    # 0.306, L 0.33; sea stack L 0.40) and the concept's dark grey cliff columns. Every non-turf texel moves to a
    # warm grey between the two (0.40, 0.38, 0.345), keeping its relative lightness (x0.6-1.5).
    rgb, hue, saturation, lightness = pixels(kit)
    turf = hue_in(hue, 50, 140) & (saturation > 0.25) & (lightness > 0.06)
    rock = ~turf & (lightness > 0.06)
    before = [round(float(v), 3) for v in np.median(rgb[rock], axis=0)]
    texels = recolour(kit, np.ones(rock.shape, bool), rock, np.array([0.40, 0.38, 0.345]), clamp=(0.6, 1.5))
    after = [round(float(v), 3) for v in np.median((kit.image / 255.0)[rock], axis=0)]
    log["rock_tint"] = {"texels": texels, "median_rgb_before": before, "median_rgb_after": after}


# The landing beacon's light (game-look workflow, seat:beacon). Its review passed with fixes: from the -60 deg game
# camera the crystal covers only 0.16 of the crown (limit 0.25; Meshy made it 1.15 m wide, not 1.6), and the review
# named the client fix: light the crystal. Godot 4.7.2's glTF import turns emissiveTexture + emissiveFactor into a
# StandardMaterial3D emission with the MULTIPLY operator on the same texture object as the albedo, and
# KHR_materials_emissive_strength into emission_energy_multiplier (probed on this kit), so the crystal's faces glow
# in their own pale blue at no texture cost; the client's world loader keeps imported materials as they are, and the
# look pass's stand-ins copy the emission (look_fade.gd copy_standard_surface). The review's dusk render clipped the
# crystal to white at x4 and suggested 1.5-2 under the look's 0.9 glow threshold.
BEACON_GLOW_STRENGTH = 1.75
# The glow's tint (emissiveFactor, a multiplier on the texture): at white the crystal rendered almost white in the game
# client (median L0.948, saturation 0.43, game-look review D12), its pale blue lost in the tonemap's shoulder; a blue
# factor keeps red and green down so it reads as a blue light without raising its strength.
BEACON_GLOW_FACTOR = [0.5, 0.78, 1.0]
# A point light at the review's measured light anchor (the area-weighted centre of the exposed crystal, kit space),
# in the crystal's median colour (rgb 160, 210, 252). The client binds a manifest's lighting.markers as OmniLight3D
# (light_marker_binder.gd); the territory publisher turns this record into one marker per placement.
BEACON_LIGHT = {"kind": "beacon", "anchor": [-0.04, 12.33, -0.011], "color": [0.635, 0.833, 1.0],
                "energyHint": 1.5, "rangeHint": 9.0}


def fix_beacon(kit: Kit, log: dict) -> None:          # N20
    """The crystal (the welded islands the review's emission mask covers, at least 90 % of their faces) becomes a
    second primitive with an emissive copy of the material: emissiveTexture = the base colour texture, factor
    BEACON_GLOW_FACTOR (blue),
    KHR_materials_emissive_strength BEACON_GLOW_STRENGTH. The mask (kit-sw-landing-beacon_emission_mask.png, the
    crystal palette AND faces above 60 % of the height, grown 2 px) lies beside the accepted kit."""
    mask = np.array(Image.open(kit.source.parent / "kit-sw-landing-beacon_emission_mask.png").convert("L")) > 127
    height, width = mask.shape
    uv = kit.uv[kit.idx]
    inside = []
    for weights in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6),
                    (0.45, 0.45, 0.1), (0.1, 0.45, 0.45), (0.45, 0.1, 0.45)):
        point = (uv * np.array(weights)[None, :, None]).sum(axis=1)
        x = np.clip((point[:, 0] * width).astype(int), 0, width - 1)
        y = np.clip((point[:, 1] * height).astype(int), 0, height - 1)
        inside.append(mask[y, x])
    covered = np.mean(inside, axis=0) >= 0.99
    _, island = welded_islands(kit)
    crystal = np.zeros(len(kit.idx), bool)
    for label in np.unique(island[covered]):
        members = island == label
        if (members & covered).sum() >= 0.9 * members.sum():
            crystal |= members
    if not 30 <= crystal.sum() <= 60:
        raise ValueError(f"N20: {int(crystal.sum())} crystal faces (the review measured 38)")
    kit.glow_faces = crystal
    kit.glow_material = json.loads(json.dumps(kit.material))
    kit.glow_material.update({"name": kit.material.get("name", kit.name) + "-crystal",
                              "emissiveTexture": {"index": 0}, "emissiveFactor": list(BEACON_GLOW_FACTOR),
                              "extensions": {"KHR_materials_emissive_strength":
                                             {"emissiveStrength": BEACON_GLOW_STRENGTH}}})
    _, area = kit.face_normals()
    low = float(kit.tri()[crystal][:, :, 1].min())
    log["crystal"] = {"faces": int(crystal.sum()), "area_m2": round(float(area[crystal].sum()), 3),
                      "y_m": [round(low, 3), round(float(kit.tri()[crystal][:, :, 1].max()), 3)],
                      "single_faces_in_mask_left_on_stone": int((covered & ~crystal).sum()),
                      "material": kit.glow_material["name"], "emissive_strength": BEACON_GLOW_STRENGTH,
                      "emissive_factor": list(BEACON_GLOW_FACTOR)}
    log["light"] = dict(BEACON_LIGHT)


# --------------------------------------------------------------------------- the pieces

# id, kit name, source (relative to --batch1, or "n8:" for --n8), origin kind, fix, collider, notes
ASSETS = [
    ("N1", "sw-palace-keep", "A/kit/kit-sw-palace-keep.glb", "base", fix_keep,
     [{"box": [30.26, 13.4, 29.63], "centre": [0, 6.7, 0], "note": "palace block to the eaves"},
      {"box": [8.0, 32.0, 8.4], "centre": [0.03, 16.0, 3.57], "note": "central tower"}],
     "landmark keep, porch at +Z; owner's call on texture softness (14 texels/m)"),
    ("N2", "sw-wall-tower-round", "A/n2_refix/kit-sw-wall-tower-round.glb", "base", None,
     [{"cylinder": {"radius": 2.4, "height": 14.0}, "base_y": 0.0, "note": "shaft r 2.0-2.4, ring r 2.67"}],
     "pilot, batch-refixed (plaque deleted, finial 199 tris, roof in the cobalt band); open shells, double-sided"),
    ("N3", "sw-curtain-wall", "A/kit/kit-sw-curtain-wall.glb", "base", fix_curtain_wall,
     [{"box": [11.19, 6.4, 3.0], "centre": [0, 3.2, 0]}],
     "11.19 m module, field face +Z; every run end abuts a module or buries in N2/N4/N5 (open cut ends)"),
    ("N4", "sw-wall-bastion", "A/kit/kit-sw-wall-bastion.glb", "base", fix_bastion,
     [{"cylinder": {"radius": 6.3, "height": 7.6}, "base_y": 0.0},
      {"cylinder": {"radius": 7.2, "height": 1.5}, "base_y": 0.0, "note": "battered base course"}],
     "origin on the drum axis, bartizan at +Z; N3 walk 5.21 m meets the 5.85 m platform (0.64 m step)"),
    ("N5", "sw-gatehouse", "A/kit/kit-sw-gatehouse.glb", "base", fix_gatehouse,
     [{"box": [9.83, 17.0, 11.41], "centre": [-7.44, 8.5, 0], "note": "west drum and gate block"},
      {"box": [9.83, 17.0, 11.41], "centre": [7.44, 8.5, 0], "note": "east drum and gate block"},
      {"box": [5.05, 5.35, 11.41], "centre": [0, 8.325, 0],
       "note": "lintel from 5.65 m; the passage paving (0.08-0.17 m) is the Walk_ child"}],
     "24.7 x 11.4 m: the town plan leaves about 25 m at the gate; walls bury in the drums; double-sided"),
    ("N6", "sw-domed-temple", "B/kit/kit-sw-domed-temple.glb", "base", fix_temple,
     [{"box": [14.4, 0.6, 12.3], "centre": [0, 0.3, 0], "note": "podium; steps walkable"},
      {"box": [11.7, 7.3, 7.5], "centre": [0, 3.95, -1.2], "note": "hall, z -4.95..+2.55"},
      {"cylinder": {"radius": 4.5, "height": 9.2}, "base_y": 7.3, "centre_xz": [0, -1.2], "note": "drum and dome"}],
     "respawn temple, portico at +Z; the six modelled ribs are the owner's call"),
    ("N7", "sw-townhouse-blue", "B/kit/kit-sw-townhouse-blue.glb", "base", fix_townhouse_blue,
     [{"box": [7.1, 5.7, 5.9], "centre": [0, 2.85, 0]},
      {"wedge": [7.1, 3.9, 5.9], "base_y": 5.7, "note": "roof to the 9.6 m ridge"}],
     "eaves 5.67 m (owner accepted; sheet row eaves ~5.7, ridge ~9.6, top 10.5); stone tint is the owner's call"),
    ("N8", "sw-townhouse-dome-arcade", "n8:kit-sw-townhouse-dome-arcade.glb", "base", fix_townhouse_dome,
     [{"box": [8.24, 6.76, 6.36], "centre": [0.02, 3.38, 0]},
      {"pyramid": [8.67, 1.24, 6.94], "base_y": 6.76, "note": "roof to about 8 m; the cupola above is visual"}],
     "redesign with a shallow blind arcade at +Z; 2,408 hidden tris kept (optional delete after a Godot check)"),
    ("N9", "sw-lighthouse-red", "C1/kit/kit-sw-lighthouse-red.glb", "base", fix_lighthouse_red,
     [{"cylinder": {"radius": 3.6, "height": 4.0}, "base_y": 0.0, "note": "battered tower base"},
      {"cylinder": {"radius": 2.9, "height": 19.0}, "base_y": 0.0, "note": "tower on the origin axis"},
      {"box": [6.6, 7.5, 8.85], "centre": [-6.29, 3.75, -0.29], "note": "keeper's cottage"}],
     "north tower = red lighthouse; origin on the tower axis; door_azimuth_deg 23 (not exactly +Z)"),
    ("N10", "sw-lighthouse-green", "C1/kit/kit-sw-lighthouse-green.glb", "waterline", fix_lighthouse_green,
     [{"cylinder": {"radius": 12.0, "height": 3.8}, "base_y": -0.76, "note": "platform; its top (+3.0 m) is Walk_"},
      {"cylinder": {"radius": 3.0, "height": 18.1}, "base_y": 3.0, "note": "tower"}],
     "WATERLINE: platform top at +3.0 m above sea, foot -0.76 m (needs seabed within ~0.7 m, or a rock skirt)"),
    ("N11", "sw-harbour-tower", "C1/kit/kit-sw-harbour-tower.glb", "base", None,
     [{"box": [5.21, 12.0, 5.27], "centre": [0, 6.0, 0]}],
     "stands on the pier deck (+2.5 m in the spec)"),
    ("N12", "sw-causeway-arch-span", "C2/kit/kit-sw-causeway-arch-span.glb", "waterline", fix_arch_span,
     [{"box": [12.0, 0.8, 10.0], "centre": [0, -0.4, 0], "note": "deck, walk surface (Walk_ child node)"},
      {"box": [12.0, 1.2, 0.8], "centre": [0, 0.6, 5.4], "note": "parapet"},
      {"box": [12.0, 1.2, 0.8], "centre": [0, 0.6, -5.4], "note": "parapet"}],
     "WATERLINE (deck-top origin, Y=0 is the walking surface); 12.0 m module; instance it (about 133 modules)"),
    ("N13", "sw-trestle-pier-span", "retry/kit/kit-sw-trestle-pier-span.glb", "waterline", fix_trestle,
     [{"box": [8.0, 0.4, 10.5], "centre": [0, -0.2, 0], "note": "deck, walk surface (Walk_ child node)"},
      {"box": [8.0, 1.07, 0.3], "centre": [0, 0.535, 5.1], "note": "rail"},
      {"box": [8.0, 1.07, 0.3], "centre": [0, 0.535, -5.1], "note": "rail"}],
     "WATERLINE (deck-top origin); 8 m module; deck lightness (L 0.435) is the owner's call"),
    ("N14", "sw-ferry-ship", "C1/kit/kit-sw-ferry-ship.glb", "waterline", None,
     [{"box": [22.0, 4.0, 7.0], "centre": [0, 0.15, 0], "note": "camera/clip only; not walkable"}],
     "WATERLINE at keel + 1.85 m (accepted); bow +X; masts 11.8 m (owner waived)"),
    ("N15", "sw-broadleaf-tree-a", "D1/kit/kit-sw-broadleaf-tree-a.glb", "base", fix_tree_a,
     [{"cylinder": {"radius": 0.8, "height": 4.0}, "base_y": 0.0, "note": "trunk"}],
     "origin at the trunk base; crown 11.0 x 8.5 m from about 3 m up"),
    ("N16", "sw-broadleaf-tree-b", "D2/kit/kit-sw-broadleaf-tree-b.glb", "base", fix_tree_b,
     [{"cylinder": {"radius": 0.45, "height": 4.5}, "base_y": 0.0, "note": "trunk"}],
     "origin at the trunk base; clear trunk 4.5 m"),
    ("N17", "sw-blossom-tree", "D2/kit/kit-sw-blossom-tree.glb", "base", fix_blossom,
     [{"cylinder": {"radius": 1.2, "height": 2.5}, "base_y": 0.0, "note": "trunk"}],
     "plaza hero; crown 13.7 x 13.3 m, rim at about 2.25 m: seat 1-2 at the plaza edge (or x0.9 for 3); "
     "the bubble crown is the owner's look call"),
    ("N18r1", "sw-sea-cliff-face", "retry/kit/kit-sw-sea-cliff-face.glb", "base", fix_turf,
     [{"mesh": "convex hull or decimated mesh (rock)"}],
     "FAILED review; no-credit fallback only: overlap copies 9 m (about 37 m net), bury the back or the cut"),
    ("N19", "sw-sea-cliff-corner", "C2/kit/kit-sw-sea-cliff-corner.glb", "base", fix_turf,
     [{"mesh": "convex hull or decimated mesh (rock)"}],
     "a ~42 m narrow promontory (apex ~84 deg, arms swept to ~55-65 deg; apex at x 1.78, z 19.16), "
     "not a compact 90 deg corner; bury the open V back"),
    ("N20", "sw-landing-beacon", "beacon:kit/kit-sw-landing-beacon.glb", "base", fix_beacon,
     [{"box": [7.4, 1.09, 7.37], "centre": [0, 0.545, 0],
       "note": "two-step octagonal plinth (treads 0.57 and 1.09 m), walkable steps"},
      {"box": [3.62, 2.84, 3.62], "centre": [0, 2.51, 0], "note": "pedestal to 3.93 m"},
      {"cylinder": {"radius": 1.34, "height": 4.82}, "base_y": 3.93, "note": "shaft to the 8.75 m cornice"},
      {"cylinder": {"radius": 2.23, "height": 2.0}, "base_y": 8.75, "note": "cornice, cobalt roof and gold cup"},
      {"cylinder": {"radius": 0.84, "height": 2.83}, "base_y": 10.67, "note": "crystal, emissive (visual)"}],
     "landing beacon (replaces the borrowed Four Gates sanctuary beacon on the arrival plaza): 13.5 m to the "
     "crystal tip, below N6's 16.5 m; front +Z; the crystal is the emissive second primitive; extras.light is "
     "the point light the publisher declares as a lighting marker"),
]

LEFT_AS_DELIVERED = {
    "N1": ["texture softness, 14 texels/m (owner's call, from a Godot 26 m look-pass screenshot)",
           "the rubble lumps at the turret bases and the side-wall bulge keep their shape (repainted stone only)",
           "optional: finial of 200 tris or fewer", "optional, after a Godot check: delete ~5,400 hidden interior tris"],
    "N3": ["optional: exterior repack to 1024", "crenel sill miss (5.24 m) accepted as cosmetic"],
    "N6": ["the six modelled gold ribs (owner's call)"],
    "N7": ["shared stone tint: this house reads creamier than N2 (owner's call)"],
    "N8": ["optional, after a Godot check: delete the 2,408 hidden enclosed tris (then a UV repack to 1024)",
           "stone S 0.41 reads cream like N7 (owner's call on a shared stone tint)"],
    "N9": ["cottage ridge 7.54 m (owner waived)", "rubble-stone shaft: judged in the Godot look pass"],
    "N10": ["x1.12 tower-only stretch (owner sign-off pending; gallery stays 12.39 m, finial 18.08 m)",
            "rock skirt to -2 m not added: place where the seabed is within about 0.7 m, or add one later",
            "optional -7 deg hue shift toward verdigris (needs the lead's or owner's OK)"],
    "N11": ["optional: window smear touch-up; warm the stone if it reads cool beside N2 in Godot"],
    "N12": ["optional: lift stone lightness 3-5 %", "instancing (MultiMesh) or LOD for the ~133 modules: build stage"],
    "N13": ["deck lightness L 0.435 against the 0.48 floor (owner's call)",
            "23 texels/m and end-profile IoU 0.805 accepted as delivered (or mirror one end's rail posts)"],
    "N14": ["optional: lift hull wood and gold lightness", "rope shimmer: check in Godot", "masts 11.8 m (owner waived)"],
    "N15": ["LOD1 3,500-4,000 tris and a far hull/impostor: Godot's importer generates LODs; no impostor yet",
            "2048 texture only if Godot shows a soft crown"],
    "N16": ["LOD1 3,000 tris: Godot's importer generates LODs"],
    "N17": ["the bubble crown (owner's look call)", "canopy fade if a path runs under it: build/runtime"],
    "N18r1": ["failed review: kept only as the buried fallback cliff piece the owner chose",
              "bisect at z about -3 m / x0.75 scale / MultiMesh: placement choices"],
    "N19": ["N18 | N19 | N18 join test: build stage",
            "the turf cap overhangs the rock top on some edges (a floating strip where the corner stands proud of "
            "the land behind it): placement sinks it; trimming the cap is open"],
    "N20": ["crystal share 0.16 of the crown at the -60 deg camera (limit 0.25): lit instead (emissive crystal + "
            "point light); a bigger crystal needs crystal and cup scaled together (untested, owner's call)",
            "R7 small-part share 61 % (target 20 %): chunky separate parts, none over the decimation cap",
            "plinth of 2 broad steps (concept 3); shaft barely tapers (2.5 -> 2.4 m)"],
}


def build(batch1: Path, n8: Path, entry, beacon: Path | None = None) -> tuple[bytes, dict]:
    asset_id, name, source, origin, fix, collider, notes = entry
    if source.startswith("beacon:"):
        path = (beacon or batch1.parent / "beacon") / source[len("beacon:"):]
    else:
        path = n8 / source[3:] if source.startswith("n8:") else batch1 / source
    kit = Kit(path)
    log: dict = {"id": asset_id, "source": source, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "tris_before": int(len(kit.idx))}
    if fix is not None:
        fix(kit, log)
    log["duplicates"] = delete_duplicate_faces(kit)
    used = np.unique(kit.idx)
    low, high = kit.pos[used].min(axis=0), kit.pos[used].max(axis=0)
    kit.extras = {"id": asset_id, "kit": "kit-" + name, "origin": origin, "collider": collider, "notes": notes}
    if asset_id == "N9":
        kit.extras["door_azimuth_deg"] = 23
    if asset_id == "N20":
        kit.extras["light"] = dict(BEACON_LIGHT)
        kit.extras["emissive_material"] = kit.glow_material["name"]
    if kit.walk_faces.any():
        kit.extras["walk_node"] = kit.walk_name
    payload = kit.write()
    log.update({"tris_after": int(len(kit.idx)), "bounds_min": [round(float(v), 3) for v in low],
                "bounds_max": [round(float(v), 3) for v in high], "texture_changed": kit.image_changed,
                "left_as_delivered": LEFT_AS_DELIVERED.get(asset_id, []),
                "output_sha256": hashlib.sha256(payload).hexdigest()})
    return payload, log


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch1", type=Path, required=True, help="work-output/continent-v2/meshy/batch1")
    parser.add_argument("--n8", type=Path, required=True, help="work-output/continent-v2/meshy/n8_redesign/kit")
    parser.add_argument("--beacon", type=Path, default=None,
                        help="work-output/continent-v2/meshy/beacon (default: beside --batch1)")
    parser.add_argument("--out", type=Path, required=True, help="folder for the fixed copies")
    parser.add_argument("--only", nargs="*", help="piece ids to (re)build")
    parser.add_argument("--check", action="store_true", help="verify the copies in --out, do not write")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "seat_fixes_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    report.setdefault("schema", "eloria-seat-fixes-v1")
    report.setdefault("pieces", {})
    stale = []
    for entry in ASSETS:
        if args.only and entry[0] not in args.only:
            continue
        payload, log = build(args.batch1, args.n8, entry, args.beacon)
        target = args.out / f"kit-{entry[1]}.glb"
        if args.check:
            if not target.exists() or target.read_bytes() != payload:
                stale.append(entry[0])
            continue
        target.write_bytes(payload)
        report["pieces"][entry[0]] = log
        print(f"{entry[0]:6s} {target.name}: {log['tris_before']} -> {log['tris_after']} tris, "
              f"{len(payload) // 1024} KB", flush=True)
    if args.check:
        print("stale: " + ", ".join(stale) if stale else "all fixed copies match")
        return 1 if stale else 0
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
