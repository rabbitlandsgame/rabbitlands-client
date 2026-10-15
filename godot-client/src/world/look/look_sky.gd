class_name LookSky
extends RefCounted
## Look pass layer L5: a painted sky, and a haze that joins the far ground to
## it. Does nothing unless LookProfile.enabled().
##
## Develop draws the engine's procedural sky: a hard two-tone gradient that is
## deep blue almost down to the horizon, over a flat brown "ground" wherever
## nothing has loaded. A map without a sky (Lantern Reach) shows its flat
## background colour instead, which the grade lifts to a pale cyan wall. In a
## low view (the rig tilts up to -15 degrees) that is where the world visibly
## ends: the last streamed ground stops against a flat colour. The reference
## frames hide their edge the other way round: the far ground dissolves into a
## haze that is the sky's own horizon colour.
##
## So the sky's material is swapped for painted_sky.gdshader and the fog is
## given the horizon's colour. The swap happens once per bind, inside the Sky
## the binder already made (a map with a background colour gets a new Sky),
## before main's map cameras copy the environment, so the maps stay ungraded.
## The colours are then re-applied after every binder rewrite, like the grade,
## because the hour and the border blend move them.
##
## The painted sky draws develop's procedural sky into its radiance cubemap,
## so ambient and reflections are exactly what they were: only what the camera
## sees behind the world changes.
##
## The hour: DayNightBinder moves a procedural sky's colours towards night,
## but only while the material is a ProceduralSkyMaterial, so once painted this
## computes the same colours itself (`sky_colours`, checked against the binder
## in test_look_sky.gd) and gives them to the radiance pass unchanged.

const SHADER := preload("res://src/world/look/painted_sky.gdshader")
## The environment's painted sky material, set once it is installed.
const PAINTED_META := &"look_painted_sky"

## Installs the painted sky on a freshly bound outdoor map. Main calls this
## straight after WorldEnvironmentBinder.apply, before the map cameras take
## their copy of the environment. Safe to call again.
static func install(manifest: WorldManifest, world_environment: WorldEnvironment) -> bool:
	if not LookProfile.enabled() or not _outdoor(manifest) or world_environment == null \
			or not LookProfile.sky_painted(manifest.asset_id()):
		return false
	return _painted(world_environment.environment) != null

## Gives the painted sky and the haze the hour's and the border blend's
## colours. `lighting` is the (possibly blended) manifest the binders just
## applied and `minute` the game minute they applied it for.
static func apply(lighting: WorldManifest, world_environment: WorldEnvironment,
		minute: float) -> bool:
	if not LookProfile.enabled() or not _outdoor(lighting) or world_environment == null \
			or not LookProfile.sky_painted(lighting.asset_id()):
		return false
	var environment: Environment = world_environment.environment
	var material := _painted(environment)
	if material == null:
		return false
	var colours := sky_colours(lighting, minute)
	_update(material, &"radiance_top", colours.top)
	_update(material, &"radiance_horizon", colours.horizon)
	_update(material, &"look_zenith", colours.zenith)
	_update(material, &"look_horizon", colours.painted_horizon)
	_update(material, &"look_haze", colours.haze)
	_update(material, &"look_cloud_lit", colours.cloud_lit)
	_update(material, &"look_cloud_opacity", colours.cloud_opacity)
	_update(material, &"look_debug",
		OS.get_environment(LookProfile.SKY_DEBUG_VARIABLE).to_int())
	_haze(environment, lighting, colours.haze)
	return true

## The sky's colours at `minute`: `top` and `horizon` exactly as DayNightBinder
## would write them into a procedural sky (for the radiance pass), and the
## painted zenith, horizon, haze and cloud light derived from them.
static func sky_colours(lighting: WorldManifest, minute: float) -> Dictionary:
	var declared: Dictionary = {}
	var raw: Variant = lighting.data.get("environment")
	if raw is Dictionary:
		declared = raw as Dictionary
	var fallback := LookProfile.sky_fallback(lighting.asset_id())
	var declared_sky: Dictionary = {}
	if declared.get("sky") is Dictionary:
		declared_sky = declared.get("sky") as Dictionary
	var top := _colour(_either(declared_sky, "topColor", "zenith"), fallback.top)
	var horizon := _colour(_either(declared_sky, "horizonColor", "horizon"),
		fallback.horizon)
	var light := 1.0
	if DayNightBinder.drives(lighting):
		light = DayNightBinder.daylight(minute)
		var edge := DayNightBinder.twilight(minute)
		top = top.lerp(DayNightBinder.NIGHT_SKY_TOP, 1.0 - light)
		horizon = horizon.lerp(DayNightBinder.NIGHT_SKY_HORIZON, 1.0 - light) \
			.lerp(DayNightBinder.DAWN_SUN_COLOUR, edge * 0.35)
	# The painted sky is warmed by daylight only: at night it keeps the
	# binder's moonlit colours. And only a clear sky is taken towards the
	# painted blue day: a dusk, an overcast or a storm the region declared
	# keeps its own colours, its clouds take its horizon's and thin out.
	var clear := clearness(lighting, declared_sky, fallback.top) * light
	var zenith := top.lerp(LookProfile.SKY_ZENITH_DEEP, LookProfile.SKY_ZENITH_DEPTH * clear)
	var painted_horizon := horizon.lerp(LookProfile.SKY_WARM,
		LookProfile.SKY_HORIZON_WARMTH * clear)
	# `sky.haze_warmth` names a region's own (sw_isle's blue lagoon fog).
	var haze_warmth := float(LookProfile.region_value(lighting.asset_id().get_slice("__chunk_", 0), "sky",
		"haze_warmth", LookProfile.SKY_HAZE_WARMTH))
	var haze := painted_horizon.lerp(LookProfile.SKY_WARM,
		haze_warmth * clear).lightened(LookProfile.SKY_HAZE_LIFT * clear)
	if haze.v > LookProfile.SKY_HAZE_VALUE_MAX:
		haze = Color.from_hsv(haze.h, haze.s, LookProfile.SKY_HAZE_VALUE_MAX, haze.a)
	var cloud_lit := LookProfile.SKY_CLOUD_NIGHT.lerp(LookProfile.SKY_CLOUD_LIT, light)
	cloud_lit = cloud_lit.lerp(horizon.lightened(LookProfile.SKY_MOODY_CLOUD_LIFT),
		(1.0 - clear) * light)
	var cloud_opacity := LookProfile.SKY_CLOUD_OPACITY \
		* lerpf(LookProfile.SKY_MOODY_CLOUD_OPACITY, 1.0, clear)
	return {"top": top, "horizon": horizon, "zenith": zenith,
		"painted_horizon": painted_horizon, "haze": haze, "cloud_lit": cloud_lit,
		"cloud_opacity": cloud_opacity, "clear": clear, "light": light}

## How clear a sky is (0..1): 1 for a saturated blue zenith, 0 for a grey
## overcast, a violet dusk or a storm, judged on the region's declared zenith
## (or `fallback_top`, its region file's or the binder's, where it declares
## none) against LookProfile.SKY_CLEAR_SATURATION and SKY_CLEAR_HUE. On the
## continent the declared colours are blended across a border, so this is
## too; a map outside it may say outright (`sky.clear` in its region file).
## The painted day (a deep blue zenith, warm haze, bright cumulus) replaced
## the Amethyst Barrens' violet dusk (64, 57, 78) and the Grey Moors' overcast
## (92, 99, 103) with one bright cloudy day.
static func clearness(lighting: WorldManifest, declared_sky: Dictionary,
		fallback_top: Color) -> float:
	if not lighting.data.has("continentGeography"):
		var own: Variant = LookProfile.region_value(lighting.asset_id(), "sky", "clear", null)
		if own is float:
			return clampf(own as float, 0.0, 1.0)
	var zenith := _colour(_either(declared_sky, "topColor", "zenith"), fallback_top)
	var hue := zenith.h * 360.0
	var edge := LookProfile.SKY_CLEAR_HUE_EDGE
	var blue := smoothstep(LookProfile.SKY_CLEAR_HUE.x - edge, LookProfile.SKY_CLEAR_HUE.x, hue) \
		* (1.0 - smoothstep(LookProfile.SKY_CLEAR_HUE.y, LookProfile.SKY_CLEAR_HUE.y + edge, hue))
	return blue * smoothstep(LookProfile.SKY_CLEAR_SATURATION.x,
		LookProfile.SKY_CLEAR_SATURATION.y, zenith.s)

## The environment's painted sky material, installing it on first use: inside
## the binder's Sky in place of its procedural material, or in a new Sky on a
## map that only declared a background colour. Any other background (a custom
## sky, a canvas) is left alone.
static func _painted(environment: Environment) -> ShaderMaterial:
	if environment == null:
		return null
	if environment.has_meta(PAINTED_META):
		return environment.get_meta(PAINTED_META) as ShaderMaterial
	var material := ShaderMaterial.new()
	material.shader = SHADER
	_set_constants(material)
	var sky: Sky = environment.sky
	if environment.background_mode == Environment.BG_SKY and sky != null \
			and sky.sky_material is ProceduralSkyMaterial:
		var procedural := sky.sky_material as ProceduralSkyMaterial
		material.set_shader_parameter(&"radiance_top", procedural.sky_top_color)
		material.set_shader_parameter(&"radiance_horizon", procedural.sky_horizon_color)
		material.set_shader_parameter(&"radiance_curve", procedural.sky_curve)
		material.set_shader_parameter(&"radiance_sky_energy",
			procedural.sky_energy_multiplier)
		material.set_shader_parameter(&"radiance_ground_bottom",
			procedural.ground_bottom_color)
		material.set_shader_parameter(&"radiance_ground_horizon",
			procedural.ground_horizon_color)
		material.set_shader_parameter(&"radiance_ground_curve", procedural.ground_curve)
		material.set_shader_parameter(&"radiance_ground_energy",
			procedural.ground_energy_multiplier)
		material.set_shader_parameter(&"radiance_sun_angle_max",
			deg_to_rad(procedural.sun_angle_max))
		material.set_shader_parameter(&"radiance_sun_curve", procedural.sun_curve)
		material.set_shader_parameter(&"radiance_exposure", procedural.energy_multiplier)
		sky.sky_material = material
	elif environment.background_mode == Environment.BG_COLOR:
		# The flat colour stays the radiance, so a map lit and reflected by it
		# still is; the binder gives such a map a colour ambient, not the sky.
		material.set_shader_parameter(&"radiance_flat", true)
		material.set_shader_parameter(&"radiance_flat_colour",
			environment.background_color)
		var painted_sky := Sky.new()
		painted_sky.sky_material = material
		environment.sky = painted_sky
		environment.background_mode = Environment.BG_SKY
	else:
		return null
	environment.set_meta(PAINTED_META, material)
	return material

static func _set_constants(material: ShaderMaterial) -> void:
	material.set_shader_parameter(&"look_gradient_power", LookProfile.SKY_GRADIENT_POWER)
	material.set_shader_parameter(&"look_haze_height", LookProfile.SKY_HAZE_HEIGHT)
	material.set_shader_parameter(&"look_haze_depth", LookProfile.SKY_HAZE_DEPTH)
	material.set_shader_parameter(&"look_cloud_scale", LookProfile.SKY_CLOUD_SCALE)
	material.set_shader_parameter(&"look_cloud_stretch", LookProfile.SKY_CLOUD_STRETCH)
	material.set_shader_parameter(&"look_cloud_contrast", LookProfile.SKY_CLOUD_CONTRAST)
	material.set_shader_parameter(&"look_cloud_threshold", LookProfile.SKY_CLOUD_THRESHOLD)
	material.set_shader_parameter(&"look_cloud_softness", LookProfile.SKY_CLOUD_SOFTNESS)
	material.set_shader_parameter(&"look_cloud_opacity", LookProfile.SKY_CLOUD_OPACITY)
	material.set_shader_parameter(&"look_cloud_shade", LookProfile.SKY_CLOUD_SHADE)
	material.set_shader_parameter(&"look_cloud_band", LookProfile.SKY_CLOUD_BAND)
	material.set_shader_parameter(&"look_sun_glow", LookProfile.SKY_SUN_GLOW)
	material.set_shader_parameter(&"look_sun_halo", LookProfile.SKY_SUN_HALO)
	material.set_shader_parameter(&"look_sun_core", LookProfile.SKY_SUN_CORE)

## The haze: depth fog in the painted horizon's colour, on every outdoor map
## the sky is painted on, whether or not its manifest declared fog (Lantern
## Reach declares none, and its sea ran out against a flat wall). It replaces
## the grade's fog shape (layer L1), which leaves too little haze at the
## world's edge to hide it. Aerial perspective is off: it would mix in the
## radiance cubemap's colour, which is develop's sky, not the painted horizon
## the haze has to meet.
##
## A map's exposure trim (Lantern Reach's) reaches the sky and the haze as it
## reaches the ground. Divided back out of both, the island's sky went a dull
## grey-blue with its blue channel pinned from zenith to horizon; the trim
## mostly evens out the two renderers (the same painted zenith draws about
## the same in both under it), so the sky keeps it.
static func _haze(environment: Environment, lighting: WorldManifest, haze: Color) -> void:
	var declared_density := 0.0
	var environment_block: Variant = lighting.data.get("environment")
	if environment_block is Dictionary:
		var fog: Variant = (environment_block as Dictionary).get("fog")
		if fog is Dictionary:
			var density: Variant = (fog as Dictionary).get("density")
			if density is float or density is int:
				declared_density = float(density)
	environment.fog_enabled = true
	environment.fog_mode = Environment.FOG_MODE_DEPTH
	environment.fog_depth_begin = LookProfile.HAZE_BEGIN
	environment.fog_depth_end = LookProfile.HAZE_END
	environment.fog_depth_curve = LookProfile.HAZE_CURVE
	environment.fog_density = LookProfile.haze_density(declared_density)
	environment.fog_light_color = haze
	environment.fog_light_energy = 1.0
	environment.fog_aerial_perspective = 0.0
	environment.fog_sky_affect = LookProfile.HAZE_SKY_AFFECT
	environment.fog_sun_scatter = 0.0

## Sets a shader parameter only when it changed: a write can mark the sky
## dirty, and a dirty sky re-renders its radiance cubemap. The border update
## re-applies these ten times a second.
static func _update(material: ShaderMaterial, parameter: StringName, value: Variant) -> void:
	if material.get_shader_parameter(parameter) != value:
		material.set_shader_parameter(parameter, value)

## Outdoor daylight maps only, as the grade: an interior declares no sun, or a
## disabled one, and has no sky to paint.
static func _outdoor(manifest: WorldManifest) -> bool:
	if manifest == null:
		return false
	var raw: Variant = manifest.data.get("environment")
	if raw is not Dictionary:
		return false
	var sun: Variant = (raw as Dictionary).get("sun")
	return sun is Dictionary and bool((sun as Dictionary).get("enabled", true))

static func _either(block: Dictionary, canonical: String, alias: String) -> Variant:
	if block.has(canonical):
		return block.get(canonical)
	return block.get(alias)

## A manifest colour, in either spelling the binders accept (an array of
## channels or a hex string).
static func _colour(value: Variant, fallback: Color) -> Color:
	if value is String:
		return Color(value as String)
	if value is Array and (value as Array).size() >= 3:
		var channels: Array = value as Array
		return Color(float(channels[0]), float(channels[1]), float(channels[2]),
			float(channels[3]) if channels.size() > 3 else 1.0)
	return fallback
