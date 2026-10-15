"""_continent_v2/crossings_v2.py: the isles' land crossings by the legacy lane rule, on synthetic served grids.

Three territories on the continent's metre lattice: "west" (x 40-100) and "east" (x 100-160) share a straight border at
x 100, which an approved route crosses at z 8 (a road link); "south" (z 60-100 under west) shares west's z 60 border,
which no route crosses (a roadless border). Each map's grid is its own ground plus the one-tile collar of the
neighbour's, as export_collision.py writes it. Along x 100 the ground is open on both sides at z 2-14 (a straight
crossing), on a mole at z 30-36 across water, and on an islet at z 44-50 that water fences off from both maps' ground;
the rest of the border is water. The z 60 border is a cliff on west's side, so the roadless border has no lane.

The server's step rule (collision_sources.walk_step_ok), the codec and the legacy publisher come from the server
checkout named by ELORIA_SERVER_ROOT; without it these tests skip.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import frames as F  # noqa: E402
import export_collision as X  # noqa: E402
import crossings_v2 as CV  # noqa: E402
import crossings as C  # noqa: E402

SERVER = os.environ.get("ELORIA_SERVER_ROOT")
pytestmark = pytest.mark.skipif(not SERVER, reason="set ELORIA_SERVER_ROOT to a server checkout with "
                                                   "eloria/served_grid.py")
CELLS = 72
WEST = F.Frame("west", "West", (34, 34), (CELLS, CELLS), (70.0, 0.0, 30.0))
EAST = F.Frame("east", "East", (34, 34), (CELLS, CELLS), (130.0, 0.0, 30.0))
SOUTH = F.Frame("south", "South", (34, 34), (CELLS, CELLS), (70.0, 0.0, 80.0))
POLYGONS = {"west": [[40.0, 0.0], [100.0, 0.0], [100.0, 60.0], [40.0, 60.0]],
            "east": [[100.0, 0.0], [160.0, 0.0], [160.0, 60.0], [100.0, 60.0]],
            "south": [[40.0, 60.0], [100.0, 60.0], [100.0, 100.0], [40.0, 100.0]]}
FLAT = 2200                      # 10 m on the served codes (50 mm above -100 m)
STRAIGHT = (2.0, 14.0)           # z run of the straight crossing
ISLET = (44.0, 50.0)             # z run of the fenced islet
ROUTE = {"id": "R1", "type": "road", "approvedPolyline": [[80.0, 8.5], [120.0, 8.5]],
         "byTerritory": [{"territory": "west", "points": [0, 0]}, {"territory": "east", "points": [1, 1]}]}


def ground_open(gx, gz, mole):
    """The shared ground: open everywhere but a water band either side of x 100 (x 92-108) outside the straight
    crossing, the mole and the islet, and a moat round the islet (z 41-43 and 51-53 over x 92-108) so it is fenced."""
    gx, gz = np.asarray(gx, float), np.asarray(gz, float)
    band = (gx > 92) & (gx < 108)
    crossing = ((gz > STRAIGHT[0]) & (gz < STRAIGHT[1])) | ((gz > mole[0]) & (gz < mole[1])) \
        | ((gz > ISLET[0]) & (gz < ISLET[1]))
    water = band & ~crossing
    # The islet does not reach either map's ground: it ends 4 m short of the band's edges.
    islet_cut = band & (gz > ISLET[0]) & (gz < ISLET[1]) & ((gx < 96) | (gx > 104))
    cliff = (gz > 56) & (gz < 64) & (gx > 40) & (gx < 100)     # the z 60 border: a cliff, no lane
    return ~(water | islet_cut | cliff)


def grid(frame, mole=(30.0, 36.0), rise=None):
    """The frame's served codes: its own ground and a one-tile collar of the neighbours', open where the ground is.
    rise(gx, gz) lifts east's ground (its own tiles and west's collar over them alike) by that many codes."""
    xs = np.arange(CELLS) - frame.origin[0] + .5 + frame.translation[0]
    zs = frame.origin[1] - np.arange(CELLS) - .5 + frame.translation[2]
    gx, gz = np.meshgrid(xs, zs)
    own = X.point_in_polygon(gx, gz, POLYGONS[frame.region])
    beside = np.zeros_like(own)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            beside |= np.roll(np.roll(own, dy, axis=0), dx, axis=1)
    inside = np.zeros_like(own)
    for polygon in POLYGONS.values():
        inside |= X.point_in_polygon(gx, gz, polygon)
    keep = (own | beside) & inside & ground_open(gx, gz, mole)
    lift = np.zeros(gx.shape, int)
    if rise is not None:
        lift = np.where(X.point_in_polygon(gx, gz, POLYGONS["east"]), rise(gx, gz), 0)
    return np.where(keep, FLAT + lift, 0).astype(np.uint16)


def arrival(frame, gx, gz):
    return list(frame.tile_of_continent(gx, gz))


def table(mole=(30.0, 36.0), frames_=(WEST, EAST, SOUTH), rise=None):
    out = {}
    hubs = {"west": (60.5, 25.5), "east": (130.5, 25.5), "south": (70.5, 80.5)}
    for frame in frames_:
        transform = {"metresPerTile": 1.0, "serverOrigin": list(frame.origin), "serverCells": list(frame.cells),
                     "origin": [0, 0, 0], "invertServerY": True, "serverStorageVersion": 1, "serverTileMin": [0, 0]}
        out[frame.region] = {"frame": frame, "polygon": POLYGONS[frame.region], "codes": grid(frame, mole, rise),
                             "arrival": arrival(frame, *hubs[frame.region]),
                             "servedGridSha256": "0" * 64 + frame.region,
                             "manifest": {"coordinateTransform": transform}, "package": ""}
    return out


def plan(pairs=(("east", "west"), ("south", "west")), moles=()):
    return {"seams": {"openSeams": [{"between": list(pair)} for pair in pairs], "moles": list(moles)},
            "approvedRoutes": [ROUTE]}


MOLE = {"id": "mole", "between": ["west", "east"], "x": [96.0, 104.0], "z": [30.0, 36.0]}


@pytest.fixture(scope="module")
def codec():
    return X.server_codec(SERVER)


@pytest.fixture(scope="module")
def built(codec):
    return CV.build(table(), plan(moles=[MOLE]), codec, plan_sha="p" * 64, log=lambda *_: None)


def connection(doc, identity):
    return next(c for c in doc["connections"] if c["id"] == identity)


def lane_z(frame, lane):
    return frame.continent(*lane["tile"])[1]


def test_the_road_link_is_anchored_where_the_route_crosses(built):
    link = next(link for link in built["links"] if link["id"] == "west--east")
    assert link["road"] is True and link["route"] == "R1"
    assert link["anchor"] == [100.0, 8.5] and link["normal"] == [1.0, 0.0]
    assert link["edgeSegments"] == [[[100.0, 0.0], [100.0, 60.0]]]


def test_straight_seams_pair_straight_across(built):
    road = connection(built, "west--east")
    frames_ = {"west": WEST, "east": EAST}
    for end in road["ends"]:
        straight = [lane for lane in end["lanes"] if STRAIGHT[0] < lane_z(frames_[end["region"]], lane) < STRAIGHT[1]]
        assert len(straight) == 12, end["region"]
        for lane in straight:
            dx, dy = lane["arrival"][0] - lane["tile"][0], lane["arrival"][1] - lane["tile"][1]
            assert dy == 0 and abs(dx) == 1, lane
        # a lane is the neighbour's first tile across the border, read in this map's frame
        for lane in end["lanes"]:
            gx, _gz = frames_[end["region"]].continent(*lane["tile"])
            assert gx == (100.5 if end["region"] == "west" else 99.5)


def test_no_arrival_is_a_departure_and_each_lane_lands_on_its_own_cell(built):
    departures = {(s, x, y) for s, x, y, *_ in built["portals"]}
    assert not any((d, ax, ay) in departures for *_, d, ax, ay in built["portals"])
    frames_ = {"west": WEST, "east": EAST}
    for source, x, y, destination, ax, ay in built["portals"]:
        assert frames_[source].continent(x, y) == frames_[destination].continent(ax, ay)


def test_a_mole_keeps_its_lanes_and_a_narrow_one_is_refused(built, codec):
    assert built["report"]["moles"] == [{"id": "mole", "between": ["west", "east"],
                                         "lanesEachWay": {"west": 6, "east": 6}, "pass": True}]
    with pytest.raises(CV.CrossingsError, match="a mole keeps fewer than 4 lanes"):
        CV.build(table(mole=(30.0, 33.0)), plan(moles=[dict(MOLE, z=[30.0, 33.0])]), codec, log=lambda *_: None)


def test_a_fenced_islet_is_pruned(built):
    road = connection(built, "west--east")
    frames_ = {"west": WEST, "east": EAST}
    for end in road["ends"]:
        zs = [lane_z(frames_[end["region"]], lane) for lane in end["lanes"]]
        assert not any(ISLET[0] < z < ISLET[1] for z in zs), end["region"]
        assert len(zs) == 12 + 6
    assert built["report"]["withdrawnLanes"] >= 2 * 6     # the islet's six lanes each way


def test_a_roadless_border_without_a_lane_is_withdrawn(built):
    assert built["report"]["withdrawnRoadless"] == ["border--west--south"]
    assert built["report"]["openedRoadless"] == []
    assert [c["id"] for c in built["connections"]] == ["west--east"]
    link = next(link for link in built["links"] if link["id"] == "border--west--south")
    # the segment runs the way west's polygon walks its edge
    assert link["road"] is False and link["edgeSegments"] == [[[100.0, 60.0], [40.0, 60.0]]]


def test_a_road_link_without_a_lane_is_refused(codec):
    closed = table()
    for region in ("west", "east"):
        frame = closed[region]["frame"]
        codes = closed[region]["codes"]
        xs = np.arange(CELLS) - frame.origin[0] + .5 + frame.translation[0]
        codes[:, (xs > 99) & (xs < 101)] = 0
    with pytest.raises(ValueError, match="no walker can reach or leave any lane"):
        CV.build(closed, plan(), codec, log=lambda *_: None)


def test_reseat_and_prune_are_safe_on_end_records_without_gate_fields(codec):
    """The roadless ends crossings.open_border_contracts makes carry no 'gate' on any lane: reseat moves the end to
    the lane nearest its tile, and prune_lanes withdraws and reseats without asking for one."""
    t = table()
    world = CV.V2World({r: e["frame"] for r, e in t.items()}, {r: e["polygon"] for r, e in t.items()},
                       {r: e["codes"] for r, e in t.items()}, 50, -100000)
    end = {"region": "west", "tile": [70, 20],
           "lanes": [{"tile": [67, 26], "arrival": [66, 26]}, {"tile": [67, 35], "arrival": [66, 35]}]}
    C.reseat(world, end)
    assert end["tile"] == [67, 26] and end["arrival"] == [66, 26] and len(end["position"]) == 3
    served = {r: C.own_ground(world, r, e["codes"]) for r, e in t.items()}
    sources = codec.sources
    step = lambda h, y, x, dy, dx: sources.walk_step_ok(h, y, x, dy, dx, 20)   # noqa: E731
    lanes = {side: C.crossing_lanes(world, {"id": "x", "regions": ["west", "east"],
                                           "edgeSegments": [[[100.0, 0.0], [100.0, 60.0]]]}, side, served, step)
             for side in (0, 1)}
    assert lanes[0] and lanes[1] and not any("gate" in lane for lane in lanes[0] + lanes[1])
    ends = [{"region": region, "tile": list(lanes[side][0]["tile"]), "lanes": copy.deepcopy(lanes[side])}
            for side, region in enumerate(("west", "east"))]
    withdrawn = C.prune_lanes(world, [{"id": "x", "type": "walk", "ends": ends}], served,
                              {r: e["arrival"] for r, e in t.items()}, 20)
    assert withdrawn == 12      # the islet's six lanes each way
    assert all(end["lanes"] and "position" in end for end in ends)


def test_the_server_reads_the_links_as_its_land_frames(built):
    """The exterior-connection entries are the server's own land frames: each lane's departure, read through them,
    lands on the lane's arrival (eloria.exterior_connections.neighbour_tile)."""
    from eloria.exterior_connections import _land_frames, _land_connections, neighbour_tile
    frames_ = _land_frames(built["exteriorConnections"])
    assert set(frames_) == {("west", "east"), ("east", "west")}
    assert set(_land_connections(built["exteriorConnections"])) == set(frames_)
    for source, x, y, destination, ax, ay in built["portals"]:
        assert neighbour_tile(frames_[source, destination], x, y) == (ax, ay)
    road = built["exteriorConnections"][0]
    assert road["seamless"] is True and "road" not in road
    for end in road["ends"]:
        assert end["frame"]["geometryMode"] == "continent-chunks-v1"
        assert end["frame"]["portal"] == "road-to-" + ("east" if end["map"] == "west" else "west")
        assert end["crossingRuns"]["runs"]


def test_a_stale_crossings_document_is_refused(built):
    t = table()
    CV.verify(built, t, "p" * 64)
    stale = copy.deepcopy(t)
    stale["east"]["servedGridSha256"] = "1" * 64
    with pytest.raises(CV.CrossingsError, match="stale for east"):
        CV.verify(built, stale)
    with pytest.raises(CV.CrossingsError, match="another continent-v2-plan"):
        CV.verify(built, t, "q" * 64)


def test_shared_segments_finds_collinear_overlaps_only():
    a = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]
    b = [[10.0, 2.0], [20.0, 2.0], [20.0, 20.0], [10.0, 20.0]]
    assert CV.shared_segments(a, b) == [[[10.0, 2.0], [10.0, 10.0]]]
    assert CV.shared_segments(a, [[11.0, 0.0], [20.0, 0.0], [20.0, 5.0]]) == []


# --- the served grid's climb: 20 codes of 50 mm, a metre --------------------------------------------------------------

def stepped_rise(gx, gz):
    """East's ground over the straight crossing: 0.9 m (18 codes) above west's at z 6-14 and 1.1 m (22 codes) at
    z 2-6. The 1.1 m band joins east's own ground through the 0.9 m one (a 0.2 m step), so only the border step
    decides it."""
    return np.where((gz > 2) & (gz < 6), 22, np.where((gz > 6) & (gz < 14), 18, 0))


def test_the_climb_decides_a_lane_at_the_served_grids_twenty_codes(codec):
    doc = CV.build(table(rise=stepped_rise), plan(), codec, log=lambda *_: None)
    assert doc["climbCodes"] == 20
    road = connection(doc, "west--east")
    frames_ = {"west": WEST, "east": EAST}
    for end in road["ends"]:
        zs = {lane_z(frames_[end["region"]], lane) for lane in end["lanes"]}
        assert {6.5 + k for k in range(8)} <= zs, end["region"]              # 0.9 m: a lane on every tile
        assert not zs & {2.5, 3.5, 4.5}, (end["region"], sorted(zs))         # 1.1 m: none
    # the corner rule makes east's diagonal crossing onto west's z 5.5 tile one-way; its walker steps once along
    # the border to cross back straight, and every other lane is crossed back in one step
    assert doc["report"]["stepBack"] == {"lanesBySteps": {"1": len(doc["portals"]) - 1, "2": 1}, "limit": 3}
    east = {lane_z(EAST, lane) for lane in next(e for e in road["ends"] if e["region"] == "east")["lanes"]}
    assert 5.5 in east


def mole_rise(gx, gz):
    """East's end of the mole: 1.1 m above west's at z 30-33, 0.55 m at z 26-30 and 33-37 (east reaches it)."""
    return np.where((gz > 30) & (gz < 33), 22, np.where(((gz > 26) & (gz < 30)) | ((gz > 33) & (gz < 37)), 11, 0))


def test_a_mole_the_climb_narrows_below_four_lanes_is_refused(codec):
    with pytest.raises(CV.CrossingsError, match="a mole keeps fewer than 4 lanes"):
        CV.build(table(rise=mole_rise), plan(moles=[MOLE]), codec, log=lambda *_: None)


def test_a_lane_that_strands_its_walker_is_refused(codec):
    """check_step_back walks each lane back: the walker it lands needs legal steps (three at most, never over another
    lane's tile) onto a reverse lane."""
    step = lambda h, y, x, dy, dx: codec.sources.walk_step_ok(h, y, x, dy, dx, 20)   # noqa: E731
    flat = np.full((6, 6), FLAT, np.uint16)
    portals = [["a", 3, 2, "b", 3, 2], ["b", 2, 2, "a", 2, 2]]
    assert CV.check_step_back(portals, {"a": flat, "b": flat}, step) == {1: 2}
    cliff = flat.copy()
    cliff[:, :3] = FLAT + 22                     # on b, the reverse lane's tile stands 1.1 m above the arrival
    with pytest.raises(CV.CrossingsError, match="cannot step back"):
        CV.check_step_back(portals, {"a": flat, "b": cliff}, step)
    with pytest.raises(CV.CrossingsError, match="cannot step back"):
        CV.check_step_back(portals[:1], {"a": flat, "b": flat}, step)        # no lane back at all
    # two steps back, but the way runs over another lane's departure, which would fire first
    far = [["a", 3, 2, "b", 4, 2], ["b", 2, 2, "a", 2, 2]]
    fenced = flat.copy()
    fenced[:, 3] = 0
    fenced[2, 3] = FLAT
    assert CV.check_step_back(far, {"a": flat, "b": fenced}, step) == {2: 1, 1: 1}
    with pytest.raises(CV.CrossingsError, match="cannot step back"):
        CV.check_step_back(far + [["b", 3, 2, "c", 3, 2]], {"a": flat, "b": fenced, "c": flat}, step)


def test_packages_from_two_export_runs_are_refused():
    def entry(snapshot, served, group):
        return {"servedGridSha256": served,
                "manifest": {"collision": {"sourceSnapshotSha256": snapshot, "groupExport": {"maps": group}}}}
    run = {"west": {"snapshotSha256": "w1", "servedGridSha256": "W1"},
           "east": {"snapshotSha256": "e1", "servedGridSha256": "E1"}}
    table_ = {"west": entry("w1", "W1", run), "east": entry("e1", "E1", run)}
    assert CV.check_one_run(table_) == run
    rerun = dict(run, east={"snapshotSha256": "e2", "servedGridSha256": "E2"})
    stale = {"west": entry("w1", "W1", run), "east": entry("e2", "E2", rerun)}
    with pytest.raises(CV.CrossingsError, match="another run"):
        CV.check_one_run(stale)
    with pytest.raises(CV.CrossingsError, match="every map"):
        CV.check_one_run({"west": entry("w1", "W1", None), "east": entry("e1", "E1", run)})


def test_survey_lanes_without_a_nearby_return_are_withdrawn(codec, monkeypatch):
    original = CV.survey

    def asymmetric(*args):
        publication, seams, settled = original(*args)
        for crossing in publication['connections']:
            for end in crossing['ends']:
                if end['region'] == 'east':
                    end['lanes'] = [lane for lane in end['lanes'] if lane_z(EAST, lane) < 9]
                    C.reseat(args[0], end)
        return publication, seams, settled

    monkeypatch.setattr(CV, 'survey', asymmetric)
    doc = CV.build(table(), plan(), codec, log=lambda *_: None)
    assert doc['report']['reciprocalWithdrawnLanes'] > 0
    assert all(end['lanes'] for c in doc['connections'] for end in c['ends'])
    step = lambda h, y, x, dy, dx: codec.sources.walk_step_ok(h, y, x, dy, dx, 20)
    codes = {region: entry['codes'] for region, entry in table().items()}
    assert CV.check_step_back(doc['portals'], codes, step) == {
        int(k): v for k, v in doc['report']['stepBack']['lanesBySteps'].items()}
