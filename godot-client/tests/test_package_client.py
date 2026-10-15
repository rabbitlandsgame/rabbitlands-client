#!/usr/bin/env python3
"""What the packager ships of a continent-v2 map the server serves (tools/package_client.py served_v2_packages,
stage_eloria_assets, check_served_packages; serve plan CV11).

    python3 godot-client/tests/test_package_client.py -v

A served isle's client package ships: its territory world.json, every chunk, and the shared images the chunks name.
What only the server reads does not: collision.bin and served-grid.escg.gz (the server vendors the grid from the
repository, never from an installed client), nor the territory folder around the package (the editor's stub, the
server content tables). A preview row still ships nothing, and a legacy package keeps everything it shipped before.
The cases stage a small fixture tree for real, with git's file list stood in for by the fixture's own files.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))

import package_client as packager  # noqa: E402

V2 = "eloria-assets/maps/continent-v2"
SHARED = V2 + "/_continent_v2/shared-assets/ground.png"
SHARED_SHA = "a" * 64


def write(root: Path, relative: str, data) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def chunk_manifest(collision=None) -> dict:
    return {"asset": {"glb": "world.glb", "units": "meters"},
            "collision": collision if collision is not None else {"nodeNames": []},
            "externalResources": {"../../../../_continent_v2/shared-assets/ground.png": SHARED_SHA}}


def build_fixture(root: Path) -> None:
    """A checkout with one served isle, one preview isle and one legacy package, and their registry rows."""
    isle = V2 + "/isle"
    write(root, isle + "/world.json", {"asset": {"glb": "world.glb"}, "server": {"origin": [1023, 993]}})
    write(root, isle + "/content/spawns.json", {"rows": []})
    write(root, isle + "/source/prepare_meshy_kit.py", b"# editor-side source\n")
    write(root, isle + "/client/world.json", {
        "asset": {"id": "isle", "glb": "world.glb", "units": "meters"},
        "collision": {"nodeNames": [], "binary": "collision.bin", "format": "EWCG-v2",
                      "servedGrid": {"binary": "served-grid.escg.gz", "format": "ESCG-v2", "sha256": "b" * 64}},
        "externalResources": {"../../_continent_v2/shared-assets/ground.png": SHARED_SHA},
        "streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local", "chunks": [
            {"id": "00_00", "manifest": "chunks/00_00/world.json"},
            {"id": "00_01", "manifest": "chunks/00_01/world.json"}]}})
    write(root, isle + "/client/publication.json", {"schema": 1})
    write(root, isle + "/client/collision.bin", b"EWCG" + bytes(64))
    write(root, isle + "/client/served-grid.escg.gz", b"\x1f\x8b" + bytes(32))
    for chunk in ("00_00", "00_01"):
        write(root, f"{isle}/client/chunks/{chunk}/world.json", chunk_manifest())
        write(root, f"{isle}/client/chunks/{chunk}/world.glb", b"glTF" + bytes(16))
    write(root, SHARED, b"\x89PNG" + bytes(16))
    write(root, V2 + "/_continent_v2/crossings.json", {"schema": 1})
    draft = V2 + "/draft"
    write(root, draft + "/client/world.json", {"asset": {"glb": "world.glb"}})
    write(root, draft + "/client/world.glb", b"glTF" + bytes(16))
    legacy = "eloria-assets/maps/legacy"
    write(root, legacy + "/world.json", {"asset": {"glb": "world.glb"},
                                          "collision": {"binary": "collision.bin", "nodeNames": []}})
    write(root, legacy + "/world.glb", b"glTF" + bytes(16))
    write(root, legacy + "/collision.bin", b"EWCG" + bytes(16))
    write(root, packager.REGISTRY_FILE, {"schemaVersion": 1, "maps": {
        "isle": {"manifest": f"res://../{isle}/client/world.json", "status": "continent-v2-served"},
        "draft": {"manifest": f"res://../{draft}/client/world.json", "status": "continent-v2-client-preview"},
        "legacy": {"manifest": f"res://../{legacy}/world.json", "status": "production-geometry-materials-population"}}})


class ServedIsle(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="package-client-tree-"))
        self.stage = Path(tempfile.mkdtemp(prefix="package-client-stage-"))
        build_fixture(self.root)
        self._tracked = packager.tracked
        self._log = packager.log
        root = self.root

        def tracked(tree, *pathspecs):
            files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
            return [p for p in files if any(p == s or p.startswith(s.rstrip("/") + "/") for s in pathspecs)]
        packager.tracked = tracked
        packager.log = lambda message: None

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
        return served, staged, warnings

    def test_the_served_rows_are_found_with_their_territory_folders(self):
        registry = json.loads((self.root / packager.REGISTRY_FILE).read_text(encoding="utf-8"))
        self.assertEqual(packager.served_v2_packages(registry), [(V2 + "/isle/client", V2 + "/isle")])
        self.assertEqual(packager.preview_map_folders(registry), [V2 + "/draft"])

    def test_the_served_grid_and_collision_bin_never_ship(self):
        served, staged, _ = self.stage_assets()
        for name in packager.SERVER_ONLY_FILES:
            self.assertNotIn(f"{V2}/isle/client/{name}", staged)
        packager.check_served_packages(self.stage, served)

    def test_the_isle_ships_its_package_chunks_and_shared_images(self):
        _, staged, _ = self.stage_assets()
        for relative in ("isle/client/world.json", "isle/client/chunks/00_00/world.json",
                         "isle/client/chunks/00_00/world.glb", "isle/client/chunks/00_01/world.glb"):
            self.assertIn(f"{V2}/{relative}", staged)
        self.assertIn(SHARED, staged)
        # the territory manifest streams chunks: its master world.glb is named but never existed, and is no refusal
        self.assertNotIn(f"{V2}/isle/client/world.glb", staged)

    def test_the_territory_folder_around_the_package_stays_home(self):
        _, staged, _ = self.stage_assets()
        for relative in ("isle/world.json", "isle/content/spawns.json", "isle/source/prepare_meshy_kit.py",
                         "_continent_v2/crossings.json"):
            self.assertNotIn(f"{V2}/{relative}", staged)

    def test_a_preview_ships_nothing_and_a_legacy_package_keeps_its_collision(self):
        _, staged, _ = self.stage_assets()
        self.assertFalse([p for p in staged if p.startswith(V2 + "/draft/")])
        self.assertIn("eloria-assets/maps/legacy/collision.bin", staged)
        self.assertIn("eloria-assets/maps/legacy/world.glb", staged)

    def test_a_chunk_glb_missing_from_the_commit_is_refused(self):
        (self.root / V2 / "isle/client/chunks/00_01/world.glb").unlink()
        with self.assertRaisesRegex(packager.PackageError, "chunks/00_01/world.glb is not in the commit"):
            self.stage_assets()

    def test_the_check_refuses_a_staged_served_grid(self):
        served, _, _ = self.stage_assets()
        write(self.stage, V2 + "/isle/client/served-grid.escg.gz", b"\x1f\x8b")
        with self.assertRaisesRegex(packager.PackageError, "served-grid.escg.gz is read by the server only"):
            packager.check_served_packages(self.stage, served)

    def test_the_check_refuses_a_chunk_that_names_a_collision_binary(self):
        served, _, _ = self.stage_assets()
        write(self.stage, V2 + "/isle/client/chunks/00_01/world.json",
              chunk_manifest({"nodeNames": [], "binary": "collision.bin"}))
        with self.assertRaisesRegex(packager.PackageError, "chunks/00_01/world.json names a collision binary"):
            packager.check_served_packages(self.stage, served)

    def test_the_check_refuses_a_missing_chunk_and_a_stray_territory_file(self):
        served, _, _ = self.stage_assets()
        shutil.rmtree(self.stage / V2 / "isle/client/chunks/00_00")
        write(self.stage, V2 + "/isle/content/spawns.json", {"rows": []})
        with self.assertRaises(packager.PackageError) as caught:
            packager.check_served_packages(self.stage, served)
        self.assertIn("chunk 00_00 (chunks/00_00/world.json) is not staged", str(caught.exception))
        self.assertIn("isle/content/spawns.json lies outside the client package", str(caught.exception))


class CommittedRegistry(unittest.TestCase):
    def test_every_partition_section_is_served_with_a_package_and_none_is_preview(self):
        checkout = TESTS.parents[1]
        registry = json.loads((checkout / packager.REGISTRY_FILE).read_text(encoding="utf-8"))
        catalog = json.loads((TESTS.parent / "world_authoring/continent-v2/territories.json").read_text(encoding="utf-8"))
        def res_path(path):
            self.assertTrue(path.startswith("res://"))
            return (TESTS.parent / path.removeprefix("res://")).resolve()
        partition = json.loads(res_path(catalog["partitionSpecPath"]).read_text(encoding="utf-8"))
        ids = sorted(section.get("mapId", section["id"]) for section in partition["sections"])
        self.assertTrue(ids)
        self.assertEqual(sorted(entry["id"] for entry in catalog["entries"]), ids)
        self.assertEqual([package for package, _ in packager.served_v2_packages(registry)],
                         [f"{V2}/{map_id}/client" for map_id in ids])
        for entry in catalog["entries"]:
            row = registry["maps"][entry["id"]]
            self.assertEqual(row["status"], "continent-v2-served")
            self.assertEqual(row["manifest"], entry["publishedManifestPath"])
            package = res_path(entry["publishedManifestPath"])
            self.assertTrue(package.is_file(), f"missing served package: {package}")
            manifest = json.loads(package.read_text(encoding="utf-8"))
            self.assertEqual(manifest["asset"]["id"], entry["id"])
            self.assertTrue(manifest.get("streamingChunks"), f"no served chunks: {entry['id']}")
        for retired in catalog.get("retiredMapIds", []):
            self.assertNotIn(retired, registry["maps"])
        self.assertEqual(packager.preview_map_folders(registry), [])


if __name__ == "__main__":
    unittest.main()
