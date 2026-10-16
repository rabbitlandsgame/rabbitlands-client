# Rabbit Lands asset authoring

Follow the parent workspace instructions for repository identity and branch policy.

For concept art, Meshy model generation, rigging/animation or reference-video fitting, use the corresponding complete `rabbitlands-*` skill under `.agents/skills/`. The creature-animation skill covers the integrated canine selection; the video-generation skill covers local image/video inference.

Read `docs/asset-authoring.md` before locating original high-resolution inputs or running historical processing helpers. They are consolidated in `.local/asset-authoring/`, which must remain Git-ignored. Keep credentials, old Git metadata and migration records outside the repository. Preserve historical hashes and create relocated working profiles instead of editing frozen provenance.
