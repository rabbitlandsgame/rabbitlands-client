"""Source-owned geometry for roads that cross the open sea.

This module deliberately does not know about river crossing sites or the
river profile implementation.  A coastal claim is identified by stable road
identity and road stations.  It exposes canonical source geometry and the
actual float32 triangles that a later exporter adapter must emit unchanged.

Terrain is never adjusted after a floor has been chosen here.  Callers must
provide the final terrain epoch, prove the full-width joins against it, and
solve any permitted terrain change jointly before building a claim.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Callable, Iterable, Mapping, Sequence

import numpy as np
import shapely
from shapely import LineString, MultiPolygon, Polygon
from shapely.ops import split as shapely_split


MAXIMUM_GRADE = .65
SEA_WET_EPSILON_METRES = .015
DEFAULT_STATION_SPACING_METRES = .5
COMPONENT500_ROAD = "discovery-amethyst_barrens-703"
COMPONENT501_ROAD = "manymouth_delta--westhaven-manymouth_delta"
COMPONENT502_ROAD = "discovery-manymouth_delta-1003"
COMPONENT500_ROAD_SHA256 = "5b4478f59875624ebfcaa9c033d131e160dcb8daf41bcd2c9c239c002cc53970"
COMPONENT501_ROAD_SHA256 = "a968a34863f4bf36cf13e941a99f4b0b38e058a29f12d4f3d034d331beda503d"
COMPONENT501_FIRST_MOVABLE = 242
COMPONENT501_LAST_MOVABLE = 247
COMPONENT501_PEAK_STATION_METRES = 421.7444824628268
COMPONENT501_INLAND_DIRECTION_XZ = (0.3173053461807273, -0.9483234244102213)
COMPONENT501_SOURCE_XZ_SHA256 = "6c0c723091b5621f48cc78fe656f18581e8b9829a48be3780cb9ff33e67dbce0"
COMPONENT501_CANDIDATE_XZ_SHA256 = "2db8da5b77e89767aec853db2f89b4b9c75d5c48fd0ab987cd205ba2bc28b216"
COMPONENT501_CANDIDATE_SHIFT_METRES = .22

# Stable road identity is the production key.  Numeric component labels are
# retained only to account for every current loose-wet inventory member.
COASTAL_COMPONENT_ROADS = {
    500: ("discovery-amethyst_barrens-703",),
    501: ("manymouth_delta--westhaven-manymouth_delta",),
    502: ("discovery-manymouth_delta-1003",),
    503: ("door-westhaven-gullstone-door", "discovery-westhaven-832"),
    504: ("door-westhaven-lamp-rock-door",),
    505: ("discovery-westhaven-832",),
    506: ("crownwater--westhaven-westhaven", "discovery-westhaven-836"),
    507: ("discovery-crownwater-908", "discovery-crownwater-911"),
    508: ("door-crownwater-eleventh-bell-door",),
    509: ("door-ssarathi_ruins-hatchery-descent", "discovery-ssarathi_ruins-437"),
    510: ("door-crownwater-cistern-stair",),
    511: ("discovery-crownwater-907",),
    512: ("door-ssarathi_ruins-cistern-shaft",),
    513: ("door-crownwater-cistern-stair",),
    514: ("door-crownwater-basilica-undercroft", "door-crownwater-case-room-door",
          "door-crownwater-eleventh-bell-door"),
    515: ("door-crownwater-campanile-door",),
    516: ("door-ssarathi_ruins-hatchery-descent",),
    517: ("crownwater--manymouth_delta-crownwater",),
    518: ("discovery-crownwater-907",),
    519: ("door-crownwater-grating-mouth",),
    520: ("door-ssarathi_ruins-archive-vault-door", "discovery-ssarathi_ruins-436",
          "door-ssarathi_ruins-undercroft-mouth", "discovery-ssarathi_ruins-438"),
}
COASTAL_SEMANTIC_GROUPS = tuple((value,) for value in range(500, 510)) + (
    (510, 513), (511,), (512,), (514,), (515,), (516,), (517,), (518,), (519,), (520,))

if tuple(shapely.geos_version) < (3, 10, 0) or not hasattr(shapely, "constrained_delaunay_triangles"):
    raise RuntimeError("coastal road unions require Shapely 2.1 with GEOS 3.10 or newer")


class CoastalGeometryError(ValueError):
    """A rejected source candidate, with a compact machine-readable witness."""

    def __init__(self, message: str, **witness):
        super().__init__(message)
        self.witness = {"message": message, **witness}


def _array(value, shape_tail, name):
    result = np.asarray(value, dtype=np.float64)
    if result.ndim < 1 or (shape_tail and result.shape[-len(shape_tail):] != tuple(shape_tail)):
        raise CoastalGeometryError(f"{name} has the wrong shape", shape=list(result.shape))
    if not np.isfinite(result).all():
        raise CoastalGeometryError(f"{name} contains a non-finite value")
    return result


def canonical_road_record(road: Mapping) -> dict:
    """Normalize the stable semantic road fields across JSON and composed objects."""
    try:
        identity = str(road["id"]); width = float(road["width"])
        points = _array(road["points"], (3,), "road points")
    except (KeyError, TypeError, ValueError) as error:
        raise CoastalGeometryError("road record lacks canonical id/width/points") from error
    return {"id": identity, "width": width, "points": points.tolist()}


def road_record_sha256(road: Mapping) -> str:
    payload = json.dumps(canonical_road_record(road), sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_road(roads: Sequence[Mapping], road_id: str, expected_sha256: str | None = None) -> Mapping:
    matches = [road for road in roads if road.get("id") == road_id]
    if len(matches) != 1:
        raise CoastalGeometryError("coastal road identity is not unique", roadId=road_id, matches=len(matches))
    road = matches[0]
    if expected_sha256 is not None:
        actual = road_record_sha256(road)
        if actual != expected_sha256:
            raise CoastalGeometryError("coastal road source changed", roadId=road_id,
                                       expectedSha256=expected_sha256, actualSha256=actual)
    return road


def require_matching_road_authorities(published_roads: Sequence[Mapping], composed_roads: Sequence[Mapping],
                                      road_id: str, expected_sha256: str) -> Mapping:
    published = require_road(published_roads, road_id, expected_sha256)
    composed = require_road(composed_roads, road_id, expected_sha256)
    if canonical_road_record(published) != canonical_road_record(composed):
        raise CoastalGeometryError("published and composed coastal road authorities disagree", roadId=road_id)
    return composed


def coastal_registry_roads(roads: Sequence[Mapping]) -> dict[int, tuple[Mapping, ...]]:
    """Resolve the complete current coastal registry by stable road identity."""
    by_id = {str(road.get("id")): road for road in roads}
    if len(by_id) != len(roads):
        raise CoastalGeometryError("road inventory contains duplicate stable ids")
    resolved = {}
    for component, identities in COASTAL_COMPONENT_ROADS.items():
        missing = [identity for identity in identities if identity not in by_id]
        if missing:
            raise CoastalGeometryError("coastal registry road is absent",
                                       componentSeed=component, missingRoadIds=missing)
        resolved[component] = tuple(by_id[identity] for identity in identities)
    labels = sorted(value for group in COASTAL_SEMANTIC_GROUPS for value in group)
    if labels != list(range(500, 521)):
        raise CoastalGeometryError("coastal semantic groups do not cover the 21-component inventory")
    return resolved


def coastal_bank_fit_request(claim_id: str, road: Mapping, left_station: float, right_station: float,
                             left_approach, right_approach, pinned_vertex_indices,
                             source_height_sha256: str, *, join_sections=None,
                             maximum_grade: float = MAXIMUM_GRADE) -> dict:
    """Build the exact two-bank request consumed by coastal_bank_fit."""
    canonical = canonical_road_record(road)
    points = np.asarray(canonical["points"], dtype=np.float64)
    distances = cumulative_stations(points)
    left_station, right_station = float(left_station), float(right_station)
    if not distances[0] <= left_station < right_station <= distances[-1]:
        raise CoastalGeometryError("coastal bank stations are outside the continuing road")
    approaches = [tuple(map(float, left_approach)), tuple(map(float, right_approach))]
    if not approaches[0][0] < approaches[0][1] <= left_station or \
       not right_station <= approaches[1][0] < approaches[1][1]:
        raise CoastalGeometryError("coastal bank approaches do not face away from the span",
                                   leftApproach=list(approaches[0]), rightApproach=list(approaches[1]))
    if join_sections is None:
        sections = np.stack([
            _section(points, distances, station, canonical["width"]).astype(np.float32).astype(np.float64)
            for station in (left_station, right_station)])
    else:
        sections = _array(join_sections, (2, 3), "actual encoded coastal join sections")
        if sections.shape != (2, 2, 3) or not np.array_equal(
                sections, sections.astype(np.float32).astype(np.float64)):
            raise CoastalGeometryError("coastal bank joins are not two actual float32 sections")
        widths = np.linalg.norm(np.diff(sections[:, :, [0, 2]], axis=1)[:, 0], axis=1)
        if (widths < 2. * canonical["width"]).any():
            raise CoastalGeometryError("actual coastal bank join lost full road width",
                                       encodedWidthsMetres=widths,
                                       requiredWidthMetres=2. * canonical["width"])
    pins = sorted({tuple(map(int, value)) for value in pinned_vertex_indices})
    return {"claimId": str(claim_id), "roadId": canonical["id"], "roadPoints": points,
            "halfWidthMetres": canonical["width"],
            "left": {"joinSection": sections[0], "joinStationMetres": left_station,
                     "approachStationRangeMetres": approaches[0]},
            "right": {"joinSection": sections[1], "joinStationMetres": right_station,
                      "approachStationRangeMetres": approaches[1]},
            "cutLimitMetres": 4., "fillLimitMetres": 3.,
            "maximumApproachGrade": float(maximum_grade),
            "pinnedVertexIndices": pins, "sourceHeightSha256": str(source_height_sha256)}


def cumulative_stations(points: np.ndarray) -> np.ndarray:
    points = _array(points, (3,), "road points")
    if len(points) < 2:
        raise CoastalGeometryError("a coastal road needs at least two points")
    runs = np.linalg.norm(np.diff(points[:, [0, 2]], axis=0), axis=1)
    if (runs <= 0).any():
        raise CoastalGeometryError("a coastal road contains a zero-length XZ segment",
                                   segment=int(np.flatnonzero(runs <= 0)[0]))
    return np.r_[0., np.cumsum(runs)]


def _point_at(points: np.ndarray, stations: np.ndarray, station: float) -> tuple[np.ndarray, int, float]:
    value = float(station)
    if value < stations[0] or value > stations[-1]:
        raise CoastalGeometryError("station lies outside its road", stationMetres=value,
                                   roadStationsMetres=[float(stations[0]), float(stations[-1])])
    index = min(int(np.searchsorted(stations, value, side="right") - 1), len(stations) - 2)
    ratio = (value - stations[index]) / (stations[index + 1] - stations[index])
    return points[index] + ratio * (points[index + 1] - points[index]), index, float(ratio)


def _unit(value, name):
    value = np.asarray(value, dtype=np.float64)
    length = float(np.linalg.norm(value))
    if not math.isfinite(length) or length <= 0:
        raise CoastalGeometryError(f"{name} has no direction")
    return value / length


def _section(points: np.ndarray, stations: np.ndarray, station: float, half_width: float) -> np.ndarray:
    centre, index, ratio = _point_at(points, stations, station)
    directions = np.diff(points[:, [0, 2]], axis=0)
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    tangent = directions[index]
    miter_scale = 1.
    # At an authored bend use the intersection of the adjacent offset lines.
    at_vertex = None
    if ratio == 0. and index > 0:
        at_vertex = index
    elif ratio == 1. and index + 1 < len(points) - 1:
        at_vertex = index + 1
    if at_vertex is not None:
        before, after = directions[at_vertex - 1], directions[at_vertex]
        tangent = _unit(before + after, "road-bend tangent")
        normal_before = np.array([-before[1], before[0]])
        normal = np.array([-tangent[1], tangent[0]])
        denominator = float(np.dot(normal, normal_before))
        if denominator <= 0:
            raise CoastalGeometryError("road bend reverses its full-width section", stationMetres=float(station))
        miter_scale = 1. / denominator
        if miter_scale > 4.:
            raise CoastalGeometryError("road bend requires an unbounded miter", stationMetres=float(station),
                                       miterScale=miter_scale)
    normal = np.array([-tangent[1], tangent[0]])
    offset = normal * float(half_width) * miter_scale
    left, right = centre[[0, 2]] + offset, centre[[0, 2]] - offset
    return np.array([[left[0], centre[1], left[1]], [right[0], centre[1], right[1]]])


def canonical_stations(points: np.ndarray, start: float, end: float,
                       maximum_spacing: float = DEFAULT_STATION_SPACING_METRES) -> np.ndarray:
    source = cumulative_stations(points)
    start, end, maximum_spacing = float(start), float(end), float(maximum_spacing)
    if not source[0] <= start < end <= source[-1]:
        raise CoastalGeometryError("coastal band has invalid station bounds", startMetres=start, endMetres=end)
    if not math.isfinite(maximum_spacing) or maximum_spacing <= 0:
        raise CoastalGeometryError("canonical station spacing must be positive")
    anchors = np.r_[start, source[(source > start) & (source < end)], end]
    result = []
    for left, right in zip(anchors, anchors[1:]):
        count = max(1, int(math.ceil((right - left) / maximum_spacing)))
        result.extend(np.linspace(left, right, count + 1)[:-1])
    return np.r_[result, end]


@dataclass(frozen=True)
class SmoothArchProfile:
    """A continuous two-sided arch with flat derivatives at joins and crown."""

    start_station: float
    crown_station: float
    end_station: float
    start_height: float
    crown_height: float
    end_height: float
    maximum_grade: float = MAXIMUM_GRADE

    def __post_init__(self):
        values = (self.start_station, self.crown_station, self.end_station,
                  self.start_height, self.crown_height, self.end_height, self.maximum_grade)
        if not all(math.isfinite(float(value)) for value in values):
            raise CoastalGeometryError("arch profile contains a non-finite value")
        if not self.start_station < self.crown_station < self.end_station:
            raise CoastalGeometryError("arch crown is outside its joins")
        if self.crown_height < max(self.start_height, self.end_height):
            raise CoastalGeometryError("arch crown lies below a join")
        grades = (1.5 * abs(self.crown_height - self.start_height) /
                  (self.crown_station - self.start_station),
                  1.5 * abs(self.crown_height - self.end_height) /
                  (self.end_station - self.crown_station))
        if max(grades) > self.maximum_grade:
            raise CoastalGeometryError("arch profile exceeds its longitudinal grade",
                                       maximumGrade=max(grades), limit=self.maximum_grade)

    @staticmethod
    def _smooth(t):
        return t * t * (3. - 2. * t)

    def height(self, stations):
        s = np.asarray(stations, dtype=np.float64)
        if ((s < self.start_station) | (s > self.end_station)).any():
            raise CoastalGeometryError("profile query lies outside the named span")
        left = s <= self.crown_station
        result = np.empty(s.shape, dtype=np.float64)
        t = (s[left] - self.start_station) / (self.crown_station - self.start_station)
        result[left] = self.start_height + (self.crown_height - self.start_height) * self._smooth(t)
        t = (s[~left] - self.crown_station) / (self.end_station - self.crown_station)
        result[~left] = self.crown_height + (self.end_height - self.crown_height) * self._smooth(t)
        return result


@dataclass(frozen=True)
class SurfaceGeometry:
    name: str
    kind: str
    road_id: str
    stations: np.ndarray
    sections: np.ndarray
    triangles: np.ndarray
    triangle_stations: np.ndarray
    join_edges: tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]] = ((), ())

    def __post_init__(self):
        stations = _array(self.stations, (), "surface stations").reshape(-1)
        sections = _array(self.sections, (2, 3), "surface sections")
        triangles = _array(self.triangles, (3, 3), "surface triangles")
        triangle_stations = _array(self.triangle_stations, (3,), "surface triangle stations")
        if len(sections) != len(stations) or len(triangles) != len(triangle_stations):
            raise CoastalGeometryError("surface geometry arrays disagree")
        if len(self.join_edges) != 2:
            raise CoastalGeometryError("surface join-edge authority must have two sides")
        join_edges = tuple(tuple(_array(edge, (3,), "surface join edge")
                                 for edge in side) for side in self.join_edges)
        object.__setattr__(self, "stations", stations)
        object.__setattr__(self, "sections", sections)
        object.__setattr__(self, "triangles", triangles)
        object.__setattr__(self, "triangle_stations", triangle_stations)
        object.__setattr__(self, "join_edges", join_edges)

    @property
    def encoded_triangles(self) -> np.ndarray:
        return self.triangles.astype(np.float32).astype(np.float64)

    @property
    def start_section(self) -> np.ndarray:
        return self.sections[0].copy()

    @property
    def end_section(self) -> np.ndarray:
        return self.sections[-1].copy()

    def geometry(self, encoded: bool = True) -> dict:
        faces = self.encoded_triangles if encoded else self.triangles
        return {"name": self.name, "kind": self.kind, "roadId": self.road_id,
                "stationsMetres": self.stations.copy(), "sections": self.sections.copy(),
                "triangles": faces.copy(), "triangleStations": self.triangle_stations.copy(),
                "joinEdges": [[edge.copy() for edge in side] for side in self.join_edges]}


@dataclass(frozen=True)
class EncodedRoadUnion:
    """One globally encoded vertex/index authority for a bounded RoadOutline union."""

    vertices_xz: np.ndarray
    triangle_indices: np.ndarray
    component_count: int
    hole_count: int

    def __post_init__(self):
        vertices = _array(self.vertices_xz, (2,), "road-union vertices")
        indices = np.asarray(self.triangle_indices, dtype=np.int64)
        if indices.ndim != 2 or indices.shape[1:] != (3,) or not len(indices):
            raise CoastalGeometryError("road union has no indexed triangles")
        if (indices < 0).any() or (indices >= len(vertices)).any():
            raise CoastalGeometryError("road union contains an invalid vertex index")
        if not np.array_equal(vertices, vertices.astype(np.float32).astype(np.float64)):
            raise CoastalGeometryError("road union vertices are not one float32 authority")
        faces = vertices[indices]
        areas = np.asarray([_signed_area_xz(face) for face in faces])
        if (areas >= 0.).any():
            raise CoastalGeometryError("road union contains a folded or non-upward encoded face",
                                       faces=np.flatnonzero(areas >= 0.))
        object.__setattr__(self, "vertices_xz", vertices)
        object.__setattr__(self, "triangle_indices", indices)

    @property
    def triangles_xz(self):
        return self.vertices_xz[self.triangle_indices]


def _upward_triangles(quads: Iterable[np.ndarray]) -> np.ndarray:
    triangles = []
    for quad in quads:
        quad = np.asarray(quad, dtype=np.float64)
        choices = ((0, 2, 1, 1, 2, 3), (0, 1, 2, 1, 3, 2))
        for choice in choices:
            pair = quad[np.asarray(choice)].reshape(2, 3, 3)
            normals = np.cross(pair[:, 1] - pair[:, 0], pair[:, 2] - pair[:, 0])
            if (normals[:, 1] > 0).all():
                triangles.extend(pair)
                break
        else:
            raise CoastalGeometryError("road-following surface has a folded or degenerate slab")
    return np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)


def _upward_pair(quad):
    quad = np.asarray(quad, dtype=np.float64)
    for choice in ((0, 2, 1, 1, 2, 3), (0, 1, 2, 1, 3, 2)):
        pair = quad[np.asarray(choice)].reshape(2, 3, 3)
        normals = np.cross(pair[:, 1] - pair[:, 0], pair[:, 2] - pair[:, 0])
        if (normals[:, 1] > 0).all():
            return pair, np.asarray(choice).reshape(2, 3)
    raise CoastalGeometryError("road-following surface has a folded or degenerate slab")


def _check_encoded_grade(triangles: np.ndarray, maximum_grade: float):
    encoded = np.asarray(triangles, dtype=np.float32).astype(np.float64)
    normals = np.cross(encoded[:, 1] - encoded[:, 0], encoded[:, 2] - encoded[:, 0])
    grade = np.hypot(normals[:, 0], normals[:, 2]) / np.maximum(normals[:, 1], np.finfo(float).tiny)
    invalid = (normals[:, 1] <= 0) | (grade > maximum_grade)
    if invalid.any():
        index = int(np.flatnonzero(invalid)[0])
        raise CoastalGeometryError("encoded coastal floor exceeds its grade",
                                   triangle=index, grade=float(grade[index]), limit=float(maximum_grade))


def road_surface(name: str, kind: str, road_id: str, points, half_width: float,
                 start_station: float, end_station: float, profile,
                 maximum_spacing: float = DEFAULT_STATION_SPACING_METRES,
                 maximum_grade: float = MAXIMUM_GRADE) -> SurfaceGeometry:
    points = _array(points, (3,), "road points")
    if not math.isfinite(float(half_width)) or half_width <= 0:
        raise CoastalGeometryError("road half-width must be positive")
    distances = cumulative_stations(points)
    stations = canonical_stations(points, start_station, end_station, maximum_spacing)
    sections = np.stack([_section(points, distances, station, half_width) for station in stations])
    heights = np.asarray(profile.height(stations), dtype=np.float64)
    sections[:, :, 1] = heights[:, None]
    triangles, triangle_stations = [], []
    for i in range(len(sections) - 1):
        quad = np.array([sections[i, 0], sections[i, 1], sections[i + 1, 0], sections[i + 1, 1]])
        pair, choice = _upward_pair(quad)
        triangles.extend(pair)
        triangle_stations.extend(np.array([stations[i], stations[i], stations[i + 1], stations[i + 1]])[choice])
    triangles = np.asarray(triangles, dtype=np.float64)
    triangle_stations = np.asarray(triangle_stations, dtype=np.float64)
    _check_encoded_grade(triangles, maximum_grade)
    return SurfaceGeometry(name, kind, road_id, stations, sections, triangles, triangle_stations)


@dataclass(frozen=True)
class TerrainPatch:
    x: np.ndarray
    z: np.ndarray
    height: np.ndarray
    solid: np.ndarray | None = None

    def __post_init__(self):
        x = _array(self.x, (), "terrain X").reshape(-1)
        z = _array(self.z, (), "terrain Z").reshape(-1)
        # Terrain GLB positions are float32.  Every support/join query uses the
        # same emitted height authority rather than pre-encoding world values.
        height = _array(self.height, (), "terrain height").astype(np.float32).astype(np.float64)
        if height.shape != (len(z), len(x)) or len(x) < 2 or len(z) < 2:
            raise CoastalGeometryError("terrain patch arrays disagree")
        if not np.allclose(np.diff(x), np.diff(x)[0], rtol=0, atol=0) or \
           not np.allclose(np.diff(z), np.diff(z)[0], rtol=0, atol=0) or \
           float(np.diff(x)[0]) != float(np.diff(z)[0]):
            raise CoastalGeometryError("terrain patch is not one exact square grid")
        solid = None if self.solid is None else np.asarray(self.solid, dtype=bool)
        if solid is not None and solid.shape != height.shape:
            raise CoastalGeometryError("terrain solid mask has the wrong shape")
        object.__setattr__(self, "x", x); object.__setattr__(self, "z", z)
        object.__setattr__(self, "height", height); object.__setattr__(self, "solid", solid)

    @property
    def cell(self):
        return float(self.x[1] - self.x[0])

    def height_at(self, points_xz):
        points = _array(points_xz, (2,), "terrain query")
        fx = (points[..., 0] - self.x[0]) / self.cell
        fz = (points[..., 1] - self.z[0]) / self.cell
        ix = np.floor(fx).astype(int); iz = np.floor(fz).astype(int)
        if ((ix < 0) | (iz < 0) | (ix >= len(self.x) - 1) | (iz >= len(self.z) - 1)).any():
            raise CoastalGeometryError("terrain query left its cropped authority")
        u, v = fx - ix, fz - iz
        a = self.height[iz, ix]; b = self.height[iz, ix + 1]
        c = self.height[iz + 1, ix]; d = self.height[iz + 1, ix + 1]
        return np.where(u + v <= 1., a + u * (b - a) + v * (c - a),
                        d + (1. - v) * (b - d) + (1. - u) * (c - d))

    def triangles(self):
        result = []
        for row in range(len(self.z) - 1):
            for col in range(len(self.x) - 1):
                a = [self.x[col], self.height[row, col], self.z[row]]
                b = [self.x[col + 1], self.height[row, col + 1], self.z[row]]
                c = [self.x[col], self.height[row + 1, col], self.z[row + 1]]
                d = [self.x[col + 1], self.height[row + 1, col + 1], self.z[row + 1]]
                result.extend((np.array([a, c, b]), np.array([b, c, d])))
        return np.asarray(result, dtype=np.float64)


def crop_terrain(world, bounds_xz, padding_metres: float = 0.) -> TerrainPatch:
    """Crop once around the union of all route-evidence search intervals."""
    bounds = np.asarray(bounds_xz, dtype=np.float64)
    if bounds.shape != (4,) or not np.isfinite(bounds).all():
        raise CoastalGeometryError("terrain crop bounds are invalid")
    x, z = np.asarray(world.x), np.asarray(world.z)
    low = bounds[[0, 1]] - float(padding_metres); high = bounds[[2, 3]] + float(padding_metres)
    ix0 = max(0, int(np.searchsorted(x, low[0], side="right") - 1)); ix1 = min(len(x), int(np.searchsorted(x, high[0], side="left") + 1))
    iz0 = max(0, int(np.searchsorted(z, low[1], side="right") - 1)); iz1 = min(len(z), int(np.searchsorted(z, high[1], side="left") + 1))
    if ix1 - ix0 < 2 or iz1 - iz0 < 2:
        raise CoastalGeometryError("terrain crop contains no complete cell")
    solid = getattr(world, "solids", None)
    solid = None if solid is None else np.asarray(solid)[iz0:iz1, ix0:ix1]
    return TerrainPatch(x[ix0:ix1], z[iz0:iz1], np.asarray(world.height)[iz0:iz1, ix0:ix1], solid)


def _signed_area_xz(polygon):
    polygon = np.asarray(polygon, dtype=np.float64)
    # Continent coordinates are large enough for an unshifted shoelace sum to
    # erase real sub-square-metre pieces.  Every positive piece is evidence.
    shifted = polygon[:, :2] - polygon[0, :2]
    x, z = shifted[:, 0], shifted[:, 1]
    return .5 * float(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1)))


def _area_xz(polygon):
    return abs(_signed_area_xz(polygon))


def _clip_halfplane_xz(polygon, point, direction):
    """Keep the left side of an oriented XZ line, preserving extra columns."""
    polygon = np.asarray(polygon, dtype=np.float64)
    point = np.asarray(point, dtype=np.float64); direction = np.asarray(direction, dtype=np.float64)
    values = direction[0] * (polygon[:, 1] - point[1]) - direction[1] * (polygon[:, 0] - point[0])
    output = []
    for index in range(len(polygon)):
        previous = (index - 1) % len(polygon)
        inside, previous_inside = values[index] >= 0., values[previous] >= 0.
        if inside != previous_inside:
            ratio = values[previous] / (values[previous] - values[index])
            output.append(polygon[previous] + ratio * (polygon[index] - polygon[previous]))
        if inside:
            output.append(polygon[index])
    return np.asarray(output, dtype=np.float64).reshape(-1, polygon.shape[1])


def _subtract_convex(subject, clip):
    """Return the positive pieces of subject outside one convex polygon."""
    inside = np.asarray(subject, dtype=np.float64)
    clip = np.asarray(clip, dtype=np.float64)
    orientation = np.sign(_signed_area_xz(clip))
    if orientation == 0:
        return [inside]
    outside = []
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        edge = b - a
        if np.array_equal(edge, np.zeros_like(edge)):
            continue
        direction = orientation * edge
        rejected = _clip_halfplane_xz(inside, a, -direction)
        if len(rejected) >= 3 and _area_xz(rejected) > 0:
            outside.append(rejected)
        inside = _clip_halfplane_xz(inside, a, direction)
        if len(inside) < 3 or _area_xz(inside) == 0:
            break
    return outside


def _normalize_polygon_xz(polygon):
    polygon = np.asarray(polygon, dtype=np.float64)
    if len(polygon) < 3:
        return polygon
    distinct = np.any(polygon != np.roll(polygon, 1, axis=0), axis=1)
    polygon = polygon[distinct]
    changed = True
    while changed and len(polygon) > 3:
        changed = False
        for index in range(len(polygon)):
            a, b, c = polygon[index - 1], polygon[index], polygon[(index + 1) % len(polygon)]
            ab, bc = b - a, c - b
            if ab[0] * bc[1] - ab[1] * bc[0] == 0 and np.dot(ab, bc) >= 0:
                polygon = np.delete(polygon, index, axis=0)
                changed = True
                break
    return polygon


def _encoded_ring(ring, name):
    points = np.asarray(ring.coords, dtype=np.float64)
    if len(points) and np.array_equal(points[0], points[-1]):
        points = points[:-1]
    points = _normalize_polygon_xz(points.astype(np.float32).astype(np.float64))
    if len(points) < 3 or _area_xz(points) == 0.:
        raise CoastalGeometryError(f"encoded {name} collapsed")
    return points


def _encode_polygonal_geometry(geometry):
    def polygon_parts(value):
        if isinstance(value, Polygon):
            yield value
        elif value.geom_type in ("MultiPolygon", "GeometryCollection"):
            for item in shapely.get_parts(value):
                yield from polygon_parts(item)

    def encode(value):
        parts = []
        for number, polygon in enumerate(polygon_parts(value)):
            exterior = _encoded_ring(polygon.exterior, "RoadOutline exterior")
            holes = [_encoded_ring(ring, "RoadOutline hole") for ring in polygon.interiors]
            candidate = Polygon(exterior, holes)
            if candidate.area > 0.:
                parts.append(candidate)
        if not parts:
            raise CoastalGeometryError("RoadOutline union is empty")
        return parts[0] if len(parts) == 1 else MultiPolygon(parts)

    encoded = encode(geometry)
    reasons = []
    for _ in range(4):
        if encoded.is_valid:
            return encoded
        reasons.append(shapely.is_valid_reason(encoded))
        # Float32 can collapse two nearby union-boundary vertices into a
        # crossing.  GEOS splits that exact encoded linework; the independent
        # nominal/emitted guard gate below still rejects any physical loss or
        # excursion, so this is topology repair rather than hull filling.
        repaired = shapely.make_valid(encoded)
        polygons = list(polygon_parts(repaired))
        if not polygons:
            break
        encoded = encode(shapely.union_all(polygons))
    if not encoded.is_valid:
        raise CoastalGeometryError("RoadOutline union remained invalid after exact encoded topology repair",
                                   reasons=reasons, finalReason=shapely.is_valid_reason(encoded))
    return encoded


def _source_road_outline_union_geometry(outline_records):
    polygons = []
    for number, record in enumerate(outline_records):
        try:
            xz = _array(record["xz"], (2,), "RoadOutline piece XZ")
        except (KeyError, TypeError) as error:
            raise CoastalGeometryError("RoadOutline record lacks XZ authority", record=number) from error
        xz = _normalize_polygon_xz(xz)
        if len(xz) < 3 or _area_xz(xz) == 0.:
            raise CoastalGeometryError("RoadOutline record is not one positive polygon", record=number)
        polygon = Polygon(xz)
        if not polygon.is_valid:
            raise CoastalGeometryError("RoadOutline record is invalid", record=number,
                                       reason=shapely.is_valid_reason(polygon))
        polygons.append(polygon)
    if not polygons:
        raise CoastalGeometryError("independent RoadOutline union is empty")
    geometry = shapely.union_all(polygons)
    if geometry.is_empty or not geometry.is_valid:
        raise CoastalGeometryError("GEOS could not form the RoadOutline union",
                                   reason=shapely.is_valid_reason(geometry))
    return geometry


def _road_outline_union_geometry(outline_records, source_guard_metres=0.):
    geometry = _source_road_outline_union_geometry(outline_records)
    guard = float(source_guard_metres)
    if not np.isfinite(guard) or guard < 0.:
        raise CoastalGeometryError("RoadOutline source guard is invalid")
    if guard:
        geometry = geometry.buffer(guard)
    return _encode_polygonal_geometry(geometry)


def road_outline_encoding_guard(outline_records) -> float:
    """Maximum XZ float32 displacement unit derived from this RoadOutline."""
    points = np.concatenate([_array(record["xz"], (2,), "RoadOutline piece XZ")
                             for record in outline_records])
    ulp = np.abs(np.spacing(points.astype(np.float32))).astype(np.float64)
    f32_guard = float(np.max(np.linalg.norm(ulp, axis=1), initial=0.))
    precision_grid = float(np.max(ulp, initial=0.))
    # One derived snap allowance expands the source RoadOutline; the second
    # covers the final common-grid overlay before float32 emission.
    guard = f32_guard + math.sqrt(2.) * precision_grid
    if not np.isfinite(guard) or guard <= 0.:
        raise CoastalGeometryError("RoadOutline has no finite positive float32 encoding guard")
    return guard


def encoded_road_outline_union(outline_records, source_guard_metres=0.) -> EncodedRoadUnion:
    """Union bounded existing RoadOutline polygons and triangulate that exact encoded set."""
    geometry = _road_outline_union_geometry(outline_records, source_guard_metres)
    parts = list(shapely.get_parts(geometry))
    triangulated = shapely.constrained_delaunay_triangles(geometry)
    triangles = []
    for number, triangle in enumerate(shapely.get_parts(triangulated)):
        if not isinstance(triangle, Polygon) or len(triangle.interiors):
            raise CoastalGeometryError("constrained road-union triangulation emitted a non-triangle",
                                       part=number, geometryType=triangle.geom_type)
        xz = _encoded_ring(triangle.exterior, "road-union triangle")
        if len(xz) != 3:
            raise CoastalGeometryError("constrained road-union triangulation emitted a non-triangle",
                                       part=number, vertices=len(xz))
        candidate = Polygon(xz)
        if not geometry.covers(candidate):
            raise CoastalGeometryError("constrained triangle escaped the encoded RoadOutline union", part=number)
        if _signed_area_xz(xz) > 0.:
            xz = xz[::-1].copy()
        triangles.append(xz)
    if not triangles:
        raise CoastalGeometryError("constrained RoadOutline triangulation is empty")
    triangle_array = np.asarray(triangles, dtype=np.float64)
    vertices, inverse = np.unique(triangle_array.reshape(-1, 2).astype(np.float32), axis=0,
                                  return_inverse=True)
    vertices = vertices.astype(np.float64); indices = inverse.reshape(-1, 3)
    emitted = shapely.union_all([Polygon(face) for face in vertices[indices]])
    if not emitted.equals(geometry):
        raise CoastalGeometryError("constrained triangles do not equal the encoded RoadOutline union",
                                   extraAreaSquareMetres=float(emitted.difference(geometry).area),
                                   uncoveredAreaSquareMetres=float(geometry.difference(emitted).area))
    return EncodedRoadUnion(vertices, indices, len(parts),
                            sum(len(polygon.interiors) for polygon in parts))


def constrained_polygon_indices(vertices_xz):
    """Triangulate one simple float32 polygon using only its shared input vertices."""
    vertices = _array(vertices_xz, (2,), "encoded polygon vertices")
    if not np.array_equal(vertices, vertices.astype(np.float32).astype(np.float64)):
        raise CoastalGeometryError("polygon vertices are not float32 authority")
    polygon = Polygon(vertices)
    if not polygon.is_valid or polygon.area == 0.:
        raise CoastalGeometryError("encoded profile-zone polygon is invalid",
                                   reason=shapely.is_valid_reason(polygon))
    lookup = {tuple(point): index for index, point in enumerate(vertices)}
    result = []
    for triangle in shapely.get_parts(shapely.constrained_delaunay_triangles(polygon)):
        xz = _encoded_ring(triangle.exterior, "profile-zone triangle")
        try:
            face = [lookup[tuple(point)] for point in xz]
        except KeyError as error:
            raise CoastalGeometryError("constrained profile triangulation invented a vertex") from error
        if _signed_area_xz(vertices[face]) > 0.:
            face.reverse()
        result.append(face)
    if not result:
        raise CoastalGeometryError("encoded profile-zone triangulation is empty")
    return np.asarray(result, dtype=np.int64)



def _clip_stationed(polygon, values, boundary_station=None):
    output = []
    for index in range(len(polygon)):
        previous = (index - 1) % len(polygon)
        inside, previous_inside = values[index] >= 0., values[previous] >= 0.
        if inside != previous_inside:
            ratio = values[previous] / (values[previous] - values[index])
            point = polygon[previous] + ratio * (polygon[index] - polygon[previous])
            if boundary_station is not None: point[-1] = float(boundary_station)
            output.append(point)
        if inside:
            point = polygon[index].copy()
            if boundary_station is not None and values[index] == 0.:
                point[-1] = float(boundary_station)
            output.append(point)
    return np.asarray(output, float).reshape(-1, polygon.shape[1])


def road_outline_records(points, half_width, start_station, end_station, outline_factory,
                         cap_guard_metres=0., terminal_sides=()):
    points = np.asarray(points, float); source = cumulative_stations(points)
    cap_guard_metres = float(cap_guard_metres)
    if not np.isfinite(cap_guard_metres) or cap_guard_metres < 0.:
        raise CoastalGeometryError("RoadOutline cap guard is invalid")
    terminal_sides = frozenset(map(str, terminal_sides))
    if not terminal_sides <= {"left", "right"}:
        raise CoastalGeometryError("RoadOutline terminal side is invalid",
                                   terminalSides=sorted(terminal_sides))
    start_point, start_index, _ = _point_at(points, source, start_station)
    end_point, end_index, _ = _point_at(points, source, end_station)
    interior_indices = np.arange(start_index + 1, end_index + 1)
    keep = (source[interior_indices] > start_station) & (source[interior_indices] < end_station)
    interior_indices = interior_indices[keep]
    route = np.concatenate(([start_point], points[interior_indices], [end_point]))
    semantic = np.r_[start_station, source[interior_indices], end_station]
    encoded = route.copy(); encoded[:, [0, 2]] = encoded[:, [0, 2]].astype(np.float32)
    outline = outline_factory([{"points": encoded, "width": float(half_width)}])
    segments = list(zip(encoded[:, [0, 2]], encoded[1:, [0, 2]])); records = []
    start_direction = (segments[0][1] - segments[0][0]); start_direction /= np.linalg.norm(start_direction)
    end_direction = (segments[-1][1] - segments[-1][0]); end_direction /= np.linalg.norm(end_direction)
    for row, polygon in zip(outline.segments, outline.polygons):
        ends = np.asarray([[row[0], row[1]], [row[2], row[3]]])
        owner = next((index for index, (a, b) in enumerate(segments)
                      if (np.array_equal(ends[0], a) and np.array_equal(ends[1], b)) or
                         (np.array_equal(ends[0], b) and np.array_equal(ends[1], a))), None)
        if owner is None: raise CoastalGeometryError("RoadOutline segment lost its source-road owner", segmentXZ=ends)
        a, b = segments[owner]; delta = b - a; length_squared = float(delta @ delta)
        polygon = np.asarray(polygon, float)
        ratio = (polygon - a) @ delta / length_squared
        stationed = np.c_[polygon, semantic[owner] + ratio * (semantic[owner + 1] - semantic[owner])]
        # Capsule caps naturally project outside their owning centreline
        # segment.  Clamp that source ownership before named endpoint planes
        # are cut; the cut intersections below then carry the named interval
        # station even when an adjacent bend capsule owns their footprint.
        stationed[:, 2] = np.clip(stationed[:, 2], semantic[owner], semantic[owner + 1])
        # Every capsule in the endpoint's own half-width station
        # neighbourhood can protrude through the intended flat cap (a short
        # final segment otherwise leaves the preceding round cap intact).
        # Clip only that local incident chain; distant returning legs retain
        # their complete RoadOutline footprint.
        if ("left" not in terminal_sides and
                semantic[owner] <= start_station + half_width + cap_guard_metres):
            stationed = _clip_stationed(stationed,
                                         ((stationed[:, :2] - encoded[0, [0, 2]]) @ start_direction +
                                          cap_guard_metres), start_station)
        if len(stationed):
            stationed[:, 2] = np.maximum(stationed[:, 2], start_station)
        if ("right" not in terminal_sides and len(stationed) and
                semantic[owner + 1] >= end_station - half_width - cap_guard_metres):
            stationed = _clip_stationed(
                stationed,
                (encoded[-1, [0, 2]] - stationed[:, :2]) @ end_direction + cap_guard_metres,
                end_station)
        if len(stationed):
            stationed[:, 2] = np.minimum(stationed[:, 2], end_station)
        if len(stationed) < 3 or _area_xz(stationed[:, :2]) <= 0: continue
        records.append({"xz": stationed[:, :2].copy(),
                        "stations": stationed[:, 2], "sourceSegment": owner})
    return records


def _intrinsic_route_stations(encoded_route, semantic_stations, query, flat_bands=()):
    query = np.asarray(query, float); best = np.full(len(query), np.inf); result = np.zeros(len(query))
    tie_low = np.full(len(query), np.inf); tie_high = np.full(len(query), -np.inf)
    for index, (a, b) in enumerate(zip(encoded_route, encoded_route[1:])):
        delta = b - a; length = float(delta @ delta)
        ratio = np.clip((query - a) @ delta / length, 0., 1.)
        projection = a + ratio[:, None] * delta
        distance = np.sum((query - projection) ** 2, axis=1)
        station = semantic_stations[index] + ratio * (semantic_stations[index + 1] - semantic_stations[index])
        tied = (distance == best) & (station != result)
        tie_low[tied] = np.minimum(np.minimum(tie_low[tied], result[tied]), station[tied])
        tie_high[tied] = np.maximum(np.maximum(tie_high[tied], result[tied]), station[tied])
        use = distance < best
        best[use] = distance[use]; result[use] = station[use]
        tie_low[use] = np.inf; tie_high[use] = -np.inf
    ambiguity = np.flatnonzero(np.isfinite(tie_low))
    unresolved = []
    for vertex in ambiguity:
        owners = [band for band in flat_bands if band[0] <= tie_low[vertex] and tie_high[vertex] <= band[1]]
        if len(owners) != 1: unresolved.append(int(vertex))
        else: result[vertex] = float(owners[0][2])
    if unresolved:
        raise CoastalGeometryError("encoded road union has ambiguous intrinsic station ownership",
                         vertices=unresolved)
    return result


def _interval_route(points, start_station, end_station):
    points = np.asarray(points, float); source = cumulative_stations(points)
    start, start_index, _ = _point_at(points, source, start_station)
    end, end_index, _ = _point_at(points, source, end_station)
    indices = np.arange(start_index + 1, end_index + 1)
    indices = indices[(source[indices] > start_station) & (source[indices] < end_station)]
    route = np.concatenate(([start], points[indices], [end]))
    semantic = np.r_[start_station, source[indices], end_station]
    encoded = route[:, [0, 2]].astype(np.float32).astype(float)
    return route, encoded, semantic


def _indexed_road_union_surface(name, kind, road_id, points, half_width, start_station, end_station,
                                profile_stations, profile_heights, outline_factory, level_bands=(),
                                terminal_sides=(), require_join_caps=True):
    """Partition one guarded RoadOutline union in its carried local station field."""
    profile_stations = np.asarray(profile_stations, float); profile_heights = np.asarray(profile_heights, float)
    if len(profile_stations) != len(profile_heights) or not np.all(np.diff(profile_stations) > 0):
        raise CoastalGeometryError("coastal indexed profile table is invalid")
    if profile_stations[0] != start_station or profile_stations[-1] != end_station:
        raise CoastalGeometryError("coastal indexed profile omits a named join")
    slopes = np.diff(profile_heights) / np.diff(profile_stations)
    break_stations = profile_stations[1:-1][slopes[:-1] != slopes[1:]]
    flat_bands = []
    for value in level_bands:
        left, right = map(float, value[:2])
        indices = [int(np.flatnonzero(profile_stations == station)[0])
                   for station in (left, right) if np.any(profile_stations == station)]
        if len(indices) != 2 or profile_heights[indices[0]] != profile_heights[indices[1]]:
            raise CoastalGeometryError("explicit level bend band is absent from the profile table",
                             bandMetres=[left, right])
        flat_bands.append((left, right, (left + right) * .5))
    route, encoded_route, semantic = _interval_route(points, start_station, end_station)
    terminal_sides = frozenset(map(str, terminal_sides))
    nominal_records = road_outline_records(points, half_width, start_station, end_station,
                                           outline_factory, terminal_sides=terminal_sides)
    encoding_guard = road_outline_encoding_guard(nominal_records)
    nominal_points = np.concatenate([record["xz"] for record in nominal_records]).astype(np.float32)
    precision_grid = float(np.max(np.abs(np.spacing(nominal_points)).astype(np.float64)))
    precision_snap_guard = math.sqrt(2.) * precision_grid * .5
    construction_guard = encoding_guard - precision_snap_guard
    construction_records = road_outline_records(
        points, float(half_width) + construction_guard,
        start_station, end_station, outline_factory, cap_guard_metres=construction_guard,
        terminal_sides=terminal_sides)
    union = encoded_road_outline_union([*construction_records, *nominal_records])
    segment_scale = np.max(np.diff(semantic) / np.linalg.norm(np.diff(encoded_route, axis=0), axis=1))
    route_encoding_error = float(np.linalg.norm(route[:, [0, 2]] - encoded_route, axis=1).max(initial=0.))
    station_encoding_guard = float((route_encoding_error + 2. * encoding_guard) * segment_scale)
    ownership_bands = [(left - station_encoding_guard, right + station_encoding_guard, centre)
                       for left, right, centre in flat_bands]
    base_vertex_count = len(union.vertices_xz)
    vertices = [point.copy() for point in union.vertices_xz]
    profile_sections = {}
    route_stations = cumulative_stations(points)
    plane_xz_guard = route_encoding_error + 2. * encoding_guard
    for station in break_stations:
        section = _section(np.asarray(points, float), route_stations, float(station), half_width).astype(
            np.float32).astype(np.float64)[:, [0, 2]]
        direction = section[1] - section[0]; direction /= np.linalg.norm(direction)
        split_extension = 2. * encoding_guard + route_encoding_error
        profile_sections[float(station)] = section
        profile_sections[(float(station), "split")] = np.asarray(
            [section[0] - direction * split_extension, section[1] + direction * split_extension])

    def clean_cycle(indices):
        result = []
        for value in indices:
            value = int(value)
            if not result or result[-1] != value: result.append(value)
        if len(result) > 1 and result[0] == result[-1]: result.pop()
        changed = True
        while changed and len(result) > 3:
            changed = False
            for position in range(len(result)):
                a, b, c = (vertices[result[position - 1]], vertices[result[position]],
                           vertices[result[(position + 1) % len(result)]])
                ab, bc = b - a, c - b
                if ab[0] * bc[1] - ab[1] * bc[0] == 0. and np.dot(ab, bc) >= 0.:
                    result.pop(position); changed = True; break
        if len(result) >= 3:
            polygon = Polygon([vertices[index] for index in result])
            if not polygon.is_valid:
                # F32 can reverse a microscopic edge.  Reorder only when every
                # vertex remains on the convex boundary, proving that no real
                # concavity is being filled.
                hull = shapely.MultiPoint([vertices[index] for index in result]).convex_hull
                if isinstance(hull, Polygon):
                    ring = np.asarray(hull.exterior.coords[:-1], float)
                    lookup = {tuple(vertices[index]): index for index in result}
                    if len(ring) == len(result) and set(map(tuple, ring)) == set(lookup):
                        result = [lookup[tuple(point)] for point in ring]
        return result

    # GEOS overlays the complete encoded road union and local profile lines on
    # a derived power-of-two grid.
    # Every resulting coordinate is exactly representable by float32 at this
    # route magnitude, so the final cells form one disjoint shared table.
    if not np.isfinite(precision_grid) or precision_grid <= 0.:
        raise CoastalGeometryError("encoded coastal partition has no finite precision grid")
    if not len(break_stations):
        # A single affine height zone needs no GEOS overlay.  Preserve the
        # already certified encoded union verbatim, including holes and caps;
        # re-polygonizing it can shave a positive F32 cap sliver.
        encoded_xz = union.vertices_xz.copy()
        pieces = union.triangle_indices.astype(int).tolist()
    else:
        base_polygons = [Polygon(union.vertices_xz[face]) for face in union.triangle_indices]
        floor = shapely.set_precision(shapely.union_all(base_polygons), precision_grid)
        split_lines = [shapely.set_precision(
            LineString(profile_sections[(float(station), "split")]).intersection(floor), precision_grid)
            for station in break_stations]
        linework = shapely.union_all(
            [floor.boundary, *(line for line in split_lines if not line.is_empty)],
            grid_size=precision_grid)
        cells = [polygon for polygon in shapely.get_parts(shapely.polygonize([linework]))
                 if isinstance(polygon, Polygon) and polygon.area > 0. and
                 floor.covers(polygon.representative_point())]
        if not cells:
            raise CoastalGeometryError("fixed-precision coastal partition is empty")
        # Partition a hole-bearing cell into CDT faces before flattening exterior
        # rings.  This preserves a genuine RoadOutline hole instead of silently
        # filling it when the global shared vertex table is assembled.
        cells = [part for polygon in cells
                 for part in (shapely.get_parts(shapely.constrained_delaunay_triangles(polygon))
                              if len(polygon.interiors) else (polygon,))
                 if isinstance(part, Polygon) and part.area > 0.]
        cell_rings = [_encoded_ring(polygon.exterior, "fixed-precision profile zone") for polygon in cells]
        encoded_xz, remap = np.unique(np.concatenate(cell_rings).astype(np.float32), axis=0,
                                      return_inverse=True)
        encoded_xz = encoded_xz.astype(np.float64); pieces = []; cursor = 0
        for ring in cell_rings:
            pieces.append(remap[cursor:cursor + len(ring)].astype(int).tolist()); cursor += len(ring)
        plane_xz_guard += math.sqrt(2.) * precision_grid
        station_encoding_guard += math.sqrt(2.) * precision_grid * segment_scale
    vertices = [point.copy() for point in encoded_xz]
    ownership_bands = [(left - station_encoding_guard, right + station_encoding_guard, centre)
                       for left, right, centre in flat_bands]
    intrinsic = _intrinsic_route_stations(encoded_route, semantic, encoded_xz, ownership_bands)
    # The interval cap can be owned by an adjacent bend capsule.  Nearest-route
    # projection then assigns that cap to the adjacent source vertex even
    # though road_outline_records carried the named endpoint station.  Restore
    # the endpoint identity from the actual local construction plane.  The
    # transverse bound excludes a distant returning leg that happens to cross
    # the same infinite plane.
    for side, station, endpoint, tangent, sign in (
            ("left", float(start_station), encoded_route[0], encoded_route[1] - encoded_route[0], -1.),
            ("right", float(end_station), encoded_route[-1], encoded_route[-1] - encoded_route[-2], 1.)):
        if side in terminal_sides:
            continue
        tangent = tangent / np.linalg.norm(tangent)
        delta = encoded_xz - endpoint
        longitudinal = delta @ tangent
        transverse = np.abs(delta[:, 0] * tangent[1] - delta[:, 1] * tangent[0])
        on_cap = (np.abs(longitudinal - sign * construction_guard) <= plane_xz_guard) & \
                 (transverse <= float(half_width) + plane_xz_guard)
        intrinsic[on_cap] = station
    intrinsic[np.abs(intrinsic - float(start_station)) <= station_encoding_guard] = float(start_station)
    intrinsic[np.abs(intrinsic - float(end_station)) <= station_encoding_guard] = float(end_station)

    def local_profile_plane(station, point):
        section = profile_sections[(float(station), "split")]
        delta = section[1] - section[0]; length = float(delta @ delta)
        ratio = float(np.clip((point - section[0]) @ delta / length, 0., 1.))
        return float(np.linalg.norm(point - (section[0] + ratio * delta))) <= plane_xz_guard

    carried = [set() for _ in encoded_xz]
    for index, point in enumerate(encoded_xz):
        for station in break_stations:
            if (abs(float(intrinsic[index]) - float(station)) <= station_encoding_guard and
                    local_profile_plane(station, point)):
                carried[index].add(float(station))

    plane_envelopes = {}
    for station in break_stations:
        indices = [index for index, values in enumerate(carried)
                   if float(station) in values and local_profile_plane(station, encoded_xz[index])]
        if not indices:
            raise CoastalGeometryError("local profile plane did not create an encoded breakline",
                             stationMetres=float(station))
        actual = intrinsic[indices]
        plane_envelopes[float(station)] = [float(actual.min()), float(actual.max())]
    plane_envelopes.setdefault(float(profile_stations[0]),
                               [float(profile_stations[0]), float(profile_stations[0])])
    plane_envelopes.setdefault(float(profile_stations[-1]),
                               [float(profile_stations[-1]), float(profile_stations[-1])])
    encoded_flat_bands = []
    for (left, right, centre), (guarded_left, guarded_right, _) in zip(flat_bands, ownership_bands):
        moved = [guarded_left, guarded_right, *plane_envelopes[left], *plane_envelopes[right]]
        encoded_flat_bands.append((min(moved), max(moved), centre, left, right))
    merged_profile_vertices = []
    break_set = set(map(float, break_stations))
    for encoded_index, values in enumerate(carried):
        exact = {value for value in values if value in break_set and
                 local_profile_plane(value, encoded_xz[encoded_index])}
        if len(exact) > 1:
            candidates = [*exact, float(intrinsic[encoded_index])]
            owners = [band for band in encoded_flat_bands
                      if band[0] <= min(candidates) and max(candidates) <= band[1]]
            if len(owners) != 1:
                raise CoastalGeometryError("profile planes merged at one encoded coastal vertex",
                                 stations=sorted(exact),
                                 vertexStationMetres=float(intrinsic[encoded_index]))
            merged_profile_vertices.append({"vertex": int(encoded_index),
                                            "stationsMetres": sorted(exact),
                                            "intrinsicStationMetres": float(intrinsic[encoded_index]),
                                            "flatBandMetres": list(owners[0][3:]),
                                            "encodedFlatBandMetres": list(owners[0][:2])})
            intrinsic[encoded_index] = float(owners[0][2])
        elif exact:
            override = exact.pop(); low, high = plane_envelopes[override]
            if not low <= intrinsic[encoded_index] <= high:
                raise CoastalGeometryError("profile override escaped its actual float32 station envelope",
                                 stationMetres=override,
                                 vertexStationMetres=float(intrinsic[encoded_index]),
                                 envelopeMetres=[low, high])
            intrinsic[encoded_index] = override
    station_values = intrinsic
    heights = np.interp(station_values, profile_stations, profile_heights).astype(np.float32).astype(float)
    faces = []; encoded_cycles = []
    for indices in pieces:
        cycle = clean_cycle(indices)
        if len(cycle) < 3: continue
        polygon = Polygon(encoded_xz[cycle])
        if not polygon.is_valid or polygon.area == 0.:
            raise CoastalGeometryError("encoded station-partition polygon is invalid",
                                       reason=shapely.is_valid_reason(polygon), vertexIndices=cycle,
                                       vertexXZ=encoded_xz[cycle])
        encoded_cycles.append(encoded_xz[cycle].copy())
        for local in constrained_polygon_indices(encoded_xz[cycle]):
            faces.append([cycle[int(value)] for value in local])
    if not faces: raise CoastalGeometryError("encoded coastal RoadOutline union has no triangles")
    faces = np.asarray(faces, int); positions = np.c_[encoded_xz[:, 0], heights, encoded_xz[:, 1]]

    def plane_cuts_face(station, face):
        polygon = Polygon(encoded_xz[face])
        intersection = LineString(profile_sections[(float(station), "split")]).intersection(polygon)
        return (intersection.length > 0. and
                intersection.representative_point().distance(polygon.boundary) > plane_xz_guard)

    for face in faces:
        low, high = float(station_values[face].min()), float(station_values[face].max())
        crossed = break_stations[(break_stations > low) & (break_stations < high)]
        unsplit = [float(station) for station in crossed
                   if low < plane_envelopes[float(station)][0] and
                   high > plane_envelopes[float(station)][1] and
                   plane_cuts_face(station, face)]
        if unsplit:
            raise CoastalGeometryError("encoded coastal face crosses an unsplit local profile breakline",
                             face=face.tolist(), stationRangeMetres=[low, high],
                             crossedStationsMetres=unsplit, faceXZ=encoded_xz[face])
    triangles = positions[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    reverse = normals[:, 1] < 0
    faces[reverse] = faces[reverse][:, [0, 2, 1]]; triangles = positions[faces]
    _check_encoded_grade(triangles, MAXIMUM_GRADE)
    # Carry the actual emitted flat cap edges as the join authority.  Selecting
    # by endpoint station alone can accidentally include an adjacent capsule
    # arc whose nearest intrinsic station was clamped to the endpoint.
    boundary = {}
    for face_index, face in enumerate(faces):
        for first, second in ((0, 1), (1, 2), (2, 0)):
            edge = (int(face[first]), int(face[second]))
            key = tuple(sorted(edge)); boundary.setdefault(key, []).append(
                (edge, station_values[face[[first, second]]]))

    def emitted_cap_section(station):
        candidates = [value[0][0] for value in boundary.values()
                      if len(value) == 1 and np.all(value[0][1] == float(station))]
        if not candidates:
            nearest = sorted((float(np.max(np.abs(value[0][1] - float(station)))),
                              value[0][1].tolist(), value[0][0])
                             for value in boundary.values() if len(value) == 1)[:8]
            raise CoastalGeometryError("encoded coastal join has no emitted cap edge",
                                       stationMetres=float(station),
                                       nearestBoundaryStationEdges=nearest)
        # The guarded and nominal flat caps meet through two derived-scale
        # lateral transition edges.  They remain floor and clearance geometry,
        # but are not the bank join.  Remove only terminal transitions no
        # longer than the independently derived encoding envelope, then demand
        # one connected full-width cap chain.
        edges = [tuple(map(int, edge)) for edge in candidates]
        changed = True
        while changed:
            changed = False; degree = {}
            for first, second in edges:
                degree[first] = degree.get(first, 0) + 1
                degree[second] = degree.get(second, 0) + 1
            for index, edge in enumerate(edges):
                length = float(np.linalg.norm(encoded_xz[edge[1]] - encoded_xz[edge[0]]))
                if length <= 2. * encoding_guard and (degree[edge[0]] == 1 or degree[edge[1]] == 1):
                    edges.pop(index); changed = True; break
        degree = {}; adjacency = {}
        for first, second in edges:
            degree[first] = degree.get(first, 0) + 1; degree[second] = degree.get(second, 0) + 1
            adjacency.setdefault(first, set()).add(second); adjacency.setdefault(second, set()).add(first)
        endpoints = [index for index, count in degree.items() if count == 1]
        if len(endpoints) != 2 or any(count > 2 for count in degree.values()):
            raise CoastalGeometryError("encoded coastal cap is not one boundary chain",
                                       stationMetres=float(station), edgeCount=len(edges),
                                       endpointCount=len(endpoints),
                                       degree={int(key): int(value) for key, value in degree.items()},
                                       edgeXZ=[positions[list(edge)][:, [0, 2]] for edge in edges])
        visited = {endpoints[0]}; pending = [endpoints[0]]
        while pending:
            pending.extend(value for value in adjacency[pending.pop()] if value not in visited)
            visited.update(pending)
        if len(visited) != len(degree):
            raise CoastalGeometryError("encoded coastal cap boundary is disconnected",
                                       stationMetres=float(station))
        section = positions[endpoints].copy()
        if np.linalg.norm(section[1, [0, 2]] - section[0, [0, 2]]) < 2. * float(half_width):
            raise CoastalGeometryError("encoded coastal cap does not retain full road width",
                                       stationMetres=float(station),
                                       encodedWidthMetres=float(np.linalg.norm(
                                           section[1, [0, 2]] - section[0, [0, 2]])),
                                       requiredWidthMetres=2. * float(half_width))
        return section, tuple(positions[list(edge)].copy() for edge in edges)

    endpoint_sections = []
    endpoint_edges = []
    route_stations = cumulative_stations(points)
    for side, station, height in (("left", start_station, profile_heights[0]),
                                  ("right", end_station, profile_heights[-1])):
        if require_join_caps and side not in terminal_sides:
            section, edges = emitted_cap_section(station)
        else:
            # A footprint probe has no bank-contact claim.  A true terminal
            # preserves its round RoadOutline cap, so there is deliberately no
            # straight emitted join chain on that side either.  The nominal
            # section is only an endpoint reference for callers; acceptance
            # must use the explicit terminal-platform evidence.
            section = _section(np.asarray(points, float), route_stations, float(station),
                               float(half_width)).astype(np.float32).astype(np.float64)
            section[:, 1] = np.float32(height)
            edges = ()
        endpoint_sections.append(section); endpoint_edges.append(tuple(edges))
    left_section, right_section = endpoint_sections
    left_join_edges, right_join_edges = endpoint_edges
    sections = np.stack((left_section, right_section))
    surface = SurfaceGeometry(name, kind, road_id, np.asarray([start_station, end_station]), sections,
                              triangles, station_values[faces], (left_join_edges, right_join_edges))
    metadata = {"unionComponents": union.component_count, "unionHoles": union.hole_count,
                "baseEncodedVertices": base_vertex_count,
                "sourceVertices": int(sum(len(piece) for piece in pieces)),
                "encodedVertices": len(encoded_xz), "triangles": len(triangles),
                "roadOutlineSegments": len(nominal_records),
                "terminalSides": sorted(terminal_sides),
                "joinCapsValidated": bool(require_join_caps and not terminal_sides),
                "validatedJoinSides": [side for side in ("left", "right")
                                       if require_join_caps and side not in terminal_sides],
                "profileStationsMetres": profile_stations, "profileHeightsMetres": profile_heights,
                "stationAuthority": "source-segment intrinsic projection with shared indexed split-plane overrides",
                "topology": "one indexed encoded bounded road union partitioned into height zones",
                "unionAuthority": "GEOS union of bounded existing RoadOutline capsules",
                "mergedProfilePlaneVertices": merged_profile_vertices,
                "roadOutlineEncodingGuardMetres": encoding_guard,
                "flatBandEncodingEnvelopesMetres": [list(value) for value in encoded_flat_bands],
                "profilePlaneEncodingEnvelopesMetres": plane_envelopes,
                "requiredExternalGate": "nominal RoadOutline contained in emitted floor; emitted floor contained in independently derived encoding guard"}
    authority = {"sourcePartitionXZ": encoded_cycles, "encodedPartitionXZ": encoded_cycles,
                 "nominalOutlineRecords": nominal_records, "encodingGuardMetres": encoding_guard}
    return surface, metadata, authority


def indexed_road_union_surface(name, kind, road_id, points, half_width, start_station, end_station,
                               profile_stations, profile_heights, outline_factory, level_bands=(),
                               terminal_sides=()):
    """Build final floor geometry and validate every non-terminal bank cap."""
    return _indexed_road_union_surface(
        name, kind, road_id, points, half_width, start_station, end_station,
        profile_stations, profile_heights, outline_factory, level_bands=level_bands,
        terminal_sides=terminal_sides, require_join_caps=True)


def indexed_road_union_probe_surface(name, kind, road_id, points, half_width,
                                     start_station, end_station, profile_stations,
                                     profile_heights, outline_factory, level_bands=()):
    """Build an exact bounded RoadOutline footprint without claiming bank joins."""
    return _indexed_road_union_surface(
        name, kind, road_id, points, half_width, start_station, end_station,
        profile_stations, profile_heights, outline_factory, level_bands=level_bands,
        require_join_caps=False)


def coastal_profile_table(points, half_width, start, wet_start, crown, wet_end, end, profile,
                          minimum_half_run):
    source = cumulative_stations(points); rows = {float(start): float(profile.height(start)),
                                                      float(end): float(profile.height(end))}
    bands = []
    directions = np.diff(np.asarray(points, float)[:, [0, 2]], axis=0)
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    for index in np.flatnonzero((source > start) & (source < end)):
        station = source[index]
        turn = math.acos(float(np.clip(directions[index - 1] @ directions[index], -1., 1.)))
        half_run = max(float(minimum_half_run), float(half_width) * math.tan(turn * .5))
        left, right = max(float(start), float(station - half_run)), min(float(end), float(station + half_run))
        if bands and left <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], right); bands[-1][2].append(float(station))
        else: bands.append([left, right, [float(station)]])
    for left, right, centres in bands:
        if left <= start or right >= end:
            raise CoastalGeometryError("level bend band reaches a fitted bank endpoint",
                             bandMetres=[left, right], joinStationsMetres=[start, end])
        level = max(float(profile.height(value)) for value in centres)
        if left <= crown <= right: level = max(level, float(profile.height(crown)))
        rows[left] = level; rows[right] = level
    for station in (wet_start, crown, wet_end):
        if not any(left < station < right for left, right, _ in bands): rows[float(station)] = float(profile.height(station))
    stations = np.asarray(sorted(rows), float); heights = np.asarray([rows[value] for value in stations], float)
    return stations, heights, bands


def _route_station_encoding_guard(points):
    """Maximum route-station movement implied by the actual float32 XZ table."""
    source_points = _array(points, (3,), "coastal route points")
    encoded_xz = source_points[:, [0, 2]].astype(np.float32).astype(np.float64)
    source_stations = cumulative_stations(source_points)
    encoded_runs = np.linalg.norm(np.diff(encoded_xz, axis=0), axis=1)
    if (encoded_runs <= 0.).any():
        raise CoastalGeometryError("coastal route collapses after float32 encoding")
    encoded_stations = np.r_[0., np.cumsum(encoded_runs)]
    station_scale = np.max(np.diff(source_stations) / encoded_runs)
    xz_ulp = np.abs(np.spacing(encoded_xz.astype(np.float32))).astype(np.float64)
    return float(np.max(np.abs(source_stations - encoded_stations)) +
                 np.max(np.linalg.norm(xz_ulp, axis=1)) * station_scale)


def _intersecting_profile_plane_bands(points, half_width, stations, heights, station_guard):
    """Find distinct-height local cross-sections that meet after float32 encoding."""
    stations = np.asarray(stations, float); heights = np.asarray(heights, float)
    slopes = np.diff(heights) / np.diff(stations)
    indices = np.flatnonzero(slopes[:-1] != slopes[1:]) + 1
    if len(indices) < 2: return []
    source = cumulative_stations(points)
    sections = [_section(np.asarray(points, float), source, stations[index], half_width).astype(
        np.float32).astype(np.float64) for index in indices]
    conflicts = []
    for left in range(len(indices)):
        for right in range(left + 1, len(indices)):
            a, b = int(indices[left]), int(indices[right])
            if stations[b] - stations[a] <= station_guard: continue
            if np.float32(heights[a]) == np.float32(heights[b]): continue
            if LineString(sections[left][:, [0, 2]]).intersects(
                    LineString(sections[right][:, [0, 2]])):
                conflicts.append([float(stations[a]), float(stations[b]),
                                  [float(stations[a]), float(stations[b])]])
    return conflicts


def broad_middle_profile_table(points, half_width, start, wet_start, crown, wet_end, end,
                               profile, _extra_level_bands=(), _depth=0):
    """Sample smooth bank shoulders around a broad crown and ramped bend pads."""
    _, _, bend_bands = coastal_profile_table(points, half_width, start, wet_start, crown,
                                              wet_end, end, profile, 0.)
    anchor_guard = _route_station_encoding_guard(points)
    half_crown = max(2., .15 * (wet_end - wet_start))
    # Near-collinear source vertices can mathematically produce a positive bend
    # band narrower than their own float32 station movement.  Such a band has no
    # distinct encoded plane and is not physical profile geometry.
    requested = [list(value) for value in bend_bands
                 if float(value[1]) - float(value[0]) > anchor_guard]
    requested.extend([list(value) for value in _extra_level_bands])
    requested.append([max(start, crown - half_crown), min(end, crown + half_crown), [float(crown)]])
    requested.sort(key=lambda value: value[0])
    bands = []
    for left, right, centres in requested:
        if bands and left <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], right); bands[-1][2].extend(centres)
        else:
            bands.append([float(left), float(right), list(centres)])
    start_height = float(profile.height(start)); crown_height = float(profile.crown_height)
    end_height = float(profile.height(end))
    limit = min(MAXIMUM_GRADE, float(profile.maximum_grade))
    # A level bend pad generally differs from the underlying smooth shoulder
    # at its edge.  Give that difference an explicit longitudinal ramp.  If
    # adjacent ramps overlap, merge their pads and solve the shared level once.
    for _ in range(len(bands) + 1):
        crown_bands = [value for value in bands if value[0] <= crown <= value[1]]
        if len(crown_bands) != 1:
            raise CoastalGeometryError("broad-middle profile has no unique crown band")
        crown_left, crown_right = map(float, crown_bands[0][:2])
        if not start < crown_left <= crown <= crown_right < end:
            raise CoastalGeometryError("broad crown leaves no bank shoulder",
                                       crownBandMetres=[crown_left, crown_right],
                                       joinStationsMetres=[start, end])
        analytic_grades = [1.5 * abs(crown_height - start_height) / (crown_left - start),
                           1.5 * abs(crown_height - end_height) / (end - crown_right)]
        if max(analytic_grades) > limit:
            raise CoastalGeometryError("broad crown leaves insufficient smooth shoulder run",
                                       maximumGrade=max(analytic_grades), limit=limit)

        def shoulder_height(station):
            station = float(station)
            if station < crown_left:
                t = (station - start) / (crown_left - start)
                return start_height + (crown_height - start_height) * SmoothArchProfile._smooth(t)
            if station > crown_right:
                t = (station - crown_right) / (end - crown_right)
                return crown_height + (end_height - crown_height) * SmoothArchProfile._smooth(t)
            return crown_height

        ramps = []
        for left, right, centres in bands:
            if left <= start or right >= end:
                raise CoastalGeometryError("broad-middle level band reaches a fitted bank endpoint",
                                 bandMetres=[left, right], joinStationsMetres=[start, end])
            level = crown_height if left <= crown <= right else \
                max(shoulder_height(value) for value in centres)

            def outer(core, bound, direction):
                if shoulder_height(core) == level:
                    return float(core)
                grade = lambda station: abs(level - shoulder_height(station)) / abs(core - station)
                if grade(bound) > limit:
                    raise CoastalGeometryError("level bend pad has no legal shoulder transition",
                                     bandMetres=[left, right], levelMetres=level,
                                     availableBoundMetres=float(bound), maximumGrade=grade(bound),
                                     limit=limit)
                valid, invalid = float(bound), float(core)
                for _ in range(64):
                    middle = (valid + invalid) * .5
                    if grade(middle) <= limit: valid = middle
                    else: invalid = middle
                # A merely legal maximum-grade millimetre ramp is neither a
                # gentle visible shoulder nor a stable encoded height zone.
                # Use at least one existing canonical station interval when
                # the fitted shoulder has that room; farther remains legal.
                minimum_run = min(DEFAULT_STATION_SPACING_METRES, abs(float(core) - float(bound)))
                gentle = float(core) + float(direction) * minimum_run
                return min(valid, gentle) if direction < 0. else max(valid, gentle)

            ramp_left = outer(left, start, -1.)
            ramp_right = outer(right, end, 1.)
            ramps.append([ramp_left, float(left), float(right), ramp_right, float(level), centres])
        overlap = next((index for index in range(len(ramps) - 1)
                        if ramps[index][3] + anchor_guard >= ramps[index + 1][0]), None)
        if overlap is None:
            break
        merged = [bands[overlap][0], bands[overlap + 1][1],
                  [*bands[overlap][2], *bands[overlap + 1][2]]]
        bands[overlap:overlap + 2] = [merged]
    else:
        raise CoastalGeometryError("level bend-pad transitions did not converge")

    anchors = np.unique(np.r_[canonical_stations(points, start, end, DEFAULT_STATION_SPACING_METRES),
                              wet_start, crown, wet_end])
    rows = {float(start): start_height, float(end): end_height}
    for ramp_left, left, right, ramp_right, level, _ in ramps:
        if left - ramp_left > anchor_guard:
            rows[ramp_left] = shoulder_height(ramp_left)
        rows[left] = level; rows[right] = level
        if ramp_right - right > anchor_guard:
            rows[ramp_right] = shoulder_height(ramp_right)
    required_breaks = np.asarray(sorted(rows), float)
    for station in anchors:
        # A canonical sampling knot within the actual float32 station error of
        # a required ramp/flat plane is certificate-only.  Keeping both makes
        # a microscopic band that cannot survive the shared encoded table.
        near_required = np.min(np.abs(required_breaks - station)) <= anchor_guard
        if not near_required and not any(ramp_left < station < ramp_right
                                         for ramp_left, _, _, ramp_right, _, _ in ramps):
            rows[float(station)] = shoulder_height(station)
    stations = np.asarray(sorted(rows), float)
    heights = np.asarray([rows[value] for value in stations], float)
    grades = np.abs(np.diff(heights) / np.diff(stations))
    if len(grades) and float(grades.max()) > MAXIMUM_GRADE:
        raise CoastalGeometryError("broad-middle profile exceeds the coastal grade",
                         maximumGrade=float(grades.max()), limit=MAXIMUM_GRADE,
                         stationsMetres=stations, heightsMetres=heights)
    conflicts = _intersecting_profile_plane_bands(
        points, half_width, stations, heights, anchor_guard)
    if conflicts:
        if _depth >= len(np.asarray(points)):
            raise CoastalGeometryError("intersecting coastal profile planes did not converge",
                                       conflicts=conflicts)
        return broad_middle_profile_table(
            points, half_width, start, wet_start, crown, wet_end, end, profile,
            (*_extra_level_bands, *conflicts), _depth + 1)
    return stations, heights, bands

def _clip_convex(subject, clip):
    subject = np.asarray(subject, dtype=np.float64)
    clip = np.asarray(clip, dtype=np.float64)
    orientation = np.sign(_signed_area_xz(clip))
    if orientation == 0:
        return np.empty((0, subject.shape[1]))
    output = subject
    for a, b in zip(clip, np.roll(clip, -1, axis=0)):
        if not len(output): break
        edge = b - a
        distance = orientation * (edge[0] * (output[:, 1] - a[1]) - edge[1] * (output[:, 0] - a[0]))
        inside = distance >= 0
        next_output = []
        for index in range(len(output)):
            previous = (index - 1) % len(output)
            if inside[index] != inside[previous]:
                ratio = distance[previous] / (distance[previous] - distance[index])
                next_output.append(output[previous] + ratio * (output[index] - output[previous]))
            if inside[index]: next_output.append(output[index])
        output = np.asarray(next_output, dtype=np.float64).reshape(-1, subject.shape[1])
    return output


def _clip_positive(polygon, values):
    polygon = np.asarray(polygon, dtype=np.float64); values = np.asarray(values, dtype=np.float64)
    output = []
    for index in range(len(polygon)):
        previous = (index - 1) % len(polygon)
        current_in, previous_in = values[index] > 0, values[previous] > 0
        if current_in != previous_in:
            ratio = values[previous] / (values[previous] - values[index])
            output.append(polygon[previous] + ratio * (polygon[index] - polygon[previous]))
        if current_in: output.append(polygon[index])
    return np.asarray(output, dtype=np.float64).reshape(-1, polygon.shape[1])


def continuous_wet_evidence(surface: SurfaceGeometry, terrain: TerrainPatch,
                            sea_level: float, wet_epsilon: float = SEA_WET_EPSILON_METRES) -> dict:
    """Partition the complete road strip against every affine terrain triangle.

    Every positive overlap piece is retained; station is interpolated through
    the same clipping operations, so the reported wet extent is continuous
    geometry rather than a centreline or raster sample.
    """
    threshold = float(sea_level) - float(wet_epsilon)
    pieces = []
    terrain_faces = terrain.triangles()
    for face, face_stations in zip(surface.triangles, surface.triangle_stations):
        subject = np.c_[face[:, 0], face[:, 2], face_stations]
        lo, hi = subject[:, :2].min(axis=0), subject[:, :2].max(axis=0)
        for ground in terrain_faces:
            gxz = ground[:, [0, 2]]
            if (gxz.max(axis=0) < lo).any() or (gxz.min(axis=0) > hi).any(): continue
            overlap = _clip_convex(subject, gxz)
            if len(overlap) < 3 or _area_xz(overlap[:, :2]) <= 0: continue
            heights = terrain.height_at(overlap[:, :2])
            wet = _clip_positive(overlap, threshold - heights)
            if len(wet) < 3: continue
            area = _area_xz(wet[:, :2])
            if area > 0:
                pieces.append({"xz": wet[:, :2], "stations": wet[:, 2], "areaSquareMetres": area})
    if not pieces:
        raise CoastalGeometryError("coastal band has no continuous wet area", roadId=surface.road_id)
    low = min(float(piece["stations"].min()) for piece in pieces)
    high = max(float(piece["stations"].max()) for piece in pieces)
    return {"wetExtentMetres": [low, high], "wetPieces": pieces,
            "wetAreaSquareMetres": float(sum(piece["areaSquareMetres"] for piece in pieces)),
            "pieceCount": len(pieces), "thresholdYMetres": threshold,
            "acceptanceAuthority": False, "role": "terrain-threshold preflight only"}


def _affine_triangle_height(triangle, points_xz):
    triangle = _array(triangle, (3,), "affine triangle")
    points_xz = _array(points_xz, (2,), "affine query")
    matrix = np.c_[triangle[:, 0], triangle[:, 2], np.ones(3)]
    coefficients = np.linalg.solve(matrix, triangle[:, 1])
    return points_xz @ coefficients[:2] + coefficients[2]


def emitted_water_evidence(surface: SurfaceGeometry, water_groups: Mapping[str, np.ndarray],
                           *, minimum_clearance_metres: float | None = None) -> dict:
    """Intersect actual encoded floor with current emitted clipped water faces.

    ``water_groups`` names every current hydrology domain (sea, river, lake,
    and any future kind).  Omitting a domain is therefore a probe error, not a
    silent pure-sea result.  Callers record the source manifest with this data.
    """
    if not water_groups:
        raise CoastalGeometryError("emitted-water evidence has no named hydrology domains")
    missing_domains = {"sea", "river", "lake"} - set(water_groups)
    if missing_domains:
        raise CoastalGeometryError("emitted-water evidence omits a current hydrology domain",
                                   missingDomains=sorted(missing_domains))
    pieces = []
    for kind, triangles in water_groups.items():
        triangles = _array(triangles, (3, 3), f"{kind} water triangles").astype(
            np.float32).astype(np.float64)
        water_xz = triangles[:, :, [0, 2]]
        water_low = water_xz.min(axis=1); water_high = water_xz.max(axis=1)
        for floor, floor_stations in zip(surface.encoded_triangles, surface.triangle_stations):
            subject = np.c_[floor[:, 0], floor[:, 2], floor_stations, floor[:, 1]]
            low, high = subject[:, :2].min(axis=0), subject[:, :2].max(axis=0)
            candidates = np.flatnonzero(np.all(water_high >= low, axis=1) &
                                        np.all(water_low <= high, axis=1))
            for index in candidates:
                wxz = water_xz[index]
                overlap = _clip_convex(subject, wxz)
                if len(overlap) < 3:
                    continue
                area = _area_xz(overlap[:, :2])
                if area > 0:
                    gaps = overlap[:, 3] - _affine_triangle_height(triangles[index], overlap[:, :2])
                    pieces.append({"kind": str(kind), "xz": overlap[:, :2],
                                   "stations": overlap[:, 2], "areaSquareMetres": area})
                    pieces[-1]["minimumClearanceMetres"] = float(gaps.min())
    if not pieces:
        raise CoastalGeometryError("encoded coastal floor has no emitted-water contact",
                                   roadId=surface.road_id)
    intervals = sorted((float(piece["stations"].min()), float(piece["stations"].max())) for piece in pieces)
    merged = []
    for low, high in intervals:
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    kinds = sorted({piece["kind"] for piece in pieces})
    non_sea = [kind for kind in kinds if kind != "sea"]
    pure_sea = not non_sea; continuous = len(merged) == 1
    minimum = min(piece["minimumClearanceMetres"] for piece in pieces)
    clearance_metres = (None if minimum_clearance_metres is None else
                         float(minimum_clearance_metres))
    clearance_clear = clearance_metres is None or minimum >= clearance_metres
    return {"acceptanceAuthority": True, "clear": pure_sea and continuous and clearance_clear,
            "encoded": True, "pieces": pieces,
            "wetExtentMetres": [merged[0][0], merged[-1][1]],
            "continuousStationIntervalsMetres": merged, "continuous": continuous,
            "contactKinds": kinds, "pureSea": pure_sea, "nonSeaContactKinds": non_sea,
            "minimumClearanceMetres": minimum,
            "requiredClearanceMetres": clearance_metres,
            "clearanceClear": clearance_clear,
            "wetAreaSquareMetres": float(sum(piece["areaSquareMetres"] for piece in pieces))}


def _domain_cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _domain_point_segment_distance_squared(point, a, b):
    delta = b - a; length = float(delta @ delta)
    ratio = 0. if length == 0. else float(np.clip((point - a) @ delta / length, 0., 1.))
    offset = point - (a + ratio * delta)
    return float(offset @ offset)


def _domain_point_in_convex(point, polygon):
    values = [_domain_cross(b - a, point - a) for a, b in zip(polygon, np.roll(polygon, -1, axis=0))]
    return all(value >= 0 for value in values) or all(value <= 0 for value in values)


def _domain_segments_intersect(a, b, c, d):
    ab, cd = b - a, d - c
    values = (_domain_cross(ab, c - a), _domain_cross(ab, d - a),
              _domain_cross(cd, a - c), _domain_cross(cd, b - c))
    if values[0] == 0 and _domain_point_segment_distance_squared(c, a, b) == 0: return True
    if values[1] == 0 and _domain_point_segment_distance_squared(d, a, b) == 0: return True
    if values[2] == 0 and _domain_point_segment_distance_squared(a, c, d) == 0: return True
    if values[3] == 0 and _domain_point_segment_distance_squared(b, c, d) == 0: return True
    return (values[0] < 0 < values[1] or values[1] < 0 < values[0]) and \
           (values[2] < 0 < values[3] or values[3] < 0 < values[2])


def _domain_segment_polygon_distance_squared(a, b, polygon):
    if _domain_point_in_convex(a, polygon) or _domain_point_in_convex(b, polygon): return 0.
    best = math.inf
    for c, d in zip(polygon, np.roll(polygon, -1, axis=0)):
        if _domain_segments_intersect(a, b, c, d): return 0.
        best = min(best, _domain_point_segment_distance_squared(a, c, d),
                   _domain_point_segment_distance_squared(b, c, d),
                   _domain_point_segment_distance_squared(c, a, b),
                   _domain_point_segment_distance_squared(d, a, b))
    return float(best)


def _lake_polygon_interior(lake, polygon):
    centre = np.asarray(lake["center"], float); angle = float(lake.get("angle", 0.))
    cosine, sine = math.cos(angle), math.sin(angle); radius = np.asarray(lake["radii"], float)
    delta = np.asarray(polygon, float) - centre
    transformed = np.c_[(delta[:, 0] * cosine + delta[:, 1] * sine) / radius[0],
                        (-delta[:, 0] * sine + delta[:, 1] * cosine) / radius[1]]
    if (np.sum(transformed * transformed, axis=1) < 1.).any(): return True
    origin = np.zeros(2)
    if _domain_point_in_convex(origin, transformed): return True
    return any(_domain_point_segment_distance_squared(origin, a, b) < 1.
               for a, b in zip(transformed, np.roll(transformed, -1, axis=0)))


def exact_domain_evidence(evidence: Mapping, world, landscape) -> dict:
    """Relabel every positive emitted-water contact by exact source domain interiors."""
    result = dict(evidence); result["pieces"] = [dict(piece) for piece in evidence["pieces"]]
    river_segments = []
    for river in world.plan.get("rivers", ()):
        points = np.asarray(landscape.river_points(river), float)[:, :2]
        width = float(river["width"])
        river_segments.extend((a, b, width, np.minimum(a, b) - width, np.maximum(a, b) + width)
                              for a, b in zip(points, points[1:]))
    lakes = []
    for lake in world.plan.get("lakes", ()):
        radius = max(map(float, lake["radii"])); centre = np.asarray(lake["center"], float)
        lakes.append((lake, centre - radius, centre + radius))
    kinds = []
    for piece in result["pieces"]:
        polygon = np.asarray(piece["xz"], float); low, high = polygon.min(axis=0), polygon.max(axis=0)
        lake_contact = any(_lake_polygon_interior(lake, polygon) for lake, box_low, box_high in lakes
                           if np.all(box_high >= low) and np.all(box_low <= high))
        river_contact = any(
            _domain_segment_polygon_distance_squared(a, b, polygon) < width * width
            for a, b, width, box_low, box_high in river_segments
            if np.all(box_high >= low) and np.all(box_low <= high))
        kind = ("river+lake" if river_contact and lake_contact else "river" if river_contact else
                "lake" if lake_contact else "sea")
        piece["kind"] = kind; kinds.append(kind)
    result["pureSea"] = all(kind == "sea" for kind in kinds)
    result["nonSeaContactKinds"] = sorted(set(kinds) - {"sea"})
    result["contactKinds"] = sorted(set(kinds))
    result["clear"] = bool(result["pureSea"] and result["continuous"] and
                           result.get("clearanceClear", True))
    result["exactDomainMethod"] = ("interior segment-to-convex-polygon distance for every curved river capsule; "
                                   "affine ellipse-to-unit-circle polygon intersection for every lake")
    result["exactDomainPieceCounts"] = {kind: kinds.count(kind) for kind in sorted(set(kinds))}
    return result


def section_evidence(section: np.ndarray, terrain: TerrainPatch, dry_threshold: float) -> dict:
    """Exact piecewise-affine terrain evidence along one complete cross-section."""
    line = _array(section, (3,), "road section")[:, [0, 2]]
    if line.shape != (2, 2):
        raise CoastalGeometryError("road join must be one full-width segment")
    delta = line[1] - line[0]; parameters = [0., 1.]
    for values, origin, component in ((terrain.x, line[0, 0], 0), (terrain.z, line[0, 1], 1)):
        if delta[component] != 0:
            parameters.extend(float((value - origin) / delta[component]) for value in values
                              if 0 < (value - origin) / delta[component] < 1)
    parameters = sorted(set(parameters))
    # Split each cell interval once more at its anti-diagonal.
    extra = []
    for left, right in zip(parameters, parameters[1:]):
        middle = (left + right) * .5; point = line[0] + middle * delta
        col = int(math.floor((point[0] - terrain.x[0]) / terrain.cell))
        row = int(math.floor((point[1] - terrain.z[0]) / terrain.cell))
        if not 0 <= col < len(terrain.x) - 1 or not 0 <= row < len(terrain.z) - 1: continue
        target = terrain.x[col] + terrain.z[row] + terrain.cell
        denominator = delta[0] + delta[1]
        if denominator != 0:
            value = (target - line[0].sum()) / denominator
            if left < value < right: extra.append(float(value))
    parameters = np.asarray(sorted(set(parameters + extra)))
    points = line[0] + parameters[:, None] * delta
    heights = terrain.height_at(points)
    margins = heights - float(dry_threshold)
    return {"dry": bool((margins >= 0).all()), "parameters": parameters, "pointsXZ": points,
            "terrainYMetres": heights, "minimumDryMarginMetres": float(margins.min()),
            "maximumTerrainYMetres": float(heights.max()), "minimumTerrainYMetres": float(heights.min())}


def _polygon_solid_overlap(polygon, terrain: TerrainPatch) -> bool:
    if terrain.solid is None: return False
    polygon = np.asarray(polygon, dtype=np.float64)
    lo, hi = polygon.min(axis=0), polygon.max(axis=0)
    for row in range(len(terrain.z) - 1):
        if terrain.z[row + 1] < lo[1] or terrain.z[row] > hi[1]: continue
        for col in range(len(terrain.x) - 1):
            if terrain.x[col + 1] < lo[0] or terrain.x[col] > hi[0]: continue
            if not terrain.solid[row:row + 2, col:col + 2].any(): continue
            cell = np.array([[terrain.x[col], terrain.z[row]], [terrain.x[col + 1], terrain.z[row]],
                             [terrain.x[col + 1], terrain.z[row + 1]], [terrain.x[col], terrain.z[row + 1]]])
            overlap = _clip_convex(np.c_[polygon, np.zeros(len(polygon))], cell)
            if len(overlap) >= 3 and _area_xz(overlap[:, :2]) > 0: return True
    return False


def solid_clearance_evidence(surface: SurfaceGeometry, terrain: TerrainPatch) -> dict:
    hits = []
    for index, face in enumerate(surface.triangles):
        if _polygon_solid_overlap(face[:, [0, 2]], terrain): hits.append(index)
    return {"clear": not hits, "intersectingTriangleIndices": hits,
            "acceptanceAuthority": False,
            "role": "coarse cached-solid preflight; retained emitted mesh is required for acceptance"}


def encoded_terrain_clearance_evidence(surface: SurfaceGeometry, terrain: TerrainPatch) -> dict:
    """Exact affine clearance of every actual float32 floor/terrain overlap."""
    ground_faces = terrain.triangles().astype(np.float32).astype(np.float64)
    ground_xz = ground_faces[:, :, [0, 2]]
    ground_low = ground_xz.min(axis=1); ground_high = ground_xz.max(axis=1)
    minimum = math.inf; witness = None; pieces = 0
    for floor_index, floor in enumerate(surface.encoded_triangles):
        subject = np.c_[floor[:, 0], floor[:, 2], floor[:, 1]]
        low, high = subject[:, :2].min(axis=0), subject[:, :2].max(axis=0)
        candidates = np.flatnonzero(np.all(ground_high >= low, axis=1) &
                                    np.all(ground_low <= high, axis=1))
        for ground_index in candidates:
            overlap = _clip_convex(subject, ground_xz[ground_index])
            if len(overlap) < 3 or _area_xz(overlap[:, :2]) <= 0.: continue
            gaps = overlap[:, 2] - _affine_triangle_height(ground_faces[ground_index], overlap[:, :2])
            pieces += 1
            index = int(np.argmin(gaps)); value = float(gaps[index])
            if value < minimum:
                minimum = value
                witness = {"floorTriangle": int(floor_index), "terrainTriangle": int(ground_index),
                           "xz": overlap[index, :2], "gapMetres": value}
    if pieces == 0:
        raise CoastalGeometryError("encoded coastal floor has no final-terrain authority overlap",
                                   roadId=surface.road_id)
    clear = minimum >= 0.
    return {"acceptanceAuthority": True, "clear": clear, "encoded": True,
            "minimumGapMetres": float(minimum), "overlapPieceCount": pieces,
            "worst": witness,
            "authority": "actual emitted float32 floor and final float32 affine TerrainPatch triangles"}


def terrain_control_height_lower_bound(base_surface: SurfaceGeometry,
                                       raised_surface: SurfaceGeometry,
                                       terrain: TerrainPatch,
                                       base_control_height_metres: float,
                                       raised_control_height_metres: float,
                                       minimum_gap_metres: float = 0.) -> dict:
    """Solve one monotone profile control from exact floor/terrain overlaps.

    The caller builds the same indexed floor twice with only one crown/control
    height changed.  This derives every affine terrain constraint from those
    actual encoded triangles; it does not approximate the road with samples.
    """
    base = base_surface.encoded_triangles
    raised = raised_surface.encoded_triangles
    if base.shape != raised.shape or not np.array_equal(base[:, :, [0, 2]], raised[:, :, [0, 2]]):
        raise CoastalGeometryError("terrain lower-bound surfaces do not share one encoded floor topology")
    low_control = float(base_control_height_metres)
    high_control = float(raised_control_height_metres)
    control_delta = high_control - low_control
    if not np.isfinite(control_delta) or control_delta <= 0.:
        raise CoastalGeometryError("terrain lower-bound control step is not positive")
    ground_faces = terrain.triangles().astype(np.float32).astype(np.float64)
    ground_xz = ground_faces[:, :, [0, 2]]
    ground_low = ground_xz.min(axis=1); ground_high = ground_xz.max(axis=1)
    required_delta = 0.; constraints = 0; limiting = None
    for floor_index, (base_face, raised_face) in enumerate(zip(base, raised)):
        subject = np.c_[base_face[:, 0], base_face[:, 2], base_face[:, 1]]
        low, high = subject[:, :2].min(axis=0), subject[:, :2].max(axis=0)
        candidates = np.flatnonzero(np.all(ground_high >= low, axis=1) &
                                    np.all(ground_low <= high, axis=1))
        for ground_index in candidates:
            overlap = _clip_convex(subject, ground_xz[ground_index])
            if len(overlap) < 3 or _area_xz(overlap[:, :2]) <= 0.:
                continue
            xz = overlap[:, :2]
            base_y = _affine_triangle_height(base_face, xz)
            raised_y = _affine_triangle_height(raised_face, xz)
            ground_y = _affine_triangle_height(ground_faces[ground_index], xz)
            gaps = base_y - ground_y
            gains = (raised_y - base_y) / control_delta
            constraints += len(xz)
            for vertex, (gap, gain) in enumerate(zip(gaps, gains)):
                needed = float(minimum_gap_metres) - float(gap)
                if needed <= 0.:
                    continue
                if gain <= 0.:
                    raise CoastalGeometryError(
                        "terrain penetration cannot be cleared by the profile control",
                        floorTriangle=int(floor_index), terrainTriangle=int(ground_index),
                        xz=xz[vertex], gapMetres=float(gap), controlGain=float(gain))
                delta = needed / float(gain)
                if delta > required_delta:
                    required_delta = delta
                    limiting = {"floorTriangle": int(floor_index),
                                "terrainTriangle": int(ground_index),
                                "xz": xz[vertex], "baseGapMetres": float(gap),
                                "controlGain": float(gain)}
    if not constraints:
        raise CoastalGeometryError("terrain lower-bound solve has no final-terrain overlap")
    height = float(np.nextafter(np.float32(low_control + required_delta), np.float32(np.inf)))
    return {"acceptanceAuthority": False,
            "authority": "actual shared-topology float32 floor response against final float32 affine terrain",
            "role": "construction lower bound; final encoded terrain-clearance evidence remains required",
            "minimumGapMetres": float(minimum_gap_metres),
            "baseControlHeightMetres": low_control,
            "requiredControlHeightMetres": height,
            "constraintCount": constraints, "limitingConstraint": limiting}


def emitted_water_height_upper_bound(surface: SurfaceGeometry,
                                     water_groups: Mapping[str, np.ndarray]) -> dict:
    """Maximum actual emitted-water height under a positive floor overlap."""
    maximum = -math.inf; witness = None; pieces = 0
    for kind, faces in water_groups.items():
        faces = _array(faces, (3, 3), f"{kind} water triangles").astype(np.float32).astype(np.float64)
        if not len(faces):
            continue
        water_xz = faces[:, :, [0, 2]]
        water_low = water_xz.min(axis=1); water_high = water_xz.max(axis=1)
        for floor_index, floor in enumerate(surface.encoded_triangles):
            floor_xz = floor[:, [0, 2]]
            low, high = floor_xz.min(axis=0), floor_xz.max(axis=0)
            candidates = np.flatnonzero(np.all(water_high >= low, axis=1) &
                                        np.all(water_low <= high, axis=1))
            for water_index in candidates:
                subject = np.c_[faces[water_index, :, 0], faces[water_index, :, 2],
                                faces[water_index, :, 1]]
                overlap = _clip_convex(subject, floor_xz)
                if len(overlap) < 3 or _area_xz(overlap[:, :2]) <= 0.:
                    continue
                pieces += 1
                index = int(np.argmax(overlap[:, 2])); value = float(overlap[index, 2])
                if value > maximum:
                    maximum = value
                    witness = {"kind": str(kind), "floorTriangle": int(floor_index),
                               "waterTriangle": int(water_index), "xz": overlap[index, :2],
                               "heightMetres": value}
    if pieces == 0:
        raise CoastalGeometryError("coastal floor has no positive emitted-water overlap",
                                   roadId=surface.road_id)
    return {"acceptanceAuthority": True,
            "authority": "actual emitted float32 water over positive actual floor overlap",
            "maximumHeightMetres": float(maximum), "overlapPieceCount": pieces,
            "witness": witness}


def solve_broad_middle_surface(name: str, kind: str, road_id: str, points, half_width: float,
                               start_station: float, wet_extent_metres: Sequence[float],
                               end_station: float, fitted_join_heights_metres: Sequence[float],
                               terrain: TerrainPatch, water_groups: Mapping[str, np.ndarray],
                               minimum_water_clearance_metres: float,
                               positive_crown_rise_metres: float,
                               outline_factory: Callable,
                               *, adjustable_endpoint: str = "right",
                               domain_classifier: Callable,
                               multi_contact_intervals_metres: Sequence[Sequence[float]] = (),
                               minimum_join_gap_metres: float = .025,
                               maximum_join_gap_metres: float = .3):
    """Build a broad crown and solve one bank control against final terrain.

    The bank fitter supplies the two starting heights.  This bounded second
    solve may raise one endpoint only within the actual emitted join's legal
    contact band.  Every trial is rebuilt from the exact RoadOutline union;
    only the final encoded terrain/water/join/coverage checks accept it.
    """
    if adjustable_endpoint not in {"left", "right"}:
        raise CoastalGeometryError("broad-middle endpoint control is invalid",
                                   adjustableEndpoint=adjustable_endpoint)
    points = _array(points, (3,), "road points")
    start, end = float(start_station), float(end_station)
    wet_start, wet_end = map(float, wet_extent_metres)
    fitted = np.asarray(fitted_join_heights_metres, dtype=np.float64)
    if fitted.shape != (2,) or not np.isfinite(fitted).all():
        raise CoastalGeometryError("broad-middle fitted join heights are invalid")
    if not start < wet_start <= wet_end < end:
        raise CoastalGeometryError("broad-middle wet extent is outside its dry joins",
                                   wetExtentMetres=[wet_start, wet_end],
                                   joinStationsMetres=[start, end])
    if not 0. < float(positive_crown_rise_metres):
        raise CoastalGeometryError("coastal crown rise must be positive")
    grouped_intervals = np.asarray(multi_contact_intervals_metres, dtype=np.float64)
    if grouped_intervals.size:
        if (grouped_intervals.ndim != 2 or grouped_intervals.shape[1:] != (2,) or
                len(grouped_intervals) < 2 or
                np.any(grouped_intervals[:, 0] > grouped_intervals[:, 1]) or
                np.any(grouped_intervals[1:, 0] <= grouped_intervals[:-1, 1])):
            raise CoastalGeometryError("grouped coastal contact intervals are invalid",
                                       contactIntervalsMetres=grouped_intervals)
    else:
        grouped_intervals = np.empty((0, 2), dtype=np.float64)
    all_water = [np.asarray(value, dtype=np.float64) for value in water_groups.values() if len(value)]
    if not all_water:
        raise CoastalGeometryError("broad-middle solve has no emitted-water authority")
    all_water = np.concatenate(all_water, axis=0)
    crown_station = (wet_start + wet_end) * .5

    preview, _, _ = indexed_road_union_surface(
        name + "_WaterAuthority", "probe", road_id, points, half_width, start, end,
        np.asarray([start, end]), np.zeros(2), outline_factory, [[start, end, []]])
    water_height = emitted_water_height_upper_bound(preview, water_groups)

    def build(left_height, right_height, crown_height, suffix):
        profile = SmoothArchProfile(start, crown_station, end, left_height, crown_height,
                                    right_height)
        stations, heights, bands = broad_middle_profile_table(
            points, half_width, start, wet_start, crown_station, wet_end, end, profile)
        surface, metadata, authority = indexed_road_union_surface(
            name + suffix, kind, road_id, points, half_width, start, end,
            stations, heights, outline_factory, bands)
        return surface, metadata, authority, stations, heights, bands

    def candidate(control_height, suffix):
        joins = fitted.copy()
        joins[0 if adjustable_endpoint == "left" else 1] = float(control_height)
        crown_floor = max(float(joins.max()),
                          float(water_height["maximumHeightMetres"]) +
                          float(minimum_water_clearance_metres))
        base_crown = crown_floor + float(positive_crown_rise_metres)
        base = build(*joins, base_crown, suffix + "_Base")[0]
        control_step = max(.01, float(np.spacing(np.float32(base_crown))) * 16.)
        raised = build(*joins, base_crown + control_step, suffix + "_Raised")[0]
        lower = terrain_control_height_lower_bound(
            base, raised, terrain, base_crown, base_crown + control_step)
        crown_height = max(base_crown, float(lower["requiredControlHeightMetres"]))
        surface, metadata, authority, stations, heights, bands = build(
            *joins, crown_height, suffix)
        terrain_evidence = encoded_terrain_clearance_evidence(surface, terrain)
        join_evidence = encoded_full_width_join_evidence(
            surface, terrain, minimum_gap_metres=minimum_join_gap_metres,
            maximum_gap_metres=maximum_join_gap_metres, water_triangles=all_water)
        water_evidence = emitted_water_evidence(
            surface, water_groups,
            minimum_clearance_metres=minimum_water_clearance_metres)
        water_evidence = dict(domain_classifier(water_evidence))
        if not water_evidence.get("pureSea"):
            raise CoastalGeometryError("coastal endpoint solve has non-sea water contact",
                                       contactKinds=water_evidence.get("contactKinds"),
                                       nonSeaContactKinds=water_evidence.get("nonSeaContactKinds"))
        actual_intervals = np.asarray(
            water_evidence.get("continuousStationIntervalsMetres", ()), dtype=np.float64)
        grouped_contact_clear = bool(
            len(grouped_intervals) and not water_evidence.get("continuous") and
            water_evidence.get("clearanceClear") is True and
            np.array_equal(actual_intervals, grouped_intervals))
        coverage = partitioned_road_outline_coverage_evidence(
            surface, authority["nominalOutlineRecords"], authority["sourcePartitionXZ"])
        clear = bool(terrain_evidence["clear"] and join_evidence["clear"] and
                     (water_evidence["clear"] or grouped_contact_clear) and coverage["clear"])
        return {"clear": clear, "surface": surface, "metadata": metadata,
                "authority": authority, "stations": stations, "heights": heights,
                "bands": bands, "joinHeights": joins, "crownHeight": crown_height,
                "terrainControlLowerBound": lower, "terrainClearance": terrain_evidence,
                "fullWidthJoins": join_evidence, "emittedWater": water_evidence,
                "groupedContactIntervalsMatched": grouped_contact_clear,
                "capsuleCoverage": coverage}

    control_index = 0 if adjustable_endpoint == "left" else 1
    initial = float(fitted[control_index]); attempts = []

    def attempt(value, suffix):
        try:
            result = candidate(value, suffix)
            attempts.append({"controlHeightMetres": float(value), "clear": result["clear"],
                             "minimumTerrainGapMetres":
                                 result["terrainClearance"]["minimumGapMetres"],
                             "minimumJoinGapMetres": result["fullWidthJoins"]["minimumGapMetres"],
                             "maximumJoinGapMetres": result["fullWidthJoins"]["maximumGapMetres"]})
            return result
        except CoastalGeometryError as error:
            attempts.append({"controlHeightMetres": float(value), "clear": False,
                             "failure": error.witness})
            return None

    low_result = attempt(initial, "_ControlLow")
    if low_result is not None:
        side = low_result["fullWidthJoins"]["joins"][control_index]
    else:
        # The minimum-water crown always exists before the terrain-derived
        # crown is applied, and is sufficient to derive the legal cap range.
        joins = fitted.copy()
        base_crown = max(float(joins.max()),
                         float(water_height["maximumHeightMetres"]) +
                         float(minimum_water_clearance_metres)) + float(positive_crown_rise_metres)
        cap_surface = build(*joins, base_crown, "_CapRange")[0]
        cap_evidence = encoded_full_width_join_evidence(
            cap_surface, terrain, minimum_gap_metres=minimum_join_gap_metres,
            maximum_gap_metres=maximum_join_gap_metres, water_triangles=all_water)
        side = cap_evidence["joins"][control_index]
    headroom = float(maximum_join_gap_metres) - float(side["maximumGapMetres"])
    if headroom < 0.:
        raise CoastalGeometryError("fitted coastal join already exceeds its contact band",
                                   side=adjustable_endpoint, join=side)
    if low_result is not None and low_result["clear"]:
        final = low_result
    else:
        final = None; high = float(np.nextafter(np.float32(initial + headroom),
                                               np.float32(-np.inf)))
        # These controls are fractions of the actual encoded join's remaining
        # legal contact band.  Stop at the first fully checked result instead
        # of chasing an ULP-minimal terrain gap with dozens of constructions.
        controls = [float(np.float32(initial + headroom * fraction))
                    for fraction in (.5, .75)] + [high]
        for index, value in enumerate(dict.fromkeys(controls)):
            if value <= initial or value > high:
                continue
            result = attempt(value, f"_Control{index:02d}")
            if result is not None and result["clear"]:
                final = result
                break
        if final is None:
            raise CoastalGeometryError(
                "coastal endpoint height control cannot clear final geometry within its join band",
                side=adjustable_endpoint, fittedHeightMetres=initial,
                maximumControlHeightMetres=high, attempts=attempts)

    profile_grade = (float(np.max(np.abs(np.diff(final["heights"]) /
                                         np.diff(final["stations"]))))
                     if len(final["stations"]) > 1 else 0.)
    report = {"acceptanceAuthority": False,
              "role": "bounded construction solve; contained exact evidence carries acceptance",
              "adjustableEndpoint": adjustable_endpoint,
              "fitDeckHeightsMetres": fitted,
              "finalDeckHeightsMetres": final["joinHeights"],
              "endpointHeightAdjustmentsMetres": final["joinHeights"] - fitted,
              "crownHeightMetres": float(final["crownHeight"]),
              "positiveCrownRiseMetres": float(positive_crown_rise_metres),
              "maximumGrade": profile_grade,
              "waterHeightAuthority": water_height,
              "terrainControlLowerBound": final["terrainControlLowerBound"],
              "groupedContactIntervalsMetres": grouped_intervals,
              "groupedContactIntervalsMatched": final["groupedContactIntervalsMatched"],
              "attempts": attempts,
              "evidence": {key: final[key] for key in
                           ("capsuleCoverage", "emittedWater", "fullWidthJoins",
                            "terrainClearance")}}
    return final["surface"], final["metadata"], final["authority"], report


def prepare_component501_surface(road: Mapping, join_stations_metres: Sequence[float],
                                 wet_extent_metres: Sequence[float],
                                 fitted_join_heights_metres: Sequence[float],
                                 terrain: TerrainPatch, water_groups: Mapping[str, np.ndarray],
                                 minimum_water_clearance_metres: float,
                                 positive_crown_rise_metres: float,
                                 outline_factory: Callable,
                                 domain_classifier: Callable):
    """Prepare component 501's final positive-crown floor after its bank fit."""
    if road.get("id") != COMPONENT501_ROAD or float(road.get("width", math.nan)) != 4.:
        raise CoastalGeometryError("component 501 surface received the wrong road authority",
                                   roadId=road.get("id"), halfWidthMetres=road.get("width"))
    if _road_xz_sha256(road["points"]) != COMPONENT501_CANDIDATE_XZ_SHA256:
        raise CoastalGeometryError("component 501 surface requires its bounded XZ edit")
    joins = np.asarray(join_stations_metres, dtype=np.float64)
    if joins.shape != (2,):
        raise CoastalGeometryError("component 501 join stations are invalid")
    return solve_broad_middle_surface(
        "Walk_Coastal501_Arch", "coastal-indexed-arch", COMPONENT501_ROAD,
        road["points"], 4., float(joins[0]), wet_extent_metres, float(joins[1]),
        fitted_join_heights_metres, terrain, water_groups,
        minimum_water_clearance_metres, positive_crown_rise_metres,
        outline_factory, adjustable_endpoint="right",
        domain_classifier=domain_classifier)


def component502_terminal_platform_start(points, half_width: float) -> float:
    """Start the level terminal pad at the last bend's exact miter extent."""
    points = _array(points, (3,), "component 502 road points")
    if len(points) < 3:
        raise CoastalGeometryError("component 502 terminal has no incoming bend")
    distances = cumulative_stations(points)
    directions = np.diff(points[:, [0, 2]], axis=0)
    lengths = np.linalg.norm(directions, axis=1)
    if (lengths <= 0.).any():
        raise CoastalGeometryError("component 502 terminal route contains a zero-length segment")
    directions /= lengths[:, None]
    turn = math.acos(float(np.clip(directions[-2] @ directions[-1], -1., 1.)))
    half_run = float(half_width) * math.tan(turn * .5)
    incoming_run = float(distances[-2] - distances[-3])
    if not 0. < half_run < incoming_run:
        raise CoastalGeometryError("component 502 terminal bend has no bounded level-pad approach",
                                   turnRadians=turn, halfRunMetres=half_run,
                                   incomingRunMetres=incoming_run)
    return float(distances[-2] - half_run)


def prepare_component502_surface(road: Mapping, landward_join_station_metres: float,
                                 wet_extent_metres: Sequence[float], terrain: TerrainPatch,
                                 water_groups: Mapping[str, np.ndarray],
                                 minimum_water_clearance_metres: float,
                                 positive_crown_rise_metres: float,
                                 outline_factory: Callable, domain_classifier: Callable):
    """Build the one-bank component-502 arch and its supported round terminal.

    The source road genuinely ends over water.  Its final RoadOutline capsule
    is retained as a level supported platform; only the landward side is a dry
    terrain join.
    """
    canonical = canonical_road_record(road)
    if canonical["id"] != COMPONENT502_ROAD or canonical["width"] != 1.65:
        raise CoastalGeometryError("component 502 surface received the wrong road authority",
                                   roadId=canonical["id"], halfWidthMetres=canonical["width"])
    points = np.asarray(canonical["points"], dtype=np.float64)
    distances = cumulative_stations(points)
    start = float(landward_join_station_metres); end = float(distances[-1])
    wet_start, wet_end = map(float, wet_extent_metres)
    if not distances[0] <= start < wet_start <= wet_end == end:
        raise CoastalGeometryError("component 502 wet extent does not reach its authored terminal",
                                   wetExtentMetres=[wet_start, wet_end],
                                   joinStationMetres=start, terminalStationMetres=end)
    if wet_start - start > 6.:
        raise CoastalGeometryError("component 502 landward landing exceeds its source rule",
                                   landingMetres=wet_start - start, limitMetres=6.)
    terminal_segment_start = float(distances[-2])
    platform_start = component502_terminal_platform_start(points, canonical["width"])
    if not wet_start < platform_start < end:
        raise CoastalGeometryError("component 502 has no distinct final terminal platform segment",
                                   platformStartMetres=platform_start)
    if not 0. < float(positive_crown_rise_metres):
        raise CoastalGeometryError("component 502 crown rise must be positive")

    preview, _, _ = indexed_road_union_surface(
        "Walk_Coastal502_ContactPreview", "coastal-terminal-preview", canonical["id"],
        points, canonical["width"], start, end, np.asarray([start, end]), np.zeros(2),
        outline_factory, terminal_sides=("right",))
    contact_samples = np.unique(np.concatenate(
        [_terrain_edge_samples(edge, terrain) for edge in preview.join_edges[0]]), axis=0)
    contact_ground = terrain.height_at(contact_samples[:, [0, 2]])
    contact_low = float(contact_ground.max() + .025)
    contact_high = float(contact_ground.min() + .3)
    if contact_low > contact_high:
        raise CoastalGeometryError("component 502 landward bank has no flat contact height",
                                   minimumDeckHeightMetres=contact_low,
                                   maximumDeckHeightMetres=contact_high,
                                   minimumTerrainHeightMetres=float(contact_ground.min()),
                                   maximumTerrainHeightMetres=float(contact_ground.max()))
    deck_height = float(np.float32((contact_low + contact_high) * .5))
    all_water = [np.asarray(value, dtype=np.float64) for value in water_groups.values() if len(value)]
    if not all_water:
        raise CoastalGeometryError("component 502 has no emitted-water authority")
    all_water = np.concatenate(all_water, axis=0)
    water_height = emitted_water_height_upper_bound(preview, water_groups)
    crown_height = max(deck_height, water_height["maximumHeightMetres"] +
                       float(minimum_water_clearance_metres)) + float(positive_crown_rise_metres)
    crown_station = (wet_start + platform_start) * .5
    profile = SmoothArchProfile(start, crown_station, platform_start,
                                deck_height, crown_height, deck_height)
    profile_stations = canonical_stations(points, start, platform_start,
                                          DEFAULT_STATION_SPACING_METRES)
    profile_heights = profile.height(profile_stations)
    profile_stations = np.r_[profile_stations, end]
    profile_heights = np.r_[profile_heights, deck_height]
    surface, metadata, authority = indexed_road_union_surface(
        "Walk_Coastal502_Terminal", "coastal-supported-terminal", canonical["id"],
        points, canonical["width"], start, end, profile_stations, profile_heights,
        outline_factory, level_bands=((platform_start, end, (platform_start,)),),
        terminal_sides=("right",))
    coverage = partitioned_road_outline_coverage_evidence(
        surface, authority["nominalOutlineRecords"], authority["sourcePartitionXZ"])
    water = dict(domain_classifier(emitted_water_evidence(
        surface, water_groups, minimum_clearance_metres=minimum_water_clearance_metres)))
    if not water.get("pureSea"):
        raise CoastalGeometryError("component 502 terminal has non-sea water contact",
                                   contactKinds=water.get("contactKinds"),
                                   nonSeaContactKinds=water.get("nonSeaContactKinds"))
    terrain_clearance = encoded_terrain_clearance_evidence(surface, terrain)
    joins = encoded_full_width_join_evidence(
        surface, terrain, water_triangles=all_water, sides=("left",))

    terminal_faces = surface.encoded_triangles[
        np.all(surface.triangle_stations >= platform_start, axis=1)]
    terminal_floor = shapely.union_all([Polygon(face[:, [0, 2]]) for face in terminal_faces])
    if not isinstance(terminal_floor, Polygon) or len(terminal_floor.interiors):
        raise CoastalGeometryError("component 502 terminal platform is not one hole-free floor",
                                   geometryType=terminal_floor.geom_type)
    support = _support_polygon_record(
        "Walk_Coastal502_TerminalSupport", "terminal-platform-support",
        terminal_floor, deck_height, terrain)
    support_evidence = support_records_contact_evidence((support,))
    support_floor = Polygon(support.footprint_xz)
    endpoint = points[-1, [0, 2]].astype(np.float32).astype(np.float64)
    tangent = points[-1, [0, 2]] - points[-2, [0, 2]]
    tangent /= np.linalg.norm(tangent)
    terminal_xz = terminal_faces[:, :, [0, 2]].reshape(-1, 2)
    overhang = float(np.max((terminal_xz - endpoint) @ tangent))
    terminal_evidence = {
        "acceptanceAuthority": True,
        "clear": bool(terminal_floor.equals(support_floor) and overhang > 0. and
                      not surface.join_edges[1] and support_evidence["clear"]),
        "authority": "actual level terminal floor footprint and final-terrain support geometry",
        "platformStartMetres": platform_start, "terminalStationMetres": end,
        "floorAreaSquareMetres": float(terminal_floor.area),
        "supportAreaSquareMetres": float(support_floor.area),
        "roundCapOverhangMetres": overhang,
        "terminalJoinEdgeCount": len(surface.join_edges[1]),
    }
    clear = bool(coverage["clear"] and water["clear"] and terrain_clearance["clear"] and
                 joins["clear"] and support_evidence["clear"] and terminal_evidence["clear"])
    report = {
        "acceptanceAuthority": False, "clear": clear,
        "role": "component 502 one-bank terminal construction; contained evidence carries acceptance",
        "landwardJoinStationMetres": start, "wetExtentMetres": [wet_start, wet_end],
        "terminalStationMetres": end, "terminalPlatformStartMetres": platform_start,
        "terminalSourceSegmentStartMetres": terminal_segment_start,
        "landwardDeckContactIntervalMetres": [contact_low, contact_high],
        "deckHeightMetres": deck_height, "crownStationMetres": crown_station,
        "crownHeightMetres": crown_height,
        "positiveCrownRiseMetres": float(positive_crown_rise_metres),
        "profileStationsMetres": profile_stations, "profileHeightsMetres": profile_heights,
        "evidence": {"capsuleCoverage": coverage, "emittedWater": water,
                     "fullWidthJoins": joins, "terrainClearance": terrain_clearance,
                     "supportContact": support_evidence,
                     "terminalPlatform": terminal_evidence},
    }
    if not clear:
        raise CoastalGeometryError("component 502 terminal surface failed final geometry",
                                   report=report)
    return surface, support, metadata, authority, report


def route_search_bounds(points, half_width: float, intervals: Sequence[Sequence[float]], guard: float = 0.) -> np.ndarray:
    """Bounds to crop before any route evidence is calculated."""
    points = _array(points, (3,), "road points"); distances = cumulative_stations(points)
    sections = []
    for low, high in intervals:
        stations = canonical_stations(points, float(low), float(high), max(float(high) - float(low), .5))
        sections.extend(_section(points, distances, station, half_width) for station in stations)
    xz = np.asarray(sections)[:, :, [0, 2]].reshape(-1, 2)
    return np.r_[xz.min(axis=0) - float(guard), xz.max(axis=0) + float(guard)]


def _capsule_polygon(a, b, radius, arc_steps=12):
    a = np.asarray(a, dtype=np.float64); b = np.asarray(b, dtype=np.float64)
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    arc = angle + np.linspace(-math.pi * .5, math.pi * .5, int(arc_steps) + 1)
    return np.concatenate((np.c_[b[0] + radius * np.cos(arc), b[1] + radius * np.sin(arc)],
                           np.c_[a[0] - radius * np.cos(arc), a[1] - radius * np.sin(arc)]))


def _route_interval_points(points, start_station, end_station):
    points = _array(points, (3,), "road points"); stations = cumulative_stations(points)
    start, start_index, _ = _point_at(points, stations, start_station)
    end, end_index, _ = _point_at(points, stations, end_station)
    interior = points[start_index + 1:end_index + 1]
    result = np.concatenate(([start], interior, [end]))
    keep = np.r_[True, np.linalg.norm(np.diff(result[:, [0, 2]], axis=0), axis=1) > 0]
    return result[keep]


def _cross2(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _line_intersection(point_a, direction_a, point_b, direction_b):
    denominator = _cross2(direction_a, direction_b)
    if denominator == 0:
        raise CoastalGeometryError("road bend has parallel offset lines")
    distance = _cross2(np.asarray(point_b) - np.asarray(point_a), direction_b) / denominator
    return np.asarray(point_a) + distance * np.asarray(direction_a)


def _arc_between(center, first, second, counterclockwise, radius):
    start = math.atan2(first[1], first[0]); end = math.atan2(second[1], second[0])
    if counterclockwise:
        while end <= start:
            end += 2. * math.pi
    else:
        while end >= start:
            end -= 2. * math.pi
    count = max(1, int(math.ceil(abs(end - start) / (math.pi / 12.))))
    angles = np.linspace(start, end, count + 1)
    return np.asarray(center) + float(radius) * np.c_[np.cos(angles), np.sin(angles)]


def _buffer_boundary(points, half_width, start_station, end_station):
    route = _route_interval_points(points, start_station, end_station)
    xz = route[:, [0, 2]].astype(np.float32).astype(np.float64)
    directions = np.diff(xz, axis=0)
    directions /= np.linalg.norm(directions, axis=1)[:, None]
    normals = np.c_[-directions[:, 1], directions[:, 0]]
    left = [xz[0] + normals[0] * half_width]
    right = [xz[0] - normals[0] * half_width]
    for index in range(1, len(xz) - 1):
        before, after = directions[index - 1], directions[index]
        turn = _cross2(before, after)
        if turn == 0:
            if np.dot(before, after) <= 0:
                raise CoastalGeometryError("road interval reverses within its capsule platform")
            left.append(xz[index] + normals[index] * half_width)
            right.append(xz[index] - normals[index] * half_width)
            continue
        if turn > 0:
            left.append(_line_intersection(xz[index] + normals[index - 1] * half_width, before,
                                           xz[index] + normals[index] * half_width, after))
            # The first tangent is a new boundary vertex at this bend.  The
            # prior entry belongs to the preceding bend (or route endpoint),
            # so dropping it shaves a positive outer shoulder.
            right.extend(_arc_between(xz[index], -normals[index - 1], -normals[index], True,
                                      half_width))
        else:
            left.extend(_arc_between(xz[index], normals[index - 1], normals[index], False,
                                     half_width))
            right.append(_line_intersection(xz[index] - normals[index - 1] * half_width, before,
                                            xz[index] - normals[index] * half_width, after))
    left.append(xz[-1] + normals[-1] * half_width)
    right.append(xz[-1] - normals[-1] * half_width)
    boundary = np.concatenate((np.asarray(left), np.asarray(right)[::-1]))
    boundary = _normalize_polygon_xz(boundary.astype(np.float32).astype(np.float64))
    if _signed_area_xz(boundary) < 0:
        boundary = boundary[::-1].copy()
    return boundary


def _point_in_ccw_triangle(point, triangle):
    return all(_cross2(b - a, point - a) >= 0 for a, b in zip(triangle, np.roll(triangle, -1, axis=0)))


def _triangulate_boundary(boundary):
    boundary = _normalize_polygon_xz(boundary)
    indices = list(range(len(boundary))); result = []
    while len(indices) > 3:
        found = False
        for position in range(len(indices)):
            selected = [indices[position - 1], indices[position], indices[(position + 1) % len(indices)]]
            triangle = boundary[selected]
            if _signed_area_xz(triangle) <= 0:
                continue
            others = [index for index in indices if index not in selected]
            if any(_point_in_ccw_triangle(boundary[index], triangle) for index in others):
                continue
            result.append(triangle); indices.pop(position); found = True; break
        if not found:
            raise CoastalGeometryError("encoded road-capsule boundary is folded or self-intersecting")
    result.append(boundary[indices])
    return tuple(result)


def intended_capsule_pieces(points, half_width, start_station, end_station):
    """One encoded road buffer triangulated with globally shared boundary vertices."""
    return _triangulate_boundary(_buffer_boundary(points, half_width, start_station, end_station))


def _boundary_edges(triangles):
    occurrences = {}
    for triangle in triangles:
        for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
            a = tuple(map(float, a)); b = tuple(map(float, b))
            key = tuple(sorted((a, b)))
            occurrences.setdefault(key, []).append((a, b))
    invalid = [key for key, values in occurrences.items() if len(values) > 2]
    boundary = [values[0] for values in occurrences.values() if len(values) == 1]
    return boundary, invalid


def _edge_is_covered(edge, candidates):
    a, b = map(np.asarray, edge); delta = b - a
    component = int(np.argmax(np.abs(delta)))
    low, high = sorted((float(a[component]), float(b[component])))
    intervals = []
    for c, d in candidates:
        c = np.asarray(c); d = np.asarray(d)
        if _cross2(delta, c - a) != 0 or _cross2(delta, d - a) != 0:
            continue
        first, last = sorted((float(c[component]), float(d[component])))
        first, last = max(low, first), min(high, last)
        if first < last:
            intervals.append((first, last))
    intervals.sort()
    cursor = low
    for first, last in intervals:
        if first > cursor:
            return False
        cursor = max(cursor, last)
        if cursor >= high:
            return True
    return cursor >= high


def _positive_triangle_overlap(first, second):
    for triangle in (first, second):
        for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
            normal = np.array([-(b - a)[1], (b - a)[0]])
            # Shift to this edge before projecting.  Absolute continent
            # coordinates can cancel enough low bits to turn a shared edge
            # into an invented positive overlap.
            one = (np.asarray(first) - a) @ normal
            two = (np.asarray(second) - a) @ normal
            if one.max() <= two.min() or two.max() <= one.min():
                return False
    return True


def _closest_route_stations(points, query_xz):
    points = _array(points, (3,), "road points")
    route = points[:, [0, 2]].astype(np.float32).astype(np.float64)
    stations = cumulative_stations(np.c_[route[:, 0], points[:, 1], route[:, 1]])
    query = _array(query_xz, (2,), "station query")
    best_distance = np.full(len(query), np.inf); best_station = np.zeros(len(query))
    for index, (a, b) in enumerate(zip(route, route[1:])):
        delta = b - a; length_squared = float(np.dot(delta, delta))
        if length_squared == 0:
            continue
        ratio = np.clip((query - a) @ delta / length_squared, 0., 1.)
        projected = a + ratio[:, None] * delta
        distance = np.sum((query - projected) ** 2, axis=1)
        use = distance < best_distance
        best_distance[use] = distance[use]
        best_station[use] = stations[index] + ratio[use] * math.sqrt(length_squared)
    return best_station


def level_capsule_surface(name: str, kind: str, road_id: str, points, half_width: float,
                          start_station: float, end_station: float, height: float) -> SurfaceGeometry:
    """One level platform over an exact disjoint encoded road-capsule union.

    This is the production representation for a bent coastal band whose two
    joins can share one legal height.  Every bend is part of the same platform,
    so nonadjacent strips can neither overlap nor disagree in height.
    """
    points = _array(points, (3,), "road points")
    polygons = intended_capsule_pieces(points, half_width, start_station, end_station)
    triangles, triangle_stations = [], []
    encoded_height = float(np.float32(height))
    for polygon in polygons:
        vertices = np.c_[polygon[:, 0], np.full(len(polygon), encoded_height), polygon[:, 1]]
        for face in _oriented_fan(vertices, True):
            triangles.append(face)
            triangle_stations.append(_closest_route_stations(points, face[:, [0, 2]]))
    if not triangles:
        raise CoastalGeometryError("level coastal platform has no capsule floor", roadId=road_id)
    distances = cumulative_stations(points)
    sections = np.stack((_section(points, distances, start_station, half_width),
                         _section(points, distances, end_station, half_width))).astype(np.float32).astype(np.float64)
    sections[:, :, 1] = encoded_height
    surface = SurfaceGeometry(name, kind, road_id, np.asarray([start_station, end_station]), sections,
                              np.asarray(triangles), np.asarray(triangle_stations))
    _check_encoded_grade(surface.triangles, MAXIMUM_GRADE)
    require_complete_capsule_coverage(floor_capsule_coverage_evidence(
        surface, points, half_width, start_station, end_station))
    return surface


def floor_capsule_coverage_evidence(surface: SurfaceGeometry, points, half_width,
                                    start_station, end_station) -> dict:
    """Check float32 triangulation against this module's canonical buffer.

    This is a construction self-check, not independent existing-road
    authority.  ``floor_road_outline_coverage_evidence`` supplies that gate.
    """
    intended = intended_capsule_pieces(points, half_width, start_station, end_station)
    floors = tuple(face[:, [0, 2]] for face in surface.encoded_triangles)
    floor_boundary, floor_nonmanifold = _boundary_edges(floors)
    intended_boundary, intended_nonmanifold = _boundary_edges(intended)
    floor_boundary_mismatch = [edge for edge in floor_boundary if not _edge_is_covered(edge, intended_boundary)]
    intended_boundary_mismatch = [edge for edge in intended_boundary if not _edge_is_covered(edge, floor_boundary)]
    extra = []
    for floor in floors:
        remaining = [floor]
        for polygon in intended:
            following = []
            for piece in remaining:
                following.extend(_subtract_convex(piece, polygon))
            remaining = following
            if not remaining:
                break
        for piece in remaining:
            piece = _normalize_polygon_xz(piece)
            if len(piece) >= 3 and _area_xz(piece) > 0:
                extra.append(piece)
    uncovered = []
    for polygon in intended:
        remaining = [polygon]
        for floor in floors:
            following = []
            for piece in remaining:
                following.extend(_subtract_convex(piece, floor))
            remaining = following
            if not remaining:
                break
        for piece in remaining:
            piece = _normalize_polygon_xz(piece)
            if len(piece) >= 3 and _area_xz(piece) > 0:
                uncovered.append(piece)
    overlaps = []
    for left in range(len(floors)):
        low_l, high_l = floors[left].min(axis=0), floors[left].max(axis=0)
        for right in range(left + 1, len(floors)):
            if right == left + 1 and left // 2 == right // 2:
                continue
            low_r, high_r = floors[right].min(axis=0), floors[right].max(axis=0)
            if (high_l < low_r).any() or (high_r < low_l).any():
                continue
            if _positive_triangle_overlap(floors[left], floors[right]):
                overlaps.append({"floorTriangles": [left, right], "positiveArea": True})
    boundary_clear = not (floor_boundary_mismatch or intended_boundary_mismatch or
                          floor_nonmanifold or intended_nonmanifold)
    arithmetic_remnants = {"extraPiecesXZ": extra, "uncoveredPiecesXZ": uncovered,
                            "extraAreaSquareMetres": float(sum(_area_xz(piece) for piece in extra)),
                            "uncoveredAreaSquareMetres": float(sum(_area_xz(piece) for piece in uncovered))}
    evidence = {
        "complete": boundary_clear and not overlaps,
        "clear": boundary_clear and not overlaps,
        "acceptanceAuthority": True, "encoded": True,
        "floorBoundaryMismatch": floor_boundary_mismatch,
        "intendedBoundaryMismatch": intended_boundary_mismatch,
        "floorNonmanifoldEdges": floor_nonmanifold,
        "intendedNonmanifoldEdges": intended_nonmanifold,
        "overlaps": overlaps,
        "arithmeticClipRemnants": arithmetic_remnants,
        "extraAreaSquareMetres": (0. if boundary_clear else arithmetic_remnants["extraAreaSquareMetres"]),
        "uncoveredAreaSquareMetres": (0. if boundary_clear else arithmetic_remnants["uncoveredAreaSquareMetres"]),
    }
    return evidence


def floor_road_outline_coverage_evidence(surface: SurfaceGeometry, outline_records,
                                         start_station: float, end_station: float) -> dict:
    """Compare encoded floor and existing RoadOutline unions with GEOS set operations."""
    floors = tuple(face[:, [0, 2]] for face in surface.encoded_triangles)
    for number, record in enumerate(outline_records):
        try:
            polygon = _array(record["xz"], (2,), "RoadOutline piece XZ")
            stations = _array(record["stations"], (), "RoadOutline piece stations").reshape(-1)
        except (KeyError, TypeError) as error:
            raise CoastalGeometryError("RoadOutline record lacks XZ/station authority",
                                       record=number) from error
        if len(polygon) != len(stations) or len(polygon) < 3 or _area_xz(polygon) <= 0:
            raise CoastalGeometryError("RoadOutline record is not one positive stationed polygon",
                                       record=number)
        outside = (stations < float(start_station)) | (stations > float(end_station))
        if outside.any():
            raise CoastalGeometryError("RoadOutline record left its named station interval",
                                       record=number, stationsMetres=stations[outside])
    intended = _road_outline_union_geometry(outline_records)
    floor_polygons = [Polygon(face) for face in floors]
    if any(not polygon.is_valid or polygon.area == 0. for polygon in floor_polygons):
        raise CoastalGeometryError("encoded coastal floor contains an invalid triangle")
    emitted = shapely.union_all(floor_polygons)
    extra_geometry = emitted.difference(intended)
    uncovered_geometry = intended.difference(emitted)

    def positive_exteriors(geometry):
        return [np.asarray(part.exterior.coords[:-1], dtype=np.float64)
                for part in shapely.get_parts(geometry)
                if isinstance(part, Polygon) and part.area > 0.]

    extra = positive_exteriors(extra_geometry); uncovered = positive_exteriors(uncovered_geometry)
    overlaps = []
    tree = shapely.STRtree(floor_polygons)
    pairs = tree.query(floor_polygons, predicate="intersects")
    for left, right in zip(*pairs):
        left, right = int(left), int(right)
        if left >= right: continue
        area = float(floor_polygons[left].intersection(floor_polygons[right]).area)
        if area > 0.:
            overlaps.append({"floorTriangles": [left, right], "positiveArea": True,
                             "areaSquareMetres": area})
    evidence = {
        "complete": not extra and not uncovered and not overlaps,
        "clear": not extra and not uncovered and not overlaps,
        "acceptanceAuthority": True,
        "encoded": True,
        "independentAuthority": "existing RoadOutline capsule union with source-segment stations",
        "outlinePieceCount": len(outline_records),
        "stationBoundsMetres": [float(start_station), float(end_station)],
        "extraPiecesXZ": extra,
        "uncoveredPiecesXZ": uncovered,
        "extraAreaSquareMetres": float(extra_geometry.area),
        "uncoveredAreaSquareMetres": float(uncovered_geometry.area),
        "overlaps": overlaps,
    }
    return evidence


def partitioned_road_outline_coverage_evidence(surface: SurfaceGeometry, nominal_outline_records,
                                                source_partition_xz=()) -> dict:
    """Independently bound the emitted floor between nominal and encoding-guard unions.

    The emitted faces are never compared with their own supplied partition.  A
    nominal union is built from the unencoded RoadOutline authority, while the
    allowed outer union is independently rebuilt with the caller's derived
    float32 construction guard.
    """
    nominal = _source_road_outline_union_geometry(nominal_outline_records)
    encoding_guard_metres = road_outline_encoding_guard(nominal_outline_records)
    allowed = nominal.buffer(2. * encoding_guard_metres)
    source_polygons = [Polygon(_array(value, (2,), "source partition polygon"))
                       for value in source_partition_xz]
    if any(not value.is_valid or value.area == 0. for value in source_polygons):
        raise CoastalGeometryError("partitioned RoadOutline authority contains an invalid polygon")
    source_union = shapely.union_all(source_polygons) if source_polygons else None
    floor_polygons = [Polygon(face[:, [0, 2]]) for face in surface.encoded_triangles]
    if any(not value.is_valid or value.area == 0. for value in floor_polygons):
        raise CoastalGeometryError("encoded coastal floor contains an invalid polygon")
    emitted = shapely.union_all(floor_polygons)
    nominal_uncovered = nominal.difference(emitted)
    outside_allowed = emitted.difference(allowed)
    overlaps = []
    tree = shapely.STRtree(floor_polygons)
    pairs = tree.query(floor_polygons, predicate="intersects")
    for left, right in zip(*pairs):
        left, right = int(left), int(right)
        if left >= right: continue
        area = float(floor_polygons[left].intersection(floor_polygons[right]).area)
        if area > 0.:
            overlaps.append({"floorTriangles": [left, right], "positiveArea": True,
                             "areaSquareMetres": area})
    complete = nominal_uncovered.is_empty and outside_allowed.is_empty and not overlaps
    return {"complete": complete, "clear": complete, "acceptanceAuthority": True, "encoded": True,
            "independentAuthority": "nominal RoadOutline contained in emitted floor; emitted floor contained in independently guarded RoadOutline",
            "encodingGuardMetres": encoding_guard_metres,
            "nominalUncoveredAreaSquareMetres": float(nominal_uncovered.area),
            "outsideAllowedGuardAreaSquareMetres": float(outside_allowed.area),
            "extraAreaSquareMetres": float(outside_allowed.area),
            "uncoveredAreaSquareMetres": float(nominal_uncovered.area),
            "sourcePartitionDiagnosticOnly": True,
            "sourcePartitionAreaSquareMetres": (None if source_union is None else float(source_union.area)),
            "sourcePartitionCount": len(source_polygons),
            "overlaps": overlaps}


def require_complete_capsule_coverage(evidence):
    if not evidence.get("complete", False):
        raise CoastalGeometryError("encoded coastal floor does not equal its road-capsule union",
                                   extraAreaSquareMetres=evidence.get("extraAreaSquareMetres"),
                                   uncoveredAreaSquareMetres=evidence.get("uncoveredAreaSquareMetres"),
                                   overlapCount=len(evidence.get("overlaps", ())))
    return evidence


@dataclass(frozen=True)
class StepPolicy:
    maximum_rise_metres: float
    minimum_tread_run_metres: float
    actor_height_metres: float
    actor_half_width_metres: float
    floor_clearance_metres: float
    authority: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        values = (self.maximum_rise_metres, self.minimum_tread_run_metres, self.actor_height_metres,
                  self.actor_half_width_metres, self.floor_clearance_metres)
        if not all(math.isfinite(float(value)) and value > 0 for value in values):
            raise CoastalGeometryError("step policy must contain positive finite thresholds")


@dataclass(frozen=True)
class SupportRecord:
    name: str
    kind: str
    footprint_xz: np.ndarray
    top_height_metres: float
    base_heights_metres: np.ndarray
    triangles: np.ndarray
    contact_pieces_xz: tuple[np.ndarray, ...] = ()
    minimum_encoded_contact_margin_metres: float = 0.

    @property
    def encoded_triangles(self):
        return self.triangles.astype(np.float32).astype(np.float64)


@dataclass(frozen=True)
class StairGeometry:
    name: str
    road_id: str
    start_station: float
    end_station: float
    tread_surfaces: tuple[SurfaceGeometry, ...]
    riser_triangles: np.ndarray
    supports: tuple[SupportRecord, ...]
    policy: StepPolicy

    @property
    def encoded_floor_triangles(self):
        return np.concatenate([surface.encoded_triangles for surface in self.tread_surfaces], axis=0)


def support_records_contact_evidence(supports: Sequence[SupportRecord]) -> dict:
    details = []
    supports = tuple(supports)
    for support in supports:
        encoded = support.encoded_triangles
        normals = np.cross(encoded[:, 1] - encoded[:, 0], encoded[:, 2] - encoded[:, 0])
        downward = int(np.count_nonzero(normals[:, 1] < 0))
        details.append({"name": support.name, "contactPieceCount": len(support.contact_pieces_xz),
                        "minimumEncodedContactMarginMetres": support.minimum_encoded_contact_margin_metres,
                        "downwardFaceCount": downward})
    clear = bool(supports) and all(
        item["contactPieceCount"] > 0 and item["minimumEncodedContactMarginMetres"] >= 0 and
        item["downwardFaceCount"] > 0 for item in details)
    return {"acceptanceAuthority": True, "clear": clear, "supports": details}


def support_contact_evidence(stair: StairGeometry) -> dict:
    evidence = support_records_contact_evidence(stair.supports)
    evidence["clear"] = bool(evidence["clear"] and
                             len(stair.supports) == len(stair.tread_surfaces))
    return evidence


def _terrain_edge_samples(edge, terrain: TerrainPatch):
    """All grid and cell-diagonal breakpoints on one encoded XZ edge."""
    edge = _array(edge, (3,), "encoded join edge")
    a, b = edge[:, [0, 2]]; delta = b - a; parameters = [0., 1.]
    for values, component in ((terrain.x, 0), (terrain.z, 1)):
        if delta[component] != 0.:
            parameters.extend(float((value - a[component]) / delta[component]) for value in values
                              if 0. < (value - a[component]) / delta[component] < 1.)
    parameters = sorted(set(parameters)); extra = []
    for left, right in zip(parameters, parameters[1:]):
        middle = (left + right) * .5; point = a + middle * delta
        col = int(math.floor((point[0] - terrain.x[0]) / terrain.cell))
        row = int(math.floor((point[1] - terrain.z[0]) / terrain.cell))
        if not 0 <= col < len(terrain.x) - 1 or not 0 <= row < len(terrain.z) - 1: continue
        denominator = delta.sum()
        if denominator != 0.:
            value = (terrain.x[col] + terrain.z[row] + terrain.cell - a.sum()) / denominator
            if left < value < right: extra.append(float(value))
    parameters = np.asarray(sorted(set(parameters + extra)), dtype=np.float64)
    xz = a + parameters[:, None] * delta
    y = edge[0, 1] + parameters * (edge[1, 1] - edge[0, 1])
    return np.c_[xz[:, 0], y, xz[:, 1]]


def encoded_full_width_join_evidence(surface: SurfaceGeometry, terrain: TerrainPatch,
                                     *, minimum_gap_metres: float = .025,
                                     maximum_gap_metres: float = .3,
                                     right_surface: SurfaceGeometry | None = None,
                                     water_triangles: np.ndarray | None = None,
                                     sides: Sequence[str] = ("left", "right")) -> dict:
    """Check complete emitted join edges at every final-terrain breakpoint."""
    details = []
    water = (None if water_triangles is None else
             _array(water_triangles, (3, 3), "join water triangles").astype(np.float32).astype(np.float64))
    right_surface = surface if right_surface is None else right_surface
    sides = tuple(map(str, sides))
    if not sides or len(sides) != len(set(sides)) or not set(sides) <= {"left", "right"}:
        raise CoastalGeometryError("encoded coastal join side selection is invalid", sides=sides)
    candidates = {"left": (surface, float(surface.stations[0])),
                  "right": (right_surface, float(right_surface.stations[-1]))}
    for side in sides:
        owner, station = candidates[side]
        # Only incidence-one edges are part of the actual emitted outer boundary.
        # An interior profile/plateau edge can have both endpoints at the join
        # station, but it must not be accepted as a bank connection.
        incidence = {}
        for face, face_stations in zip(owner.encoded_triangles, owner.triangle_stations):
            encoded = face.astype(np.float32)
            for first, second in ((0, 1), (1, 2), (2, 0)):
                edge = encoded[[first, second]]
                key = tuple(sorted(tuple(value.tolist()) for value in edge))
                incidence.setdefault(key, []).append((edge, face_stations[[first, second]]))
        join_side = 0 if side == "left" else 1
        edges = [edge.astype(np.float32).astype(np.float64)
                 for edge in owner.join_edges[join_side]]
        if edges:
            for edge in edges:
                key = tuple(sorted(tuple(value.tolist()) for value in edge.astype(np.float32)))
                records = incidence.get(key, ())
                if len(records) != 1 or not np.all(records[0][1] == station):
                    raise CoastalGeometryError("carried coastal cap edge is not one emitted boundary edge",
                                               side=side, stationMetres=station,
                                               edgeXZ=edge[:, [0, 2]])
        else:
            target = (owner.start_section if side == "left" else owner.end_section).astype(
                np.float32).astype(np.float64)
            target_key = tuple(sorted(tuple(value.tolist()) for value in target.astype(np.float32)))
            direct = incidence.get(target_key, ())
            edges = [direct[0][0].astype(np.float64)] if len(direct) == 1 else []
        if not edges and not owner.join_edges[join_side]:
            target_line = LineString(target[:, [0, 2]])
            edges = [records[0][0].astype(np.float64) for records in incidence.values()
                     if len(records) == 1 and np.all(records[0][1] == station) and
                     target_line.covers(LineString(records[0][0][:, [0, 2]]))]
            covered = shapely.union_all([LineString(edge[:, [0, 2]]) for edge in edges])
            if not edges or not covered.equals(target_line):
                edges = []
        if not edges:
            raise CoastalGeometryError("encoded coastal join has no exact full-width cap edge", side=side,
                                       stationMetres=station)
        edges = tuple(edges)
        # Terrain/grid intersections are exact affine points on F32-emitted
        # edges.  Keep them in float64; re-encoding would move them off the
        # edge or diagonal and independently round their interpolated height.
        samples = np.unique(np.concatenate([_terrain_edge_samples(edge, terrain) for edge in edges]), axis=0)
        ground = terrain.height_at(samples[:, [0, 2]])
        gaps = samples[:, 1] - ground
        water_hits = []
        if water is not None:
            for edge_index, edge in enumerate(edges):
                line = LineString(edge[:, [0, 2]])
                for water_index, triangle in enumerate(water):
                    polygon = Polygon(triangle[:, [0, 2]])
                    if polygon.area > 0. and line.intersection(polygon).length > 0.:
                        water_hits.append({"edge": edge_index, "waterTriangle": water_index})
        details.append({"side": side, "stationMetres": station,
                        "encodedBoundaryXZ": samples[:, [0, 2]],
                        "encodedEdgeCount": len(edges),
                        "terrainBreakpointCount": len(samples),
                        "waterIntersections": water_hits,
                        "minimumGapMetres": float(gaps.min()),
                        "maximumGapMetres": float(gaps.max()),
                        "minimumGapXZ": samples[int(np.argmin(gaps)), [0, 2]],
                        "maximumGapXZ": samples[int(np.argmax(gaps)), [0, 2]],
                        "worstBankXZ": samples[int(np.argmax(gaps)), [0, 2]]})
    minimum = min(value["minimumGapMetres"] for value in details)
    maximum = max(value["maximumGapMetres"] for value in details)
    water_clear = water is not None and all(not value["waterIntersections"] for value in details)
    clear = minimum >= float(minimum_gap_metres) and maximum <= float(maximum_gap_metres) and water_clear
    worst = max(details, key=lambda value: value["maximumGapMetres"])
    return {"acceptanceAuthority": water is not None, "clear": clear,
            "authority": "actual emitted float32 guard-expanded floor edges against final float32 affine terrain and water",
            "minimumGapMetres": minimum, "maximumGapMetres": maximum,
            "waterClear": water_clear,
            "worstBankXZ": worst["worstBankXZ"], "joins": details}


def guarded_step_evidence(stair: StairGeometry, collision_result: Mapping[str, object]) -> dict:
    """Combine encoded stair geometry with current client/server collision proof.

    Geometry proves the rise/run limits.  The probe must separately exercise
    the current guarded client and server paths plus actor head volume against
    retained emitted solids; booleans without an authority record are rejected.
    """
    levels = np.asarray([surface.encoded_triangles[0, 0, 1] for surface in stair.tread_surfaces])
    rises = np.abs(np.diff(levels))
    runs = np.asarray([surface.end_section[:, [0, 2]].mean(axis=0) -
                       surface.start_section[:, [0, 2]].mean(axis=0)
                       for surface in stair.tread_surfaces])
    runs = np.linalg.norm(runs.astype(np.float32).astype(np.float64), axis=1)
    geometry_clear = (not len(rises) or float(rises.max()) <= stair.policy.maximum_rise_metres) and \
        bool((runs >= stair.policy.minimum_tread_run_metres).all())
    required = ("clientPassable", "serverPassable", "headClear", "guardsContinuous")
    authority = collision_result.get("authority")
    externally_clear = bool(authority) and all(collision_result.get(name) is True for name in required)
    return {"acceptanceAuthority": bool(authority), "clear": geometry_clear and externally_clear,
            "encodedGeometryClear": geometry_clear,
            "maximumEncodedRiseMetres": float(rises.max(initial=0.)),
            "minimumEncodedTreadRunMetres": float(runs.min(initial=math.inf)),
            "clientPassable": collision_result.get("clientPassable"),
            "serverPassable": collision_result.get("serverPassable"),
            "headClear": collision_result.get("headClear"),
            "guardsContinuous": collision_result.get("guardsContinuous"),
            "authority": authority}


class _ConstantProfile:
    def __init__(self, height): self.value = float(height)
    def height(self, stations): return np.full(np.asarray(stations).shape, self.value)


def _oriented_fan(vertices, upward):
    vertices = np.asarray(vertices, dtype=np.float64)
    result = []
    for index in range(1, len(vertices) - 1):
        face = vertices[[0, index, index + 1]]
        normal_y = float(np.cross(face[1] - face[0], face[2] - face[0])[1])
        if normal_y == 0:
            continue
        if (normal_y > 0) != bool(upward):
            face = face[[0, 2, 1]]
        result.append(face)
    return result


def _support_polygon_record(name, kind, footprint_polygon, top, terrain: TerrainPatch):
    """Close one exact encoded floor footprint down to final affine terrain."""
    if not isinstance(footprint_polygon, Polygon) or not footprint_polygon.is_valid or \
       footprint_polygon.area <= 0. or len(footprint_polygon.interiors):
        raise CoastalGeometryError("support footprint is not one positive hole-free polygon",
                                   support=name)
    footprint = _encoded_ring(footprint_polygon.exterior, "support footprint")
    footprint_polygon = Polygon(footprint)
    terrain_authority = shapely.box(float(terrain.x[0]), float(terrain.z[0]),
                                    float(terrain.x[-1]), float(terrain.z[-1]))
    if not terrain_authority.covers(footprint_polygon):
        uncovered = footprint_polygon.difference(terrain_authority)
        raise CoastalGeometryError("shore support footprint left its final terrain authority", support=name,
                                   uncoveredAreaSquareMetres=float(uncovered.area),
                                   footprintBounds=list(footprint_polygon.bounds),
                                   terrainAuthorityBounds=list(terrain_authority.bounds))
    ground_faces = terrain.triangles()
    ground_polygons = [Polygon(face[:, [0, 2]].astype(np.float32).astype(np.float64))
                       for face in ground_faces]
    tree = shapely.STRtree(ground_polygons)
    contact = []
    for ground_index in tree.query(footprint_polygon, predicate="intersects"):
        ground_index = int(ground_index)
        overlap = footprint_polygon.intersection(ground_polygons[ground_index])
        for part in shapely.get_parts(overlap):
            if isinstance(part, Polygon) and part.area > 0.:
                contact.append((np.asarray(part.exterior.coords[:-1], dtype=np.float64),
                                ground_faces[ground_index]))
    if not contact:
        raise CoastalGeometryError("shore support has no terrain-triangle contact", support=name)
    triangles, base_values, margins = [], [], []
    encoded_top = float(np.float32(top))
    contact_pieces = []
    for polygon, ground in contact:
        encoded_xz = polygon.astype(np.float32).astype(np.float64)
        # Encoding an intersection vertex can move it across the terrain
        # diagonal.  Query the final patch at that encoded coordinate instead
        # of extrapolating the source overlap face.
        ground_y = terrain.height_at(encoded_xz)
        # One float32 predecessor keeps the closed support at or below the
        # exact emitted terrain plane after its own coordinate encoding.
        bottom_y = np.nextafter(ground_y.astype(np.float32), np.float32(-np.inf)).astype(np.float64)
        if (bottom_y > encoded_top).any():
            raise CoastalGeometryError("shore tread is penetrated by its final terrain", support=name,
                                       topHeightMetres=encoded_top,
                                       maximumEncodedGroundMetres=float(bottom_y.max()))
        upper = np.c_[encoded_xz[:, 0], np.full(len(encoded_xz), encoded_top), encoded_xz[:, 1]]
        lower = np.c_[encoded_xz[:, 0], bottom_y, encoded_xz[:, 1]]
        local_faces = constrained_polygon_indices(encoded_xz)
        for local in local_faces:
            top_face = upper[np.asarray(local, int)]
            bottom_face = lower[np.asarray(local, int)]
            if np.cross(top_face[1] - top_face[0], top_face[2] - top_face[0])[1] < 0.:
                top_face = top_face[[0, 2, 1]]
            if np.cross(bottom_face[1] - bottom_face[0], bottom_face[2] - bottom_face[0])[1] > 0.:
                bottom_face = bottom_face[[0, 2, 1]]
            triangles.extend((top_face, bottom_face))
        for index in range(len(polygon)):
            following = (index + 1) % len(polygon)
            quad = np.array([upper[index], upper[following], lower[index], lower[following]])
            triangles.extend((quad[[0, 2, 1]], quad[[1, 2, 3]]))
        base_values.extend(bottom_y)
        margins.extend(ground_y - bottom_y)
        contact_pieces.append(encoded_xz)
    return SupportRecord(name, kind, footprint, encoded_top, np.asarray(base_values),
                         np.asarray(triangles, dtype=np.float64), tuple(contact_pieces), float(min(margins)))


def _support_record(name, kind, section_a, section_b, top, terrain: TerrainPatch):
    # The footprint is the actual float32 tread projection, not its source-double proxy.
    footprint = np.array([section_a[0, [0, 2]], section_a[1, [0, 2]],
                          section_b[1, [0, 2]], section_b[0, [0, 2]]],
                         dtype=np.float32).astype(np.float64)
    return _support_polygon_record(name, kind, Polygon(footprint), top, terrain)


def supported_shore_stair(name: str, road_id: str, points, half_width: float,
                          start_station: float, end_station: float,
                          start_height: float, end_height: float, policy: StepPolicy,
                          final_terrain: TerrainPatch) -> StairGeometry:
    """Build ordinary level treads and explicit risers on the continuing road.

    Tread count comes only from the supplied current collision/actor policy.
    Every tread gets a geometric support down to the supplied final terrain.
    """
    run = float(end_station) - float(start_station)
    rise = float(end_height) - float(start_height)
    if run <= 0 or rise == 0:
        raise CoastalGeometryError("shore stair needs positive run and nonzero rise")
    steps = int(math.ceil(abs(rise) / policy.maximum_rise_metres))
    tread_count = steps + 1
    tread_run = run / tread_count
    if tread_run < policy.minimum_tread_run_metres:
        raise CoastalGeometryError("continuing road is too short for legal guarded treads",
                                   runMetres=run, riseMetres=rise, requiredRisers=steps,
                                   availableTreadRunMetres=tread_run,
                                   minimumTreadRunMetres=policy.minimum_tread_run_metres)
    boundaries = np.linspace(start_station, end_station, tread_count + 1)
    levels = np.linspace(start_height, end_height, tread_count)
    points = _array(points, (3,), "road points"); distances = cumulative_stations(points)
    surfaces, supports, risers = [], [], []
    for index, (left, right, level) in enumerate(zip(boundaries, boundaries[1:], levels)):
        surface = road_surface(f"{name}_Tread_{index:02d}", "shore-tread", road_id, points, half_width,
                               left, right, _ConstantProfile(level), maximum_spacing=max(right - left, .5))
        surfaces.append(surface)
        supports.append(_support_record(f"{name}_Support_{index:02d}", "full-width-tread-support",
                                        surface.start_section, surface.end_section, float(level), final_terrain))
        if index:
            lower, upper = levels[index - 1], level
            section = surface.start_section.copy()
            low = section.copy(); high = section.copy(); low[:, 1] = min(lower, upper); high[:, 1] = max(lower, upper)
            quad = np.array([low[0], low[1], high[0], high[1]])
            # Vertical faces do not use the walk-floor winding rule.
            risers.extend((quad[[0, 1, 2]], quad[[1, 3, 2]]))
    return StairGeometry(name, road_id, float(start_station), float(end_station), tuple(surfaces),
                         np.asarray(risers, dtype=np.float64).reshape(-1, 3, 3), tuple(supports), policy)


@dataclass(frozen=True)
class RoadEdit:
    road_id: str
    changed_indices: tuple[int, ...]
    source_points: np.ndarray
    candidate_points: np.ndarray
    shift_metres: float

    def __post_init__(self):
        source = _array(self.source_points, (3,), "source road points")
        candidate = _array(self.candidate_points, (3,), "candidate road points")
        if source.shape != candidate.shape:
            raise CoastalGeometryError("road edit point arrays disagree")
        allowed = np.zeros(len(source), dtype=bool); allowed[list(self.changed_indices)] = True
        if not np.array_equal(source[~allowed], candidate[~allowed]):
            raise CoastalGeometryError("road edit changed a point outside its allowlist")
        if not np.array_equal(source[:, 1], candidate[:, 1]):
            raise CoastalGeometryError("road edit changed authored road heights")
        object.__setattr__(self, "source_points", source); object.__setattr__(self, "candidate_points", candidate)


def component501_road_edit(road: Mapping, shift_metres: float = COMPONENT501_CANDIDATE_SHIFT_METRES) -> RoadEdit:
    if road.get("id") != COMPONENT501_ROAD:
        raise CoastalGeometryError("component 501 edit received the wrong road", roadId=road.get("id"))
    if road_record_sha256(road) != COMPONENT501_ROAD_SHA256:
        raise CoastalGeometryError("component 501 road changed before its bounded edit",
                                   actualSha256=road_record_sha256(road), expectedSha256=COMPONENT501_ROAD_SHA256)
    points = _array(road["points"], (3,), "component 501 road points")
    distances = cumulative_stations(points)
    left, right = COMPONENT501_FIRST_MOVABLE - 1, COMPONENT501_LAST_MOVABLE + 1
    peak = COMPONENT501_PEAK_STATION_METRES
    if not distances[left] < peak < distances[right]:
        raise CoastalGeometryError("component 501 peak left its pinned source interval")
    weights = np.zeros(len(points), dtype=np.float64)
    for index in range(COMPONENT501_FIRST_MOVABLE, COMPONENT501_LAST_MOVABLE + 1):
        station = distances[index]
        weights[index] = ((station - distances[left]) / (peak - distances[left]) if station <= peak else
                          (distances[right] - station) / (distances[right] - peak))
    direction = _unit(COMPONENT501_INLAND_DIRECTION_XZ, "component 501 inland direction")
    candidate = points.copy(); candidate[:, [0, 2]] += weights[:, None] * float(shift_metres) * direction
    return RoadEdit(COMPONENT501_ROAD,
                    tuple(range(COMPONENT501_FIRST_MOVABLE, COMPONENT501_LAST_MOVABLE + 1)),
                    points, candidate, float(shift_metres))


def _road_xz_sha256(points) -> str:
    xz = _array(points, (3,), "road points")[:, [0, 2]].astype("<f8", copy=False)
    return hashlib.sha256(xz.tobytes()).hexdigest()


def apply_coastal_road_edits(world) -> tuple[RoadEdit, ...]:
    """Apply the bounded source-owned coastal XZ edit before bridge fitting."""
    existing = getattr(world, "applied_coastal_road_edits", None)
    if existing is not None:
        return existing
    road = require_road(world.roads, COMPONENT501_ROAD)
    if float(road.get("width", math.nan)) != 4.:
        raise CoastalGeometryError("component 501 road width changed before its bounded edit",
                                   roadId=COMPONENT501_ROAD, expectedHalfWidthMetres=4.,
                                   actualHalfWidthMetres=road.get("width"))
    identity = _road_xz_sha256(road["points"])
    if identity == COMPONENT501_CANDIDATE_XZ_SHA256:
        result = ()
    elif identity == COMPONENT501_SOURCE_XZ_SHA256:
        # The production identity intentionally ignores Y: an earlier normal
        # road-height epoch may differ while the authorized XZ topology does not.
        points = _array(road["points"], (3,), "component 501 road points")
        distances = cumulative_stations(points)
        left, right = COMPONENT501_FIRST_MOVABLE - 1, COMPONENT501_LAST_MOVABLE + 1
        peak = COMPONENT501_PEAK_STATION_METRES
        weights = np.zeros(len(points), dtype=np.float64)
        for index in range(COMPONENT501_FIRST_MOVABLE, COMPONENT501_LAST_MOVABLE + 1):
            station = distances[index]
            weights[index] = ((station - distances[left]) / (peak - distances[left]) if station <= peak else
                              (distances[right] - station) / (distances[right] - peak))
        candidate = points.copy()
        candidate[:, [0, 2]] += weights[:, None] * COMPONENT501_CANDIDATE_SHIFT_METRES * np.asarray(
            COMPONENT501_INLAND_DIRECTION_XZ)
        edit = RoadEdit(COMPONENT501_ROAD,
                        tuple(range(COMPONENT501_FIRST_MOVABLE, COMPONENT501_LAST_MOVABLE + 1)),
                        points, candidate, COMPONENT501_CANDIDATE_SHIFT_METRES)
        road["points"] = candidate
        result = (edit,)
    else:
        raise CoastalGeometryError("component 501 XZ topology changed before its bounded edit",
                                   roadId=COMPONENT501_ROAD, actualSha256=identity,
                                   expectedSourceSha256=COMPONENT501_SOURCE_XZ_SHA256,
                                   expectedCandidateSha256=COMPONENT501_CANDIDATE_XZ_SHA256)
    world.applied_coastal_road_edits = result
    return result


DEFAULT_SELECTED_COASTAL_ROADS = (COMPONENT502_ROAD,)
SUPPORTED_SELECTED_COASTAL_ROADS = frozenset((COMPONENT501_ROAD, COMPONENT502_ROAD))


def _selected_coastal_roads(selected_road_ids):
    selected = tuple(map(str, selected_road_ids))
    if not selected:
        raise CoastalGeometryError("selected coastal road list is empty")
    if len(selected) != len(set(selected)):
        raise CoastalGeometryError("selected coastal road list contains duplicates",
                                   selectedRoadIds=selected)
    unsupported = tuple(sorted(set(selected)-SUPPORTED_SELECTED_COASTAL_ROADS))
    if unsupported:
        raise CoastalGeometryError("selected coastal road is unsupported",
                                   unsupportedRoadIds=unsupported)
    return selected


def prepare_coastal_claims(world, content=None, *, inventory=None,
                            selected_road_ids=DEFAULT_SELECTED_COASTAL_ROADS) -> tuple[CoastalClaim, ...]:
    """Prepare the explicitly selected claims; every other crossing stays legacy."""
    selected = _selected_coastal_roads(selected_road_ids)
    existing = getattr(world, "claimed_coastal_records", None)
    if existing is not None:
        existing = tuple(existing)
        actual = tuple(road for claim in existing for road in claim.road_ids)
        if len(actual) != len(set(actual)) or set(actual) != set(selected):
            raise CoastalGeometryError("prepared coastal registry does not match its selection",
                                       selectedRoadIds=selected, preparedRoadIds=actual)
        return existing
    if inventory is None:
        import bridge_export
        inventory = bridge_export.loose_crossing_inventory(world)
    import coastal_prepare
    dispatch = {
        COMPONENT501_ROAD: coastal_prepare.prepare_component501_claim,
        COMPONENT502_ROAD: coastal_prepare.prepare_component502_claim,
    }
    return tuple(dispatch[road](world, inventory, content=content) for road in selected)


@dataclass(frozen=True)
class CoastalClaim:
    claim_id: str
    component_seed: int
    road_ids: tuple[str, ...]
    wet_extent_metres: tuple[float, float]
    join_stations_metres: tuple[float, float]
    surfaces: tuple[SurfaceGeometry, ...]
    stairs: tuple[StairGeometry, ...] = ()
    supports: tuple[SupportRecord, ...] = ()
    road_edits: tuple[RoadEdit, ...] = ()
    loose_wet_cells: tuple[int, ...] = ()
    terminal_sides: tuple[str, ...] = ()
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        cells = tuple(int(value) for value in self.loose_wet_cells)
        if any(value < 0 for value in cells) or len(cells) != len(set(cells)):
            raise CoastalGeometryError("coastal loose-wet cell authority is invalid", claimId=self.claim_id)
        terminal_sides = tuple(map(str, self.terminal_sides))
        if len(terminal_sides) != len(set(terminal_sides)) or not set(terminal_sides) <= {"left", "right"}:
            raise CoastalGeometryError("coastal terminal-side authority is invalid", claimId=self.claim_id,
                                       terminalSides=terminal_sides)
        object.__setattr__(self, "loose_wet_cells", tuple(sorted(cells)))
        object.__setattr__(self, "terminal_sides", tuple(sorted(terminal_sides)))

    @property
    def encoded_floor_triangles(self):
        groups = [surface.encoded_triangles for surface in self.surfaces]
        groups.extend(stair.encoded_floor_triangles for stair in self.stairs)
        return np.concatenate(groups, axis=0) if groups else np.empty((0, 3, 3), dtype=np.float64)

    @property
    def source_ready(self):
        required = ["capsuleCoverage", "emittedWater", "fullWidthJoins", "terrainClearance"]
        if self.supports or any(stair.supports for stair in self.stairs):
            required.append("supportContact")
        if self.stairs:
            required.append("guardedSteps")
        if self.terminal_sides:
            required.append("terminalPlatform")
        def clear(name):
            proof = self.evidence.get(name)
            if not isinstance(proof, Mapping) or proof.get("acceptanceAuthority") is not True:
                return False
            if proof.get("clear") is True:
                return True
            if name == "emittedWater" and proof.get("pureSea") is True and \
               proof.get("clearanceClear") is True:
                grouped = self.evidence.get("multiContactOwnership")
                return (isinstance(grouped, Mapping) and
                        grouped.get("acceptanceAuthority") is True and grouped.get("clear") is True)
            return False
        return all(clear(name) for name in required)

    def geometry(self):
        return {"claimId": self.claim_id, "componentSeed": self.component_seed, "roadIds": self.road_ids,
                "wetExtentMetres": self.wet_extent_metres, "joinStationsMetres": self.join_stations_metres,
                "looseWetCells": self.loose_wet_cells,
                "terminalSides": self.terminal_sides,
                "surfaces": [surface.geometry() for surface in self.surfaces],
                "stairs": [{"name": stair.name, "roadId": stair.road_id,
                            "startStationMetres": stair.start_station, "endStationMetres": stair.end_station,
                            "treads": [surface.geometry() for surface in stair.tread_surfaces],
                            "encodedRiserTriangles": stair.riser_triangles.astype(np.float32).astype(np.float64),
                            "supports": [support.name for support in stair.supports]} for stair in self.stairs],
                "supports": [support.name for support in self.supports], "evidence": dict(self.evidence),
                "sourceReady": self.source_ready}


def validate_claim_preflight(claim: CoastalClaim, *, landing_limit_metres: float = 6.) -> CoastalClaim:
    """Check only station bounds; this never establishes source readiness."""
    low, high = map(float, claim.wet_extent_metres); left, right = map(float, claim.join_stations_metres)
    if not left <= low <= high <= right:
        raise CoastalGeometryError("coastal joins do not enclose the complete wet extent", claimId=claim.claim_id)
    landings = {"left": low - left, "right": right - high}
    checked_landings = [value for side, value in landings.items() if side not in claim.terminal_sides]
    if checked_landings and max(checked_landings) > landing_limit_metres:
        raise CoastalGeometryError("coastal landing exceeds its source rule", claimId=claim.claim_id,
                                   landingMetres=landings, terminalSides=claim.terminal_sides,
                                   limitMetres=float(landing_limit_metres))
    if not claim.surfaces:
        raise CoastalGeometryError("coastal claim has no named floor", claimId=claim.claim_id)
    return claim


def validate_claim(claim: CoastalClaim, *, landing_limit_metres: float = 6.) -> CoastalClaim:
    """Require current physical geometry; publication collision tests stay external."""
    validate_claim_preflight(claim, landing_limit_metres=landing_limit_metres)
    if not claim.source_ready:
        required = ["capsuleCoverage", "emittedWater", "fullWidthJoins", "terrainClearance"]
        if claim.supports or any(stair.supports for stair in claim.stairs):
            required.append("supportContact")
        if claim.stairs:
            required.append("guardedSteps")
        if claim.terminal_sides:
            required.append("terminalPlatform")
        def clear(name):
            proof = claim.evidence.get(name)
            if not isinstance(proof, Mapping) or proof.get("acceptanceAuthority") is not True:
                return False
            if proof.get("clear") is True:
                return True
            if name == "emittedWater" and proof.get("pureSea") is True and \
               proof.get("clearanceClear") is True:
                grouped = claim.evidence.get("multiContactOwnership")
                return (isinstance(grouped, Mapping) and
                        grouped.get("acceptanceAuthority") is True and grouped.get("clear") is True)
            return False
        missing = [name for name in required if not clear(name)]
        raise CoastalGeometryError("coastal claim lacks current full-geometry acceptance proof",
                                   claimId=claim.claim_id, missingOrFailedProofs=missing)
    water = claim.evidence["emittedWater"]
    if not water.get("pureSea"):
        raise CoastalGeometryError("coastal claim is not pure-sea contact",
                                   claimId=claim.claim_id,
                                   contactKinds=water.get("contactKinds"))
    if not water.get("continuous"):
        grouped = claim.evidence.get("multiContactOwnership")
        intervals = np.asarray(water.get("continuousStationIntervalsMetres", ()), dtype=np.float64)
        declared = (np.asarray(grouped.get("contactIntervalsMetres", ()), dtype=np.float64)
                    if isinstance(grouped, Mapping) else np.empty((0, 2)))
        cells = (tuple(sorted(map(int, grouped.get("ownedLooseWetCells", ()))))
                 if isinstance(grouped, Mapping) else ())
        valid_intervals = (intervals.ndim == 2 and intervals.shape[1:] == (2,) and len(intervals) > 1 and
                           np.all(intervals[:, 0] <= intervals[:, 1]) and
                           np.all(intervals[1:, 0] > intervals[:-1, 1]))
        grouped_clear = (isinstance(grouped, Mapping) and
                         grouped.get("acceptanceAuthority") is True and grouped.get("clear") is True and
                         grouped.get("outerJoinOnly") is True and valid_intervals and
                         np.array_equal(declared, intervals) and cells == claim.loose_wet_cells)
        if not grouped_clear:
            raise CoastalGeometryError(
                "discontinuous coastal contact lacks exact grouped ownership",
                claimId=claim.claim_id,
                continuousStationIntervalsMetres=water.get("continuousStationIntervalsMetres"),
                ownedLooseWetCells=claim.loose_wet_cells)
    return claim
