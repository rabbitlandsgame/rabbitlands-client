"""Process-owned failed-drain termination; fake processes only, no engine."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "integration"))
import run_crowd_presentation_benchmark as runner
from crowd_benchmark_support import EvidenceError, read_json


class TeardownCompletionTests(unittest.TestCase):
    def marker(self, root):
        request = {"pid": 12345, "executable": str(root / "app.exe"), "executable_mode": "exported",
                   "start_token": "own-nonce", "user_root": str(root / "userdata")}
        marker = {"schemaVersion": 1, "benchmark": "crowd_presentation", "pid": request["pid"],
                  "executablePath": request["executable"], "executionMode": "exported",
                  "startToken": "own-nonce", "userDataDir": str(root / "userdata/custom"),
                  "requiresRunnerTermination": True, "failure": "teardown_timeout",
                  "teardown": {"ready": False, "failedStage": "beforeUnload", "animationWorkers": 1}}
        return request, marker

    def test_small_valid_marker_stops_only_own_process_and_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, marker = self.marker(root)
            path = root / "sample.json.teardown-failed.json"
            path.write_text(json.dumps(marker))
            process = mock.Mock(pid=12345, poll=mock.Mock(return_value=None))
            with mock.patch.object(runner, "read_json", wraps=read_json) as read:
                code, retained = runner.wait_for_workload(process, path, request, 60)
            self.assertEqual(code, "teardown-failed")
            self.assertEqual(retained, marker)
            read.assert_called_once_with(path)
            process.kill.assert_called_once_with()
            process.wait.assert_called_once_with()

    def test_wrong_or_malformed_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, marker = self.marker(root)
            path = root / "sample.json.teardown-failed.json"
            for changed in (marker | {"pid": 999}, marker | {"startToken": "stale"},
                            marker | {"requiresRunnerTermination": False}, marker | {"failure": "other"},
                            marker | {"teardown": {"ready": True}}, [], "not a JSON object"):
                path.write_text(json.dumps(changed))
                process = mock.Mock(pid=12345)
                with self.subTest(changed=changed), self.assertRaises(EvidenceError):
                    runner.wait_for_workload(process, path, request, 60)
                process.kill.assert_not_called()  # The caller owns rejected-workload termination.
            path.write_bytes(b"x" * 16385)
            with self.assertRaisesRegex(EvidenceError, "unexpectedly large"):
                runner.wait_for_workload(mock.Mock(), path, request, 60)

    def test_normal_exit_does_not_read_full_report_or_kill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.json").write_text("a large full report is not a control channel")
            process = mock.Mock(wait=mock.Mock(return_value=0))
            with mock.patch.object(runner, "read_json") as read:
                self.assertEqual(runner.wait_for_workload(process, root / "sample.json.teardown-failed.json", {}, 60), (0, None))
            read.assert_not_called()
            process.kill.assert_not_called()

    def test_completion_timeout_is_bounded_without_internal_live_join(self):
        with tempfile.TemporaryDirectory() as directory:
            process = mock.Mock(args=["own-app"])
            with mock.patch.object(runner.time, "monotonic", side_effect=[0, 1]), \
                    self.assertRaises(subprocess.TimeoutExpired):
                runner.wait_for_workload(process, Path(directory) / "absent", {}, .5)
            process.wait.assert_not_called()
            process.kill.assert_not_called()

    def test_run_retains_failed_report_and_marker_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "app.exe"
            exe.write_bytes(b"not executed")
            args = runner.parser().parse_args(["--godot", str(exe), "--project-path", str(root),
                                              "--executable-mode", "exported", "--main-pack", "test.pck"])
            args.godot = exe
            process = mock.Mock(pid=12345, poll=mock.Mock(return_value=None), wait=mock.Mock(return_value=-9))

            def launch(_command, *, env, **_kwargs):
                ack = {"schemaVersion": 1, "benchmark": "crowd_presentation", "pid": 12345,
                       "executablePath": str(exe), "executionMode": "exported",
                       "userDataDir": env["APPDATA"] + "/Godot/app_userdata/Eloria",
                       "startToken": env["RABBITLANDS_CROWD_BENCH_START_TOKEN"]}
                report = env["RABBITLANDS_CROWD_BENCH_OUT"]
                Path(report + ".started.json").write_text(json.dumps(ack))
                teardown = {"ready": False, "requiresRunnerTermination": True, "animationWorkers": 1}
                Path(report).write_text(json.dumps({"failureCount": 1, "teardown": teardown}))
                Path(report + ".teardown-failed.json").write_text(json.dumps(ack | {
                    "requiresRunnerTermination": True, "failure": "teardown_timeout", "teardown": teardown}))
                return process

            with mock.patch.object(runner, "identity", return_value={"source": "stable"}), \
                    mock.patch.object(runner.subprocess, "Popen", side_effect=launch):
                result = runner.run_one(args, "all", 1, root)
            self.assertFalse(result["validation"]["valid"])
            self.assertTrue(result["startup"]["valid"])
            self.assertEqual(result["exit"], "teardown-failed")
            self.assertEqual(result["teardownFailure"]["teardown"]["animationWorkers"], 1)
            self.assertTrue(Path(result["report"]).is_file())
            process.kill.assert_called_once_with()
            metadata = read_json(next(root.glob("*.process.json")))
            self.assertEqual(metadata["teardownFailure"], result["teardownFailure"])


if __name__ == "__main__":
    unittest.main()
