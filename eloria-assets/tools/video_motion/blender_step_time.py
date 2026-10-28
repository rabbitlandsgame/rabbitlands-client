"""Keep a Blender float32 frame query on its authored glTF STEP interval."""

import numpy as np


def step_safe_frame(time, fps, samplers, evaluate=None):
    requested = float(time) * fps
    frame = requested
    intervals = []
    lower, upper = -np.inf, np.inf
    for values in samplers:
        times = np.asarray(values, dtype=float).reshape(-1)
        index = max(0, int(np.searchsorted(times, time, side="right")) - 1)
        first = float(np.float32(times[index] * fps))
        following = (
            float(np.float32(times[index + 1] * fps))
            if index + 1 < len(times)
            else np.inf
        )
        # glTF clamps to its first value before the first key.
        lower = max(lower, first if time >= times[0] else -np.inf)
        upper = min(upper, following)
        intervals.append(
            {
                "source_key_time": float(times[index]),
                "source_next_time": (
                    float(times[index + 1]) if index + 1 < len(times) else None
                ),
                "imported_frame_lower": first,
                "imported_frame_upper": following if np.isfinite(following) else None,
            }
        )
    if lower >= upper:
        raise ValueError("Distinct source STEP intervals collapse to one Blender frame")
    if float(np.float32(frame)) < lower:
        frame = lower
    if float(np.float32(frame)) >= upper:
        frame = float(np.nextafter(np.float32(upper), np.float32(-np.inf)))
    curve_proof = None
    if samplers and evaluate is not None:
        interior = (
            (lower + upper) / 2
            if np.isfinite(lower) and np.isfinite(upper)
            else (
                max(frame, lower) + 1
                if np.isfinite(lower)
                else min(frame, upper) - 1 if np.isfinite(upper) else frame
            )
        )
        interior = float(np.float32(interior))
        if not lower <= interior < upper:
            raise ValueError("No representable interior of source STEP intersection")
        expected = tuple(evaluate(interior))
        if not expected:
            raise ValueError("Source STEP animation has no imported CONSTANT curves")
        actual = tuple(evaluate(frame))
        if actual != expected:
            bad, good = float(np.float32(frame)), interior
            # Find the nearest representable frame whose imported CONSTANT
            # evaluation has the same value as the original STEP interval.
            for _ in range(64):
                adjacent = float(np.nextafter(np.float32(bad), np.float32(good)))
                if adjacent == good:
                    break
                middle = float(np.float32((bad + good) / 2))
                if middle == bad or middle == good:
                    raise ValueError("Could not resolve imported STEP query boundary")
                if tuple(evaluate(middle)) == expected:
                    good = middle
                else:
                    bad = middle
            else:
                raise ValueError("Imported STEP correspondence search did not converge")
            frame = good
            if not lower <= frame < upper or tuple(evaluate(frame)) != expected:
                raise ValueError("Imported STEP query left the source interval")
            curve_proof = {
                "interior_reference_frame": interior,
                "constant_curve_values": list(expected),
                "nearest_rejected_frame": bad,
                "nearest_rejected_values": list(evaluate(bad)),
            }
    if frame == requested:
        return frame, None
    budget = 2 * float(np.spacing(np.float32(max(1, abs(requested)))))
    if abs(frame - requested) > budget and curve_proof is None:
        raise ValueError("STEP interval correspondence needs more than frame roundoff")
    return frame, {
        "requested_time": float(time),
        "requested_frame": requested,
        "effective_frame": frame,
        "time_displacement": (frame - requested) / fps,
        "frame_roundoff_budget": budget,
        "step_intervals": intervals,
        "imported_constant_curve_proof": curve_proof,
    }
