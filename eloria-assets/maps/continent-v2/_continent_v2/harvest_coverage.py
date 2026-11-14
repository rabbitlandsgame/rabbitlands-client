"""harvest_coverage.py: the harvest coverage pass - EL-style harvest sites generated against the served grids.

The 2026-11-14 distribution audit (rabbitlands-client .local work-output/harvest-distribution-2026-11-14/FINDINGS.md)
measured Eternal Lands' own map files against the continent with a set of grid stencils. Its first finding: on every
Landfall map most of the walkable ground is far from any harvestable (90th percentile 29-168 s of running, against
EL's 6.7 s), because the nodes sit in a few single-kind lattices. This tool places the missing sites.

What it does, per map, deterministically (content/harvest-coverage-rules.json holds every number, the seed included):

1. Reads the committed scene (godot-client/world_authoring/regions/<map>/<map>.tscn): its gameplay and runtime
   markers, its Roads/* curves (the D11 road bands) and its AuthoredAssets placements (the scenery features), and the
   map's served grid from its client package, eroded and closed as publish_server.py judges rows (storage bodies
   eroded, NPC posts closed), with reach over every map from every arrival across the land crossings
   (publish_server.union_reach).
2. Finds the dead ground: reachable tiles farther than coverage.cutSeconds of running from any harvest node.
3. Throws sites at it in a random order weighted by coverage gain and by the scenery around them (a site near trees,
   shrubs, meadow plants, rock, shore wrack, reeds or a farm takes that feature's kinds; a placement whose kit is a
   harvest resource - an olive tree, a lavender clump, kelp wrack - is promoted: the node binds to it, as
   harvest_presentation.py's PROMOTED SCENERY). Each site is a clump of one to six nodes in one to three kinds,
   sizes drawn like EL's, at irregular spacing, never on a grid.
4. Checks every node with publish_server.py's own rules: the reach-side approach rule (Checker.node), D11 (no node in a
   road band, harvest_presentation.road_offenders), ownership, unique object ids apart from every interior's; then
   closes all the new nodes' tiles and recomputes the union reach, dropping any node whose body would cut off ground,
   another node's approach or a protected point. Existing nodes must still pass.
5. Measures the result with the audit's stencils (nearest-harvestable times, empty ground, kinds in reach, window
   occupancy, patch mixing, grid regularity, spacing) and compares them with the rules' targets.

Outputs: content/harvest-coverage.json (the plan: every site and node, the inputs' digests, before/after metrics).
--check regenerates and compares it. --apply-scenes appends the plan's markers to the scenes (Gameplay/Harvestables
Marker3D nodes, extras {authority, objectId, resource, cluster, grouping, groupingName, yaw, zone, pass,
bindPlacement?}) and raises each map's region-authoring-spec gameplay.authoredMarkerCount; it is idempotent (blocks
carrying this pass are replaced). Applied scenes change collision (each node closes its tile), so they must go
through the full republication (README "Republishing every territory"); nothing here writes packages or server rows.

  python harvest_coverage.py --server C:/rabbitlands/rabbitlands-server --plan [--maps a,b] [--report DIR]
  python harvest_coverage.py --server ... --check
  python harvest_coverage.py --server ... --apply-scenes        (only with the owner's approval to republish)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import frames  # noqa: E402
import ownership  # noqa: E402
import export_collision as X  # noqa: E402
import harvest_presentation as HP  # noqa: E402
import publish_server as P  # noqa: E402

ROOT = frames.DEFAULT_CHECKOUT
V2 = "eloria-assets/maps/continent-v2"
RULES = HERE / "content/harvest-coverage-rules.json"
PLAN = HERE / "content/harvest-coverage.json"
SCHEMA = "rabbitlands-harvest-coverage-v1"
TOOL = V2 + "/_continent_v2/harvest_coverage.py"
EXTERIOR = ("landfall", "boarsend", "brambleshaw", "coilmere", "greenlight", "hearthcroft", "hornmere", "pinebrow",
            "ravenhead", "reedfall", "ringholm", "saltsound", "stagheath", "suncoil", "twinbrook", "warrenmead",
            "whitepeak")
HARVEST_PARENT = "Gameplay/Harvestables"
PH_TILES = 1.8          # one player height in tiles (1 m tiles, 1.8 m player)


class CoverageError(ValueError):
    """The inputs disagree or a generated node fails a rule this pass will not relax."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(Path(path).read_bytes())


# --- scenes ----------------------------------------------------------------------------------------------------------

HEADER = re.compile(r'^\[(\w+)([^\]]*)\]', re.M)
ATTR = re.compile(r'(\w+)="([^"]*)"')
FLOATS = re.compile(r'-?\d+(?:\.\d+)?(?:e-?\d+)?')


def blocks(text: str):
    """(kind, attributes, body, start, end) for every [section] of a .tscn."""
    heads = list(HEADER.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        yield m.group(1), dict(ATTR.findall(m.group(2))), text[m.end():end], m.start(), end


def _field(body: str, name: str):
    m = re.search(rf'^{name} = (.*)$', body, re.M)
    return m.group(1).strip() if m else None


def _transform(body: str):
    value = _field(body, "transform")
    inner = re.match(r"Transform3D\((.*)\)", value or "")
    if not inner:
        return None
    nums = [float(v) for v in FLOATS.findall(inner.group(1))]
    if len(nums) != 12:
        return None
    basis = np.array(nums[:9]).reshape(3, 3)          # rows are the basis columns x, y, z
    return basis, np.array(nums[9:])


def _extras(body: str):
    m = re.search(r'^extras = (\{.*?^\}|\{[^\n]*\})', body, re.M | re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def kit_of(catalog_id: str) -> str:
    name = catalog_id.split(":", 1)[-1]
    name = re.sub(r"^kit-", "", name)
    name = re.sub(r"-[0-9a-f]{12}$", "", name)
    return re.sub(r"-\d+$", "", name)


def read_scene(region: str, checkout: Path, pass_name: str):
    """The scene's markers, road paths (bake shape: territory-local points with widths), scenery placements and the
    blocks a previous --apply-scenes of this pass wrote (returned separately, so the base scene is recoverable)."""
    path = checkout / f"godot-client/world_authoring/regions/{region}/{region}.tscn"
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    curves, markers, roads, placements, generated = {}, [], [], [], []
    for kind, attrs, body, start, end in blocks(text):
        if kind == "sub_resource" and attrs.get("type") == "Curve3D":
            m = re.search(r'"points": PackedVector3Array\(([^)]*)\)', body)
            if m:
                v = np.array([float(x) for x in FLOATS.findall(m.group(1))]).reshape(-1, 3)
                curves[attrs["id"]] = v[2::3]       # (in, out, position) per point
            continue
        if kind != "node":
            continue
        parent = attrs.get("parent", "")
        if parent.startswith("Gameplay") or parent.startswith("RuntimePoints"):
            extras = _extras(body)
            tr = _transform(body)
            if extras is not None and tr is not None:
                marker = {"name": attrs.get("name"), "parent": parent, "extras": extras,
                          "position": tr[1].tolist(), "kind": (_field(body, "kind") or "").strip('"')}
                if parent == HARVEST_PARENT and extras.get("pass") == pass_name:
                    generated.append((start, end, marker))
                else:
                    markers.append(marker)
        elif parent == "Roads" and attrs.get("type") == "Path3D":
            curve = re.search(r'curve = SubResource\("([^"]+)"\)', body)
            tr = _transform(body)
            widths = _field(body, "point_widths")
            default = float(_field(body, "default_width") or 8.0)
            pid = (_field(body, "path_id") or attrs.get("name", "road")).strip('"')
            roads.append({"curve": curve.group(1) if curve else None, "transform": tr, "default": default,
                          "widths": [float(w) for w in FLOATS.findall(widths)] if widths else [], "id": pid})
        elif parent == "AuthoredAssets":
            asset = _field(body, "asset_id")
            catalog = _field(body, "catalog_asset_id")
            tr = _transform(body)
            if asset and catalog and tr is not None:
                placements.append({"assetId": asset.strip('"'), "nodeName": (_field(body, "node_name") or "").strip('"'),
                                   "kit": kit_of(catalog.strip('"')), "role": (_field(body, "collision_role") or "").strip('"'),
                                   "position": tr[1].tolist()})
    paths = []
    for road in roads:
        points = curves.get(road["curve"])
        if points is None or road["transform"] is None:
            continue
        basis, origin = road["transform"]
        world = points @ basis + origin
        widths = road["widths"] if len(road["widths"]) == len(world) else [road["default"]] * len(world)
        paths.append({"kind": "road", "id": road["id"],
                      "points": [{"position": p.tolist(), "width": w} for p, w in zip(world, widths)]})
    base = text
    for start, end, _ in sorted(generated, reverse=True):
        base = base[:start] + base[end:]
    # A generated block is appended as "\n[node ...]...\n": removing the blocks leaves the base's own ending.
    base = base.rstrip("\r\n") + text[len(text.rstrip("\r\n")):] if generated else base
    return {"path": path, "raw": raw, "text": text, "base": base, "markers": markers, "paths": paths,
            "placements": placements, "generated": [g[2] for g in generated]}


# --- server inputs ---------------------------------------------------------------------------------------------------

def server_inputs(server: Path):
    """Loaders and tables from the server checkout, read as publish_server.py and the Lakehead amendment read them."""
    if str(server) not in sys.path:
        sys.path.insert(0, str(server))
    from eloria.served_grid import decode_file
    from eloria.harvesting import load_harvesting
    from eloria.interactives import load_interactives
    from eloria.npcs import load_npcs
    profile = server / "config/eloria"
    manifest = read_json(profile / "client_content_manifest.json")["continentV2"]
    resources, nodes = load_harvesting(profile / "harvesting.txt")
    overlay_resources, overlay_nodes = load_harvesting(profile / "continent-v2/harvesting.txt", overlay=True)
    resources = {**resources, **overlay_resources}
    nodes = {**nodes, **overlay_nodes}
    interactives = load_interactives(profile / "continent-v2/interactives.txt", overlay=False)
    people = []
    for name in ("npcs.txt", "home_npcs.txt", "service_npcs.txt"):
        if (profile / "continent-v2" / name).exists():
            people += list(load_npcs(profile / "continent-v2" / name, overlay=False))
    lanes = []
    names = set(manifest["maps"])
    for line in (profile / "continent-v2/maps.txt").read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 7 and parts[0] == "portal" and parts[1] in names and parts[4] in names:
            lanes.append((parts[1], int(parts[2]), int(parts[3]), parts[4], int(parts[5]), int(parts[6])))
    return {"decode": decode_file, "manifest": manifest, "resources": resources, "nodes": nodes,
            "interactives": interactives, "people": people, "lanes": lanes,
            "harvestSha256": sha((profile / "continent-v2/harvesting.txt").read_bytes())}


# --- per-map ground --------------------------------------------------------------------------------------------------

class Ground:
    """One map's frame, served codes (storage eroded; `codes` with NPC posts closed, `ground` with them open), the
    existing nodes and the protected tiles."""

    def __init__(self, region, checkout, srv, scene):
        self.region = region
        self.frame = frames.load(region, checkout)
        package = checkout / f"{V2}/{region}/client"
        world = read_json(package / "world.json")
        grid_bytes = (package / "served-grid.escg.gz").read_bytes()
        expected = srv["manifest"]["maps"][region]["servedGridSha256"]
        if sha(grid_bytes) != expected:
            raise CoverageError(f"{region}: the client package's served grid is not the server's ({expected[:12]})")
        self.grid_sha = sha(grid_bytes)
        self.grid = srv["decode"](grid_bytes)
        storage = {(i.x, i.y) for i in srv["interactives"].values() if i.map_id == region and i.role == "storage"}
        codes, _ = P.eroded_codes(region, {"grid": self.grid}, storage)
        self.ground = codes.copy()
        for person in srv["people"]:
            if person.map_id == region:
                codes[person.y, person.x] = 0
        self.codes = codes
        self.climb = self.grid.climb_units
        self.polygon = world["continentGeography"]          # ownership.rings reads one or several rings from it
        self.arrival = tuple(srv["manifest"]["maps"][region]["arrival"])
        self.heights = (self.grid.datum_mm + codes.astype(np.int64) * self.grid.unit_mm) / 1000.0
        self.nodes = [n for n in srv["nodes"].values() if n.map_id == region]
        self.scene = scene
        h, w = codes.shape
        self.shape = (h, w)
        # protected tiles: every marker that is not a harvest node, every NPC post and interactive, the arrival
        self.protected = []
        for m in scene["markers"]:
            if m["parent"] == HARVEST_PARENT:
                continue
            try:
                self.protected.append(self.frame.tile(m["position"][0], m["position"][2]))
            except frames.FrameError:
                pass
        self.protected += [(p.x, p.y) for p in srv["people"] if p.map_id == region]
        self.protected += [(i.x, i.y) for i in srv["interactives"].values() if i.map_id == region]
        self.protected.append(self.arrival)
        self.lane_tiles = [(x, y) for s, x, y, d, ax, ay in srv["lanes"] if s == region] + \
                          [(ax, ay) for s, x, y, d, ax, ay in srv["lanes"] if d == region]
        self.used_ids = {n.object_id for n in self.nodes} | {i.object_id for i in srv["interactives"].values()
                                                             if i.map_id == region}
        for m in scene["markers"]:
            oid = m["extras"].get("objectId")
            if isinstance(oid, int):
                self.used_ids.add(oid)
        self.used_groupings = {m["extras"].get("grouping") for m in scene["markers"] if m["parent"] == HARVEST_PARENT}
        self.bound = {m["extras"].get("bindPlacement") for m in scene["markers"] if m["parent"] == HARVEST_PARENT}

    def local(self, tx, ty):
        return self.frame.local(tx, ty)


def interior_ids(srv):
    """Object ids every interior uses; an isle object may not share one (publish_server: apart from every isle
    object)."""
    exterior = set(EXTERIOR)
    ids = {n.object_id for n in srv["nodes"].values() if n.map_id not in exterior}
    ids |= {i.object_id for i in srv["interactives"].values() if i.map_id not in exterior}
    return ids


def union_reach(grounds, srv, closed=None):
    """publish_server.union_reach over the given maps, with `closed` {region: [(x, y)]} tiles shut first."""
    codes = {}
    for region, g in grounds.items():
        c = g.codes.copy()
        for x, y in (closed or {}).get(region, ()):
            c[y, x] = 0
        codes[region] = c
    lanes = [lane for lane in srv["lanes"] if lane[0] in grounds and lane[3] in grounds]
    arrivals = {r: g.arrival for r, g in grounds.items()}
    climb = next(iter(grounds.values())).climb
    return P.union_reach(codes, arrivals, lanes, climb), codes


# --- masks -----------------------------------------------------------------------------------------------------------

def tile_centres(g):
    h, w = g.shape
    tx = np.arange(w) - g.frame.origin[0] + 0.5
    tz = g.frame.origin[1] - np.arange(h) - 0.5
    return tx, tz


def road_band(g, margin):
    """Tiles whose centre lies within a road's half-width plus `margin` metres (D11 with a margin)."""
    h, w = g.shape
    band = np.zeros((h, w), bool)
    tx, tz = tile_centres(g)
    for (ax, az), (bx, bz), ah, bh, _ in HP.road_segments(g.scene["paths"]):
        reach = max(ah, bh) + margin
        x0, x1 = min(ax, bx) - reach, max(ax, bx) + reach
        z0, z1 = min(az, bz) - reach, max(az, bz) + reach
        cols = np.nonzero((tx >= x0) & (tx <= x1))[0]
        rows = np.nonzero((tz >= z0) & (tz <= z1))[0]
        if not len(cols) or not len(rows):
            continue
        X_, Z_ = np.meshgrid(tx[cols], tz[rows])
        dx, dz = bx - ax, bz - az
        l2 = dx * dx + dz * dz
        t = np.zeros_like(X_) if l2 <= 1e-12 else np.clip(((X_ - ax) * dx + (Z_ - az) * dz) / l2, 0, 1)
        dist = np.hypot(X_ - (ax + t * dx), Z_ - (az + t * dz))
        inside = dist < (ah + t * (bh - ah)) + margin
        band[np.ix_(rows, cols)] |= inside
    return band


def chebyshev_mask(shape, tiles, radius):
    m = np.zeros(shape, bool)
    h, w = shape
    for x, y in tiles:
        m[max(0, y - radius):min(h, y + radius + 1), max(0, x - radius):min(w, x + radius + 1)] = True
    return m


def candidate_mask(g, reached, rules):
    """Open, reached tiles whose eight neighbours are open and reached (stricter than D4, so a new body never pinches
    a path), on gentle ground, off roads, inside the map's own polygon and clear of protected points."""
    pl = rules["placement"]
    open_ = (g.codes != 0) & reached
    ring = open_.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring &= np.roll(np.roll(open_, dy, 0), dx, 1)
    hi = ndimage.maximum_filter(np.where(open_, g.heights, -1e9), size=3)
    lo = ndimage.minimum_filter(np.where(open_, g.heights, 1e9), size=3)
    gentle = (hi - lo) <= pl["maxRingReliefMetres"]
    tx, tz = tile_centres(g)
    X_, Z_ = np.meshgrid(tx, tz)
    cx, cz = g.frame.to_continent(X_, Z_)
    inside = ownership.contains(cx, cz, g.polygon)
    m = pl["edgeMarginTiles"]
    edge = np.zeros(g.shape, bool)
    edge[m:-m, m:-m] = True
    blocked = road_band(g, pl["roadMarginMetres"])
    blocked |= chebyshev_mask(g.shape, g.protected, pl["protectChebyshev"])
    blocked |= chebyshev_mask(g.shape, g.lane_tiles, pl["laneProtectChebyshev"])
    blocked |= chebyshev_mask(g.shape, [(n.x, n.y) for n in g.nodes], rules["clumps"]["minSpacingToExisting"])
    allow = inside & edge & ~blocked
    settled = settled_mask(g, rules)
    # A promoted placement's tile may be closed already (a trunk, a rock): it needs only the D4 approach, at least
    # HARVEST_RING_MINIMUM of its eight neighbours open and reached.
    ring_open = np.zeros(g.shape, np.int8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                ring_open += np.roll(np.roll(open_, dy, 0), dx, 1)
    promotable_ok = allow & (ring_open >= P.HARVEST_RING_MINIMUM)
    return ring & gentle & allow & ~settled, promotable_ok


def settled_mask(g, rules):
    """Built-up ground - streets, plazas, quays, yards: at least settledMinBuilt built placements (walls, houses,
    lanterns, benches, stalls, piers...) within settledRadiusTiles. Patch props stay out of it; real scenery there
    (a town's citrus planters) may still be promoted."""
    pl = rules["placement"]
    built = np.zeros(g.shape, np.float32)
    for p in g.scene["placements"]:
        if any(word in p["kit"] for word in rules["built"]):
            try:
                tx, ty = g.frame.tile(p["position"][0], p["position"][2])
            except frames.FrameError:
                continue
            built[ty, tx] += 1
    if not built.any():
        return np.zeros(g.shape, bool)
    from scipy import signal
    near = signal.fftconvolve(built, disk(pl["settledRadiusTiles"]).astype(np.float32), mode="same")
    return near >= pl["settledMinBuilt"] - 0.5


def feature_fields(g, rules):
    """{feature: distance in tiles to the nearest placement of that feature}, and the promotable placements."""
    classes = rules["features"]
    rasters = {name: np.zeros(g.shape, bool) for name in classes}
    promotable = []
    for p in g.scene["placements"]:
        try:
            tx, ty = g.frame.tile(p["position"][0], p["position"][2])
        except frames.FrameError:
            continue
        kit = p["kit"]
        for name, words in classes.items():
            if any(w in kit for w in words):
                rasters[name][ty, tx] = True
                break
        resource = next((r for k, r in rules["promote"].items() if kit == k or kit.startswith(k)), None)
        if resource and p["assetId"] not in g.bound:
            promotable.append({"tile": (tx, ty), "resource": resource, "assetId": p["assetId"], "kit": kit,
                               "height": float(p["position"][1])})
    dist = {name: (ndimage.distance_transform_edt(~r) if r.any() else np.full(g.shape, np.inf))
            for name, r in rasters.items()}
    return dist, promotable


# --- placement -------------------------------------------------------------------------------------------------------

def disk(radius):
    r = int(math.ceil(radius))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return (xx * xx + yy * yy) <= radius * radius


def window(shape, x, y, r):
    h, w = shape
    return max(0, y - r), min(h, y + r + 1), max(0, x - r), min(w, x + r + 1)


def weighted(rng, weights: dict):
    keys = sorted(weights)
    p = np.array([weights[k] for k in keys], float)
    if p.sum() <= 0:
        return None
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def palette_for(g, rules, resources, features_present):
    cap = rules["levelCaps"].get(g.region, rules["levelCaps"]["default"])
    allowed = lambda k: k in resources and resources[k].required_level <= cap
    kinds = {}
    for feature in features_present + ["open"]:
        for k, w in rules["kindsByFeature"].get(feature, {}).items():
            if allowed(k):
                kinds.setdefault(feature, {})[k] = w
    return kinds, cap


def plan_map(g, reached, rules, resources, srv_interior_ids, log=print):
    """Sites and nodes for one map: [{"id", "name", "feature", "nodes": [{objectId, tile, resource, yaw,
    bindPlacement?}]}]."""
    seed = int(sha(f"{rules['seed']}:{g.region}".encode())[:8], 16)
    rng = np.random.default_rng(seed)
    cov, cl, pl = rules["coverage"], rules["clumps"], rules["placement"]
    cut = cov["cutSeconds"] / rules["secondsPerTile"]
    reach = reached & (g.codes != 0)
    existing = np.zeros(g.shape, bool)
    for n in g.nodes:
        existing[n.y, n.x] = True
    dist = ndimage.distance_transform_edt(~existing) if existing.any() else np.full(g.shape, np.inf)
    dead = reach & (dist > cut)
    cand, promotable_ok = candidate_mask(g, reached, rules)
    fdist, promotable = feature_fields(g, rules)
    present = [f for f, d in fdist.items() if np.isfinite(d).any()]
    palette, cap = palette_for(g, rules, resources, present)
    promotable = [p for p in promotable if promotable_ok[p["tile"][1], p["tile"][0]]
                  and p["resource"] in resources and resources[p["resource"]].required_level <= cap]
    lowshore = reach & (g.heights <= pl["shoreHeightMetres"]) & (ndimage.distance_transform_edt(reach) <= 3)
    # attractiveness: near any natural feature, more near a promotable placement
    natural = np.full(g.shape, np.inf)
    for f, d in fdist.items():
        natural = np.minimum(natural, d)
    attract = np.where(natural <= pl["featureReachTiles"], pl["featureBonus"], 1.0)
    prom_by_tile = {}
    for p in promotable:
        prom_by_tile.setdefault(p["tile"], p)
    taken = np.zeros(g.shape, bool)          # node tiles placed in this pass
    spacing = np.zeros(g.shape, bool)        # tiles within min spacing of a node of this pass
    used_ids = set(g.used_ids) | set(srv_interior_ids)
    next_id = rules["objectIdBase"]
    kind_sites = {}
    sites = []
    coarse = 8
    reach_total = reach.sum()
    misses = 0

    def alloc_id():
        nonlocal next_id
        while next_id in used_ids:
            next_id += 1
        if next_id > rules["objectIdLimit"]:
            raise CoverageError(f"{g.region}: object id range {rules['objectIdBase']}-{rules['objectIdLimit']} is full")
        used_ids.add(next_id)
        next_id += 1
        return next_id - 1

    def feature_at(x, y):
        best, bd = None, pl["featureReachTiles"] + 1e-9
        for f in present:
            d = fdist[f][y, x]
            if d <= bd:
                best, bd = f, d
        if best is None and lowshore[y, x]:
            return "lowshore"
        return best or "open"

    nov = rules["novelty"]
    promote_only = set(rules["promoteOnly"])
    kind_pos = {}
    for n in g.nodes:
        kind_pos.setdefault(n.resource, []).append((n.x, n.y))

    def kinds_for(feature, at, avoid=()):
        w = dict(palette.get(feature) or palette.get("open") or {})
        if feature == "lowshore":
            w = {k: v for k, v in rules["kindsByFeature"]["lowshore"].items()
                 if k in resources and resources[k].required_level <= cap}
        for k in rules["commons"]:
            if feature not in ("lowshore", "shore", "wet") and k in resources:
                w.setdefault(k, nov["commonWeight"])
        out = {}
        for k, v in w.items():
            if k in promote_only:
                continue
            if kind_sites.get(k, 0) < nov["fewSites"]:          # each palette kind recurs in several places
                v *= nov["global"]
            pos = kind_pos.get(k)
            if not pos or np.min(np.hypot(*(np.array(pos) - np.array(at)).T)) > nov["localTiles"]:
                v *= nov["local"]                                # a kind missing within 30 s of here
            if k in avoid:
                v *= nov["withinSite"]
            out[k] = v
        return out

    while dead.sum() > cov["maxResidualDeadShare"] * reach_total and misses < cov["giveUpAfter"]:
        # pick a coarse block in proportion to its dead ground, then candidate tiles near it
        h, w = g.shape
        hb, wb = (h + coarse - 1) // coarse, (w + coarse - 1) // coarse
        pad = np.zeros((hb * coarse, wb * coarse), np.float32)
        pad[:h, :w] = dead
        blocksum = pad.reshape(hb, coarse, wb, coarse).sum(axis=(1, 3)).ravel()
        if blocksum.sum() == 0:
            break
        radius = cut * rng.uniform(*cov["siteRadiusFraction"])
        foot = disk(radius)
        r = foot.shape[0] // 2
        best = None
        for _ in range(cov["proposalsPerSite"]):
            b = int(rng.choice(len(blocksum), p=blocksum / blocksum.sum()))
            by, bx = divmod(b, wb)
            cy, cx = by * coarse + coarse // 2, bx * coarse + coarse // 2
            y0, y1, x0, x1 = window(g.shape, cx, cy, int(radius))
            sub = cand[y0:y1, x0:x1] & ~spacing[y0:y1, x0:x1]
            prom = [p for p in promotable if x0 <= p["tile"][0] < x1 and y0 <= p["tile"][1] < y1
                    and not spacing[p["tile"][1], p["tile"][0]] and not taken[p["tile"][1], p["tile"][0]]]
            options = []
            if sub.any():
                ys, xs = np.nonzero(sub)
                k = int(rng.integers(len(ys)))
                options.append((x0 + xs[k], y0 + ys[k], None))
            if prom:
                p = prom[int(rng.integers(len(prom)))]
                options.append((p["tile"][0], p["tile"][1], p))
            for x, y, p in options:
                wy0, wy1, wx0, wx1 = window(g.shape, x, y, r)
                fy0, fx0 = wy0 - (y - r), wx0 - (x - r)
                gain = (dead[wy0:wy1, wx0:wx1] & foot[fy0:fy0 + wy1 - wy0, fx0:fx0 + wx1 - wx0]).sum()
                bonus = (pl["promoteBonus"] / (1.0 + kind_sites.get(p["resource"], 0) / pl["promoteDecaySites"])
                         if p else attract[y, x])
                score = gain * bonus * rng.lognormal(0, 0.35)
                if best is None or score > best[0]:
                    best = (score, gain, x, y, p)
        if best is None or best[1] < cov["minGainShare"] * foot.sum():
            misses += 1
            continue
        misses = 0
        _, _, x, y, prom = best
        site = build_site(g, x, y, prom, cand, taken, spacing, promotable, rules, rng, feature_at, kinds_for,
                          alloc_id)
        if not site:
            # mark the proposal's tile as unusable and try elsewhere
            spacing[y, x] = True
            misses += 1
            continue
        for node in site["nodes"]:
            nx, ny = node["tile"]
            y0, y1, x0, x1 = window(g.shape, nx, ny, int(cut))
            fy0, fx0 = y0 - (ny - int(cut)), x0 - (nx - int(cut))
            cover = disk(cut)
            dead[y0:y1, x0:x1] &= ~cover[fy0:fy0 + y1 - y0, fx0:fx0 + x1 - x0]
            kind_pos.setdefault(node["resource"], []).append((nx, ny))
        for k in {n["resource"] for n in site["nodes"]}:
            kind_sites[k] = kind_sites.get(k, 0) + 1
        site["id"] = unique_grouping(g, len(sites) + 1)
        sites.append(site)
    log(f"  {g.region}: {len(sites)} sites, {sum(len(s['nodes']) for s in sites)} nodes, residual dead "
        f"{dead.sum() / max(1, reach_total):.3f}")
    return sites


def unique_grouping(g, n):
    while True:
        gid = f"{g.region}-wild-{n:04d}"
        if gid not in g.used_groupings:
            return gid
        n += 1000


def _draw(rng, table):
    keys = sorted(int(k) for k in table)
    p = np.array([table[str(k)] for k in keys], float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def build_site(g, x, y, prom, cand, taken, spacing, promotable, rules, rng, feature_at, kinds_for, alloc_id):
    """One site, read as one place the way an EL patch is: one to three sub-clumps a few metres apart, each of one to
    six nodes in one or two kinds, the kinds differing between sub-clumps. The first sub-clump stands on (x, y) - a
    promoted placement when `prom` - and a member may itself be a promotable placement nearby."""
    cl = rules["clumps"]
    promote_only = set(rules["promoteOnly"])
    h, w = g.shape
    centres = [(x, y, prom)]
    n_sub = _draw(rng, cl["subClumps"])
    spread = rng.uniform(*cl["subSpreadTiles"])
    if n_sub > 1:
        r = int(math.ceil(spread))
        y0, y1, x0, x1 = window(g.shape, x, y, r)
        ys, xs = np.nonzero(cand[y0:y1, x0:x1] & ~spacing[y0:y1, x0:x1])
        order = rng.permutation(len(ys))
        for i in order:
            if len(centres) >= n_sub:
                break
            tx, ty = x0 + xs[i], y0 + ys[i]
            d2 = (tx - x) ** 2 + (ty - y) ** 2
            if d2 > spread * spread or any((tx - a) ** 2 + (ty - b) ** 2 < cl["subMinApartTiles"] ** 2
                                           for a, b, _ in centres):
                continue
            centres.append((int(tx), int(ty), None))
    nodes, site_kinds = [], []

    def free(tx, ty):
        if not (0 <= tx < w and 0 <= ty < h) or taken[max(0, ty - 1):ty + 2, max(0, tx - 1):tx + 2].any():
            return False
        return all(max(abs(tx - n["tile"][0]), abs(ty - n["tile"][1])) >= cl["minSpacingChebyshev"] for n in nodes)

    def place(tx, ty, resource, p):
        node = {"objectId": alloc_id(), "tile": [int(tx), int(ty)], "resource": resource,
                "yaw": int(rng.integers(0, 360))}
        if p:
            node["bindPlacement"] = p["assetId"]
            node["height"] = round(p["height"], 3)
        nodes.append(node)
        taken[ty, tx] = True
        s_ = cl["minSpacingChebyshev"]
        spacing[max(0, ty - s_):ty + s_ + 1, max(0, tx - s_):tx + s_ + 1] = True

    for cx, cy, p in centres:
        if not p and not free(cx, cy):
            continue
        if p and taken[max(0, cy - 1):cy + 2, max(0, cx - 1):cx + 2].any():
            continue
        feature = feature_at(cx, cy)
        anchor = p["resource"] if p else weighted(rng, kinds_for(feature, (cx, cy), site_kinds))
        if anchor is None:
            continue
        kinds = [anchor]
        if _draw(rng, cl["kindsPerClump"]) > 1 or anchor in promote_only:
            extra = weighted(rng, {k: v for k, v in kinds_for(feature, (cx, cy), site_kinds + kinds).items()
                                   if k not in kinds})
            if extra:
                kinds.append(extra)
        # patch props carry only kinds a patch model may show: a promote-only anchor (an olive tree) keeps its kind
        # to itself and to further promoted placements; its companions are the other kinds
        patch_kinds = [k for k in kinds if k not in promote_only]
        size = max(_draw(rng, cl["sizes"]), len(kinds))
        place(cx, cy, anchor, p)
        members = [(cx, cy)]
        radius = rng.uniform(*cl["radiusTiles"])
        y0, y1, x0, x1 = window(g.shape, cx, cy, int(math.ceil(radius)))
        options = [(pp["tile"][0], pp["tile"][1], pp) for pp in promotable
                   if x0 <= pp["tile"][0] < x1 and y0 <= pp["tile"][1] < y1
                   and (pp["tile"][0] - cx) ** 2 + (pp["tile"][1] - cy) ** 2 <= cl["promoteWithinTiles"] ** 2
                   and pp["resource"] in kinds]
        ys, xs = np.nonzero(cand[y0:y1, x0:x1])
        options += [(int(x0 + a), int(y0 + b), None) for b, a in zip(ys, xs)
                    if (x0 + a - cx) ** 2 + (y0 + b - cy) ** 2 <= radius * radius]
        for i in rng.permutation(len(options)):
            if len(members) >= size:
                break
            tx, ty, pp = options[i]
            if (tx, ty) in members or not free(tx, ty):
                continue
            # a neighbour straight along a row or column reads as a grid: take such a tile only sometimes
            near = min(members, key=lambda m: (m[0] - tx) ** 2 + (m[1] - ty) ** 2)
            if (near[0] == tx or near[1] == ty) and rng.random() > cl["axisKeep"]:
                continue
            if not pp and not patch_kinds:
                continue
            resource = pp["resource"] if pp else patch_kinds[len(members) % len(patch_kinds)]
            place(tx, ty, resource, pp)
            members.append((tx, ty))
        site_kinds += [k for k in kinds if k not in site_kinds]
    if not nodes:
        return None
    names = sorted({n["resource"] for n in nodes})
    name = (f"Wild {names[0]}" if len(names) == 1 else " and ".join(names) if len(names) == 2
            else ", ".join(names[:-1]) + " and " + names[-1])
    first = centres[0]
    return {"name": name, "feature": f"promoted:{prom['kit']}" if prom else feature_at(first[0], first[1]),
            "nodes": nodes}


# --- verification ----------------------------------------------------------------------------------------------------

def verify(grounds, srv, plans, log=print):
    """Production rules on the whole continent with the new bodies closed. Drops failing new nodes (and repeats) and
    returns {region: [problem records]} for anything that still fails (existing nodes included)."""
    dropped = {r: [] for r in plans}
    before, _ = union_reach(grounds, srv)
    for round_ in range(6):
        closed = {r: [tuple(n["tile"]) for s in plans[r] for n in s["nodes"]] for r in plans}
        after, codes_after = union_reach(grounds, srv, closed)
        offenders = {r: set() for r in grounds}
        # 1. no reachable tile other than the new bodies may be lost
        for r, g in grounds.items():
            new = np.zeros(g.shape, bool)
            for x, y in closed.get(r, ()):
                new[y, x] = True
            lost = before[r] & ~after[r] & ~new
            if lost.any():
                ly, lx = np.nonzero(lost)
                near = chebyshev_mask(g.shape, list(zip(lx.tolist(), ly.tolist())), 3)
                for s in plans.get(r, []):
                    for n in s["nodes"]:
                        if near[n["tile"][1], n["tile"][0]]:
                            offenders[r].add(n["objectId"])
                log(f"  {r}: {int(lost.sum())} tiles would lose reach")
        # 2. every node (old and new) by the reach-side rule over the closed codes; D11 and ids for the new
        frames_ = {r: g.frame for r, g in grounds.items()}
        polys = {r: g.polygon for r, g in grounds.items()}
        grounds_open = {}
        for r, g in grounds.items():
            ground = g.ground.copy()
            for x, y in closed.get(r, ()):
                ground[y, x] = 0
            grounds_open[r] = ground
        checker = P.Checker(codes_after, after, frames_, polys, ground=grounds_open)
        old_failures = {}
        for r, g in grounds.items():
            for n in g.nodes:
                before_n = len(checker.failures)
                checker.node(r, [n.x, n.y], f"{r}:{n.object_id}")
                if len(checker.failures) > before_n:
                    old_failures.setdefault(r, []).append(checker.failures[-1])
            for s in plans.get(r, []):
                for n in s["nodes"]:
                    if not checker.node(r, n["tile"], f"{r}:{n['objectId']}"):
                        offenders[r].add(n["objectId"])
            road = HP.road_offenders(g.scene["paths"], [{"id": n["objectId"], "tile": n["tile"]}
                                                        for s in plans.get(r, []) for n in s["nodes"]], g.frame.local)
            offenders[r] |= {o["id"] for o in road}
        # an existing node that fails now but passes with nothing closed is a new neighbour's fault
        if any(old_failures.values()):
            base_checker = P.Checker({r: g.codes for r, g in grounds.items()}, before, frames_, polys,
                                     ground={r: g.ground for r, g in grounds.items()})
            for r, items in old_failures.items():
                for item in items:
                    if base_checker.node(r, item["tile"], item["id"]):
                        near = chebyshev_mask(grounds[r].shape, [tuple(item["tile"])], 3)
                        for s in plans[r]:
                            for n in s["nodes"]:
                                if near[n["tile"][1], n["tile"][0]]:
                                    offenders[r].add(n["objectId"])
        if not any(offenders.values()):
            residual = {r: [f for f in old_failures.get(r, [])] for r in plans}
            return dropped, residual
        for r, ids in offenders.items():
            if not ids or r not in plans:
                continue
            for s in plans[r]:
                keep = [n for n in s["nodes"] if n["objectId"] not in ids]
                dropped[r] += [n["objectId"] for n in s["nodes"] if n["objectId"] in ids]
                s["nodes"] = keep
            plans[r] = [s for s in plans[r] if s["nodes"]]
            log(f"  {r}: dropped {len(ids)} nodes (round {round_ + 1})")
    raise CoverageError("verification did not settle after six rounds")


# --- stencil metrics (the audit's, on one map) -----------------------------------------------------------------------

def metrics(g, reached, points, rules):
    """points: [(x, y, resource)]. Travel in seconds of running; patches link at 8 player heights."""
    spt = rules["secondsPerTile"]
    reach = reached & (g.codes != 0)
    for x, y, _ in points:
        reach[y, x] = True
    rows = np.nonzero(reach)
    out = {"nodes": len(points), "kinds": len({k for _, _, k in points})}
    if not points:
        return out
    raster = np.zeros(g.shape, bool)
    for x, y, _ in points:
        raster[y, x] = True
    d = ndimage.distance_transform_edt(~raster)[rows] * spt
    out["nearestMedianSeconds"] = round(float(np.median(d)), 2)
    out["nearestP90Seconds"] = round(float(np.percentile(d, 90)), 2)
    out["noneWithin50mShare"] = round(float((d > 10.0).mean()), 4)
    kinds = sorted({k for _, _, k in points})
    within = np.zeros(len(rows[0]), np.int16)
    for k in kinds:
        kr = np.zeros(g.shape, bool)
        for x, y, kk in points:
            if kk == k:
                kr[y, x] = True
        within += (ndimage.distance_transform_edt(~kr)[rows] * spt <= 30.0)
    out["kindsWithin30s"] = round(float(within.mean()), 2)
    side = int(round(16 / spt))
    s = np.pad(reach.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    n = np.pad(raster.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    h, w = g.shape
    ys, xs = np.arange(0, max(1, h - side + 1), side // 2), np.arange(0, max(1, w - side + 1), side // 2)
    y1, x1 = np.minimum(ys + side, h), np.minimum(xs + side, w)
    box = lambda a: a[np.ix_(y1, x1)] - a[np.ix_(ys, x1)] - a[np.ix_(y1, xs)] + a[np.ix_(ys, xs)]
    keep = box(s) >= 0.5 * side * side
    out["squares16sOccupied"] = round(float((box(n)[keep] > 0).mean()), 4) if keep.any() else None
    out["kindsPerMap"] = len(kinds)
    from scipy.spatial import cKDTree
    P_ = np.array([[x, y] for x, y, _ in points], float)
    res = [k for _, _, k in points]
    if len(P_) >= 5:
        tree = cKDTree(P_)
        parent = list(range(len(P_)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a
        for a, b in tree.query_pairs(8 * PH_TILES):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        groups = {}
        for i in range(len(P_)):
            groups.setdefault(find(i), []).append(i)
        kinds_per = [len({res[i] for i in m}) for m in groups.values()]
        big = [len({res[i] for i in m}) == 1 for m in groups.values() if len(m) >= 3]
        out["kindsPerPatch"] = round(float(np.mean(kinds_per)), 2)
        out["singleKindPatchShare"] = round(float(np.mean(big)), 3) if big else 0.0
        dd, nn = tree.query(P_, k=2)
        v = P_[nn[:, 1]] - P_
        dist = dd[:, 1]
        axis = (v[:, 0] == 0) | (v[:, 1] == 0)
        vals, cnts = np.unique(dist, return_counts=True)
        modal = np.isclose(dist, vals[np.argmax(cnts)])
        out["exactGridShare"] = round(float((axis & modal).mean()), 3)
        out["spacingCV"] = round(float(dist.std() / dist.mean()), 3)
    return out


def judge(m, targets):
    verdict = {}
    for key, rule in targets.items():
        v = m.get(key)
        if v is None:
            continue
        ok = (v <= rule["max"]) if "max" in rule else (v >= rule["min"])
        verdict[key] = bool(ok)
    return verdict


# --- the plan --------------------------------------------------------------------------------------------------------

def build(checkout: Path, server: Path, maps=None, log=print):
    rules = read_json(RULES)
    srv = server_inputs(server)
    regions = list(EXTERIOR)
    scenes = {r: read_scene(r, checkout, rules["pass"]) for r in regions}
    grounds = {r: Ground(r, checkout, srv, scenes[r]) for r in regions}
    for r, g in grounds.items():           # the road parser must agree with the publisher: no existing node offends
        hits = HP.road_offenders(g.scene["paths"], [{"id": n.object_id, "tile": [n.x, n.y]} for n in g.nodes],
                                 g.frame.local)
        if hits:
            raise CoverageError(f"{r}: existing nodes read as on a road {hits[:3]}; the scene's roads are misread")
    reached, _ = union_reach(grounds, srv)
    srv_interior = interior_ids(srv)
    targets = rules["targets"]
    chosen = [m for m in regions if not maps or m in maps]
    plans = {}
    for r in chosen:
        plans[r] = plan_map(grounds[r], reached[r], rules, srv["resources"], srv_interior, log=log)
    dropped, residual = verify({r: grounds[r] for r in regions}, srv, plans, log=log)
    after_reach, _ = union_reach(grounds, srv, {r: [tuple(n["tile"]) for s in plans[r] for n in s["nodes"]]
                                                for r in plans})
    out_maps = {}
    for r in chosen:
        g = grounds[r]
        old = [(n.x, n.y, n.resource) for n in g.nodes]
        new = [(n["tile"][0], n["tile"][1], n["resource"]) for s in plans[r] for n in s["nodes"]]
        mb, ma = metrics(g, reached[r], old, rules), metrics(g, after_reach[r], old + new, rules)
        mn = metrics(g, after_reach[r], new, rules)
        shape_new = {k: mn[k] for k in ("kindsPerPatch", "singleKindPatchShare", "exactGridShare", "spacingCV")
                     if k in mn}
        for s in plans[r]:
            for n in s["nodes"]:
                x, z = g.frame.local(*n["tile"])
                y = n.pop("height", None)
                if y is None:
                    y = float(g.heights[n["tile"][1], n["tile"][0]])
                n["position"] = [round(x, 3), round(y, 3), round(z, 3)]
        out_maps[r] = {
            "inputs": {"scene": f"godot-client/world_authoring/regions/{r}/{r}.tscn",
                       "sceneSha256": sha(g.scene["base"].encode("utf-8")), "servedGridSha256": g.grid_sha},
            "existingNodes": len(old), "addedNodes": len(new), "sites": len(plans[r]),
            "promoted": sum(1 for s in plans[r] for n in s["nodes"] if "bindPlacement" in n),
            "kinds": sorted({k for *_, k in new}), "dropped": sorted(dropped.get(r, [])),
            "existingNodeProblems": residual.get(r, []),
            "before": mb, "after": ma, "newOnly": shape_new, "targetsBefore": judge(mb, targets),
            "targetsAfter": judge(ma, targets), "targetsNewOnly": judge(shape_new, targets),
            "groupings": plans[r]}
        log(f"{r:12s} +{len(new):4d} in {len(plans[r]):3d} sites | p90 {mb.get('nearestP90Seconds')} -> "
            f"{ma.get('nearestP90Seconds')} s | kinds {mb.get('kindsPerMap')} -> {ma.get('kindsPerMap')} | "
            f"in 30 s {mb.get('kindsWithin30s')} -> {ma.get('kindsWithin30s')}")
    return {"schema": SCHEMA, "tool": TOOL, "rules": RULES.relative_to(checkout).as_posix(),
            "rulesSha256": sha(RULES.read_bytes()), "pass": rules["pass"],
            "serverHarvestingSha256": srv["harvestSha256"],
            "about": "Generated by harvest_coverage.py; do not hand-edit. Every node passed publish_server.py's "
                     "reach-side approach rule, D11 and the id rules with all of this plan's bodies closed.",
            "maps": out_maps}


def encode(plan) -> bytes:
    return (json.dumps(plan, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


# --- scenes ----------------------------------------------------------------------------------------------------------

def marker_block(region, site, node, pass_name, newline):
    identity = f"{region}--harvest-{node['objectId']}-{node['resource'].lower().replace(' ', '-')}"
    extras = {"authority": "server", "cluster": site["id"], "grouping": site["id"], "groupingName": site["name"],
              "objectId": node["objectId"], "pass": pass_name, "resource": node["resource"], "yaw": node["yaw"],
              "zone": "coverage"}
    if "bindPlacement" in node:
        extras["bindPlacement"] = node["bindPlacement"]
    HP.marker_hints({"id": identity, **extras})           # refuse anything the presentation schema refuses
    x, y, z = node["position"]
    lines = [f'[node name="{identity}" type="Marker3D" parent="{HARVEST_PARENT}"]', "gizmo_extents = 0.8",
             'script = ExtResource("s0_marker")', f'record_id = "{identity}"', 'kind = "harvestable"',
             f'label = "{node["resource"]}"', "extras = " + json.dumps(extras, indent=0, ensure_ascii=False),
             f"transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {x}, {y}, {z})", ""]
    return newline + newline.join("\n".join(lines).split("\n"))


def apply_scenes(checkout: Path, plan, log=print):
    rules = read_json(RULES)
    writes = {}
    for region, entry in plan["maps"].items():
        scene = read_scene(region, checkout, plan["pass"])
        if sha(scene["base"].encode("utf-8")) != entry["inputs"]["sceneSha256"]:
            raise CoverageError(f"{region}: the scene changed since the plan was made; run --plan again")
        newline = "\r\n" if "\r\n" in scene["base"] else "\n"
        body = "".join(marker_block(region, s, n, plan["pass"], newline) for s in entry["groupings"]
                       for n in s["nodes"])
        text = scene["base"].rstrip("\r\n") + newline + body.rstrip("\r\n") + newline
        spec_path = checkout / f"godot-client/world_authoring/regions/{region}/region-authoring-spec.json"
        spec_raw = spec_path.read_bytes()
        spec = json.loads(spec_raw)
        previous = len(scene["generated"])
        count = sum(len(s["nodes"]) for s in entry["groupings"])
        spec["gameplay"]["authoredMarkerCount"] = spec["gameplay"]["authoredMarkerCount"] - previous + count
        spec_text = json.dumps(spec, indent=_indent(spec_raw), ensure_ascii=False) + "\n"
        if b"\r\n" in spec_raw:
            spec_text = spec_text.replace("\n", "\r\n")
        writes[scene["path"]] = text.encode("utf-8")
        writes[spec_path] = spec_text.encode("utf-8")
        log(f"  {region}: {count} markers ({previous} replaced)")
    for path, data in writes.items():
        path.write_bytes(data)
    return writes


def _indent(raw: bytes) -> int:
    m = re.search(rb'\n( +)"', raw)
    return len(m.group(1)) if m else 2


# --- report ----------------------------------------------------------------------------------------------------------

def summary(plan):
    rows = []
    for r, e in plan["maps"].items():
        b, a = e["before"], e["after"]
        rows.append({"map": r, "existing": e["existingNodes"], "added": e["addedNodes"], "sites": e["sites"],
                     "promoted": e["promoted"], "p90": [b.get("nearestP90Seconds"), a.get("nearestP90Seconds")],
                     "median": [b.get("nearestMedianSeconds"), a.get("nearestMedianSeconds")],
                     "none50": [b.get("noneWithin50mShare"), a.get("noneWithin50mShare")],
                     "kinds": [b.get("kindsPerMap"), a.get("kindsPerMap")],
                     "kinds30": [b.get("kindsWithin30s"), a.get("kindsWithin30s")],
                     "failsAfter": sorted(k for k, ok in e["targetsAfter"].items() if not ok),
                     "failsNewOnly": sorted(k for k, ok in e["targetsNewOnly"].items() if not ok),
                     "spacingCV": [b.get("spacingCV"), a.get("spacingCV"), e["newOnly"].get("spacingCV")]})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", type=Path, required=True, help="rabbitlands-server checkout (read only)")
    ap.add_argument("--checkout", type=Path, default=ROOT)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="generate content/harvest-coverage.json")
    mode.add_argument("--check", action="store_true", help="regenerate and compare with the committed plan")
    mode.add_argument("--apply-scenes", action="store_true", help="write the committed plan's markers into scenes")
    ap.add_argument("--maps", help="comma-separated subset (plan only; for trials, never committed)")
    ap.add_argument("--report", type=Path, help="write a per-map summary JSON here")
    a = ap.parse_args(argv)
    if a.apply_scenes:
        apply_scenes(a.checkout, read_json(PLAN))
        return 0
    maps = set(a.maps.split(",")) if a.maps else None
    plan = build(a.checkout, a.server, maps)
    data = encode(plan)
    if a.report:
        a.report.write_text(json.dumps(summary(plan), indent=1), encoding="utf-8")
    if a.check:
        if not PLAN.exists() or PLAN.read_bytes() != data:
            print("content/harvest-coverage.json is stale: run --plan", file=sys.stderr)
            return 1
        print("harvest coverage plan is current")
        return 0
    if maps:
        print("trial run on a subset: the plan was not written")
        return 0
    PLAN.write_bytes(data)
    print(f"wrote {PLAN.relative_to(a.checkout)}: {sum(e['addedNodes'] for e in plan['maps'].values())} nodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
