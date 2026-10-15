extends SceneTree
## Guards the look's switch and the graphics quality as LookProfile resolves
## them: who decides (ELORIA_LOOK and ELORIA_LOOK_QUALITY beat the player's
## choice, which beats the defaults), the preset table (HIGH is the renderer's
## defaults and the pass as tuned, and a lower quality only ever gives things
## up), the per-entry trims the measurements use, and the switch's generation,
## which marks a root painted under an older answer as stale.

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var variables := [LookProfile.ENABLE_VARIABLE, LookProfile.QUALITY_VARIABLE,
		LookProfile.QUALITY_TRIM_VARIABLE, LookProfile.SSAO_VARIABLE, LookProfile.SSIL_VARIABLE]
	var saved := {}
	for variable: String in variables:
		saved[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)
	var saved_look := LookProfile.player_look()
	var saved_quality := LookProfile.player_quality()
	LookProfile.set_player_look(LookProfile.LOOK_DEFAULT)
	LookProfile.set_player_quality(LookProfile.QUALITY_DEFAULT)

	_check_precedence()
	_check_quality()
	_check_presets()
	_check_trims()
	_check_generation()

	for variable: String in variables:
		if str(saved[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(saved[variable]))
	LookProfile.set_player_look(saved_look)
	LookProfile.set_player_quality(saved_quality)
	print("look settings tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(1 if failures > 0 else 0)

## ELORIA_LOOK beats the player's switch, which beats the default.
func _check_precedence() -> void:
	_expect(LookProfile.enabled() and LookProfile.player_look() and not LookProfile.look_forced(),
		"a player who never chose has the look on, and nothing forces it")
	_expect(LookProfile.set_player_look(false), "switching the look off changes the answer")
	_expect(not LookProfile.enabled(), "the player's Off turns the look off")
	_expect(not LookProfile.set_player_look(false), "the same answer again changes nothing")

	OS.set_environment(LookProfile.ENABLE_VARIABLE, "1")
	_expect(LookProfile.enabled() and LookProfile.look_forced() and not LookProfile.player_look(),
		"ELORIA_LOOK=1 turns the look on over the player's Off, and keeps the player's choice")
	_expect(not LookProfile.set_player_look(true),
		"while the variable decides, the player's switch does not change the answer")
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "0")
	_expect(not LookProfile.enabled() and LookProfile.look_forced() and LookProfile.player_look(),
		"ELORIA_LOOK=0 turns the look off over the player's On")
	for stray: String in ["", "yes", "off", "2"]:
		OS.set_environment(LookProfile.ENABLE_VARIABLE, stray)
		_expect(LookProfile.enabled() and not LookProfile.look_forced(),
			"a stray ELORIA_LOOK (%s) leaves the player's choice" % stray)
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	LookProfile.set_player_look(false)
	_expect(not LookProfile.enabled() and not LookProfile.look_forced(),
		"unset, the player's choice decides again")
	LookProfile.set_player_look(true)

## ELORIA_LOOK_QUALITY beats the player's quality, which beats HIGH.
func _check_quality() -> void:
	_expect(LookProfile.quality() == LookProfile.Quality.HIGH and not LookProfile.quality_forced(),
		"a player who never chose draws at HIGH")
	_expect(LookProfile.set_player_quality(LookProfile.Quality.LOW)
		and LookProfile.quality() == LookProfile.Quality.LOW,
		"the player's quality is the quality")
	_expect(not LookProfile.set_player_quality(LookProfile.Quality.LOW),
		"the same quality again changes nothing")
	OS.set_environment(LookProfile.QUALITY_VARIABLE, " High ")
	_expect(LookProfile.quality() == LookProfile.Quality.HIGH and LookProfile.quality_forced()
		and LookProfile.player_quality() == LookProfile.Quality.LOW,
		"ELORIA_LOOK_QUALITY (any case) beats the player's and keeps it")
	OS.set_environment(LookProfile.QUALITY_VARIABLE, "ultra")
	_expect(LookProfile.quality() == LookProfile.Quality.LOW and not LookProfile.quality_forced(),
		"a quality the variable does not name leaves the player's")
	OS.unset_environment(LookProfile.QUALITY_VARIABLE)
	for wrong: int in [-1, 3, 99]:
		LookProfile.set_player_quality(wrong)
		_expect(LookProfile.player_quality() == LookProfile.QUALITY_DEFAULT,
			"an unknown quality (%d) is taken as the default" % wrong)
	_expect(LookProfile.quality_named("MEDIUM") == LookProfile.Quality.MEDIUM
		and LookProfile.quality_named("best") == -1
		and LookProfile.quality_name(LookProfile.Quality.LOW) == "low",
		"qualities are written by name, and read back in any case")

## HIGH is the renderer's defaults and the pass as tuned; every quality has
## every entry, of HIGH's type; a lower one never draws what a higher one does not.
func _check_presets() -> void:
	var high: Dictionary = LookProfile.QUALITY_PRESETS[LookProfile.Quality.HIGH]
	_expect(LookProfile.QUALITY_PRESETS.size() == LookProfile.QUALITY_NAMES.size(),
		"every quality has a row")
	for level: int in LookProfile.QUALITY_NAMES.size():
		var row: Dictionary = LookProfile.QUALITY_PRESETS[level]
		_expect(row.keys() == high.keys(), "%s names HIGH's entries" % LookProfile.quality_name(level))
		for key: String in high:
			_expect(typeof(row[key]) == typeof(high[key]),
				"%s.%s is written as HIGH's is" % [LookProfile.quality_name(level), key])
	_expect(int(high.shadow_atlas) == int(ProjectSettings.get_setting(
			"rendering/lights_and_shadows/directional_shadow/size"))
		and int(high.shadow_filter) == int(ProjectSettings.get_setting(
			"rendering/lights_and_shadows/directional_shadow/soft_shadow_filter_quality"))
		and int(high.shadow_filter) == int(ProjectSettings.get_setting(
			"rendering/lights_and_shadows/positional_shadow/soft_shadow_filter_quality"))
		and LookProfile.SHADOW_ATLAS_16_BITS == bool(ProjectSettings.get_setting(
			"rendering/lights_and_shadows/directional_shadow/16_bits")),
		"HIGH's shadow atlas and filters are the project's own")
	var sun := DirectionalLight3D.new()
	_expect(int(high.shadow_splits) == 4
		and sun.directional_shadow_mode == DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS,
		"HIGH keeps the sun's four cascades, Godot's default")
	sun.free()
	_expect(bool(high.ssao) and bool(high.ssil) and bool(high.glow) and bool(high.grass),
		"HIGH draws the whole pass as tuned")
	for pair: Array in [[LookProfile.Quality.LOW, LookProfile.Quality.MEDIUM],
			[LookProfile.Quality.MEDIUM, LookProfile.Quality.HIGH]]:
		var lower: Dictionary = LookProfile.QUALITY_PRESETS[pair[0]]
		var higher: Dictionary = LookProfile.QUALITY_PRESETS[pair[1]]
		for key: String in high:
			var ok := true
			if high[key] is bool:
				ok = not bool(lower[key]) or bool(higher[key])
			else:
				ok = float(lower[key]) <= float(higher[key])
			_expect(ok, "%s gives up %s rather than adding to %s" % [
				LookProfile.quality_name(pair[0]), key, LookProfile.quality_name(pair[1])])

## ELORIA_LOOK_QUALITY_TRIM overrides single entries of the quality in use,
## and the older SSAO/SSIL switches still take those two off.
func _check_trims() -> void:
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)
	OS.set_environment(LookProfile.QUALITY_TRIM_VARIABLE, "ssao=0, shadow_splits=2,shadow_atlas=2048")
	_expect(not LookProfile.ssao_enabled() and LookProfile.ssil_enabled()
		and int(LookProfile.quality_value("shadow_splits")) == 2
		and int(LookProfile.quality_value("shadow_atlas")) == 2048
		and int(LookProfile.quality_value("shadow_filter")) == 2,
		"a trim overrides only the entries it names")
	OS.set_environment(LookProfile.QUALITY_TRIM_VARIABLE, "glow=false,grass=1")
	_expect(not LookProfile.glow_enabled() and bool(LookProfile.quality_value("grass")),
		"a trim reads true and false in words or digits")
	OS.unset_environment(LookProfile.QUALITY_TRIM_VARIABLE)
	OS.set_environment(LookProfile.SSIL_VARIABLE, "0")
	_expect(not LookProfile.ssil_enabled() and LookProfile.ssao_enabled(),
		"ELORIA_LOOK_SSIL=0 still takes SSIL off at HIGH")
	OS.unset_environment(LookProfile.SSIL_VARIABLE)
	LookProfile.set_player_quality(LookProfile.Quality.LOW)
	_expect(not LookProfile.ssao_enabled() and not LookProfile.ssil_enabled()
		and not LookProfile.glow_enabled(),
		"LOW draws no screen-space effects and no glow")
	LookProfile.set_player_quality(LookProfile.Quality.HIGH)

## The generation counts every change of the answer; a root painted under an
## older one is stale until it is synced.
func _check_generation() -> void:
	LookProfile.set_player_look(true)
	var painted := Node.new()
	var generation := LookProfile.switch_generation()
	_expect(LookProfile.enabled_for(painted) and not LookProfile.stale(painted),
		"a root painted under the current answer is not stale")
	var untouched := Node.new()
	_expect(not LookProfile.stale(untouched), "a root no painter has seen is never stale")
	LookProfile.set_player_look(false)
	_expect(LookProfile.switch_generation() == generation + 1,
		"switching counts one generation")
	_expect(LookProfile.stale(painted) and LookProfile.any_stale(),
		"the root painted before the switch is stale")
	LookProfile.enabled_for(painted)
	_expect(LookProfile.stale(painted),
		"a second painter on the same root keeps the first one's generation")
	LookProfile.stamp(painted)
	_expect(not LookProfile.stale(painted), "a synced root is no longer stale")
	OS.set_environment(LookProfile.ENABLE_VARIABLE, "1")
	_expect(LookProfile.stale(painted),
		"a change of ELORIA_LOOK counts as a switch too")
	OS.unset_environment(LookProfile.ENABLE_VARIABLE)
	LookProfile.set_player_look(true)
	painted.free()
	untouched.free()
	_expect(not LookProfile.any_stale(), "a freed root is forgotten")

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS " + message)
	else:
		failures += 1
		print("FAIL " + message)
