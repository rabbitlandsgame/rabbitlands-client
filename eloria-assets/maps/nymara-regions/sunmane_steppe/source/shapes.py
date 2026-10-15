"""Solid modelling primitives for the Sunmane Steppe kit.

Everything produced here is a closed, thickened volume with outward normals and
world-scale UVs, so texel density stays uniform across terrain, architecture
and props without any per-asset UV bookkeeping.  Nothing emits single-sided
"card" geometry except where a real object is genuinely a sheet (banners,
flags), and those are explicitly marked double sided by the caller.
"""
from __future__ import annotations

import math

import numpy as np

from glb import Geometry

# Metres of world space covered by one texture repeat, per family. Keeping this
# in one place is what makes texel density consistent across the whole region.
UV_SCALE = {
    "canvas": 3.2,
    "timber": 2.4,
    "ground": 6.0,
    "stone": 3.6,
    "cavern": 4.4,
    "thatch": 1.8,
    "crystal": 1.1,
    "hide": 0.9,
    "leather": 0.8,
    "textile": 1.2,
    "metal": 0.5,
    "bone": 0.6,
}


def _as_array(value) -> np.ndarray:
    return np.asarray(value, dtype="float64").reshape(3)


def _quad_indices(offset: int = 0) -> np.ndarray:
    return np.array([0, 1, 2, 0, 2, 3], dtype="uint32") + offset


def add_quad(geometry: Geometry, corners, uvs, *, flip: bool = False,
             normal=None) -> None:
    """Append one flat quad given four corners in winding order."""
    corners = np.asarray(corners, dtype="float64").reshape(4, 3)
    if normal is None:
        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
        length = np.linalg.norm(normal)
        normal = normal / length if length > 1e-12 else np.array([0.0, 1.0, 0.0])
    normal = np.asarray(normal, dtype="float64")
    if flip:
        corners = corners[::-1]
        uvs = np.asarray(uvs)[::-1]
        normal = -normal
    geometry.add(corners, np.tile(normal, (4, 1)), uvs, _quad_indices())


def oriented_quad(geometry: Geometry, corners, uvs, toward) -> None:
    """Emit a quad whose face normal points the same side as `toward`.

    Winding a surface by hand is where orientation bugs come from: the geometry
    reads correctly in the authoring code and still ends up inside-out. Stating
    the direction the surface should face, and letting the winding follow, makes
    that class of mistake impossible.
    """
    corners = np.asarray(corners, dtype="float64").reshape(4, 3)
    uvs = np.asarray(uvs, dtype="float64").reshape(4, 2)
    # Emitted as two independently oriented triangles. A warped quad's halves
    # do not share a face normal, so giving both the same vertex normal leaves
    # one of them disagreeing with the surface it belongs to.
    for triangle in ((0, 1, 2), (0, 2, 3)):
        oriented_triangle(geometry, corners[list(triangle)],
                          uvs[list(triangle)], toward)


def oriented_triangle(geometry: Geometry, corners, uvs, toward) -> None:
    """Emit a triangle whose face normal points the same side as `toward`."""
    corners = np.asarray(corners, dtype="float64").reshape(3, 3)
    normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
    length = float(np.linalg.norm(normal))
    if length < 1e-12:
        return
    if float(np.dot(normal, np.asarray(toward, dtype="float64"))) < 0.0:
        corners = corners[::-1]
        uvs = np.asarray(uvs)[::-1]
        normal = -normal
    geometry.add(corners, np.tile(normal / length, (3, 1)), uvs, [0, 1, 2])


def _planar_uv(points: np.ndarray, scale: float) -> np.ndarray:
    """Project points onto their dominant plane for world-scale UVs."""
    normal = np.cross(points[1] - points[0], points[2] - points[0])
    axis = int(np.argmax(np.abs(normal)))
    if axis == 1:
        uv = points[:, [0, 2]]
    elif axis == 0:
        uv = points[:, [2, 1]]
    else:
        uv = points[:, [0, 1]]
    return uv / scale


# ------------------------------------------------------------------------ box
def box(geometry: Geometry, center, size, *, uv_scale: float = 2.0,
        rotation_y: float = 0.0) -> None:
    """Axis-aligned (optionally yawed) solid box with per-face world UVs."""
    center = _as_array(center)
    half = _as_array(size) * 0.5
    signs = np.array([[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
                      [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]], dtype="float64")
    corners = signs * half
    if rotation_y:
        c, s = math.cos(rotation_y), math.sin(rotation_y)
        rotation = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
        corners = corners @ rotation.T
    corners = corners + center
    faces = (((4, 5, 6, 7), (0, 0, 1)), ((1, 0, 3, 2), (0, 0, -1)),
             ((5, 1, 2, 6), (1, 0, 0)), ((0, 4, 7, 3), (-1, 0, 0)),
             ((3, 7, 6, 2), (0, 1, 0)), ((0, 1, 5, 4), (0, -1, 0)))
    for indices, normal in faces:
        quad = corners[list(indices)]
        normal = np.asarray(normal, dtype="float64")
        if rotation_y:
            normal = rotation @ normal
        add_quad(geometry, quad, _planar_uv(quad, uv_scale), normal=normal)


def beam(geometry: Geometry, start, end, width: float, depth: float | None = None,
         *, uv_scale: float = 2.0, roll: float = 0.0) -> None:
    """Rectangular-section timber running from `start` to `end`, capped at both ends."""
    start, end = _as_array(start), _as_array(end)
    depth = width if depth is None else depth
    axis = end - start
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        return
    axis /= length
    reference = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(axis, reference))) > 0.98:
        reference = np.array([1.0, 0.0, 0.0])
    side = np.cross(reference, axis)
    side /= np.linalg.norm(side)
    up = np.cross(axis, side)
    if roll:
        c, s = math.cos(roll), math.sin(roll)
        side, up = side * c + up * s, up * c - side * s
    offsets = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    ring_a = [start + side * (u * width) + up * (v * depth) for u, v in offsets]
    ring_b = [end + side * (u * width) + up * (v * depth) for u, v in offsets]
    for index in range(4):
        following = (index + 1) % 4
        quad = [ring_a[index], ring_a[following], ring_b[following], ring_b[index]]
        extent = width if index % 2 == 0 else depth
        uvs = [[0.0, 0.0], [extent / uv_scale, 0.0],
               [extent / uv_scale, length / uv_scale], [0.0, length / uv_scale]]
        add_quad(geometry, quad, uvs)
    add_quad(geometry, ring_b, _planar_uv(np.array(ring_b), uv_scale), normal=axis)
    add_quad(geometry, ring_a[::-1], _planar_uv(np.array(ring_a[::-1]), uv_scale),
             normal=-axis)


# ------------------------------------------------------------------- revolved
def frustum(geometry: Geometry, start, end, radius_start: float, radius_end: float,
            *, sides: int = 16, uv_scale: float = 2.0, cap_start: bool = True,
            cap_end: bool = True, uv_offset: float = 0.0) -> None:
    """Cylinder / cone / tapered post between two points."""
    start, end = _as_array(start), _as_array(end)
    axis = end - start
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        return
    axis /= length
    reference = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(axis, reference))) > 0.98:
        reference = np.array([1.0, 0.0, 0.0])
    side = np.cross(reference, axis)
    side /= np.linalg.norm(side)
    up = np.cross(axis, side)
    angles = np.linspace(0.0, 2.0 * math.pi, sides + 1)
    circumference = 2.0 * math.pi * max(radius_start, radius_end, 1e-4)
    slope = math.atan2(radius_start - radius_end, length)
    for index in range(sides):
        a0, a1 = angles[index], angles[index + 1]
        directions = [side * math.cos(a) + up * math.sin(a) for a in (a0, a1)]
        p0 = start + directions[0] * radius_start
        p1 = start + directions[1] * radius_start
        p2 = end + directions[1] * radius_end
        p3 = end + directions[0] * radius_end
        # Slope-corrected normals so cones shade as cones, not cylinders.
        normals = [d * math.cos(slope) + axis * math.sin(slope) for d in directions]
        u0 = (a0 / (2.0 * math.pi)) * circumference / uv_scale + uv_offset
        u1 = (a1 / (2.0 * math.pi)) * circumference / uv_scale + uv_offset
        v1 = length / uv_scale
        if radius_start <= 1e-6:
            geometry.add([p0, p2, p3], [normals[0], normals[1], normals[0]],
                         [[u0, 0.0], [u1, v1], [u0, v1]], [0, 1, 2])
        elif radius_end <= 1e-6:
            geometry.add([p0, p1, p2], [normals[0], normals[1], normals[1]],
                         [[u0, 0.0], [u1, 0.0], [u1, v1]], [0, 1, 2])
        else:
            geometry.add([p0, p1, p2, p3],
                         [normals[0], normals[1], normals[1], normals[0]],
                         [[u0, 0.0], [u1, 0.0], [u1, v1], [u0, v1]],
                         _quad_indices())
    for cap, point, radius, normal in ((cap_end, end, radius_end, axis),
                                       (cap_start, start, radius_start, -axis)):
        if not cap or radius <= 1e-6:
            continue
        ring = [point + (side * math.cos(a) + up * math.sin(a)) * radius
                for a in angles[:-1]]
        positions = [point] + ring
        uvs = [[0.0, 0.0]] + [[radius * math.cos(a) / uv_scale,
                               radius * math.sin(a) / uv_scale] for a in angles[:-1]]
        indices = []
        for index in range(sides):
            following = 1 + (index + 1) % sides
            if normal is axis or np.allclose(normal, axis):
                indices.extend([0, 1 + index, following])
            else:
                indices.extend([0, following, 1 + index])
        geometry.add(positions, np.tile(normal, (len(positions), 1)), uvs, indices)


def revolve(geometry: Geometry, profile, center, *, sides: int = 20,
            uv_scale: float = 1.0, close_bottom: bool = True,
            close_top: bool = False) -> None:
    """Lathe a 2D (radius, height) profile around the Y axis through `center`."""
    center = _as_array(center)
    profile = [(float(r), float(y)) for r, y in profile]
    for index in range(len(profile) - 1):
        r0, y0 = profile[index]
        r1, y1 = profile[index + 1]
        frustum(geometry, center + np.array([0.0, y0, 0.0]),
                center + np.array([0.0, y1, 0.0]), r0, r1, sides=sides,
                uv_scale=uv_scale,
                cap_start=close_bottom and index == 0,
                cap_end=close_top and index == len(profile) - 2)


def sphere(geometry: Geometry, center, radius: float, *, rings: int = 10,
           sides: int = 16, uv_scale: float = 1.0, squash: float = 1.0) -> None:
    center = _as_array(center)
    for ring in range(rings):
        phi0 = math.pi * ring / rings
        phi1 = math.pi * (ring + 1) / rings
        for segment in range(sides):
            theta0 = 2.0 * math.pi * segment / sides
            theta1 = 2.0 * math.pi * (segment + 1) / sides
            corners, normals, uvs = [], [], []
            for phi, theta in ((phi0, theta0), (phi0, theta1),
                               (phi1, theta1), (phi1, theta0)):
                direction = np.array([math.sin(phi) * math.cos(theta),
                                      math.cos(phi) * squash,
                                      math.sin(phi) * math.sin(theta)])
                point = center + direction * radius
                # An ellipsoid's normal is not its position direction: with a
                # squash factor the two diverge, which leaves shading wrong and
                # can flip a coarse polar triangle against its own face.
                gradient = np.array([direction[0], direction[1] / (squash ** 2),
                                     direction[2]])
                normal = gradient / max(np.linalg.norm(gradient), 1e-9)
                corners.append(point)
                normals.append(normal)
                uvs.append([theta / (2.0 * math.pi) * 2.0 * math.pi * radius / uv_scale,
                            phi / math.pi * math.pi * radius / uv_scale])
            # Pole rings collapse to a point on one edge; emit a triangle there
            # rather than a zero-area quad.
            if ring == 0:
                geometry.add(corners[1:], normals[1:], uvs[1:], [0, 1, 2])
            elif ring == rings - 1:
                geometry.add(corners[:3], normals[:3], uvs[:3], [0, 1, 2])
            else:
                geometry.add(corners, normals, uvs, _quad_indices())


# ----------------------------------------------------------------- extrusions
def prism(geometry: Geometry, polygon, y_bottom: float, y_top: float, *,
          uv_scale: float = 2.0, cap_top: bool = True, cap_bottom: bool = False,
          smooth_walls: bool = False) -> None:
    """Extrude a closed CCW polygon (list of (x, z)) between two heights."""
    points = [(float(x), float(z)) for x, z in polygon]
    count = len(points)
    if count < 3:
        return
    # Canonicalise to negative shoelace area in XZ. In a Y-up right-handed
    # system that is the orientation whose side quads face outward and whose
    # top cap faces +Y with the winding used below.
    area = 0.0
    for index in range(count):
        x0, z0 = points[index]
        x1, z1 = points[(index + 1) % count]
        area += x0 * z1 - x1 * z0
    if area > 0.0:
        points = points[::-1]
    perimeter = 0.0
    for index in range(count):
        x0, z0 = points[index]
        x1, z1 = points[(index + 1) % count]
        length = math.hypot(x1 - x0, z1 - z0)
        wall = [[x0, y_bottom, z0], [x1, y_bottom, z1],
                [x1, y_top, z1], [x0, y_top, z0]]
        uvs = [[perimeter / uv_scale, y_bottom / uv_scale],
               [(perimeter + length) / uv_scale, y_bottom / uv_scale],
               [(perimeter + length) / uv_scale, y_top / uv_scale],
               [perimeter / uv_scale, y_top / uv_scale]]
        if smooth_walls:
            centroid = np.mean(np.asarray(points), axis=0)
            normals = []
            for x, z in ((x0, z0), (x1, z1), (x1, z1), (x0, z0)):
                outward = np.array([x - centroid[0], 0.0, z - centroid[1]])
                norm = np.linalg.norm(outward)
                normals.append(outward / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0]))
            geometry.add(wall, normals, uvs, _quad_indices())
        else:
            add_quad(geometry, wall, uvs)
        perimeter += length
    for cap, height, normal, reverse in ((cap_top, y_top, (0.0, 1.0, 0.0), False),
                                         (cap_bottom, y_bottom, (0.0, -1.0, 0.0), True)):
        # `reverse` flips the bottom cap so it faces -Y.
        if not cap:
            continue
        ordered = points[::-1] if reverse else points
        positions = [[x, height, z] for x, z in ordered]
        uvs = [[x / uv_scale, z / uv_scale] for x, z in ordered]
        indices = []
        for index in range(1, count - 1):
            indices.extend([0, index, index + 1])
        geometry.add(positions, np.tile(np.asarray(normal, dtype="float64"),
                                        (count, 1)), uvs, indices)


def wall_run(geometry: Geometry, path, height: float, thickness: float, *,
             uv_scale: float = 2.0, base_y: float = 0.0,
             height_at=None) -> None:
    """Solid wall of constant thickness following an open or closed path.

    `path` is a list of (x, z). `height_at(index)` may vary the crest height.
    """
    points = [np.array([float(x), 0.0, float(z)]) for x, z in path]
    if len(points) < 2:
        return
    half = thickness * 0.5
    left, right = [], []
    for index, point in enumerate(points):
        if index == 0:
            direction = points[1] - points[0]
        elif index == len(points) - 1:
            direction = points[-1] - points[-2]
        else:
            direction = points[index + 1] - points[index - 1]
        direction[1] = 0.0
        norm = np.linalg.norm(direction)
        direction = direction / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])
        normal = np.array([-direction[2], 0.0, direction[0]])
        left.append(point + normal * half)
        right.append(point - normal * half)
    crest = [height if height_at is None else float(height_at(i))
             for i in range(len(points))]
    travelled = 0.0
    for index in range(len(points) - 1):
        length = float(np.linalg.norm(points[index + 1] - points[index]))
        top0, top1 = base_y + crest[index], base_y + crest[index + 1]
        for outer, inner, flip in ((left, right, False), (right, left, True)):
            quad = [outer[index] + [0.0, base_y, 0.0],
                    outer[index + 1] + [0.0, base_y, 0.0],
                    outer[index + 1] + [0.0, top1, 0.0],
                    outer[index] + [0.0, top0, 0.0]]
            uvs = [[travelled / uv_scale, base_y / uv_scale],
                   [(travelled + length) / uv_scale, base_y / uv_scale],
                   [(travelled + length) / uv_scale, top1 / uv_scale],
                   [travelled / uv_scale, top0 / uv_scale]]
            add_quad(geometry, quad, uvs, flip=flip)
        cap = [right[index] + [0.0, top0, 0.0], left[index] + [0.0, top0, 0.0],
               left[index + 1] + [0.0, top1, 0.0], right[index + 1] + [0.0, top1, 0.0]]
        add_quad(geometry, cap, _planar_uv(np.asarray(cap), uv_scale),
                 normal=(0.0, 1.0, 0.0))
        travelled += length
    for end, points_pair, flip in ((0, (left[0], right[0]), True),
                                   (len(points) - 1, (right[-1], left[-1]), True)):
        top = base_y + crest[end]
        quad = [points_pair[0] + [0.0, base_y, 0.0], points_pair[1] + [0.0, base_y, 0.0],
                points_pair[1] + [0.0, top, 0.0], points_pair[0] + [0.0, top, 0.0]]
        add_quad(geometry, quad, _planar_uv(np.asarray(quad), uv_scale), flip=flip)


def ribbon(geometry: Geometry, path, width: float, *, uv_scale: float = 4.0,
           lift: float = 0.03, height_at=None, double_sided: bool = False) -> None:
    """Flat surface strip following a path - roads, trails and plaza spines."""
    points = [np.array([float(x), 0.0, float(z)]) for x, z in path]
    if len(points) < 2:
        return
    half = width * 0.5
    travelled = 0.0
    for index in range(len(points) - 1):
        current, following = points[index], points[index + 1]
        direction = following - current
        length = float(np.linalg.norm(direction))
        if length < 1e-9:
            continue
        direction /= length
        normal = np.array([-direction[2], 0.0, direction[0]])
        offsets = []
        for point in (current, following):
            base = 0.0 if height_at is None else float(height_at(point[0], point[2]))
            offsets.append(base + lift)
        quad = [current - normal * half + [0.0, offsets[0], 0.0],
                current + normal * half + [0.0, offsets[0], 0.0],
                following + normal * half + [0.0, offsets[1], 0.0],
                following - normal * half + [0.0, offsets[1], 0.0]]
        uvs = [[0.0, travelled / uv_scale], [width / uv_scale, travelled / uv_scale],
               [width / uv_scale, (travelled + length) / uv_scale],
               [0.0, (travelled + length) / uv_scale]]
        add_quad(geometry, quad, uvs, normal=(0.0, 1.0, 0.0))
        if double_sided:
            add_quad(geometry, quad, uvs, normal=(0.0, -1.0, 0.0), flip=True)
        travelled += length


def sheet(geometry: Geometry, corners, *, uv_scale: float = 1.0,
          uv_rect=(0.0, 0.0, 1.0, 1.0), both_sides: bool = True) -> None:
    """A genuine cloth sheet - banner, flag, awning panel."""
    u0, v0, u1, v1 = uv_rect
    uvs = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]]
    add_quad(geometry, corners, uvs)
    if both_sides:
        add_quad(geometry, corners, uvs, flip=True)


# --------------------------------------------------------------- tent canopies
def conical_canopy(geometry: Geometry, center, radius: float, wall_top: float,
                   peak: float, *, sides: int = 16, uv_scale: float = 3.0,
                   sag: float = 0.10, scallop: float = 0.10,
                   overhang: float = 0.22, eave_drop: float = 0.16) -> None:
    """Scalloped canvas cone, sagging between ribs, with an overhanging eave.

    This is the shape language the concept art repeats at every scale: a broad
    conical roof whose edge dips between the radial ribs.
    """
    center = _as_array(center)
    outer = radius + overhang
    angles = np.linspace(0.0, 2.0 * math.pi, sides + 1)
    rows = 4
    circumference = 2.0 * math.pi * outer

    def surface(angle: float, t: float) -> np.ndarray:
        """t = 0 at the eave, 1 at the peak."""
        scallop_phase = 0.5 - 0.5 * math.cos(angle * sides)
        edge_radius = outer * (1.0 - scallop * scallop_phase)
        current_radius = edge_radius * (1.0 - t)
        straight = wall_top - eave_drop + (peak - wall_top + eave_drop) * t
        # Catenary-ish sag between ribs, strongest mid-slope.
        droop = sag * math.sin(math.pi * t) * scallop_phase
        return center + np.array([current_radius * math.cos(angle),
                                  straight - droop,
                                  current_radius * math.sin(angle)])

    for segment in range(sides):
        a0, a1 = angles[segment], angles[segment + 1]
        for row in range(rows):
            t0, t1 = row / rows, (row + 1) / rows
            # Wound a1 -> a0 so the cone's outer surface faces up and outward;
            # the opposite order makes the whole canopy invisible from above.
            corners = [surface(a1, t0), surface(a0, t0), surface(a0, t1), surface(a1, t1)]
            uvs = [[a1 / (2 * math.pi) * circumference / uv_scale, t0 * radius / uv_scale],
                   [a0 / (2 * math.pi) * circumference / uv_scale, t0 * radius / uv_scale],
                   [a0 / (2 * math.pi) * circumference / uv_scale, t1 * radius / uv_scale],
                   [a1 / (2 * math.pi) * circumference / uv_scale, t1 * radius / uv_scale]]
            if row == rows - 1:
                # Collapse the apex row into a triangle to avoid sliver quads.
                apex = surface((a0 + a1) * 0.5, 1.0)
                normal = np.cross(corners[1] - corners[0], apex - corners[0])
                length = np.linalg.norm(normal)
                normal = normal / length if length > 1e-12 else np.array([0.0, 1.0, 0.0])
                geometry.add([corners[0], corners[1], apex], np.tile(normal, (3, 1)),
                             [uvs[0], uvs[1], uvs[2]], [0, 1, 2])
                continue
            add_quad(geometry, corners, uvs)
    # Underside of the eave so the canopy reads as cloth with thickness.
    for segment in range(sides):
        a0, a1 = angles[segment], angles[segment + 1]
        inner0, inner1 = surface(a0, 0.14), surface(a1, 0.14)
        outer0, outer1 = surface(a0, 0.0), surface(a1, 0.0)
        under = [outer1 - [0.0, 0.06, 0.0], outer0 - [0.0, 0.06, 0.0], inner0, inner1]
        # Cloth has thickness: the eave soffit faces down.
        add_quad(geometry, under, _planar_uv(np.asarray(under), uv_scale), flip=True)


def polygon_points(center, radius: float, sides: int, *, rotation: float = 0.0,
                   jitter=None) -> list[tuple[float, float]]:
    """Regular polygon footprint in the XZ plane."""
    cx, _, cz = _as_array(center)
    points = []
    for index in range(sides):
        angle = rotation + 2.0 * math.pi * index / sides
        r = radius if jitter is None else radius * (1.0 + jitter[index % len(jitter)])
        points.append((cx + r * math.cos(angle), cz + r * math.sin(angle)))
    return points
