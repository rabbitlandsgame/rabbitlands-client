"""Harvest presentation (owner-approved 2026-10-14): the marker extras, the package entries, D11 and D4.

harvest_presentation.py turns a harvest marker's optional presentation extras (variant, yaw, footprint, grouping,
groupingName, bindPlacement) into the territory manifest's harvestables and harvestGroupings, refusing malformed or
unresolvable ones; publish_client.py writes them (and drops them from chunk manifests). publish_server.py refuses a
node on a road (D11) and judges harvest nodes by the reach-side approach rule (D4), with the old eight-neighbour rule
one constant away. None of this needs a server checkout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import frames as F  # noqa: E402
import harvest_presentation as HP  # noqa: E402
import publish_client as PC  # noqa: E402
import publish_server as P  # noqa: E402

ORIGIN = [300, 400]                      # serverOrigin: tile = (floor(x + 300), floor(400 - z))


def marker(object_id, x, z, **extras):
    position = [float(x), 10.0, float(z)]
    return {"id": f"m-harvest-{object_id}", "objectId": object_id, "resource": extras.pop("resource", "Cotton"),
            "label": "Cotton", "position": position, "serverTile": HP.tile_of(position, ORIGIN), **extras}


PLACEMENTS = [
    {"node": "Authored_landfall_kit_olive_tree_1_017", "authoringId": "landfall-kit-olive-tree-1-017",
     "position": [20.0, 10.0, -5.0], "chunk": "08_10", "top": 15.25},
    {"node": "Authored_landfall_kit_olive_tree_1_018", "authoringId": "landfall-kit-olive-tree-1-018",
     "position": [26.0, 10.0, -5.0], "chunk": "08_10", "top": 14.0},
]


# --- the package entries -----------------------------------------------------------------------------------------

def test_a_marker_without_extras_publishes_its_node_and_nothing_else():
    entries, groupings = HP.package_entries([marker(337, 1.5, 2.5), marker(336, 4.5, 2.5)], PLACEMENTS, ORIGIN)
    assert [e["objectId"] for e in entries] == [336, 337]
    assert set(entries[0]) == {"id", "objectId", "resource", "serverTile", "position"}
    assert entries[0]["serverTile"] == [304, 397]
    assert groupings == []


def test_the_extras_reach_the_entry_and_the_grouping_is_summarised():
    records = [marker(350, 0.5, 0.5, variant=2, yaw=450, footprint=[3, 0.9], grouping="north-wall-cotton",
                      groupingName="North Wall farm"),
               marker(351, 3.5, 0.5, variant=0, yaw=90.0, footprint=[3.0, 0.9], grouping="north-wall-cotton"),
               marker(352, 6.5, 0.5, grouping="north-wall-cotton", resource="Hearthroot")]
    entries, groupings = HP.package_entries(records, PLACEMENTS, ORIGIN)
    first = entries[0]
    assert first["variant"] == 2 and first["yaw"] == 90.0 and first["footprint"] == [3.0, 0.9]
    assert first["grouping"] == "north-wall-cotton" and "groupingName" not in first and "bind" not in first
    assert "variant" not in entries[2] and "yaw" not in entries[2]
    assert groupings == [{"id": "north-wall-cotton", "name": "North Wall farm",
                          "resources": ["Cotton", "Hearthroot"], "centre": [3.5, 0.5], "centreTile": [303, 399],
                          "nodeCount": 3, "objectIds": [350, 351, 352]}]
    # deterministic whatever the marker order
    again = HP.package_entries(list(reversed(records)), PLACEMENTS, ORIGIN)
    assert json.dumps(again) == json.dumps((entries, groupings))


def test_an_unnamed_grouping_is_named_for_its_one_resource():
    _, groupings = HP.package_entries([marker(1, 0.5, 0.5, grouping="sage-drift")], [], ORIGIN)
    assert groupings[0]["name"] == "Cotton"


@pytest.mark.parametrize("reference", ["landfall-kit-olive-tree-1-017", "Authored_landfall_kit_olive_tree_1_017",
                                       "AuthoredAssets/landfall-kit-olive-tree-1-017",
                                       "Region/AuthoredAssets/Authored_landfall_kit_olive_tree_1_017"])
def test_promoted_scenery_binds_its_placement_by_id_node_or_path(reference):
    entries, _ = HP.package_entries([marker(106, 21.0, -6.0, bindPlacement=reference, resource="Olive")],
                                    PLACEMENTS, ORIGIN)
    assert entries[0]["bind"] == {"node": "Authored_landfall_kit_olive_tree_1_017",
                                  "assetId": "landfall-kit-olive-tree-1-017", "chunk": "08_10", "height": 5.25}


@pytest.mark.parametrize("records, words", [
    ([marker(1, 0, 0, bindPlacement="no-such-placement")], "names 0 kit placements"),
    ([marker(1, 10, -5, bindPlacement="landfall-kit-olive-tree-1-017")], "stands 10.00 m from the node"),
    ([marker(1, 20, -5, bindPlacement="landfall-kit-olive-tree-1-017"),
      marker(2, 21, -5, bindPlacement="Authored_landfall_kit_olive_tree_1_017")], "is already bound by"),
    ([marker(1, 0, 0, variant=-1)], "variant"),
    ([marker(1, 0, 0, variant=1.5)], "variant"),
    ([marker(1, 0, 0, variant=True)], "variant"),
    ([marker(1, 0, 0, yaw="east")], "yaw"),
    ([marker(1, 0, 0, footprint=[0, 1])], "footprint"),
    ([marker(1, 0, 0, footprint=[13, 1])], "footprint"),
    ([marker(1, 0, 0, footprint=[3])], "footprint"),
    ([marker(1, 0, 0, grouping="North Wall")], "grouping"),
    ([marker(1, 0, 0, groupingName="A farm")], "groupingName without a grouping"),
    ([marker(1, 0, 0, grouping="farm", groupingName="A | farm")], "groupingName"),
    ([marker(1, 0, 0, grouping="farm", groupingName="One"), marker(2, 3, 0, grouping="farm", groupingName="Two")],
     "its nodes name it"),
    ([marker(1, 0, 0), marker(1, 3, 0)], "used by two harvest markers"),
])
def test_a_malformed_or_unresolvable_marker_is_refused(records, words):
    with pytest.raises(HP.PresentationError, match=words):
        HP.package_entries(records, PLACEMENTS, ORIGIN)


def test_publish_client_measures_only_the_placements_a_node_binds():
    asked = []
    doc = {"server": {"origin": ORIGIN}, "gameplay": {"harvestables": [
        marker(106, 21.0, -6.0, bindPlacement="landfall-kit-olive-tree-1-017", resource="Olive"),
        marker(107, 4.0, 4.0)]}}
    placements = [dict(p, groupedNodes=[p["node"]], top=None) for p in PLACEMENTS]

    def top_of(nodes):
        asked.append(list(nodes))
        return 16.5
    entries, groupings = PC.harvest_package(doc, placements, top_of)
    assert asked == [["Authored_landfall_kit_olive_tree_1_017"]]
    assert entries[0]["bind"]["height"] == 6.5 and "bind" not in entries[1]
    assert PC.HARVEST_SCHEMA == HP.SCHEMA


def test_a_package_without_harvest_markers_still_publishes_an_empty_list():
    doc = {"server": {"origin": ORIGIN}, "gameplay": {}}
    assert PC.harvest_package(doc, [], lambda nodes: 0.0) == ([], [])


def test_chunk_manifests_carry_no_harvest_presentation():
    manifest = {"asset": {"id": "landfall"}, "collision": {}, "harvestables": [{"objectId": 1}],
                "harvestGroupings": [{"id": "g"}], "harvestablesSchema": HP.SCHEMA}
    chunk = PC.chunk_manifest(manifest, "landfall", "08_10", {"externalResources": {}}, {"min": [0] * 3,
                                                                                      "max": [1] * 3})
    assert not {"harvestables", "harvestGroupings", "harvestablesSchema"} & set(chunk)


# --- D11: no node on a road ---------------------------------------------------------------------------------------

ROAD = {"id": "r29-2", "kind": "road", "closed": False,
        "points": [{"position": [0.0, 10.0, 0.0], "width": 8.0}, {"position": [40.0, 10.0, 0.0], "width": 4.0}]}
RIVER = {"id": "brook", "kind": "river", "points": [{"position": [0.0, 10.0, 20.0], "width": 30.0},
                                                    {"position": [40.0, 10.0, 20.0], "width": 30.0}]}


def test_a_node_within_a_roads_half_width_is_an_offender():
    nodes = [{"id": 340, "tile": (0, 0)}, {"id": 341, "tile": (1, 1)}, {"id": 342, "tile": (2, 5)},
             {"id": 343, "tile": (35, 2)}, {"id": 344, "tile": (10, 12)}]

    def local_of(tx, ty):
        return tx + 0.5, -(ty + 0.5)
    offenders = HP.road_offenders([ROAD, RIVER], nodes, local_of)
    # centreline; 1.5 m off it (half-width 4); 5.5 m off it (outside); at x 35.5 the width has tapered to 4.45 m
    # (half 2.2) and the tile is 2.5 m off; the river's 15 m half-width is not a road.
    assert [o["id"] for o in offenders] == [340, 341]
    assert offenders[0]["road"] == "r29-2" and offenders[0]["inside"] == pytest.approx(3.5, abs=0.05)


def test_a_closed_road_loops_back_to_its_first_point():
    square = {"id": "ring-road", "kind": "road", "closed": True, "points": [
        {"position": [0.0, 0.0, 0.0], "width": 2.0}, {"position": [10.0, 0.0, 0.0], "width": 2.0},
        {"position": [10.0, 0.0, 10.0], "width": 2.0}]}
    assert HP.road_clearance(5.0, 5.0, HP.road_segments([square])) is not None   # on the closing diagonal
    assert HP.road_clearance(5.0, 5.0, HP.road_segments([dict(square, closed=False)])) is None


# --- D4: the reach-side harvest approach ---------------------------------------------------------------------------

def checker(codes=None, reached=None, ground=None):
    frame = F.Frame("isle", "Isle", (0, 12), (12, 12), (0, 0, 0))
    codes = np.full((12, 12), 200, np.uint16) if codes is None else codes
    reached = np.ones((12, 12), bool) if reached is None else reached
    return P.Checker({"isle": codes}, {"isle": reached}, {"isle": frame},
                     {"isle": [[0, 0], [12, 0], [12, 12], [0, 12]]},
                     ground=None if ground is None else {"isle": ground})


def test_the_rule_constant_defaults_to_the_reach_side_rule():
    assert P.HARVEST_APPROACH_RULE == "reach-side" and P.HARVEST_RING_MINIMUM == 3 and P.HARVEST_REACH == 2


def test_a_seam_against_a_cliff_passes_from_its_open_side_only_under_d4():
    codes = np.full((12, 12), 200, np.uint16)
    codes[:, :6] = 0                       # the cliff: everything west of x 6 is closed
    codes[5, 6] = 0                        # the node's own tile (harvest_mask)
    check = checker(codes)
    assert check.node("isle", (6, 5), "seam")                    # five ring tiles open, all reached
    assert check.failures == []
    assert not check.node("isle", (6, 5), "seam", rule="ring")   # the old rule wants all eight
    assert "blocked" in check.failures[0]["problems"][0]


def test_a_node_reached_only_two_tiles_away_passes():
    codes = np.zeros((12, 12), np.uint16)
    codes[5, 8] = 200                      # one open, reached tile at Chebyshev 2; the ring is all closed
    check = checker(codes)
    assert check.node("isle", (6, 5), "reed")
    assert check.server_walk_tile("isle", 6, 5) == [8, 5]


def test_a_node_with_nothing_reached_within_two_tiles_is_refused():
    codes = np.zeros((12, 12), np.uint16)
    codes[5, 9] = 200                      # Chebyshev 3: the server would walk there and stop short of range
    check = checker(codes)
    assert not check.node("isle", (6, 5), "kelp")
    problems = check.failures[0]["problems"]
    assert any(p.startswith("no approach: 0 of 8") for p in problems)
    assert any("beyond Chebyshev 2" in p for p in problems)


def test_the_tile_the_server_walks_to_must_be_reached():
    # Open ground all round, but the first tile free_player_tile finds (north-west, (5, 4)) is an unreached pocket:
    # the ring rule's three reached tiles would not save a harvester the server sends there.
    codes = np.full((12, 12), 200, np.uint16)
    codes[5, 6] = 0                         # the node's own tile (harvest_mask)
    reached = np.ones((12, 12), bool)
    reached[4, 5] = False
    check = checker(codes, reached)
    assert check.server_walk_tile("isle", 6, 5) == [5, 4]
    assert not check.node("isle", (6, 5), "olive")
    assert "which is not reached" in check.failures[0]["problems"][-1]


def test_an_npc_post_the_server_would_walk_to_is_named():
    walk = np.full((12, 12), 200, np.uint16)
    walk[4, 5] = 0                          # an NPC post: open ground, closed to walkers
    walk[5, 6] = 0                          # the node's own tile
    ground = np.full((12, 12), 200, np.uint16)
    ground[5, 6] = 0
    reached = np.ones((12, 12), bool)
    reached[4, 5] = False
    check = checker(walk, reached, ground)
    assert not check.node("isle", (6, 5), "olive")
    assert check.failures[0]["problems"][-1].endswith("is an NPC post")


def test_an_unknown_rule_is_refused():
    with pytest.raises(P.PublishError):
        checker().node("isle", (6, 5), "x", rule="anything")


def test_d4_keeps_the_seam_strip_owner_rule_on_the_ring():
    """As test_publish_server's ring test: an off-owner ring tile is judged on its owner, and an inconsistent one
    still fails the node."""
    source = F.Frame("landfall", "Landfall", (0, 4), (5, 5), (0, 0, 0))
    neighbour = F.Frame("tollholm", "Tollholm", (1, 4), (5, 5), (0, 0, 0))
    codes = {region: np.full((5, 5), 222, dtype=np.uint16) for region in ("landfall", "tollholm")}
    reached = {region: np.ones((5, 5), bool) for region in codes}
    codes["landfall"][2, 1] = 0
    polygons = {"landfall": [[0, -1], [2, -1], [2, 4], [0, 4]], "tollholm": [[2, -1], [4, -1], [4, 4], [2, 4]]}
    frames = {"landfall": source, "tollholm": neighbour}
    assert P.Checker(codes, reached, frames, polygons).node("landfall", [1, 2], 247)
    codes["tollholm"][2, 3] += 1                       # the seam alias no longer matches its owner's height
    check = P.Checker(codes, reached, frames, polygons)
    assert not check.node("landfall", [1, 2], 247)
    assert any("canonical height mismatch" in p for p in check.failures[0]["problems"])
