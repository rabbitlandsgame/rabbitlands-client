# Sculpt saved terrain

Open one of the twelve authored territory scenes. In **Territories**, turn on
**Sculpt terrain in 3D**, choose **Raise**, **Lower**, **Smooth**, or **Flatten**,
then drag the left mouse button over the active ground. Set the radius,
strength, and edge softness in the dock. For Flatten, enter a target Y height or
press **Pick** and click the desired terrain height. The cursor ring shows the
brush radius; a missed ray or protected border reports why it cannot paint.

## Brush keys

While sculpting, these keys work in the 3D view:

| Key | Action |
|---|---|
| 1 / 2 / 3 / 4 | Pick **Raise**, **Lower**, **Smooth** or **Flatten**. |
| `[` / `]`, or Shift+mouse wheel | Shrink or grow the radius. |
| Shift+`[` / Shift+`]` | Change the strength. |
| Ctrl+drag | Swap Raise and Lower for that stroke. |
| Ctrl+click with Flatten | Sample the target height, like **Pick**. |

- The cursor ring is coloured by brush: cyan for Raise, orange for Lower, blue for Smooth and gold for Flatten.
- Two lines at the bottom of the 3D view show the brush settings and these keys.
- The keys can be rebound under **Editor Settings > Shortcuts > Map Authoring**.
- The radius and strength step factors are under **Editor Settings > Map Authoring > Sculpt**.
- The brush cursor uses the fast terrain probe from [map-authoring-usability.md](map-authoring-usability.md), so hovering stays smooth on the full 397×397 grids.

## Heightmaps and plateaus

**Import heightmap…** in the sculpt section writes a greyscale image into the same sparse layer, with explicit heights for black and white, **Replace** or **Offset**, and the same border protection. Its area can be dragged out on the map, and **Preview** shows the result before anything is kept. **Map tools > Stamp plateaus…** adds Set or Add terrain patches instead, refusing any that would touch the protected border. Both are described in [map-authoring-usability.md](map-authoring-usability.md).

## Strokes, undo and saving

Each drag is one undo step. **Escape** cancels a drag. Releasing the mouse,
switching scenes, or using a camera gesture ends or cancels it safely. Alt,
right mouse, and middle mouse remain camera controls. Asset placement and
terrain sculpting are mutually exclusive. **Ctrl+Z** and **Ctrl+Y** use the
scene's normal editor history; **Ctrl+S** saves the sculpt layer in the active
scene. The region root's **Bake continent authoring snapshot** button exports an
active-scene diagnostic. The normal continent build consumes the saved layer.

The brush changes a sparse saved layer above the original height grid. It does
not rewrite the imported base file or any neighboring scene. The true
ownership polygon protects a strip at least two terrain cells wide; the next
two cells fade the brush inward. This also protects diagonal border triangles.
References temporarily step aside during a drag so the current active terrain
is visible, then return when the drag ends. Save/reopen keeps the layer.

Terrain patches, road shaping, and river shaping still run after the sculpted
base. Existing objects and water do not automatically snap to edited ground;
inspect them after large height changes. **Map tools > Drop selection to
ground** re-seats selected assets and markers on the new surface. A heightmap
import writes the same layer (see above).
