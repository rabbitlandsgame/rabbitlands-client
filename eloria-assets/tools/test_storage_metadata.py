import numpy as np
import pytest
from test_crystalback_correctives import source_fixture
from video_motion.asset import read_glb
from video_motion.storage_metadata import remap_witness, remap_vertex_fields, vertex_permutation


def test_partial_prefix_zero_columns_are_removed_without_reinventing_observations(tmp_path):
    source, profile = source_fixture(tmp_path)
    d, _ = read_glb(source)
    witness = {'sha256': profile['source_sha256'], 'surface_vertex_ids': [4],
               'surface_source_morph_positions': [[[1, 2, 3], [0, 0, 0]]],
               'surface_skin_influences': [{'Root': 1.}], 'surface_rest': [[9, 8, 7]],
               'clips': {'Walk': [{'time': .123, 'bones': {'Root': [1, 2, 3]},
                                    'surface': [[4, 5, 6]], 'morph_weights': {'1': [1, 0, .25]}}]}}
    prune = {'meshes': [{'mesh': 0, 'targets_before': 3, 'targets_after': 2,
                         'removed_target_indices': [1], 'retained_target_indices': [0, 2]}]}
    result = remap_witness(witness, d, prune, None, profile['source_sha256'], 'f' * 64)
    assert result['surface_source_morph_positions'] == [[[1, 2, 3]]]
    assert result['clips']['Walk'][0]['morph_weights']['1'] == [1, .25]
    assert result['clips']['Walk'][0]['surface'] == [[4, 5, 6]]
    assert result['surface_rest'] == witness['surface_rest']
    assert witness['sha256'] == profile['source_sha256']


def test_partition_remaps_physical_ids_but_not_bone_ids_or_coordinates(tmp_path):
    source, profile = source_fixture(tmp_path); d, _ = read_glb(source)
    partition = {'new_node': 3, 'all_candidate_original_vertex_ids': [0, 3, 4, 1, 2, 5]}
    inverse = vertex_permutation(d, partition)
    metadata = {'sole_vertices': {'left': [1, 2]}, 'primary_joint_ids': [1, 2], 'surface_rest': [[1, 2, 3]]}
    result = remap_vertex_fields(metadata, inverse)
    assert result['sole_vertices']['left'] == [3, 4]
    assert result['primary_joint_ids'] == [1, 2]
    assert result['surface_rest'] == [[1, 2, 3]]
    bad = {'all_candidate_original_vertex_ids': [0, 0, 1, 2, 3, 4]}
    with pytest.raises(ValueError): vertex_permutation(d, bad)


def test_immutable_reference_hash_must_match(tmp_path):
    source, _ = source_fixture(tmp_path); d, _ = read_glb(source)
    with pytest.raises(ValueError): remap_witness({'sha256': 'a' * 64}, d, {}, None, 'b' * 64, 'c' * 64)


def test_multi_owner_binding_remap_keeps_original_surface_observations(tmp_path):
    source, base_profile = source_fixture(tmp_path); d,_ = read_glb(source)
    d['nodes'].append({'name':'OtherBone'});d['skins'][0]['joints'].append(3)
    profile = {'source_node':1,'vertex_ids':[3,4,5],'mode':'rigid','owner_joints':[0,1,1]}
    partition = {'new_node':4,'all_candidate_original_vertex_ids':list(range(6))}
    witness = {'sha256':base_profile['source_sha256'],'surface_vertex_ids':[2,3,4,5],
        'surface_skin_influences':[{'Root':1.}]*4,'surface_rest':[[7,8,9]]*4,
        'clips':{'Walk':[{'time':.25,'surface':[[1,2,3]]*4}]}}
    after = remap_witness(witness,d,{},partition,witness['sha256'],'f'*64,profile)
    assert after['surface_skin_influences'] == [{'Root':1.},{'Root':1.},{'OtherBone':1.},{'OtherBone':1.}]
    assert after['surface_rest'] == witness['surface_rest'] and after['clips'] == witness['clips']
