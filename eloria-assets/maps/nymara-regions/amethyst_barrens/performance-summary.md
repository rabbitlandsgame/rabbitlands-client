# Amethyst Barrens — performance summary

Measured from the September 2026 package. Counts describe shipped assets,
not frame rate. File sizes use decimal MB; texture memory uses MiB.

| Metric | Full package | Reduced package |
| --- | ---: | ---: |
| GLB size | 25.87 MB | 17.06 MB |
| Nodes | 1,034 | 499 |
| Unique triangles | 450,566 | 426,088 |
| Instanced triangles | 604,342 | 436,664 |
| Meshes | 389 | — |
| Pinned materials | 39 | — |
| Embedded images | 87 | — |
| Embedded texture data | 9.58 MB | — |
| Uncompressed texture memory | 73.7 MiB | — |

The full package is 1.44 MB smaller and uses
48,640 fewer instanced triangles
than the preceding package. Both the full and reduced GLBs validate without
errors or warnings. Their bytes reproduce after a fresh corrected build.

The shared arcaded bridges, continuous stairs and clipped backdrop reduce
geometry while the exchange and packet landing add a small amount. The pinned
material count remains unchanged. Total texture memory is an estimate before
client overhead and does not predict actual GPU allocation or performance.
No play-session frame-rate benchmark was performed. See layout-review.md for
the authored route, collision and capture evidence.
