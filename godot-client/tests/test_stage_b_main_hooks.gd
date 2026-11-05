extends SceneTree
## Wave 2 stage B hook commit (group B5): the wiring of the hooks that the
## stage-B chunks asked for in files they did not own. Each provider's suite
## tests its behaviour (test_renderer_policy, test_light_marker_budget,
## test_low_end_graphics, test_client_runtime_main_lifecycle, test_exit_drain
## --mode=main, test_world_distance, ...); this checks, on the real main.tscn
## and on the providers' entry points, that the calls sit where they asked:
## - Main._ready: MOB-C3g's restart guard is the first statement; RB-C1g's
##   NativeLibrary.startup() runs before NH-A2's ContentDigest.initialize(),
##   and both before the geometry preparation;
## - WD-C3: one WorldDistance node under world_root, set_quality from
##   _apply_graphics_quality, watch() from _watch_surface_stream, update() per
##   frame with the rig's distance;
## - LIGHT: the budget binds the marker rig, lets go on a map without markers
##   and on a map clear, and is ticked per frame;
## - the startup receipt and the diagnostics snapshot carry the new rows
##   (content_digest, native_runtime, native_kernels, exit_watchdog,
##   actor_reducer);
## - AW-01: _close_client and the maintenance quit go through ExitDrain;
## - MOB-C5: the restart notice asks SettingsWindow.renderer_restart_needed;
## - hardware_tier.gd: ELORIA_VIEW_REACH (WD-C4) and the overhead switch
##   (OV-1) block first-run seeding with the providers' own spellings, and
##   view_reach is logged by switches();
## - the small hooks: the cape loader reason (RB-C1g), the census detail keys
##   (FIX-MEM), the scene-cache format 12 (WD-C2/WD-C5), the cook stages
##   (ALOD-C4/C11) and the setup helper's schema check (UD-05u).

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const NativeLibrary := preload("res://src/runtime/native_library.gd")
const ViewReach := preload("res://src/world/view_reach.gd")
const OverheadLayerScript := preload("res://src/ui/overhead/overhead_layer.gd")
const CapeNativeMath := preload("res://src/actors/cape_native_math.gd")
const MemoryCensus := preload("res://src/runtime/memory_census.gd")
const Release := preload("res://src/updates/release.gd")
const MAIN_SOURCE := "res://src/app/main.gd"

var failures := 0
var checks := 0
var _source := ""

func _init() -> void:
	call_deferred("_run")

func _expect(ok: bool, message: String) -> void:
	checks += 1
	if ok:
		print("PASS: ", message)
	else:
		failures += 1
		push_error("FAIL: " + message)

## The body of `func name(` in main.gd, up to the next top-level func.
func _body(name: String) -> String:
	var start := _source.find("\nfunc %s(" % name)
	if start < 0:
		return ""
	var end := _source.find("\nfunc ", start + 1)
	return _source.substr(start, (end if end > 0 else _source.length()) - start)

## Whether `needles` occur in this order in `text` (each found after the last).
static func _in_order(text: String, needles: Array) -> bool:
	var at := 0
	for needle: Variant in needles:
		var found := text.find(str(needle), at)
		if found < 0:
			return false
		at = found + str(needle).length()
	return true

func _run() -> void:
	_source = FileAccess.get_file_as_string(MAIN_SOURCE).replace("\r\n", "\n")
	_check_main_source()
	_check_hardware_tier()
	_check_small_hooks()
	await _check_main_scene()
	print("stage B main hooks: %d checks, %s" % [checks, "PASS" if failures == 0 else "FAIL (%d)" % failures])
	quit(failures)

# --- main.gd: where each call sits ---------------------------------------------

func _check_main_source() -> void:
	var ready := _body("_ready")
	var first := ready.get_slice("\n", 2).strip_edges()
	_expect(first == "if Diagnostics.restart_pending():"
		and _in_order(ready, ["if Diagnostics.restart_pending():", "_geometry_maintenance_active = true",
			"process_mode = Node.PROCESS_MODE_DISABLED", "hide()", "return", "if OS.has_feature(\"web\"):"]),
		"MOB-C3g: the restart guard is _ready's first statement and returns before the web branch")
	_expect(_in_order(ready, ["Diagnostics.startup_stage(\"geometry_preparation\")", "NativeLibrary.startup()",
			"ContentDigest.initialize()", "if await _prepare_geometry_before_login():", "client_runtime.initialize()"]),
		"RB-C1g before NH-A2, both after the geometry_preparation stage and before the preparation and the runtime")
	_expect(ready.count("NativeLibrary.startup()") == 1 and ready.count("ContentDigest.initialize()") == 1,
		"each startup call is made once")
	_expect(_in_order(ready, ["world_root.add_child(night_lamps)", "world_distance = WorldDistanceScript.new()",
			"world_root.add_child(world_distance)"]), "WD-C3: Main creates its WorldDistance node beside the night lamps")
	var process := _body("_process")
	var visible_block := process.get_slice("\tif game_view.visible:\n", 1)
	_expect(_in_order(visible_block, ["night_lamps.update(camera_rig.focus", "light_marker_budget.update(camera_rig.focus)",
			"world_distance.update(camera_rig.distance, LookProfile.quality(),",
			"campaign_scene.playing or campaign_cutaway.presenting)"]),
		"LIGHT and WD-C3: both per-frame calls follow the night lamps inside `if game_view.visible:`")
	_expect(_in_order(_body("_apply_graphics_quality"), ["LookSwitch.apply_shadow_quality(world_sun)",
			"world_distance.set_quality(LookProfile.quality())", "crowd.set_quality("]),
		"WD-C3: a quality change reaches the world distance pass")
	_expect(_in_order(_body("_watch_surface_stream"), ["night_lamps.watch(chunk_stream)",
			"if chunk_stream != null and world_distance != null:", "world_distance.watch(chunk_stream)"]),
		"WD-C3: every watched chunk stream is handed to the world distance pass")
	var bind := _body("_bind_light_markers")
	_expect(_in_order(bind, ["LightMarkerBinder.apply(manifest, root_node)", "if bound == 0:",
			"light_marker_budget.bind(null)", "root_node.queue_free()", "map_light_root = root_node",
			"light_marker_budget.bind(root_node)", "print_debug(\"light_markers map="]),
		"LIGHT: _bind_light_markers binds the rig it built and lets go when the map declares none")
	_expect(_in_order(_body("_clear_world_presentation"), ["if not retain_map_resources:",
			"map_light_root.queue_free()", "map_light_root = null", "light_marker_budget.bind(null)"]),
		"LIGHT: the map clear lets go of the freed rig")
	_expect(_body("_refresh_graphics_restart_notice").contains(
			"SettingsWindowScript.renderer_restart_needed(_renderer_preference, _startup_renderer_preference)")
		and not _body("_refresh_graphics_restart_notice").contains("_renderer_preference != _startup_renderer_preference"),
		"MOB-C5: the restart notice compares the renderer a choice starts with the running one")
	var close := _body("_close_client")
	_expect(_in_order(close, ["if not ExitDrain.begin(\"close\"):", "return", "_flush_hud_settings_save(true)",
			"ExitDrain.wait_until(get_tree(), \"actor_warmup\"", "ExitDrain.wait_until(get_tree(), \"rl_head_warm\"",
			"ExitDrain.wait_until(get_tree(), \"exterior_stream\"", "ExitDrain.wait_until(get_tree(), \"world_park\"",
			"world_park.release_now()", "ExitDrain.quit(get_tree(), 0, \"close\")"])
		and not close.contains("get_tree().quit(") and not close.contains("\n\twhile "),
		"AW-01: _close_client drains through ExitDrain, bounded, and quits through it")
	_expect(_body("_prepare_geometry_before_login").contains(
			"ExitDrain.quit(get_tree(), 0 if bool(report.get(\"ok\", false)) else 1, \"prepare_map_geometry\")")
		and not _body("_prepare_geometry_before_login").contains("get_tree().quit("),
		"AW-01: the explicit geometry preparation quits through ExitDrain with its 0/1 code")
	var receipt := _body("_log_optimization_startup")
	_expect(_in_order(receipt, ["\"effects\": RustSpellFlights.snapshot_for(world_root),",
			"\"content_digest\": ContentDigest.snapshot(),", "\"native_runtime\": NativeLibrary.snapshot(),",
			"\"native_kernels\": NativeCrowd.snapshot(),", "\"exit_watchdog\": ClientRuntime.exit_watchdog_state(),"]),
		"the startup receipt names the digest backend, the native runtime, the kernels and the watchdog")

# --- hardware_tier.gd ----------------------------------------------------------------

func _launch(extra := {}) -> Dictionary:
	var launch := {"web": false, "headless": false, "engine_args": PackedStringArray(),
		"user_args": PackedStringArray(), "overrides": PackedStringArray()}
	launch.merge(extra, true)
	return launch

func _check_hardware_tier() -> void:
	_expect(HardwareTier.VIEW_REACH_VARIABLE == ViewReach.VARIABLE and HardwareTier.VIEW_REACH_MODES == ViewReach.MODES,
		"WD-C4: hardware_tier spells ELORIA_VIEW_REACH and its modes as view_reach.gd does")
	_expect(HardwareTier.OVERHEAD_2D_VARIABLE == OverheadLayerScript.SWITCH_VARIABLE
		and HardwareTier.OVERHEAD_2D_ARGUMENT == OverheadLayerScript.SWITCH_ARGUMENT,
		"OV-1: hardware_tier spells the overhead switch as overhead_layer.gd does")
	var previous := {}
	for variable: String in [HardwareTier.VIEW_REACH_VARIABLE, HardwareTier.OVERHEAD_2D_VARIABLE,
			HardwareTier.WORLD_DISTANCE_VARIABLE]:
		previous[variable] = OS.get_environment(variable)
		OS.unset_environment(variable)
	_expect(not HardwareTier.switches().has("view_reach"), "an unset ELORIA_VIEW_REACH adds no switch entry")
	for variable: String in [HardwareTier.VIEW_REACH_VARIABLE, HardwareTier.OVERHEAD_2D_VARIABLE]:
		OS.set_environment(variable, "off")
		_expect(variable in HardwareTier.OVERRIDE_VARIABLES and variable in HardwareTier.launch_context().overrides
			and HardwareTier.blocker(HardwareTier.launch_context().merged({"headless": false,
				"engine_args": PackedStringArray()}, true)) == "environment_override",
			"%s keeps a first run from being seeded" % variable)
		OS.unset_environment(variable)
	_expect(HardwareTier.blocker(_launch({"user_args": PackedStringArray(["--overhead-2d=off"])})) == "argument_override"
		and HardwareTier.blocker(_launch({"user_args": PackedStringArray(["--overhead-2dx"])})) == "",
		"--overhead-2d= keeps a first run from being seeded; an unrelated argument does not")
	var table := {"ground": "ground", " Ground ": "ground", "off": "off", "0": "off", "false": "off", "auto": "auto",
		"on": "auto", "1": "auto", "bogus": "auto"}
	var agreed := true
	for value: String in table:
		OS.set_environment(HardwareTier.VIEW_REACH_VARIABLE, value)
		var logged := HardwareTier.switches()
		var wanted: String = table[value]
		agreed = agreed and str(logged.get("view_reach", "")) == wanted and ViewReach.mode_from_environment() == wanted \
			and (value != "bogus" or str(logged.get("rejected", {}).get("view_reach", "")) == "bogus")
		if not agreed:
			print("view_reach mismatch for %s: %s / %s" % [value, logged, ViewReach.mode_from_environment()])
			break
	_expect(agreed, "switches() logs ELORIA_VIEW_REACH as view_reach.gd reads it (and an unknown value as rejected)")
	for variable: String in previous:
		if str(previous[variable]).is_empty():
			OS.unset_environment(variable)
		else:
			OS.set_environment(variable, str(previous[variable]))

# --- the small hooks ------------------------------------------------------------------

func _check_small_hooks() -> void:
	_expect(CapeNativeMath.reason_for({"code": NativeLibrary.SWITCHED_OFF}) == "native_runtime_switched_off"
		and CapeNativeMath.reason_for({"code": "loaded"}) == "",
		"RB-C1g: mounted cape math names the native kill switch")
	var row := MemoryCensus.cache_row({"entries": 1, "bytes": 2, "world_released_bytes": 3, "world_retained_bytes": 4})
	var source := GlbSceneCache.retention_snapshot()
	_expect(int(row.get("world_released_bytes", -1)) == 3 and int(row.get("world_retained_bytes", -1)) == 4
		and source.has("world_released_bytes") and source.has("world_retained_bytes"),
		"FIX-MEM: the census row carries the world release detail the scene cache reports")
	_expect(MapSceneCache.CACHE_FORMAT_VERSION == 12, "WD-C2/WD-C5: the scene-cache format is 12")
	var cook := load("res://tools/actor_geometry/cook.gd") as GDScript
	var constants: Dictionary = cook.get_script_constant_map() if cook != null else {}
	var cook_source := FileAccess.get_file_as_string("res://tools/actor_geometry/cook.gd").replace("\r\n", "\n")
	_expect(constants.get("LiningPolicy") == preload("res://tools/actor_geometry/lining_policy.gd")
		and constants.get("BudgetPolicy") == preload("res://tools/actor_geometry/budget_policy.gd")
		and _in_order(cook_source, ["var plan := plan_state(parsed.state,",
			"plan = LiningPolicy.apply(parsed.state, plan, item.get(\"lining\", {}))",
			"plan = BudgetPolicy.apply(parsed.state, plan, item.get(\"budget\", {}))", "summary[\"meshes\"] = plan.meshes"]),
		"ALOD-C4/C11: the cook runs the lining stage, then the budget stage, on the plan")
	var setup := FileAccess.get_file_as_string("res://tools/install_client_payload.gd")
	_expect(setup.contains("if not manifest.has(\"error\") and Release.package_manifest(manifest):")
		and not setup.contains("manifest.schema == 2") and Release.package_manifest({"schema": 3.0})
		and Release.package_manifest({"schema": 2}) and not Release.package_manifest({"schema": 1}),
		"UD-05u: the setup helper installs schema 2 and 3 manifests by packages")

# --- the real Main ----------------------------------------------------------------

func _check_main_scene() -> void:
	var main: Variant = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	for frame: int in 4:
		await process_frame
	var native := NativeLibrary.snapshot()
	_expect(not (native.startup as Dictionary).is_empty() and str(native.startup.code) == str(native.code),
		"RB-C1g: Main's startup load ran (%s)" % native.startup)
	var digest := ContentDigest.snapshot()
	_expect(bool(digest.initialized), "NH-A2: Main resolved the content digest (%s, %s)" % [digest.backend, digest.reason])
	var row: Dictionary = main.client_diagnostic_snapshot()
	_expect((row.get("native_runtime", {}) as Dictionary).get("startup", {}) == native.startup
		and (row.get("native_kernels", {}) as Dictionary).has("features")
		and str((row.get("actor_reducer", {}) as Dictionary).get("mode", "")) \
			== str(root.get_node("/root/AppState").get("actor_reducer_mode"))
		and bool((row.get("content_digest", {}) as Dictionary).get("initialized", false)),
		"the diagnostics snapshot carries native_runtime, native_kernels, actor_reducer and content_digest")

	# WD-C3: the node, the quality and the streams.
	var distance: Node = main.world_distance
	_expect(distance != null and distance.get_parent() == main.world_root and distance.is_inside_tree(),
		"WD-C3: Main's WorldDistance node stands under world_root")
	if distance == null:
		main.queue_free()
		return
	var other := (LookProfile.quality() + 1) % LookProfile.QUALITY_NAMES.size()
	distance.update(30.0, other)
	main._apply_graphics_quality()
	_expect(int(distance.quality) == LookProfile.quality() and is_equal_approx(float(distance.camera_distance), 30.0),
		"WD-C3: _apply_graphics_quality hands the quality in use to the pass (%d)" % int(distance.quality))
	var stream := ContinentChunkStream.new()
	main._watch_surface_stream(stream)
	_expect((distance.get("_streams") as Array).has(stream), "WD-C3: a watched chunk stream reaches the pass")
	stream.free()

	# LIGHT: bind, let go, and the per-frame tick.
	var budget: RefCounted = main.light_marker_budget
	var markers: Array = []
	for index: int in 30:
		markers.append({"id": "b5-hook-%d" % index, "position": [index * 1.0, 1.0, 0.0]})
	var manifest := WorldManifest.new()
	manifest.data = {"schemaVersion": "1.0",
		"asset": {"id": "b5_hook_probe", "name": "B5 Hook Probe", "glb": "world.glb",
			"units": "meters", "coordinateSystem": {"upAxis": "Y"}, "bounds": {}},
		"lighting": {"markers": markers}}
	main._bind_light_markers(manifest)
	var rig: Node3D = main.map_light_root
	_expect(rig != null and bool(budget.call("is_bound")) and LightMarkerBinder.budgeted(rig),
		"LIGHT: the budget takes the rig _bind_light_markers built")

	# The per-frame calls: the game view shown, the rig's distance and focus.
	main.camera_rig.distance = 41.0
	main.game_view.show()
	for frame: int in 3:
		await process_frame
	_expect(is_equal_approx(float(distance.camera_distance), 41.0) and int(distance.quality) == LookProfile.quality(),
		"WD-C3: the pass follows the rig's distance each frame (%.1f m)" % float(distance.camera_distance))
	_expect(float(budget.get("_now")) >= 0.0 and (budget.get("_focus") as Vector3).is_equal_approx(main.camera_rig.focus),
		"LIGHT: the budget is ticked each frame with the camera focus")
	main.game_view.hide()

	var empty := WorldManifest.new()
	empty.data = {"schemaVersion": "1.0",
		"asset": {"id": "b5_hook_empty", "name": "B5 Hook Empty", "glb": "world.glb",
			"units": "meters", "coordinateSystem": {"upAxis": "Y"}, "bounds": {}},
		"lighting": {"markers": []}}
	main._bind_light_markers(empty)
	_expect(not bool(budget.call("is_bound")) and main.map_light_root == null,
		"LIGHT: a map without markers leaves the budget unbound")
	main._bind_light_markers(manifest)
	_expect(bool(budget.call("is_bound")), "(fixture) bound again")
	main._clear_world_presentation(false)
	_expect(not bool(budget.call("is_bound")), "LIGHT: a map clear lets go of the rig at once")

	main.queue_free()
	await process_frame
	await process_frame
