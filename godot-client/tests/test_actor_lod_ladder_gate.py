"""Gate G5 judge of the actor LOD ladder (tests/integration/actor_lod_ladder.py,
actor LODs C5) on synthetic ladder manifests: GO when Compatibility selects
what Forward+ selects and both draw fewer than the plain parse, NO-GO when
Compatibility ignores the chains or a cooked run draws more, INCOMPLETE when
a run is missing, renderer-only pieces (the RL head) judged by selection,
Mobile reported against Forward+, and a run without rows judged instead of
crashing the report."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / "integration" / "actor_lod_ladder.py"
SPEC = importlib.util.spec_from_file_location("actor_lod_ladder_under_test", SCRIPT)
ladder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ladder)

DISTANCES = [4.0, 26.0, 70.0]
PLAIN = [1000, 1000, 1000]
COOKED = [1000, 600, 300]


def rows(primitives: list[int], predicted: list[int] | None = None, pieces: dict | None = None,
         subject: str = "kit_b_human", quality: str = "high") -> list[dict]:
    predicted = primitives if predicted is None else predicted
    return [{"subject": subject, "quality": quality, "distance": d, "primitives": p, "predicted": q,
             "base": 1000, "shadow_primitives": p // 2, "draw_calls": 5, "stable": True,
             "pieces": dict(pieces or {"body": {}})}
            for d, p, q in zip(DISTANCES, primitives, predicted)]


def write_run(out: Path, renderer: str, variant: str, run_rows: list[dict]) -> None:
    folder = out / f"{renderer}__{variant}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps({
        "schema": 1, "renderer": renderer, "variant": variant, "mode": "ladder", "distances": DISTANCES,
        "failures": 0, "rows": run_rows}), encoding="utf-8")


def judge(out: Path) -> tuple[int, dict]:
    with contextlib.redirect_stdout(io.StringIO()):
        code = ladder.gate(out)
    return code, json.loads((out / "gate.json").read_text(encoding="utf-8"))


class LadderGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.out = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def plain_runs(self) -> None:
        for renderer in (ladder.FORWARD, ladder.COMPATIBILITY):
            write_run(self.out, renderer, "off", rows(PLAIN))

    def test_same_selection_and_fewer_primitives_is_go(self) -> None:
        self.plain_runs()
        write_run(self.out, ladder.FORWARD, "px3", rows(COOKED))
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(COOKED))
        code, report = judge(self.out)
        self.assertEqual((code, report["verdict"]), (0, "GO"))
        self.assertEqual(report["variants"]["px3"]["selection_equal"], len(DISTANCES))

    def test_compatibility_ignoring_the_chains_is_no_go(self) -> None:
        self.plain_runs()
        write_run(self.out, ladder.FORWARD, "px3", rows(COOKED))
        # Compatibility draws the base everywhere while the rule predicts the chain.
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(PLAIN, predicted=COOKED))
        code, report = judge(self.out)
        self.assertEqual((code, report["verdict"]), (1, "NO-GO"))
        self.assertEqual(len(report["variants"]["px3"]["selection_differs"]), 2)

    def test_a_cooked_run_drawing_more_than_plain_is_no_go(self) -> None:
        self.plain_runs()
        more = [1000, 1100, 300]
        write_run(self.out, ladder.FORWARD, "px3", rows(more))
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(more))
        code, report = judge(self.out)
        self.assertEqual((code, report["verdict"]), (1, "NO-GO"))
        self.assertTrue(report["variants"]["px3"]["steps"][ladder.FORWARD]["more_anywhere"])

    def test_a_missing_renderer_run_is_incomplete(self) -> None:
        self.plain_runs()
        write_run(self.out, ladder.FORWARD, "px3", rows(COOKED))
        code, report = judge(self.out)
        self.assertEqual((code, report["verdict"]), (2, "INCOMPLETE"))

    def test_renderer_only_pieces_are_judged_by_selection(self) -> None:
        # The RL head is drawn on Forward+ only: totals differ, the residual
        # against each renderer's own prediction does not. The plain parse
        # draws the head too.
        write_run(self.out, ladder.FORWARD, "off", rows([p + 200 for p in PLAIN]))
        write_run(self.out, ladder.COMPATIBILITY, "off", rows(PLAIN))
        head = [p + 200 for p in COOKED]
        write_run(self.out, ladder.FORWARD, "px3", rows(head, pieces={"body": {}, "RLHead": {}}))
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(COOKED, pieces={"body": {}, "eyes": {}}))
        code, report = judge(self.out)
        entry = report["variants"]["px3"]
        self.assertEqual((code, report["verdict"]), (0, "GO"))
        self.assertEqual(entry["same_content_cells"], 0)
        self.assertEqual(len(entry["content_differs"]), 1)

    def test_mobile_is_reported_against_forward_plus(self) -> None:
        self.plain_runs()
        write_run(self.out, ladder.FORWARD, "px3", rows(COOKED))
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(COOKED))
        write_run(self.out, ladder.MOBILE, "px3", rows([1000, 600, 290]))
        code, report = judge(self.out)
        self.assertEqual(code, 0, "Mobile is informational, not part of G5")
        self.assertEqual(report["mobile"]["px3"]["equal"], 2)
        self.assertEqual(report["mobile"]["px3"]["differ"], [["kit_b_human", "high", 70.0]])

    def test_a_run_without_rows_is_judged_not_a_crash(self) -> None:
        self.plain_runs()
        write_run(self.out, ladder.FORWARD, "px3", [])
        write_run(self.out, ladder.COMPATIBILITY, "px3", rows(COOKED))
        code, report = judge(self.out)
        self.assertEqual((code, report["verdict"]), (1, "NO-GO"))


if __name__ == "__main__":
    unittest.main()
