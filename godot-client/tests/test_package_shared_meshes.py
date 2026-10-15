#!/usr/bin/env python3
"""What the packager ships of the shared prototype mesh pool (tools/package_client.py shipped_eloria_assets,
check_shared_meshes, report_duplicate_geometry; eloria-assets/tools/shared_meshes.py).

    python3 godot-client/tests/test_package_shared_meshes.py -v

eloria-assets/tools/shared_meshes.py publishes a mesh that repeats across map files once, as
maps/_shared/meshes/<sha256>.glb with an index.json beside it, and the manifests name the prototypes their
placements draw under "externalMeshes". The pool holds no world.json, so no map package carries it: the packager
must pull in exactly the prototypes a shipped manifest names - a preview map's prototype is not one of them - and
must refuse a package whose prototype did not ship or is not the file the manifest recorded, which no other check
would notice (the placement keeps its name and transform, so collision and the look pass are satisfied and only
the geometry is gone). The cases stage a small fixture tree for real, with git's file list stood in for by the
fixture's own files, as test_package_client.py does.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))

import package_client as packager  # noqa: E402

MAPS = "eloria-assets/maps"
POOL = MAPS + "/_shared/meshes"
IMAGE = MAPS + "/_shared/shared-assets/bark.png"
VILLAGE = MAPS + "/village"
HAMLET = MAPS + "/hamlet"
DRAFT = MAPS + "/continent-v2/draft"
ISLE = MAPS + "/continent-v2/isle"
CHUNK = ISLE + "/client/chunks/00_00"
# A prototype's file name is its identity (geometry and appearance), never the sha256 of the written file: the
# manifests and the index record the file's bytes separately, and a check that confused the two would pass.
SHIPPED_ID = "a" * 64
PREVIEW_ID = "b" * 64
CHUNK_ID = "c" * 64
BIG = bytes((i * 7 + 3) % 251 for i in range(7200))
OTHER = bytes((i * 11 + 5) % 251 for i in range(7200))
THIRD = bytes((i * 17 + 9) % 251 for i in range(7200))
SMALL = bytes((i * 13 + 1) % 251 for i in range(1200))


def write(root: Path, relative: str, data) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def glb(blobs: list[bytes], images: list[str] = ()) -> bytes:
    """A GLB holding one single-primitive mesh per blob, each primitive's POSITION accessor over those bytes."""
    document: dict = {"asset": {"version": "2.0"}, "meshes": [], "accessors": [], "bufferViews": []}
    packed = bytearray()
    for index, blob in enumerate(blobs):
        document["bufferViews"].append({"buffer": 0, "byteOffset": len(packed), "byteLength": len(blob)})
        packed.extend(blob)
        document["accessors"].append({"bufferView": index, "componentType": 5126, "type": "VEC3",
                                      "count": len(blob) // 12})
        document["meshes"].append({"primitives": [{"attributes": {"POSITION": index}}]})
    if images:
        document["images"] = [{"uri": uri} for uri in images]
    document["buffers"] = [{"byteLength": len(packed)}]
    text = json.dumps(document, separators=(",", ":")).encode("utf-8")
    text += b" " * ((-len(text)) % 4)
    binary = bytes(packed) + b"\0" * ((-len(packed)) % 4)
    chunks = (struct.pack("<II", len(text), 0x4E4F534A) + text
              + struct.pack("<II", len(binary), 0x004E4942) + binary)
    return struct.pack("<III", 0x46546C67, 2, 12 + len(chunks)) + chunks


def build_fixture(root: Path) -> dict[str, str]:
    """A checkout with the pool and three kinds of package: a legacy one and a served isle's chunk that name a
    prototype, and a preview that names one of its own.

    Returns the sha256 of each prototype file, as the manifests and the index record it.
    """
    prototypes = {SHIPPED_ID: glb([OTHER], ["../shared-assets/bark.png"]), PREVIEW_ID: glb([SMALL]),
                  CHUNK_ID: glb([THIRD])}
    shas = {}
    index: dict = {"schema": "eloria-shared-meshes-v1", "prototypes": {}}
    for identity, data in prototypes.items():
        write(root, f"{POOL}/{identity}.glb", data)
        shas[identity] = hashlib.sha256(data).hexdigest()
        index["prototypes"][identity] = {"bytes": len(data), "sha256": shas[identity], "primitives": 1}
    write(root, f"{POOL}/{packager.SHARED_MESH_INDEX}", index)
    write(root, IMAGE, b"\x89PNG" + bytes(16))

    write(root, VILLAGE + "/world.json", {
        "asset": {"glb": "world.glb", "units": "meters"},
        "collision": {"nodeNames": []},
        packager.SHARED_MESH_KEY: {f"../_shared/meshes/{SHIPPED_ID}.glb": shas[SHIPPED_ID]}})
    write(root, VILLAGE + "/world.glb", glb([BIG, SMALL]))
    write(root, HAMLET + "/world.json", {"asset": {"glb": "world.glb"}, "collision": {"nodeNames": []}})
    write(root, HAMLET + "/world.glb", glb([BIG, SMALL]))
    write(root, DRAFT + "/client/world.json", {
        "asset": {"glb": "world.glb", "units": "meters"},
        packager.SHARED_MESH_KEY: {f"../../../_shared/meshes/{PREVIEW_ID}.glb": shas[PREVIEW_ID]}})
    write(root, DRAFT + "/client/world.glb", glb([OTHER]))
    # A served isle: only its client package ships, and the prototypes are named per chunk, as publish_client.py
    # writes them (the territory manifest streams the chunks and carries no geometry of its own).
    write(root, ISLE + "/world.json", {"asset": {"glb": "world.glb"}, "server": {"origin": [1023, 993]}})
    write(root, ISLE + "/client/world.json", {
        "asset": {"id": "isle", "glb": "world.glb", "units": "meters"},
        "collision": {"nodeNames": [], "binary": "collision.bin"},
        "streamingChunks": {"schemaVersion": "1.0",
                            "chunks": [{"id": "00_00", "manifest": "chunks/00_00/world.json"}]}})
    write(root, ISLE + "/client/collision.bin", b"EWCG" + bytes(64))
    write(root, CHUNK + "/world.json", {
        "asset": {"glb": "world.glb", "units": "meters"},
        "collision": {"nodeNames": []},
        packager.SHARED_MESH_KEY: {f"../../../../../_shared/meshes/{CHUNK_ID}.glb": shas[CHUNK_ID]}})
    write(root, CHUNK + "/world.glb", glb([BIG]))
    write(root, packager.REGISTRY_FILE, {"schemaVersion": 1, "maps": {
        "village": {"manifest": f"res://../{VILLAGE}/world.json",
                    "status": "production-geometry-materials-population"},
        "hamlet": {"manifest": f"res://../{HAMLET}/world.json",
                   "status": "production-geometry-materials-population"},
        "isle": {"manifest": f"res://../{ISLE}/client/world.json", "status": "continent-v2-served"},
        "draft": {"manifest": f"res://../{DRAFT}/client/world.json", "status": "continent-v2-client-preview"}}})
    return shas


class SharedMeshPool(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="package-meshes-tree-"))
        self.stage = Path(tempfile.mkdtemp(prefix="package-meshes-stage-"))
        self.shas = build_fixture(self.root)
        self.messages: list[str] = []
        self._tracked = packager.tracked
        self._log = packager.log
        root = self.root

        def tracked(tree, *pathspecs):
            files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
            return [p for p in files if any(p == s or p.startswith(s.rstrip("/") + "/") for s in pathspecs)]
        packager.tracked = tracked
        packager.log = self.messages.append

    def tearDown(self):
        packager.tracked = self._tracked
        packager.log = self._log
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.stage, ignore_errors=True)

    def stage_assets(self):
        """main()'s order: the preview rows leave the build tree's registry, then the stage is made."""
        previews = packager.drop_preview_maps(self.root)
        served = packager.read_served_v2_packages(self.root)
        warnings = packager.stage_eloria_assets(self.root, self.stage, previews, served)
        staged = sorted(p.relative_to(self.stage).as_posix() for p in self.stage.rglob("*") if p.is_file())
        return staged, warnings

    def test_the_pool_ships_what_a_shipped_manifest_names_with_its_index(self):
        staged, warnings = self.stage_assets()
        self.assertIn(f"{POOL}/{SHIPPED_ID}.glb", staged)
        self.assertIn(f"{POOL}/{packager.SHARED_MESH_INDEX}", staged)
        self.assertIn(IMAGE, staged)
        self.assertEqual(warnings, [])
        staged_prototype = (self.stage / POOL / f"{SHIPPED_ID}.glb").read_bytes()
        self.assertEqual(hashlib.sha256(staged_prototype).hexdigest(), self.shas[SHIPPED_ID])

    def test_a_served_isles_chunk_pulls_its_prototype_in(self):
        staged, _ = self.stage_assets()
        self.assertIn(f"{CHUNK}/world.json", staged)
        self.assertIn(f"{POOL}/{CHUNK_ID}.glb", staged)
        self.assertNotIn(f"{ISLE}/client/collision.bin", staged)

    def test_a_prototype_only_a_preview_names_ships_nowhere(self):
        staged, _ = self.stage_assets()
        self.assertNotIn(f"{POOL}/{PREVIEW_ID}.glb", staged)
        self.assertFalse([p for p in staged if p.startswith(DRAFT + "/")])

    def test_a_prototype_missing_from_the_commit_is_refused(self):
        (self.root / POOL / f"{SHIPPED_ID}.glb").unlink()
        with self.assertRaisesRegex(packager.PackageError, f"{SHIPPED_ID}.glb is not in the commit"):
            self.stage_assets()

    def test_a_pool_index_missing_from_the_commit_is_refused(self):
        (self.root / POOL / packager.SHARED_MESH_INDEX).unlink()
        with self.assertRaisesRegex(packager.PackageError, "index.json is not in the commit"):
            self.stage_assets()

    def test_an_image_a_prototype_names_and_the_package_lacks_is_a_warning(self):
        (self.root / IMAGE).unlink()
        staged, warnings = self.stage_assets()
        self.assertIn(f"{POOL}/{SHIPPED_ID}.glb", staged)
        self.assertTrue([w for w in warnings if "bark.png" in w and "does not ship" in w], warnings)

    def test_the_check_passes_and_reports_what_the_package_left_behind(self):
        self.stage_assets()
        self.messages.clear()
        packager.check_shared_meshes(self.root, self.stage)
        self.assertIn("2 prototypes staged of 3 published", " ".join(self.messages))

    def test_the_check_refuses_a_prototype_that_did_not_ship(self):
        self.stage_assets()
        (self.stage / POOL / f"{SHIPPED_ID}.glb").unlink()
        with self.assertRaisesRegex(packager.PackageError, "is not in the package"):
            packager.check_shared_meshes(self.root, self.stage)

    def test_the_check_refuses_a_prototype_that_is_not_the_file_the_manifest_named(self):
        self.stage_assets()
        (self.stage / POOL / f"{SHIPPED_ID}.glb").write_bytes(glb([BIG]))
        with self.assertRaisesRegex(packager.PackageError, "sha256 differs from the one"):
            packager.check_shared_meshes(self.root, self.stage)

    def test_the_check_refuses_a_pool_without_its_index(self):
        self.stage_assets()
        (self.stage / POOL / packager.SHARED_MESH_INDEX).unlink()
        with self.assertRaisesRegex(packager.PackageError, "index.json is not in the package"):
            packager.check_shared_meshes(self.root, self.stage)

    def test_the_check_refuses_an_index_that_does_not_describe_what_shipped(self):
        self.stage_assets()
        write(self.stage, f"{POOL}/{packager.SHARED_MESH_INDEX}",
              {"schema": "eloria-shared-meshes-v1",
               "prototypes": {SHIPPED_ID: {"bytes": 1, "sha256": "c" * 64, "primitives": 1}}})
        with self.assertRaisesRegex(packager.PackageError, "sha256 of .* differs from the file"):
            packager.check_shared_meshes(self.root, self.stage)

    def test_the_check_refuses_a_prototype_no_staged_manifest_names(self):
        self.stage_assets()
        shutil.copyfile(self.root / POOL / f"{PREVIEW_ID}.glb", self.stage / POOL / f"{PREVIEW_ID}.glb")
        with self.assertRaisesRegex(packager.PackageError, "no staged manifest names it"):
            packager.check_shared_meshes(self.root, self.stage)

    def test_the_check_is_quiet_about_a_package_that_names_no_prototype(self):
        for manifest in (VILLAGE + "/world.json", CHUNK + "/world.json"):
            data = json.loads((self.root / manifest).read_text(encoding="utf-8"))
            del data[packager.SHARED_MESH_KEY]
            write(self.root, manifest, data)
        self.stage_assets()
        self.messages.clear()
        packager.check_shared_meshes(self.root, self.stage)
        self.assertIn("no staged manifest names a prototype", " ".join(self.messages))


class DuplicateGeometryScan(unittest.TestCase):
    """The reporting scan: what geometry two staged map GLBs still hold byte for byte."""

    def setUp(self):
        self.stage = Path(tempfile.mkdtemp(prefix="package-meshes-scan-"))
        self.messages: list[str] = []
        self._log = packager.log
        packager.log = self.messages.append
        # BIG is in both packages and SMALL in both as well, under the scan's floor; OTHER is in one.
        write(self.stage, VILLAGE + "/world.glb", glb([BIG, SMALL]))
        write(self.stage, HAMLET + "/world.glb", glb([BIG, SMALL, OTHER]))

    def tearDown(self):
        packager.log = self._log
        shutil.rmtree(self.stage, ignore_errors=True)

    def test_it_counts_the_shared_primitive_and_skips_the_small_one(self):
        report = packager.report_duplicate_geometry(self.stage)
        self.assertEqual(report, {"bytes": len(BIG), "files": 2, "scanned": 2, "total": 2})
        self.assertIn(f"duplicate map geometry: {len(BIG) / 1e6:.0f} MB across 2 files "
                      "(shared_meshes.py --apply removes it)", self.messages)

    def test_a_spent_budget_samples_and_says_so(self):
        report = packager.report_duplicate_geometry(self.stage, budget=-1.0)
        self.assertEqual((report["scanned"], report["total"]), (1, 2))
        self.assertIn("sampled 1 of 2 files", " ".join(self.messages))

    def test_a_file_that_is_not_gltf_is_no_failure(self):
        write(self.stage, VILLAGE + "/broken.glb", b"not a glb at all")
        self.assertEqual(packager.report_duplicate_geometry(self.stage)["bytes"], len(BIG))


if __name__ == "__main__":
    unittest.main()
