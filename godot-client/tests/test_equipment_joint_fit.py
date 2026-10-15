"""Equipment shafts follow the regenerated body, including its curved calves."""

import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eloria-assets/tools"))
import equipment_joint_fit as fit

REGISTRY = json.loads((ROOT / "godot-client/data/actors/equipment.json").read_text())


def piece_path(key, sex):
    scene = REGISTRY["models"][key]["variants"]["canonical_human_" + sex]["scene"]
    return ROOT / "godot-client" / scene.removeprefix("res://")


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize(
    "key,upper,tolerance", [("4:230", 0.45, 0.012), ("6:226", 0.23, 0.005)]
)
def test_ranger_shaft_follows_the_body_surface(sex, key, upper, tolerance):
    """The reported 60–85 mm trouser and 20 mm boot offsets must not return."""
    d, b = fit.ea.read_glb(piece_path(key, sex))
    primitive = d["meshes"][0]["primitives"][0]
    points = fit.ea.accessor_array(d, b, primitive["attributes"]["POSITION"])
    faces = fit.ea.accessor_array(d, b, primitive["indices"]).reshape(-1, 3)
    labels = fit.limbs.components(points, faces)
    levels = np.linspace(0.14, upper, 12)
    for side, sign in [("l", 1), ("r", -1)]:
        candidates = np.unique(labels[points[:, 0] * sign > 0])
        shell = max(
            candidates,
            key=lambda label: np.count_nonzero(
                (labels == label) & (points[:, 0] * sign > 0)
            )
            * np.ptp(points[(labels == label) & (points[:, 0] * sign > 0), 1]),
        )
        own = (labels[faces] == shell).all(1) & (points[faces, 0].mean(1) * sign > 0)
        actual = fit.sections(points, faces[own], levels)
        body = fit.body_sections(fit.rig_for(sex), side, levels)
        assert np.isfinite(actual).all()
        assert np.linalg.norm(actual - body, axis=1).mean() < tolerance


def test_complete_lower_catalog_has_the_joint_fit():
    """Both body variants are installed for every canonical lower garment."""
    count = 0
    for key, model in REGISTRY["models"].items():
        if model.get("fitProfile") != "canonical" or not key.startswith(("4:", "6:")):
            continue
        for sex in ["male", "female"]:
            d, _ = fit.ea.read_glb(piece_path(key, sex))
            assert d["asset"]["extras"]["shaftFitVersion"] == fit.FIT_VERSION
            count += 1
    assert count == 272


@pytest.mark.parametrize("slug", ["luminous_female", "glasswarden_female"])
def test_sparse_spine_weights_still_measure_the_waist(slug):
    rig = fit.ea.load_rig(ROOT / f"godot-client/assets/actors/native/races/{slug}.glb")
    index = rig.joint_names.index("spine_01")
    assert (rig.weights * (rig.joints == index)).sum() < 1.0
    measured = fit.ea.body_girth(rig, ["spine_01"])
    assert 0.08 < measured["spine_01"] < 0.20
    assert REGISTRY["bodyGirth"][slug]["spine_01"] == measured["spine_01"]


@pytest.mark.parametrize("key", ["4:179", "4:230", "6:226"])
def test_a_rebuild_never_applies_a_second_shift(key, tmp_path):
    target = tmp_path / "again.glb"
    report = fit.revise(
        piece_path(key, "male"),
        target,
        "male",
        "legs" if key.startswith("4:") else "boots",
    )
    assert report["changedVertices"] == 0
    assert not target.exists()


def test_short_ornaments_travel_whole_and_soling_stays_fixed():
    # Two disconnected decorative plates span a region with a varying field.
    # Each keeps its shape; the rigid sole and waist outside that band stay put.
    points = np.array(
        [[x, y, z] for x in [-0.01, 0.025] for y in [0.30, 0.46] for z in [-0.02, 0.01]]
    )
    faces = np.array(
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
    plates = np.vstack([points, points * [-1, 1, 1]])
    plate_faces = np.vstack([faces, faces[:, ::-1] + 8])
    maps = {
        s: np.column_stack(
            [
                np.linspace(0.01, 0.03, len(fit.LEVELS)),
                np.linspace(-0.02, -0.07, len(fit.LEVELS)),
            ]
        )
        for s in ["l", "r"]
    }
    maps["r"][:, 0] *= -1
    moved = fit.apply(plates, plate_faces, maps)
    for offset in [0, 8]:
        np.testing.assert_allclose(
            moved[offset : offset + 8] - moved[offset],
            plates[offset : offset + 8] - plates[offset],
        )
    np.testing.assert_array_equal(moved[:, 1], plates[:, 1])
    for y in [0.02, 0.70]:
        fixed = plates.copy()
        fixed[:, 1] = y + (fixed[:, 1] - 0.30) * 0.1
        np.testing.assert_array_equal(fit.apply(fixed, plate_faces, maps), fixed)
