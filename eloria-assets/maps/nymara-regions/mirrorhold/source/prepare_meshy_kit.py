"""Seat generated Mirrorhold models in the territory kit at their real size.

The alpine trees and plants, snow-capped rock, mirror and lens works, civic
street props and lakeshore pieces generated for Mirrorhold (from
work-output/mirrorhold-2026-09-27/asset-prompts.md), and the Verdant Stair models
this mountain bowl shares (mossy crags and boulders, saplings, meadow flowers,
flowering shrubs, reeds), arrive normalised to a one-unit cube centred on the
origin, with 2K textures and a metallic factor of one. This rewrites each as a
territory prototype (`godot-client/world_authoring/regions/mirrorhold/assets/
prototypes/`): scaled so its height (or its length, for pieces that lie flat) is
the one in SIZES, moved so the centre of its base stands on the origin, textures
shrunk to 1024 or 512 px and written once, content-addressed, to the territory's
`assets/textures/` and referenced by URI, and non-metallic unless it is metal.
Geometry is otherwise left exactly as generated. It is Sunmane's
`prepare_meshy_kit.py` with this kit's sizes, reading several folders.

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
PROTOTYPES = CLIENT / "godot-client/world_authoring/regions/mirrorhold/assets/prototypes"
TEXTURES = PROTOTYPES.parent / "textures"
RECORD = HERE / "prepare-meshy-kit.json"

# name -> (measure, metres, texture px). "height" scales the model to that
# height; "length" scales its longest horizontal side, for pieces that lie flat.
SIZES = {
    # generated for Mirrorhold
    "alpine-fir-tree-1": ("height", 9.0, 1024), "alpine-fir-tree-2": ("height", 12.0, 1024),
    "alpine-flower-cushion-1": ("length", 1.5, 512), "drinking-fountain-1": ("height", 2.2, 512),
    "flower-planter-1": ("length", 2.0, 512), "giant-lens-stand-1": ("height", 3.5, 1024),
    "glassware-handcart-1": ("length", 2.4, 512), "heron-weathervane-1": ("height", 3.0, 512),
    "juniper-shrub-1": ("length", 2.2, 512), "laundry-line-rack-1": ("height", 2.2, 512),
    "lens-crate-basket-1": ("height", 0.8, 512), "lens-grinder-bench-1": ("height", 1.6, 512),
    "lens-sign-rack-1": ("height", 2.6, 512), "lens-tripod-1": ("height", 1.8, 512),
    "mirror-obelisk-1": ("height", 5.0, 1024), "mirrorhold-banner-pole-1": ("height", 4.0, 512),
    "mirrorhold-market-stall-1": ("height", 3.2, 1024), "mooring-posts-1": ("height", 1.4, 512),
    "mountain-pine-tree-1": ("height", 7.0, 1024), "potted-cypress-tree-1": ("height", 2.4, 512),
    "rowing-boat-1": ("length", 4.0, 512),
    "snow-scree-1": ("length", 3.5, 512), "snow-scree-2": ("length", 4.0, 512),
    "snowcap-boulder-1": ("height", 3.5, 1024), "snowcap-boulder-2": ("height", 5.0, 1024),
    "snowcap-boulder-3": ("height", 2.5, 1024),
    "stone-bench-1": ("length", 2.0, 512), "stone-landing-stage-1": ("length", 6.0, 1024),
    "sun-mirror-1": ("height", 3.0, 1024), "sundial-plinth-1": ("height", 1.4, 512),
    "tussock-grass-1": ("height", 0.8, 512),
    # shared with Verdant Stair
    "mossy-crag-1": ("height", 16.0, 1024), "mossy-crag-2": ("height", 20.0, 1024),
    "mossy-crag-3": ("height", 14.0, 1024), "mossy-crag-5": ("height", 22.0, 1024),
    "mossy-boulder-1": ("height", 2.4, 1024), "mossy-boulder-2": ("height", 3.2, 1024),
    "mossy-boulder-3": ("height", 1.8, 1024), "mossy-boulder-5": ("height", 2.6, 1024),
    "sapling-tree-1": ("height", 5.0, 1024), "sapling-tree-2": ("height", 4.4, 1024),
    "flower-meadow-1": ("length", 2.6, 512), "flower-meadow-2": ("length", 2.4, 512),
    "flower-meadow-3": ("length", 2.8, 512), "flower-meadow-4": ("length", 2.2, 512),
    "flower-shrub-1": ("height", 1.4, 512), "flower-shrub-2": ("height", 1.2, 512),
    "flower-shrub-3": ("height", 1.6, 512),
    "river-reed-1": ("height", 1.6, 512), "river-reed-3": ("height", 1.8, 512),
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
    document["asset"] = {"version": "2.0", "generator": "Eloria Mirrorhold prepare_meshy_kit"}
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
