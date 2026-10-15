#!/usr/bin/env python3
"""Convert unrigged high-resolution player GLBs into compact authored sources.

This authoring-only importer uses NumPy for deterministic vertex clustering.
The checked-in .emesh files are consumed by the normal asset build using only
the Python standard library; end users do not need NumPy or the original GLBs.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import struct
import zlib

import numpy as np
from PIL import Image


COMPONENT_DTYPES = {5123: "<u2", 5125: "<u4", 5126: "<f4"}
TYPE_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
MAGIC = b"EMSH\x01\x00\x00\x00"


def read_glb(path: Path):
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError(f"not a GLB file: {path}")
    version, total = struct.unpack_from("<II", data, 4)
    if version != 2 or total != len(data):
        raise ValueError(f"unsupported GLB header: {path}")
    offset = 12; chunks = {}
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset); offset += 8
        chunks[kind] = data[offset:offset + length]; offset += length
    document = json.loads(chunks[0x4E4F534A])
    return document, chunks[0x004E4942]


def accessor(document, binary, index):
    spec = document["accessors"][index]
    view = document["bufferViews"][spec["bufferView"]]
    width = TYPE_WIDTHS[spec["type"]]
    dtype = np.dtype(COMPONENT_DTYPES[spec["componentType"]])
    start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
    stride = view.get("byteStride", dtype.itemsize * width)
    shape = (spec["count"],) if width == 1 else (spec["count"], width)
    strides = (stride,) if width == 1 else (stride, dtype.itemsize)
    return np.ndarray(shape, dtype=dtype, buffer=binary, offset=start,
                      strides=strides).copy()


def compact(vertices, normals, texcoords, faces):
    used = np.unique(faces.reshape(-1))
    remap = np.full(len(vertices), -1, dtype=np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return vertices[used], normals[used], texcoords[used], remap[faces]


def clean_mesh(document, binary, cell, uv_bins):
    if len(document.get("meshes", [])) != 1:
        raise ValueError("authored player GLB must contain exactly one mesh")
    primitive = document["meshes"][0]["primitives"][0]
    attributes = primitive["attributes"]
    positions = accessor(document, binary, attributes["POSITION"]).astype(np.float64)
    normals = accessor(document, binary, attributes["NORMAL"]).astype(np.float64)
    texcoords = accessor(document, binary, attributes["TEXCOORD_0"]).astype(np.float64)
    faces = accessor(document, binary, primitive["indices"]).astype(np.int64).reshape(-1, 3)

    # Source files use X-right, Y-up, Z-forward. Eloria uses X-right,
    # Y-back, Z-up, so source +Z becomes runtime -Y.
    low, high = positions.min(axis=0), positions.max(axis=0)
    uniform = 1.82 / (high[1] - low[1])
    transformed = np.column_stack((positions[:, 0] * uniform,
                                   -positions[:, 2] * uniform,
                                   (positions[:, 1] - low[1]) * uniform))
    transformed_normals = np.column_stack((normals[:, 0], -normals[:, 2], normals[:, 1]))

    # Preserve UV discontinuities while clustering spatially close scan
    # vertices. UV bins prevent unrelated atlas islands from being averaged.
    spatial = np.floor((positions - low) / cell + 0.5).astype(np.int32)
    uv_key = np.floor(texcoords * uv_bins + 0.5).astype(np.int32)
    keys = np.column_stack((spatial, uv_key))
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    count = np.bincount(inverse).astype(np.float64)
    vertex_count = len(count)

    def average(values):
        result = np.zeros((vertex_count, values.shape[1]), dtype=np.float64)
        for axis in range(values.shape[1]):
            np.add.at(result[:, axis], inverse, values[:, axis])
        return result / count[:, None]

    clean_positions = average(transformed)
    clean_normals = average(transformed_normals)
    lengths = np.linalg.norm(clean_normals, axis=1)
    clean_normals /= np.maximum(lengths[:, None], 1e-12)
    clean_uvs = average(texcoords)
    clean_faces = inverse[faces]
    clean_faces = clean_faces[(clean_faces[:, 0] != clean_faces[:, 1]) &
                              (clean_faces[:, 1] != clean_faces[:, 2]) &
                              (clean_faces[:, 0] != clean_faces[:, 2])]
    # Remove duplicate scan triangles without changing their winding.
    canonical = np.sort(clean_faces, axis=1)
    _, unique = np.unique(canonical, axis=0, return_index=True)
    clean_faces = clean_faces[np.sort(unique)]
    a=clean_positions[clean_faces[:,0]]; b=clean_positions[clean_faces[:,1]]; c=clean_positions[clean_faces[:,2]]
    crosses=np.cross(b-a,c-a); areas=np.linalg.norm(crosses,axis=1)
    clean_faces=clean_faces[areas>1e-10]; crosses=crosses[areas>1e-10]
    # Cal3D's runtime validator uses the first corner normal for winding.
    # Reject tangential scan slivers and orient against that exact normal.
    orientation=np.einsum("ij,ij->i",crosses,clean_normals[clean_faces[:,0]])
    keep=np.abs(orientation)>1e-9; clean_faces=clean_faces[keep]; orientation=orientation[keep]
    backwards=orientation<0
    clean_faces[backwards]=clean_faces[backwards][:,[0,2,1]]
    clean_positions, clean_normals, clean_uvs, clean_faces = compact(
        clean_positions, clean_normals, clean_uvs, clean_faces)
    return (clean_positions.astype("<f4"), clean_normals.astype("<f4"),
            clean_uvs.astype("<f4"), clean_faces.astype("<u4"))


def write_emesh(path, positions, normals, texcoords, faces):
    payload = bytearray(struct.pack("<II", len(positions), len(faces)))
    payload.extend(positions.tobytes())
    payload.extend(normals.tobytes())
    payload.extend(texcoords.tobytes())
    payload.extend(faces.tobytes())
    compressed = zlib.compress(bytes(payload), 9)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<II", len(payload), len(compressed)) + compressed)


def extract_base_color(document, binary, path):
    material = document["materials"][0]
    texture_id = material["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    image_id = document["textures"][texture_id]["source"]
    image = document["images"][image_id]
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    raw = binary[start:start + view["byteLength"]]
    texture = Image.open(io.BytesIO(raw)).convert("RGBA")
    if texture.size != (2048, 2048):
        raise ValueError(f"expected 2048x2048 authored atlas, found {texture.size}")
    path.parent.mkdir(parents=True, exist_ok=True)
    texture.save(path, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--cell", type=float, default=.012)
    parser.add_argument("--uv-bins", type=int, default=24)
    args = parser.parse_args()
    names = ("glasswarden_female", "glasswarden_male",
             "ssarathi_female", "ssarathi_male")
    manifest = {"schema": 1, "models": {}}
    for name in names:
        source = args.source_dir / f"{name}.glb"
        document, binary = read_glb(source)
        positions, normals, texcoords, faces = clean_mesh(
            document, binary, args.cell, args.uv_bins)
        write_emesh(args.output_dir / f"{name}.emesh",
                    positions, normals, texcoords, faces)
        extract_base_color(document, binary, args.output_dir / f"{name}.png")
        manifest["models"][name] = {
            "source": source.name,
            "vertices": len(positions), "triangles": len(faces),
            "texture": [2048, 2048], "cell": args.cell,
            "uv_bins": args.uv_bins,
        }
        print(f"{name}: {len(positions)} vertices, {len(faces)} triangles")
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
