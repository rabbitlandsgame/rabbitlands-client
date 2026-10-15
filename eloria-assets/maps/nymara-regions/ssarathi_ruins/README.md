# Ssarathi Ruins

Ssarathi Ruins is a drowned serpent city with working archive and market quarters, jade pools, connected causeways and a monumental northern temple. The compact exterior is **384 × 384 metres**, with server origin **[116,116]**, one metre per tile and arrival **[116,116]**. The 72 metre temple and 35 metre summit rise retain their original scale; ordinary houses, working courts and furniture keep human dimensions.

The north causeway joins Four Gates and the east causeway joins Verdant Stair. Both have seven metres of clear deck over connected water. The west link to Manymouth Delta remains an ordinary portal; the south Crownwater link remains a ferry journey. Its departure at `[124,42]` and return at `[124,44]` stand on the existing dock.

All 11 ordinary links, seven Royal Archive entrances, 14 exterior secret IDs, named lore and gameplay identities are retained. Explicit working posts and habitat discs preserve 14 exterior NPCs, 26 creatures and 37 resource nodes. The Royal Archive, lineage house, hatchery, cistern, undercroft, Tenth Mouth and water-gate rooms remain connected to their existing IDs.

The package contains `world.glb`, a reduced `world-lod2.glb`, `world.json`, `collision.bin` and a geometry-rendered minimap. Collision is an EWCG v2 half-metre grid of 768 × 768 cells; the shared server publisher folds it to the strict 384-cell map. Actual actors stand at tile centres, so the final guard rejects unsupported, submerged or height-mismatched cells. Building bodies and furniture remain closed. Temple stairs and decks are explicitly declared walking surfaces; the summit roof is a separate structure so the normal camera can fade it.

Rebuild with `python source/rebuild_landscape.py --verify`. See [the source guide](source/README.md) for the authored composition, revision-guarded server migration, dedicated tests and exact served-world fixture generator. The shared coordinator owns server publication; this package never fabricates standable water or silently reopens guarded collision.

Current budgets are in [performance-summary.md](performance-summary.md), and geometric diagnostics are in `verification-report.json`. Historical comparison, change-log and modeling documents describe earlier production passes; they are not current size, performance or live-validation claims. Current matched gameplay views, annotated overview, package provenance and route audits are in `work-output/southern-rollout/ssarathi-ruins/index.html`.
