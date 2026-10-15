# The Resonant Cut kit: Meshy batch (2026-10-13)

6 pieces, 90 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| RT1 | colossal crystal spires | 01a133fd-90c9-73ac-b079-6b6bf3ac1e37 | 3,489 | 15.75 x 16 x 16 | pass | 8 (the Shard Gallery, the Crystal Hall) |
| RT2 | crane gantry bridge | 01a133fe-70d8-74d2-9684-5e9056903883 | 6,877 | 48.35 x 22 x 9.93 | pass | 1 (the Crane Bridge) |
| RT3 | quarry bench wall | 01a133fd-9568-772e-8743-cbe3fa7811e1 | 3,777 | 21.66 x 8 x 4.45 | pass | 20+ (the bench walls of the pit) |
| RT4 | giant split geode | 01a133ff-065e-73b1-92f5-8d8b265da214 | 8,279 | 17.82 x 9 x 17.8 | pass | 1 (the Geode, the vault) |
| RT5 | quarry hoist scaffold | 01a133fd-99d4-73fa-8262-afb04578373f | 3,896 | 5.55 x 10 x 7.76 | pass | 3 (the Mite Cut, the Crane Bridge) |
| RT6 | cut-stone quarry stair | 01a133fc-ab78-7026-80d4-3135ac160490 | 2,180 | 9.04 x 5 x 9.62 | pass | 3 (the Storm Stair) |
