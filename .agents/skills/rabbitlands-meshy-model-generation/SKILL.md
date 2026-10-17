---
name: rabbitlands-meshy-model-generation
description: Generate, resume, download, organize, and validate Rabbit Lands 3D models through Meshy Image-to-3D using the project's paid-task ledger and hybrid production workflow. Use when choosing between direct Smart Topology and a high-detail-to-baked-low-poly route, running .local/asset-authoring/workspace/eloria-tools/meshy_gen.py, recovering a batch, or reviewing models before rigging.
---

Paths are relative to the Rabbit Lands client checkout. Original assets, authoring stages, scripts and private memory are consolidated under `.local/asset-authoring/workspace/`. Read [the local authoring workspace](../../../docs/asset-authoring.md) for current tools, path relocation and historical receipt handling. Preserve Eloria lore and compatibility-sensitive identifiers.


# Rabbit Lands Meshy Model Generation

Treat Meshy submission as a paid, stateful production operation. Preserve task IDs, downloads, hashes, source concepts, and rejected outputs. Never delete a ledger or resubmit a completed task just to make a clean run.

For Meshy image-to-video followed by rig animation, use [Eloria Video Motion Fitting](../rabbitlands-video-motion-fitting/SKILL.md). The 3D API client and its generation ledger do not submit the website's video jobs. Each video needs its own exact reference-image/upload authorization, displayed quote, prompt, settings and task receipt; a prior model/walk job approval does not cover additional jobs.

When polishing an existing video-derived animation or transferring it to another actor, reuse the recorded reference and native fitting stage; local corrections do not need another provider job. A generated video is a motion reference, not an exported skeleton or accepted animation. For continuing the wolf pilots, read `.local/asset-authoring/workspace/memory/wolf-video-motion.md` in the workspace for selected artifacts and receipt locations. Recheck live settings and quotes only when a new authorized generation is needed.

Read [references/hybrid-production-routing.md](references/hybrid-production-routing.md) to choose the production route. Read [references/commands-and-settings.md](references/commands-and-settings.md) before running the local client. Read [references/model-review.md](references/model-review.md) before approving an output for rigging.

## Workflow

1. Confirm the input passes the concept-art 3D-input gate: one isolated subject, complete silhouette, neutral construction-friendly pose, unambiguous anatomy, flat background, and no text or scenery.
2. Create a new output stage. Keep source concepts immutable and preserve stable IDs/slugs in filenames.
3. Classify the asset as **volume/direct**, **hero/bake-down**, or **deformation-critical** using the hybrid routing reference. Record the choice and reason before generation.
4. Inventory inputs and run the local client with `--dry-run`. Review ordering, planned settings, output path, and which ledger records will be skipped.
5. For volume/direct assets, use the established Smart Topology baseline: 4,000 target faces, 2K base color, no PBR maps, and no Meshy rigging. Change this only for a documented asset need.
6. Obtain explicit user authorization before a command that submits paid API tasks. Never print or commit API keys. Supply the key with `MESHY_API_KEY` in the process environment or `--api-key`; do not keep a key file in the checkout, including the ignored authoring archive.
7. Submit one representative pilot before a large new asset class or changed settings. Persist its task ID immediately, download it, and apply both the structural and visual review gates. Existing authorization covers this pilot; ask again only if continuing the full batch would materially exceed the approved scope or cost.
8. Run or resume the batch. Re-running the same command is the recovery path because the ledger records accepted task IDs. A polling timeout or interrupted client is not a failed task and never justifies duplicate submission. Resolve the saved task ID first.
9. Use `--retry-failed` only after inspecting the provider's terminal failure and the input. It creates a new paid task. Do not automatically retry repeated content, anatomy, or topology failures; revise the source or settings instead.
10. Preserve every original Meshy download. Put cleanup, scale correction, topology edits, rigging, animation, and bake-down work in later stages.
11. Record two separate outcomes: **technical completion** (the service produced valid downloadable files) and **production acceptance** (the asset passed anatomy, topology, texture, and deformation review). Never infer the latter from task status.
12. Record selected/rejected status, source image hash, task ID, route, settings, model hashes, geometry counts, texture properties, bake provenance when applicable, and review notes in the batch manifest.

## Decision rules

- Prefer Image-to-3D over Text-to-3D when approved concept art exists.
- Prefer Smart Topology for ordinary creatures, background NPCs, prototypes, small props, and assets viewed mainly at gameplay distance. Meshy's current API uses `model_type: smart-topology` with `ai_model: meshy-t2`; it directly targets 100–15,000 faces.
- Use the high-detail-to-baked-low-poly route for player races, major bosses, close-up characters, complex armor, hero props, or assets whose important material/surface detail would be lost at direct generation. Do not use it merely because more polygons sound better.
- Deformation-critical topology is an independent requirement. Shoulders, hips, jaws, hands, wing roots, cloth joints, and unusual appendages may require intentional retopology even when the asset does not need a detailed high-poly source.
- If Smart Topology repeatedly fuses thin parts or destroys the silhouette, stop resubmitting the same input. Improve the reference or deliberately change routes.
- Use pose forcing only for humanoids that will benefit from A- or T-pose generation. Do not force humanoid poses onto quadrupeds, serpents, flyers, or unusual creatures.
- Do not use Meshy auto-rigging for this creature pipeline. Local tools support body-plan-aware and custom rigs and preserve the project animation contract.
- Keep base-color-only output for the established Eloria creature look unless the target runtime/material design explicitly needs PBR maps.
- Do not approve from the front view alone. Smart Topology may separate parts; decide deliberately whether parts should be joined, rigidly attached, or independently skinned.
- Keep the exact provider task ID and canonical output metadata in the private ledger. Shareable reports may include stable IDs and hashes but must omit credentials and expiring signed download URLs.

## Current external reference

Check the official [Meshy Image-to-3D API documentation](https://docs.meshy.ai/en/api/image-to-3d) before changing API fields or model IDs. The local client is authoritative for what this repository currently supports; update it and this skill together when the API changes.

## Local evidence

The completed `.local/asset-authoring/workspace/generate_models/basic_creature_expansion_100_meshy/` batch remains the volume/direct reference implementation: 100 textured Smart Topology models, approximately 4,000 triangle faces each, 2K embedded base color, and no Meshy rigging. Hero/bake-down assets require their own staged evidence and do not change this baseline.
