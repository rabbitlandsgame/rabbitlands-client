"""The shared prototype pass: identity, round trip, idempotence.

`eloria-assets/tools/shared_meshes.py` moves a mesh that repeats across map
files into one content-addressed prototype and leaves the placement as a node
with the same name. Three properties decide whether a package survives it:

  * identity covers geometry and appearance, and nothing else. A prototype that
    rehashed when a tree moved would rewrite the pool, and with it every
    manifest, digest and client cache entry, on every republish.
  * the placement draws what the package drew: same geometry bytes, same
    material, same node name, same transform.
  * running the pass again changes nothing, so a republish of one region does
    not touch another's packages.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

CLIENT = Path(__file__).resolve().parents[1]
REPO = CLIENT.parent
TOOL = REPO / "eloria-assets" / "tools" / "shared_meshes.py"
sys.path.insert(0, str(TOOL.parent))
import shared_meshes as SM  # noqa: E402


def glb(document: dict, binary: bytes = b"") -> bytes:
    return SM.write_glb(document, binary)


def one_mesh_document(positions: bytes, material_name: str = "bark", name: str = "Prop") -> tuple[dict, bytes]:
    """A minimal two-node document: one mesh, placed twice."""
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, 1]}],
        "nodes": [
            {"name": name + "_a", "mesh": 0, "translation": [1, 0, 0]},
            {"name": name + "_b", "mesh": 0, "translation": [9, 0, 0]},
        ],
        "meshes": [{"name": "prop_mesh", "primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
        "materials": [{"name": material_name, "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(positions) // 12,
                       "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(positions)}],
        "buffers": [{"byteLength": len(positions)}],
    }
    return document, positions


class SharedMeshIdentityTest(unittest.TestCase):
    def setUp(self):
        self.positions = struct.pack("<9f", *[float(v) for v in range(9)])

    def test_identity_ignores_placement_name_and_transform(self):
        a, binary = one_mesh_document(self.positions, name="Oak")
        b, _ = one_mesh_document(self.positions, name="Pine")
        b["nodes"][0]["translation"] = [77, 3, -4]
        b["meshes"][0]["name"] = "another_name"
        first = SM.mesh_identity(a, binary, 0, Path("a.glb"), {})[0]
        second = SM.mesh_identity(b, binary, 0, Path("b.glb"), {})[0]
        self.assertEqual(first, second, "a moved or renamed placement must not rehash the prototype")

    def test_identity_follows_geometry_and_material(self):
        a, binary = one_mesh_document(self.positions)
        moved = struct.pack("<9f", *[float(v) + 0.5 for v in range(9)])
        b, other = one_mesh_document(moved)
        self.assertNotEqual(SM.mesh_identity(a, binary, 0, Path("a.glb"), {})[0],
                            SM.mesh_identity(b, other, 0, Path("b.glb"), {})[0])
        c, _ = one_mesh_document(self.positions, material_name="stone")
        c["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"] = [0.2, 0.2, 0.2, 1]
        self.assertNotEqual(SM.mesh_identity(a, binary, 0, Path("a.glb"), {})[0],
                            SM.mesh_identity(c, binary, 0, Path("c.glb"), {})[0])

    def test_material_name_alone_does_not_rehash(self):
        a, binary = one_mesh_document(self.positions, material_name="bark")
        b, _ = one_mesh_document(self.positions, material_name="bark_renamed")
        self.assertEqual(SM.mesh_identity(a, binary, 0, Path("a.glb"), {})[0],
                         SM.mesh_identity(b, binary, 0, Path("b.glb"), {})[0])


class SharedMeshApplyTest(unittest.TestCase):
    """The whole pass over a sandbox of two packages that share one prop."""

    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp(prefix="shared-meshes-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        positions = struct.pack("<9f", *[float(v) for v in range(9)]) * 400  # over MIN_BYTES
        self.before = {}
        for region in ("north", "south"):
            package = self.root / "continent-v2" / region / "client"
            package.mkdir(parents=True)
            document, binary = one_mesh_document(positions, name=f"Walk_{region}_oak")
            (package / "world.glb").write_bytes(glb(document, binary))
            (package / "world.json").write_text(json.dumps({"asset": {"id": region}}), encoding="utf-8")
            self.before[region] = (document, binary)
        self.env = dict(os.environ, ELORIA_MAPS_ROOT=str(self.root))

    def run_tool(self, *args) -> str:
        done = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                              env=self.env, cwd=str(REPO))
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_apply_shares_the_prop_and_keeps_every_placement(self):
        self.run_tool("--apply", "--sets", "continent-v2")
        pool = sorted((self.root / "_shared" / "meshes").glob("*.glb"))
        self.assertEqual(len(pool), 1, "the prop both packages carry becomes one prototype")

        for region in ("north", "south"):
            package = self.root / "continent-v2" / region / "client"
            document, binary = SM.read_glb(package / "world.glb")
            self.assertEqual(document.get("meshes", []), [], "the copy is gone from the package")
            names = [node.get("name") for node in document["nodes"]]
            self.assertEqual(names, [node.get("name") for node in self.before[region][0]["nodes"]],
                             "placements keep their names")
            for node in document["nodes"]:
                self.assertNotIn("mesh", node)
                self.assertIn(SM.PROTOTYPE_FIELD, node["extras"][SM.EXTRAS_KEY])
            manifest = json.loads((package / "world.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest[SM.MANIFEST_KEY]), 1)
            for uri, digest in manifest[SM.MANIFEST_KEY].items():
                target = (package / uri).resolve()
                self.assertTrue(target.is_file(), f"{uri} resolves from the package")
                self.assertEqual(SM.sha256(target.read_bytes()), digest)

        # The prototype draws what the packages drew.
        prototype, prototype_binary = SM.read_glb(pool[0])
        original, original_binary = self.before["north"]
        self.assertEqual(SM.mesh_identity(prototype, prototype_binary, 0, pool[0], {})[0],
                         SM.mesh_identity(original, original_binary, 0, Path("x.glb"), {})[0])

    def test_second_run_changes_nothing(self):
        self.run_tool("--apply", "--sets", "continent-v2")
        stamp = {path: path.read_bytes() for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.run_tool("--apply", "--sets", "continent-v2")
        after = {path: path.read_bytes() for path in sorted(self.root.rglob("*")) if path.is_file()}
        self.assertEqual(sorted(stamp), sorted(after), "no file appears or disappears on a second run")
        for path, data in stamp.items():
            self.assertEqual(data, after[path], f"{path.name} changed on a second run")

    def test_a_reader_sees_the_shared_package_as_it_was(self):
        """inline_prototypes, as glb_reader.load runs it: the mesh back on each
        placement and the pool reference gone, so a tool that writes the
        document out again does not make the client draw the prop twice."""
        self.run_tool("--apply", "--sets", "continent-v2")
        path = self.root / "continent-v2" / "north" / "client" / "world.glb"
        SM._prototype.cache_clear()
        self.addCleanup(SM._prototype.cache_clear)
        with mock.patch.object(SM, "POOL", self.root / "_shared" / "meshes"):
            document, binary = SM.inline_prototypes(path, *SM.read_glb(path))
        original, original_binary = self.before["north"]
        self.assertEqual(document["nodes"], original["nodes"])
        self.assertEqual(SM.mesh_identity(document, binary, 0, path, {})[0],
                         SM.mesh_identity(original, original_binary, 0, Path("x.glb"), {})[0])


if __name__ == "__main__":
    unittest.main()
