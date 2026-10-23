extends RefCounted
## Keep engine switches before `--`; everything after it belongs to the game.
## The restart launcher must preserve this separation when spawning its child.

const RENDERERS := ["auto", "forward_plus", "gl_compatibility"]
const RENDERER_RESTART := "--graphics-renderer-restarted"

static func saved_renderer(path := "user://eloria_hud.cfg") -> String:
	var config := ConfigFile.new()
	config.load(path)
	return renderer_name(config.get_value("graphics", "renderer", "auto"))

static func renderer_name(value: Variant) -> String:
	return str(value) if value is String and value in RENDERERS else "auto"

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
		if argument not in ["--client-debug", "--client-compatibility", "--client-safe-mode"]:
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
