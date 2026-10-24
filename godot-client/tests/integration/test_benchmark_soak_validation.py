"""Public route-soak evidence contract; synthetic JSON only, no processes or files."""
import copy
import math
import unittest

from benchmark_soak_validation import soak_ids, validate_soak


LEGS = ("first-southern-border", "consecutive-southern-border", "interior-entry",
        "interior-return", "teleport", "return")


def fixture():
    cells = []
    for index, identity in enumerate(("traversal-southern-soak-aa", "traversal-southern-soak-ab")):
        begin = 10_000_000 + index * 35_000_000
        wall = 1_700_000_000.0 + index * 35.0
        cells.append({"id": identity, "status": "complete", "readiness": {"ready": True},
            "route": {"iterationClock": {"index": index, "plannedIterations": 2,
                "pid": 4321, "mainInstanceId": 9876, "visit": "cold" if index == 0 else "warm",
                "begin": {"ticksUsec": begin, "unixTime": wall},
                "end": {"ticksUsec": begin + 30_000_000, "unixTime": wall + 30.0}},
                "legs": [{"id": name, "success": True, "readiness": {"ready": True}} for name in LEGS]}})
    return {"cells": cells, "teardown": {"ready": True,
        "ownedSubtreeDisabledAfterDrain": True, "ownedInstrumentationDisconnected": True,
        "beforeUnload": {"ready": True}, "afterUnload": {"ready": True}, "afterMainFree": {"ready": True}}}


class SoakEvidenceTests(unittest.TestCase):
    def test_two_iterations_preserve_one_owner_and_include_inter_iteration_gap(self):
        report = fixture()
        original = copy.deepcopy(report)
        result = validate_soak(report, "route-soak-2")
        self.assertEqual(report, original)
        self.assertEqual((result["pid"], result["mainInstanceId"]), (4321, 9876))
        self.assertEqual((result["iterations"], result["successfulTransitions"], result["expectedTransitions"]), (2, 12, 12))
        self.assertEqual(result["iterationWindowSeconds"], 65.0)
        self.assertEqual((result["coldPasses"], result["warmPasses"]), (1, 1))
        self.assertEqual(result["firstIterationBegin"], report["cells"][0]["route"]["iterationClock"]["begin"])
        self.assertEqual(result["lastIterationEnd"], report["cells"][1]["route"]["iterationClock"]["end"])
        self.assertFalse(result["serverNavigationCertified"])
        self.assertFalse(result["osStorageCacheColdCertified"])

    def test_selector_bounds_canonical_form_and_letter_rollover(self):
        self.assertEqual(soak_ids("route-soak-2"), ["traversal-southern-soak-aa", "traversal-southern-soak-ab"])
        maximum = soak_ids("route-soak-32")
        self.assertEqual(len(maximum), 32)
        self.assertEqual(maximum[25:27], ["traversal-southern-soak-az", "traversal-southern-soak-ba"])
        self.assertEqual(maximum[-1], "traversal-southern-soak-bf")
        for selector in ("route-soak-1", "route-soak-33", "route-soak-02", "route-soak-2.0", "route-soak-", "route-soak-two"):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                soak_ids(selector)
        self.assertIsNone(validate_soak({}, "empty"))
        with self.assertRaises(ValueError):
            validate_soak(fixture(), "route-soak-3")

    def test_duplicate_reordered_truncated_or_nonobject_iterations_rejected(self):
        variants = []
        for replacement in ([], fixture()["cells"][:1], list(reversed(fixture()["cells"])),
                            [fixture()["cells"][0], fixture()["cells"][0]], [None, None], {}):
            report = fixture()
            report["cells"] = replacement
            variants.append(report)
        for report in variants:
            with self.subTest(cells=report["cells"]), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")

    def test_pid_main_restart_and_invalid_owner_rejected(self):
        for key in ("pid", "mainInstanceId"):
            for value in (12345, 0, True):
                report = fixture()
                report["cells"][1]["route"]["iterationClock"][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_soak(report, "route-soak-2")

    def test_missing_misnumbered_visit_or_planned_count_witness_rejected(self):
        for key, value in (("index", 0), ("plannedIterations", 3), ("visit", "cold"), ("begin", None)):
            report = fixture()
            report["cells"][1]["route"]["iterationClock"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")
        for location in ("route", "iterationClock"):
            report = fixture()
            if location == "route":
                report["cells"][1]["route"] = None
            else:
                report["cells"][1]["route"].pop("iterationClock")
            with self.subTest(location=location), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")

    def test_monotonic_overlap_zero_duration_and_wall_clock_regression_rejected(self):
        changes = ((0, "end", "ticksUsec", 10_000_000),
                   (1, "begin", "ticksUsec", 39_999_999),
                   (0, "end", "unixTime", 1_699_999_999.0),
                   (1, "begin", "unixTime", 1_700_000_029.0))
        for index, boundary, key, value in changes:
            report = fixture()
            report["cells"][index]["route"]["iterationClock"][boundary][key] = value
            with self.subTest(change=(index, boundary, key)), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")

    def test_nonfinite_negative_boolean_or_fractional_clock_rejected(self):
        changes = (("ticksUsec", 10_000_000.5), ("ticksUsec", True), ("ticksUsec", -1),
                   ("unixTime", math.nan), ("unixTime", math.inf), ("unixTime", True), ("unixTime", -1))
        for key, value in changes:
            report = fixture()
            report["cells"][0]["route"]["iterationClock"]["begin"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")

    def test_leg_count_identity_order_success_and_readiness_rejected(self):
        good = fixture()["cells"][0]["route"]["legs"]
        variants = (good[:-1], good + [copy.deepcopy(good[-1])], list(reversed(good)),
                    [copy.deepcopy(good[0])] * 6, [None] * 6)
        for legs in variants:
            report = fixture()
            report["cells"][1]["route"]["legs"] = legs
            with self.subTest(legs=legs), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")
        for key in ("success", "readiness"):
            report = fixture()
            report["cells"][1]["route"]["legs"][2][key] = False if key == "success" else {"ready": False}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")

    def test_incomplete_iteration_and_each_cleanup_boundary_rejected(self):
        for key, value in (("status", "failed"), ("readiness", {"ready": False})):
            report = fixture()
            report["cells"][1][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")
        for key in ("ready", "ownedSubtreeDisabledAfterDrain", "ownedInstrumentationDisconnected",
                    "beforeUnload", "afterUnload", "afterMainFree"):
            report = fixture()
            report["teardown"][key] = False if key in ("ready", "ownedSubtreeDisabledAfterDrain", "ownedInstrumentationDisconnected") else {"ready": False}
            with self.subTest(cleanup=key), self.assertRaises(ValueError):
                validate_soak(report, "route-soak-2")


if __name__ == "__main__":
    unittest.main()
