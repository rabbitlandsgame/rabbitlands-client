"""crossings_v2.py: where a walker crosses between the continent-v2 isles, by the legacy lane rule.

  python -B eloria-assets/maps/continent-v2/_continent_v2/crossings_v2.py --server <server checkout> \
         [--maps-root <dir holding continent-v2/<region>/client/>] [--out <crossings.json>] [--check] \
         [--checkout <worktree>]

The lanes are the legacy continent's, reused by import from eloria-assets/maps/nymara-regions/_continent/crossings.py
(frozen: imported, never edited): crossings.prepare_contracts lays each road link's seven gate lanes about its anchor
and surveys the roadless borders (open_borders, open_border_contracts); crossings.widen_seams gives every seam every
lane its two maps' ground allows (crossing_lanes: the neighbour's first tile across the border that a walker can step
onto from a tile of this map's own ground, and that the neighbour's grid can stand on); crossings.settle_crossings
opens the roadless borders that have a lane each way and keeps only the lanes a walker can get onto from some map's
arrival and step off at the far end (prune_lanes, by step_bits and flood). The owner's rule is unchanged: ground
walkable on both sides of a border is a way across. What is new here is the stand-in for the legacy world object
(V2World): every catalog territory's frames (frames.py, the four copies agreeing), their ownership polygons (the
bootstrap stubs), and their served grids, read from the published packages and decoded by the server's own codec.
The server's own step rule (collision_sources.walk_step_ok) judges every step at the served grid's climb, 20 codes
of 50 mm: a metre.

Links. The plan's seams (continent-v2-plan.json `seams`: openSeams and moles) name the pairs that meet; each pair's
border is the shared part of the two ownership polygons. A pair an approved route crosses is a road link, anchored
where the lowest-numbered such route crosses the border; the rest are roadless,
anchored at the border point nearest its middle, as
crossings.open_borders anchors the legacy roadless borders. A roadless border left without a lane either way is
withdrawn; a road link left without one is refused.

Contracts, each refused (exit 1) when broken: every mole keeps at least four lanes each way after the 2x2 fold (the
served grid is the fold); no arrival is a departure (publish_diagonal_continent.connection_rows refuses one); every
lane is reciprocal, walked: the walker it lands reaches a departure of a lane back within three legal steps (the
server's rule; check_step_back). The packages must come from one export_collision.py run (each collision block's
groupExport names every package's own snapshot and served grid): a map's collar is its neighbour's export.

Output (crossings.json, written LF with indent 1): the inputs it was made from (the plan's and each package's served
grid's SHA-256, each map's frame, polygon and arrival), the links, the settled connections with their lanes, the
walk-over portal rows (publish_diagonal_continent.connection_rows: the arrival is the departure's own cell read in
the neighbour's tile frame), the exterior-connection entries (publish_diagonal_continent.connection_manifests: the
continent-chunks-v1 frames, preload edges and crossing runs the server and the client read), and a report.
publish_server.py refuses a crossings.json whose inputs differ from the packages it publishes. --check rebuilds it
and compares, without writing.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import frames  # noqa: E402  (also puts the composer's _continent on the path)
import export_collision as X  # noqa: E402  (the server codec guard, the plan's seams, point_in_polygon)
import crossings as C  # noqa: E402  (frozen: imported, never edited)
import ownership as O
from storage_bounds import StorageBounds  # noqa: E402

DEFAULT_CHECKOUT = frames.DEFAULT_CHECKOUT
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/crossings_v2.py"
SCHEMA = "eloria-continent-v2-crossings-v1"
DEFAULT_OUT = "eloria-assets/maps/continent-v2/_continent_v2/crossings.json"
MAPS_ROOT = "eloria-assets/maps"
PACKAGES = "continent-v2"
REVISION = "continent-v2-draft-1"
MOLE_MINIMUM_LANES = 4
STEP_BACK_STEPS = 3          # legal steps a landed walker may take to reach a lane back
ROUTE_TYPES = ("road", "road_inferred")
NEAREST_OPEN = 16            # tiles searched for a height where the point itself is blocked
EPSILON = 1e-9


class CrossingsError(ValueError):
    """An input crossings_v2 refuses, or a contract the settled lanes break."""


def say(*parts):
    print(*parts, flush=True)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def json_text(value):
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


# --- the stand-in for the legacy world --------------------------------------------------------------------------------

def shared_segments(a, b):
    """The parts of polygon a's edges that lie on polygon b's edges, as [[x, z], [x, z]] segments (continent metres)."""
    if len(O.rings(a)) > 1 or len(O.rings(b)) > 1:
        return sorted(segment for ar in O.rings(a) for br in O.rings(b) for segment in shared_segments(ar, br))
    a, b = np.asarray(O.rings(a)[0], float), np.asarray(O.rings(b)[0], float)
    out = []
    for p1, p2 in zip(a, np.roll(a, -1, axis=0)):
        d = p2 - p1
        length2 = float(d @ d)
        if length2 < EPSILON:
            continue
        for q1, q2 in zip(b, np.roll(b, -1, axis=0)):
            cross1 = d[0] * (q1[1] - p1[1]) - d[1] * (q1[0] - p1[0])
            cross2 = d[0] * (q2[1] - p1[1]) - d[1] * (q2[0] - p1[0])
            scale = math.sqrt(length2)
            if abs(cross1) / scale > 1e-6 or abs(cross2) / scale > 1e-6:
                continue
            t1, t2 = float((q1 - p1) @ d) / length2, float((q2 - p1) @ d) / length2
            lo, hi = max(0.0, min(t1, t2)), min(1.0, max(t1, t2))
            if (hi - lo) * scale > 1e-6:
                start, end = p1 + lo * d, p1 + hi * d
                out.append([[float(start[0]), float(start[1])], [float(end[0]), float(end[1])]])
    return sorted(out)


class V2World:
    """What crossings.py asks of the legacy continent world, for the continent-v2 territories.

    ids are the catalog's order; a territory's centre is its translation (x, z), so crossings.tile_for and
    global_tile give frames.py's tile rule; owner_at reads the stubs' ownership polygons; height_at the served grids.
    """

    def __init__(self, frame_table, polygons, grids, unit_mm, datum_mm):
        self.ids = list(frame_table)
        self.frames = dict(frame_table)
        self.polygons = {region: polygons[region] for region in self.ids}
        self.grids = {region: np.asarray(grids[region]) for region in self.ids}
        self.unit_mm, self.datum_mm = int(unit_mm), int(datum_mm)
        self.regions = {region: {"center": np.array([f.translation[0], f.translation[2]], float)}
                        for region, f in self.frames.items()}
        self.centers = [self.regions[region]["center"] for region in self.ids]
        self.connections = []
        for region, f in self.frames.items():
            if self.grids[region].shape != (f.cells[1], f.cells[0]):
                raise CrossingsError(f"{region}: served grid {self.grids[region].shape} differs from the frame "
                                     f"{f.cells}")

    def address(self, region):
        f = self.frames[region]
        return list(f.origin), list(f.cells)

    def storage(self, region):
        return StorageBounds(*self.frames[region].cells)

    def owner_at(self, gx, gz):
        gx, gz = np.asarray(gx, float), np.asarray(gz, float)
        out = np.full(np.broadcast(gx, gz).shape, -1, np.int64)
        for index, region in enumerate(self.ids):
            inside = X.point_in_polygon(gx, gz, self.polygons[region])
            out = np.where(inside & (out < 0), index, out)
        return out

    def adjacent_edges(self):
        edges = {}
        for ia, ib in itertools.combinations(range(len(self.ids)), 2):
            segments = shared_segments(self.polygons[self.ids[ia]], self.polygons[self.ids[ib]])
            if segments:
                edges[(ia, ib)] = segments
        return edges

    def metres(self, code):
        return (int(code) * self.unit_mm + self.datum_mm) / 1000.0

    def height_at(self, gx, gz):
        """The served height under a continent point: the owner's grid first, then the others'; where the point is
        blocked, the nearest open tile within NEAREST_OPEN tiles (nearest first, then north-west first); else 0."""
        owner = int(self.owner_at(gx, gz))
        order = ([self.ids[owner]] if owner >= 0 else []) + [r for r in self.ids if owner < 0 or r != self.ids[owner]]
        located = []
        for region in order:
            f = self.frames[region]
            lx, lz = f.to_local(float(gx), float(gz))
            tx, ty = math.floor(lx + f.origin[0]), math.floor(f.origin[1] - lz)
            if f.contains(tx, ty):
                code = self.grids[region][ty, tx]
                if code:
                    return self.metres(code)
                located.append((region, tx, ty))
        for region, tx, ty in located:
            grid = self.grids[region]
            rows, cols = grid.shape
            y0, y1 = max(0, ty - NEAREST_OPEN), min(rows, ty + NEAREST_OPEN + 1)
            x0, x1 = max(0, tx - NEAREST_OPEN), min(cols, tx + NEAREST_OPEN + 1)
            ys, xs = np.nonzero(grid[y0:y1, x0:x1])
            if len(ys):
                distance = (ys + y0 - ty) ** 2 + (xs + x0 - tx) ** 2
                best = np.lexsort((xs, ys, distance))[0]
                return self.metres(grid[ys[best] + y0, xs[best] + x0])
        return 0.0


# --- links -------------------------------------------------------------------------------------------------------------

def _crossing(polyline, segment):
    """The first point where a polyline crosses a segment (both continent x, z), or None."""
    (ax, az), (bx, bz) = segment
    for (px, pz), (qx, qz) in zip(polyline, polyline[1:]):
        dx, dz, ex, ez = qx - px, qz - pz, bx - ax, bz - az
        det = dx * ez - dz * ex
        if abs(det) < EPSILON:
            continue
        t = ((ax - px) * ez - (az - pz) * ex) / det
        u = ((ax - px) * dz - (az - pz) * dx) / det
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return [px + t * dx, pz + t * dz]
    return None


def road_links(world, plan):
    """The plan's seam pairs that an approved route crosses, as legacy walk links (prepare_contracts reads them).

    The anchor is where the lowest-numbered crossing route meets the border; the normal is the border's, from the
    first territory (catalog order) to the second; the edge segments are the whole shared border."""
    pairs = {tuple(pair) for pair in X.plan_links(plan)}
    edges = world.adjacent_edges()
    touching = {tuple(sorted((world.ids[ia], world.ids[ib]))) for ia, ib in edges}
    if touching != pairs:
        raise CrossingsError(f"the plan's seams join {sorted(pairs)}, but the ownership polygons touch along "
                             f"{sorted(touching)}")
    routes = sorted((r for r in plan.get("approvedRoutes", []) if r.get("type") in ROUTE_TYPES),
                    key=lambda r: (int("".join(ch for ch in r["id"] if ch.isdigit()) or 0), r["id"]))
    links = []
    for (ia, ib), segments in sorted(edges.items()):
        ra, rb = world.ids[ia], world.ids[ib]
        found = None
        for route in routes:
            territories = {entry.get("territory") for entry in route.get("byTerritory", [])}
            if not {ra, rb} <= territories:
                continue
            for segment in segments:
                point = _crossing(route["approvedPolyline"], segment)
                if point is not None:
                    found = (route["id"], point, segment)
                    break
            if found:
                break
        if found is None:
            continue
        route_id, anchor, ((sx, sz), (ex, ez)) = found
        normal = np.array([ez - sz, -(ex - sx)], float)
        normal /= np.linalg.norm(normal)
        if normal @ (world.centers[ib] - world.centers[ia]) < 0:
            normal = -normal
        links.append({"id": f"{ra}--{rb}", "type": "walk", "road": True, "regions": [ra, rb],
                      "anchor": [float(anchor[0]), float(anchor[1])], "normal": [float(v) + 0.0 for v in normal],
                      "edgeSegments": segments, "route": route_id})
    return links


# --- inputs ------------------------------------------------------------------------------------------------------------

def package_inputs(checkout, maps_root, codec, *, log=say):
    """Each catalog map's frame, ownership polygon, served grid (decoded by the server's codec) and arrival, from its
    published package (<maps root>/continent-v2/<region>/client/world.json), refused unless the package agrees with
    the frame and the stub."""
    checkout = Path(checkout)
    maps_root = Path(maps_root)
    table = {}
    for region in frames.regions(checkout):
        frame = frames.load(region, checkout)
        stub = json.loads((checkout / "eloria-assets/maps/continent-v2" / region / "world.json")
                          .read_text(encoding="utf-8"))
        package = maps_root / PACKAGES / region / "client"
        world_path = package / "world.json"
        if not world_path.is_file():
            raise CrossingsError(f"{region}: no published package at {package}")
        manifest = json.loads(world_path.read_text(encoding="utf-8"))
        rings = O.rings(stub.get("continentGeography", {}))
        polygon = rings[0] if len(rings) == 1 else rings
        if O.rings(manifest.get("continentGeography", {})) != rings:
            raise CrossingsError(f"{region}: the package's ownership polygon differs from the stub's")
        transform = manifest.get("coordinateTransform", {})
        if (list(transform.get("serverOrigin", [])) != list(frame.origin)
                or list(transform.get("serverCells", [])) != list(frame.cells)):
            raise CrossingsError(f"{region}: the package's coordinateTransform differs from the frame")
        spec = (manifest.get("collision") or {}).get("servedGrid")
        if not spec or not spec.get("binary"):
            raise CrossingsError(f"{region}: {world_path} declares no served grid: export_collision.py and "
                                 "publish_client.py --collision first")
        blob = (package / spec["binary"]).read_bytes()
        digest = sha256_bytes(blob)
        if digest != spec.get("sha256"):
            raise CrossingsError(f"{region}: {spec['binary']} has SHA-256 {digest}, world.json says "
                                 f"{spec.get('sha256')}")
        grid = codec.served_grid.decode_file(blob)
        if (grid.width, grid.height) != tuple(frame.cells):
            raise CrossingsError(f"{region}: the served grid is {grid.width}x{grid.height}, the frame {frame.cells}")
        rule = (grid.climb_mm, grid.unit_mm, grid.datum_mm)
        server_rule = (codec.served_grid.CLIMB_MM, codec.served_grid.UNIT_MM, codec.served_grid.DATUM_MM)
        if rule != server_rule:
            raise CrossingsError(f"{region}: the served grid states climb/unit/datum {rule}, the server {server_rule}")
        codes = np.frombuffer(grid.codes, dtype=np.uint16).reshape(grid.height, grid.width).copy()
        if int(codes.max()) > 32767:
            raise CrossingsError(f"{region}: a served code over 32,767 would wrap in crossings.step_bits (int16)")
        defaults = [s for s in manifest.get("spawnPoints", []) if s.get("default")]
        if len(defaults) != 1:
            raise CrossingsError(f"{region}: the package needs exactly one default spawn point")
        spawn = defaults[0]
        arrival = list(frame.tile(spawn["position"][0], spawn["position"][2]))
        if list(spawn.get("serverTile", [])) != arrival:
            raise CrossingsError(f"{region}: the spawn point's serverTile {spawn.get('serverTile')} is not its "
                                 f"position's tile {arrival}")
        if not codes[arrival[1], arrival[0]]:
            raise CrossingsError(f"{region}: the arrival {arrival} is blocked on the served grid")
        table[region] = {"frame": frame, "polygon": polygon, "codes": codes,
                         "arrival": arrival, "servedGridSha256": digest, "manifest": manifest,
                         "package": str(package)}
        log(f"{region}: served grid {grid.width}x{grid.height}, {int((codes != 0).sum())} open tiles, "
            f"arrival {arrival}")
    check_one_run(table)
    return table


def check_one_run(table):
    """The packages come from one export_collision.py run: each collision block's groupExport names every package of
    the catalog with the snapshot and served grid that package carries. A map's one-tile collar is its neighbour's
    export, so a package re-exported beside a re-baked neighbour that was not republished (or the other way round)
    keeps the neighbour's old ground there; refused."""
    expected = {region: {"snapshotSha256": (entry["manifest"].get("collision") or {}).get("sourceSnapshotSha256"),
                         "servedGridSha256": entry["servedGridSha256"]} for region, entry in table.items()}
    for region, entry in table.items():
        group = ((entry["manifest"].get("collision") or {}).get("groupExport") or {}).get("maps")
        if group != expected:
            differ = sorted(set(group or {}) ^ set(expected)
                            | {r for r in set(group or {}) & set(expected) if group[r] != expected[r]})
            raise CrossingsError(f"{region}: its collision block's groupExport differs from the packages for "
                                 f"{differ or 'every map'} (exported in another run): re-run export_collision.py over "
                                 "the whole group and republish every map")
    return expected


def specs_of(table):
    """The publisher's per-territory spec (publish_diagonal_continent.destination_tile / world_point read these)."""
    out = {}
    for region, entry in table.items():
        f = entry["frame"]
        out[region] = {"serverOrigin": list(f.origin), "serverCells": list(f.cells),
                       "translation": [f.translation[0], f.translation[1], f.translation[2]],
                       **StorageBounds(*f.cells).metadata()}
    return out


# --- the survey --------------------------------------------------------------------------------------------------------

def survey(world, served, step, hubs, climb, links):
    """The legacy stages, in export_contracts' order: prepare_contracts, widen_seams on the road links,
    settle_crossings (opens the roadless borders and prunes every lane no walker can use)."""
    world.connections = links
    publication = {"connections": C.prepare_contracts(world), "visualConnections": world.visual_connections,
                   "revision": REVISION}
    seams = C.widen_seams(world, publication["connections"], served, step)
    settled = C.settle_crossings(world, publication, served, step, hubs, limit=climb)
    return publication, seams + settled["roadless"], settled


def lane_point(world, region, tile):
    return C.global_tile(world, region, tile)


def mole_report(world, publication, plan):
    """Lanes on each mole, each way: a lane counts where its tile's centre lies inside the mole's rectangle."""
    report = []
    for mole in plan.get("seams", {}).get("moles", []):
        (x0, x1), (z0, z1) = mole["x"], mole["z"]
        pair = set(mole["between"])
        counts = {}
        for connection in publication["connections"]:
            if {end["region"] for end in connection["ends"]} != pair:
                continue
            for end in connection["ends"]:
                n = 0
                for lane in end["lanes"]:
                    gx, gz = lane_point(world, end["region"], lane["tile"])
                    n += int(x0 <= gx <= x1 and z0 <= gz <= z1)
                counts[end["region"]] = n
        report.append({"id": mole["id"], "between": mole["between"], "lanesEachWay": counts,
                       "pass": bool(counts) and all(n >= MOLE_MINIMUM_LANES for n in counts.values())})
    return report


def lane_runs(world, end):
    """An end's lanes as runs of continent metres along the border (for the report)."""
    points = sorted((lane_point(world, end["region"], lane["tile"]).tolist() for lane in end["lanes"]),
                    key=lambda p: (p[0], p[1]))
    runs = []
    for gx, gz in points:
        if runs and runs[-1]["x"] == gx and gz - runs[-1]["z"][1] == 1.0:
            runs[-1]["z"][1] = gz
        else:
            runs.append({"x": gx, "z": [gz, gz]})
    merged = []
    for run in runs:
        if run["z"][0] == run["z"][1]:
            # a horizontal border: runs along x at one z
            if merged and merged[-1].get("z1") == run["z"][0] and run["x"] - merged[-1]["x"][1] == 1.0:
                merged[-1]["x"][1] = run["x"]
                continue
            merged.append({"x": [run["x"], run["x"]], "z1": run["z"][0]})
        else:
            merged.append({"x": [run["x"], run["x"]], "z": run["z"]})
    out = []
    for run in merged:
        if "z1" in run:
            out.append({"continentX": [run["x"][0] - .5, run["x"][1] + .5],
                        "continentZ": [run["z1"] - .5, run["z1"] + .5],
                        "tiles": int(run["x"][1] - run["x"][0]) + 1})
        else:
            out.append({"continentX": [run["x"][0] - .5, run["x"][1] + .5],
                        "continentZ": [run["z"][0] - .5, run["z"][1] + .5],
                        "tiles": int(run["z"][1] - run["z"][0]) + 1})
    return out


def _step_back_analysis(portals, codes, step, reach=STEP_BACK_STEPS):
    """Reciprocity, walked: a walker any lane lands on t at (ax, ay) can step onto the departure of some t->s lane
    within `reach` legal steps (the server's rule, `step(heights, y, x, dy, dx)`), never over another lane's tile on
    the way (stepping on one fires it), so every crossing can be crossed back where it was crossed. More than one
    step is allowed because the corner rule makes a diagonal crossing at a height edge one-way: the walker it lands
    steps once along the border and crosses back straight. Refused (CrossingsError) when a lane strands its walker.
    Returns {steps needed: lanes}."""
    departures, every = {}, {}
    for source, x, y, destination, *_ in portals:
        departures.setdefault((source, destination), set()).add((int(x), int(y)))
        every.setdefault(source, set()).add((int(x), int(y)))
    needed, stranded = Counter(), []
    for source, x, y, destination, ax, ay in portals:
        back = departures.get((destination, source), set())
        fires = every.get(destination, set())
        grid = codes[destination]
        seen, frontier, found = {(ax, ay)}, [(ax, ay)], None
        for depth in range(1, reach + 1):
            following = []
            for cx, cy in frontier:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nxt = (cx + dx, cy + dy)
                        if (dx or dy) and nxt not in seen and step(grid, cy, cx, dy, dx):
                            seen.add(nxt)
                            if nxt in back:
                                found = depth
                            elif nxt not in fires:
                                following.append(nxt)
            if found:
                break
            frontier = following
        if found:
            needed[found] += 1
        else:
            stranded.append([source, x, y, destination, ax, ay])
    return dict(sorted(needed.items())), stranded


def check_step_back(portals, codes, step, reach=STEP_BACK_STEPS):
    """Refuse any emitted lane without a legal return within the required step limit."""
    needed, stranded = _step_back_analysis(portals, codes, step, reach)
    if stranded:
        raise CrossingsError(f"{len(stranded)} lanes land a walker who cannot step back onto a reverse lane within "
                             f"{reach} steps, e.g. {stranded[:4]}")
    return needed


def prune_step_back(world, publication, specs, codes, step, served, hubs, climb):
    """Withdraw unusable return lanes, then repeat reach pruning until all remaining lanes are reciprocal.

    The initial legacy survey checks reach and a non-triggering first step, but those do not guarantee a
    return in three steps on a subdivided border. This filters candidate lanes without changing ground;
    an expected connection losing either end remains a hard error.
    """
    import publish_diagonal_continent as PDC
    withdrawn = 0
    while True:
        _text, entries = PDC.connection_rows(publication['connections'], specs)
        _needed, stranded = _step_back_analysis(entries, codes, step)
        if not stranded:
            return withdrawn
        gone = {(source, int(x), int(y)) for source, x, y, *_ in stranded}
        for connection in publication['connections']:
            for end in connection['ends']:
                before = len(end['lanes'])
                end['lanes'] = [lane for lane in end['lanes']
                                if (end['region'], *map(int, lane['tile'])) not in gone]
                withdrawn += before - len(end['lanes'])
                C.reseat(world, end)
        withdrawn += C.prune_lanes(world, publication['connections'], served, hubs, climb)
        empty = [c['id'] for c in publication['connections'] if not all(e['lanes'] for e in c['ends'])]
        if empty:
            raise CrossingsError('no reciprocal reachable lane remains for ' + ', '.join(empty))


def straight_pairs(end):
    straight = sum(1 for lane in end["lanes"]
                   if abs(lane["tile"][0] - lane["arrival"][0]) + abs(lane["tile"][1] - lane["arrival"][1]) == 1)
    return {"lanes": len(end["lanes"]), "pairedStraightAcross": straight}


def build(table, plan, codec, *, plan_sha=None, log=say):
    """The crossings document for the packages in `table` (package_inputs)."""
    unit, datum, climb = codec.served_grid.UNIT_MM, codec.served_grid.DATUM_MM, int(codec.climb_units)
    frame_table = {region: entry["frame"] for region, entry in table.items()}
    world = V2World(frame_table, {r: e["polygon"] for r, e in table.items()},
                    {r: e["codes"] for r, e in table.items()}, unit, datum)
    links = road_links(world, plan)
    served = {region: C.own_ground(world, region, entry["codes"]) for region, entry in table.items()}
    sources = codec.sources

    def step(heights, y, x, dy, dx):
        return sources.walk_step_ok(heights, y, x, dy, dx, climb)

    hubs = {region: entry["arrival"] for region, entry in table.items()}
    started = time.time()
    publication, seams, settled = survey(world, served, step, hubs, climb, links)
    log(f"lanes surveyed and pruned in {time.time() - started:.1f} s: opened {settled['opened'] or 'none'}, "
        f"{settled['withdrawnLanes']} withdrawn")
    specs = specs_of(table)
    reciprocal_withdrawn = prune_step_back(world, publication, specs,
                                         {region: entry['codes'] for region, entry in table.items()},
                                         step, served, hubs, climb)
    log(f'reciprocal return pruning withdrew {reciprocal_withdrawn} additional candidate lanes')
    for connection in publication["connections"]:
        for end in connection["ends"]:
            if not end["lanes"]:
                raise CrossingsError(f"{connection['id']}: {end['region']} has no lane left")
    moles = mole_report(world, publication, plan)
    short = [m for m in moles if not m["pass"]]
    if short:
        raise CrossingsError("a mole keeps fewer than %d lanes each way: %s" % (
            MOLE_MINIMUM_LANES, "; ".join(f"{m['id']} {m['lanesEachWay']}" for m in short)))
    for connection in publication["connections"]:
        ends = connection["ends"]
        for end, other in ((ends[0], ends[1]), (ends[1], ends[0])):
            # crossing_lanes takes every lane from the neighbour's first ring, so only a surveyed gate's fallback
            # lane could stand elsewhere; such a lane would land its walker off the neighbour's own ground.
            for lane in end["lanes"]:
                point = lane_point(world, end["region"], lane["tile"])
                if int(world.owner_at(*point)) != world.ids.index(other["region"]):
                    raise CrossingsError(f"{connection['id']}: {end['region']} lane {lane['tile']} does not stand on "
                                         f"{other['region']}'s ground")
    import publish_diagonal_continent as PDC
    # connection_rows refuses a row whose arrival is itself a departure (a walker would bounce straight back).
    _text, entries = PDC.connection_rows(publication["connections"], specs)
    step_back = check_step_back(entries, {region: entry["codes"] for region, entry in table.items()}, step)
    worlds = {region: entry["manifest"] for region, entry in table.items()}
    _graph, streaming = PDC.connection_manifests(publication, worlds, specs)
    report = {"links": [], "moles": moles, "withdrawnLanes": settled["withdrawnLanes"] + reciprocal_withdrawn,
              "reciprocalWithdrawnLanes": reciprocal_withdrawn,
              "openedRoadless": settled["opened"], "seams": seams,
              "stepBack": {"lanesBySteps": {str(k): v for k, v in step_back.items()}, "limit": STEP_BACK_STEPS}}
    for connection in publication["connections"]:
        report["links"].append({
            "id": connection["id"], "road": connection.get("road", True),
            "ends": [{"region": end["region"], "portal": end["portal"], "tile": end["tile"],
                      **straight_pairs(end), "runs": lane_runs(world, end)} for end in connection["ends"]]})
    withdrawn_links = [link["id"] for link in getattr(world, "open_border_links", [])
                       if link["id"] not in settled["opened"]]
    report["withdrawnRoadless"] = withdrawn_links
    doc = {
        "schema": SCHEMA, "tool": TOOL,
        "rule": "ground walkable on both sides of a border is a way across (the owner's rule, 2026-09-18): "
                "crossings.crossing_lanes, widen_seams, settle_crossings and prune_lanes, imported; the server's "
                "collision_sources.walk_step_ok at the served grid's climb",
        "climbCodes": climb,
        "codec": {"unitMillimetres": unit, "datumMillimetres": datum, "climbMillimetres": codec.served_grid.CLIMB_MM},
        "inputs": {
            "plan": {"path": X.PLAN, "sha256": plan_sha},
            "maps": {region: {"frame": {"origin": list(e["frame"].origin), "cells": list(e["frame"].cells),
                                        "translation": list(e["frame"].translation)},
                              "polygon": e["polygon"], "arrival": e["arrival"],
                              "servedGridSha256": e["servedGridSha256"]}
                     for region, e in table.items()}},
        "links": [{key: link[key] for key in ("id", "type", "road", "regions", "anchor", "normal", "edgeSegments",
                                              "route") if key in link}
                  for link in links + list(getattr(world, "open_border_links", []))],
        "connections": [_plain(connection) for connection in publication["connections"]],
        "portals": [list(entry) for entry in entries],
        "exteriorConnections": _plain(streaming["connections"]),
        "exteriorSettings": {k: v for k, v in streaming.items() if k != "connections"},
        "report": _plain(report),
    }
    return doc


def _plain(value):
    """numpy scalars and arrays to JSON values."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


# --- reading it back ---------------------------------------------------------------------------------------------------

def verify(doc, table, plan_sha=None):
    """Refuse a crossings document made from other packages, frames, polygons, arrivals or plan."""
    if doc.get("schema") != SCHEMA:
        raise CrossingsError(f"crossings.json schema {doc.get('schema')!r}, not {SCHEMA}")
    recorded = doc.get("inputs", {}).get("maps", {})
    if set(recorded) != set(table):
        raise CrossingsError(f"crossings.json covers {sorted(recorded)}, the catalog {sorted(table)}")
    for region, entry in table.items():
        mine = recorded[region]
        expected = {"frame": {"origin": list(entry["frame"].origin), "cells": list(entry["frame"].cells),
                              "translation": list(entry["frame"].translation)},
                    "polygon": entry["polygon"], "arrival": list(entry["arrival"]),
                    "servedGridSha256": entry["servedGridSha256"]}
        for key, value in expected.items():
            if mine.get(key) != value:
                raise CrossingsError(f"crossings.json is stale for {region}: its {key} differs from the package's; "
                                     "re-run crossings_v2.py")
    if plan_sha is not None and doc.get("inputs", {}).get("plan", {}).get("sha256") != plan_sha:
        raise CrossingsError("crossings.json was made from another continent-v2-plan.json; re-run crossings_v2.py")
    return doc


def load(path, table, plan_sha=None):
    return verify(json.loads(Path(path).read_text(encoding="utf-8")), table, plan_sha)


# --- the command -------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", required=True, type=Path, help="the server checkout whose codec and step rule are used")
    ap.add_argument("--maps-root", type=Path, default=None,
                    help="the folder holding continent-v2/<region>/client/ (default: eloria-assets/maps here)")
    ap.add_argument("--out", type=Path, default=None, help=f"where to write crossings.json (default {DEFAULT_OUT})")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    ap.add_argument("--check", action="store_true", help="rebuild and compare with --out; write nothing")
    a = ap.parse_args(argv)
    started = time.time()
    checkout = a.checkout.resolve()
    out = a.out or checkout / DEFAULT_OUT
    try:
        codec = X.server_codec(a.server)
        importlib.import_module("publish_diagonal_continent")
        plan_path = checkout / X.PLAN
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        table = package_inputs(checkout, (a.maps_root or checkout / MAPS_ROOT).resolve(), codec)
        doc = build(table, plan, codec, plan_sha=sha256_file(plan_path))
    except (CrossingsError, X.ExportError, frames.FrameError, ValueError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    text = json_text(doc)
    summary = {"links": [{"id": link["id"], "ends": {end["region"]: end["lanes"] for end in link["ends"]}}
                         for link in doc["report"]["links"]],
               "moles": doc["report"]["moles"], "withdrawnLanes": doc["report"]["withdrawnLanes"],
               "withdrawnRoadless": doc["report"]["withdrawnRoadless"], "portals": len(doc["portals"]),
               "seconds": round(time.time() - started, 1)}
    if a.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else None
        summary["check"] = "clean" if current == text else "differs"
        print(json.dumps(summary, indent=1))
        return 0 if current == text else 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    summary["written"] = str(out)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
