class_name WeatherSky
extends RefCounted
## What the weather does to the light: a weathered copy of a lighting manifest.
##
## The server's rain only ever reached the particles, so a storm over Ravenhead
## fell out of the same bright blue sky, under the same hard sun and the same
## clear haze, as a fine noon in Landfall. This takes the manifest the binders
## are about to apply and weathers it by the look the sky shows
## (Weather3D.look): cloud greys and darkens the sky and takes the warmth off
## the sun, fog thickens and greys the haze, darkness dims the sun and the
## ambient, and anything falling flattens the colours. The night and twilight
## variants are greyed the same way, so a wet dusk does not glow orange.
##
## Nothing is decided here: the look is what the server said the sky is. And
## nothing is stored: DayNightBinder, LookGrade and LookSky read the copy
## exactly as they read the manifest, so the painted sky judges a grey zenith
## overcast on its own (LookSky.clearness) and draws its clouds in the
## horizon's colour.

## How far the sky and the haze are taken towards their overcast grey at full
## cover. They go by the square root: the painted sky reads a zenith as
## overcast only below a saturation of 0.3-0.5 (LookProfile.SKY_CLEAR_
## SATURATION), so a linear grey left a storm's sky half clear.
const SKY_GREY := 0.95
const FOG_GREY := 0.8
## Cloud below this cover leaves the sky its own colour: a partly cloudy day
## is a blue one with clouds in it, and the painted sky draws those.
const CLOUD_GREY_FROM := 0.35
## The overcast grey is the colour's own value times this, with a cool cast:
## rain light is blue-grey, never neutral or warm.
const SKY_DARKEN := 0.78
const OVERCAST_TINT := Color(0.86, 0.92, 1.0)
## The sun's energy at full darkness, and the ambient's.
const SUN_LEFT_DARK := 0.03
const AMBIENT_LEFT_DARK := 0.7
## How much thicker the haze is in a full fog: the density is multiplied by
## 1 + FOG_THICKER * fog squared, so a shower's haze thickens a little and a
## fog bank closes the view.
const FOG_THICKER := 9.0
## The sun's colour under full cloud: the warmth goes first.
const SUN_GREY := 0.6
## What full cloud or rain leaves of the colour's saturation.
const SATURATION_LEFT := 0.72

## The manifest under a single wetness (0 dry to 1 a full storm): the look of
## a storm scaled by it. Kept for callers that have only that number.
static func weathered(lighting: WorldManifest, wet: float) -> WorldManifest:
	var w := clampf(wet, 0.0, 1.0)
	return weathered_look(lighting, {"precipitation": w, "clouds": w, "fog": w * 0.4,
		"darkness": w * 0.6})

## The manifest as the shown look leaves it. With nothing in the look (or no
## environment to weather) the manifest itself is returned, untouched.
static func weathered_look(lighting: WorldManifest, look: Dictionary) -> WorldManifest:
	if lighting == null:
		return lighting
	var clouds := clampf(float(look.get("clouds", 0.0)), 0.0, 1.0)
	var fog := clampf(float(look.get("fog", 0.0)), 0.0, 1.0)
	var darkness := clampf(float(look.get("darkness", 0.0)), 0.0, 1.0)
	var falling := clampf(float(look.get("precipitation", 0.0)), 0.0, 1.0)
	var cover := maxf(smoothstep(CLOUD_GREY_FROM, 1.0, clouds), falling * 0.8)
	if cover <= 0.001 and fog <= 0.001 and darkness <= 0.001:
		return lighting
	var declared: Variant = lighting.data.get("environment")
	if declared is not Dictionary:
		return lighting
	var copy := WorldManifest.new()
	copy.source_path = lighting.source_path
	copy.data = lighting.data.duplicate()
	copy.data["environment"] = weather_environment(declared as Dictionary,
		cover, fog, darkness, falling)
	return copy

## The environment block under the weather, as a new dictionary: `cover`
## greys the sky, `fog` the haze, `darkness` dims, `falling` flattens.
static func weather_environment(declared: Dictionary, cover: float, fog := 0.0,
		darkness := -1.0, falling := -1.0) -> Dictionary:
	if darkness < 0.0:
		darkness = cover * 0.6
	if falling < 0.0:
		falling = cover
	var result: Dictionary = declared.duplicate(true)
	_grey_block(result, cover, fog)
	var variants: Variant = result.get("variants")
	if variants is Dictionary:
		for name: Variant in (variants as Dictionary).keys():
			var variant: Variant = (variants as Dictionary)[name]
			if variant is Dictionary:
				_grey_block(variant as Dictionary, cover, fog)
	var sun: Variant = result.get("sun")
	if sun is Dictionary:
		var block: Dictionary = sun as Dictionary
		block["energy"] = float(block.get("energy", 1.0)) * lerpf(1.0, SUN_LEFT_DARK, darkness)
	var ambient: Variant = result.get("ambient")
	if ambient is Dictionary:
		var block: Dictionary = ambient as Dictionary
		block["energy"] = float(block.get("energy", 0.85)) * lerpf(1.0, AMBIENT_LEFT_DARK, darkness)
	var haze: Variant = result.get("fog")
	if haze is Dictionary:
		var block: Dictionary = haze as Dictionary
		if block.has("density"):
			block["density"] = float(block["density"]) * (1.0 + FOG_THICKER * fog * fog)
	result["saturation"] = float(result.get("saturation", 1.0)) \
		* lerpf(1.0, SATURATION_LEFT, maxf(cover, maxf(falling, fog * 0.6)))
	return result

## Greys the sky, fog and sun colours of one block (the environment itself or
## one of its variants), in whichever spelling the block uses.
static func _grey_block(block: Dictionary, cover: float, fog: float) -> void:
	var sky: Variant = block.get("sky")
	if sky is Dictionary:
		for key: String in ["zenith", "topColor", "horizon", "horizonColor",
				"groundHorizon"]:
			_grey(sky as Dictionary, key, sqrt(cover) * SKY_GREY)
	var haze: Variant = block.get("fog")
	if haze is Dictionary:
		_grey(haze as Dictionary, "color", sqrt(maxf(cover, fog)) * FOG_GREY)
	var sun: Variant = block.get("sun")
	if sun is Dictionary:
		_grey(sun as Dictionary, "color", cover * SUN_GREY)

static func _grey(block: Dictionary, key: String, amount: float) -> void:
	if not block.has(key) or amount <= 0.0:
		return
	var colour := DayNightBinder._colour(block[key], Color.WHITE)
	var value := colour.get_luminance() * SKY_DARKEN
	var grey := Color(value, value, value) * OVERCAST_TINT
	var weathered := colour.lerp(Color(grey.r, grey.g, grey.b, colour.a), amount)
	block[key] = [weathered.r, weathered.g, weathered.b]
