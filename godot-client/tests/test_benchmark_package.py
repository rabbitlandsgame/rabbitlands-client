"""The local workload export must not widen ordinary release contents."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark_package
import package_client


class BenchmarkPackageTests(unittest.TestCase):
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
            benchmark_package.prepare_export(project)
            self.assertFalse((project / "tests/private_fixture.json").exists())
            self.assertTrue(all((project / name).is_file() for name in benchmark_package.WORKLOAD_FILES))
            self.assertNotIn("tests/*,", (project / "export_presets.cfg").read_text(encoding="utf-8"))
            marker = json.loads((project / "data/benchmark_profile.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["executionKind"], "exported-local-benchmark")
            self.assertIn("tests/*,", package_client.EXPORT_PRESETS)

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
            manifest = benchmark_package.write_manifest(stage, "a" * 40)
            original = manifest.read_bytes()
            benchmark_package.write_manifest(stage, "a" * 40)
            self.assertEqual(manifest.read_bytes(), original)
            rows = {r["path"]: r for r in json.loads(original)["artifacts"]}
            self.assertEqual(set(rows), {"app/RabbitLands.pck", "loose.glb"})
            self.assertEqual(rows["loose.glb"]["sha256"], hashlib.sha256(b"actor").hexdigest())


if __name__ == "__main__":
    unittest.main()
