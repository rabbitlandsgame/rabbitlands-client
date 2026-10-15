# The Coil Causeway kit: Meshy batch (2026-10-13)

8 pieces, 120 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| CC1 | water gate arch | 01a133f7-2c0e-7261-b85b-eced7c0851ad | 5,593 | 13.6 x 11 x 3.79 | pass | 2 (the Water Gate, the shore landing) |
| CC2 | causeway span | 01a133f6-c5bb-77d8-a9df-4cb3fd2c9f3a | 3,849 | 17.08 x 4 x 5.11 | pass | 12+ (the causeways between the islands) |
| CC3 | serpent pillar | 01a133f6-50dc-7117-aec0-e2d30ff5fe34 | 2,779 | 2.54 x 7.5 x 2.65 | pass | 12 (the Serpent Colonnade) |
| CC4 | colossal serpent head | 01a133f7-315d-761e-ab50-58385ae6eca6 | 5,855 | 10.9 x 9 x 13.13 | pass | 2 (the Two Mouths) |
| CC5 | serpent egg clutch | 01a133f5-c9e9-76f6-8089-51c1d90cd6ef | 2,247 | 4.61 x 2 x 4.61 | pass | 8 (the Lily Hatchery) |
| CC6 | carved sun stela | 01a133f5-ce8e-776f-86fd-47fa3dc3b85b | 2,329 | 3.91 x 6 x 2.95 | pass | 3 (the Sun Stair) |
| CC7 | pyramid crown shrine | 01a133f7-e3f2-759c-8f20-cfc794df1f4e | 7,808 | 20.24 x 13 x 19.12 | pass | 1 (the Coiled Court, on the step pyramid) |
| CC8 | temple stair flight | 01a133f6-553f-7340-a190-661385943864 | 2,976 | 6.97 x 4 x 7.27 | pass | 4 (the pyramid tiers, the Sun Stair) |
