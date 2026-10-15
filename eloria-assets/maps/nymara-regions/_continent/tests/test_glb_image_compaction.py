import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

HERE = Path(__file__).resolve().parents[1]
TOOLKIT = HERE.parent / "_toolkit"
sys.path[:0] = [str(HERE), str(TOOLKIT)]

from amberwood import gltf as G, mesh as M
from compact_glb_images import (GlbCompactionError, _chunks,
                                compact_document, compact_embedded_images)


def view_bytes(document, binary, index):
    view = document["bufferViews"][index]
    start = view.get("byteOffset", 0)
    return bytes(binary[start:start + view["byteLength"]])


class ImageCompactionTests(unittest.TestCase):
    def fixture(self, path):
        builder = G.GltfBuilder("image compaction fixture")
        repeated = b"\x89PNG\r\n\x1a\nrepeated-payload"
        distinct = b"\x89PNG\r\n\x1a\ndistinct-payload"
        builder.add_image("repeated-a", repeated)
        builder.add_image("distinct", distinct)
        builder.add_image("repeated-b", repeated)
        for name, image in (("one", "repeated-a"), ("two", "distinct"),
                            ("three", "repeated-b")):
            builder.add_material(G.Material(name, base_color_texture=image))
            builder.add_mesh(name, M.box((1, 1, 1), material=name))
            builder.add_node(G.Node(name, mesh=name))
        builder.write_glb(str(path))

    def test_exact_image_payloads_share_storage_without_changing_scene_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.glb"
            self.fixture(path)
            before_document, before_binary = _chunks(path.read_bytes())
            before_document_copy = copy.deepcopy(before_document)
            before_views = [view_bytes(before_document, before_binary, index)
                            for index in range(len(before_document["bufferViews"]))]
            before_size = path.stat().st_size

            report = compact_embedded_images(path)
            after_document, after_binary = _chunks(path.read_bytes())
            after_views = [view_bytes(after_document, after_binary, index)
                           for index in range(len(after_document["bufferViews"]))]

            self.assertEqual(before_views, after_views)
            self.assertEqual(len(before_document["bufferViews"]), len(after_document["bufferViews"]))
            self.assertEqual(len(before_document["images"]), len(after_document["images"]))
            self.assertEqual(len(before_document["textures"]), len(after_document["textures"]))
            for key in ("asset", "scene", "scenes", "nodes", "meshes", "materials",
                        "accessors", "images", "textures", "samplers"):
                self.assertEqual(before_document_copy[key], after_document[key], key)
            for old, new in zip(before_document_copy["bufferViews"], after_document["bufferViews"]):
                self.assertEqual({k: v for k, v in old.items() if k != "byteOffset"},
                                 {k: v for k, v in new.items() if k != "byteOffset"})
                self.assertEqual(new.get("byteOffset", 0) % 4, 0)
            duplicate_views = [image["bufferView"] for image in after_document["images"]
                               if image["name"].startswith("repeated")]
            self.assertEqual(len(duplicate_views), 2)
            self.assertEqual(after_document["bufferViews"][duplicate_views[0]]["byteOffset"],
                             after_document["bufferViews"][duplicate_views[1]]["byteOffset"])
            self.assertEqual(report["aliasedImageBufferViews"], 1)
            self.assertEqual(report["uniqueImagePayloads"], 2)
            self.assertLess(path.stat().st_size, before_size)
            second = compact_embedded_images(path)
            self.assertEqual(second["aliasedImageBufferViews"], 1)
            self.assertEqual(second["beforeBytes"], second["afterBytes"])

    def test_all_exact_views_share_aligned_storage_and_preserve_logical_bytes(self):
        repeated = b"seven77"
        collision = b"other77"
        odd = b"odd"
        document = {
            "buffers": [{"byteLength": 35}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 7, "target": 34963},
                {"buffer": 0, "byteOffset": 8, "byteLength": 3},
                {"buffer": 0, "byteOffset": 12, "byteLength": 7, "target": 34962},
                {"buffer": 0, "byteOffset": 20, "byteLength": 7, "target": 34963},
                {"buffer": 0, "byteOffset": 28, "byteLength": 7, "target": 34963},
            ],
            "accessors": [{"bufferView": index} for index in range(5)],
            "images": [],
        }
        binary = (repeated + b"\0" + odd + b"\0" + repeated + b"\0"
                  + repeated + b"\0" + collision)
        before = copy.deepcopy(document)
        before_views = [view_bytes(document, binary, index) for index in range(5)]

        # Force every payload into one digest bucket. Exact equality, rather
        # than the digest alone, must decide which ranges may be shared.
        digest = mock.Mock()
        digest.digest.return_value = b"collision"
        with mock.patch("compact_glb_images.hashlib.sha256", return_value=digest):
            after, compacted, report = compact_document(document, binary)

        self.assertEqual(before_views,
                         [view_bytes(after, compacted, index) for index in range(5)])
        self.assertEqual(report["aliasedBufferViews"], 2)
        self.assertEqual(report["uniqueBufferViewPayloads"], 3)
        self.assertEqual(after["bufferViews"][0]["byteOffset"],
                         after["bufferViews"][2]["byteOffset"])
        self.assertEqual(after["bufferViews"][0]["byteOffset"],
                         after["bufferViews"][3]["byteOffset"])
        self.assertNotEqual(after["bufferViews"][0]["byteOffset"],
                            after["bufferViews"][4]["byteOffset"])
        for old, new in zip(before["bufferViews"], after["bufferViews"]):
            self.assertEqual({k: v for k, v in old.items() if k != "byteOffset"},
                             {k: v for k, v in new.items() if k != "byteOffset"})
            self.assertEqual(new["byteOffset"] % 4, 0)
        self.assertEqual(len(compacted) % 4, 0)

    def test_unsupported_or_ambiguous_buffer_structures_fail_closed(self):
        document = {"buffers": [{"byteLength": 8, "uri": "external.bin"}],
                    "bufferViews": [], "images": []}
        with self.assertRaisesRegex(GlbCompactionError, "one embedded"):
            compact_document(document, b"\0" * 8)

        document = {"buffers": [{"byteLength": 8}],
                    "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 8}],
                    "images": [{"bufferView": 0, "mimeType": "image/png"}],
                    "accessors": [{"bufferView": 0}]}
        with self.assertRaisesRegex(GlbCompactionError, "image and accessor"):
            compact_document(document, b"\0" * 8)

        document = {"buffers": [{"byteLength": 12}],
                    "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 8},
                                    {"buffer": 0, "byteOffset": 4, "byteLength": 8}],
                    "images": [{"bufferView": 0, "mimeType": "image/png"},
                               {"bufferView": 1, "mimeType": "image/png"}]}
        with self.assertRaisesRegex(GlbCompactionError, "partially overlap"):
            compact_document(document, b"\0" * 12)


if __name__ == "__main__":
    unittest.main()
