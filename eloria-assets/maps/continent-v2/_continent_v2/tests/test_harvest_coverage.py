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


def test_trails_without_a_transform_are_read():
    # Regression: Godot omits an identity transform, and the A3 trails carry none; they were once skipped, so D11
    # was judged with no roads at all on the isles.
    for region, least in (("suncoil", 15), ("hornmere", 11), ("whitepeak", 12)):
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        assert len(scene["paths"]) >= least, (region, len(scene["paths"]))


def test_server_rows_are_protected():
    """Spawns, landing targets, cast posts and homes are rows publish_server.py ring-checks; the generator keeps clear
    of them (a node in a spawn's ring once refused the publication)."""
    if not SERVER:
        pytest.skip("set ELORIA_SERVER_ROOT to read the server's rows")
    srv = H.server_inputs(Path(SERVER))
    assert len(srv["spawns"]) > 1000 and srv["targets"] and srv["posts"]
    if PLAN is None:
        return
    for region, entry in PLAN["maps"].items():
        rows = [(x, y) for m, x, y in srv["spawns"] + srv["posts"] if m == region]
        for site in entry["groupings"]:
            for node in site["nodes"]:
                x, y = node["tile"]
                near = [(a, b) for a, b in rows if max(abs(x - a), abs(y - b)) <= RULES["placement"]["protectChebyshev"]]
                assert not near, (region, node["objectId"], near[:3])


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
    if H.applied_maps(H.ROOT, PLAN):
        # Applied and published: the grids now hold the pass's own bodies, so prove the applied state instead.
        assert not H.verify_applied(H.ROOT, PLAN)
        return
    stale = []
    for region, entry in PLAN["maps"].items():
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        world = H.read_json(H.ROOT / f"{H.V2}/{region}/client/world.json")
        grid = (H.ROOT / f"{H.V2}/{region}/client/served-grid.escg.gz").read_bytes()
        assert H.sha(grid) == world["collision"]["servedGrid"]["sha256"], region
        if (H.sha(scene["base"].encode("utf-8")) != entry["inputs"]["sceneSha256"]
                or H.sha(grid) != entry["inputs"]["servedGridSha256"]):
            stale.append(region)
    # A later scene or package edit makes the plan stale without making it wrong; --apply-scenes refuses a stale
    # plan, so this reports it rather than failing someone else's unrelated change.
    if stale:
        pytest.skip(f"the plan is stale for {stale}: run harvest_coverage.py --plan before applying it")


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
    base_count = json.loads((regions / "region-authoring-spec.json").read_bytes())["gameplay"].get("authoredMarkerCount")
    current = H.read_scene(region, tmp_path, RULES["pass"])
    if H.sha(current["base"].encode("utf-8")) != plan["maps"][region]["inputs"]["sceneSha256"]:
        # A later pass edited the scene after this plan was applied (the 2026-11-15 map quality pass): the writer
        # must refuse to write the plan onto a base it was not made from.
        with pytest.raises(H.CoverageError):
            H.apply_scenes(tmp_path, plan, log=lambda *a: None)
        pytest.skip(f"{region}'s scene changed after the plan was applied; the writer refuses it, as it should")
    already = len(current["generated"])
    if base_count is not None:
        base_count -= already               # the scene may carry the applied pass already
    first = H.apply_scenes(tmp_path, plan, log=lambda *a: None)
    once = {p: p.read_bytes() for p in first}
    H.apply_scenes(tmp_path, plan, log=lambda *a: None)
    assert {p: p.read_bytes() for p in first} == once
    scene = H.read_scene(region, tmp_path, RULES["pass"])
    added = sum(len(s["nodes"]) for s in plan["maps"][region]["groupings"])
    assert len(scene["generated"]) == added
    assert H.sha(scene["base"].encode("utf-8")) == plan["maps"][region]["inputs"]["sceneSha256"]
    spec = json.loads((regions / "region-authoring-spec.json").read_bytes())
    assert spec["gameplay"].get("authoredMarkerCount") == (None if base_count is None else base_count + added)
    for m in scene["generated"]:
        HP.marker_hints({"id": m["name"], **m["extras"]})
        assert m["extras"]["pass"] == RULES["pass"] and m["extras"]["authority"] == "server"
        # the scene's own marker script id: scenes name it differently (s0_marker, lv_marker, s2_marker, marker)
        assert m["script"] == scene["markerScript"] and scene["markerScript"]


# Generated nodes the 2026-11-15 map quality pass removed from raised pier, causeway and landing-stage decks (Walk_
# surfaces 1.3-18.5 m above the terrain; .local/map-quality-20261115/fixes/harvest.md): served tiles per map.
DECK_REGRESSION = {
    "ravenhead": [(579, 416), (576, 411), (554, 250), (548, 464), (716, 346), (693, 345), (611, 320), (776, 350)],
    "coilmere": [(428, 1041), (432, 1042), (62, 815), (55, 815), (147, 770)],
    "reedfall": [(300, 358), (303, 353)],
    "hornmere": [(591, 291), (590, 299), (592, 287)],
}


def bare_ground(region):
    """A Ground stand-in without the server: the real frame, scene and kit models, every tile open, flat and reached,
    no protected rows or existing nodes, so only the scene's own scenery can exclude a tile."""
    from types import SimpleNamespace
    frame = H.frames.load(region, H.ROOT)
    world = H.read_json(H.ROOT / f"{H.V2}/{region}/client/world.json")
    shape = (frame.cells[1], frame.cells[0])
    codes = np.ones(shape, np.int64)
    return SimpleNamespace(region=region, frame=frame, scene=H.read_scene(region, H.ROOT, RULES["pass"]),
                           checkout=H.ROOT, shape=shape, codes=codes, ground=codes, heights=np.zeros(shape),
                           polygon=world["continentGeography"], protected=[], targets=[], lane_tiles=[], nodes=[])


def test_candidate_mask_keeps_off_decks_and_piers():
    """Regression: the served grid is open and flat on a pier deck, so the mask once let the pass seed sites on the
    trestle piers and causeways. Deck kits and Walk_ faces now exclude their footprint, for promotion too."""
    for region, tiles in DECK_REGRESSION.items():
        g = bare_ground(region)
        cand, promotable_ok = H.candidate_mask(g, np.ones(g.shape, bool), RULES)
        deck = H.scenery_exclusions(g, RULES)["deck"]
        for x, y in tiles:
            assert deck[y, x] and not cand[y, x] and not promotable_ok[y, x], (region, x, y)
        # every pier and causeway span's own origin tile is a deck tile
        for p in g.scene["placements"]:
            if "trestle-pier-span" in p["kit"] or "causeway-arch" in p["kit"]:
                try:
                    x, y = g.frame.tile(p["position"][0], p["position"][2])
                except H.frames.FrameError:
                    continue
                assert deck[y, x], (region, p["nodeName"])
        # decks are a small part of a map: the mask still offers its open ground
        assert deck.mean() < 0.05 and cand.sum() > 0.2 * cand.size, (region, deck.mean(), cand.mean())


def test_saved_bridge_decks_are_excluded():
    """A saved bridge (Bridges/<id> with Start and End markers) excludes its deck strip widened by the margin."""
    from types import SimpleNamespace
    g = SimpleNamespace(frame=SimpleNamespace(origin=(50, 50)), shape=(100, 100), checkout=H.ROOT,
                        scene={"placements": [], "groundRegions": [],
                               "bridges": [{"id": "b", "start": [-10.0, 3.0, 0.0], "end": [10.0, 3.0, 0.0],
                                            "width": 4.0}]})
    deck = H.scenery_exclusions(g, RULES)["deck"]
    tx, tz = H.tile_centres(g)
    on = lambda x, z: deck[int(np.argmin(abs(tz - z))), int(np.argmin(abs(tx - x)))]
    margin = H.EXCLUSIONS["deckMarginMetres"]
    assert on(0.5, 0.5) and on(9.5, 2.5) and on(-9.5, -2.5)
    assert not on(0.5, 2.0 + margin + 1.5) and not on(10.0 + margin + 1.5, 0.5)
    assert deck.sum() < 2 * (20 + 2 * margin + 1) * (4 + 2 * margin + 1)


def test_every_applied_scene_uses_its_own_marker_script():
    for region in H.EXTERIOR:
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        scripts = {m["script"] for m in scene["generated"]}
        assert scripts <= {scene["markerScript"]}, (region, scripts, scene["markerScript"])


@pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout to regenerate the plan")
def test_plan_is_current():
    assert H.main(["--server", SERVER, "--check"]) == 0
