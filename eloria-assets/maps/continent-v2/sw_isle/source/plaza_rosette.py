"""The arrival plaza's rosette as a kit inlay: a 16 m mosaic disc drawn as one mesh with its own texture.

The rosette at the spawn (a cobalt ring round a gilt centre on the limestone plaza) was two ellipse ground regions,
`plaza-rosette` (16 m) and `plaza-rosette-centre` (6 m). The territory exporter draws a ground region on the terrain's
2 m cells with a vertex-alpha blend, so a 16 m ring with a 0.8 m blend cannot be round: in the game client the ring was
an octagon with stepped corners and the gilt centre a ragged blob that read as a spill (game-look review D8), the first
thing a new player sees. This tool draws the rosette as a kit piece instead, as garden_paving.py draws the walks:

- the disc: `RINGS` concentric rings of `SEGMENTS` vertices (a 96-gon: 0.04 m off a true circle at 8 m), flat, its
  origin at the disc's centre, laid `liftMetres` (0.10 m) over the level plaza (121.494 m at every vertex under
  it): above every ground region's lift (the territory exporter lifts region layers at most 0.07 m), or the
  plaza's own limestone region draws over it;
- its texture, planar over the disc (u, v = 0.5 + x, z / 16 m), a procedural mosaic in the plaza's own palette: a
  gilt boss and a 16-ray sunburst of gilt and limestone, a cobalt field with a ring of 24 pale lotus petals between
  thin gilt rules, and a limestone border with cobalt dots, all in square tesserae (`TESSERA_M`) with darker grout,
  at `PIXELS` px; the stone normal map the paving uses gives it relief;
- the material is named `kit-sw-plaza-rosette`, so the region's look file can keep its chroma (`props.keep_words`).

The client publisher names the piece's mesh a `Walk_` surface (publish_client.py), as it does the garden paving, so
the look leaves its colours alone, the grass never grows on it and OccluderFade keeps it solid under the player.

`python plaza_rosette.py` writes the piece and its texture into the territory kit and `plaza-rosette-record.json`;
`--check` confirms the committed files are what this script makes."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
KIT = CLIENT / "godot-client/world_authoring/regions/sw_isle/assets"
RECORD = HERE / "plaza-rosette-record.json"
NAME = "kit-sw-plaza-rosette"
RADIUS = 8.0
RINGS = 8
SEGMENTS = 96
LIFT = 0.10
PIXELS = 1024
TESSERA_M = 0.12
NORMAL = CLIENT / "godot-client/src/dev/map_authoring_pilot/style/textures/stone-normal.png"
# the plaza's palette (display sRGB): the castle kit's cobalt and gold, the courts' limestone
COBALT = np.array([46, 82, 168])
COBALT_DEEP = np.array([30, 56, 128])
GILT = np.array([214, 170, 82])
LIMESTONE = np.array([226, 216, 196])
GROUT = 0.78


def mosaic() -> np.ndarray:
    n = PIXELS
    metres = (np.arange(n) + 0.5) / n * 2 * RADIUS - RADIUS
    x, z = np.meshgrid(metres, metres)
    r = np.hypot(x, z)
    a = np.arctan2(z, x)
    img = np.empty((n, n, 3))
    img[:] = LIMESTONE
    # cobalt field 3.3-6.6 m, gilt rules at its edges
    img[(r >= 3.3) & (r < 6.6)] = COBALT
    img[(r >= 3.1) & (r < 3.3)] = GILT
    img[(r >= 6.6) & (r < 6.85)] = GILT
    # 24 lotus petals in the field (pale limestone, pointed outwards), 4.0-6.1 m
    k = 24
    local = (a + math.pi) % (2 * math.pi / k) - math.pi / k
    t = np.clip((r - 4.0) / 2.1, 0.0, 1.0)
    half = (0.9 * np.sin(math.pi * np.sqrt(t)) * (1.0 - 0.35 * t)) / np.maximum(r, 1e-6)
    petal = (r >= 4.0) & (r < 6.1) & (np.abs(local) < half)
    img[petal] = LIMESTONE
    inner = (r >= 4.15) & (r < 5.8) & (np.abs(local) < half * 0.45)
    img[inner] = GILT * 0.5 + LIMESTONE * 0.5
    # sunburst 0.7-3.1 m: 16 rays, gilt and limestone alternating, tapered
    rays = 16
    sector = ((a + math.pi) / (2 * math.pi) * rays).astype(int) % 2
    burst = (r >= 0.7) & (r < 3.1)
    img[burst & (sector == 0)] = GILT
    img[burst & (sector == 1)] = LIMESTONE
    # tapering points: the gilt rays end in points towards the rule
    lr = (a + math.pi) % (2 * math.pi / rays) / (2 * math.pi / rays)
    point = burst & (r > 2.2) & (np.abs(lr - 0.5) * 2 > 1.0 - (3.1 - r) / 0.9) & (sector == 0)
    img[point] = LIMESTONE
    # gilt boss with a cobalt eye
    img[r < 0.7] = GILT
    img[r < 0.28] = COBALT_DEEP
    # limestone border with cobalt dots 6.85-8 m
    dots = 40
    dl = (a + math.pi) % (2 * math.pi / dots) - math.pi / dots
    dot = (np.hypot(r - 7.4, dl * 7.4) < 0.17)
    img[dot] = COBALT
    # tesserae: grout lines on a square grid, each tessera's tone jittered
    tx, tz = np.floor((x + RADIUS) / TESSERA_M), np.floor((z + RADIUS) / TESSERA_M)
    fx, fz = (x + RADIUS) / TESSERA_M - tx, (z + RADIUS) / TESSERA_M - tz
    grout = (np.minimum(np.minimum(fx, 1 - fx), np.minimum(fz, 1 - fz)) < 0.09)
    rng = np.random.default_rng(1003)
    jitter = rng.uniform(0.9, 1.06, (int(tx.max()) + 2, int(tz.max()) + 2))
    img *= jitter[tx.astype(int), tz.astype(int)][..., None]
    img[grout] *= GROUT
    # the rim fades into the plaza over the last 0.35 m (the disc edge is opaque: keep the border pale)
    return np.clip(img, 0, 255).astype(np.uint8)


def _bytes(image: Image.Image, mime: str) -> tuple[bytes, str]:
    out = io.BytesIO()
    if mime == "image/png":
        image.save(out, "PNG", optimize=True)
    else:
        image.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    data = out.getvalue()
    return data, hashlib.sha256(data).hexdigest() + (".png" if mime == "image/png" else ".jpg")


def disc() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    verts, uvs, tris = [(0.0, LIFT, 0.0)], [(0.5, 0.5)], []
    for i in range(1, RINGS + 1):
        rr = RADIUS * i / RINGS
        for j in range(SEGMENTS):
            ang = 2 * math.pi * j / SEGMENTS
            x, z = rr * math.cos(ang), rr * math.sin(ang)
            verts.append((x, LIFT, z))
            uvs.append((0.5 + x / (2 * RADIUS), 0.5 + z / (2 * RADIUS)))
    for j in range(SEGMENTS):
        tris.append((0, 1 + (j + 1) % SEGMENTS, 1 + j))
    for i in range(1, RINGS):
        a0, b0 = 1 + (i - 1) * SEGMENTS, 1 + i * SEGMENTS
        for j in range(SEGMENTS):
            j1 = (j + 1) % SEGMENTS
            tris += [(a0 + j, a0 + j1, b0 + j), (a0 + j1, b0 + j1, b0 + j)]
    v, t = np.asarray(verts, float), np.asarray(tris, np.int64)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    up = (b[:, 2] - a[:, 2]) * (c[:, 0] - a[:, 0]) - (b[:, 0] - a[:, 0]) * (c[:, 2] - a[:, 2])
    t[up < 0] = t[up < 0][:, [0, 2, 1]]
    return v, np.asarray(uvs, float), t


def glb(verts: np.ndarray, uvs: np.ndarray, tris: np.ndarray, albedo: str, normal: str) -> bytes:
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
    document = {
        "asset": {"version": "2.0", "generator": "Eloria sw_isle plaza_rosette"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"name": NAME, "mesh": 0}],
        "meshes": [{"name": NAME, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                                                  "indices": 3, "material": 0}]}],
        "materials": [{"name": NAME,
                       "pbrMetallicRoughness": {"baseColorTexture": {"index": 0},
                                                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                                                "metallicFactor": 0.0, "roughnessFactor": 0.9},
                       "normalTexture": {"index": 1, "scale": 0.5}}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071},
                     {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
        "textures": [{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}],
        "images": [{"name": "plaza-rosette-mosaic", "mimeType": "image/jpeg", "uri": "../textures/" + albedo},
                   {"name": "stone-normal", "mimeType": "image/png", "uri": "../textures/" + normal}],
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blobs)}],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(blobs)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(blobs), 0x004E4942) + bytes(blobs))


def build() -> dict[str, bytes]:
    albedo_bytes, albedo = _bytes(Image.fromarray(mosaic(), "RGB"), "image/jpeg")
    normal_bytes, normal = _bytes(Image.open(NORMAL), "image/png")
    v, uv, t = disc()
    return {"textures/" + albedo: albedo_bytes, "textures/" + normal: normal_bytes,
            f"prototypes/{NAME}.glb": glb(v, uv, t, albedo, normal)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    outputs = build()
    record = {"schema": "eloria-sw-isle-plaza-rosette-v1", "tool": "plaza_rosette.py",
              "outputs": {path: hashlib.sha256(data).hexdigest() for path, data in sorted(outputs.items())},
              "disc": {"radiusMetres": RADIUS, "rings": RINGS, "segments": SEGMENTS, "liftMetres": LIFT,
                       "triangles": SEGMENTS * (2 * RINGS - 1)},
              "placement": {"stem": NAME, "positionLocal": [-443.0, 121.4942, 121.0],
                            "replaces": ["plaza-rosette", "plaza-rosette-centre"]}}
    text = json.dumps(record, indent=1) + "\n"
    if args.check:
        bad = [p for p, data in outputs.items() if not (KIT / p).exists() or (KIT / p).read_bytes() != data]
        if not RECORD.exists() or RECORD.read_text(encoding="utf-8") != text:
            bad.append(RECORD.name)
        print(f"{len(outputs)} outputs, {len(bad)} differ: {bad}")
        return 1 if bad else 0
    for path, data in outputs.items():
        target = KIT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    RECORD.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps(record, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
