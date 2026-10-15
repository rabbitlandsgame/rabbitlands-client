# Optional source ownership in the continent editor

`eloria-assets/maps/nymara-regions/_continent/diagonal-plan.json` remains the
single selector. Its optional `ownership_contract` has exactly `path`, `sha256`
and `revision`. The path is relative to `_continent`. The current production
plan is unchanged and has no selection.

With a selection, the editor resolves the client checkout from globalized
`res://`, checks its project/plan markers, and reads raw source bytes through
`src/dev/map_authoring_region/ownership_source.gd`. Absolute/drive/URI/traversal
paths and symlink/junction/reparse components are rejected. Missing, changed or
structurally invalid selected sources produce errors; published ownership is
never substituted. Without selection, existing published/legacy ownership and
manually saved polygon hashes continue to apply.

The catalog retains parsed scalar coordinates in `ownership_polygon_scalars`.
Its selected identity is the source SHA-256 plus region ID. `Vector2` arrays
serve previews/sculpt masks only; they never produce selected authority hashes.
Plan/source/baseline bytes participate in catalog cache keys. Scene frame checks use
numeric scalar equality and preserve the existing translations/server origins.
The editor reports that its source checks are structural; full polygon and
partition validation runs during baking.

Selected snapshot export calls the existing strict Python `ownership_contract`
validator with an argument array, before writing sidecars. The normal Python
build launcher passes its `sys.executable` as `--python` to the existing Godot
bake command. An interactive editor uses `python` on Windows or `python3`
elsewhere from PATH; interpreter/dependency/validation errors remain visible.
There is no validation certificate or second geometry implementation. Export
re-reads all ownership dependency bytes after strict validation and again before writing the
snapshot, rejecting a stale result.

Selected snapshots add:

```json
{
  "ownershipSource": {
    "path": "eloria-assets/maps/nymara-regions/_continent/ownership/selected.json",
    "sha256": "<source bytes SHA-256>",
    "revision": "<selected revision>",
    "regionId": "<region>",
    "planPath": "eloria-assets/maps/nymara-regions/_continent/diagonal-plan.json",
    "planSha256": "<plan bytes SHA-256>"
  },
  "sources": {
    "repositoryDependencies": [
      {"path": "<checkout-relative input>", "sha256": "<input bytes SHA-256>"}
    ]
  }
}
```

Repository dependencies are separate from Godot resource dependencies. They
contain the sorted exact plan/source/baseline records, never host absolute paths.
`seams.ownershipPolygonSha256` is derived by Python using compact JSON encoding
of the canonical scalar arrays; the old manually saved scene hash is not used
for a selected export. Python catalog, snapshot loading and composition verify
the selected source/frame and reject stale/missing bindings, including a removed
selection. Source dependencies feed the existing composition certificates.

The frozen `ownership/plan-feature-baseline-v1.json` preserves the exact original
plan bytes so existing certified feature claims remain verifiable when the
additive ownership selector changes the active plan hash. A selected editor/bake
requires this file. The entire active parsed plan, minus only
`ownership_contract`, must equal the baseline. Each authored feature claim still
requires the baseline's raw SHA to match its existing migration/composition
provenance; no expected hashes are rewritten. Baseline bytes participate in
snapshot dependencies, final stale checks, and captured catalog-entry checks.

For migrated terrain, `terrain.migration` is copied from the region spec into
the snapshot under either legacy or selected ownership. The shared manifest and
its height/color arrays are additional repository dependencies. Both languages
check contained paths, exact hashes, encodings, byte lengths, and the saved grid
origin against `globalVertexMin`. Export re-reads these sources before writing
the snapshot. Python production loading also requires snapshot migration
metadata to equal the current region spec. Historical grid hashes are lineage;
they do not prevent later saved terrain edits.

Selected composition requires the saved envelope to cover every incident vertex
of its owned cells plus the one-vertex 3x3 seam ring, before any terrain mutation.
The in-world mask is computed before local slicing. Legacy clipping is retained.
Activation still requires storage/wire/lane integration and normal region
rebakes. This slice does not activate the new authority.
