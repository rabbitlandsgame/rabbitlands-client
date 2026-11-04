extends Node
## Release-build diagnostics use the engine's rotating log, including engine
## errors. Callers pass selected technical fields, never packets, credentials,
## chat, server reply text or the full command line.

var _driver_thread: Thread
static var _startup_stage := ""
static var _startup_stage_started := 0
const GraphicsOptions := preload("res://src/world/graphics_options.gd")
const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const RendererPolicy := preload("res://src/runtime/renderer_policy.gd")

static func record(event: String, details: Dictionary = {}) -> void:
	var row := details.duplicate()
	row["event"] = event
	row["elapsed_ms"] = Time.get_ticks_msec()
	row["time_utc"] = Time.get_datetime_string_from_system(true)
	print("client_diagnostic ", JSON.stringify(row))

## Named, non-overlapping startup intervals. No player data is recorded.
static func startup_stage(next_stage: String) -> void:
	var now := Time.get_ticks_usec()
	if not _startup_stage.is_empty():
		record("startup_stage", {"stage": _startup_stage,
			"duration_ms": (now - _startup_stage_started) / 1000.0})
	_startup_stage = next_stage
	_startup_stage_started = now

## True while this process is quitting to restart into another renderer
## (RendererPolicy.restart): Main skips its setup then, which the new process
## repeats.
static func restart_pending() -> bool:
	return RendererPolicy.restarting

## The startup record's renderer-policy fields, from RendererPolicy.reconcile's
## result (`policy`) and HardwareTier.seed_first_run's (`tier`).
static func renderer_policy_fields(policy: Dictionary, tier: Dictionary) -> Dictionary:
	var values: Dictionary = policy.get("values", {})
	var setting: Dictionary = policy.get("policy", {})
	var fields := {
		"renderer_effective": policy.get("effective", "auto"),
		"renderer_requested": policy.get("requested", ""),
		"renderer_fallback": bool(policy.get("fallback", false)),
		"auto_renderer": values.get("auto_renderer", ""),
		"auto_renderer_state": values.get("auto_renderer_state", ""),
		"auto_renderer_attempts": int(values.get("auto_renderer_attempts", 0)),
		"adapter_class": tier.get("adapter_class", ""),
		"renderer_policy": {"integrated_renderer": setting.get("renderer", ""),
			"source": setting.get("source", ""), "action": policy.get("action", "none"),
			"reason": policy.get("reason", "")},
	}
	if not str(setting.get("rejected", "")).is_empty():
		fields.renderer_policy["rejected"] = setting.rejected
	return fields

func _ready() -> void:
	if OS.has_feature("web"): WebPrototype.prepare_preferences()
	# A fresh profile's graphics defaults follow the hardware; before the map
	# texture tier below is read and cached for the session, and before Main
	# builds the login backdrop.
	var tier := HardwareTier.seed_first_run()
	record("hardware_tier", tier)
	# Which renderer Automatic starts here: a first run's recommendation and the
	# trial's outcome, recorded before the restart check reads them.
	var policy := RendererPolicy.reconcile(tier)
	GraphicsOptions.active_texture_skip()
	var renderer := str(policy.effective)
	var current := RenderingServer.get_current_rendering_method()
	if RendererPolicy.needs_restart(renderer, current, OS.get_cmdline_args(), OS.get_cmdline_user_args(),
			DisplayServer.get_name() == "headless"):
		var plan := RendererPolicy.restart(get_tree(), renderer)
		record("renderer_restart", {"renderer": renderer, "from": current, "mode": plan.mode,
			"attempts": plan.get("attempts", -1), "renderer_policy": renderer_policy_fields(policy, tier).renderer_policy})
		return
	if float(policy.confirm_after) > 0.0:
		get_tree().create_timer(float(policy.confirm_after), true, false, true).timeout.connect(
			func() -> void: record("renderer_confirmed", RendererPolicy.confirm()))
	var identity: Dictionary = {}
	if FileAccess.file_exists("res://data/client_release.json"):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://data/client_release.json"))
		if parsed is Dictionary:
			identity = parsed
	record("startup", renderer_policy_fields(policy, tier).merged({
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
	}))
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
