# Sunmane continent authoring

Sunmane Steppe is authored in
`res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn`. Open it with
`open-sunmane-authoring.bat`, edit the saved controls, and save the scene. The
normal continent build automatically imports and bakes that saved scene before
shared terrain partitioning, collision, manifests, and publication. The root's
**Bake continent authoring snapshot** button is only an optional preview and
diagnostic.

The scene is the source of truth. Do not edit generated preview children or
the Python snapshot by hand. The one-time migration converter exists to make
the initial scene reproducible from the certified legacy package; it is not
part of the normal edit loop.

## Scene layout

- **Terrain** previews the full 397×397, 2 m natural height grid. It contains no
  old Sunmane road or river grading, so moving or deleting an authored path
  cannot leave a hidden terrain scar. Add saved patch controls under
  `Terrain/Patches` for broad height edits.
- **Ground/Regions** holds painted surface areas.
- **Roads** holds 21 editable controls: 19 replacements for the legacy routing
  curves plus two local East-gate access ramps. Their widths are full metres:
  seam roads are 8 m and door, discovery, and access paths are 3.3 m.
- **Rivers/southern_river** owns the complete Limestone River topology and its
  depth, valley, bank, and sea-mouth settings. Its width is 13 m full width.
- **Bridges** contains two editable controls: the continental bridge and the
  short Steppe Hall access footbridge.
- **AuthoredAssets** contains 298 named current placements. Each is an editable
  wrapper around one of 80 small reusable prototype GLBs; the scene never
  embeds the opaque composed region world.
- **Gameplay** contains the current spawns, portals, interactives, landmarks,
  harvestables, NPC markers, and ambient groups. Markers linked to an authored
  object follow that object with a saved local offset. **RuntimePoints** adds
  individually named controls for server records that had no visual marker;
  moving one updates that exact record on the next build.

Coordinates are territory-local metres: +X east, +Y up, +Z south. The region
root records the separate continent translation `[1200, 0, 720]`, server tile
origin `[194, 292]`, and collision origin `[-194, 292]`. Do not derive one from
another.

## Editing and baking

1. Run `open-sunmane-authoring.bat` and wait for the imported prototype assets
   and terrain preview to finish loading.
2. Move or edit the saved control. Use the inspector fields on the wrapper,
   path, surface, terrain patch, or gameplay marker. Move the wrapper rather
   than the `Content` child of an authored asset.
3. For a gameplay marker that should move with an object, set **Follow Asset
   Id**, position the marker, and click **Capture offset from linked asset**.
4. Save the scene. Click **Refresh authoring preview** on the root if an editor
   preview is stale.
5. Run the normal continent build. It automatically bakes the saved scene, then
   applies authored replacements before partitioning so dependent overlap
   packages, collision, and server fields are rebuilt from the scene.

From the client repository root (the folder containing both `godot-client` and
`eloria-assets`), the reusable full build invocation is:

```powershell
C:\Python\Python313\python.exe <path-to-run_limited.py> `
  C:\Python\Python313\python.exe `
  eloria-assets\maps\nymara-regions\_continent\build_pipeline.py `
  --server <sunmane-authoring-server> `
  --data <server-data-dir> `
  --artifacts <artifact-dir> `
  --library <artifact-dir>\library `
  --stage all `
  --cores 8 `
  --godot godot-client\Godot_v4.7.2-stable_win64_console.exe
```

The CPU-affinity wrapper is workspace-owned and is not stored in the client
repository, so supply its actual path. Those output/input directories are
environment-specific. Run
`build_pipeline.py --help` for the current options and stage descriptions.

For this Windows integration checkout, the exact command is:

```powershell
Set-Location C:\rabbitlands\rabbitlands-client
C:\Python\Python313\python.exe ..\diagonal-continent\run_limited.py `
  C:\Python\Python313\python.exe `
  eloria-assets\maps\nymara-regions\_continent\build_pipeline.py `
  --server ..\sunmane-authoring-server `
  --data ..\godot-map-editor-qa\full-continent\server-data `
  --artifacts ..\godot-map-editor-qa\full-continent\artifacts `
  --library ..\godot-map-editor-qa\full-continent\artifacts\library `
  --stage all `
  --cores 8 `
  --godot C:\rabbitlands\rabbitlands-client\godot-client\Godot_v4.7.2-stable_win64_console.exe
```

The root's **Bake continent authoring snapshot** button is an optional preview
and diagnostic. A failed manual or automatic bake names the invalid node or
unsupported material; fix that error before publishing.

The root keeps all 19 route replacement IDs and `southern_river` in persistent
registries. Deleting a path does not revive its procedural predecessor. A
missing required seam or portal route fails validation and must be resolved
explicitly.

The two East-gate ramps and the Steppe Hall footbridge are ordinary saved
controls. Artists can move their curve points or bridge markers in the same
way as the other paths and bridges; they are not hidden build-time patches.

The base grid records the natural terrain with `southern_river` removed. The
bake emits a second resolved height grid after saved patches and path effects.
The first migration intentionally measures the terrain/profile difference from
the retired road-settling algorithm; it does not hide that difference in a
static baked road or channel.

## Migration provenance

`migration-provenance.json` records the certified input hashes, all migrated
object identities, prototype families, path point hashes, gameplay identities,
the clean base-grid hash, and the saved one-time vertical migration from the
published surface to the initial authored resolved grid. That shift preserves
the old surface clearance in the editable node positions; it is not rerun when
artists later edit terrain. The migration source was the published current
Sunmane package; neighbor terrain/water chunks and generated seam/bridge union
parts were excluded from object ownership.

To reproduce the initial extraction against a certified copy, run:

```powershell
C:\Python\Python313\python.exe godot-client\tools\import_sunmane_authoring.py `
  --source-world <certified-sunmane-world.glb> `
  --source-manifest <certified-sunmane-world.json> `
  --roads <certified-roads.json> `
  --plan <certified-diagonal-plan.json> `
  --base-heights <certified-prefeature-height-f32le.bin> `
  --resolved-heights <frozen-first-authored-resolved-height-f32le.bin> `
  --runtime-bindings godot-client\world_authoring\regions\sunmane_steppe\runtime-bindings.seed.json `
  --output godot-client\world_authoring\review\sunmane-steppe
```

The converter validates the 397×397 byte count, current owned routes, object
identity uniqueness, and reusable prototype path uniqueness. Review the new
provenance hashes before replacing a committed migration baseline. It refuses
to overwrite an existing authored scene unless `--force` is supplied, so a
future run cannot silently discard saved editor work.

Every runtime binding also carries a reviewed territory-local
`targetOffset: [dx, 0, dz]`. Existing semantic markers retain the distinct
certified offsets of all records they serve, so moving one shared marker moves
its door and return endpoints together without collapsing them. Individually
authored RuntimePoints use `[0, 0, 0]`.

The initial southern river keeps the former continent builder's exact 43-point
sampled centerline: six Catmull-Rom samples for each of the seven spans plus the
final endpoint. Those samples are saved as ordinary zero-handle curve points,
so the river remains directly editable while the initial editor shape matches
the former water, crossing, and routing geometry.

When the scene first opens, select `SunmaneSteppe/Terrain` or a named town
asset under `AuthoredAssets` and press **F** to frame it. Roads, the river, and
the continental bridge are named controls in their top-level scene groups, so
their handles remain discoverable on a fresh checkout without editor-local
camera state.
