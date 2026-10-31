"""Optional outside-only proof from complete, closed horizontal contours.

No distance or placement is supplied. Open, branched, coplanar, touching and
degenerate sections fall back to the caller's original sign. Each independent
closed contour is treated as filled, so overlapping/nested parts cannot cancel
one another into a false outside result.
"""
import numpy as np


class ClosedSectionOutside:
    def __init__(self, complete_mesh, epsilon=1e-8, cache_planes=8192):
        assert 0 < epsilon <= 1e-6 and cache_planes >= 0
        self.mesh = complete_mesh
        self.triangles = np.asarray(complete_mesh.triangles, float)
        assert len(self.triangles) and np.isfinite(self.triangles).all()
        self.epsilon = float(epsilon)
        self.cache_planes = int(cache_planes)
        self.cache = {}
        self.volumetric = bool(((complete_mesh.bounds[1] - complete_mesh.bounds[0]) > epsilon * 2).all())

    def _contours(self, y):
        eps = self.epsilon
        lo, hi = self.mesh.bounds.copy()
        lo[1], hi[1] = y - eps, y + eps
        ids = list(self.mesh.triangles_tree.intersection(np.r_[lo - eps, hi + eps]))
        segments = []
        for tri in self.triangles[ids]:
            dy = tri[:, 1] - y
            # A plane through a vertex/edge has an ambiguous contour topology.
            if (np.abs(dy) <= eps).any():
                return None
            crossed = (dy > 0) != (np.roll(dy, -1) > 0)
            if not crossed.any():
                continue
            first, second = tri[crossed], np.roll(tri, -1, axis=0)[crossed]
            points = first + (second - first) * ((y - first[:, 1]) / (second[:, 1] - first[:, 1]))[:, None]
            if len(points) != 2:
                return None
            segments.append(points[:, [0, 2]])
        if not segments:
            return None
        points = np.asarray(segments).reshape(-1, 2)
        _, first, inverse = np.unique(np.round(points / eps).astype(np.int64), axis=0, return_index=True, return_inverse=True)
        vertices = points[first]
        edges = np.unique(np.sort(inverse.reshape(-1, 2), axis=1), axis=0)
        if (edges[:, 0] == edges[:, 1]).any():
            return None
        neighbors = [[] for _ in vertices]
        for a, b in edges:
            neighbors[a].append(b)
            neighbors[b].append(a)
        if any(len(n) != 2 for n in neighbors):
            return None
        seen = set()
        contours = []
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
                return None
            contours.append(vertices[cycle])
        return contours

    def outside(self, points):
        points = np.asarray(points, float)
        assert points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
        result = np.zeros(len(points), bool)
        if not len(points) or not self.volumetric:
            return result
        for y in np.unique(points[:, 1]):
            if float(y) not in self.cache:
                contours = self._contours(float(y))
                if len(self.cache) >= self.cache_planes:
                    self.cache.clear()
                if self.cache_planes:
                    self.cache[float(y)] = contours
            else:
                contours = self.cache[float(y)]
            if contours is None:
                continue
            rows = np.flatnonzero(points[:, 1] == y)
            q = points[rows][:, [0, 2]]
            outside_all = np.ones(len(rows), bool)
            for contour in contours:
                a, b = contour, np.roll(contour, -1, axis=0)
                # Boundary points and near-degenerate ray events provide no proof.
                edge = b - a
                t = np.clip(np.sum((q[:, None] - a) * edge, axis=2) / np.sum(edge * edge, axis=1), 0, 1)
                nearest = a + t[:, :, None] * edge
                boundary = (np.linalg.norm(q[:, None] - nearest, axis=2) <= self.epsilon * 2).any(axis=1)
                crosses = (a[:, 1] > q[:, None, 1]) != (b[:, 1] > q[:, None, 1])
                intercept = np.zeros_like(t)
                np.divide((q[:, None, 1] - a[:, 1]) * edge[:, 0], edge[:, 1], out=intercept, where=np.abs(edge[:, 1]) > 1e-30)
                intercept += a[:, 0]
                inside = np.count_nonzero(crosses & (q[:, None, 0] < intercept), axis=1) % 2 == 1
                outside_all &= ~inside & ~boundary
            result[rows] = outside_all
        return result
