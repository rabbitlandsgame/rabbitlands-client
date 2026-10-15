# The Resin Road kit: Meshy batch (2026-10-13)

8 pieces, 120 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| RR1 | domed charcoal kiln | 01a133f0-9adb-7383-ac84-9ee47526a3b0 | 2,943 | 7.26 x 4.5 x 6.84 | pass | 4 (the Kiln Clearing) |
| RR2 | charcoal log clamp | 01a133f0-1a43-7061-85b7-db581c02f127 | 2,272 | 4.22 x 2.6 x 4.06 | pass | 6 (Kiln Clearing, the burners' camp) |
| RR3 | giant root arch | 01a133f1-485f-728d-b73a-01f0cedb86ed | 5,054 | 20.75 x 9 x 14.24 | pass | 4 (the Root Cellar, the road runs under them) |
| RR4 | colossal fallen-log bridge | 01a133f1-4d4a-7426-b8be-58352a3fd521 | 5,416 | 6.97 x 6 x 16.11 | pass | 1 (the Sap Ravine crossing) |
| RR5 | resin tapping frame | 01a133f0-9f86-728b-89ed-5daa3cd37d07 | 3,073 | 7.5 x 3.5 x 3.1 | pass | 6 (the Resin Works) |
| RR6 | copper resin vat | 01a133f0-ae20-7595-b48a-fd6be59b3799 | 2,773 | 3 x 2.6 x 3 | pass | 4 (the Resin Works) |
| RR7 | colossal hollow amber oak | 01a133f2-1440-74af-8446-8b998df59931 | 10,920 | 49.14 x 32 x 41.58 | pass-with-note | 1 (the Boar King's Wallow; its hollow is the vault) |
| RR8 | giant glade tree | 01a133f1-a7ac-740a-aadd-36dfdcda7fc0 | 7,007 | 26.19 x 30 x 23.53 | pass | 5 (the Lantern Glade) |
