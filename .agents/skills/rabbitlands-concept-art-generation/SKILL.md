---
name: rabbitlands-concept-art-generation
description: Generate and review Rabbit Lands concept art in the project's chunky hand-painted Oldcraft style, especially images intended as reliable inputs for image-to-3D generation. Use for characters, creatures, equipment, props, regions, and interiors; for prompt authoring; or for deciding whether an image is production-ready for Meshy.
---

Paths are relative to the Rabbit Lands client checkout. Original assets, authoring stages, scripts and private memory are consolidated under `.local/asset-authoring/workspace/`. Read [the local authoring workspace](../../../docs/asset-authoring.md) for current tools, path relocation and historical receipt handling. Preserve Eloria lore and compatibility-sensitive identifiers.


# Rabbit Lands Concept Art Generation

Create images that communicate one production decision clearly. For any asset that will become a 3D model, prioritize readable construction over illustration spectacle.

Before prompting or reviewing an asset, read [references/style-and-input-contract.md](references/style-and-input-contract.md). Use [references/prompt-templates.md](references/prompt-templates.md) for the matching asset class.

## Workflow

1. Find the authoritative Eloria source for the asset's identity, anatomy, palette, equipment, scale, and region. Treat prose and registries as content truth; use existing concept art only as visual evidence.
2. Choose the production mode before writing the prompt:
   - **Exploration:** vary silhouette, palette, or signature feature while preserving the brief; do not present an unselected variant as production truth.
   - **Faithful recreation:** preserve the accepted identity and construction. Minimize competing style language and state exactly what may change.
   - **Single-image 3D input:** one complete character, creature, wearable, or prop per image; a restrained front three-quarter view may expose useful volume.
   - **Orthographic reference pack:** a dead-front master plus separately generated side/back support views. All views and isolated parts must preserve the same design, scale, pose, and camera height.
   - **Environment concept:** communicates layout, landmarks, mood, and traversal; it is not direct single-object Meshy input.
3. Choose two to four relevant local style references. Prefer references with the same asset class and body plan. Do not copy their identity or scenery.
4. Write a prompt with five explicit layers: identity, silhouette/proportions, materials and palette, presentation, and exclusions.
5. Generate with the image-generation tool. Generate distinct assets as separate calls so each receives an individual production image. (In Claude Code that tool is the user-level `gpt-image-bridge` skill: `~/.claude/skills/gpt-image-bridge/bin/gpt-image-2 "<prompt>" <out.png> --image <style ref>...`. It reaches the same image model through Codex, returns about 1.6 MP, and is safe to run in parallel.)
6. Review the result at full size against the acceptance gate below. Classify it as `pass`, `soft_fail`, or `hard_fail` and record the reason. A soft failure may remain as design reference but is not direct 3D input.
7. For a hard failure, retry at most twice with the observed failure stated explicitly. Strengthen only the failed constraint so identity does not drift. After three failed attempts, stop and show the attempts rather than silently accepting one.
8. Save the image, exact prompt, source references, dimensions, production mode, intended camera, stable asset ID/slug, generation date, attempt number, and verdict together. Keep production-selected images separate from explorations and preserve rejected takes with concise reasons.

## Acceptance gate for 3D inputs

Accept an image only when all are true:

- One complete subject is visible, centered, and not cropped.
- The silhouette reads at thumbnail size and does not merge important appendages.
- Limb, head, wing, horn, fin, finger, toe, and tentacle counts are unambiguous.
- The pose is neutral and construction-friendly: feet share a ground plane, arms and legs have clearance, wings are relaxed, and tails follow a readable centerline.
- The camera matches the production mode. A single-image input may use a restrained front three-quarter view; a master for modular parts, fitting, or orthographic reconstruction must be dead front with no body twist.
- Materials and color regions are readable without dramatic lighting, fog, bloom, or cast shadows.
- The background is flat white or light neutral gray, with no scenery, floor platform, frame, labels, text, or adjacent subjects.
- Thin structures have enough visual thickness to become geometry. Moving parts have visible attachment roots.
- The design remains recognizably Eloria: chunky broad forms, restrained surface frequency, painted matte materials, and a game-readable silhouette.

For turnarounds, generate views separately and verify that front, side, and back are intentional orthographic projections rather than intermediate three-quarter angles. Never use a multi-subject sheet as the Meshy input; isolate and approve one view supported by the others.

For modular humanoids, generate the strict-front full-body A-pose master before extracting body, hair, paired items, or equipment. Keep every extracted part at the same front orientation and scale relationship. Generate side/back parts only as a separate support pass; do not mix a hero-angle accessory with strict-front body parts.

## Environment concepts

For maps and interiors, preserve the same painted stylization but optimize for play-space communication: traversable paths, landmark hierarchy, elevation changes, encounter spaces, entrances, exits, and biome transitions. Avoid labels unless the user explicitly requests a labeled design map. Do not claim an environment painting alone is sufficient construction data for a level.

## Project sources

Use these local sources when present:

- `.local/asset-authoring/workspace/oldcraft_style_concept_art/PROMPTS.md` for the established style language.
- `.local/asset-authoring/workspace/oldcraft_style_concept_art/manifest.json` for generated asset records.
- `.local/asset-authoring/workspace/concept_art/README.md` for the broader reference registry.
- `.local/asset-authoring/workspace/concept_art/creatures/basic_creature_expansion_100/MODELING_HANDOFF.md` for model-facing creature constraints.

Do not modify source references while generating new art. Put deliverables in a named output stage with subdirectories by asset class and a machine-readable manifest.
