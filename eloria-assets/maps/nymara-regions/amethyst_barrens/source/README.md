# Amethyst Barrens source

Region-specific authoring and review modules. Shared primitives are imported
from the shared toolkit at `../../_toolkit/`, which is not copied here.

| File | What it owns |
| --- | --- |
| `region.py` | extent, scale, anchors, routes, watercourses, terrain sculpting, surface painting |
| `populate.py` | the landmark kit and every placement pass |
| `views.py` | the camera set, the panel mapping, and this region's capture lighting |
| `build_amethyst.py` | the build: GLB, manifest, collision, minimap, validation |
| `landscape_plan.py` | 384m survey, inhabited outpost, road grading, ecological placement and reciprocal borders |
| `rebuild_landscape.py` | sequential exterior build, geometry height correction, open decks and solid footprints |
| `migrate_compact_server.py` | revision-guarded server coordinate migration; preview by default |
| `review_landscape.py` | stable IDs, retained node references and conservative portal tile checks |
| `review_border_lanes.py` | all seven trigger/arrival lanes and 40m approaches in final client and served collision |
| `write_walk_fixture.py` | short service, resource, habitat and all-door routes for the real server walker |
| `write_review.py` | annotated raw gameplay-camera comparison and geometry-derived overview |

## Build

```bash
python rebuild_landscape.py --verify     # complete corrected package
python build_amethyst.py --skip-lod2 --skip-minimap   # fast iteration
```

The seeded build also reads shared reciprocal border definitions and receiving
sources; keep their revision fixed to reproduce the published package.

Runtime startup never depends on running this. The package is the committed
artefacts.

## Then

```bash
cd ..
PYTHONPATH=../_toolkit python ../_toolkit/validate_gltf.py world.glb
PYTHONPATH=../_toolkit python ../_toolkit/verify_runtime.py --report verification-report.json
PYTHONPATH=../_toolkit python ../_toolkit/capture_views.py
PYTHONPATH=../_toolkit python ../_toolkit/make_comparison.py
PYTHONPATH=../_toolkit python ../_toolkit/export_server_collision.py --out ../server-collision/amethyst_barrens.bin
```

## Real client frames

The current inhabited landscape's raw before/after frames and precise camera
specifications are under `work-output/northern-rollout/amethyst_barrens`.
Use `godot-client/tests/integration/rendered_landscape_survey.gd` for the complete
gameplay-camera rig, traveller and HUD. The integrated server walker consumes
the generated `walk-routes.json`. The older capture workflow below remains
available for concept review.

`references/captures/` is the offline rasteriser and is *not* the client.
For engine frames, from a Godot 4.7.2 binary:

```bash
godot --path ../../../../godot-client --headless --import   # once, or class_name lookups fail
godot --path ../../../../godot-client       --script ../../_toolkit/godot_capture.gd --resolution 1280x800 --       --package=<abs path to this package> --out=<abs path to client-captures>
```

The harness loads `world.json` through the client's own
`WorldLoader.load_world()` and takes its camera set from
`references/captures/index.json`, so the client frames line up one-for-one with
the offline previews they are compared against. Run `capture_views.py` first.

## Material set

`build_amethyst.py` pins `MATERIALS` and passes `only=` when registering glTF
materials, so this package embeds its selected palette and the reciprocal border
materials. Adding a kit piece that introduces a new material means
adding its name there; an unpinned material is a `KeyError` at export rather
than a silent omission.

## Editor kit

The territory palette paints the barrens with `kit-*.glb` pieces in
`godot-client/world_authoring/regions/amethyst_barrens/assets/prototypes/`. The
saved-source migration kept only the all-crystal outcrops and spires, so the
barrens had no grey rock for the amethyst to come through and no ground cover.

- `prepare_meshy_kit.py --input <folder>` seats the generated models (from
  `work-output/amethyst-barrens-2026-09-27/asset-prompts.md`): crystal-veined
  boulders and crags, basalt columns, split geodes, a rock arch, crystal vents and
  growths, vein scree, lichen mats, ashen brush, dead thorn, and prospector props
  (ore cart, mine rail, crates, lean-to, sluice, tripod, tool rack, lantern post).
  Each is scaled to its size in `SIZES`, stood on the origin, and its textures are
  shrunk and content-addressed into `assets/textures/`; `prepare-meshy-kit.json`
  records the input and output digests and `--check` verifies them.
- `export_editor_kit.py` builds the few pieces no model covers: grey rubble scree
  with a glint of shard, a crystal-burning brazier, a workbench and a survey
  signpost. Its stone is the territory's storm rock lifted to a mid grey, written
  beside the other textures under its content digest; `--check` verifies.

A piece whose file name holds a walk-through word (`scree`, `crystal`, `brush`,
`thorn`, `lichen`, `mine-rail`, ... in `asset_catalog.gd` `WALK_THROUGH_WORDS`)
starts walk-through in the palette, the rest start solid; the arch and the sluice
were made solid on their first copies, and the palette keeps a placed piece's role.
