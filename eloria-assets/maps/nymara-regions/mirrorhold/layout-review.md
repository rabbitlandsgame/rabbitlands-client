# Mirrorhold layout review — 2026-09-07

Final combined tests, complete-route checks and fresh reproduction results
are recorded in the [three-region review](../LAYOUT-PASS-2026-09-07.md).
The checkpoint counts below record this region's earlier individual pass.

The Sanctuary Road now enters on purpose: a bent marble causeway joins the
south watch apron, the colonnaded island and the quay road. The citadel and
snow peaks stay in view across the lake. The shorter side arms serve as
fishing piers with skiffs and crates. Cardinal openings in the colonnade
clear the bridge approaches.

Three visible stone entrances replace portals that previously sat inside
the orrery, fountain and cliff-town scenery. The Lens Vault opens below the
orrery platform, the cistern opens beside the fountain court, and the Stair
Cellars have a broad court at the foot of the houses. A graded lane descends
from the western arrival. Information, storage, crafting and training share
the south side of the fountain court; road waygates retain their roles.

All additions use the existing procedural stone, marble, slate and wood.
Continuous decks, the upward-facing annular promenade and the cellar
entrance are shared routecraft recipes. No material block or imported asset
was added. The initial collision builder now rasterises actual walk
triangles; it no longer opens a bounding disc around a long bent bridge.
The normal three correction passes still follow the build.

## Validation

| Check | Result |
| --- | --- |
| Native grid reachability from default arrival, climb 2 | 525,456 / 626,682 walkable cells: **83.8%**, up from 506,050 / 622,877 (**81.2%**) |
| Exterior departures | All five reachable in the native grid and final server export |
| Interior thresholds | All three reachable in both grids |
| Reproduction | Exterior GLB, LOD2, manifest, collision and minimap match the independent rebuild; added road metadata was checked against the final built terrain |
| Server collision repeat | Byte-identical against the final profile |
| glTF validator | Exterior and LOD2: zero errors or warnings |
| Runtime grounding | 331,776 samples, zero misses, zero errors |
| Coplanar overlap | **336.3 m²**, down from 873.1 m² (**61.5% less**); none on the new decks or entrances |
| Client suite | **148 failed, 102 passed, 7,039 subtests passed**; failures match the measured baseline |
| Server suite | **1,501 passed, 351 subtests passed** after the final wildlife road exclusions |

The exterior is 22.39 MB with 1,270,602 instanced triangles. LOD2 is 12.38 MB
with 916,968 triangles. Interiors and secrets were rebuilt. Mirrorhold's
interior builder exports its composed collision directly, which the server
reads from the interior package; it has no separate export wrapper.

The new road metadata keeps wildlife off the lake promenade and cellar lane.
It displaced an otter that the earlier content pass had put on a fishing
pier, while retaining the region's wildlife counts.

## Visual review

All 26 offline and Godot views were refreshed. Godot used GL Compatibility
and the package's own manifest environment. The eye-level review widened the
cellar court and moved the southern waystation off its submerged setback.

[Sanctuary arrival](references/godot-captures/21-sanctuary-arrival.webp),
[lake promenade](references/godot-captures/22-lake-promenade.webp),
[cellar court](references/godot-captures/23-cellar-lane.webp),
[Lens Vault](references/godot-captures/24-lens-vault-entry.webp),
[cistern court](references/godot-captures/25-cistern-court.webp).

[Concept comparison](references/comparisons/aerial-comparison.webp) and
[contact sheet](references/comparisons/landmark-contact-sheet.webp).

The package capture does not instantiate server service objects. It shows
the space reserved for them, with the same renderer and environment as the
map package.

## Remaining work

The upper town still has abrupt terrain cuts and uneven house foundations.
The quarry and remote mountain content need a fuller route and habitat pass.
The old dome, hall, roof and basin meshes account for the remaining overlaps.

Runtime warnings remain for 542 adjacent cliff/deck height differences, the
existing mirror-basin secret marker below a surface, and the orrery's display
anchor above its supporting floor. The two northern passes were already
connected before this pass; the formerly isolated Four Gates crossing was
on the southern shore.

Use the documented rebuild sequence, then the scoped --region mirrorhold
options for collision sync, continent portals and content authoring. Run the
normal content relocation pass afterward. This includes both directions of
the affected crossing and interior links.

The integration rebase also preserves the newer upstream wildlife batches.
Their three regional placement corrections and updated test results are
recorded in the combined review.
