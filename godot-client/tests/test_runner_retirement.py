"""Owned disposable runner retirement; no SDK/compiler/engine execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import runner_retirement as retirement

COMMIT = "a" * 40


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class RunnerRetirementTests(unittest.TestCase):
    def sdk(self, base):
        runner_temp = base / "runner-temp"
        root = runner_temp / "rabbitlands-native-toolchain"
        write(root / "rustup/toolchains/pinned/lib/rustlib.rlib", b"job-owned Rust SDK")
        write(root / "cargo/registry/index/config.json", b"job-owned Cargo cache")
        system = write(base / "system-rust/lib/rustlib.rlib", b"system Rust must survive")
        sibling = write(runner_temp / "unrelated-job/keep", b"unrelated runner sibling")
        environment = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": retirement.release.REPOSITORY,
                       "GITHUB_RUN_ID": "40116956902", "GITHUB_RUN_ATTEMPT": "2",
                       "RUNNER_TEMP": str(runner_temp), "RUSTUP_HOME": str(root / "rustup"),
                       "CARGO_HOME": str(root / "cargo")}
        bootstrap = {"schema": 1, "policy": "rl-native-payload-cache-v1", "selected_commit": COMMIT,
                     "platform": "linux", "scratch_cleaned": True,
                     "prewarm": {"policy": "exact-native-git-blobs-before-assets-v1", "scratch_cleaned": True,
                                 "game_assets_materialized": False}}
        return root, runner_temp, environment, bootstrap, system, sibling

    def maps(self, base):
        source, stage = base / "source", base / "stage"
        files = {"eloria-assets/maps/staged/art.glb": b"raw staged fallback\r\n",
                 "eloria-assets/maps/pilot/world.json": b'{"prepared":"protected"}\n',
                 "eloria-assets/maps/unused/a.bin": b"unstaged original A\r\n",
                 "eloria-assets/maps/unused/b.bin": b"unstaged original B\n"}
        for relative, data in files.items():
            write(source / relative, data)
        write(stage / "eloria-assets/maps/staged/art.glb", files["eloria-assets/maps/staged/art.glb"])
        actor = write(source / "godot-client/assets/pilot.glb", b"protected actor outside maps")
        expected = {path: git_blob(data) for path, data in files.items()}
        protected = {"eloria-assets/maps/pilot/world.json": retirement.digest(source / "eloria-assets/maps/pilot/world.json"),
                     actor.relative_to(source).as_posix(): retirement.digest(actor)}
        return source, stage, expected, protected, files

    def assert_sdk_preserved(self, root, system, sibling):
        self.assertTrue((root / "rustup/toolchains/pinned/lib/rustlib.rlib").is_file())
        self.assertTrue((root / "cargo/registry/index/config.json").is_file())
        self.assertEqual(system.read_bytes(), b"system Rust must survive")
        self.assertEqual(sibling.read_bytes(), b"unrelated runner sibling")

    def test_claim_and_retire_only_job_homes_with_complete_sealed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, bootstrap, system, sibling = self.sdk(base)
            # A same-basename file inside the SDK is data, not the root marker.
            nested = write(root / "rustup/nested" / retirement.SDK_MARKER, b"nested SDK data must be receipted")
            original = {path.relative_to(root).as_posix(): {"size": path.stat().st_size, "sha256": retirement.digest(path)}
                        for path in root.rglob("*") if path.is_file()}
            receipt_path = base / "native-retirement.json"
            observations = []
            def budget(label):
                current = json.loads(receipt_path.read_text())
                observations.append((label, current["status"], (root / "rustup").exists(), (root / "cargo").exists()))
            with mock.patch.dict(os.environ, env):
                owner = retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                self.assertEqual(retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux"), owner)
                marker = (root / retirement.SDK_MARKER).read_bytes()
                actual = retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, budget, receipt_path)
            self.assertEqual(actual["files"], original)
            self.assertIn(nested.relative_to(root).as_posix(), actual["files"])
            self.assertEqual(actual["retired_bytes"], sum(row["size"] for row in original.values()))
            self.assertEqual(actual["status"], "retired_after_verified_native_bootstrap")
            self.assertEqual(json.loads(receipt_path.read_text()), actual)
            self.assertEqual((root / retirement.SDK_MARKER).read_bytes(), marker)
            self.assertEqual({path.name for path in root.iterdir()}, {retirement.SDK_MARKER})
            self.assertEqual(system.read_bytes(), b"system Rust must survive")
            self.assertEqual(sibling.read_bytes(), b"unrelated runner sibling")
            self.assertEqual([row[1:] for row in observations], [("verified_before_retirement", True, True),
                                                               ("retired_after_verified_native_bootstrap", False, False)])

    def test_sdk_environment_root_commit_and_platform_mismatches_fail_before_claim(self):
        cases = {"GITHUB_ACTIONS": "false", "GITHUB_REPOSITORY": "unrelated/repository",
                 "RUNNER_TEMP": "outside", "RUSTUP_HOME": "outside", "CARGO_HOME": "outside"}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, _bootstrap, system, sibling = self.sdk(base)
            for key, value in cases.items():
                with self.subTest(key=key), mock.patch.dict(os.environ, {**env, key: value}), self.assertRaises(ValueError):
                    retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                self.assertFalse((root / retirement.SDK_MARKER).exists())
            with mock.patch.dict(os.environ, env):
                for commit, platform in (("short", "linux"), (COMMIT, "macos")):
                    with self.subTest(commit=commit, platform=platform), self.assertRaises(ValueError):
                        retirement.claim_native_sdk(root, runner_temp, commit, platform)
                with self.assertRaises(ValueError):
                    retirement.claim_native_sdk(root.parent, runner_temp, COMMIT, "linux")
            self.assert_sdk_preserved(root, system, sibling)

    def test_changed_owner_marker_unknown_root_input_and_incomplete_bootstrap_do_not_delete(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, bootstrap, system, sibling = self.sdk(base)
            with mock.patch.dict(os.environ, env):
                owner = retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                marker = root / retirement.SDK_MARKER
                marker.write_text(json.dumps({**owner, "run_attempt": "another-run"}))
                with self.assertRaises(ValueError):
                    retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, lambda *_: None, base / "wrong-owner.json")
                marker.write_text(json.dumps(owner))
                extra = write(root / "not-installed-by-this-job", b"preserve unknown input")
                with self.assertRaises(ValueError):
                    retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, lambda *_: None, base / "extra.json")
                extra.unlink()
                for key in ("scratch_cleaned", "selected_commit", "platform", "prewarm"):
                    changed = json.loads(json.dumps(bootstrap))
                    changed[key] = {"scratch_cleaned": False} if key == "prewarm" else "wrong"
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", changed, lambda *_: None, base / (key + ".json"))
            self.assert_sdk_preserved(root, system, sibling)
            self.assertFalse((base / "wrong-owner.json").exists())

    def test_sdk_budget_failure_retains_homes_and_predeletion_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, bootstrap, system, sibling = self.sdk(base)
            receipt = base / "refused.json"
            def budget(_label):
                raise ValueError("fixture SDK disk refusal")
            with mock.patch.dict(os.environ, env):
                retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                with self.assertRaisesRegex(ValueError, "disk refusal"):
                    retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, budget, receipt)
            self.assertEqual(json.loads(receipt.read_text())["status"], "verified_before_retirement")
            self.assert_sdk_preserved(root, system, sibling)

    def test_sdk_receipt_must_be_fresh_and_outside_retired_homes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, bootstrap, system, sibling = self.sdk(base)
            existing = write(base / "old-receipt.json", b"preserve old receipt")
            with mock.patch.dict(os.environ, env):
                retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                for receipt in (existing, root / "cargo/new-receipt.json"):
                    with self.subTest(path=receipt), self.assertRaises(ValueError):
                        retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, lambda *_: None, receipt)
            self.assertEqual(existing.read_bytes(), b"preserve old receipt")
            self.assert_sdk_preserved(root, system, sibling)

    def test_map_retirement_preserves_staged_fallback_and_complete_prepared_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, stage, expected, protected, original = self.maps(base)
            receipt_path = base / "maps-retired.json"
            observed = []
            def budget(label):
                receipt = json.loads(receipt_path.read_text())
                observed.append((label, receipt["status"], (source / "eloria-assets/maps/unused/a.bin").exists()))
            actual = retirement.retire_unstaged_maps(source, stage, expected, protected, budget, receipt_path)
            retired = {"eloria-assets/maps/unused/a.bin", "eloria-assets/maps/unused/b.bin"}
            self.assertEqual(set(actual["files"]), retired)
            for relative in retired:
                self.assertEqual(actual["files"][relative], {"size": len(original[relative]),
                                 "git_blob": git_blob(original[relative]), "sha256": hashlib.sha256(original[relative]).hexdigest()})
                self.assertFalse((source / relative).exists())
            for relative in set(original) - retired:
                self.assertEqual((source / relative).read_bytes(), original[relative])
            self.assertEqual((stage / "eloria-assets/maps/staged/art.glb").read_bytes(), original["eloria-assets/maps/staged/art.glb"])
            for relative, digest in protected.items():
                self.assertEqual(retirement.digest(source / relative), digest)
            self.assertEqual(actual["retired_bytes"], sum(len(original[path]) for path in retired))
            self.assertEqual(json.loads(receipt_path.read_text()), actual)
            self.assertEqual([row[1:] for row in observed], [("verified_before_retirement", True),
                                                           ("retired_after_shipping_and_prepared_closure_proof", False)])

    def test_map_unknown_changed_protected_missing_and_wrong_roots_fail_before_any_delete(self):
        for mutation in ("unknown", "changed", "wrong_blob", "changed_protected", "missing_protected", "escaped_protected",
                         "missing_stage", "stage_file", "same_roots", "nested_stage", "missing_maps", "receipt_in_maps", "existing_receipt"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                source, stage, expected, protected, _original = self.maps(base)
                receipt = base / "must-not-complete.json"
                if mutation == "unknown": write(source / "eloria-assets/maps/unknown/new.bin", b"not selected Git input")
                elif mutation == "changed": (source / "eloria-assets/maps/unused/b.bin").write_bytes(b"changed before plan")
                elif mutation == "wrong_blob": expected["eloria-assets/maps/unused/b.bin"] = "0" * 40
                elif mutation == "changed_protected": (source / "eloria-assets/maps/pilot/world.json").write_bytes(b"changed protected source")
                elif mutation == "missing_protected": (source / "godot-client/assets/pilot.glb").unlink()
                elif mutation == "escaped_protected":
                    external = write(base / "outside.bin", b"outside scope")
                    protected["../outside.bin"] = retirement.digest(external)
                elif mutation == "missing_stage": stage = base / "absent-stage"
                elif mutation == "stage_file": stage = write(base / "not-a-stage", b"file")
                elif mutation == "same_roots": stage = source
                elif mutation == "nested_stage": stage = source / "nested-stage"
                elif mutation == "missing_maps": source = base / "missing-source"
                elif mutation == "receipt_in_maps": receipt = source / "eloria-assets/maps/new-receipt.json"
                elif mutation == "existing_receipt": write(receipt, b"old evidence")
                with self.assertRaises((ValueError, FileNotFoundError)):
                    retirement.retire_unstaged_maps(source, stage, expected, protected, lambda *_: None, receipt)
                real_source = base / "source"
                self.assertTrue((real_source / "eloria-assets/maps/unused/a.bin").exists())
                self.assertTrue((real_source / "eloria-assets/maps/unused/b.bin").exists())

    def test_map_budget_failure_keeps_all_verified_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, stage, expected, protected, _original = self.maps(base)
            receipt = base / "map-refusal.json"
            def budget(_label):
                raise ValueError("fixture map disk refusal")
            with self.assertRaisesRegex(ValueError, "disk refusal"):
                retirement.retire_unstaged_maps(source, stage, expected, protected, budget, receipt)
            self.assertEqual(json.loads(receipt.read_text())["status"], "verified_before_retirement")
            self.assertTrue((source / "eloria-assets/maps/unused/a.bin").exists())
            self.assertTrue((source / "eloria-assets/maps/unused/b.bin").exists())

    def test_links_in_sdk_map_source_stage_or_receipt_fail_without_external_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, runner_temp, env, bootstrap, system, sibling = self.sdk(base)
            source, stage, expected, protected, _original = self.maps(base)
            external = write(base / "external/keep", b"must never delete")
            link = base / "probe-link"
            try:
                link.symlink_to(external)
                link.unlink()
            except OSError:
                self.skipTest("symlink privilege unavailable")
            with mock.patch.dict(os.environ, env):
                retirement.claim_native_sdk(root, runner_temp, COMMIT, "linux")
                sdk_link = root / "rustup/linked-file"
                sdk_link.symlink_to(external)
                with self.assertRaises(ValueError):
                    retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, lambda *_: None, base / "sdk-link.json")
                sdk_link.unlink()
                receipt_link = base / "dangling-receipt"
                receipt_link.symlink_to(base / "external/new-receipt")
                with self.assertRaises(ValueError):
                    retirement.retire_native_sdk(root, runner_temp, COMMIT, "linux", bootstrap, lambda *_: None, receipt_link)
                self.assert_sdk_preserved(root, system, sibling)
                receipt_link.unlink()
            for parent in (source / "eloria-assets/maps", stage):
                map_link = parent / "linked-file"
                map_link.symlink_to(external)
                with self.assertRaises(ValueError):
                    retirement.retire_unstaged_maps(source, stage, expected, protected, lambda *_: None, base / "map-link.json")
                map_link.unlink()
            receipt_link = base / "dangling-map-receipt"
            receipt_link.symlink_to(base / "external/new-map-receipt")
            with self.assertRaises(ValueError):
                retirement.retire_unstaged_maps(source, stage, expected, protected, lambda *_: None, receipt_link)
            self.assertEqual(external.read_bytes(), b"must never delete")
            self.assertFalse((base / "external/new-receipt").exists())
            self.assertFalse((base / "external/new-map-receipt").exists())
            self.assertTrue((source / "eloria-assets/maps/unused/a.bin").exists())


if __name__ == "__main__":
    unittest.main()
