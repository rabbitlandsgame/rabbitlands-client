class_name LookGrade
extends RefCounted
## Look pass layer L1: a base grade and light over whatever the manifest
## binders built. Does nothing unless LookProfile.enabled().
##
## WorldEnvironmentBinder builds the environment at bind; DayNightBinder then
## rewrites the sun, the ambient, the sky and the fog colour on every clock
## packet and slow refresh, and main's border update rewrites fog density and
## saturation every 100 ms on a streamed continent. A grade applied once would
## be gone within a tenth of a second, so main calls this straight after each
## of those rewrites, and it has to be safe to call any number of times.
##
## Values the grade sets outright (tone curve, adjustments, fog shape, screen
## effects) are idempotent by nature. Values it scales (sun colour and energy,
## ambient colour, energy and sky share) remember the ungraded value they
## scaled and what they wrote. If the property still holds what the grade
## wrote, nobody has rewritten it since, and the remembered ungraded value is
## scaled again rather than the graded one; so the grade never compounds, even
## on a map whose hour does not drive its light.
##
## Only outdoor daylight maps are graded: an interior declares no sun, or a
## disabled one, and its lamps are its whole lighting.

static func apply(lighting: WorldManifest, world_environment: WorldEnvironment,
		sun: DirectionalLight3D) -> bool:
	if not LookProfile.enabled() or lighting == null or world_environment == null:
		return false
	var environment: Environment = world_environment.environment
	var raw: Variant = lighting.data.get("environment")
	if environment == null or raw is not Dictionary:
		return false
	var declared: Dictionary = raw as Dictionary
	var declared_sun: Variant = declared.get("sun")
	if declared_sun is not Dictionary or not bool(
			(declared_sun as Dictionary).get("enabled", true)):
		return false
	_grade_tone(environment, declared, lighting.asset_id(),
		lighting.data.has("continentGeography"))
	_grade_ambient(environment)
	_grade_fog(environment, declared)
	_grade_screen_space(environment)
	if sun != null:
		_grade_key(sun)
	return true

## `map_id`'s region file may trim the exposure and saturation (its `grade`
## section), unless it is a `continent` region, which shares one grade.
static func _grade_tone(environment: Environment, declared: Dictionary,
		map_id: String, continent := false) -> void:
	var curve: Dictionary = LookProfile.tonemap_curve()
	environment.tonemap_mode = int(curve.mode) as Environment.ToneMapper
	environment.tonemap_exposure = float(curve.exposure) \
		* LookProfile.map_trim(map_id, "exposure", continent) * LookProfile.renderer_exposure()
	environment.tonemap_white = float(curve.white)
	# A map's `grade.background` scales what the camera sees behind its world
	# (its sky or background colour): an interior whose void is meant dark
	# but whose floor needs an exposure trim (the Ssarathi archive, 1.4) had
	# its void lifted with the floor (luminance 48 to 71).
	environment.background_energy_multiplier = LookProfile.map_trim(map_id, "background",
		continent)
	if curve.has("agx_white"):
		environment.tonemap_agx_white = float(curve.agx_white)
		environment.tonemap_agx_contrast = float(curve.get("agx_contrast_forward",
			curve.agx_contrast)) if LookProfile.forward_plus() else float(curve.agx_contrast)
	# Main's border update writes the manifest's raw saturation here every
	# 100 ms, but nothing ever enabled the adjustment, so it has never shown.
	# The grade enables it and replaces the raw boost with a tempered one.
	environment.adjustment_enabled = true
	environment.adjustment_brightness = 1.0
	environment.adjustment_contrast = LookProfile.CONTRAST
	environment.adjustment_color_correction = toe_curve()
	environment.adjustment_saturation = LookProfile.saturation(
		float(_number(declared.get("saturation"), 1.0))) \
		* LookProfile.map_trim(map_id, "saturation", continent)

## The toe (LookProfile.TOE_LIFT, TOE_END) as the per-channel lookup the
## environment's colour correction applies to display values after the curve;
## null when the toe is off. Built once: the grade is re-applied every 100 ms.
static func toe_curve() -> ImageTexture:
	if LookProfile.TOE_LIFT <= 0.0:
		return null
	if _toe == null:
		var size := 256
		var image := Image.create_empty(size, 1, false, Image.FORMAT_RGB8)
		for index: int in size:
			var value := float(index) / float(size - 1)
			var lift := 0.0
			if value < LookProfile.TOE_END:
				lift = LookProfile.TOE_LIFT * pow(1.0 - value / LookProfile.TOE_END, 2.0)
			var lifted := clampf(value + lift, 0.0, 1.0)
			image.set_pixel(index, 0, Color(lifted, lifted, lifted))
		_toe = ImageTexture.create_from_image(image)
	return _toe

static var _toe: ImageTexture = null

static func _grade_ambient(environment: Environment) -> void:
	var colour: Color = _ungraded(environment, &"ambient_light_color")
	_set_graded(environment, &"ambient_light_color",
		colour.lerp(LookProfile.AMBIENT_COOL, LookProfile.AMBIENT_COOL_SHARE))
	var energy: float = _ungraded(environment, &"ambient_light_energy")
	_set_graded(environment, &"ambient_light_energy",
		energy * LookProfile.AMBIENT_ENERGY_SCALE)
	if environment.ambient_light_source == Environment.AMBIENT_SOURCE_SKY:
		var share: float = _ungraded(environment, &"ambient_light_sky_contribution")
		_set_graded(environment, &"ambient_light_sky_contribution",
			share * LookProfile.AMBIENT_SKY_SHARE)

static func _grade_fog(environment: Environment, declared: Dictionary) -> void:
	if not environment.fog_enabled:
		return
	var fog: Variant = declared.get("fog")
	var density: float = 0.0
	if fog is Dictionary:
		density = _number((fog as Dictionary).get("density"), 0.0)
	environment.fog_mode = Environment.FOG_MODE_DEPTH
	environment.fog_depth_begin = LookProfile.FOG_BEGIN
	environment.fog_depth_end = LookProfile.FOG_END
	environment.fog_depth_curve = LookProfile.FOG_CURVE
	# In depth mode the density is the haze at FOG_END, not a rate.
	environment.fog_density = LookProfile.fog_density(density)
	environment.fog_aerial_perspective = LookProfile.FOG_AERIAL_PERSPECTIVE
	environment.fog_sky_affect = LookProfile.FOG_SKY_AFFECT

static func _grade_screen_space(environment: Environment) -> void:
	if LookProfile.screen_space_effects():
		environment.ssao_enabled = LookProfile.ssao_enabled()
		environment.ssao_radius = LookProfile.SSAO_RADIUS
		environment.ssao_intensity = LookProfile.SSAO_INTENSITY
		environment.ssao_power = LookProfile.SSAO_POWER
		environment.ssao_detail = LookProfile.SSAO_DETAIL
		environment.ssao_light_affect = LookProfile.SSAO_LIGHT_AFFECT
		environment.ssil_enabled = LookProfile.ssil_enabled()
		environment.ssil_radius = LookProfile.SSIL_RADIUS
		environment.ssil_intensity = LookProfile.SSIL_INTENSITY
	# Set outright either way: a lower graphics quality turns off what a higher
	# one turned on in the same environment.
	environment.glow_enabled = LookProfile.glow_enabled()
	environment.glow_intensity = LookProfile.GLOW_INTENSITY
	environment.glow_strength = LookProfile.GLOW_STRENGTH
	environment.glow_bloom = LookProfile.GLOW_BLOOM
	environment.glow_hdr_threshold = LookProfile.GLOW_HDR_THRESHOLD
	environment.glow_blend_mode = LookProfile.GLOW_BLEND_MODE

static func _grade_key(sun: DirectionalLight3D) -> void:
	var colour: Color = _ungraded(sun, &"light_color")
	_set_graded(sun, &"light_color", colour * LookProfile.sun_warmth())
	var energy: float = _ungraded(sun, &"light_energy")
	_set_graded(sun, &"light_energy", energy * LookProfile.SUN_ENERGY_SCALE)

## Gives the key light back the colour and energy the binders last gave it,
## for LookSwitch when the look is switched off. The environment is rebound
## from develop's own copy instead (main), but the sun is the scene's one
## light and outlives every map, and on a map whose hour does not drive it
## nothing else would ever rewrite the warmed values. A property a binder has
## rewritten since the grade (it no longer holds what the grade wrote) is left
## as it is. Safe to call on a sun the grade never touched.
static func revert_key(sun: DirectionalLight3D) -> void:
	if sun == null:
		return
	for property: StringName in [&"light_color", &"light_energy"]:
		var graded_key := StringName("look_graded_" + property)
		var original_key := StringName("look_ungraded_" + property)
		if sun.has_meta(graded_key) and sun.get_meta(graded_key) == sun.get(property) \
				and sun.has_meta(original_key):
			sun.set(property, sun.get_meta(original_key))
		if sun.has_meta(graded_key):
			sun.remove_meta(graded_key)
		if sun.has_meta(original_key):
			sun.remove_meta(original_key)

## The value `property` had before the grade scaled it. If it still holds what
## the grade last wrote, nothing has rewritten it and the remembered original
## is returned; otherwise a binder has written a fresh value, which becomes the
## new original.
static func _ungraded(owner: Object, property: StringName) -> Variant:
	var current: Variant = owner.get(property)
	var graded_key := StringName("look_graded_" + property)
	var original_key := StringName("look_ungraded_" + property)
	if owner.has_meta(graded_key) and owner.get_meta(graded_key) == current:
		return owner.get_meta(original_key)
	owner.set_meta(original_key, current)
	return current

## Writes a graded value and remembers it as read back, so the float precision
## of the property's storage cannot make the next `_ungraded` miss it.
static func _set_graded(owner: Object, property: StringName, value: Variant) -> void:
	owner.set(property, value)
	owner.set_meta(StringName("look_graded_" + property), owner.get(property))

static func _number(value: Variant, fallback: float) -> float:
	if value is float or value is int:
		return float(value)
	return fallback
