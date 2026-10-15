# Westhaven 396m package measurements

These measurements describe the compact coastal package. The previous 576m export remains available in the frozen before-camera evidence.

| Measure | Main | Reduced |
| --- | ---: | ---: |
| GLB bytes | 29,531,584 | 16,872,820 |
| Instanced triangles | 864,737 | 630,985 |
| Unique triangles | 488,516 | 414,042 |

The final guarded EWCG v2 collision grid is 792 by 792 at half-metre resolution: 365,959 walkable cells (58.34%). `performance.json.collision` is the raw export measurement before the ordered correction passes; `world.json.collision` records their final result.

The runtime validator sampled 156,816 tile centres, with zero grounding misses and zero errors. Its one warning reports 138 height discontinuities at cliffs and tower galleries. All 29 required service, portal and secret destinations are reachable in the real server pathfinder; the longest path has 317 steps and all six practical-road bounds pass. The folded publisher opens no blocked tiles and adds no joins.

The artifact review includes nine matched before/after real-client camera views, the nineteen-route fixture, the full population packing report, and SHA256 provenance. Settled debug-camera frame samples are not a substitute for live border-handoff measurements. Final live coastal integration is tracked separately by the integration owner.
