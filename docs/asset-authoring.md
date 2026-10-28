# Local asset-authoring workspace

Creature runtime sampling, fixed mesh/skin fitting and approval follow the maintained [creature runtime optimization skill](../.agents/skills/rabbitlands-creature-runtime-optimization/SKILL.md). The [completed retrofit report](qa/creature-storage/completed-runtime-retrofit.md) explains the review browser and separate draft/delivery choices. For optimized installed assets, [runtime-delivery.json](qa/creature-storage/runtime-delivery.json) records current hashes and cadence; frozen authoring observations remain historical evidence.

The [visually accepted delivery registry](qa/creature-storage/visually-accepted-delivery.json) now supersedes overlapping conservative selections. See the [191-model installation report](qa/creature-storage/accepted-creature-delivery.md) for exact-version acceptance, qualified local-draft metadata and retained repair notes.

The later [accepted repair delivery registry](qa/creature-storage/accepted-repair-delivery.json) takes precedence for Skeleton, Tengu, Giant Wasp, Heartwood Treant and Nightweave Spider. Their new exact-version acceptance retains the earlier draft findings and known limits.

Regional map detail images are rendered from the current published chunk GLBs,
including shared mesh placements, with `eloria-assets/tools/render_region_map_details.py`.
The maintained chunk reader and native cartography rasterizer are reused; no map
geometry or retired procedural model is regenerated. The four-pixels-per-metre
`map-detail.webp` sidecars share the exact Tab-map extent. Their independent
`godot-client/data/maps/map-details.json` index leaves the certified continent
overview and its original renderer inputs unchanged. Run from the client root:

```powershell
python eloria-assets/tools/render_region_map_details.py --work .local/asset-authoring/working/map-detail-4ppm --apply
python eloria-assets/tools/render_region_map_details.py --check
```

The render command resumes by skipping detail images whose frame, pixels and
chunk inputs are current. `--region <id>` scopes a run. Intermediate reports and
native libraries remain ignored; only the detail images, minimap detail metadata
and generated index belong with the client. Re-run after publishing changed map
chunks. The renderer expands shared scenery and applies the same retired-model
index as the game; the reader version and policy hash invalidate old renders.
Runtime loads detailed images with mipmaps for the active region, nearby regions
visible while magnifying or panning, and the latest preview. At most five visible
regions and one preview are retained; the wider overview uses smaller images.

Procedural model outputs across all types were archived and removed from game
use on 2026-10-16. See [the retirement record](procedural-model-archive.md) before
running older builders or selecting animation targets. Their original sources
are recoverable in the ignored archive; current imported-model processing tools
and approved models remain active. Historical receipts below describe completed
verification and do not reactivate retired generators.

The complete concept-art, Meshy model-generation, rigging/animation and video-motion-fitting skills live under `.agents/skills/rabbitlands-*`. Their references and UI metadata are included. The existing video-generation and creature-integration skills remain available.

Completed creature deliveries also use the [creature runtime optimization skill](../.agents/skills/rabbitlands-creature-runtime-optimization/SKILL.md): 30-sample/second delivery candidates, offline mesh/skin corrective reduction, independent shading and blend checks, and ordinary uncompressed creature GLBs. Dense private authoring evidence remains preserved. Actor-specific visual acceptance controls approximate runtime replacement.

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

### Imported quivers (2026-10-20)

The eight selected Meshy quivers have current-body variants for all sixteen
player rigs. Their portable source meshes and measured fitting frames are in
`eloria-assets/source/quivers/`; rebuild instructions and the part-8 visual
contract are in that directory's README. `fit_quivers.py` reshapes only imported
geometry, preserving the current rig rest contract. Runtime textures are shared
across the body variants. The engine probe is
`tests/integration/quiver_equipment_fit.gd`.

Item icon IDs 599-606 extend the approved paintings through the public
`item-icons/quivers-2026-10-20` supplement. The atlas builder checks the original
painting hashes and preserves IDs 0-598. No retired model builder is involved.
