"""Optional outside-only certificate in a plane normal to point-minus-closest.

The complete evaluated fixture is required. Distances, witnesses and normals
are never replaced here. Open, branched, touching, self-crossing, coplanar and
degenerate sections provide no certificate. Each simple closed contour is
filled independently, so nested/overlapping components cannot cancel.
"""
import numpy as np


def fallback_plane_normals():
    """Fixed 64-plane schedule; smaller budgets use its exact prefix."""
    index = np.arange(64, dtype=np.float64)
    y = 1 - 2 * (index + .5) / 64
    phi = index * np.pi * (3 - np.sqrt(5))
    radius = np.sqrt(1 - y * y)
    return np.column_stack([radius * np.cos(phi), y, radius * np.sin(phi)])


def _cross(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _simple(contour, epsilon):
    a = contour
    b = np.roll(a, -1, axis=0)
    edge = b - a
    length = np.linalg.norm(edge, axis=1)
    if len(a) < 3 or (length <= epsilon * 2).any():
        return False
    if abs(_cross(a, b).sum()) <= epsilon * epsilon * 4:
        return False
    # Non-adjacent segments may neither cross nor touch. Collinear consecutive
    # edges are allowed; they arise when a plane crosses a triangulated quad.
    for i in range(len(a)):
        indices = np.arange(i + 2, len(a))
        if i == 0:
            indices = indices[indices != len(a) - 1]
        if not len(indices):
            continue
        lo = np.maximum(np.minimum(a[i], b[i]), np.minimum(a[indices], b[indices]))
        hi = np.minimum(np.maximum(a[i], b[i]), np.maximum(a[indices], b[indices]))
        indices = indices[(lo <= hi + epsilon * 2).all(1)]
        if not len(indices):
            continue
        first = _cross(edge[i], a[indices] - a[i])
        second = _cross(edge[i], b[indices] - a[i])
        third = _cross(edge[indices], a[i] - a[indices])
        fourth = _cross(edge[indices], b[i] - a[indices])
        tolerance = epsilon * np.maximum(length[i], length[indices]) * 2
        if (((np.minimum(first, second) <= tolerance) &
             (np.maximum(first, second) >= -tolerance)) &
            ((np.minimum(third, fourth) <= tolerance) &
             (np.maximum(third, fourth) >= -tolerance))).any():
            return False
    return True


class ClosestSectionOutside:
    def __init__(self, complete_mesh, epsilon=1e-8, cache_points=8192,
                 fallback_plane_count=0):
        assert 0 < epsilon <= 1e-6 and cache_points >= 0
        assert type(fallback_plane_count) is int and 0 <= fallback_plane_count <= 64
        self.triangles = np.asarray(complete_mesh.triangles, dtype=np.float64)
        assert len(self.triangles) and np.isfinite(self.triangles).all()
        self.epsilon = float(epsilon)
        self.cache_points = int(cache_points)
        self.cache = {}
        self.fallback_plane_count = fallback_plane_count
        self.fallback_normals = fallback_plane_normals()[:fallback_plane_count]
        self.volumetric = bool(((complete_mesh.bounds[1] - complete_mesh.bounds[0]) > epsilon * 2).all())
        self.last_query = {}

    def _certificate(self, point, closest):
        eps = self.epsilon
        separation = point - closest
        distance = np.linalg.norm(separation)
        if distance <= eps * 4:
            return False, 'near_surface'
        normal = separation / distance
        ref = np.eye(3)[np.argmin(abs(normal))]
        u = np.cross(normal, ref)
        u /= np.linalg.norm(u)
        v = np.cross(u, normal)
        dy = (self.triangles - point) @ normal
        selected = (dy.min(1) <= eps) & (dy.max(1) >= -eps)
        triangles, dy = self.triangles[selected], dy[selected]
        if not len(triangles):
            return False, 'empty_section'
        if (abs(dy) <= eps).any():
            return False, 'vertex_or_coplanar_event'
        crossed = (dy > 0) != (np.roll(dy, -1, axis=1) > 0)
        if not (crossed.sum(1) == 2).all():
            return False, 'degenerate_intersection'
        first = triangles[crossed]
        second = np.roll(triangles, -1, axis=1)[crossed]
        d0, d1 = dy[crossed], np.roll(dy, -1, axis=1)[crossed]
        points = first + (second - first) * (d0 / (d0 - d1))[:, None]
        projected = (points - point) @ np.stack([u, v]).T
        _, at, inverse = np.unique(np.round(projected / eps).astype(np.int64),
                                    axis=0, return_index=True, return_inverse=True)
        vertices = projected[at]
        edges = np.unique(np.sort(inverse.reshape(-1, 2), axis=1), axis=0)
        if (edges[:, 0] == edges[:, 1]).any():
            return False, 'collapsed_edge'
        neighbors = [[] for _ in vertices]
        for a, b in edges:
            neighbors[a].append(b)
            neighbors[b].append(a)
        if any(len(n) != 2 for n in neighbors):
            return False, 'open_or_branched_section'
        contours, seen = [], set()
        for start in range(len(vertices)):
            if start in seen:
                continue
            cycle, previous, current = [], -1, start
            while current not in seen:
                seen.add(current)
                cycle.append(current)
                following = neighbors[current][0]
                if following == previous:
                    following = neighbors[current][1]
                previous, current = current, following
            if current != start or len(cycle) < 3:
                return False, 'non_cycle'
            contour = vertices[cycle]
            if not _simple(contour, eps):
                return False, 'non_simple_contour'
            contours.append(contour)
        for contour in contours:
            a, b = contour, np.roll(contour, -1, axis=0)
            edge = b - a
            t = np.clip(-(a * edge).sum(1) / (edge * edge).sum(1), 0, 1)
            if (np.linalg.norm(a + t[:, None] * edge, axis=1) <= eps * 2).any():
                return False, 'near_boundary'
            crossed = (a[:, 1] > 0) != (b[:, 1] > 0)
            intercept = np.zeros(len(a))
            np.divide(-a[:, 1] * edge[:, 0], edge[:, 1], out=intercept,
                      where=abs(edge[:, 1]) > 1e-30)
            intercept += a[:, 0]
            if np.count_nonzero(crossed & (intercept > 0)) % 2:
                return False, 'inside_contour'
        return True, 'outside_all_complete_simple_contours'

    def _with_fallback(self, point, closest):
        result, reason = self._certificate(point, closest)
        if result or not self.fallback_plane_count:
            return result, reason
        # Only complete simple closed sections can certify outside. Lighting
        # normals and inconclusive planes never supply a sign change.
        for normal in self.fallback_normals:
            result, fallback_reason = self._certificate(point, point - normal)
            if result:
                return True, fallback_reason
        return False, reason

    def outside(self, points, closest):
        points = np.ascontiguousarray(points, dtype=np.float64)
        closest = np.ascontiguousarray(closest, dtype=np.float64)
        assert points.ndim == 2 and points.shape[1] == 3 and closest.shape == points.shape
        assert np.isfinite(points).all() and np.isfinite(closest).all()
        result = np.zeros(len(points), bool)
        reasons = {}
        if not self.volumetric:
            self.last_query = {'points': len(points), 'fallback': 'non_volumetric'}
            return result
        for i, (point, cp) in enumerate(zip(points, closest)):
            key = point.tobytes() + cp.tobytes()
            value = self.cache.get(key)
            if value is None:
                value = self._with_fallback(point, cp)
                if len(self.cache) >= self.cache_points:
                    self.cache.clear()
                if self.cache_points:
                    self.cache[key] = value
            result[i], reason = value
            reasons[reason] = reasons.get(reason, 0) + 1
        self.last_query = {'points': len(points), 'proven_outside_points': int(result.sum()), 'reasons': reasons}
        if self.fallback_plane_count:
            self.last_query['fallback_plane_count'] = self.fallback_plane_count
        return result
