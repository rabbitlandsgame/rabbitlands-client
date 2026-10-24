"""Optional Rust payload provenance and staging; never builds or starts Godot."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = PROJECT.parent
sys.path.insert(0, str(PROJECT / "tools"))
import client_runtime_package as runtime_package


class ClientRuntimePackageTests(unittest.TestCase):
    def fixture(self, root: Path):
        repository = root / "repository"
        native = repository / runtime_package.NATIVE_PATH
        source = native / "core/src/lib.rs"
        source.parent.mkdir(parents=True)
        source.write_text("pub const ABI: u32 = 1;\n", encoding="utf-8")
        (native / "CMakeLists.txt").write_text("project(runtime)\n", encoding="utf-8")
        for relative in runtime_package.EXTERNAL_SOURCE_INPUTS:
            shared = repository / relative
            shared.parent.mkdir(parents=True, exist_ok=True)
            shared.write_text("// fixture shared native arithmetic\n", encoding="utf-8")
        payload = root / "payload"
        payload.mkdir()
        (payload / "client_runtime.dll").write_bytes(b"fixture-native-library")
        (payload / "client_runtime.gdextension").write_text("fixture descriptor\n", encoding="utf-8")
        manifest = {
            "schema": 1, "abi": 1, "engine_major": 4, "engine_minor": 7,
            "platform": "windows", "architecture": "x86_64", "library": "client_runtime.dll",
            "source_digest": runtime_package.source_digest(repository),
            "library_sha256": runtime_package.sha256(payload / "client_runtime.dll"),
            "descriptor_sha256": runtime_package.sha256(payload / "client_runtime.gdextension"),
        }
        self.write_manifest(payload, manifest)
        return repository, payload, manifest

    @staticmethod
    def write_manifest(directory, manifest):
        (directory / "runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_actual_built_payload_stages_its_exact_verified_inventory(self):
        payload = PROJECT / "bin/client_runtime"
        if not (payload / "runtime-manifest.json").is_file():
            self.skipTest("optional actual native build is absent")
        manifest = json.loads((payload / "runtime-manifest.json").read_text(encoding="utf-8"))
        platform = manifest["platform"]
        validated = runtime_package.validate_payload(payload, REPOSITORY, platform)
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "app"
            staged = runtime_package.stage_payload(payload, REPOSITORY, app, platform)
            self.assertEqual(staged, validated)
            destination = app / "bin/client_runtime"
            names = {runtime_package.LIBRARIES[platform], "client_runtime.gdextension", "runtime-manifest.json"}
            self.assertEqual({p.name for p in destination.iterdir()}, names)
            for name in names:
                self.assertEqual(runtime_package.sha256(destination / name), runtime_package.sha256(payload / name))

    def test_source_change_rejects_previously_built_payload_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, payload, _ = self.fixture(root)
            (repository / runtime_package.NATIVE_PATH / "core/src/lib.rs").write_text("changed source", encoding="utf-8")
            app = root / "app"
            with self.assertRaisesRegex(ValueError, "different source"):
                runtime_package.stage_payload(payload, repository, app, "windows")
            self.assertFalse(app.exists())

    def test_source_digest_covers_adapter_core_descriptor_and_toolchain_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, _, _ = self.fixture(root)
            native = repository / runtime_package.NATIVE_PATH
            for relative in ["src/client_runtime.cpp", "src/client_core.h", "core/Cargo.toml",
                             "core/Cargo.lock", "core/rust-toolchain.toml", "client_runtime.gdextension.in", "build_profile.json"]:
                with self.subTest(input=relative):
                    before = runtime_package.source_digest(repository)
                    path = native / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("another source input", encoding="utf-8")
                    self.assertNotEqual(runtime_package.source_digest(repository), before)

    def test_exact_external_arithmetic_bytes_are_bound_and_required(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, _, _ = self.fixture(Path(directory))
            for relative in runtime_package.EXTERNAL_SOURCE_INPUTS:
                before = runtime_package.source_digest(repository)
                path = repository / relative
                path.write_text("// changed external arithmetic\n", encoding="utf-8")
                self.assertNotEqual(runtime_package.source_digest(repository), before)
            path.unlink()
            with self.assertRaisesRegex(ValueError, "external native source input"):
                runtime_package.source_digest(repository)

    def test_build_outputs_are_not_mistaken_for_source_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            repository, _, _ = self.fixture(Path(directory))
            before = runtime_package.source_digest(repository)
            for relative in ["core/target/release/generated.rs", "build/generated/client.h", ".deps/dependency.cpp"]:
                path = repository / runtime_package.NATIVE_PATH / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ignored build output", encoding="utf-8")
            self.assertEqual(runtime_package.source_digest(repository), before)

    def test_api_platform_architecture_and_library_path_mismatches_reject(self):
        for field, bad in [("abi", 99), ("engine_minor", 99), ("platform", "linux"),
                           ("architecture", "arm64"), ("library", "../elsewhere.dll")]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                repository, payload, manifest = self.fixture(Path(directory))
                manifest[field] = bad
                self.write_manifest(payload, manifest)
                with self.assertRaises(ValueError):
                    runtime_package.validate_payload(payload, repository, "windows")

    def test_missing_or_mutated_library_and_descriptor_fail_closed(self):
        for name in ["client_runtime.dll", "client_runtime.gdextension"]:
            for mutation in ["missing", "changed"]:
                with self.subTest(file=name, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    repository, payload, _ = self.fixture(Path(directory))
                    path = payload / name
                    if mutation == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(b"changed bytes")
                    with self.assertRaisesRegex(ValueError, "checksum"):
                        runtime_package.validate_payload(payload, repository, "windows")

    def test_staging_revalidates_copied_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository, payload, _ = self.fixture(root)
            original = runtime_package.shutil.copy2

            def corrupt_copy(source, destination):
                result = original(source, destination)
                if Path(destination).name == "client_runtime.dll":
                    Path(destination).write_bytes(b"corrupted during staging")
                return result

            with mock.patch.object(runtime_package.shutil, "copy2", side_effect=corrupt_copy):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    runtime_package.stage_payload(payload, repository, root / "app", "windows")

    def test_launchers_offer_explicit_legacy_and_comparison_profiles(self):
        for platform, extension in [("windows", "bat"), ("linux", "sh")]:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                runtime_package.write_launchers(stage, platform)
                for label, mode in [("Rust rider pilot", "rust"), ("Rust comparison", "compare"), ("legacy runtime", "legacy")]:
                    text = (stage / f"RabbitLands ({label}).{extension}").read_text(encoding="utf-8")
                    self.assertIn("RABBITLANDS_CLIENT_RUNTIME=" + mode, text)
                    self.assertIn("%*" if platform == "windows" else '"$@"', text)


    def test_spell_comparator_source_inputs_and_explicit_pilot_launchers(self):
        for relative in ("godot-client/native/native_crowd/src/native_spell_flight_geometry.cpp",
                         "godot-client/native/native_crowd/src/native_spell_flight_geometry.h"):
            self.assertIn(Path(relative), runtime_package.EXTERNAL_SOURCE_INPUTS)
        # The generic exact-external-bytes test above mutates every listed input,
        # including both unchanged C++ comparator implementation and header.
        for platform, extension in (("windows", "bat"), ("linux", "sh")):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                runtime_package.write_launchers(stage, platform)
                pilot = (stage / f"RabbitLands (Rust heat bolt pilot).{extension}").read_text(encoding="utf-8")
                self.assertIn("RABBITLANDS_CLIENT_RUNTIME=rust", pilot)
                self.assertIn("RABBITLANDS_RUST_EFFECTS=heat_bolt", pilot)
                self.assertIn("ELORIA_NATIVE_PRESENTATION=0", pilot)
                for label in ("Rust rider pilot", "Rust comparison", "legacy runtime"):
                    text = (stage / f"RabbitLands ({label}).{extension}").read_text(encoding="utf-8")
                    self.assertIn("RABBITLANDS_RUST_EFFECTS=", text)
                    self.assertNotIn("RABBITLANDS_RUST_EFFECTS=heat_bolt", text)


if __name__ == "__main__":
    unittest.main()
