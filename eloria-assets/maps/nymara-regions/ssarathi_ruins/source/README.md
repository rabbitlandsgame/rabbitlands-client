# Ssarathi Ruins: inhabited floodplain city

The compact exterior is 384 by 384 metres, with server origin `[116,116]` and arrival `[116,116]`. Its monumental temple remains 72 metres across with a 35 metre ascent. The working quay, six houses, market, archive entrance and service furniture retain human dimensions. Travel space was recomposed around connected water basins and useful shores rather than uniformly shrinking architecture.

`region.py` forms the basin and precincts; `layout.py` grades surveyed roads, bridge banks and working yards, then adds houses, stores, boats and explicit content posts. `populate.py` places the regional architecture and nature. `ssaratharch.py` contains the supported temple stair. `ssarathikit.py` owns the muted inland water palette; the receiving bays retain the shared `water_lake` material. The source seed is fixed at 20260829.

Run the complete build from the package directory:

```powershell
python source/rebuild_landscape.py --verify
```

The wrapper exports the main and reduced terrain LOD GLBs, raw collision and minimap, then refines real walk heights, opens exposed walk meshes, stamps solid furniture/building footprints and applies the final actor-centre surface guard. The guard may close unsupported edge tiles; no later publication step may reopen them. Shared approaches contain each surface and prop once; `sceneNodes` exposes those same nodes in active and receiving views. The narrow source threshold retains navigation for the handoff tile without duplicating visible scenery.

North connects to Four Gates at `[154.5,4,-264.5]`; east connects to Verdant Stair at `[264.5,4,-88.5]`. Both have seven-metre causeways with water four metres below their decks. Native roads meet the shared causeway 42 metres inward. The west causeway remains an ordinary Manymouth Delta portal. The Crownwater south link remains a ferry journey.

All 11 ordinary portal IDs, seven Royal Archive entrances, 14 exterior secret IDs, landmark IDs, NPC identities and configured wildlife/resource counts are retained. `CONTENT_LAYOUT` contains named working posts, habitats and the Coil Causeway gauntlet keeper/return tiles. Interior room geometry and lore remain intact; the shared coordinator seats Archive Copyist Uln-Sath at clear working tile `[31,287]`, away from the archive arrival.

The scoped `migrate_compact_server.py --server PATH --apply` is invoked by the parent rollout coordinator. It preserves local offsets around protected neighbourhoods, uses explicit NPC posts, and records revision `inhabited-ssarathi-384-v1` so coordinates are migrated only once. Regional authors should not run global publication.

After final server publication, generate exact occupied-world traversal evidence:

```powershell
python source/write_walk_fixture.py --server SERVER --data SERVED_ELM_DIRECTORY --out ARTIFACT_DIRECTORY/live-fixture.json
```

This uses the actual server pathfinder, strict height/diagonal rules, configured NPC footprints, conservative service furniture clearance and automatic portal locations. Every ordinary archive doorway walks two metres off the arrival threshold before returning. Service replies, storage, a rendered resource and a representative creature are positive live assertions. The generated occupancy audit records served file hashes; it is preparation for a real client/server run, not a claim that live traversal has already passed.

Matched gameplay-camera captures and the frozen original package are stored in `work-output/southern-rollout/ssarathi-ruins`. The survey uses the normal client camera and grounding code. Overviews explain layout; they do not substitute for gameplay-camera evidence.

## Editor kit

`prepare_meshy_kit.py --input <ssarathi models> <verdant models>` seats the
generated models in the territory palette's kit
(`godot-client/world_authoring/regions/ssarathi_ruins/assets/prototypes/kit-*.glb`):
the Ssarathi set from `work-output/ssarathi-ruins-2026-09-27/asset-prompts.md`
(coastal rocks and sea stacks, beach palms, dune grass, flower mats and shells,
serpent ruin fragments, mangroves, lagoon reeds and lotus pads, jungle understory,
a stilt fishing platform, dugout canoe, fish trap, jade lantern pole, serpent
incense brazier and prayer-banner rack) and the Verdant Stair models this jungle
shares (mossy crags and boulders, undergrowth, flowering shrubs, tree ferns,
reeds), each taken from the first folder that has it. Each is scaled to its size
in `SIZES`, stood on the origin, and its textures shrunk and content-addressed
into `assets/textures/`; `prepare-meshy-kit.json` records the input and output
digests and `--check` verifies them.
