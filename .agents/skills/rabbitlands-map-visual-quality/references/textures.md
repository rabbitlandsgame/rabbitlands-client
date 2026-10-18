# Ground textures

## Judge what is there first

Tile each candidate 3x3 at a small size before judging it. A single tile hides
the two faults that show in a game: a repeat grid and a stripe.

- **One texture under several tints.** On the isles, Grass, Worn earth, Soil and
  Sand are all `src/dev/map_authoring_pilot/style/textures/ground-basecolor.png`,
  tinted in `texture_presets.gd`. A road then has no path structure and sand has no
  sand structure.
- **A texture from the wrong family.** Pale paving uses
  `weathered-limestone-masonry`, an architecture (wall) texture in regular brick
  courses. Laid flat it reads as a brick wall on the ground.
- **A repeat grid.** Generators darken tile edges, and the darker band repeats as
  a lattice even when the pixels wrap. Measure it as edge-to-edge difference
  against neighbour difference; `scripts/make_seamless.py` prints both.
- **An alpha vignette.** Some generated tiles come back RGBA with an alpha that
  falls off towards the edges. The coastal limestone gravel pack's alpha is about
  0.3 in the corners and 0.58 along the edges. The look multiplies a patch's
  coverage by its texture's alpha, so each tile edge opens to the ground beneath:
  the isles' scree showed a grid of green grout lines that no colour fix removed.
  Check the alpha channel of any RGBA tile; `make_seamless.py` writes RGB.
- **Stripes.** Directional detail (wear streaks, ripples) at a 3-4 m repeat
  becomes stripes across a field. Flatten it, or prompt it out.

## Make a new one

1. Prompt in the texture pack's structure:
   `src/dev/map_authoring_pilot/style/texture_packs/<id>/manifest.json`. The fields
   are use case, asset type, primary request, style/medium, composition/framing,
   colour palette, materials/textures with an intended world repeat, lighting,
   constraints and avoid. Ask for a flat orthographic square tile, uniform diffuse
   albedo, no centre feature and no edge treatment. Attach one or two approved pack
   tiles as style references only, and say so in the prompt.
2. Generate. Any image tool works. The 2026-10-17 set came back at 1254x1254 RGB.
3. Make it tile:
   `python scripts/make_seamless.py raw.png tile.png --size 1024`. It divides out
   low-frequency light falloff (`--flatten`, a share of the tile), then quilts the
   middle bands along a minimum-error cut, so stones stay whole.
   - Lower `--flatten` (0.03-0.05) removes wear streaks and ripples that would stripe.
   - Widen `--band` (0.45) for large structured content such as flagstones.
   - Check the result tiled 3x3 again.
4. Record provenance beside the file: the prompt, the generator, the source and file
   SHA-256, and the processing flags. See `godot-client/src/world/look/textures/README.md`.

## Put it in the game

There are two routes. Neither needs the other.

- **Runtime class texture (no republish).** Add the file under
  `godot-client/src/world/look/textures/`, add a name to `LookProfile.CLASS_TEXTURES`
  with its repeat in metres, and opt maps in with `ground.class_textures` in their
  look overrides (see `edge-pipeline.md`).
  - The shader maps it in continent metres, the same on every deck and patch, and
    rescales it to the source texture's mean colour. Palette and paint classes are
    unchanged; only structure changes.
  - Slots: `deck` (worn walk decks), `paving`, `sand`, `meadow`, `rock` and `soil`
    (`LookGround.class_slot`). Kept patches keep their own textures.
  - A scene's patch reaches the runtime as a tint and a texture, not as its preset
    name, so a slot is the runtime route to a preset. On the isles every `rock`
    patch is "Coastal limestone gravel" and every `soil` patch is "Soil"
    (`LookProfile.SOIL_TINT`). Check this with the chunk GLBs' materials before
    opting a map in elsewhere: on Nymara maps rock is also granite and lilac scree.
  - `.import` files are not versioned, so `LookGround.class_texture` builds the
    mipmaps itself.
- **Authored preset (republish).** Add a texture pack folder and a preset in
  `src/dev/map_authoring_pilot/style/texture_presets.gd`, then assign it to surfaces
  in the scenes. The bake publishes it content-addressed into
  `_continent_v2/shared-assets/`.
  - Use this route for a texture a whole map's design should own, or for a surface the
    look cannot tell apart by tint (on the isles, forest floor is a plain glaze).
  - A seam fix to a pack tile belongs here too, as a new pack version. Until a
    republish ships it, the runtime slot carries it (the isles' coastal gravel).
  - It needs the full publication order: bake every catalog map and run
    `publish_client`, then `publish_server`.

New PNGs need `godot --headless --path godot-client --import` before a test or bake
can load them.
