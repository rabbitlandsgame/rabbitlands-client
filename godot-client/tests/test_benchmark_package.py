"""The local workload export must not widen ordinary release contents."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark_package
import package_client


class BenchmarkPackageTests(unittest.TestCase):
    def test_native_resource_lifetime_fixture_survives_local_export(self):
        expected = {"tests/integration/benchmark_resource_admission.gd",
                    "tests/test_native_streaming_lifetime.gd"}
        self.assertTrue(expected.issubset(benchmark_package.WORKLOAD_FILES))
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "data").mkdir()
            for name in benchmark_package.WORKLOAD_FILES | {"tests/unrelated_private.json"}:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
            (project / "project.godot").write_text(
                '[application]\nrun/main_scene="res://src/app/main.tscn"\n', encoding="utf-8")
            benchmark_package.prepare_export(project)
            self.assertTrue(all((project / name).is_file() for name in expected))
            self.assertFalse((project / "tests/unrelated_private.json").exists())


    def test_local_asset_links_do_not_share_mutable_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous = package_client.BENCHMARK_LINKS
            package_client.BENCHMARK_LINKS = True
            try:
                for name in ["actor.glb", "client-release.json"]:
                    source = root / name
                    source.write_bytes(b"fixture")
                    destination = root / "stage" / name
                    package_client.copy_file(source, destination)
                    self.assertEqual(source.stat().st_ino == destination.stat().st_ino,
                                     name.endswith(".glb"))
            finally:
                package_client.BENCHMARK_LINKS = previous

    def test_profile_is_an_explicit_standalone_only_option(self):
        self.assertIn("tests/*,", package_client.EXPORT_PRESETS)
        self.assertEqual(package_client.main(["--benchmark-profile"]), 1)

    def test_only_allowlisted_workloads_are_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "data").mkdir()
            for name in benchmark_package.WORKLOAD_FILES | {"tests/private_fixture.json"}:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
            normal_settings = ('[application]\nconfig/name="Fixture"\n'
                               'run/main_scene="res://src/app/main.tscn"\n'
                               'run/main_loop_type="SceneTree"\n\n'
                               '[autoload]\nAppState="*res://src/state/app_state.gd"\n\n'
                               '[editor_plugins]\nenabled=PackedStringArray("res://editor/plugin.cfg")\n')
            (project / "project.godot").write_text(normal_settings, encoding="utf-8")
            benchmark_package.prepare_export(project)
            self.assertFalse((project / "tests/private_fixture.json").exists())
            self.assertTrue(all((project / name).is_file() for name in benchmark_package.WORKLOAD_FILES))
            self.assertNotIn("tests/*,", (project / "export_presets.cfg").read_text(encoding="utf-8"))
            marker = json.loads((project / "data/benchmark_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["executionKind"], "exported-local-benchmark")
            self.assertEqual(marker["mainLoopClass"], benchmark_package.MAIN_LOOP_CLASS)
            self.assertEqual(marker["mainEntryScene"], benchmark_package.MAIN_ENTRY_SCENE)
            self.assertEqual(marker["executionModeEnvironment"], benchmark_package.EXECUTION_MODE_ENVIRONMENT)
            self.assertEqual(marker["benchmarkExecutionMode"], "exported")
            self.assertEqual(marker["defaultMainScene"], "res://src/app/main.tscn")
            settings = (project / "project.godot").read_text(encoding="utf-8")
            self.assertIn(f'run/main_loop_type="{benchmark_package.MAIN_LOOP_CLASS}"', settings)
            self.assertIn(f'run/main_scene="{benchmark_package.MAIN_ENTRY_SCENE}"', settings)
            self.assertNotIn('run/main_scene="res://src/app/main.tscn"', settings)
            self.assertIn('[autoload]\nAppState="*res://src/state/app_state.gd"', settings)
            self.assertIn('enabled=PackedStringArray()', settings)
            self.assertIn("tests/*,", package_client.EXPORT_PRESETS)

    def test_route_snapshot_helper_survives_export_without_exporting_its_test(self):
        helper = "tests/integration/benchmark_route_content.gd"
        fixture = "tests/integration/test_benchmark_route_content.gd"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "data").mkdir()
            for name in benchmark_package.WORKLOAD_FILES | {helper, fixture}:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
            (project / "project.godot").write_text(
                '[application]\nrun/main_scene="res://src/app/main.tscn"\n', encoding="utf-8")
            benchmark_package.prepare_export(project)
            self.assertTrue((project / helper).is_file())
            self.assertFalse((project / fixture).exists())

    def test_mounted_census_helper_survives_export_without_exporting_its_test(self):
        helper = "tests/integration/benchmark_mounted_census.gd"
        fixture = "tests/test_benchmark_mounted_census.gd"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "data").mkdir()
            for name in benchmark_package.WORKLOAD_FILES | {helper, fixture}:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture", encoding="utf-8")
            (project / "export_presets.cfg").write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
            (project / "project.godot").write_text(
                '[application]\nrun/main_scene="res://src/app/main.tscn"\n', encoding="utf-8")
            benchmark_package.prepare_export(project)
            self.assertTrue((project / helper).is_file())
            self.assertFalse((project / fixture).exists())

    def test_loop_settings_preserve_unrelated_sections_and_are_idempotent(self):
        original = ('[application]\nconfig/name="Fixture"\n'
                    'run/main_scene="res://src/app/main.tscn"\n\n'
                    '[unrelated]\nrun/main_scene="unrelated"\n'
                    'run/main_loop_type="other"\n')
        prepared = benchmark_package._benchmark_loop_settings(original)
        self.assertEqual(benchmark_package._benchmark_loop_settings(prepared), prepared)
        application, unrelated = prepared.split("[unrelated]")
        self.assertEqual(len(re.findall(r"(?m)^run/main_loop_type=", application)), 1)
        self.assertIn(f'run/main_loop_type="{benchmark_package.MAIN_LOOP_CLASS}"', application)
        self.assertIn(f'run/main_scene="{benchmark_package.MAIN_ENTRY_SCENE}"', application)
        self.assertEqual(unrelated, '\nrun/main_scene="unrelated"\nrun/main_loop_type="other"\n')

    def test_missing_project_entry_settings_fail_before_pruning(self):
        for config in (None, '[display]\nwindow/size/viewport_width=1280\n'):
            with self.subTest(config=config), tempfile.TemporaryDirectory() as directory:
                project = Path(directory)
                for name in benchmark_package.WORKLOAD_FILES | {"tests/kept.json"}:
                    path = project / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("fixture", encoding="utf-8")
                presets = project / "export_presets.cfg"
                presets.write_text(package_client.EXPORT_PRESETS, encoding="utf-8")
                if config is not None:
                    (project / "project.godot").write_text(config, encoding="utf-8")
                with self.assertRaises(ValueError):
                    benchmark_package.prepare_export(project)
                self.assertTrue((project / "tests/kept.json").is_file())
                self.assertEqual(presets.read_text(encoding="utf-8"), package_client.EXPORT_PRESETS)

    def test_incomplete_profile_is_rejected_before_removing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "tests/kept.gd"
            path.parent.mkdir()
            path.write_text("fixture", encoding="utf-8")
            with self.assertRaises(ValueError):
                benchmark_package.prepare_export(project)
            self.assertTrue(path.exists())

    def test_manifest_covers_loose_assets_and_has_stable_self_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / "app").mkdir()
            (stage / "app/RabbitLands.pck").write_bytes(b"packed")
            (stage / "loose.glb").write_bytes(b"actor")
            # This test isolates the complete-artifact manifest contract; the
            # dedicated closure tests exercise real fake-PCK byte verification.
            with mock.patch.object(benchmark_package, "build_asset_closure", return_value={"fixture": True}):
                manifest = benchmark_package.write_manifest(stage, "a" * 40)
                original = manifest.read_bytes()
                benchmark_package.write_manifest(stage, "a" * 40)
            self.assertEqual(manifest.read_bytes(), original)
            rows = {r["path"]: r for r in json.loads(original)["artifacts"]}
            self.assertEqual(set(rows), {"app/RabbitLands.pck", "loose.glb"})
            self.assertEqual(rows["loose.glb"]["sha256"], hashlib.sha256(b"actor").hexdigest())


if __name__ == "__main__":
    unittest.main()
