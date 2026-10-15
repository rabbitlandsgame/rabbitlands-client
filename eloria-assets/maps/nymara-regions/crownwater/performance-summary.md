# Crownwater performance summary

The current 396-metre coastal package is 22.13 MB / 579,630 instanced triangles;
the far package is 13.29 MB / 567,318 triangles. The matched 576-metre baseline
was 33.47 MB / 931,090 triangles and 20.66 MB for its far package. Exact current
measurements are in `performance.json`; see `coastal-review.md` for validation.

The lagoon is a continuous water plane occluded by the actual shoreline, with
an exactly partitioned shared causeway patch. Removing the coarse shoreline
mask also removes unnecessary flat-water triangles from both packages.

The 1440 × 900 gameplay-camera survey is runtime/composition evidence rather
than a controlled GPU benchmark. Window focus, frame caps and neighbor residency
affect frame timing; raw samples and draw counts remain in each `survey.json`.

**Historical performance notes follow.**

Current layout pass: full package 33.47 MB and
931,510 instanced triangles; reduced package
20.66 MB and 767,978
instanced triangles. Surveyed arches replace overlapping length-class masonry.
See [layout-review.md](layout-review.md) for current validation and comparison
against the previous package; historical measurements below predate this pass.


Measured from the shipped package, not estimated.

| Metric | `world.glb` | `world-lod2.glb` |
| --- | --- | --- |
| Size | 23.45 MB | 14.01 MB |
| Nodes | 1,892 | 1,697 |
| Unique triangles | 587,040 | 433,888 |
| Instanced triangles | 1,273,378 | 1,109,698 |
| Embedded texture bytes | 18.95 MB | - |

## Against the repository guideline

The stated desktop guideline is **1.5 M visible triangles and 512 MiB of
texture**, from `four-gates-city/performance-summary.md`.

| | Value |
| --- | --- |
| Instanced triangles | **1,273,378 - inside the guideline** |
| Region area | 331,776 m2 (576 x 576) |
| Triangles per square metre | **3.84** |
| Amberwood, for calibration | 3,146,376 triangles, 9.5 per m2, ~2.1x the guideline |
| Four Gates, for calibration | 4,538 unique triangles, 3.0 MB |

Crownwater comes in at about 40% of Amberwood's triangle load for the same 576 m
extent. That is not a virtue of the build so much as of the region: 74% of the
footprint is water, and a water plane is cheap. The built ground carries a
comparable density to Amberwood's settlement.

## Where the triangles are

| | Triangles | Note |
| --- | --- | --- |
| Terrain sub-meshes | ~207,000 | five surface classes, crack-free shared vertices |
| Lagoon plane | ~110,000 | 3.5 m cells over a 260 m reach past the terrain |
| Causeways | ~26,000 each | 3 unique meshes instanced across 22 crossings |
| Cathedral | 9,278 | |
| Pavilions | 3,744 (large), ~2,600 (small) | 2 unique meshes, 14 instances |
| Everything else | remainder | quays, boats, lamps, stalls, palms, hedges, props |

## Levers used

1. **Instancing.** 22 causeways from 3 meshes, 14 pavilions from 2. Authoring
   each uniquely would have added ~500,000 unique triangles on its own.
2. **The water plane's cell size.** An early pass used 3 m cells over a 420 m
   reach: 480,000 triangles, more than half the region's unique geometry, for
   flat water. 3.5 m over 260 m costs a fifth of that and the waterline is
   indistinguishable at any camera a player can reach.
3. **An exact material pin.** `only=crownkit.MATERIALS` drops every material no
   mesh references. Three had crept in unnoticed - a shore texture and a water
   texture made redundant when the surface classes were repointed, and a cloth
   made redundant when banners changed to canvas - costing 0.96 MB between them.
   The build now warns when the pin carries anything unreferenced, because
   nothing else catches it: an over-broad pin is silent and only costs bytes.

## What is not optimised

- Nothing streams, and nothing selects between `world.glb` and `world-lod2.glb`
  at runtime. The reduced package is there for low-end machines and for whoever
  adds streaming.
- The reduced package saves bytes rather than geometry (40.3% smaller,
  only 12.9% fewer triangles). The toolkit's LOD strategy drops vegetation
  detail tiers, and Crownwater is architecture and terrain, not forest.
- Frame rate was not measured. Triangle and byte counts are facts; performance
  with actors, NPCs and effects present is not something this build tested.
