# The Red Canyon kit: Meshy batch (2026-10-13)

4 pieces, 60 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| RC1 | natural sandstone arch | 01a133fb-ee90-717d-84cf-d65ffa3c3798 | 8,308 | 34.98 x 16 x 14.76 | pass | 1 (the Rock Arch) |
| RC2 | undercut cliff shelter | 01a133fb-45ad-710f-9af1-2d08d2577343 | 7,375 | 29.45 x 10 x 11.55 | pass | 3 (the Horse Caves) |
| RC3 | split pillar crown | 01a133fa-b156-73e2-9a02-5432cfde5928 | 5,633 | 32.83 x 24 x 24.86 | pass | 1 (the Sun Court) |
| RC4 | rock shade shelter | 01a133fa-440d-75d9-849f-54e5df064faf | 5,288 | 11.53 x 6 x 9.73 | pass | 1 (the Shade Shelter, the vault) |
