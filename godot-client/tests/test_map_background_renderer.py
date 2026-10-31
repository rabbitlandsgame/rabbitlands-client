"""CPU-only pixel and ownership contracts for mandatory 2D map assets."""
import json
from pathlib import Path
import struct
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
import render_map_backgrounds as Tool


def sections():
    return [{"id": "one", "bounds": {"min": [0, 0], "max": [10, 10]}},
            {"id": "two", "bounds": {"min": [20, 20], "max": [30, 30]}}]


def write_scene(path):
    # The red room's mesh intentionally overlaps the green room in XZ. Its
    # node prefix must still hide it; cropping an aggregate image would leak it.
    positions = np.array([[0, 0, 0], [0, 0, 10], [10, 0, 10], [10, 0, 0]], dtype="<f4")
    indices = np.array([0, 1, 2, 0, 2, 3], dtype="<u2")
    binary = positions.tobytes() + indices.tobytes()
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0, 1, 2]}],
                "nodes": [{"name": "Walk_one_floor", "mesh": 0},
                          {"name": "Build_two_hidden", "mesh": 1, "translation": [0, 2, 0]},
                          {"name": "Shell_Ceiling", "mesh": 1, "translation": [0, 4, 0]}],
                "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]},
                           {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 1}]}],
                "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.05, 0.8, 0.05, 1]}},
                              {"pbrMetallicRoughness": {"baseColorFactor": [0.9, 0.02, 0.02, 1]}}],
                "buffers": [{"byteLength": len(binary)}],
                "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": positions.nbytes},
                                {"buffer": 0, "byteOffset": positions.nbytes, "byteLength": indices.nbytes}],
                "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
                              {"bufferView": 1, "componentType": 5123, "count": 6, "type": "SCALAR"}]}
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(encoded) + len(binary))
                     + struct.pack("<II", len(encoded), 0x4E4F534A) + encoded
                     + struct.pack("<II", len(binary), 0x004E4942) + binary)


def test_prefix_and_centre_ownership_match_runtime_order():
    assert Tool.named_section("Walk_two_marble", sections()) == "two"
    assert Tool.named_section("Section_twoInner", sections()) == "two"
    assert Tool.named_section("Props_chest", sections()) == ""
    assert Tool.section_at((10.9, 10.9), sections()) == "one"
    assert Tool.section_at((12, 12), sections()) == ""
    assert Tool.section_at((21, 21), sections()) == "two"


def test_label_is_mesh_aabb_centre_not_triangle_or_node_origin():
    class Raster:
        @staticmethod
        def accessor(document, binary, index):
            return np.array([[19, 0, 19], [23, 0, 23]], dtype=float)
    label = Tool.SectionLabels(sections(), Raster)
    document = {"meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}]}
    assert label("Props_chest", 0, np.eye(4), document, b"") == "two"
    assert label("Walk_one_floor", 0, np.eye(4), document, b"") == "one"
    translated = np.eye(4)
    translated[:3, 3] = [-15, 0, -15]
    assert label("Props_chest", 0, translated, document, b"") == "one"


def test_native_raster_filters_other_section_and_private_cutaway(tmp_path):
    _, _, Reader, Raster = Tool._renderer()
    glb = tmp_path / "world.glb"
    write_scene(glb)
    original = glb.read_bytes()
    pool = Reader.Pool(Raster)
    chunk = Reader.read_chunk(Raster, pool, glb, {}, "fixture",
                              hidden_nodes=["Shell_Ceiling"], node_label=Tool.SectionLabels(sections(), Raster))
    assert chunk["part_labels"] == ["one", "two"]
    assert glb.read_bytes() == original
    selected = dict(chunk)
    selected["parts"] = [p for p, label in zip(chunk["parts"], chunk["part_labels"])
                         if label in ("", "one")]
    scene, colors = Reader.window_scene(Raster, pool, [(selected, (0, 0))])
    rgb, _, coverage, counts = Raster.raster(scene, colors, np.array([0, 0]), np.array([10, 10]),
                                            (32, 32), 1, native_cache=tmp_path / "native")
    pixel = np.asarray(rgb)[16, 16]
    assert int(pixel[1]) > int(pixel[0]) * 2  # Green floor; the hidden red room cannot cover it.
    assert np.asarray(coverage)[16, 16] == 255
    assert counts["coveredSamples"] > 0


def test_image_dimensions_preserve_exact_rectangle_without_unbounded_allocation():
    assert Tool.dimensions([0, 0], [10, 5]) == [512, 256]
    assert Tool.dimensions([0, 0], [1000, 500]) == [2048, 1024]
    assert Tool.dimensions([0.15, -4.72], [10.15, 15.28]) == [256, 512]


def test_scoped_regeneration_cannot_relabel_untouched_old_renderer_pictures():
    old = {"maps": {"old": {}}, "rendererInputs": {"tool": "old"}, "renderSettings": {"ppm": 4}}
    Tool._check_scope(old, old["rendererInputs"], old["renderSettings"], ["old"])
    with pytest.raises(Tool.Contract.BackgroundError, match="regenerate all maps"):
        Tool._check_scope(old, {"tool": "new"}, old["renderSettings"], ["old"])
    with pytest.raises(Tool.Contract.BackgroundError, match="regenerate all maps"):
        Tool._check_scope(old, old["rendererInputs"], {"ppm": 8}, ["old"])
    Tool._check_scope(old, {"tool": "new"}, {"ppm": 8}, None)
