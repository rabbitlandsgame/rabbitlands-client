# The Ice Stair kit: Meshy batch (2026-10-13)

7 pieces, 105 credits, delivered and placed by the road's dressing (layout.json `dressing.landmarks`, written by work-output/gauntlet-v2-design/regions/tools/author_routes.py). Concepts, prompts and previews: work-output/hg/meshy/trail-roads/ (spec.json, concepts/, previews/).

Settings: Meshy image-to-3D, smart topology at each piece's face target, triangles, 2K base colour only, no pose, no rig (work-output/hg/meshy/trail-roads/run_meshy.sh). Normalised in Blender (tools/normalize_kit.py): node transforms baked, scaled uniformly to the spec height, base centre on the origin, the image side at glTF +Z, metallic 0, 1024 px JPEG base colour.

Sizes are as delivered at the spec height (x length, height, z depth); the dressing scales some pieces (see the landmarks). Decks (bridges, causeways, stairs) are placed with their deck on the road and close nothing: the road under them is terrain.

| ID | Piece | Task | Tris | Size (m) | Concept verdict | Seating |
|---|---|---|---|---|---|---|
| IS1 | frozen cascade wall | 01a133f4-9903-75f1-a5db-570598c6010d | 6,601 | 41.85 x 18 x 15.26 | pass | 2 (the Frozen Cascade) |
| IS2 | crevasse span segment | 01a133f4-046f-76f3-896c-d4e3c40daeff | 5,138 | 21.88 x 6 x 7.15 | pass-with-fixes | 6 (the Crevasse Span) |
| IS3 | snowbound miners' hall | 01a133f5-48a3-7637-a079-6226266a87c1 | 6,681 | 25.56 x 11 x 14.03 | pass | 1 (the Snowline Hall) |
| IS4 | mine adit portal | 01a133f4-9da6-72d6-8a97-079d013c8965 | 5,761 | 17.22 x 9 x 14.46 | pass | 1 (the Silver Adit, the vault) |
| IS5 | rime ice pillar | 01a133f3-2a97-71d9-afd4-3cdca9acecac | 2,356 | 7.96 x 12 x 7.91 | pass | 8 (the Rime Court ring) |
| IS6 | ore chute and spoil heap | 01a133f3-97bd-7527-9bce-d56b1b0aee0e | 3,996 | 10.63 x 6 x 5.67 | pass | 2 (the First Riser) |
| IS7 | silver-veined boulder | 01a133f2-aa23-76cd-b1c5-453740d4a586 | 2,083 | 4.82 x 2.6 x 4.81 | pass (attempt 2) | 6 (the Last Riser) |
