class_name WeatherSky
extends RefCounted
## What rain does to the light: a weathered copy of a lighting manifest.
##
## The server's rain only ever reached the particles, so a storm over Ravenhead
## fell out of the same bright blue sky, under the same hard sun and the same
## clear haze, as a fine noon in Landfall. This takes the manifest the binders
## are about to apply and turns it towards an overcast one, in proportion to
## how wet it is (`Weather3D.overcast`, 0 dry to 1 a full storm): the sky and
## the haze greyed and darkened, the sun dimmed and cooled, the haze thicker,
## the colours a little flatter. The night and twilight variants are greyed
## the same way, so a wet dusk does not glow orange.
##
## Nothing is decided here: how wet it is comes from what the server said is
## falling. And nothing is stored: DayNightBinder, LookGrade and LookSky read
## the copy exactly as they read the manifest, so the painted sky judges a
## grey zenith overcast on its own (LookSky.clearness) and draws its clouds in
## the horizon's colour.

## How far each colour is taken towards its overcast grey at a full storm.
## The sky and the haze go by the square root of the wet: the painted sky
## reads a zenith as overcast only below a saturation of 0.3-0.5
## (LookProfile.SKY_CLEAR_SATURATION), so a linear grey left a storm's sky
## half clear; this way a light shower keeps a bright sunshower sky and heavy
## rain and storms go grey.
const SKY_GREY := 0.95
const FOG_GREY := 0.8
## The overcast grey is the colour's own value times this, with a cool cast:
## rain light is blue-grey, never neutral or warm.
const SKY_DARKEN := 0.78
const OVERCAST_TINT := Color(0.86, 0.92, 1.0)
## What a full storm leaves of the sun's energy, its ambient and its saturation.
const SUN_LEFT := 0.42
const AMBIENT_LEFT := 0.82
const SATURATION_LEFT := 0.72
## How much thicker the haze is at a full storm.
const FOG_THICKER := 2.6
## The sun's colour at a full storm: the warmth goes first.
const SUN_GREY := 0.6

## The manifest as the weather leaves it. `wet` is 0..1; at 0 (or with no
## environment to weather) the manifest itself is returned, untouched.
static func weathered(lighting: WorldManifest, wet: float) -> WorldManifest:
	if lighting == null or wet <= 0.001:
		return lighting
	var declared: Variant = lighting.data.get("environment")
	if declared is not Dictionary:
		return lighting
	var copy := WorldManifest.new()
	copy.source_path = lighting.source_path
	copy.data = lighting.data.duplicate()
	copy.data["environment"] = weather_environment(declared as Dictionary, clampf(wet, 0.0, 1.0))
	return copy

## The environment block at `wet`, as a new dictionary.
static func weather_environment(declared: Dictionary, wet: float) -> Dictionary:
	var result: Dictionary = declared.duplicate(true)
	_grey_block(result, wet)
	var variants: Variant = result.get("variants")
	if variants is Dictionary:
		for name: Variant in (variants as Dictionary).keys():
			var variant: Variant = (variants as Dictionary)[name]
			if variant is Dictionary:
				_grey_block(variant as Dictionary, wet)
	var sun: Variant = result.get("sun")
	if sun is Dictionary:
		var block: Dictionary = sun as Dictionary
		block["energy"] = float(block.get("energy", 1.0)) * lerpf(1.0, SUN_LEFT, wet)
	var ambient: Variant = result.get("ambient")
	if ambient is Dictionary:
		var block: Dictionary = ambient as Dictionary
		block["energy"] = float(block.get("energy", 0.85)) * lerpf(1.0, AMBIENT_LEFT, wet)
	var fog: Variant = result.get("fog")
	if fog is Dictionary:
		var block: Dictionary = fog as Dictionary
		if block.has("density"):
			block["density"] = float(block["density"]) * lerpf(1.0, FOG_THICKER, wet)
	result["saturation"] = float(result.get("saturation", 1.0)) * lerpf(1.0, SATURATION_LEFT, wet)
	return result

## Greys the sky, fog and sun colours of one block (the environment itself or
## one of its variants), in whichever spelling the block uses.
static func _grey_block(block: Dictionary, wet: float) -> void:
	var sky: Variant = block.get("sky")
	if sky is Dictionary:
		for key: String in ["zenith", "topColor", "horizon", "horizonColor",
				"groundHorizon"]:
			_grey(sky as Dictionary, key, sqrt(wet) * SKY_GREY)
	var fog: Variant = block.get("fog")
	if fog is Dictionary:
		_grey(fog as Dictionary, "color", sqrt(wet) * FOG_GREY)
	var sun: Variant = block.get("sun")
	if sun is Dictionary:
		_grey(sun as Dictionary, "color", wet * SUN_GREY)

static func _grey(block: Dictionary, key: String, amount: float) -> void:
	if not block.has(key):
		return
	var colour := DayNightBinder._colour(block[key], Color.WHITE)
	var value := colour.get_luminance() * SKY_DARKEN
	var grey := Color(value, value, value) * OVERCAST_TINT
	var weathered := colour.lerp(Color(grey.r, grey.g, grey.b, colour.a), amount)
	block[key] = [weathered.r, weathered.g, weathered.b]
