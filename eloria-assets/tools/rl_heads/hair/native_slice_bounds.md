# Optional complete-fixture horizontal outside proof

`load_fixture(manifest, record, horizontal_slice_proof=True)` opts into a
conservative sign correction. The default remains unchanged. The checker has
the matching `horizontal_slice_proof` argument and CLI
`--horizontal-slice-proof`; its exact-result cache includes that policy.

The proof uses all triangles from the hash-verified evaluated body, scalp and
shirt parts **before** the existing contact-region filtering. It does not use
a sparse head, a bind-space part or a replacement collision surface. The
existing geometric query, distances, closest points and supplied normals stay
unchanged.

For each query height, the helper intersects the complete actual surface with
that horizontal plane. Every edge crossing contributes its exact interpolated
X/Z position. Horizontal edges contribute both endpoints. If the point is
outside the resulting conservative X/Z bounds, it cannot be inside the actor's
cross-section, so only the sign of its existing distance is made positive.
The original sign is retained inside those bounds. Empty, degenerate and
near-coplanar sections supply no proof and fall back to the prior behavior.
An explicit numerical slack expands the bounds; it never relaxes the 2 mm gate.

The optional `EvaluatedNativeSurface.proven_outside(points)` combines the old
whole-mesh proof and this opt-in proof. A union-query accelerator must apply
that method to each corresponding complete fixture after reconstructing its
own original sign; a different fixture's proof cannot be reused.

This is a sign proof only. It is not a distance query, nearest-point estimate,
placement field, binding surface or runtime change. Full identity, grooming,
LOD, pose and actual-client qualification remains mandatory.

Synthetic tests cover closed cubes/tetrahedra, skew and varying cross-sections,
real interior contacts, complete-versus-filtered sources, empty/coplanar
fallback and exact bounded plane caching. Actual measured male hair witnesses
confirmed two false negative signs changed to positive with geometric distance,
closest point and normal exactly preserved; the separate real ear contact
remained negative. Hashes and exact witness coordinates stay in ignored
authoring receipts.
