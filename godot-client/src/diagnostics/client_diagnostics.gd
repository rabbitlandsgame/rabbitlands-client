extends Node
## Release-build diagnostics use the engine's rotating log, including engine
## errors. Callers pass selected technical fields, never packets, credentials,
## chat, server reply text or the full command line.

var _driver_thread: Thread
const LaunchOptions := preload("res://src/updates/launch_options.gd")
const GraphicsOptions := preload("res://src/world/graphics_options.gd")

static func record(event: String, details: Dictionary = {}) -> void:
	var row := details.duplicate()
	row["event"] = event
	row["elapsed_ms"] = Time.get_ticks_msec()
	row["time_utc"] = Time.get_datetime_string_from_system(true)
	print("client_diagnostic ", JSON.stringify(row))

func _ready() -> void:
	GraphicsOptions.active_texture_skip()
	var renderer := LaunchOptions.saved_renderer()
	if LaunchOptions.needs_renderer_restart(renderer, RenderingServer.get_current_rendering_method(),
			OS.get_cmdline_args(), OS.get_cmdline_user_args(), DisplayServer.get_name() == "headless"):
		OS.set_restart_on_exit(true, LaunchOptions.restart_arguments(renderer,
			OS.get_cmdline_args(), OS.get_cmdline_user_args()))
		get_tree().quit()
		return
	var identity: Dictionary = {}
	if FileAccess.file_exists("res://data/client_release.json"):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/client_release.json"))
		if parsed is Dictionary:
			identity = parsed
	record("startup", {
		"build_commit": identity.get("commit", "") if not str(identity.get("commit", "")).is_empty() else "source",
		"build_platform": identity.get("platform", "source"),
		"engine": Engine.get_version_info().get("string", ""),
		"debug_build": OS.is_debug_build(), "os": OS.get_name(),
		"os_version": OS.get_version(), "cpu": OS.get_processor_name(),
		"cpu_threads": OS.get_processor_count(), "memory": OS.get_memory_info(),
		"display_driver": DisplayServer.get_name(),
		"renderer": RenderingServer.get_current_rendering_method(),
		"rendering_driver": RenderingServer.get_current_rendering_driver_name(),
		"gpu": RenderingServer.get_video_adapter_name(),
		"gpu_vendor": RenderingServer.get_video_adapter_vendor(),
		"graphics_api": RenderingServer.get_video_adapter_api_version(),
		"s3tc": RenderingServer.has_os_feature("s3tc"),
		"rgtc": RenderingServer.has_os_feature("rgtc"),
		"bptc": RenderingServer.has_os_feature("bptc"),
		"window_size": str(get_window().size),
		"user_data_dir": OS.get_user_data_dir(),
		"default_log_path": ProjectSettings.globalize_path(str(ProjectSettings.get_setting(
			"debug/file_logging/log_path", "user://logs/client.log"))),
		"look_override": OS.get_environment("ELORIA_LOOK"),
		"quality_override": OS.get_environment("ELORIA_LOOK_QUALITY"),
		"vram_override": OS.get_environment("ELORIA_VRAM_TEXTURES"),
		"no_map_cache": OS.get_environment("ELORIA_NO_MAP_CACHE") == "1"
	})
	# Driver discovery can take seconds on Windows. Query once off the main
	# thread, without stalling login or touching rendering objects there.
	if DisplayServer.get_name() != "headless" and OS.get_name() in ["Windows", "Linux", "FreeBSD"]:
		_driver_thread = Thread.new()
		var error := _driver_thread.start(func() -> void:
			record("graphics_driver", {"driver_info": OS.get_video_adapter_driver_info()}))
		if error != OK:
			_driver_thread = null
			record("graphics_driver_query_failed", {"error": error_string(error)})

func _process(_delta: float) -> void:
	if _driver_thread != null and not _driver_thread.is_alive():
		_driver_thread.wait_to_finish()
		_driver_thread = null
	if _driver_thread == null:
		set_process(false)

func _exit_tree() -> void:
	if _driver_thread != null:
		_driver_thread.wait_to_finish()
		_driver_thread = null
