"""Raw-node correspondence cannot bypass complete original payload checks."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from video_motion import blender_vertex_identity as identity


class Rows:
    def __init__(self, values, weight=1.0):
        self.values = np.asarray(values, np.float32)
        self.weight = weight

    def __len__(self):
        return len(self.values)

    def foreach_get(self, name, target):
        target[:] = self.values.ravel()

    def __iter__(self):
        for index in range(len(self.values)):
            yield NS(index=index, groups=[NS(group=0, weight=self.weight)])


def bind(monkeypatch, *, bad_basis=False, bad_uv=False, bad_skin=False,
         bad_shape=False, original_rest=False):
    positions = np.array([[.1, .2, .3], [.3, .4, .5], [.7, .8, .9]], np.float32)
    uv = np.array([[.1, .2], [.3, .4], [.5, .6]], np.float32)
    delta = np.full((3, 3), .01, np.float32)
    arrays = {0: positions, 1: np.zeros((3, 4)),
              2: np.tile([1., 0., 0., 0.], (3, 1)), 3: uv, 4: delta}
    primitive = {"attributes": {"POSITION": 0, "JOINTS_0": 1,
                               "WEIGHTS_0": 2, "TEXCOORD_0": 3},
                 "targets": [{"POSITION": 4}]}
    doc = {"accessors": [{"count": 3}] * 5,
           "nodes": [{"name": "Bone"}, {"mesh": 0, "skin": 0, "name": "Mesh"}],
           "skins": [{"joints": [0]}], "meshes": [{"primitives": [primitive]}]}
    monkeypatch.setattr(identity, "document", lambda path: (doc, b""))
    monkeypatch.setattr(identity, "array", lambda d, b, index: arrays[index].astype(float))
    frame = np.tile(np.eye(4), (3, 1, 1)); frame[:, 1, 3] = .02
    monkeypatch.setattr(identity, "source_frames", lambda *args: frame)
    raw = positions @ identity._C.T
    if original_rest:
        raw += np.array([0., .02, 0.]) @ identity._C.T
    actual = raw.copy(); actual[0, 0] += .001 if bad_basis else 0
    actual_uv = uv.copy(); actual_uv[:, 1] = 1 - actual_uv[:, 1]
    actual_uv[0, 0] += .01 if bad_uv else 0
    shape = raw + delta @ identity._C.T
    shape[0, 0] += .01 if bad_shape else 0
    keys = NS(key_blocks=[NS(data=Rows(raw)), NS(data=Rows(shape))], as_pointer=lambda: 8)
    data = NS(vertices=Rows(actual, .5 if bad_skin else 1.), loops=Rows([0, 1, 2]),
              uv_layers=[NS(data=Rows(actual_uv))], shape_keys=keys)
    ob = NS(type="MESH", name="Mesh", as_pointer=lambda: 1, matrix_world=np.eye(4),
            data=data, vertex_groups=[NS(name="Bone")])
    return identity.imported_bindings("unused", [ob])


def test_raw_node_basis_is_proved_and_recorded(monkeypatch):
    _, _, records = bind(monkeypatch)
    assert records[0]["basis_strategy"] == "authored_mesh_node_raw_basis"
    assert records[0]["authored_rest_skin_component_error"] > .019
    assert records[0]["all_target_position_error"] < 1e-7


def test_primary_rest_basis_keeps_priority(monkeypatch):
    _, _, records = bind(monkeypatch, original_rest=True)
    assert records[0]["basis_strategy"] == "authored_joint_rest_skin"


@pytest.mark.parametrize("mutation", ["bad_basis", "bad_uv", "bad_skin", "bad_shape"])
def test_raw_basis_never_accepts_changed_payload(monkeypatch, mutation):
    with pytest.raises(AssertionError):
        bind(monkeypatch, **{mutation: True})
