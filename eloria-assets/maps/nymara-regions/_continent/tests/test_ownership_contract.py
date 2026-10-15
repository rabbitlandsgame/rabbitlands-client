"""Canonical source ownership is opt-in, exact, and independent of map storage."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ownership_contract as O
import world_layout as W

CANONICAL = HERE / "ownership/user-boundary-redesign-v4.json"
CORRECTED = HERE / "ownership/user-boundary-redesign-v4-topology-correction-v1.json"
# Recorded independently from the hash-verified, approved QA candidate before
# adoption. Never derive expected values from the corrected source under test.
ORIGINAL_SOURCE_SHA256 = "715d545c5f855dd8207878b985ee47f0d4795a58f67ca8b97df44482623ff98e"
APPROVED_CANDIDATE_SHA256 = "30356aca59906ccd2ec8ee01c5051eb369a61564b4a3de10d484b2ec0d1c6a09"
CORRECTED_SOURCE_SHA256 = "98e48012e95815957437f26dedbc66f9394dd5538ff7a318e9b945c1f05b011f"
CANDIDATE_POLYGON_HASHES = {
    "whitehorn_range": "3d28ec32dd58b7d80f4ff5c006f075cc450f73368114a1e4783991dc7e61ec58",
    "grey_moors": "c109174c798a731e325cd34040cc8b35e49d61a8ddf0cc3c349f838ad1c453b1",
    "amberwood": "c28fd9011623b6db271d5dc8288f639d7eb3f866d96bd8c06a8f7e94dad28bca",
    "amethyst_barrens": "9f1036858558b3589d8dab6357bf456705dc9b0479acdca80dad74d014cf0aeb",
    "mirrorhold": "c1dd6131cc0fd165d243e8e8cdae3e1d3f5c991612c0e86bb52e898a0f5e7144",
    "sunmane_steppe": "b31e69d4c8921525aea5b4a96a67ad2832dacced3383c7fc55f82a8db1eec482",
    "four_gates": "743fcf6c78cc6ebe645a79a80436b567afd7f17a8d35ac64ebce07da2f6371cf",
    "westhaven": "7f19d828a25f2381a02936982abd4867227aa4680fe5ef5823492b2c97925adc",
    "manymouth_delta": "918368823c656ec62d5c7bd62a25e9c36097448490b42f72f42fe05f4e3dc281",
    "crownwater": "e91694f6190500899d92c5ffdab2493f2a69b6a391b365e22a7c3009fe76f1b7",
    "verdant_stair": "c2bfb0c3fbe8b5c4b50670a041d9e95083417ac1a7936c525357ffca4f2a2cc7",
    "ssarathi_ruins": "c31a7365372745846c2dd63943e0646e6d07b8a205751e5e26cc7d497caab752",
}
# Independently recorded from the approved master manifest, not re-derived from
# the source under test. Hashes preserve order, every vertex and numeric value.
MASTER_POLYGON_HASHES = {
    "amberwood": "ab5191699c81ed05201abb3165b4123a2706a8746752176c93f37367d2b26c99",
    "amethyst_barrens": "9f1036858558b3589d8dab6357bf456705dc9b0479acdca80dad74d014cf0aeb",
    "crownwater": "e91694f6190500899d92c5ffdab2493f2a69b6a391b365e22a7c3009fe76f1b7",
    "four_gates": "743fcf6c78cc6ebe645a79a80436b567afd7f17a8d35ac64ebce07da2f6371cf",
    "grey_moors": "fe6854f53402b8ab3139d6ec4411c4a99066bc68434389547ffb7408c443df61",
    "manymouth_delta": "1f21bb3b6b8c33ef823969a13686ad3de412e98525f2b9c3de793286cb8ba268",
    "mirrorhold": "17a603e9befa25911ec2b19044f11e55f900525921288ebe4fd9329b5f978100",
    "ssarathi_ruins": "c31a7365372745846c2dd63943e0646e6d07b8a205751e5e26cc7d497caab752",
    "sunmane_steppe": "b31e69d4c8921525aea5b4a96a67ad2832dacced3383c7fc55f82a8db1eec482",
    "verdant_stair": "c2bfb0c3fbe8b5c4b50670a041d9e95083417ac1a7936c525357ffca4f2a2cc7",
    "westhaven": "7dc5144678a39c4879aec28c3e5da7ee63e48958a92202126f0fb25e0516f169",
    "whitehorn_range": "53104bd47370ed61f106a68f186fec4ed63e8a0c1050d9fc909183bc2dd6e0a2",
}


def encode(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def fixture_document():
    def region(center, polygon):
        return {"ownershipPolygon": polygon,
                "coordinateFrame": {"continentTranslation": [center, 0, 20],
                    "origin": [0, 0, 0], "metresPerTile": 1, "serverOrigin": [60, 70],
                    "invertServerY": True},
                "baselineStorage": {"serverCells": [120, 120], "serverTileMin": [0, 0],
                    "collisionOriginMetres": [-60, 70]}}
    return {"schema": O.SCHEMA, "revision": "fixture-v1", "bounds": [0, 0, 40, 40],
            "boundaryRule": "lexical-region-id", "source": {"revision": "fixture",
                "manifestSha256": "1" * 64}, "design": {},
            "regions": {"west": region(10, [[0, 0], [20.5, 0], [20.5, 40], [0, 40]]),
                        "east": region(30, [[20.5, 0], [40, 0], [40, 40], [20.5, 40]])}}


def write_selection(tmp_path, monkeypatch, document=None):
    monkeypatch.setattr(O, "SOURCE_ROOT", tmp_path)
    path = tmp_path / "ownership.json"
    path.write_bytes(encode(document or fixture_document()))
    plan = {"bounds": [0, 0, 40, 40],
            "regions": [{"id": "west", "center": [10, 20]}, {"id": "east", "center": [30, 20]}],
            "ownership_contract": {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                   "revision": "fixture-v1"}}
    return plan, path


def test_canonical_source_matches_every_master_vertex_and_keeps_baseline_order():
    # The original invalid topology is historical evidence, not loadable input.
    document = json.loads(CANONICAL.read_bytes())
    assert hashlib.sha256(CANONICAL.read_bytes()).hexdigest() == ORIGINAL_SOURCE_SHA256
    assert {r: hashlib.sha256(encode(row["ownershipPolygon"])).hexdigest()
            for r, row in document["regions"].items()} == MASTER_POLYGON_HASHES
    plan = json.loads((HERE / "diagonal-plan.json").read_bytes())
    assert list(document["regions"]) == [row["id"] for row in plan["regions"]]


def test_original_canonical_source_defect_is_rejected():
    with pytest.raises(O.OwnershipContractError, match=r"grey_moors: invalid ownership polygon: Self-intersection"):
        O.load_contract(CANONICAL)


def test_corrected_source_matches_approved_candidate_and_pinned_frames():
    contract = O.load_contract(CORRECTED)
    document = json.loads(CORRECTED.read_bytes())
    original = json.loads(CANONICAL.read_bytes())
    assert contract.sha256 == CORRECTED_SOURCE_SHA256
    assert document["correction"]["approvedCandidateSha256"] == APPROVED_CANDIDATE_SHA256
    assert document["correction"]["originalSourceSha256"] == ORIGINAL_SOURCE_SHA256
    assert document["source"] == original["source"]
    assert document["design"] == original["design"]
    assert document["regions"]["four_gates"] == original["regions"]["four_gates"]
    plan = json.loads((HERE / "diagonal-plan.json").read_bytes())
    assert "ownership_contract" not in plan  # Phase one must not activate it.
    contract.validate_plan(plan)
    assert contract.region_ids == tuple(row["id"] for row in plan["regions"])
    assert contract.bounds == (0, 0, 1500, 1680)
    assert contract.revision == O.NYMARA_CORRECTED_REVISION
    assert {r: hashlib.sha256(encode(p)).hexdigest() for r, p in contract.polygons().items()} == CANDIDATE_POLYGON_HASHES
    assert hashlib.sha256(encode({r: contract.frame(r) for r in contract.region_ids})).hexdigest() == "8298ea6f95a28cdcd0e3a9ba1c120aed38655420bd01385e12c7b9286c6d3e36"
    assert hashlib.sha256(encode({r: contract.storage(r) for r in contract.region_ids})).hexdigest() == "7864891eab6df12d44bd548a500e06417ead1cb1a7a96f558cf55e737663a0ee"
    assert hashlib.sha256(encode(contract.metadata())).hexdigest() == "6ee94a80070c144081d95bf6ea6d8a67faec2fdb75816068efb54844b688ccb4"
    assert contract.metadata()["fourGatesCircle"] == {"centre": [520.0, 820.0], "radiusMetres": 200.0,
            "bounds": [320.0, 620.0, 720.0, 1020.0], "vertexCount": 384}
    client = HERE.parents[3]
    for region in contract.region_ids:
        assert contract.frame(region) == original["regions"][region]["coordinateFrame"]
        assert contract.storage(region) == original["regions"][region]["baselineStorage"]
        spec = json.loads((client / "godot-client/world_authoring/regions" / region / "region-authoring-spec.json").read_bytes())
        assert contract.frame(region)["continentTranslation"] == spec["continentTranslation"]
        assert contract.frame(region)["serverOrigin"] == spec["server"]["origin"]
        assert contract.storage(region)["serverCells"] == spec["server"]["cells"]
        assert contract.storage(region)["collisionOriginMetres"] == spec["server"]["collisionOriginMetres"]


def test_corrected_partition_and_opt_in_selection_preserve_exact_arrays():
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    contract = O.load_contract(CORRECTED)
    polygons = list(map(Polygon, contract.polygons().values()))
    assert all(p.is_valid for p in polygons)
    assert box(*contract.bounds).difference(unary_union(polygons)).area < O.AREA_EPSILON
    assert all(a.intersection(b).area < O.AREA_EPSILON
               for i, a in enumerate(polygons) for b in polygons[i + 1:])
    plan = json.loads((HERE / "diagonal-plan.json").read_bytes())
    plan["ownership_contract"] = {"path": str(CORRECTED.relative_to(HERE)),
            "sha256": CORRECTED_SOURCE_SHA256, "revision": O.NYMARA_CORRECTED_REVISION}
    assert O.for_plan(plan).polygons() == contract.polygons()
    for cell, order in ((8, list(contract.region_ids)), (13, list(reversed(contract.region_ids)))):
        ids, owner, _, _ = W.ownership_map(plan, cell, order)
        assert ids == order and np.all(owner >= 0)
        assert {r: hashlib.sha256(encode(p)).hexdigest()
                for r, p in O.for_plan(plan).polygons().items()} == CANDIDATE_POLYGON_HASHES


def test_exact_edge_ties_and_domain_corners_are_independent_of_index_order(tmp_path, monkeypatch):
    plan, _ = write_selection(tmp_path, monkeypatch)
    contract = O.for_plan(plan)
    xs = [0, 20.499, 20.5, 20.501, 40, -0.001, 40.001, 20.5]
    zs = [0, 20, 20, 20, 40, 20, 20, -0.001]
    expected = ["west", "west", "east", "east", "east", None, None, None]
    for ids in (["west", "east"], ["east", "west"]):
        indices = contract.sample(xs, zs, ids)
        assert [ids[i] if i >= 0 else None for i in indices] == expected
    assert int(contract.sample(20.5, 0, ["west", "east"])) == 1
    with pytest.raises(O.OwnershipContractError, match="finite"):
        contract.sample(np.nan, 0, ["west", "east"])


def test_polygon_map_uses_actual_centers_in_partial_preview_cells(tmp_path, monkeypatch):
    plan, _ = write_selection(tmp_path, monkeypatch)
    for order in (["west", "east"], ["east", "west"]):
        ids, owner, x0, z0 = W.ownership_map(plan, 13, order)
        assert ids == order and (x0, z0) == (0, 0)
        assert owner.shape == (4, 4)
        assert [ids[i] for i in owner[0]] == ["west", "west", "east", "east"]
        # The final cell is [39,40], sampled at 39.5, never at 45.5.
        assert np.all(owner >= 0)
    for invalid in (0, -2, np.inf, np.nan, True):
        with pytest.raises(ValueError, match="spacing"):
            W.ownership_map(plan, invalid)


def test_explicit_geometry_cannot_be_changed_by_retired_voronoi_controls(tmp_path, monkeypatch):
    plan, _ = write_selection(tmp_path, monkeypatch)
    expected = W.ownership_map(plan, 2)[1]
    plan["ownership_bias"] = {"west": 1e9}
    plan["ownership_sites"] = {"west": [[39, 20], [39, 39]]}
    np.testing.assert_array_equal(W.ownership_map(plan, 2)[1], expected)


def test_world_retains_subcell_polygon_and_frozen_address(tmp_path, monkeypatch):
    plan, path = write_selection(tmp_path, monkeypatch)
    monkeypatch.setattr(W.L, "height_at", lambda x, z, _plan: np.zeros(np.broadcast(x, z).shape))
    monkeypatch.setattr(W.L, "water_fields", lambda *args, **kwargs: {})
    world = W.World(plan)
    assert world.polygons == O.for_plan(plan).polygons()
    assert world.polygons["west"][1] == [20.5, 0]
    assert world.address("west") == ([60, 70], [120, 120])
    assert world.address("east") == ([60, 70], [120, 120])
    assert world.ids[int(world.owner_at(20.25, 20))] == "west"
    assert world.ids[int(world.owner_at(20.5, 20))] == "east"
    assert int(world.owner_at(-.01, 20)) == -1
    assert world.ownership_source_dependencies == {path: hashlib.sha256(path.read_bytes()).hexdigest()}
    # Mutating a consumer's copy cannot poison the cached source for later worlds.
    world.polygons["west"][1][0] = 999
    assert O.for_plan(plan).polygons()["west"][1][0] == 20.5


def test_selected_source_hash_detects_edits_and_is_in_composition_certificate(tmp_path, monkeypatch):
    plan, path = write_selection(tmp_path, monkeypatch)
    import build_continent as B
    monkeypatch.setattr(B.L, "load_plan", lambda: plan)
    assert path in B.composition_certificate_paths()
    assert O.source_dependencies(plan) == {path: plan["ownership_contract"]["sha256"]}
    # Same-size content edit must not survive a cached parse or mtime shortcut.
    path.write_bytes(path.read_bytes().replace(b'"fixture"', b'"changed"'))
    with pytest.raises(O.OwnershipContractError, match="hash/revision"):
        O.for_plan(plan)
    assert O.source_dependencies({}) == {}


@pytest.mark.parametrize("change,message", [
    (lambda d: d.update(schema="unknown"), "schema"),
    (lambda d: d.update(boundaryRule="input-order"), "boundaryRule"),
    (lambda d: d.update(bounds=[0, 0, 0, 40]), "positive area"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"][1].__setitem__(0, float("inf")), "non-finite"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"][1].__setitem__(0, True), "finite"),
    (lambda d: d["regions"]["west"].update(ownershipPolygon=[[0, 0], [20, 40], [0, 40], [20, 0]]), "invalid ownership"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"].append([0, 0]), "repeated"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"][0].__setitem__(0, -1), "outside"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"][1].__setitem__(0, 20.4), "partition"),
    (lambda d: d["regions"]["west"]["ownershipPolygon"][1].__setitem__(0, 20.6), "partition"),
    (lambda d: d["regions"]["west"]["coordinateFrame"].update(serverOrigin=[False, 0]), "integer"),
    (lambda d: d["regions"]["west"]["baselineStorage"].update(serverCells=[0, 12]), "positive"),
])
def test_rejects_malformed_contracts_and_real_partition_defects(tmp_path, change, message):
    document = fixture_document()
    change(document)
    path = tmp_path / "bad.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match=message):
        O.load_contract(path)


def test_duplicate_json_keys_and_invalid_json_fail_without_fallback(tmp_path):
    path = tmp_path / "bad.json"
    for raw, message in ((b'{"schema":1,"schema":2}', "duplicate"), (b'{oops', "valid JSON")):
        path.write_bytes(raw)
        with pytest.raises(O.OwnershipContractError, match=message):
            O.load_contract(path)


@pytest.mark.parametrize("change,message", [
    (lambda p: p.update(ownership_contract=None), "requires exactly"),
    (lambda p: p["ownership_contract"].update(path="../escaped.json"), "contained"),
    (lambda p: p["ownership_contract"].update(path="missing.json"), "cannot read"),
    (lambda p: p["ownership_contract"].update(sha256="0" * 64), "hash/revision"),
    (lambda p: p["ownership_contract"].update(revision="wrong"), "hash/revision"),
    (lambda p: p.update(bounds=[-40, -40, 1540, 1720]), "domain"),
    (lambda p: p["regions"][0].update(center=[11, 20]), "frozen"),
    (lambda p: p["regions"].append(copy.deepcopy(p["regions"][0])), "duplicates"),
    (lambda p: p["regions"].pop(), "match the plan"),
])
def test_invalid_selection_or_plan_never_silently_uses_voronoi(tmp_path, monkeypatch, change, message):
    plan, _ = write_selection(tmp_path, monkeypatch)
    change(plan)
    with pytest.raises(O.OwnershipContractError, match=message):
        W.ownership_map(plan)


def test_canonical_circle_metadata_cannot_drift(tmp_path):
    document = json.loads(CORRECTED.read_bytes())
    document["design"]["fourGatesCircle"]["radiusMetres"] = 201
    path = tmp_path / "wrong-circle.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match="circle metadata"):
        O.load_contract(path)


@pytest.mark.parametrize("change", [
    lambda d: d["design"]["fourGatesCircle"].update(centre=[521, 820]),
    lambda d: d["design"]["fourGatesCircle"].update(radiusMetres=201),
    lambda d: d["design"]["fourGatesCircle"].update(vertexCount=383),
    lambda d: d["regions"]["four_gates"]["ownershipPolygon"].pop(),
    lambda d: d["regions"]["four_gates"].update(ownershipPolygon=[
        [x + 1, z] for x, z in d["regions"]["four_gates"]["ownershipPolygon"]]),
    lambda d: d["regions"]["four_gates"].update(ownershipPolygon=[
        [520 + (x - 520) * 1.01, 820 + (z - 820) * 1.01]
        for x, z in d["regions"]["four_gates"]["ownershipPolygon"]]),
])
def test_four_gates_cannot_shift_grow_or_lose_vertices(tmp_path, change):
    document = json.loads(CORRECTED.read_bytes())
    change(document)
    path = tmp_path / "changed-circle.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match="circle metadata|partition"):
        O.load_contract(path)


def test_marked_inclusion_exempts_only_the_immutable_circle(tmp_path):
    from shapely.geometry import Polygon, box
    document = json.loads(CORRECTED.read_bytes())
    marked = Polygon(document["design"]["amberwoodMarkedInclusion"])
    regions = document["regions"]
    circle = Polygon(regions["four_gates"]["ownershipPolygon"])
    amberwood = Polygon(regions["amberwood"]["ownershipPolygon"])
    # Independently measured on the approved candidate. This pre-existing
    # overlap explains why checking the entire enclosure was incorrect.
    assert marked.intersection(circle).area == pytest.approx(480.3464337980281, abs=1e-8)
    required = marked.intersection(box(*document["bounds"])).difference(circle)
    assert required.difference(amberwood).area == pytest.approx(0.00480872282858, abs=1e-8)
    assert O.load_contract(CORRECTED).revision == O.NYMARA_CORRECTED_REVISION
    # Reassigning land keeps a valid partition but violates the marked design;
    # circle precedence must not become an exemption for other missing land.
    regions["amberwood"]["ownershipPolygon"], regions["amethyst_barrens"]["ownershipPolygon"] = (
        regions["amethyst_barrens"]["ownershipPolygon"], regions["amberwood"]["ownershipPolygon"])
    path = tmp_path / "missing-marked-land.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match="amberwoodMarkedInclusion is not included"):
        O.load_contract(path)


@pytest.mark.parametrize("change,message", [
    (lambda d: d["design"].pop("amberwoodMarkedInclusion"), "requires amberwoodMarkedInclusion"),
    (lambda d: d["design"].update(amethystBarrensMarkedInclusion=[[0, 0], [100, 0], [0, 100]]), "not included in amethyst_barrens"),
    (lambda d: d["design"].update(revision="fixture"), "original design lineage"),
    (lambda d: d.pop("correction"), "original design lineage"),
    (lambda d: d["correction"].update(approvedCandidateSha256="invalid"), "SHA-256"),
    (lambda d: d["correction"].update(originalMasterManifestSha256="0" * 64), "master provenance"),
])
def test_corrected_revision_retains_design_and_provenance_checks(tmp_path, change, message):
    document = json.loads(CORRECTED.read_bytes())
    change(document)
    path = tmp_path / "changed.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match=message):
        O.load_contract(path)


def test_renaming_revision_cannot_bypass_nymara_design_constraints(tmp_path):
    document = json.loads(CORRECTED.read_bytes())
    document["revision"] = "renamed-correction"
    document["design"]["fourGatesCircle"]["radiusMetres"] = 201
    path = tmp_path / "renamed.json"
    path.write_bytes(encode(document))
    with pytest.raises(O.OwnershipContractError, match="circle metadata"):
        O.load_contract(path)


def test_legacy_voronoi_keeps_order_dependent_ties_and_no_source_dependencies():
    plan = {"bounds": [0, 0, 40, 40], "regions": [
        {"id": "west", "center": [10, 20]}, {"id": "east", "center": [30, 20]}]}
    for order in (["west", "east"], ["east", "west"]):
        ids, owner, _, _ = W.ownership_map(plan, 8, order)
        assert ids[owner[2, 2]] == order[0]
    assert O.for_plan(plan) is None
    assert O.source_dependencies(plan) == {}
