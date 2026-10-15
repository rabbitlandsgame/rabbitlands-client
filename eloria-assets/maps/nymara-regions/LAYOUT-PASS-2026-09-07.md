# Nymara layout pass — 2026-09-07

This pass covers Westhaven, Mirrorhold and Verdant Stair in the continent
worktrees. It repairs their principal missing connections and organises the
settlements around working routes, services and geographic habitats. Other
regions, Four Gates and gauntlet interiors remain for subsequent passes.

| Region | Layout result | Native ground reachable from arrival |
| --- | --- | --- |
| [Westhaven](westhaven/layout-review.md) | Cart ascent and north gate, shipyard and Lamp Rock causeways, grouped quay services, farmhouse above planted Wheat and Sage strips | 68.3% → **86.2%** |
| [Mirrorhold](mirrorhold/layout-review.md) | Bent Sanctuary Road and lake promenade, working fishing piers, fountain service court and three visible cellar entrances | 81.2% → **83.8%** |
| [Verdant Stair](verdant_stair/layout-review.md) | Six fitted terrace stairs, five bank-to-bank gorge bridges, cenote landing, lower market court and visible interior thresholds | 16.8% → **96.3%** |

The existing regional palettes and architectural forms are retained: warm
port masonry and roofs, pale marble beside the mountain lake, and jade,
mossy stone and gilt in the jungle. New reusable geometry lives in the shared
toolkit. No imported models, external textures or new surface-class blocks
were added. Verdant Stair's sunlight vector was reversed to match the
client's direction-of-light convention.

## Integration with current develop

The subsequent rebase preserves the new upstream wildlife records. One
Mirrorhold crag ogre moves to the nearest connected ledge; a Verdant treant
and praying mantis move one tile each onto standable ground. Other regions'
new spawn records remain unchanged.

The rebased server suite passes **1,515 tests and 351 subtests**.

The rebased client suite reports **93 failures, 124 passes and 8,892 passing
subtests** after upstream actor and equipment updates. Its map tests pass.
The earlier results below record the original comparison baseline.

## Original pass verification

The server suite passes **1,515 tests and 351 subtests**, against the starting
1,495 tests. The client Python suite reports **148 failures, 104 passes and
7,039 passing subtests**; its failure count matches the measured starting
baseline. The existing rig, equipment and GDScript reference failures remain.

All eleven exterior departures in these three regions are reachable from
their arrivals in both the native and server grids. All three Mirrorhold and
seven Verdant Stair interior thresholds are reachable. Westhaven reaches its
six mainland/Lamp Rock thresholds; Gullstone remains a separate island.

The server crossing contract now walks eighteen complete surveyed routes:
two in Westhaven, four in Mirrorhold and twelve in Verdant Stair. These
standing points cover the real banks and full flights, replacing partial
bridge extents inferred from a nearby landmark.

Fresh builds reproduce the exterior GLB, LOD2, manifest, collision and minimap
byte for byte for all three packages. Repeating each server collision export
against its final content profile also produces identical compressed bytes.
Both GLBs per region validate without errors or warnings. Runtime grounding
reports zero misses and zero errors for each region.

The overlap scan decreased from 7,028.8 to 2,167.2 m² in Westhaven, 873.1 to
336.3 m² in Mirrorhold, and 588.5 to 337.9 m² in Verdant Stair. The new walking
decks and fitted stairs have no reported coplanar pairs; older scenery
overlaps and runtime warnings are listed in each regional review.

## Review the result

The packages contain 28 Westhaven, 26 Mirrorhold and 48 Verdant Stair views
from both the offline renderer and Godot. The final engine captures use
GL Compatibility and --environment=manifest.

[Westhaven fields](westhaven/references/godot-captures/22-gullscar-fields.webp),
[Mirrorhold Sanctuary arrival](mirrorhold/references/godot-captures/21-sanctuary-arrival.webp),
[Verdant Grand Stair](verdant_stair/references/godot-captures/02-grand-stair.webp),
[Verdant market](verdant_stair/references/godot-captures/58-market-court.webp).

The engine harness draws the map package, including its real environment.
Service objects are spawned by the full client, so these captures show the
space reserved for the hub services.

## Rebuild and next work

Follow CONTINENT.md from a fresh exterior build, including all three
correction passes exactly once and in their documented order. The server
collision sync, portal writer and content author now accept --region for
scoped updates; portal updates include both ends of each affected link.
Composed interiors and secrets are synced by their own map IDs.

The known Crownwater portal-writer rejection remains outside this pass.
Gullstone needs a designed harbour ferry. Mirrorhold's upper town foundations
and Verdant Stair's temple sightlines, cliff dressing and canopy still need
more work. The other eight exterior regions, Four Gates and eight gauntlets
have not received this layout pass.

Builds, tests and captures were first limited to eight logical cores and
then reduced to the same four logical cores at the user's request.
