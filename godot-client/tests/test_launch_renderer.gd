extends SceneTree
## The updater half of the renderer policy (src/updates/launch_options.gd,
## MOB-C3u): Mobile as a startable renderer, the renderer Automatic starts from
## the game's recorded recommendation, the relaunch handshake's constants and
## arguments, which starts are trials, and the crash guard that gives a failed
## trial up. Runs in the game project and in the updater-only project of
## tests/run_client_update_tests.py (no game scripts there: this proves that
## launch_options.gd stands alone). In the game project it also checks that the
## updater and src/runtime/renderer_policy.gd apply the same rule. Uses its own
## settings files in the user directory; the player's file is never read.

const LaunchOptions := preload("res://src/updates/launch_options.gd")
const POLICY_PATH := "res://src/runtime/renderer_policy.gd"
const TEMP := "user://test_launch_renderer.cfg"
const MISSING := "user://test_launch_renderer_missing.cfg"

var failures := 0

func _init() -> void:
	_run.call_deferred()

func expect(ok: bool, label: String) -> void:
	if not ok:
		failures += 1
		push_error("FAIL: " + label)
	else:
		print("PASS: " + label)

func _run() -> void:
	_remove(MISSING)
	_check_renderers()
	_check_effective_renderer()
	_check_game_arguments()
	_check_restart_rules()
	_check_relaunch_arguments()
	_check_trial_renderer()
	_check_failed_start()
	_check_features()
	_check_policy_conformance()
	_remove(TEMP)
	_remove(MISSING)
	print("launch renderer tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(0 if failures == 0 else 1)

func _remove(path: String) -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))

## Writes a settings file with unrelated sections and keys around `values`.
func _write(values: Dictionary, path := TEMP) -> void:
	var config := ConfigFile.new()
	config.set_value("notes", "text", "keep [graphics] notes")
	config.set_value("lower_hud", "order", ["health", "mana"])
	config.set_value("graphics", "quality", "low")
	for key: String in values:
		config.set_value("graphics", key, values[key])
	config.save(path)

## An Automatic profile with a recorded Mobile recommendation.
func _trial(state: Variant = "trial", attempts: Variant = 0, extra := {}) -> Dictionary:
	return {"renderer": "auto", "auto_renderer": "mobile", "auto_renderer_basis": "integrated_gpu",
		"auto_renderer_adapter": "Intel(R) UHD Graphics 620", "auto_renderer_state": state,
		"auto_renderer_attempts": attempts}.merged(extra, true)

## An untyped copy, so typed and untyped arrays compare by content.
func _plain(values: Variant) -> Array:
	var result := []
	for value: Variant in values:
		result.append(value)
	return result

func _bytes(path := TEMP) -> PackedByteArray:
	return FileAccess.get_file_as_bytes(path) if FileAccess.file_exists(path) else PackedByteArray()

func _value(key: String, path := TEMP) -> Variant:
	var config := ConfigFile.new()
	config.load(path)
	return config.get_value("graphics", key, null)

func _engine(args: PackedStringArray) -> PackedStringArray:
	var split := args.find("--")
	return args.slice(0, split) if split >= 0 else args

func _user(args: PackedStringArray) -> PackedStringArray:
	var split := args.find("--")
	return args.slice(split + 1) if split >= 0 else PackedStringArray()

# Checks ----------------------------------------------------------------------

func _check_renderers() -> void:
	expect(LaunchOptions.RENDERERS == ["auto", "forward_plus", "mobile", "gl_compatibility"],
		"the renderer choices, in menu order, include Mobile")
	expect(LaunchOptions.renderer_arguments("mobile") == PackedStringArray(["--rendering-method", "mobile"]),
		"Mobile starts with --rendering-method mobile and the project's driver")
	expect(LaunchOptions.renderer_arguments("forward_plus") == PackedStringArray(["--rendering-method", "forward_plus"])
		and LaunchOptions.renderer_arguments("gl_compatibility") == PackedStringArray(
			["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])
		and LaunchOptions.renderer_arguments("auto").is_empty()
		and LaunchOptions.renderer_arguments("vulkan").is_empty(), "the other renderers' arguments are unchanged")
	expect(LaunchOptions.renderer_name("mobile") == "mobile" and LaunchOptions.renderer_name("vulkan") == "auto"
		and LaunchOptions.renderer_name(3) == "auto", "a saved Mobile choice is read back; unknown values are Automatic")
	for renderer: String in ["forward_plus", "mobile", "gl_compatibility"]:
		expect(LaunchOptions.startable(renderer), renderer + " can be started by name")
	for renderer: String in ["auto", "", "vulkan", "Mobile"]:
		expect(not LaunchOptions.startable(renderer), "'%s' cannot be started by name" % renderer)
	for platform: String in ["Linux", "Windows", "macOS"]:
		expect(LaunchOptions.performance_renderer("mobile", platform) == "mobile",
			"Performance keeps an explicit Mobile on " + platform)
	expect(LaunchOptions.performance_renderer("auto", "Linux") == "gl_compatibility"
		and LaunchOptions.performance_renderer("auto", "Windows") == "auto",
		"Performance still moves Automatic to OpenGL on Linux only")
	expect(LaunchOptions.RELAUNCH_EXIT_CODE == 75 and LaunchOptions.LAUNCHER_FEATURES_ENV == "RABBITLANDS_LAUNCHER_FEATURES"
		and LaunchOptions.RELAUNCH_FEATURE == "renderer-relaunch", "the relaunch handshake's constants")
	expect(LaunchOptions.SETTINGS_PATH == "user://eloria_hud.cfg", "the updater reads the game's settings file")

## [values, expected effective renderer, label]. null = no settings file.
func _effective_cases() -> Array:
	return [
		[null, "auto", "no settings file"],
		[{}, "auto", "no renderer key"],
		[{"renderer": "auto"}, "auto", "Automatic without a recommendation"],
		[{"renderer": "forward_plus"}, "forward_plus", "explicit Forward+"],
		[{"renderer": "mobile"}, "mobile", "explicit Mobile"],
		[{"renderer": "gl_compatibility"}, "gl_compatibility", "explicit OpenGL"],
		[{"renderer": "vulkan"}, "auto", "an unknown renderer reads as Automatic"],
		[{"renderer": 3}, "auto", "a non-text renderer reads as Automatic"],
		[_trial("trial", 0), "mobile", "a new trial"],
		[_trial("trial", 1), "mobile", "a trial after one counted start"],
		[_trial("trial", 2), "auto", "a trial after two starts without ok"],
		[_trial("trial", 7), "auto", "a trial far past the attempts"],
		[_trial("ok", 0), "mobile", "a confirmed recommendation"],
		[_trial("ok", 2), "auto", "attempts also bound an ok record"],
		[_trial("failed_fallback"), "auto", "failed_fallback"],
		[_trial("failed_start"), "auto", "failed_start"],
		[_trial("withdrawn"), "auto", "withdrawn (the game's kill switch)"],
		[_trial(""), "auto", "an empty state"],
		[_trial("unheard_of"), "auto", "an unknown state"],
		[_trial(3), "auto", "a non-text state"],
		[_trial("trial", 0, {"auto_renderer": ""}), "auto", "an empty recommendation"],
		[_trial("trial", 0, {"auto_renderer": "vulkan"}), "auto", "a recommendation that cannot be started"],
		[_trial("trial", 0, {"auto_renderer": 5}), "auto", "a non-text recommendation"],
		[_trial("ok", 0, {"auto_renderer": "forward_plus"}), "forward_plus", "a Forward+ recommendation"],
		[_trial("ok", 0, {"auto_renderer": "gl_compatibility"}), "gl_compatibility", "an OpenGL recommendation"],
		[_trial("trial", "1"), "mobile", "text attempts count as none, as in the game"],
		[_trial("trial", 1.0), "mobile", "float attempts below the limit"],
		[_trial("trial", 2.0), "auto", "float attempts at the limit"],
		[_trial("trial", true), "mobile", "boolean attempts count as none, as in the game"],
		[_trial("trial", 0, {"renderer": "forward_plus"}), "forward_plus", "an explicit choice beats the record"],
		[_trial("trial", 0, {"renderer": "gl_compatibility"}), "gl_compatibility", "an explicit OpenGL beats the record"],
		[_trial("trial", 0, {"renderer": "vulkan"}), "mobile", "an unknown choice is Automatic, which starts the record"],
		[_trial("ok", 0).merged({"renderer": null}, true), "mobile", "no renderer key with a record"],
	]

func _write_case(values: Variant) -> String:
	if values == null:
		return MISSING
	var cleaned := {}
	for key: String in values:
		if values[key] != null:
			cleaned[key] = values[key]
	_write(cleaned)
	return TEMP

func _check_effective_renderer() -> void:
	for case: Array in _effective_cases():
		var path := _write_case(case[0])
		var effective := LaunchOptions.effective_renderer(path)
		expect(effective == case[1], "Automatic resolution, %s: %s (want %s)" % [case[2], effective, case[1]])
	expect(not FileAccess.file_exists(MISSING), "reading a missing settings file creates none")
	var config := ConfigFile.new()
	config.set_value("graphics", "auto_renderer", "mobile")
	config.set_value("graphics", "auto_renderer_state", "ok")
	expect(LaunchOptions.recommended_renderer(config) == "mobile", "recommended_renderer reads a parsed file")
	config.set_value("graphics", "renderer", "forward_plus")
	expect(LaunchOptions.recommended_renderer(config) == "mobile",
		"recommended_renderer ignores the player's choice (the settings window's Automatic label)")

func _check_game_arguments() -> void:
	var defaults := PackedStringArray(["--server=play.example.org", "--port=2000"])
	_write(_trial("trial", 1))
	var args := LaunchOptions.game_arguments(PackedStringArray(), defaults, "C:/Game Folder", false, TEMP)
	var split := args.find("--")
	expect(_engine(args) == PackedStringArray(["--rendering-method", "mobile"])
		and _user(args) == defaults, "Automatic with an active Mobile record starts --rendering-method mobile: %s" % args)
	_write(_trial("failed_start", 1))
	args = LaunchOptions.game_arguments(PackedStringArray(), defaults, "C:/Game Folder", false, TEMP)
	expect(args == PackedStringArray(["--"]) + defaults, "a failed record starts the project default: %s" % args)
	_write(_trial("withdrawn", 0, {"auto_renderer": ""}))
	args = LaunchOptions.game_arguments(PackedStringArray(), defaults, "C:/Game Folder", false, TEMP)
	expect(args == PackedStringArray(["--"]) + defaults, "a withdrawn record starts the project default")
	_write({"renderer": "mobile"})
	args = LaunchOptions.game_arguments(PackedStringArray(["--client-debug"]), defaults, "C:/Game Folder", false, TEMP)
	split = args.find("--")
	expect(args.slice(0, 2) == PackedStringArray(["--rendering-method", "mobile"]) and args.find("--log-file") < split
		and args.find("--verbose") < split and _user(args) == defaults + PackedStringArray(["--client-debug"]),
		"an explicit Mobile with the debug launcher: %s" % args)
	_write(_trial("ok", 0))
	for flag: String in ["--client-compatibility", "--client-safe-mode"]:
		args = LaunchOptions.game_arguments(PackedStringArray([flag]), defaults, "C:/Game Folder", false, TEMP)
		expect(args.slice(0, 4) == PackedStringArray(["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])
			and args.count("--rendering-method") == 1, "%s keeps OpenGL over an active recommendation" % flag)
	args = LaunchOptions.game_arguments(PackedStringArray(), defaults, "C:/Game Folder", true, TEMP)
	expect(args == PackedStringArray(["--headless", "--"]) + defaults, "a headless launch names no renderer")
	_write({"renderer": "forward_plus"})
	args = LaunchOptions.game_arguments(PackedStringArray(), PackedStringArray(), "C:/Game Folder", false, TEMP)
	expect(args == PackedStringArray(["--rendering-method", "forward_plus", "--"]), "an explicit Forward+ is unchanged")

func _check_restart_rules() -> void:
	var none := PackedStringArray()
	expect(LaunchOptions.needs_renderer_restart("mobile", "forward_plus", none, none, false),
		"a Forward+ process restarts into a saved Mobile")
	expect(not LaunchOptions.needs_renderer_restart("mobile", "mobile", none, none, false), "Mobile running: no restart")
	expect(not LaunchOptions.needs_renderer_restart("auto", "mobile", none, none, false), "Automatic never restarts")
	expect(not LaunchOptions.needs_renderer_restart("mobile", "forward_plus", none,
		PackedStringArray([LaunchOptions.RENDERER_RESTART]), false), "a restarted process never restarts again")
	expect(not LaunchOptions.needs_renderer_restart("mobile", "forward_plus", none, none, true), "headless never restarts")
	for flag: String in ["--client-compatibility", "--client-safe-mode"]:
		expect(not LaunchOptions.needs_renderer_restart("forward_plus", "gl_compatibility", none,
			PackedStringArray([flag]), false), "the %s launcher is never restarted out of OpenGL" % flag)
		expect(LaunchOptions.compatibility_launch(PackedStringArray(["--port=1", flag])), flag + " is a compatibility launch")
	expect(not LaunchOptions.compatibility_launch(PackedStringArray(["--client-debug"])), "debug is not a compatibility launch")
	var engine := PackedStringArray(["--verbose", "--log-file", "C:/x.log", "--", "--port=1"])
	var restart := LaunchOptions.restart_arguments("mobile", engine, PackedStringArray(["--port=1"]))
	expect(restart == PackedStringArray(["--verbose", "--log-file", "C:/x.log", "--rendering-method", "mobile", "--",
		"--port=1", LaunchOptions.RENDERER_RESTART]), "the self-restart into Mobile: %s" % restart)

func _check_relaunch_arguments() -> void:
	var defaults := PackedStringArray(["--server=play.example.org"])
	var user := PackedStringArray(["--port=2001"])
	var marker := PackedStringArray([LaunchOptions.RENDERER_RESTART])
	# First run: Automatic, nothing recorded. The game records a trial and asks.
	_write({"renderer": "auto"})
	var first := LaunchOptions.game_arguments(user, defaults, "C:/Game Folder", false, TEMP)
	_write(_trial("trial", 1))
	var relaunch := LaunchOptions.relaunch_arguments(first, TEMP)
	expect(relaunch == LaunchOptions.game_arguments(user, defaults, "C:/Game Folder", false, TEMP) + marker,
		"the relaunch is the fresh launch for the new settings plus the marker: %s" % relaunch)
	expect(LaunchOptions.engine_renderer(relaunch) == "mobile" and LaunchOptions.relaunch_arguments(relaunch, TEMP) == relaunch,
		"... asks for Mobile, and the marker is added once")
	# An explicit Mobile changed to Forward+ while running.
	_write({"renderer": "forward_plus"})
	var debug := PackedStringArray(["--rendering-method", "mobile", "--verbose", "--log-file", "C:/Game Folder/eloria-debug.log",
		"--", "--client-debug"])
	relaunch = LaunchOptions.relaunch_arguments(debug, TEMP)
	expect(relaunch == PackedStringArray(["--rendering-method", "forward_plus", "--verbose", "--log-file",
		"C:/Game Folder/eloria-debug.log", "--", "--client-debug", LaunchOptions.RENDERER_RESTART]),
		"old renderer flags are replaced and diagnostics kept: %s" % relaunch)
	# Back to Automatic without a recommendation: the project default.
	_write({"renderer": "auto"})
	relaunch = LaunchOptions.relaunch_arguments(PackedStringArray(["--rendering-method=mobile", "--rendering-driver=vulkan",
		"--rendering-driver", "d3d12", "--", "--port=1"]), TEMP)
	expect(relaunch == PackedStringArray(["--", "--port=1", LaunchOptions.RENDERER_RESTART]),
		"both flag spellings are removed for the project default: %s" % relaunch)
	_write(_trial("ok", 0))
	for flag: String in ["--client-compatibility", "--client-safe-mode"]:
		var compatibility := LaunchOptions.game_arguments(PackedStringArray([flag]), defaults, "C:/Game Folder", false, TEMP)
		relaunch = LaunchOptions.relaunch_arguments(compatibility, TEMP)
		expect(relaunch == compatibility + marker, "%s relaunches on OpenGL unchanged: %s" % [flag, relaunch])
	var headless := LaunchOptions.game_arguments(user, defaults, "C:/Game Folder", true, TEMP)
	expect(LaunchOptions.relaunch_arguments(headless, TEMP) == headless + marker, "a headless launch stays headless")
	expect(LaunchOptions.relaunch_arguments(PackedStringArray(["--verbose"]), TEMP) == PackedStringArray(
		["--rendering-method", "mobile", "--verbose", "--", LaunchOptions.RENDERER_RESTART]),
		"arguments without a separator gain one")
	_write(_trial("ok", 0))
	var launch := LaunchOptions.game_arguments(user, defaults, "C:/Game Folder", false, TEMP)
	var resumed := LaunchOptions.resume_arguments(LaunchOptions.resume_context(launch, _user(launch)))
	expect(resumed == launch and LaunchOptions.engine_renderer(resumed) == "mobile",
		"a Mobile launch survives the update hand-off (resume context): %s" % resumed)

func _check_trial_renderer() -> void:
	var mobile := PackedStringArray(["--rendering-method", "mobile", "--", "--port=1"])
	_write(_trial("trial", 1))
	expect(LaunchOptions.trial_renderer(mobile, TEMP) == "mobile", "a Mobile start of a trial record is a trial")
	expect(LaunchOptions.trial_renderer(PackedStringArray(["--rendering-method=mobile", "--"]), TEMP) == "mobile",
		"... also with the = spelling")
	expect(LaunchOptions.trial_renderer(PackedStringArray(["--", "--port=1"]), TEMP) == "",
		"a start without renderer flags is no trial")
	expect(LaunchOptions.trial_renderer(PackedStringArray(["--headless", "--"]), TEMP) == "", "a headless start is no trial")
	expect(LaunchOptions.trial_renderer(PackedStringArray(["--rendering-method", "gl_compatibility",
		"--rendering-driver", "opengl3", "--", "--client-compatibility"]), TEMP) == "", "a compatibility start is no trial")
	expect(LaunchOptions.trial_renderer(PackedStringArray(["--", "--rendering-method", "mobile"]), TEMP) == "",
		"user arguments never count as engine flags")
	_write(_trial("trial", 2))
	expect(LaunchOptions.trial_renderer(mobile, TEMP) == "", "an exhausted trial is no trial")
	_write(_trial("ok", 0))
	expect(LaunchOptions.trial_renderer(mobile, TEMP) == "", "a confirmed record is no trial")
	_write(_trial("trial", 0, {"renderer": "mobile"}))
	expect(LaunchOptions.trial_renderer(mobile, TEMP) == "", "an explicit Mobile choice is no trial")
	expect(LaunchOptions.trial_renderer(mobile, MISSING) == "", "no settings file, no trial")
	_write_unreadable()
	expect(LaunchOptions.trial_renderer(mobile, TEMP) == "", "an unreadable settings file, no trial")

func _write_unreadable() -> void:
	var file := FileAccess.open(TEMP, FileAccess.WRITE)
	file.store_string("[graphics]\nauto_renderer=\"mobile\"\nauto_renderer_state=\"trial\"\nbroken = = [\n")
	file.close()

func _check_failed_start() -> void:
	var window := LaunchOptions.TRIAL_FAILURE_WINDOW_MSEC
	expect(window == 60000, "the crash guard's window is 60 s")
	# Exit codes measured on Windows with Godot 4.7.2: quit(3) gives 3, an engine
	# crash (OS.crash) -1073741795, quit(-1) -1.
	for exit_code: int in [3, 1, -1073741795, -1, 255]:
		_write(_trial("trial", 1))
		expect(LaunchOptions.record_failed_start("mobile", exit_code, 2500, TEMP), "exit %d of a trial start is recorded" % exit_code)
		expect(_value("auto_renderer_state") == "failed_start" and _value("auto_renderer") == "mobile"
			and _value("auto_renderer_attempts") == 1 and _value("auto_renderer_adapter") == "Intel(R) UHD Graphics 620"
			and _value("quality") == "low", "... as failed_start only, the record kept")
		var config := ConfigFile.new()
		config.load(TEMP)
		expect(config.get_value("notes", "text", "") == "keep [graphics] notes"
			and config.get_value("lower_hud", "order", []) == ["health", "mana"], "... other sections kept")
		expect(LaunchOptions.effective_renderer(TEMP) == "auto", "... and Automatic starts the project default after it")
	_write(_trial("trial", 1))
	expect(LaunchOptions.record_failed_start("mobile", 3, window - 1, TEMP), "an error just inside the window counts")
	var cases := [
		[_trial("trial", 1), "mobile", 0, 1000, "a clean exit"],
		[_trial("trial", 1), "mobile", LaunchOptions.RELAUNCH_EXIT_CODE, 1000, "the relaunch request"],
		[_trial("trial", 1), "mobile", 3, window, "an error after the window"],
		[_trial("trial", 1), "mobile", 3, -5, "a clock that ran backwards"],
		[_trial("trial", 1), "", 3, 1000, "a start that was no trial"],
		[_trial("ok", 0), "mobile", 3, 1000, "a record confirmed meanwhile"],
		[_trial("failed_fallback", 1), "mobile", 3, 1000, "a record the game already failed"],
		[_trial("withdrawn", 0, {"auto_renderer": ""}), "mobile", 3, 1000, "a withdrawn record"],
		[_trial("trial", 1, {"auto_renderer": "forward_plus"}), "mobile", 3, 1000, "another recommendation"],
		[_trial("trial", 1, {"renderer": "forward_plus"}), "mobile", 3, 1000, "an explicit choice made meanwhile"],
	]
	for case: Array in cases:
		_write(case[0])
		var before := _bytes()
		expect(not LaunchOptions.record_failed_start(case[1], case[2], case[3], TEMP) and _bytes() == before,
			"no write for %s" % case[4])
	expect(not LaunchOptions.record_failed_start("mobile", 3, 1000, MISSING) and not FileAccess.file_exists(MISSING),
		"no settings file is created")
	_write_unreadable()
	var broken := _bytes()
	expect(not LaunchOptions.record_failed_start("mobile", 3, 1000, TEMP) and _bytes() == broken,
		"an unreadable settings file is left as it is")

func _check_features() -> void:
	expect(LaunchOptions.launcher_features("") == "renderer-relaunch", "the updater announces the relaunch")
	expect(LaunchOptions.launcher_features("other") == "other,renderer-relaunch", "... after features already set")
	expect(LaunchOptions.launcher_features(" renderer-relaunch , other,,other ") == "renderer-relaunch,other",
		"... once, without blanks or repeats")

## The game's renderer_policy.gd applies the same rule (absent in the updater
## project, where this check is skipped).
func _check_policy_conformance() -> void:
	if not ResourceLoader.exists(POLICY_PATH):
		print("SKIP: no renderer_policy.gd in this project (the updater project)")
		return
	var policy: Script = load(POLICY_PATH)
	var theirs := policy.get_script_constant_map()
	var pairs := {"RELAUNCH_EXIT_CODE": "RELAUNCH_EXIT_CODE", "LAUNCHER_FEATURES_ENV": "LAUNCHER_FEATURES_ENV",
		"RELAUNCH_FEATURE": "RELAUNCH_FEATURE", "AUTO_RENDERER_KEY": "KEY_RENDERER", "AUTO_STATE_KEY": "KEY_STATE",
		"AUTO_ATTEMPTS_KEY": "KEY_ATTEMPTS", "TRIAL_STATE": "STATE_TRIAL", "FAILED_START_STATE": "STATE_FAILED_START",
		"MAX_TRIAL_ATTEMPTS": "MAX_TRIAL_ATTEMPTS", "SETTINGS_SECTION": "SECTION", "SETTINGS_PATH": "SETTINGS_PATH"}
	var options: Script = load("res://src/updates/launch_options.gd")
	var ours := options.get_script_constant_map()
	for name: String in pairs:
		expect(theirs.has(pairs[name]) and theirs[pairs[name]] == ours[name],
			"LaunchOptions.%s equals RendererPolicy.%s" % [name, pairs[name]])
	expect(_plain(theirs.get("ACTIVE_STATES", [])) == LaunchOptions.ACTIVE_AUTO_STATES,
		"the active states agree: %s" % [theirs.get("ACTIVE_STATES")])
	var supported := _plain(policy.call("supported_renderers"))
	expect(supported == ["forward_plus", "mobile", "gl_compatibility"], "the game can now start Mobile: %s" % [supported])
	expect(policy.call("launcher_relaunches", LaunchOptions.launcher_features("")) == true,
		"the game recognises the updater's announcement")
	for case: Array in _effective_cases():
		var path := _write_case(case[0])
		var config := ConfigFile.new()
		config.load(path)
		var game: String = policy.call("resolve", policy.call("read_values", config), "mobile")
		var launcher := LaunchOptions.effective_renderer(path)
		expect(launcher == game, "updater and game (policy on) agree for %s: %s vs %s" % [case[2], launcher, game])
	_write(_trial("trial", 1))
	var parent := PackedStringArray()
	var plan: Dictionary = policy.call("restart_plan", "mobile", LaunchOptions.launcher_features(""), parent, parent)
	expect(plan.get("mode") == "relaunch" and plan.get("exit_code") == LaunchOptions.RELAUNCH_EXIT_CODE,
		"under this updater the game restarts by the exit-code handshake: %s" % plan)
