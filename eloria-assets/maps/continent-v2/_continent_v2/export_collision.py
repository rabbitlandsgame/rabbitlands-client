"""export_collision.py: the served walk collision of the continent-v2 island group, every map in one run.

  python -B eloria-assets/maps/continent-v2/_continent_v2/export_collision.py --server <server checkout> \
         --bake <catalog-id>=<bake> [--bake <catalog-id>=<bake> ...] --out <work dir> \
         [--packages <dir holding <region>/client/>] [--checkout <worktree>] [--partial]

<bake> is the region bake of each committed scene (the editor-pass check bake: the directory holding
continent-authoring.json and resolved-heights.f32le). One run covers every map of the catalog, because each map's
grid carries a one-tile collar of its neighbour's ground, and the neighbour's own export decides what is open there.
Each collision block records the whole run (groupExport: every map's snapshot and served-grid SHA-256), and
crossings_v2.py and publish_server.py refuse packages from different runs. --partial allows a run over fewer maps (a
collar whose neighbour is missing is left closed and reported); it needs --packages outside the checkout, so it
never overwrites a committed package's binaries; never publish one.

The rule, per map, over the whole server frame at 0.5 m (half-cell (r, c) is centred on local x = x0 + (c + .5) / 2,
z = z1 - (r + .5) / 2 with (x0, z1) = collisionOriginMetres, and tile (tx, ty) holds half-cells 2tx..2tx+1 by
2ty..2ty+1: gridAlignment tile-centres-v1, the reshape fold the server's sync checks against):

- ground: the bake's resolved terrain on the two triangles per 2 m square the client's Terrain_ mesh draws
  (collision_export.terrain_grade's split);
- walk surfaces lie over it where they stand at or above the ground less 3 cm, faces no steeper than 0.65 only
  (collision_export's rule, glb_reader.rasterise): the road ribbons (terrain_export's own conformed Walk_ faces,
  terrain + 0.055 m), the saved bridges' deck strips (bridge_export's Walk_AuthoredBridge_ tops), each kit model's
  Walk_ subtrees, and the flat kit inlays publish_client.py publishes as walk surfaces (WALK_KIT_STEMS on a
  placement that is not solid; the solid kit decks, the causeway arch and pier trestle spans, keep their Walk_ deck
  child as the walk surface and their body as a solid);
- standable: no steeper than 0.65 or on a walk surface; not under water deeper than 0.35 m, the water being the sea
  at the plan's level wherever the ground lies below it, the lake ellipses (waterRegions) and the river ribbons
  (paths of kind river, which are NOT waterRegions: each segment's capsule at the width interpolated between its
  points, surface at the points' y); not where a solid placement's (collisionRole solid) real triangles cross the
  actor prism (collision_export.structural_mask, imported, never copied), nor on the ground an open (not
  watertight) placement's blocked cells wall in on every side, its own walk surface excepted (enclosed: a Meshy
  house is a shell, and without this its floor was open inside a ring of wall), whichever map's scene the placement
  is in: a piece whose body reaches over a border closes the neighbour's own ground as well, judged in the
  neighbour's frame on the neighbour's surface, so both maps' grids agree over it; and not on a harvest node's served
  tile (the node is a body, harvested from the ring round it: harvest_mask);
- walkable = this map's own ground (the stub's ownership polygon) and standable, or the collar: the neighbour's first
  tile across an open border (the plan's openSeams and moles), eight-connected and one tile deep, taken at the
  neighbour's surface where the neighbour's own export is open and none of this map's solids closes it;
- collision.bin = collision_export.encode_heights (this map's own ground sets the 255-step scale), then
  walkable &= grid != 0, and only then the served grid = the server's own eloria.served_grid.fold_and_encode of the
  same surface and mask: the sync refuses a served grid whose mask differs from the all-four fold of collision.bin.

The codec comes from --server: export_contracts.server_modules puts that checkout on the path and refuses modules
loaded from another, and eloria.served_grid is held to the same rule. The server's defaults only (datum -100 m,
50 mm codes, a 1.0 m climb), checked against sync_authored_collision's own constants. Never a vendored copy.

Outputs:
  <packages>/<region>/client/collision.bin          EWCG v2 (<4sHHII header, one u8 code per half-cell, row 0 south)
  <packages>/<region>/client/served-grid.escg.gz    ESCG v2, the served grid (docs/served-grid.md)
  <out>/<region>.collision.json                     the sidecar: the package manifest's collision block, which
                                                    publish_client.py --collision stamps (it refuses a stale one)
  <out>/<region>.tiles.npz                          tile masks for the reach analysis (served codes, open, reached)
  <out>/export-report.json                          AC-4(b) reach and its lost patches, AC-5, the height-frame
                                                    residual, collar and seam-crossing statistics, timings
The frames come from frames.load (the four copies must agree) and must equal each bake's server block.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import frames  # noqa: E402  (also puts the composer's _continent on the path)
import collision_export as CE  # noqa: E402  (frozen: imported, never edited)
from storage_bounds import StorageBounds  # noqa: E402
import glb_reader as GR  # noqa: E402  (collision_export put _toolkit on the path)

DEFAULT_CHECKOUT = frames.DEFAULT_CHECKOUT
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/export_collision.py"
PLAN = "eloria-assets/maps/continent-v2/_continent_v2/continent-v2-plan.json"
PACKAGES = "eloria-assets/maps/continent-v2"
SIDECAR_SCHEMA = "eloria-continent-v2-collision-v1"
COLLISION_BIN = "collision.bin"
SERVED_GRID = "served-grid.escg.gz"
CELL = CE.CELL                      # 0.5 m half-cells
MAX_GRADE = CE.MAX_GRADE            # 0.65
WADE = CE.WADE                      # 0.35 m
DECK_TOLERANCE = .03                # a walk surface supports from 3 cm below the ground up (collision_export)
UPWARD = 1 / math.sqrt(1 + MAX_GRADE ** 2) - 1e-9
CEILINGS = CE.CEILINGS
# A floor no prism reaches, for half-cells with no ground (beyond the bake's terrain) while solids are tested: a NaN
# there would make collision_export.structural_mask skip a whole triangle's window.
FLOOR_FILL = -1.0e4
AC5_RISE = 1.05                     # metres: AC-5's limit on a legal step's float rise
RESIDUAL_WARN = 0.5                 # metres: the served-heights plan's median residual warning
BAND = 512                          # half-cell rows per sampling band
PARALLEL_TRIANGLES = 200_000        # solid triangles above which the solids go to worker processes
ORTHOGONAL = ((0, 1), (1, 0), (0, -1), (-1, 0))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
FOUR = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
EIGHT = np.ones((3, 3), bool)
# A solid kit model with one of these words in its file name blocks its trunk only (the owner's call for the landing
# isle, 2026-10-09: a crown or frond that droops into an actor's height is walked under, the trunk is not). The trunk
# is the narrowest horizontal slice of the model between TRUNK_BAND metres, read in slices TRUNK_SLICE thick (palm
# trunks lean: the base stands metres from the model's origin), as a closed TRUNK_SIDES-gon prism of that slice's
# median radius within TRUNK_RADIUS, from TRUNK_SPAN below the origin to above it.
TRUNK_WORDS = ("tree",)
TRUNK_BAND = (0.3, 2.1)
TRUNK_SLICE = 0.3
TRUNK_MIN_VERTICES = 8
TRUNK_RADIUS = (0.25, 1.0)
TRUNK_SIDES = 8
TRUNK_SPAN = (-1.0, 3.0)


def say(*parts):
    print(*parts, flush=True)


class ExportError(ValueError):
    """An input the exporter refuses: a drifted frame, a stale prototype, a water shape it cannot read, a bad codec."""


# --- the server's codec ----------------------------------------------------------------------------------------------

def server_codec(server):
    """eloria.served_grid and the sync's modules from the --server checkout, behind export_contracts.server_modules."""
    server = Path(server).resolve()
    if not (server / "eloria" / "served_grid.py").is_file():
        raise ExportError(f"{server} has no eloria/served_grid.py: not a server checkout with the 16-bit served grid")
    import export_contracts as EC
    try:
        modules = EC.server_modules(server)
        served_grid = importlib.import_module("eloria.served_grid")
    except ValueError as error:
        raise ExportError(str(error)) from None
    if not Path(served_grid.__file__).resolve().is_relative_to(server):
        raise ExportError("eloria.served_grid was loaded from a different server checkout")
    sync = modules["sync_authored_collision"]
    codec_rule = (served_grid.CLIMB_MM, served_grid.UNIT_MM, served_grid.DATUM_MM)
    sync_rule = (sync.CLIMB_MILLIMETRES, sync.UNIT_MILLIMETRES, sync.DATUM_MILLIMETRES)
    if codec_rule != sync_rule:
        raise ExportError(f"the codec's climb/unit/datum {codec_rule} differ from the sync's {sync_rule}")
    return SimpleNamespace(server=server, served_grid=served_grid, sources=modules["collision_sources"], sync=sync,
                           climb_units=served_grid.CLIMB_MM // served_grid.UNIT_MM)


# --- inputs ----------------------------------------------------------------------------------------------------------

@dataclass
class Territory:
    """One map's collision input, in territory-local metres (continent = local + frame.translation)."""
    region: str
    frame: "frames.Frame"
    polygon: list                                   # ownership polygon, continent (x, z)
    heights: np.ndarray                             # resolved terrain, [row z, column x]
    terrain_origin: tuple                           # local (x, z) of heights[0, 0]
    terrain_cell: float = 2.0
    sea_level: float = 0.0
    lakes: list = field(default_factory=list)       # waterRegions: center, radii, level (ellipses only)
    rivers: list = field(default_factory=list)      # paths of kind river: points [{position, width}]
    walk: np.ndarray = field(default_factory=lambda: np.zeros((0, 3, 3)))
    solids: list = field(default_factory=list)      # [(object id, [(triangles, closed), ...], own walk triangles)]
    spawn: tuple | None = None                      # local (x, z) of the default spawn point
    harvest_tiles: list = field(default_factory=list)  # served (tx, ty) of each harvest node: the node's own body
    sources: dict = field(default_factory=dict)
    walk_sources: dict = field(default_factory=dict)


class Prototype:
    """A kit model's walk and solid triangles in its own space, split as collision_export._mesh_groups splits them."""
    cache: dict = {}

    def __init__(self, path):
        document, body = GR.load(Path(path))
        _matrices, parents = GR.hierarchy(document)
        nodes = document["nodes"]
        walk, every, solid = [], [], []
        for index, node in enumerate(nodes):
            if "mesh" not in node:
                continue
            ancestry, current = [], index
            while True:
                ancestry.append(nodes[current].get("name", ""))
                if current not in parents:
                    break
                current = parents[current]
            surface = any(name.startswith(("Terrain_", "Walk_")) for name in ancestry)
            ceiling = any(any(word in name.lower() for word in CEILINGS) for name in ancestry)
            triangles = GR.triangles(document, body, [index])
            if not len(triangles):
                continue
            every.append(triangles)
            if surface and any(name.startswith("Walk_") for name in ancestry) and not ceiling:
                walk.append(triangles)
            if not (surface and not ceiling):
                solid.append((triangles, CE.closed_mesh(triangles)))
        self.walk = np.concatenate(walk) if walk else np.zeros((0, 3, 3))
        self.every = np.concatenate(every) if every else np.zeros((0, 3, 3))
        self.solid = solid
        self.trunk = trunk(self.every) if any(word in Path(path).stem for word in TRUNK_WORDS) else None

    @classmethod
    def load(cls, path, sha256=None):
        path = Path(path)
        key = (str(path), sha256)
        if key not in cls.cache:
            if sha256 is not None:
                found = hashlib.sha256(path.read_bytes()).hexdigest()
                if found != sha256:
                    raise ExportError(f"{path}: sha256 {found} differs from the bake's {sha256}: re-bake the scene")
            cls.cache[key] = cls(path)
        return cls.cache[key]


def trunk(triangles):
    """A tree model's trunk as one closed prism group [(triangles, True)] in its own space, or None when no slice in
    TRUNK_BAND holds enough of the model to measure (the whole model then stays the solid)."""
    points = np.asarray(triangles, float).reshape(-1, 3)
    best = None
    low = TRUNK_BAND[0]
    while low < TRUNK_BAND[1] - 1e-9:
        ring = points[(points[:, 1] >= low) & (points[:, 1] < min(low + TRUNK_SLICE, TRUNK_BAND[1]))][:, [0, 2]]
        low += TRUNK_SLICE
        if len(ring) < TRUNK_MIN_VERTICES:
            continue
        centre = ring.mean(axis=0)
        radius = float(np.median(np.hypot(*(ring - centre).T)))
        if best is None or radius < best[1]:
            best = (centre, radius)
    if best is None:
        return None
    (cx, cz), radius = best[0], float(np.clip(best[1], *TRUNK_RADIUS))
    angles = np.arange(TRUNK_SIDES) * (2 * math.pi / TRUNK_SIDES)
    ring = np.stack([cx + radius * np.cos(angles), cz + radius * np.sin(angles)], axis=1)
    y0, y1 = TRUNK_SPAN
    faces = []
    for (ax, az), (bx, bz) in zip(ring, np.roll(ring, -1, axis=0)):
        faces.append([[cx, y1, cz], [ax, y1, az], [bx, y1, bz]])            # top cap
        faces.append([[cx, y0, cz], [bx, y0, bz], [ax, y0, az]])            # bottom cap
        faces.append([[ax, y0, az], [bx, y0, bz], [bx, y1, bz]])            # side
        faces.append([[ax, y0, az], [bx, y1, bz], [ax, y1, az]])
    faces = np.asarray(faces, float)
    # Outward winding (structural_mask's winding counts a face up as +1 and down as -1).
    normals = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])
    outward = np.einsum("ij,ij->i", normals, faces.mean(axis=1) - [cx, (y0 + y1) / 2, cz]) < 0
    faces[outward] = faces[outward][:, [0, 2, 1]]
    return [(faces, True)]


def placed(triangles, matrix):
    """Triangles through a glTF column-major placement matrix."""
    m = np.asarray(matrix, float).reshape(4, 4, order="F")
    return triangles @ m[:3, :3].T + m[:3, 3]


def plan_document(checkout=DEFAULT_CHECKOUT):
    return json.loads((Path(checkout) / PLAN).read_text(encoding="utf-8"))


def plan_links(plan):
    """The open borders: every pair the plan's seams join (openSeams and moles), as sorted pairs."""
    seams = plan.get("seams", {})
    pairs = {tuple(sorted(item["between"])) for key in ("openSeams", "moles") for item in seams.get(key, [])}
    return sorted(pairs)


def plan_sea_level(plan):
    levels = {float(plan.get("frame", {}).get("seaLevel", 0.0)), float(plan.get("water", {}).get("seaLevel", 0.0))}
    if len(levels) != 1:
        raise ExportError(f"the plan states two sea levels: {sorted(levels)}")
    return levels.pop()


def load_bake(region, bake, checkout=DEFAULT_CHECKOUT, *, sea_level=0.0, log=say):
    """A territory's collision input from its region bake, through publish_client.open_territory (the composer's
    snapshot loader and facade), so the walk surfaces are the ones the client package draws."""
    import publish_client as PC
    checkout = Path(checkout).resolve()
    bake = Path(bake)
    snapshot_path = bake / "continent-authoring.json" if bake.is_dir() else bake
    frame = frames.load_source(region, checkout)
    t0 = time.time()
    territory = PC.open_territory(snapshot_path, region, checkout)
    doc, world, snapshot = territory.doc, territory.world, territory.snapshot
    T, BX, G = territory.modules.T, territory.modules.BX, territory.modules.G
    if doc.get("regionId") != region:
        raise ExportError(f"{snapshot_path} is a bake of {doc.get('regionId')!r}, not {region}")
    server = doc["server"]
    baked = ((int(server["origin"][0]), int(server["origin"][1])), (int(server["cells"][0]), int(server["cells"][1])),
             tuple(float(v) for v in server["collisionOriginMetres"]))
    if baked != (frame.origin, frame.cells, frame.collision_origin):
        raise ExportError(f"{region}: the bake's server block {baked} differs from the frame "
                          f"{(frame.origin, frame.cells, frame.collision_origin)}: re-bake the committed scene")
    if tuple(float(v) for v in doc["continentTranslation"]) != frame.translation:
        raise ExportError(f"{region}: the bake's translation differs from the frame's")
    translation = np.asarray(frame.translation, float)
    lakes = []
    for water in doc.get("waterRegions", []):
        if water.get("shape") != "ellipse":
            raise ExportError(f"{region}: water region {water.get('id')} is a {water.get('shape')!r}; the exporter "
                              "reads ellipses only and will not guess another shape's footprint")
        lakes.append({"id": water["id"], "center": [float(v) for v in water["center"]],
                      "radii": [float(v) for v in water["radii"]], "level": float(water["level"])})
    rivers = [{"id": path["id"], "points": [{"position": [float(v) for v in point["position"]],
                                             "width": float(point["width"])} for point in path["points"]]}
              for path in doc.get("paths", []) if path.get("kind") == "river"]
    walk, sources = [], {}
    # Road ribbons: terrain_export's conformed Walk_ faces, as authored_overlays adds them (walk=True encodes them).
    t = time.time()
    road_faces = 0
    for path in doc.get("paths", []):
        if path.get("kind") != "road":
            continue
        faces, uv, colours = T.conform_road_faces(world, *T.authored_road_faces(world, snapshot, path))
        faces = T.encoded_road_faces(faces, uv, colours)[0]
        if len(faces):
            walk.append(faces.astype(np.float32).astype(float) - translation)
            road_faces += len(faces)
    sources["roads"] = {"paths": sum(1 for p in doc.get("paths", []) if p.get("kind") == "road"),
                        "faces": road_faces, "seconds": round(time.time() - t, 1)}
    # Saved bridges: the deck strips bridge_export draws as Walk_AuthoredBridge_* (fascia and piers are visual).
    builder = G.GltfBuilder("export_collision: bridge decks")
    _parts, bridge_walk, _records = BX._authored_bridge_geometry(world, builder)
    bridge_faces = 0
    for top in bridge_walk:
        walk.append(np.asarray(top, float).astype(np.float32).astype(float) - translation)
        bridge_faces += len(top)
    sources["bridges"] = {"decks": len(doc.get("bridges", [])), "faces": bridge_faces}
    # Kit placements whose origin the client package keeps (publish_client's closed ownership window).
    t = time.time()
    solids, kit_walk, kept, outside, stem_walk = [], 0, 0, 0, 0
    for entry in doc.get("objects", []):
        position = np.asarray(entry["matrix"], float)[12:15]
        if not PC.in_closed_window(territory.inside_window, position[0] + translation[0],
                                   position[2] + translation[2]):
            outside += 1
            continue
        kept += 1
        baked_source = entry.get("bakedSource", {})
        relative = baked_source.get("path") or ("godot-client/" + entry["scenePath"].removeprefix("res://"))
        proto = Prototype.load(checkout / relative, baked_source.get("sha256"))
        role = entry.get("collisionRole", "none")
        stem = Path(relative).stem
        if role != "solid" and stem.startswith(PC.WALK_KIT_STEMS) and len(proto.every):
            walk.append(placed(proto.every, entry["matrix"]))
            kit_walk += len(proto.every)
            stem_walk += 1
        elif len(proto.walk):
            walk.append(placed(proto.walk, entry["matrix"]))
            kit_walk += len(proto.walk)
        if role == "solid" and proto.solid:
            body = proto.trunk or proto.solid
            solids.append((entry["id"], [(placed(tris, entry["matrix"]), closed) for tris, closed in body],
                           placed(proto.walk, entry["matrix"])))
    sources["kit"] = {"placements": kept, "outsideWindow": outside, "walkFaces": kit_walk,
                      "walkInlayPlacements": stem_walk, "solidPlacements": len(solids),
                      "solidTriangles": int(sum(len(t_) for _, groups, _deck in solids for t_, _c in groups)),
                      "prototypes": len(Prototype.cache), "seconds": round(time.time() - t, 1)}
    spawn = default_spawn(doc, region, frame=frame, checkout=checkout)["position"]
    harvest_tiles = sorted({tuple(frame.tile(float(h["position"][0]), float(h["position"][2])))
                            for h in doc.get("gameplay", {}).get("harvestables", [])})
    log(f"{region}: bake read in {time.time() - t0:.1f} s ({json.dumps(sources)})")
    return Territory(
        region=region, frame=frame, polygon=territory.polygon,
        heights=np.asarray(territory.height, float), terrain_origin=tuple(float(v) for v in doc["terrain"]["origin"]),
        terrain_cell=float(doc["terrain"]["cellMetres"]), sea_level=float(sea_level), lakes=lakes, rivers=rivers,
        walk=np.concatenate(walk) if walk else np.zeros((0, 3, 3)), solids=solids,
        spawn=(float(spawn[0]), float(spawn[2])), harvest_tiles=harvest_tiles,
        sources={"bake": snapshot_path.parent.name, "snapshotSha256": sha256_file(snapshot_path),
                 "sceneSha256": doc["sources"]["scene"]["sha256"],
                 "resolvedHeightsSha256": sha256_file(territory.snapshot.resolved_heights_path),
                 **({"generatedArrival": doc["sources"]["generatedArrival"]}
                    if doc.get("sources", {}).get("generatedArrival") else {})},
        walk_sources=sources)


def default_spawn(doc, region, *, frame=None, checkout=DEFAULT_CHECKOUT):
    """The bake's one spawn point marked default: the arrival the packages, crossings_v2.py and publish_server.py
    seed their reach from (a bake's first spawn point is not necessarily that one)."""
    if frame is not None:
        import arrivals
        try:
            return arrivals.resolve(doc, frame, checkout)
        except arrivals.ArrivalError as error:
            raise ExportError(str(error)) from error
    if doc.get("generatedArrival") is not None:
        raise ExportError(f"{region}: generated arrival resolution requires its checked source frame")
    spawns = [s for s in doc.get("gameplay", {}).get("spawnPoints", []) if s.get("default")]
    if len(spawns) != 1:
        raise ExportError(f"{region}: the bake has {len(spawns)} spawn points marked default; the reach is seeded "
                          "from exactly one")
    return spawns[0]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- sampling --------------------------------------------------------------------------------------------------------

def point_in_polygon(x, z, polygon):
    """Exact ownership union using the same crossing-number rule as client publication."""
    import ownership
    return ownership.contains(x, z, polygon)


class Ground:
    """The resolved terrain on the client's two triangles per square (u + v <= 1 is the first)."""

    def __init__(self, heights, origin, cell):
        self.h = np.asarray(heights, float)
        self.rows, self.cols = self.h.shape
        self.ox, self.oz = float(origin[0]), float(origin[1])
        self.cell = float(cell)

    def sample(self, x, z):
        fx = (np.asarray(x, float) - self.ox) / self.cell
        fz = (np.asarray(z, float) - self.oz) / self.cell
        inside = (fx >= 0) & (fz >= 0) & (fx <= self.cols - 1) & (fz <= self.rows - 1)
        ix = np.clip(np.floor(fx).astype(np.int64), 0, self.cols - 2)
        iz = np.clip(np.floor(fz).astype(np.int64), 0, self.rows - 2)
        u, v = fx - ix, fz - iz
        f = self.h
        a, b, c, d = f[iz, ix], f[iz, ix + 1], f[iz + 1, ix], f[iz + 1, ix + 1]
        low = u + v <= 1
        height = np.where(low, a + (b - a) * u + (c - a) * v, d + (c - d) * (1 - u) + (b - d) * (1 - v))
        dx = np.where(low, b - a, d - c) / self.cell
        dz = np.where(low, c - a, d - b) / self.cell
        return np.where(inside, height, np.nan), np.hypot(dx, dz), inside


def _span(values, lo, hi):
    """The index slice of a monotonic (ascending or descending) 1-D array whose values lie in [lo, hi]."""
    hits = np.flatnonzero((values >= lo) & (values <= hi))
    return slice(int(hits[0]), int(hits[-1]) + 1) if len(hits) else None


def water_level(t, xs, zs, ground):
    """The water surface over a band (rows zs, columns xs, local metres): -inf where dry."""
    water = np.where(ground < t.sea_level, t.sea_level, -np.inf)
    for lake in t.lakes:
        (cx, cz), (rx, rz), level = lake["center"], lake["radii"], lake["level"]
        cs, rs = _span(xs, cx - rx, cx + rx), _span(zs, cz - rz, cz + rz)
        if cs is None or rs is None:
            continue
        xx, zz = np.meshgrid(xs[cs], zs[rs])
        inside = ((xx - cx) / rx) ** 2 + ((zz - cz) / rz) ** 2 <= 1
        block = water[rs, cs]
        water[rs, cs] = np.where(inside, np.maximum(block, level), block)
    for river in t.rivers:
        pts = np.asarray([p["position"] for p in river["points"]], float)
        widths = np.asarray([p["width"] for p in river["points"]], float)
        for a, b, wa, wb in zip(pts[:-1], pts[1:], widths[:-1], widths[1:]):
            reach = max(wa, wb) / 2
            cs = _span(xs, min(a[0], b[0]) - reach, max(a[0], b[0]) + reach)
            rs = _span(zs, min(a[2], b[2]) - reach, max(a[2], b[2]) + reach)
            if cs is None or rs is None:
                continue
            xx, zz = np.meshgrid(xs[cs], zs[rs])
            d = b - a
            length2 = d[0] ** 2 + d[2] ** 2
            s = (np.clip(((xx - a[0]) * d[0] + (zz - a[2]) * d[2]) / length2, 0, 1) if length2 > 1e-12
                 else np.zeros_like(xx))
            distance = np.hypot(xx - (a[0] + s * d[0]), zz - (a[2] + s * d[2]))
            wet = distance <= (wa + s * (wb - wa)) / 2
            block = water[rs, cs]
            water[rs, cs] = np.where(wet, np.maximum(block, a[1] + s * d[1]), block)
    return water


def half_cells(frame):
    """Half-cell centres of the frame: columns' local x (ascending), rows' local z (descending: row 0 is south)."""
    x0, z1 = frame.collision_origin
    xs = x0 + (np.arange(2 * frame.cells[0]) + .5) * CELL
    zs = z1 - (np.arange(2 * frame.cells[1]) + .5) * CELL
    return xs, zs


def own_cells(t):
    xs, zs = half_cells(t.frame)
    tx, _ty, tz = t.frame.translation
    own = np.zeros((len(zs), len(xs)), bool)
    for r0 in range(0, len(zs), BAND):
        own[r0:r0 + BAND] = point_in_polygon(xs[None, :] + tx, zs[r0:r0 + BAND, None] + tz, t.polygon)
    return own


def surface_fields(t, own):
    """Pass 1: ground, walk surfaces, slope and water over the map's own ground plus a two-cell margin."""
    xs, zs = half_cells(t.frame)
    rows, cols = len(zs), len(xs)
    x0, z1 = t.frame.collision_origin
    margin = ndimage.binary_dilation(own, np.ones((5, 5), bool))
    rr, cc = np.nonzero(margin.any(axis=1))[0], np.nonzero(margin.any(axis=0))[0]
    surface = np.full((rows, cols), np.nan)
    terrain = np.full((rows, cols), np.nan)
    support = np.zeros((rows, cols), bool)
    slope_ok = np.zeros((rows, cols), bool)
    submerged = np.zeros((rows, cols), bool)
    counts = {"walkTriangles": int(len(t.walk))}
    if not len(rr):
        return dict(surface=surface, terrain=terrain, support=support, slope_ok=slope_ok, submerged=submerged,
                    base_open=np.zeros((rows, cols), bool), window=None, counts=counts)
    window = (slice(int(rr[0]), int(rr[-1]) + 1), slice(int(cc[0]), int(cc[-1]) + 1))
    covered, top = GR.rasterise(np.asarray(t.walk, float).reshape(-1, 3, 3), cols, rows, x0, z1, CELL, upward=UPWARD)
    ground = Ground(t.heights, t.terrain_origin, t.terrain_cell)
    wx = xs[window[1]]
    for r0 in range(window[0].start, window[0].stop, BAND):
        r1 = min(r0 + BAND, window[0].stop)
        band = (slice(r0, r1), window[1])
        xx, zz = np.meshgrid(wx, zs[r0:r1])
        height, grade, inside = ground.sample(xx, zz)
        deck = top[band]
        supported = covered[band] & (deck >= height - DECK_TOLERANCE) & inside
        surf = np.where(supported, deck, height)
        water = water_level(t, wx, zs[r0:r1], height)
        surface[band] = surf
        terrain[band] = height
        support[band] = supported
        slope_ok[band] = ((grade <= MAX_GRADE + 1e-9) | supported) & inside
        submerged[band] = np.isfinite(surf) & (surf < water - WADE)
    base_open = slope_ok & ~submerged & np.isfinite(surface)
    return dict(surface=surface, terrain=terrain, support=support, slope_ok=slope_ok, submerged=submerged,
                base_open=base_open, window=window, counts=counts)


def enclosed(shell, deck=None):
    """The cells a placement's blocked shell walls in on every side: an open (not watertight) mesh closes only the
    cells its triangles cross, so a building is a ring of wall with a walkable floor inside it. Ground the ring
    leaves a way out of (a doorway, an arcade, a passage under an arch) is not enclosed and stays open, and so does
    the placement's own walk surface (a gatehouse passage, a pier or causeway deck between its parapets)."""
    inside = ndimage.binary_fill_holes(shell) & ~shell
    if deck is not None:
        inside &= ~deck
    return inside


def _mask_batch(batch):
    """A worker's share of the solid placements: [(index, blocked sub-window)]. An open mesh's shell also blocks
    the ground it encloses (enclosed); a closed one is already solid inside (collision_export's winding)."""
    results = []
    for index, keep, deck, sub, sx0, sz1 in batch:
        mask = CE.structural_mask(keep, sub, sx0, sz1)
        if not all(closed for _tris, closed in keep):
            walk = None
            if len(deck):
                walk = GR.rasterise(deck, sub.shape[1], sub.shape[0], sx0, sz1, CELL, upward=UPWARD)[0]
            mask |= enclosed(mask, walk)
        results.append((index, mask))
    return results


def structure_mask(solids, floor, x0, z1, *, workers=None):
    """collision_export.structural_mask, one placement at a time over its own window (open meshes' triangles beyond
    the floor's reach are dropped first: they cannot cross an actor's prism), with the ground an open mesh's shell
    encloses blocked too. The placements are independent and their masks are OR-ed, so a large map spreads them over
    worker processes with the same result."""
    rows, cols = floor.shape
    blocked = np.zeros((rows, cols), bool)
    tasks, triangles = [], 0
    for _identity, groups, deck in solids:
        points = np.concatenate([g.reshape(-1, 3) for g, _closed in groups])
        c0 = max(0, int(math.floor((points[:, 0].min() - 1 - x0) / CELL)))
        c1 = min(cols, int(math.floor((points[:, 0].max() + 1 - x0) / CELL)) + 1)
        r0 = max(0, int(math.floor((z1 - points[:, 2].max() - 1) / CELL)))
        r1 = min(rows, int(math.floor((z1 - points[:, 2].min() + 1) / CELL)) + 1)
        if c1 <= c0 or r1 <= r0:
            continue
        sub = floor[r0:r1, c0:c1]
        low, high = float(sub.min()), float(sub.max())
        keep = []
        for tris, closed in groups:
            if closed:
                keep.append((tris, closed))
                continue
            lo, hi = tris[:, :, 1].min(axis=1), tris[:, :, 1].max(axis=1)
            selected = (lo <= high + CE.ACTOR_HEIGHT) & (hi >= low + CE.ACTOR_FLOOR_CLEARANCE)
            if selected.any():
                keep.append((tris[selected], False))
        if keep:
            size = sum(len(k) for k, _ in keep)
            triangles += size
            tasks.append((size, (len(tasks), keep, np.asarray(deck, float).reshape(-1, 3, 3), sub.copy(),
                                 x0 + c0 * CELL, z1 - r0 * CELL), (r0, r1, c0, c1)))
    workers = min(4, os.cpu_count() or 1) if workers is None else workers
    if not 1 <= workers <= 4:
        raise ValueError("collision workers must be between one and four")
    windows = {task[1][0]: task[2] for task in tasks}
    if workers <= 1 or triangles < PARALLEL_TRIANGLES:
        results = _mask_batch([task[1] for task in tasks])
    else:
        # Largest first, dealt round-robin into a few batches per worker.
        order = sorted(tasks, key=lambda task: -task[0])
        batches = [[task[1] for task in order[k::workers * 4]] for k in range(workers * 4)]
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = [item for part in pool.map(_mask_batch, [b for b in batches if b]) for item in part]
    for index, mask in results:
        r0, r1, c0, c1 = windows[index]
        blocked[r0:r1, c0:c1] |= mask
    return blocked, triangles


# --- the group export ------------------------------------------------------------------------------------------------

def harvest_mask(t, shape):
    """The half-cells of every harvest node's served tile: a node is a body on its tile (a tree, a rock, a bush),
    harvested from the ring round it, so its own tile is closed as a solid's are (tile (tx, ty) holds half-cells
    2tx..2tx+1 by 2ty..2ty+1)."""
    mask = np.zeros(shape, bool)
    for tx, ty in t.harvest_tiles:
        mask[2 * ty:2 * ty + 2, 2 * tx:2 * tx + 2] = True
    return mask


def _offset(a, b):
    """Half-cell (row, column) offsets from map a's grid to map b's: the frames share whole continent metres."""
    ax, az = a.frame.lattice
    bx, bz = b.frame.lattice
    dc, dr = 2 * (ax - bx), 2 * (bz - az)
    if dc != round(dc) or dr != round(dr):
        raise ExportError(f"{a.region} and {b.region} do not share the continent's metre lattice")
    return int(round(dr)), int(round(dc))


def solids_over(t, o, own_o):
    """t's solid placements whose body (with structure_mask's one-metre margin) reaches over o's own ground, moved
    into o's territory-local metres: [(object id, groups)]. The frames share the continent's metre lattice, so the
    move is a whole-metre translation."""
    shift = np.asarray(t.frame.translation, float) - np.asarray(o.frame.translation, float)
    if shift[1] != 0.0:
        raise ExportError(f"{t.region} and {o.region} differ in their vertical translation")
    x0, z1 = o.frame.collision_origin
    rows, cols = own_o.shape
    picked = []
    for identity, groups, deck in t.solids:
        points = np.concatenate([g.reshape(-1, 3) for g, _closed in groups]) + shift
        c0 = max(0, int(math.floor((points[:, 0].min() - 1 - x0) / CELL)))
        c1 = min(cols, int(math.floor((points[:, 0].max() + 1 - x0) / CELL)) + 1)
        r0 = max(0, int(math.floor((z1 - points[:, 2].max() - 1) / CELL)))
        r1 = min(rows, int(math.floor((z1 - points[:, 2].min() + 1) / CELL)) + 1)
        if c1 > c0 and r1 > r0 and own_o[r0:r1, c0:c1].any():
            picked.append((identity, [(tris + shift, closed) for tris, closed in groups],
                           np.asarray(deck, float).reshape(-1, 3, 3) + shift))
    return picked


def export_group(territories, links, codec, *, log=say, workers=None):
    """Every map's collision: {region: result namespace}. Nothing is written here (write_outputs does)."""
    by_region = {t.region: t for t in territories}
    if len(by_region) != len(territories):
        raise ExportError("a region is given twice")
    for t in territories:
        if t.frame.cells[0] != t.frame.cells[1]:
            raise ExportError(f"{t.region}: the server needs a square frame")
    timings = {}
    # Pass 1: each map's own ground.
    own, fields = {}, {}
    for t in territories:
        started = time.time()
        own[t.region] = own_cells(t)
        fields[t.region] = surface_fields(t, own[t.region])
        timings[t.region] = {"surface_s": round(time.time() - started, 1)}
        log(f"{t.region}: surface in {timings[t.region]['surface_s']} s")
    # Pass 2: the collars and each map's solids on its floor (own surface, the neighbours' over the collar).
    neighbours = {t.region: [] for t in territories}
    skipped = []
    for a, b in links:
        if a in by_region and b in by_region:
            neighbours[a].append(b)
            neighbours[b].append(a)
        elif a in by_region or b in by_region:
            skipped.append([a, b])
    collars, floors, structures = {}, {}, {}
    for t in territories:
        started = time.time()
        xs, zs = half_cells(t.frame)
        tx, _ty, tz = t.frame.translation
        # Two half-cells to the tile: a tile eight-adjacent to this map's ground has every cell within two cells
        # of one of its own (collision_export.seam_collar's 5 x 5 dilation).
        beside = ndimage.binary_dilation(own[t.region], np.ones((5, 5), bool)) & ~own[t.region]
        beside_rows, beside_cols = np.nonzero(beside)
        floor = fields[t.region]["surface"].copy()
        collars[t.region] = {}
        for other in sorted(neighbours[t.region]):
            o = by_region[other]
            rows, cols = beside_rows, beside_cols
            inside_other = point_in_polygon(xs[cols] + tx, zs[rows] + tz, o.polygon)
            rows, cols = rows[inside_other], cols[inside_other]
            dr, dc = _offset(t, o)
            orow, ocol = rows + dr, cols + dc
            size = 2 * o.frame.cells[0]
            fits = (orow >= 0) & (orow < size) & (ocol >= 0) & (ocol < size)
            if not fits.all():
                raise ExportError(f"{t.region}: {int((~fits).sum())} collar cells lie outside {other}'s frame")
            if not own[other][orow, ocol].all():
                raise ExportError(f"{t.region}: the collar toward {other} leaves {other}'s ownership polygon")
            floor[rows, cols] = fields[other]["surface"][orow, ocol]
            collars[t.region][other] = (rows, cols, orow, ocol)
        floors[t.region] = floor
        x0, z1 = t.frame.collision_origin
        filled = np.where(np.isfinite(floor), floor, FLOOR_FILL)
        mask, tested = structure_mask(t.solids, filled, x0, z1, workers=workers)
        structures[t.region] = (mask | harvest_mask(t, mask.shape), tested)
        timings[t.region]["solids_s"] = round(time.time() - started, 1)
        log(f"{t.region}: solids in {timings[t.region]['solids_s']} s")
    # Pass 2b: a solid whose body reaches over a border blocks the ground it stands on whichever map owns it. Each
    # map's own ground is closed under every other map's placements too, judged in that map's own frame on its own
    # surface (so a piece the frame of its owner clips still blocks), and the result is the same ground both maps'
    # grids then share: the owner's collar and the neighbour's own tiles.
    crossing = {t.region: np.zeros_like(own[t.region]) for t in territories}
    crossing_report = {t.region: {} for t in territories}
    for o in territories:
        x0, z1 = o.frame.collision_origin
        filled = None
        for t in territories:
            if t is o:
                continue
            picked = solids_over(t, o, own[o.region])
            if not picked:
                continue
            if filled is None:
                filled = np.where(np.isfinite(floors[o.region]), floors[o.region], FLOOR_FILL)
            mask, _tested = structure_mask(picked, filled, x0, z1, workers=workers)
            hit = mask & own[o.region]
            crossing[o.region] |= hit
            closed = hit & fields[o.region]["base_open"] & ~structures[o.region][0]
            crossing_report[o.region][t.region] = {"placements": len(picked), "cells": int(hit.sum()),
                                                   "openCellsClosed": int(closed.sum())}
        if crossing_report[o.region]:
            log(f"{o.region}: other maps' solids over its ground: {json.dumps(crossing_report[o.region])}")
    # Pass 3: walkable, collision.bin, the served grid.
    results = {}
    for t in territories:
        started = time.time()
        region = t.region
        f = fields[region]
        own_solids, solid_triangles = structures[region]
        blocked = own_solids | crossing[region]
        own_open = own[region] & f["base_open"] & ~blocked
        walkable = own_open.copy()
        collar_stats = {}
        collar_cells = np.zeros_like(walkable)
        for other, (rows, cols, orow, ocol) in collars[region].items():
            other_blocked = structures[other][0] | crossing[other]
            opened = (fields[other]["base_open"][orow, ocol] & ~other_blocked[orow, ocol] & ~blocked[rows, cols])
            walkable[rows[opened], cols[opened]] = True
            collar_cells[rows, cols] = True
            # The neighbour's own export: its ground under its own placements (another map's pieces over it are
            # counted apart, as this map's solids where they are this map's).
            theirs = fields[other]["base_open"][orow, ocol] & ~structures[other][0][orow, ocol]
            collar_stats[other] = {"cells": int(len(rows)), "openCells": int(opened.sum()),
                                   "closedByTheNeighbour": int((~theirs).sum()),
                                   "closedByThisMapsSolids": int((theirs & own_solids[rows, cols]).sum()),
                                   "closedByThirdMapsSolids": int((theirs & ~own_solids[rows, cols]
                                                                   & crossing[other][orow, ocol]).sum())}
        floor = floors[region]
        heights = np.where(walkable, floor, 0.0)
        grid, encoding = CE.encode_heights(heights, walkable, basis=own_open)
        dropped = walkable & (grid == 0)
        walkable &= grid != 0
        heights = np.where(walkable, floor, 0.0)
        served_bytes = codec.served_grid.fold_and_encode(heights, walkable)
        served = codec.served_grid.decode_file(served_bytes)
        cells = t.frame.cells[0]
        codes = np.frombuffer(served.codes, dtype=np.uint16).reshape(cells, cells).copy()
        folded = (grid.reshape(cells, 2, cells, 2) != 0).all(axis=(1, 3))
        if not np.array_equal(folded, codes != 0):
            raise ExportError(f"{region}: the served mask differs from the all-four fold of collision.bin")
        for other in collar_stats:
            rows, cols = collars[region][other][:2]
            collar_stats[other]["droppedByTheHeightScale"] = int(dropped[rows, cols].sum())
            collar_stats[other]["walkableCells"] = int(walkable[rows, cols].sum())
            mask = np.zeros_like(walkable)
            mask[rows, cols] = walkable[rows, cols]
            collar_stats[other]["walkableTiles"] = int(mask.reshape(cells, 2, cells, 2).all(axis=(1, 3)).sum())
        quad = (cells, 2, cells, 2)
        open_tiles = codes != 0
        tile_own = own[region].reshape(quad).all(axis=(1, 3))
        cells4 = heights.reshape(quad)                       # an open tile's four cells are all walkable
        top = np.where(open_tiles, cells4.max(axis=(1, 3)), np.nan)
        spread = np.where(open_tiles, cells4.max(axis=(1, 3)) - cells4.min(axis=(1, 3)), 0.0)
        deck_tiles = open_tiles & f["support"].reshape(quad).any(axis=(1, 3))
        mixed = deck_tiles & ~f["support"].reshape(quad).all(axis=(1, 3))
        ground = Ground(t.heights, t.terrain_origin, t.terrain_cell)
        ox, oy = t.frame.origin
        tcx = np.arange(cells) - ox + .5
        tcz = oy - np.arange(cells) - .5
        centre_height = ground.sample(*np.meshgrid(tcx, tcz))[0]
        metres = (codes.astype(np.float64) * served.unit_mm + served.datum_mm) / 1000.0
        plain = open_tiles & tile_own & ~deck_tiles & np.isfinite(centre_height)
        residual = np.abs(metres[plain] - centre_height[plain])
        proxy_tiles = (own[region] & f["base_open"]).reshape(quad).all(axis=(1, 3))
        step_free_tiles = (own[region] & f["base_open"] & ~blocked).reshape(quad).all(axis=(1, 3))
        statistics = {
            "walkTriangles": int(len(t.walk)),
            "structuralMeshes": int(sum(len(groups) for _, groups, _deck in t.solids)),
            "structuralPlacements": int(len(t.solids)),
            "structuralTriangles": int(sum(len(tris) for _, groups, _deck in t.solids for tris, _c in groups)),
            "structuralTrianglesTested": int(solid_triangles),
            "ownCells": int(own[region].sum()),
            "deckCells": int((own[region] & f["support"]).sum()),
            "steepCells": int((own[region] & ~f["slope_ok"] & np.isfinite(f["surface"])).sum()),
            "waterCells": int((own[region] & f["submerged"]).sum()),
            "structuralCells": int((own[region] & blocked & f["base_open"]).sum()),
            "crossSeamSolidCells": int((own[region] & f["base_open"] & crossing[region] & ~own_solids).sum()),
            "harvestNodeTiles": len(t.harvest_tiles),
            "noGroundCells": int((own[region] & ~np.isfinite(f["surface"])).sum()),
            "seamCollarCells": int((collar_cells & walkable).sum()),
            "ownWalkableCells": int(own_open.sum()),
        }
        timings[region]["grid_s"] = round(time.time() - started, 1)
        results[region] = SimpleNamespace(
            region=region, territory=t, frame=t.frame, grid=grid, encoding=encoding, walkable=walkable,
            served_bytes=served_bytes, served=served, codes=codes, open_tiles=open_tiles, own_tiles=tile_own,
            top=top, deck_tiles=deck_tiles, proxy_tiles=proxy_tiles, step_free_tiles=step_free_tiles,
            statistics=statistics, collar=collar_stats, cross_seam_solids=crossing_report[region],
            intra_tile={"openTiles": int(open_tiles.sum()),
                        "spreadOver1.05m": int((open_tiles & (spread > AC5_RISE)).sum()),
                        "deckAndGroundOver1.05m": int((mixed & (spread > AC5_RISE)).sum()),
                        "maxSpreadMetres": round(float(spread[open_tiles].max()), 3) if open_tiles.any() else 0.0},
            residual={"tiles": int(plain.sum()),
                      "medianMetres": round(float(np.median(residual)), 4) if len(residual) else None,
                      "p95Metres": round(float(np.percentile(residual, 95)), 4) if len(residual) else None,
                      "maxMetres": round(float(residual.max()), 4) if len(residual) else None,
                      "warn": bool(len(residual) and float(np.median(residual)) > RESIDUAL_WARN)})
        log(f"{region}: grid in {timings[region]['grid_s']} s: {int(walkable.sum())} walkable half-cells, "
            f"{int(open_tiles.sum())} open tiles")
    return SimpleNamespace(results=results, timings=timings, skipped_links=skipped,
                           links=[[a, b] for a, b in links if a in by_region and b in by_region])


# --- the reach analysis ----------------------------------------------------------------------------------------------

def _neighbour(a, dy, dx, fill):
    """b[y, x] = a[y + dy, x + dx] (fill beyond the edge)."""
    rows, cols = a.shape
    out = np.full_like(a, fill)
    out[max(0, -dy):rows - max(0, dy), max(0, -dx):cols - max(0, dx)] = \
        a[max(0, dy):rows + min(0, dy), max(0, dx):cols + min(0, dx)]
    return out


def legal_steps(codes, climb):
    """The server's eight steps (collision_sources.walk_step_ok): both tiles open, |code step| <= climb, and a
    diagonal only when both orthogonal steps whose corner it cuts are legal from the same start. {(dy, dx): mask}"""
    open_ = codes != 0
    h = codes.astype(np.int32)
    legal = {}
    for dy, dx in ORTHOGONAL:
        legal[(dy, dx)] = open_ & _neighbour(open_, dy, dx, False) & (np.abs(_neighbour(h, dy, dx, 0) - h) <= climb)
    for dy, dx in DIAGONAL:
        legal[(dy, dx)] = (open_ & _neighbour(open_, dy, dx, False)
                           & (np.abs(_neighbour(h, dy, dx, 0) - h) <= climb) & legal[(dy, 0)] & legal[(0, dx)])
    return legal


def reach_from(legal, shape, seeds):
    """Tiles reached from any seed over the legal steps (directed: the corner rule is judged from the start)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import breadth_first_order
    rows, cols = shape
    total = rows * cols
    index = np.arange(total, dtype=np.int64).reshape(shape)
    sources, targets = [], []
    for (dy, dx), ok in legal.items():
        start = index[ok]
        sources.append(start)
        targets.append(start + dy * cols + dx)
    seeds = [s for s in seeds if s is not None]
    sources.append(np.full(len(seeds), total, np.int64))
    targets.append(np.asarray([y * cols + x for y, x in seeds], np.int64))
    sources, targets = np.concatenate(sources), np.concatenate(targets)
    graph = coo_matrix((np.ones(len(sources), np.int8), (sources, targets)), shape=(total + 1, total + 1)).tocsr()
    order = breadth_first_order(graph, total, directed=True, return_predecessors=False)
    reached = np.zeros(total + 1, bool)
    reached[order] = True
    return reached[:total].reshape(shape)


def components_from(mask, seeds, structure=FOUR):
    labels, _count = ndimage.label(mask, structure=structure)
    hubs = {int(labels[y, x]) for y, x in seeds if y is not None and labels[y, x]}
    return np.isin(labels, sorted(hubs)) if hubs else np.zeros(mask.shape, bool)


def union_analysis(export, codec, *, top_patches=40):
    """The group's tiles on the continent's metre lattice (each map's own tiles only), flooded from every map's
    spawn: the served reach (the server's step rule), the step-free reach on the same open tiles, and the
    solid-free step-free proxy (reachlib's measure); the patches between them; AC-5; the seam crossings."""
    results = export.results
    maps = list(results.values())
    lattice = {m.region: m.frame.lattice for m in maps}
    x_lo = min(int(round(lx)) for lx, _lz in lattice.values())
    z_hi = max(int(round(lz)) for _lx, lz in lattice.values())
    x_hi = max(int(round(lattice[m.region][0])) + m.frame.cells[0] for m in maps)
    z_lo = min(int(round(lattice[m.region][1])) - m.frame.cells[1] for m in maps)
    shape = (z_hi - z_lo, x_hi - x_lo)
    codes = np.zeros(shape, np.uint16)
    top = np.full(shape, np.nan, np.float32)
    deck = np.zeros(shape, bool)
    step_free = np.zeros(shape, bool)
    proxy = np.zeros(shape, bool)
    owner = np.full(shape, -1, np.int8)
    places = {}
    seeds = []
    for k, m in enumerate(maps):
        lx, lz = (int(round(v)) for v in lattice[m.region])
        r0, c0 = z_hi - lz, lx - x_lo
        n = m.frame.cells[0]
        window = (slice(r0, r0 + n), slice(c0, c0 + n))
        places[m.region] = (r0, c0, n)
        own = m.own_tiles
        codes[window] = np.where(own, m.codes, codes[window])
        top[window] = np.where(own, m.top, top[window])
        deck[window] |= own & m.deck_tiles
        step_free[window] |= own & m.step_free_tiles
        proxy[window] |= own & m.proxy_tiles
        owner[window] = np.where(own, k, owner[window])
        spawn = m.territory.spawn
        if spawn is not None:
            try:
                sx, sy = m.frame.tile(*spawn)
                seeds.append((m.region, (r0 + sy, c0 + sx), bool(m.codes[sy, sx]), [sx, sy]))
            except frames.FrameError:
                seeds.append((m.region, None, False, None))
    seed_tiles = [s for _r, s, ok, _tile in seeds if ok]
    legal = legal_steps(codes, codec.climb_units)
    served = reach_from(legal, shape, seed_tiles)
    free = components_from(step_free, seed_tiles)
    proxied = components_from(proxy, seed_tiles)
    # AC-5 from the float tops: every legal step's rise, and the deck/ground ones.
    rise_over, rise_max, contact_over, contact_max, deck_steps, refused_deck_edges = 0, 0.0, 0, 0.0, 0, 0
    open_ = codes != 0
    for (dy, dx), ok in legal.items():
        rise = np.abs(_neighbour(top, dy, dx, np.nan).astype(np.float64) - top.astype(np.float64))
        rise_over += int((ok & (rise > AC5_RISE)).sum())
        if ok.any():
            rise_max = max(rise_max, float(np.nanmax(np.where(ok, rise, np.nan))))
        contact = ok & (deck != _neighbour(deck, dy, dx, False))
        deck_steps += int(contact.sum())
        contact_over += int((contact & (rise > AC5_RISE)).sum())
        if contact.any():
            contact_max = max(contact_max, float(np.nanmax(np.where(contact, rise, np.nan))))
        edge = open_ & _neighbour(open_, dy, dx, False) & (deck != _neighbour(deck, dy, dx, False)) & ~ok
        refused_deck_edges += int(edge.sum())
    ac5 = {"legalStepsOver1.05m": rise_over, "maxLegalRiseMetres": round(rise_max, 4),
           "legalDeckGroundSteps": deck_steps, "legalDeckGroundStepsOver1.05m": contact_over,
           "maxLegalDeckGroundRiseMetres": round(contact_max, 4),
           "refusedDeckGroundSteps": refused_deck_edges,
           "pass": rise_over == 0 and contact_over == 0}

    def patch_list(mask, reached_tiles, kind):
        labels, count = ndimage.label(mask, structure=EIGHT)
        if not count:
            return {"patches": 0, "tiles": 0, "largest": []}
        sizes = np.bincount(labels.ravel())[1:]
        drop = np.full(count + 1, np.inf)
        if kind == "step":
            heights = codes.astype(np.int32)
            for (dy, dx) in ORTHOGONAL + DIAGONAL:
                nb_reached = _neighbour(reached_tiles, dy, dx, False) & mask
                nb_codes = _neighbour(heights, dy, dx, 0)
                at = nb_reached & (labels > 0) & (_neighbour(codes, dy, dx, 0) != 0)
                np.minimum.at(drop, labels[at], np.abs(nb_codes[at] - heights[at]) * codec.served_grid.UNIT_MM / 1000)
        objects = ndimage.find_objects(labels)
        order = np.argsort(-sizes, kind="stable")[:top_patches]
        largest = []
        for index in order:
            box = objects[index]
            region_votes = np.bincount(owner[box][labels[box] == index + 1] + 1, minlength=len(maps) + 1)[1:]
            region = maps[int(np.argmax(region_votes))].region
            r0, c0, n = places[region]
            ys, xs_ = np.nonzero(labels[box] == index + 1)
            ys, xs_ = ys + box[0].start, xs_ + box[1].start
            entry = {"map": region, "tiles": int(sizes[index]),
                     "tileBounds": [int(xs_.min() - c0), int(ys.min() - r0), int(xs_.max() - c0), int(ys.max() - r0)],
                     "continentCentre": [round(float(x_lo + xs_.mean() + .5), 1),
                                         round(float(z_hi - ys.mean() - .5), 1)]}
            if kind == "step":
                entry["smallestJoinMetres"] = None if not np.isfinite(drop[index + 1]) else round(
                    float(drop[index + 1]), 2)
            if kind == "solid":
                inside = labels[box] == index + 1
                entry["underSolids"] = int((inside & ~step_free[box]).sum())
                entry["cutOff"] = int((inside & step_free[box]).sum())
            largest.append(entry)
        return {"patches": int(count), "tiles": int(sizes.sum()), "largest": largest}

    step_losses = patch_list(free & ~served, served, "step")
    solid_losses = patch_list(proxied & ~free, free, "solid")
    per_map = {}
    for k, m in enumerate(maps):
        mine = owner == k
        per_map[m.region] = {"ownTiles": int(mine.sum()), "openTiles": int((open_ & mine).sum()),
                             "servedReach": int((served & mine).sum()),
                             "stepFreeReach": int((free & mine).sum()),
                             "solidFreeStepFreeProxyReach": int((proxied & mine).sum()),
                             "stepLossTiles": int((free & ~served & mine).sum()),
                             "solidLossTiles": int((proxied & ~free & mine).sum())}
    # Seam crossings: legal steps from one map's own tile into a neighbour's own tile.
    crossings = []
    for a, b in export.links:
        ka = next(i for i, m in enumerate(maps) if m.region == a)
        kb = next(i for i, m in enumerate(maps) if m.region == b)
        for src, dst in ((ka, kb), (kb, ka)):
            departures = np.zeros(shape, bool)
            moves = 0
            for (dy, dx), ok in legal.items():
                hit = ok & (owner == src) & (_neighbour(owner, dy, dx, -1) == dst)
                moves += int(hit.sum())
                departures |= hit
            labels, count = ndimage.label(departures, structure=EIGHT)
            runs = []
            for number, box in enumerate(ndimage.find_objects(labels), start=1):
                ys, xs_ = np.nonzero(labels[box] == number)
                ys, xs_ = ys + box[0].start, xs_ + box[1].start
                runs.append({"tiles": int(len(ys)),
                             "continentX": [int(x_lo + xs_.min()), int(x_lo + xs_.max() + 1)],
                             "continentZ": [int(z_hi - ys.max() - 1), int(z_hi - ys.min())]})
            runs.sort(key=lambda r: (r["continentZ"][0], r["continentX"][0]))
            crossings.append({"from": maps[src].region, "to": maps[dst].region, "legalMoves": moves,
                              "departureTiles": int(departures.sum()),
                              "departureTilesReached": int((departures & served).sum()), "runs": runs})
    tiles = {}
    for m in maps:
        r0, c0, n = places[m.region]
        tiles[m.region] = {"served": served[r0:r0 + n, c0:c0 + n]}
    return {"seeds": [{"map": r, "tile": t_, "unionRowColumn": None if s is None else list(s), "open": ok}
                      for r, s, ok, t_ in seeds],
            "climbCodes": int(codec.climb_units),
            "union": {"shape": list(shape), "continentX0": x_lo, "continentZSouth": z_hi},
            "perMap": per_map, "stepLosses": step_losses, "solidLosses": solid_losses, "ac5": ac5,
            "seamCrossings": crossings}, tiles


# --- outputs ---------------------------------------------------------------------------------------------------------

def json_text(value):
    return json.dumps(value, indent=1, ensure_ascii=False) + "\n"


def collision_block(result, collision_sha, served_sha, codec, group=None):
    """The package manifest's collision block (the legacy exporter's keys, plus the served grid and the bake).

    `group` is the run's every map: {region: {snapshotSha256, servedGridSha256}}. A map's collar is its neighbour's
    export, so a package is only whole beside the packages of the same run: crossings_v2.py and publish_server.py
    refuse a set whose groupExport blocks disagree with each other or with the packages' own digests."""
    frame = result.frame
    cells = list(frame.cells)
    bounds = StorageBounds(*cells)
    t = result.territory
    served = result.served
    walkable = result.walkable
    return {
        "binary": COLLISION_BIN, "format": "EWCG-v2", "formatVersion": 2, "version": 2,
        "width": int(walkable.shape[1]), "height": int(walkable.shape[0]), "cellMetres": CELL,
        **bounds.metadata(), "serverCells": cells, "originMetres": list(frame.collision_origin),
        "heightEncoding": {k: (list(v) if isinstance(v, (list, tuple)) else float(v))
                           for k, v in result.encoding.items()},
        "gridAlignment": "tile-centres-v1", "authoredSurfaceExport": True,
        "maxTerrainGrade": MAX_GRADE, "maximumWadingDepth": WADE,
        "actorVolume": {"floorClearance": CE.ACTOR_FLOOR_CLEARANCE, "height": CE.ACTOR_HEIGHT,
                        "halfCellWidth": CELL},
        "walkableCells": int(walkable.sum()), "walkableFraction": round(float(walkable.mean()), 6),
        "sha256": collision_sha,
        "exportStatistics": result.statistics,
        "seamCollar": result.collar,
        "sourceSnapshotSha256": t.sources.get("snapshotSha256"),
        "sourceSceneSha256": t.sources.get("sceneSha256"),
        "groupExport": {"maps": group if group is not None else
                        {result.region: {"snapshotSha256": t.sources.get("snapshotSha256"),
                                         "servedGridSha256": served_sha}}},
        "exporter": TOOL,
        "servedGrid": {"binary": SERVED_GRID, "format": "ESCG-v2", "unitMetres": served.unit_mm / 1000,
                       "climbMetres": served.climb_mm / 1000, "originMetres": served.datum_mm / 1000,
                       "width": served.width, "height": served.height, "openTiles": int(result.open_tiles.sum()),
                       "sha256": served_sha},
    }


def ewcg_bytes(grid):
    rows, cols = grid.shape
    return struct.pack("<4sHHII", b"EWCG", 2, 0, cols, rows) + np.ascontiguousarray(grid, np.uint8).tobytes()


def write_outputs(export, analysis, tiles, codec, out, packages, *, partial=False, server=None):
    """Write each map's binaries into <packages>/<region>/client/, then the sidecars, masks and the report to out."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"tool": TOOL, "partial": bool(partial), "server": None if server is None else str(server),
              "codec": {"datumMillimetres": codec.served_grid.DATUM_MM, "unitMillimetres": codec.served_grid.UNIT_MM,
                        "climbMillimetres": codec.served_grid.CLIMB_MM},
              "links": export.links, "skippedLinks": export.skipped_links, "maps": {}}
    written = {}
    binaries = {region: ewcg_bytes(result.grid) for region, result in export.results.items()}
    group = {region: {"snapshotSha256": result.territory.sources.get("snapshotSha256"),
                      "servedGridSha256": hashlib.sha256(result.served_bytes).hexdigest()}
             for region, result in sorted(export.results.items())}
    for region, result in export.results.items():
        package = Path(packages) / region / "client"
        package.mkdir(parents=True, exist_ok=True)
        collision = binaries[region]
        (package / COLLISION_BIN).write_bytes(collision)
        (package / SERVED_GRID).write_bytes(result.served_bytes)
        collision_sha = hashlib.sha256(collision).hexdigest()
        served_sha = hashlib.sha256(result.served_bytes).hexdigest()
        block = collision_block(result, collision_sha, served_sha, codec, group=group)
        sidecar = {"schema": SIDECAR_SCHEMA, "region": region, "partial": bool(partial),
                   "frame": {"origin": list(result.frame.origin), "cells": list(result.frame.cells),
                             "translation": list(result.frame.translation)},
                   "bake": result.territory.sources, "collision": block}
        (out / f"{region}.collision.json").write_text(json_text(sidecar), encoding="utf-8", newline="\n")
        np.savez_compressed(out / f"{region}.tiles.npz", codes=result.codes, own=result.own_tiles,
                            deck=result.deck_tiles, stepFreeOpen=result.step_free_tiles, proxyOpen=result.proxy_tiles,
                            served=tiles.get(region, {}).get("served", np.zeros_like(result.own_tiles)))
        report["maps"][region] = {
            "package": str(package), "collisionSha256": collision_sha, "servedGridSha256": served_sha,
            "collisionBytes": len(collision), "servedGridBytes": len(result.served_bytes),
            "walkableCells": block["walkableCells"], "openTiles": block["servedGrid"]["openTiles"],
            "codeRange": [int(result.codes[result.codes > 0].min()), int(result.codes.max())]
            if (result.codes > 0).any() else None,
            "heightEncoding": block["heightEncoding"], "exportStatistics": result.statistics,
            "seamCollar": result.collar, "crossSeamSolids": result.cross_seam_solids,
            "intraTile": result.intra_tile, "heightFrameResidual": result.residual,
            "bake": result.territory.sources, "walkSources": result.territory.walk_sources,
            "timings": export.timings.get(region, {})}
        written[region] = sidecar
    report.update(analysis)
    (out / "export-report.json").write_text(json_text(report), encoding="utf-8", newline="\n")
    return report, written


def run(territories, links, codec, out, packages, *, partial=False, top_patches=40, log=say, workers=None):
    export = export_group(territories, links, codec, log=log, workers=workers)
    started = time.time()
    analysis, tiles = union_analysis(export, codec, top_patches=top_patches)
    analysis["analysis_s"] = round(time.time() - started, 1)
    return write_outputs(export, analysis, tiles, codec, out, packages, partial=partial, server=codec.server)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", required=True, type=Path, help="the server checkout whose codec and rule are used")
    ap.add_argument("--bake", action="append", required=True, metavar="REGION=DIR",
                    help="a region bake per map (the directory holding continent-authoring.json)")
    ap.add_argument("--out", required=True, type=Path, help="the work directory for sidecars, masks and the report")
    ap.add_argument("--packages", type=Path, default=None,
                    help="the folder holding <region>/client/ (default: eloria-assets/maps/continent-v2 here)")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    ap.add_argument("--partial", action="store_true", help="allow fewer maps than the catalog holds (never publish)")
    ap.add_argument("--top-patches", type=int, default=40)
    ap.add_argument("--workers", type=int, default=None, help="processes for the solids (default: cores, at most 4)")
    a = ap.parse_args(argv)
    started = time.time()
    checkout = a.checkout.resolve()
    if a.partial and (a.packages is None or a.packages.resolve().is_relative_to(checkout)):
        ap.error("--partial writes collar-less binaries: give --packages a folder outside the checkout, so the "
                 "committed packages' collision.bin and served-grid.escg.gz are never overwritten by an experiment")
    bakes = {}
    for item in a.bake:
        region, _, directory = item.partition("=")
        if not directory or region in bakes:
            ap.error(f"--bake {item!r}: give REGION=DIR once per map")
        bakes[region] = Path(directory)
    catalog = frames.regions(checkout)
    unknown = sorted(set(bakes) - set(catalog))
    if unknown:
        ap.error(f"not in the continent-v2 catalog: {unknown}")
    if set(bakes) != set(catalog) and not a.partial:
        ap.error(f"one run exports every map of the catalog ({sorted(catalog)}); missing "
                 f"{sorted(set(catalog) - set(bakes))} (--partial for an experiment)")
    codec = server_codec(a.server)
    plan = plan_document(checkout)
    sea = plan_sea_level(plan)
    territories = [load_bake(region, bakes[region], checkout, sea_level=sea) for region in catalog if region in bakes]
    packages = (a.packages or checkout / PACKAGES).resolve()
    report, _ = run(territories, plan_links(plan), codec, a.out, packages, partial=a.partial,
                    top_patches=a.top_patches, workers=a.workers)
    report["seconds"] = round(time.time() - started, 1)
    (Path(a.out) / "export-report.json").write_text(json_text(report), encoding="utf-8", newline="\n")
    summary = {region: {k: report["maps"][region][k] for k in ("walkableCells", "openTiles", "codeRange")}
               for region in report["maps"]}
    print(json.dumps({"maps": summary, "perMap": report["perMap"], "ac5": report["ac5"],
                      "seconds": report["seconds"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
