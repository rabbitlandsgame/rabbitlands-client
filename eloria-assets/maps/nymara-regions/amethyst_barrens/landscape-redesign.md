# An inhabited Amethyst Barrens

The exterior is now 384 metres square, with one metre per server tile and
origin `(116,116)`. The Glasswarden Observatory, massif, six field stations,
ten worked crystal sites, six ruins, four caves and eleven calibration stones
retain their identity. The lower basin has room for travel and encounters.

The assay exchange is a working outpost. A bunkhouse and Naia Flint's cookhouse
face the existing station, storage and crafting court; stores sit against the
buildings. Their local timber, pale rubble and verdigris roofs use the existing
toolkit. The buildings retain their dimensions. Dust and aggregate replace the
large luminous paved apron; amethyst remains concentrated in actual crystal,
specimens and ceremonial features.

## Geography and travel

`source/landscape_plan.py` owns the compact axis survey. Original X `[-95,30]`
and Z `[-205,5]` are protected, retaining the observatory stair and the spacing
of the inhabited yard. Other journeys shorten through monotonic axis maps.
This does not scale characters, dwellings, furniture or cave mouths.

The river and its western tributary retain their downstream profile and their
shared outlet at the south-east inlet. Seven crystal bridges are recomposed
between their compact bank surveys at 5.4m width. The Crownwater packet jetty
retains 3.6m width. These are actual walking decks with structural rails kept
outside the navigation prefix.

Two broad road approaches meet the reciprocal streaming frames declared by
the shared `streaming_borders` toolkit. The Whitehorn road climbs gently to
12m; the Mirror Road reaches an 8m shelf. The old west tower moves aside so
the seven crossing lanes remain clear. Snowline scree and bedrock carry the
transition; the adjacent region supplies its real receiving scene. Sunmane's
southern road and the Crownwater ferry retain their existing destinations.
The southern ascent has a broad, continuous grade instead of the old compressed
rim zigzag. The packet jetty starts on the connected dry headland, with the
cargo tender alongside its walking deck. A short rising trail reaches the
Sour Cut threshold at the massif foot.

Debris follows the massif, the eastern fault and the western gully shoulders.
It no longer occupies every eligible part of the basin. Three quiet expanses
retain open ground. Sparse dry grass collects in leeward pockets and sheltered
drainage margins. The exposed upper basin remains mostly bare.

## Preserved gameplay

All four continent links and seven Resonant Vault entries keep their stable
IDs and destinations. All thirteen exterior secret entrances remain; the
fourteenth secret opens from the existing interior. Keys, resources, named
NPCs, dialogue threads and interior geometry remain part of the original
region. The Geode Hollow threshold moves four original survey metres east
to place its full server tile outside the mouth's solid geometry.
The Massif Reliquary slab sits at the accessible foot of its parent massif;
its identity, key, texts and interior remain unchanged.

The coordinate migration is revision guarded. It transforms existing NPCs,
harvestables, creature spawns, services, special areas and incoming return
portals before the coordinator reauthors the final positions from the package.
The primary arrival is tile `(140,85)`. `source/server-content.json`, when
present, reapplies final server marker identities during subsequent builds.
`source/runtime-content.json` records the actual served roster separately from
the preserved editorial markers and is reapplied by the shared content toolkit.

## Reproduction and review

From `source`, run `python rebuild_landscape.py --verify`. It rebuilds the
exterior, LOD, collision and geometry-derived minimap, then runs the shared
height refinement, walking-surface opening and solid-landmark stamping.
It does not write shared server configuration. The coordinator runs
`migrate_compact_server.py --server <checkout> --apply` and the scoped
collision/content/portal synchronisation after all reciprocal packages exist.

`review_landscape.py --baseline <frozen package> --report <json>` checks
retained IDs, actual landmark nodes and conservative portal tiles.
`write_walk_fixture.py --out <json>` emits short service, habitat, resource,
interior and exterior approaches for the real-server landscape walker.
`review_border_lanes.py --server <checkout> --maps <data> --report <json>`
checks all seven lanes of both local borders from their triggers through
40m inland, including each two-tile receiving position. It checks the exact
half-grid footprint, the served ELM tile and consecutive legal server steps.

The rollout evidence is in `work-output/northern-rollout/amethyst_barrens`:
raw before/after gameplay-camera PNGs, the exact capture specifications,
contract report, real-client walk fixture and an annotated HTML comparison.
Both capture sets use the game's isometric rig, character scale and HUD.
The baseline uses the frozen runtime; the after set uses the new checkout.

The survey harness places a QA traveller and checks the rendered camera.
It does not itself prove network movement or remote actor visibility. The
coordinator's integrated server walks cover authoritative traversal. Regional
LOD packages retain the generated receiving strips; active-scene and receiving
scene visibility are controlled by the streaming runtime.
