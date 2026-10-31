# RL High cap surface support

`short_surface_guard.guard(head,P,T,deltas,ids,combos,margin=.003,
max_shift_mm=14)` returns contact-only High rest positions and a receipt. It
checks vertices, triangle centres and edge midpoints for every individual
supplied target plus mixed/groom cases. Identity cases use the actual morphed
RL skin. POSITION-split seams receive identical displacement; already-clear
rows stay exact. Targets and input arrays are not modified. Unresolved or
over-limit seating fails closed. Native seating must remain a separate
corrective; the old experimental native flag is explicitly rejected.

Pass only the isolated cap to preserve a painted exterior. To preserve every
old cap row as well, first refine the limiting faces with the conforming cap
refiner, then pass only newly added position/target rows with one degenerate
triangle per new row. Reassemble the unchanged old rows and seated additions,
then run the independent real-client triangle-interior check. `fixed` selects
the2.4mm hidden-cap margin; it is not a freeze mask. New normals/receipts remain
the caller's responsibility. This authoring helper is not asset qualification.

For independently identified limiting exterior faces, `all_faces=True` also
checks faces whose corners all lie beyond the default 18 mm near-skin filter.
A long chord can cross skin while every corner remains clear. Pass the bounded
local face neighborhood explicitly; the default filtering and Native rejection
remain unchanged. Check its adjacent faces and attachment after reassembly.

`geometric_projection=True` uses the signed closest-point separation direction
for a correction, retaining the supplied skin normal only at zero separation.
This avoids tangential drift along interpolated shading normals at ear folds.
The default normal projection, margin, displacement limit and Native rejection
remain unchanged. This option still requires the independent final surface gate.
