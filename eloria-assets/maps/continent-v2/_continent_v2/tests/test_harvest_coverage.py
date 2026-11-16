"""The harvest coverage pass: its scene reader, its committed plan and its scene writer.

Plan checks read only the client checkout. The regeneration check (the plan is current) needs a server checkout named
by ELORIA_SERVER_ROOT and skips without one.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from types import SimpleNamespace

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


def _strip(x0, z0, x1, z1):
    return [[(x0, z0), (x1, z0), (x1, z1)], [(x0, z0), (x1, z1), (x0, z1)]]


def _face_distance(tri, p):
    """Brute force: metres from point p to the x/z triangle tri (0 inside)."""
    def seg(a, b):
        d = b - a
        l2 = float(d @ d)
        t = 0.0 if l2 <= 1e-12 else min(1.0, max(0.0, float((p - a) @ d) / l2))
        return float(np.hypot(*(p - (a + t * d))))
    a, b, c = tri
    area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(area) > 1e-12:
        e = [(q[0] - o[0]) * (p[1] - o[1]) - (q[1] - o[1]) * (p[0] - o[0]) for o, q in ((a, b), (b, c), (c, a))]
        if min(e) >= 0 or max(e) <= 0:
            return 0.0
    return min(seg(a, b), seg(b, c), seg(c, a))


def test_deck_footprint_is_its_faces_not_their_hull():
    """Regression: a deck kit was once excluded as the convex hull of all its vertices, plus the margin. A garden
    paving chunk is a network of walks, so its hull took the lawns between them (about 7,000 open candidate tiles on
    Landfall). mark_triangles marks exactly the tile centres within the margin of a face."""
    g = SimpleNamespace(frame=SimpleNamespace(origin=(30, 30)), shape=(60, 60))
    tx, tz = H.tile_centres(g)
    margin = H.EXCLUSIONS["deckMarginMetres"]
    # a U of 2 m walks (west, east, south) around a 16 m lawn
    walks = np.array(_strip(-10, -10, -8, 10) + _strip(8, -10, 10, 10) + _strip(-10, -10, 10, -8), float)
    deck = np.zeros(g.shape, bool)
    H.mark_triangles(deck, tx, tz, walks, margin)
    on = lambda m, x, z: m[int(np.argmin(abs(tz - z))), int(np.argmin(abs(tx - x)))]
    assert on(deck, -9.5, 0.5) and on(deck, 9.5, 0.5) and on(deck, 0.5, -9.5)            # the walks
    assert on(deck, -7.5, 0.5) and not on(deck, -6.5, 0.5)                                # widened by the margin only
    assert not any(on(deck, x, z) for x, z in ((0.5, 0.5), (-5.5, 5.5), (5.5, 5.5), (0.5, -6.5)))   # the lawn
    hull = np.zeros(g.shape, bool)
    H.mark_convex(hull, tx, tz, walks.reshape(-1, 2), margin)
    assert on(hull, 0.5, 0.5) and deck.sum() < 0.6 * hull.sum()
    # exact against a brute-force distance, with a face seen edge-on (a wall) and a point among random faces, and with
    # a batch budget small enough to send the larger faces through the row-stripe path
    rng = np.random.default_rng(3)
    tris = rng.uniform(-25, 25, (14, 1, 2)) + rng.normal(size=(14, 3, 2)) * rng.choice([0.3, 2.0, 12.0], (14, 1, 1))
    tris[0, 2] = (tris[0, 0] + tris[0, 1]) / 2
    tris[1, 1:] = tris[1, 0]
    X_, Z_ = np.meshgrid(tx, tz)
    dist = np.array([min(_face_distance(t, p) for t in tris)
                     for p in np.stack([X_.ravel(), Z_.ravel()], 1)]).reshape(g.shape)
    for budget in (H._TRI_BUDGET, 50):
        got = np.zeros(g.shape, bool)
        saved, H._TRI_BUDGET = H._TRI_BUDGET, budget
        try:
            H.mark_triangles(got, tx, tz, tris, margin)
        finally:
            H._TRI_BUDGET = saved
        tie = np.abs(dist - margin) < 1e-6
        assert ((got == (dist <= margin)) | tie).all(), budget


# Landfall's garden paving chunks: the 2026-11-15 audit removed the two nodes standing on the paving itself and kept
# the nodes on the lawns between the walks, 4-25 m from any paving face (served tiles).
GARDEN_REMOVED = [(226, 349), (239, 365)]
GARDEN_KEPT = [(286, 314), (314, 271), (281, 221), (295, 235), (271, 275)]


def test_garden_lawns_between_paving_walks_stay_open():
    g = bare_ground("landfall")
    deck = H.scenery_exclusions(g, RULES)["deck"]
    for x, y in GARDEN_REMOVED:
        assert deck[y, x], ("removed", x, y)
    for x, y in GARDEN_KEPT:
        assert not deck[y, x], ("kept", x, y)
    # no node of this pass the audit kept on Landfall is on a deck tile (16 stand inside the garden chunks' hulls)
    kept = [g.frame.tile(m["position"][0], m["position"][2]) for m in g.scene["generated"]]
    assert not [t for t in kept if deck[t[1], t[0]]]
    # the chunks' hulls are mostly lawn: their paving faces, widened by the margin, take well under half of them
    tx, tz = H.tile_centres(g)
    hull = np.zeros(g.shape, bool)
    for p in g.scene["placements"]:
        if "garden-paving" in p["kit"]:
            placed = H.kit_faces(H.ROOT, p["scenePath"]).reshape(-1, 3) @ np.asarray(p["basis"]).T + p["position"]
            H.mark_convex(hull, tx, tz, placed[:, [0, 2]], H.EXCLUSIONS["deckMarginMetres"])
    assert hull.sum() > 5000 and (deck & hull).sum() < 0.5 * hull.sum(), (int(hull.sum()), int((deck & hull).sum()))


def test_tree_words_are_whole_kit_words():
    """Regression: tree words once matched anywhere in a kit name, so "pine" made the alpine flower cushions (soft
    meadow flora the meadow feature draws sites to) trees, and "tree" made Suncoil's street-market obelisks trees:
    their footprints went into the tree layer."""
    ex = H.exclusion_rules(RULES)
    for kit in ("alpine-flower-cushion", "obelisk-street-market"):
        assert H.scenery_class(kit, ex) is None, kit
    for kit in ("scots-pine-tree", "alpine-fir-tree", "dark-fir", "golden-larch", "tree-fern", "beach-palm-tree-1-clear",
                "landmark-deadtree", "treehouse", "banyan-tree", "resin-tapped-pine"):
        assert H.scenery_class(kit, ex) == "tree", kit
    assert H.scenery_class("coastal-boulders", ex) == "dense"          # dense words still match inside a name
    assert H.kit_words("dark-fir", ["-fir"]) and not H.kit_words("fire-pit", ["fir-"])
    assert H.kit_words("giant-tree-fern-2", ["tree-fern"]) and not H.kit_words("street-fern", ["tree-fern"])
    # no meadow plant in any exterior scene is classed a tree or dense scenery
    meadow = RULES["features"]["meadow"]
    for region in H.EXTERIOR:
        for p in H.read_scene(region, H.ROOT, RULES["pass"])["placements"]:
            if any(w in p["kit"] for w in meadow):
                assert H.scenery_class(p["kit"], ex) not in ("tree", "dense"), (region, p["kit"])
    # the cushions and the obelisks exclude nothing
    for region, kit in (("hornmere", "alpine-flower-cushion"), ("suncoil", "obelisk-street-market")):
        g = bare_ground(region)
        g.scene = {"placements": [p for p in g.scene["placements"] if p["kit"] == kit], "bridges": [],
                   "groundRegions": []}
        assert g.scene["placements"], (region, kit)
        assert not any(layer.any() for layer in H.scenery_exclusions(g, RULES).values()), (region, kit)


SPARSE_SCENE = """[gd_scene format=3]

[sub_resource type="Resource" id="Resource_masonry"]
texture_preset = "Weathered limestone masonry"

[node name="Sample" type="Node3D"]

[node name="Ground" type="Node3D" parent="."]

[node name="Regions" type="Node3D" parent="Ground"]

[node name="Plaza" type="Marker3D" parent="Ground/Regions"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 20, 0, 20)
region_id = "plaza"
enabled = true
surface = SubResource("Resource_masonry")

[node name="Quiet" type="Marker3D" parent="Ground/Regions"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, -20, 0, 20)
region_id = "quiet"
surface = SubResource("Resource_masonry")

[node name="Bridges" type="Node3D" parent="."]

[node name="Ford" type="Node3D" parent="Bridges"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, -20, 0, -20)
bridge_id = "ford"

[node name="Start" type="Marker3D" parent="Bridges/Ford"]

[node name="End" type="Marker3D" parent="Bridges/Ford"]
transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, 12, 0, 0)
"""


def test_unwritten_region_and_bridge_properties_take_the_script_defaults(tmp_path):
    """Godot leaves a property out of the .tscn while it equals the script default. read_scene once read an unwritten
    enabled as true, size as 0 x 0 (the region was then dropped), blend_width as 0 and a bridge width as 8 m."""
    pilot = H.ROOT / "godot-client/src/dev/map_authoring_pilot"
    ground = (pilot / "ground_region.gd").read_text(encoding="utf-8")
    bridge = (pilot / "bridge_control.gd").read_text(encoding="utf-8")
    d = H.GROUND_REGION_DEFAULTS
    assert re.search(r"^@export var enabled := (\w+)", ground, re.M).group(1) == str(d["enabled"]).lower()
    shapes = [s.strip() for s in re.search(r"enum Shape \{([^}]*)\}", ground).group(1).split(",") if s.strip()]
    assert shapes.index(re.search(r"var shape: int = Shape\.(\w+)", ground).group(1)) == d["shape"]
    size = re.search(r"^@export var size := Vector2\(([^)]*)\)", ground, re.M).group(1)
    assert tuple(float(v) for v in size.split(",")) == d["size"]
    assert float(re.search(r"var blend_width := ([\d.]+)", ground).group(1)) == d["blend_width"]
    assert float(re.search(r"var opacity := ([\d.]+)", ground).group(1)) == d["opacity"]
    assert float(re.search(r"var width := ([\d.]+)", bridge).group(1)) == H.BRIDGE_DEFAULTS["width"]
    # the region scenes' scripts extend these and declare none of the properties again
    region_scripts = H.ROOT / "godot-client/src/dev/map_authoring_region"
    for name, base, props in (("ground_region_control.gd", "ground_region.gd", ("enabled", "shape", "size",
                                                                                "blend_width", "opacity")),
                              ("bridge_control.gd", "bridge_control.gd", ("width",))):
        text = (region_scripts / name).read_text(encoding="utf-8")
        assert f'extends "res://src/dev/map_authoring_pilot/{base}"' in text, name
        for prop in props:
            assert not re.search(rf"^(?:@\w+(?:\([^)]*\))?\s+)*var {prop}\b", text, re.M), (name, prop)
    # a scene that writes none of them
    folder = tmp_path / "godot-client/world_authoring/regions/sample"
    folder.mkdir(parents=True)
    (folder / "sample.tscn").write_text(SPARSE_SCENE, encoding="utf-8", newline="\n")
    scene = H.read_scene("sample", tmp_path, RULES["pass"])
    regions = {r["id"]: r for r in scene["groundRegions"]}
    for region in regions.values():
        assert region["shape"] == "ellipse" and region["size"] == list(d["size"]), region
        assert region["blend"] == d["blend_width"] and region["opacity"] == d["opacity"], region
        assert region["preset"] == "Weathered limestone masonry"
    assert regions["plaza"]["enabled"] and not regions["quiet"]["enabled"]
    (deck,) = scene["bridges"]
    assert deck["width"] == H.BRIDGE_DEFAULTS["width"]
    assert deck["start"] == [-20.0, 0.0, -20.0] and deck["end"] == [-8.0, 0.0, -20.0]
    # end to end: the enabled region at the default size paints paving, the default (disabled) one does not
    g = SimpleNamespace(frame=SimpleNamespace(origin=(50, 50)), shape=(100, 100), checkout=tmp_path,
                        scene={**scene, "placements": []})
    layers = H.scenery_exclusions(g, RULES)
    tx, tz = H.tile_centres(g)
    on = lambda m, x, z: m[int(np.argmin(abs(tz - z))), int(np.argmin(abs(tx - x)))]
    assert on(layers["paving"], 20.5, 20.5) and not on(layers["paving"], -19.5, 20.5)
    assert 20 < layers["paving"].sum() < 60, int(layers["paving"].sum())
    margin = H.EXCLUSIONS["deckMarginMetres"]
    assert on(layers["deck"], -14.5, -20.5) and not on(layers["deck"], -14.5, -20.5 - 1.5 - margin - 1.0)


def test_every_applied_scene_uses_its_own_marker_script():
    for region in H.EXTERIOR:
        scene = H.read_scene(region, H.ROOT, RULES["pass"])
        scripts = {m["script"] for m in scene["generated"]}
        assert scripts <= {scene["markerScript"]}, (region, scripts, scene["markerScript"])


@pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout to regenerate the plan")
def test_plan_is_current():
    assert H.main(["--server", SERVER, "--check"]) == 0
