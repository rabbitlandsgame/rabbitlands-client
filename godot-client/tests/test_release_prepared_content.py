"""Fresh release-coordinator contracts; fake cooker, no engine or network."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import prepared_content_package as prepared
import release_prepared_content as release


def glb(document):
    data = json.dumps(document).encode()
    data += b" " * (-len(data) % 4)
    body = struct.pack("<II", len(data), 0x4E4F534A) + data
    return struct.pack("<4sII", b"glTF", 2, len(body) + 12) + body


def write_pck(path, rows):
    data = b"".join(value for _name, value in rows)
    start = 104
    header = b"GDPC" + struct.pack("<4IIQQ", 4, 4, 7, 2, 2, start, start + len(data)) + bytes(64)
    table = bytearray(struct.pack("<I", len(rows)))
    offset = 0
    for name, content in rows:
        name = name.encode()
        name += bytes(-len(name) % 4)
        table += struct.pack("<I", len(name)) + name
        table += struct.pack("<QQ", offset, len(content)) + b"m" * 16 + struct.pack("<I", 0)
        offset += len(content)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + data + table)


class ReleasePreparedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "source/godot-client"
        self.project.mkdir(parents=True)
        (self.project / "project.godot").write_text("config_version=5\n")
        (self.project.parent / ".git").write_text("gitdir: owned-disposable-test\n")
        (self.project / ".godot/imported").mkdir(parents=True)
        self.scene_name = "godot-client/assets/world/synthetic.glb"
        self.scene = prepared.scoped(self.project.parent, self.scene_name)
        self.scene.parent.mkdir(parents=True)
        self.scene.write_bytes(glb({"asset": {"version": "2.0"}, "images": [{"uri": "external.jpg"}]}))
        self.image = self.scene.parent / "external.jpg"
        self.image.write_bytes(b"source import image")
        self.remap = self.scene.parent / "external.jpg.import"
        self.original_remap = b'[remap]\npath="res://.godot/imported/external.ctex"\n[deps]\nsource_file="external.jpg"\n[params]\ncompress/mode=2\n'
        self.runtime_remap = b'[remap]\npath="res://.godot/imported/external.ctex"\n\x00'
        self.remap.write_bytes(self.original_remap)
        self.product = self.project / ".godot/imported/external.ctex"
        self.product.write_bytes(b"original editor import product")
        self.world = prepared.scoped(self.project.parent, release.FOUR_GATES)
        self.world.parent.mkdir(parents=True)
        world_glb = glb({"asset": {"version": "2.0"}, "images": [{"uri": "albedo.jpg"}]})
        (self.world.parent / "world.glb").write_bytes(world_glb)
        albedo = b"actual raw map image"
        (self.world.parent / "albedo.jpg").write_bytes(albedo)
        self.world.write_text(json.dumps({"asset": {"glb": "world.glb"},
            "externalResources": {"albedo.jpg": hashlib.sha256(albedo).hexdigest()}}))
        self.stage = self.root / "stage"
        (self.stage / ".eloria-package").parent.mkdir(parents=True)
        (self.stage / ".eloria-package").write_text("a" * 40)
        self.runtime_rows = [("assets/world/synthetic.glb", self.scene.read_bytes()),
            ("assets/world/external.jpg.import", self.runtime_remap),
            (".godot/imported/external.ctex", b"actual PCK import product")]
        write_pck(self.stage / "app/RabbitLands.pck", self.runtime_rows)
        for name in ("world.json", "world.glb", "albedo.jpg"):
            target = prepared.scoped(self.stage, (Path(release.FOUR_GATES).parent / name).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.world.parent / name, target)
        self.old_index = self.world.parent / "vram/index.json"
        self.old_index.parent.mkdir()
        self.old_index.write_bytes(b"old unrelated source index must be restored")
        staged_vram = prepared.scoped(self.stage, (Path(release.FOUR_GATES).parent / "vram").as_posix())
        staged_vram.mkdir()
        dds = b"synthetic selected DDS bytes"
        self.dds_sha = hashlib.sha256(dds).hexdigest()
        (staged_vram / (self.dds_sha + ".dds")).write_bytes(dds)
        (staged_vram / "index.json").write_text(json.dumps({"schema": 1, "recipeVersion": 1,
            "images": {hashlib.sha256(albedo).hexdigest(): {"file": self.dds_sha + ".dds", "pool": ".", "sha256": self.dds_sha}}}))
        self.work = self.root / "prepared-work"
        self.invocations, self.budgets = [], []
        self.targets = [("scene", self.scene_name)]
        self.pilot_patch = patch.object(prepared, "pilot", return_value=self.targets)
        self.pilot_patch.start()
        self.addCleanup(self.pilot_patch.stop)

    def fake_cook(self, invocation):
        self.invocations.append(invocation)
        self.assertNotIn("--headless", invocation["argv"])
        self.assertEqual(invocation["environment"]["RABBITLANDS_PREPARED_CONTENT"], "raw")
        self.assertEqual(invocation["environment"]["RABBITLANDS_OPTIMIZATION_PROFILE"], "legacy")
        job = json.loads(Path(invocation["argv"][-1]).read_text())
        self.assertEqual(self.remap.read_bytes(), self.runtime_remap)
        self.assertEqual(self.product.read_bytes(), b"actual PCK import product")
        self.assertEqual(prepared.digest(self.old_index), prepared.digest(
            prepared.scoped(self.stage, (Path(release.FOUR_GATES).parent / "vram/index.json").as_posix())))
        output = prepared.scoped(self.project, job["output"].removeprefix("res://"))
        output.mkdir(parents=True)
        entries = []
        for spec in job["targets"]:
            data = (invocation["variant"] + ":" + spec["source"]).encode()
            sha = hashlib.sha256(data).hexdigest()
            resource = job["output"] + "/" + sha + ".scn"
            prepared.scoped(self.project, resource.removeprefix("res://")).write_bytes(data)
            entry = {"kind": spec["kind"], "source": spec["source"], "node_policy": spec["node_policy"],
                "source_digest": next(row["sha256"] for row in spec["inputs"] if row["path"] == spec["source"]),
                "texture_token": "synthetic:7:" + job["texture_quality"], "texture_skip": release.TEXTURES.index(job["texture_quality"]),
                "format_mask": 7, "resource": resource, "inputs": spec["inputs"],
                "payloads": [{"path": resource, "sha256": sha}],
                "metadata_json": json.dumps({"runtime_import_snapshot": spec["runtime_import_snapshot"]})}
            entry["entry_id"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
            entries.append(entry)
        attestation = {"policy": "actual-renderer-supported-format-subset-v1", "platform": job["platform"],
            "detected_format_mask": 7, "resource_buffer_probe": True, "software_adapter": True,
            "adapter_name": "Microsoft Basic Render Driver" if job["platform"] == "windows" else "llvmpipe",
            "adapter_type": 4 if job["platform"] == "windows" else 0,
            "rendering_method": invocation["argv"][invocation["argv"].index("--rendering-method") + 1],
            "rendering_driver": "d3d12" if job["platform"] == "windows" else "opengl3"}
        (output / "variant-catalog.json").write_text(json.dumps({"schema_version": prepared.SCHEMA,
            "policy": prepared.POLICY, "entries": entries, "release_cook": attestation}))
        invocation["log"].write_text("prepared asset cook: PASS entries=" + str(len(entries)) + "\n")

    def run_prepare(self, callback=None, **options):
        return release.prepare_generation(self.project, self.stage, platform=options.pop("platform", "windows"),
            godot=self.root / "owned-godot", run_cook=callback or self.fake_cook,
            check_budget=lambda phase, additional=0: self.budgets.append((phase, additional)), work_root=self.work, **options)

    def assert_restored(self):
        self.assertEqual(self.remap.read_bytes(), self.original_remap)
        self.assertEqual(self.product.read_bytes(), b"original editor import product")
        self.assertEqual(self.old_index.read_bytes(), b"old unrelated source index must be restored")
        self.assertFalse((self.old_index.parent / (self.dds_sha + ".dds")).exists())
        self.assertFalse((self.project / prepared.RUNTIME_IMPORT_MARKER).exists())
        self.assertFalse((self.project / ".prepared-cook-project.json").exists())

    def test_fresh_serial_all_qualities_policies_snapshot_restore_install_and_final_pck(self):
        result = self.run_prepare()
        self.assertEqual(len(self.invocations), 6)
        self.assertEqual([row["variant"] for row in self.invocations],
            [quality + "-" + policy for quality in release.TEXTURES for policy in ("retain", "lazy-source-v1")])
        self.assertEqual(result["entries"], 9)  # Fixture plan, not production's 48.
        self.assertEqual(result["source_planned_entries"], 9)
        self.assertFalse(result["catalog_reused"])
        self.assertTrue(result["selected_source_inputs_restored"])
        self.assertTrue(self.budgets)
        self.assert_restored()
        self.assertFalse((self.project / "prepared-content").exists())
        index = Path(result["catalog"])
        installed = prepared.install_generation(index, self.project, self.stage, link_payloads=True)
        self.assertEqual(installed["entries"], 9)
        entries = json.loads(index.read_text())["entries"]
        rows = self.runtime_rows + [("prepared-content/index.json", index.read_bytes())]
        for entry in entries:
            for payload in entry["payloads"]:
                installed_path = prepared.scoped(self.project, payload["path"].removeprefix("res://"))
                external_path = prepared.scoped(index.parent, payload["path"].removeprefix("res://prepared-content/"))
                self.assertEqual(installed_path.stat().st_ino, external_path.stat().st_ino)
                rows.append((payload["path"].removeprefix("res://"), installed_path.read_bytes()))
        write_pck(self.stage / "app/RabbitLands.pck", rows)
        self.assertEqual(prepared.check_export(self.project / "prepared-content/index.json", self.stage)["status"], "complete")

    def test_linux_native_userdata_mapping_is_lowercase_and_environment_is_isolated(self):
        result = self.run_prepare(platform="linux")
        self.assertEqual(result["platform"], "linux")
        for invocation in self.invocations:
            job = json.loads(Path(invocation["argv"][-1]).read_text())
            user = Path(invocation["environment"]["XDG_DATA_HOME"])
            self.assertEqual(Path(job["expected_user_directory"]), user / "godot/app_userdata/Eloria")
            self.assertTrue(user.is_relative_to(self.work))
        self.assert_restored()

    def test_mid_cook_failure_restores_only_owned_inputs_and_keeps_failure_receipt(self):
        def failing(invocation):
            self.fake_cook(invocation)
            if len(self.invocations) == 2:
                raise TimeoutError("owned fake process timed out")
        with self.assertRaises(TimeoutError):
            self.run_prepare(failing)
        self.assert_restored()
        receipt = json.loads((self.work / "prepared-release.json").read_text())
        self.assertEqual(receipt["status"], "incomplete")
        self.assertIn("TimeoutError", receipt["error"])
        self.assertTrue(receipt["selected_source_inputs_restored"])
        self.assertFalse((self.work / "generation").exists())

    def test_missing_or_forged_renderer_proof_rejects_without_promoting_catalog(self):
        def forged(invocation):
            self.fake_cook(invocation)
            job = json.loads(Path(invocation["argv"][-1]).read_text())
            path = prepared.scoped(self.project, job["output"].removeprefix("res://")) / "variant-catalog.json"
            data = json.loads(path.read_text())
            data["release_cook"]["resource_buffer_probe"] = False
            path.write_text(json.dumps(data))
        with self.assertRaisesRegex(prepared.PreparedError, "proof is missing"):
            self.run_prepare(forged)
        self.assert_restored()

    def test_source_mutation_between_jobs_is_not_hidden_by_snapshot_or_merge(self):
        def mutate(invocation):
            self.fake_cook(invocation)
            if len(self.invocations) == 6:
                self.scene.write_bytes(self.scene.read_bytes() + b"changed")
        with self.assertRaisesRegex(prepared.PreparedError, "input changed after cooking"):
            self.run_prepare(mutate)
        self.assertTrue(self.scene.read_bytes().endswith(b"changed"))
        self.assert_restored()

    def test_partial_plan_rejects(self):
        def missing(invocation):
            self.fake_cook(invocation)
            job = json.loads(Path(invocation["argv"][-1]).read_text())
            path = prepared.scoped(self.project, job["output"].removeprefix("res://")) / "variant-catalog.json"
            data = json.loads(path.read_text())
            data["entries"].pop()
            path.write_text(json.dumps(data))
        with self.assertRaisesRegex(prepared.PreparedError, "complete source-planned"):
            self.run_prepare(missing)
        self.assert_restored()

    def test_actual_capability_loss_rejects_instead_of_forging_a_format_token(self):
        def reduced(invocation):
            self.fake_cook(invocation)
            job = json.loads(Path(invocation["argv"][-1]).read_text())
            path = prepared.scoped(self.project, job["output"].removeprefix("res://")) / "variant-catalog.json"
            data = json.loads(path.read_text())
            for entry in data["entries"]:
                entry["format_mask"] = 3
            data["release_cook"]["detected_format_mask"] = 3
            path.write_text(json.dumps(data))
        with self.assertRaisesRegex(prepared.PreparedError, "actual observed BC1"):
            self.run_prepare(reduced)
        self.assert_restored()

    def test_exit_zero_catalog_with_engine_error_is_still_rejected(self):
        def errors(invocation):
            self.fake_cook(invocation)
            with invocation["log"].open("a") as stream:
                stream.write("SCRIPT ERROR: synthetic failure\n")
        with self.assertRaisesRegex(prepared.PreparedError, "cooker reported errors"):
            self.run_prepare(errors)
        self.assert_restored()

    def test_installer_rechecks_fresh_staged_source_after_cooking(self):
        result = self.run_prepare()
        staged = prepared.scoped(self.stage, release.FOUR_GATES)
        staged.write_bytes(staged.read_bytes() + b" changed after cook")
        with self.assertRaisesRegex(prepared.PreparedError, "input differs from target package"):
            prepared.install_generation(Path(result["catalog"]), self.project, self.stage, link_payloads=True)
        self.assertFalse((self.project / "prepared-content").exists())

    def test_runtime_snapshot_never_mutates_existing_cache_or_stage_hardlink_aliases(self):
        product_alias = self.root / "external-cached-import-product"
        remap_alias = self.root / "external-cached-import-remap"
        os.link(self.product, product_alias)
        os.link(self.remap, remap_alias)
        def linked(invocation):
            self.fake_cook(invocation)
            self.assertEqual(product_alias.read_bytes(), b"original editor import product")
            self.assertEqual(remap_alias.read_bytes(), self.original_remap)
            self.assertNotEqual(self.product.stat().st_ino, product_alias.stat().st_ino)
            self.assertNotEqual(self.remap.stat().st_ino, remap_alias.stat().st_ino)
        self.run_prepare(linked)
        self.assert_restored()
        self.assertEqual(product_alias.read_bytes(), b"original editor import product")
        self.assertEqual(remap_alias.read_bytes(), self.original_remap)

    def test_existing_generation_or_work_directory_never_reused(self):
        (self.project / "prepared-content").mkdir()
        with self.assertRaisesRegex(prepared.PreparedError, "leftover"):
            self.run_prepare()
        self.assertFalse(self.work.exists())

    def test_unbounded_timeout_and_unqualified_platform_reject_before_writes(self):
        for options in ({"timeout_seconds": 0}, {"timeout_seconds": 3601}, {"platform": "macos"}):
            with self.subTest(options=options), self.assertRaises(prepared.PreparedError):
                self.run_prepare(**options)
        self.assertFalse(self.work.exists())


if __name__ == "__main__":
    unittest.main()
