"""The source-pose torso path keeps artwork and skinning consistent."""
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

TOOLS = Path(__file__).resolve().parents[2] / 'eloria-assets/tools'
sys.path.insert(0, str(TOOLS))
import conform_equipment as ce
import equipment_authoring as ea
import torso_remap as remap
import garment_coverage as coverage
import repair_torso_lining as repair


@pytest.fixture(scope='module')
def rig():
    return ea.load_rig(ce.RACES / 'luminous_male.glb', ce.BODY_MESH)


def test_limb_rotation_preserves_lengths_and_handedness():
    source = np.array([.14, -.70, .06])
    target = np.array([.494, 0., -.001])
    rotation = remap.rotation_between(source, target)
    np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-12)
    assert np.linalg.det(rotation) == pytest.approx(1.)
    np.testing.assert_allclose(rotation @ (source / np.linalg.norm(source)),
                               target / np.linalg.norm(target), atol=1e-12)


def test_arm_silhouette_is_baked_radially_and_caps_stay_rigid(rig):
    root = rig.origin('upperarm_l')
    wrist = rig.origin('hand_l')
    axis = wrist - root
    axis /= np.linalg.norm(axis)
    radial = np.array([0.0, 0.12, 0.0])
    sleeve = np.vstack([root + axis * t + radial for t in (0.08, 0.4, 0.9)])
    cap = np.array([[.24, 1.42, -.12], [.31, 1.46, -.08],
                    [.27, 1.51, -.03]])
    points = np.vstack((sleeve, cap))
    before = points.copy()
    share = np.zeros((len(points), 2))
    share[:len(sleeve), 0] = 1.0
    cap_side = np.r_[np.full(len(sleeve), -1), np.zeros(len(cap), dtype=int)]
    report = remap.tighten_arm_silhouette(points, rig, share, cap_side)
    before_travel = (before[:3] - root) @ axis
    after_travel = (points[:3] - root) @ axis
    np.testing.assert_allclose(after_travel, before_travel, atol=1e-12)
    assert np.all(np.linalg.norm(points[:3] - root - after_travel[:, None] * axis,
                                 axis=1) < np.linalg.norm(radial))
    np.testing.assert_allclose(points[3:] - points[3], before[3:] - before[3])
    np.testing.assert_allclose(points[3:, 0], before[3:, 0]
                               - remap.SHOULDER_CAP_INSET * rig.fit_scale)
    assert report['movedVertices'] == len(points)
    assert report['maximumMove'] > 0.0


def test_reviewed_arm_profiles_lock_elbow_and_cuff_to_previous_bytes():
    locked = remap.SLEEVE_PROFILE_T >= remap.SLEEVE_PROFILE_LOCK_T
    for source, revised in remap.ARM_FIT_OVERRIDES.items():
        baseline = remap.REVIEWED_ARM_FIT_BASELINES[source]
        np.testing.assert_array_equal(
            revised['radial_scale'][locked], baseline['radial_scale'][locked])
        assert revised['cap_inset'] >= baseline['cap_inset']
    for profile in remap.PACKED_BACKING_RELATIVE_PROFILES.values():
        np.testing.assert_array_equal(profile[locked], np.ones(locked.sum()))


def test_reviewed_arm_profile_rosters_are_exactly_the_four_class_torsos():
    """A stray torso must not inherit these narrowly reviewed fit deltas."""
    source_roster = {
        'Militia_torso_armor_concept_sheet__r01_c02.glb',
        'Eight_leather_ranger_torso_designs__r01_c02.glb',
        'Eloria_Arcane_Armor_Design_Sheet__r01_c01.glb',
        'Amberwood_Woodland_Armor_Concept_Sheet__r02_c02.glb',
    }
    packed_roster = {
        'militia_torso_armor_02',
        'leather_ranger_torso_02',
        'eloria_arcane_armor_01',
        'amberwood_woodland_cuirass_06',
    }
    assert set(remap.ARM_FIT_OVERRIDES) == source_roster
    assert set(remap.REVIEWED_ARM_FIT_BASELINES) == source_roster
    assert set(remap.PACKED_BACKING_RELATIVE_PROFILES) == packed_roster


def test_packed_arm_profile_never_assigns_locked_rows(rig):
    root = rig.origin('upperarm_l')
    wrist = rig.origin('hand_l')
    axis = wrist - root
    radial = np.array([0., .05, .025])
    radial -= axis * (radial @ axis) / (axis @ axis)
    # Row 2 sits on the lock (SLEEVE_PROFILE_LOCK_T = .62). Travel is
    # recomputed from the rig's arm axis, which can land one ulp below an exact
    # .62 (it does on the regenerated Human rig: 0.6199999999999999), so the
    # fixture sits a hair past the lock instead of on the floating-point edge.
    travel = np.array([.2, .61, .62 + 1e-9, .8])
    points = root + travel[:, None] * axis + radial
    before = points.copy()
    share = np.zeros((len(points), 2))
    share[:3, 0] = 1.
    cap_side = np.array([-1, -1, -1, 0])
    report = remap.tighten_arm_silhouette(
        points, rig, share, cap_side,
        radial_scale=remap.PACKED_BACKING_RELATIVE_PROFILES[
            'militia_torso_armor_02'],
        cap_inset=.02, locked_from=remap.SLEEVE_PROFILE_LOCK_T)
    assert np.any(points[:2] != before[:2])
    np.testing.assert_array_equal(points[2:], before[2:])
    assert report['lockedVertices'] == 1
    assert report['capVertices'] == 0
    assert report['lockedCapVertices'] == 1


def test_authoring_profile_keeps_baseline_tail_but_locks_far_caps(rig):
    root = rig.origin('upperarm_l')
    wrist = rig.origin('hand_l')
    axis = wrist - root
    radial = np.array([0., .05, .025])
    radial -= axis * (radial @ axis) / (axis @ axis)
    travel = np.array([.2, .8])
    points = root + travel[:, None] * axis + radial
    before = points.copy()
    share = np.zeros((len(points), 2))
    share[0, 0] = 1.
    report = remap.tighten_arm_silhouette(
        points, rig, share, np.array([-1, 0]),
        radial_scale=remap.SLEEVE_PROFILE_SCALE,
        cap_inset=.02, cap_locked_from=remap.SLEEVE_PROFILE_LOCK_T)
    assert np.any(points[0] != before[0])
    np.testing.assert_array_equal(points[1], before[1])
    assert report['lockedVertices'] == 0
    assert report['lockedCapVertices'] == 1


def test_visible_sleeve_clearance_recesses_only_covered_unlocked_backing(rig):
    root = rig.origin('upperarm_l')
    wrist = rig.origin('hand_l')
    axis = wrist - root
    axis /= np.linalg.norm(axis)
    helper = np.array([0., 1., 0.])
    if abs(helper @ axis) > .9:
        helper = np.array([0., 0., 1.])
    first = np.cross(axis, helper)
    first /= np.linalg.norm(first)
    second = np.cross(axis, first)
    angles = np.linspace(0., 2*np.pi, 24, endpoint=False)
    rings = []
    for travel in (-.1, .9):
        centre = root + travel * (wrist - root)
        rings.append(np.array([
            centre + .08 * (np.cos(a)*first + np.sin(a)*second)
            for a in angles]))
    visible = np.vstack(rings)
    triangles = []
    count = len(angles)
    for index in range(count):
        following = (index + 1) % count
        triangles.extend([[index, following, count + following],
                          [index, count + following, count + index]])
    visible_faces = visible[np.asarray(triangles)]
    direction = np.cos(.13)*first + np.sin(.13)*second
    travel = np.array([.2, .4, .7])
    points = (root + travel[:, None] * (wrist - root)
              + .078 * direction)
    before = points.copy()
    share = np.zeros((len(points), 2))
    share[:, 0] = 1.
    report = remap.seat_arm_backing_inside_visible(
        points, rig, share, [visible_faces, np.empty((0, 3, 3))])
    centres = root + travel[:, None] * (wrist - root)
    radius = np.linalg.norm(points - centres, axis=1)
    assert np.all(radius[:2] < np.linalg.norm(before[:2] - centres[:2], axis=1))
    np.testing.assert_array_equal(points[2], before[2])
    assert report['minimumClearanceAfter'] >= (
        remap.SLEEVE_BACKING_CLEARANCE * rig.fit_scale - 1e-9)
    assert report['lockedVertices'] == 1


def test_position_only_revision_preserves_packed_resources_and_topology(tmp_path):
    source, out = tmp_path / 'source.glb', tmp_path / 'revised.glb'
    points = np.array([[-.3, .2, -.1], [.3, .2, -.1], [0., .8, .1]], dtype=np.float32)
    glb = ea.EquipmentGLB()
    primitive = glb.primitive(points, np.ones_like(points), np.zeros((3, 2)),
                              np.array([0, 1, 2], dtype=np.uint16), 0)
    glb.doc['materials'] = [{'name': 'Existing packed material'}]
    glb.doc['images'] = [{'uri': 'textures/existing.jpg', 'mimeType': 'image/jpeg'}]
    glb.mesh('Existing mesh', [primitive])
    glb.write(source)
    before_doc, before_binary = ea.read_glb(source)
    position = primitive['attributes']['POSITION']
    tightened = points.copy()
    tightened[:, 0] *= .8
    report = remap.position_only_revision(source, out, {position: tightened})
    after_doc, after_binary = ea.read_glb(out)
    assert source.stat().st_size == out.stat().st_size
    assert after_doc == before_doc
    assert after_doc['images'] == [{'uri': 'textures/existing.jpg',
                                    'mimeType': 'image/jpeg'}]
    assert report['documentPreserved'] and report['changedBytes'] > 0
    for index in range(len(before_doc['accessors'])):
        before = ea.accessor_array(before_doc, before_binary, index)
        after = ea.accessor_array(after_doc, after_binary, index)
        if index == position:
            np.testing.assert_array_equal(after, tightened)
        else:
            np.testing.assert_array_equal(after, before)


def test_deformation_transports_all_incident_normals_without_stale_lighting():
    original = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    revised = original.copy()
    revised[2, 2] = .5
    authored = np.tile([0., 0., 1.], (3, 1))
    triangles = np.array([[0, 1, 2]])
    normals, report = remap.transport_normals_across_deformation(
        original, revised, authored, triangles)
    expected = np.cross(revised[1] - revised[0], revised[2] - revised[0])
    expected /= np.linalg.norm(expected)
    np.testing.assert_allclose(normals, np.tile(expected, (3, 1)), atol=1e-12)
    assert report['incidentFaces'] == 1
    assert report['movedNormals'] == 3
    assert report['maximumAlignmentDelta'] == pytest.approx(0., abs=1e-12)

    unchanged, unchanged_report = remap.transport_normals_across_deformation(
        original, original, authored, triangles)
    np.testing.assert_array_equal(unchanged, authored)
    assert unchanged_report['movedNormals'] == 0


def test_packed_deformation_gate_rejects_folded_and_collapsed_faces():
    original = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    triangles = np.array([[0, 1, 2]])
    safe = original.copy()
    safe[2] = [.1, .7, .2]
    report = remap.require_safe_deformation(original, safe, triangles)
    assert report['minimumCosine'] > .1
    assert report['newlyDegenerateFaces'] == []
    assert report['unsafeOrientationFaces'] == []

    folded = original.copy()
    folded[2] = [0., -1., 0.]
    with pytest.raises(ValueError, match='orientation faces'):
        remap.require_safe_deformation(original, folded, triangles)

    collapsed = original.copy()
    collapsed[2] = [.5, 0., 0.]
    with pytest.raises(ValueError, match='newly degenerate faces'):
        remap.require_safe_deformation(original, collapsed, triangles)


def test_packed_deformation_limiter_is_local_safe_and_uv_split_coherent():
    original = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.],
                         [0., 1., 0.], [-1., 0., 0.]])
    desired = original.copy()
    desired[[2, 3], 1] = -1.
    triangles = np.array([[0, 1, 2], [0, 3, 4]])
    revised, limiter = remap.constrain_deformation_orientation(
        original, desired, triangles)
    report = remap.require_safe_deformation(original, revised, triangles)
    assert limiter['iterations'] > 0
    assert limiter['limitedVertices'] > 0
    assert report['minimumCosine'] > .1
    np.testing.assert_array_equal(revised[2], revised[3])


def test_uv_split_positions_receive_identical_mapping_and_weights(rig):
    # A closed little sleeve island, split at every texture seam, plus torso
    # landmarks. Changing UV topology must never shear coincident positions.
    p = np.array([[.30, -.10, .02], [.34, -.10, .02],
                  [.32, -.15, .02], [.32, -.12, .06],
                  [0., -.5, 0.], [0., .5, 0.]])
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    expanded = np.vstack((p[faces.ravel()], p[4:]))
    tris = np.arange(12).reshape(-1, 3)
    mapped, joints, weights, keep, _ = remap.remap(expanded, tris, rig)
    for original in range(4):
        copies = np.flatnonzero(faces.ravel() == original)
        np.testing.assert_allclose(mapped[copies], np.tile(mapped[copies[0]], (len(copies), 1)))
        np.testing.assert_array_equal(joints[copies], np.tile(joints[copies[0]], (len(copies), 1)))
        np.testing.assert_allclose(weights[copies], np.tile(weights[copies[0]], (len(copies), 1)))
    assert keep.all()
    np.testing.assert_allclose(weights.sum(axis=1), 1.)


def test_shallow_contact_shell_cannot_throw_the_backplate_outward(rig):
    p = np.array([[x, y, z] for x in [-.18, .18]
                  for y in [1.04, 1.52] for z in [-.10, .05]])
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                      [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                      [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    before = p.copy()
    remap._clear_trunk(p, faces, rig, np.ones(len(p)), np.zeros(len(p), dtype=int))
    # The old median-depth rule sent these shallow shoulder contacts far
    # behind the body. A shirt opening must not become a dorsal fin.
    assert np.max(np.linalg.norm(p - before, axis=1)) < .07
    assert np.ptp(p[:, 2]) > np.ptp(before[:, 2])  # still fits, rather than skipping the cage


def test_raised_collar_keeps_shoulder_and_small_ornaments_rigid(rig):
    box_faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                          [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                          [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    collar = np.array([[x, y, z] for x in [-.08, .08]
                       for y in [.10, .50] for z in [-.04, .04]])
    ornament = np.array([[x, y, z] for x in [-.02, .02]
                         for y in [.42, .44] for z in [.045, .055]])
    shoulder = np.array([[x, y, z] for x in [.23, .35]
                         for y in [.25, .37] for z in [-.05, .05]])
    p = np.vstack((collar, ornament, shoulder, [[0., -.50, 0.]]))
    faces = np.vstack([box_faces + offset for offset in [0, 8, 16]])
    before, _, _, _, _ = remap.remap(p, faces, rig)
    after, joints, weights, _, report = remap.remap(p, faces, rig, collar_lift=.045)
    np.testing.assert_allclose(after[16:], before[16:])
    assert set(joints[16:24, 0]) == {rig.joint_names.index('clavicle_l')}
    np.testing.assert_allclose(weights[16:24, 0], 1.)
    np.testing.assert_allclose(after[8:16] - after[8], before[8:16] - before[8])
    assert after[8, 1] > before[8, 1] + .02
    assert after[:8, 1].max() - before[:8, 1].max() == pytest.approx(.045 * rig.fit_scale)
    np.testing.assert_allclose(after[:, [0, 2]], before[:, [0, 2]])
    assert next(p for p in report['passes'] if p['name'] == 'raised_collar')['movedVertices'] > 0


def test_original_glb_bypasses_legacy_fitting_and_keeps_image_encoding(tmp_path, rig, monkeypatch):
    source = tmp_path / 'piece.glb'
    original = tmp_path / 'piece.glb.orig'
    source.write_bytes(b'processed file must not be read')
    points = np.array([[-.2, -.5, -.1], [.2, -.5, -.1], [0., .5, -.1], [0., 0., .2]])
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    image = BytesIO()
    Image.new('RGB', (4, 4), (65, 52, 31)).save(image, format='JPEG')
    glb = ea.EquipmentGLB()
    material = ce.textured_material(glb, 'Original', image.getvalue(), double_sided=True)
    glb.doc['images'][0]['mimeType'] = 'image/jpeg'
    glb.mesh('Original', [glb.primitive(points, np.ones_like(points),
        np.zeros((len(points), 2)), faces.ravel(), material)])
    glb.write(original)
    def legacy(*args, **kwargs):
        pytest.fail('torso entered the legacy conversion')
    monkeypatch.setattr(ce, 'seat', legacy)
    monkeypatch.setattr(ce, 'repose', legacy)
    out = tmp_path / 'fitted.glb'
    report = ce.build(source, out, rig, 'cuirass', 'Fixture')
    doc, binary = ea.read_glb(out)
    assert report['source'] == original.name
    assert doc['images'][0]['mimeType'] == 'image/jpeg'
    view = doc['bufferViews'][doc['images'][0]['bufferView']]
    offset = view.get('byteOffset', 0)
    assert binary[offset:offset + view['byteLength']] == image.getvalue()
    assert doc['materials'][0]['doubleSided']
    assert any(m['name'] == 'GeneratedArmorBacking' for m in doc['meshes'])
    primitives, _, _ = coverage.load(str(out))
    shells = coverage.components(primitives[1].points, primitives[1].triangles)
    assert shells and all(s.closed and s.volume > 0 for s in shells)
    np.testing.assert_allclose(primitives[1].weights.sum(axis=1), 1., atol=1e-6)


@pytest.mark.parametrize('width', [.220, .244])
def test_source_boundary_preserves_each_drawings_trunk_width(width):
    # Independent side walls with the same overall source height. The wider
    # wrap must retain its chest rather than receive the narrow coat's cut.
    points = np.array([[x, y, z] for x in [-width, width]
                       for y in [-.3, .3] for z in [-.10, .10]])
    faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5]])
    points = np.vstack([points, [0., -.5, 0.], [0., .5, 0.]])
    boundaries = remap.source_seam_boundaries(points, faces)
    for side in ['l', 'r']:
        assert boundaries[side]['fraction'] == pytest.approx(width)


def test_chest_coverage_does_not_count_the_bridges_removed_from_sleeves(monkeypatch):
    from types import SimpleNamespace
    body = np.array([[-.2, 1.2, 0.], [.2, 1.2, 0.], [.2, 1.4, 0.], [-.2, 1.4, 0.]])
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    fake_rig = SimpleNamespace(positions=body, faces=faces, fit_scale=1.,
                              origin=lambda _: np.array([0., 1.28, 0.]))
    bridge = body + [0., 0., .03]
    narrow = body * [0.25, 1., 1.] + [0., 0., .02]
    points = np.vstack([bridge, narrow])
    faces = np.vstack([faces, faces + 4])
    influence = np.r_[np.zeros(4), np.ones(4)]
    solved = []
    monkeypatch.setattr(remap, '_bounded_trunk', lambda *args: None)
    monkeypatch.setattr(remap, '_paired_trunk', lambda *args: solved.append(True))
    remap._clear_trunk(points, faces, fake_rig, influence, np.zeros(8, dtype=int))
    assert solved == [True]


def test_cut_debris_is_removed_without_deleting_original_floating_ornaments():
    points = np.array([[x*.01, y*.01, 0.] for y in range(9) for x in range(9)])
    faces = []
    for y in range(8):
        for x in range(8):
            i = y*9+x
            faces.extend([[i, i+1, i+10], [i, i+10, i+9]])
    count = len(points)
    points = np.vstack([points, [[.4,0.,0.], [.41,0.,0.], [.4,.01,0.]],
                        [[-.4,0.,0.], [-.41,0.,0.], [-.4,.01,0.]]])
    faces = np.vstack([faces, [count,count+1,count+2], [count+3,count+4,count+5]])
    original = np.r_[np.zeros(count+3,dtype=int), np.ones(3,dtype=int)]
    keep, removed = remap.drop_cut_fragments(points, faces, np.ones(len(faces),dtype=bool), original, 1.)
    assert removed == 1
    assert not keep[-2] and keep[-1]
    assert keep[:-2].all()


def test_nearly_mirrored_long_sleeves_keep_the_same_arm_assignment(rig):
    box_faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                          [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                          [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    trunk = np.array([[x, y, z] for x in [-.10, .10]
                      for y in [-.50, .50] for z in [-.1, .1]])
    sleeves = [np.array([[center+x, y, z] for x in [-.05, .05]
                         for y in [-.215, .355] for z in [-.08, .08]])
               for center in [.2496, -.2526]]
    points = np.vstack([trunk, *sleeves])
    faces = np.vstack([box_faces+offset for offset in [0, 8, 16]])
    parts = np.zeros(len(points), dtype=int)
    remap.remap(points, faces, rig, parts_out=parts)
    assert (parts[8:16] == 1).all()
    assert (parts[16:24] == 2).all()
    # A matching width on a low skirt island does not make it a sleeve.
    low = sleeves[0] - [0., .5, 0.]
    frame = remap.source_skeleton(points)['l']
    assert not remap.long_sleeve_island(low, low.mean(axis=0), *frame, 1.)


def test_broad_connected_cloth_sleeves_keep_their_outer_panels(rig):
    # A broad cloth panel lies outside the narrow arm-axis cylinder. Its
    # shared connection to the chest must not turn the outer cloth into trunk.
    trunk = np.array([[x, y, z] for x in [-.1, .1]
                      for y in [-.5, .5] for z in [-.08, .08]])
    faces = [[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
             [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6]]
    panels = [np.array([[sign*.52, y, z] for y in [.13, .20]
                        for z in [-.08, .08]]) for sign in [1., -1.]]
    for start, anchor in [(8, 6), (12, 2)]:
        faces.extend([[anchor, start, start+1], [anchor, start+1, start+3],
                      [anchor, start+3, start+2]])
    points = np.vstack([trunk, *panels])
    parts = np.zeros(len(points), dtype=int)
    remap.remap(points, np.asarray(faces), rig, parts_out=parts)
    assert (parts[8:12] == 1).all()
    assert (parts[12:16] == 2).all()


def test_low_hem_tabs_follow_the_trunk_instead_of_the_hand(rig, monkeypatch):
    box_faces = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5],
                          [0, 4, 5], [0, 5, 1], [2, 3, 7], [2, 7, 6],
                          [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])
    trunk = np.array([[x, y, z] for x in [-.10, .10]
                      for y in [-.50, .50] for z in [-.1, .1]])
    tabs = [np.array([[sign*x, y, z] for x in [.25, .272]
                      for y in [-.40, -.382] for z in [-.05, .07]]) for sign in [1, -1]]
    cuff = tabs[0] + [0., .32, 0.]
    points = np.vstack([trunk, *tabs, cuff])
    faces = np.vstack([box_faces+offset for offset in [0, 8, 16, 24]])
    monkeypatch.setattr(remap, 'source_skeleton', lambda *_: {
        side: (np.array([sign*.23, .33, -.04]), np.array([sign*.32, -.09, -.07]))
        for side, sign in [('l', 1), ('r', -1)]})
    parts = np.zeros(len(points), dtype=int)
    remap.remap(points, faces, rig, parts_out=parts)
    assert (parts[8:24] == 0).all()
    assert (parts[24:] == 1).all()


@pytest.mark.parametrize('scale', [1., .98])
def test_lining_opens_the_throat_without_lowering_shoulder_coverage(scale):
    # The source shirt may contain an interior collar fold as well as a rim.
    # Both cross the throat opening; the separate shoulder must remain intact.
    points = np.array([[-.04,1.37,.10],[.04,1.37,.10],[.04,1.48,.10],[-.04,1.48,.10],
                       [-.03,1.39,.08],[.03,1.39,.08],[0.,1.47,.09],
                       [.22,1.42,.04],[.25,1.42,.04],[.25,1.52,.04]]) * scale
    faces = np.array([[0,1,2],[0,2,3],[4,5,6],[7,8,9]])
    out, triangles = remap.clip_lining_neckline(points, faces, scale)
    assert out[np.abs(out[:,0]) < .08*scale,1].max() == pytest.approx(1.40*scale)
    for point in points[7:]:
        assert np.linalg.norm(out-point,axis=1).min() < 1e-12
    area = np.linalg.norm(np.cross(out[triangles[:,1]]-out[triangles[:,0]],
                                  out[triangles[:,2]]-out[triangles[:,0]]),axis=1)
    assert (area > 1e-10).all()
    # Clipping retains the original face planes instead of flattening a shell.
    assert np.max(out[:,2]) <= np.max(points[:,2]) + 1e-12


def test_loose_cuff_tie_does_not_change_the_opposite_sleeve_scale():
    points, faces = [], []
    for sign in [-1., 1.]:
        start = len(points)
        for y in [-.23, -.10, .15]:
            for angle in np.arange(8) * np.pi / 4:
                points.append([sign * (.31 + .04 * np.cos(angle)), y, .05 * np.sin(angle)])
        for row in range(2):
            for col in range(8):
                a = start + row * 8 + col
                b = start + row * 8 + (col + 1) % 8
                faces.extend([[a, b, a + 8], [b, b + 8, a + 8]])
    # A tiny ribbon below only the right cuff used to enter its distal median.
    start = len(points)
    points.extend([[-.32, -.50, 0.], [-.33, -.34, 0.], [-.31, -.34, .01], [0., .50, 0.]])
    faces.append([start, start + 1, start + 2])
    frame = remap.source_skeleton(np.asarray(points), np.asarray(faces))
    np.testing.assert_allclose(frame['l'][1] * [-1., 1., 1.], frame['r'][1], atol=1e-8)


def test_reconstructed_sleeve_rings_share_an_arm_weight_field(rig):
    root, wrist = rig.origin('upperarm_l'), rig.origin('hand_l')
    points = []
    for travel in [.3, .5, .8]:
        center = root + travel * (wrist - root)
        points.extend(center + np.array([0., .045 * np.cos(a), .045 * np.sin(a)])
                      for a in np.arange(12) * np.pi / 6)
    joints, weights = remap.lining_weights(np.asarray(points), rig)
    dense = np.zeros((len(points), len(rig.joint_names)))
    for slot in range(4):
        dense[np.arange(len(points)), joints[:, slot]] += weights[:, slot]
    for ring in dense.reshape(3, 12, -1):
        # The slightly tilted canonical arm gives opposite ring sides a
        # small difference in elbow travel; it must not give them chest motion.
        assert np.ptp(ring, axis=0).max() < .025
        assert ring[:, [rig.joint_names.index('upperarm_l'), rig.joint_names.index('lowerarm_l')]].sum(1).min() > .995


def test_medial_cloth_cap_does_not_swing_out_with_the_upper_arm(rig):
    root = rig.origin('upperarm_l')
    points = np.array([root + [-.048, .109, -.04],
                       root + [-.044, .110, -.094],
                       root + [-.030, .084, .025]])
    joints = np.full((3, 4), rig.joint_names.index('upperarm_l'), dtype=np.uint16)
    weights = np.tile([1., 0., 0., 0.], (3, 1))
    glb = ea.EquipmentGLB()
    glb.skeleton(rig)
    primitive = glb.primitive(points, np.tile([0., 0., 1.], (3, 1)),
        np.zeros((3, 2)), np.array([0, 1, 2]), 0, joints=joints, weights=weights)
    glb.mesh('Cloth', [primitive], skin=0)
    document, data, report = repair.repair_cloth_sleeves(glb.doc, glb.binary, rig)
    attrs = primitive['attributes']
    for name in ('TEXCOORD_0',):
        np.testing.assert_array_equal(ea.accessor_array(document, data, attrs[name]),
                                      ea.accessor_array(glb.doc, glb.binary, attrs[name]))
    np.testing.assert_array_equal(ea.accessor_array(document, data, primitive['indices']).ravel(), [0, 1, 2])
    out = ea.accessor_array(document, data, attrs['POSITION'])
    assert np.max(out[:, 1] - root[1]) <= .075 * rig.fit_scale + 1e-6
    j = ea.accessor_array(document, data, attrs['JOINTS_0'])
    w = ea.accessor_array(document, data, attrs['WEIGHTS_0']).astype(float)
    w /= w.sum(axis=1, keepdims=True)
    np.testing.assert_allclose((w * (j == rig.joint_names.index('clavicle_l'))).sum(axis=1), 1.)
    assert report['artworkTopologyPreserved']
