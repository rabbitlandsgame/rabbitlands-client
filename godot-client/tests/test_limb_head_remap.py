"""Original-source fitting preserves shells and the anatomical slot contract."""

from io import BytesIO
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eloria-assets/tools"))
import conform_equipment as ce
import equipment_authoring as ea
import limb_head_remap as remap
import garment_coverage as coverage


def test_two_atlas_samples_produce_a_finite_lining_colour():
    image = Image.new("RGB", (2, 1))
    image.putdata([(10, 30, 10), (220, 230, 200)])
    texture = BytesIO()
    image.save(texture, format="PNG")
    surface = SimpleNamespace(
        positions=np.array([[0.4, 0.0, 0.0], [0.4, 0.1, 0.0], [0.0, 1.0, 0.0]]),
        uvs=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]),
    )
    colour = remap.torso_remap.backing_colour(surface, texture.getvalue())
    assert np.isfinite(colour).all()
    np.testing.assert_allclose(colour[:3], ea.srgb_to_linear([10, 30, 10]))


BOX = np.array(
    [
        [0, 1, 3],
        [0, 3, 2],
        [4, 6, 7],
        [4, 7, 5],
        [0, 4, 5],
        [0, 5, 1],
        [2, 3, 7],
        [2, 7, 6],
        [0, 2, 6],
        [0, 6, 4],
        [1, 5, 7],
        [1, 7, 3],
    ]
)


@pytest.fixture(scope="module")
def rig():
    return ea.load_rig(ce.RACES / "luminous_male.glb", ce.BODY_MESH)


def boots():
    left = np.array(
        [[x, y, z] for x in [0.12, 0.30] for y in [-0.5, 0.5] for z in [-0.2, 0.4]]
    )
    right = left.copy()
    right[:, 0] *= -1
    return np.vstack((left, right)), np.vstack((BOX, BOX[:, ::-1] + 8))


def test_boots_use_foot_length_and_preserve_each_shell(rig):
    points, faces = boots()
    mapped, cuff, report = remap.boot_frame(points, faces, rig)
    for offset, foot in zip([0, 8], report["feet"]):
        np.testing.assert_allclose(
            mapped[offset : offset + 8] - mapped[offset],
            (points[offset : offset + 8] - points[offset]) * foot["scale"],
        )
        assert mapped[offset : offset + 8, 1].min() == pytest.approx(
            ea.weighted_sole(rig, foot["side"]) - 0.004 * rig.fit_scale
        )
    # The shaft keeps its full height at the foot-length scale; a tall shaft
    # is not flattened to the old 333 mm span. The regenerated Human foot is
    # 282 mm (the Oldcraft-sized 341 mm foot is gone), so a 1 m shaft maps to
    # about 490 mm rather than the 0.5+ m of the previous body.
    assert np.ptp(mapped[:8, 1]) == pytest.approx(
        np.ptp(points[:8, 1]) * report["feet"][0]["scale"]
    )
    assert np.ptp(mapped[:8, 1]) > 0.40
    assert cuff > 0.45


def test_leg_mapping_does_not_shear_uv_seams(rig):
    points, faces = boots()
    expanded = points[faces.ravel()]
    expanded_faces = np.arange(len(expanded)).reshape(-1, 3)
    mapped, _ = remap.leg_frame(expanded, expanded_faces, rig)
    for index in range(len(points)):
        own = faces.ravel() == index
        np.testing.assert_allclose(mapped[own], np.tile(mapped[own][0], (own.sum(), 1)))


def test_headwear_mapping_is_one_positive_uniform_transform(rig):
    points = np.array(
        [[x, y, z] for x in [-0.3, 0.3] for y in [-0.4, 0.4] for z in [-0.3, 0.3]]
    )
    mapped, report = remap.head_frame(points, BOX, rig, "Test Helm")
    assert report["scale"] > 0
    assert report["enclosure"] >= 0.88
    np.testing.assert_allclose(
        mapped - mapped[0], (points - points[0]) * report["scale"]
    )


def test_wrapped_band_clears_eyes_without_shrinking_its_scarf(rig):
    points = np.array(
        [[x, y, z] for x in [-0.3, 0.3] for y in [-0.4, 0.4] for z in [-0.3, 0.3]]
    )
    circlet, ring = remap.head_frame(points, BOX, rig, "Test Circlet")
    headband, wrapped = remap.head_frame(points, BOX, rig, "Test Headband")
    assert wrapped["scale"] == pytest.approx(ring["scale"])
    np.testing.assert_allclose(
        headband - circlet,
        np.tile([0.0, 0.045 * rig.fit_scale, 0.0], (len(points), 1)),
        atol=1e-10,
    )


def test_lining_boundary_preserves_all_coincident_body_seams(rig):
    points, faces = boots()
    mapped, cuff, _ = remap.boot_frame(points, faces, rig)
    low, high = -0.03, 0.348
    lining, normal, *_ = remap.backing(rig, mapped, faces, "boots", low, high)
    body, triangles = rig.positions, rig.faces
    centers = body[triangles].mean(axis=1)
    crossing = ((body[triangles, 1] > low) & (body[triangles, 1] < high)).any(axis=1)
    retained = (centers[:, 1] <= low) | (centers[:, 1] >= high)
    required = np.unique(
        np.round(body[triangles[crossing & retained]].reshape(-1, 3), 6), axis=0
    )
    count = len(lining) // 2
    actual = set(
        map(tuple, np.round(lining[:count] - normal[:count] * 0.003 * rig.fit_scale, 6))
    )
    assert all(tuple(point) in actual for point in required)


def test_fitted_garment_backing_clips_exactly_at_the_cuff_band(rig):
    points, faces = boots()
    mapped, _, _ = remap.boot_frame(points, faces, rig)
    low, high = 0.19 * rig.fit_scale, 0.36 * rig.fit_scale
    lining, normal, _, indices, _, _ = remap.backing(
        rig, mapped, faces, "boots", low, high,
        join_default_clothing=False, exact_low=True, exact_high=True)
    # Thickening offsets along the surface normal by at most three mm; the
    # old uncut body triangles overshot these planes by roughly fifty mm.
    tolerance = 0.0031 * rig.fit_scale
    assert lining[:, 1].min() >= low - tolerance
    assert lining[:, 1].max() <= high + tolerance
    primitives = coverage.components(lining, indices.reshape(-1, 3))
    assert primitives and all(shell.closed and shell.volume > 0 for shell in primitives)


def test_sheet_band_interpolates_boundary_instead_of_dropping_crossing_faces():
    points = np.array([[-.1, .1, 0.], [.1, .1, 0.], [0., .3, 0.]])
    clipped, faces = remap.clip_sheet_band(points, np.array([[0, 1, 2]]), low=.2)
    assert len(faces) == 1
    assert clipped[:, 1].min() == pytest.approx(.2)
    assert clipped[:, 1].max() == pytest.approx(.3)


@pytest.mark.parametrize(
    ("bound", "points"),
    [
        ({"low": .2}, np.array([[-.1, .2, 0.], [.1, .3, 0.], [0., .1, 0.]])),
        ({"high": .2}, np.array([[-.1, .2, 0.], [.1, .1, 0.], [0., .3, 0.]])),
    ],
)
def test_sheet_band_reuses_exact_on_plane_endpoint_without_degenerate_face(
    bound, points
):
    clipped, faces = remap.clip_sheet_band(
        points, np.array([[0, 1, 2]]), **bound
    )
    assert len(faces) == 1
    assert len(np.unique(faces[0])) == 3
    triangle = clipped[faces[0]]
    assert np.linalg.norm(np.cross(
        triangle[1] - triangle[0], triangle[2] - triangle[0]
    )) > 1e-12
    assert np.count_nonzero(np.isclose(triangle[:, 1], .2)) == 2


def test_sheet_band_drops_an_exact_on_plane_line_instead_of_emitting_a_face():
    points = np.array([[-.1, .2, 0.], [.1, .2, 0.], [0., .1, 0.]])
    clipped, faces = remap.clip_sheet_band(
        points, np.array([[0, 1, 2]]), low=.2
    )
    assert clipped.shape == (0, 3)
    assert faces.shape == (0, 3)


def test_sheet_band_preserves_weighted_side_when_left_foot_crosses_center():
    # Positive X is normally the left side, but a broad left foot can extend
    # across the centre line. Its bone weights, not its X coordinate, own the
    # clipped cuff. The signed values model left_share - right_share.
    points = np.array([
        [-.08, .10, -.04], [-.04, .30, -.04], [.03, .30, .05],
    ])
    left_ownership = np.array([.92, .86, .74])
    clipped, faces, ownership = remap.clip_sheet_band(
        points, np.array([[0, 1, 2]]), low=.20,
        vertex_values=left_ownership)
    assert len(faces) == 2
    assert (clipped[:, 0] < 0).any()
    assert (ownership >= 0).all(), (
        "left-foot cuff vertices must stay on the left bone chain")


@pytest.mark.parametrize(('keep_above', 'seam'), [(True, .19), (False, .19)])
def test_packed_cuff_compression_preserves_topology_order_and_far_edge(keep_above, seam):
    y = np.linspace(.04, .36, 17)
    points = np.column_stack((np.linspace(-.2, .2, len(y)), y, np.zeros(len(y))))
    fitted = remap.compress_cuff_band(points, seam, keep_above)
    assert fitted.shape == points.shape
    assert np.all(np.diff(fitted[:, 1]) >= 0)
    if keep_above:
        assert fitted[:, 1].min() == pytest.approx(seam)
        assert fitted[:, 1].max() == pytest.approx(points[:, 1].max())
    else:
        assert fitted[:, 1].max() == pytest.approx(seam)
        assert fitted[:, 1].min() == pytest.approx(points[:, 1].min())


def test_packed_fitted_backings_meet_at_one_canonical_cuff():
    seam = remap.FITTED_BOOT_CUFF_SEAM
    y = np.linspace(.04, .36, 17)
    points = np.column_stack((np.linspace(-.2, .2, len(y)), y, np.zeros(len(y))))
    legs = remap.compress_cuff_band(points, seam, keep_above=True)
    boots = remap.compress_cuff_band(points, seam, keep_above=False)
    assert legs[:, 1].min() == pytest.approx(seam)
    assert boots[:, 1].max() == pytest.approx(seam)


def test_packed_cuff_orientation_is_checked_before_normal_transport():
    # A monotonic seam map can still fold a coarse, diagonally triangulated
    # sheet when its overshoot is compressed too abruptly.  Packed candidates
    # therefore use the same face-orientation gate as torso silhouettes.
    points = np.array([[0., .04, 0.], [1., .18, 0.], [0., .36, 1.]])
    triangles = np.array([[0, 1, 2]])
    fitted = remap.compress_cuff_band(points, .19, keep_above=True)
    report = remap.torso_remap.require_safe_deformation(
        points, fitted, triangles)
    assert report['newlyDegenerateFaces'] == []
    assert report['unsafeOrientationFaces'] == []


@pytest.mark.parametrize("kind", ["legs", "boots", "helm"])
def test_original_source_writer_bypasses_old_fit_and_preserves_texture(
    tmp_path, rig, monkeypatch, kind
):
    source = tmp_path / "fixture.glb"
    original = tmp_path / "fixture.glb.orig"
    source.write_bytes(b"processed source must not be read")
    points, faces = boots()
    if kind == "helm":
        points = points[:8] - np.array([0.21, 0.0, 0.1])
        points[:, [0, 2]] *= 2
        faces = BOX
    image = BytesIO()
    Image.new("RGB", (8, 8), (38, 31, 20)).save(image, format="JPEG")
    glb = ea.EquipmentGLB()
    material = ce.textured_material(glb, "Fixture", image.getvalue(), double_sided=True)
    glb.doc["images"][0]["mimeType"] = "image/jpeg"
    glb.mesh(
        "Original",
        [
            glb.primitive(
                points,
                np.ones_like(points),
                np.zeros((len(points), 2)),
                faces.ravel(),
                material,
            )
        ],
    )
    glb.write(original)

    def legacy(*args, **kwargs):
        pytest.fail("original-source fit entered a legacy pass")

    monkeypatch.setattr(ce, "seat", legacy)
    monkeypatch.setattr(ce, "repose", legacy)
    monkeypatch.setattr(ce, "seat_socket", legacy)
    out = tmp_path / "fit.glb"
    report = ce.build(source, out, rig, kind, "Fixture")
    assert report["source"] == original.name
    doc, binary = ea.read_glb(out)
    view = doc["bufferViews"][doc["images"][0]["bufferView"]]
    start = view.get("byteOffset", 0)
    assert binary[start : start + view["byteLength"]] == image.getvalue()
    assert doc["images"][0]["mimeType"] == "image/jpeg"
    assert doc["materials"][0]["doubleSided"]
    if kind != "helm":
        backing = doc["meshes"][1]
        assert len(backing["extras"]["bodyCover"]) == 3
        primitives, _, _ = coverage.load(str(out))
        for primitive in primitives[1:]:
            np.testing.assert_allclose(primitive.weights.sum(axis=1), 1.0, atol=1e-6)
            shells = coverage.components(primitive.points, primitive.triangles)
            assert shells and all(s.closed and s.volume > 0 for s in shells)
def test_closed_visor_uses_eyes_instead_of_full_head_feature_height(monkeypatch):
    import equipment_authoring as ea
    import conform_equipment as ce
    import limb_head_remap as remap
    rig = ea.load_rig(ce.RACES / 'votary_male.glb', ea.BODY_SURFACES)
    target = ce.socket_origin(rig, 3).copy()
    monkeypatch.setattr(ce, 'socket_origin', lambda *args: target.copy())
    # A simple hood has side/back walls, a roof and a front brow, with its
    # face open below the brow. This exercises the actual opening detector.
    points = np.array([[x,y,z] for x in [-.16,.16]
                       for y in [-.20,.20] for z in [-.12,.12]])
    points = np.vstack([points, [-.16,.06,.12], [.16,.06,.12]])
    faces = np.array([[0,1,3],[0,3,2],[4,6,7],[4,7,5],
                      [0,2,6],[0,6,4],[2,3,7],[2,7,6],[8,9,7],[8,7,3]])
    class TallFeature:
        def __getattr__(self, name):
            return getattr(rig, name)
        def _region(self, bones):
            return np.vstack([rig._region(bones), [0.,2.4,0.]])
    regular, before = remap.head_frame(points, faces, rig, 'Fixture Hood')
    tall, after = remap.head_frame(points, faces, TallFeature(), 'Fixture Hood')
    assert before['sourceBrow'] is not None
    np.testing.assert_allclose(tall, regular, atol=1e-10)
