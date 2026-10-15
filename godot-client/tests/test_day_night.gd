extends SceneTree
## Guards the day/night cycle.
##
## The daylight curve is the server's own - `World` uses
## `(1 - cos(2*PI*minute/360)) / 2` to decide how far a creature can see - and
## this suite pins the client to that same expression, so what the player sees
## and what the server acts on cannot drift apart. The manifest is the noon
## reference; a package that declares no sun, or opts out, is left alone.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	# The curve, against the server's own formula computed here independently.
	for minute: int in [0, 45, 90, 180, 270, 359]:
		var expected: float = (1.0 - cos(TAU * float(minute) / 360.0)) * 0.5
		_expect(is_equal_approx(DayNightBinder.daylight(float(minute)), expected),
			"minute %d matches the server's daylight expression" % minute)
	_expect(is_equal_approx(DayNightBinder.daylight(180.0), 1.0)
		and is_equal_approx(DayNightBinder.daylight(0.0), 0.0),
		"minute 180 is the brightest and minute 0 the darkest, as the server has it")
	_expect(DayNightBinder.twilight(90.0) > DayNightBinder.twilight(180.0)
		and DayNightBinder.twilight(90.0) > DayNightBinder.twilight(0.0),
		"twilight peaks at sunrise and sunset rather than at noon or midnight")

	var outdoor := WorldManifest.new()
	outdoor.data = {"environment": {
		"sky": {"topColor": "3d7ec2", "horizonColor": "bcc9cd"},
		"sun": {"enabled": true, "energy": 1.4, "color": "fff2d8",
			"shadows": true},
		"ambient": {"energy": 0.9, "skyContribution": 0.8,
			"color": "c8ccd2"},
		"fog": {"enabled": true, "color": "d8c9a4"}}}
	var interior := WorldManifest.new()
	interior.data = {"environment": {"sun": {"enabled": false},
		"ambient": {"energy": 0.4}}}
	var opted_out := WorldManifest.new()
	opted_out.data = {"environment": {"sun": {"enabled": true, "energy": 1.0},
		"dayNight": {"enabled": false}}}
	_expect(DayNightBinder.drives(outdoor), "an outdoor package is driven")
	_expect(not DayNightBinder.drives(interior),
		"an interior that declares no sun keeps its own lighting")
	_expect(not DayNightBinder.drives(opted_out),
		"a package can opt out of the hour entirely")
	_expect(not DayNightBinder.drives(null), "no manifest drives nothing")

	var world_environment := WorldEnvironment.new()
	var environment := Environment.new()
	var sky := Sky.new()
	sky.sky_material = ProceduralSkyMaterial.new()
	environment.sky = sky
	environment.background_mode = Environment.BG_SKY
	environment.fog_enabled = true
	world_environment.environment = environment
	var sun := DirectionalLight3D.new()
	root.add_child(world_environment)
	root.add_child(sun)

	_expect(DayNightBinder.apply(outdoor, world_environment, sun, 180.0),
		"noon applies")
	var noon_energy: float = sun.light_energy
	var noon_ambient: float = environment.ambient_light_energy
	var noon_elevation: float = sun.rotation_degrees.x
	var noon_contribution: float = environment.ambient_light_sky_contribution
	var noon_ambient_colour: Color = environment.ambient_light_color
	var noon_sky: Color = (environment.sky.sky_material as ProceduralSkyMaterial).sky_top_color
	_expect(is_equal_approx(noon_energy, 1.4),
		"noon is the energy the package declared, not a value of its own: %f"
			% noon_energy)
	_expect(sun.shadow_enabled, "the sun casts at noon")

	DayNightBinder.apply(outdoor, world_environment, sun, 0.0)
	_expect(sun.light_energy < noon_energy * 0.4,
		"midnight is a fraction of noon: %f" % sun.light_energy)
	_expect(environment.ambient_light_energy < noon_ambient
		and environment.ambient_light_energy > 0.0,
		"ambient dims but never reaches black: %f" % environment.ambient_light_energy)
	_expect(not sun.shadow_enabled,
		"a sun below the horizon casts no shadow")
	_expect(sun.rotation_degrees.x > noon_elevation,
		"the sun is somewhere else at midnight than at noon")

	# The moon is the night's only directed light. It rides the sun's arc half a
	# day away, so at midnight it stands where the sun stands at noon - above
	# the horizon, throwing light down on the ground the sun is under - and it
	# is dark and hidden by the time the sun is properly up, so day is as it was.
	var moon := DirectionalLight3D.new()
	root.add_child(moon)
	DayNightBinder.apply(outdoor, world_environment, sun, 0.0, moon)
	_expect(moon.light_energy > 0.0 and moon.visible,
		"the moon lights the ground at midnight: %f" % moon.light_energy)
	_expect(moon.rotation_degrees.x < 0.0,
		"the moon stands above the horizon at midnight: %f" % moon.rotation_degrees.x)
	_expect(is_equal_approx(moon.rotation_degrees.x, noon_elevation),
		"it stands where the sun stands at noon: %f for %f" % [moon.rotation_degrees.x, noon_elevation])
	_expect(not moon.shadow_enabled,
		"the moon throws no shadow of its own, which would cost a second shadow pass")
	DayNightBinder.apply(outdoor, world_environment, sun, 180.0, moon)
	_expect(is_zero_approx(moon.light_energy) and not moon.visible,
		"the moon is dark and hidden at noon: %f" % moon.light_energy)
	_expect(is_equal_approx(sun.light_energy, noon_energy),
		"and noon is still the package's own light")
	DayNightBinder.apply(outdoor, world_environment, sun, 90.0, moon)
	_expect(is_zero_approx(moon.light_energy),
		"and it is out by sunrise, so dawn and dusk are unchanged: %f" % moon.light_energy)
	moon.queue_free()
	DayNightBinder.apply(outdoor, world_environment, sun, 0.0)

	# Regression: a sun still below the horizon must not cast a shadow, even
	# once `light` has climbed past a small fraction. Minute 40 sits at
	# light ~0.117 - past the old flat 0.08 cutoff, but the interpolated
	# elevation (MIDNIGHT_ELEVATION 12 -> NOON_ELEVATION -62) is still
	# positive there, i.e. still on the below-horizon side. The old check
	# turned shadows on anyway, and a directional light aimed away from the
	# ground casts a huge, wrong-angle shadow - the giveaway a player sees as
	# a shadow glued to their character every dawn and dusk.
	DayNightBinder.apply(outdoor, world_environment, sun, 40.0)
	_expect(sun.rotation_degrees.x > 0.0,
		"minute 40's interpolated elevation is still below the horizon: %f"
			% sun.rotation_degrees.x)
	_expect(not sun.shadow_enabled,
		"a sun still below the horizon casts no shadow even past minute 0")

	# Regression: a sun that has genuinely cleared the horizon but is still at
	# a grazing angle must also wait. Minute 60 sits at elevation ~-6.5, well
	# past the horizon crossing above, yet a caster there still throws a
	# shadow ~9x its own height - a rendered Four Gates capture at this minute
	# is exactly the huge trailing shadow a player reported, glued behind them
	# for most of a walk down the plaza. Minute 90 (~-25 degrees) is
	# comfortably past SHADOW_ELEVATION_CUTOFF and must have shadows back on,
	# so the cutoff does not just push the same bug later into the morning.
	DayNightBinder.apply(outdoor, world_environment, sun, 60.0)
	_expect(sun.rotation_degrees.x < 0.0
			and sun.rotation_degrees.x > DayNightBinder.SHADOW_ELEVATION_CUTOFF,
		"minute 60 is above the horizon but still inside the grazing band: %f"
			% sun.rotation_degrees.x)
	_expect(not sun.shadow_enabled,
		"a grazing-angle sun does not cast a shadow long enough to dominate the screen")
	DayNightBinder.apply(outdoor, world_environment, sun, 90.0)
	_expect(sun.rotation_degrees.x < DayNightBinder.SHADOW_ELEVATION_CUTOFF,
		"minute 90 has climbed clear of the grazing band: %f" % sun.rotation_degrees.x)
	_expect(sun.shadow_enabled,
		"shadows return well before noon, once the angle is sane")
	# Back to exact midnight so the checks below still read the state their
	# comments describe.
	DayNightBinder.apply(outdoor, world_environment, sun, 0.0)

	var night_sky: Color = (environment.sky.sky_material as ProceduralSkyMaterial).sky_top_color
	_expect(night_sky.get_luminance() < noon_sky.get_luminance(),
		"the sky is darker at midnight than at noon")
	# The night sky is nearly black, so a package that takes all of its ambient
	# from the sky - which is every package that names no skyContribution - had
	# no ambient at all at midnight. The sky's share is turned down and the
	# moonlit colour stands in for it.
	_expect(environment.ambient_light_sky_contribution < noon_contribution
		and environment.ambient_light_sky_contribution
			<= DayNightBinder.NIGHT_SKY_CONTRIBUTION + 0.01,
		"the night sky is not left as the whole ambient source: %f"
			% environment.ambient_light_sky_contribution)
	_expect(environment.ambient_light_color.get_luminance()
		> night_sky.get_luminance(),
		"midnight ambient is lit by the moon rather than by the night sky")

	# A map authored for a dim noon must still be walkable at midnight; a
	# fraction of its own noon would leave it as dark as it was.
	var overcast := WorldManifest.new()
	overcast.data = {"environment": {
		"sun": {"enabled": true, "energy": 0.8},
		"ambient": {"energy": 0.3, "skyColor": [0.2, 0.17, 0.3]}}}
	DayNightBinder.apply(overcast, world_environment, sun, 0.0)
	_expect(environment.ambient_light_energy >= DayNightBinder.NIGHT_AMBIENT_FLOOR,
		"a dim package still gets a floor under its night: %f"
			% environment.ambient_light_energy)
	_expect(environment.ambient_light_sky_contribution
		<= DayNightBinder.NIGHT_SKY_CONTRIBUTION + 0.01
		and environment.ambient_light_color.get_luminance() > 0.3,
		"the `skyColor` spelling of the ambient colour is read too")

	# Shadows let part of the sun through: the renderer has no bounce light, so
	# an opaque shadow is ambient alone. The same energy gets through whatever
	# the sun's strength, the hour does not move it, and a package may set its
	# own opacity.
	DayNightBinder.apply(outdoor, world_environment, sun, 180.0)
	var leaked: float = (1.0 - sun.shadow_opacity) * 1.4
	_expect(sun.shadow_opacity < 1.0 and is_equal_approx(leaked,
			WorldEnvironmentBinder.SUN_SHADOW_LEAK_ENERGY),
		"a shadow lets the leak energy of the noon sun through: %f" % sun.shadow_opacity)
	var noon_opacity: float = sun.shadow_opacity
	DayNightBinder.apply(outdoor, world_environment, sun, 100.0)
	_expect(is_equal_approx(sun.shadow_opacity, noon_opacity),
		"the opacity is the noon sun's at every hour: %f" % sun.shadow_opacity)
	var strong := WorldManifest.new()
	strong.data = {"environment": {"sun": {"enabled": true, "energy": 2.35}}}
	DayNightBinder.apply(strong, world_environment, sun, 180.0)
	_expect(sun.shadow_opacity > noon_opacity and is_equal_approx(
			(1.0 - sun.shadow_opacity) * 2.35,
			WorldEnvironmentBinder.SUN_SHADOW_LEAK_ENERGY),
		"a stronger sun gets a more opaque shadow, not a washed-out one: %f"
			% sun.shadow_opacity)
	DayNightBinder.apply(overcast, world_environment, sun, 180.0)
	_expect(sun.shadow_opacity >= WorldEnvironmentBinder.MIN_SUN_SHADOW_OPACITY,
		"a weak sun still keeps enough shadow to ground things: %f" % sun.shadow_opacity)
	var declared_opacity := WorldManifest.new()
	declared_opacity.data = {"environment": {
		"sun": {"enabled": true, "energy": 1.0, "shadowOpacity": 0.9}}}
	DayNightBinder.apply(declared_opacity, world_environment, sun, 180.0)
	_expect(is_equal_approx(sun.shadow_opacity, 0.9),
		"the hour keeps a package's declared shadow opacity: %f" % sun.shadow_opacity)
	sun.shadow_opacity = 1.0
	WorldEnvironmentBinder.apply(declared_opacity, world_environment, sun)
	_expect(is_equal_approx(sun.shadow_opacity, 0.9),
		"binding a package applies its declared shadow opacity: %f" % sun.shadow_opacity)
	WorldEnvironmentBinder.apply(outdoor, world_environment, sun)
	_expect(is_equal_approx(sun.shadow_opacity, noon_opacity),
		"a package that declares none gets the leak-derived opacity: %f"
			% sun.shadow_opacity)
	# The binder replaces the Environment; carry on with the one it bound.
	environment = world_environment.environment

	DayNightBinder.apply(outdoor, world_environment, sun, 90.0)
	var dawn_colour: Color = sun.light_color
	DayNightBinder.apply(outdoor, world_environment, sun, 180.0)
	_expect(dawn_colour.r - dawn_colour.b > sun.light_color.r - sun.light_color.b,
		"sunrise is warmer than noon")
	_expect(is_equal_approx(sun.light_energy, noon_energy)
		and is_equal_approx(environment.ambient_light_energy, noon_ambient)
		and is_equal_approx(sun.rotation_degrees.x, noon_elevation)
		and is_equal_approx(environment.ambient_light_sky_contribution,
			noon_contribution)
		and environment.ambient_light_color.is_equal_approx(noon_ambient_colour),
		"returning to noon returns the exact noon values, so repeated"
			+ " application cannot drift")

	# An interior is untouched even when asked.
	sun.light_energy = 3.0
	_expect(not DayNightBinder.apply(interior, world_environment, sun, 0.0)
		and is_equal_approx(sun.light_energy, 3.0),
		"an interior's lighting is left exactly as its package set it")

	# The clock the client carries forward between packets.
	var app_state: Node = root.get_node("/root/AppState")
	app_state.call("_on_packet", 5, PackedByteArray([100, 0]))
	_expect(is_equal_approx(float(app_state.call("continuous_game_minute")), 100.0),
		"one minute alone is reported as stated, with nothing interpolated")
	app_state.call("_on_packet", 5, PackedByteArray([101, 0]))
	var carried: float = float(app_state.call("continuous_game_minute"))
	_expect(carried >= 101.0 and carried < 102.0,
		"after two minutes the clock runs on from the second: %f" % carried)
	# A #set_clock jump is not a pace: the time since the last minute says
	# nothing about how fast the clock runs, so the measured interval stands.
	app_state.set("game_minute_interval_msec", 1500)
	app_state.call("_on_packet", 5, PackedByteArray([200, 0]))
	_expect(int(app_state.get("game_minute")) == 200
		and int(app_state.get("game_minute_interval_msec")) == 1500,
		"a jumped minute is taken without re-measuring the clock's pace")

	print("day night tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
