# Local asset-authoring workspace

Procedural model outputs across all types were archived and removed from game
use on 2026-10-16. See [the retirement record](procedural-model-archive.md) before
running older builders or selecting animation targets. Their original sources
are recoverable in the ignored archive; current imported-model processing tools
and approved models remain active. Historical receipts below describe completed
verification and do not reactivate retired generators.

The complete concept-art, Meshy model-generation, rigging/animation and video-motion-fitting skills live under `.agents/skills/rabbitlands-*`. Their references and UI metadata are included. The existing video-generation and creature-integration skills remain available.

Original high-resolution models, full-resolution textures, concept inputs, animation libraries, generated source stages and processing scripts are consolidated under:

```text
.local/asset-authoring/
  workspace/          Preserved authoring folder layout and asset stages
  original-scripts/   Exact pre-relocation copies of changed scripts
  working/            Relocated profiles and future processing outputs
  production-snapshot/ Current game's asset-processing sources
  referenced-inputs/  Additional originals traced from production manifests
  location-map.json   Private old-to-new filesystem mapping
  copy-receipts.jsonl Per-file SHA-256 copy verification
  status.json         Resumable transfer status
```

This entire directory is ignored by Git. It contains local authoring data, not assets to package with the game. No credentials, old Git metadata or migration identity records belong here. Packaged game releases, engine caches and rebuildable map caches are outside the transfer scope. Original files remain intact at their source.

The transfer verified 348,626 files (239,423,641,584 bytes) and updated literal paths in 1,233 copied scripts with exact original backups. All four complete skills include their 18 supporting references and original UI metadata. `docs/qa/asset-authoring/transfer-summary.json` records the public summary; full per-file inventories remain local. The tracked ignore rule and repository-local exclusion protect the archive across branch changes.

The archive retains original folder names such as `generate_models`, `eloria-tools` and `eloria-client` so related inputs still line up. These are local authoring snapshots; current development and publication target the Rabbit Lands repositories. The historical client source snapshot is not a Git checkout. Tools that replay historical Git commits still require the separately retained original checkout; this migration does not manufacture the old history.

Useful locations from the client checkout:

- Raw/processed source models: `.local/asset-authoring/workspace/generate_models/`
- High-poly players: `.local/asset-authoring/workspace/highpoly_actors/`
- Full-resolution texture/pre-quantization sources: `.local/asset-authoring/workspace/archive/`
- Concept art: `.local/asset-authoring/workspace/concept_art/` and `oldcraft_style_concept_art/`
- Original rig/Meshy processing tools: `.local/asset-authoring/workspace/eloria-tools/`
- Original actor assets, registries and playback scripts: `.local/asset-authoring/workspace/eloria-client/godot-client/`
- Asset-specific processing stages: `.local/asset-authoring/workspace/work-output/`
- Original map generators/sources: `.local/asset-authoring/workspace/eloria-client/eloria-assets/maps/`
- Current reference-motion fitting tools: `eloria-assets/tools/video_motion/`
- Current portable canine replay package: `eloria-assets/source/animations/canine/`

Literal old workspace prefixes in executable processing scripts are relocated, with their exact originals and change receipts retained locally. Historical JSON reports, acceptance records, manifests and binary assets retain their original bytes and hashes. Before running an old profile, create a working copy with relocated paths:

```powershell
python tools/asset-authoring/localize_profile.py `
  --input .local/asset-authoring/workspace/generate_models/wolf_action_motion_pilot/source/dire_wolf.action-rig.json `
  --output .local/asset-authoring/working/dire-wolf/action-rig.json
```

This changes known filesystem prefixes and rebases a relative `source_glb`; native curves, event times, role names and source hashes are preserved. Read the working profile before executing a fit. A new execution records its own dependency hashes; historical receipts continue to describe the original authoring run.

Inspect tools without generating or spending credits:

```powershell
python .local/asset-authoring/workspace/eloria-tools/rig_glb.py --help
python .local/asset-authoring/workspace/eloria-tools/meshy_gen.py --help
python eloria-assets/tools/video_motion_cli.py --help
```

Use explicit input/output options for historical helpers and keep new intermediate work under `.local/asset-authoring/working/`. Runtime promotion remains a deliberate step with preservation, deformation, contact and engine checks. A paid Meshy job still needs scoped authorization; copying the existing ledger does not submit or authorize another job. The source `meshy.key` is not transferred; use the configured environment when a future authorized job needs credentials.
