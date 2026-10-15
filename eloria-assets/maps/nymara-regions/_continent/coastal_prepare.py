"""Prepare ordinary one-road coastal bridge claims as one atomic terrain epoch."""
from __future__ import annotations

import hashlib
import math
import re
from types import SimpleNamespace

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon

import bridge_export as B
import bridge_profiles as BP
import coastal_bank_fit as F
import landscape as L
import sea_crossings as S


LANDING_LIMIT_METRES = 6.
JOIN_SEARCH_STEP_METRES = .125
LOCAL_GUARD_METRES = 2. * math.sqrt(2.)
DEFAULT_EXCLUDED_ROADS = frozenset({
    S.COMPONENT500_ROAD,
    S.COMPONENT501_ROAD,
    "discovery-manymouth_delta-1003",
    "door-crownwater-cistern-stair",
    "discovery-westhaven-832",
})
HATCHERY_GROUP_ROAD = "door-ssarathi_ruins-hatchery-descent"
HATCHERY_GROUP_SEEDS = frozenset((2311067, 2321563))
COMPONENT501_OUTER_LANDING_STATIONS_METRES = (415.64353621790934, 486.27749393955537)
COMPONENT501_EMITTED_CAP_STATIONS_METRES = (416.14353621790934, 485.77749393955537)
COMPONENT502_LANDING_METRES = 5.125


def _road_by_id(world, road_id):
    return S.require_road(world.roads, str(road_id))


def _eligible_components(inventory, excluded):
    result = []
    for component in inventory.get("components", ()):
        roads = tuple(map(str, component.get("roadIds", ())))
        wet_roads = tuple(map(str, component.get("fullWidthWaterRoadIds", ())))
        if len(roads) != 1 or wet_roads != roads or roads[0] in excluded:
            continue
        matches = [item for item in component.get("fullWidthWaterCells", ())
                   if str(item.get("roadId")) == roads[0]]
        if len(matches) != 1 or not matches[0].get("looseWetCells"):
            raise S.CoastalGeometryError("ordinary coastal component has no unique wet-road authority",
                                          componentSeed=component.get("componentSeed"),
                                          roadIds=list(roads))
        result.append((component, matches[0]))
    return tuple(sorted(result, key=lambda value: (
        value[0]["roadIds"][0], tuple(value[0].get("bounds", ())),
        tuple(value[0]["looseWetCells"]))))


def _group_explicit_components(eligible):
    """Replace the two authorized Hatchery contacts with one outer-bank span."""
    eligible = tuple(eligible)
    hatchery = [(component, binding) for component, binding in eligible
                if tuple(map(str, component.get("roadIds", ()))) == (HATCHERY_GROUP_ROAD,)]
    if not hatchery:
        return eligible
    seeds = frozenset(int(component["componentSeed"]) for component, _ in hatchery)
    if seeds != HATCHERY_GROUP_SEEDS or len(hatchery) != 2:
        raise S.CoastalGeometryError(
            "Hatchery grouped crossing inventory does not match its two authorized contacts",
            roadId=HATCHERY_GROUP_ROAD, componentSeeds=sorted(seeds))
    cells = tuple(sorted({int(cell) for component, _ in hatchery
                          for cell in component["looseWetCells"]}))
    bounds = np.asarray([component["bounds"] for component, _ in hatchery], int)
    combined = dict(hatchery[0][0])
    combined.update({
        "componentSeed": min(HATCHERY_GROUP_SEEDS),
        "groupedComponentSeeds": tuple(sorted(HATCHERY_GROUP_SEEDS)),
        "looseWetCells": cells,
        "bounds": [int(bounds[:, 0].min()), int(bounds[:, 1].max()),
                   int(bounds[:, 2].min()), int(bounds[:, 3].max())],
        "fullWidthWaterCells": ({"roadId": HATCHERY_GROUP_ROAD,
                                 "looseWetCells": cells},),
    })
    binding = {"roadId": HATCHERY_GROUP_ROAD, "looseWetCells": cells}
    result = [(component, item) for component, item in eligible
              if str(component["roadIds"][0]) != HATCHERY_GROUP_ROAD]
    result.append((combined, binding))
    return tuple(sorted(result, key=lambda value: (
        value[0]["roadIds"][0], tuple(value[0].get("bounds", ())),
        tuple(value[0]["looseWetCells"]))))


def _nearest_stations(points, query):
    points = np.asarray(points, float); query = np.atleast_2d(np.asarray(query, float))
    source = S.cumulative_stations(points); xz = points[:, [0, 2]]
    best = np.full(len(query), np.inf); stations = np.zeros(len(query))
    for index, (a, b) in enumerate(zip(xz, xz[1:])):
        delta = b-a; length = float(delta@delta)
        ratio = np.clip((query-a)@delta/length, 0., 1.)
        projected = a+ratio[:, None]*delta
        distance = np.sum((query-projected)**2, axis=1)
        use = distance < best
        best[use] = distance[use]
        stations[use] = source[index]+ratio[use]*(source[index+1]-source[index])
    return stations


def _cell_centres(world, shape, cells):
    rows, cols = np.unravel_index(np.asarray(cells, np.int64), tuple(shape))
    cell = float(B.CELL)
    return np.c_[world.x0+(cols+.5)*cell, world.z0+(rows+.5)*cell]


def _bounds_for_interval(world, points, half_width, low, high, guard=LOCAL_GUARD_METRES):
    xz = S.route_search_bounds(points, half_width, ((float(low), float(high)),), guard)
    cell = float(np.asarray(world.x, float)[1]-np.asarray(world.x, float)[0])
    lower = np.floor((xz[:2]-[world.x0, world.z0])/cell).astype(int)-1
    upper = np.ceil((xz[2:]-[world.x0, world.z0])/cell).astype(int)+1
    nz, nx = np.asarray(world.height).shape
    return (max(0, int(lower[0])), min(nx-1, int(upper[0])),
            max(0, int(lower[1])), min(nz-1, int(upper[1])))


def _outline_factory(roads):
    return B.RoadOutline(SimpleNamespace(roads=roads))


def _flat_surface(name, road, low, high):
    values = np.asarray([low, high], float)
    return S.indexed_road_union_probe_surface(
        name, "coastal-wet-search", str(road["id"]), np.asarray(road["points"], float),
        float(road["width"]), float(low), float(high), values, np.zeros(2),
        _outline_factory)[0]


def _water_authority(world, bounds):
    authority = B._encoded_water_authority(world, bounds)
    faces = np.asarray(authority["faces"], float)
    return authority, {"sea": faces, "river": np.empty((0, 3, 3)),
                       "lake": np.empty((0, 3, 3))}


def _exact_water_evidence(surface, groups, world):
    evidence = S.emitted_water_evidence(surface, groups)
    helper = getattr(S, "exact_domain_evidence", None)
    if helper is None:
        raise S.CoastalGeometryError("exact coastal water-domain helper is unavailable")
    return helper(evidence, world, L)


def _water_union(groups):
    polygons = [Polygon(face[:, [0, 2]]) for faces in groups.values() for face in faces]
    polygons = [value for value in polygons if value.area > 0.]
    if not polygons:
        raise S.CoastalGeometryError("ordinary coastal component has no emitted water geometry")
    return shapely.union_all(polygons)


def _require_wet_cell_coverage(world, shape, cells, evidence, road_id):
    pieces = [Polygon(np.asarray(piece["xz"], float)) for piece in evidence.get("pieces", ())]
    wet_union = shapely.union_all(pieces) if pieces else Polygon()
    cell = float(B.CELL)
    rows, cols = np.unravel_index(np.asarray(cells, np.int64), tuple(shape))
    missing = []
    for flat, row, col in zip(cells, rows, cols):
        square = shapely.box(world.x0+col*cell, world.z0+row*cell,
                             world.x0+(col+1)*cell, world.z0+(row+1)*cell)
        if square.intersection(wet_union).area <= 0.: missing.append(int(flat))
    if missing:
        raise S.CoastalGeometryError("ordinary coastal floor misses an owned wet cell",
                                      roadId=str(road_id), missingWetCells=missing)


def _owned_water_evidence(world, shape, cells, evidence, road_id):
    """Select this loose component's water contact from a wider probe."""
    cell = float(B.CELL)
    rows, cols = np.unravel_index(np.asarray(cells, np.int64), tuple(shape))
    owned = shapely.union_all([shapely.box(world.x0+col*cell, world.z0+row*cell,
                                           world.x0+(col+1)*cell, world.z0+(row+1)*cell)
                               for row, col in zip(rows, cols)])
    pieces = [dict(piece) for piece in evidence.get("pieces", ())]
    intervals = [(float(np.min(piece["stations"])), float(np.max(piece["stations"])))
                 for piece in pieces]
    selected_indices = set()
    for index, piece in enumerate(pieces):
        polygon = Polygon(np.asarray(piece["xz"], float))
        if polygon.intersection(owned).area > 0.:
            selected_indices.add(index)
    if not selected_indices:
        raise S.CoastalGeometryError("ordinary coastal component has no owned emitted-water contact",
                                      roadId=str(road_id), looseWetCells=list(map(int, cells)))
    # A coarse owned cell chooses a connected station interval; it does not
    # clip that interval at the cell boundary.  Include every actual contact
    # piece transitively joined to the selected pieces, but not a neighbour
    # separated by a positive dry station gap.
    changed = True
    while changed:
        changed = False
        for index, (low, high) in enumerate(intervals):
            if index in selected_indices: continue
            if any(low <= intervals[other][1] and intervals[other][0] <= high
                   for other in selected_indices):
                selected_indices.add(index); changed = True
    selected = [piece for index, piece in enumerate(pieces) if index in selected_indices]
    result = dict(evidence); result["pieces"] = selected
    intervals = sorted((float(np.min(piece["stations"])), float(np.max(piece["stations"])))
                       for piece in selected)
    merged = []
    for low, high in intervals:
        if merged and low <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], high)
        else: merged.append([low, high])
    kinds = sorted({str(piece["kind"]) for piece in selected})
    result.update({"wetExtentMetres": [merged[0][0], merged[-1][1]],
                   "continuousStationIntervalsMetres": merged,
                   "continuous": len(merged) == 1,
                   "contactKinds": kinds, "pureSea": kinds == ["sea"],
                   "nonSeaContactKinds": sorted(set(kinds)-{"sea"}),
                   "wetAreaSquareMetres": float(sum(piece["areaSquareMetres"] for piece in selected))})
    result["clear"] = bool(result["pureSea"] and result["continuous"] and
                           result.get("clearanceClear", True))
    _require_wet_cell_coverage(world, shape, cells, result, road_id)
    return result


def _dry_join(points, half_width, wet_station, direction, water_union):
    distances = S.cumulative_stations(points); total = float(distances[-1])
    candidates = [wet_station+direction*offset
                  for offset in np.arange(JOIN_SEARCH_STEP_METRES,
                                          LANDING_LIMIT_METRES+JOIN_SEARCH_STEP_METRES*.5,
                                          JOIN_SEARCH_STEP_METRES)]
    candidates.extend(float(value) for value in distances
                      if 0. < direction*(value-wet_station) <= LANDING_LIMIT_METRES)
    candidates = sorted({float(value) for value in candidates if 0. < value < total},
                        key=lambda value: direction*(value-wet_station))
    tested = []
    for station in candidates:
        if direction*(station-wet_station) <= 0.: continue
        section = S._section(points, distances, station, half_width).astype(np.float32).astype(float)
        contact = LineString(section[:, [0, 2]]).intersection(water_union)
        tested.append({"stationMetres": station, "waterIntersectionEmpty": bool(contact.is_empty)})
        if contact.is_empty:
            return station, tuple(tested)
    raise S.CoastalGeometryError("ordinary coastal component has no full-width dry join within six metres",
                                  wetStationMetres=float(wet_station), direction=int(direction),
                                  tested=tested)


def _claim_id(road_id, loose_cells):
    digest = hashlib.sha256(np.asarray(tuple(sorted(map(int, loose_cells))), dtype="<i8").tobytes()).hexdigest()[:12]
    token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(road_id)).strip("-")
    return f"ordinary-{token}-{digest}"


def _plan_component(world, inventory, component, binding):
    road_id = str(component["roadIds"][0]); road = _road_by_id(world, road_id)
    points = np.asarray(road["points"], float); distances = S.cumulative_stations(points)
    centres = _cell_centres(world, inventory["shape"], binding["looseWetCells"])
    seeds = _nearest_stations(points, centres)
    low = max(0., float(seeds.min())-8.); high = min(float(distances[-1]), float(seeds.max())+8.)
    if not low < high:
        raise S.CoastalGeometryError("ordinary coastal wet-cell station envelope is empty", roadId=road_id)
    search_bounds = _bounds_for_interval(world, points, float(road["width"]), low, high)
    _, groups = _water_authority(world, search_bounds)
    broad = _flat_surface(f"Probe_Ordinary_{_claim_id(road_id, component['looseWetCells'])}", road, low, high)
    wet = _owned_water_evidence(world, inventory["shape"], binding["looseWetCells"],
                                _exact_water_evidence(broad, groups, world), road_id)
    grouped = tuple(map(int, component.get("groupedComponentSeeds", ())))
    grouped_clear = (frozenset(grouped) == HATCHERY_GROUP_SEEDS and len(grouped) == 2 and
                     road_id == HATCHERY_GROUP_ROAD and wet.get("pureSea") and
                     wet.get("clearanceClear", True) and
                     len(wet.get("continuousStationIntervalsMetres", ())) == 2)
    if not grouped_clear and (not wet.get("clear") or not wet.get("continuous") or
                              not wet.get("pureSea")):
        raise S.CoastalGeometryError("ordinary coastal component is not one continuous pure-sea crossing",
                                      roadId=road_id, contactKinds=wet.get("contactKinds"),
                                      intervals=wet.get("continuousStationIntervalsMetres"))
    wet_low, wet_high = map(float, wet["wetExtentMetres"])
    water_union = _water_union(groups)
    left, left_tested = _dry_join(points, float(road["width"]), wet_low, -1, water_union)
    right, right_tested = _dry_join(points, float(road["width"]), wet_high, 1, water_union)
    if left <= 0. or right >= distances[-1]:
        raise S.CoastalGeometryError("ordinary coastal joins leave no continuing-road approach", roadId=road_id)
    bounds = _bounds_for_interval(world, points, float(road["width"]),
                                  max(0., left-LANDING_LIMIT_METRES),
                                  min(float(distances[-1]), right+LANDING_LIMIT_METRES))
    return {"claimId": _claim_id(road_id, component["looseWetCells"]),
            "component": component, "road": road, "points": points,
            "inventoryShape": tuple(map(int, inventory["shape"])),
            "wetExtentMetres": (wet_low, wet_high), "joinStationsMetres": (left, right),
            "continuousStationIntervalsMetres": tuple(
                tuple(map(float, interval))
                for interval in wet["continuousStationIntervalsMetres"]),
            "groupedComponentSeeds": grouped,
            "bounds": bounds, "joinSearch": {"left": left_tested, "right": right_tested}}


def _water_incident_nodes(world, authority):
    width = np.asarray(world.height).shape[1]-1; result = set()
    for cell in np.asarray(authority["sourceCells"], int):
        row, col = divmod(int(cell), width)
        result.update(((row, col), (row, col+1), (row+1, col), (row+1, col+1)))
    return result


def _protected_nodes(world, plans, content, before):
    result = {tuple(map(int, value)) for value in
              np.asarray(getattr(world, "claimed_bridge_protected_nodes", ()), int).reshape(-1, 2)}
    for authority in before.values(): result.update(_water_incident_nodes(world, authority))
    footprints, _ = B._retained_footprints(content)
    footprints = B._crop_footprints(world, footprints, [plan["bounds"] for plan in plans])
    for plan in plans:
        for nodes, triangle in B._terrain_triangles(world, plan["bounds"]):
            if any(B._footprint_intersects_triangle(footprint, triangle) for footprint in footprints):
                result.update(nodes)
    return tuple(sorted(result))


def _request(world, plan, pins, source_sha):
    road = plan["road"]; points = plan["points"]
    left, right = plan["joinStationsMetres"]; total = float(S.cumulative_stations(points)[-1])
    preview = S.indexed_road_union_surface(
        f"Probe_Joins_{plan['claimId']}", "coastal-join-authority", str(road["id"]),
        points, float(road["width"]), left, right, np.asarray([left, right]),
        np.zeros(2), _outline_factory, [[left, right, []]])[0]
    return S.coastal_bank_fit_request(
        plan["claimId"], road, left, right,
        (max(0., left-LANDING_LIMIT_METRES), left),
        (right, min(total, right+LANDING_LIMIT_METRES)), pins, source_sha,
        join_sections=preview.sections)


def _build_surface(world, plan, fit, groups):
    road = plan["road"]; points = plan["points"]; width = float(road["width"])
    wet_low, wet_high = plan["wetExtentMetres"]; left, right = plan["joinStationsMetres"]
    clearance = float(world.plan["crossing_policy"]["deck_clearance_metres"])
    rise = float(BP.arch_rise(wet_high-wet_low, clearance, S.MAXIMUM_GRADE))
    terrain = S.crop_terrain(world, S.route_search_bounds(
        points, width, ((left, right),), LOCAL_GUARD_METRES))
    expected_intervals = np.asarray(
        plan.get("continuousStationIntervalsMetres", ((wet_low, wet_high),)), float)
    grouped = bool(plan.get("groupedComponentSeeds", ()))

    def domain_classifier(evidence):
        return S.exact_domain_evidence(evidence, world, L)

    return S.solve_broad_middle_surface(
        f"Walk_Coastal_{plan['claimId']}", "coastal-indexed-arch", str(road["id"]),
        points, width, left, (wet_low, wet_high), right,
        (float(fit.left_deck_height_metres), float(fit.right_deck_height_metres)),
        terrain, groups, clearance, rise, _outline_factory,
        adjustable_endpoint="right", domain_classifier=domain_classifier,
        multi_contact_intervals_metres=(expected_intervals if grouped else ()))


def _claim(world, plan, fit, before, after):
    unchanged, fields = B._same_water_authority(before, after)
    if not unchanged:
        raise S.CoastalGeometryError("ordinary coastal fit changed emitted hydrology",
                                      claimId=plan["claimId"], changedFields=fields)
    _, groups = _water_authority(world, plan["bounds"])
    surface, metadata, authority, solve_report = _build_surface(world, plan, fit, groups)
    exact = solve_report["evidence"]
    coverage = exact["capsuleCoverage"]
    water = exact["emittedWater"]
    joins = exact["fullWidthJoins"]
    terrain_clearance = dict(exact["terrainClearance"])
    _require_wet_cell_coverage(world, plan["inventoryShape"],
                               plan["component"]["looseWetCells"], water,
                               plan["road"]["id"])
    terrain_clearance.update({"bankFit": fit.report(), "hydrologyUnchanged": fields,
                              "indexedUnion": metadata, "broadMiddleSolve": solve_report})
    evidence = {"capsuleCoverage": coverage, "emittedWater": water,
                "fullWidthJoins": joins, "terrainClearance": terrain_clearance}
    if plan["groupedComponentSeeds"]:
        evidence["multiContactOwnership"] = {
            "acceptanceAuthority": True, "clear": True, "outerJoinOnly": True,
            "sourceComponentSeeds": list(plan["groupedComponentSeeds"]),
            "ownedLooseWetCells": list(map(int, plan["component"]["looseWetCells"])),
            "contactIntervalsMetres": water["continuousStationIntervalsMetres"],
        }
    claim = S.CoastalClaim(plan["claimId"], int(plan["component"]["componentSeed"]),
                           (str(plan["road"]["id"]),), tuple(map(float, water["wetExtentMetres"])),
                           tuple(map(float, plan["joinStationsMetres"])), (surface,),
                           loose_wet_cells=tuple(map(int, plan["component"]["looseWetCells"])),
                           evidence=evidence)
    return S.validate_claim(claim)


def prepare_ordinary_single_road_claims(world, inventory, *, content=None,
                                        exclude_road_ids=()):
    """Fit and construct every ordinary one-road coastal claim atomically.

    The returned tuple is complete only for the eligible inventory subset.  It
    never assigns ``world.claimed_coastal_records``; the outer coastal registry
    merges these records with its special and junction claims before publishing.
    """
    if not hasattr(world, "water"):
        raise S.CoastalGeometryError("ordinary coastal preparation requires current hydrology")
    excluded = DEFAULT_EXCLUDED_ROADS | frozenset(map(str, exclude_road_ids))
    eligible = _group_explicit_components(_eligible_components(inventory, excluded))
    if not eligible: return ()
    source_height = np.asarray(world.height, float).copy()
    source_water = world.water
    plans = tuple(_plan_component(world, inventory, component, binding)
                  for component, binding in eligible)
    before = {plan["claimId"]: _water_authority(world, plan["bounds"])[0] for plan in plans}
    pins = _protected_nodes(world, plans, content, before)
    source_sha = F.height_sha256(world.height)
    requests = tuple(_request(world, plan, pins, source_sha) for plan in plans)
    try:
        fits = F.fit_coastal_banks(world, requests, content=content)
        world.water = L.water_fields(world.gx, world.gz, height=world.height, plan=world.plan)
        after = {plan["claimId"]: _water_authority(world, plan["bounds"])[0] for plan in plans}
        fit_by_id = {value.claim_id: value for value in fits}
        if set(fit_by_id) != {plan["claimId"] for plan in plans}:
            raise S.CoastalGeometryError("ordinary coastal bank fitter returned an incomplete claim set")
        claims = tuple(_claim(world, plan, fit_by_id[plan["claimId"]],
                              before[plan["claimId"]], after[plan["claimId"]])
                       for plan in plans)
        owned = [cell for claim in claims for cell in claim.loose_wet_cells]
        expected = [cell for plan in plans for cell in plan["component"]["looseWetCells"]]
        if len(owned) != len(set(owned)) or set(owned) != set(expected):
            raise S.CoastalGeometryError("ordinary coastal claims do not exactly partition their wet cells")
        return claims
    except Exception:
        world.height[...] = source_height
        world.water = source_water
        raise


def _selected_inventory_member(inventory, identity, label):
    """Bind one selected road by stable identity and complete live cell authority."""
    identity = str(identity)
    matches = []
    for component in inventory.get("components", ()):
        roads = tuple(map(str, component.get("roadIds", ())))
        wet_roads = tuple(map(str, component.get("fullWidthWaterRoadIds", ())))
        bindings = tuple(component.get("fullWidthWaterCells", ()))
        mentions = identity in roads or identity in wet_roads or any(
            str(item.get("roadId")) == identity for item in bindings)
        if not mentions:
            continue
        if roads != (identity,) or wet_roads != roads:
            raise S.CoastalGeometryError(
                f"{label} appears outside its exact single-road inventory member",
                roadId=identity, componentSeed=component.get("componentSeed"),
                roadIds=list(roads), fullWidthWaterRoadIds=list(wet_roads))
        bindings = [item for item in bindings if str(item.get("roadId")) == identity]
        cells = tuple(map(int, component.get("looseWetCells", ())))
        if len(bindings) != 1 or tuple(map(int, bindings[0].get("looseWetCells", ()))) != cells:
            raise S.CoastalGeometryError(
                f"{label} live full-width binding is incomplete",
                roadId=identity, componentSeed=component.get("componentSeed"))
        matches.append(component)
    if len(matches) != 1:
        raise S.CoastalGeometryError(f"{label} live ownership is ambiguous",
                                     roadId=identity, matches=len(matches))
    return matches[0]


def _component501_inventory_member(inventory):
    """Bind 501 by stable road and its complete live loose-cell authority."""
    return _selected_inventory_member(inventory, S.COMPONENT501_ROAD, "component 501")


def _component502_inventory_member(inventory):
    """Bind 502 by stable road and its complete live loose-cell authority."""
    return _selected_inventory_member(inventory, S.COMPONENT502_ROAD, "component 502")


def prepare_component501_claim(world, inventory, *, content=None):
    """Fit and validate the one selected component-501 claim on the current epoch."""
    if not hasattr(world, "water"):
        raise S.CoastalGeometryError("component 501 preparation requires current hydrology")
    component = _component501_inventory_member(inventory)
    road = _road_by_id(world, S.COMPONENT501_ROAD)
    points = np.asarray(road["points"], float); width = float(road["width"])
    distances = S.cumulative_stations(points)
    outer_left, outer_right = COMPONENT501_OUTER_LANDING_STATIONS_METRES
    left, right = COMPONENT501_EMITTED_CAP_STATIONS_METRES
    if not (distances[0] < outer_left < left < right < outer_right < distances[-1]):
        raise S.CoastalGeometryError("component 501 bounded stations left the continuing road")
    bounds = _bounds_for_interval(world, points, width,
                                  max(0., outer_left-LANDING_LIMIT_METRES),
                                  min(float(distances[-1]), outer_right+LANDING_LIMIT_METRES))
    source_height = np.asarray(world.height, float).copy(); source_water = world.water
    before, groups = _water_authority(world, bounds)
    probe = _flat_surface("Probe_Coastal501_Water", road,
                          max(0., outer_left-2.), min(float(distances[-1]), outer_right+2.))
    wet = _exact_water_evidence(probe, groups, world)
    if not wet.get("clear") or not wet.get("continuous") or not wet.get("pureSea"):
        raise S.CoastalGeometryError("component 501 is not one continuous pure-sea crossing",
                                     contactKinds=wet.get("contactKinds"),
                                     intervals=wet.get("continuousStationIntervalsMetres"))
    wet_low, wet_high = map(float, wet["wetExtentMetres"])
    if not (outer_left <= left <= wet_low <= wet_high <= right <= outer_right and
            wet_low-outer_left <= LANDING_LIMIT_METRES and
            outer_right-wet_high <= LANDING_LIMIT_METRES):
        raise S.CoastalGeometryError("component 501 bounded stations no longer enclose its wet extent",
                                     wetExtentMetres=[wet_low, wet_high],
                                     outerLandingStationsMetres=[outer_left, outer_right],
                                     emittedCapStationsMetres=[left, right])
    preview = S.indexed_road_union_surface(
        "Probe_Coastal501_FitCaps", "coastal-join-authority", str(road["id"]),
        points, width, left, right, np.asarray([left, right]),
        np.zeros(2), _outline_factory, [[left, right, []]])[0]
    plan = {"bounds": bounds}
    pins = _protected_nodes(world, (plan,), content, {"coastal-501": before})
    request = S.coastal_bank_fit_request(
        "coastal-501", road, left, right,
        (max(0., left-LANDING_LIMIT_METRES), left),
        (right, min(float(distances[-1]), right+LANDING_LIMIT_METRES)),
        pins, F.height_sha256(world.height), join_sections=preview.sections)
    try:
        fits = tuple(F.fit_coastal_banks(world, (request,), content=content))
        if len(fits) != 1 or fits[0].claim_id != "coastal-501":
            raise S.CoastalGeometryError("component 501 bank fitter returned the wrong result")
        fit = fits[0]
        world.water = L.water_fields(world.gx, world.gz, height=world.height, plan=world.plan)
        after, groups = _water_authority(world, bounds)
        unchanged, fields = B._same_water_authority(before, after)
        if not unchanged:
            raise S.CoastalGeometryError("component 501 bank fit changed emitted hydrology",
                                         changedFields=fields)
        clearance = float(world.plan["crossing_policy"]["deck_clearance_metres"])
        rise = float(BP.arch_rise(wet_high-wet_low, clearance, S.MAXIMUM_GRADE))
        terrain = S.crop_terrain(world, S.route_search_bounds(
            points, width, ((left, right),), LOCAL_GUARD_METRES))
        surface, metadata, authority, solved = S.prepare_component501_surface(
            road, (left, right), (wet_low, wet_high),
            (float(fit.left_deck_height_metres), float(fit.right_deck_height_metres)),
            terrain, groups, clearance, rise, _outline_factory,
            lambda evidence: S.exact_domain_evidence(evidence, world, L))
        exact = solved["evidence"]
        _require_wet_cell_coverage(world, inventory["shape"],
                                   component["looseWetCells"],
                                   exact["emittedWater"], road["id"])
        terrain_clearance = dict(exact["terrainClearance"])
        terrain_clearance.update({"bankFit": fit.report(),
                                  "hydrologyUnchanged": fields,
                                  "indexedUnion": metadata,
                                  "coverageAuthority": authority,
                                  "broadMiddleSolve": solved})
        edits = tuple(edit for edit in getattr(world, "applied_coastal_road_edits", ())
                      if edit.road_id == S.COMPONENT501_ROAD)
        claim = S.CoastalClaim(
            "coastal-501", int(component["componentSeed"]), (S.COMPONENT501_ROAD,),
            tuple(map(float, exact["emittedWater"]["wetExtentMetres"]),),
            (left, right), (surface,), road_edits=edits,
            loose_wet_cells=tuple(map(int, component["looseWetCells"])),
            evidence={"capsuleCoverage": exact["capsuleCoverage"],
                      "emittedWater": exact["emittedWater"],
                      "fullWidthJoins": exact["fullWidthJoins"],
                      "terrainClearance": terrain_clearance})
        return S.validate_claim(claim)
    except Exception:
        world.height[...] = source_height; world.water = source_water
        raise


def prepare_component502_claim(world, inventory, *, content=None):
    """Build the selected one-bank terminal claim without changing terrain or water."""
    del content
    if not hasattr(world, "water"):
        raise S.CoastalGeometryError("component 502 preparation requires current hydrology")
    component = _component502_inventory_member(inventory)
    road = _road_by_id(world, S.COMPONENT502_ROAD)
    points = np.asarray(road["points"], float); width = float(road["width"])
    distances = S.cumulative_stations(points); total = float(distances[-1])
    cells = tuple(map(int, component["looseWetCells"]))
    centres = _cell_centres(world, inventory["shape"], cells)
    seeds = _nearest_stations(points, centres)
    target = max(0., float(seeds.min())-8.)
    earlier = distances[distances <= target]
    probe_start = float(earlier[-1]) if len(earlier) else 0.
    bounds = _bounds_for_interval(world, points, width, probe_start, total)
    _, groups = _water_authority(world, bounds)
    probe = S.indexed_road_union_surface(
        "Probe_Component502_Terminal", "coastal-terminal-wet-search", str(road["id"]),
        points, width, probe_start, total, np.asarray([probe_start, total]),
        np.zeros(2), _outline_factory, terminal_sides=("right",))[0]
    wet = _owned_water_evidence(
        world, inventory["shape"], cells,
        _exact_water_evidence(probe, groups, world), road["id"])
    if not wet.get("clear") or not wet.get("continuous") or not wet.get("pureSea"):
        raise S.CoastalGeometryError(
            "component 502 is not one continuous pure-sea terminal crossing",
            contactKinds=wet.get("contactKinds"),
            intervals=wet.get("continuousStationIntervalsMetres"))
    wet_start, wet_end = map(float, wet["wetExtentMetres"])
    landward = wet_start-COMPONENT502_LANDING_METRES
    if wet_end != total:
        raise S.CoastalGeometryError(
            "component 502 wet authority does not reach the authored terminal",
            wetEndStationMetres=wet_end, terminalStationMetres=total)
    if wet_start-landward > LANDING_LIMIT_METRES:
        raise S.CoastalGeometryError("component 502 landward landing exceeds its source rule",
                                     landingMetres=wet_start-landward,
                                     limitMetres=LANDING_LIMIT_METRES)
    terrain = S.crop_terrain(
        world, S.route_search_bounds(points, width, ((landward, total),), 3.),
        padding_metres=4.)
    clearance = float(world.plan["crossing_policy"]["deck_clearance_metres"])
    rise = float(BP.arch_rise(wet_end-wet_start, clearance, S.MAXIMUM_GRADE))
    surface, support, metadata, authority, solved = S.prepare_component502_surface(
        road, landward, (wet_start, wet_end), terrain, groups, clearance, rise,
        _outline_factory, lambda evidence: S.exact_domain_evidence(evidence, world, L))
    exact = solved["evidence"]
    owned_water = _owned_water_evidence(
        world, inventory["shape"], cells, exact["emittedWater"], road["id"])
    evidence = dict(exact); evidence["emittedWater"] = owned_water
    terrain_clearance = dict(evidence["terrainClearance"])
    terrain_clearance.update({"indexedUnion": metadata,
                              "coverageAuthority": authority,
                              "terminalSolve": solved})
    evidence["terrainClearance"] = terrain_clearance
    claim = S.CoastalClaim(
        "coastal-502", int(component["componentSeed"]), (S.COMPONENT502_ROAD,),
        tuple(map(float, owned_water["wetExtentMetres"])), (landward, total),
        (surface,), supports=(support,), loose_wet_cells=cells,
        terminal_sides=("right",), evidence=evidence)
    return S.validate_claim(claim)
