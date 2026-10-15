"""Tiny pure geometry/encoding fixtures; no World, exporter or output generation."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import shapely as SH
from shapely.geometry import Polygon, box

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import terrain_boundary as B


def square(x0=0., z0=0., size=4.):
    xz = np.array([[x0, z0], [x0 + size, z0], [x0, z0 + size], [x0 + size, z0 + size]])
    return xz, np.array([[0, 2, 1], [1, 2, 3]])


def split_regions(domain, cut):
    return {"a": cut, "b": domain.difference(cut)}


def emitted(partition, owner=None, source=None, xz=None):
    points = partition.vertices if xz is None else xz
    return SH.union_all([Polygon(points[face]) for i, face in enumerate(partition.triangles)
                         if (owner is None or owner == partition.owners[i]) and
                         (source is None or source == partition.source_faces[i])])


def check_certificates(partition):
    for report in partition.report["sourceFaces"].values():
        assert report["missingArea"] <= report["roundoffAreaBound"]
        assert report["extraArea"] <= report["roundoffAreaBound"]
        assert report["overlapArea"] <= report["roundoffAreaBound"]


@pytest.mark.parametrize("slope", [(.75, -1.25), (-.75, 1.25), (0., 0.)])
def test_diagonal_partition_preserves_source_planes_and_shared_recipes(slope):
    xz, faces = square(-2., -1.)
    domain = box(-2., -1., 2., 3.)
    a = Polygon([[-2, -1], [1.25, -1], [-.75, 3], [-2, 3]])
    regions = split_regions(domain, a)
    result = B.partition_triangles(xz, faces, regions=regions, domain=domain)
    assert emitted(result, "a").equals(a)
    assert emitted(result, "b").equals(regions["b"])
    assert emitted(result, "a").intersection(emitted(result, "b")).area == 0.
    assert emitted(result).equals(domain)
    assert all(B._area2(result.vertices[f]) < 0. for f in result.triangles)
    heights = xz[:, 0] * slope[0] + xz[:, 1] * slope[1] + 7.
    interpolated = B.interpolate(result, heights)
    np.testing.assert_allclose(interpolated, result.vertices[:, 0] * slope[0] + result.vertices[:, 1] * slope[1] + 7., atol=2e-14, rtol=0)
    encoded = B.encode_positions(result, np.c_[xz[:, 0], heights, xz[:, 1]])
    assert encoded.positions.dtype == np.float32
    seam_a = {int(v) for i, f in enumerate(result.triangles) if result.owners[i] == "a" for v in f}
    seam_b = {int(v) for i, f in enumerate(result.triangles) if result.owners[i] == "b" for v in f}
    common = seam_a & seam_b
    assert len(common) >= 3
    assert any(result.recipes[i].kind == "edge" for i in common)
    # Compaction by either owner copies the exact shared encoding, not a second
    # interpolation of reversed endpoints.
    copies = []
    for indices in (seam_a, seam_b):
        compact_ids = np.asarray(sorted(indices))
        compact = encoded.positions[compact_ids].copy()
        copies.append({int(index): compact[at].tobytes() for at, index in enumerate(compact_ids)})
    for i in common:
        assert copies[0][i] == copies[1][i]
    check_certificates(result)


def test_original_diagonal_is_interpolation_authority_not_bilinear_resampling():
    xz, faces = square(size=2.)
    domain = box(0, 0, 2, 2)
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, box(0, 0, .5, 2)))
    # Non-coplanar quad: changing its diagonal or bilinearly sampling would alter
    # the height at (.5, 1.5), which lies on the original shared diagonal.
    values = np.array([0., 2., -2., 100.])
    samples = B.interpolate(result, values)
    index = next(i for i, p in enumerate(result.vertices) if tuple(p) == (.5, 1.5))
    assert samples[index] == -1.
    assert result.recipes[index].kind == "edge"
    for i, face in enumerate(result.triangles):
        source = faces[int(result.source_faces[i])]
        source_matrix = np.c_[xz[source], np.ones(3)]
        plane = np.linalg.solve(source_matrix, values[source])
        np.testing.assert_allclose(samples[face], np.c_[result.vertices[face], np.ones(3)] @ plane, atol=1e-13)


def test_interior_preserves_original_topology_attributes_and_inputs():
    xz = np.array([[1., 1.], [2., 3.], [3., 1.], [99., 99.]])
    faces = np.array([[2, 0, 1]])
    attrs = np.array([[.1, .2, .3, 1.], [.3, .9, .1, .4], [.8, .6, .4, .5], [.1, .1, .1, .1]])
    before = [a.tobytes() for a in (xz, faces, attrs)]
    xz.setflags(write=False)
    faces.setflags(write=False)
    attrs.setflags(write=False)
    result = B.partition_triangles(xz, faces, regions={"only": box(0, 0, 4, 4)})
    np.testing.assert_array_equal(result.vertices, xz)
    np.testing.assert_array_equal(result.triangles, faces)
    np.testing.assert_array_equal(B.interpolate(result, attrs), attrs)
    assert result.report["interiorTriangles"] == 1
    assert result.report["boundaryTriangles"] == 0
    assert before == [a.tobytes() for a in (xz, faces, attrs)]
    assert not result.vertices.flags.writeable and not result.triangles.flags.writeable


def test_uv_color_and_vector_recipes_preserve_affine_fields_and_byte_error_bound():
    xz, faces = square()
    domain = box(0, 0, 4, 4)
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, box(0, 0, 1.1, 4)))
    # Affine rotated/translated UVs and an arbitrary three-component field.
    uv = xz @ np.array([[.3, -.7], [.7, .3]]) + [4., -2.]
    np.testing.assert_allclose(B.interpolate(result, uv), result.vertices @ np.array([[.3, -.7], [.7, .3]]) + [4., -2.], atol=2e-15)
    vectors = np.c_[xz[:, 0] * .5, np.ones(4), xz[:, 1] * -.2]
    np.testing.assert_allclose(B.interpolate(result, vectors), np.c_[result.vertices[:, 0] * .5, np.ones(len(result.vertices)), result.vertices[:, 1] * -.2], atol=1e-15)
    byte_colors = np.array([[0, 0, 30, 255], [255, 0, 80, 10], [0, 255, 110, 120], [255, 255, 170, 200]], np.uint8)
    linear = B.interpolate(result, byte_colors.astype(float) / 255.)
    encoded = np.rint(linear * 255.).astype(np.uint8)
    np.testing.assert_array_equal(encoded[:4], byte_colors)
    assert np.max(np.abs(encoded.astype(float) / 255. - linear)) <= .5 / 255. + 1e-15


def test_concave_disconnected_intersections_and_hole_are_all_retained():
    # This source triangle intersects the two arms of a U but not its connector.
    xz = np.array([[0., 2.], [4., 2.], [2., 4.]])
    faces = np.array([[0, 2, 1]])
    domain = box(0, 0, 4, 4)
    u = Polygon([(0, 0), (4, 0), (4, 4), (3, 4), (3, 1), (1, 1), (1, 4), (0, 4)])
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, u), domain=domain)
    expected = u.intersection(Polygon(xz))
    assert expected.geom_type == "MultiPolygon"
    assert emitted(result, "a").equals(expected)
    check_certificates(result)
    xz, faces = square()
    inner = box(1.2, 1.1, 1.4, 1.3)
    ring = domain.difference(inner)
    assert len(ring.interiors) == 1
    result = B.partition_triangles(xz, faces, regions={"ring": ring, "tiny": inner})
    assert emitted(result, "tiny").equals(inner)
    assert emitted(result, "ring").equals(ring)
    assert "tiny" in result.owners  # no source triangle center is inside it


@pytest.mark.parametrize("cut", [
    Polygon([(0, 0), (4, 0), (0, 4)]),  # exact source diagonal
    Polygon([(0, 0), (2, 0), (2, 1), (2, 2), (2, 4), (0, 4)]),  # collinear nodes
    Polygon([(0, 0), (4, 0), (4, 4)]),  # through source vertices
])
def test_boundary_on_source_edges_vertices_and_collinear_nodes(cut):
    xz, faces = square()
    domain = box(0, 0, 4, 4)
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, cut))
    assert emitted(result, "a").equals(cut)
    used = {tuple(result.vertices[v]) for f in result.triangles for v in f}
    assert set(map(tuple, list(cut.exterior.coords)[:-1])).issubset(used)
    assert all(B._area2(result.vertices[f]) < 0. for f in result.triangles)
    B.encode_positions(result, np.c_[xz[:, 0], xz[:, 0] - xz[:, 1], xz[:, 1]])


def test_three_region_meeting_and_zero_dimensional_contacts():
    xz, faces = square()
    regions = {"left": box(0, 0, 2, 4), "bottom": box(2, 0, 4, 2), "top": box(2, 2, 4, 4)}
    result = B.partition_triangles(xz, faces, regions=regions)
    center = [i for i, p in enumerate(result.vertices) if tuple(p) == (2., 2.)]
    assert len(center) == 1
    owners = {result.owners[i] for i, f in enumerate(result.triangles) if center[0] in f}
    assert owners == set(regions)
    for name, region in regions.items():
        assert emitted(result, name).equals(region)
    check_certificates(result)


def test_collinear_constrained_node_is_reinserted_if_cdt_omits_it(monkeypatch):
    polygon = Polygon([(0, 0), (1, 0), (3, 0), (4, 0), (4, 4), (0, 4)])
    triangulate = B.SH.constrained_delaunay_triangles
    monkeypatch.setattr(B.SH, "constrained_delaunay_triangles", lambda _polygon: triangulate(box(0, 0, 4, 4)))
    faces = B._triangulate(polygon)
    used = {p for face in faces for p in face}
    assert {(1., 0.), (3., 0.)}.issubset(used)
    assert SH.union_all([Polygon(face) for face in faces]).equals(polygon)
    assert sum(Polygon(face).area for face in faces) == polygon.area


def test_positive_xz_source_winding_is_preserved_too():
    xz, faces = square()
    domain = box(0, 0, 4, 4)
    result = B.partition_triangles(xz, faces[:, ::-1], regions=split_regions(domain, box(0, 0, 1.25, 4)))
    assert all(B._area2(result.vertices[face]) > 0 for face in result.triangles)
    B.encode_positions(result, np.c_[xz[:, 0], xz[:, 0] * .5, xz[:, 1]])


def test_deterministic_region_face_and_ring_order_with_stable_source_keys():
    xz, faces = square()
    domain = box(0, 0, 4, 4)
    regions = split_regions(domain, Polygon([(0, 0), (3.5, 0), (.3, 4), (0, 4)]))
    one = B.partition_triangles(xz, faces, regions=regions, source_face_keys=["south", "north"])
    reversed_regions = {name: SH.reverse(regions[name]) for name in reversed(regions)}
    two = B.partition_triangles(xz, faces[::-1], regions=reversed_regions, source_face_keys=["north", "south"])
    three = B.partition_triangles(xz, faces, regions=regions, source_face_keys=["south", "north"])
    for other in (two, three):
        assert one.vertices.tobytes() == other.vertices.tobytes()
        assert one.triangles.tobytes() == other.triangles.tobytes()
        assert one.owners == other.owners and one.source_faces == other.source_faces
        assert one.recipes == other.recipes


def test_actual_384_vertex_four_gates_polygon_without_circle_approximation():
    path = HERE / "ownership/user-boundary-redesign-v4-topology-correction-v1.json"
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "98e48012e95815957437f26dedbc66f9394dd5538ff7a318e9b945c1f05b011f"
    document = json.loads(data)
    original = copy.deepcopy(document)
    ring = document["regions"]["four_gates"]["ownershipPolygon"]
    assert len(ring) == 384
    circle = Polygon(ring)
    domain = box(300, 601, 742, 1041)
    xz = np.array([[300., 601.], [742., 601.], [300., 1041.], [742., 1041.]])
    faces = np.array([[0, 2, 1], [1, 2, 3]])
    result = B.partition_triangles(xz, faces, regions={"four_gates": circle, "outside": domain.difference(circle)}, domain=domain)
    actual = emitted(result, "four_gates")
    assert actual.symmetric_difference(circle).area <= B._audit_tolerance(circle)
    used = {tuple(result.vertices[v]) for i, f in enumerate(result.triangles) if result.owners[i] == "four_gates" for v in f}
    assert set(map(tuple, ring)).issubset(used)
    # Every canonical segment is covered by the actual boundary, with no replaced
    # circle, raster staircase, deleted collinear vertex or changed metadata.
    assert actual.boundary.hausdorff_distance(circle.boundary) < 1e-10
    assert document == original and path.read_bytes() == data
    heights = .02 * xz[:, 0] - .03 * xz[:, 1]
    encoded = B.encode_positions(result, np.c_[xz[:, 0], heights, xz[:, 1]])
    assert max(encoded.report["maxPositionError"][0::2]) <= .00006103515625
    check_certificates(result)


def test_positive_sliver_is_kept_but_float32_collapse_is_a_hard_failure():
    xz, faces = square(1000., 1000., 2.)
    domain = box(1000, 1000, 1002, 1002)
    sliver = box(1000, 1000, 1000.0000001, 1002)
    result = B.partition_triangles(xz, faces, regions={"sliver": sliver, "rest": domain.difference(sliver)})
    assert emitted(result, "sliver").area > 0.
    np.testing.assert_allclose(emitted(result, "sliver").area, sliver.area, rtol=1e-12)
    with pytest.raises(B.BoundaryError, match="collapsed or reversed") as failure:
        B.encode_positions(result, np.c_[xz[:, 0], xz[:, 0] * -.3, xz[:, 1]])
    assert "sourceFace" in failure.value.details and "owner" in failure.value.details


def test_float32_restored_world_seams_use_ulp_derived_bounds():
    xz, faces = square(519.1, 819.1, 4.)
    domain = box(519.1, 819.1, 523.1, 823.1)
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, box(519.1, 819.1, 520.123456, 823.1)))
    source = np.c_[xz[:, 0], xz[:, 0] * .03, xz[:, 1]]
    encoded = B.encode_positions(result, source)
    center_a = np.array([530., 0., 840.])
    center_b = np.array([1074., 0., 251.])
    a = (encoded.positions - center_a.astype(np.float32)).astype(np.float32) + center_a.astype(np.float32)
    b = (encoded.positions - center_b.astype(np.float32)).astype(np.float32) + center_b.astype(np.float32)
    bound = B.float32_translation_bound(encoded.positions, center_a) + B.float32_translation_bound(encoded.positions, center_b)
    assert np.all(np.abs(a.astype(float) - b.astype(float)) <= bound)
    assert np.max(bound[:, [0, 2]]) < .0005
    np.testing.assert_array_equal(center_a, [530., 0., 840.])
    np.testing.assert_array_equal(center_b, [1074., 0., 251.])


@pytest.mark.parametrize("regions, domain, message", [
    ({"a": box(0, 0, 3, 4), "b": box(2, 0, 4, 4)}, box(0, 0, 4, 4), "coverage or overlap"),
    ({"a": box(0, 0, 1, 4), "b": box(2, 0, 4, 4)}, box(0, 0, 4, 4), "coverage or overlap"),
    ({"a": box(0, 0, 3, 4)}, None, "outside canonical domain"),
])
def test_invalid_coverage_overlap_and_outside_domain_have_diagnostics(regions, domain, message):
    xz, faces = square()
    with pytest.raises(B.BoundaryError, match=message) as failure:
        B.partition_triangles(xz, faces, regions=regions, domain=domain)
    assert failure.value.details
    assert any(value > 0 for name, value in failure.value.details.items() if name.endswith("Area"))


def test_missing_stencil_and_changed_source_positions_never_clamp():
    xz, faces = square()
    with pytest.raises(B.BoundaryError, match="missing source stencil"):
        B.partition_triangles(xz[:3], faces, regions={"all": box(0, 0, 4, 4)})
    result = B.partition_triangles(xz, faces, regions={"all": box(0, 0, 4, 4)})
    with pytest.raises(B.BoundaryError, match="attribute stencil"):
        B.interpolate(result, [1., 2.])
    changed = np.c_[xz[:, 0], np.zeros(4), xz[:, 1]]
    changed[0, 0] += .1
    with pytest.raises(B.BoundaryError, match="XZ changed"):
        B.encode_positions(result, changed)


def test_invalid_input_shapes_numbers_and_identities_fail_before_partition():
    xz, faces = square()
    regions = {"all": box(0, 0, 4, 4)}
    invalid = xz.copy()
    invalid[1, 0] = np.nan
    with pytest.raises(B.BoundaryError, match="finite Nx2"):
        B.partition_triangles(invalid, faces, regions=regions)
    with pytest.raises(B.BoundaryError, match="integer Nx3"):
        B.partition_triangles(xz, faces.astype(float), regions=regions)
    with pytest.raises(B.BoundaryError, match="unique nonempty"):
        B.partition_triangles(xz, faces, regions=regions, source_face_keys=["duplicate", "duplicate"])
    with pytest.raises(B.BoundaryError, match="degenerate source triangle"):
        B.partition_triangles(xz, np.array([[0, 0, 1]]), regions=regions)
    with pytest.raises(B.BoundaryError, match="invalid canonical polygon"):
        B.partition_triangles(xz, faces, regions={"bowtie": Polygon([(0, 0), (4, 4), (0, 4), (4, 0)])})


def test_overlapping_source_surfaces_keep_distinct_height_provenance():
    # The same XZ triangle at two heights is an intentional source-layer overlap,
    # not a territorial overlap. Never merge unrelated attribute stencils.
    points = np.array([[0., 0.], [0., 4.], [4., 0.]])
    xz = np.vstack([points, points])
    faces = np.array([[0, 1, 2], [3, 4, 5]])
    domain = Polygon(points)
    left = domain.intersection(box(0, 0, 1, 4))
    result = B.partition_triangles(xz, faces, regions=split_regions(domain, left), source_face_keys=["lower", "upper"])
    heights = B.interpolate(result, [0., 0., 0., 10., 10., 10.])
    for i, face in enumerate(result.triangles):
        np.testing.assert_array_equal(heights[face], [0.] * 3 if result.source_faces[i] == "lower" else [10.] * 3)
    check_certificates(result)
