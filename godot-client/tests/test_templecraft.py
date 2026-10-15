"""Opaque architectural and leaf discs must expose their intended front faces."""
import sys
from pathlib import Path
import numpy as np
import pytest

KIT = Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(KIT))
from amberwood import templecraft as T


@pytest.mark.parametrize("recipe", [T.sun_disc, T.lily_cluster])
def test_opaque_discs_face_outward(recipe):
    disc = recipe().parts[0]
    faces = disc.indices.reshape(-1, 3)
    triangles = disc.positions[faces]
    geometric = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    declared = disc.normals[faces].mean(axis=1)
    assert np.all(np.einsum("ij,ij->i", geometric, declared) > 0)
