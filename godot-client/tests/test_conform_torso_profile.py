"""The generated torso fit measures the lining and preserves solid shells."""
from pathlib import Path
import sys

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "eloria-assets/tools"
sys.path.insert(0, str(TOOLS))
import conform_equipment as ce
import equipment_authoring as ea


def _tube():
    # A hollow solid with separate inner/outer walls and closed end rims.
    # Rays from the wearing cavity cross TWO walls, not an odd number.
    heights = np.linspace(ea.TORSO_HEM, ea.COLLAR_TOP, 27)
    sides = 32
    points = []
    for width, depth in ((.12, .12), (.135, .135)):
        for y in heights:
            for angle in np.arange(sides) * (2 * np.pi / sides):
                points.append((width * np.cos(angle), y,
                               -.035 + depth * np.sin(angle)))
    layer = len(heights) * sides
    faces = []
    for offset in (0, layer):
        for row in range(len(heights) - 1):
            for side in range(sides):
                a = offset + row * sides + side
                b = offset + row * sides + (side + 1) % sides
                faces.extend(((a, b, b + sides), (a, b + sides, a + sides)))
        if offset == 0:
            faces = [f[::-1] for f in faces]
    for row in (0, len(heights) - 1):
        for side in range(sides):
            a = row * sides + side
            b = row * sides + (side + 1) % sides
            rim = [(a, a + layer, b + layer), (a, b + layer, b)]
            faces.extend(rim if row == 0 else [f[::-1] for f in rim])
    return np.array(points), np.array(faces)


def _rig():
    return ea.load_rig(ce.RACES / "luminous_male.glb",
                       body_mesh_names=ce.BODY_MESH)


def test_hollow_multishell_torso_grows_to_clear_the_chest():
    rig = _rig()
    points, faces = _tube()
    origin = np.array([0., 1.30, -.035])
    direction = np.array([1., 0., 0.])
    before, crossings = ce.cast(origin, direction, points[faces])
    assert crossings % 2 == 0
    report = ce._fit_trunk_profile(
        points, faces, rig, np.ones(len(points), dtype=bool), ce.CLEARANCE)
    after, _ = ce.cast(origin, direction, points[faces])
    assert before < .13
    assert after > .175
    assert report["bands"] > 10
    # Both walls survive as separate surfaces after widening.
    assert np.linalg.norm(points[len(points) // 2] - points[0]) > .01


def test_short_ornament_moves_rigidly_and_does_not_set_the_girth():
    rig = _rig()
    points, faces = _tube()
    bare = points.copy()
    ce._fit_trunk_profile(bare, faces, rig,
                          np.ones(len(bare), dtype=bool), ce.CLEARANCE)
    # Small tetrahedron outboard of the lining, spanning a steep profile band.
    ornament = np.array([[.40, 1.30, .01], [.42, 1.30, .01],
                         [.40, 1.32, .01], [.40, 1.30, .03]])
    tetra = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
    joined = np.vstack((points, ornament))
    ce._fit_trunk_profile(
        joined, np.vstack((faces, tetra + len(points))), rig,
        np.ones(len(joined), dtype=bool), ce.CLEARANCE)
    np.testing.assert_allclose(joined[:len(points)], bare)
    np.testing.assert_allclose(joined[-4:] - joined[-4],
                               ornament - ornament[0], atol=1e-12)
    assert joined[-4, 0] > ornament[0, 0]


def test_collar_hem_and_exempt_shells_keep_their_seating():
    rig = _rig()
    points, faces = _tube()
    original = points.copy()
    ce._fit_trunk_profile(points, faces, rig,
                          np.ones(len(points), dtype=bool), ce.CLEARANCE)
    ends = (original[:, 1] == ea.TORSO_HEM) | (original[:, 1] == ea.COLLAR_TOP)
    np.testing.assert_array_equal(points[ends], original[ends])
    np.testing.assert_array_equal(points[:, 1], original[:, 1])
    ce._fit_trunk_profile(original, faces, rig,
                          np.zeros(len(original), dtype=bool), ce.CLEARANCE)
    np.testing.assert_array_equal(original, _tube()[0])
