# Harrowcrag fort kit: Meshy batch (2026-10-12)

Owner approved 180 credits plus up to 70 for retries. Pilot H1 first, then the other 11.
Spend: 180 credits on 12 tasks, no retries. Balance 2,685 -> 2,505.
Settings: image-to-3d, smart-topology at each piece's face target, triangles, 2K base colour only, no pose, no rig.
Kits are in kit/ (normalised in Blender: baked transforms, scaled to the spec height, base centre on the origin, metallic 0, 1024 JPEG).
Previews: previews/<id>/, review_sheet_1.jpg, review_sheet_2.jpg, fort_kit_lineup.png (H5 shown at x0.732).

| ID | Piece | Task | Tris | Size (m) | Verdict | Note |
|---|---|---|---|---|---|---|
| H1 | ruined curtain wall section | 01a131a5-693c-7582-bfeb-bb76c5900d23 | 3,929 | 16.3 x 3.1 x 6.4 | pass-with-fixes | Matches the concept; 16.3 m module at 6.4 m. Clip both ends flat before tiling; back is plain stone (fine for a curtain). |
| H2 | curtain wall breach with rubble | 01a131a9-c12a-738f-a709-04d8ceb8a47f | 4,996 | 19.7 x 10.3 x 6.4 | pass-with-fixes | Breach and two-sided rubble slope as drawn; 19.7 m long at 6.4 m. Many small rubble islands (expected); place between H1 runs. |
| H3 | half-collapsed round tower | 01a131aa-7b5b-741f-a49d-d6bb67361bbd | 5,567 | 13.8 x 12.4 x 13.0 | pass | Half slate cone, exposed rafters, stepped collapse, open door; 13.8 x 12.4 m with the collapsed wing. Cylinder collider on the drum. |
| H4 | burst ruined gatehouse | 01a131ab-5e80-7779-82fa-1a1e5ece71a8 | 7,188 | 25.0 x 10.9 x 13.0 | pass | Passage open through with the portcullis band; 25 x 10.9 x 13 m. Check the rubble at the outer feet against the curtain joins when seating. |
| H5 | ruined castle keep | 01a131ac-330f-7742-9568-be75ccec7900 | 11,521 | 41.0 x 30.6 x 28.0 | pass-with-fixes | Roofless shell with a rubble floor, doorway, turret and banners. At its 28 m spec height it is 41 m wide: seat it at x0.732 (30 x 22.4 x 20.5 m). Clean the loose floor rubble islands; banner colour bleeds faintly onto the back wall. |
| H6 | low rubble pile | 01a131a7-1415-7027-994c-b198c67940dc | 1,936 | 3.9 x 2.2 x 1.2 | pass | One closed heap, no open edges. |
| H7 | large masonry collapse | 01a131a8-64a9-75f7-816b-d8128c289887 | 2,791 | 7.8 x 5.0 x 2.6 | pass | Column drum, arch fragment and blocks; 7.8 x 5.0 x 2.6 m. |
| H8 | burnt barn | 01a131a9-c700-7306-840a-6f3ba5ca8124 | 4,614 | 8.8 x 11.4 x 7.0 | pass | Burnt half-roof, red boards, stone footing, open doors; 8.8 x 11.4 x 7 m. Back gained two round windows (fine). |
| H9 | carved ring altar | 01a131a7-bc93-758f-a84f-fcb9d5e9d9e2 | 2,317 | 4.2 x 2.7 x 1.5 | pass | Carved dais with the spiral and ring band; 4.2 x 2.7 x 1.5 m. |
| H10 | warband war standard | 01a131a8-6d3f-750b-b62d-23c95e3d805c | 3,072 | 4.1 x 3.6 x 6.5 | pass | Skull, crossbar, two rag banners, cairn and spears came through; 6.5 m. |
| H11 | wrecked siege engine | 01a131a9-cba9-74e7-9606-27fa86c9cf81 | 5,081 | 10.4 x 6.4 x 5.0 | pass | Snapped arm, three wheels on and one leaning; 10.4 x 6.4 x 5 m. |
| H12 | rock-tomb doorway | 01a131a9-056b-74b1-b558-621bd4aa1db9 | 3,962 | 12.3 x 6.9 x 6.5 | pass-with-note | Front as drawn (doorway, skull lintel, fallen slab); 12.3 x 6.9 x 6.5 m. The back is a hollow slab: always set it against the gorge wall. |

## Fixes at seating (no credits)

- H1: clip both ends flat so modules tile; delete loose pebbles at the foot.
- H5: seat at x0.732 (30 m wide); delete loose floor-rubble islands; the doorway must reach the walkable undercroft.
- H2, H7, H8, H11: many small parts by design; keep double-sided, judge collision by footprint (solid role).
- H12: back is hollow; always against the gorge wall.
- All: a Godot look-pass check in the art pass before final acceptance.
