"""Prepared Meshy Whitehorn cave asset and deterministic toolkit adapter.

The vendor GLB remains the reviewable source artifact.  This module validates
its identity and narrow glTF contract, then exposes the original indexed
positions, normals and UVs to Whitehorn's existing exporter without welding
texture seams or re-encoding the embedded JPEG textures.

This asset is not active production content. Future activation must add both
this adapter and the binary asset to the regional library input certificate.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np

from amberwood import gltf as GLTF
from amberwood import mesh as M

ASSET = Path(__file__).resolve().parent / "model-reference.glb"
ASSET_SHA256 = "44b0f68e60fa26e200ecccf0a09318e946e611b77ee9b7a3ee96b30a23249873"
MESHY_TASK_ID = "01a0b927-06cb-725a-9639-ac8a2091b1aa"
MESHY_CREDITS = 15
MATERIAL = "whitehorn_cave_v001"
SCALE = 16.0
NOMINAL_SPAN = 7.5
YAW_RADIANS = math.pi
PASSAGE_FLOOR_Y = -0.23254863242764562
WALK_FLOOR_TOP_Y = 0.245
TRANSLATION_Y = WALK_FLOOR_TOP_Y - SCALE * PASSAGE_FLOOR_Y
EXPECTED_VERTICES = 5770
EXPECTED_TRIANGLES = 3859
EXPECTED_IMAGE_SHA256 = (
    "8d51cf70456b91bfb08a623c10b8ccb8f82b9348926331dd1bbfb70f11c3722a",
    "0ea3f6fb908d478b53aebc4bb371a7a6fb0cc24186b5f1022f5024aff7dcbbe5",
    "e07e2eed47158bc7371f96e2b70d6089b16026482558f56a949d37b42e0641ff",
)
IMAGE_NAMES = ("whitehorn_cave_base", "whitehorn_cave_orm", "whitehorn_cave_normal")

_COMPONENT_TYPES = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def _document() -> tuple[dict, bytes]:
    raw = ASSET.read_bytes()
    actual = _digest(raw)
    if actual != ASSET_SHA256:
        raise ValueError(f"Whitehorn cave source SHA-256 changed: {actual}")
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError("Whitehorn cave source is not a GLB")
    magic, version, total = struct.unpack_from("<4sII", raw, 0)
    if magic != b"glTF" or version != 2 or total != len(raw):
        raise ValueError("Whitehorn cave GLB header is invalid")
    offset = 12
    document = None
    binary = None
    while offset < len(raw):
        length, kind = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        payload = raw[offset:offset+length]
        offset += length
        if kind == b"JSON":
            document = json.loads(payload.rstrip(b" \t\r\n\0"))
        elif kind == b"BIN\0":
            binary = payload
    if document is None or binary is None:
        raise ValueError("Whitehorn cave GLB must embed JSON and BIN chunks")
    _validate(document, binary)
    return document, binary


def _view_bytes(document: dict, binary: bytes, view_index: int) -> bytes:
    view = document["bufferViews"][view_index]
    if view.get("buffer", 0) != 0:
        raise ValueError("Whitehorn cave GLB must use its embedded buffer")
    start = int(view.get("byteOffset", 0))
    return binary[start:start+int(view["byteLength"])]


def _accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    if "sparse" in accessor or "bufferView" not in accessor:
        raise ValueError("Whitehorn cave GLB uses an unsupported sparse accessor")
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(_COMPONENT_TYPES[accessor["componentType"]]).newbyteorder("<")
    width = _TYPE_WIDTHS[accessor["type"]]
    count = int(accessor["count"])
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride", dtype.itemsize * width))
    if stride == dtype.itemsize * width:
        return np.frombuffer(binary, dtype=dtype, count=count*width, offset=start).reshape(count, width).copy()
    result = np.empty((count, width), dtype=dtype)
    for row in range(count):
        result[row] = np.frombuffer(binary, dtype=dtype, count=width, offset=start+row*stride)
    return result


def _image_bytes(document: dict, binary: bytes, index: int) -> bytes:
    image = document["images"][index]
    if image.get("mimeType") != "image/jpeg" or "bufferView" not in image:
        raise ValueError("Whitehorn cave textures must be embedded JPEG images")
    return _view_bytes(document, binary, image["bufferView"])


def _validate(document: dict, binary: bytes) -> None:
    expected_counts = {
        "scenes": 1, "nodes": 1, "meshes": 1, "materials": 1,
        "textures": 3, "images": 3,
    }
    for key, expected in expected_counts.items():
        if len(document.get(key, [])) != expected:
            raise ValueError(f"Whitehorn cave GLB expected {expected} {key}")
    if document.get("animations") or document.get("skins"):
        raise ValueError("Whitehorn cave GLB unexpectedly contains animation or skin data")
    node = document["nodes"][0]
    identity = [1.0, 0.0, 0.0, 0.0,
                0.0, 1.0, 0.0, 0.0,
                0.0, 0.0, 1.0, 0.0,
                0.0, 0.0, 0.0, 1.0]
    unexpected_trs = any(key in node for key in ("translation", "rotation", "scale"))
    if (node.get("mesh") != 0 or unexpected_trs
            or ("matrix" in node and node["matrix"] != identity)):
        raise ValueError("Whitehorn cave GLB node transform contract changed")
    primitives = document["meshes"][0].get("primitives", [])
    if len(primitives) != 1 or primitives[0].get("mode", 4) != 4:
        raise ValueError("Whitehorn cave GLB must contain one triangle primitive")
    primitive = primitives[0]
    if primitive.get("material") != 0:
        raise ValueError("Whitehorn cave GLB primitive material contract changed")
    if set(primitive.get("attributes", {})) != {"POSITION", "NORMAL", "TEXCOORD_0"}:
        raise ValueError("Whitehorn cave GLB vertex attribute contract changed")
    positions = _accessor(document, binary, primitive["attributes"]["POSITION"])
    indices = _accessor(document, binary, primitive["indices"]).reshape(-1)
    if len(positions) != EXPECTED_VERTICES or len(indices) != EXPECTED_TRIANGLES * 3:
        raise ValueError("Whitehorn cave GLB vertex/triangle counts changed")
    material = document["materials"][0]
    pbr = material.get("pbrMetallicRoughness", {})
    expected_textures = (
        pbr.get("baseColorTexture", {}).get("index"),
        pbr.get("metallicRoughnessTexture", {}).get("index"),
        material.get("normalTexture", {}).get("index"),
    )
    if expected_textures != (0, 1, 2) or material.get("doubleSided") is not True:
        raise ValueError("Whitehorn cave GLB material contract changed")
    if tuple(texture.get("source") for texture in document["textures"]) != (0, 1, 2):
        raise ValueError("Whitehorn cave GLB texture/image mapping changed")
    for index, expected in enumerate(EXPECTED_IMAGE_SHA256):
        actual = _digest(_image_bytes(document, binary, index))
        if actual != expected:
            raise ValueError(f"Whitehorn cave embedded texture {index} changed: {actual}")


def _raw_mesh() -> M.Mesh:
    document, binary = _document()
    primitive = document["meshes"][0]["primitives"][0]
    attributes = primitive["attributes"]
    return M.Mesh(
        positions=_accessor(document, binary, attributes["POSITION"]).astype(np.float64),
        normals=_accessor(document, binary, attributes["NORMAL"]).astype(np.float64),
        uvs=_accessor(document, binary, attributes["TEXCOORD_0"]).astype(np.float64),
        indices=_accessor(document, binary, primitive["indices"]).reshape(-1).astype(np.int64),
        material=MATERIAL,
    )


def source_mesh(scale: float = SCALE,
                floor_top_y: float = WALK_FLOOR_TOP_Y) -> M.Mesh:
    """Return a fresh fitted mesh; callers may reuse another uniform scale."""
    if scale <= 0.0:
        raise ValueError("Whitehorn cave scale must be positive")
    mesh = _raw_mesh()
    translation_y = float(floor_top_y) - float(scale) * PASSAGE_FLOOR_Y
    transform = (M.translation(0.0, translation_y, 0.0)
                 @ M.rotation_y(YAW_RADIANS) @ M.scaling(scale))
    return mesh.transform(transform)


def scale_for_span(span: float) -> float:
    """Preserve the reviewed primary fit while supporting real kit variants."""
    if span <= 0.0:
        raise ValueError("Whitehorn cave span must be positive")
    return SCALE * float(span) / NOMINAL_SPAN


def register_material(builder: GLTF.GltfBuilder) -> None:
    """Register exact embedded JPEGs and the approved PBR material."""
    document, binary = _document()
    for index, name in enumerate(IMAGE_NAMES):
        image_index = builder.add_image(name, _image_bytes(document, binary, index))
        image = builder._images[image_index]
        if image.get("name") != name:
            raise ValueError(f"Whitehorn cave image registration collision: {name}")
        # The shared writer predates JPEG source assets and defaults add_image
        # to PNG. This model owns these unique records, so correct only their
        # declared MIME type while retaining the byte-exact embedded payload.
        image["mimeType"] = "image/jpeg"
    material_index = builder.add_material(GLTF.Material(
        name=MATERIAL,
        base_color_texture=IMAGE_NAMES[0],
        orm_texture=IMAGE_NAMES[1],
        normal_texture=IMAGE_NAMES[2],
        metallic=1.0,
        roughness=1.0,
        double_sided=True,
    ))
    # The source uses this image only for metallic/roughness; the shared
    # material helper assumes every ORM image also carries occlusion.
    builder._materials[material_index].pop("occlusionTexture", None)


def embedded_texture_bytes() -> int:
    document, binary = _document()
    return sum(len(_image_bytes(document, binary, index)) for index in range(3))


def provenance() -> dict:
    return {
        "generator": "Meshy",
        "taskId": MESHY_TASK_ID,
        "credits": MESHY_CREDITS,
        "source": ASSET.relative_to(Path(__file__).resolve().parent).as_posix(),
        "sha256": ASSET_SHA256,
        "triangles": EXPECTED_TRIANGLES,
        "textureResolution": "2048x2048",
        "ownerApprovalDate": "2026-09-19",
        "ownerApprovalRecord": "owner-review/map-assets/whitehorn-ice-cave-mouth/v001/approval.json",
    }
