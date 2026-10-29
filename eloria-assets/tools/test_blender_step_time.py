import numpy as np
import pytest

from video_motion.blender_step_time import step_safe_frame


def test_query_before_step_stays_before_rounded_imported_key():
    key = float(np.float32(11 / 24))
    frame, report = step_safe_frame(11 / 24, 240, [[0, key, 1]])
    assert frame == float(np.nextafter(np.float32(110), np.float32(-np.inf)))
    assert report["requested_time"] == 11 / 24
    assert report["step_intervals"][0]["source_next_time"] == key
    assert report["time_displacement"] < 0


def test_authored_key_uses_new_value_without_nudge():
    key = float(np.float32(11 / 24))
    frame, report = step_safe_frame(key, 240, [[0, key, 1]])
    assert frame == key * 240
    assert report is None


def test_ordinary_queries_and_linear_clips_unchanged():
    assert step_safe_frame(0.3, 240, [[0, 0.5, 1]]) == (72, None)
    assert step_safe_frame(0.3, 240, []) == (72, None)
    assert step_safe_frame(-0.1, 240, [[0, 0.5, 1]]) == (-24, None)


def test_unrepresentable_distinct_steps_are_rejected():
    with pytest.raises(ValueError, match="collapse"):
        step_safe_frame(0.500000001, 240, [[0, 0.5, 0.500000002, 1]])


def test_imported_constant_key_snapping_uses_nearest_proven_query():
    evaluate = lambda frame: (0 if frame < 119.9999 else 1,)
    frame, report = step_safe_frame(0.5 - 1e-9, 240, [[0, 0.5, 1]], evaluate)
    assert evaluate(frame) == (0,)
    assert evaluate(float(np.nextafter(np.float32(frame), np.float32(np.inf)))) == (1,)
    assert report["requested_time"] == 0.5 - 1e-9
    assert report["imported_constant_curve_proof"]["constant_curve_values"] == [0]


def test_overlapping_step_samplers_keep_common_interval():
    frame, report = step_safe_frame(
        0.49,
        240,
        [[0, 0.5, 1], [0, 0.4, 0.6, 1]],
        lambda value: (1 if value >= 96 else 0,),
    )
    assert frame == 0.49 * 240
    assert report is None
