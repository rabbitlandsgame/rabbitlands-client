# Closest-section outside certificate

`closest_section_outside.ClosestSectionOutside` is an optional authoring check
for a complete evaluated fixture. It supplies no distance, placement, normal,
mesh deformation or inside certificate. Existing Native checks keep their
original behavior unless the option is explicitly enabled.

For each query, the point-minus-closest vector selects a plane through the
query. Every intersecting triangle of the complete fixture participates. The
intersection must form unambiguous, simple, closed contours. The query must
lie outside every independently filled contour and clear every boundary.
Open or branched sections, self-crossing/touching contours, near-vertex events,
empty/degenerate sections and boundary queries withhold a certificate.
Nested or overlapping contours never cancel into an outside result.

The Native adapter applies this certificate only to a negative shading-normal
sign. It may change that sign to positive; the exact unsigned distance,
closest point and returned normal stay unchanged. A withheld certificate
retains the original result. Positive results are not certified as inside or
outside by this option, so inside controls and mesh topology remain separate
diagnostics. Displacement and clearance limits are unchanged.

```python
RigidNativePoseUnion(manifest, sex, horizontal_slice_proof=True,
                    closest_section_proof=True)
```

The independent serialized-asset checker exposes the same explicit option:

```text
python native_hair_fixtures.py hair.glb --manifest manifest.json --out result.json --horizontal-slice-proof --closest-section-proof
```

The result records the option and certificate-tool hash. Exact-result cache
keys include both outside-proof options. The complete fixture is assembled
before contact-region filtering; a cropped head or a selectively retained
shirt patch is not a suitable input.

Shading normals and raw triangle normals alone are insufficient to choose a
sign at an edge or vertex. The angle-weighted pseudonormal method has a closed
manifold assumption; it is not substituted for an open actor surface here.
See [Bærentzen and Aanæs, 2005](https://www2.imm.dtu.dk/pubdb/edoc/imm3578.pdf).

Run `test_closest_section_outside.py`, `test_native_hair_fixtures.py`,
`test_native_slice_bounds.py` and `test_native_rigid_pose_union.py`. Private
fixture receipts and source model inputs belong in ignored authoring output.
