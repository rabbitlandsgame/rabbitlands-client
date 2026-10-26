"""The approved road cart must survive the real release staging policy."""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

CLIENT = Path(__file__).resolve().parents[1]
ROOT = CLIENT.parent
sys.path.insert(0, str(CLIENT / "tools"))
import package_client as packager

NATIVE = CLIENT / "world_authoring/continent-v2/kits/lf-biomes/prototypes/kit-cart.glb"
RUNTIME = CLIENT / "assets/world/campaign/road_handcart.glb"
APPROVED_SHA256 = "42b6c098a527dd09678802d0301b8f1d537f1f0f7111c167d06112a96c53d8ad"


def glb_document(path: Path) -> dict:
    raw = path.read_bytes()
    length, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A
    return json.loads(raw[20:20 + length])


def closure() -> list[Path]:
    paths = [RUNTIME]
    document = glb_document(RUNTIME)
    for image in document.get("images", []):
        uri = image.get("uri", "")
        if uri and not uri.startswith("data:"):
            paths.append((RUNTIME.parent / uri).resolve())
    return paths


class CampaignRoadPackage(unittest.TestCase):
    def test_runtime_copy_preserves_the_approved_native_bytes(self):
        self.assertEqual(RUNTIME.read_bytes(), NATIVE.read_bytes())
        self.assertEqual(hashlib.sha256(RUNTIME.read_bytes()).hexdigest(), APPROVED_SHA256)
        presenter = (CLIENT / "src/world/campaign_road_works.gd").read_text(encoding="utf-8")
        self.assertIn('const CART := "res://assets/world/campaign/road_handcart.glb"', presenter)
        self.assertNotIn('const CART := "res://world_authoring/', presenter)

    def test_every_relative_texture_is_identical_and_inside_runtime_assets(self):
        document = glb_document(RUNTIME)
        self.assertEqual(len(document["images"]), 9)
        self.assertTrue(all("uri" not in buffer for buffer in document["buffers"]))
        for image in document["images"]:
            uri = image["uri"]
            self.assertFalse(uri.startswith(("http:", "https:", "file:")))
            target = (RUNTIME.parent / uri).resolve()
            self.assertTrue(target.is_relative_to(CLIENT / "assets/world"))
            self.assertEqual(target.read_bytes(), (NATIVE.parent / uri).read_bytes())
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), target.stem)

    def test_existing_windows_and_linux_policies_include_the_runtime_closure(self):
        filters = re.findall(r'^exclude_filter="([^"]+)"', packager.EXPORT_PRESETS, re.M)
        self.assertGreaterEqual(len(filters), 2)
        for exclusions in filters:
            patterns = exclusions.split(",")
            self.assertTrue(any(fnmatch.fnmatchcase("world_authoring/kit-cart.glb", p) for p in patterns))
            for path in closure():
                local = path.relative_to(CLIENT).as_posix()
                self.assertFalse(any(fnmatch.fnmatchcase(local, p) for p in patterns), local)

    def test_real_loose_stager_preserves_the_cart_and_texture_closure(self):
        # A committed release's tracked set will contain these ten new files.
        # Use the real staging function; no PCK or full release build is needed.
        files = [path.relative_to(ROOT).as_posix() for path in closure()]

        def tracked(_build_dir, *roots):
            return [f for f in files if any(f.startswith(root + "/") for root in roots)]

        temporary_root = CLIENT / "test-artifacts"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as temporary:
            app = Path(temporary) / "app"
            with patch.object(packager, "tracked", side_effect=tracked), \
                    patch.object(packager, "pck_paths", return_value=set()), \
                    patch.object(packager, "actor_shipping", return_value={"loose": set(), "dropped": set()}), \
                    patch.object(packager, "log"):
                packager.stage_loose_client_files(ROOT, app)
            for path in closure():
                staged = app / path.relative_to(CLIENT)
                self.assertTrue(staged.is_file(), str(staged))
                self.assertEqual(staged.read_bytes(), path.read_bytes())
            self.assertFalse((app / "world_authoring").exists())


if __name__ == "__main__":
    unittest.main()
