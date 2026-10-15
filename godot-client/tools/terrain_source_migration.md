# Saved terrain envelope migration

`migrate_region_terrain.py` is an explicit source migration, separate from bootstrap
import. It does not select an ownership plan, publish runtime data, move regional
frames or change server storage. It needs Python/NumPy and the existing continent
ownership loader.

`prepare --transaction <external-directory> --contract <checkout-relative-source>
--seed-checkout <staging-root>` derives owned-cell incident vertices plus the
production 3×3 ring, unions those bounds with every old grid, validates the complete
saved source tree, and stages an exact allowlist with original bytes. The seed
checkout contains `godot-client/world_authoring/terrain/shared-field-v1/manifest.json`
and its hash-bound float32/RGBA8 arrays. Source records in that manifest describe
historical derivation; consumers read the portable seed, not the old publication.

`apply --transaction <directory>` rechecks every precondition, payload and backup
before writing. Each file is replaced atomically, with a per-file recovery journal.
Re-running an interrupted application resumes only where the original or staged
hash still matches; unrelated edits cause rejection. A committed repeat performs
zero writes. `rollback` restores original bytes and removes files created by this
transaction, refusing to overwrite concurrent edits. Keep the transaction directory
until the source changes are reviewed. An interrupted prepare has made no product
writes; an interrupted apply is diagnosed by `journal.json` plus actual file hashes.

`verify --transaction <directory>` checks the full source tree and extracts each old
rectangle from its new global location to prove old base/color bytes are unchanged.
Only Terrain.origin/grid_size are edited in scenes; the remaining scene bytes are
identical. Grid indices are global lattice identities, so changed row widths cannot
shift old sculpt coordinates. Growing scenes with active modifiers fail explicitly;
resolved samples cannot become their base without a separate modifier policy.

After application, load each saved scene with Godot and use the ordinary exporter:

```
Godot --headless --path godot-client --script res://tools/validate_migrated_terrain.gd -- REGION OUTPUT.json
```

The helper validates loaded dimensions and invokes `region.export_snapshot`. It
does not save or modify the scene. Use bounded processes and keep diagnostic exports
outside runtime assets. A legacy-selection export is source evidence; repeat the
normal selected-source export after ownership activation before publication.

Focused tests: `python godot-client/tests/test_terrain_source_migration.py`.
