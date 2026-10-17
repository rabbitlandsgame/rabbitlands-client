# Look class textures

Ground detail textures a region can lay over its walk decks, pale paving, sand
and meadows (`ground.class_textures` in its look file; `LookProfile.CLASS_TEXTURES`).
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
