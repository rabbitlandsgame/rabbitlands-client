# Enriched essence paintings

The [radiant-burst selection](../enriched-essences-radiant-2026-10-30/README.md)
now supersedes these initial eight paintings in the runtime atlas. This source
set remains intact for provenance and exact replacement-hash validation.

Eight separate built-in imagegen edits enhance the selected Life, Fire, Water,
Earth, Wind, Death, Magic and Frost paintings. Wind uses the Air source image.
The base silhouettes and palettes remain recognizable; luminous cores and
brighter painted highlights identify the rare versions at inventory size.

The selected 50×50 cells occupy image IDs 617–624 and item IDs 1950–1957. Their
manifest records exact prompts, original generated image and edit-target hashes,
base-cell hashes, dimensions and selection verdicts. Generated transparency is
preserved through Lanczos resizing and composited onto the standard dark teal
backing with a clear three-pixel perimeter. Full-resolution authoring inputs,
outputs and paired review images stay in the ignored local task stage.

`python eloria-assets/tools/build_item_icon_atlases.py --check` validates every
source and confirms exact runtime pixels. Rebuilding adds these cells to
`items25.png`; existing base essence cells and all other inventory art remain
unchanged. The original eleven-cell selection is retained as historical art
provenance; retired Matter, Energy and Spirit cells are no longer referenced
by active item definitions.
