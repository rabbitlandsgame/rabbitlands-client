"""Seat generated Amberwood models in the territory kit at their real size.

The great amber oak, copper beech, crimson maple, golden larch, aspens, sweet
chestnut and dark fir, the autumn ferns, toadstool ring, bramble and leaf pile,
the resin-tapped pine, amber drying rack, woodcutter's block, sawhorse, hunter's
hide, forest shrine, mushroom basket and cider press, and the cottages,
treehouse and watermill generated for Amberwood (from
work-output/amberwood-2026-09-28/asset-prompts.md), and the models the wood
shares with other territories (Four Gates' autumn trees, apple trees, fallen
leaves, farm pieces and notice board; Verdant Stair's mossy logs, stumps and
boulders, undergrowth, saplings, stream stones, waterfall rocks, reeds,
baskets, skeps and herb racks; Sunmane's autumn shrubs, sacks, churn and
pails; Grey Moors' bracken), are rewritten as territory prototypes
(`godot-client/world_authoring/regions/amberwood/assets/prototypes/`): wrapper-
node transforms baked into the vertices, then scaled so the height (or the
length, for pieces that lie flat or are long) is the one in SIZES, the centre
of the base on the origin, textures shrunk to 1024 or 512 px and written once,
content-addressed, to the territory's `assets/textures/` and referenced by URI,
and non-metallic unless metal. Geometry is otherwise left exactly as
generated. It is Sunmane's `prepare_meshy_kit.py` with this kit's sizes,
reading several folders.

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
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/amberwood/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "prepare-meshy-kit.json"

# name -> (measure, metres, texture px). "height" scales the model to that
# height; "length" scales its longest horizontal side, for pieces that lie flat.
SIZES = {
    # generated for Amberwood
    "amber-cottage-1": ("length", 7.0, 1024), "amber-cottage-2": ("length", 8.0, 1024),
    "amber-drying-rack-1": ("length", 2.2, 512), "aspen-clump-1": ("height", 10.0, 1024),
    "autumn-fern-1": ("length", 2.0, 512), "bramble-1": ("length", 2.5, 512),
    "cider-press-1": ("height", 2.5, 512), "copper-beech-1": ("height", 13.0, 1024),
    "crimson-maple-1": ("height", 9.0, 1024), "dark-fir-1": ("height", 12.0, 1024),
    "forest-shrine-1": ("height", 2.5, 512), "golden-larch-1": ("height", 14.0, 1024),
    "great-amber-oak-1": ("height", 16.0, 1024), "hunter-hide-1": ("height", 5.0, 512),
    "leaf-pile-1": ("length", 2.0, 512), "mushroom-basket-1": ("height", 0.6, 512),
    "resin-tapped-pine-1": ("height", 9.0, 1024), "sawhorse-1": ("length", 2.0, 512),
    "sweet-chestnut-1": ("height", 12.0, 1024), "toadstool-ring-1": ("length", 2.5, 512),
    "treehouse-1": ("height", 10.0, 1024), "watermill-1": ("length", 9.0, 1024),
    "woodcutter-block-1": ("length", 1.5, 512),
    # shared with four-gates
    "hay-stack-1": ("height", 3.5, 512),
    "wheat-stooks-1": ("height", 1.6, 512),
    "apple-cart-1": ("length", 2.4, 512),
    "apple-tree-1": ("height", 5.0, 1024),
    "autumn-maple-tree-1": ("height", 8.0, 1024),
    "autumn-maple-tree-2": ("height", 7.0, 1024),
    "cabbage-rows-1": ("length", 4.0, 512),
    "fallen-leaves-1": ("length", 3.0, 512),
    "fallen-leaves-2": ("length", 4.0, 512),
    "golden-birch-tree-1": ("height", 10.0, 1024),
    "notice-board-1": ("height", 2.2, 512),
    "pumpkin-patch-1": ("length", 4.0, 512),
    "russet-oak-tree-1": ("height", 11.0, 1024),
    "scarecrow-1": ("height", 2.2, 512),
    "split-rail-fence-1": ("length", 4.0, 512),
    "wheelbarrow-1": ("length", 1.6, 512),
    # shared with verdant_stair
    "beehive-skeps-1": ("height", 1.3, 512),
    "harvest-baskets-1": ("height", 0.6, 512),
    "herb-drying-rack-1": ("height", 1.9, 512),
    "hollow-log-1": ("length", 5.0, 1024),
    "mossy-boulder-1": ("height", 2.4, 1024),
    "mossy-boulder-2": ("height", 3.2, 1024),
    "mossy-boulder-3": ("height", 1.8, 1024),
    "mossy-boulder-4": ("length", 3.8, 1024),
    "mossy-boulder-5": ("height", 2.6, 1024),
    "mossy-log-1": ("length", 7.0, 1024),
    "mossy-log-2": ("length", 6.0, 1024),
    "mossy-stump-1": ("height", 1.8, 512),
    "mossy-stump-2": ("height", 1.2, 512),
    "river-reed-1": ("height", 1.6, 512),
    "river-reed-2": ("height", 1.3, 512),
    "river-reed-3": ("height", 1.8, 512),
    "river-stones-1": ("length", 2.8, 512),
    "river-stones-2": ("length", 2.4, 512),
    "sapling-tree-1": ("height", 5.0, 1024),
    "sapling-tree-2": ("height", 4.4, 1024),
    "undergrowth-1": ("height", 1.4, 512),
    "undergrowth-2": ("height", 1.3, 512),
    "undergrowth-3": ("height", 1.0, 512),
    "undergrowth-4": ("height", 1.2, 512),
    "undergrowth-5": ("length", 2.0, 512),
    "waterfall-rocks-1": ("length", 13.0, 1024),
    "waterfall-rocks-2": ("length", 12.0, 1024),
    # shared with sunmane_steppe
    "autumn-shrub-1": ("height", 1.6, 512),
    "autumn-shrub-2": ("height", 2.0, 512),
    "autumn-shrub-3": ("height", 1.3, 512),
    "feed-sacks-1": ("height", 0.8, 512),
    "milk-churn-1": ("height", 0.9, 512),
    "wooden-pail-1": ("height", 0.4, 512),
    "wooden-pail-2": ("height", 0.35, 512),
    # shared with grey_moors
    "bracken-patch-1": ("length", 3.0, 512),
}

METAL = set()
# delivered with their waterline, not their keel, at the origin
WATERLINE: set = set()   # nothing in this kit floats


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
    # Boats and buoys keep their waterline at the origin (their hulls reach below it); every other
    # piece stands the centre of its base on the origin.
    rise = 0.0 if name in WATERLINE else -low[1]
    shift = np.array([-(low[0] + high[0]) / 2, rise, -(low[2] + high[2]) / 2], dtype=np.float64)
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
    document["asset"] = {"version": "2.0", "generator": "Eloria Amberwood prepare_meshy_kit"}
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
