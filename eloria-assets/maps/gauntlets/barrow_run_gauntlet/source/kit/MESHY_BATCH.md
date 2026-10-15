# The Barrow Run kit: Meshy batch (2026-10-13)

5 pieces, 75 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| BW1 | great barrow portal | 01a133ed-552e-7498-9aa7-5bf48a924b98 | 8,030 | 26.41 x 9 x 26.41 | pass (attempt 2) | 1 (the Reeve's Forecourt; the vault is behind it) |
| BW2 | barrow with passage entrance | 01a133ee-f129-76e3-8ac1-84436260a4ae | 4,012 | 12.61 x 4.5 x 12.61 | pass | 4 (the First Barrow, the Fifth Chamber) |
| BW3 | split barrow | 01a133ef-7245-746b-b5d4-3a08854b43c6 | 6,896 | 30.88 x 7 x 36.01 | pass | 1 (the Split Barrow) |
| BW4 | bog boardwalk section | 01a133ee-98ce-7600-a379-d802fa956e5a | 2,407 | 7.85 x 1.6 x 2.79 | pass | 10 (the Bog Board) |
| BW5 | ruined moor chapel with spire | 01a133ef-77b4-7529-bece-aaf7ba2f281f | 5,681 | 15.33 x 16 x 17.28 | pass | 1 (the Fifth Chamber) |
