# Rabbit Lands asset authoring

Follow the parent workspace instructions for repository identity and branch policy.

Before changing map geometry, chunking, collision, material processing or map publication, read `docs/client-map-geometry-cache.md` and the linked texture/performance notes. Keep preparation scope and cache invalidation current, and qualify affected maps with load, memory, disk and appearance/physics checks. The private server handbook's `Client-Map-Preparation.md` records the reusable map workflow and measured limits; follow the workspace's handbook routing for internal notes.

For concept art, Meshy model generation, rigging/animation or reference-video fitting, use the corresponding complete `rabbitlands-*` skill under `.agents/skills/`. The creature-animation skill covers the integrated canine selection; the video-generation skill covers local image/video inference.

Read `docs/asset-authoring.md` before locating original high-resolution inputs or running historical processing helpers. They are consolidated in `.local/asset-authoring/`, which must remain Git-ignored. Keep credentials, old Git metadata and migration records outside the repository. Preserve historical hashes and create relocated working profiles instead of editing frozen provenance.

Procedural models across all asset types were retired at the user's request on 2026-10-16, including removal from game use. Read `docs/procedural-model-archive.md` and `eloria-assets/source/model-development-roster.json` before selecting animation targets. Black Bear and Ice Bear are archived procedural creatures; their attempted gait adaptations are withdrawn. Do not animate, regenerate, restore or select retired models by name similarity. Preserve current imported/Meshy models and the approved Moss Bear animation set. Shared readers, rig utilities and imported-model processors remain maintained; archived procedural generation entrypoints are disabled. Historical generator code and old QA descriptions do not authorize restarting that workflow.
