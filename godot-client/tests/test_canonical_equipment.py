"""Canonical surface sampling and anatomical exclusions for equipment."""
from pathlib import Path
import sys
import numpy as np
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import equipment_authoring as ea
import conform_equipment as ce


def test_shared_attribute_sets_are_sampled_once_and_selected_faces_are_unioned(tmp_path):
    rig=ea.load_rig(ce.RACES/'luminous_male.glb')
    glb=ea.EquipmentGLB();glb.skeleton(rig)
    glb.doc['materials'].append({'name':'body'})
    p=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[1.,1.,0.],[2.,1.,0.],[9.,9.,9.]])
    j=np.zeros((6,4),dtype=np.uint16);w=np.tile([.7,.3,0.,0.],(6,1));j[:,1]=1
    primitive=glb.primitive(p,np.tile([0.,0.,1.],(6,1)),np.zeros((6,2)),np.array([0,1,2]),0,joints=j,weights=w)
    second=dict(primitive);second['indices']=glb.accessor(np.array([2,3,4],dtype=np.uint32),'SCALAR')
    glb.mesh('body',[primitive],skin=0);glb.mesh('wardrobe_shirt',[second],skin=0)
    path=tmp_path/'split.glb';glb.write(path)
    union=ea.load_rig(path)
    assert len(union.positions)==5 and len(union.faces)==2
    np.testing.assert_allclose(union.weights.sum(axis=1),1.)
    assert len(ea.load_rig(path,('body',)).positions)==3
    assert np.max(union.positions)<9. # Unreferenced accessor samples do not enter girth.


def test_weighted_soles_do_not_follow_the_tail_or_the_other_foot():
    rig=ea.load_rig(ce.RACES/'luminous_male.glb')
    original=[ea.weighted_sole(rig,side) for side in ('l','r')]
    pelvis=rig.joint_names.index('pelvis')
    rig.positions=np.vstack([rig.positions,[0.,-50.,-2.]])
    rig.joints=np.vstack([rig.joints,[pelvis]*4]);rig.weights=np.vstack([rig.weights,[1.,0.,0.,0.]])
    assert [ea.weighted_sole(rig,side) for side in ('l','r')]==original
    # Each foot is measured on its own. The regenerated Human soles are level
    # to 0.1 mm, so probe directly instead of relying on an asymmetric body: a
    # vertex wholly on foot_r far below the floor moves the right sole only.
    foot_r=rig.joint_names.index('foot_r')
    rig.positions=np.vstack([rig.positions,[-.1,-1.,0.]])
    rig.joints=np.vstack([rig.joints,[foot_r]*4]);rig.weights=np.vstack([rig.weights,[1.,0.,0.,0.]])
    assert ea.weighted_sole(rig,'l')==original[0]
    assert ea.weighted_sole(rig,'r')==-1.


def test_tail_core_is_excluded_from_backing_but_foot_is_preserved():
    rig=ea.load_rig(ce.RACES/'ssarathi_female.glb')
    faces=ea.garment_faces(rig);centers=rig.positions[faces].mean(axis=1)
    assert not ((centers[:,2]<-.35)&(centers[:,1]<.90)).any()
    foot=rig.positions[rig.faces].mean(axis=1)
    foot_ids=np.flatnonzero((foot[:,1]<.15)&(foot[:,2]>.04))
    kept=set(map(tuple,faces))
    assert all(tuple(rig.faces[i]) in kept for i in foot_ids)
    assert len(rig.faces)-len(faces)>100


def test_texture_packing_preserves_accessor_arrays_and_original_jpeg(tmp_path):
    from io import BytesIO
    from PIL import Image
    import pack_canonical_equipment as pack
    image=BytesIO();Image.new('RGB',(8,8),(31,42,55)).save(image,format='JPEG')
    glb=ea.EquipmentGLB()
    mat=ce.textured_material(glb,'Test',image.getvalue())
    glb.doc['images'][0]['mimeType']='image/jpeg'
    p=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    primitive=glb.primitive(p,np.tile([0.,0.,1.],(3,1)),np.zeros((3,2)),np.array([0,1,2]),mat)
    glb.mesh('test',[primitive]);source=tmp_path/'source.glb';glb.write(source)
    stage=tmp_path/'packed';target=pack.PREFIX/'variants/test/test.glb'
    textures=pack.pack_glb(source,target,stage)
    assert len(textures)==1 and (stage/textures[0]).read_bytes()==image.getvalue()
    before,bb=ea.read_glb(source);after,ab=ea.read_glb(stage/target)
    assert 'bufferView' not in after['images'][0]
    assert after['images'][0]['mimeType']=='image/jpeg'
    for index in range(len(before['accessors'])):
        np.testing.assert_array_equal(ea.accessor_array(before,bb,index),ea.accessor_array(after,ab,index))
    assert pack.validate(source)==pack.validate(stage/target)


def test_frontmost_coverage_keeps_both_sides_and_absolute_denominator():
    from measure_canonical_coverage import front_depth
    xs=np.linspace(-.9,.9,19);ys=np.linspace(.1,.9,9)
    square=np.array([[[-1.,0.,0.],[1.,0.,0.],[1.,1.,0.]],
                     [[-1.,0.,0.],[1.,1.,0.],[-1.,1.,0.]]])
    body=front_depth(square,xs,ys)
    armour=square.copy();armour[:,:,2]=.02
    front=front_depth(armour[:,::-1],xs,ys) # Winding cannot alter the ray hit.
    assert np.isfinite(body).all() and ((front-body)>.001).sum()==body.size
    behind=armour.copy();behind[:,:,2]=-.20
    hidden=front_depth(behind,xs,ys)
    assert ((hidden-body)>.001).sum()==0 # Pushing armour back cannot improve the score.


def test_long_source_edges_cannot_bind_the_belt_to_a_calf():
    from equipment_skinning import constrain_legs
    rig=ea.load_rig(ce.RACES/'luminous_male.glb')
    # Actual positions/weights of the Bronze Tassets cut panel that tore by
    # 176 mm during Run_Female when graph smoothing reached across its length.
    p=np.array([[-.04234,1.00263,-.081],[-.04208,.97934,-.08725]])
    j=np.tile([rig.joint_names.index(n) for n in ('pelvis','calf_r','calf_l','thigh_r')],(2,1)).astype(np.uint16)
    w=np.array([[.68,.24,.04,.04],[.45,.49,.02,.04]])
    j,w=constrain_legs(p,j,w,rig)
    names=np.array(rig.joint_names)[j]
    assert np.max(w[np.char.startswith(names,'calf_')])==0.
    np.testing.assert_allclose(w.sum(axis=1),1.)
    # An arbitrary calf rotation must no longer pull these two belt points.
    matrices=np.tile(np.eye(4),(len(rig.joint_names),1,1))
    for side in ('l','r'):matrices[rig.joint_names.index('calf_'+side),:3,3]=[0.,-.6,.7]
    posed=p.copy()
    for slot in range(4):posed+=matrices[j[:,slot],:3,3]*w[:,slot,None]
    np.testing.assert_allclose(posed,p)


def test_unweighted_toe_joint_samples_the_forefoot_instead_of_the_whole_body():
    rig=ea.load_rig(ce.RACES/'ssarathi_male.glb')
    toe=rig._region(['ball_l'])
    assert len(toe)>8
    assert toe[:,1].max()<.14 and toe[:,2].min()>.04
    assert np.abs(toe[:,0]).max()<.25


def test_sparse_replay_matches_direct_four_weight_skinning():
    from replay_canonical_equipment import skin_operator
    rng = np.random.default_rng(20260907)
    points = rng.normal(size=(47, 3))
    joints = rng.integers(0, 77, size=(47, 4), dtype=np.uint16)
    # Include duplicate joints, zero slots and translations as well as bases.
    joints[0] = [1, 1, 2, 2]
    weights = rng.uniform(size=(47, 4))
    weights[1, 2:] = 0
    weights /= weights.sum(axis=1, keepdims=True)
    matrices = rng.normal(size=(77, 4, 4))
    direct = np.zeros_like(points)
    for slot in range(4):
        direct += (np.einsum('nij,nj->ni', matrices[joints[:, slot], :3, :3], points)
                   + matrices[joints[:, slot], :3, 3]) * weights[:, slot, None]
    sparse = skin_operator(points, joints, weights, 77) @ matrices[:, :3, :].transpose(0, 2, 1).reshape(-1, 3)
    np.testing.assert_allclose(sparse, direct, rtol=1e-13, atol=1e-13)


def test_non_torso_reuse_requires_an_unchanged_import_and_colour_helper():
    from pack_canonical_equipment import only_torso_mapping_changed
    before = "GAIN = 1\ndef backing_colour(): return GAIN\ndef remap(x=1): return x\n"
    after = before.replace("return x", "return x + 2")
    assert only_torso_mapping_changed(before, after)
    assert not only_torso_mapping_changed(before, after.replace("GAIN = 1", "GAIN = 2"))
    assert not only_torso_mapping_changed(before, after.replace("return GAIN", "return GAIN + 1"))
    assert not only_torso_mapping_changed(before, after.replace("x=1", "x=changed_default()"))
    assert not only_torso_mapping_changed(before, after.replace("def remap", "@side_effect()\ndef remap"))


def test_head_only_reuse_requires_the_head_guard_and_unchanged_shared_helpers():
    from pack_canonical_equipment import head_frame_is_guarded, only_function_body_changed, module_references_only
    before = 'def clip(x): return x\ndef head_frame(x): return x\n'
    after = before.replace('head_frame(x): return x', 'head_frame(x): return x + 1')
    assert only_function_body_changed(before, after, 'head_frame')
    assert not only_function_body_changed(before, after.replace('clip(x): return x', 'clip(x): return x * 2'), 'head_frame')
    guarded = 'def build(kind):\n is_head = kind in io.SOCKET_KIND\n if is_head:\n  return head_frame(kind)\n return clip(kind)\n'
    assert head_frame_is_guarded(guarded)
    assert not head_frame_is_guarded(guarded.replace(' if is_head:\n  return', ' if True:\n  return'))
    assert not head_frame_is_guarded(guarded.replace('kind in io.SOCKET_KIND', 'True'))
    assert module_references_only('import limb_head_remap\nx = limb_head_remap.clip(x)', 'limb_head_remap', {'clip'})
    assert not module_references_only('import limb_head_remap\nx = limb_head_remap.head_frame(x)', 'limb_head_remap', {'clip'})


def test_source_specific_reuse_rejects_any_change_beyond_the_low_tab_guard():
    from pack_canonical_equipment import only_low_ornament_guard_added
    before = 'def remap(points):\n for block in points:\n  wrist = [0., 0.]\n  source_height = 1.\n  out = block\n'
    guard = '  if block[:, 1].max() < wrist[1] - .16 * source_height:\n   continue\n'
    after = before.replace('  out = block', guard+'  out = block')
    assert only_low_ornament_guard_added(before, after)
    assert not only_low_ornament_guard_added(before, after.replace('.16', '.10'))
    assert not only_low_ornament_guard_added(before, after.replace('out = block', 'out = block * 2'))
    assert not only_low_ornament_guard_added(before, after.replace('source_height = 1.', 'source_height = 2.'))


def test_flat_double_sided_decoration_is_not_an_enclosing_volume():
    import garment_coverage as coverage
    flat = np.array([[0., 0., 0.], [.1, 0., 0.], [0., .1, 0.]])
    sheets = coverage.components(flat, np.array([[0, 1, 2], [2, 1, 0]]))
    assert len(sheets) == 1 and not sheets[0].closed
    # A very thin shell still encloses space, even when inverted. The winding
    # assertion must continue catching it after the planar-sheet correction.
    points = np.vstack([flat, [0., 0., .000001]]) + [0.2, 1.3, -0.1]
    faces = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]])
    positive = coverage.components(points, faces)[0]
    negative = coverage.components(points, faces[:, ::-1])[0]
    assert positive.closed and positive.volume > 0
    assert negative.closed and negative.volume < 0
