"""Seat generated Whitehorn Range models in the territory kit at their real size.

The granite spires, crags and boulders, glacier ice, snow-laden trees, trail
camp props, shrines and waymarks and snow dressing generated for Whitehorn
Range (from work-output/whitehorn-range-2026-09-28/asset-prompts.md), and the
models it shares with other territories (Mirrorhold's snow-capped boulders,
snow scree, alpine firs and pines, juniper and tussock grass; Amethyst
Barrens' lantern post, supply crates, ore cart, mine rails and tool rack for
the mine yard), arrive normalised to a one-unit cube centred on the origin (or
already at size), with 2K textures and a metallic factor of one. This rewrites
each as a territory prototype (`godot-client/world_authoring/regions/
whitehorn_range/assets/prototypes/`): scaled so its height (or its length, for
pieces that lie flat) is the one in SIZES, moved so the centre of its base
stands on the origin, textures shrunk to 1024 or 512 px and written once,
content-addressed, to the territory's `assets/textures/` and referenced by
URI, and non-metallic unless it is metal. Geometry is otherwise left exactly
as generated. Node transforms are baked into the vertices first (some deliveries
size their models with wrapper nodes). It is Sunmane's `prepare_meshy_kit.py`
with this kit's sizes, reading several folders.

`python prepare_meshy_kit.py --input <folder> [<folder> ...]` writes the kit and
`prepare-meshy-kit.json` (the SHA-256 of every input and output), taking each
model from the first folder that has it; `--check` confirms the committed files
are what the recorded inputs produce.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
CLIENT = HERE.parents[4]
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/whitehorn_range/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "prepare-meshy-kit.json"

# name -> (measure, metres, texture px). "height" scales the model to that
# height; "length" scales its longest horizontal side, for pieces that lie flat.
SIZES = {
    # generated for Whitehorn Range
    "cairn-tower-1": ("height", 3.5, 512), "climbing-gear-basket-1": ("height", 0.8, 512),
    "expedition-tent-1": ("length", 3.0, 512), "firewood-shelter-1": ("length", 2.5, 512),
    "frost-grass-1": ("length", 2.0, 512), "frosted-larch-tree-1": ("height", 8.0, 1024),
    "frozen-pond-1": ("length", 8.0, 1024), "frozen-waterfall-1": ("height", 12.0, 1024),
    "glacier-block-1": ("length", 5.0, 1024), "granite-crag-1": ("height", 12.0, 1024),
    "granite-spire-1": ("height", 18.0, 1024), "granite-spire-2": ("height", 22.0, 1024),
    "horn-shrine-1": ("height", 3.0, 512), "horn-waystone-1": ("height", 2.4, 512),
    "ice-shards-1": ("height", 4.0, 1024), "ice-shards-2": ("height", 2.0, 512),
    "icicle-fringe-1": ("length", 4.0, 512), "icicle-rock-arch-1": ("length", 12.0, 1024),
    "knife-ridge-1": ("length", 20.0, 1024), "lichen-rock-patch-1": ("length", 3.0, 512),
    "prayer-bell-frame-1": ("height", 3.0, 512), "prayer-flag-line-1": ("length", 8.0, 512),
    "rockfall-1": ("length", 6.0, 1024), "ski-rack-1": ("height", 1.8, 512),
    "snow-drift-1": ("length", 6.0, 512), "snowy-boulder-1": ("length", 2.5, 1024),
    "snowy-boulder-2": ("height", 3.5, 1024), "snowy-fir-tree-1": ("height", 11.0, 1024),
    "snowy-fir-tree-2": ("height", 7.0, 1024), "snowy-juniper-shrub-1": ("length", 2.5, 512),
    "stone-windbreak-1": ("length", 5.0, 512), "supply-sledge-1": ("length", 2.4, 512),
    "trail-lantern-post-1": ("height", 2.6, 512), "windbent-pine-tree-1": ("height", 4.0, 1024),
    # shared with Mirrorhold
    "alpine-fir-tree-1": ("height", 9.0, 1024), "alpine-fir-tree-2": ("height", 12.0, 1024),
    "alpine-flower-cushion-1": ("length", 1.5, 512), "juniper-shrub-1": ("length", 2.2, 512),
    "mountain-pine-tree-1": ("height", 7.0, 1024), "snow-scree-1": ("length", 3.5, 512),
    "snow-scree-2": ("length", 4.0, 512), "snowcap-boulder-1": ("height", 3.5, 1024),
    "snowcap-boulder-2": ("height", 5.0, 1024), "snowcap-boulder-3": ("height", 2.5, 1024),
    "tussock-grass-1": ("height", 0.8, 512),
    # shared with Amethyst Barrens
    "lantern-post-1": ("height", 2.6, 512), "mine-rail-straight-1": ("length", 4.0, 512),
    "mine-rail-straight-2": ("length", 4.0, 512), "ore-cart-1": ("height", 1.4, 1024),
    "supply-crate-1": ("height", 0.9, 512), "supply-crate-2": ("height", 0.65, 512),
    "supply-crate-3": ("height", 0.85, 512), "tool-rack-1": ("height", 1.6, 512),
}
METAL = set()


def _read(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError(f"{path.name} is not a binary glTF")
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    offset = 20 + json_length
    binary_length = struct.unpack_from("<I", data, offset)[0]
    return document, data[offset + 8:offset + 8 + binary_length]


def _view(document: dict, binary: bytes, index: int) -> bytes:
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def _positions(document: dict, binary: bytes, accessor_index: int) -> np.ndarray:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    if accessor.get("componentType") != 5126 or accessor["type"] != "VEC3" or view.get("byteStride"):
        raise ValueError("expected tightly packed float VEC3 positions")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return np.frombuffer(binary, dtype="<f4", count=accessor["count"] * 3, offset=start).reshape(-1, 3)


def _texture(payload: bytes, mime: str, size: int) -> tuple[bytes, str]:
    image = Image.open(io.BytesIO(payload))
    image.load()
    if max(image.size) > size:
        image = image.resize((size, size) if image.size[0] == image.size[1]
                             else (size, round(size * image.size[1] / image.size[0])), Image.LANCZOS)
    out = io.BytesIO()
    if mime == "image/png":
        image.save(out, "PNG", optimize=True)
    else:
        image.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue(), mime


def _local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    x, y, z, w = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    out = np.eye(4)
    out[:3, :3] = rotation * np.array(node.get("scale", [1.0, 1.0, 1.0]), dtype=np.float64)
    out[:3, 3] = node.get("translation", [0.0, 0.0, 0.0])
    return out


def _bake_node_transforms(document: dict, binary: bytes) -> bytes:
    """Moves every mesh node's world transform into its vertices (positions, and normals and tangents
    by the matching linear maps) and leaves every node untransformed. Some deliveries size a model with
    wrapper nodes rather than in its vertices; baked, every model is measured as it looks."""
    world: dict[int, np.ndarray] = {}

    def visit(index: int, parent: np.ndarray) -> None:
        world[index] = parent @ _local_matrix(document["nodes"][index])
        for child in document["nodes"][index].get("children", []):
            visit(child, world[index])

    for root in document["scenes"][document.get("scene", 0)]["nodes"]:
        visit(root, np.eye(4))
    out = bytearray(binary)
    done: dict[int, int] = {}
    for index, node in enumerate(document["nodes"]):
        if "mesh" not in node:
            continue
        matrix = world.get(index, np.eye(4))
        if np.array_equal(matrix, np.eye(4)):
            continue                                  # nothing to bake; leave the arrays untouched
        linear = matrix[:3, :3]
        normal_map = np.linalg.inv(linear).T
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            for key, accessor_index in primitive["attributes"].items():
                if key not in ("POSITION", "NORMAL", "TANGENT"):
                    continue
                if accessor_index in done:
                    if done[accessor_index] != index:
                        raise ValueError("a vertex array shared by two mesh nodes cannot be baked")
                    continue
                done[accessor_index] = index
                accessor = document["accessors"][accessor_index]
                view = document["bufferViews"][accessor["bufferView"]]
                columns = 4 if key == "TANGENT" else 3
                if accessor.get("componentType") != 5126 or view.get("byteStride"):
                    raise ValueError(f"expected tightly packed float {key}")
                start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
                values = np.frombuffer(bytes(out[start:start + accessor["count"] * columns * 4]),
                                       dtype="<f4").reshape(-1, columns).astype(np.float64)
                if key == "POSITION":
                    values = values @ linear.T + matrix[:3, 3]
                    accessor["min"] = [float(v) for v in values.min(axis=0)]
                    accessor["max"] = [float(v) for v in values.max(axis=0)]
                else:
                    turned = values[:, :3] @ (normal_map if key == "NORMAL" else linear).T
                    turned /= np.maximum(np.linalg.norm(turned, axis=1, keepdims=True), 1e-12)
                    values[:, :3] = turned
                    if key == "TANGENT" and np.linalg.det(linear) < 0:
                        values[:, 3] = -values[:, 3]
                out[start:start + values.size * 4] = values.astype("<f4").tobytes()
    for node in document["nodes"]:
        for key in ("matrix", "translation", "rotation", "scale"):
            node.pop(key, None)
    return bytes(out)


def prepare(source: Path, name: str) -> tuple[bytes, dict[str, bytes]]:
    """The prototype's bytes, and the texture files it references by name."""
    measure, metres, texture_size = SIZES[name]
    document, binary = _read(source)
    binary = _bake_node_transforms(document, binary)
    position_accessors = sorted({primitive["attributes"]["POSITION"]
                                 for mesh in document["meshes"] for primitive in mesh["primitives"]})
    points = np.concatenate([_positions(document, binary, index) for index in position_accessors])
    low, high = points.min(axis=0), points.max(axis=0)
    size = high - low
    scale = metres / (size[1] if measure == "height" else max(size[0], size[2]))
    shift = np.array([-(low[0] + high[0]) / 2, -low[1], -(low[2] + high[2]) / 2], dtype=np.float64)
    replaced: dict[int, bytes] = {}
    for index in position_accessors:
        accessor = document["accessors"][index]
        moved = ((_positions(document, binary, index).astype(np.float64) + shift) * scale).astype("<f4")
        accessor["min"] = [float(v) for v in moved.min(axis=0)]
        accessor["max"] = [float(v) for v in moved.max(axis=0)]
        if accessor.get("byteOffset", 0) != 0:
            raise ValueError("expected positions at the start of their buffer view")
        view = _view(document, binary, accessor["bufferView"])
        replaced[accessor["bufferView"]] = moved.tobytes() + view[moved.nbytes:]
    textures: dict[str, bytes] = {}
    image_views = set()
    for image in document.get("images", []):
        payload = _view(document, binary, image["bufferView"])
        encoded, mime = _texture(payload, image.get("mimeType", "image/png"), texture_size)
        file = hashlib.sha256(encoded).hexdigest() + (".png" if mime == "image/png" else ".jpg")
        textures[file] = encoded
        image_views.add(image.pop("bufferView"))
        image["uri"] = "../textures/" + file
        image["mimeType"] = mime
    for material in document.get("materials", []):
        if name not in METAL:
            material.setdefault("pbrMetallicRoughness", {})["metallicFactor"] = 0.0
    for node in document["nodes"]:
        node.pop("matrix", None)
    document["nodes"][0]["name"] = "kit-" + name
    document["asset"] = {"version": "2.0", "generator": "Eloria Whitehorn prepare_meshy_kit"}
    # Rebuild the buffer view by view, 4-byte aligned, without the images.
    out = bytearray()
    kept, renumber = [], {}
    for index, view in enumerate(document["bufferViews"]):
        if index in image_views:
            continue
        payload = replaced.get(index, _view(document, binary, index))
        while len(out) % 4:
            out.append(0)
        view["byteOffset"] = len(out)
        view["byteLength"] = len(payload)
        out.extend(payload)
        renumber[index] = len(kept)
        kept.append(view)
    document["bufferViews"] = kept
    for accessor in document["accessors"]:
        accessor["bufferView"] = renumber[accessor["bufferView"]]
    while len(out) % 4:
        out.append(0)
    document["buffers"] = [{"byteLength": len(out)}]
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(out)
    return (b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
            + struct.pack("<II", len(out), 0x004E4942) + bytes(out)), textures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, nargs="+", required=True,
                        help="folders holding the generated kit-*.glb, searched in order")
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    record = {"schema": "eloria-prepared-kit-v1", "tool": "prepare_meshy_kit.py", "models": {}}
    stale = []
    for name in sorted(SIZES):
        source = next((folder / f"kit-{name}.glb" for folder in args.input
                       if (folder / f"kit-{name}.glb").exists()), args.input[0] / f"kit-{name}.glb")
        payload, textures = prepare(source, name)
        target = PROTOTYPES / f"kit-{name}.glb"
        record["models"][name] = {"input": hashlib.sha256(source.read_bytes()).hexdigest(),
                                  "output": hashlib.sha256(payload).hexdigest(),
                                  "textures": sorted(textures),
                                  "measure": SIZES[name][0], "metres": SIZES[name][1],
                                  "texturePixels": SIZES[name][2]}
        if args.check:
            if not target.exists() or target.read_bytes() != payload or any(
                    not (TEXTURES / file).exists() or (TEXTURES / file).read_bytes() != data
                    for file, data in textures.items()):
                stale.append(name)
            continue
        target.write_bytes(payload)
        for file, data in textures.items():
            (TEXTURES / file).write_bytes(data)
        print(f"{target.name}: {len(payload) // 1024} KB")
    if args.check:
        if stale:
            print("stale: " + ", ".join(stale))
            return 1
        return 0
    RECORD.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
