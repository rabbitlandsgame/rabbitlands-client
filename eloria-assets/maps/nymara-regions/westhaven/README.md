# Westhaven

A 396 × 396 metre harbour region with a south-facing working quay, a climbing town, sheltered pasture, and two exposed rocky islands. One metre equals one server tile. The coordinate origin is `(120,172)`; the main arrival is world `(34,3.4,6)`, tile `(154,166)`.

The 2026-09 coastal redesign preserves the existing lore, map IDs, eleven exterior portals, seven interiors and fourteen exterior secret entrances. The League Post-House retains thread E: returned unopened mail, seals and countersigns. Crownwater and Amberwood remain ferry journeys. The north road forms a surveyed seamless join to Grey Moors; the east road still leads to Manymouth Delta.

## Layout

The level 14m cargo spine serves two finger piers and the shipyard. Five retained warehouse identities now face their loading approaches. Twenty-six full-sized town houses face connected lanes with small work yards. Two routes climb from the quay: the market street through the civic terraces, and a cart road through the upland farms. The civic court has a continuous retaining edge with a graded entrance gap; three house plots were moved clear of its higher foundations. Gullstone retains open water around its rock and is reached through the quay-mole ramp and a narrow elevated footbridge. Lamp Rock is reached along the eastern shore and tidal causeway.

The region uses continuous landforms beneath building foundations. Public road grades are applied after field and yard preparation. Fourteen named NPCs have explicit work posts. A dry shingle wrack shelf provides room for existing sea-plant clusters, crabs and a heron beside the bay track. Crop beds occupy sheltered pasture; sea plants and crabs follow shallow shores; boar, rams and hounds occupy the upland and island habitat.

## Rebuild and verify

```powershell
python source/rebuild_landscape.py
python source/verify_landscape.py --server <server-checkout> --report <audit.json>
```

The first command exports main and reduced GLBs, a 792 × 792 half-metre EWCG grid, minimap, manifests and validators. It refines collision from actual rendered triangles, opens exposed walk surfaces, stamps solid towers, then guards the actual actor-centre samples before verification. The second performs the server fold and real `World.find_path` in memory, without writing server state. Source uses fixed seed `20260829` and the shared toolkit. `source/migrate_compact_server.py` records the one-time coordinate migration; the integration owner runs it before publishing updated services and portals.

Current machine measurements are in `performance.json` and `verification-report.json`. Gameplay-camera before/after views, route audits and annotated review are in `work-output/coastal-rollout/westhaven` at the workspace root. Final live path verification is recorded by the coastal integration run. Older comparison and validation documents describe the previous 576m package and are historical evidence.

## Editor kit

`source/prepare_meshy_kit.py --input <westhaven> <ssarathi> <verdant> <mirrorhold> <four gates models>`
seats generated models in the territory palette's kit
(`godot-client/world_authoring/regions/westhaven/assets/prototypes/kit-*.glb`). Each model is taken
from the first folder that has it.

- The Westhaven set, from `work-output/westhaven-2026-09-28/asset-prompts.md`: terracotta townhouses, a
  harbour row, a merchant house and a fisher's hut; a harbour crane, cargo, rope, lobster pots, fish
  crates, an anchor, a mooring buoy and quay steps; fishing boats, a skiff, a sloop and a caravel;
  olives, stone pines, cypresses, lemon trees and bougainvillea; beach rocks, net frames, vineyards, a
  windmill, a dovecote and terrace walls.
- Ssarathi's coastal rocks, sea stacks, dune grass and beach dressing.
- Verdant Stair's drying racks, beached rowboat, driftwood, baskets, pots and flowers.
- Mirrorhold's rowing boat, mooring posts, benches, planters, cypress, fountain and laundry line.
- Four Gates' barrels, crates, carts, board, urn, well and farm pieces.

Wrapper-node transforms are baked into the vertices before each model is scaled to its size in
`SIZES`. It is then stood on the origin, except the boats and the buoy (`WATERLINE`), which keep their
waterline there. Its textures are shrunk and content-addressed into `assets/textures/`.
`source/prepare-meshy-kit.json` records the input and output digests, and `--check` verifies them.

## Practical limits

Terrain and road boundaries remain visibly polygonal at close range. The shared final guard closes unsupported, submerged or incorrectly grounded folded tiles at the actual actor centre, including the client half-tile offset. Tower galleries and sea cliffs create deliberate height discontinuities. Actors and resources remain map-scoped, and seamless static scenery does not remove map handoff costs. The reduced package drops minor ground clutter and uses smaller embedded textures.
