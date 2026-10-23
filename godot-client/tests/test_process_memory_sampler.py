"""Owned-process memory telemetry contracts; fake handles/readers/processes only."""
from __future__ import annotations

import ctypes
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent / "integration"))
import process_memory_sampler as memory
import run_crowd_presentation_benchmark as runner


def counters(working=100, private=80, os_working=150, os_private=110):
    return dict(zip(memory.METRICS, (working, private, os_working, os_private)))


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class ProcessMemoryTests(unittest.TestCase):
    def sampler(self, reader, **kwargs):
        self.clock = Clock()
        self.process = SimpleNamespace(pid=6789, _handle=123)
        self.factory = mock.Mock(return_value=reader)
        return memory.ProcessMemorySampler(self.process, 0, reader_factory=self.factory,
            clock=self.clock, wall_clock=lambda: 1000 + self.clock.now, **kwargs)

    def test_query_rate_peaks_and_observation_timestamps(self):
        reader = mock.Mock(side_effect=[counters(), counters(200, 90, 500, 120),
                                       counters(120, 160, 500, 190)])
        sampler = self.sampler(reader)
        for now in (0, .01, .99, 1, 1.01, 2.1):
            self.clock.now = now
            sampler.sample_if_due()
        data = sampler.snapshot()
        self.factory.assert_called_once_with(self.process)
        self.assertEqual(reader.call_count, 3)
        self.assertEqual(data["status"], "available")
        self.assertEqual([s["elapsedSeconds"] for s in data["samples"]], [0, 1, 2.1])
        self.assertEqual(data["peaks"]["workingSetBytes"],
                         {"bytes": 200, "observedAt": {"elapsedSeconds": 1, "unixTime": 1001}})
        self.assertEqual(data["peaks"]["privateBytes"]["bytes"], 160)
        self.assertEqual(data["peaks"]["osPeakWorkingSetBytes"]["bytes"], 500)
        self.assertEqual(data["peaks"]["osPeakPrivateCommitBytes"]["bytes"], 190)

    def test_optional_os_peaks_are_null_rather_than_zero(self):
        sampler = self.sampler(lambda: counters(os_working=0, os_private=None))
        self.assertTrue(sampler.sample_if_due())
        data = sampler.snapshot()
        self.assertIsNone(data["samples"][0]["osPeakWorkingSetBytes"])
        self.assertIsNone(data["peaks"]["osPeakPrivateCommitBytes"])
        self.assertEqual(data["status"], "available")

    def test_invalid_current_counter_is_unavailable_not_zero(self):
        for invalid in (0, -1, None, True, float("nan")):
            with self.subTest(invalid=invalid):
                sampler = self.sampler(lambda: counters(working=invalid))
                self.assertFalse(sampler.sample_if_due())
                data = sampler.snapshot()
                self.assertEqual(data["status"], "unavailable")
                self.assertEqual(data["samples"], [])
                self.assertTrue(all(v is None for v in data["peaks"].values()))
                self.assertIn("workingSetBytes", data["unavailableReason"]["reason"])

    def test_failure_preserves_prior_peak_and_disables_more_queries(self):
        reader = mock.Mock(side_effect=[counters(), OSError("gone")])
        sampler = self.sampler(reader)
        self.assertTrue(sampler.sample_if_due(0))
        self.assertFalse(sampler.sample_if_due(1))
        self.assertFalse(sampler.sample_if_due(2))
        data = sampler.snapshot()
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(data["status"], "partial")
        self.assertEqual(data["sampleCount"], 1)
        self.assertEqual(data["peaks"]["privateBytes"]["bytes"], 80)
        self.assertEqual(data["unavailableReason"]["elapsedSeconds"], 1)
        self.assertIn("gone", data["unavailableReason"]["reason"])

    def test_factory_failure_is_explicit_unavailable(self):
        factory = mock.Mock(side_effect=OSError("unsupported_platform"))
        sampler = memory.ProcessMemorySampler(SimpleNamespace(pid=6789), 0,
            reader_factory=factory, clock=lambda: 0, wall_clock=lambda: 1000)
        self.assertFalse(sampler.sample_if_due(0))
        self.assertEqual(sampler.snapshot()["status"], "unavailable")
        self.assertIn("unsupported_platform", sampler.snapshot()["unavailableReason"]["reason"])
        factory.assert_called_once()

    def test_series_is_bounded_while_peaks_continue(self):
        sampler = self.sampler(lambda: counters(working=int(self.clock.now) + 100), series_limit=2)
        for now in range(5):
            self.clock.now = now
            sampler.sample_if_due()
        data = sampler.snapshot()
        self.assertEqual(data["sampleCount"], 5)
        self.assertEqual(len(data["samples"]), 2)
        self.assertTrue(data["seriesTruncated"])
        self.assertEqual(data["peaks"]["workingSetBytes"]["bytes"], 104)
        self.assertEqual(data["peaks"]["workingSetBytes"]["observedAt"]["elapsedSeconds"], 4)

    def test_no_wait_observations_is_explicit_unavailable(self):
        data = self.sampler(lambda: counters()).snapshot()
        self.assertEqual(data["status"], "unavailable")
        self.assertEqual(data["sampleCount"], 0)
        self.assertIn("no_workload", data["unavailableReason"]["reason"])

    def test_windows_counter_abi_borrows_exact_owned_handle(self):
        calls = []

        def fill(handle, pointer, size):
            value = pointer._obj
            calls.append((handle.value, size, value.cb))
            value.WorkingSetSize, value.PrivateUsage = 1234, 900
            value.PeakWorkingSetSize, value.PeakPagefileUsage = 2000, 1100
            return 1

        api = mock.Mock(side_effect=fill)
        # The fake DLL exposes only GetProcessMemoryInfo. No OpenProcess,
        # CloseHandle, subprocess, or query of any real process is available.
        dll = SimpleNamespace(GetProcessMemoryInfo=api)
        with mock.patch.object(memory.os, "name", "nt"), \
                mock.patch.object(ctypes, "WinDLL", create=True, return_value=dll) as loader:
            read = memory._owned_windows_reader(SimpleNamespace(_handle=12345))
            self.assertEqual(read(), counters(1234, 900, 2000, 1100))
        expected_size = 8 + 9 * ctypes.sizeof(ctypes.c_size_t)
        self.assertEqual(calls, [(12345, expected_size, expected_size)])
        loader.assert_called_once_with("psapi", use_last_error=True)
        self.assertEqual(api.restype, ctypes.c_int)

    def test_no_handle_and_non_windows_never_load_windows_api(self):
        with mock.patch.object(ctypes, "WinDLL", create=True) as loader:
            for handle in (None, 0, -1, True, "123"):
                with self.subTest(handle=handle), mock.patch.object(memory.os, "name", "nt"):
                    with self.assertRaisesRegex(OSError, "owned_process_handle"):
                        memory._owned_windows_reader(SimpleNamespace(_handle=handle))
            with mock.patch.object(memory.os, "name", "posix"):
                with self.assertRaisesRegex(OSError, "unsupported_platform"):
                    memory._owned_windows_reader(SimpleNamespace(_handle=123))
            loader.assert_not_called()

    def test_wait_loop_samples_without_changing_normal_completion(self):
        reader = mock.Mock(return_value=counters())
        sampler = self.sampler(reader)
        marker = SimpleNamespace(is_file=lambda: False)

        def wait(timeout=None):
            self.clock.now += timeout
            if self.clock.now >= 2.5:
                return 0
            raise subprocess.TimeoutExpired(["fake"], timeout)

        process = SimpleNamespace(args=["fake"], wait=wait)
        with mock.patch.object(runner.time, "monotonic", self.clock):
            result = runner.wait_for_workload(process, marker, {}, 10, memory_sampler=sampler)
        self.assertEqual(result, (0, None))
        data = sampler.snapshot()
        self.assertEqual(reader.call_count, 3)
        times = [s["elapsedSeconds"] for s in data["samples"]]
        self.assertTrue(all(b - a >= 1 for a, b in zip(times, times[1:])))

    def test_existing_failed_teardown_protocol_precedes_optional_sampling(self):
        sampler = mock.Mock()
        marker = SimpleNamespace(is_file=lambda: True, stat=lambda: SimpleNamespace(st_size=10))
        process = mock.Mock(poll=mock.Mock(return_value=None))
        failure = {"requiresRunnerTermination": True, "failure": "teardown_timeout",
                   "teardown": {"ready": False}}
        with mock.patch.object(runner, "read_json", return_value=failure), \
                mock.patch.object(runner, "validate_startup_ack", return_value=failure):
            result = runner.wait_for_workload(process, marker, {}, 10, memory_sampler=sampler)
        self.assertEqual(result, ("teardown-failed", failure))
        process.kill.assert_called_once()
        process.wait.assert_called_once_with()
        sampler.sample_if_due.assert_not_called()


if __name__ == "__main__":
    unittest.main()
