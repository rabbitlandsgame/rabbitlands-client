"""Admission runner controls and evidence contracts; fake child only."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_crowd_benchmark_runner import fixture, write_startup_ack
import crowd_benchmark_support as support
import run_crowd_presentation_benchmark as runner


def admission_fixture():
    data, request = fixture()
    request.update(client_runtime="services", resource_admission="rust", resource_admission_budget_mib=512)
    for runtime in (data, data["cells"][0]["effectiveRuntime"]):
        runtime["activeBackends"]["clientRuntime"] = {
            "requested": "services", "mode": "services", "presentation_backend": "legacy",
            "native_available": True, "mismatches": 0}
        runtime["activeBackends"]["resourceAdmission"] = {
            "requested_mode": "rust", "requested_estimate_budget": 512 * 1048576,
            "mode": "rust", "reason": "rust_global_admission", "estimate_budget": 512 * 1048576,
            "admitted": 2, "denied": 0, "publication_grants": 2, "publication_deferrals": 0,
            "transition_failures": 0, "dependency_graph": {"registrations": 2, "failures": {}},
            "native": dict.fromkeys(("reserved", "loading", "ready", "active", "retiring", "cancelled",
                                     "old_epoch", "denials", "forced_sync"), 0)}
    return data, request


class AdmissionRunnerTests(unittest.TestCase):
    def test_selectors_defaults_and_request_capture(self):
        args = runner.parser().parse_args(["--godot", "unused.exe"])
        self.assertEqual((args.client_runtime, args.resource_admission, args.resource_admission_budget_mib),
                         ("legacy", "legacy", 768))
        args = runner.parser().parse_args(["--godot", "unused.exe", "--client-runtime", "services",
            "--resource-admission", "rust", "--resource-admission-budget-mib", "512"])
        request = runner.request_for(args)
        self.assertEqual((request["client_runtime"], request["resource_admission"],
                          request["resource_admission_budget_mib"]), ("services", "rust", 512))
        for budget in ("0", "63", "8193", "1.5", "nan"):
            with self.subTest(budget=budget), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                runner.parser().parse_args(["--godot", "unused.exe", "--resource-admission-budget-mib", budget])

    def test_services_requires_actual_native_and_legacy_presentation(self):
        data, request = admission_fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for update in ({"native_available": False}, {"mode": "legacy"}, {"presentation_backend": "mixed"}):
            bad = copy.deepcopy(data)
            bad["activeBackends"]["clientRuntime"].update(update)
            with self.subTest(update=update), self.assertRaises(support.EvidenceError):
                support.validate_report(bad, request, "")

    def test_admission_request_budget_fallback_and_failures_rejected_at_cell_boundary(self):
        data, request = admission_fixture()
        for update in ({"requested_mode": "legacy"}, {"requested_estimate_budget": 768 * 1048576},
                       {"estimate_budget": 768 * 1048576}, {"mode": "legacy"},
                       {"reason": "optional_admission_api_absent"}, {"transition_failures": 1},
                       {"native": {}}, {"dependency_graph": {"registrations": 2, "failures": {"changed": 1}}}):
            bad = copy.deepcopy(data)
            bad["cells"][0]["effectiveRuntime"]["activeBackends"]["resourceAdmission"].update(update)
            with self.subTest(update=update), self.assertRaises(support.EvidenceError):
                support.validate_report(bad, request, "")
        bad = copy.deepcopy(data)
        del bad["activeBackends"]["resourceAdmission"]
        with self.assertRaises(support.EvidenceError):
            support.validate_report(bad, request, "")

    def test_legacy_compatibility_and_explicit_legacy_selector(self):
        data, request = fixture()
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        for runtime in (data, data["cells"][0]["effectiveRuntime"]):
            runtime["activeBackends"]["resourceAdmission"] = {"mode": "legacy", "requested": False,
                "requested_mode": "legacy", "requested_estimate_budget": 768 * 1048576}
        self.assertTrue(support.validate_report(data, request, "")["valid"])
        data["activeBackends"]["resourceAdmission"]["requested"] = True
        with self.assertRaises(support.EvidenceError):
            support.validate_report(data, request, "")

    def test_rust_admission_without_service_rejected_before_launch(self):
        with mock.patch.object(runner.subprocess, "Popen") as launch:
            self.assertEqual(runner.main(["--godot", "unused.exe", "--resource-admission", "rust"]), 1)
        launch.assert_not_called()

    def test_only_owned_child_receives_controls_and_metadata_captures_them(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "Godot.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                "--cells", "s3-market-160", "--mode", "windowed", "--quality", "high",
                "--minimap", "show", "--body-cap", "160", "--sample-ms", "1000", "--warmup-ms", "100",
                "--client-runtime", "services", "--resource-admission", "rust",
                "--resource-admission-budget-mib", "512"])
            args.godot = exe
            data, _ = admission_fixture()
            def fake_launch(command, *, env, stdout, **kwargs):
                self.assertEqual(env["RABBITLANDS_CLIENT_RUNTIME"], "services")
                self.assertEqual(env["RABBITLANDS_RESOURCE_ADMISSION"], "rust")
                self.assertEqual(env["RABBITLANDS_RESOURCE_BUDGET_MIB"], "512")
                user = Path(env["APPDATA"]) / "Godot/app_userdata/Eloria"
                data["runtimeBuild"].update(executablePath=str(exe), userDataDir=str(user))
                write_startup_ack(env, exe, user)
                Path(env["RABBITLANDS_CROWD_BENCH_OUT"]).write_text(json.dumps(data))
                Path(command[command.index("--log-file") + 1]).write_text("normal")
                return mock.Mock(pid=12345, wait=mock.Mock(return_value=0), poll=mock.Mock(return_value=None))
            with mock.patch.dict(os.environ, {"RABBITLANDS_RESOURCE_ADMISSION": "inherited",
                                             "RABBITLANDS_RESOURCE_BUDGET_MIB": "2048"}), \
                    mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner, "ProcessMemorySampler"), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=fake_launch):
                before = dict(os.environ)
                runner.ProcessMemorySampler.return_value.snapshot.return_value = {"status": "unavailable"}
                result = runner.run_one(args, "all", 1, root)
                self.assertEqual(dict(os.environ), before)
            self.assertTrue(result["validation"]["valid"])
            self.assertEqual(result["effectiveOverrides"]["RABBITLANDS_RESOURCE_BUDGET_MIB"], "512")
            self.assertEqual(result["data"]["activeBackends"]["preparedContent"], {"active": False})
            self.assertIn("RABBITLANDS_RESOURCE_ADMISSION", result["clearedOverrideNames"])
            self.assertEqual(json.loads(next(root.glob("*.process.json")).read_text())["effectiveOverrides"]
                             ["RABBITLANDS_RESOURCE_ADMISSION"], "rust")


if __name__ == "__main__":
    unittest.main()
