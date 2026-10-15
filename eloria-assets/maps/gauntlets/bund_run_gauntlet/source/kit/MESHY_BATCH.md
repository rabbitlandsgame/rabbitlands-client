# The Bund Run kit: Meshy batch (2026-10-13)

5 pieces, 75 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| BU1 | delta watchtower | 01a133ff-ed09-72e6-9050-04dfdf84c35a | 3,894 | 6.48 x 13 x 7.12 | pass | 1 (the Watchtower Camp) |
| BU2 | sluice house with water wheel | 01a13401-d3f4-720f-8c15-5f92a4cb4c92 | 6,611 | 13.99 x 9 x 10.38 | pass | 1 (the Sluice House) |
| BU3 | great weir section | 01a13400-8190-746c-8093-26aa50f8ec2a | 4,834 | 12.71 x 5 x 3.03 | pass | 5 (the Weir Pool) |
| BU4 | weir-keeper's house | 01a13401-3e48-719c-b935-9433f09baa12 | 5,619 | 12.12 x 8 x 9.34 | pass | 1 (the Weir House, beside the vault) |
| BU5 | channel footbridge | 01a133ff-8833-726b-94c1-885baff1497a | 2,466 | 10.59 x 2.5 x 3.22 | pass | 2 (the Two Channels) |
