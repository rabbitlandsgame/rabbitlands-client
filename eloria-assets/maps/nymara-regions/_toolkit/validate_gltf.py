#!/usr/bin/env python3
"""Standalone glTF 2.0 / GLB validator.

Written for this project because the Khronos gltf-validator binary cannot be
fetched in the build environment. It implements the structural and semantic
checks that matter for the Godot GLTFDocument import path, and reports
errors / warnings / infos in the same shape as the Khronos tool so the result
can be committed next to the asset like the Four Gates report.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from datetime import datetime, timezone

import numpy as np

VALIDATOR_VERSION = "eloria-gltf-validate-1.1.0"

COMPONENT = {
    5120: ("BYTE", np.int8, 1), 5121: ("UNSIGNED_BYTE", np.uint8, 1),
    5122: ("SHORT", np.int16, 2), 5123: ("UNSIGNED_SHORT", np.uint16, 2),
    5125: ("UNSIGNED_INT", np.uint32, 4), 5126: ("FLOAT", np.float32, 4),
}
TYPE_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4,
              "MAT2": 4, "MAT3": 9, "MAT4": 16}


class Report:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.messages: list[dict] = []

    def add(self, severity: int, code: str, message: str, pointer: str = "") -> None:
        self.messages.append({"code": code, "message": message,
                              "severity": severity, "pointer": pointer})

    def error(self, code, message, pointer=""):
        self.add(0, code, message, pointer)

    def warning(self, code, message, pointer=""):
        self.add(1, code, message, pointer)

    def info(self, code, message, pointer=""):
        self.add(2, code, message, pointer)

    def counts(self) -> dict:
        return {
            "numErrors": sum(1 for m in self.messages if m["severity"] == 0),
            "numWarnings": sum(1 for m in self.messages if m["severity"] == 1),
            "numInfos": sum(1 for m in self.messages if m["severity"] == 2),
            "numHints": sum(1 for m in self.messages if m["severity"] == 3),
        }

    def to_dict(self) -> dict:
        counts = self.counts()
        counts["messages"] = self.messages
        return {
            "uri": self.uri,
            "mimeType": "model/gltf-binary",
            "validatorVersion": VALIDATOR_VERSION,
            "validatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "issues": counts,
        }


def parse_glb(path: str, report: Report):
    data = open(path, "rb").read()
    if len(data) < 12:
        report.error("GLB_TOO_SHORT", "File is shorter than a GLB header.")
        return None, None
    magic, version, length = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:
        report.error("GLB_INVALID_MAGIC", "Invalid GLB magic.")
        return None, None
    if version != 2:
        report.error("GLB_INVALID_VERSION", f"Unsupported GLB version {version}.")
    if length != len(data):
        report.error("GLB_LENGTH_MISMATCH",
                     f"Declared length {length} != actual {len(data)}.")
    offset = 12
    json_chunk = None
    bin_chunk = b""
    index = 0
    while offset + 8 <= len(data):
        chunk_length, chunk_type = struct.unpack("<II", data[offset:offset + 8])
        payload = data[offset + 8:offset + 8 + chunk_length]
        if len(payload) < chunk_length:
            report.error("GLB_CHUNK_TRUNCATED", f"Chunk {index} truncated.")
            break
        if chunk_length % 4:
            report.error("GLB_CHUNK_LENGTH_UNALIGNED",
                         f"Chunk {index} length {chunk_length} is not 4-byte aligned.")
        if chunk_type == 0x4E4F534A:
            if index != 0:
                report.error("GLB_UNEXPECTED_BIN_CHUNK", "JSON chunk must be first.")
            json_chunk = payload
        elif chunk_type == 0x004E4942:
            bin_chunk = payload
        else:
            report.warning("GLB_UNKNOWN_CHUNK", f"Unknown chunk type 0x{chunk_type:08X}.")
        offset += 8 + chunk_length
        index += 1
    if json_chunk is None:
        report.error("GLB_MISSING_JSON", "No JSON chunk found.")
        return None, None
    try:
        document = json.loads(json_chunk.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        report.error("GLB_JSON_PARSE", f"JSON chunk is not valid JSON: {exc}")
        return None, None
    return document, bin_chunk


def read_accessor(document, binary, index):
    accessor = document["accessors"][index]
    name, dtype, size = COMPONENT[accessor["componentType"]]
    components = TYPE_COUNT[accessor["type"]]
    count = accessor["count"]
    view = document["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride")
    if stride and stride != size * components:
        out = np.zeros((count, components), dtype=dtype)
        for i in range(count):
            chunk = binary[start + i * stride:start + i * stride + size * components]
            out[i] = np.frombuffer(chunk, dtype=dtype)
        return out if components > 1 else out.reshape(-1)
    total = count * components
    raw = np.frombuffer(binary, dtype=dtype, count=total, offset=start)
    return raw.reshape(count, components) if components > 1 else raw


def validate(path: str) -> Report:
    report = Report(path.rsplit("/", 1)[-1])
    document, binary = parse_glb(path, report)
    if document is None:
        return report

    asset = document.get("asset", {})
    if asset.get("version") != "2.0":
        report.error("ASSET_VERSION", "asset.version must be '2.0'.", "/asset/version")

    for extension in document.get("extensionsRequired", []):
        report.error("UNSUPPORTED_EXTENSION_REQUIRED",
                     f"Required extension '{extension}' is not part of the runtime subset.",
                     "/extensionsRequired")

    buffers = document.get("buffers", [])
    for i, buffer in enumerate(buffers):
        if "uri" in buffer:
            report.error("BUFFER_EXTERNAL",
                         "Runtime GLB must be self-contained; external buffer URI found.",
                         f"/buffers/{i}/uri")
        if i == 0 and buffer.get("byteLength", 0) > len(binary):
            report.error("BUFFER_LENGTH",
                         f"buffers[0].byteLength {buffer.get('byteLength')} exceeds "
                         f"BIN chunk {len(binary)}.", "/buffers/0")

    views = document.get("bufferViews", [])
    for i, view in enumerate(views):
        end = view.get("byteOffset", 0) + view["byteLength"]
        if end > len(binary):
            report.error("BUFFER_VIEW_OUT_OF_RANGE",
                         f"bufferView {i} ends at {end} beyond BIN chunk {len(binary)}.",
                         f"/bufferViews/{i}")
        if view.get("byteOffset", 0) % 4 and view.get("target"):
            report.warning("BUFFER_VIEW_ALIGNMENT",
                           "bufferView byteOffset should be 4-byte aligned.",
                           f"/bufferViews/{i}/byteOffset")

    accessors = document.get("accessors", [])
    for i, accessor in enumerate(accessors):
        pointer = f"/accessors/{i}"
        if accessor.get("componentType") not in COMPONENT:
            report.error("ACCESSOR_COMPONENT_TYPE", "Unknown componentType.", pointer)
            continue
        if accessor.get("type") not in TYPE_COUNT:
            report.error("ACCESSOR_TYPE", "Unknown accessor type.", pointer)
            continue
        if "bufferView" not in accessor:
            report.warning("ACCESSOR_SPARSE_OR_ZERO",
                           "Accessor without bufferView is treated as zero-filled.", pointer)
            continue
        _, dtype, size = COMPONENT[accessor["componentType"]]
        components = TYPE_COUNT[accessor["type"]]
        view = views[accessor["bufferView"]]
        needed = accessor["count"] * components * size
        available = view["byteLength"] - accessor.get("byteOffset", 0)
        if needed > available:
            report.error("ACCESSOR_TOO_LONG",
                         f"Accessor needs {needed} bytes but bufferView provides {available}.",
                         pointer)
            continue
        values = read_accessor(document, binary, i)
        if "min" in accessor and "max" in accessor:
            actual_min = np.asarray(values).reshape(accessor["count"], components).min(axis=0)
            actual_max = np.asarray(values).reshape(accessor["count"], components).max(axis=0)
            if not np.allclose(actual_min, np.asarray(accessor["min"], dtype=np.float64),
                               rtol=1e-4, atol=1e-4):
                report.error("ACCESSOR_MIN_MISMATCH",
                             f"Declared min {accessor['min']} != actual {list(actual_min)}.",
                             pointer + "/min")
            if not np.allclose(actual_max, np.asarray(accessor["max"], dtype=np.float64),
                               rtol=1e-4, atol=1e-4):
                report.error("ACCESSOR_MAX_MISMATCH",
                             f"Declared max {accessor['max']} != actual {list(actual_max)}.",
                             pointer + "/max")
        if np.issubdtype(np.asarray(values).dtype, np.floating):
            if not np.all(np.isfinite(np.asarray(values))):
                report.error("ACCESSOR_NON_FINITE",
                             "Accessor contains NaN or infinity.", pointer)

    used_accessors: set[int] = set()
    used_materials: set[int] = set()
    meshes = document.get("meshes", [])
    for mesh_index, mesh in enumerate(meshes):
        for primitive_index, primitive in enumerate(mesh.get("primitives", [])):
            pointer = f"/meshes/{mesh_index}/primitives/{primitive_index}"
            mode = primitive.get("mode", 4)
            if mode != 4:
                report.error("PRIMITIVE_MODE",
                             "Runtime subset supports triangles (mode 4) only.", pointer)
            attributes = primitive.get("attributes", {})
            if "POSITION" not in attributes:
                report.error("PRIMITIVE_NO_POSITION", "POSITION attribute is required.", pointer)
                continue
            position_accessor = accessors[attributes["POSITION"]]
            if "min" not in position_accessor or "max" not in position_accessor:
                report.error("POSITION_ACCESSOR_NO_BOUNDS",
                             "POSITION accessor must declare min and max.",
                             f"/accessors/{attributes['POSITION']}")
            vertex_count = position_accessor["count"]
            for name, accessor_index in attributes.items():
                used_accessors.add(accessor_index)
                if accessors[accessor_index]["count"] != vertex_count:
                    report.error("ATTRIBUTE_COUNT_MISMATCH",
                                 f"Attribute {name} count differs from POSITION.", pointer)
            if "NORMAL" in attributes:
                normals = read_accessor(document, binary, attributes["NORMAL"]).astype(np.float64)
                lengths = np.linalg.norm(normals, axis=1)
                if np.any(np.abs(lengths - 1.0) > 5e-3):
                    worst = float(np.max(np.abs(lengths - 1.0)))
                    report.error("NORMAL_NOT_UNIT",
                                 f"NORMAL vectors must be unit length (worst deviation {worst:.4f}).",
                                 pointer + "/attributes/NORMAL")
            if "TANGENT" in attributes:
                tangents = read_accessor(document, binary, attributes["TANGENT"]).astype(np.float64)
                if tangents.shape[1] != 4:
                    report.error("TANGENT_TYPE", "TANGENT must be VEC4.", pointer)
                else:
                    w = tangents[:, 3]
                    if not np.all(np.isin(np.round(w, 3), (-1.0, 1.0))):
                        report.error("TANGENT_W", "TANGENT w must be +1 or -1.", pointer)
                    lengths = np.linalg.norm(tangents[:, :3], axis=1)
                    if np.any(np.abs(lengths - 1.0) > 5e-3):
                        report.error("TANGENT_NOT_UNIT", "TANGENT xyz must be unit length.",
                                     pointer)
            if "indices" in primitive:
                used_accessors.add(primitive["indices"])
                indices = read_accessor(document, binary, primitive["indices"])
                accessor = accessors[primitive["indices"]]
                if accessor["type"] != "SCALAR":
                    report.error("INDICES_TYPE", "Index accessor must be SCALAR.", pointer)
                if accessor["componentType"] not in (5121, 5123, 5125):
                    report.error("INDICES_COMPONENT_TYPE",
                                 "Index componentType must be UNSIGNED_BYTE/SHORT/INT.", pointer)
                if accessor["count"] % 3:
                    report.error("INDICES_COUNT",
                                 "Triangle index count must be a multiple of three.", pointer)
                if int(np.max(indices)) >= vertex_count:
                    report.error("INDEX_OUT_OF_RANGE",
                                 f"Index {int(np.max(indices))} >= vertex count {vertex_count}.",
                                 pointer)
                view = views[accessor["bufferView"]]
                if view.get("target") not in (None, 34963):
                    report.warning("INDICES_TARGET",
                                   "Index bufferView target should be ELEMENT_ARRAY_BUFFER.",
                                   pointer)
            elif vertex_count % 3:
                report.error("NON_INDEXED_COUNT",
                             "Non-indexed triangle vertex count must be a multiple of three.",
                             pointer)
            if "material" in primitive:
                used_materials.add(primitive["material"])
                if primitive["material"] >= len(document.get("materials", [])):
                    report.error("MATERIAL_INDEX", "material index out of range.", pointer)

    materials = document.get("materials", [])
    textures = document.get("textures", [])
    images = document.get("images", [])
    used_textures: set[int] = set()
    for i, material in enumerate(materials):
        pointer = f"/materials/{i}"
        alpha_mode = material.get("alphaMode", "OPAQUE")
        if alpha_mode not in ("OPAQUE", "MASK", "BLEND"):
            report.error("MATERIAL_ALPHA_MODE", "Unknown alphaMode.", pointer)
        if "alphaCutoff" in material and alpha_mode != "MASK":
            report.warning("MATERIAL_ALPHA_CUTOFF_UNUSED",
                           "alphaCutoff is only used when alphaMode is MASK.", pointer)
        pbr = material.get("pbrMetallicRoughness", {})
        for key in ("baseColorTexture", "metallicRoughnessTexture"):
            if key in pbr:
                used_textures.add(pbr[key]["index"])
        for key in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            if key in material:
                used_textures.add(material[key]["index"])
        factor = pbr.get("baseColorFactor")
        if factor is not None and (len(factor) != 4 or any(not 0.0 <= v <= 1.0 for v in factor)):
            report.error("MATERIAL_BASE_COLOR_FACTOR",
                         "baseColorFactor must be four values in [0,1].", pointer)

    for i, texture in enumerate(textures):
        if "source" not in texture:
            report.warning("TEXTURE_NO_SOURCE", "Texture has no image source.",
                           f"/textures/{i}")
        elif texture["source"] >= len(images):
            report.error("TEXTURE_SOURCE_INDEX", "texture.source out of range.",
                         f"/textures/{i}/source")

    for i, image in enumerate(images):
        pointer = f"/images/{i}"
        if "uri" in image:
            report.error("IMAGE_EXTERNAL",
                         "Runtime GLB must embed images; external image URI found.", pointer)
            continue
        if "bufferView" not in image:
            report.error("IMAGE_NO_SOURCE", "Image has neither uri nor bufferView.", pointer)
            continue
        view = views[image["bufferView"]]
        start = view.get("byteOffset", 0)
        blob = binary[start:start + view["byteLength"]]
        mime = image.get("mimeType", "")
        if mime == "image/png":
            if blob[:8] != b"\x89PNG\r\n\x1a\n":
                report.error("IMAGE_MIME_MISMATCH", "Declared PNG but signature is wrong.",
                             pointer)
        elif mime == "image/jpeg":
            if blob[:2] != b"\xff\xd8":
                report.error("IMAGE_MIME_MISMATCH", "Declared JPEG but signature is wrong.",
                             pointer)
        else:
            report.error("IMAGE_MIME", f"Unsupported image mimeType '{mime}'.", pointer)

    nodes = document.get("nodes", [])
    child_of: dict[int, int] = {}
    for i, node in enumerate(nodes):
        pointer = f"/nodes/{i}"
        if not node.get("name"):
            report.info("NODE_UNNAMED", "Node has no name; runtime lookups rely on names.",
                        pointer)
        if "matrix" in node and any(k in node for k in ("translation", "rotation", "scale")):
            report.error("NODE_MATRIX_TRS",
                         "A node must not mix matrix with TRS properties.", pointer)
        rotation = node.get("rotation")
        if rotation is not None:
            length = math.sqrt(sum(v * v for v in rotation))
            if abs(length - 1.0) > 1e-3:
                report.error("ROTATION_NON_UNIT", "node.rotation must be a unit quaternion.",
                             pointer + "/rotation")
        scale = node.get("scale")
        if scale is not None and any(abs(v) < 1e-9 for v in scale):
            report.error("NODE_ZERO_SCALE", "node.scale must not collapse an axis.", pointer)
        if "mesh" not in node and not node.get("children") and "camera" not in node:
            report.info("NODE_EMPTY", "Empty node encountered.", pointer)
        for child in node.get("children", []):
            if child in child_of:
                report.error("NODE_MULTIPLE_PARENTS",
                             f"Node {child} appears under more than one parent.", pointer)
            if child == i:
                report.error("NODE_SELF_PARENT", "Node lists itself as a child.", pointer)
            child_of[child] = i

    # cycle detection
    for i in range(len(nodes)):
        seen = set()
        current = i
        while current in child_of:
            current = child_of[current]
            if current in seen:
                report.error("NODE_CYCLE", "Node hierarchy contains a cycle.", f"/nodes/{i}")
                break
            seen.add(current)

    scenes = document.get("scenes", [])
    if not scenes:
        report.warning("SCENE_MISSING", "Document declares no scene.", "/scenes")
    for scene_index, scene in enumerate(scenes):
        for root in scene.get("nodes", []):
            if root in child_of:
                report.error("SCENE_ROOT_IS_CHILD",
                             f"Scene root {root} is also a child node.",
                             f"/scenes/{scene_index}/nodes")

    names: dict[str, int] = {}
    for i, node in enumerate(nodes):
        name = node.get("name")
        if name:
            names[name] = names.get(name, 0) + 1
    duplicates = {n: c for n, c in names.items() if c > 1}
    if duplicates:
        sample = ", ".join(sorted(duplicates)[:5])
        report.error("NODE_NAME_NOT_UNIQUE",
                     f"{len(duplicates)} node names are reused (e.g. {sample}); the client "
                     "resolves collision and navigation nodes by name.", "/nodes")

    for i in range(len(accessors)):
        if i not in used_accessors:
            report.info("UNUSED_OBJECT", "This object may be unused.", f"/accessors/{i}")
    for i in range(len(materials)):
        if i not in used_materials:
            report.info("UNUSED_OBJECT", "This object may be unused.", f"/materials/{i}")
    for i in range(len(textures)):
        if i not in used_textures:
            report.info("UNUSED_OBJECT", "This object may be unused.", f"/textures/{i}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a GLB against glTF 2.0.")
    parser.add_argument("path")
    parser.add_argument("--out", help="write the JSON report here")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    report = validate(args.path)
    payload = report.to_dict()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
    counts = payload["issues"]
    if not args.quiet:
        for message in report.messages:
            if message["severity"] <= 1:
                label = "ERROR" if message["severity"] == 0 else "WARN "
                print(f"{label} {message['code']}: {message['message']} {message['pointer']}")
        print(f"errors={counts['numErrors']} warnings={counts['numWarnings']} "
              f"infos={counts['numInfos']}")
    return 1 if counts["numErrors"] else 0


if __name__ == "__main__":
    sys.exit(main())
