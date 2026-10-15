# Sunmane Steppe performance summary

## Current package cost - September 2026

| Measure | LOD1 | LOD2 |
|---|---:|---:|
| GLB bytes | 19,249,384 | 10,171,192 |
| Unique mesh triangles | 244,565 | 152,687 |
| Meshes | 262 | 167 |
| Nodes | 958 | 334 |
| Materials | 31 | 29 |
| Embedded textures | 30 | 30 |
| Terrain triangles | 91,600 | 91,600 |
| Kit unique triangles | 49,727 | 48,455 |
| Kit instances | 748 | 210 |
| Ground-cover triangles | 84,866 | 0 |

These totals describe the current layout. Both levels retain 120 landmarks,
88 authored geometry interactives and 30 embedded textures. LOD2 removes ground
clutter and uses half-resolution textures. The standalone world-statistics
files contain build-time collision counts before the three correction passes;
layout-review.md records the final corrected grid.

## Historical client measurements - before the current layout

The measurements below predate the September 2026 circulation pass. They are
retained for reference and do not benchmark the rebuilt package.

Godot 4.7.2, `gl_compatibility` renderer, 1280x720, adapter `llvmpipe (LLVM 20.1.2, 256 bits)`.

**These frame times are software rasterisation.** This session had no GPU, so Mesa's llvmpipe rendered every frame on the CPU. The absolute milliseconds are not a prediction of player frame rate. The useful figures are the relative costs between packages and views, the draw-call and primitive counts, and the geometry and memory totals, all of which are hardware independent.

| Package | View | Draw calls | Primitives | ms/frame (llvmpipe) |
|---|---|---:|---:|---:|
| LOD1 | gameplay-default | 2,807 | 674,874 | 366.49 |
| LOD1 | gameplay-zoomed-out | 3,261 | 725,655 | 406.77 |
| LOD1 | region-overview | 2,391 | 462,789 | 299.47 |
| LOD1 | low-settings-no-shadows | 1,378 | 293,251 | 157.17 |
| LOD1 | high-settings | 2,831 | 642,330 | 342.84 |
| LOD2 | gameplay-default | 2,160 | 498,339 | 333.88 |
| LOD2 | gameplay-zoomed-out | 2,269 | 471,071 | 334.61 |
| LOD2 | region-overview | 1,519 | 283,617 | 242.15 |
| LOD2 | low-settings-no-shadows | 989 | 214,168 | 132.03 |
| LOD2 | high-settings | 2,132 | 472,145 | 293.02 |

| Package | Load time | Mesh instances | Collision bodies | Ambient animals |
|---|---:|---:|---:|---:|
| LOD1 | 718.1 ms | 1029 | 241 | 111 |
| LOD2 | 441.5 ms | 300 | 241 | 111 |

Renderer-reported GPU memory at the default gameplay camera, LOD1: texture 22.64 MiB, buffers 19.43 MiB.

## Cave interiors

| Measure | Wind Caves | Crystal Hollow |
|---|---:|---:|
| GLB bytes | 4,147,168 | 4,302,312 |
| Unique mesh triangles | 17,405 | 17,882 |
| Cavern shell triangles | 12,740 | 13,164 |
| Nodes | 201 | 223 |
| Meshes | 57 | 64 |
| Kit instances | 167 | 184 |

Each interior is about a fifth of the surface package on disk and an order of magnitude cheaper in geometry: a cave is a small volume with no terrain grid, no vegetation and no distant scenery, and its shell is two surfaces over roughly 3,000 open cells rather than a 201 x 201 heightfield.

## Historical budget comparison

`maps/four-gates-city/performance-summary.md` documents a desktop LOD1 budget of 1.5M visible triangles and 512 MiB of texture memory, and 350k triangles and 192 MiB on mobile.

| | Sunmane LOD1 | Sunmane LOD2 |
|---|---:|---:|
| GLB bytes | 18,407,036 | 9,169,492 |
| Nodes | 1,041 | 312 |
| Unique mesh triangles | 229,363 | 136,047 |
| Peak primitives in frame | 725,655 | 471,071 |
| Texture memory | 22.64 MiB | 12.23 MiB |

These historical frame counts sit inside the documented desktop budget. LOD2's peak of 471,071 primitives exceeds the cited 350,000 mobile triangle target; primitive counts and triangles are not a direct frame-time measurement. Sunmane carries far more unique geometry than Four Gates because its terrain is a sculpted 280 m heightfield with real ground cover rather than a terraced plateau, and because its architecture is authored rather than assembled from scaled primitives.

Draw calls remain the honest weak point: 2,807 at the default gameplay camera against 2,160 for LOD2, up from the pre-expansion figures because the desert, badland and mountain ground added several hundred more instanced props. That is the cost of instancing authored props as plain glTF nodes, which is what the current loader consumes. Batching the small props into per-chunk meshes would trade duplicated triangles for roughly 600 fewer draw calls; it is deliberately not done here because the loader has no multi-mesh path and triangles are the budget the repository documents, but it is the first thing to try if a low-end target proves draw-call bound.
