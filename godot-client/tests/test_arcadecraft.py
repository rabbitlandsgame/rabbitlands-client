"""Liquid scenery must preserve solid ground; bell shells must face outward."""
import sys
from pathlib import Path
import numpy as np

KIT = Path(__file__).resolve().parents[2] / "eloria-assets/maps/nymara-regions/_toolkit"
sys.path.insert(0, str(KIT))
from amberwood import arcadecraft as A, mesh as M
from amberwood.stonework import MeshGroup
from secrets_build import build_collision


def test_shallow_water_preserves_the_solid_grid_and_gate_cut():
    group = MeshGroup()
    for z in (-7, 7):
        group.add_walk(M.box((12, .4, 10), center=(0, -.2, z), material="ashlar"))
    group.add(M.box((1, 3, 5), center=(2, 1.5, -6), material="ashlar"))
    dry, _ = build_collision(group)
    water = M.quad([(-6,.32,-12),(-6,.32,12),(6,.32,12),(6,.32,-12)],material="water_pool")
    group.add(water)
    wet, _ = build_collision(group, non_blocking_materials=("water_pool",))
    assert wet == dry
    blocked, _ = build_collision(group)
    assert blocked != dry  # the explicit liquid policy is required
    # Dry equality covers the void between floors as well as the solid wall.


def test_bell_shell_geometric_faces_match_declared_normals():
    shell = A.hanging_bell().parts[0]
    faces = shell.indices.reshape(-1, 3)
    tri = shell.positions[faces]
    geometric = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    declared = shell.normals[faces].mean(axis=1)
    assert np.all(np.einsum("ij,ij->i",geometric,declared) > 0)


def test_crownwater_material_registration_is_append_only_and_repeatable():
    from amberwood import crownmaterials as C, materials as MAT
    original, lookup = MAT.SPECS, dict(MAT.BY_NAME)
    try:
        # Pre-populated texture sets exercise registration without regenerating
        # the large images already checked in the material migration audit.
        sets = {name: object() for name in C.TEXTURE_FACTORIES}
        C.register(sets)
        once = MAT.SPECS
        assert once[:len(original)] == original
        C.register(sets)
        assert MAT.SPECS == once
        assert len({s.name for s in once}) == len(once)
    finally:
        MAT.SPECS = original
        MAT.BY_NAME.clear()
        MAT.BY_NAME.update(lookup)
