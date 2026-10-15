"""Pure canonical boundary subdivision; deliberately not wired into an exporter.

Regions are already-authenticated Polygon/MultiPolygon values. No ownership
sampler, source grid, transform, height field, filesystem or plan is mutated.
GEOS nodes the boundary band once per supplied source topology. Attribute recipes
refer to original vertices, so every recipient uses the same interpolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
import math

import numpy as np
import shapely as SH
from shapely.geometry import LineString, Point, Polygon


class BoundaryError(ValueError):
    def __init__(self, message, **details):
        self.details = details
        super().__init__(message + (": " + repr(details) if details else ""))


@dataclass(frozen=True)
class Recipe:
    kind: str
    vertices: tuple[int, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True)
class Partition:
    vertices: np.ndarray
    triangles: np.ndarray
    owners: tuple[str, ...]
    source_faces: tuple[str, ...]
    recipes: tuple[Recipe, ...]
    source_vertex_count: int
    original_triangles: np.ndarray
    face_keys: tuple[str, ...]
    report: dict


@dataclass(frozen=True)
class EncodedPartition:
    positions: np.ndarray
    report: dict


def _readonly(value, dtype=float):
    result = np.array(value, dtype=dtype, copy=True)
    result.setflags(write=False)
    return result


def _cross(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def _area2(points):
    return _cross(points[1] - points[0], points[2] - points[0])


def _keys(values, count, label):
    result = tuple(str(i) for i in range(count)) if values is None else tuple(values)
    if len(result) != count or any(not isinstance(v, str) or not v for v in result) or len(set(result)) != count:
        raise BoundaryError("source identities must be unique nonempty strings", field=label)
    return result


def _audit_tolerance(geometry):
    # Numerical audit only: never a simplification, welding or deletion distance.
    scale = max(1., *(abs(v) for v in geometry.bounds))
    return 128. * np.finfo(float).eps * scale * max(1., geometry.length)


def _certificate(faces, expected, *, allowance=0.):
    union = SH.union_all(faces)
    missing = float(expected.difference(union).area)
    extra = float(union.difference(expected).area)
    tree = SH.STRtree(faces)
    overlaps = []
    for i, face in enumerate(faces):
        for j in sorted(tree.query(face).tolist()):
            if j > i:
                overlaps.append(float(face.intersection(faces[j]).area))
    overlap = math.fsum(overlaps)
    tolerance = _audit_tolerance(expected)
    result = {"missingArea": missing, "extraArea": extra, "overlapArea": overlap,
              "roundoffAreaBound": tolerance, "encodingAreaBound": float(allowance)}
    if missing > tolerance + allowance or extra > tolerance + allowance or overlap > tolerance:
        raise BoundaryError("surface coverage or overlap certificate failed", **result)
    return result


def _edge_certificate(faces):
    """Internal chains must use the same indices with opposite directions."""
    edges = {}
    for face in faces:
        for a, b in zip(face, (*face[1:], face[0])):
            if a == b:
                raise BoundaryError("collapsed topological edge", vertex=int(a))
            key = tuple(sorted((int(a), int(b))))
            edges.setdefault(key, []).append(1 if a < b else -1)
    for edge, directions in edges.items():
        if len(directions) > 2 or (len(directions) == 2 and sum(directions) != 0):
            raise BoundaryError("nonmanifold or inconsistently wound source partition", edge=edge)
    return {"boundaryEdges": sum(len(v) == 1 for v in edges.values()),
            "interiorEdges": sum(len(v) == 2 for v in edges.values())}


def _rings(polygon):
    return [polygon.exterior, *polygon.interiors]


def _segments(geometry):
    result = set()
    for part in SH.get_parts(geometry):
        for ring in _rings(part):
            points = list(ring.coords)
            for a, b in zip(points, points[1:]):
                if a != b:
                    result.add(tuple(sorted((a, b))))
    return result


def _edge_parameter(point, a, b):
    """Identify lineage of an existing noded point, without moving or welding it.

    A GEOS intersection may be a few double ULPs off the original segment. The
    determinant error bound only identifies its interpolation source; full XY
    remains part of the cache key and is never snapped to a different point.
    """
    u, q = b - a, point - a
    scale = max(1., *np.abs(point), *np.abs(a), *np.abs(b))
    error = 16. * np.finfo(float).eps * scale * max(abs(u[0]) + abs(u[1]), np.finfo(float).tiny)
    if abs(_cross(u, q)) > error:
        return None
    axis = int(np.argmax(np.abs(u)))
    t = float(q[axis] / u[axis])
    return t if 0. < t < 1. else None


def _triangulate(polygon):
    """Keep all ring constraints, including any collinear nodes omitted by CDT."""
    required = {tuple(p) for ring in _rings(polygon) for p in list(ring.coords)[:-1]}
    faces = []
    for part in SH.get_parts(SH.constrained_delaunay_triangles(polygon)):
        if part.geom_type != "Polygon" or len(part.interiors) or len(part.exterior.coords) != 4 or not part.is_valid or part.area <= 0.:
            raise BoundaryError("constrained triangulator emitted a non-triangle")
        face = [tuple(p) for p in list(part.exterior.coords)[:-1]]
        if not set(face).issubset(required):
            raise BoundaryError("constrained triangulator invented a vertex")
        faces.append(face)
    for point in sorted(required - {p for face in faces for p in face}):
        replacement = []
        inserted = False
        for face in faces:
            edge = next((i for i in range(3) if _edge_parameter(
                np.asarray(point), np.asarray(face[i]), np.asarray(face[(i + 1) % 3])) is not None), None)
            if edge is None:
                replacement.append(face)
            else:
                a, b, c = face[edge], face[(edge + 1) % 3], face[(edge + 2) % 3]
                replacement.extend([[a, point, c], [point, b, c]])
                inserted = True
        if not inserted:
            raise BoundaryError("triangulation lost a constrained node", point=point)
        faces = replacement
    if not faces:
        raise BoundaryError("positive polygon produced no triangles")
    _certificate([Polygon(f) for f in faces], polygon)
    return faces


def partition_triangles(xz, triangles, *, regions: Mapping[str, object], domain=None,
                        source_vertex_keys: Sequence[str] | None = None,
                        source_face_keys: Sequence[str] | None = None) -> Partition:
    """Partition source triangles without changing interior topology or attributes.

    ``regions`` must form a valid partition of ``domain`` (defaults to their
    union). Holes/multipart regions are supported. Overlapping *source* faces
    retain separate provenance; their deliberate layering is not owner overlap.
    Region order and input face order with stable face keys do not affect output.
    """
    if not hasattr(SH, "constrained_delaunay_triangles"):
        raise BoundaryError("installed GEOS lacks constrained triangulation")
    points = np.array(xz, dtype=float, copy=True)
    raw_faces = np.asarray(triangles)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise BoundaryError("source XZ must be finite Nx2")
    if raw_faces.ndim != 2 or raw_faces.shape[1] != 3 or raw_faces.dtype.kind not in "iu":
        raise BoundaryError("source triangles must be integer Nx3")
    faces = np.array(raw_faces, dtype=np.int64, copy=True)
    if np.any(faces < 0) or np.any(faces >= len(points)):
        raise BoundaryError("missing source stencil vertex")
    vertex_keys = _keys(source_vertex_keys, len(points), "vertices")
    face_keys = _keys(source_face_keys, len(faces), "faces")
    if not isinstance(regions, Mapping) or not regions or any(not isinstance(k, str) or not k for k in regions):
        raise BoundaryError("regions require nonempty canonical IDs")
    names = sorted(regions)
    for name in names:
        g = regions[name]
        if not isinstance(g, (SH.Polygon, SH.MultiPolygon)) or not g.is_valid or g.is_empty or g.area <= 0. or not np.isfinite(SH.get_coordinates(g)).all():
            raise BoundaryError("invalid canonical polygon", region=name)
    geography = SH.union_all([regions[name] for name in names])
    domain = geography if domain is None else domain
    if not isinstance(domain, (SH.Polygon, SH.MultiPolygon)) or domain.is_empty or not domain.is_valid:
        raise BoundaryError("invalid canonical domain")
    geography_report = _certificate([regions[name] for name in names], domain)
    polygons = [Polygon(points[face]) for face in faces]
    for i, polygon in enumerate(polygons):
        if not polygon.is_valid or polygon.area <= 0.:
            raise BoundaryError("degenerate source triangle", sourceFace=face_keys[i])
        outside = float(polygon.difference(domain).area)
        if outside > 0.:
            raise BoundaryError("source surface outside canonical domain", sourceFace=face_keys[i], outsideArea=outside)
    boundary = SH.union_all([regions[name].boundary for name in names])
    touched = [i for i, p in enumerate(polygons) if boundary.intersects(p)]
    touched_set = set(touched)
    # Input source vertices retain exact values and identities, including unused
    # ones. Added vertices are interned in stable face/ring order below.
    vertices = [tuple(p) for p in points]
    recipes = [Recipe("vertex", (i,), (1.,)) for i in range(len(points))]
    cache = {}
    output = []
    source_order = sorted(range(len(faces)), key=lambda i: face_keys[i])

    def owner(point):
        found = [name for name in names if regions[name].covers(point)]
        if len(found) != 1:
            raise BoundaryError("arrangement cell has ambiguous or missing owner", owners=found,
                                point=(point.x, point.y))
        return found[0]

    def sample(point, source):
        point = tuple(point)
        indices = faces[source]
        for index in indices:
            if point == vertices[index]:
                return int(index)
        q = np.asarray(point)
        edges = sorted((tuple(sorted((int(indices[i]), int(indices[(i + 1) % 3])),
                                    key=lambda k: vertex_keys[k])) for i in range(3)),
                       key=lambda edge: tuple(vertex_keys[k] for k in edge))
        recipe = None
        for a, b in edges:
            t = _edge_parameter(q, points[a], points[b])
            if t is not None:
                key = ("edge", vertex_keys[a], vertex_keys[b], *point)
                recipe = Recipe("edge", (a, b), (1. - t, t))
                break
        if recipe is None:
            a, b, c = points[indices]
            u, v, offset = b - a, c - a, q - a
            determinant = _cross(u, v)
            s, t = _cross(offset, v) / determinant, _cross(u, offset) / determinant
            key = ("face", face_keys[source], *point)
            recipe = Recipe("face", tuple(map(int, indices)), (1. - s - t, s, t))
        if key not in cache:
            cache[key] = len(vertices)
            vertices.append(point)
            recipes.append(recipe)
        return cache[key]

    pieces_by_face = {i: [] for i in touched}
    if touched:
        tree = SH.STRtree([polygons[i] for i in touched])
        lines = set()
        for i in touched:
            lines.update(_segments(polygons[i]))
        for name in names:
            for segment in _segments(regions[name]):
                if len(tree.query(LineString(segment), predicate="intersects")):
                    lines.add(segment)
        noded = SH.node(SH.MultiLineString(sorted(lines)))
        arrangement = SH.polygonize(SH.get_parts(noded))
        for piece in SH.get_parts(arrangement):
            if piece.area <= 0.:
                continue
            representative = piece.representative_point()
            for at in sorted(tree.query(representative, predicate="intersects").tolist()):
                source = touched[at]
                extra = float(piece.difference(polygons[source]).area)
                if extra > _audit_tolerance(polygons[source]):
                    raise BoundaryError("arrangement crossed a source edge", sourceFace=face_keys[source], extraArea=extra)
                pieces_by_face[source].append((owner(representative), piece))

    for source in source_order:
        if source not in touched_set:
            output.append((owner(polygons[source].representative_point()), face_keys[source], tuple(map(int, faces[source]))))
            continue
        pieces = pieces_by_face[source]
        # Canonical coordinate ring normalization affects ordering only.
        pieces.sort(key=lambda item: (item[0], SH.to_wkb(SH.normalize(item[1]))))
        for name, piece in pieces:
            for face in sorted(_triangulate(piece), key=lambda f: tuple(sorted(f))):
                indices = [sample(p, source) for p in face]
                result_points = np.asarray([vertices[k] for k in indices])
                if _area2(result_points) * _area2(points[faces[source]]) < 0.:
                    indices.reverse()
                at = indices.index(min(indices))
                indices = indices[at:] + indices[:at]
                output.append((name, face_keys[source], tuple(indices)))
    output.sort(key=lambda row: (row[0], row[1], row[2]))
    vertices = _readonly(vertices).reshape(-1, 2)
    result_faces = _readonly([row[2] for row in output], np.int64).reshape(-1, 3)
    grouped = {key: [] for key in face_keys}
    for row in output:
        grouped[row[1]].append(row[2])
    certificates = {}
    for source in source_order:
        selected = grouped[face_keys[source]]
        emitted = [Polygon(vertices[face, :]) for face in selected]
        try:
            certificates[face_keys[source]] = _certificate(emitted, polygons[source])
            certificates[face_keys[source]].update(_edge_certificate(selected))
        except BoundaryError as error:
            raise BoundaryError("source face partition failed", sourceFace=face_keys[source], **error.details) from error
    return Partition(vertices, result_faces, tuple(r[0] for r in output), tuple(r[1] for r in output),
                     tuple(recipes), len(points), _readonly(faces, np.int64), face_keys,
                     {"geography": geography_report, "sourceFaces": certificates,
                      "sourceTriangles": len(faces), "boundaryTriangles": len(touched),
                      "interiorTriangles": len(faces) - len(touched), "emittedTriangles": len(output)})


def interpolate(partition: Partition, source_values):
    """Affine source samples; caller owns normal/tangent normalization and color encoding."""
    values = np.array(source_values, dtype=float, copy=True)
    if values.ndim < 1 or len(values) != partition.source_vertex_count or not np.isfinite(values).all():
        raise BoundaryError("missing or invalid source attribute stencil", expectedVertices=partition.source_vertex_count)
    result = np.empty((len(partition.vertices), *values.shape[1:]), dtype=float)
    result[:len(values)] = values
    for i in range(len(values), len(result)):
        recipe = partition.recipes[i]
        result[i] = np.tensordot(np.asarray(recipe.weights), values[list(recipe.vertices)], axes=1)
    return _readonly(result)


def float32_translation_bound(global_positions, translation):
    """Per-axis worst-case rounding bound for encode, local subtract and world add.

    Add the bounds of two wrappers when comparing their restored world points.
    This is a measurement bound, never authority to move a source point.
    """
    points = np.asarray(global_positions, dtype=float)
    center = np.asarray(translation, dtype=float)
    def half_ulp(value):
        return np.abs(np.spacing(np.asarray(value, dtype=np.float32)).astype(float)) * .5
    return half_ulp(points) + 2. * half_ulp(center) + half_ulp(points - center) + half_ulp(points)


def encode_positions(partition: Partition, source_positions) -> EncodedPartition:
    """Encode shared samples once; fail on any positive triangle collapse/reversal.

    Original XZ must match the partition exactly. Height is affine interpolation
    of the supplied original positions, never resampled from a terrain field.
    """
    source = np.asarray(source_positions, dtype=float)
    if source.shape != (partition.source_vertex_count, 3) or not np.isfinite(source).all():
        raise BoundaryError("missing or invalid source position stencil")
    if not np.array_equal(source[:, [0, 2]], partition.vertices[:len(source)]):
        raise BoundaryError("source position XZ changed after partition")
    positions = np.array(interpolate(partition, source), copy=True)
    positions[:, [0, 2]] = partition.vertices
    with np.errstate(over="ignore", invalid="ignore"):
        encoded = positions.astype(np.float32)
    if not np.isfinite(encoded).all():
        raise BoundaryError("float32 position overflow")
    encoded_xz = encoded[:, [0, 2]].astype(float)
    for i, face in enumerate(partition.triangles):
        before = _area2(partition.vertices[face])
        after = _area2(encoded_xz[face])
        if before == 0. or after == 0. or np.sign(before) != np.sign(after):
            raise BoundaryError("positive triangle collapsed or reversed in float32", sourceFace=partition.source_faces[i],
                                owner=partition.owners[i], triangle=i, sourceArea2=before, encodedArea2=after)
    certificates = {}
    grouped = {key: [] for key in partition.face_keys}
    for i, key in enumerate(partition.source_faces):
        grouped[key].append(i)
    for source_index, key in enumerate(partition.face_keys):
        ids = grouped[key]
        target = Polygon(encoded_xz[partition.original_triangles[source_index]])
        source_target = Polygon(partition.vertices[partition.original_triangles[source_index]])
        point_ids = np.unique(partition.triangles[ids])
        movement = np.max(np.linalg.norm(encoded_xz[point_ids] - partition.vertices[point_ids], axis=1), initial=0.)
        # The encoded outer edge is allowed only its measured quantization band.
        # Owner-owner overlap has no such allowance: all owners share one mesh.
        allowance = 2. * max(target.length, source_target.length) * movement + 4. * math.pi * movement * movement
        try:
            certificates[key] = _certificate([Polygon(encoded_xz[partition.triangles[i]]) for i in ids],
                                             target, allowance=allowance)
        except BoundaryError as error:
            raise BoundaryError("encoded source face partition failed", sourceFace=key, **error.details) from error
    error = np.abs(encoded.astype(float) - positions)
    return EncodedPartition(_readonly(encoded, np.float32),
                            {"maxPositionError": error.max(axis=0).tolist() if len(error) else [0., 0., 0.],
                             "sourceFaces": certificates})
