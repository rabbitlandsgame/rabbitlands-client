class_name LookProfile
extends RefCounted
## The frame-level look pass: its switch, the graphics quality, and every
## constant it tunes.
##
## The pass is the client's look: it is on unless the player turns "Painted
## look" off in the settings window, or the client was started with
## ELORIA_LOOK=0, and that one switch (`enabled`) is the whole of its off path.
## Every layer asks `enabled()` first and does nothing when it is false, which
## gives back the frames the client drew before the pass (the look-off renders
## match them within run-to-run noise), for a player who prefers them, an A/B
## capture, or to rule the pass out when a frame looks wrong. The switch works
## live: LookSwitch takes the pass off, or puts it back on, everything already
## loaded. The graphics quality (`quality`, QUALITY_PRESETS) sets what the
## shadows and the pass's costlier layers draw. Forward+ is the renderer the
## pass is tuned for; the compatibility renderer (the OpenGL fallback, and
## CI's rendered tests) keeps its own trims wherever the two light differently.
##
## The constants live here, not beside the code that uses them, so the whole
## look can be read, compared and retuned in one place. They are every map's
## defaults: what a map or region does differently (its grade and ground
## trims, grass palette, fallback sky, sea, extra foliage names) lives in its
## own file, regions/<id>.json, read through `region` and the accessors below
## it (see regions/README.md), so one region can be retuned without touching
## another's. They are tuned for the
## isometric camera's default framing (pitch -60, 26 m away). There four
## fifths of the frame is ground, so the grade matters more than the sky; only
## the low views (pitch -30 and -20) reach the horizon.

## The environment variable that overrides the player's switch for a
## developer or a test: "0" forces the pass off and "1" on, whatever the
## settings file says; unset, or any other value, leaves the player's choice.
const ENABLE_VARIABLE := "ELORIA_LOOK"
## The switch before the player has touched it: on.
const LOOK_DEFAULT := true
## On every material the pass puts in place of another (a painted ground or
## crown, a decoded sea or river, a kept signature colour): the material it
## stands in for, which LookSwitch puts back when the look is switched off.
const SOURCE_META := &"look_source"
## Picks another tone curve for an A/B capture ("agx", "aces" or "filmic").
## Unset, the pass uses TONEMAP_CURVE.
const TONEMAP_VARIABLE := "ELORIA_LOOK_TONEMAP"

# --- Graphics quality ----------------------------------------------------------

## The settings window's "Graphics quality". HIGH draws everything, exactly as
## the client drew before the setting existed; the lower two give up what costs
## most for what it adds to a frame (QUALITY_PRESETS). ActorRenderQuality uses
## the same enum order for mesh LOD, actor shadows and cape cloth, so this one
## player-facing setting controls world and character cost together.
enum Quality { LOW, MEDIUM, HIGH }
## How each quality is written in the settings file ([graphics] quality) and in
## QUALITY_VARIABLE, by Quality.
const QUALITY_NAMES: Array[String] = ["low", "medium", "high"]
const QUALITY_DEFAULT := Quality.HIGH
## Overrides the player's quality for a developer or a test ("low", "medium" or
## "high"; anything else leaves the player's choice).
const QUALITY_VARIABLE := "ELORIA_LOOK_QUALITY"
## Overrides single entries of the quality in use ("ssao=0,shadow_splits=2"),
## for measuring what each one costs and what it adds to a frame.
const QUALITY_TRIM_VARIABLE := "ELORIA_LOOK_QUALITY_TRIM"
## What each quality draws. The shadows are the directional sun's: its
## cascades (`shadow_splits`, 1, 2 or 4), the shadow atlas's side in pixels
## (`shadow_atlas`) and the filter its edges are sampled with (`shadow_filter`,
## RenderingServer.ShadowQuality, from 0 hard to 5 ultra). They apply whether
## the look is on or off: they are the renderer's, and with the look off HIGH
## is develop's own frame. The rest is the look's and applies only while it is
## on: SSAO and SSIL (Forward+ only), glow, and the grass beds (`grass`).
##
## HIGH must stay the renderer's defaults (Godot's directional shadow atlas of
## 4096 at 16 bits, soft-low filtering, four cascades; test_look_settings.gd
## checks it against the project settings) and the pass as tuned.
##
## Measured, not guessed: each entry was taken away from HIGH on its own
## (QUALITY_TRIM_VARIABLE), over the pilot's eight gameplay and low views in
## Forward+ at 1440x900, uncapped, on an RTX 5080 laptop GPU, where HIGH's 3D
## view costs 1.39 ms of GPU time (the review's settings notes have the
## tables). Of that, SSIL is 0.18 ms (13 %), a 4096 atlas over a 2048 one
## 0.18 ms (13 %), the grass 0.18 ms (13 %, and a tenth of the primitives),
## glow 0.06, SSAO 0.05 and soft-low over hard filtering 0.03; four cascades
## over two cost 0.04 ms of GPU but a fifth of the draw calls and a quarter of
## the primitives, which is what a slower machine's CPU and vertex work pay.
## Two things were measured and left out: thinning the grass (0.82 of its
## reach at 0.7 of its density) halved its tufts but saved 0.02 ms, a tenth of
## what the whole bed costs, so MEDIUM keeps the full beds; and the painted
## sky's clouds cost nothing measurable even in the -15 degree horizon views,
## so every quality keeps them.
##
## MEDIUM gives up SSIL, the look's costliest pass and its subtlest (bounce
## light in the shade), and two of the cascades: about a sixth of the GPU
## time, a fifth of the draw calls, a quarter of the primitives. LOW keeps the
## grade, the painted ground and crowns and the painted sky, and gives up
## every screen-space pass, the glow and the grass, and draws the shadows into
## a 2048 atlas with hard edges: cheaper than the look off at HIGH.
const QUALITY_PRESETS := {
	Quality.LOW: {"shadow_splits": 2, "shadow_atlas": 2048, "shadow_filter": 0,
		"ssao": false, "ssil": false, "glow": false, "grass": false},
	Quality.MEDIUM: {"shadow_splits": 2, "shadow_atlas": 4096, "shadow_filter": 2,
		"ssao": true, "ssil": false, "glow": true, "grass": true},
	Quality.HIGH: {"shadow_splits": 4, "shadow_atlas": 4096, "shadow_filter": 2,
		"ssao": true, "ssil": true, "glow": true, "grass": true},
}
## The shadow atlas's depth, which no quality changes (Godot's default).
const SHADOW_ATLAS_16_BITS := true

# --- Grade (layer L1) --------------------------------------------------------

## The tone curve every outdoor map is graded through. The manifests disagree:
## Lantern Reach declares Filmic with a white of 1, which clips every bright
## channel and is why its grass and trail read neon; Four Gates declares
## Filmic with a white of 9, which folds its pale stone into flat grey; and
## Amberwood declares nothing, so it falls back to a linear curve that leaves
## its ground dull and dark. One curve gives the three places one exposure
## language, and the continent's seams need one anyway: the lighting manifest
## blends between neighbours every 100 ms, but the curve is only chosen at
## bind, so a player who walked in from Four Gates saw Amberwood through Four
## Gates' curve and one who logged in there saw it linear.
##
## AgX, from a compatibility-renderer A/B at matched mid-grey: ACES had the
## most contrast but blew Four Gates' paving out (luminance 167 against 144)
## and crushed 3 % of Lantern Reach's low view to black; Filmic kept Lantern
## Reach's trail neon orange; AgX rolled the pale stone off softly, turned the
## trail to sand and the red maples towards copper, and crushed nothing.
const TONEMAP_CURVE := "agx"
## Each curve with the exposure that puts mid-grey near the same display
## value, so an A/B compares the curves' shapes rather than their brightness.
## AgX's contrast is its own; the other two shape contrast by their white.
## AgX carries all of the grade's contrast (see CONTRAST): 1.35 against its
## default 1.25 opens Amberwood's value spread from 26 to 33. Forward+ rolls
## the highlights off harder than the compatibility renderer (the brightest
## tenth of a Four Gates or Lantern Reach frame 15-25 levels lower at the same
## mid-grey), which left its frames flat (value spread 24-37 against 40-45);
## it takes 1.65, with SATURATION_FORWARD taking back the chroma a stronger
## per-channel curve adds and TOE_LIFT the blacks it deepens. AgX's white
## (agx_white) was tried as the highlight lever and changed nothing measurable.
const TONEMAP_CURVES := {
	"agx": {"mode": Environment.TONE_MAPPER_AGX, "exposure": 1.15,
		"white": 1.0, "agx_white": 16.29, "agx_contrast": 1.35,
		"agx_contrast_forward": 1.65},
	"aces": {"mode": Environment.TONE_MAPPER_ACES, "exposure": 1.0,
		"white": 3.0},
	"filmic": {"mode": Environment.TONE_MAPPER_FILMIC, "exposure": 1.15,
		"white": 4.0},
}

## The adjustment's own contrast, left neutral. It is a straight line through
## display mid-grey applied to each channel after the curve, so it drives the
## smallest channel of a dark saturated colour to zero: at 1.08 the dark side
## of the red maples went from (32, 23, 16) to (16, 6, 1) and the navy slate at
## Four Gates' east gate to (2, 12, 25). Even 1.03 crushed 3 % of that frame.
## Raising AgX's own contrast instead gave the same value spread with those
## colours intact, because its curve eases into black rather than clipping.
const CONTRAST := 1.0
## A toe under the curve, drawn after it as a per-channel lookup on display
## values: a display value x below TOE_END is lifted by TOE_LIFT * (1 -
## x / TOE_END)^2, so black itself becomes TOE_LIFT and the lift has run out,
## smoothly, by TOE_END. It keeps the darkest authored colours (the navy slate
## at Four Gates' east gate, the coppice's dark timber and the maples' crimson
## shade, 5-6 % of those frames below luminance 20 once the curve's contrast
## was raised for Forward+) out of black without greying the mid-tones the
## contrast is for. 0 turns it off. At 0.045 up to 0.2 the shade was still
## crushed where dark ground turns from the sun: the Grey Moors' steep peat
## facets at gm_wild came out (22, 19, 17), 12 % of the frame below luminance
## 20 against develop's 0.1 %, and Cinderbank's timber crates black; the
## shade is meant cool, not black.
const TOE_LIFT := 0.06
const TOE_END := 0.28
## Saturation for a map that declares none. Below 1 because the tone curve adds
## chroma: AgX's contrast acts on each channel apart, and at 1.0 it took
## Amberwood's orange leaf litter and Four Gates' lime grass most of the way to
## neon. At 0.9 Amberwood still measured 0.60 (the reference frames average
## 0.51). Forward+ takes less for its stronger curve (AGX contrast 1.65): at
## 0.8 there Lantern Reach measured 0.75 and Amberwood 0.57.
const SATURATION := 0.86
const SATURATION_FORWARD := 0.69
## A region's signature materials (its file's `props.keep_words`: crystals,
## jade) have their chroma scaled by this before the grade takes it back
## (LookFoliage.keep_chroma), about the inverse of the saturation above, so
## they land near the colour develop drew them.
const KEEP_CHROMA := 1.15
const KEEP_CHROMA_FORWARD := 1.45
## How much of a manifest's own saturation boost survives. Amberwood declares
## 1.3, which has never been visible because nothing enabled the adjustment;
## at full strength it turns the red maple kit neon. A third of it warms the
## autumn palette without that.
const SATURATION_BOOST_SHARE := 0.33

## The key light is warmed, not re-aimed: the continent's regions share one
## sun heading and a crossing must not turn it. Multiplied into whatever colour
## the manifest and the hour give it. It turns Four Gates' lime grass towards
## chartreuse (hue 81 to 69-71 degrees); holding its blue back to 0.97 fixed
## little of that and cooled every frame (red minus blue down 9 levels) and
## greyed the roads, so the grass is turned back in the ground paint instead
## (LookProfile.VERGE_GREEN_RED).
const SUN_WARMTH := Color(1.0, 0.98, 0.94)
## Forward+ lights in linear light and adds bounce (SSIL) from warm ground, so
## the same warmth landed its roads rose (hue 17-29 degrees against 43 in the
## compatibility renderer) and its grass mustard. It takes a milder warmth.
const SUN_WARMTH_FORWARD := Color(1.0, 0.99, 0.97)
## A little more key than the manifests give, and no more: at 1.1 the first
## capture bleached Four Gates' pale stone without shading anything better.
const SUN_ENERGY_SCALE := 1.04

## Shadows read cool against a warm key. Every outdoor manifest's ambient is
## lerped this far towards AMBIENT_COOL.
const AMBIENT_COOL := Color(0.56, 0.68, 0.92)
const AMBIENT_COOL_SHARE := 0.4
## On a map lit by its sky the ambient colour is inert: the manifests declare a
## cool grey-blue ambient but no `skyContribution`, so the sky is the whole
## ambient. Amberwood's sky has a warm grey horizon over a brown ground, which
## tints its shade brown. Keeping this share of the sky lets the cool colour
## reach the shade.
const AMBIENT_SKY_SHARE := 0.75
## The fill keeps its strength. Cutting it to 0.88 for contrast moved the
## captures' value spread by less than one step and only darkened the shade
## that SSAO already darkens in Forward+; the tone curve does that job better.
const AMBIENT_ENERGY_SCALE := 1.0

## A map's own trims on the exposure and saturation above live in its region
## file's `grade` section (see REGIONS_DIRECTORY; Lantern Reach's is the only
## one). Only a map that is never streamed beside another may have them: a
## trim changes the moment the active map does, which on the continent would
## be a visible step at every crossing, so the continent's regions share one
## grade and `map_trim` ignores a continent region's `grade` section.
## Forward+ draws the continent darker than the compatibility renderer does
## (Four Gates luminance 92 against 123, Amberwood 58 against 72, mostly its
## SSAO and linear lighting), so it takes this much more exposure everywhere.
## A per-map trim cannot close the gap on the continent, whose regions share
## one grade (Amberwood streams beside Four Gates); Lantern Reach's own trim
## (regions/lantern_reach.json) is divided by it. 1.65 (it was 1.12, then 1.42) also pays for the stronger
## Forward+ curve, which darkens everything below its pivot.
const FORWARD_EXPOSURE := 1.65

## Depth fog instead of the manifests' exponential haze. An exponential curve
## at the densities declared (0.0001-0.0007) is either invisible or a uniform
## wash, because a -60 degree view spans only about 20-40 m of depth. Depth fog
## leaves the player's surroundings clear and gathers only beyond them, where
## the low views reach the world's edge. It only replaces fog a manifest
## already enables. The sky layer (L5) then re-shapes it as the horizon haze
## (HAZE_BEGIN and after) on every map whose sky it paints.
const FOG_BEGIN := 38.0
const FOG_END := 320.0
const FOG_CURVE := 1.4
## The haze at FOG_END. A map that declares denser exponential fog gets more
## of it, up to FOG_DENSITY_MAX, so Amberwood stays mistier than the city.
const FOG_DENSITY := 0.3
const FOG_DENSITY_PER_DECLARED := 250.0
const FOG_DENSITY_MAX := 0.5
## How much of the distant haze takes the sky's colour rather than the fog's,
## so the far ground melts into the horizon instead of into grey.
const FOG_AERIAL_PERSPECTIVE := 0.55
const FOG_SKY_AFFECT := 0.25

## Contact shade under eaves, trees and props. Forward+ only (see
## `screen_space_effects()`), so they cost the compatibility renderer nothing.
## At 1.4 the Forward+ frames' shade under eaves and crowns went a notch too
## dark once the curve's contrast was raised.
const SSAO_RADIUS := 1.6
const SSAO_INTENSITY := 1.1
const SSAO_POWER := 1.4
const SSAO_DETAIL := 0.5
## Some occlusion reaches direct light too, or noon AO vanishes in the sun.
## More than this blacked out the coppice's eaves.
const SSAO_LIGHT_AFFECT := 0.1
## ELORIA_LOOK_SSAO=0 turns it off, for measuring its cost and its share of a
## frame's shade (as ELORIA_LOOK_SSIL does SSIL's).
const SSAO_VARIABLE := "ELORIA_LOOK_SSAO"
## Bounce light from sunlit ground into the shade beside it. Forward+ only.
## ELORIA_LOOK_SSIL=0 turns it off, for measuring what it costs (it is the
## grade's most expensive screen-space pass; see the review's cost notes) or
## for a slower GPU until the client has a graphics-quality setting.
const SSIL_RADIUS := 4.0
const SSIL_INTENSITY := 0.6
const SSIL_VARIABLE := "ELORIA_LOOK_SSIL"

## Only what is already brighter than white glows, and softly: sunlit pale
## stone and water glints, not the whole frame.
const GLOW_INTENSITY := 0.35
const GLOW_STRENGTH := 0.9
const GLOW_BLOOM := 0.0
const GLOW_HDR_THRESHOLD := 0.9
const GLOW_BLEND_MODE := Environment.GLOW_BLEND_MODE_SCREEN

# --- Ground (layer L2) -------------------------------------------------------

## The painted ground's value hierarchy. The reference frames read because
## their roads are the palest thing on the ground (a path is 1.25-1.72 times
## the luminance of the grass beside it); Four Gates' roads were darker than
## the grass they cross (0.5) and Amberwood's matched their floor (1.0). The
## values below act on linear albedo, before the light and the AgX curve, and
## the grade pulls chroma down by about 14 %, so they are authored a little
## richer than they would look in a paint program.
##
## A path is repainted rather than lifted: its texture's grain is kept, but
## its value and colour are set outright, so a road reads the same wherever
## the exporter's worn tint happens to sit. The worn-road decks are a
## saturated orange-brown of luminance 0.056 (the shared ground texture under
## the worn tint #997a4f); lifting that colour kept its red hue, which Forward+
## lit rose and mauve and the compatibility renderer grey. PATH_LUMA is the
## albedo luminance a road is painted at; a region whose verge is much darker
## than Four Gates' grass trims it (its region file's `ground` section, see
## `ground_value`), because the path/ground
## ratio is what the eye reads, and 0.24 over Amberwood's floor (0.04) made its
## paths cream decals 2.2-2.4 times the floor's luminance. Never more than
## PATH_LIFT_MAX times the source.
const PATH_LUMA := 0.24
const PATH_LIFT_MAX := 6.0
## The hue a road is painted in, as an sRGB colour whose own brightness is
## ignored: warm dust and pale stone at about 36 degrees, not the red the worn
## tint lifts to. PATH_CHROMA is how much of this colour's chroma it keeps (1
## all of it, 0 grey).
const PATH_TINT := Color(0.82, 0.68, 0.52)
const PATH_CHROMA := 1.0
## The compatibility renderer lights its gamma-encoded albedo, which washes a
## painted colour's chroma out (the same road measured sat 0.24-0.34 there and
## 0.4 in Forward+), so painted tints carry this much more chroma on it.
const COMPAT_CHROMA := 1.2
## A road keeps its texture's grain, raised to this power, so a worn track
## reads as trodden stones and dust rather than as a poured surface (internal
## luminance spread 9-18 against about 33 on the reference roads).
const PATH_DETAIL := 1.8
## And a fine mottle the size of a cart's width: this many metres across,
## this far either side of the mean.
const PATH_FINE_METRES := 1.5
const PATH_FINE := 0.12

## A road through pale paving (the Four Gates hub square) goes darker than the
## paving instead of lighter: a warm brick-brown cobble about 0.55 of the
## paving's display value, as the reference fountain court lays a warm, darker
## floor under its pale buildings. Lifted like a country road, the hub's
## avenue matched the plaza (168 against 178) and the square lost the dark
## ground its monument stood on; at 0.075 in the road's dusty stone it read as
## a taupe-grey concrete strip (Y 121, saturation 0.2) and the square went
## greige (value spread 35 against develop's 49). ROAD_UNDER_PAVING_TINT is its
## hue (about 22 degrees, display saturation about 0.4 after the grade).
## Paving is recognised by its authored tint (see PAVING_TINT_VALUE); a road
## counts as inside it this many metres in from the paving's bounds, so it
## darkens as it enters the square rather than at a line.
const ROAD_UNDER_PAVING_LUMA := 0.046
const ROAD_UNDER_PAVING_CHROMA := 1.0
const ROAD_UNDER_PAVING_TINT := Color(0.74, 0.52, 0.4)
const PAVING_INSET_METRES := 3.0
## An authored ground patch is pale stone paving when its tint is at least this
## bright and at most this saturated (the Four Gates crystal paving is #ccba9c,
## value 0.8, saturation 0.24). Soil (#ffa85c), leaf litter (#f29e52), the
## east forecourt's worn cobble (#ad9e82, value 0.68) and the yards are not.
const PAVING_TINT_VALUE := 0.75
const PAVING_TINT_SATURATION := 0.3
## The pale paving itself steps down a little and warms, so the square's
## floor is not the brightest thing in it (the paving came out at Y 175 under
## a cream monument base) and the warm cobble reads as part of it. A region
## file may name its own (`ground.paving_tint`): sw_isle's limestone courts
## read near-white at this one.
const PAVING_SURFACE_TINT := Color(0.87, 0.83, 0.75)
## A patch at least this bright (display value) and at most this saturated is
## worn cobble or stone (the east gate's forecourt, #ad9e82): drawn solid, not
## as a PATCH_OPACITY glaze, through which the grass beneath tinted its stone
## green-grey. The grass layer keeps cobble bare by the same test
## (GRASS_BARE_PATCH).
const COBBLE_TINT := Vector2(0.6, 0.35)
## Paving and cobble must also be stone by hue: their green may lead their
## red and blue by at most x and their blue lead their red by at most y
## (display values). Judged by value and saturation alone, the regions' other
## pale patches passed as paving: the Grey Moors' pale green moor-grass
## (#b8eba8, 39 patches round its hub) had every road inside its bounds
## painted brick-brown and grew no grass; Whitehorn's granite (#b3b5bf) put a
## dark red-brown smudge on the roads beside its crags; the lilac scree
## scatters and a cave's snow were drawn as paving. The Four Gates plaza
## (#ccba9c), the civic courts (#d1c7ab, #e6e0d1), worn cobble and the
## Sunmane steppe's pale grey-green grain-west patches (#c7dbb8, green ahead
## by 0.08; taken for grass, one was deepened to a dark disc) keep theirs.
const STONE_TINT_LEAD := Vector2(0.1, 0.03)
## A patch at least this bright and at least this saturated (display value,
## saturation) is pale beach sand, #fff5d1: the life passes' sand banks and
## beaches (20 in Manymouth, Westhaven's, Crownwater's and Ssarathi's shores).
## Taken for paving, a road through a bank's bounding box was repainted
## brick-brown (Manymouth's bridge head, Westhaven's quay) and the bank drawn
## as solid cream paving; sand is a glaze over the ground, and bare. The
## sand shares its texture with the Four Gates plaza's paving, so its tint is
## all that tells them apart.
const SAND_TINT := Vector2(0.95, 0.1)
## At most this many paving patches are handed to a root's roads, the largest
## first; a chunk holds two or three.
const PAVING_RECTS_MAX := 8

## The authored ground patches (yards, forecourts, market aprons, and
## Amberwood's leaf litter) keep their own colour and are lifted only a
## little: towards this luminance, by at most YARD_LIFT_MAX. Their albedo runs
## from 0.007 (a dark root margin) to 0.24 (crystal paving); the leaf litter
## is 0.12 and stays exactly the copper the authors gave it. The first pass
## lifted them three times, stripped a sixth of their chroma and warmed them
## like a road, which turned the leaf litter peach and a coppice workyard rust.
const YARD_LUMA := 0.12
const YARD_LIFT_MAX := 2.0
const YARD_SATURATION := 0.9
## A green meadow or pasture patch (LookGround.is_meadow: its tint's green
## leads its red and blue by GRASS_PATCH_GREEN of itself, `green_tint`) is not
## a yard: it keeps its own colour at MEADOW_VALUE (a linear multiplier) and
## MEADOW_CHROMA (MEADOW_CHROMA_FORWARD in Forward+), drawn at MEADOW_OPACITY
## and faded in over its coverage by MEADOW_RIM rather than cut: the
## exporter's weights fall off across most of a meadow (Mirrorhold's hub
## meadow is under 0.42 over half its vertices, Sunmane's pastures dip to 0.1
## inside), and cut at a threshold they drew the earth beneath as pale
## blotches through the grass. Glazed as soil, Sunmane's pastures went khaki
## (hue 58 to 43) and Mirrorhold's hub meadow the scree's grey (saturation
## 0.57 to 0.16). Forward+ lights an already saturated grass texture under a
## green tint into lime: at chroma 1.35 Manymouth's meadow drew (124, 133,
## 25) against develop's (149, 165, 115).
const MEADOW_VALUE := 1.0
const MEADOW_CHROMA := 1.0
const MEADOW_CHROMA_FORWARD := 0.8
const MEADOW_OPACITY := 1.0
const MEADOW_RIM := Vector3(0.14, 0.12, 0.04)
## A patch at least this bright (display value) and at most this saturated,
## and not paving, cobble, sand or green, is bare rock (LookGround.is_rock):
## Whitehorn's granite, the Amethyst Barrens' lilac scree. Drawn solid in its
## own colour times ROCK_VALUE (a region's `ground.rock_value`).
const ROCK_TINT := Vector2(0.5, 0.12)
const ROCK_VALUE := 1.0
## A patch (not paving) is a glaze over the ground beneath rather than a
## sticker: drawn solid over its footprint, the leaf litter under the deep
## grove's player became a saturated orange oval, the brightest shape in a dark
## frame. Its region weights (mean 0.33) say it is meant as a wash.
const PATCH_OPACITY := 0.78
## Ground whose albedo is already pale (paving, sand, the Lantern Reach gold
## trail) is a path's value by itself. Between these two luminances it moves
## from the verge treatment to being left as it is. Not for the biome blend,
## which is verge by definition: Four Gates mixes a pale limestone gravel into
## its grass, and protected as "pale" that grass stayed bright lime.
const PALE_LUMA := Vector2(0.16, 0.3)
## Pale ground in this hue window (sRGB degrees) and at least GOLD_SATURATION
## saturated is gold: Lantern Reach's trail. AgX rolls a bright saturated
## colour off towards white, which turned the island's gold thread to sand
## (241, 202, 81 became 188, 157, 90), so gold is painted a little darker and
## richer, where the curve leaves its chroma alone. The compatibility renderer
## washes painted chroma out and takes more: at 1.5 in both, Forward+ drove
## the trail to 159, 120, 15 while the compatibility renderer landed 201,
## 166, 85.
## After the first pass the trail still read pale sand in the compatibility
## renderer (199, 167, 92) and dull ochre in Forward+ (152, 122, 63), and the
## island lost the coastal gold that was its signature; the reference gold is
## about (215, 170, 60). Both take more chroma, Forward+ at the trail's full
## value (its exposure trim is lower); the compatibility renderer keeps it
## under AgX's highlight roll-off, which pales a brighter gold back to sand.
## Forward+'s stronger curve and lower saturation (SATURATION_FORWARD) paled
## it to straw again (193, 169, 100); it takes chroma 2.1 at value 1.2, which
## with the island's saturation trim lands (207, 170, 85).
const GOLD_HUE := Vector2(35.0, 56.0)
const GOLD_SATURATION := 0.5
const GOLD_VALUE := 1.2
const GOLD_VALUE_COMPAT := 0.78
const GOLD_CHROMA := 2.1
const GOLD_CHROMA_COMPAT := 2.6
## Grass, moss, forest floor: deeper and a little richer, so the paths have
## something to stand out against. Green grass deepens most, towards the
## reference's deep green; earthy verge (Amberwood's olive floor and moss,
## already dark at 0.05) least. Chosen by hue rather than by value: deepening
## bright verge harder, by value, turned a 5 % lighting step at a Four Gates
## chunk seam into a 13 % band, because the albedo there differs by more than
## the light shows. Hue does not change across it. Four Gates' lime fields
## sat at display value 0.6 against the reference greens' 0.33, and at the
## first pass's 0.66 its south gate highway still read no paler than them.
const VERGE_VALUE_GREEN := 0.42
const VERGE_VALUE_EARTH := 0.8
## The biome grass is already a saturated yellow-green (0.15, 0.19, 0.02
## linear), so it takes little extra chroma.
const VERGE_SATURATION := 1.08
## Green verge loses a little red, which turns the biome's yellow-green (hue
## about 70 degrees under the warm key, chartreuse) back towards grass green.
const VERGE_GREEN_RED := 0.84
## A painted mottle on the verge only, finer than the variation below: the
## south gate's field was 64 % of its frame in one flat lime.
const VERGE_FINE_METRES := 4.0
const VERGE_FINE := 0.12
## The verge keeps this share of its texture's grain around the texture's
## mean colour; the painted mottle and variation carry its variety instead.
## Kept whole, the grass texture's fine grain came through the deeper verge
## and the AgX curve as a camouflage mottle, the frame's busiest texture
## after the grass beds (high-frequency energy 15 against 14 here, in the
## south gate's field).
const VERGE_GRAIN := 0.55
## Low-frequency painterly variation in continent space: two octaves of value
## noise, the coarse one this many metres across. It breaks the flat fields
## and the hard edges of repeated texture patches. VARIATION is the value swing
## either side of the mean; VARIATION_HUE the warm/cool shift that goes with
## it (bright patches warmer, dark ones cooler, as sun and shade would).
const VARIATION_METRES := 16.0
const VARIATION := 0.2
const VARIATION_HUE := 0.06
## Paths keep a third of the variation: enough to wear, not enough to blotch.
const PATH_VARIATION_SHARE := 0.35

## Where a walk deck or authored patch ends. The exporter writes each one's
## coverage into its vertex alpha (a road: 0 on the edge, 1 one strip in; a
## patch: its region's weight), which the imported material never read, so on
## develop both end in hard steps along the terrain cells. Honoured as a
## linear ramp it drew 1-3 m airbrushed rims around sharp textures, two styles
## at once. Instead the coverage is cut at a threshold with a narrow smooth
## step (x: threshold, y: half-width of the step) and a noise wobble (z) about
## RIM_NOISE_METRES across, a broken brush edge rather than a feather.
## Roads cut at the middle of their rim strip.
const DECK_RIM := Vector3(0.5, 0.06, 0.1)
## Patches keep their region's footprint as the exporter weighted it: the
## east forecourt's weight is under 0.35 over half its area, which it means as
## grass, and forcing it solid from there turned that grass into cobble.
const PATCH_RIM := Vector3(0.42, 0.06, 0.1)
## Paving keeps almost all of its geometry, as develop draws it: its low
## weights are where two plaza patches meet, and cut there the grass beneath
## showed through the square as a green veil.
const PAVING_RIM := Vector3(0.12, 0.04, 0.05)
const RIM_NOISE_METRES := 0.9
## The cut also wanders in broad lobes (two octaves, the coarse one
## RIM_LOBE_METRES across) and follows its texture's grain. With the fine
## wobble alone, a rectangle's side, an ellipse's arc and a road's shoulder
## read as ruled lines from the game camera (map audit 2026-10-17: Greenlight's
## quay and lighthouse square, Landfall's gate yard). Each class's x moves the
## cut by up to x vertex alpha either way in lobes; y moves it by y per unit of
## relative luminance, so paving ends stone by stone and dark joints go first.
## Neither carries an edge past its authored footprint: the exporter's ramp,
## a road's one rim strip or a patch's blend width, is all there is to move in.
const RIM_LOBE_METRES := 5.0
const DECK_RIM_LOBE := Vector2(0.14, 0.25)
const PATCH_RIM_LOBE := Vector2(0.18, 0.2)
const PAVING_RIM_LOBE := Vector2(0.09, 0.3)
const MEADOW_RIM_LOBE := Vector2(0.12, 0.12)

## Detail textures a region may lay over its ground by class
## (`ground.class_textures`, slot -> name, e.g. {"deck": "packed_earth"}).
## Mapped in continent metres (`metres` per repeat) and rescaled to the source
## texture's mean colour (painted_ground_surface.gdshaderinc), so a region's
## palette and paint classes are unchanged and only the structure is new.
## Generated for the Landfall isles (map audit 2026-10-17), which drew their
## roads, sand, soil and lawns from one mottled ground texture under four
## tints and their paving from wall masonry laid flat; provenance in
## textures/README.md.
const CLASS_TEXTURES := {
	"packed_earth": {"path": "res://src/world/look/textures/packed-earth-path.png", "metres": 3.5},
	"flagstone": {"path": "res://src/world/look/textures/flagstone-paving.png", "metres": 3.2},
	"beach_sand": {"path": "res://src/world/look/textures/beach-sand.png", "metres": 4.0},
}
## The surfaces a class texture can cover: walk decks, pale paving, sand
## glazes and green meadows (LookGround.class_slot). A meadow keeps its own
## texture on the isles: a fine turf at a 4 m repeat averaged to flat green at
## the game camera, losing the mottle the painted look leans on (audit renders,
## 2026-10-17).
const CLASS_TEXTURE_SLOTS := ["deck", "paving", "sand", "meadow"]
## How much of a class texture's own hue survives its recolouring (0: the
## source's mean colour exactly; 1: only its luminance is matched).
const CLASS_TEXTURE_HUE := 0.5
## Every road is edged: on the far side of its rim, where its coverage has
## run out but its geometry has not (vertex alpha from EDGE_BAND_FROM up to the
## rim), whatever lies under it is darkened by EDGE_BAND (value x0.72) - the
## dark verge that frames the reference's roads, and a curb where a road
## meets paving. The band is drawn EDGE_BAND_PUSH_METRES behind its own plane,
## so where two coplanar road decks overlap the other road hides it rather
## than taking a dark line across its middle.
const EDGE_BAND := 0.28
## Where a road runs through pale paving its band is a curb, darker.
const EDGE_BAND_PAVING := 0.45
const EDGE_BAND_FROM := 0.1
const EDGE_BAND_PUSH_METRES := 0.03

## Banks and cliffs darken with slope: from this world-up component of the
## surface normal (about 26 degrees) to this one (about 57), down to
## SLOPE_SHADE of their value. The terrain's facets change slope at straight
## cell edges, so shade that began at 20 degrees drew a gentle field's rise
## as a straight step across the frame (ten levels at the south gate). At 0.72
## from 31 to 53 degrees it stacked on the sun's own falloff: a sunlit
## terrace bank at wh_garden drew a straight-edged dark band, and the Grey
## Moors' shaded facets went black; the light shades a slope already. A bank
## turned towards the sun is spared it altogether (LookGround.sun_heading_of).
const SLOPE_UP := Vector2(0.9, 0.55)
const SLOPE_SHADE := 0.84
## The terrain's worn-road colour is painted as road only where the ground is
## at least this level (world-up normal component, from about 44 degrees of
## slope to 33): the exporter's road tint bleeds up the faces beside a lane,
## and painted as road it laid pale gravel blotches up the crags at
## gm_border_wh.
const ROAD_SLOPE_UP := Vector2(0.72, 0.84)
## The continent exporter paints its worn roads into the terrain's vertex
## colour as this linear colour (0.49, 0.435, 0.315 in sRGB, over the grain
## divisor 0.92). The terrain shader treats vertex colour this close to it,
## relative to its length, as road.
const TERRAIN_ROAD_COLOUR := Color(0.2265, 0.1746, 0.0855)
const TERRAIN_ROAD_TOLERANCE := Vector2(0.12, 0.34)
## A walk deck whose region names the colour its roads carry in its vertex
## colour (`ground.deck_road_colour`, Reedway's cart tracks) finds them within
## this relative distance: tighter than the terrain's, because the ground
## beside them is the same deck in another vertex colour (Reedway's meadow is
## 0.26 from its tracks, which the terrain's tolerance takes for a third road).
const DECK_ROAD_TOLERANCE := Vector2(0.05, 0.15)

## A sea shader whose colours were picked in the compatibility renderer is
## named, with the value its sea is drawn at in Forward+, in its map's region
## file (`water.decode_albedo`, read by LookGround.decode_water): Lantern
## Reach's lantern_water.gdshader is the only one.
##
## The continent's sea (continent_water.gdshader) is the same case and is
## decoded everywhere at this value in Forward+ (LookGround.decode_continent_sea):
## it runs on across every region's border, so it cannot be a region's. Lit as
## linear albedo it drew a milky pale turquoise as bright as the painted roads
## (Ssarathi's shore luminance 110-127 against develop's 51-52, Crownwater's
## harbour and Westhaven's quays the same). At 4 Ssarathi's shore measures
## luminance 51, develop's; 2.5, Lantern Reach's value, left it at 39. A
## region whose sea meets no other region's (sw_isle, an island in the
## continent-v2 frame) may name its own value, chroma and tint
## (`water.sea_value`, `sea_chroma`, `sea_tint`, a multiplier on the decoded
## linear colour).
const CONTINENT_SEA_VALUE := 4.0
## And its chroma after the decode, around its own luminance: decoded whole,
## the small red channel went to nothing and the sea read a saturated teal
## (11, 62, 76 against develop's 37, 72, 87; md_border_cw's frame saturation
## 0.63, over the 0.52 ceiling).
const CONTINENT_SEA_CHROMA := 0.7
## Inland water drawn by a StandardMaterial3D (rivers, canals, lagoons, the
## tutorial islands' seas and pools) is tinted by this display multiplier in
## Forward+ (LookGround.decode_inland_water): value down and red down most,
## so the grade's greying lands it near the cyan develop drew and clearly
## below the painted roads. A map outside the continent may set its own in its
## region file (`water.inland_tint`); the continent has one, since its rivers
## cross the regions' borders.
const INLAND_WATER_TINT := Color(0.55, 0.8, 0.9)

## Forward+ lights the painted ground's linear albedo as linear light, where
## the compatibility renderer lights it display-encoded: the same verge came
## out darker and more mustard (hue 57 against 64 degrees in the south gate's
## field) and the same roads duller. In Forward+ these replace the constants
## above as the defaults every region starts from. They are renderer defaults
## rather than a region's trims because the ground runs on across a region's
## border: tuned as Four Gates' own trims, they drew a straight seam across
## the south gate's field where Four Gates' grass meets its neighbour's.
const GROUND_FORWARD := {"path_luma": 0.27, "verge_value_green": 0.55,
	"verge_green_red": 0.66, "verge_saturation": 0.92}

## A region's own ground trims over the defaults above live in its region
## file's `ground` section (keys: path_luma, path_tint, path_chroma,
## verge_value_green, verge_value_earth, verge_saturation, verge_green_red).
## Unlike a grade trim these are safe on the continent: they are baked into a
## chunk's painted materials when it loads, so they change where the ground
## changes, never when the player crosses it.
##
## Near a border they fade into the neighbour's (LookBorders): baked at a
## chunk's edge, a trim on ground that runs on unchanged into the neighbour
## drew the region's border as a straight or cell-stepped line (Four Gates'
## verge trims across the south gate field, 13 levels; Ssarathi's laterite
## road against Verdant's cream, 128 against 150; a Whitehorn snow trim
## against the same snow in Amberwood's blend), and the migration's region
## agents had to drop their own roads to avoid it. Now a painted material near
## a border blends its trims towards each neighbour's by the signed distance
## to the border: the two meet at their mean on the border line and each is
## wholly its own BORDER_FEATHER_METRES inside. The default framing shows
## about 45 by 35 m of ground, so the blend is spread wider than a frame and
## reads as a change of country rather than as a band. The borders are
## simplified to within BORDER_SIMPLIFY_METRES of the ownership polygons'
## 2 m staircase, and a material takes the BORDER_SEGMENTS_MAX segments and
## BORDER_NEIGHBOURS_MAX neighbours nearest its meshes (a chunk touches one or
## two; a neighbour's whole-region preview more, from farther away).
const BORDER_FEATHER_METRES := 24.0
const BORDER_SIMPLIFY_METRES := 2.0
const BORDER_SEGMENTS_MAX := 32
const BORDER_NEIGHBOURS_MAX := 4

## ELORIA_LOOK_GROUND_DEBUG=1 draws each painted class as a flat colour
## (terrain red, biome blend green, authored patch blue, walk deck magenta),
## =2 its weights (path red, yard green, pale blue) and =3 its reference
## luminance in steps (above 0.08, 0.12, 0.2), for checking what a metric box
## is measuring and what the shader sees.
const GROUND_DEBUG_VARIABLE := "ELORIA_LOOK_GROUND_DEBUG"

# --- Foliage and fade (layer L3) ---------------------------------------------

## What counts as a crown. The authored trees split crown and trunk into
## separate nodes (Tree_<n>_<species>_Canopy / _Wood), and every crown there
## draws with one of these alpha-cut leaf materials; the trunks' bark is never
## painted. The kit's Meshy trees and shrubs are one surface with one atlas
## material for crown and trunk together, so they are recognised by the
## species words in their node names (kit-crimson-maple-3, kit-dark-fir-12)
## and split inside the shader by height (see CROWN_FLOOR).
## These lists are every map's; a region file's `foliage` section adds its
## own names and words to them for that region's roots (`foliage_words`).
## The authored leaf materials are the continent exporter's own and shared by
## many regions (Four Gates, Crownwater, the Grey Moors, Westhaven and
## Mirrorhold draw foliage_amber too), so they are listed here, not per region.
const CROWN_MATERIALS := ["foliage_amber", "foliage_rust", "foliage_gold", "undergrowth"]
## Kit species with a trunk under a crown.
const KIT_TREE_WORDS := ["tree", "maple", "oak", "fir", "pine", "birch", "sapling", "cypress"]
## Kit plants that are foliage from the ground up.
const KIT_SHRUB_WORDS := ["shrub", "hedge", "fern", "undergrowth", "bramble", "bracken", "reed", "juniper"]
## Kit plants whose colour is the point (blossom), so their hue is not tamed.
const KIT_UNTAMED_WORDS := ["flower"]
## Kit props that carry a plant's word but are not plants: checked first, so
## they are never painted as crowns (Manymouth's kit-reed-raft, a 4 m boat,
## was lit, tamed and swayed as a shrub by its word "reed").
const KIT_NOT_FOLIAGE_WORDS := ["raft", "boat", "basket", "cart", "bundle", "thatch"]
## A foliage mesh this much wider than it is tall, and wider than
## CROWN_MERGED_METRES, is many plants merged into one mesh (Lantern Reach's
## wind pines are one 74 m mesh): its bounds say nothing about any one crown,
## so it is left as it is.
const CROWN_MERGED_RATIO := 2.5
const CROWN_MERGED_METRES := 20.0

## Where a kit tree's crown begins, as a fraction of the mesh's height. Below
## it is trunk. Measured by sampling each kit tree's atlas at its vertices: the
## crimson maple's lowest fifth is bark (saturation 0.25, value 0.36) and the
## rest crown (0.8-0.93, 0.71-0.81); the great amber oak, the autumn maple and
## the dark fir split at the same fifth. Saturation alone does not split
## them: the resin-tapped pine's bark is as saturated (0.52) as its needles
## (0.45). Shrubs are crown from the ground up.
const CROWN_FLOOR := 0.2
## The painted top light: a crown's top is warmed and lifted, its underside
## (and the trunk beneath it) cooled and deepened, across the crown's height
## in mesh space, eased by CROWN_LIGHT_POWER (below 1, the light holds most of
## the crown and falls off towards its underside). Linear multipliers on
## albedo, before the sun; the grade adds its own warm key and cool shade on
## top. The first capture (under 0.5, 0.56, 0.68; core 0.62; power 0.8) took
## the dark firs from luminance 83 to 51 and, by adding blue under a red crown,
## turned the crimson maple's shaded side pink. So the value is redistributed
## rather than taken away, and a tamed (warm, saturated) texel's underside
## goes towards CROWN_UNDER_WARM, a deep red-brown, instead of blue.
## Now that the sun falls across the crown as one volume (CROWN_VOLUME) the
## light itself shades the underside, so the painted gradient under it is
## milder than the first pass's 0.6.
const CROWN_TOP := Color(1.16, 1.08, 0.92)
const CROWN_UNDER := Color(0.78, 0.82, 0.9)
const CROWN_UNDER_WARM := Color(0.78, 0.7, 0.68)
const CROWN_LIGHT_POWER := 0.7
## How much of a crown's shading normal is the ellipsoid its box holds rather
## than the leaf card's own. Card by card, the maple read as a heap of
## vermilion cards with dark edges, the reference's trees as a few top-lit
## lobes. Some of the card's own normal is kept so the leaves still catch the
## light one by one inside a lobe.
const CROWN_VOLUME := 0.6
## The volume normal leans this far up (added to the unit box position):
## taken straight off the box, a tall dark fir's normals faced sideways and it
## fell from luminance 74 to 52; leaning them all the way up (0.8) lit every
## crown flat and the maple read as a pink blob.
const CROWN_VOLUME_LIFT := 0.55
## Fake occlusion towards the crown's centre: at the centre of the crown's
## box the albedo is scaled by CROWN_CORE, reaching 1 at CROWN_CORE_EDGE of
## the way out to its shell. Leaves inside the crown and the gaps between its
## clumps read darker, which is what makes a clump read at all.
const CROWN_CORE := 0.84
const CROWN_CORE_EDGE := Vector2(0.25, 0.85)
## Painted clumps: a value mottle in mesh space, CROWN_LOBES of them across
## a crown's width, this far either side of the mean, so a crown lit as one
## volume still breaks into three to five lobes - lit masses with shaded gaps
## between them - as the reference trees do. A fixed size in metres could not
## do that: the kit's meshes are in their own units, scaled by their nodes.
const CROWN_LOBES := 3.5
const CROWN_CLUMP := 0.3
## Every crown is a little different: its hue turns by up to this many
## degrees and its value by this fraction either way, from a hash of its
## position in its region (not in the world, which a seam crossing rebases).
const CROWN_JITTER_HUE := 7.0
const CROWN_JITTER_VALUE := 0.1
## The jitter comes in this many variants, so the copies of one kit tree
## share that many painted materials rather than one each.
const CROWN_JITTER_VARIANTS := 8

## The autumn crowns' tame. The kit's crimson maple is saturation 0.9 at hue
## 300-349 (magenta, not crimson) and its great amber oak 0.9 at hue 25: flat
## neon blobs beside the painted canopies (0.45-0.6). A warm, saturated texel
## (hue in the window below, in sRGB degrees, above TAME_FROM saturation) has
## its saturation compressed past TAME_KNEE towards TAME_CEILING, its magenta
## pulled towards crimson (no bluer than TAME_MAGENTA_FLOOR degrees, i.e.
## 358), and its hue walked across the crown: towards scarlet and amber at the
## top (TAME_HUE_TOP degrees) and towards maroon underneath (TAME_HUE_UNDER).
## Hues are judged on display-encoded colour in both renderers. Compressed to
## 0.68 at the same value, the maple went salmon (luminance 92 to 100,
## saturation 0.80 to 0.67): the tame keeps more chroma and takes value off
## the bright texels instead, which is what a painter deepening a neon red
## would do.
const TAME_HUE := Vector2(268.0, 60.0)
const TAME_FROM := Vector2(0.4, 0.6)
const TAME_KNEE := 0.55
const TAME_CEILING := 0.8
const TAME_MAGENTA_FLOOR := -2.0
## The maple's hue runs from crimson underneath to copper on top, and the
## value, not the hue, carries the top light. Walked to 9 degrees on top at
## TAME_VALUE 0.72 it read coral; it is the top's pale value that turns a warm
## red coral or salmon (walked to 16-22 degrees at 0.64 it read peach), so the
## top walks further (14) only because TAME_VALUE holds it deep.
const TAME_HUE_TOP := 14.0
const TAME_HUE_UNDER := -8.0
## Bright texels (display value from TAME_VALUE_FROM.x to .y) lose this much
## value, so a tamed crown's lit top stays a deep warm red or amber rather
## than a pale neon one. Lit card by card at 0.8 it took the maple from
## luminance 92 to 78 and Amberwood with it; lit as a volume the maple's top
## takes more sun, and above 0.8 AgX paled it to pink. At 0.72 Forward+ still
## drew the maple's lit lobes salmon-pink over a crimson underside (crown
## colour 167, 69, 53); at 0.5 it is a painted crimson turning copper where
## the sun lands (129, 51, 36), as dark as develop's neon (luminance 67
## against 68) with a fifth less chroma, and its lobes still read.
const TAME_VALUE := 0.5
const TAME_VALUE_FROM := Vector2(0.5, 0.9)

## Wind: a crown sways by up to this many metres at its top, weighted by the
## square of the height within the mesh, so the trunk's foot never moves; one
## cycle takes about 2 pi / CROWN_SWAY_SPEED seconds, each crown on its own
## phase. Gentle: the camera is 26 m away.
const CROWN_SWAY_METRES := 0.07
const CROWN_SWAY_SPEED := 1.1
## Camera distance alone must not hide a tree beside the player. Disable the
## independent crown/trunk depth cut; OccluderFade owns player visibility and
## opens a hole only in geometry that actually obstructs the character.
const CROWN_NEAR_FADE_METRES := Vector2.ZERO
## ELORIA_LOOK_FOLIAGE_DEBUG=1 draws every painted crown flat by its view
## depth (red nearer than 10 m, yellow to 15, green to 20, blue beyond) with
## no near fade, for telling which crowns a frame's canopy is and how far.
const FOLIAGE_DEBUG_VARIABLE := "ELORIA_LOOK_FOLIAGE_DEBUG"

## The occluder fade opens a hole round the player instead of blending the
## whole occluder (LookFade, look_fade_hole.gdshaderinc); its timing stays
## OccluderFade's (FADE_SECONDS). The hole is FADE_HOLE_METRES in radius across
## the view at the player's depth - at the default 26 m framing about 95
## pixels, a player and a stride of ground either side - or FADE_HOLE_SHARE of
## a wider occluder's width, up to FADE_HOLE_MAX_METRES (a giant canopy). Its
## rim is dithered over FADE_RIM_METRES or FADE_RIM_SHARE of the radius,
## whichever is wider, and it cuts only what stands in front of the player's
## chest or at most FADE_BEHIND_METRES behind it. Dithering the whole occluder
## at 35 % coverage covered up to a fifth of the frame in a one-pixel
## crosshatch (high-frequency energy 51 in the deep grove against the
## reference's 13-18). A rim of 0.4 m on a 2 x 2 pixel Bayer read as a
## checker band about 15 pixels wide round the player (Whitehorn's gate
## pillars, the Verdant hub gate): now one-pixel noise over 0.25 m, about 9.
const FADE_HOLE_METRES := 2.6
const FADE_HOLE_SHARE := 0.2
const FADE_HOLE_MAX_METRES := 6.5
## A crown opens a wider hole, CROWN_HOLE_SHARE of its width up to
## CROWN_HOLE_MAX_METRES: a crown never vanishes, and under Amberwood's giant
## canopies (37-52 m across) a 6.5 m hole left a ceiling of orange leaf cards
## over half of aw_deep_grove.
const CROWN_HOLE_SHARE := 0.25
const CROWN_HOLE_MAX_METRES := 11.0
const FADE_RIM_METRES := 0.25
const FADE_RIM_SHARE := 0.08
const FADE_BEHIND_METRES := 0.4
## Which occluders dissolve whole instead of opening a hole (LookFade
## Mode.VANISH): one whose box, projected, covers more than
## FADE_VANISH_COVERAGE of the view (the Grey Moors' turf roof held a quarter
## of gm_road near-black round its hole, Sunmane's tent 40 % of ss_road); a
## thin one, at most FADE_THIN_METRES across the ground one way (a wall, a
## fence, a beam), or at least FADE_PILLAR_RATIO times as tall as it is wide
## and FADE_PILLAR_METRES tall (Whitehorn's gate pillars, Verdant's hub
## obelisk); and one whose footprint, shrunk by FADE_OVER_INSET_METRES, holds
## the player under its top (a roof, a yurt: at ss_wild a straw cone sat over
## the player with a porthole in it).
const FADE_VANISH_COVERAGE := 0.1
## A landmark a region names to keep its hole (`props.hole_words`) still
## vanishes when its box covers more than this of the view: from the camera's
## low limit behind sw_isle's 32 m keep (coverage 1.0: its box reaches behind the
## camera), a hole left the frame one wall. The west gatehouse seen from the game
## camera with the player in its passage covers 0.90 and keeps its hole.
const FADE_NAMED_HOLE_MAX_COVERAGE := 0.95
const FADE_THIN_METRES := 2.0
const FADE_PILLAR_RATIO := 2.0
const FADE_PILLAR_METRES := 4.0
const FADE_OVER_INSET_METRES := 0.3
## A mesh under a node whose name starts with one of these, holding at most
## FADE_ASSEMBLY_PIECES_MAX meshes, is a piece of one structure, and the
## structure's width decides whether it blends (LookFade.assembly_width): each
## piece of Crownwater's dome is narrower than FADE_SOLID_MAX_METRES.
const FADE_ASSEMBLY_PREFIXES: Array[String] = ["Landmark_"]
const FADE_ASSEMBLY_PIECES_MAX := 48
## An occluder wider than this across the ground blends as develop blends
## it instead of opening the hole (LookFade.keeps_hole), unless it is a
## painted crown: it is as wide as the largest hole (FADE_HOLE_MAX_METRES)
## can make a fifth of (FADE_HOLE_SHARE), so a hole would leave most of it
## covering the frame. Crownwater's giant dome drew the player in a dark disc
## under an opaque teal cap (world luminance 183 to 107) where develop showed
## the plaza through it. A cottage's roof keeps its hole: blended, the
## coppice's roof turned into a grey smear of the room's inside (aw_coppice,
## 12 % of the frame). On an interior every occluder blends (LookFade.bind).
const FADE_SOLID_MAX_METRES := FADE_HOLE_MAX_METRES / FADE_HOLE_SHARE

# --- Grass beds (layer L4) ---------------------------------------------------

## Grass grows around the camera's focus, out to GRASS_RADIUS metres, and its
## tufts shrink to nothing over the last GRASS_FADE_METRES, so the bed never
## ends in a line. Keep full grass through 52 m and fade over the outer 20 m
## so wider and lower camera views do not reveal a small ring around the
## player. The instance budget below grows with the covered area to preserve
## the near grass's density and keep budget cuts outside the visible ground.
const GRASS_RADIUS := 72.0
const GRASS_FADE_METRES := 20.0
## And from GRASS_SOFTEN_METRES.x to .y from the camera a tuft loses up to
## GRASS_SOFTEN of its root-to-tip gradient and GRASS_SOFTEN_SHRINK of its
## size. At the default framing the frame's foot is about 22 m from the
## camera and its top about 33-40 m, so the near ground keeps its blades and
## the far half turns to tone: dark roots and bright tips a pixel or two apart
## were most of the high-frequency speckle at lr_beacon and fg_south_gate
## (p95 65 and 58 in the compatibility renderer, against a 50 target).
const GRASS_SOFTEN_METRES := Vector2(24.0, 44.0)
const GRASS_SOFTEN := 0.6
const GRASS_SOFTEN_SHRINK := 0.2
## Placement is worked out in square tiles this many metres across, each
## GRASS_TILE_CELLS candidates a side (one every 0.62 m), and a tile is kept
## until the focus leaves it behind or the ground under it changes (a chunk
## or a neighbour streams in or out). Every candidate casts one ray down the
## walk collision, so a tile costs about 170 rays and 2 ms.
const GRASS_TILE_METRES := 8.0
const GRASS_TILE_CELLS := 13
## The focus has to move this far before the set of tiles is looked at again.
const GRASS_REFOCUS_METRES := 2.0
## Never more than this many tufts: the tiles nearest the focus fill first.
## GrassBeds ends its distance fade inside the uploaded coverage, so neither
## a budget cut nor a tile still loading exposes a square edge.
const GRASS_INSTANCE_BUDGET := 72000
## How long placement may take per frame, in microseconds: more while the
## ground the camera frames (GRASS_BARE_METRES around the focus) is still bare
## after a map load, a teleport or a chunk that changed under it, less while
## the bed only extends ahead of a walking player.
const GRASS_BUILD_USEC := 2000
const GRASS_BUILD_USEC_BARE := 6000
const GRASS_BARE_METRES := 24.0
## Tufts per square metre. Verge is the strip along a road's edge where its
## deck has run out (the edge band the ground layer darkens), the dense bed
## that frames every road in the reference frames. Open grass carries beds
## where a slow noise (GRASS_BED_METRES across) rises through GRASS_BED_EDGE,
## and a light scatter everywhere else, both scaled by how grassy the ground
## layer under them is.
## A bed has to cover its ground to read as one from the -60 degree camera:
## at 4.5 tufts a square metre the first capture showed single tufts, dark
## stars on the grass, with the ground between them. Between the beds there
## is only a sprinkle of tall tufts: at 0.25 a square metre the scatter's lone
## tufts were most of what the open fields showed, one- and two-pixel specks
## that doubled the frame's high-frequency energy; with none at all the low
## views lost the dry grass standing in their foreground. The bed's edge (the
## noise from GRASS_BED_EDGE.x to .y) is narrow, so grass gathers into beds
## with bare ground between them, and its fringe shrinks (GRASS_THIN_SCALE)
## rather than thinning out.
const GRASS_VERGE_DENSITY := 12.0
const GRASS_BED_DENSITY := 9.0
const GRASS_SCATTER_DENSITY := 0.04
## Ground asking for fewer tufts a square metre than this grows none, so grass
## ends in beds rather than thinning out into single tufts: the scatter and a
## bed's thin fringe on sparse ground (Manymouth's silt, the Grey Moors' peat,
## the verge's minimum over bare scree and snow) grew one tuft a cell here and
## there, the speckle the reviews measured (hf95 47-58).
const GRASS_DENSITY_FLOOR := 2.5
const GRASS_BED_METRES := 7.0
const GRASS_BED_EDGE := Vector2(0.47, 0.6)
## A tuft on thin ground (low grassiness, a bed's fringe) is scaled down
## towards this. At 0.5 Amberwood's moss (half as grassy as a meadow) grew
## tufts too small to read from the low views.
const GRASS_THIN_SCALE := 0.7
## Most tufts a single candidate may carry, so a verge stays a bed of tufts
## rather than a pile of them.
const GRASS_TUFTS_PER_CELL := 6
## A road deck's coverage (its vertex alpha: 0 at its edge, 1 one strip in)
## from which it is verge, and from which it is road. The ground layer cuts
## the road at 0.5 with a 0.1 wobble, and a verge tuft's blades reach 0.4 m
## out from its foot, so grass stops well short of it: from 0.4 the tufts
## covered 6-11 % of the roads' own metric boxes, and from 0.3 they still
## stood a little way into Amberwood's pale camp deck.
const GRASS_VERGE_ALPHA := Vector2(0.02, 0.24)
## The verge bed feathers in over this much coverage from the deck's outer
## edge, with as much jitter, so it does not end in the straight line the
## deck's geometry ends on (a hard hedge edge at the east gate), and from
## coverage GRASS_VERGE_ROADSIDE.x up to the road it thins by
## GRASS_VERGE_ROADSIDE.y, so its tufts stand back from the road's edge.
const GRASS_VERGE_FEATHER := 0.14
const GRASS_VERGE_ROADSIDE := Vector2(0.12, 0.5)
## An authored patch (a yard, a forecourt, leaf litter) at or above
## LookProfile.PATCH_RIM coverage keeps this share of the grass, and its rim
## (from GRASS_PATCH_RIM_FROM up to PATCH_RIM) is verge. Pale paving keeps none
## from LookProfile.PAVING_RIM up. None: dark spiky tufts on Amberwood's
## copper leaf litter read as dirt specks, and yards are trodden ground.
const GRASS_ON_PATCH := 0.0
const GRASS_PATCH_RIM_FROM := 0.3
## Except a green meadow: a patch whose tint's green leads its red and blue by
## this share of it (the life passes' Grass preset regions, #b3eb80 and
## #b8eba8) is grass however bare the biome under it, from
## GRASS_PATCH_RIM_FROM coverage to full at PATCH_RIM, with no verge ring at
## its edge. Kept to GRASS_ON_PATCH like a yard, Mirrorhold's 28 meadows over
## scree and Manymouth's 36 over silt grew no tufts inside and a single row
## round their rims, and the tufts stood on the bare ground around them.
const GRASS_PATCH_GREEN := 0.06
## A road's or a patch's rim keeps its verge bed in proportion to the biome
## beneath it (twice its grassiness, so moss and heather keep all of it), but
## no less than this on bare scree, snow or sand.
const GRASS_BARE_RIM := 0.15
## A patch at least this bright (display value) and at most this saturated is
## worn cobble or stone, like paving if not as pale (the east gate's forecourt,
## #ad9e82): no grass where it covers the ground. Soil, dirt yards and leaf
## litter are warmer and keep GRASS_ON_PATCH.
const GRASS_BARE_PATCH := Vector2(0.6, 0.35)
## Where such a patch ends. The exporter's coverage runs straight along the
## terrain cells, and the grass used to stop at PATCH_RIM with a dense verge
## row just before it, which drew the east gate forecourt's edge as a ruled
## line through the grass (fg_east_gate_close). Now the coverage the grass
## stops at wanders GRASS_BARE_EDGE_JITTER either side of PATCH_RIM on a noise
## GRASS_BARE_EDGE_METRES across, about the ground paint's own rim wobble, and
## the tufts thin out over the last GRASS_BARE_EDGE_FEATHER of coverage before
## it.
const GRASS_BARE_EDGE_METRES := 1.3
const GRASS_BARE_EDGE_JITTER := 0.2
const GRASS_BARE_EDGE_FEATHER := 0.25
## No grass within pale paving's bounds, nor this many metres beyond them:
## judged by its coverage, the grass came up through the one-cell seams
## between the Four Gates plaza's patches and along the rims of the avenue
## decks that cross it.
const GRASS_PAVING_MARGIN := 0.5
## A terrain road (the worn colour the exporter paints into the terrain's
## vertex colour, LookProfile.TERRAIN_ROAD_COLOUR) is road from this weight
## and verge from this one.
const GRASS_TERRAIN_ROAD := Vector2(0.25, 0.5)
## Grass stands on ground whose world-up normal component is at least the
## second value and thins out down to the first (about 39 to 26 degrees).
const GRASS_SLOPE_UP := Vector2(0.78, 0.9)
## How grassy each biome layer is, by a word in its texture's file name. The
## blend's layers differ from cell to cell (Four Gates' grass is layer 1 in
## one cell, Amberwood's layer 2 in another, beside alpine scree, snow crust
## and moor heather), so the textures are what say which is grass. A layer
## whose texture has none of these words counts GRASS_LAYER_DEFAULT. The
## words are every map's; a region file's `grass.layers` adds its own words
## (or re-weighs these) for that region's blends, and is read first.
const GRASS_LAYER_WORDS := {
	"ground-basecolor": 1.0, "grass": 1.0, "meadow": 1.0, "lawn": 1.0,
	"heather": 0.6, "moor": 0.6, "moss": 0.5, "forest-floor": 0.5,
	"gravel": 0.12, "mud": 0.2, "scree": 0.0, "snow": 0.0, "sand": 0.0,
	"rock": 0.0, "cliff": 0.0,
}
const GRASS_LAYER_DEFAULT := 0.3
## Maps outside the continent colour their ground by vertex colour (Lantern
## Reach's island is one mesh: green grass at value 0.45, a sand-gold trail
## at 0.82, and a one-vertex blend between, which the ground layer paints as
## trail from about its middle). Ground at the second value or brighter is
## path, between the two it is the verge along it, and below the first it is
## grass when its green leads red and blue by GRASS_VERTEX_GREEN. From 0.62
## the tufts stood on the trail's painted margin (up to 9 % of its metric box
## dark) and took the trail's path/ground ratio from 1.6 to 1.3; the verge is
## now only the blend's grassy foot.
const GRASS_VERTEX_PATH_VALUE := Vector2(0.46, 0.49)
const GRASS_VERTEX_GREEN := 0.06
## Where a region's file asks for it (`grass.open_green`), open terrain with no
## biome blend grows grass as its vertex colour's green leads its red and blue
## (display): none at or under x, all of it from y (sw_isle's graded meadow
## green leads by about 0.09, its dry meadow 0.02, sand and rock not at all).
const GRASS_OPEN_GREEN := Vector2(-0.01, 0.05)

## The tufts: GRASS_TUFTS blades each (4 to 6), in three sizes - short and
## splayed for the verge, mid-height for the beds, taller and upright for a
## few in each bed - each blade a tapered two-segment strip that arcs
## outward, so a tuft still reads as a star of strokes from the -60 degree
## camera. Every tuft is turned, scaled within GRASS_SCALE and tilted halfway
## to the ground. At 0.065 m a blade was one or two pixels wide at the 26 m
## framing, which with no anti-aliasing crawls as it sways; blades are wider
## and fewer (the three averaged 21 triangles a tuft, now 15), and the verge's
## are about a third shorter, with more spread in length, so a verge is a low
## bed rather than a hedge.
const GRASS_TUFTS := [
	{"blades": 6, "length": Vector2(0.2, 0.46), "splay": Vector2(20.0, 46.0),
		"width": 0.1, "spread": 0.1},
	{"blades": 5, "length": Vector2(0.36, 0.66), "splay": Vector2(16.0, 40.0),
		"width": 0.1, "spread": 0.08},
	{"blades": 4, "length": Vector2(0.52, 0.84), "splay": Vector2(8.0, 28.0),
		"width": 0.095, "spread": 0.06},
]
const GRASS_SCALE := Vector2(0.7, 1.1)
## A verge tuft stands on the road's dark edging band (EDGE_BAND), so its
## palette is taken down this far: a verge bed at the band's value frames the
## road, where at the open grass's value the east gate's read as a bright
## hedge along it.
const GRASS_VERGE_SHADE := 0.82
const GRASS_GROUND_TILT := 0.5
## The grass, root to tip, as display (sRGB) colours: a root darker than the
## verge it grows from and a tip lighter and warmer, averaging about the
## verge's own value, so the bed reads as depth and light rather than as a
## paler carpet (roads stay the palest thing on the ground). This one is for
## any map whose region file has no `grass` section; a region's own palette
## (Four Gates' lush green, Amberwood's dry straw and amber, Lantern Reach's
## coastal green) and its per-renderer `value` trim live in its file
## (`grass_palette`). The shader holds GRASS_PALETTE_SLOTS palettes, slot 0
## this one; the grass hands the others out as it meets their regions.
const GRASS_PALETTE_DEFAULT := {"root": Color(0.09, 0.15, 0.06), "tip": Color(0.52, 0.6, 0.28)}
## How many palettes the grass shader holds (grass_beds.gdshader's arrays).
## A client that walks into more regions with their own palettes than this
## grows the rest in slot 0's.
const GRASS_PALETTE_SLOTS := 32
## The palettes' value in each renderer. The compatibility renderer lights
## the display-encoded colour, Forward+ its linear value with SSIL's bounce
## on top: at 1 in both, Forward+ drew Four Gates' tufts at luminance 125
## over grass at 83, the compatibility renderer at 99 over 118.
const GRASS_VALUE_COMPAT := 1.3
const GRASS_VALUE_FORWARD := 0.3
## And their chroma: the compatibility renderer's grade drove Four Gates'
## tufts to (64, 101, 20), a blue channel near zero, while Forward+ drew the
## same palette a grey olive (71, 78, 46).
const GRASS_CHROMA_COMPAT := 0.85
const GRASS_CHROMA_FORWARD := 1.35
## The root-to-tip blend's power (above 1, most of a blade is the root's
## colour and only its end lights up) and the vertex-colour shade at the root.
const GRASS_GRADIENT_POWER := 1.4
const GRASS_ROOT_SHADE := 0.75
## Every tuft keeps this share of its root-to-tip gradient about the middle
## (0.45 of the way): the regions' palettes run from a root about a fifth of
## the tip's luminance, and dark roots beside bright tips one or two pixels
## apart were most of the speckle the reviews measured. Against renders with
## no grass at all (ELORIA_LOOK_GRASS_DEBUG=none) the beds added 16-34 to hf95
## at ss_wild, ss_grove, md_hub, cw_hub, cw_horizon and vs_road.
const GRASS_CONTRAST := 0.6
## Every tuft's value moves by up to this much either way, and a slow noise
## (GRASS_TONE_METRES across) turns whole beds warmer or cooler by up to
## GRASS_WARM, so a field reads as painted patches rather than one colour. Both
## are mild: a tuft also takes the ground paint's own mottle at its foot, and
## at 0.1 the jitter alone made single tufts stand out as specks.
const GRASS_VALUE_JITTER := 0.05
const GRASS_TONE_METRES := 11.0
const GRASS_WARM := Color(1.05, 1.0, 0.9)
const GRASS_SPECULAR := 0.15
## Wind: the tips lean downwind by up to GRASS_WIND_METRES and sway on a wave
## GRASS_WIND_WAVE_METRES long that rolls across the field, swelling and
## easing with gusts. Directions are in the continent frame (x east, z south).
const GRASS_WIND_DIRECTION := Vector2(0.8, -0.6)
const GRASS_WIND_METRES := 0.1
const GRASS_WIND_SPEED := 1.7
const GRASS_WIND_WAVE_METRES := 6.5
const GRASS_GUST_SPEED := 0.37
## The render layer the grass draws on: the main camera's gameplay layer,
## which the map cameras do not render (the maps are navigation aids).
const GRASS_RENDER_LAYER := 2
## ELORIA_LOOK_GRASS_DEBUG=1 prints each finished build's placement census;
## =none grows no grass at all, for measuring the tufts against the bare
## painted ground under them (l4/diffpix.py).
const GRASS_DEBUG_VARIABLE := "ELORIA_LOOK_GRASS_DEBUG"

# --- Sky and haze (layer L5) -------------------------------------------------

## The painted sky starts from the region's own declared sky colours (after
## the hour has moved them, as DayNightBinder would), so Four Gates keeps its
## clear blue and Amberwood its dusky autumn sky. A map that declares no sky
## takes its colours from its region file's `sky` section (Lantern Reach
## declared only a dark background colour, which the grade lifted to a flat
## pale cyan wall above its sea), or else these, the binder's own defaults.
const SKY_FALLBACK := {"top": Color("3d7ec2"), "horizon": Color("bcc9cd")}
## The reference skies are blue down to a thin warm pale haze at the horizon,
## where the manifests' horizons are cool grey-blue (Four Gates) or a dull
## warm grey (Amberwood). Daylight warms the sky's horizon colour only this far
## towards SKY_WARM (display colours), a warm cream, and the haze band (which
## is also the fog) SKY_HAZE_WARMTH further, lifted a little, so the far ground
## melts into light rather than into grey. The first capture warmed the whole
## horizon by 0.35: the sky above the haze went cream-grey, an overcast day.
const SKY_WARM := Color(1.0, 0.87, 0.68)
const SKY_HORIZON_WARMTH := 0.12
const SKY_HAZE_WARMTH := 0.45
## A region's file may name its own (`sky.haze_warmth`, LookSky.sky_colours):
## sw_isle's lagoon fog is blue, and warmed by 0.45 its far views read cream.
## Lifted 0.1, the haze band was the brightest thing in a low view (197 luma
## at gm_horizon, a paper-white wall over the tutorial islands) and pulled the
## eye off the road and the landmark.
const SKY_HAZE_LIFT := 0.03
## And never brighter than this display value: the sky takes the grade's
## exposure too, so a pale declared horizon (Whitehorn's, Crownwater's) came
## out white over white snow or over the far palace. 0.72 still left it near
## white (198); 0.66.
const SKY_HAZE_VALUE_MAX := 0.66
## Only a clear sky is painted as the bright day (LookSky.clearness): a
## declared zenith this blue (hue window in degrees, with SKY_CLEAR_HUE_EDGE
## either side) and this saturated. Every clear map's zenith is 208-218
## degrees at 0.6-0.8; the Amethyst Barrens' violet dusk (249 degrees) and
## the Grey Moors' overcast (0.23) are not, and keep their own colours, with
## clouds in their horizon's colour lifted SKY_MOODY_CLOUD_LIFT and at
## SKY_MOODY_CLOUD_OPACITY of the clear sky's opacity.
const SKY_CLEAR_HUE := Vector2(190.0, 235.0)
const SKY_CLEAR_HUE_EDGE := 10.0
const SKY_CLEAR_SATURATION := Vector2(0.3, 0.5)
const SKY_MOODY_CLOUD_LIFT := 0.12
const SKY_MOODY_CLOUD_OPACITY := 0.5
## The zenith is taken this far towards a clear, deep blue, which lifts
## Amberwood's murky navy (0.15, 0.25, 0.42) and deepens Four Gates' blue
## (0.24, 0.45, 0.73). AgX and the grade's saturation pale a blue sky a long
## way: Four Gates' own zenith drew about (122, 166, 207), the low reference
## skies are nearer (70, 130, 210).
const SKY_ZENITH_DEEP := Color(0.08, 0.3, 0.78)
const SKY_ZENITH_DEPTH := 0.45
## The gradient from horizon to zenith: 1 - (1 - sin(elevation))^power, so the
## zenith's blue takes over soon above the haze: two thirds of it 10 degrees
## up. A low camera sees at most about 13 degrees of sky, and at 2.6 (a third
## there) that sky was the pale horizon's.
const SKY_GRADIENT_POWER := 6.0
## The haze band: in the sky it fades from exactly the haze colour at the
## horizon to none at this sine of elevation (about 6 degrees); below the
## horizon, where nothing has loaded or the world has ended, it carries on and
## gives way to the old ground colour by this sine (about 17 degrees). A map
## camera looking straight down still sees only that ground colour. At 0.1
## the band filled most of what a low view sees of the sky, and over
## Whitehorn's snow it read as white sky meeting white ground (wr_horizon's
## sky 198 against develop's 151); at 0.07 (about 4 degrees) the zenith's
## blue comes down to it.
const SKY_HAZE_HEIGHT := 0.07
const SKY_HAZE_DEPTH := 0.3
## Brushed cumulus: four octaves of value noise on a flat cloud layer, the
## noise this many cells per unit of the layer's plane (larger, smaller
## clouds), stretched across the wind (x) by SKY_CLOUD_STRETCH so the masses
## read as horizontal brush strokes. The noise is pushed SKY_CLOUD_CONTRAST
## times further from its mean, then cut at SKY_CLOUD_THRESHOLD with a soft
## edge of SKY_CLOUD_SOFTNESS either side (about a quarter of the sky covered,
## a tenth solid), at most SKY_CLOUD_OPACITY opaque: uncut, most of the noise
## sits inside the soft edge and the clouds were one thin grey veil. A
## cloud is SKY_CLOUD_LIT, brighter than the sky, on its sun-facing side and
## towards the sky behind it at SKY_CLOUD_SHADE of its value in its core and
## underside. They fade in between the two elevations (sines) of
## SKY_CLOUD_BAND, above the haze. Shaded half-way to the sky, the first
## capture's clouds read as a grey overcast.
const SKY_CLOUD_SCALE := 2.2
const SKY_CLOUD_STRETCH := 0.5
const SKY_CLOUD_CONTRAST := 1.8
const SKY_CLOUD_THRESHOLD := 0.62
const SKY_CLOUD_SOFTNESS := 0.06
const SKY_CLOUD_OPACITY := 0.9
const SKY_CLOUD_LIT := Color(1.0, 0.97, 0.9)
const SKY_CLOUD_NIGHT := Color(0.3, 0.33, 0.42)
const SKY_CLOUD_SHADE := 0.94
const SKY_CLOUD_BAND := Vector2(0.03, 0.2)
## A warm glow round the sun: a wide halo and a tighter core, this colour over
## the sun's own light. At noon the sun stands 62 degrees up, out of every
## camera framing; it matters at dawn and dusk.
const SKY_SUN_GLOW := Color(1.0, 0.82, 0.55)
const SKY_SUN_HALO := 0.25
const SKY_SUN_CORE := 0.6
## The haze is depth fog in the haze colour, and it replaces the grade's fog
## (FOG_BEGIN and after). The grade's fog left the ground 70 % clear at 320 m,
## so wherever streaming stopped the ground ended in a hard line against the
## sky. This gathers from HAZE_BEGIN to HAZE_END along a smoothstep raised to
## HAZE_CURVE, up to HAZE_DENSITY: nothing in the default -60 degree framing
## (its far edge is about 50 m away: under 0.1 %), 6 % at 150 m, 31 % at
## 250 m, 59 % at 330 m and 75 % from 420 m. A map that declares denser fog
## gets more, as the grade did, so Amberwood stays mistier than the city. At
## 0.8 from 380 m the far Four Gates town beyond the south gate bleached into
## the haze at the -15 degree view: a landmark lost to hide the world's edge.
## From 40 m on a curve of 1.6 the middle distance hazed too (31 % at 250 m):
## Crownwater's palace dome went from saturation 0.34 to 0.15 at cw_horizon
## and Mirrorhold's valley into a flat cream wall; from 80 m on 2.0 it is
## 19 % there, and the world's edge is as hidden (52 % at 330 m, 75 % beyond).
const HAZE_BEGIN := 80.0
const HAZE_END := 420.0
const HAZE_CURVE := 2.0
const HAZE_DENSITY := 0.75
const HAZE_DENSITY_PER_DECLARED := 100.0
const HAZE_DENSITY_MAX := 0.92
## The haze a fog bank closes it to (WeatherSky marks the weather's fog in the
## manifest's `fog.weather`, 0..1): from HAZE_BEGIN-HAZE_END to these at full
## fog, and up to full density. Begun at 80 m, the haze could only ever grey
## the far half of a frame, so a fog state read as an overcast one.
const WEATHER_HAZE_BEGIN := 6.0
const WEATHER_HAZE_END := 150.0
## How much of the haze also veils the sky itself, clouds and zenith alike.
## Little: the painted sky draws its own haze where it belongs, at the horizon.
const HAZE_SKY_AFFECT := 0.1
## ELORIA_LOOK_SKY_DEBUG=1 draws the painted sky flat magenta above the
## horizon and cyan below it, for counting how much of a capture is sky; =2
## leaves the clouds out; =3 and =4 draw the zenith's and the horizon's colour
## flat, for reading what AgX and the grade make of them.
const SKY_DEBUG_VARIABLE := "ELORIA_LOOK_SKY_DEBUG"

## True while the look is on. ELORIA_LOOK decides when it is "0" (off) or "1"
## (on), for a developer or a test; otherwise the player's own choice does
## (`set_player_look`, the settings file's [graphics] look), and a player who
## never chose has it on (LOOK_DEFAULT). A stray value of the variable is
## ignored rather than read as off. Read on every call, from the loader's
## worker threads too; LookSwitch applies a change to what is already loaded.
static func enabled() -> bool:
	match OS.get_environment(ENABLE_VARIABLE):
		"0":
			return false
		"1":
			return true
	return _player_look

## True when ELORIA_LOOK decides the switch, so the player's choice is kept
## but has no effect (the settings window greys it out and says why).
static func look_forced() -> bool:
	return OS.get_environment(ENABLE_VARIABLE) in ["0", "1"]

## The player's own choice, whether or not ELORIA_LOOK overrides it.
static func player_look() -> bool:
	return _player_look

## Records the player's choice. Returns true when `enabled()`'s answer changed,
## which is when the loaded world has to follow (LookSwitch).
static func set_player_look(on: bool) -> bool:
	var before := enabled()
	_player_look = on
	return _note_switch() != before

## The graphics quality in use (Quality): ELORIA_LOOK_QUALITY's when it names
## one, otherwise the player's (`set_player_quality`, the settings file's
## [graphics] quality), HIGH for a player who never chose.
static func quality() -> Quality:
	var forced := quality_named(OS.get_environment(QUALITY_VARIABLE))
	return (forced if forced >= 0 else _player_quality) as Quality

## True when ELORIA_LOOK_QUALITY decides the quality.
static func quality_forced() -> bool:
	return quality_named(OS.get_environment(QUALITY_VARIABLE)) >= 0

## The player's own quality, whether or not ELORIA_LOOK_QUALITY overrides it.
static func player_quality() -> Quality:
	return _player_quality as Quality

## Records the player's quality; one out of range is taken as the default.
## Returns true when `quality()`'s answer changed.
static func set_player_quality(level: int) -> bool:
	var before := quality()
	_player_quality = level if level >= 0 and level < QUALITY_NAMES.size() else QUALITY_DEFAULT
	return quality() != before

## The Quality a name stands for (QUALITY_NAMES, any case), or -1.
static func quality_named(name: String) -> int:
	return QUALITY_NAMES.find(name.strip_edges().to_lower())

## The name a Quality is written as.
static func quality_name(level: int) -> String:
	return QUALITY_NAMES[clampi(level, 0, QUALITY_NAMES.size() - 1)]

## `key`'s entry (QUALITY_PRESETS) for the quality in use, after any
## ELORIA_LOOK_QUALITY_TRIM override of it.
static func quality_value(key: String) -> Variant:
	var value: Variant = QUALITY_PRESETS[quality()][key]
	var trims := OS.get_environment(QUALITY_TRIM_VARIABLE)
	if trims.is_empty():
		return value
	for pair: String in trims.split(",", false):
		if pair.get_slice("=", 0).strip_edges() != key or not pair.contains("="):
			continue
		var raw := pair.get_slice("=", 1).strip_edges()
		if value is bool:
			return raw not in ["0", "false", "off", ""]
		if value is int:
			return raw.to_int()
		return raw.to_float()
	return value

## The player's switch and quality as main read them from the settings file or
## the settings window last set them. Read through `enabled` and `quality`.
static var _player_look := LOOK_DEFAULT
static var _player_quality: int = QUALITY_DEFAULT

# The switch's generation: it counts every change of `enabled()`'s answer, so a
# root painted (or left alone) under an older answer can be told apart from
# one that already follows the current one. Loader workers read it too.
static var _switch_mutex := Mutex.new()
static var _generation := 0
static var _generation_state := LOOK_DEFAULT
static var _stamps: Dictionary = {}

## The switch's generation now (see `stale`).
static func switch_generation() -> int:
	_note_switch()
	_switch_mutex.lock()
	var generation := _generation
	_switch_mutex.unlock()
	return generation

## `enabled()`, recorded against `root` (a map, chunk or neighbour the loader
## is finishing, or the map main binds): the painters ask this rather than
## `enabled()` when they start on a root. The generation is read before the
## switch, and only the first painter's is kept, so a toggle that lands while
## a worker is painting leaves the root marked stale (`stale`) whichever way
## the worker read it, and main puts it right when it adopts it.
static func enabled_for(root: Node) -> bool:
	var generation := switch_generation()
	if root != null:
		_switch_mutex.lock()
		if not _stamps.has(root.get_instance_id()):
			_stamps[root.get_instance_id()] = generation
		_switch_mutex.unlock()
	return enabled()

## Marks `root` as following the switch's current answer (LookSwitch.sync).
static func stamp(root: Node) -> void:
	if root == null:
		return
	var generation := switch_generation()
	_switch_mutex.lock()
	_stamps[root.get_instance_id()] = generation
	_switch_mutex.unlock()

## True when `root` was painted, or left unpainted, under an older answer of
## the switch than the current one. A root no painter has seen is not stale:
## there is nothing of the look's on it to put right.
static func stale(root: Node) -> bool:
	if root == null:
		return false
	var generation := switch_generation()
	_switch_mutex.lock()
	var stamped: Variant = _stamps.get(root.get_instance_id())
	_switch_mutex.unlock()
	return stamped != null and int(stamped) != generation

## True while some root that is still alive was painted, or left unpainted,
## under an older answer of the switch (`stale`): main then looks for it among
## the loaded roots. Forgets the roots that have been freed on the way, so it
## costs a walk of the live roots' stamps and nothing more.
static func any_stale() -> bool:
	var generation := switch_generation()
	var found := false
	_switch_mutex.lock()
	for id: int in _stamps.keys():
		if not is_instance_id_valid(id):
			_stamps.erase(id)
		elif int(_stamps[id]) != generation:
			found = true
	_switch_mutex.unlock()
	return found

## Counts a change of `enabled()`'s answer (the player's switch, or the
## variable in a test) into the generation; returns the answer.
static func _note_switch() -> bool:
	var now := enabled()
	_switch_mutex.lock()
	if now != _generation_state:
		_generation_state = now
		_generation += 1
	_switch_mutex.unlock()
	return now

## True when the renderer has SSAO and SSIL. Only Forward+ does; the others
## ignore the settings but warn about them, so they are not set there at all.
static func screen_space_effects() -> bool:
	return RenderingServer.get_current_rendering_method() == "forward_plus"

## False below HIGH quality, and when the client was started with
## ELORIA_LOOK_SSIL=0 (SSIL_VARIABLE).
static func ssil_enabled() -> bool:
	return bool(quality_value("ssil")) and OS.get_environment(SSIL_VARIABLE) != "0"

## False at LOW quality, and when the client was started with
## ELORIA_LOOK_SSAO=0 (SSAO_VARIABLE).
static func ssao_enabled() -> bool:
	return bool(quality_value("ssao")) and OS.get_environment(SSAO_VARIABLE) != "0"

## False at LOW quality.
static func glow_enabled() -> bool:
	return bool(quality_value("glow"))

## The tone curve in use: TONEMAP_CURVE unless an A/B capture names another.
static func tonemap_curve() -> Dictionary:
	var requested := OS.get_environment(TONEMAP_VARIABLE).to_lower()
	if TONEMAP_CURVES.has(requested):
		return TONEMAP_CURVES[requested]
	return TONEMAP_CURVES[TONEMAP_CURVE]

## The saturation to grade a map with, from what its manifest declares.
static func saturation(declared: float) -> float:
	var base := SATURATION_FORWARD if forward_plus() else SATURATION
	return base * (1.0 + (declared - 1.0) * SATURATION_BOOST_SHARE)

## A map's trim on `key` ("exposure" or "saturation") from its region file's
## `grade` section; 1 for most maps. A continent region's (`continent`) is
## ignored, with a warning, because the continent shares one grade (see
## FORWARD_EXPOSURE's neighbour above).
static func map_trim(map_id: String, key: String, continent := false) -> float:
	if continent:
		if not region_section(map_id, "grade").is_empty():
			_warn_once("grade:" + map_id, "look region %s: a continent region's grade "
				% map_id + "section is ignored; the continent shares one grade")
		return 1.0
	return float(region_value(map_id, "grade", key, 1.0))

## True when a patch tint (display colour) is green: its green leads its red
## and blue by at least GRASS_PATCH_GREEN of itself. The ground paint's meadow
## class (LookGround.is_meadow), its stone test and the grass's green patches
## (LookGrassBeds) all ask this one question, so they agree: judged apart (an
## absolute lead of 0.1 for stone, a relative 0.06 for grass), Sunmane's pale
## grain patches (#c7dbb8) were painted as paving and grew grass at once.
static func green_tint(tint: Color) -> bool:
	return (tint.g - maxf(tint.r, tint.b)) / maxf(tint.g, 0.0001) >= GRASS_PATCH_GREEN

## True in the Forward+ renderer, which some trims tell apart (see
## SUN_WARMTH_FORWARD).
static func forward_plus() -> bool:
	# Asked once: the renderer never changes while the client runs, and the
	# ground is painted on the loader's worker threads too.
	if _forward_plus < 0:
		_forward_plus = 1 if RenderingServer.get_current_rendering_method() == "forward_plus" else 0
	return _forward_plus == 1

## forward_plus()'s answer once asked: -1 not yet, 0 no, 1 yes.
static var _forward_plus := -1

## The exposure trim for the renderer in use (FORWARD_EXPOSURE in Forward+).
static func renderer_exposure() -> float:
	return FORWARD_EXPOSURE if forward_plus() else 1.0

## The key light's warmth for the renderer in use.
static func sun_warmth() -> Color:
	return SUN_WARMTH_FORWARD if forward_plus() else SUN_WARMTH

## The depth fog's density at FOG_END for a manifest's exponential density.
static func fog_density(declared: float) -> float:
	return clampf(FOG_DENSITY + maxf(declared, 0.0) * FOG_DENSITY_PER_DECLARED,
		0.0, FOG_DENSITY_MAX)

## The sky colours (`top`, `horizon`) for a map that declares no sky: its
## region file's `sky` section, else SKY_FALLBACK.
static func sky_fallback(map_id: String) -> Dictionary:
	return {"top": region_value(map_id, "sky", "top", SKY_FALLBACK.top),
		"horizon": region_value(map_id, "sky", "horizon", SKY_FALLBACK.horizon)}

## False when `map_id`'s region file turns the painted sky off (`sky.paint`
## 0): an interior that declares a sun for its open-to-sky sections but whose
## void is meant dark (the Sunmane wind caves, the Ssarathi archive, the
## Drowned Crown), where the painted sky and haze lit the void round the rooms
## (near-black 70 % to 0.6 % in the caves, a pale haze band where develop is
## black). The binder's own sky and the grade stay.
static func sky_painted(map_id: String) -> bool:
	return float(region_value(map_id, "sky", "paint", 1.0)) > 0.0

## The haze's density at HAZE_END for a manifest's exponential density.
static func haze_density(declared: float) -> float:
	return clampf(HAZE_DENSITY + maxf(declared, 0.0) * HAZE_DENSITY_PER_DECLARED,
		0.0, HAZE_DENSITY_MAX)

## A region's ground trim on `key` from its region file's `ground` section,
## or the renderer's default when it has none: GROUND_FORWARD's entry in
## Forward+, else `fallback`. A `<key>_forward` entry wins over `<key>` in
## Forward+ (and `<key>_compat` in the compatibility renderer), as in every
## section (`region_value`).
static func ground_value(region_id: String, key: String, fallback: Variant) -> Variant:
	var renderer_default: Variant = GROUND_FORWARD[key] \
		if forward_plus() and GROUND_FORWARD.has(key) else fallback
	return region_value(region_id, "ground", key, renderer_default)

# --- Per-map and per-region data ---------------------------------------------

## Where each map's and region's own look lives: one file per id,
## REGIONS_DIRECTORY/<id>.json, where <id> is the manifest's asset id (a
## continent chunk, `<region>__chunk_<x>_<z>`, reads its region's file; see
## LookGround.region_of). The constants above are every map's defaults; a file
## says only where its map differs, and a map without one is drawn with the
## defaults. The schema, and why each pilot value is what it is, is in
## regions/README.md; REGION_SECTIONS is what the code reads.
const REGIONS_DIRECTORY := "res://src/world/look/regions"
## The sections a region file may hold and the keys each may hold. A number
## or colour key may also carry a `_forward` or `_compat` suffix, which wins
## over the bare key in that renderer. `grass.layers`, `water.decode_albedo`
## and the `foliage` lists are tables, not trims, and take no suffix. `id`
## (the file's own name), `schema` and `notes` (prose for whoever retunes the
## region) sit beside the sections.
const REGION_SECTIONS := {
	"grade": ["exposure", "saturation", "background"],
	"ground": ["path_luma", "path_tint", "path_chroma", "verge_value_green",
		"verge_value_earth", "verge_saturation", "verge_green_red", "deck_path",
		"deck_road_colour", "deck_tint", "deck_chroma", "deck_grain", "path_detail",
		"path_fine", "rock_value", "meadow_value", "meadow_chroma", "meadow_tint", "keep_patches",
		"paving_tint", "verge_grain", "verge_grain_steep", "class_textures"],
	"grass": ["root", "tip", "value", "layers", "open", "meadow", "open_green"],
	"sky": ["top", "horizon", "paint", "clear", "haze_warmth"],
	"water": ["decode_albedo", "inland_tint", "sea_value", "sea_chroma", "sea_tint"],
	"foliage": ["crown_materials", "tree_words", "shrub_words", "untamed_words", "plain_words",
		"crown_tint"],
	"props": ["keep_words", "keep_chroma", "keep_tint", "hole_words"],
}
const REGION_TABLE_KEYS := ["layers", "decode_albedo", "crown_materials", "tree_words",
	"shrub_words", "untamed_words", "plain_words", "keep_words", "keep_patches", "hole_words",
	"class_textures"]
const REGION_META_KEYS := ["id", "schema", "notes"]
## Keys whose values are colours: [r, g, b] display (sRGB) components, exactly
## as a Color() constant takes them, or "#rrggbb".
const REGION_COLOUR_KEYS := ["path_tint", "root", "tip", "top", "horizon", "deck_road_colour",
	"deck_tint", "inland_tint", "keep_tint", "meadow_tint", "paving_tint", "sea_tint",
	"crown_tint"]
## The lists a region's `foliage` section extends, by key.
const FOLIAGE_DEFAULTS := {"crown_materials": CROWN_MATERIALS, "tree_words": KIT_TREE_WORDS,
	"shrub_words": KIT_SHRUB_WORDS, "untamed_words": KIT_UNTAMED_WORDS,
	"plain_words": KIT_NOT_FOLIAGE_WORDS}

## Parsed region files by id ({} for an id with no file), each read once.
## Chunks are painted on the loader's worker threads, so the cache is locked.
static var _regions: Dictionary = {}
static var _regions_mutex := Mutex.new()
static var _warned: Dictionary = {}

## `id`'s region file, parsed, typed (its colours are Colors, its numbers
## floats) and kept; {} when it has none. Read-only.
static func region(id: String) -> Dictionary:
	_regions_mutex.lock()
	var data: Variant = _regions.get(id)
	if data == null:
		data = _load_region(id)
		_regions[id] = data
	_regions_mutex.unlock()
	return data

## The file `id`'s look is read from.
static func region_path(id: String) -> String:
	return REGIONS_DIRECTORY.path_join(id + ".json")

## Every id that has a region file.
static func region_ids() -> PackedStringArray:
	var ids := PackedStringArray()
	for file: String in DirAccess.get_files_at(REGIONS_DIRECTORY):
		if file.get_extension() == "json":
			ids.append(file.get_basename())
	ids.sort()
	return ids

## Forgets every region file read so far (and every `define_region`), so the
## next use reads the files again.
static func reload_regions() -> void:
	_regions_mutex.lock()
	_regions.clear()
	_regions_mutex.unlock()

## Uses `raw`, a region file's content, for `id` until `reload_regions`, as if
## it had been read from `id`'s file; for tests and previews. Returns what is
## wrong with it, as `region_problems` would.
static func define_region(id: String, raw: Dictionary) -> PackedStringArray:
	var problems := PackedStringArray()
	var data := typed_region(raw, id, problems)
	data.make_read_only()
	_regions_mutex.lock()
	_regions[id] = data
	_regions_mutex.unlock()
	return problems

## Section `section` of `id`'s file; {} when it has none.
static func region_section(id: String, section: String) -> Dictionary:
	var value: Variant = region(id).get(section)
	return value if value is Dictionary else {}

## `key` in `id`'s `section`: `<key>_forward` in Forward+ (`<key>_compat` in
## the compatibility renderer) wins over `<key>`; `fallback` when neither is
## there.
static func region_value(id: String, section: String, key: String, fallback: Variant) -> Variant:
	var entries := region_section(id, section)
	var renderer_key := key + ("_forward" if forward_plus() else "_compat")
	if entries.has(renderer_key):
		return entries[renderer_key]
	return entries.get(key, fallback)

## `id`'s grass palette: its root and tip (GRASS_PALETTE_DEFAULT's where it
## names none) times its `value` trim for the renderer in use, measured
## against its painted ground; {} when its file names no palette, which grows
## the default one.
static func grass_palette(id: String) -> Dictionary:
	var grass := region_section(id, "grass")
	var own := false
	for key: String in grass:
		own = own or not (key.begins_with("layers") or key.begins_with("open")
			or key.begins_with("meadow"))
	if not own:
		return {}
	var trim := float(_grass_value(id, "value", 1.0))
	var root_colour: Color = _grass_value(id, "root", GRASS_PALETTE_DEFAULT.root)
	var tip_colour: Color = _grass_value(id, "tip", GRASS_PALETTE_DEFAULT.tip)
	return {"root": root_colour * trim, "tip": tip_colour * trim}

## A grass palette key as `region_value` reads it, except that a region that
## tuned its palette's colours for one renderer only lends them to the other
## (the renderers' own value and chroma scales, GRASS_VALUE_* and
## GRASS_CHROMA_*, are applied on top either way). Falling back to the default
## palette instead, the compatibility renderer drew Verdant's and Westhaven's
## beds as the dark speckle their notes measured the default at (hf95 82 at
## vs_road, 59 at wh_border_fg, against 42 and 38 in Forward+). A `value` trim
## is never lent: it was measured against one renderer's ground, and Verdant's
## Forward+ 1.6 drew near-white tips in the other.
static func _grass_value(id: String, key: String, fallback: Variant) -> Variant:
	var entries := region_section(id, "grass")
	var own_key := key + ("_forward" if forward_plus() else "_compat")
	var other_key := key + ("_compat" if forward_plus() else "_forward")
	if entries.has(own_key):
		return entries[own_key]
	if entries.has(key) or key == "value":
		return entries.get(key, fallback)
	return entries.get(other_key, fallback)

## How grassy a biome layer whose texture file is `file` (lower case) is:
## `id`'s own `grass.layers` words first, then GRASS_LAYER_WORDS, else
## GRASS_LAYER_DEFAULT.
static func grass_layer_value(id: String, file: String) -> float:
	var own: Variant = region_section(id, "grass").get("layers")
	if own is Dictionary:
		for word: String in own:
			if file.contains(word):
				return float(own[word])
	for word: String in GRASS_LAYER_WORDS:
		if file.contains(word):
			return float(GRASS_LAYER_WORDS[word])
	return GRASS_LAYER_DEFAULT

## The foliage list `key` (a FOLIAGE_DEFAULTS key) for `id`'s roots: every
## map's plus the names and words its file's `foliage` section adds.
static func foliage_words(id: String, key: String) -> Array:
	var own: Variant = region_section(id, "foliage").get(key)
	return own if own is Array else FOLIAGE_DEFAULTS[key]

## The words naming `id`'s signature materials (its file's `props.keep_words`,
## lower case), whose chroma the grade must not grey (LookFoliage.keep_chroma);
## empty for most regions.
static func keep_words(id: String) -> Array:
	var words: Variant = region_section(id, "props").get("keep_words")
	return words if words is Array else []

## The words naming `id`'s decorative ground patches (its file's
## `ground.keep_patches`, lower case, contained in the patch material's
## name): an inlay drawn in its own colour (LookGround.painted_for) rather
## than taken for a yard by its tint; empty for most regions.
static func keep_patches(id: String) -> Array:
	var words: Variant = region_section(id, "ground").get("keep_patches")
	return words if words is Array else []

## The words naming `id`'s landmarks that keep a hole round the player when
## they fade, never vanishing whole (its file's `props.hole_words`, lower
## case, contained in the occluding mesh's node name; LookFade.mode_of);
## empty for most regions.
static func hole_words(id: String) -> Array:
	var words: Variant = region_section(id, "props").get("hole_words")
	return words if words is Array else []

## The value a water shader at `shader_path` is decoded to in Forward+ on
## `id`'s map (its file's `water.decode_albedo`); 0 when it is not listed.
static func water_decode_value(id: String, shader_path: String) -> float:
	var table: Variant = region_section(id, "water").get("decode_albedo")
	return float((table as Dictionary).get(shader_path, 0.0)) if table is Dictionary else 0.0

## What is wrong with `id`'s file, one line each (nothing for a good file or
## none): what `region` warned about when it read it.
static func region_problems(id: String) -> PackedStringArray:
	var problems := PackedStringArray()
	var path := region_path(id)
	if id.is_empty() or not FileAccess.file_exists(path):
		return problems
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if parsed is not Dictionary:
		problems.append("%s is not a JSON object" % path)
		return problems
	typed_region(parsed as Dictionary, id, problems)
	return problems

static func _load_region(id: String) -> Dictionary:
	var data := {}
	var path := region_path(id)
	if not id.is_empty() and FileAccess.file_exists(path):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		var problems := PackedStringArray()
		if parsed is Dictionary:
			data = typed_region(parsed as Dictionary, id, problems)
		else:
			problems.append("%s is not a JSON object; the defaults are used" % path)
		for problem: String in problems:
			push_warning("look region %s: %s" % [id, problem])
	data.make_read_only()
	return data

## A parsed region file as the code reads it: colours made Colors, numbers
## floats (JSON gives every number as a float anyway, and an int never
## compares equal to one inside an Array), foliage lists merged with
## FOLIAGE_DEFAULTS. Unknown sections and keys and values of the wrong kind
## are left out and listed in `problems`.
static func typed_region(raw: Dictionary, id: String, problems: PackedStringArray) -> Dictionary:
	var data := {}
	for section_key: Variant in raw:
		var section := str(section_key)
		var content: Variant = raw[section_key]
		if section in REGION_META_KEYS:
			if section == "id" and str(content) != id:
				problems.append("its id \"%s\" is not its file's name" % str(content))
			data[section] = content
			continue
		if not REGION_SECTIONS.has(section):
			problems.append("unknown section \"%s\"" % section)
			continue
		if content is not Dictionary:
			problems.append("section \"%s\" is not an object" % section)
			continue
		var entries := {}
		for entry_key: Variant in content:
			var key := str(entry_key)
			var bare := _bare_key(key)
			var where := "%s.%s" % [section, key]
			if bare not in REGION_SECTIONS[section]:
				problems.append("unknown key \"%s\"" % where)
				continue
			if bare != key and bare in REGION_TABLE_KEYS:
				problems.append("\"%s\" is a table and takes no renderer suffix" % where)
				continue
			var value: Variant = _typed_value(section, bare, (content as Dictionary)[entry_key])
			if value == null:
				problems.append("\"%s\" is not a %s" % [where, _expected(section, bare)])
				continue
			entries[key] = value
		entries.make_read_only()
		data[section] = entries
	return data

## `key` without a renderer suffix.
static func _bare_key(key: String) -> String:
	for suffix: String in ["_forward", "_compat"]:
		if key.ends_with(suffix):
			return key.trim_suffix(suffix)
	return key

static func _expected(section: String, bare: String) -> String:
	if bare in REGION_COLOUR_KEYS:
		return "colour ([r, g, b] or \"#rrggbb\")"
	if bare == "layers" or bare == "decode_albedo":
		return "table of numbers"
	if bare == "class_textures":
		return "table of %s to class texture names" % [CLASS_TEXTURE_SLOTS]
	if section == "foliage" or bare == "keep_words" or bare == "keep_patches" or bare == "hole_words":
		return "list of strings"
	return "number"

## `value` as `section.bare` holds it, or null when it is the wrong kind.
static func _typed_value(section: String, bare: String, value: Variant) -> Variant:
	if bare in REGION_COLOUR_KEYS:
		if value is String and Color.html_is_valid(value as String):
			return Color.html(value as String)
		if value is Array and (value as Array).size() in [3, 4]:
			var parts := value as Array
			for part: Variant in parts:
				if part is not float and part is not int:
					return null
			return Color(float(parts[0]), float(parts[1]), float(parts[2]),
				float(parts[3]) if parts.size() == 4 else 1.0)
		return null
	if bare == "class_textures":
		if value is not Dictionary:
			return null
		var slots := {}
		for slot: Variant in value:
			var texture_name: Variant = (value as Dictionary)[slot]
			if str(slot) not in CLASS_TEXTURE_SLOTS or texture_name is not String \
					or not CLASS_TEXTURES.has(texture_name):
				return null
			slots[str(slot)] = texture_name
		slots.make_read_only()
		return slots
	if bare == "layers" or bare == "decode_albedo":
		if value is not Dictionary:
			return null
		var table := {}
		for word: Variant in value:
			var weight: Variant = (value as Dictionary)[word]
			if weight is not float and weight is not int:
				return null
			table[str(word)] = float(weight)
		table.make_read_only()
		return table
	if bare == "keep_words" or bare == "keep_patches" or bare == "hole_words":
		if value is not Array:
			return null
		var words: Array = []
		for word: Variant in value:
			if word is not String:
				return null
			words.append((word as String).to_lower())
		words.make_read_only()
		return words
	if section == "foliage":
		if value is not Array:
			return null
		var merged: Array = (FOLIAGE_DEFAULTS[bare] as Array).duplicate()
		for word: Variant in value:
			if word is not String:
				return null
			if word not in merged:
				merged.append(word)
		merged.make_read_only()
		return merged
	if value is float or value is int:
		return float(value)
	return null

static func _warn_once(key: String, message: String) -> void:
	if _warned.has(key):
		return
	_warned[key] = true
	push_warning(message)
