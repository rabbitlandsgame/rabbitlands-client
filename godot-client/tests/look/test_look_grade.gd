extends SceneTree
## Guards the look pass's grade (layer L1).
##
## The grade is re-applied after every binder rewrite, up to ten times a
## second, so it must never compound: scaling a value it already scaled would
## walk the sun towards orange and the ambient towards black within a minute.
## With ELORIA_LOOK=0 it must change nothing at all, and an interior, whose
## lamps are its whole lighting, is never graded.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var previous := OS.get_environment(LookProfile.ENABLE_VARIABLE)
	var outdoor := WorldManifest.new()
	outdoor.data = {"environment": {
		"sky": {"topColor": "3d7ec2", "horizonColor": "bcc9cd"},
		"sun": {"enabled": true, "energy": 1.1, "color": [1.0, 0.94, 0.83]},
		"ambient": {"energy": 0.6, "color": [0.6, 0.67, 0.72]},
		"fog": {"enabled": true, "color": [0.38, 0.37, 0.35], "density": 0.0007},
		"saturation": 1.3}}
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false},
		"ambient": {"energy": 0.4}}}
	var world_environment := WorldEnvironment.new()
	var sun := DirectionalLight3D.new()
	root.add_child(world_environment)
	root.add_child(sun)

	# Off: nothing changes.
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_bind(outdoor, world_environment, sun)
	var before := _snapshot(world_environment.environment, sun)
	_expect(not LookGrade.apply(outdoor, world_environment, sun),
		"with ELORIA_LOOK=0 the grade reports it did nothing")
	_expect(_snapshot(world_environment.environment, sun) == before,
		"with ELORIA_LOOK=0 the environment and sun are exactly as bound")

	# On: graded, and graded the same however often it runs.
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	_expect(LookGrade.apply(outdoor, world_environment, sun),
		"an outdoor map is graded")
	var environment := world_environment.environment
	var graded := _snapshot(environment, sun)
	_expect(environment.adjustment_enabled
		and is_equal_approx(environment.adjustment_saturation,
			LookProfile.saturation(1.3))
		and environment.adjustment_saturation < 1.3,
		"the declared saturation is enabled and tempered, not applied raw")
	_expect(sun.light_color.b < before.sun_colour.b
		and sun.light_energy > before.sun_energy,
		"the key light is warmed and strengthened")
	_expect(environment.ambient_light_sky_contribution < 1.0
		and environment.ambient_light_color.b / environment.ambient_light_color.r
			> before.ambient_colour.b / before.ambient_colour.r,
		"the ambient is cooled and reaches a sky-lit map")
	_expect(environment.fog_mode == Environment.FOG_MODE_DEPTH
		and is_equal_approx(environment.fog_density, LookProfile.fog_density(0.0007)),
		"declared fog becomes depth fog")
	var toe := environment.adjustment_color_correction as ImageTexture
	var toe_image := toe.get_image() if toe != null else null
	var width := toe_image.get_width() if toe_image != null else 0
	var past := ceili(LookProfile.TOE_END * (width - 1)) + 1
	_expect(toe_image != null and width > past
		and absf(toe_image.get_pixel(0, 0).r - LookProfile.TOE_LIFT) < 2.0 / 255.0
		and absf(toe_image.get_pixel(past, 0).r - float(past) / float(width - 1)) < 1.0 / 255.0
		and absf(toe_image.get_pixel(width - 1, 0).r - 1.0) < 1.0 / 255.0,
		"the toe lifts black to TOE_LIFT and leaves everything past TOE_END alone")
	_expect(environment.adjustment_color_correction == LookGrade.toe_curve(),
		"the toe is built once and shared")
	for i: int in 5:
		LookGrade.apply(outdoor, world_environment, sun)
	_expect(_snapshot(environment, sun) == graded,
		"re-applying the grade without a binder rewrite does not compound")
	DayNightBinder.apply(outdoor, world_environment, sun, 180.0)
	LookGrade.apply(outdoor, world_environment, sun)
	_expect(_snapshot(environment, sun) == graded,
		"a binder rewrite followed by the grade lands on the same values")
	# A fresh value from a binder (a later hour) is graded from itself.
	DayNightBinder.apply(outdoor, world_environment, sun, 120.0)
	var ungraded_energy := sun.light_energy
	LookGrade.apply(outdoor, world_environment, sun)
	_expect(is_equal_approx(sun.light_energy,
			ungraded_energy * LookProfile.SUN_ENERGY_SCALE),
		"a new hour's sun is graded from the hour's own value")

	# An interior is left alone.
	_bind(interior, world_environment, sun)
	var interior_before := _snapshot(world_environment.environment, sun)
	_expect(not LookGrade.apply(interior, world_environment, sun)
		and _snapshot(world_environment.environment, sun) == interior_before,
		"an interior is never graded")
	_expect(not LookGrade.apply(null, world_environment, sun),
		"no manifest grades nothing")

	OS.set_environment(LookProfile.ENABLE_VARIABLE, previous)
	world_environment.queue_free()
	sun.queue_free()
	await process_frame
	print("look grade tests: %s" % ("PASS" if failures == 0 else "%d FAILED" % failures))
	quit(failures)

func _bind(manifest: WorldManifest, world_environment: WorldEnvironment,
		sun: DirectionalLight3D) -> void:
	WorldEnvironmentBinder.apply(manifest, world_environment, sun)
	DayNightBinder.apply(manifest, world_environment, sun, 180.0)

func _snapshot(environment: Environment, sun: DirectionalLight3D) -> Dictionary:
	return {"tonemap": environment.tonemap_mode,
		"exposure": environment.tonemap_exposure,
		"adjusted": environment.adjustment_enabled,
		"saturation": environment.adjustment_saturation,
		"contrast": environment.adjustment_contrast,
		"colour_correction": environment.adjustment_color_correction,
		"ambient_colour": environment.ambient_light_color,
		"ambient_energy": environment.ambient_light_energy,
		"sky_share": environment.ambient_light_sky_contribution,
		"fog_mode": environment.fog_mode,
		"fog_density": environment.fog_density,
		"ssao": environment.ssao_enabled,
		"glow": environment.glow_enabled,
		"sun_colour": sun.light_color,
		"sun_energy": sun.light_energy}

func _expect(ok: bool, message: String) -> void:
	if ok:
		print("PASS: " + message)
	else:
		failures += 1
		push_error("FAIL: " + message)
