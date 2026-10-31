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
