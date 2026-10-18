# Action cursor artwork

The current 14-cursor family uses original Rabbit Lands artwork generated with
OpenAI image generation on 2026-10-18 and reviewed in-game at 32x32 pixels.
Ivory faces, muted brass accents, restrained shading and antialiased contours
replace the previous doubled 16x16 monochrome glyphs. The pointer has a centered
tail, the attack sword points upper-left, and trade uses two exchanging hands.

The published PNGs and `cursors.json` live in
`godot-client/assets/ui/cursors/`. Each image is 32x32 RGBA with transparent
padding. Hotspots use image pixels, without further runtime scaling, and retain
the existing cursor ids and action behavior. The sword and pointer click at
their tips, the wand at its star, and the text caret at its center.

Run `python godot-client/tools/make_action_cursors.py` to validate the published
family. Add `--out <directory>` to copy the exact images and manifest or
`--preview <image.png>` to inspect actual-size light/dark samples and enlarged
pixel detail. The helper does not regenerate the retired character-map art.

High-resolution generation sources, exact prompts, superseded takes and the
previous runtime set remain in the ignored local authoring stage
`.local/asset-authoring/working/cursor-refresh-2026-10-18/`. Eternal Lands artwork
was used only as a comparison and gesture reference; its pixels are not part of
the Rabbit Lands cursor assets.
