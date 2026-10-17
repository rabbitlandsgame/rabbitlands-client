# Look pass region files

Each map or continent region that looks different from the look pass's
defaults has one file here, `<id>.json`. `LookProfile` reads a file the first
time the id is asked for and keeps it for the rest of the session (the cache
is locked, because chunks are painted on the loader's worker threads). Every
constant in `look_profile.gd` is the default for every map; a file only says
where its map differs. **A map without a file is drawn with the defaults**,
so a missing file is never an error.

`tests/look/test_look_regions.gd` checks every file here: it must parse, name
itself, and hold nothing unknown or mistyped. Run it after editing a file:

```
Godot --headless --path godot-client --script res://tests/look/test_look_regions.gd
```

A file with a problem still loads: the bad key is left out (the default is
used) and the client prints `look region <id>: ...` as a warning.

## Which id

`<id>` is the manifest's asset id (`asset.id` in its `world.json`), which is
what `LookGround.region_of` and `LookGrade` use:

- A continent region: its id, for example `amberwood`, `grey_moors`,
  `manymouth_delta`. Its chunks (`<region>__chunk_<x>_<z>`) and its preview
  copy as a neighbour read the same file.
- A standalone map: its id, for example `lantern_reach`, `bellwatch`.
- An interior: its asset id, which is **not always its registry key**. For
  example, registry `drowned_crown` is asset `crownwater_insides`,
  `sunmane_wind_caves` is `sunmane_insides`, `resonant_vault` is
  `amethyst_barrens_insides`, `whitehorn_glacier_temple` is
  `whitehorn_insides`, `grey_moor_barrows` is `grey_moors_insides`,
  `manymouth_flooded_labyrinth` is `manymouth_delta_insides`,
  `ssarathi_royal_archive` is `ssarathi_insides`, and `amberwood_estate` is
  `amberwood_insides`. The look pass only grades and paints maps that declare
  an enabled sun, so most interiors never read a file.

## Format

```json
{
	"id": "lantern_reach",
	"schema": 1,
	"grade": {"exposure": 1.6, "exposure_forward": 1.04},
	"ground": {"verge_value_green": 0.82, "verge_green_red_forward": 0.55},
	"grass": {"root": [0.05, 0.14, 0.05], "tip": [0.4, 0.55, 0.22], "value_forward": 1.7},
	"sky": {"top": [0.16, 0.42, 0.8], "horizon": [0.66, 0.82, 0.9]},
	"water": {"decode_albedo": {"res://src/world/lantern_water.gdshader": 2.5}},
	"foliage": {"crown_materials": ["foliage_green"], "tree_words": ["palm"]},
	"notes": {"ground": "why the trims are what they are"}
}
```

- `id` must be the file's own name. `schema` is 1. `notes` is prose for
  whoever retunes the region. It can be a string or an object keyed by
  section. Write down what you measured, so the next person does not undo it.
- **Numbers** are plain JSON numbers. JSON has no integers as far as Godot is
  concerned: every number arrives as a float, and the loader turns every
  value into a float or a Color before any code sees it. So `2` and `2.0` are
  the same, and no code compares raw JSON arrays.
- **Colours** are display (sRGB) components as a `Color()` constant takes
  them, `[r, g, b]` (or `[r, g, b, a]`), or `"#rrggbb"`. Use the array form to
  keep a value exact. A hex colour rounds to 1/255.
- **Renderer suffixes.** Any number or colour key may also be written with
  `_forward` or `_compat`. In Forward+ `<key>_forward` wins over `<key>`. In
  the compatibility renderer (the OpenGL fallback, and CI's rendered tests)
  `<key>_compat` wins over `<key>`. The bare key applies in both. The tables
  (`grass.layers`, `water.decode_albedo`, the `foliage` lists) take no suffix.

## Sections

| Section | Key | What it does | Default |
|---|---|---|---|
| `grade` | `exposure`, `saturation`, `background` | Multiplies the grade's exposure and saturation (`LookGrade`), and `background` what the camera sees behind the world (its sky or background colour: an interior's void an exposure trim would lift, the Ssarathi archive's). **Only for a map never streamed beside another** (an island, a tutorial map, an instance): a trim changes when the active map changes, which on the continent would step at every crossing. A continent region's `grade` section is ignored, with a warning. | 1 |
| `ground` | `path_luma`, `path_tint` (colour), `path_chroma`, `verge_value_green`, `verge_value_earth`, `verge_saturation`, `verge_green_red` | Trims the painted ground (`LookGround._set_paint`); baked into a chunk's materials when it loads. On the continent they fade into each neighbour's across the border (`LookBorders`, see the rules below). | Forward+: `GROUND_FORWARD`, else the `PATH_*` / `VERGE_*` constants |
| `ground` | `deck_path` (0..1), `deck_road_colour` (colour), `deck_tint` ([r, g, b] multiplier), `deck_chroma`, `deck_grain` | How much of a road the region's `Walk_` decks are painted as. At 0 a deck is the region's own ground: it keeps its own colour whatever its hue, times `deck_tint` (a multiplier on its linear colour, not a display colour) at `deck_chroma`, and has no road edging (the tutorial maps' courts, which are decks from wall to wall). The grade warms and greys a kept court, so `deck_tint` is solved against develop's colour. `deck_road_colour` is the vertex colour (display sRGB) a deck carries where it is road: that part is painted as a road again (Reedway's cart tracks), within `DECK_ROAD_TOLERANCE`. `deck_grain` scales the kept deck's texture grain about its mean (Bellwatch's and Stillglass's flagstones). A tint solved in one renderer must carry that renderer's suffix (`deck_tint_forward`): bare, it ran in the compatibility renderer too and turned Echo Court purple. | 1, none, [1, 1, 1], 1, 1 |
| `ground` | `path_detail`, `path_fine` | The power a road's texture grain is raised to and its fine mottle (`PATH_DETAIL`, `PATH_FINE`): lower flattens a texture's dark flecks (Mirrorhold's honey sand, Reedway's tracks). **Not faded across a border**, so on the continent render the border shots after changing them. | 1.8, 0.12 |
| `ground` | `meadow_value`, `meadow_chroma`, `meadow_tint` ([r, g, b] multiplier) | A green meadow patch (`LookGround.is_meadow`) keeps its own colour times this value and tint (a multiplier on its linear colour, as `deck_tint` is), at this chroma: the Grey Moors' pale moor grass sits under its roads at 0.62; sw_isle's lawns take a greener tint because their own olive came out hue 60-64. | `MEADOW_VALUE`, `MEADOW_CHROMA(_FORWARD)`, white |
| `ground` | `rock_value` | Bare rock patches (`LookGround.is_rock`: Whitehorn's granite, the Barrens' lilac scree) are drawn solid in their own colour times this. | `ROCK_VALUE` (1) |
| `ground` | `keep_patches` (list of strings) | Decorative inlays: a blended authored patch whose material name (the continent exporter writes `authored_<region>_<patch id>`) contains one of these words is drawn solid in its own colour, at the region's `props.keep_chroma`, instead of being classed by its tint (`LookGround.is_kept_patch`). sw_isle's arrival rosette, a cobalt ring round a gilt centre on the limestone plaza, was a yard and a sand glaze by tint, and a yard inside pale paving is worn into its cobble: a brown stain at the spawn. | none |
| `ground` | `paving_tint` (colour multiplier) | The surface tint pale paving patches (`LookGround.is_paving`) are drawn at, in place of `PAVING_SURFACE_TINT`: sw_isle's limestone courts and avenue read near-white (L0.72 s0.20) at the shared one. | `PAVING_SURFACE_TINT` |
| `ground` | `class_textures` (table: slot to name) | Detail textures laid over the region's ground by class (`LookGround.class_slot`). The slots are `deck` (worn walk decks), `paving`, `sand` and `meadow`; the names are those in `LookProfile.CLASS_TEXTURES` (`packed_earth`, `flagstone`, `beach_sand`, files in `../textures/`). Mapped in continent metres and rescaled to the source texture's mean colour, so the palette and paint classes are unchanged and only structure changes. Kept patches and rock keep their own texture. The Landfall isles name all three (map visuals audit, 2026-10-17): their roads, sand and soil were one tinted texture, and their paving was wall masonry. No table suffix. | none |
| `ground` | `verge_grain_steep` (0..1) | How much of the texture's grain a steep face (up under 0.55, faded in to 0.8) keeps, of the paint's whole albedo and its verge alike: a planar-mapped detail tile streaks down a cliff, so sw_isle calms it on its gorge walls. | 1 |
| `ground` | `verge_grain` (0..1) | How much of its texture's grain the painted verge keeps (`look_verge_grain`): a region whose base is one vertex colour per 2 m under a detail tile (sw_isle) needs all of it, or its ground reads as smooth vertex colour. | `VERGE_GRAIN` (0.55) |
| `grass` | `root`, `tip` (colours), `value` | The region's grass palette, root to tip, and its value trim, measured against its painted ground (tufts at 0.9-1.05 of the ground under them). Any of the three gives the region its own palette slot; missing colours come from `GRASS_PALETTE_DEFAULT`. | `GRASS_PALETTE_DEFAULT`, value 1 |
| `grass` | `layers` (table word to 0..1) | How grassy a biome layer is, by a word in its texture's file name, read before `GRASS_LAYER_WORDS` for this region's biome blends only. | `GRASS_LAYER_WORDS` |
| `grass` | `open` (0..1) | How grassy the region's ground is where no biome blend covers it (the Sunmane Steppe's opaque authored base). Green meadow patches grow grass whatever this says (`GRASS_PATCH_GREEN`). | 1 |
| `grass` | `meadow` (0..1) | How grassy its green meadow patches are, whatever lies under them (the Sunmane pastures carry half the beds, 0.5). | 1 |
| `grass` | `open_green` (0..1) | Where no biome blend covers the terrain, how far open ground's grass follows its vertex colour's green (`LookGrassBeds.open_green`, `GRASS_OPEN_GREEN`): at 1, sand, grey rock and earth grow none and a lawn green all of `open`. sw_isle's opaque base also covers its beaches and cut faces, which grew tufts at `grass.open`. | 0 (off) |
| `sky` | `top`, `horizon` (colours) | The sky painted over a map that **declares no sky** (`LookSky`). A map with its own `environment.sky` ignores this. | `SKY_FALLBACK` (the binder's 3d7ec2 / bcc9cd) |
| `sky` | `clear` (0..1) | How far the painted sky is taken towards the bright clear day (a deep blue zenith, warm haze, white cumulus) on a map **outside the continent**. Unset, `LookSky.clearness` judges it from the declared zenith: a saturated blue is clear, a violet dusk (the Amethyst Barrens) or a grey overcast (the Grey Moors) keeps its own colours, with clouds in its horizon's colour. On the continent it is always judged from the declared (border-blended) sky, so it never steps at a crossing. | judged from the zenith |
| `sky` | `paint` (0 or 1) | 0 leaves the map's own sky and fog alone (`LookProfile.sky_painted`): for a sunlit interior whose void is meant dark (the Sunmane wind caves, the Ssarathi archive, the Drowned Crown). The grade still runs. | 1 |
| `sky` | `haze_warmth` (0..1) | How far the far haze is warmed towards `SKY_WARM` (`LookSky.sky_colours`), read from the lighting manifest's region (a chunk reads its region's file): sw_isle's blue lagoon fog read cream at the shared 0.45. | `SKY_HAZE_WARMTH` |
| `water` | `inland_tint` (colour) | Forward+ only: the display multiplier the rivers, pools and small seas drawn by a StandardMaterial3D take (`LookGround.decode_inland_water`), on a map **outside the continent**; the continent has one, `INLAND_WATER_TINT`, since its rivers cross the borders. | `INLAND_WATER_TINT` |
| `water` | `decode_albedo` (table shader path to value) | Forward+ only: a sea shader whose colours were picked in the compatibility renderer is told to decode them to linear albedo, at this value (`LookGround.decode_water`). Only maps outside the continent run it; the continent's own sea is decoded for every region at `CONTINENT_SEA_VALUE`. | none |
| `water` | `sea_value`, `sea_chroma`, `sea_tint` ([r, g, b] multiplier) | Forward+ only: the continent sea's decode (`LookGround.decode_continent_sea`) for this region's roots, in place of `CONTINENT_SEA_VALUE` and `CONTINENT_SEA_CHROMA`, its decoded linear colour times `sea_tint`. Only for a region whose sea meets no other region's (the sea is one surface across the old continent's borders): sw_isle, an island in the continent-v2 frame, takes a lagoon turquoise where the shared value drew navy-teal. | `CONTINENT_SEA_VALUE`, `CONTINENT_SEA_CHROMA`, white |
| `foliage` | `crown_materials`, `tree_words`, `shrub_words`, `untamed_words`, `plain_words` (lists of strings) | Extends `CROWN_MATERIALS`, `KIT_TREE_WORDS`, `KIT_SHRUB_WORDS`, `KIT_UNTAMED_WORDS` and `KIT_NOT_FOLIAGE_WORDS` for this region's roots (`LookFoliage`). A crown material is an authored leaf material's name, compared exactly. The words are matched against the hyphen-separated words of a `kit-...` node name; the plain words (raft, boat, cart, and a region's own) always win: such a kit piece keeps its own material instead of being painted as a crown (sw_isle's clipped hedges and flower shrubs). **Continent regions only**: the foliage layer does not run on any other map, so this section is never read there. | the lists in `look_profile.gd` |
| `foliage` | `crown_tint` ([r, g, b] multiplier) | The region's tree crowns (authored canopies and kit trees, not shrubs or trunks) take this tint, a multiplier on the painted crown's linear colour as `deck_tint` is (`LookFoliage.crown_tint_at`, `painted_foliage_body.gdshaderinc` `look_crown_tint`); a runtime harvest node whose model is a tree takes it too. On the twelve-territory continent it fades into each neighbour's across the border as the ground trims do (`LookBorders`); the continent-v2 isles have no blended borders, so an isle's tint stands to its edge. Owner-approved 2026-10-14 (harvest audit B4); no file sets it yet. **Continent regions only.** | white (no change) |
| `props` | `keep_words` (list of strings), `keep_chroma`, `keep_tint` (colour) | The region's signature materials, by a word of their material's name (lower case, contained): their albedo and emission chroma is scaled by `keep_chroma` before the grade greys it (`LookFoliage.keep_chroma`, look_chroma_standard), the Amethyst Barrens' crystals, Ssarathi's and Verdant's jade, the Drowned Crown's mosaic. `keep_tint` multiplies their tint as well, where a warm key has to be turned back rather than a grey. | none, `KEEP_CHROMA(_FORWARD)`, white |
| `props` | `hole_words` (list of strings) | Landmarks that keep a hole round the player when they fade, never vanishing whole (`LookFade.mode_of`): a word contained in the occluding mesh's node name (lower case; the continent exporter names a kit piece's mesh after its model). Read from the bound map's file as it binds (`LookFade.bind`). A named landmark still vanishes when its box covers more than `FADE_NAMED_HOLE_MAX_COVERAGE` (0.95) of the view (its box reaches behind the camera or fills the frame): from the camera's low limit behind the 32 m keep a hole left the frame one wall. sw_isle's palace keep vanished from its own town's view at the player's maximum zoom, and its west gatehouse left a wall stub and a floating floor slab while the player stood in the gate passage. | none |

## Rules learned on the pilot

- A **continent region's ground trims and grass palette fade into each
  neighbour's across the border** (`LookBorders`): on the border line the two
  meet at their mean, and each is wholly its own `BORDER_FEATHER_METRES`
  (24 m) inside. Baked at the chunk's edge instead, a trim on ground that runs
  on unchanged into the neighbour drew the border as a straight or
  cell-stepped line (Four Gates' old verge trims across the south gate field,
  13 levels; Ssarathi's laterite road against Verdant's cream), and the
  migration's region agents dropped their own roads to avoid it. A region may
  now keep its own roads and verge; still render a shot across each border,
  because a big difference reads as a change of country over about 50 m.
  Renderer-wide changes still belong in `GROUND_FORWARD`. The borders come
  from the ownership polygons in the regions' manifests
  (`continentGeography.ownershipPolygon`), read once.
- **Grass palettes are per region, not per chunk.** The shader holds
  `GRASS_PALETTE_SLOTS` (32) palettes. Slot 0 is the default. A region with
  its own palette takes the next slot the first time the client meets it,
  and keeps it.
- The **authored leaf materials** (`foliage_amber`, `_rust`, `_gold`,
  `undergrowth`) are the continent exporter's own and shared by many
  regions, so they stay in `CROWN_MATERIALS`. Add a region's other leaf
  materials, such as `foliage_green`, `foliage_dead` or
  `fg_foliage_broadleaf`, in its `foliage.crown_materials`. Keep in mind
  that a material shared with a neighbour is painted there only if the
  neighbour's file lists it too.
- **Interiors are never graded or painted**, unless their manifest declares
  an enabled sun. A handful do: `sunmane_insides`, `crownwater_insides`,
  `ssarathi_insides`, and the Sunmane gauntlet. On every interior (no enabled
  sun, or an `asset.interiorClass`) occluders fade as develop fades them
  (`LookFade.bind`), because a ceiling kept solid round the player's hole
  blacked out the room.
- **What a patch is, is decided by its tint** (`LookGround.is_paving`,
  `is_cobble`, `sand_tint`, `stone_tint`): pale paving and cobble must be warm
  or neutral stone, so pale grass (`#b8eba8`), granite (`#b3b5bf`) and snow
  are not; the life passes' beach sand (`#fff5d1`) is a glaze, not paving,
  and grows no grass; a green meadow patch (`LookProfile.green_tint`, the one
  test the paint, the stone test and the grass all ask) is painted solid in
  its own green (`is_meadow`, `meadow_value`) and grows grass whatever the
  biome beneath; a pale grey patch that is not stone paving (granite, lilac
  scree) is bare rock, solid in its own colour (`is_rock`). The patch
  textures are content-addressed, so their names cannot say it.
- **A material is water by a word of its name** (`LookGround.water_named`:
  `water` or `sea` between underscores), never by a substring: Crownwater's
  materials all contain "water", and taken for rivers its road decks were
  tinted and never painted.

## Seeing what the generic classifier does with a map

`tests/look/probe_look_classes.gd` loads maps as the client does, with the
look on, and writes JSON describing what happened to each surface:

- which ground surfaces were painted, and as what: terrain, biome verge,
  pale paving, worn cobble, a glaze patch, or a road deck;
- which ground surfaces were left alone, and why: a bridge's timber, a water
  shader, a threshold, and so on;
- how grassy each biome layer texture counts;
- what the grass beds grew;
- which foliage-looking meshes were painted as crowns and which were not,
  with the reason;
- the water materials;
- points on the painted roads, for placing survey shots.

Read it before writing a region file. Anything listed as "no crown material
or kit word" is what `foliage` can add, and a biome texture that "matched
default" is what `grass.layers` can weigh. Run it like this:

```
ELORIA_PROBE_TARGETS=targets.json ELORIA_INVENTORY_OUT=out.json ELORIA_NO_MAP_CACHE=1 \
  Godot --audio-driver Dummy --path godot-client --script res://tests/look/probe_look_classes.gd
```

`targets.json` is `[{"map": "<registry id>", "x": 0, "z": 0}]`. The point is
where the actor stands, in the map's own frame.

## The pilot files

| File | What it holds |
|---|---|
| `lantern_reach.json` | Grade trims (island), ground trims, coastal grass palette, fallback sky, sea decode |
| `four_gates.json` | Grass palette only; its old ground trims became `GROUND_FORWARD` |
| `amberwood.json` | Ground trims (dim ochre roads, a lighter earthy verge), straw grass palette |

They reproduce, value for value, the constants they replaced
(`MAP_TRIMS`, `GROUND_TRIMS`, `GRASS_PALETTES`, `SKY_FALLBACKS` and
`DISPLAY_ALBEDO_WATER` in `look_profile.gd` before 2026-09-30).
`test_look_regions.gd` pins those values.
