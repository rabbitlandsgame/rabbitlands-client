# Geographic paint finish

`terrain_paint.apply(build, region)` runs after connector finishing in Crownwater,
Four Gates, Manymouth, Ssarathi and Grey Moors. It changes only visual terrain
paint copies. Native terrain, roads, water, placed structures and boundary
heights remain unchanged.

At competing corners, each terrain face belongs to the neighboring recipe
whose actual finite common boundary is nearest its centroid. Sorted recipe IDs
break equal-distance ties. Both continent mixture layers retain their masks
and UVs together; road turf/frost/paving layers likewise share ownership.
Redundant nested road paint is removed. Paint is seated on its own original
physical terrain class with separate 2–20 mm visual offsets, below 30 mm road
decks. This prevents later terrain grading from collapsing paint onto its base.

The coordinator certifies this directory only for those five regions. The
finish is independent of the frozen physical geometry helpers. Native terrain
mask quantization is outside this correction; exact emitted paint overlap,
physical array equality, and final camera checks remain separate evidence.
