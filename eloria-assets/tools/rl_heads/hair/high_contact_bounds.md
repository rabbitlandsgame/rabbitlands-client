# High contact query bounds

`ContactHead(head, margin_mm=3.2)` is an opt-in guard-only adapter. Pass a
threshold at least as large as every contact margin used by the caller. It
computes the complete current morphed skin's AABB on each query. Points farther
than that threshold from the box cannot contact any contained skin triangle;
other points retain the original `Head.signed` result and rim handling exactly.
Planar or line bounds always query the original surface.

The returned distance for an omitted point is a conservative geometric lower
bound. Its closest point/normal are unused box witnesses, not skin witnesses.
Use this adapter only in a contact guard that never reads those witnesses for
already-clear points. Binding, styling and general nearest-surface queries must
continue using the original head. This adds no default behavior or margin
change and does not combine the High and Native skull fits. `statistics` records
the exact-query and outside-box counts for qualification evidence.

`ContactHead(..., geometric_sign=True)` explicitly selects the optional physical
sign in `BoundedHead.signed`. Face interiors use the geometric face normal,
edges use adjacent face normals and welded vertices use angle-weighted incident
face normals. This prevents large neighboring triangles' lighting weights from
putting an outside temple point on the wrong side. The original nearest-skin
distance, closest point, rim handling and clearance threshold are retained.
Normals used for placement must still come from the intended authoring route.
The default stays unchanged; use the matching explicit policy for authoring and
independent checks. Cached geometric normals are invalidated when source
positions or indices change. This adds no runtime behavior or replacement skin.
