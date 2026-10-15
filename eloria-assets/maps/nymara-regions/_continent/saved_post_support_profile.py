"""Apply reviewed saved-seam shoulder heights after the last terrain support.

The data is a fixed source artifact, not an earthworks solver. Its local
preconditions make a changed seam or support ask for a fresh review while
allowing unrelated authoring edits and new saved authority in the neighbour.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SIDECAR = HERE / "saved-seam-post-support-v1.json"
SCHEMA = "eloria-saved-post-support-seam-profile-v1"
PHASE = "after-final-authored-terrain-before-final-seam-validation"
ROADS_SHA = "6ec5f505abce4f8b219bfa4278d59d7b8d9d8038a65cddf461b422a7986463f8"
WHITEHORN_BASE_SHA = "6b25ba0f7bbd5ae21ff8eede5498afee207541471fd08f026842ac1d0e55fd79"
MIRRORHOLD_BASE_SHA = "0511c783876d44444e27a435cb3f78f88f1f9fa2869907102cfa628aebff12ab"
PRIOR_GREY_DATA_SHA = "9d9506ab51d3680ebab40fa8f3c1dbd6ca48245eef2ec9a3729db3548b3b5279"
MIRRORHOLD_SNAPSHOT_SHA = "212ccf6d9977038e28d4c572aa0efe198ce95f4de13cb1aed201a243b0b936f7"
WHITEHORN_SNAPSHOT_SHA = "e6ac6aea01c624834475318646565776c470575778a3df0fbe743f4dd2361c64"
SOURCES = {
    "amberwoodSupportSourceSha256": "a7d31b7a572e08d84994e0344a132fe261256555282e81a6e1cd5e7c839301fe",
    "reachLinksSourceSha256": "890cc5f545655141c93546e4714cac779db0a7ab5c9072c268b897d4a3d37643",
    "landscapeSourceSha256": "7297ad2a12b3ce53e1d0ff5c74e2a0b22a4c13b391cee30cca1fe8ee90208e9b",
}
PAIRINGS = {
    "amberwood--mirrorhold": ("amberwood", "mirrorhold", MIRRORHOLD_SNAPSHOT_SHA),
    "grey_moors--whitehorn_range": ("grey_moors", "whitehorn_range", WHITEHORN_SNAPSHOT_SHA),
}
MAX_GRADE = .65
CHECK_METRES = 72.


def _fail(reason):
    raise ValueError("saved post-support seam profile incompatible: " + reason +
                     "; review the local seam/support sidecar against the new authoring")


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(data):
    return hashlib.sha256(_canonical(data)).hexdigest()


def _route_sha(points):
    return hashlib.sha256(np.asarray(points, dtype="<f8").tobytes()).hexdigest()


def _same(a, b):
    return bool(np.allclose(a, b, rtol=0., atol=1e-7))


def _load():
    data = json.loads(SIDECAR.read_text(encoding="utf-8"))
    claimed = data.pop("dataSha256", None)
    if claimed != _sha(data):
        _fail("sidecar data SHA-256 mismatch")
    if data.get("schema") != SCHEMA or data.get("phase") != PHASE:
        _fail("sidecar schema or terrain phase changed")
    expected = {
        "certifiedPublishedRoadsSha256": ROADS_SHA,
        "whitehornBaseHeightsSha256": WHITEHORN_BASE_SHA,
        "mirrorholdBaseHeightsSha256": MIRRORHOLD_BASE_SHA,
        "priorGreySeamProfileDataSha256": PRIOR_GREY_DATA_SHA,
        **SOURCES,
    }
    if data.get("provenance") != expected:
        _fail("certified source provenance changed")
    actual_sources = {
        "amberwoodSupportSourceSha256": hashlib.sha256((HERE / "amberwood_support.py").read_bytes()).hexdigest(),
        "reachLinksSourceSha256": hashlib.sha256((HERE / "reach_links.py").read_bytes()).hexdigest(),
        "landscapeSourceSha256": hashlib.sha256((HERE / "landscape.py").read_bytes()).hexdigest(),
    }
    if actual_sources != SOURCES:
        _fail("Amberwood/reach terrain support implementation changed")
    entries = data.get("entries")
    if not isinstance(entries, list) or {row.get("seamId") for row in entries} != set(PAIRINGS) or len(entries) != len(PAIRINGS):
        _fail("saved seam records changed")
    return data, claimed


def _grid_index(world, xz):
    x, z = map(float, xz)
    ix = (x - world.x0) / 2.
    iz = (z - world.z0) / 2.
    if ix != round(ix) or iz != round(iz):
        _fail(f"non-grid shoulder vertex {xz}")
    ix, iz = int(round(ix)), int(round(iz))
    if not (0 <= iz < world.height.shape[0] and 0 <= ix < world.height.shape[1]):
        _fail(f"shoulder vertex outside continent grid {xz}")
    return iz, ix


def _distance_to_path(point, path):
    point = np.asarray(point, dtype=float)
    path = np.asarray(path, dtype=float)
    best = np.inf
    for a, b in zip(path, path[1:]):
        d = b-a
        t = np.clip((point-a)@d/max(float(d@d), 1e-9), 0., 1.)
        best = min(best, float(np.linalg.norm(point-(a+t*d))))
    return best


def _check_protected_core(world, entry):
    points = [cell["xz"] for cell in entry["terrainEdits"]]
    kind = entry["protectedCore"]["kind"]
    if kind == "amberwood-support":
        from amberwood_support import authored_routes, branch_routes
        routes = {**authored_routes(world), **branch_routes(world)}
        core = entry["protectedCore"]
        if core["route"] != "amber-side-kilnyard" or core["halfWidthMetres"] != 3.6:
            _fail("Amberwood support core identity or width changed")
        if core["route"] not in routes or _route_sha(routes[core["route"]]) != core["routeXzSha256"]:
            _fail("Amberwood support route moved")
        for point in points:
            if any(_distance_to_path(point, route) <= core["halfWidthMetres"]+1e-7
                   for route in routes.values()):
                _fail(f"Amberwood authored support core would change at {point}")
    elif kind == "reach-links":
        import landscape as L
        from reach_links import links
        rows = links(world.plan)
        core = entry["protectedCore"]
        local = {row["id"]: row for row in rows if row["id"] in core["localLinkSha256"]}
        if set(local) != set(core["localLinkSha256"]) or any(
                _sha(local[identity]) != expected for identity, expected in core["localLinkSha256"].items()):
            _fail("Grey reach-link source geometry changed")
        if core["coreWeightThreshold"] != .999:
            _fail("Grey reach core threshold changed")
        for point in points:
            x, z = point
            if any(float(row.get("strength", 1.)) > 0. and
                   float(L._edit_weight(np.asarray(x), np.asarray(z), row)) >=
                   core["coreWeightThreshold"]*float(row.get("strength", 1.)) for row in rows):
                _fail(f"authored reach-link core would change at {point}")
    else:
        _fail("unknown protected support core")


def _incident_edges(world, edits):
    pairs = {}
    for z, x in edits:
        for dz, dx in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            zz, xx = z+dz, x+dx
            if not (0 <= zz < world.height.shape[0] and 0 <= xx < world.height.shape[1]):
                continue
            a, b = tuple(sorted(((z, x), (zz, xx))))
            distance = 2.*np.hypot(a[0]-b[0], a[1]-b[1])
            before = abs(float(world.height[a]-world.height[b]))/distance
            before32 = abs(float(np.float32(world.height[a]))-float(np.float32(world.height[b])))/distance
            pairs[a, b] = distance, before, before32
    return pairs


def _check_edges(world, before):
    for (a, b), (distance, prior, prior32) in before.items():
        after = abs(float(world.height[a]-world.height[b]))/distance
        if after > MAX_GRADE+1e-7 and after > prior+1e-7:
            _fail(f"new/worsened grid edge {a}->{b}: {prior:.6f}->{after:.6f}")
        after32 = abs(float(np.float32(world.height[a]))-float(np.float32(world.height[b])))/distance
        if after32 > MAX_GRADE+1e-7 and after32 > prior32+1e-7:
            _fail(f"new/worsened float32 grid edge {a}->{b}: {prior32:.6f}->{after32:.6f}")


def _check_road(world, entry, road, link, feasibility_gate, grade_gate):
    points = np.asarray(road["points"], float)
    xz = points[:, [0, 2]]
    grade = float(grade_gate(world, road, entry["region"], np.asarray(link["anchor"], float)))
    if grade > MAX_GRADE+1e-8:
        _fail(f"{entry['seamId']}: complete final-ground 72 m grade {grade:.6f} exceeds {MAX_GRADE}")
    old_height = world.height
    try:
        world.height = np.asarray(old_height, dtype=np.float32)
        grade32 = float(grade_gate(world, road, entry["region"], np.asarray(link["anchor"], float)))
    finally:
        world.height = old_height
    if grade32 > MAX_GRADE+1e-8:
        _fail(f"{entry['seamId']}: float32 final-ground 72 m grade {grade32:.6f} exceeds {MAX_GRADE}")
    routing = [row for row in world.routing if row.get("name") == road["id"]]
    if not feasibility_gate(world, xz, np.asarray(link["anchor"], float), routing):
        _fail(f"{entry['seamId']}: original road-profile/cut-fill feasibility gate failed")
    return grade, grade32


def apply_post_support_seam_profile(world, authored_regions, feasibility_gate, grade_gate):
    """Install fixed shoulder samples only after all native support terrain is final."""
    if not getattr(world, "reach_links", None) or not getattr(world, "amberwood_support", None):
        _fail("last support terrain has not run")
    data, data_sha = _load()
    if data["grid"] != {"x0":float(world.x0), "z0":float(world.z0),
                        "cellMetres":2.0, "shape":list(world.height.shape)}:
        _fail("continent grid layout changed")
    if ("grey_moors" not in authored_regions and
            getattr(world, "saved_seam_profile", {}).get("dataSha256") != PRIOR_GREY_DATA_SHA):
        _fail("prior saved Grey seam profile missing or changed")
    prepared = []
    statuses = []
    for entry in data["entries"]:
        seam = entry["seamId"]
        region, authored, snapshot_sha = PAIRINGS[seam]
        if entry["region"] != region or entry["authoredRegion"] != authored or entry["source"] != {"authoredSnapshotSha256":snapshot_sha}:
            _fail(f"{seam}: source territory identity changed")
        if authored not in authored_regions or region in authored_regions:
            statuses.append({"id":seam,"region":region,"status":"saved-authority-skip"})
            continue
        links = [row for row in world.connections if row["id"] == seam]
        if len(links) != 1:
            _fail(f"{seam}: connection missing or ambiguous")
        link = links[0]
        if (list(link["regions"]) != entry["link"]["regions"] or
            not _same(link["anchor"], entry["link"]["anchor"]) or
            not _same(link["normal"], entry["link"]["normal"])):
            _fail(f"{seam}: saved anchor, normal or paired territories changed")
        if not any(row.get("id") == seam and row.get("region") == region
                   for row in getattr(world, "saved_seam_approaches", ())):
            _fail(f"{seam}: saved neighbour claim missing")
        roads = [row for row in world.roads if row["id"] == entry["road"]["id"]]
        if len(roads) != 1:
            _fail(f"{seam}: neighbour road missing or ambiguous")
        road = roads[0]
        points = np.asarray(road["points"], float)
        if (road["id"] != seam+"-"+region or len(points) != entry["road"]["stationCount"] or
            _route_sha(points[:, [0, 2]]) != entry["road"]["xzSha256"] or
            not _same(points[-4:, [0, 2]], entry["road"]["terminalXZ"])):
            _fail(f"{seam}: repaired neighbour route identity changed")
        for guard in entry["authoredBoundaryGuard"]:
            z, x = _grid_index(world, guard["xz"])
            if (not world.authored_terrain_authority[z, x] or
                world.ids[int(world.owner_at(*guard["xz"]))] != guard["owner"] or
                not _same(world.height[z, x], guard["height"])):
                _fail(f"{seam}: saved boundary changed at {guard['xz']}")
        _check_protected_core(world, entry)
        edits = {}
        states = set()
        for cell in entry["terrainEdits"]:
            z, x = _grid_index(world, cell["xz"])
            if world.ids[int(world.owner_at(*cell["xz"]))] != region:
                _fail(f"{seam}: neighbour ownership changed at {cell['xz']}")
            if world.authored_terrain_authority[z, x]:
                _fail(f"{seam}: saved terrain now owns shoulder at {cell['xz']}")
            value = float(world.height[z, x])
            state = "before" if _same(value, cell["before"]) else "after" if _same(value, cell["after"]) else None
            if state is None:
                _fail(f"{seam}: local final-support ground changed at {cell['xz']}")
            states.add(state)
            edits[z, x] = cell
        if len(states) != 1:
            _fail(f"{seam}: sidecar was only partially applied")
        prepared.append((entry, road, link, edits, states.pop()))
    all_edits = {index:cell for _entry,_road,_link,edits,state in prepared if state == "before"
                 for index,cell in edits.items()}
    before_edges = _incident_edges(world, all_edits)
    prior = {index:float(world.height[index]) for index in all_edits}
    try:
        for index, cell in all_edits.items():
            world.height[index] = cell["after"]
        _check_edges(world, before_edges)
        for entry, road, link, edits, state in prepared:
            grade, grade32 = _check_road(world, entry, road, link, feasibility_gate, grade_gate)
            statuses.append({"id":entry["seamId"],"region":entry["region"],
                             "status":"applied" if state == "before" else "already-applied",
                             "changedCells":len(edits) if state == "before" else 0,
                             "maximumGrade":grade,"maximumFloat32Grade":grade32})
    except Exception:
        for index, value in prior.items():
            world.height[index] = value
        raise
    return {"phase":PHASE,"dataSha256":data_sha,"entries":statuses,
            "changedCells":len(all_edits),"roadXZChanged":0,"roadQueryFieldsChanged":0}
