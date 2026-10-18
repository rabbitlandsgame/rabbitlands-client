# Look class textures

Ground detail textures a region can lay over its walk decks, pale paving, sand,
meadows, bare rock and bare soil (`ground.class_textures` in its look file;
`LookProfile.CLASS_TEXTURES`).
The look pass keeps the source texture's mean colour and takes only the
structure from these (see `painted_ground_surface.gdshaderinc`), so they change
how a surface reads, not a map's palette.

They were made for the Landfall isles' map visuals audit (2026-10-17). Those
maps drew roads, sand, soil and lawns from one mottled ground texture under four
tints, and their paving from wall masonry laid flat.

| File | Use | Repeat | Source SHA-256 (generated) | File SHA-256 |
|---|---|---:|---|---|
| `packed-earth-path.png` | worn walk decks | 3.5 m | `53973b79eb8887fee5f7ddfc791e954ab422e5b1ed775898ecbd3193b6e4d077` | `a2b082adfc5e48247883414ee7d4a16195d048f2f8e77f21f0b2f3e31e58d521` |
| `flagstone-paving.png` | pale paving | 3.2 m | `34f3a961c8a8f8eed433142afe9cf156d9836163255ecba1d49e6181c78e2b81` | `71f3eaf384cdbfaec8e9feaa1fc1404a375c84c5fecfc1813caa811857fdfbe7` |
| `beach-sand.png` | sand glazes | 4 m | `9074f0f802ae065b57727edc3e89c32b52168e479a6a68a63c97993a3457feb9` | `08fc23be7a27463682741a7c1ca73bb1fc2a203d4160787d85ec74720b09f079` |
| `coastal-gravel.png` | bare rock: the isles' coastal scree and shingle | 4 m | `9ee53453b9ded8fedd5fdbff750c5d9f7c80bf985dc2cfd49207c15860a057e7` (pack tile, not regenerated) | `8ceb494b4b117ba3372ccb353a22909455be2d5e9e107985401110ff3261bdc4` |
| `tilled-soil.png` | bare soil: the isles' ploughed fields | 3.5 m | `0cc2ea142e1309414b47ed31bd9c5c05f951a9d6624a96441451e7ed6211c27c` | `85cde066a2fdd1a01f91e057054489ecf627636d16f1d68f18c1d081ffb5ba59` |

A fourth, meadow turf, was generated with them and dropped. At a 4 m repeat its
fine clover and grass detail averaged to flat green at the game camera, and the
lawns lost the mottle the painted look relies on. A meadow texture needs
structure at a 1-4 m scale, not a 5 cm one.

## How they were made

Each source is a 1254x1254 albedo from the OpenAI image generation tool
(through Codex), prompted in the same structure as
`src/dev/map_authoring_pilot/style/texture_packs/*/manifest.json`, with the pack's
`forest-floor-moss` and `coastal-limestone-gravel` tiles attached as style
references only. The shared prompt tail:

> Style/medium: quiet painterly hand-painted low-poly fantasy ground in the same
> brushwork, saturation and scale as Image 1 and Image 2 (style references only;
> do not copy their content); medium-scale surface detail. Composition/framing:
> flat orthographic top-down square tile, evenly distributed detail with no centre
> feature; left/right and top/bottom edges must wrap seamlessly with no framing or
> edge treatment. Lighting/mood: uniform neutral diffuse albedo only. Constraints:
> both-axis seamless repeat; texture only; diffuse base colour only. Avoid: edge
> frame, borders, vignette, gradients, cast shadows, highlights, directional
> lighting, perspective, horizon, text, logos, watermark.

The subjects:
- packed earth: a trodden footpath of warm compacted ochre-brown soil, fine dust,
  small rounded pebbles, hairline cracks, faint foot-worn streaks, a few dry
  sprigs. No bricks, cobbles, tiles or regular patterns.
- flagstone: randomly laid weathered pale limestone flagstones, 30-80 cm, soil
  joints with tiny moss and grass. No brick courses or mortar grid.
- beach sand: fine pale golden sand with low wind ripples, sparse shell fragments
  and pebbles.

Generated images never wrap cleanly. Each was resized to 1024x1024 and made
seamless with `.agents/skills/rabbitlands-map-visual-quality/scripts/make_seamless.py`.
That script divides out low-frequency light falloff (the edge darkening that
repeats as a grid), rolls the tile by half, and replaces the middle bands along a
minimum-error cut. Defaults were used except: packed earth `--flatten 0.035`
(its wear streaks repeated as diagonal stripes); flagstone `--band 0.45
--flatten 0.08`.

## Coastal gravel and tilled soil (2026-10-17, second pass)

The isles' remaining ground surfaces are authored presets: "Coastal limestone
gravel" (every patch the look classes as rock), "Forest floor moss" and "Soil".

- **Coastal gravel** is not a new image. It is the pack's own tile,
  `src/dev/map_authoring_pilot/style/texture_packs/coastal-limestone-gravel/coastal-limestone-gravel-v001.png`,
  run through `make_seamless.py --size 1024` with the defaults, which also
  drops its alpha. The grid the isles' scree showed came from that alpha, not
  the colour: the generator returned RGBA with a vignette in the alpha (about
  0.3 in the corners, 0.58 along the edges, 0.94 inside). The look multiplies
  coverage by the texture's alpha, so every 4 m tile edge opened to the grass
  beneath. A class texture now brings its own alpha
  (`painted_ground_surface.gdshaderinc`).
  The colour's mean is unchanged (188.7, 181.2, 162.6 against 188.5, 181.0,
  162.2), so the patches keep their look and lose only the grid.
- **Tilled soil** was generated as described above, with `packed-earth-path.png`
  (Image 1) and the `forest-floor-moss` pack tile (Image 2) attached as style
  references. The subject: a tilled farm field of warm brown loam in soft clods
  10-40 cm across, darker damp hollows and lighter dry crests grouped in broad
  1-2 m patches, a few small pale stones and short bits of straw, intended
  repeat about 3.5 m. It asked for no furrows, ridges, rows or ruts, because
  directional detail stripes at a world repeat. It was made seamless with the
  defaults. It replaces `ground-basecolor.png`, which the fields shared with
  the lawns. The tile is redder than that texture (hue 28 against 40 degrees),
  and `CLASS_TEXTURE_HUE` keeps half of it: at the game camera Landfall's farm
  field moved from hue 34 to 30 degrees and saturation 0.45 to 0.49.
- **Forest floor** has no class texture. The moss pack is already its own
  texture, and it wraps without a grid when tiled 3x3 (its alpha is a near
  uniform 0.95). What it lacks at the game camera is coverage: all 103 forest
  floor patches on the isles are authored at opacity 0.4, under the look's 0.42
  patch cut (`LookProfile.PATCH_RIM`), so most of each patch is cut away and
  what is left is the brightest moss in noisy blocks. That needs a look or
  content change, not a texture.
