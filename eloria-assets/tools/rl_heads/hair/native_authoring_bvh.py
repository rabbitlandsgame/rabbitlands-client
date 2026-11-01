"""Optional Blender BVH acceleration for Native authoring queries.

This is not an acceptance checker. The independent Native fixture scan stays
exact. Ambiguous nearest edges/vertices always use the source's exact signed
query, even when the approximate lighting-normal sign says a point is far
outside. All exact calls retain the source's complete-fixture outside policy.
"""
import numpy as np
import headref


class NativeAuthoringSurface:
    def __init__(self, source, contact_fallback_mm=5.0, feature_tolerance=1e-6):
        assert np.isfinite(contact_fallback_mm) and contact_fallback_mm >= 0
        assert np.isfinite(feature_tolerance) and 0 < feature_tolerance <= 1e-3
        # Authoring dependency only; importing this module never starts Blender.
        import bpy  # noqa: F401 - initializes the bundled mathutils modules
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        self._vector = Vector
        self.source = source
        self.P, self.N, self.T = source.P, source.N, source.T
        self.tree = BVHTree.FromPolygons(
            [Vector(p) for p in self.P], self.T.tolist(), all_triangles=True)
        self.contact_fallback_m = float(contact_fallback_mm) * .001
        self.feature_tolerance = float(feature_tolerance)
        self.queries = self.exact_queries = self.feature_fallbacks = 0

    def __getattr__(self, name):
        return getattr(self.source, name)

    def signed(self, points):
        points = np.asarray(points, dtype=np.float64)
        assert points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
        if not len(points):
            return np.empty(0), np.empty((0, 3)), np.empty((0, 3))
        nearest = [self.tree.find_nearest(self._vector(p)) for p in points]
        assert all(item[0] is not None for item in nearest)
        closest = np.asarray([item[0] for item in nearest], dtype=np.float64)
        distance = np.asarray([item[3] for item in nearest], dtype=np.float64)
        triangles = self.T[np.asarray([item[2] for item in nearest], dtype=int)]
        barycentric = headref.barycentric(
            closest, self.P[triangles[:, 0]], self.P[triangles[:, 1]],
            self.P[triangles[:, 2]])
        normal = headref.unit((self.N[triangles] * barycentric[:, :, None]).sum(1))
        sign = np.sign(((points - closest) * normal).sum(1))
        sign[sign == 0] = 1
        distance *= sign
        feature = barycentric.min(1) <= self.feature_tolerance
        exact = feature | (distance < self.contact_fallback_m)
        if exact.any():
            distance[exact], closest[exact], normal[exact] = self.source.signed(points[exact])
        self.queries += len(points)
        self.exact_queries += int(exact.sum())
        self.feature_fallbacks += int(feature.sum())
        return distance, closest, normal
