# The Drowned Arcades — modeling assumptions

The Crownwater concept detail board supplies the pale marble, turquoise
lagoon, verdigris and gilt, repeated round arches and built stone waterfront.
The gauntlet's old-city customs lore supplies the use of the rooms. Every
piece and texture is generated in the shared toolkit.

The dry staging bay provides preparation space, a cargo store and a small
bell. Beyond it, raised bonded-store plinths and inspection counters explain
the Customs Arcade's side aisles. Shallow water covers the old mosaic floor;
the central lane stays wide enough for the existing encounters.

The Bell Walk is carried by three masonry arches reaching the chamber bed.
Its balustrades border the walk surface, and three elevated arcade frames
divide the crossing into shorter views. Its original timed leg is retained.

Cisterns stand beside the circulation lane, with gates in vertical guides,
screw lifts, handwheels, dark throats and visible outfalls into raised troughs.
The Long Arcade repeats the same architecture beside cargo alcoves and the
existing Kelp alcove. The two branches distinguish a maintained valve aisle
with bonded stores from a silted passage with fallen marble pier fragments.
The branch names and encounter choices retain their published identities.

Flooded rooms carry water 0.32 metres above real walk floors, retained by
0.4-metre stone thresholds at their doors. These thresholds are walk geometry
and remain climbable on the server grid. Water is clipped around cistern
footprints so a basin never contains two overlapping transparent skins.
Only the explicitly declared lagoon material is ignored as a solid obstacle;
this policy neither creates walk ground nor reopens a gate.

The Campanile Stair rises to a dry upper court. Smaller bells on plinths
lead to the great hollow bell above the reward doorway, carried by a yoke
between the arch piers. A rear dais step completes the route to the vault.
Shorter connecting passages remove thirty-six metres of empty traversal
while preserving seven legs, the fork, timed crossing and boss court.
The safe arrival and escalating route take the place of an exterior hub
and danger rings in this instance.

Shared arcadecraft recipes supply frames, hollow bells, sluice lifts and
cargo bays. Crownwater's six texture recipes now live in crownmaterials;
the exterior's crownkit module remains a compatibility entry point. All
eighteen base-colour, ORM and normal arrays match the former implementation
at their default full sizes. Material names and existing surface IDs are
preserved, and registration appends missing entries without reordering.

Local material batches keep point lights near their intended surfaces.
Lids use add_overhead and the package declares gameplay cutaways. The
environment has no sun, cool ambient fill and warm lamps; review captures
use that actual manifest. The retained chamber envelopes provide clear
fight floors rather than reproducing every exterior architectural detail.

The package owns a geometry-derived walk grid. Do not apply the exterior
height-field corrections: intentional gate cuts must stay sealed. The
server layout refresh moves published content onto authored candidates and
preserves rules, rosters, rewards, keeper coordinates and exterior returns.
