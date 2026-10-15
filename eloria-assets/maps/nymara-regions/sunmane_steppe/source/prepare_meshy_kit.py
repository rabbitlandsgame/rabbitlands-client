"""Seat generated steppe models in the territory kit at their real size.

The ground cover, rock and herding models generated for Sunmane arrive
normalised to a one-unit cube centred on the origin, with 2K textures and a
metallic factor of one. This rewrites each as a territory prototype
(`godot-client/world_authoring/regions/sunmane_steppe/assets/prototypes/`):
scaled so its height (or its length, for the flat talus) is the one in SIZES,
moved so the centre of its base stands on the origin, textures shrunk to 1024
or 512 px and written once, content-addressed, to the territory's
`assets/textures/` and referenced by URI (the kit's convention, so importing
extracts nothing beside the model), and non-metallic unless it is metal.
Geometry is otherwise left exactly as generated.

sagebrush-3, saltbush-1 and saltbush-2 were generated with their background
card fused to the plant, so they are left out.

`python prepare_meshy_kit.py --input <folder of kit-*.glb>` writes the kit and
`prepare-meshy-kit.json` (the SHA-256 of every input and output); `--check`
confirms the committed files are what the recorded inputs produce.
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
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/sunmane_steppe/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "prepare-meshy-kit.json"

# name -> (measure, metres, texture px). "height" scales the model to that
# height; "length" scales its longest horizontal side, for pieces that lie flat.
SIZES = {
    "autumn-shrub-1": ("height", 1.6, 512), "autumn-shrub-2": ("height", 2.0, 512),
    "autumn-shrub-3": ("height", 1.3, 512),
    "coastal-boulders-1": ("height", 6.0, 1024), "coastal-boulders-2": ("height", 7.0, 1024),
    "coastal-boulders-3": ("height", 4.5, 1024), "coastal-boulders-4": ("height", 6.5, 1024),
    "feather-grass-1": ("height", 0.45, 512), "feather-grass-2": ("height", 0.8, 512),
    "feather-grass-3": ("height", 0.7, 512), "feather-grass-4": ("height", 0.55, 512),
    "feed-sacks-1": ("height", 0.8, 512), "hay-feeder-1": ("height", 1.2, 512),
    "hitching-rail-1": ("height", 1.2, 512), "horse-blanket-1": ("height", 1.1, 512),
    "mesa-corner-1": ("height", 5.5, 1024), "mesa-corner-2": ("height", 5.5, 1024),
    "mesa-face-1": ("height", 5.5, 1024), "mesa-face-2": ("height", 5.5, 1024),
    "mesa-face-3": ("height", 5.5, 1024), "mesa-face-4": ("height", 4.5, 1024),
    "mesa-hoodoo-1": ("height", 8.0, 1024),
    "mesa-talus-1": ("length", 2.6, 512), "mesa-talus-2": ("length", 2.0, 512),
    "mesa-talus-3": ("length", 1.6, 512),
    "milk-churn-1": ("height", 0.9, 512), "saddle-rack-1": ("height", 1.3, 512),
    "sagebrush-1": ("height", 0.8, 512), "sagebrush-2": ("height", 1.2, 512),
    "saxaul-1": ("height", 4.5, 1024), "saxaul-2": ("height", 4.0, 1024),
    "saxaul-3": ("height", 3.5, 1024),
    "shrine-cairn-1": ("height", 2.2, 1024), "shrine-cairn-2": ("height", 2.0, 1024),
    "tumbleweed-1": ("height", 0.6, 512), "tumbleweed-2": ("height", 0.9, 512),
    "wooden-pail-1": ("height", 0.4, 512), "wooden-pail-2": ("height", 0.35, 512),
}
METAL = {"milk-churn-1"}


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


def prepare(source: Path, name: str) -> tuple[bytes, dict[str, bytes]]:
    """The prototype's bytes, and the texture files it references by name."""
    measure, metres, texture_size = SIZES[name]
    document, binary = _read(source)
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
    document["asset"] = {"version": "2.0", "generator": "Eloria Sunmane prepare_meshy_kit"}
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
    parser.add_argument("--input", type=Path, required=True, help="folder holding the generated kit-*.glb")
    parser.add_argument("--check", action="store_true", help="verify, do not write")
    args = parser.parse_args()
    record = {"schema": "eloria-prepared-kit-v1", "tool": "prepare_meshy_kit.py", "models": {}}
    stale = []
    for name in sorted(SIZES):
        source = args.input / f"kit-{name}.glb"
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
