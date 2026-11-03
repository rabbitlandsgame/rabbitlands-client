"""Lining visibility masks (actor LOD plan C3): helpers, mask files and the Blender ray casts.

The Blender tests run background Blender (skipped when it is not installed):
an analytic fixture checks the ray casts exactly, including back-face culling,
pass-through and alpha; a real boot checks the posed skinning against
Blender's own deformation and that two runs write byte-identical masks.
"""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lining_visibility as lv  # noqa: E402

BOOTS = lv.VARIANTS / "human_male/arcane_fantasy_boots_02.glb"
CUIRASS = lv.VARIANTS / "human_male/amberwood_woodland_cuirass_02.glb"


def _blender():
    try:
        return lv.find_blender()
    except SystemExit:
        return None


needs_blender = pytest.mark.skipif(_blender() is None, reason="Blender is not installed")


# ----------------------------------------------------------------- helpers

def test_bits_round_trip_and_rejections():
    rng = np.random.default_rng(3)
    for count in (0, 1, 7, 8, 9, 17, 1000):
        mask = rng.random(count) < 0.4
        assert np.array_equal(lv.unpack_bits(lv.pack_bits(mask), count), mask)
    text = lv.pack_bits(np.ones(9, bool))
    with pytest.raises(ValueError):
        lv.unpack_bits(text, 17)          # too few bytes
    with pytest.raises(ValueError):
        lv.unpack_bits(text, 8)           # a bit set past the count


def test_run_count():
    assert lv.run_count(np.array([], bool)) == 0
    assert lv.run_count(np.array([1, 1, 0, 1, 0, 0, 1, 1], bool)) == 3
    assert lv.run_count(np.array([0, 0], bool)) == 0


def test_directions_cover_the_sphere():
    dirs = lv.fibonacci_directions(128)
    assert dirs.shape == (128, 3)
    assert np.allclose(np.linalg.norm(dirs, axis=1), 1.0)
    assert np.abs(dirs.mean(axis=0)).max() < 0.02
    upper = lv.upper_flags(dirs, -10.0)
    assert abs(upper.mean() - (1 + math.sin(math.radians(10))) / 2) < 0.02
    # the largest angular gap between neighbours stays near the even spacing
    cos = dirs @ dirs.T
    np.fill_diagonal(cos, -1)
    assert math.degrees(math.acos(cos.max(axis=1).min())) < 25.0


def test_subdivision_samples_lie_inside_and_cover():
    for k in range(1, 6):
        bary = lv.subdivision_barycentrics(k)
        assert bary.shape == (k * k, 3)
        assert np.allclose(bary.sum(axis=1), 1.0) and (bary > 0).all()
        assert np.allclose(bary.mean(axis=0), 1.0 / 3.0)
    corners = np.array([[[0, 0, 0], [0.01, 0, 0], [0, 0.01, 0]],      # small: centroid only
                        [[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], float)  # 10 cm: 4 x 4
    owner, bary = lv.sample_plan(corners, 0.03, 4)
    assert np.bincount(owner).tolist() == [1, 16]
    points = lv.apply_samples(corners, owner, bary)
    assert np.allclose(points[0], corners[0].mean(axis=0))


def _grid(nx, nz, x0, x1, z0, z1, y=0.0):
    xs, zs = np.linspace(x0, x1, nx + 1), np.linspace(z0, z1, nz + 1)
    positions = np.array([[x, y, z] for z in zs for x in xs], float)
    tris = []
    for j in range(nz):
        for i in range(nx):
            a, b = j * (nx + 1) + i, j * (nx + 1) + i + 1
            c, d = a + nx + 1, b + nx + 1
            tris += [[a, c, b], [b, c, d]]       # counter-clockwise seen from +Y
    return positions, np.array(tris, np.int64)


def test_margin_rules_match_brute_force():
    positions, tris = _grid(30, 4, 0.0, 0.3, 0.0, 0.04)
    corners = positions[tris]
    visible = corners[:, :, 0].max(axis=1) <= 0.01 + 1e-9    # the first column, x = 0..0.01
    centre = corners.mean(axis=1)
    for margin in (0.0, 0.015, 0.05):
        keep = lv.keep_with_margin(corners, visible, margin, "centroid")
        distance = np.linalg.norm(centre[:, None] - centre[visible][None], axis=2).min(axis=1)
        assert np.array_equal(keep, visible | (distance <= margin) if margin > 0 else visible)
        surface = lv.keep_with_margin(corners, visible, margin, "surface")
        assert (surface >= keep).all()             # surface distance never exceeds centroid distance
        if margin > 0:
            near = corners[:, :, 0].min(axis=1) <= 0.01 + margin - lv.MARGIN_SPACING_M
            far = corners[:, :, 0].min(axis=1) > 0.01 + margin + lv.MARGIN_SPACING_M
            assert surface[near].all() and not surface[far].any()
    with pytest.raises(ValueError):
        lv.keep_with_margin(corners, visible, 0.01, "nearest")


def test_pose_recipes():
    assert lv.parse_pose("bind") == {"name": "bind", "kind": "bind"}
    walk = lv.parse_pose("Walk@0.25")
    assert walk["kind"] == "clip" and walk["clip"] == "Walk" and walk["at"] == 0.25
    horse = lv.parse_pose("mount:golden_plains_horse")
    profile = json.loads((lv.MOUNTS / "golden_plains_horse.json").read_text(encoding="utf-8"))
    assert horse["rider"]["foot"] == profile["footOffsetMetres"]
    assert horse["rider"]["lean_deg"] == float(profile["pelvisLeanDegrees"])
    for bad in ("Walk", "Walk@1.5", "@0.5"):
        with pytest.raises(ValueError):
            lv.parse_pose(bad)
    with pytest.raises(ValueError):
        lv.resolve_poses(["bind", "bind"])


def test_pose_sets_use_real_clips_and_review_is_unsampled():
    clips = lv.library_clips()
    for names in (lv.POSES_V1, lv.REVIEW_POSES, lv.SHEET_POSES):
        for recipe in lv.resolve_poses(list(names)):
            if "clip" in recipe:
                assert recipe["clip"] in clips, recipe["name"]
    assert lv.POSES_V1[0] == "bind"
    assert not set(lv.REVIEW_POSES) & set(lv.POSES_V1)
    assert set(lv.SHEET_POSES) <= set(lv.POSES_V1)


def test_samples_name_lining_garments():
    for name in lv.SAMPLES:
        for path in lv.sample_paths(name):
            assert path.exists(), path
            assert lv.lining_names(lv.read_glb_json(path)), path
    assert len(lv.SAMPLES["review"]) == 20 and len(lv.SAMPLES["sheets"]) == 6
    assert set(lv.SAMPLES["sheets"]) <= set(lv.SAMPLES["review"])


def test_garment_parts_of_a_real_cuirass():
    document, blob = lv.read_glb(CUIRASS)
    parts = lv.garment_parts(document, blob)
    by = {p["mesh"]: p for p in parts}
    assert set(by) == {"Mossbound Coat", "GeneratedArmorBacking"}
    lining = by["GeneratedArmorBacking"]
    assert lining["lining"] and not by["Mossbound Coat"]["lining"]
    assert len(lining["triangles"]) == 14956 and lining["triangles"].max() < len(lining["positions"])
    assert lining["double_sided"] and by["Mossbound Coat"]["double_sided"]
    assert np.allclose(lining["weights"].sum(axis=1), 1.0)
    assert len(lining["skin_joints"]) == 77 and lining["joints"].max() < 77
    checks = lv.check_centroids(lv.triangle_corners(lining["positions"], lining["triangles"]))
    assert len(checks) == lv.CHECK_TRIANGLES and checks[0][0] == 0 and checks[-1][0] == 14955


def test_forearm_skin_is_never_trusted_double_sided():
    document, blob = lv.read_glb(lv.VARIANTS / "human_male/eloria_frontier_shirt_01.glb")
    by = {p["mesh"]: p for p in lv.garment_parts(document, blob)}
    assert not by["EquipmentForearmSkin"]["double_sided"]


def test_discover_and_balance():
    found = lv.discover()
    assert BOOTS in found and CUIRASS in found
    assert all(lv.lining_names(lv.read_glb_json(p)) for p in found[:20])
    jobs = [{"path": str(i), "cost": c} for i, c in enumerate([90, 10, 40, 40, 30, 20])]
    bins = lv.balance(jobs, 2)              # longest first: 90+20+10 | 40+40+30
    assert sorted(sorted(j["cost"] for j in b) for b in bins) == [[10, 20, 90], [30, 40, 40]]
    assert len(lv.balance(jobs, 9)) == 6


def test_plan_reuses_only_current_records(tmp_path):
    settings, poses = dict(lv.DEFAULT_SETTINGS), lv.resolve_poses(["bind"])
    inputs = {"tool_sha256": "a"}
    jobs, reused = lv.plan_visibility([BOOTS], tmp_path, settings, poses, inputs)
    assert len(jobs) == 1 and not reused and jobs[0]["cost"] == 4568 + 4476
    record = {"schema": lv.SCHEMA, "policy": lv.POLICY, "source": {"sha256": jobs[0]["sha256"]},
              "settings_sha256": lv.json_sha256({"settings": settings, "poses": poses}), "inputs": inputs}
    target = lv.visibility_path(tmp_path, BOOTS)
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(record), encoding="utf-8")
    assert lv.plan_visibility([BOOTS], tmp_path, settings, poses, inputs)[1] == [BOOTS]
    assert lv.plan_visibility([BOOTS], tmp_path, settings, poses, {"tool_sha256": "b"})[0]
    assert lv.plan_visibility([BOOTS], tmp_path, dict(settings, directions=64), poses, inputs)[0]
    assert lv.plan_visibility([BOOTS], tmp_path, settings, poses, inputs, force=True)[0]


def test_png_writer(tmp_path):
    image = np.zeros((3, 5, 3), np.uint8)
    image[1, 2] = (255, 10, 20)
    lv.write_png(tmp_path / "a.png", image)
    PIL = pytest.importorskip("PIL.Image")
    assert np.array_equal(np.asarray(PIL.open(tmp_path / "a.png").convert("RGB")), image)


def test_pose_gains_follow_cast_order():
    docs = {"a": {"poses": ["bind", "Walk@0", "mount:x"], "linings": {
        "L": {"new_visible_by_pose": {"bind": 5, "Walk@0": 2, "mount:x": 0}},
        "M": {"new_visible_by_pose": {"bind": 1, "Walk@0": 0, "mount:x": 3}}}}}
    gains = lv.pose_gains(docs)
    assert gains == [["bind", 6], ["Walk@0", 2], ["mount:x", 3]]
    assert "| mount:x | 3 |" in lv.pose_gains_markdown(gains)


def test_reports():
    rows = lv.summarise({"human_male/x": {"linings": {"GeneratedLegBacking": {
        "triangles": 100, "counts": {"visible": 20, "visible_upper": 10, "visible_bind": 15, "keep": 40,
                                     "keep_upper": 30, "keep_bind": 35}, "runs": {"keep": 3}}}}},
        {"x.glb": {"GeneratedLegBacking": {"tris": 100, "sphere_visible": 18, "sphere_hidden_margin2cm": 50,
                                           "upper_hidden_margin2cm": 60}}})
    assert rows[0]["removable"] == 60 and rows[0]["e4_removable"] == 50 and rows[0]["removable_bind"] == 65
    assert "60%" in lv.summary_markdown(rows)
    review = [{"garment": "g", "lining": "L", "variant": v, "triangles": 10, "removed": r, "changed_px": c,
               "lining_px": 5, "garment_px": 9, "views": 2} for v, r, c in (("mask", 4, 0), ("e4", 6, 3))]
    text = lv.review_markdown(review)
    assert "40% / 0" in text and "60% / 3" in text


# --------------------------------------------------------- fixture garments

def _material(name, double_sided, alpha="OPAQUE"):
    return {"name": name, "doubleSided": double_sided, "alphaMode": alpha}


def _pack_glb(path, document, blob):
    text = json.dumps(document).encode("utf-8")
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


def write_fixture(path, lining_double_sided=False, shells=((1.0, True, "OPAQUE", False),), extras=None,
                  lining_y=0.99, joint=None):
    """A static garment: shell sheet(s) over a single-sided lining sheet.

    The lining sheet sits at y = ``lining_y`` (0.99) over x -1..1.5,
    z -0.5..0.5, facing +Y; each shell is a 2 x 2 m sheet at height ``y``
    (double-sided or not, alpha mode, flipped to face -Y).  ``extras`` maps a
    mesh name to its glTF mesh extras.  ``joint`` = (rest translation, bind
    translation) skins every sheet fully to one joint node.
    """
    document = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                "materials": [], "accessors": [], "bufferViews": [], "buffers": [{"byteLength": 0}]}
    blob = bytearray()

    def add(array, kind, component, target):
        data = np.ascontiguousarray(array).tobytes()
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        document["bufferViews"].append(view)
        blob.extend(data + b"\0" * (-len(data) % 4))
        spec = {"bufferView": len(document["bufferViews"]) - 1, "componentType": component,
                "count": len(array), "type": kind}
        if kind == "VEC3":
            spec.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        document["accessors"].append(spec)
        return len(document["accessors"]) - 1

    if joint is not None:
        rest, bind = joint
        document["nodes"].append({"name": "root", "translation": list(rest)})
        document["scenes"][0]["nodes"].append(0)
        inverse = np.eye(4, dtype=np.float32)
        inverse[:3, 3] = -np.asarray(bind, np.float32)
        document["skins"] = [{"joints": [0], "inverseBindMatrices": add(inverse.T.reshape(1, 16), "MAT4", 5126, None)}]

    def mesh(name, positions, tris, material):
        document["materials"].append(material)
        attributes = {"POSITION": add(positions.astype(np.float32), "VEC3", 5126, 34962)}
        if joint is not None:
            attributes["JOINTS_0"] = add(np.zeros((len(positions), 4), np.uint8), "VEC4", 5121, 34962)
            weights = np.zeros((len(positions), 4), np.float32)
            weights[:, 0] = 1.0
            attributes["WEIGHTS_0"] = add(weights, "VEC4", 5126, 34962)
        entry = {"name": name, "primitives": [{
            "attributes": attributes, "indices": add(tris.astype(np.uint32).ravel(), "SCALAR", 5125, 34963),
            "material": len(document["materials"]) - 1}]}
        if extras and name in extras:
            entry["extras"] = extras[name]
        document["meshes"].append(entry)
        node = {"name": name, "mesh": len(document["meshes"]) - 1}
        if joint is not None:
            node["skin"] = 0
        document["nodes"].append(node)
        document["scenes"][0]["nodes"].append(len(document["nodes"]) - 1)

    for index, (y, double_sided, alpha, flipped) in enumerate(shells):
        positions, tris = _grid(1, 1, -1.0, 1.0, -1.0, 1.0, y)
        if flipped:
            tris = tris[:, [0, 2, 1]]
        mesh(f"Shell{index}", positions, tris, _material(f"Shell{index}", double_sided, alpha))
    positions, tris = _grid(25, 5, -1.0, 1.5, -0.5, 0.5, lining_y)
    mesh("GeneratedTestBacking", positions, tris, _material("Backing", lining_double_sided))
    document["buffers"][0]["byteLength"] = len(blob)
    return _pack_glb(path, document, blob)


def rewrite_json(source, target, edit):
    """A copy of a GLB with its JSON edited and the BIN chunk unchanged (build-tree bytes)."""
    document, blob = lv.read_glb(source)
    edit(document)
    return _pack_glb(target, document, blob)


def visibility_record(glb, visible_of):
    """A visibility record as the Blender worker writes it, from ``visible_of(corners)`` (no Blender)."""
    document, blob = lv.read_glb(glb)
    linings = {}
    for part in lv.garment_parts(document, blob):
        if not part["lining"]:
            continue
        corners = lv.triangle_corners(part["positions"], part["triangles"])
        visible = np.asarray(visible_of(corners), bool)
        linings[part["mesh"]] = {
            "mesh": part["mesh"], "primitive": part["primitive"], "triangles": len(corners),
            "vertices": len(part["positions"]), "double_sided": part["double_sided"], "material": part["material"],
            "gltf_index_sha256": lv.index_digest(part["triangles"]), "check": lv.check_centroids(corners),
            "samples": len(corners), "rays": 0, "new_visible_by_pose": {"bind": int(visible.sum())},
            "visible": lv.pack_bits(visible), "visible_upper": lv.pack_bits(visible),
            "visible_bind": lv.pack_bits(visible),
            "counts": {"visible": int(visible.sum()), "visible_upper": int(visible.sum()),
                       "visible_bind": int(visible.sum())}, "runs": {}}
    return {"schema": lv.SCHEMA, "policy": lv.POLICY,
            "source": {"path": lv.res_path(glb), "sha256": lv.file_sha256(glb), "bytes": glb.stat().st_size},
            "inputs": {"tool_sha256": "test"}, "settings": {}, "settings_sha256": "test", "poses": ["bind"],
            "occluders": [], "linings": linings}


def _first_column(corners):
    return corners[:, :, 0].max(axis=1) <= -0.9 + 1e-5     # float32 positions


def analytic_visible(directions, shell_y=1.0):
    """Centroids of the fixture lining that see past the 2 x 2 m shell sheet."""
    positions, tris = _grid(25, 5, -1.0, 1.5, -0.5, 0.5, 0.99)
    centre = positions[tris].mean(axis=1)
    up = directions[directions[:, 1] > 1e-9]
    t = (shell_y - 0.99) / up[:, 1]
    x = centre[:, 0, None] + t[None] * up[None, :, 0]
    z = centre[:, 2, None] + t[None] * up[None, :, 2]
    return ((np.abs(x) > 1.0) | (np.abs(z) > 1.0)).any(axis=1)


def test_fixture_reads_back(tmp_path):
    glb = write_fixture(tmp_path / "f.glb")
    parts = lv.garment_parts(*lv.read_glb(glb))
    assert [p["mesh"] for p in parts] == ["Shell0", "GeneratedTestBacking"]
    lining = parts[1]
    assert lining["lining"] and not lining["double_sided"] and lining.get("rigid") is None
    normals = lv.face_normals(lv.triangle_corners(lining["positions"], lining["triangles"]))
    assert np.allclose(normals, [0, 1, 0])
    expected = analytic_visible(lv.fibonacci_directions(64))
    assert 0 < expected.sum() < len(expected)       # the case is not trivial


def test_runtime_shader_extras_make_a_lining_double_sided(tmp_path):
    # repairQuiltPaint / matchAntlerPalette swap the mesh's materials for a
    # cull_disabled shader at runtime, so such a lining draws its back faces.
    glb = write_fixture(tmp_path / "quilt.glb", shells=((1.0, False, "OPAQUE", False),),
                        extras={"GeneratedTestBacking": {"repairQuiltPaint": True},
                                "Shell0": {"matchAntlerPalette": True}})
    by = {p["mesh"]: p for p in lv.garment_parts(*lv.read_glb(glb))}
    assert by["GeneratedTestBacking"]["double_sided"]
    assert not by["Shell0"]["double_sided"]        # occluders keep their glTF sidedness (conservative)
    plain = {p["mesh"]: p for p in lv.garment_parts(*lv.read_glb(write_fixture(tmp_path / "plain.glb")))}
    assert not plain["GeneratedTestBacking"]["double_sided"]


def test_finalise_keeps_the_cached_record_and_check_binds_build_tree_bytes(tmp_path):
    glb = write_fixture(tmp_path / "f.glb")
    visibility = visibility_record(glb, _first_column)
    before = json.dumps(visibility, sort_keys=True)
    mask = lv.finalise(visibility, glb, 0.02, "surface")
    assert json.dumps(visibility, sort_keys=True) == before     # the cached record is not modified
    entry = mask["linings"]["GeneratedTestBacking"]
    assert entry["counts"]["visible"] < entry["counts"]["keep"] < entry["triangles"]
    assert entry["keep_bind"] == entry["keep"] and not lv.check_mask(mask, glb)
    mask_file = tmp_path / "f.lining.json"
    mask_file.write_text(json.dumps(mask, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    # build-tree bytes (same geometry, other bytes) bind by geometry only when asked to
    build = rewrite_json(glb, tmp_path / "build.glb", lambda d: d["asset"].update(generator="build tree"))
    problems = lv.check_mask(mask, build)
    assert len(problems) == 1 and "sha256" in problems[0]
    assert not lv.check_mask(mask, build, rewritten=True)
    assert lv.main(["check", str(mask_file), str(build)]) == 1
    assert lv.main(["check", str(mask_file), str(build), "--rewritten"]) == 0
    # moved geometry is caught even then (1 mm, over the 0.1 mm check tolerance)
    moved = write_fixture(tmp_path / "moved.glb", lining_y=0.991)
    assert any("centroid" in p for p in lv.check_mask(mask, moved, rewritten=True))
    # the bind-pose bitsets are validated too
    broken = json.loads(json.dumps(mask))
    bad = broken["linings"]["GeneratedTestBacking"]
    bad["visible_bind"] = lv.pack_bits(np.ones(bad["triangles"], bool))
    problems = lv.check_mask(broken)
    assert any("visible_bind is not inside visible" in p for p in problems)
    assert any("not in keep_bind" in p for p in problems)


def test_finalise_into_a_fresh_folder_reports_missing_records(tmp_path):
    glb = write_fixture(tmp_path / "f.glb")
    out = tmp_path / "fresh" / "out"
    assert lv.main(["finalise", str(glb), "--out", str(out)]) == 1
    assert (out / "summary.md").exists() and not lv.mask_path(out, glb).exists()


def test_skin_bind_pose_must_be_the_rest_pose(tmp_path):
    good = write_fixture(tmp_path / "good.glb", joint=((0.0, 0.5, 0.0), (0.0, 0.5, 0.0)))
    bad = write_fixture(tmp_path / "bad.glb", joint=((0.0, 0.5, 0.0), (0.0, 0.0, 0.0)))
    assert lv.skin_rest_deviation(*lv.read_glb(good)) < 1e-6
    assert lv.skin_rest_deviation(*lv.read_glb(bad)) == pytest.approx(0.5)
    assert all("joints" in p for p in lv.garment_parts(*lv.read_glb(good)))
    mask = lv.finalise(visibility_record(good, _first_column), good)
    assert not lv.check_mask(mask, good)
    assert any("bind pose" in p for p in lv.check_mask(mask, bad, rewritten=True))
    assert lv.skin_rest_deviation(*lv.read_glb(CUIRASS)) < lv.BIND_REST_TOLERANCE


def _masks(tmp_path, glbs, *extra):
    out = tmp_path / "out"
    code = lv.main(["masks", *map(str, glbs), "--out", str(out), "--workers", "1", *extra])
    return code, out


@needs_blender
def test_blender_fixture_matches_analytic_visibility(tmp_path):
    cases = {
        "plain": write_fixture(tmp_path / "plain.glb"),
        "lining_two_sided": write_fixture(tmp_path / "lining_two_sided.glb", lining_double_sided=True),
        "shell_culled": write_fixture(tmp_path / "shell_culled.glb", shells=((1.0, False, "OPAQUE", True),)),
        "shell_front": write_fixture(tmp_path / "shell_front.glb", shells=((1.0, False, "OPAQUE", False),)),
        "shell_alpha": write_fixture(tmp_path / "shell_alpha.glb", shells=((1.0, True, "BLEND", False),)),
        "two_culled": write_fixture(tmp_path / "two_culled.glb",
                                    shells=((1.0, False, "OPAQUE", True), (1.2, False, "OPAQUE", True))),
    }
    code, out = _masks(tmp_path, cases.values(), "--poses", "bind", "--directions", "64", "--spacing-m", "10")
    assert code == 0
    expected = analytic_visible(lv.fibonacci_directions(64))
    every = np.ones_like(expected)
    for name, wanted in (("plain", expected), ("shell_front", expected), ("lining_two_sided", every),
                         ("shell_culled", every), ("shell_alpha", every), ("two_culled", every)):
        mask = json.loads(lv.mask_path(out, cases[name]).read_text(encoding="utf-8"))
        entry = mask["linings"]["GeneratedTestBacking"]
        visible = lv.unpack_bits(entry["visible"], entry["triangles"])
        assert np.array_equal(visible, wanted), name
        assert np.array_equal(lv.unpack_bits(entry["visible_bind"], entry["triangles"]), visible)
        assert entry["new_visible_by_pose"] == {"bind": int(wanted.sum())}
        assert not lv.check_mask(mask, cases[name])
    # the plain case: everything a full sphere sees from above is also "upper"
    entry = json.loads(lv.mask_path(out, cases["plain"]).read_text(encoding="utf-8"))["linings"]["GeneratedTestBacking"]
    assert entry["visible_upper"] == entry["visible"]
    keep = lv.unpack_bits(entry["keep"], entry["triangles"])
    assert (keep >= expected).all() and keep.sum() > expected.sum()


@needs_blender
def test_blender_real_garment_is_deterministic_and_checked(tmp_path):
    first, out_a = _masks(tmp_path / "a", [BOOTS], "--poses", "bind,Walk@0.25,mount:crystalback_tortoise",
                          "--directions", "16")
    second, out_b = _masks(tmp_path / "b", [BOOTS], "--poses", "bind,Walk@0.25,mount:crystalback_tortoise",
                           "--directions", "16")
    assert first == 0 and second == 0
    a = lv.mask_path(out_a, BOOTS).read_bytes()
    assert a == lv.mask_path(out_b, BOOTS).read_bytes()
    mask = json.loads(a)
    assert mask["source"]["path"] == "res://assets/actors/native/equipment/variants/human_male/arcane_fantasy_boots_02.glb"
    assert mask["poses"] == ["bind", "Walk@0.25", "mount:crystalback_tortoise"]
    assert sorted(mask["linings"]) == ["GeneratedBootBacking", "GeneratedBootBackingWithLegs"]
    for entry in mask["linings"].values():
        counts = entry["counts"]
        assert 0 < counts["visible_bind"] <= counts["visible"] <= counts["keep"] <= entry["triangles"]
        assert sum(entry["new_visible_by_pose"].values()) == counts["visible"]
    assert not lv.check_mask(mask, BOOTS)
    # a damaged mask is caught
    broken = json.loads(a)
    entry = broken["linings"]["GeneratedBootBacking"]
    keep = lv.unpack_bits(entry["keep"], entry["triangles"])
    keep[np.argmax(lv.unpack_bits(entry["visible"], entry["triangles"]))] = False
    entry["keep"] = lv.pack_bits(keep)
    entry["check"][1][2] += 0.01
    problems = lv.check_mask(broken, BOOTS)
    assert any("not kept" in p for p in problems) and any("centroid" in p for p in problems)
    # a new margin needs no Blender run: the cached record is re-finalised
    assert lv.main(["finalise", str(BOOTS), "--out", str(out_a), "--margin", "0"]) == 0
    tight = json.loads(lv.mask_path(out_a, BOOTS).read_text(encoding="utf-8"))
    for name, entry in tight["linings"].items():
        assert entry["keep"] == entry["visible"] and tight["margin_m"] == 0.0
        assert entry["counts"]["keep"] < mask["linings"][name]["counts"]["keep"]
    # the cache is reused for an unchanged garment, tool and settings
    assert _masks(tmp_path / "a", [BOOTS], "--poses", "bind,Walk@0.25,mount:crystalback_tortoise",
                  "--directions", "16")[0] == 0
    assert lv.mask_path(out_a, BOOTS).read_bytes() == a


@needs_blender
def test_blender_skinning_matches_blender_deformation(tmp_path):
    poses = lv.resolve_poses(["bind", "Run_Female@0.25", "mount:crystalback_tortoise"])
    job = dict(lv.common_job(dict(lv.DEFAULT_SETTINGS), poses), mode="selfcheck",
               glbs=[{"path": str(BOOTS), "out": str(tmp_path / "selfcheck.json")}])
    [(_, code, log)] = lv.run_blender_jobs([job], tmp_path, lv.find_blender(), "selfcheck")
    assert code == 0, log.read_text(errors="replace")[-2000:]
    result = json.loads((tmp_path / "selfcheck.json").read_text(encoding="utf-8"))
    assert not result.get("errors")
    for pose, rows in result["poses"].items():
        for mesh, row in rows.items():
            assert row["max_rest_mismatch_m"] < 1e-5, (pose, mesh)
            assert row["max_pose_error_m"] < 1e-5, (pose, mesh)
            if pose != "bind":
                assert row["max_displacement_m"] > 0.05, (pose, mesh)
