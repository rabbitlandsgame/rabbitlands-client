"""Mandatory image coverage/freshness and staged-package contracts; no engine."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import map_background_package as backgrounds
import package_client as packager
import asset_packages


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else (json.dumps(data) + "\n").encode())
    return path


def png(width=8, height=4):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x80\x80\x80\xff" * width) * height)) + chunk(b"IEND", b"")


def glb():
    data = json.dumps({"asset": {"version": "2.0"}, "scenes": [{"nodes": []}], "scene": 0,
                       "images": [{"uri": "cloth.png"}]}).encode()
    data += b" " * (-len(data) % 4)
    return struct.pack("<5I", 0x46546C67, 2, 20 + len(data), len(data), 0x4E4F534A) + data


class MandatoryMapBackgrounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="map-background-contract-")
        self.root = Path(self.tmp.name) / "source"
        self.stage = Path(self.tmp.name) / "stage"
        self.root.mkdir()
        self.catalog = {"schemaVersion": 1, "generator": backgrounds.GENERATOR,
                        "rendererInputs": {}, "aliases": {"hall_old": "hall"}, "maps": {}}
        for name in backgrounds.RENDERER_REQUIRED_INPUTS:
            self.catalog["rendererInputs"][name] = digest(write(self.root, name, b"fixture renderer input"))
        registry = {}
        for identity, sectioned in [("field", False), ("hall", True)]:
            base = "eloria-assets/maps/" + identity
            document = {"asset": {"id": identity, "glb": "world.glb",
                                    "bounds": {"min": [0, -2, 0], "max": [40, 10, 20]}}}
            if sectioned:
                document.update(sectioned=True, sections=[
                    {"id": "north", "bounds": {"min": [0, 0], "max": [10, 10]}},
                    {"id": "south", "bounds": {"min": [20, 10], "max": [40, 20]}}])
            manifest = write(self.root, base + "/world.json", document)
            write(self.root, base + "/world.glb", glb())
            write(self.root, base + "/cloth.png", png())
            resource = "res://../" + base + "/world.json"
            registry[identity] = {"manifest": resource}
            row = {"rendererPolicy": backgrounds.POLICY,
                   "worldMin": [0.0, 0.0], "worldMax": [40.0, 20.0],
                   "sourceInputs": backgrounds.source_inputs(self.root, manifest), "sections": {}}
            if sectioned:
                row["sectioned"] = True
                for section in document["sections"]:
                    name = section["id"]
                    image = write(self.root, "eloria-assets/maps/_backgrounds/" + identity + "-" + name + ".png", png())
                    row["sections"][name] = {"path": "res://../" + image.relative_to(self.root).as_posix(),
                        "worldMin": section["bounds"]["min"], "worldMax": section["bounds"]["max"],
                        "imageSize": [8, 4], "sha256": digest(image)}
            else:
                image = write(self.root, "eloria-assets/maps/_backgrounds/" + identity + ".png", png())
                row.update(path="res://../" + image.relative_to(self.root).as_posix(), imageSize=[8, 4], sha256=digest(image))
            self.catalog["maps"][identity] = row
        registry["hall_old"] = {"alias": "hall"}
        write(self.root, backgrounds.REGISTRY, {"maps": registry})
        self.save()

    def save(self):
        write(self.root, backgrounds.CATALOG, self.catalog)

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self):
        return backgrounds.validate_catalog(self.root, self.catalog)

    def test_complete_canonical_alias_and_section_images_qualify(self):
        self.assertEqual(self.errors(), [])
        packager.check_map_backgrounds(self.root)

    def test_missing_catalog_blocks_release(self):
        (self.root / backgrounds.CATALOG).unlink()
        with self.assertRaisesRegex(packager.PackageError, "incomplete or stale"):
            packager.check_map_backgrounds(self.root)

    def test_missing_map_or_alias_or_section_is_rejected(self):
        for change in [lambda c:c["maps"].pop("field"), lambda c:c["aliases"].clear(),
                       lambda c:c["maps"]["hall"]["sections"].pop("north")]:
            with self.subTest(change=change):
                catalog = copy.deepcopy(self.catalog)
                change(catalog)
                self.assertTrue(backgrounds.validate_catalog(self.root, catalog))

    def test_sectioned_aggregate_image_cannot_reveal_other_rooms(self):
        self.catalog["maps"]["hall"]["path"] = self.catalog["maps"]["field"]["path"]
        self.assertTrue(any("without an aggregate" in error for error in self.errors()))

    def test_bad_frame_or_image_dimensions_are_rejected(self):
        self.catalog["maps"]["field"]["worldMin"] = [1, 0]
        self.assertTrue(any("frame differs" in e for e in self.errors()))
        self.catalog["maps"]["field"]["worldMin"] = [0, 0]
        self.catalog["maps"]["field"]["imageSize"] = [4, 8]
        self.assertTrue(any("dimensions differ" in e for e in self.errors()))

    def test_changed_source_mesh_or_external_texture_invalidates_picture(self):
        path = self.root / "eloria-assets/maps/field/cloth.png"
        path.write_bytes(png(4, 8))
        self.assertTrue(any("source closure is stale" in e for e in self.errors()))

    def test_changed_renderer_or_retirement_policy_invalidates_catalog(self):
        path = self.root / "godot-client/data/assets/retired_procedural_models.json"
        path.write_bytes(b"changed retirement policy")
        self.assertTrue(any("stale input" in e for e in self.errors()))

    def test_missing_or_altered_image_cannot_qualify(self):
        image = self.root / "eloria-assets/maps/_backgrounds/field.png"
        image.write_bytes(png(4, 8))
        self.assertTrue(any("bytes differ" in e for e in self.errors()))
        image.unlink()
        self.assertTrue(self.errors())

    def test_mapview_bounds_priority_and_unknown_section(self):
        manifest = {"asset": {"mapBounds": {"min": [-4, 0, -2], "max": [6, 1, 8]},
                              "bounds": {"min": [-20, 0, -20], "max": [20, 2, 20]}},
                    "coordinateTransform": {"addressableWorldBounds": {"min": [-10, -10], "max": [10, 10]}}}
        self.assertEqual(backgrounds.frame_for(manifest), ([-4, -2], [6, 8]))
        del manifest["asset"]["mapBounds"]
        self.assertEqual(backgrounds.frame_for(manifest), ([-10, -10], [10, 10]))
        with self.assertRaisesRegex(backgrounds.BackgroundError, "Unknown section"):
            backgrounds.frame_for(manifest, "missing")

    def test_catalog_references_stage_and_enter_stable_update_packages(self):
        # The catalog alone names images outside world folders; section-only
        # pictures must be staged even when no world manifest references them.
        root = self.root
        tracked = lambda tree, *paths: [p.relative_to(root).as_posix() for p in root.rglob("*")
                                       if p.is_file() and any(p.relative_to(root).as_posix().startswith(s) for s in paths)]
        with mock.patch.object(packager, "tracked", tracked):
            wanted, errors, warnings = packager.shipped_eloria_assets(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])
            for label, row in backgrounds.picture_rows(self.catalog):
                relative = backgrounds.resource_path(root, row["path"]).relative_to(root).as_posix()
                self.assertIn(relative, wanted, label)
                destination = self.stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / relative, destination)
        self.assertEqual(backgrounds.staged_image_errors(root, self.stage), [])
        packager.check_map_backgrounds(root, self.stage)
        packages = asset_packages.build(self.stage, "https://example.test/releases/test")
        files = {entry["path"]: package["id"] for package in packages for entry in package["files"]}
        for label, row in backgrounds.picture_rows(self.catalog):
            relative = backgrounds.resource_path(root, row["path"]).relative_to(root).as_posix()
            self.assertEqual(files[relative], asset_packages.package_id(relative))
        target = self.stage / "eloria-assets/maps/_backgrounds/hall-north.png"
        target.write_bytes(b"corrupt payload")
        self.assertTrue(any("Staged background differs" in e for e in backgrounds.staged_image_errors(root, self.stage)))
        target.unlink()
        self.assertTrue(any("missing from staged" in e for e in backgrounds.staged_image_errors(root, self.stage)))

    def test_runtime_catalog_must_ship_in_pack_and_match_loose_copy(self):
        app = self.stage / "app"
        loose = write(app, "data/maps/map-backgrounds.json", self.catalog)
        # Directory-only fixture is sufficient for the normal packager's
        # resource-presence check; no engine or full package is involved.
        def pack(names):
            header = b"GDPC" + struct.pack("<4I", 4, 4, 7, 2) + struct.pack("<I", 2)
            offset = len(header) + 16 + 64
            directory = struct.pack("<I", len(names))
            for name in names:
                raw = name.encode()
                raw += b"\0" * (-len(raw) % 4)
                directory += struct.pack("<I", len(raw)) + raw + bytes(36)
            (app / "RabbitLands.pck").write_bytes(header + struct.pack("<QQ", 0, offset) + bytes(64) + directory)
        pack([])
        with self.assertRaisesRegex(packager.PackageError, "missing from the PCK"):
            packager.check_map_background_export(self.root, app)
        pack(["data/maps/map-backgrounds.json"])
        packager.check_map_background_export(self.root, app)
        loose.write_bytes(b"old catalog")
        with self.assertRaisesRegex(packager.PackageError, "differs in staged"):
            packager.check_map_background_export(self.root, app)


if __name__ == "__main__":
    unittest.main()
