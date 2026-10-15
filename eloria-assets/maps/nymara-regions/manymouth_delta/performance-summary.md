# Current circulation package - 8 September 2026

The current full GLB is 29,783,880 bytes with 2,307,227 instanced triangles;
the reduced GLB is 17,783,748 bytes with 1,431,989 instanced triangles.
The package retains 49 materials and an estimated 262,275,072 bytes of
uncompressed texture storage. Full-build warnings identify four unused Grey
Moors texture pins; the reduced build also leaves woven_cloth unused.

These are package totals, not measured frame times. The 27 reviewed Godot
captures use GL Compatibility and the package's own environment. See
layout-review.md and performance.json for the current evidence.

The older notes below describe the first package and are retained as history.

# Manymouth Delta performance summary

Machine-written measurements live in `performance.json`; this file is the human
reading of them. Both come out of the same build, so they cannot drift.

## The package

| | `world.glb` | `world-lod2.glb` |
| --- | --- | --- |
| Size | **26.40 MB** | 18.71 MB |
| Nodes | 11,731 | 4,196 |
| Unique triangles | 486,653 | 351,704 |
| Instanced triangles | **2,458,407** | 1,559,927 |
| Embedded texture bytes | 21.0 MB | 8.9 MB |
| Texture memory, uncompressed | 167 MB | 42 MB |
| Materials embedded | 22 | 22 |

The reduced package is **36.5% fewer instanced triangles** and 29% smaller. It
carries far-tier vegetation only, drops ground dressing and mangrove root mats
entirely, thins the mangrove belt from 1,500 candidates to 520, and halves every
texture.

## Against the budget

The repository's stated desktop guideline is 1.5 M visible triangles and 512 MiB
of texture, from `four-gates-city/performance-summary.md`.

| Region | Extent | Instanced tris | Triangles / mÂ² |
| --- | --- | --- | --- |
| Four Gates | â€” | 4,538 | â€” |
| Mirrorhold | 576 m | 1,246,632 | 3.8 |
| **Manymouth Delta** | **576 m** | **2,458,407** | **7.4** |
| Amberwood | 576 m | 3,123,378 | 9.4 |

Manymouth sits between the two existing 576 m regions, closer to Amberwood than
to Mirrorhold, at **1.6Ã— the triangle guideline** and well inside the texture
one. That is the expected place for it: it is a vegetated region like Amberwood
rather than a stone one like Mirrorhold, but two thirds of its area is water and
carries no vegetation at all, so the tree count is spread over a third of the
ground.

The target set before building was 7 triangles per square metre and the build
came out at 7.4, measured every rebuild.

## Where the triangles are

| | Instances | Share of instanced tris |
| --- | --- | --- |
| Palms, nipa and young palms | 2,494 | ~44% |
| Mangrove trees and root mats | 1,500 | ~19% |
| Terrain (six surface classes) | 6 meshes | ~13% |
| Walkway network, decks and landings | 101 | ~8% |
| Stilt houses and halls | 87 | ~7% |
| Water planes | 2 meshes | ~5% |
| Ground dressing, props, boats, ruins | ~2,400 | ~4% |

Vegetation is 63% of the instanced total, which is what the per-instance detail
tier is for: 10% of palms are built at the high tier, 30% at mid and 60% at low.
Raising the low-tier share by ten points would take roughly 6% off the total.

## The cheapest levers, in order

1. **Per-instance detail tier.** Already the main control. The high tier is 1,266
   triangles a palm against 550 at low.
2. **Ground-dressing subdivision.** 2,192 undergrowth and reed patches at ~28
   triangles each. Cuttable to zero with no silhouette change.
3. **Mangrove root mats.** 943 instances of 320 triangles, purely to keep the
   channel banks from reading as clean edges. The reduced package already drops
   them.
4. **Pile fields.** Every deck and every house stands on one. Already six-sided
   cylinders with the interior of each field thinned to a checkerboard; going
   further starts to show.

## What this does not measure

Nothing streams and nothing switches LOD at runtime: `world-lod2.glb` exists but
the Godot loader does not select between the two packages. The figures above are
whole-package totals, not what is on screen â€” the client draws the entire region
at once. In the in-engine check the loader batched the scene into **95 static
batches over 3,673 instances**, which is the number that actually matters for
draw calls and is the one to watch if this region is ever profiled properly.

Frame time has **not** been measured. Real client frames were rendered for
comparison captures, but no frame-time or draw-call profiling was run, so
nothing here is a statement about whether the region hits any frame budget.

## The four pinned-but-unreferenced materials

The reduced build warns that `timber_dark`, `timber_warm`, `undergrowth` and
`woven_cloth` are pinned but unreferenced. All four *are* referenced by the full
package; they fall out only when the reduced build drops ground clutter and
props. They therefore cost the LOD2 package about 1.4 MB of embedded texture for
nothing. Fixing it means a second, narrower material pin for the reduced build.
The full package's pin is exact â€” zero unreferenced materials.
