"""Qualification failures and tail statistics must not silently pass."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("continent_stream_benchmark", Path(__file__).resolve().parents[1] / "tools/continent_stream_benchmark.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
compare_spec = importlib.util.spec_from_file_location("continent_stream_benchmark_compare", Path(__file__).resolve().parents[1] / "tools/continent_stream_benchmark_compare.py")
comparison = importlib.util.module_from_spec(compare_spec)
compare_spec.loader.exec_module(comparison)
project_spec = importlib.util.spec_from_file_location("continent_stream_benchmark_project", Path(__file__).resolve().parents[1] / "tools/continent_stream_benchmark_project.py")
project_overlay = importlib.util.module_from_spec(project_spec)
project_spec.loader.exec_module(project_overlay)


class ContinentStreamEvidenceTests(unittest.TestCase):
    def report(self):
        return {"ok": True, "configuration": {"run_id": "new"}, "configuration_sha256": "digest",
                "frames": [{"phase": "walk", "frame_ms": 16}]}

    def test_missing_report_cannot_qualify_successful_engine_exit(self):
        self.assertEqual(["fresh_report_missing"], bench.qualification_errors(None, {"run_id": "new"}, "digest", {}, {}))

    def test_stale_report_and_changed_config_are_rejected(self):
        report = self.report()
        report["configuration"]["run_id"] = "old"
        report["configuration_sha256"] = "old_digest"
        self.assertEqual(["report_run_id_mismatch", "report_configuration_digest_mismatch"],
                         bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))

    def test_runtime_or_import_change_invalidates_trial(self):
        errors = bench.qualification_errors(self.report(), {"run_id": "new"}, "digest", {"class.ctex": "old"}, {"class.ctex": "new"})
        self.assertIn("runtime_or_import_inputs_changed", errors)

    def test_arrival_only_is_not_moving_route_evidence(self):
        report = self.report()
        report["frames"][0]["phase"] = "arrival"
        self.assertIn("measured_movement_missing", bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))

    def test_settling_only_is_not_moving_route_evidence(self):
        report = self.report()
        report["frames"][0]["phase"] = "post_route_settle"
        self.assertIn("measured_movement_missing", bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))

    def test_missing_or_disabled_terrain_cannot_qualify(self):
        report = self.report()
        report["frames"][0].update(ground_hit=False,resident=False)
        self.assertIn("movement_ground_missing", bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))
        self.assertIn("movement_bounds_not_resident", bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))
        self.assertIn("terrain_deadline_probe_disabled", bench.qualification_errors(report, {"run_id": "new", "ground_probe":False}, "digest", {}, {}))

    def test_failed_checks_reject_otherwise_matching_report(self):
        report = self.report()
        report["ok"] = False
        self.assertIn("engine_checks_failed", bench.qualification_errors(report, {"run_id": "new"}, "digest", {}, {}))

    def test_shutdown_error_rejects_valid_report_after_successful_process_exit(self):
        log = "CONTINENT_BENCH_DONE report.json\nERROR: 1 Shader RID allocations leaked at exit\n"
        self.assertIn("engine_error_in_complete_log",bench.qualification_errors(self.report(),{"run_id":"new"},"digest",{},{},log))

    def test_short_memory_peak_survives_between_sampling_intervals(self):
        result = bench.process_memory_summary([{"rss_bytes":400,"peak_rss_bytes":500},
                                               {"rss_bytes":300,"peak_rss_bytes":1000}])
        self.assertEqual(1000,result["peak_process_rss_bytes"])
        self.assertEqual(400,result["peak_process_sampled_rss_bytes"])

    def test_tail_thresholds_are_strict_and_unprobed_is_not_a_ground_pass(self):
        frames = [{"frame_ms": value, "ground_hit": True, "resident": True} for value in [16, 33, 34, 50, 51, 100, 101]]
        frames[0]["ground_hit"] = None
        frames[1]["ground_hit"] = False
        result = bench.frame_summary(frames)
        self.assertEqual((5, 3, 1), (result["over_33ms"], result["over_50ms"], result["over_100ms"]))
        self.assertEqual(6, result["ground_probed_frames"])
        self.assertEqual(1, result["ground_missing_frames"])

    def test_nearest_rank_preserves_rare_large_frame(self):
        values = [16] * 98 + [50, 900]
        self.assertEqual(50, bench.percentile(values, .99))
        self.assertEqual(900, bench.percentile(values, 1))

    def test_route_truncation_keeps_path_and_reversal_distance(self):
        self.assertEqual([[0, 0, 0], [3, 0, 0], [3, 0, 2]], bench.trim_route([[0, 0, 0], [3, 0, 0], [3, 0, 4]], 5))

    def cohort_run(self, worst=300, p99=25, resident=100):
        self._cohort_sequence = getattr(self,"_cohort_sequence",0)+1
        return {"qualified":True,"configuration":{"run_id":str(self._cohort_sequence)},
                "output":str(self._cohort_sequence),"process_started_monotonic_ns":self._cohort_sequence*10,
                "movement":{"max_ms":worst,"p99_ms":p99,
                "ground_missing_frames":0,"bounds_not_resident_frames":0,"ground_probed_frames":100},
                "movement_and_settle":{"max_ms":worst,"p99_ms":p99},"post_route_settle_ms":100,
                "peak_process_rss_bytes":resident,"peak_memory":{"resident_estimated_bytes":resident}}

    def test_cohort_uses_median_of_per_run_worst_frames(self):
        controls = [self.cohort_run(x) for x in [1000,100,300]]
        candidates = [self.cohort_run(200,19) for unused in range(3)]
        candidates[1]["process_started_monotonic_ns"] = controls[1]["process_started_monotonic_ns"]-1
        result = comparison.compare(controls,candidates)
        self.assertEqual({"control":300,"candidate":200},result["median_worst_ms"])
        self.assertTrue(result["performance_targets_met"])

    def test_single_outlier_win_cannot_meet_cohort_verdict(self):
        result = comparison.compare([self.cohort_run()],[self.cohort_run(100,19)])
        self.assertFalse(result["performance_targets_met"])
        self.assertIn("fewer_than_three_pairs",result["validation_errors"])

    def test_quality_or_budget_comparison_is_not_a_matched_default_win(self):
        controls = [self.cohort_run() for unused in range(3)]
        candidates = [self.cohort_run(100,19) for unused in range(3)]
        for run in candidates: run["configuration"]["mip_skip"] = 1
        self.assertFalse(comparison.compare(controls,candidates)["performance_targets_met"])

    def test_low_baseline_p99_uses_absolute_two_ms_nonregression_floor(self):
        controls = [self.cohort_run(100,16.5) for unused in range(3)]
        candidates = [self.cohort_run(70,18.5) for unused in range(3)]
        candidates[1]["process_started_monotonic_ns"] = controls[1]["process_started_monotonic_ns"]-1
        self.assertTrue(comparison.compare(controls,candidates)["performance_targets_met"])

    def test_duplicate_run_cannot_supply_three_independent_pairs(self):
        control,candidate = self.cohort_run(),self.cohort_run(100,19)
        result = comparison.compare([control]*3,[candidate]*3)
        self.assertFalse(result["performance_targets_met"])
        self.assertIn("missing_or_reused_run_ids",result["validation_errors"])

    def test_always_running_candidate_second_is_not_counterbalanced(self):
        controls = [self.cohort_run() for unused in range(3)]
        candidates = [self.cohort_run(100,19) for unused in range(3)]
        self.assertIn("process_order_not_counterbalanced",comparison.compare(controls,candidates)["validation_errors"])

    def test_work_shifted_after_movement_cannot_supply_overall_win(self):
        controls = [self.cohort_run() for unused in range(3)]
        candidates = [self.cohort_run(100,19) for unused in range(3)]
        candidates[1]["process_started_monotonic_ns"] = controls[1]["process_started_monotonic_ns"]-1
        for run in candidates:
            run["movement_and_settle"] = {"max_ms":500,"p99_ms":28}
            run["post_route_settle_ms"] = 351
        result = comparison.compare(controls,candidates)
        self.assertFalse(result["performance_targets_met"])
        self.assertFalse(result["targets"]["combined_worst_frame_not_regressed"])
        self.assertFalse(result["targets"]["combined_p99_within_two_ms"])
        self.assertFalse(result["targets"]["settle_wall_within_250ms"])

    def test_default_overlay_preserves_exact_override_or_absence(self):
        original = b'\xef\xbb\xbf[rendering]\r\nmethod="forward_plus"\r\n'
        self.assertEqual(original,project_overlay.configured_override(original,0))
        self.assertIsNone(project_overlay.configured_override(None,0))

    def test_worker_override_changes_only_the_declared_key(self):
        original = b'[threading]\r\nworker_pool/max_threads=-1\r\nworker_pool/low_priority_thread_ratio=0.3\r\n[display]\r\nname="unchanged"\r\n'
        expected = original.replace(b'worker_pool/max_threads=-1',b'worker_pool/max_threads=8')
        self.assertEqual(expected,project_overlay.configured_override(original,8))

    def test_worker_override_inserts_into_existing_threading_section(self):
        original = b'[threading]\nworker_pool/low_priority_thread_ratio=0.3\n[rendering]\nsetting=true\n'
        changed = project_overlay.configured_override(original,4)
        self.assertIn(b'worker_pool/max_threads=4\n[rendering]',changed)
        self.assertIn(b'worker_pool/low_priority_thread_ratio=0.3',changed)

    def test_ambiguous_or_undeclared_worker_configuration_is_rejected(self):
        with self.assertRaises(ValueError): project_overlay.configured_override(b'[threading]\nworker_pool/max_threads=4\nworker_pool/max_threads=8\n',8)
        with self.assertRaises(ValueError): project_overlay.configured_override(None,24)


if __name__ == "__main__":
    unittest.main()
