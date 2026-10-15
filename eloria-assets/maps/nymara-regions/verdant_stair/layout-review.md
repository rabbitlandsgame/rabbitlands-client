# Verdant Stair layout review — 2026-09-07

The western Temple Road now climbs from its original Ssarathi trigger to the
quay, market, shrine, temple and summit shelves. Six fitted stair flights
have full-width lower and upper landings, with contour roads between them.
Their stone beds follow the flight and rest-landing profile below the walking
skin. The cenote outfall bends west of the main stair.

The market occupies a level lower-terrace court beside the arrival. Storage,
crafting, information and training share that court. Three ordered stalls
replace overlapping scatter. The Physick and sanctum doors sit at visible
thresholds; a jade causeway reaches the head of the cenote spiral. Its final
eight-centimetre threshold keeps the bridge and first tread on separate planes.

Five gorge bridges now meet both banks. The lower rope crossing follows the
different heights of its shores, and the western crossing moved upstream to
banks on the same shelf. Boarding aprons extend onto land. Tree crowns, vines
and ground dressing are cleared along the decks after population, preserving
the seeded draws for all remaining placements.

The safe market and lower approaches lead into glider and owl habitat, then
the upper shrine and remote queen, lynx and dragon grounds. The existing
fourteen server wildlife spawns remain, with roads excluded from their
habitats. These are geographic bands following the terraces, rather than
circles cutting through cliffs.

All new pieces use shared routecraft and junglecraft recipes with the existing
jade, mossy stone, gilt, timber and foliage materials. Surface classes were
not renumbered. The manifest sun now follows the client's light-travel
convention; its former upward vector illuminated the region from below.
Offline lighting already used the opposite, toward-sun convention.

## Validation

| Check | Result |
| --- | --- |
| Native grid reachability from default arrival, climb limit 2 | **943,941 / 980,308 = 96.3%**, up from 163,373 / 974,846 = 16.8% |
| Exterior departures | Both reachable in the native grid and final server export |
| Interior thresholds | All seven reachable in both grids |
| Surveyed routes | All twelve complete routes pass the server crossing contract |
| Independent build | Exterior GLB, LOD2, manifest, collision and minimap match byte for byte |
| Server collision repeat | Byte-identical against the final content profile |
| glTF validation | Exterior and LOD2: zero errors or warnings |
| Runtime grounding | 331,776 samples, zero misses, zero errors |
| Coplanar overlap | **337.9 m²**, down from 588.5 m²; none reported on the new stair flights or cenote deck |
| Combined regression suites | See the [three-region verification](../LAYOUT-PASS-2026-09-07.md) |

Native portal checks sample the declared world positions. The quarry portal
is slightly offset from its integer server-tile centre; both its actual native
standing point and its final server trigger are reachable.

The exterior is 30.18 MB with 2,638,945 instanced triangles. LOD2 is 18.39 MB
with 1,065,475 triangles, 59.6% fewer. Seven interior rooms and fourteen secret
sections were rebuilt and their composed collision exported.

## Visual review

All 48 offline and Godot views were refreshed, with a final Godot pass after
the sunlight correction. Godot used GL Compatibility and the package's
manifest environment. Eye-level review cleared bridge foliage, opened the
market court, corrected the cellar thresholds and separated the cenote joint.

[Grand Stair](references/godot-captures/02-grand-stair.webp),
[Temple Road arrival](references/godot-captures/53-temple-road-arrival.webp),
[market court](references/godot-captures/58-market-court.webp),
[cenote landing](references/godot-captures/59-cenote-landing.webp),
[western ravine](references/godot-captures/61-western-ravine.webp),
[rope descent](references/godot-captures/62-middle-rope-descent.webp).

[Concept comparison](references/comparisons/aerial-comparison.webp) and
[contact sheet](references/comparisons/landmark-contact-sheet.webp).

The capture harness shows package geometry. It does not instantiate the
server's service objects. The court images show their reserved space.

## Remaining work

The concept has more architecture and a stronger temple silhouette above its
canopy. The built zone still needs selective canopy shaping around distant
temple views, fuller terrace fronts and fewer obvious foliage cards. Some
bridge boarding shelves and quarry cuts remain visually abrupt. This pass
establishes the connected route and hub; it does not finish every vista.

The overlap scan still reports older hut, house, shrine, aqueduct, tree and
terrain intersections. Runtime warnings remain for 990 cliff/deck height
differences, two house-edge collision/surface mismatches, and the kiln-yard
display anchor 4.64 m above its supporting floor. The kiln huts themselves
stand on ground.

## Rebuilding

Use the documented exterior, interiors and collision-export sequence. Apply
refine_walk_heights, open_walk_surfaces and stamp_solid_landmarks once, in that
order, to a fresh exterior build, then rebuild secrets. Reapplying corrections
to an already corrected grid is not an independent rebuild.

Sync verdant_stair, verdant_stair_insides and verdant_stair_secrets on the
server. Generate served maps, apply continent portals and authored content
with --region verdant_stair, then relocate content. Surveyed crossings retain
the corrected authored surface during the server fold; the older
landmark-centred ramp must not pull them toward neighbouring cliff heights.

The integration rebase also preserves the newer upstream wildlife batches.
Their three regional placement corrections and updated test results are
recorded in the combined review.
