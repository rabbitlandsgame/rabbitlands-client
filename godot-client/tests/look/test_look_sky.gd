extends SceneTree
## Guards the look pass's painted sky and haze (layer L5).
##
## With ELORIA_LOOK=0 the sky must stay develop's procedural one. With it
## on, the painted sky must light the world exactly as develop's did: its
## radiance pass is drawn from the colours DayNightBinder would have given the
## procedural sky, so those colours are checked against the binder's own for
## several hours. The haze has to be the painted horizon's colour and energy,
## or the far ground would end in a line against the sky, and the sky has to
## be swapped inside the bound Sky, so the map cameras that share it are not
## handed a new, graded copy of the environment.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var region := WorldManifest.new()
	region.data = {"asset": {"id": "amberwood"}, "environment": {
		"sky": {"zenith": [0.15, 0.25, 0.42], "horizon": [0.58, 0.56, 0.5],
			"groundBottom": [0.3, 0.25, 0.2], "sunAngleMax": 14, "curve": 0.2},
		"sun": {"enabled": true, "energy": 1.1, "color": [1.0, 0.94, 0.83]},
		"ambient": {"energy": 0.6, "color": [0.6, 0.67, 0.72]},
		"fog": {"enabled": true, "color": [0.38, 0.37, 0.35], "density": 0.0007}}}
	var island := WorldManifest.new()
	island.data = {"asset": {"id": "lantern_reach"}, "environment": {
		"backgroundColor": "18363f",
		"sun": {"enabled": true, "energy": 1.0, "color": "ffe5ba"},
		"ambient": {"energy": 0.7, "color": "acc6cb"}}}
	var still := WorldManifest.new()
	still.data = {"asset": {"id": "still"}, "environment": {
		"sky": {"topColor": "3d7ec2", "horizonColor": "bcc9cd"},
		"dayNight": {"enabled": false},
		"sun": {"enabled": true, "energy": 1.0}}}
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false},
		"ambient": {"energy": 0.4}}}
	var world_environment := WorldEnvironment.new()
	var sun := DirectionalLight3D.new()
	root.add_child(world_environment)
	root.add_child(sun)

	# Off: the procedural sky stays and nothing is touched.
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_bind(region, world_environment, sun, 180.0)
	var bound_sky: Sky = world_environment.environment.sky
	var off_before := _snapshot(world_environment.environment)
	_expect(not LookSky.install(region, world_environment)
		and not LookSky.apply(region, world_environment, 180.0),
		"with ELORIA_LOOK=0 the sky layer reports it did nothing")
	_expect(world_environment.environment.sky.sky_material is ProceduralSkyMaterial
		and _snapshot(world_environment.environment) == off_before,
		"with ELORIA_LOOK=0 the procedural sky and the fog are exactly as bound")

	# On: painted inside the bound Sky, with develop's sky kept for radiance.
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	var procedural := bound_sky.sky_material as ProceduralSkyMaterial
	_expect(LookSky.install(region, world_environment), "an outdoor map's sky is painted")
	var environment := world_environment.environment
	var painted := environment.sky.sky_material as ShaderMaterial
	_expect(environment.sky == bound_sky and painted != null
		and painted.shader == LookSky.SHADER,
		"the painted material replaces the procedural one inside the same Sky")
	_expect(is_equal_approx(float(painted.get_shader_parameter(&"radiance_curve")),
			procedural.sky_curve)
		and painted.get_shader_parameter(&"radiance_ground_bottom")
			== procedural.ground_bottom_color
		and is_equal_approx(float(painted.get_shader_parameter(&"radiance_sun_angle_max")),
			deg_to_rad(procedural.sun_angle_max))
		and is_equal_approx(float(painted.get_shader_parameter(&"radiance_exposure")),
			procedural.energy_multiplier),
		"the radiance pass takes the procedural sky's own settings")
	_expect(LookSky.install(region, world_environment)
		and environment.sky.sky_material == painted,
		"installing again keeps the one painted material")

	# The radiance colours are the binder's, hour by hour.
	for minute: float in [180.0, 120.0, 45.0, 0.0]:
		var reference := _procedural_at(region, minute)
		LookSky.apply(region, world_environment, minute)
		_expect(painted.get_shader_parameter(&"radiance_top") == reference.sky_top_color
			and painted.get_shader_parameter(&"radiance_horizon")
				== reference.sky_horizon_color,
			"at minute %d the radiance sky is the binder's procedural sky" % int(minute))

	# The haze meets the painted horizon.
	DayNightBinder.apply(region, world_environment, sun, 180.0)
	_expect(LookSky.apply(region, world_environment, 180.0), "the colours are applied")
	var colours := LookSky.sky_colours(region, 180.0)
	_expect(environment.fog_enabled and environment.fog_mode == Environment.FOG_MODE_DEPTH
		and environment.fog_light_color == colours.haze
		and painted.get_shader_parameter(&"look_haze") == colours.haze
		and is_zero_approx(environment.fog_aerial_perspective),
		"the fog is depth haze in exactly the painted horizon's colour")
	_expect(is_equal_approx(environment.fog_density, LookProfile.haze_density(0.0007))
		and environment.fog_density > LookProfile.HAZE_DENSITY,
		"a map that declares denser fog gets more haze")
	var horizon := colours.horizon as Color
	var warmed := colours.painted_horizon as Color
	_expect(warmed.r - warmed.b > horizon.r - horizon.b,
		"daylight warms the painted horizon")
	var night := LookSky.sky_colours(region, 0.0)
	_expect(night.painted_horizon == night.horizon and night.zenith == night.top,
		"at midnight the painted sky keeps the binder's moonlit colours")
	# A region may keep its haze cooler (`sky.haze_warmth`): its chunks read it too.
	LookProfile.define_region("haze_test", {"id": "haze_test", "schema": 1, "sky": {"haze_warmth": 0.0}})
	var cool := WorldManifest.new()
	cool.data = region.data.duplicate(true)
	cool.data["asset"] = {"id": "haze_test__chunk_3_4"}
	var cool_colours := LookSky.sky_colours(cool, 180.0)
	var cool_haze := cool_colours.haze as Color
	var warm_haze := colours.haze as Color
	_expect(cool_haze.b - cool_haze.r > warm_haze.b - warm_haze.r,
		"a region's own haze warmth keeps its far haze cooler than the shared warmth does")
	LookProfile.reload_regions()
	# Only a clear blue sky is painted as the bright day: a violet dusk and a
	# grey overcast keep their own colours, clouds in their horizon's colour.
	var dusk := WorldManifest.new()
	dusk.data = {"asset": {"id": "amethyst_barrens"}, "continentGeography": {}, "environment": {
		"sky": {"zenith": [0.1, 0.09, 0.16], "horizon": [0.34, 0.3, 0.38]},
		"dayNight": {"enabled": false}, "sun": {"enabled": true}}}
	var overcast := WorldManifest.new()
	overcast.data = {"asset": {"id": "grey_moors"}, "continentGeography": {}, "environment": {
		"sky": {"zenith": [0.2, 0.22, 0.26], "horizon": [0.44, 0.46, 0.47]},
		"dayNight": {"enabled": false}, "sun": {"enabled": true}}}
	var dusk_colours := LookSky.sky_colours(dusk, 720.0)
	var overcast_colours := LookSky.sky_colours(overcast, 720.0)
	_expect(is_zero_approx(float(dusk_colours.clear)) and is_zero_approx(float(overcast_colours.clear))
		and dusk_colours.zenith == dusk_colours.top and overcast_colours.zenith == overcast_colours.top
		and float(dusk_colours.cloud_opacity) < LookProfile.SKY_CLOUD_OPACITY,
		"a violet dusk and a grey overcast keep their zenith, with thinner clouds")
	_expect(float(colours.clear) > 0.5 and (colours.zenith as Color) != (colours.top as Color),
		"a clear blue sky is taken towards the painted day")
	_expect((colours.haze as Color).v <= LookProfile.SKY_HAZE_VALUE_MAX + 0.001,
		"the haze is never paler than SKY_HAZE_VALUE_MAX")
	var applied := _snapshot(environment)
	for i: int in 3:
		DayNightBinder.apply(region, world_environment, sun, 180.0)
		LookGrade.apply(region, world_environment, sun)
		LookSky.apply(region, world_environment, 180.0)
	_expect(_snapshot(environment) == applied,
		"re-applying after the binders and the grade lands on the same values")

	# A map with only a background colour gets a Sky, lit as before.
	_bind(island, world_environment, sun, 180.0)
	environment = world_environment.environment
	var background := environment.background_color
	_expect(environment.sky == null and not environment.fog_enabled,
		"the island binds with a background colour and no fog")
	_expect(LookSky.install(island, world_environment)
		and LookSky.apply(island, world_environment, 180.0),
		"a background-colour map's sky is painted")
	painted = environment.sky.sky_material as ShaderMaterial
	_expect(environment.background_mode == Environment.BG_SKY and painted != null
		and bool(painted.get_shader_parameter(&"radiance_flat"))
		and painted.get_shader_parameter(&"radiance_flat_colour") == background
		and environment.ambient_light_source == Environment.AMBIENT_SOURCE_COLOR,
		"its radiance stays the background colour and its ambient the declared colour")
	_expect(environment.fog_enabled and environment.fog_mode == Environment.FOG_MODE_DEPTH
		and environment.fog_light_color == LookSky.sky_colours(island, 180.0).haze,
		"the island gets the haze although its manifest declares no fog")
	var fallback := LookProfile.sky_fallback("lantern_reach")
	_expect(LookSky.sky_colours(island, 180.0).top == fallback.top,
		"the island's sky comes from its fallback colours")

	# A map whose hour does not drive its light keeps its noon sky.
	_bind(still, world_environment, sun, 180.0)
	_expect(LookSky.sky_colours(still, 0.0).top == Color("3d7ec2"),
		"a map with the hour turned off keeps its declared sky at midnight")

	# An interior is left alone.
	_bind(interior, world_environment, sun, 180.0)
	var interior_before := _snapshot(world_environment.environment)
	_expect(not LookSky.install(interior, world_environment)
		and not LookSky.apply(interior, world_environment, 180.0)
		and _snapshot(world_environment.environment) == interior_before,
		"an interior's sky and fog are never touched")
	_expect(not LookSky.apply(null, world_environment, 180.0),
		"no manifest paints nothing")

	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	world_environment.queue_free()
	sun.queue_free()
	await process_frame
	print("look sky tests: %s" % ("PASS" if failures == 0 else "%d FAILED" % failures))
	quit(failures)

func _bind(manifest: WorldManifest, world_environment: WorldEnvironment,
		sun: DirectionalLight3D, minute: float) -> void:
	WorldEnvironmentBinder.apply(manifest, world_environment, sun)
	DayNightBinder.apply(manifest, world_environment, sun, minute)

## The procedural sky DayNightBinder leaves at `minute`, on a fresh binding.
func _procedural_at(manifest: WorldManifest, minute: float) -> ProceduralSkyMaterial:
	var reference := WorldEnvironment.new()
	var reference_sun := DirectionalLight3D.new()
	WorldEnvironmentBinder.apply(manifest, reference, reference_sun)
	DayNightBinder.apply(manifest, reference, reference_sun, minute)
	var material := reference.environment.sky.sky_material as ProceduralSkyMaterial
	reference.free()
	reference_sun.free()
	return material

func _snapshot(environment: Environment) -> Dictionary:
	var material: Material = environment.sky.sky_material if environment.sky != null else null
	var parameters := {}
	if material is ShaderMaterial:
		for name: StringName in [&"radiance_top", &"radiance_horizon", &"look_zenith",
				&"look_horizon", &"look_haze", &"look_cloud_lit"]:
			parameters[name] = (material as ShaderMaterial).get_shader_parameter(name)
	return {"background": environment.background_mode,
		"material": material,
		"parameters": parameters,
		"fog": environment.fog_enabled,
		"fog_mode": environment.fog_mode,
		"fog_colour": environment.fog_light_color,
		"fog_energy": environment.fog_light_energy,
		"fog_density": environment.fog_density,
		"fog_end": environment.fog_depth_end,
		"sky_affect": environment.fog_sky_affect}

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)
