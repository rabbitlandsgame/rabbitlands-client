# Preserve reference shape while fitting hair

Keep the approved extraction immutable. Record positions and original edge IDs
after neutralization, sex mapping, head seating and body seating. A short source
edge becoming a long triangle through the skull is a placement failure; inspect
the first stage that creates it before filling holes, deleting faces or raising
a displacement limit. Retain rejected stages privately.

## Inverse identity fitting

`reference_surface.neutralize(..., exact=False)` reverses the blended identity
field without first applying forward nearest-surface clearance. The original
default remains available for exact historical replay. New preparation profiles
can request this path with:

```json
{"neutralize_identity_only": true}
```

`keep_clear=False` alone does not disable `Binding.delta`'s separate `exact`
clearance step. Subtracting that forward projection can send neighbouring source
points in opposite directions. Measure edge changes on the actual extraction
when selecting the identity-only path.

## Coherent placement

`build_loose_reference.prepare(args, head_fit=callback)` optionally replaces the
initial nearest-surface head seating after neutralization and sex mapping. The
callback receives the mapped head and copies of positions, normals, triangles
and profile, and returns positions, unit normals and a serializable receipt. It must
preserve vertex count and triangle correspondence. Without a callback, the
existing preparation path is retained.

Use a measured, continuous field for a source region that crosses the head's
medial axis. Verify the unaffected rows exactly and transport the changed
surface normals. A placement witness is separate from a physical closest-point
query; do not replace independent clearance checks with a directional envelope.

The `preserve_curtain_depth` profile option selects continuous body placement.
Tied-hair identity and grooming construction also forwards that option, so a
later step does not restore the old front/back divide. Check source-position
weld groups after every correction: moving UV copies independently can reopen
seams even when scalp coverage passes.

## Qualification and packaging

Check vertices and face centres/edge midpoints on triangles with edges of at
least 5 mm, across the identity and grooming states. Check the body and shirt as
well as the head. Scalp coverage and vertex-only clearance do not establish
triangle-interior clearance. Keep signed-distance witnesses and distinguish
actual intersections from incorrect shading-normal signs before altering hair.

Native head tiers need their separate corrective and evaluated control/pose
fixtures. High identity shapes are not a substitute for those fixtures. Retain
the style's declared triangle and displacement limits, verify detail attachment,
and review the final imported texture through ordinary client quality switching.

Only register a body variant after its own gates pass. The saved hairstyle byte
and frozen semantic modules remain compatible; an unavailable body fit stays
unregistered. Use [lossless compaction](compact_hair_glb.md) after fitting, retain
the authoring original, and keep all detailed source and recovery receipts out
of the published asset. The [rounded crest workflow](rounded_crest.md) uses the
same appearance controls with an independent close cap and explicit clump roles.
