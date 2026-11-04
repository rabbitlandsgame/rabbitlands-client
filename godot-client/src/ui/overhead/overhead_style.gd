extends RefCounted
## The numbers the 2D overhead layer draws with (src/ui/overhead/, wave 2 OV-1).
##
## Overhead text - names, titles, health rows, status icons, quest marks,
## speech, the combat pointer and the world labels - is drawn today as Label3D
## and billboard quads on render layer 20, by a second camera in a native-size
## SubViewport (src/ui/world_text_overlay.gd). The overhead layer draws the
## same content as retained 2D canvas items over the game view instead. Until
## the switch-over (OV-3 for actors, OV-5 for world labels) nothing draws
## through it, so this file only states the numbers both paths share.
##
## Design pixels. A fixed-size Label3D scales by its own view depth, which
## cancels the perspective divide: one unit of `pixel_size` covers
## `P[1][1] * H / 2` pixels of an H-pixel-tall view at any depth. A "design
## pixel" here is one OVERHEAD_PIXEL of that, so on the 50-degree gameplay
## camera it is H / 720 native pixels: one canvas unit of the 1280x720 design
## at UI scale 100 % on 16:9-or-wider windows (1.333 canvas units on 4:3). The
## Label3D raster factor (world_label_style.gd RASTER_SCALE) is not part of a
## design pixel: the 2D layer rasterises glyphs at their final size instead.
##
## Const-only apart from two pure helpers: nothing here holds state.

## One design pixel in Label3D `pixel_size` units: `2 * tan(25 degrees) / 720`.
## The same number as ReplicatedActor3D.OVERHEAD_PIXEL (tests/test_overhead_layer.gd
## pins every constant below that has a ReplicatedActor3D twin).
const OVERHEAD_PIXEL := 0.0012953

# Font sizes and the banner block, in design pixels, copied from
# ReplicatedActor3D (src/actors/replicated_actor_3d.gd) where the 3D banner
# still reads them; OV-3 makes the actor re-export these instead.
const NAMEPLATE_FONT_SIZE := 12
const HEALTH_NUMBER_FONT_SIZE := 11
const SPEECH_BUBBLE_FONT_SIZE := 15
const TITLE_FONT_SIZE := 10
const OCCUPATION_FONT_SIZE := 10
const OVERHEAD_OUTLINE_SIZE := 4
const HEALTH_BAR_WIDTH := 56.0
const HEALTH_BAR_THICKNESS := 7.0
const HEALTH_BAR_BORDER := 2.0
const HEALTH_BAR_BACKING := Color(0.05, 0.04, 0.03, 0.78)
const HEALTH_BAR_DROP := 16.0
const HEALTH_LABEL_DROP := HEALTH_BAR_DROP
const HEALTH_NUMBER_GAP := 5.0
const OVERHEAD_BACKING := Color(0.0, 0.0, 0.0, 0.45)
const NEGATIVE_STATUS_SIZE := 20.0
const NEGATIVE_STATUS_GAP := 3.0
const NEGATIVE_STATUS_RISE := 24.0
const SPEECH_BUBBLE_RISE := 28.0
const SPEECH_BUBBLE_WIDTH := 270.0
const SPEECH_BUBBLE_TEXT := Color(0.96, 0.91, 0.78, 1.0)
const SPEECH_BUBBLE_SURROUND := Color(0.035, 0.026, 0.018, 0.94)
## Speech outline (design pixels): the dark surround that stands in for a bubble.
const SPEECH_OUTLINE_SIZE := 6
const TITLE_RISE := 12.0
const OCCUPATION_DROP := 12.0
const OCCUPATION_COLOUR := Color(0.78, 0.76, 0.68, 1.0)

## Quest offer "!" (replicated_actor_3d.gd set_quest_available): 30 px with a
## 2 px brown outline, bobbing between 36 and 42 design pixels above the name
## and pulsing to `lightened(0.35)` and back, 0.8 s each way. The Tween eases
## the rise with TRANS_SINE (in-out) and fades the colour linearly; the layer
## evaluates the same curves from a start time (OverheadItem.set_pulse).
const QUEST_FONT_SIZE := 30
const QUEST_OUTLINE_SIZE := 2
const QUEST_OUTLINE := Color(0.28, 0.13, 0.01)
const QUEST_RISE_FROM := 36.0
const QUEST_RISE_TO := 42.0
const QUEST_LIGHTEN := 0.35
const QUEST_PULSE_HALF_SECONDS := 0.8

## Combat target pointer (combat_target_marker_3d.gd): a 48-point "▼" at
## pixel_size 0.00075, without the raster factor, 0.75 m over the head.
## POINTER_PIXEL / OVERHEAD_PIXEL is its design scale (design_scale()).
const POINTER_PIXEL := 0.00075
const POINTER_FONT_SIZE := 48
const POINTER_OUTLINE_SIZE := 6
const POINTER_LIFT := 0.75

# Passes, by today's effective render priorities. Godot sorts every
# transparent draw by priority before depth, so all backings of all actors draw
# before any bar, and every text outline before any letter: the cross-actor
# overlap order of docs/crowd-presentation-optimization.md "Rendering review
# constraints". The layer keeps one canvas-item parent per pass (LAYERED) to
# reproduce it. WORLD_LABEL_STYLE.apply puts every label at 10/11, the
# numbers label included; the pointer keeps the Label3D defaults -1/0.
const PASS_POINTER_OUTLINE := -1
const PASS_BACKING := 0
const PASS_BAR_BACK := 1
const PASS_BAR_FILL := 2
const PASS_ICONS := 4
const PASS_TEXT_OUTLINE := 10
const PASS_TEXT := 11
## Every pass, in draw order. The pointer's fill shares PASS_BACKING (priority 0).
const PASSES: Array[int] = [PASS_POINTER_OUTLINE, PASS_BACKING, PASS_BAR_BACK,
	PASS_BAR_FILL, PASS_ICONS, PASS_TEXT_OUTLINE, PASS_TEXT]

## Overlap order (owner option O2). LAYERED: one parent per pass, as today.
## PER_BANNER: one canvas item per item holding all its passes, so a nearer
## banner covers a farther one completely; one transform call per item.
const ORDER_LAYERED := 0
const ORDER_PER_BANNER := 1

## Text shaping per frame (microseconds); at least one shape always runs.
const SHAPE_BUDGET_USEC := 500
## Re-recording changed items per frame (microseconds); at least one always runs.
const RERECORD_BUDGET_USEC := 1000
## A changed raster scale (window resize, UI scale, a campaign FOV lerp) is
## followed by the transform at once and re-rasterised once it has held this long.
const SCALE_SETTLE_USEC := 250000
## Glyph raster scales are quantised to this step to bound glyph-cache growth.
const OVERSAMPLING_STEP := 1.0 / 16.0
## A shaped text nobody draws is dropped after this long (microseconds).
const TEXT_IDLE_USEC := 10000000
## Items are culled once their extent is this far outside the layer (canvas units).
const CULL_MARGIN := 64.0

## The overhead font: the project fallback (Open Sans SemiBold), as
## WORLD_LABEL_STYLE.apply sets on every Label3D today.
static func font() -> Font:
	return ThemeDB.fallback_font

## A fixed-size Label3D's `pixel_size` in design pixels: 1.0 for the overhead
## block, POINTER_PIXEL / OVERHEAD_PIXEL for the pointer. Use the raw
## pixel_size a producer intends, not one WORLD_LABEL_STYLE.apply divided by
## its raster factor.
static func design_scale(pixel_size: float) -> float:
	return pixel_size / OVERHEAD_PIXEL

## Draw position of a pass among PASSES, or -1 for a pass that does not exist.
static func pass_index(pass_id: int) -> int:
	return PASSES.find(pass_id)
