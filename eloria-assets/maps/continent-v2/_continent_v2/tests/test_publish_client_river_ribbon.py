"""_continent_v2/publish_client.py river_ribbon_faces: a river path's Water_ ribbon, one mitred section per point.

The ribbon used to be one quad per segment, each squared to its own segment: at every bend the quads overlapped on
the inside and left a wedge open on the outside. Under the soft-edged water (map polish round 4, 2026-11-16)
Twinbrook's brook drew the overlaps as stripes and pale chips and the wedges as dry spikes across the stream. Every
point now carries one section that both quads meeting there share. These cases pin that down on synthetic paths
sampled like the editor's snapshot_points (about every metre, with each corner inserted, so a corner often sits a
few centimetres from a regular sample):
  - a straight path keeps exactly the old geometry (square sections, same winding);
  - on bends the faces neither overlap (the summed triangle area is the union's) nor leave a gap (the union is the
    centreline's mitred buffer), every quad is convex and turns like a straight one, and the old per-segment
    ribbon of the same path shows both defects;
  - a bend tighter than the ribbon is wide (legs shorter than the mitre's setback, coincident points) is cut at
    its inner corner and covers its buffer once; a sharp bend that also widens (Twinbrook's castle-brook-east,
    its own points) fans its inner half-sections instead of crossing them; an out-and-back path stays finite;
  - widths and surface heights stay those of each point, and the publisher's river loop builds from this function.

    python -m pytest eloria-assets/maps/continent-v2/_continent_v2/tests/test_publish_client_river_ribbon.py -q
"""
from __future__ import annotations

import inspect
import math
from pathlib import Path
import sys

import numpy as np
import pytest

shapely = pytest.importorskip("shapely")
from shapely.geometry import LineString, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2))
import publish_client as PC  # noqa: E402


def old_ribbon_faces(pts, widths):
    """The publisher's river loop before 2026-11-16 (one quad per segment, squared to it), for comparison."""
    pts = np.asarray(pts, float)
    faces = []
    for i in range(len(pts) - 1):
        d = pts[i + 1][[0, 2]] - pts[i][[0, 2]]
        length = np.linalg.norm(d)
        if length < 1e-6:
            continue
        side = np.array([-d[1], d[0]]) / length
        l0 = pts[i].copy(); r0 = pts[i].copy(); l1 = pts[i + 1].copy(); r1 = pts[i + 1].copy()
        l0[[0, 2]] += side * widths[i] / 2; r0[[0, 2]] -= side * widths[i] / 2
        l1[[0, 2]] += side * widths[i + 1] / 2; r1[[0, 2]] -= side * widths[i + 1] / 2
        faces += [np.array([l0, r0, l1]), np.array([r0, r1, l1])]
    return np.asarray(faces).reshape(-1, 3, 3)


def sampled(corners, step=1.0, surface=10.0, fall=0.0):
    """A polyline through `corners` (x, z) sampled every `step` metres along each leg, every corner kept: the
    editor's snapshot_points. y falls by `fall` metres per metre from `surface`."""
    corners = np.asarray(corners, float)
    out = [corners[0]]
    for a, b in zip(corners[:-1], corners[1:]):
        length = float(np.hypot(*(b - a)))
        for t in np.arange(step, length, step) / length:
            out.append(a + (b - a) * t)
        out.append(b)
    xz = np.asarray(out)
    along = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xz, axis=0).T))]
    return np.c_[xz[:, 0], surface - fall * along, xz[:, 1]]


def polygons(faces):
    return [Polygon(f[:, [0, 2]]) for f in faces if Polygon(f[:, [0, 2]]).area > 1e-12]


def overlap_area(faces):
    polys = polygons(faces)
    return sum(p.area for p in polys) - unary_union(polys).area


def union(faces):
    return unary_union(polygons(faces))


def buffer(pts, half):
    return LineString(np.asarray(pts)[:, [0, 2]]).buffer(half, cap_style="flat", join_style="mitre", mitre_limit=5.0)


def signed_areas(faces):
    a, b, c = faces[:, 0][:, [0, 2]], faces[:, 1][:, [0, 2]], faces[:, 2][:, [0, 2]]
    u, v = b - a, c - a
    return (u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]) / 2


def assert_convex_quads(faces):
    """Each pair of faces is the quad l_k, r_k, r_k+1, l_k+1; every corner turns the way a straight quad's do."""
    left0, right0, left1 = faces[0::2, 0], faces[0::2, 1], faces[0::2, 2]
    right1 = faces[1::2, 1]
    quad = np.stack([left0, right0, right1, left1], axis=1)[:, :, [0, 2]]
    edge = np.roll(quad, -1, axis=1) - quad
    nxt = np.roll(edge, -1, axis=1)
    corner = edge[:, :, 0] * nxt[:, :, 1] - edge[:, :, 1] * nxt[:, :, 0]
    assert (corner > -1e-9).all(), f"{int((corner <= -1e-9).any(axis=1).sum())} quads fold"
    assert (signed_areas(faces) > -1e-12).all()


def test_a_straight_path_keeps_the_old_ribbon():
    pts = sampled([(0.0, 0.0), (23.4, 9.1)], fall=0.05)
    widths = np.linspace(4.0, 7.0, len(pts))
    new, old = PC.river_ribbon_faces(pts, widths), old_ribbon_faces(pts, widths)
    assert new.shape == old.shape
    assert np.allclose(new, old, atol=1e-9)
    assert (signed_areas(new) > 0).all(), "the old winding: put_water's upward test sees the same faces"


@pytest.mark.parametrize("turn", [8.0, 22.0, 45.0, 90.0])
def test_a_bend_is_mitred_without_gap_or_overlap(turn):
    angle = math.radians(turn)
    corner = (20.3, 0.0)
    end = (corner[0] + 20.0 * math.cos(angle), 20.0 * math.sin(angle))
    pts = sampled([(0.0, 0.0), corner, end], fall=0.02)
    half = 5.0
    widths = np.full(len(pts), 2 * half)
    new = PC.river_ribbon_faces(pts, widths)
    assert_convex_quads(new)
    assert overlap_area(new) < 1e-6
    footprint = buffer(pts, half)
    assert union(new).symmetric_difference(footprint).area < 1e-6 * footprint.area, \
        "the ribbon is the centreline's mitred buffer: no wedge open on the outside, nothing past the inside"
    old = old_ribbon_faces(pts, widths)
    gap = footprint.difference(union(old)).area
    assert overlap_area(old) > 0.5 * half * half * math.tan(angle / 2) and gap > 0.1, \
        "the old per-segment quads overlap inside the bend and leave its outside open"


def test_a_brook_of_many_small_turns_has_no_stripes():
    # Twinbrook's castle-brook-west pool: a curve drawn as many short legs, 8-10 m wide, a few degrees per point.
    theta = np.radians(np.linspace(0.0, 150.0, 40))
    corners = np.c_[14.0 * np.sin(theta), 14.0 * (1 - np.cos(theta))]
    pts = sampled(corners, step=0.7, fall=0.01)
    widths = np.interp(np.arange(len(pts)), [0, len(pts) - 1], [8.0, 10.3])
    new, old = PC.river_ribbon_faces(pts, widths), old_ribbon_faces(pts, widths)
    assert_convex_quads(new)
    assert overlap_area(new) < 1e-6
    stripes = union(new).difference(union(old)).area
    assert overlap_area(old) > 1.0 and stripes > 1.0, "the old ribbon's overlaps and wedges this case stands for"


@pytest.mark.parametrize("corners,half", [
    ([(0.0, 0.0), (12.0, 0.0), (12.4, 0.5), (3.0, 7.0)], 4.0),        # 145 degrees in two corners 0.6 m apart
    ([(0.0, 0.0), (6.0, 0.0), (6.0, 0.0), (6.0, 0.0005), (6.0, 7.0)], 3.0),   # coincident points at a corner
])
def test_a_bend_tighter_than_the_ribbon_is_cut_at_its_inner_corner(corners, half):
    # The legs come closer than the ribbon is wide: the inner edges of both legs run over each other, and the old
    # quads overlapped by tens of square metres. The cut ribbon covers the buffer once.
    pts = sampled(corners, step=0.9)
    widths = np.full(len(pts), 2 * half)
    new = PC.river_ribbon_faces(pts, widths)
    assert len(new) and np.isfinite(new).all()
    assert_convex_quads(new)
    assert overlap_area(new) < 1e-6
    footprint = buffer(pts, half)
    assert footprint.difference(union(new)).area < 1e-6 * footprint.area
    assert union(new).difference(footprint).area < 1e-3 * footprint.area, "at most the capped mitre's sliver"


# Twinbrook's castle-brook-east, points 18-30 of the polish bake (x, z, width): a 27 degree corner at point 27 with
# legs of 0.45 and 0.52 m, the ribbon widening from 9.3 to 13.9 m through it.
CASTLE_BROOK_EAST = [(-70.8, 123.6, 9.3), (-70.85, 122.91, 9.61), (-70.93, 121.96, 10.04), (-71.0, 121.01, 10.46),
                     (-71.07, 120.05, 10.89), (-71.15, 119.1, 11.32), (-71.22, 118.15, 11.75),
                     (-71.29, 117.2, 12.17), (-71.37, 116.25, 12.6), (-71.4, 115.8, 12.8), (-71.68, 115.35, 13.03),
                     (-72.19, 114.53, 13.47), (-72.7, 113.7, 13.9)]


def test_widths_that_change_through_a_sharp_bend_do_not_overlap():
    # The inner edge folds back there without crossing itself; the half-sections fan round the last edge point
    # before the fold instead of crossing the ones before them.
    rows = np.asarray(CASTLE_BROOK_EAST)
    pts = np.c_[rows[:, 0], np.full(len(rows), 150.0), rows[:, 1]]
    new, old = PC.river_ribbon_faces(pts, rows[:, 2]), old_ribbon_faces(pts, rows[:, 2])
    assert_convex_quads(new)
    assert overlap_area(new) < 1e-6 and overlap_area(old) > 1.0
    assert union(old).difference(union(new)).area < 0.01 * union(old).area, "the fan leaves out only a sliver"


def test_an_out_and_back_path_stays_finite():
    # Rivers do not reverse, but a ribbon must not blow up if one does: it lies on itself, as the old one did.
    pts = sampled([(0.0, 0.0), (10.0, 0.0), (0.5, 0.2)], step=0.9)
    new = PC.river_ribbon_faces(pts, np.full(len(pts), 3.0))
    assert new.shape == (2 * (len(pts) - 1), 3, 3) and np.isfinite(new).all()
    assert union(new).difference(buffer(pts, 1.5 * PC.RIVER_MITRE_LIMIT)).area < 1e-6


def test_points_keep_their_width_and_surface():
    pts = sampled([(0.0, 0.0), (10.0, 0.0), (16.0, 6.0)], surface=40.0, fall=0.1)
    widths = np.linspace(3.0, 6.0, len(pts))
    widths[4] = 0.0
    faces = PC.river_ribbon_faces(pts, widths)
    assert_convex_quads(faces)
    left = np.r_[faces[0::2, 0], faces[-2:-1, 2]]
    right = np.r_[faces[0::2, 1], faces[-1:, 1]]
    assert np.allclose(left[:, 1], pts[:, 1]) and np.allclose(right[:, 1], pts[:, 1]), "the water surface is the point's"
    across = np.hypot(*(left - right)[:, [0, 2]].T)
    assert np.allclose(across[4], 0.0)
    assert (across >= widths - 1e-9).all() and (across <= widths * PC.RIVER_MITRE_LIMIT + 1e-9).all()
    assert np.allclose(np.c_[left[:, [0, 2]] + right[:, [0, 2]]] / 2, pts[:, [0, 2]]), "sections are centred"


def test_short_paths_give_no_faces():
    assert PC.river_ribbon_faces(np.zeros((0, 3)), np.zeros(0)).shape == (0, 3, 3)
    assert PC.river_ribbon_faces([[1.0, 2.0, 3.0]], [4.0]).shape == (0, 3, 3)
    assert PC.river_ribbon_faces([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]], [4.0, 4.0]).shape == (0, 3, 3)


def test_the_publisher_builds_its_rivers_from_it():
    source = inspect.getsource(PC.main)
    assert "put_water(river_ribbon_faces(pts, widths))" in source
    assert "side = np.array([-d[1], d[0]]) / length" not in source, "the per-segment quads are gone"
