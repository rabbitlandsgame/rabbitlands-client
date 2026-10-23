"""An explicit local benchmark can reuse one committed actor reference proof."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import package_client


class BenchmarkActorPlanCacheTests(unittest.TestCase):
    def _invoke_until_first_external_step(self, callback, *, benchmark=True):
        """Stop before build/export; only argument and invocation setup runs."""
        def stop(_wanted):
            callback()
            raise package_client.PackageError("controlled stop before build")

        arguments = ["--no-fetch"]
        if benchmark:
            arguments.extend(["--distribution", "standalone", "--benchmark-profile"])
        with mock.patch.object(package_client, "find_godot", side_effect=stop), \
                mock.patch.object(package_client, "log"):
            self.assertEqual(package_client.main(arguments), 1)

    def test_benchmark_profile_reuses_plan_for_resolved_build_path(self):
        build = Path("fixture-build")
        plan = {"loose": {"actor.glb"}}

        def probe():
            self.assertIsNotNone(package_client.BENCHMARK_ACTOR_PLANS)
            for spelling in (build, build / ".", build, build):
                self.assertIs(package_client.actor_shipping(spelling), plan)

        with mock.patch.object(package_client, "_actor_shipping", return_value=plan) as compute:
            self._invoke_until_first_external_step(probe)
            compute.assert_called_once_with(build)

    def test_normal_package_recomputes_plan_at_each_call(self):
        build = Path("fixture-build")
        plans = [{"generation": index} for index in range(4)]

        def probe():
            self.assertIsNone(package_client.BENCHMARK_ACTOR_PLANS)
            for plan in plans:
                self.assertIs(package_client.actor_shipping(build), plan)

        with mock.patch.object(package_client, "_actor_shipping", side_effect=plans) as compute:
            self._invoke_until_first_external_step(probe, benchmark=False)
            self.assertEqual(compute.call_count, 4)

    def test_different_build_roots_never_share_a_plan(self):
        first, second = Path("first-build"), Path("second-build")
        plans = [{"source": "first"}, {"source": "second"}]

        def probe():
            self.assertIs(package_client.actor_shipping(first), plans[0])
            self.assertIs(package_client.actor_shipping(second), plans[1])
            self.assertIs(package_client.actor_shipping(first), plans[0])

        with mock.patch.object(package_client, "_actor_shipping", side_effect=plans) as compute:
            self._invoke_until_first_external_step(probe)
            self.assertEqual(compute.call_count, 2)

    def test_consecutive_invocations_use_fresh_plan_and_restore_caller_cache(self):
        build = Path("fixture-build")
        caller_cache = {build.resolve(): {"source": "caller"}}
        plans = [{"generation": 1}, {"generation": 2}]
        observed = []

        def probe():
            self.assertIsNot(package_client.BENCHMARK_ACTOR_PLANS, caller_cache)
            current = package_client.actor_shipping(build)
            observed.append(current)
            self.assertIs(package_client.actor_shipping(build), current)

        with mock.patch.object(package_client, "BENCHMARK_ACTOR_PLANS", caller_cache), \
                mock.patch.object(package_client, "_actor_shipping", side_effect=plans) as compute:
            for _ in range(2):
                self._invoke_until_first_external_step(probe)
                self.assertIs(package_client.BENCHMARK_ACTOR_PLANS, caller_cache)
            self.assertEqual(compute.call_count, 2)
            self.assertEqual(observed, plans)

    def test_main_restores_context_even_after_unexpected_failure(self):
        caller_cache = {Path("previous").resolve(): {"previous": True}}
        prior_storage = object()

        def stop(_wanted):
            self.assertEqual(package_client.BENCHMARK_ACTOR_PLANS, {})
            self.assertIsNot(package_client.BENCHMARK_ACTOR_PLANS, caller_cache)
            raise RuntimeError("unexpected failure")

        with mock.patch.object(package_client, "BENCHMARK_ACTOR_PLANS", caller_cache), \
                mock.patch.object(package_client, "BENCHMARK_LINKS", False), \
                mock.patch.object(package_client, "STORAGE", prior_storage), \
                mock.patch.object(package_client, "find_godot", side_effect=stop):
            with self.assertRaisesRegex(RuntimeError, "unexpected failure"):
                package_client.main(["--distribution", "standalone", "--benchmark-profile"])
            self.assertIs(package_client.BENCHMARK_ACTOR_PLANS, caller_cache)
            self.assertIs(package_client.STORAGE, prior_storage)
            self.assertFalse(package_client.BENCHMARK_LINKS)

    def test_preparing_another_generation_invalidates_that_build_path(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            project = build / "godot-client"
            (project / "assets/actors").mkdir(parents=True)
            (build / ".git").write_text("fixture", encoding="utf-8")
            stale = {"source": "previous generation"}
            fresh = {"pck_folders": set(), "loose_folders": set(), "kept": {}}
            cache = {build.resolve(): stale}
            with mock.patch.object(package_client, "STORAGE", None), \
                    mock.patch.object(package_client, "BENCHMARK_ACTOR_PLANS", cache), \
                    mock.patch.object(package_client, "git"), \
                    mock.patch.object(package_client, "log"), \
                    mock.patch.object(package_client, "_actor_shipping", return_value=fresh) as compute, \
                    mock.patch.object(package_client, "write_actor_import_settings"), \
                    mock.patch.object(package_client, "scene_textures", return_value={}), \
                    mock.patch.object(package_client, "write_scene_texture_import_settings"):
                self.assertIs(package_client.actor_shipping(build), stale)
                self.assertEqual(package_client.prepare_build_tree(build, "a" * 40), project)
                self.assertIs(package_client.actor_shipping(build), fresh)
                compute.assert_called_once_with(build)


if __name__ == "__main__":
    unittest.main()
