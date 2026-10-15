"""Focused contract for the prepared, inactive Whitehorn cave asset."""
from pathlib import Path
import hashlib
import json
import struct
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
REGIONS = HERE.parents[2]
sys.path.insert(0, str(REGIONS / "_toolkit"))
sys.path.insert(0, str(HERE))

from amberwood import gltf as GLTF
import cave_model as CAVE


def test_vendor_topology_attributes_and_indices_are_preserved():
    assert hashlib.sha256(CAVE.ASSET.read_bytes()).hexdigest() == CAVE.ASSET_SHA256
    document, binary = CAVE._document()
    primitive = document["meshes"][0]["primitives"][0]
    attributes = primitive["attributes"]
    positions = CAVE._accessor(document, binary, attributes["POSITION"])
    normals = CAVE._accessor(document, binary, attributes["NORMAL"])
    uvs = CAVE._accessor(document, binary, attributes["TEXCOORD_0"])
    indices = CAVE._accessor(document, binary, primitive["indices"]).reshape(-1)
    mesh = CAVE._raw_mesh()

    assert positions.shape == normals.shape == (CAVE.EXPECTED_VERTICES, 3)
    assert uvs.shape == (CAVE.EXPECTED_VERTICES, 2)
    assert indices.shape == (CAVE.EXPECTED_TRIANGLES * 3,)
    assert np.array_equal(mesh.positions, positions)
    assert np.array_equal(mesh.normals, normals)
    assert np.array_equal(mesh.uvs, uvs)
    assert np.array_equal(mesh.indices, indices)
    assert mesh.copy().weld(1e-4).vertex_count == CAVE.EXPECTED_VERTICES
    triangles = positions[indices.reshape(-1, 3)]
    twice_area = np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0],
                 triangles[:, 2] - triangles[:, 0]), axis=1)
    assert np.all(twice_area > 0.0)
    assert np.all(np.isfinite(normals)) and np.all(np.isfinite(uvs))


def test_two_reviewed_fits_have_exact_transformed_bounds():
    primary = CAVE.source_mesh(scale=16.0)
    primary_low, primary_high = primary.bounds()
    assert np.allclose(primary_low, [-8.0, -0.190478, -8.0], atol=2e-5)
    assert np.allclose(primary_high, [8.0, 8.153282, 8.0], atol=2e-5)

    secondary_scale = 10.666666666666666
    secondary = CAVE.source_mesh(scale=secondary_scale)
    secondary_low, secondary_high = secondary.bounds()
    assert np.allclose(secondary_low,
                       [-5.333333333333333, -0.045318, -5.333333333333333],
                       atol=2e-5)
    assert np.allclose(secondary_high,
                       [5.333333333333333, 5.517189, 5.333333333333333],
                       atol=2e-5)
    assert np.isclose(CAVE.scale_for_span(5.0), secondary_scale)


def test_embedded_jpegs_and_pbr_material_survive_export(tmp_path):
    document, binary = CAVE._document()
    assert [hashlib.sha256(CAVE._image_bytes(document, binary, index)).hexdigest()
            for index in range(3)] == list(CAVE.EXPECTED_IMAGE_SHA256)

    builder = GLTF.GltfBuilder()
    CAVE.register_material(builder)
    assert [image["mimeType"] for image in builder._images] == ["image/jpeg"] * 3
    assert [image["name"] for image in builder._images] == list(CAVE.IMAGE_NAMES)
    material = builder._materials[0]
    assert material["doubleSided"] is True
    assert set(material) >= {"pbrMetallicRoughness", "normalTexture"}
    assert "occlusionTexture" not in material

    builder.add_mesh("prepared_cave", CAVE.source_mesh())
    builder.add_node(GLTF.Node("PreparedCave", mesh="prepared_cave"))
    output = tmp_path / "adapter.glb"
    builder.write_glb(str(output))
    raw = output.read_bytes()
    offset = 12
    readback = None
    payload = None
    while offset < len(raw):
        length, kind = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        chunk = raw[offset:offset + length]
        offset += length
        if kind == b"JSON":
            readback = json.loads(chunk.rstrip(b" \t\r\n\0"))
        elif kind == b"BIN\0":
            payload = chunk
    assert readback is not None and payload is not None
    assert [image["mimeType"] for image in readback["images"]] == ["image/jpeg"] * 3
    readback_hashes = []
    for image in readback["images"]:
        view = readback["bufferViews"][image["bufferView"]]
        start = int(view.get("byteOffset", 0))
        image_bytes = payload[start:start + int(view["byteLength"])]
        readback_hashes.append(hashlib.sha256(image_bytes).hexdigest())
    assert readback_hashes == list(CAVE.EXPECTED_IMAGE_SHA256)
