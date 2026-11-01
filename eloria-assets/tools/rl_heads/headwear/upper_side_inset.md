# Optional upper side ornament inset

`RLHeadwearFit` accepts `warp.upperSideInset` on an exact hairstyle fit. It
moves raised side ornament radially toward the existing tilted band axis, with
smooth height and symmetric bearing fades. The fitted band plane and front/back
ornament are unchanged. This is an offline-authored fit correction, not a live
collision solver.

Configuration uses `insetMm` (strictly positive, at most 20), `heightMm`
(`[start, full]` above the band's plane, 0 <= start < full <= 100), and
`sectorDegrees` (`[fade_in, full_in, full_out, fade_out]` on the absolute
bearing from the front, 0 <= a < b <= c < d <= 180). An optional `minRadiusMm` (1..200, default 1) caps the inset at an
offline-verified skull clearance radius; it never expands an already smaller
part. The displacement never crosses the axis. All values must be finite numbers. Missing or invalid
configuration keeps the previous output exactly.

The first use is piece 111's exact `female/layered_long_female` and
`luminous_female/layered_long_female` fits. Its small raised side plate otherwise
emerges through the long curtain as isolated blue fragments. Keep wildcard,
bald and other hairstyle fits unchanged. Trail subdivision and draping remain
separate: the plate has zero trail weight, so cloth refinement cannot fix it.
Native opt-in still requires the exact fit's `nativeQualified` gate after
actual-client review. The shipped equipment and hair source assets stay intact.

Run `godot-client/tests/test_headwear_upper_side_inset.gd` headlessly for
finite/bound checks, exact absent/invalid behavior, symmetric sectors and
unchanged band/front/back points. Visual qualification must include both
profiles of the actual High and Native heads using the ordinary client path.
