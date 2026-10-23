"""Fake PCK/stage evidence tests. No engine, real package, GPU or network."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT / "tools"))
sys.path.insert(0, str(CLIENT / "tests/integration"))
import benchmark_asset_closure as closure
import benchmark_package
import crowd_benchmark_support as support


def write_pck(path, rows, version=4, flags=2, absolute_v2=False):
    """Independent tiny writer with format2's front directory and3/4's tail."""
    rows = [dict(row) for row in rows]
    header_size = 96 if version == 2 else 104
    names = []
    for row in rows:
        name = row["path"].encode("utf-8")
        names.append(name + b"\0" * (-len(name) % 4))
    directory_size = 4 + sum(40 + len(name) for name in names)
    base = header_size + directory_size if version == 2 else header_size
    data = b"".join(row["data"] for row in rows)
    directory = header_size if version == 2 else base + len(data)
    if absolute_v2 and version != 2:
        raise ValueError("absolute base fixture is format 2 only")
    header = b"GDPC" + struct.pack("<4IIQ", version, 4, 7, 2, 0 if absolute_v2 else flags,
                                   0 if absolute_v2 else base)
    if version != 2:
        header += struct.pack("<Q", directory)
    header += bytes(64)
    assert len(header) == header_size
    table, positions, offset = bytearray(struct.pack("<I", len(rows))), [], 0
    for name, row in zip(names, rows):
        table += struct.pack("<I", len(name)) + name
        positions.append(directory + len(table))
        table += struct.pack("<QQ", row.get("offset", offset) + (base if absolute_v2 else 0),
                             row.get("size", len(row["data"])))
        # Deliberately invalid/non-content MD5: evidence must read actual bytes.
        table += b"m" * 16 + struct.pack("<I", row.get("flags", 0))
        offset += len(row["data"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + table + data if version == 2 else header + data + table)
    return positions


def asset_rows(code=b"code", scene=b"scene", asset=b"asset", release=b"commit-a"):
    return [{"path": path, "data": data} for path, data in (
        ("res://assets/model.bin", asset), ("data/catalog.json", b"catalog"),
        (".godot/imported/texture.ctex", b"texture"), (".godot/imported/keep.gdc", b"import-product"),
        ("src/main.gdc", code), ("src/main.gd.remap", b"script-remap"),
        ("src/main.gd.uid", b"script-uid"), (".godot/exported/main.scn", scene),
        ("src/material.tres.remap", b"resource-remap"), ("unknown-root/extra.dat", b"unknown-asset"),
        ("data/client_release.json", release), ("data/benchmark_profile.json", b"profile"),
        ("project.binary", b"project"), (".godot/uid_cache.bin", b"cache"))]


def stage_fixture(stage, **kwargs):
    pack = stage / "app/RabbitLands.pck"
    write_pck(pack, asset_rows(**kwargs))
    for relative, content in (("app/RabbitLands.exe", b"exe"), ("app/assets/actor.glb", b"actor"),
            ("app/data/models.json", b"models"), ("app/schemas/world.json", b"schema"),
            ("eloria-assets/maps/shared-assets/vram/image.bptc", b"encoded"),
            ("unknown-pool/mesh.bin", b"pool"), ("app/client-release.json", b"commit"),
            ("README.txt", b"version"), (".eloria-package", b"commit")):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return pack


class AssetClosureTests(unittest.TestCase):
    def test_formats_two_three_four_have_identical_actual_asset_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hashes = []
            for version in (2, 3, 4):
                stage = root / str(version)
                stage_fixture(stage)
                write_pck(stage / closure.PCK_PATH, asset_rows(), version)
                data = closure.build_asset_closure(stage)
                hashes.append(data["contentHash"])
                actual = closure.verify_asset_closure(stage, json.loads(json.dumps(data)))
                self.assertEqual(actual["scope"], "complete-exported-asset-closure")
                self.assertEqual(actual["unknowns"], [])
                self.assertEqual(actual["pckPayloadFileCount"], 7)
            self.assertEqual(len(set(hashes)), 1)

    def test_format_two_absolute_base_offsets_have_same_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            relative = closure.build_asset_closure(stage)
            write_pck(pack, asset_rows(), version=2, absolute_v2=True)
            absolute = closure.build_asset_closure(stage)
            self.assertEqual(relative["contentHash"], absolute["contentHash"])

    def test_code_generated_metadata_and_layout_changes_do_not_change_asset_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            before = closure.build_asset_closure(stage)
            write_pck(pack, asset_rows(code=b"different code shifts every following payload", release=b"commit-b"))
            (stage / "app/RabbitLands.exe").write_bytes(b"new executable")
            (stage / "README.txt").write_bytes(b"new version")
            (stage / "app/client-release.json").write_bytes(b"new commit")
            after = closure.build_asset_closure(stage)
            self.assertEqual(before["contentHash"], after["contentHash"])

    def test_scene_resource_remap_import_product_and_unknown_assets_are_included(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            original = closure.build_asset_closure(stage)
            for target in (".godot/exported/main.scn", "src/material.tres.remap",
                           ".godot/imported/keep.gdc", "unknown-root/extra.dat", "data/catalog.json"):
                rows = asset_rows()
                next(row for row in rows if row["path"] == target)["data"] += b"changed"
                write_pck(pack, rows)
                self.assertNotEqual(original["contentHash"], closure.build_asset_closure(stage)["contentHash"], target)
                with self.assertRaises(closure.AssetClosureError):
                    closure.verify_asset_closure(stage, original)
            write_pck(pack, asset_rows())
            extra = stage / "unknown-pool/new.bin"
            extra.write_bytes(b"new")
            with self.assertRaises(closure.AssetClosureError):
                closure.verify_asset_closure(stage, original)
            extra.unlink()
            (stage / "app/assets/actor.glb").unlink()
            with self.assertRaises(closure.AssetClosureError):
                closure.verify_asset_closure(stage, original)

    def test_payload_mutation_is_hashed_even_when_directory_md5_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            original = closure.build_asset_closure(stage)
            row = next(row for row in closure.pck_index(pack)["entries"] if row["path"] == "assets/model.bin")
            with pack.open("r+b") as stream:
                stream.seek(row["offset"])
                stream.write(b"ASSET")
            changed = closure.build_asset_closure(stage)
            self.assertNotEqual(original["contentHash"], changed["contentHash"])
            actual_asset = next(item for item in changed["pck"]["files"] if item["path"] == "assets/model.bin")
            self.assertEqual(actual_asset["sha256"], hashlib.sha256(b"ASSET").hexdigest())

    def test_invalid_formats_flags_paths_truncation_missing_and_overlays_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            for flags in (1, 4, 8):
                write_pck(pack, asset_rows(), flags=flags)
                with self.assertRaises(closure.AssetClosureError):
                    closure.build_asset_closure(stage)
            for path in ("../asset", "assets//double", "assets/./dot", "assets/evil\x00tail"):
                write_pck(pack, [{"path": path, "data": b"asset"}])
                with self.assertRaises(closure.AssetClosureError):
                    closure.build_asset_closure(stage)
            for entry_flag in (1, 2, 4, 8):
                write_pck(pack, [{"path": "assets/x", "data": b"x", "flags": entry_flag}])
                with self.assertRaises(closure.AssetClosureError):
                    closure.build_asset_closure(stage)
            for content in (b"not-a-pack", b"GDPC", b"GDPC" + struct.pack("<I", 5) + bytes(100)):
                pack.write_bytes(content)
                with self.assertRaises(closure.AssetClosureError):
                    closure.build_asset_closure(stage)
            pack.unlink()
            with self.assertRaises(closure.AssetClosureError):
                closure.build_asset_closure(stage)
            stage_fixture(stage)
            (stage / "app/overlay.pck").write_bytes(b"overlay")
            with self.assertRaises(closure.AssetClosureError):
                closure.build_asset_closure(stage)

    def test_duplicate_ambiguous_overlapping_or_outside_payload_ranges_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            pack = Path(directory) / "test.pck"
            cases = [
                [{"path": "assets/a", "data": b"a"}, {"path": "res://assets/a", "data": b"b"}],
                [{"path": "assets/A", "data": b"a"}, {"path": "assets/a", "data": b"b"}],
                [{"path": "assets/a", "data": b"aa"}, {"path": "assets/b", "data": b"bb", "offset": 1}],
                [{"path": "assets/a", "data": b"a", "offset": 2**63}],
                [{"path": "assets/a", "data": b"a", "size": 2**63}],
                [{"path": "assets/a", "data": b"a", "offset": 1}],  # directory begins after one payload byte
            ]
            for rows in cases:
                write_pck(pack, rows)
                with self.assertRaises(closure.AssetClosureError):
                    closure.pck_index(pack)

    def test_zero_byte_payload_is_real_empty_sha_and_scope_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            pack = stage_fixture(stage)
            write_pck(pack, asset_rows() + [{"path": "assets/empty", "data": b""}])
            data = closure.build_asset_closure(stage)
            row = next(row for row in data["pck"]["files"] if row["path"] == "assets/empty")
            self.assertEqual(row["sha256"], hashlib.sha256(b"").hexdigest())
            for key, value in (("scope", "not-covered"), ("policy", "other"), ("unknowns", ["gap"]),
                               ("coverage", {}), ("contentHash", "0" * 64)):
                bad = copy.deepcopy(data)
                bad[key] = value
                with self.assertRaises(closure.AssetClosureError):
                    closure.verify_asset_closure(stage, bad)

    def test_benchmark_manifest_and_runner_verify_actual_payload_and_self_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            stage_fixture(stage)
            manifest = benchmark_package.write_manifest(stage, "a" * 40)
            before = manifest.read_bytes()
            benchmark_package.write_manifest(stage, "a" * 40)
            self.assertEqual(before, manifest.read_bytes())
            result = support.manifest_identity(manifest)
            verified = result["assetClosure"]
            self.assertEqual(verified["status"], "complete")
            self.assertEqual(verified["scope"], closure.SCOPE)
            self.assertEqual(verified["assetClosureHash"], json.loads(before)["assetClosure"]["contentHash"])
            document = json.loads(before)
            document["assetClosure"]["pck"]["files"][0]["sha256"] = "0" * 64
            manifest.write_text(json.dumps(document))
            with self.assertRaisesRegex(support.EvidenceError, "asset closure"):
                support.manifest_identity(manifest)


if __name__ == "__main__":
    unittest.main()
