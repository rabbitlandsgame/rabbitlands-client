"""Apply a reviewed, immutable procedural neighbour profile at one saved seam.

The sidecar records final ground and road samples, not solver parameters.  A
changed local seam is rejected for a new review; unrelated authoring remains
free to change without recapturing this profile.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


SIDECAR = Path(__file__).with_name("saved-seam-grey-whitehorn-v1.json")
SEAM = "grey_moors--whitehorn_range"
REGION = "grey_moors"
AUTHORED = "whitehorn_range"
BASE_SHA = "6b25ba0f7bbd5ae21ff8eede5498afee207541471fd08f026842ac1d0e55fd79"
ROADS_SHA = "6ec5f505abce4f8b219bfa4278d59d7b8d9d8038a65cddf461b422a7986463f8"
COMPOSED_SHA = "c65f38d7446a1408b3911f00d0e6e72a857f4ce1b5717fe922a87340699132f7"
MAX_GRADE = .65
CHECK_METRES = 72.


def _fail(reason):
    raise ValueError(f"{SEAM}: saved Grey neighbour profile incompatible: {reason}; review the seam sidecar against the new authoring")


def _load():
    data = json.loads(SIDECAR.read_text(encoding="utf-8"))
    claimed = data.pop("dataSha256", None)
    actual = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()
    if claimed != actual:
        _fail("sidecar data SHA-256 mismatch")
    if data.get("schema") != "eloria-saved-neighbour-seam-profile-v1" or data.get("seamId") != SEAM:
        _fail("sidecar schema or seam identity changed")
    if data.get("region") != REGION or data.get("authoredRegion") != AUTHORED:
        _fail("sidecar territory identity changed")
    if data.get("provenance") != {
        "certifiedWhitehornBaseSha256": BASE_SHA,
        "certifiedPublishedRoadsSha256": ROADS_SHA,
        "certifiedPublishedComposedSha256": COMPOSED_SHA,
    }:
        _fail("certified source provenance changed")
    return data, claimed


def _grid_index(world, xz):
    x, z = map(float, xz)
    ix = (x - world.x0) / 2.
    iz = (z - world.z0) / 2.
    if ix != round(ix) or iz != round(iz):
        _fail(f"non-grid seam vertex {xz}")
    ix, iz = int(round(ix)), int(round(iz))
    if not (0 <= iz < world.height.shape[0] and 0 <= ix < world.height.shape[1]):
        _fail(f"seam vertex outside current grid {xz}")
    return iz, ix


def _same(a, b):
    return bool(np.allclose(a, b, rtol=0., atol=1e-7))


def _route_sha(points):
    return hashlib.sha256(np.asarray(points[:, [0, 2]], dtype="<f8").tobytes()).hexdigest()


def _edge_before(world, edits):
    pairs = {}
    for z, x in edits:
        for dz, dx in ((-1, -1),(-1, 0),(-1, 1),(0, -1),(0, 1),(1, -1),(1, 0),(1, 1)):
            zz, xx = z + dz, x + dx
            if not (0 <= zz < world.height.shape[0] and 0 <= xx < world.height.shape[1]):
                continue
            pair = tuple(sorted(((z, x), (zz, xx))))
            a, b = pair
            distance = 2. * np.hypot(a[0]-b[0], a[1]-b[1])
            prior = abs(float(world.height[a]-world.height[b]))/distance
            encoded_prior = abs(float(np.float32(world.height[a]))-
                                float(np.float32(world.height[b])))/distance
            pairs[pair] = (distance, prior, encoded_prior)
    return pairs


def _check_edges(world, before):
    for (a, b), (distance, prior, encoded_prior) in before.items():
        grade = abs(float(world.height[a]-world.height[b]))/distance
        if grade > MAX_GRADE+1e-7 and grade > prior+1e-7:
            xz_a = [world.x0+2*a[1], world.z0+2*a[0]]
            xz_b = [world.x0+2*b[1], world.z0+2*b[0]]
            _fail(f"new/worsened grid edge {xz_a}->{xz_b}, {prior:.6f}->{grade:.6f}")
        encoded = abs(float(np.float32(world.height[a]))-
                      float(np.float32(world.height[b])))/distance
        if encoded > MAX_GRADE+1e-7 and encoded > encoded_prior+1e-7:
            _fail(f"new/worsened float32 grid edge {a}->{b}, "
                  f"{encoded_prior:.6f}->{encoded:.6f}")


def _check_route(world, road, link, feasibility_gate):
    points = np.asarray(road["points"], dtype=float)
    xz = points[:, [0, 2]]
    segment = np.linalg.norm(np.diff(xz, axis=0), axis=1)
    remaining = np.r_[np.cumsum(segment[::-1])[::-1], 0.]
    near = (remaining[:-1] <= CHECK_METRES) | (remaining[1:] <= CHECK_METRES)
    owner = world.ids.index(REGION)
    owned = (world.owner_at(xz[:-1, 0], xz[:-1, 1]) == owner) | (
        world.owner_at(xz[1:, 0], xz[1:, 1]) == owner)
    heights = np.asarray(world.height_at(xz[:, 0], xz[:, 1]), dtype=float)
    grade = np.abs(np.diff(heights))/np.maximum(segment, 1e-9)
    maximum = float(np.max(grade[near & owned], initial=0.))
    if maximum > MAX_GRADE+1e-8:
        _fail(f"complete 72 m road approach grade {maximum:.6f} exceeds {MAX_GRADE}")
    old_height = world.height
    try:
        world.height = np.asarray(old_height, dtype=np.float32)
        encoded = np.asarray(world.height_at(xz[:, 0], xz[:, 1]), dtype=float)
    finally:
        world.height = old_height
    encoded_grade = np.abs(np.diff(encoded))/np.maximum(segment, 1e-9)
    encoded_maximum = float(np.max(encoded_grade[near & owned], initial=0.))
    if encoded_maximum > MAX_GRADE+1e-8:
        _fail(f"float32 complete 72 m road grade {encoded_maximum:.6f} exceeds {MAX_GRADE}")
    # The recorded road surface must still lie on this finished terrain throughout
    # the approach.  This also detects later local authored edits not in the patch.
    if not _same(points[remaining <= CHECK_METRES, 1], heights[remaining <= CHECK_METRES]):
        _fail("saved road profile no longer matches local approach terrain")
    routing = [item for item in world.routing if item.get("name") == road["id"]]
    if not feasibility_gate(world, xz, np.asarray(link["anchor"], float), routing):
        _fail("unchanged road-profile, cut/fill or earthwork feasibility gate failed")
    return maximum


def _refresh_local_road_fields(world, road, before_points, station_edits):
    """Rebuild road queries only where a changed station could have influence."""
    old = {name:getattr(world, name).copy() for name in
           ("road_distance", "road_nearest", "road_target")}
    after_points = np.asarray(road["points"], dtype=float)
    padding = float(road["width"]) + max(16., float(road["width"])*4.) + 2.
    affected = np.zeros_like(world.height, dtype=bool)
    for edit in station_edits:
        index = edit["index"]
        for segment in (index-1, index):
            if not 0 <= segment < len(after_points)-1:
                continue
            endpoints = np.vstack((before_points[segment:segment+2, [0, 2]],
                                   after_points[segment:segment+2, [0, 2]]))
            low = endpoints.min(axis=0)-padding
            high = endpoints.max(axis=0)+padding
            affected |= ((world.gx >= low[0]) & (world.gx <= high[0]) &
                         (world.gz >= low[1]) & (world.gz <= high[1]))
    import authoring
    world.road_distance = np.full_like(world.height, np.inf)
    world.road_nearest = np.full_like(world.height, np.inf)
    world.road_target = world.height.copy()
    for item in world.roads:
        authoring._register_road_fields(world, item)
    for name, prior in old.items():
        getattr(world, name)[~affected] = prior[~affected]
    return int(affected.sum())


def apply_saved_seam_profile(world, authored_regions, feasibility_gate):
    """Apply the fixed profile once; give Grey saved terrain priority if it exists."""
    if AUTHORED not in authored_regions or REGION in authored_regions:
        return None
    data, data_sha = _load()
    grid = data["grid"]
    if grid != {"x0":float(world.x0), "z0":float(world.z0), "cellMetres":2.0,
                "shape":list(world.height.shape)}:
        _fail("continent grid layout changed")
    links = [row for row in world.connections if row["id"] == SEAM]
    if len(links) != 1:
        _fail("saved seam connection missing or ambiguous")
    link = links[0]
    if (list(link["regions"]) != data["link"]["regions"] or
        not _same(link["anchor"], data["link"]["anchor"]) or
        not _same(link["normal"], data["link"]["normal"])):
        _fail("saved anchor, normal or paired territories changed")
    if not any(row.get("id") == SEAM and row.get("region") == REGION
               for row in getattr(world, "saved_seam_approaches", ())):
        _fail("expected Grey saved-seam approach claim missing")
    road_data = data["road"]
    roads = [row for row in world.roads if row["id"] == road_data["id"]]
    if len(roads) != 1:
        _fail("Grey seam road missing or ambiguous")
    road = roads[0]
    original_points = np.asarray(road["points"], dtype=float)
    if len(original_points) != road_data["stationCount"]:
        _fail("Grey road station count changed")
    route_sha = _route_sha(original_points)
    original_route = route_sha == road_data["originalXzSha256"]
    applied_route = route_sha == road_data["afterXzSha256"]
    if not (original_route or applied_route):
        _fail("Grey road alignment changed")
    station = road_data["stationGuard"]
    expected_station = station["before" if original_route else "after"]
    if not _same(original_points[station["index"]], expected_station):
        _fail("guarded terminal road station changed")
    for guard in data["authoredBoundaryGuard"]:
        z, x = _grid_index(world, guard["xz"])
        if (not world.authored_terrain_authority[z, x] or
            world.ids[int(world.owner_at(*guard["xz"]))] != guard["owner"] or
            not _same(world.height[z, x], guard["height"])):
            _fail(f"authored seam boundary changed at {guard['xz']}")
    edits = {}
    for cell in data["terrainEdits"]:
        z, x = _grid_index(world, cell["xz"])
        if world.ids[int(world.owner_at(*cell["xz"]))] != REGION:
            _fail(f"Grey ownership changed at {cell['xz']}")
        if world.authored_terrain_authority[z, x]:
            _fail(f"saved terrain now owns Grey seam vertex {cell['xz']}")
        expected = cell["before" if original_route else "after"]
        if not _same(world.height[z, x], expected):
            _fail(f"local Grey terrain changed at {cell['xz']}")
        edits[z, x] = cell
    for item in road_data["stationEdits"]:
        expected = item["before" if original_route else "after"]
        if not _same(original_points[item["index"]], expected):
            _fail(f"road station {item['index']} changed")
    if applied_route:
        grade = _check_route(world, road, link, feasibility_gate)
        return {"id":SEAM,"region":REGION,"status":"already-applied",
                "dataSha256":data_sha,"changedCells":0,"maximumGrade":grade}
    before_edges = _edge_before(world, edits)
    old_heights = {(z, x):float(world.height[z, x]) for z, x in edits}
    old_road = road["points"]
    try:
        for (z, x), cell in edits.items():
            world.height[z, x] = cell["after"]
        new_points = original_points.copy()
        for item in road_data["stationEdits"]:
            new_points[item["index"]] = item["after"]
        road["points"] = new_points.tolist()
        if _route_sha(new_points) != road_data["afterXzSha256"]:
            _fail("recorded route edit does not match its XZ hash")
        _check_edges(world, before_edges)
        grade = _check_route(world, road, link, feasibility_gate)
    except Exception:
        for (z, x), value in old_heights.items():
            world.height[z, x] = value
        road["points"] = old_road
        raise
    # The last road settle has already happened.  Refresh query fields where
    # these stations influence them, preserving all other roads and regions.
    field_cells = _refresh_local_road_fields(world, road, original_points,
                                             road_data["stationEdits"])
    return {"id":SEAM,"region":REGION,"status":"applied",
            "dataSha256":data_sha,"changedCells":len(edits),
            "roadStationsChanged":len(road_data["stationEdits"]),
            "roadFieldInfluenceCells":field_cells,
            "maximumChangeMetres":max(abs(item["after"]-item["before"])
                                     for item in data["terrainEdits"]),
            "maximumGrade":grade}
