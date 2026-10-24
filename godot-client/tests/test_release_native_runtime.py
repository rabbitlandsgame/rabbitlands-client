"""Fake-only desktop native release checks; no compiler, network or engine."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import build_client_runtime as build
import release_native_runtime as release
import client_runtime_package as package

COMMIT = "a" * 40


def blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def toolchain(platform="windows"):
    return {"policy": build.BUILD_POLICY, "rustc": "rustc 1.99.1 (fixture 2026-01-01)",
            "rust_host": build.HOST_TARGETS[platform], "cargo": "cargo 1.99.1 (fixture)",
            "cmake": "cmake version 4.1.2", "ninja": "1.13.1", "compiler": "MSVC fixture x64" if platform == "windows" else "g++ fixture",
            "compiler_path": "cl.exe" if platform == "windows" else "/usr/bin/g++", "generator": "Ninja"}


class NativeReleaseTests(unittest.TestCase):
    def fixture(self, root):
        repository = root / "selected"
        files = {package.NATIVE_PATH / "src/client_runtime.cpp": b"// adapter\n",
                 package.NATIVE_PATH / "core/src/lib.rs": b"pub const ABI: u32 = 1;\n",
                 package.NATIVE_PATH / "CMakeLists.txt": b"project(runtime)\n",
                 package.NATIVE_PATH / "client_runtime.gdextension.in": b"[configuration]\nentry_symbol=\"fixture\"\n"}
        files.update({path: b"// external math\n" for path in package.EXTERNAL_SOURCE_INPUTS})
        files.update({path: b"# selected helper\n" for path in release.BUILD_TOOLS})
        for relative, data in files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        tree = "\0".join("100644 blob " + blob(data) + "\t" + path.as_posix()
                         for path, data in files.items()) + "\0"
        def git_output(command, *args, **kwargs):
            if "ls-tree" in command:
                return tree
            if "rev-parse" in command:
                return COMMIT
            self.fail("unexpected external command: " + str(command))
        return repository, git_output

    def payload(self, directory, repository, platform, actual):
        directory.mkdir(parents=True, exist_ok=True)
        if platform == "windows":
            data = bytearray(128)
            data[:2] = b"MZ"
            struct.pack_into("<I", data, 60, 64)
            data[64:68] = b"PE\0\0"
            struct.pack_into("<H", data, 68, 0x8664)
            struct.pack_into("<H", data, 88, 0x20B)
        else:
            data = bytearray(64)
            data[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<HH", data, 16, 3, 62)
        library = directory / package.LIBRARIES[platform]
        library.write_bytes(data)
        descriptor = directory / "client_runtime.gdextension"
        descriptor.write_bytes((repository / package.NATIVE_PATH / "client_runtime.gdextension.in").read_bytes())
        (directory / ".gdignore").write_bytes(b"")
        manifest = {"schema": 1, "abi": package.ABI, "engine_major": 4, "engine_minor": 7,
                    "platform": platform, "architecture": "x86_64", "library": library.name,
                    "rustc": actual["rustc"], "cargo": actual["cargo"], "build": actual,
                    "godot_cpp_revision": build.GODOT_CPP_REVISION,
                    "source_digest": package.source_digest(repository), "library_sha256": package.sha256(library),
                    "descriptor_sha256": package.sha256(descriptor)}
        (directory / "runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return manifest

    def test_key_needs_only_selected_git_tree_not_materialized_inputs_or_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository, git = self.fixture(Path(temporary))
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())):
                first = release.release_cache_key(repository, COMMIT, "windows")
                # Tool-only checkout may lack every runtime/asset source file.
                import shutil
                shutil.rmtree(repository / package.NATIVE_PATH)
                second = release.release_cache_key(repository, COMMIT, "windows")
            self.assertEqual(first, second)
            self.assertTrue(first["requires_materialized_verification"])

    def test_materialized_source_checks_actual_blob_bytes_and_missing_or_extra_inputs(self):
        for mutation in ("modified", "missing", "extra"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                repository, git = self.fixture(Path(temporary))
                path = repository / package.NATIVE_PATH / "src/client_runtime.cpp"
                if mutation == "modified":
                    path.write_bytes(b"changed")
                elif mutation == "missing":
                    path.unlink()
                else:
                    (path.parent / "untracked.cpp").write_bytes(b"new")
                with mock.patch.object(build, "output", side_effect=git), self.assertRaisesRegex(ValueError, "input"):
                    release.source_identity(repository, COMMIT)

    def test_unrelated_generated_import_does_not_invalidate_selected_native_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository, git = self.fixture(Path(temporary))
            (repository / "godot-client/generated.import").write_bytes(b"unrelated generated data")
            with mock.patch.object(build, "output", side_effect=git):
                verified = release.source_identity(repository, COMMIT)
            self.assertEqual(verified["selected_commit"], COMMIT)

    def test_wrong_head_and_uncommitted_external_or_helper_bytes_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository, git = self.fixture(Path(temporary))
            with mock.patch.object(build, "output", return_value="b" * 40), self.assertRaisesRegex(ValueError, "HEAD"):
                release.source_identity(repository, COMMIT)
            for relative in (package.EXTERNAL_SOURCE_INPUTS[0], release.BUILD_TOOLS[0]):
                path = repository / relative
                original = path.read_bytes()
                path.write_bytes(b"modified selected input")
                with mock.patch.object(build, "output", side_effect=git), self.assertRaisesRegex(ValueError, "Git blob"):
                    release.source_identity(repository, COMMIT)
                path.write_bytes(original)

    def test_key_changes_with_platform_toolchain_pin_source_and_helper_blobs(self):
        source = {"selected_commit": COMMIT, "input_blob_digest": "1", "input_count": 9, "build_tools": {"helper": "2"}}
        first = release.cache_identity(source, "windows", toolchain())
        same = dict(source, selected_commit="b" * 40)
        self.assertEqual(release.cache_key(first), release.cache_key(release.cache_identity(same, "windows", toolchain())))
        variants = [release.cache_identity(source, "linux", toolchain("linux")),
                    release.cache_identity(dict(source, input_blob_digest="changed"), "windows", toolchain()),
                    release.cache_identity(dict(source, build_tools={"helper": "changed"}), "windows", toolchain()),
                    release.cache_identity(source, "windows", dict(toolchain(), compiler="new compiler"))]
        self.assertEqual(len({release.cache_key(first), *(release.cache_key(value) for value in variants)}), 5)

    def test_prepare_builds_then_reuses_only_verified_payload_and_cleans_owned_scratch(self):
        for platform in ("windows", "linux"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository, git = self.fixture(root)
                actual = toolchain(platform)
                budget = []
                def fake_build(args, target, env, identity, checkpoint=None):
                    self.assertEqual(target, platform)
                    self.assertTrue(args.build_root.is_relative_to(root / "work"))
                    self.assertTrue(args.dependency_dir.is_relative_to(root / "work"))
                    (args.build_root / "bounded-target").mkdir(parents=True)
                    return self.payload(args.out, repository, target, identity)
                with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, actual)), mock.patch.object(build, "build_payload", side_effect=fake_build) as called:
                    first = release.prepare_runtime(repository, COMMIT, platform, root / "cache", root / "out1", root / "work", lambda label, upcoming_bytes=0: budget.append((label, upcoming_bytes)))
                    second = release.prepare_runtime(repository, COMMIT, platform, root / "cache", root / "out2", root / "work", lambda *args, **kwargs: None)
                self.assertEqual(called.call_count, 1)
                self.assertFalse(first["cache_hit"])
                self.assertTrue(second["cache_hit"])
                self.assertEqual(second["workspace_budget"]["status"], "not_created")
                self.assertIsNone(second["workspace_budget"]["observed_peak_workspace_bytes"])
                self.assertTrue(first["scratch_cleaned"])
                self.assertTrue(first["workspace_budget"]["measured_before_cleanup"])
                self.assertGreater(first["workspace_budget"]["observed_peak_workspace_bytes"], 0)
                self.assertEqual(list((root / "work").iterdir()), [])
                self.assertEqual(first["verification"]["files"], second["verification"]["files"])
                self.assertTrue(any(size == release.BUILD_RESERVE_BYTES for _, size in budget))

    def test_corrupt_restored_cache_fails_without_rebuild_or_output(self):
        for mutation in ("library", "receipt", "extra"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository, git = self.fixture(root)
                with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload", side_effect=lambda args, target, env, actual, **kwargs: self.payload(args.out, repository, target, actual)):
                    first = release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out1", root / "work", lambda *a, **k: None)
                entry = root / "cache" / first["cache_key"]
                if mutation == "library":
                    (entry / "payload/client_runtime.dll").write_bytes(b"corrupt")
                elif mutation == "receipt":
                    (entry / "cache-record.json").write_text("{}")
                else:
                    (entry / "unknown").write_bytes(b"unknown")
                with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload") as build_again, self.assertRaises(ValueError):
                    release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out2", root / "work", lambda *a, **k: None)
                build_again.assert_not_called()
                self.assertFalse((root / "out2").exists())

    def test_failed_build_cleans_only_owned_scratch_and_never_publishes_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, git = self.fixture(root)
            sibling = root / "work/unrelated"
            sibling.mkdir(parents=True)
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload", side_effect=RuntimeError("fixture compile failed")), self.assertRaisesRegex(RuntimeError, "compile failed"):
                release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out", root / "work", lambda *a, **k: None)
            self.assertEqual(list((root / "work").iterdir()), [sibling])
            self.assertEqual(list((root / "cache").iterdir()), [])
            with self.assertRaisesRegex(ValueError, "unowned"):
                release.remove_owned_work(sibling, root / "work")

    def test_budget_refusal_does_not_start_build_or_create_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, git = self.fixture(root)
            def exhausted(label, upcoming_bytes=0):
                raise ValueError("fixture disk budget exhausted")
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload") as called, self.assertRaisesRegex(ValueError, "disk budget"):
                release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out", root / "work", exhausted)
            called.assert_not_called()
            self.assertFalse((root / "out").exists())
            self.assertFalse((root / "work").exists())

    def test_observed_workspace_over_reservation_fails_and_still_cleans(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, git = self.fixture(root)
            checkpoints = []
            def fake_build(args, target, env, actual, checkpoint=None):
                checkpoint("fixture compiler running")
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload", side_effect=fake_build), mock.patch.object(release, "workspace_bytes", return_value=release.BUILD_RESERVE_BYTES + 1), self.assertRaisesRegex(ValueError, "3 GiB"):
                release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out", root / "work", lambda label, **kwargs: checkpoints.append(label))
            self.assertIn("fixture compiler running", checkpoints)
            self.assertIn("native peak before scratch cleanup", checkpoints)
            self.assertEqual(list((root / "work").iterdir()), [])
            self.assertFalse((root / "out").exists())

    def test_copied_output_is_reverified_and_cannot_be_accepted_after_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, git = self.fixture(root)
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(build, "build_payload", side_effect=lambda args, target, env, actual, **kwargs: self.payload(args.out, repository, target, actual)):
                release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out1", root / "work", lambda *a, **k: None)
            original = release.shutil.copytree
            def corrupt_copy(source, destination, *args, **kwargs):
                result = original(source, destination, *args, **kwargs)
                if Path(destination) == root / "out2":
                    (Path(destination) / "client_runtime.dll").write_bytes(b"changed during output materialization")
                return result
            with mock.patch.object(build, "output", side_effect=git), mock.patch.object(release, "tool_context", return_value=({}, toolchain())), mock.patch.object(release.shutil, "copytree", side_effect=corrupt_copy), self.assertRaisesRegex(ValueError, "checksum"):
                release.prepare_runtime(repository, COMMIT, "windows", root / "cache", root / "out2", root / "work", lambda *a, **k: None)

    def test_overlapping_cleanup_roots_reject_before_external_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, _ = self.fixture(root)
            with mock.patch.object(release, "source_identity") as queried, self.assertRaisesRegex(ValueError, "disjoint"):
                release.prepare_runtime(repository, COMMIT, "windows", root / "work/cache", root / "out", root / "work", lambda *a, **k: None)
            queried.assert_not_called()

    def test_cleanup_retry_is_limited_to_owned_read_only_git_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            owned = parent / "rl-native-fixture"
            owned.mkdir()
            (owned / ".rl-native-work.json").write_text(json.dumps({"path": str(owned.resolve())}))
            packed = owned / "pack.idx"
            packed.write_bytes(b"owned git pack")
            retried = mock.Mock()
            def fake_rmtree(directory, onexc=None):
                onexc(retried, packed, PermissionError("fixture readonly"))
                with self.assertRaisesRegex(ValueError, "escaped"):
                    onexc(retried, parent / "unrelated", PermissionError("outside"))
            with mock.patch.object(release.shutil, "rmtree", side_effect=fake_rmtree):
                release.remove_owned_work(owned, parent)
            retried.assert_called_once_with(packed)

    def test_manifest_provenance_descriptor_and_binary_architecture_are_verified(self):
        for mutation in ("revision", "rust", "compiler", "descriptor", "architecture"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository, _ = self.fixture(root)
                actual = toolchain()
                payload = root / "payload"
                manifest = self.payload(payload, repository, "windows", actual)
                identity = release.cache_identity({}, "windows", actual)
                if mutation in {"revision", "rust", "compiler"}:
                    manifest[{"revision": "godot_cpp_revision", "rust": "rustc", "compiler": "build"}[mutation]] = "bad"
                elif mutation == "descriptor":
                    (payload / "client_runtime.gdextension").write_bytes(b"changed")
                    manifest["descriptor_sha256"] = package.sha256(payload / "client_runtime.gdextension")
                else:
                    binary = bytearray((payload / "client_runtime.dll").read_bytes())
                    struct.pack_into("<H", binary, 68, 0xAA64)
                    (payload / "client_runtime.dll").write_bytes(binary)
                    manifest["library_sha256"] = package.sha256(payload / "client_runtime.dll")
                (payload / "runtime-manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    release.verify_release_payload(payload, repository, "windows", identity)


class NativeBuilderTests(unittest.TestCase):
    def test_subprocess_checks_budget_while_running_and_after_completion(self):
        child = mock.Mock()
        child.wait.side_effect = [build.subprocess.TimeoutExpired("fixture", 5), 0]
        checkpoints = []
        with mock.patch.object(build.subprocess, "Popen", return_value=child), mock.patch.object(build, "stop_owned_child") as stopped:
            build.run(["fixture", "--compile"], checkpoint=checkpoints.append, label="C++")
        self.assertEqual(checkpoints, ["C++ before start", "C++ running", "C++ completed"])
        self.assertEqual(child.wait.call_args_list, [mock.call(timeout=5), mock.call(timeout=5)])
        stopped.assert_not_called()

    def test_budget_failure_stops_exact_owned_child_and_propagates(self):
        child = mock.Mock()
        child.wait.side_effect = build.subprocess.TimeoutExpired("fixture", 5)
        def budget(label):
            if label.endswith("running"):
                raise ValueError("fixture budget exhausted during compilation")
        with mock.patch.object(build.subprocess, "Popen", return_value=child), mock.patch.object(build, "stop_owned_child") as stopped, self.assertRaisesRegex(ValueError, "during compilation"):
            build.run(["fixture"], checkpoint=budget)
        stopped.assert_called_once_with(child)

    def test_nonzero_child_exit_cannot_be_accepted_by_budget_wrapper(self):
        child = mock.Mock()
        child.wait.return_value = 17
        with mock.patch.object(build.subprocess, "Popen", return_value=child), mock.patch.object(build, "stop_owned_child"), self.assertRaises(build.subprocess.CalledProcessError) as error:
            build.run(["fixture"], checkpoint=lambda label: None)
        self.assertEqual(error.exception.returncode, 17)

    def test_windows_stop_uses_only_owned_pid_tree_and_reaps(self):
        child = mock.Mock(pid=123456)
        child.poll.side_effect = [None, 0]
        with mock.patch.object(build.subprocess, "run") as terminate:
            build.stop_owned_child(child, system="nt")
        self.assertEqual(terminate.call_args.args[0], ["taskkill", "/PID", "123456", "/T", "/F"])
        child.wait.assert_called_once_with(timeout=15)

    def test_intel_macos_local_builder_is_preserved_but_not_release_target(self):
        with mock.patch.object(build.platform, "system", return_value="Darwin"), mock.patch.object(build.platform, "machine", return_value="x86_64"):
            self.assertEqual(build.host_platform(), "macos")
        with self.assertRaisesRegex(ValueError, "Windows and Linux only"):
            release.tool_context("macos")

    def test_environment_is_child_only_and_removes_unbound_build_overrides(self):
        original = {"PATH": "fixture", "RUSTFLAGS": "-C danger", "CARGO_TARGET_X_LINKER": "bad", "CMAKE_GENERATOR": "old", "CXX": "wrong", "KEEP": "yes",
                    "CARGO_BUILD_RUSTC": "unbound", "CARGO_BUILD_RUSTFLAGS": "unbound", "CARGO_PROFILE_RELEASE_PANIC": "abort"}
        result = build.build_environment("linux", original)
        self.assertEqual(result, {"PATH": "fixture", "KEEP": "yes"})
        self.assertIn("RUSTFLAGS", original)

    def test_windows_uses_detected_vs_environment_not_hard_coded_generator_year(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "Visual Studio Future"
            script = install / "Common7/Tools/VsDevCmd.bat"
            script.parent.mkdir(parents=True)
            script.write_text("fixture")
            with mock.patch.object(build.shutil, "which", return_value="vswhere.exe"), mock.patch.object(build, "output", side_effect=[str(install), "Path=MSVC-new\nVSCMD_ARG_TGT_ARCH=x64\nKEEP=yes"]) as called:
                result = build.windows_environment({"PATH": "old"})
            self.assertEqual(result["PATH"], "MSVC-new")
            self.assertNotIn("Path", result)
            self.assertIn("-arch=x64", called.call_args_list[1].args[0])
            self.assertIsInstance(called.call_args_list[1].args[0], str)
            self.assertNotIn('\\"', called.call_args_list[1].args[0])
            self.assertNotIn("2022", str(called.call_args_list))

    @unittest.skipUnless(os.name == "nt", "actual cmd.exe grammar is a Windows control")
    def test_actual_windows_batch_path_with_spaces_and_parentheses(self):
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "Visual Studio (Future Edition)"
            script = install / "Common7/Tools/VsDevCmd.bat"
            script.parent.mkdir(parents=True)
            script.write_bytes(b"@echo off\r\nset VSCMD_ARG_TGT_ARCH=x64\r\nset RL_FIXTURE_VS=space-parentheses\r\n")
            original = build.output
            def vswhere_or_real(command, *args, **kwargs):
                if isinstance(command, list) and "-property" in command:
                    return str(install)
                return original(command, *args, **kwargs)
            with mock.patch.object(build.shutil, "which", return_value="vswhere.exe"), mock.patch.object(build, "output", side_effect=vswhere_or_real):
                actual = build.windows_environment(dict(os.environ))
            self.assertEqual(actual["RL_FIXTURE_VS"], "space-parentheses")
            self.assertEqual(actual["VSCMD_ARG_TGT_ARCH"], "x64")

    def test_wrong_rust_version_target_or_dirty_godot_cpp_fails_closed(self):
        for rust in ("rustc 1.98.0 (old)\nhost: x86_64-unknown-linux-gnu", "rustc 1.99.1 (new)\nhost: aarch64-unknown-linux-gnu"):
            with mock.patch.object(build, "output", return_value=rust), self.assertRaises(ValueError):
                build.toolchain_identity("linux", "cargo", "1.99.1", "cmake", "ninja", {})
        for observed in [("wrong", ""), (build.GODOT_CPP_REVISION, " M tracked.h"), (build.GODOT_CPP_REVISION, "?? untracked.h")]:
            with mock.patch.object(build, "output", side_effect=observed), self.assertRaisesRegex(ValueError, "pinned"):
                build.verify_dependency(Path("fixture"), {})

    def test_linux_gnu_triplet_and_actual_tool_versions(self):
        responses = ["rustc 1.99.1 (fixture)\nhost: x86_64-unknown-linux-gnu", "g++ 14.2", "x86_64-linux-gnu", "cargo 1.99.1", "cmake version 4.1.2", "1.13.1"]
        with mock.patch.object(build.shutil, "which", side_effect=lambda name, **kwargs: "/usr/bin/"+name), mock.patch.object(build, "output", side_effect=responses):
            actual = build.toolchain_identity("linux", "cargo", "1.99.1", "cmake", "ninja", {})
        self.assertEqual(actual["generator"], "Ninja")
        self.assertEqual(actual["compiler"], "g++ 14.2")

    def test_build_uses_ninja_pinned_dependency_bounded_jobs_and_external_cargo_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository, _ = NativeReleaseTests().fixture(root)
            args = build.parser().parse_args([])
            args.repository, args.out = repository, root / "out"
            args.build_root, args.dependency_dir = root / "owned/build", root / "owned/godot-cpp"
            calls = []
            def fake_run(command, env=None, cwd=None, **kwargs):
                calls.append((list(map(str, command)), env, cwd))
                if "--build" in command:
                    artifact = args.build_root / "cpp/client_runtime.dll"
                    artifact.parent.mkdir(parents=True)
                    artifact.write_bytes(b"compiled fixture")
            with mock.patch.object(build, "run", side_effect=fake_run), mock.patch.object(build, "prepare_dependency"), mock.patch.object(build, "verify_dependency", return_value=build.GODOT_CPP_REVISION):
                manifest = build.build_payload(args, "windows", {}, toolchain())
            configure = next(row for row in calls if "-S" in row[0])[0]
            self.assertEqual(configure[configure.index("-G")+1], "Ninja")
            self.assertIn("-DGODOT_CPP_REVISION="+build.GODOT_CPP_REVISION, configure)
            self.assertIn("-DFETCHCONTENT_SOURCE_DIR_GODOT_CPP="+str(args.dependency_dir), configure)
            self.assertTrue(all(row[1]["CARGO_TARGET_DIR"] == str(args.build_root / "cargo") for row in calls))
            self.assertEqual(manifest["build"]["policy"], build.BUILD_POLICY)
            self.assertEqual(manifest["godot_cpp_revision"], build.GODOT_CPP_REVISION)


if __name__ == "__main__":
    unittest.main()
