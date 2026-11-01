# Native authoring BVH

`NativeAuthoringSurface(source)` is an optional authoring accelerator. It does
not replace the independent exact Native fixture acceptance scan.

Wrap each surface of a `RigidNativePoseUnion`, retaining its transform/inverse:

```python
union.poses = [(NativeAuthoringSurface(surface), transform, inverse)
               for surface, transform, inverse in union.poses]
```

Near-contact queries and every closest-on-edge or closest-on-vertex query
delegate to `source.signed`. This includes positive distances: split lighting
normals can assign opposite signs to the same welded vertex depending on which
incident triangle a float BVH chooses. Exact fallback preserves the source's
complete-fixture outside options, distance, closest point and supplied normal.

Far, unique triangle-interior queries remain approximate. Final acceptance
must run the exact checker with the same explicit outside-proof flags.
