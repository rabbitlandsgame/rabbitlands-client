"""The harvest coverage pass: its scene reader, its committed plan and its scene writer.

Plan checks read only the client checkout. The regeneration check (the plan is current) needs a server checkout named
by ELORIA_SERVER_ROOT and skips without one.
"""
import copy
import json
import math
import os
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import harvest_coverage as H  # noqa: E402
import harvest_presentation as HP  # noqa: E402

RULES = H.read_json(H.RULES)
PLAN = H.read_json(H.PLAN) if H.PLAN.exists() else None
needs_plan = pytest.mark.skipif(PLAN is None, reason="content/harvest-coverage.json has not been generated")
SERVER = os.environ.get("ELORIA_SERVER_ROOT")


def test_transform_reads_the_twelve_numbers_after_the_constructor():
    # Regression: the "3" in "Transform3D(" was once read as a number, so every transform was refused and the scene
    # seemed to hold no roads or scenery.
    body = "\ntransform = Transform3D(-0.95, 0, -0.29, 0, 1, 0, 0.29, 0, -0.95, -183.395, 121.494, -9.9e-05)\n"
    basis, origin = H._transform(body)
    assert basis.shape == (3, 3)
    assert origin.tolist() == [-183.395, 121.494, -9.9e-05]


def test_kit_names_drop_catalog_prefix_variant_and_digest():
    assert H.kit_of("sw_isle:kit-olive-tree-1") == "olive-tree"
    assert H.kit_of("lf_biomes:woodlandfloor-0327-7f0bb3a588d3") == "woodlandfloor"
    assert H.kit_of("landfall:kit-beach-palm-tree-3-clear") == "beach-palm-tree-3-clear"


def test_landfall_scene_reads_markers_roads_and_scenery():
    scene = H.read_scene("landfall", H.ROOT, RULES["pass"])
    harvest = [m for m in scene["markers"] if m["parent"] == H.HARVEST_PARENT]
    assert len(harvest) >= 80 and all(isinstance(m["extras"].get("objectId"), int) for m in harvest)
    assert len(scene["paths"]) >= 5 and all(len(p["points"]) >= 2 for p in scene["paths"])
    assert len(scene["placements"]) > 1000
    kits = {p["kit"] for p in scene["placements"]}
    assert {"olive-tree", "lemon-tree"} <= kits


def test_landfall_road_band_lies_on_walkable_ground():
    """The road reader agrees with the ground: a road's band is overwhelmingly walkable on the served grid."""
    scene = H.read_scene("landfall", H.ROOT, RULES["pass"])
    frame = H.frames.load("landfall", H.ROOT)
    grid_bytes = (H.ROOT / f"{H.V2}/landfall/client/served-grid.escg.gz").read_bytes()
    g = type("G", (), {})()
    g.frame, g.scene = frame, scene
    g.shape = (frame.cells[1], frame.cells[0])
    band = H.road_band(g, 0.0)
    assert band.sum() > 2000
    # walkability without the server: the package's collision half-cells (EWCG-v2; 0 is closed)
    raw = (H.ROOT / f"{H.V2}/landfall/client/collision.bin").read_bytes()
    width, height = (int(v) for v in np.frombuffer(raw[8:16], "<u4"))
    half = np.frombuffer(raw[16:16 + width * height], np.uint8).reshape(height, width)
    walkable = half.reshape(height // 2, 2, width // 2, 2).max(axis=(1, 3)) > 0
    assert grid_bytes and walkable.shape == band.shape and walkable[band].mean() > 0.9


@needs_plan
def test_plan_covers_every_exterior_map_with_its_inputs():
    assert PLAN["schema"] == H.SCHEMA and PLAN["pass"] == RULES["pass"]
    assert set(PLAN["maps"]) == set(H.EXTERIOR)
    assert PLAN["rulesSha256"] == H.sha(H.RULES.read_bytes())
    for region, entry in PLAN["maps"].items():
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        assert H.sha(scene["base"].encode("utf-8")) == entry["inputs"]["sceneSha256"], region
        world = H.read_json(H.ROOT / f"{H.V2}/{region}/client/world.json")
        grid = (H.ROOT / f"{H.V2}/{region}/client/served-grid.escg.gz").read_bytes()
        assert H.sha(grid) == entry["inputs"]["servedGridSha256"] == world["collision"]["servedGrid"]["sha256"]


@needs_plan
def test_plan_ids_groupings_and_kinds_follow_the_rules():
    promote_only = set(RULES["promoteOnly"])
    for region, entry in PLAN["maps"].items():
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        taken = {m["extras"].get("objectId") for m in scene["markers"]}
        groupings = {m["extras"].get("grouping") for m in scene["markers"] if m["parent"] == H.HARVEST_PARENT}
        placements = {p["assetId"]: p for p in scene["placements"]}
        frame = H.frames.load(region, H.ROOT)
        ids, tiles, bound = set(), set(), set()
        for site in entry["groupings"]:
            assert site["id"] not in groupings and H.HP.GROUPING_ID.match(site["id"])
            groupings.add(site["id"])
            assert site["nodes"]
            for node in site["nodes"]:
                oid = node["objectId"]
                assert RULES["objectIdBase"] <= oid <= RULES["objectIdLimit"] and oid not in taken and oid not in ids
                ids.add(oid)
                tile = tuple(node["tile"])
                assert frame.contains(*tile) and tile not in tiles
                tiles.add(tile)
                x, z = frame.local(*tile)
                assert math.isclose(node["position"][0], round(x, 3)) and math.isclose(node["position"][2], round(z, 3))
                if "bindPlacement" in node:
                    p = placements[node["bindPlacement"]]
                    assert node["bindPlacement"] not in bound
                    bound.add(node["bindPlacement"])
                    assert math.hypot(p["position"][0] - x, p["position"][2] - z) <= HP.BIND_MAX_METRES
                    assert RULES["promote"].get(p["kit"]) == node["resource"] or any(
                        p["kit"].startswith(k) and v == node["resource"] for k, v in RULES["promote"].items())
                else:
                    assert node["resource"] not in promote_only, (region, oid, node["resource"])
        # nodes of this pass keep the minimum spacing between themselves
        pts = np.array(sorted(tiles))
        if len(pts) > 1:
            d = np.abs(pts[:, None, :] - pts[None, :, :]).max(axis=2)
            np.fill_diagonal(d, 99)
            assert d.min() >= RULES["clumps"]["minSpacingChebyshev"]


@needs_plan
def test_plan_reaches_the_coverage_targets_everywhere():
    """The gate: every map's harvest reach meets EL's; variety and shape are reported per map."""
    for region, entry in PLAN["maps"].items():
        after = entry["targetsAfter"]
        assert after["nearestP90Seconds"] and after["noneWithin50mShare"], (region, entry["after"])
        assert entry["after"]["kindsPerMap"] >= entry["before"]["kindsPerMap"]
        assert not entry["existingNodeProblems"], (region, entry["existingNodeProblems"][:2])


@needs_plan
def test_scene_writer_is_idempotent_and_restores_the_count(tmp_path):
    region = min(PLAN["maps"], key=lambda r: PLAN["maps"][r]["addedNodes"])
    regions = tmp_path / "godot-client/world_authoring/regions" / region
    regions.mkdir(parents=True)
    source = H.ROOT / "godot-client/world_authoring/regions" / region
    for name in (f"{region}.tscn", "region-authoring-spec.json"):
        shutil.copy2(source / name, regions / name)
    plan = copy.deepcopy(PLAN)
    plan["maps"] = {region: plan["maps"][region]}
    base_count = json.loads((regions / "region-authoring-spec.json").read_bytes())["gameplay"]["authoredMarkerCount"]
    first = H.apply_scenes(tmp_path, plan, log=lambda *a: None)
    once = {p: p.read_bytes() for p in first}
    H.apply_scenes(tmp_path, plan, log=lambda *a: None)
    assert {p: p.read_bytes() for p in first} == once
    scene = H.read_scene(region, tmp_path, RULES["pass"])
    added = sum(len(s["nodes"]) for s in plan["maps"][region]["groupings"])
    assert len(scene["generated"]) == added
    assert H.sha(scene["base"].encode("utf-8")) == plan["maps"][region]["inputs"]["sceneSha256"]
    spec = json.loads((regions / "region-authoring-spec.json").read_bytes())
    assert spec["gameplay"]["authoredMarkerCount"] == base_count + added
    for m in scene["generated"]:
        HP.marker_hints({"id": m["name"], **m["extras"]})
        assert m["extras"]["pass"] == RULES["pass"] and m["extras"]["authority"] == "server"


@pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout to regenerate the plan")
def test_plan_is_current():
    assert H.main(["--server", SERVER, "--check"]) == 0
