#!/usr/bin/env python3
"""The package-time RL hair/beard image strip (tools/strip_rl_head_images.py, AT-C0).

    python godot-client/tests/test_strip_rl_head_images.py -v

Synthetic GLBs (meshes, a strided attribute, a sparse morph target, a skin and an
animation on accessors packed after the images, so the repack moves them) hold
the four conditions: an embedded image goes only when its bytes are a tracked RL
map, every material sampling it is in the RL material contract and names a map
with those bytes in extras.texture, and nothing else references it. Everything
that is not the removed images' data - accessor bytes, kept images, materials and
their extras, nodes, skins, animations - must come out identical, and the
verifier must catch any change to it. The strip must never write through a hard
link, must fail when a map's PCK copy is missing (the packager: before the
import when the committed import names no product, after the export when the
PCK lacks it), and must leave a receipt. The packager strips the build tree
before the import (schedule 1.1 #6). The contract is read from the real
rl_head_library.gd as GDScript reads it (a drift test; comments do not count),
and every tracked RL hair and beard GLB must strip completely under it.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS = Path(__file__).resolve().parent
CLIENT = TESTS.parent
sys.path.insert(0, str(CLIENT / "tools"))

import strip_rl_head_images as strip  # noqa: E402

LIBRARY_TEXT = '''
const SHADERS := {
	"rl_skin": preload("res://src/actors/rl_head/rl_skin.gdshader"),
	"rl_hair": preload("res://src/actors/rl_head/rl_hair.gdshader"),
	"rl_hidden": preload("res://src/actors/rl_head/rl_hidden.gdshader"),
}
## Canonical material role -> the shader that draws it.
const MATERIAL_SHADERS := {
	"rl_skin": "rl_skin", "rl_hair_clump": "rl_hair",
	"rl_hair_card": "rl_hair", "rl_beard": "rl_hair",
}
const MATERIAL_ROLES := {
	"rl_hair_clump_crest": "rl_hair_clump",
	"rl_hair_clump_crest_lod1": "rl_hair_clump",
	"rl_orphan_role": "rl_not_a_role",
}
'''
CONTRACT = strip.read_contract(LIBRARY_TEXT)

PNG_A = b"\x89PNG-a" + bytes(range(31))          # 37 bytes: the repack must realign what follows
PNG_B = b"\x89PNG-b" + bytes(range(50, 93))       # 49 bytes
PNG_C = b"\x89PNG-c" + bytes(range(100, 121))     # unmatched
MAPS = {hashlib.sha256(PNG_A).hexdigest(): ["a.png"],
        hashlib.sha256(PNG_B).hexdigest(): ["b.png", "b_copy.png"]}
MAP_DIR = strip.MAP_DIR


def material(name, texture=None, slot="baseColorTexture", extras_texture=None, **extra):
    """A glTF material; `texture` is a texture index sampled at `slot`."""
    result = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [0.5, 0.25, 1.0, 1.0],
                                                     "metallicFactor": 0.0}, "alphaMode": "MASK",
              "alphaCutoff": 0.35, "doubleSided": True,
              "extras": {"texture": extras_texture, "softHairline": True, "uv": [0, 1]}}
    if extras_texture is None:
        del result["extras"]["texture"]
    if texture is not None:
        info = {"index": texture, "texCoord": 0}
        if slot == "baseColorTexture":
            result["pbrMetallicRoughness"][slot] = info
        else:
            result[slot] = info
    result.update(extra)
    return result


def fixture(images, textures, materials, samplers=None, **top) -> tuple[dict, bytes]:
    """A GLB document and BIN: geometry before the images, animation and skin data after.

    `images` holds bytes (a new bufferView), an int (share image n's view) or a
    str (a URI image).
    """
    binary = bytearray()
    views: list[dict] = []

    def add(data: bytes, **view) -> int:
        binary.extend(b"\0" * ((-len(binary)) % 4))
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data), **view})
        binary.extend(data)
        return len(views) - 1

    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    # Interleaved: a VEC2 UV and 4 bytes of junk per 12-byte vertex.
    strided = b"".join(struct.pack("<2f", u, v) + b"\xAA\xBB\xCC\xDD" for u, v in ((0, 0), (1, 0), (0, 1)))
    accessors = []
    pos = add(positions, target=34962)
    accessors.append({"bufferView": pos, "componentType": 5126, "count": 3, "type": "VEC3",
                      "min": [0, 0, 0], "max": [1, 1, 0]})
    uv = add(strided, byteStride=12, target=34962)
    accessors.append({"bufferView": uv, "componentType": 5126, "count": 3, "type": "VEC2"})
    indices = add(struct.pack("<3H", 0, 1, 2), target=34963)
    accessors.append({"bufferView": indices, "componentType": 5123, "count": 3, "type": "SCALAR"})
    image_rows = []
    for index, image in enumerate(images):
        if isinstance(image, bytes):
            image_rows.append({"bufferView": add(image), "mimeType": "image/png", "name": f"image{index}"})
        elif isinstance(image, int):
            image_rows.append({"bufferView": image_rows[image]["bufferView"], "mimeType": "image/png",
                               "name": f"image{index}"})
        else:
            image_rows.append({"uri": image})
    times = add(struct.pack("<2f", 0.0, 1.0))
    accessors.append({"bufferView": times, "componentType": 5126, "count": 2, "type": "SCALAR",
                      "min": [0.0], "max": [1.0]})
    rotations = add(struct.pack("<8f", 0, 0, 0, 1, 0, 0.7071, 0, 0.7071))
    accessors.append({"bufferView": rotations, "componentType": 5126, "count": 2, "type": "VEC4"})
    ibm = add(struct.pack("<16f", *(1.0 if i % 5 == 0 else 0.0 for i in range(16))))
    accessors.append({"bufferView": ibm, "componentType": 5126, "count": 1, "type": "MAT4"})
    sparse_indices = add(struct.pack("<I", 2))
    sparse_values = add(struct.pack("<3f", 0.0, 0.0, 0.25))
    accessors.append({"componentType": 5126, "count": 3, "type": "VEC3",
                      "sparse": {"count": 1, "indices": {"bufferView": sparse_indices, "componentType": 5125},
                                 "values": {"bufferView": sparse_values}}})
    primitives = [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": m,
                   "targets": [{"POSITION": 6}]} for m in range(len(materials))]
    document = {
        "asset": {"version": "2.0", "generator": "test", "extras": {"rlHair": {"keep": [1, 2]}}},
        "scene": 0, "scenes": [{"nodes": [0, 1]}],
        "nodes": [{"name": "hair_lod0", "mesh": 0, "skin": 0, "extras": {"flag": True}},
                  {"name": "hair_root", "rotation": [0, 0, 0, 1]}],
        "meshes": [{"name": "hair", "primitives": primitives, "weights": [0.0],
                    "extras": {"targetNames": ["hl_volume"]}}],
        "skins": [{"joints": [1], "inverseBindMatrices": 5}],
        "animations": [{"name": "Idle", "channels": [{"sampler": 0, "target": {"node": 1, "path": "rotation"}}],
                        "samplers": [{"input": 3, "output": 4, "interpolation": "LINEAR"}]}],
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(binary)}],
        "materials": materials, "textures": textures, "images": image_rows,
        "samplers": samplers if samplers is not None else [{"magFilter": 9729, "minFilter": 9987},
                                                           {"magFilter": 9728}],
        **top}
    if not textures:
        del document["textures"]
    if not image_rows:
        del document["images"]
    return document, bytes(binary)


def glb(document: dict, binary: bytes) -> bytes:
    return strip.write_glb(document, binary)


def run(document, binary, maps=MAPS, contract=CONTRACT):
    return strip.strip_glb(glb(document, binary), maps, contract)


class Contract(unittest.TestCase):
    def test_synthetic_contract_is_what_material_replaces(self):
        # Exact names, as RLHeadLibrary.material() looks them up: a role only
        # through MATERIAL_ROLES or MATERIAL_SHADERS, never a SHADERS key or a
        # MATERIAL_ROLES entry whose role draws with nothing.
        self.assertEqual(CONTRACT, {"rl_beard": "rl_hair", "rl_hair_card": "rl_hair", "rl_hair_clump": "rl_hair",
                                    "rl_hair_clump_crest": "rl_hair", "rl_hair_clump_crest_lod1": "rl_hair",
                                    "rl_skin": "rl_skin"})
        self.assertNotIn("rl_hair", CONTRACT)
        self.assertNotIn("rl_orphan_role", CONTRACT)

    def test_an_unreadable_entry_fails_instead_of_shrinking_the_contract(self):
        broken = LIBRARY_TEXT.replace('"rl_beard": "rl_hair"', '"rl_beard": BEARD_KIND')
        with self.assertRaises(strip.StripError):
            strip.read_contract(broken)
        with self.assertRaises(strip.StripError):
            strip.read_contract(LIBRARY_TEXT.replace("const MATERIAL_ROLES", "const MATERIAL_ROLE_TABLE"))
        with self.assertRaises(strip.StripError):
            strip.read_contract(LIBRARY_TEXT.replace('"rl_hair": preload', '"rl_hair_shader": preload'))

    def test_comments_and_strings_are_read_as_gdscript_reads_them(self):
        # A commented-out entry is not in the contract: material() would not
        # replace that surface, so its image must stay.
        text = LIBRARY_TEXT.replace(
            '"rl_orphan_role": "rl_not_a_role",',
            '"rl_orphan_role": "rl_not_a_role",  # "rl_retired_clump": "rl_hair_clump", {\n'
            '\t# "rl_hair_clump_crest_lod2": "rl_hair_clump",\n\t## } note\n')
        self.assertEqual(strip.read_contract(text), CONTRACT)
        self.assertEqual(strip.read_contract(text.replace('"rl_hair_clump_crest": "rl_hair_clump",',
                                                          '"rl_hair_clump_crest": "rl_hair_clump", # {{ x')),
                         CONTRACT)
        # A StringName key is not the String name material() is asked for.
        with self.assertRaises(strip.StripError):
            strip.read_contract(LIBRARY_TEXT.replace('"rl_hair_clump_crest":', '&"rl_hair_clump_crest":'))

    def test_real_library_contract_has_not_drifted(self):
        text = (CLIENT / strip.LIBRARY).read_text(encoding="utf-8")
        contract = strip.read_contract(text)
        for name in ("rl_hair_clump", "rl_hair_card", "rl_beard", "rl_hair_clump_crest",
                     "rl_hair_clump_backing", "rl_skin", "rl_eye", "rl_lash", "rl_brow", "rl_cornea", "rl_mouth"):
            self.assertIn(name, contract, name)
        for name in ("rl_hair", "rl_hidden", "rl_bodypatch", ""):
            self.assertNotIn(name, contract, name)
        shaders = strip._gd_pairs(strip._gd_dictionary(text, "SHADERS"), "SHADERS", r"(preload)\(")
        self.assertTrue(set(contract.values()) <= set(shaders))
        roles = strip._gd_pairs(strip._gd_dictionary(text, "MATERIAL_ROLES"), "MATERIAL_ROLES", r'"([^"\\]+)"')
        self.assertTrue(roles and all(contract.get(name) == "rl_hair" for name in roles))


class StripDocument(unittest.TestCase):
    def test_strips_a_matched_contract_image_and_keeps_everything_else(self):
        document, binary = fixture(
            images=[PNG_A, PNG_C],
            textures=[{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}],
            materials=[material("rl_hair_clump", 0, extras_texture="a.png"),
                       material("rl_hair_card", 0, extras_texture="a.png"),
                       material("rl_beard", 1, extras_texture="c.png")])
        new, result = run(document, binary)
        self.assertIsNotNone(new)
        self.assertEqual([r["image"] for r in result["removed"]], [0])
        self.assertEqual(result["removed"][0]["materials"], ["rl_hair_card", "rl_hair_clump"])
        self.assertEqual(result["embedded_bytes_removed"], len(PNG_A))
        self.assertEqual([k["image"] for k in result["kept"]], [1])
        self.assertIn("no tracked rl_head_textures map", result["kept"][0]["reason"])
        stripped, stripped_bin = strip.read_glb(new)
        self.assertEqual(stripped["images"], [{"bufferView": 3, "mimeType": "image/png", "name": "image1"}])
        self.assertEqual(stripped["textures"], [{"sampler": 0, "source": 0}])
        self.assertEqual(stripped["samplers"], [{"magFilter": 9728}])
        for index in (0, 1):
            self.assertNotIn("baseColorTexture", stripped["materials"][index]["pbrMetallicRoughness"])
            self.assertEqual(stripped["materials"][index]["extras"], document["materials"][index]["extras"])
            self.assertEqual(stripped["materials"][index]["pbrMetallicRoughness"]["baseColorFactor"],
                             [0.5, 0.25, 1.0, 1.0])
        self.assertEqual(stripped["materials"][2]["pbrMetallicRoughness"]["baseColorTexture"],
                         {"index": 0, "texCoord": 0})
        for key in ("nodes", "meshes", "skins", "animations", "scenes", "asset"):
            self.assertEqual(stripped[key], document[key], key)
        for index in range(len(document["accessors"])):
            self.assertEqual(strip._accessor_bytes(document, binary, index),
                             strip._accessor_bytes(stripped, stripped_bin, index), index)
        self.assertEqual(strip._view_bytes(stripped, stripped_bin, 3), PNG_C)
        self.assertTrue(all(view["byteOffset"] % 4 == 0 for view in stripped["bufferViews"]))
        self.assertEqual(len(stripped["bufferViews"]), len(document["bufferViews"]) - 1)
        self.assertEqual(stripped["buffers"][0]["byteLength"], len(stripped_bin))
        self.assertLess(len(new), len(glb(document, binary)))

    def test_every_image_gone_drops_the_arrays(self):
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_beard", 0, extras_texture="a.png")])
        new, result = run(document, binary)
        stripped, _ = strip.read_glb(new)
        for key in ("images", "textures"):
            self.assertNotIn(key, stripped)
        # Sampler 1 was never used: not the strip's to remove.
        self.assertEqual(stripped["samplers"], [{"magFilter": 9728}])
        self.assertEqual(stripped["materials"][0]["pbrMetallicRoughness"],
                         {"baseColorFactor": [0.5, 0.25, 1.0, 1.0], "metallicFactor": 0.0})

    def test_material_outside_the_contract_keeps_its_image(self):
        # rl_hair_clump_lod2 is not listed: the runtime keeps its imported
        # material, which samples the embedded image. "rl_hair" is a shader
        # name, not a role.
        for name in ("rl_hair_clump_lod2", "rl_hair", "rl_hidden", "rl_bodypatch", "rl_orphan_role"):
            document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                       materials=[material(name, 0, extras_texture="a.png")])
            new, result = run(document, binary)
            self.assertIsNone(new, name)
            self.assertIn("outside the RL material contract", result["kept"][0]["reason"], name)

    def test_one_material_outside_the_contract_keeps_a_shared_image(self):
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png"),
                                              material("Hair_Imported", 0, extras_texture="a.png")])
        new, result = run(document, binary)
        self.assertIsNone(new)
        self.assertIn("'Hair_Imported' is outside", result["kept"][0]["reason"])

    def test_extras_must_name_a_map_with_those_bytes(self):
        for named, removed in (("b.png", False), (None, False), ("a.png", True)):
            document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                       materials=[material("rl_hair_card", 0, extras_texture=named)])
            new, result = run(document, binary)
            self.assertEqual(new is not None, removed, named)
        # Two tracked maps with the same bytes: either name will do.
        document, binary = fixture(images=[PNG_B], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_card", 0, extras_texture="b_copy.png")])
        new, result = run(document, binary)
        self.assertIsNotNone(new)
        self.assertEqual(result["removed"][0]["maps"], ["b.png", "b_copy.png"])
        self.assertEqual(result["removed"][0]["named"], ["b_copy.png"])

    def test_any_slot_of_a_contract_material_counts(self):
        document, binary = fixture(images=[PNG_A, PNG_B],
                                   textures=[{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
                                   materials=[material("rl_beard", 0, extras_texture="a.png"),
                                              material("rl_beard", 1, slot="normalTexture",
                                                       extras_texture="b.png")])
        new, result = run(document, binary)
        self.assertEqual([r["image"] for r in result["removed"]], [0, 1])
        stripped, _ = strip.read_glb(new)
        self.assertNotIn("normalTexture", stripped["materials"][1])
        self.assertEqual(stripped["samplers"], [{"magFilter": 9728}])

    def test_a_texture_named_outside_materials_keeps_its_image(self):
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        document["nodes"][0]["extras"]["previewTexture"] = {"index": 0}
        new, result = run(document, binary)
        self.assertIsNone(new)
        self.assertIn("referenced at nodes/0/extras/previewTexture", result["kept"][0]["reason"])
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        document["materials"][0]["extras"]["bakeTexture"] = {"index": 0}
        new, result = run(document, binary)
        self.assertIsNone(new)

    def test_files_with_extensions_or_odd_buffers_are_left_alone(self):
        variants = []
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")],
                                   extensionsUsed=["KHR_texture_transform"])
        variants.append((document, binary, "extensions"))
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["extensions"] = {
            "KHR_texture_transform": {"scale": [2, 2]}}
        variants.append((document, binary, "extension at"))
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        document["buffers"].append({"byteLength": 4, "uri": "other.bin"})
        variants.append((document, binary, "one embedded buffer"))
        for document, binary, reason in variants:
            new, result = run(document, binary)
            self.assertIsNone(new, reason)
            self.assertIn(reason, result["kept"][0]["reason"])

    def test_uri_unreferenced_and_unreadable_images_stay(self):
        document, binary = fixture(images=["textures/a.png", PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        new, result = run(document, binary)
        self.assertIsNone(new)
        reasons = {k["image"]: k["reason"] for k in result["kept"]}
        self.assertEqual(reasons, {0: "not embedded (uri)", 1: "no material samples it"})
        new, result = strip.strip_glb(b"glTF but not really", MAPS, CONTRACT)
        self.assertIsNone(new)
        self.assertIn("unreadable GLB", result["kept"][0]["reason"])

    def test_two_images_on_one_view_go_together(self):
        document, binary = fixture(images=[PNG_A, 0],
                                   textures=[{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png"),
                                              material("rl_hair_card", 1, extras_texture="a.png")])
        new, result = run(document, binary)
        self.assertEqual(len(result["removed"]), 2)
        self.assertEqual(result["embedded_bytes_removed"], len(PNG_A))
        stripped, _ = strip.read_glb(new)
        self.assertEqual(len(stripped["bufferViews"]), len(document["bufferViews"]) - 1)

    def test_a_view_a_kept_image_shares_stays(self):
        document, binary = fixture(images=[PNG_A, 0],
                                   textures=[{"sampler": 0, "source": 0}, {"sampler": 0, "source": 1}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png"),
                                              material("Imported", 1)])
        new, result = run(document, binary)
        self.assertEqual([r["image"] for r in result["removed"]], [0])
        self.assertNotIn("embedded_bytes_removed", {k: v for k, v in result.items() if v})
        stripped, stripped_bin = strip.read_glb(new)
        self.assertEqual(len(stripped["bufferViews"]), len(document["bufferViews"]))
        self.assertEqual(strip._view_bytes(stripped, stripped_bin, stripped["images"][0]["bufferView"]), PNG_A)
        self.assertEqual(stripped["materials"][1]["pbrMetallicRoughness"]["baseColorTexture"]["index"], 0)


class Verify(unittest.TestCase):
    def setUp(self):
        self.document, self.binary = fixture(
            images=[PNG_A, PNG_C],
            textures=[{"sampler": 0, "source": 0}, {"sampler": 1, "source": 1}],
            materials=[material("rl_hair_clump", 0, extras_texture="a.png"),
                       material("rl_beard", 1, extras_texture="c.png")])
        self.stripped, self.stripped_bin = strip.strip_document(self.document, self.binary, {0})

    def check(self, stripped, stripped_bin):
        strip.verify(self.document, self.binary, stripped, stripped_bin, {0})

    def test_the_faithful_strip_passes(self):
        self.check(self.stripped, self.stripped_bin)

    def test_changed_accessor_bytes_fail(self):
        for accessor in (0, 1, 4, 6):
            stripped = json.loads(json.dumps(self.stripped))
            data = bytearray(self.stripped_bin)
            parts = strip._accessor_bytes(stripped, self.stripped_bin, accessor)
            target = stripped["accessors"][accessor]
            view = stripped["bufferViews"][target["bufferView"] if "bufferView" in target
                                            else target["sparse"]["values"]["bufferView"]]
            data[view["byteOffset"]] ^= 0xFF
            self.assertTrue(parts)
            with self.assertRaises(strip.StripError, msg=accessor):
                self.check(stripped, bytes(data))

    def test_stride_padding_is_not_data(self):
        data = bytearray(self.stripped_bin)
        data[self.stripped["bufferViews"][1]["byteOffset"] + 8] ^= 0xFF  # the junk after vertex 0's UV
        self.check(self.stripped, bytes(data))

    def test_changed_json_fails(self):
        def mutated(change):
            copy = json.loads(json.dumps(self.stripped))
            change(copy)
            return copy

        changes = [
            lambda d: d["materials"][0]["extras"].update(softHairline=False),
            lambda d: d["materials"][0].update(alphaMode="BLEND"),
            lambda d: d["nodes"][0].update(name="hair_lod1"),
            lambda d: d["animations"][0]["samplers"][0].update(interpolation="STEP"),
            lambda d: d["skins"][0].update(joints=[0]),
            lambda d: d["materials"][1]["pbrMetallicRoughness"].pop("baseColorTexture"),
            lambda d: d["materials"][1]["pbrMetallicRoughness"]["baseColorTexture"].update(texCoord=1),
            lambda d: d["materials"][0].update(normalTexture={"index": 0}),
            lambda d: d["samplers"][0].update(magFilter=9729),
            lambda d: d["images"][0].update(mimeType="image/jpeg"),
            lambda d: d["accessors"][0].update(count=2),
        ]
        for index, change in enumerate(changes):
            with self.assertRaises(strip.StripError, msg=index):
                self.check(mutated(change), self.stripped_bin)

    def test_changed_kept_image_fails(self):
        data = bytearray(self.stripped_bin)
        data[self.stripped["bufferViews"][self.stripped["images"][0]["bufferView"]]["byteOffset"]] ^= 1
        with self.assertRaises(strip.StripError):
            self.check(self.stripped, bytes(data))


def write_pck(path: Path, names: list[str]) -> None:
    """A Godot 4 PCK (format 3) whose directory lists `names` (no file data)."""
    header = b"GDPC" + struct.pack("<4I", 3, 4, 7, 2) + struct.pack("<I", 0) + struct.pack("<Q", 0)
    directory_at = len(header) + 8 + 16 * 4
    directory = struct.pack("<I", len(names))
    for name in names:
        encoded = ("res://" + name).encode("utf-8")
        encoded += b"\0" * ((-len(encoded)) % 4)
        directory += struct.pack("<I", len(encoded)) + encoded + struct.pack("<QQ", 0, 0) + b"\0" * 16 \
            + struct.pack("<I", 0)
    path.write_bytes(header + struct.pack("<Q", directory_at) + b"\0" * (16 * 4) + directory)


def library_tree(root: Path) -> None:
    path = root / "godot-client" / strip.LIBRARY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LIBRARY_TEXT, encoding="utf-8")


class Stage(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.build = root / "build"
        self.app = root / "stage" / "app"
        library_tree(self.build)
        hair = self.build / "godot-client" / strip.RL_GLB_DIRS[0]
        hair.mkdir(parents=True)
        document, binary = fixture(images=[PNG_A], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_hair_clump", 0, extras_texture="a.png")])
        self.original = glb(document, binary)
        (hair / "style.glb").write_bytes(self.original)
        # A staged hard link to the build tree, as release_storage.link_file stages it.
        staged = self.app / strip.RL_GLB_DIRS[0]
        staged.mkdir(parents=True)
        os.link(hair / "style.glb", staged / "style.glb")
        plain, plain_bin = fixture(images=[PNG_C], textures=[{"sampler": 0, "source": 0}],
                                   materials=[material("rl_beard", 0, extras_texture="c.png")])
        beards = self.app / strip.RL_GLB_DIRS[1]
        beards.mkdir(parents=True)
        self.untouched = glb(plain, plain_bin)
        (beards / "goatee.glb").write_bytes(self.untouched)
        # A head GLB beside the folders, and a GLB one folder down, are not RL hair or beards.
        (self.app / strip.RL_GLB_DIRS[0] / "nested").mkdir()
        (self.app / strip.RL_GLB_DIRS[0] / "nested" / "deeper.glb").write_bytes(self.original)
        (self.app / strip.RL_GLB_DIRS[0]).parent.joinpath("rl_head_male.glb").write_bytes(self.original)
        self.receipt = root / "logs" / "rl-head-strip.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_strips_staged_copies_only_and_writes_a_receipt(self):
        budget = mock.Mock()
        asked: list[str] = []
        receipt = strip.strip_stage(self.app, self.build, receipt=self.receipt, maps=MAPS, budget=budget,
                                    pck_has=lambda local: asked.append(local) or True, log=lambda message: None)
        source = self.build / "godot-client" / strip.RL_GLB_DIRS[0] / "style.glb"
        staged = self.app / strip.RL_GLB_DIRS[0] / "style.glb"
        self.assertEqual(source.read_bytes(), self.original, "the build tree's file was written through")
        self.assertEqual(source.stat().st_nlink, 1)
        stripped = staged.read_bytes()
        self.assertLess(len(stripped), len(self.original))
        self.assertNotIn("images", strip.read_glb(stripped)[0])
        self.assertEqual(asked, [f"{MAP_DIR}/a.png"])
        budget.assert_called_once_with("before the RL head image strip", len(stripped))
        self.assertEqual((self.app / strip.RL_GLB_DIRS[1] / "goatee.glb").read_bytes(), self.untouched)
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0] / "nested" / "deeper.glb").read_bytes(), self.original)
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0]).parent.joinpath("rl_head_male.glb").read_bytes(),
                         self.original)
        self.assertFalse(list(self.app.rglob("*.tmp")))
        written = json.loads(self.receipt.read_text(encoding="utf-8"))
        self.assertEqual(written, receipt)
        self.assertEqual(written["contract"], CONTRACT)
        totals = written["totals"]
        self.assertEqual((totals["files"], totals["changed"], totals["images_removed"], totals["images_kept"]),
                         (2, 1, 1, 1))
        self.assertEqual(totals["image_bytes_removed"], len(PNG_A))
        self.assertEqual(totals["bytes_removed"], len(self.original) - len(stripped))
        row = next(r for r in written["files"] if r["path"].endswith("style.glb"))
        self.assertEqual(row["before"], {"sha256": hashlib.sha256(self.original).hexdigest(),
                                         "bytes": len(self.original)})
        self.assertEqual(row["after"], {"sha256": hashlib.sha256(stripped).hexdigest(), "bytes": len(stripped)})
        self.assertIsNone(next(r for r in written["files"] if r["path"].endswith("goatee.glb"))["after"])

    def test_a_map_missing_from_the_pck_fails_before_anything_is_written(self):
        with self.assertRaisesRegex(strip.StripError, "rl_head_textures/a.png"):
            strip.strip_stage(self.app, self.build, maps=MAPS, pck_has=lambda local: False,
                              log=lambda message: None)
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0] / "style.glb").read_bytes(), self.original)
        with self.assertRaisesRegex(strip.StripError, "PCK copies must be checked"):
            strip.strip_stage(self.app, self.build, maps=MAPS, log=lambda message: None)

    def test_dry_run_writes_no_glb(self):
        receipt = strip.strip_stage(self.app, self.build, maps=MAPS, dry_run=True, log=lambda message: None)
        self.assertEqual(receipt["totals"]["images_removed"], 1)
        self.assertTrue(receipt["totals"]["dry_run"])
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0] / "style.glb").read_bytes(), self.original)

    def test_the_contract_is_read_from_the_build_tree(self):
        (self.build / "godot-client" / strip.LIBRARY).write_text(
            LIBRARY_TEXT.replace('"rl_hair_clump": "rl_hair",', ""), encoding="utf-8")
        receipt = strip.strip_stage(self.app, self.build, maps=MAPS, pck_has=lambda local: True,
                                    log=lambda message: None)
        self.assertEqual(receipt["totals"]["images_removed"], 0)
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0] / "style.glb").read_bytes(), self.original)

    def test_command_line_reads_the_pck_and_the_tracked_maps(self):
        folder = self.build / "godot-client" / MAP_DIR
        folder.mkdir(parents=True)
        (folder / "a.png").write_bytes(PNG_A)
        (folder / "untracked.png").write_bytes(PNG_B)
        product = ".godot/imported/a.png-0123.s3tc.ctex"
        (folder / "a.png.import").write_text(f'[deps]\n\ndest_files=["res://{product}"]\n', encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.build)], check=True)
        subprocess.run(["git", "-C", str(self.build), "add", f"godot-client/{MAP_DIR}/a.png"], check=True)
        self.assertEqual(strip.tracked_maps(self.build), {hashlib.sha256(PNG_A).hexdigest(): ["a.png"]})
        args = ["strip", str(self.app), str(self.build), "--receipt", str(self.receipt)]
        write_pck(self.app / "RabbitLands.pck", [f"{MAP_DIR}/a.png.import"])
        with mock.patch("builtins.print"):
            self.assertEqual(strip.main(args), 1)
        self.assertEqual((self.app / strip.RL_GLB_DIRS[0] / "style.glb").read_bytes(), self.original)
        write_pck(self.app / "RabbitLands.pck", [f"{MAP_DIR}/a.png.import", product])
        with mock.patch("builtins.print"):
            self.assertEqual(strip.main(args), 0)
        self.assertNotIn("images", strip.read_glb((self.app / strip.RL_GLB_DIRS[0] / "style.glb").read_bytes())[0])
        self.assertEqual(json.loads(self.receipt.read_text(encoding="utf-8"))["totals"]["images_removed"], 1)

    def test_package_client_step_strips_the_build_tree_and_checks_the_pck(self):
        import package_client as packager
        folder = self.build / "godot-client" / MAP_DIR
        folder.mkdir(parents=True)
        (folder / "a.png").write_bytes(PNG_A)
        product = ".godot/imported/a.png-0123.s3tc.ctex"
        sidecar = folder / "a.png.import"
        relative = f"godot-client/{MAP_DIR}/a.png"
        shipping = {"folder_textures": {relative, f"godot-client/{MAP_DIR}/sub/x.png"}}
        source = self.build / "godot-client" / strip.RL_GLB_DIRS[0] / "style.glb"
        # The build tree's file is itself a hard link (a runner source or an
        # earlier benchmark stage): neither may be written through.
        elsewhere = Path(self.temp.name) / "elsewhere.glb"
        os.link(source, elsewhere)
        logs = Path(self.temp.name) / "logs"
        with mock.patch.object(packager, "actor_shipping", return_value=shipping), \
                mock.patch.object(packager, "log"):
            # No committed import naming a product: the map would not reach the PCK.
            with self.assertRaisesRegex(packager.PackageError, "RL head image strip"):
                packager.strip_rl_head_stage(self.build, logs)
            sidecar.write_text('[remap]\n\nimporter="texture"\n\n[deps]\n\ndest_files=[]\n', encoding="utf-8")
            with self.assertRaisesRegex(packager.PackageError, "RL head image strip"):
                packager.strip_rl_head_stage(self.build, logs)
            self.assertEqual(source.read_bytes(), self.original)
            sidecar.write_text(f'[remap]\n\nimporter="texture"\n\n[deps]\n\ndest_files=["res://{product}"]\n',
                               encoding="utf-8")
            # A map this package does not ship in the PCK is not compared against.
            with mock.patch.object(packager, "actor_shipping", return_value={"folder_textures": set()}):
                self.assertEqual(packager.strip_rl_head_stage(self.build, logs)["totals"]["images_removed"], 0)
            self.assertEqual(source.read_bytes(), self.original)
            receipt = packager.strip_rl_head_stage(self.build, logs)
        self.assertEqual(receipt["totals"]["images_removed"], 1)
        self.assertEqual(receipt["files"][0]["path"], f"{strip.RL_GLB_DIRS[0]}/style.glb")
        self.assertTrue((logs / "rl-head-strip.json").is_file())
        self.assertNotIn("images", strip.read_glb(source.read_bytes())[0])
        self.assertEqual(elsewhere.read_bytes(), self.original, "a hard link into the build tree was written through")
        self.assertFalse(list(self.build.rglob("*.tmp")))
        # After the export: the stripped copy's map must be in the PCK with its product.
        write_pck(self.app / "RabbitLands.pck", [f"{MAP_DIR}/a.png.import"])
        with self.assertRaisesRegex(packager.PackageError, "rl_head_textures/a.png"):
            packager.check_rl_head_strip_pack(self.build, self.app, logs)
        write_pck(self.app / "RabbitLands.pck", [f"{MAP_DIR}/a.png.import", product])
        self.assertEqual(packager.check_rl_head_strip_pack(self.build, self.app, logs), 1)

    def test_package_client_strips_before_the_import_and_checks_after_the_export(self):
        # Wave-2 schedule 1.1 #6: the RL image strip is the first build-tree
        # transform, before the import (later quantisation and cooks see its
        # bytes); the PCK check follows the export and the loose staging.
        source = (CLIENT / "tools" / "package_client.py").read_text(encoding="utf-8")
        body = source[source.index("def _main(argv=None, storage=None) -> int:"):]
        self.assertEqual(body.count("strip_rl_head_stage("), 1)
        strip_at = body.index("strip_rl_head_stage(build_dir, logs")
        self.assertLess(body.index("project = prepare_build_tree(build_dir, sha)"), strip_at)
        self.assertLess(strip_at, body.index("import_project(godot, project, logs)"))
        export = body.index("export_project(godot, project, app_dir, logs, platform)")
        staged = body.index("stage_loose_client_files(build_dir, app_dir")
        check = body.index("check_rl_head_strip_pack(build_dir, app_dir, logs")
        self.assertLess(export, staged)
        self.assertLess(staged, check)
        self.assertLess(check, body.index("publish_artifacts("))


class RealContent(unittest.TestCase):
    """Every tracked RL hair and beard GLB strips completely under the real contract."""

    def test_every_embedded_rl_map_copy_goes(self):
        maps: dict[str, list[str]] = {}
        for path in sorted((CLIENT / MAP_DIR).iterdir()):
            if path.suffix.lower() in strip.MAP_SUFFIXES:
                maps.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), []).append(path.name)
        self.assertTrue(maps)
        contract = strip.read_contract((CLIENT / strip.LIBRARY).read_text(encoding="utf-8"))
        files = removed = 0
        for folder in strip.RL_GLB_DIRS:
            for path in sorted((CLIENT / folder).glob("*.glb")):
                data = path.read_bytes()
                document, binary = strip.read_glb(data)
                embedded = [i for i, image in enumerate(document.get("images", [])) if "bufferView" in image]
                new, result = strip.strip_glb(data, maps, contract)
                self.assertEqual(result["kept"], [], path.name)
                self.assertEqual([r["image"] for r in result["removed"]], embedded, path.name)
                if new is not None:
                    files += 1
                    removed += len(embedded)
                    self.assertNotIn("images", strip.read_glb(new)[0], path.name)
        self.assertGreater(files, 0)
        self.assertGreater(removed, 0)


if __name__ == "__main__":
    unittest.main()
