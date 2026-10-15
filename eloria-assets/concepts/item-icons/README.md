# Potential item icon sheets

These 20 themed sheets provide 500 potential item concepts in the same compact
fantasy UI style as the active Eloria item atlases. They are concept assets
only: neither the client runtime atlas registry nor the server item catalog
loads them yet.

Each PNG is 256×256. The first 250×250 pixels contain a fixed 5×5 grid of
50×50 cells; the final six rows and columns are transparent padding. Icons are
listed in row-major order in `manifest.json`, so a future item can be promoted
without guessing its source cell.

The generated source contact sheets were packed cell-by-cell with
`godot-client/tools/pack_ui_icon_sheet.py`. Independent cell cropping keeps
frames, glows, and silhouettes from bleeding into adjacent icons during
downsampling.

Design constraints shared by all sheets:

- one centered object per cell, with no cross-cell overlap or clipping;
- uniform rounded-square dark teal plates with antique-gold corner accents;
- simplified silhouettes targeted to their inventory function;
- cohesive, restrained theme palettes and no text or numeric overlays.

To promote a concept into gameplay, copy its cell into a runtime item atlas,
update `godot-client/data/items/atlases.json` as needed, and add the separate
server item definition. Those integration steps are intentionally outside this
concept-only set.
