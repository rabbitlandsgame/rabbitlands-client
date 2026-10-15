# The Drowned Arcades kit: Meshy batch (2026-10-13)

6 pieces, 90 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| DA1 | marble arcade bay | 01a133f8-797e-7358-9395-84743c8c95be | 4,770 | 7.27 x 11 x 4.04 | pass | 20+ (the Long Arcade, the squares) |
| DA2 | arcaded bridge span | 01a133f8-7e71-71a5-8e93-36726c3b4c1b | 4,710 | 14.99 x 7 x 4.03 | pass-with-note | 6 (the Bell Walk) |
| DA3 | great cistern fountain | 01a133f9-27db-7215-9065-6af6abe34692 | 5,637 | 10.81 x 6 x 10.81 | pass | 1 (the Cistern Square) |
| DA4 | canal sluice lock | 01a133f8-837a-7223-8747-2107a7fd43c4 | 4,666 | 10.21 x 5 x 2.73 | pass | 2 (the Two Sluices) |
| DA5 | drowned campanile | 01a133f9-a8f6-7202-964e-1ad26ee52290 | 7,800 | 15.3 x 46 x 15.31 | pass | 1 (the Bell Court) |
| DA6 | domed treasury | 01a133f9-ad39-709a-9845-2c8d2e24a4f4 | 7,281 | 14.41 x 16 x 12.85 | pass | 1 (the Treasury, the vault) |
