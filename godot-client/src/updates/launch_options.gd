extends RefCounted
## Keep engine switches before `--`; everything after it belongs to the game.
## The restart launcher must preserve this separation when spawning its child.

const RENDERERS := ["auto", "forward_plus", "gl_compatibility"]
const RENDERER_RESTART := "--graphics-renderer-restarted"
const CONTEXT_ENV := "RABBITLANDS_LAUNCH_CONTEXT"

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

static func resume_context(engine_args: PackedStringArray, user_args: PackedStringArray) -> Dictionary:
	# Preserve the active renderer and diagnostic log without carrying editor,
	# script, pack or project-path overrides into the newly installed game.
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
	var user := PackedStringArray(context.user)
	# Reuse the allow-list when consuming the handoff, too.
	if resume_context(engine, user).engine != Array(engine):
		return PackedStringArray()
	engine.append("--")
	engine.append_array(user)
	return engine

static func saved_renderer(path := "user://eloria_hud.cfg") -> String:
	var config := ConfigFile.new()
	config.load(path)
	return renderer_name(config.get_value("graphics", "renderer", "auto"))

static func renderer_name(value: Variant) -> String:
	return str(value) if value is String and value in RENDERERS else "auto"

## Performance is an explicit request for a cheaper graphics configuration.
## Linux's Automatic path otherwise keeps Forward+, even on low-VRAM GPUs.
## Keep a renderer the player deliberately selected on every platform.
static func performance_renderer(preference: String, platform := OS.get_name()) -> String:
	var renderer := renderer_name(preference)
	return "gl_compatibility" if platform == "Linux" and renderer == "auto" else renderer

static func renderer_arguments(renderer: String) -> PackedStringArray:
	if renderer == "gl_compatibility":
		return PackedStringArray(["--rendering-method", renderer, "--rendering-driver", "opengl3"])
	if renderer == "forward_plus":
		return PackedStringArray(["--rendering-method", renderer])
	return PackedStringArray()

## Direct game launches also honor the saved preference. An explicit engine
## flag wins (including the compatibility launchers); the marker prevents a
## restart loop if the engine falls back from the requested renderer.
static func needs_renderer_restart(renderer: String, current: String,
		engine_args: PackedStringArray, user_args: PackedStringArray, headless: bool) -> bool:
	if headless or renderer == "auto" or renderer == current or RENDERER_RESTART in user_args:
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

static func game_arguments(user_args: PackedStringArray, defaults: PackedStringArray,
		install_root: String, headless: bool) -> PackedStringArray:
	var args := PackedStringArray()
	if headless:
		args.append("--headless")
	var safe := "--client-safe-mode" in user_args
	var compatibility := safe or "--client-compatibility" in user_args
	if compatibility:
		args.append_array(["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])
	elif not headless:
		args.append_array(renderer_arguments(saved_renderer()))
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
