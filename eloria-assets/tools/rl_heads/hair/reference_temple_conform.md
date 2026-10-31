# Bounded temple correction

`conform_temples(head, scalp, P, N, T, ranges, spec)` is an optional authoring
step for real geometric boundary spikes in an extracted painted surface. It
does nothing without `spec.temple_conform`. It does not modify UVs, indices,
paint or source files. Run it before skin and grooming targets are authored.

The owning profile gives four absolute-longitude ramp angles, a small hairline
margin/softness and a maximum displacement in millimetres. The correction is
symmetric as a rule; it preserves the source's asymmetry. Only the narrow
boundary neighborhood below the intended temple curve can move. Complete
source offsets and shading normals are rotated between scalp frames, retaining
tangential surface flow. The bun, nape and frontal mass remain outside the
correction. The helper reports per-side changed counts and maximum movement,
and fails closed at the configured displacement limit.

`preserve_parts: ["shell"]` optionally keeps a deliberately wider hidden
coverage cap completely unchanged. Its own boundary may extend under the
painted exterior; it must not be lifted back to the exterior's visible curve.

Example used by the tied pilot: ramps `[55, 70, 105, 120]`, margin 0.5 degrees,
softness 1.5 degrees, limit 30mm. These values are profile choices, not global
defaults. Keep an ordinary narrow 1–2mm root-coverage feather after conformance.
Both profiles, front and rear, all identities, LODs, clearance and coverage must
still pass review. The helper does not qualify a hairstyle by itself.
