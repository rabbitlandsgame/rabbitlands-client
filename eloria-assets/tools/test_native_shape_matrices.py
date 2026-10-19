"""Matrix-authored rigs retain their rest transform in the QA evaluator."""
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_motion.asset import write_glb
from video_motion.native_shapes import NativeShapeAsset


@pytest.mark.parametrize('scale', [(2., 3., 4.), (-2., 3., 4.)])
def test_matrix_rest_round_trip_without_changing_source(tmp_path, scale):
    matrix = np.eye(4)
    matrix[:3, :3] = Rotation.from_euler('xyz', [.3, -.5, .2]).as_matrix() * scale
    matrix[:3, 3] = [1, 2, 3]
    document = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
                'nodes': [{'name': 'parent', 'matrix': matrix.T.ravel().tolist(), 'children': [1]},
                          {'name': 'child', 'translation': [0, 1, 0]}], 'animations': []}
    path = tmp_path / 'matrix.glb'
    write_glb(path, document, b'')
    # The evaluator supports empty rigs through a minimal harmless mesh part.
    from unittest.mock import patch
    with patch.object(NativeShapeAsset, 'skin', return_value=np.zeros((1, 3))):
        asset = NativeShapeAsset(path)
    assert np.allclose(asset.rest[0], matrix, atol=1e-12)
    child = np.eye(4)
    child[1, 3] = 1
    assert np.allclose(asset.rest[1], matrix @ child, atol=1e-12)
    assert asset.d['nodes'] == document['nodes']


@pytest.mark.parametrize('kind', ['singular', 'sheared'])
def test_unsupported_matrix_rest_is_rejected(tmp_path, kind):
    matrix = np.eye(4)
    matrix[0, 0] = 0 if kind == 'singular' else 1
    if kind == 'sheared': matrix[0, 1] = .2
    path = tmp_path / 'bad.glb'
    write_glb(path, {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 0}],
                     'nodes': [{'matrix': matrix.T.ravel().tolist()}], 'animations': []}, b'')
    with pytest.raises(ValueError, match=kind.capitalize()):
        NativeShapeAsset(path)
