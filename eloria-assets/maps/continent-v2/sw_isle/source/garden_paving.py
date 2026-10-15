"""Pave the garden town's walks and lanes in the courts' limestone: kit pieces drawn from the walks' own lines.

The garden town's streets were Worn-earth road ribbons (the only road surface the bake accepts). The road shader
multiplies its brown earth texture by a worn tint the bake caps at 1, so a ribbon can only be darkened: every
`gt-` ribbon read as brown dirt where the concept shows cream stone. The polish pass paved the avenue and two
straight court links as limestone ground regions, but the remaining walks and lanes curve (62 straight pieces at a
0.5 m tolerance) and the editor draws at most 127 ground regions (123 were used). The game-look fix stage (owner,
2026-10-02: "fix the garden town's brown paths") paves them as kit pieces instead:

- `garden-paving.json` holds the ribbons as they were drawn (centre points, widths, the ground under each point
  read from the check bake), the courts' paving surface (the Weathered limestone masonry albedo, the stone normal
  map, the walks' tint 0.90/0.86/0.78, the region repeat of 7.35 m: terrain UV 0.17 per metre times the masonry's
  0.8) and the publish chunk grid;
- each ribbon becomes a strip, its half width plus `edgeMarginMetres` either side of the line, with round ends,
  `liftMetres` over the ground plus `liftStepMetres` per ribbon (so where two walks cross the later one draws on top),
  its paving turned along the walk (u = distance along the line, v = across it, in repeats). With `groundGrid` (the
  check bake's resolved heights over the town, `garden-paving-ground.f32le`, written by editor-pass/polish/g4/
  paving_ground.py) every vertex lies on that ground (the terrain's own triangles), its rows at most
  `acrossMetres` apart; without it a strip lies flat across its width on the ground under its centre line (the first
  pieces, which dipped up to 0.29 m under the keep terrace's edge);
- the strips' triangles are grouped by the 96 m publish chunk their centroid falls in, so each piece streams with
  the ground it covers: one prototype `kit-sw-garden-paving-<ix>-<iz>.glb` per chunk, its origin at the chunk's
  centre on the median ground height, placed once at that origin (identity rotation and scale);
- the two textures are written once, content-addressed, to the territory's `assets/textures/` and referenced by
  URI, as prepare_meshy_kit.py does (the albedo at `albedoPixels`, 768: the pieces stream with the arrival hub,
  whose texture budget is already over). The client publisher names each piece's mesh a `Walk_` surface
  (publish_client.py), so the client stands actors on it, OccluderFade keeps it solid under the player and the
  grass does not grow through it; the server, which has no map yet, never sees it.

`python garden_paving.py` writes the pieces and `garden-paving-record.json` (the SHA-256 of every input and
output); `--check` confirms the committed files are what the inputs produce; `--ground-check <resolved-heights.f32le>`
(a check bake's) measures every piece's clearance over the current terrain at its vertices, edge midpoints and
triangle centroids, and fails when any point is buried (under -0.02 m) or floats (over 0.15 m).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
KIT = CLIENT / "godot-client/world_authoring/regions/sw_isle/assets"
INPUT = HERE / "garden-paving.json"
RECORD = HERE / "garden-paving-record.json"
CAP_SEGMENTS = 8


def _texture(path: Path, mime: str, size: int = 0) -> tuple[bytes, str]:
    image = Image.open(path)
    image.load()
    if size and max(image.size) > size:
        image = image.resize((size, round(size * image.size[1] / image.size[0])), Image.LANCZOS)
    out = io.BytesIO()
    if mime == "image/png":
        image.save(out, "PNG", optimize=True)
    else:
        image.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    data = out.getvalue()
    return data, hashlib.sha256(data).hexdigest() + (".png" if mime == "image/png" else ".jpg")


def _clean(points: np.ndarray) -> np.ndarray:
    keep = [0]
    for i in range(1, len(points)):
        if math.hypot(*(points[i, [0, 2]] - points[keep[-1], [0, 2]])) > 0.05:
            keep.append(i)
    return points[keep]


class Ground:
    """Heights on a 2 m vertex lattice (row = +z), sampled on the terrain's own triangles: each cell split along
    (r, c+1)-(r+1, c), as the territory's terrain and the publish draw it."""

    def __init__(self, grid: dict, data: bytes):
        self.h = np.frombuffer(data, "<f4").reshape(grid["shape"]).astype(np.float64)
        self.x0, self.z0 = grid["firstVertexLocal"]
        self.cell = float(grid["cellMetres"])

    def __call__(self, x, z):
        fx = (np.asarray(x, float) - self.x0) / self.cell
        fz = (np.asarray(z, float) - self.z0) / self.cell
        c = np.clip(np.floor(fx).astype(int), 0, self.h.shape[1] - 2)
        r = np.clip(np.floor(fz).astype(int), 0, self.h.shape[0] - 2)
        u, v = fx - c, fz - r
        h00, h01 = self.h[r, c], self.h[r, c + 1]
        h10, h11 = self.h[r + 1, c], self.h[r + 1, c + 1]
        lower = u + v <= 1.0
        return np.where(lower, h00 + (h01 - h00) * u + (h10 - h00) * v,
                        h11 + (h10 - h11) * (1.0 - u) + (h01 - h11) * (1.0 - v))


def strip(ribbon: dict, lift: float, tile: float, margin: float, ground_at: "Ground | None" = None,
          across_metres: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vertices (x, y, z), uvs and triangles of one ribbon's paving: a strip along the line plus round ends."""
    p = _clean(np.asarray(ribbon["points"], float))
    ground = np.asarray(ribbon["ground"], float)[:len(p)] if len(ribbon["ground"]) == len(p) else \
        np.interp(np.arange(len(p)), np.linspace(0, len(p) - 1, len(ribbon["ground"])), ribbon["ground"])
    xz = p[:, [0, 2]]
    half = ribbon["width"] / 2.0 + margin
    across = max(2, int(math.ceil(2 * half / across_metres)))
    seg = np.hypot(*np.diff(xz, axis=0).T)
    arc = np.r_[0.0, np.cumsum(seg)]
    tangent = np.gradient(xz, axis=0)
    tangent /= np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-9)[:, None]
    normal = np.c_[-tangent[:, 1], tangent[:, 0]]
    verts, uvs, tris = [], [], []
    for i in range(len(p)):
        for k in range(across + 1):
            off = -half + 2 * half * k / across
            q = xz[i] + normal[i] * off
            verts.append((q[0], ground[i] + lift, q[1]))
            uvs.append((arc[i] / tile, off / tile))
    row = across + 1
    for i in range(len(p) - 1):
        for k in range(across):
            a, b = i * row + k, i * row + k + 1
            c, d = (i + 1) * row + k, (i + 1) * row + k + 1
            tris += [(a, c, b), (b, c, d)]
    # round ends: a fan of CAP_SEGMENTS triangles about the end point, beyond the strip's end
    for end, sign in ((0, -1.0), (len(p) - 1, 1.0)):
        centre = len(verts)
        verts.append((xz[end][0], ground[end] + lift, xz[end][1]))
        uvs.append((arc[end] / tile, 0.0))
        ring = []
        for j in range(CAP_SEGMENTS + 1):
            ang = math.pi * j / CAP_SEGMENTS
            d = normal[end] * math.cos(ang) * half + tangent[end] * sign * math.sin(ang) * half
            q = xz[end] + d
            ring.append(len(verts))
            verts.append((q[0], ground[end] + lift, q[1]))
            uvs.append(((arc[end] + float(d @ tangent[end])) / tile, float(d @ normal[end]) / tile))
        for j in range(CAP_SEGMENTS):
            tri = (centre, ring[j], ring[j + 1]) if sign > 0 else (centre, ring[j + 1], ring[j])
            tris.append(tri)
    v, t = np.asarray(verts, float), np.asarray(tris, np.int64)
    if ground_at is not None:
        v[:, 1] = ground_at(v[:, 0], v[:, 2]) + lift
    # wind every triangle counter-clockwise seen from above (+Y), so the face looks up
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    up = (b[:, 2] - a[:, 2]) * (c[:, 0] - a[:, 0]) - (b[:, 0] - a[:, 0]) * (c[:, 2] - a[:, 2])
    t[up < 0] = t[up < 0][:, [0, 2, 1]]
    return v, np.asarray(uvs, float), t


def glb(name: str, verts: np.ndarray, uvs: np.ndarray, tris: np.ndarray, spec: dict, albedo: str,
        normal: str) -> bytes:
    positions = verts.astype("<f4")
    normals = np.tile(np.array([0.0, 1.0, 0.0], "<f4"), (len(verts), 1))
    texcoords = uvs.astype("<f4")
    indices = tris.astype("<u4").ravel()
    blobs, views, accessors = bytearray(), [], []

    def add(data: bytes, target: int) -> int:
        while len(blobs) % 4:
            blobs.append(0)
        views.append({"buffer": 0, "byteOffset": len(blobs), "byteLength": len(data), "target": target})
        blobs.extend(data)
        return len(views) - 1

    accessors.append({"bufferView": add(positions.tobytes(), 34962), "componentType": 5126, "count": len(positions),
                      "type": "VEC3", "min": [float(v) for v in positions.min(0)],
                      "max": [float(v) for v in positions.max(0)]})
    accessors.append({"bufferView": add(normals.tobytes(), 34962), "componentType": 5126, "count": len(normals),
                      "type": "VEC3"})
    accessors.append({"bufferView": add(texcoords.tobytes(), 34962), "componentType": 5126,
                      "count": len(texcoords), "type": "VEC2"})
    accessors.append({"bufferView": add(indices.tobytes(), 34963), "componentType": 5125, "count": len(indices),
                      "type": "SCALAR"})
    while len(blobs) % 4:
        blobs.append(0)
    tint = spec["tint"]
    document = {
        "asset": {"version": "2.0", "generator": "Eloria sw_isle garden_paving"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                                                  "indices": 3, "material": 0}]}],
        "materials": [{"name": "garden-paving-limestone",
                       "pbrMetallicRoughness": {"baseColorTexture": {"index": 0},
                                                "baseColorFactor": [tint[0], tint[1], tint[2], 1.0],
                                                "metallicFactor": 0.0, "roughnessFactor": spec["roughness"]},
                       "normalTexture": {"index": 1, "scale": spec["normalScale"]}}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
        "images": [{"name": "weathered-limestone-masonry", "mimeType": "image/jpeg", "uri": "../textures/" + albedo},
                   {"name": "stone-normal", "mimeType": "image/png", "uri": "../textures/" + normal}],
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blobs)}],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(blobs)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(blobs), 0x004E4942) + bytes(blobs))


def build() -> tuple[dict[str, bytes], dict]:
    spec = json.loads(INPUT.read_text(encoding="utf-8"))
    surface = spec["surface"]
    albedo_bytes, albedo = _texture(CLIENT / surface["albedo"], "image/jpeg", surface["albedoPixels"])
    normal_bytes, normal = _texture(CLIENT / surface["normal"], "image/png")
    outputs = {"textures/" + albedo: albedo_bytes, "textures/" + normal: normal_bytes}
    grid = spec["chunks"]
    ground_at = None
    if "groundGrid" in spec:
        data = (HERE / spec["groundGrid"]["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != spec["groundGrid"]["sha256"]:
            raise SystemExit("garden-paving-ground.f32le differs from its record in garden-paving.json")
        ground_at = Ground(spec["groundGrid"], data)
    cells: dict[tuple[int, int], list] = defaultdict(list)
    for k, ribbon in enumerate(spec["ribbons"]):
        lift = spec["liftMetres"] + spec["liftStepMetres"] * k
        v, uv, t = strip(ribbon, lift, surface["repeatMetres"], spec["edgeMarginMetres"], ground_at,
                         spec.get("acrossMetres", 2.0))
        cx = v[t, 0].mean(axis=1)
        cz = v[t, 2].mean(axis=1)
        ix = np.floor((cx - grid["originMetres"]) / grid["metres"]).astype(int)
        iz = np.floor((cz - grid["originMetres"]) / grid["metres"]).astype(int)
        for key in set(zip(ix.tolist(), iz.tolist())):
            sel = (ix == key[0]) & (iz == key[1])
            cells[key].append((ribbon["id"], v, uv, t[sel]))
    placements = []
    for (ix, iz), parts in sorted(cells.items()):
        name = f"kit-sw-garden-paving-{ix}-{iz}"
        verts, uvs, tris = [], [], []
        base = 0
        for _, v, uv, t in parts:
            used = np.unique(t)
            remap = -np.ones(len(v), np.int64)
            remap[used] = np.arange(len(used)) + base
            verts.append(v[used])
            uvs.append(uv[used])
            tris.append(remap[t])
            base += len(used)
        verts = np.concatenate(verts)
        origin = np.array([grid["originMetres"] + (ix + 0.5) * grid["metres"], float(np.median(verts[:, 1])),
                           grid["originMetres"] + (iz + 0.5) * grid["metres"]])
        outputs[f"prototypes/{name}.glb"] = glb(name, verts - origin, np.concatenate(uvs), np.concatenate(tris),
                                                surface, albedo, normal)
        placements.append({"stem": name, "origin": [round(float(c), 4) for c in origin],
                           "ribbons": sorted({rid for rid, *_ in parts}), "triangles": int(sum(len(t) for *_, t in parts))})
    return outputs, {"placements": placements, "albedo": albedo, "normal": normal}


def ground_check(heights_path: Path) -> int:
    """Clearance of every committed piece over a check bake's resolved heights (the whole terrain window, 1446 x 1259
    vertices from local (-1119, -1107) every 2 m), at each vertex, edge midpoint and triangle centroid."""
    terrain = Ground({"shape": [1259, 1446], "firstVertexLocal": [-1119.0, -1107.0], "cellMetres": 2.0},
                     heights_path.read_bytes())
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    worst = {"buried": 0.0, "floating": 0.0}
    rows = []
    for placement in record["placements"]:
        document, body = _read_glb(KIT / "prototypes" / (placement["stem"] + ".glb"))
        verts = _accessor(document, body, 0) + np.asarray(placement["origin"], float)
        tris = _accessor(document, body, 3).astype(np.int64).reshape(-1, 3)
        a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
        points = np.concatenate([verts, (a + b) / 2, (b + c) / 2, (c + a) / 2, (a + b + c) / 3])
        clear = points[:, 1] - terrain(points[:, 0], points[:, 2])
        rows.append({"stem": placement["stem"], "min": round(float(clear.min()), 3),
                     "max": round(float(clear.max()), 3), "buried": int((clear < -0.02).sum()),
                     "floating": int((clear > 0.15).sum()), "points": int(len(clear))})
        worst["buried"] = min(worst["buried"], float(clear.min()))
        worst["floating"] = max(worst["floating"], float(clear.max()))
    bad = [r for r in rows if r["buried"] or r["floating"]]
    print(json.dumps({"pieces": rows, "worst": worst, "bad": len(bad)}, indent=1))
    return 1 if bad else 0


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    length = struct.unpack("<I", data[12:16])[0]
    document = json.loads(data[20:20 + length])
    return document, data[20 + length + 8:]


def _accessor(document: dict, body: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = {5126: "<f4", 5125: "<u4"}[accessor["componentType"]]
    width = {"VEC3": 3, "VEC2": 2, "SCALAR": 1}[accessor["type"]]
    raw = np.frombuffer(body, dtype, accessor["count"] * width, view["byteOffset"] + accessor.get("byteOffset", 0))
    return raw.reshape(accessor["count"], width) if width > 1 else raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    parser.add_argument("--ground-check", type=Path, default=None,
                        help="a check bake's resolved-heights.f32le: measure every piece's clearance over it")
    args = parser.parse_args()
    if args.ground_check is not None:
        return ground_check(args.ground_check)
    outputs, facts = build()
    record = {"schema": "eloria-sw-isle-garden-paving-v1", "tool": "garden_paving.py",
              "input": {"file": INPUT.name, "sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest()},
              **({"ground": {"file": "garden-paving-ground.f32le",
                             "sha256": hashlib.sha256((HERE / "garden-paving-ground.f32le").read_bytes()).hexdigest()}}
                 if (HERE / "garden-paving-ground.f32le").exists() else {}),
              "outputs": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(outputs.items())},
              "placements": facts["placements"]}
    text = json.dumps(record, indent=1) + "\n"
    if args.check:
        bad = [path for path, data in outputs.items() if not (KIT / path).exists() or (KIT / path).read_bytes() != data]
        if RECORD.read_text(encoding="utf-8") != text:
            bad.append(RECORD.name)
        print(f"{len(outputs)} outputs, {len(bad)} differ: {bad}")
        return 1 if bad else 0
    for path, data in outputs.items():
        target = KIT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    RECORD.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"pieces": len(facts["placements"]), "placements": facts["placements"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
