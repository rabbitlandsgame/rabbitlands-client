"""Regression tests for Tracy crowd-profile marker and zone attribution checks."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


CLIENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = CLIENT_ROOT / "scripts" / "analyze_tracy_crowd_profile.py"
SPEC = importlib.util.spec_from_file_location("analyze_tracy_crowd_profile", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def _marker(
    event: str,
    *,
    process_id: int = 42,
    cell: str = "cell-a",
    trace_ns: int = 1_000,
    unix_us: int = 10_000,
    engine_us: int = 20_000,
    process_frame: int = 100,
) -> dict:
    return {
        "schemaVersion": 1,
        "event": event,
        "cell": cell,
        "processId": process_id,
        "unixMicroseconds": unix_us,
        "engineMicroseconds": engine_us,
        "processFrame": process_frame,
        "traceNanoseconds": trace_ns,
    }


def _complete_window() -> tuple[dict, dict, list[dict]]:
    start = _marker("sample_start")
    end = _marker(
        "sample_end",
        trace_ns=4_000,
        unix_us=10_300,
        engine_us=20_300,
        process_frame=103,
    )
    return start, end, [start, end]


class MarkerPairingTests(unittest.TestCase):
    def test_rejects_orphan_end_and_unpaired_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "Orphan sample_end"):
            ANALYZER.pair_windows([_marker("sample_end")])

        with self.assertRaisesRegex(ValueError, "Unpaired sample_start"):
            ANALYZER.pair_windows([_marker("sample_start")])

    def test_rejects_duplicate_start_for_same_process_and_cell(self) -> None:
        duplicate = [
            _marker("sample_start", trace_ns=1_000),
            _marker("sample_start", trace_ns=2_000),
        ]
        with self.assertRaisesRegex(ValueError, "Overlapping sample_start"):
            ANALYZER.pair_windows(duplicate)

    def test_rejects_invalid_timestamp_and_zero_frame_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            messages = Path(temporary) / "messages.csv"
            messages.write_text(
                "message,timestamp\n"
                "ELORIA_CROWD_ENGINE_PROFILE {\"event\":\"sample_start\"},bad\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                ANALYZER.read_markers(messages)

        start = _marker("sample_start", trace_ns=1_000, process_frame=100)
        zero_frame_end = _marker(
            "sample_end",
            trace_ns=2_000,
            unix_us=10_100,
            engine_us=20_100,
            process_frame=100,
        )
        with self.assertRaisesRegex(ValueError, "Nonpositive sample window"):
            ANALYZER.pair_windows([start, zero_frame_end])

    def test_rejects_nonmonotonic_engine_and_unix_clocks(self) -> None:
        start = _marker("sample_start")
        same_engine = _marker(
            "sample_end",
            trace_ns=2_000,
            unix_us=10_100,
            engine_us=20_000,
            process_frame=101,
        )
        with self.assertRaisesRegex(ValueError, "Non-monotonic engine clock"):
            ANALYZER.pair_windows([start, same_engine])

        same_unix = _marker(
            "sample_end",
            trace_ns=2_000,
            unix_us=10_000,
            engine_us=20_100,
            process_frame=101,
        )
        with self.assertRaisesRegex(ValueError, "Non-monotonic UTC clock"):
            ANALYZER.pair_windows([start, same_unix])


class BenchmarkCorroborationTests(unittest.TestCase):
    def test_rejects_benchmark_pid_cell_and_frame_mismatches(self) -> None:
        start, end, markers = _complete_window()
        window = ANALYZER.pair_windows(markers)[0]
        marker_fields = {
            key: start[key]
            for key in (
                "schemaVersion",
                "event",
                "cell",
                "processId",
                "unixMicroseconds",
                "engineMicroseconds",
                "processFrame",
            )
        }
        stored_start = marker_fields
        stored_end = {
            key: end[key]
            for key in (
                "schemaVersion",
                "event",
                "cell",
                "processId",
                "unixMicroseconds",
                "engineMicroseconds",
                "processFrame",
            )
        }

        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            report_path = session / "benchmark.json"
            manifest_path = session / "manifest.json"
            report = {
                "process": {"pid": 42},
                "cells": [
                    {
                        "id": "cell-a",
                        "sample": {
                            "frames": 3,
                            "engineProfileWindow": {
                                "enabled": True,
                                "start": stored_start,
                                "end": stored_end,
                            },
                        },
                    }
                ],
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            manifest_path.write_text(
                json.dumps({"captured": {"reports": [str(report_path)]}}),
                encoding="utf-8",
            )
            self.assertEqual(
                ANALYZER.corroborate_benchmark(session, [window]), report_path
            )

            for label, mutate, expected in (
                (
                    "pid",
                    lambda candidate: candidate["process"].update(pid=99),
                    "captured benchmark PID",
                ),
                (
                    "cell",
                    lambda candidate: candidate["cells"][0].update(id="other-cell"),
                    "absent from benchmark",
                ),
                (
                    "frames",
                    lambda candidate: candidate["cells"][0]["sample"].update(frames=4),
                    "sampled frame count",
                ),
            ):
                with self.subTest(label=label):
                    candidate = copy.deepcopy(report)
                    mutate(candidate)
                    report_path.write_text(json.dumps(candidate), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected):
                        ANALYZER.corroborate_benchmark(session, [window])


class ZoneBoundaryAccountingTests(unittest.TestCase):
    def test_omits_boundary_self_time_and_keeps_fully_contained_self_exact(self) -> None:
        events = [
            {
                "name": "boundary-before",
                "startNs": 90,
                "inclusiveNs": 20,
                "selfNs": 17,
            },
            {
                "name": "fully-contained",
                "startNs": 120,
                "inclusiveNs": 10,
                "selfNs": 6,
            },
            {
                "name": "boundary-after",
                "startNs": 190,
                "inclusiveNs": 20,
                "selfNs": 13,
            },
        ]
        totals = ANALYZER.zone_totals(
            events,
            [{"startNs": 100, "endNs": 200}],
        )[0]

        before = totals["boundary-before"]
        self.assertEqual(before["inclusiveNs"], 10)
        self.assertEqual(before["selfNs"], 0)
        self.assertEqual(before["selfCount"], 0)
        self.assertEqual(before["boundaryOmittedSelfCount"], 1)

        contained = totals["fully-contained"]
        self.assertEqual(contained["inclusiveNs"], 10)
        self.assertEqual(contained["selfNs"], 6)
        self.assertEqual(contained["selfCount"], 1)
        self.assertEqual(contained["boundaryOmittedSelfCount"], 0)

        after = totals["boundary-after"]
        self.assertEqual(after["inclusiveNs"], 10)
        self.assertEqual(after["selfNs"], 0)
        self.assertEqual(after["selfCount"], 0)
        self.assertEqual(after["boundaryOmittedSelfCount"], 1)

    def test_focused_totals_keep_same_named_script_zones_separate_by_source(self) -> None:
        header = "name,src_file,src_line,ns_since_start,exec_time_ns,thread\n"
        inclusive = (
            header
            + "update_pose,res://a.gd,10,120,10,main\n"
            + "update_pose,res://b.gd,20,140,20,main\n"
        )
        self_time = (
            header
            + "update_pose,res://a.gd,10,120,4,main\n"
            + "update_pose,res://b.gd,20,140,7,main\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            session = Path(temporary)
            (session / "focus-00-inclusive.csv").write_text(
                inclusive, encoding="utf-8"
            )
            (session / "focus-00-self.csv").write_text(self_time, encoding="utf-8")
            totals = ANALYZER.read_focus_zone_totals(
                session, [{"startNs": 100, "endNs": 200}]
            )[0]

        self.assertEqual(totals[("update_pose", "res://a.gd")]["inclusiveNs"], 10)
        self.assertEqual(totals[("update_pose", "res://a.gd")]["selfNs"], 4)
        self.assertEqual(totals[("update_pose", "res://b.gd")]["inclusiveNs"], 20)
        self.assertEqual(totals[("update_pose", "res://b.gd")]["selfNs"], 7)


if __name__ == "__main__":
    unittest.main()
