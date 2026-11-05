extends RefCounted
## Keep engine switches before `--`; everything after it belongs to the game.
## The restart launcher must preserve this separation when spawning its child.
##
## This file is copied into the updater project (tools/client_release.py
## export_launcher) and must stay self-contained: no preload of game scripts.
## The game's src/runtime/renderer_policy.gd shares the renderer-recommendation
## values below; tests/test_launch_renderer.gd checks that they agree.

const RENDERERS := ["auto", "forward_plus", "mobile", "gl_compatibility"]
const RENDERER_RESTART := "--graphics-renderer-restarted"
const CONTEXT_ENV := "RABBITLANDS_LAUNCH_CONTEXT"
const SETTINGS_PATH := "user://eloria_hud.cfg"
const SETTINGS_SECTION := "graphics"

## The renderer-restart handshake. The updater lists RELAUNCH_FEATURE in
## LAUNCHER_FEATURES_ENV (comma-separated) for the game it starts. A game that
## must restart into another renderer then exits with RELAUNCH_EXIT_CODE, and
## the updater starts it again once with `relaunch_arguments`, keeping its
## installation lock. Without the feature the game restarts itself
## (OS.set_restart_on_exit with `restart_arguments`).
const RELAUNCH_EXIT_CODE := 75
const LAUNCHER_FEATURES_ENV := "RABBITLANDS_LAUNCHER_FEATURES"
const RELAUNCH_FEATURE := "renderer-relaunch"

## The recommendation the game records for Automatic in [graphics] (see
## renderer_policy.gd): what Automatic starts, its trial state and the trial
## starts that have not reached "ok". A record, never the player's choice.
const AUTO_RENDERER_KEY := "auto_renderer"
const AUTO_STATE_KEY := "auto_renderer_state"
const AUTO_ATTEMPTS_KEY := "auto_renderer_attempts"
const TRIAL_STATE := "trial"
const FAILED_START_STATE := "failed_start"
## States in which Automatic starts the recommendation.
const ACTIVE_AUTO_STATES := ["trial", "ok"]
## Trial starts without reaching "ok" after which Automatic gives up.
const MAX_TRIAL_ATTEMPTS := 2
## Updater-only requests (launcher.gd): a server's required commit and its
## manifest URL, and the count of updater handovers so far. They travel through
## handovers but never reach the game or a saved launch context.
const LAUNCHER_ONLY_PREFIXES := ["--target-commit=", "--target-manifest-url=", "--handoff-hops="]
## A trial start that exits with an error sooner than this after it was
## started marks the recommendation failed_start (`record_failed_start`).
const TRIAL_FAILURE_WINDOW_MSEC := 60000

static func current_context(install_root: String) -> Dictionary:
	var user := OS.get_cmdline_user_args()
	var saved: Variant = JSON.parse_string(Marshalls.base64_to_utf8(OS.get_environment(CONTEXT_ENV))) if OS.has_environment(CONTEXT_ENV) else null
	if saved is Dictionary and saved.get("user") == Array(user) and not resume_arguments(saved).is_empty():
		return saved
	# Godot consumes recognized engine switches before get_cmdline_args(). For
	# direct executable launches reconstruct the active mode from runtime state.
	var args := game_arguments(user, [], install_root, DisplayServer.get_name() == "headless")
	var split := args.find("--")
	var engine := args.slice(0, split)
	if DisplayServer.get_name() != "headless":
		# This reflects the actual renderer, including an explicit engine override.
		var retained := PackedStringArray()
		var skip_value := false
		for argument: String in engine:
			if skip_value:
				skip_value = false
				continue
			if argument in ["--rendering-method", "--rendering-driver"]:
				skip_value = true
			else:
				retained.append(argument)
		engine = renderer_arguments(RenderingServer.get_current_rendering_method()) + retained
	if OS.is_stdout_verbose() and not "--verbose" in engine:
		engine.append_array(["--verbose", "--log-file", install_root.path_join("eloria-debug.log")])
	return resume_context(engine, user)

static func encode_context(context: Dictionary) -> String:
	# Base64 avoids platform command-line quote processing, particularly JSON's
	# embedded quotes being stripped by Windows process creation.
	return Marshalls.utf8_to_base64(JSON.stringify(context))

## `args` without the updater-only requests (LAUNCHER_ONLY_PREFIXES).
static func without_launcher_flags(args: PackedStringArray) -> PackedStringArray:
	var kept := PackedStringArray()
	for argument: String in args:
		if not LAUNCHER_ONLY_PREFIXES.any(func(prefix: String) -> bool: return argument.begins_with(prefix)):
			kept.append(argument)
	return kept

static func resume_context(engine_args: PackedStringArray, user_args: PackedStringArray) -> Dictionary:
	# Preserve the active renderer and diagnostic log without carrying editor,
	# script, pack or project-path overrides into the newly installed game.
	user_args = without_launcher_flags(user_args)
	var engine := PackedStringArray()
	var value_options := ["--rendering-method", "--rendering-driver", "--log-file"]
	var index := 0
	while index < engine_args.size() and engine_args[index] != "--":
		var option := engine_args[index]
		if option in value_options and index + 1 < engine_args.size():
			engine.append_array([option, engine_args[index + 1]])
			index += 1
		elif option in ["--verbose", "-v", "--headless"]:
			engine.append(option)
		elif option.get_slice("=", 0) in value_options and "=" in option:
			engine.append(option)
		index += 1
	return {"schema": 1, "engine": Array(engine), "user": Array(user_args)}

static func resume_arguments(context: Dictionary) -> PackedStringArray:
	if context.get("schema") != 1 or not context.get("engine") is Array or not context.get("user") is Array:
		return PackedStringArray()
	for key: String in ["engine", "user"]:
		for value: Variant in context[key]:
			if not value is String:
				return PackedStringArray()
	var engine := PackedStringArray(context.engine)
	var user := without_launcher_flags(PackedStringArray(context.user))
	# Reuse the allow-list when consuming the handoff, too.
	if resume_context(engine, user).engine != Array(engine):
		return PackedStringArray()
	engine.append("--")
	engine.append_array(user)
	return engine

static func saved_renderer(path := SETTINGS_PATH) -> String:
	var config := ConfigFile.new()
	config.load(path)
	return renderer_name(config.get_value(SETTINGS_SECTION, "renderer", "auto"))

static func renderer_name(value: Variant) -> String:
	return str(value) if value is String and value in RENDERERS else "auto"

## Whether the launch code can start `renderer` by name (not "auto").
static func startable(renderer: String) -> bool:
	return renderer != "auto" and renderer_name(renderer) == renderer and not renderer_arguments(renderer).is_empty()

## The renderer the settings file at `path` starts: the player's explicit
## choice when it can be started; for Automatic, the game's recorded
## recommendation while it is active (`recommended_renderer`); else "auto",
## the project default (Forward+). The game applies the same rule
## (RendererPolicy.resolve with its policy on).
static func effective_renderer(path := SETTINGS_PATH) -> String:
	var config := ConfigFile.new()
	config.load(path)
	var explicit := _setting_text(config, "renderer", "auto")
	return explicit if startable(explicit) else recommended_renderer(config)

## The recommendation Automatic starts in `config`, or "auto": one that can be
## started, in an ACTIVE_AUTO_STATES state, with fewer than MAX_TRIAL_ATTEMPTS
## attempts. Ignores the player's choice.
static func recommended_renderer(config: ConfigFile) -> String:
	var recommended := _setting_text(config, AUTO_RENDERER_KEY, "")
	var attempts: Variant = config.get_value(SETTINGS_SECTION, AUTO_ATTEMPTS_KEY, 0)
	var count := int(attempts) if attempts is int or attempts is float else 0
	if startable(recommended) and _setting_text(config, AUTO_STATE_KEY, "") in ACTIVE_AUTO_STATES \
			and count < MAX_TRIAL_ATTEMPTS:
		return recommended
	return "auto"

static func _setting_text(config: ConfigFile, key: String, fallback: String) -> String:
	var value: Variant = config.get_value(SETTINGS_SECTION, key, fallback)
	return value if value is String else fallback

## The value of `--rendering-method` among the engine arguments of `args`
## (before `--`), or "".
static func engine_renderer(args: PackedStringArray) -> String:
	var split := args.find("--")
	var engine := args.slice(0, split) if split >= 0 else args
	for index in engine.size():
		var argument := engine[index]
		if argument == "--rendering-method" and index + 1 < engine.size():
			return engine[index + 1]
		if argument.begins_with("--rendering-method="):
			return argument.get_slice("=", 1)
	return ""

## The recommendation a game started with `args` is trialling, or "": the
## settings at `path` are Automatic with a recommendation in the trial state
## that Automatic starts, and `args` ask the engine for it (not, for example, a
## compatibility or headless launch).
static func trial_renderer(args: PackedStringArray, path := SETTINGS_PATH) -> String:
	var config := ConfigFile.new()
	if not FileAccess.file_exists(path) or config.load(path) != OK:
		return ""
	if startable(_setting_text(config, "renderer", "auto")):
		return ""
	var recommended := recommended_renderer(config)
	if recommended == "auto" or _setting_text(config, AUTO_STATE_KEY, "") != TRIAL_STATE:
		return ""
	return recommended if engine_renderer(args) == recommended else ""

## The updater's crash guard: a game started on trial of `renderer`
## (`trial_renderer`) exited with `exit_code` after `elapsed_msec`. An error
## exit (not 0 and not RELAUNCH_EXIT_CODE) within TRIAL_FAILURE_WINDOW_MSEC
## sets only auto_renderer_state to failed_start, by load, change and save,
## while the file still records that trial; Automatic then starts the project
## default for good. Never writes a file that is missing or cannot be read.
## Returns whether it wrote.
static func record_failed_start(renderer: String, exit_code: int, elapsed_msec: int,
		path := SETTINGS_PATH) -> bool:
	if renderer.is_empty() or exit_code == 0 or exit_code == RELAUNCH_EXIT_CODE \
			or elapsed_msec < 0 or elapsed_msec >= TRIAL_FAILURE_WINDOW_MSEC:
		return false
	var config := ConfigFile.new()
	if not FileAccess.file_exists(path) or config.load(path) != OK:
		return false
	if startable(_setting_text(config, "renderer", "auto")) \
			or _setting_text(config, AUTO_RENDERER_KEY, "") != renderer \
			or _setting_text(config, AUTO_STATE_KEY, "") != TRIAL_STATE:
		return false
	config.set_value(SETTINGS_SECTION, AUTO_STATE_KEY, FAILED_START_STATE)
	return config.save(path) == OK

## LAUNCHER_FEATURES_ENV's value for a game this updater starts: `existing`
## with RELAUNCH_FEATURE added once.
static func launcher_features(existing: String) -> String:
	var features := PackedStringArray()
	for feature: String in existing.split(",", false):
		var name := feature.strip_edges()
		if not name.is_empty() and not name in features:
			features.append(name)
	if not RELAUNCH_FEATURE in features:
		features.append(RELAUNCH_FEATURE)
	return ",".join(features)

## Performance is an explicit request for a cheaper graphics configuration.
## Linux's Automatic path otherwise keeps Forward+, even on low-VRAM GPUs.
## Keep a renderer the player deliberately selected on every platform.
static func performance_renderer(preference: String, platform := OS.get_name()) -> String:
	var renderer := renderer_name(preference)
	return "gl_compatibility" if platform == "Linux" and renderer == "auto" else renderer

static func renderer_arguments(renderer: String) -> PackedStringArray:
	if renderer == "gl_compatibility":
		return PackedStringArray(["--rendering-method", renderer, "--rendering-driver", "opengl3"])
	if renderer in ["forward_plus", "mobile"]:
		# Mobile keeps the project's driver (Vulkan, falling back to Direct3D 12).
		return PackedStringArray(["--rendering-method", renderer])
	return PackedStringArray()

## Whether `user_args` come from the compatibility or safe-mode launchers,
## which force OpenGL with engine flags (`game_arguments`).
static func compatibility_launch(user_args: PackedStringArray) -> bool:
	return "--client-compatibility" in user_args or "--client-safe-mode" in user_args

## Direct game launches also honor the saved preference. An explicit engine
## flag wins (including the compatibility launchers); the marker prevents a
## restart loop if the engine falls back from the requested renderer. Godot
## consumes `--rendering-method` and `--rendering-driver` before
## OS.get_cmdline_args(), so in a real launch only the launchers' user
## arguments show that OpenGL was forced.
static func needs_renderer_restart(renderer: String, current: String,
		engine_args: PackedStringArray, user_args: PackedStringArray, headless: bool) -> bool:
	if OS.has_feature("web") or headless or renderer == "auto" or renderer == current or RENDERER_RESTART in user_args \
			or compatibility_launch(user_args):
		return false
	for argument: String in engine_args:
		if argument in ["--script", "-s", "--editor", "-e", "--editor-pid", "--rendering-method", "--rendering-driver"] \
				or argument.begins_with("--rendering-method=") or argument.begins_with("--rendering-driver="):
			return false
	return true

static func restart_arguments(renderer: String, engine_args: PackedStringArray,
		user_args: PackedStringArray) -> PackedStringArray:
	var args := PackedStringArray()
	for argument: String in engine_args:
		if argument == "--":
			break
		args.append(argument)
	args.append_array(renderer_arguments(renderer))
	args.append("--")
	args.append_array(user_args)
	args.append(RENDERER_RESTART)
	return args

## The arguments the updater starts the game with again after it exited with
## RELAUNCH_EXIT_CODE: `previous` (what it started last) with its renderer
## flags replaced by those of the renderer the settings at `path` start now
## (`effective_renderer`), and RENDERER_RESTART after the user arguments, so
## the relaunched game never asks again (it records a fallback instead).
## Headless and compatibility launches keep their engine arguments.
static func relaunch_arguments(previous: PackedStringArray, path := SETTINGS_PATH) -> PackedStringArray:
	var split := previous.find("--")
	var engine := previous.slice(0, split) if split >= 0 else previous.duplicate()
	var user := previous.slice(split + 1) if split >= 0 else PackedStringArray()
	var args := PackedStringArray()
	if "--headless" in engine or compatibility_launch(user):
		args = engine
	else:
		args = renderer_arguments(effective_renderer(path))
		var skip_value := false
		for argument: String in engine:
			if skip_value:
				skip_value = false
			elif argument in ["--rendering-method", "--rendering-driver"]:
				skip_value = true
			elif not argument.begins_with("--rendering-method=") and not argument.begins_with("--rendering-driver="):
				args.append(argument)
	args.append("--")
	args.append_array(user)
	if not RENDERER_RESTART in user:
		args.append(RENDERER_RESTART)
	return args

## `path`: the settings file whose renderer to start (tests pass their own).
static func game_arguments(user_args: PackedStringArray, defaults: PackedStringArray,
		install_root: String, headless: bool, path := SETTINGS_PATH) -> PackedStringArray:
	var args := PackedStringArray()
	if headless:
		args.append("--headless")
	var safe := "--client-safe-mode" in user_args
	var compatibility := safe or "--client-compatibility" in user_args
	if compatibility:
		args.append_array(["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])
	elif not headless:
		args.append_array(renderer_arguments(effective_renderer(path)))
	if compatibility or "--client-debug" in user_args:
		var log_name := "eloria-safe-mode.log" if safe else (
			"eloria-compatibility.log" if compatibility else "eloria-debug.log")
		args.append_array(["--verbose", "--log-file", install_root.path_join(log_name)])
	args.append("--")
	args.append_array(defaults)
	for argument: String in user_args:
		args.append(argument)
	return args

static func apply_environment(user_args: PackedStringArray) -> void:
	if "--client-safe-mode" in user_args:
		# These overrides last for this process and its child, and never save
		# over the player's graphics preferences.
		OS.set_environment("ELORIA_LOOK", "0")
		OS.set_environment("ELORIA_LOOK_QUALITY", "low")
		OS.set_environment("ELORIA_VRAM_TEXTURES", "0")
		OS.set_environment("ELORIA_NO_MAP_CACHE", "1")
