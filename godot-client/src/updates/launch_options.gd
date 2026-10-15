extends RefCounted
## Keep engine switches before `--`; everything after it belongs to the game.
## The restart launcher must preserve this separation when spawning its child.

static func game_arguments(user_args: PackedStringArray, defaults: PackedStringArray,
		install_root: String, headless: bool) -> PackedStringArray:
	var args := PackedStringArray()
	if headless:
		args.append("--headless")
	var safe := "--client-safe-mode" in user_args
	var compatibility := safe or "--client-compatibility" in user_args
	if compatibility:
		args.append_array(["--rendering-method", "gl_compatibility", "--rendering-driver", "opengl3"])
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
