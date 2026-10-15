extends SceneTree
## Repeatable landscape survey in the complete client, using its actual camera,
## environment, static batching, ground sampler, minimap and occluder fade.
## ELORIA_SURVEY_SPEC points at JSON [{map,id,x,z,yaw?,distance?}].
##
## ELORIA_SURVEY_UNCAPPED=1 also times each view without a frame cap: once main
## has applied the player's settings (which may cap the frame rate) it sets
## Engine.max_fps to 0 and turns vsync off, and before each capture it reads
## the renderer's own timers (RenderingServer's measured render time, GPU and
## CPU) for the 3D viewport, the minimap viewport and the window over
## UNCAPPED_FRAMES frames, and writes their medians to survey.json as
## `render_ms`. Those timers time the renderer's work for each viewport, which
## holds still while the desktop compositor throttles a window that is not in
## front (the uncapped wall time, `uncapped_frame_ms`, jumps between 240, 120
## and 60 Hz plateaus there, so it is kept only as a sanity check). They do not
## include the scene tree's own CPU time (scripts, physics, animation), which a
## headless run with the low-processor sleep removed measures instead.
##
## ELORIA_SURVEY_LIVE_TOGGLE=1 then switches the painted look off in the
## running client, through main's settings path as the settings window does,
## captures <id>_live_off.png, switches it back on and captures
## <id>_live_on.png, each after the same settling as the view's own capture,
## and records how long each switch took. The client has to be started with
## ELORIA_LOOK unset (the look on by its settings file), or the variable
## decides and the switch does nothing. Main saves the switch to the settings
## file, as it does for a player, so each toggle copies the file first and
## puts it back once both captures are taken: a run by hand outside a scratch
## user directory leaves the player's own settings as they were.
##
## ELORIA_SURVEY_CHUNK_WAIT_S raises the 90 s the survey waits for the
## selected geometry chunks of a view (a render-only manifest that keeps a
## whole territory resident streams hundreds of cells one by one).
##
## A spec with `"top": {"size", "height", "far", "haze", "tiles": [[x, z],
## ...]}` is a whole-territory overview instead of a rig view: once its chunks
## are ready, an orthographic camera looks straight down (north up) from
## `height` over each tile centre, `size` metres of frame height, and the 3D
## viewport alone (no HUD) is saved as <id>_<nn>.png; survey.json lists each
## tile's centre, size and pixels for the mosaic. `"haze": false` draws the
## tiles without the depth fog, which is keyed to the game camera's depth and
## would veil ground seen from hundreds of metres up. The rig, its focus and
## the streaming focus stay where the spec put them.
const UNCAPPED_VARIABLE := "ELORIA_SURVEY_UNCAPPED"
const CHUNK_WAIT_VARIABLE := "ELORIA_SURVEY_CHUNK_WAIT_S"
const UNCAPPED_FRAMES := 60
const LIVE_TOGGLE_VARIABLE := "ELORIA_SURVEY_LIVE_TOGGLE"
const SETTINGS_PATH := "user://eloria_hud.cfg"
var main: Control
var state: Node
var out: String
var report: Array = []
var uncapped := false

static func _override_registry(registry: Dictionary, data: Dictionary, path: String, specs: Array) -> Dictionary:
	var entry := MapRegistry.resolve(registry, str(data.get("asset", {}).get("id", "")))
	if entry.is_empty() or path.is_empty() or not data.get("coordinateTransform") is Dictionary:
		return {"error": "Candidate manifest has no unique registry target/path/coordinate transform"}
	var key := str(entry.registryKey)
	var selected := false
	for spec: Dictionary in specs:
		if str(MapRegistry.resolve(registry, str(spec.get("map", ""))).get("registryKey", "")) == key:
			selected = true
	if not selected:
		return {"error": "Candidate registry target is absent from the requested survey: " + key}
	# Resolve aliases exactly as the production loader does. Four's asset id
	# is four-gates, whose alias points to the actual four_gates registry row.
	registry[key]["manifest"] = path
	registry[key]["coordinateTransform"] = data.coordinateTransform.duplicate(true)
	return {"registryKey": key, "manifest": path}

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	out = OS.get_environment("ELORIA_ARTIFACT_DIR")
	DirAccess.make_dir_recursive_absolute(out)
	root.size = Vector2i(1440, 900)
	main = (load("res://src/app/main.tscn") as PackedScene).instantiate()
	root.add_child(main)
	await process_frame
	# main's _ready has applied the player's saved settings by now, fps cap
	# included, so lifting the cap here is not undone by them.
	uncapped = OS.get_environment(UNCAPPED_VARIABLE) == "1"
	if uncapped:
		_lift_frame_cap()
		print("SURVEY_UNCAPPED max_fps=", Engine.max_fps, " vsync=",
			DisplayServer.window_get_vsync_mode(), " renderer=",
			RenderingServer.get_current_rendering_method())
	state = root.get_node("AppState")
	var specs: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("ELORIA_SURVEY_SPEC")))
	# A complete composed continent can be inspected before server publication.
	# Every coordinate below comes from its real exported manifest and generated
	# crossing graph; the override only lives in this renderer process.
	var world_override := OS.get_environment("ELORIA_SURVEY_WORLD")
	if not world_override.is_empty():
		var composed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(world_override))
		var registry: Dictionary = main.get("map_registry")
		for map_id: String in composed.maps:
			var path := str(composed.maps[map_id])
			var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
			var entry := MapRegistry.resolve(registry,map_id)
			if entry.is_empty() or str(data.get("asset", {}).get("id", "")) != map_id:
				push_error("Composed survey manifest identity mismatch: " + map_id)
				quit(2)
				return
			registry[str(entry.registryKey)]["manifest"] = path
			registry[str(entry.registryKey)]["coordinateTransform"] = data.coordinateTransform.duplicate(true)
		var stream: ExteriorRegionStream = main.get("exterior_stream")
		stream.registry = registry
		stream.links = composed.graph.connections.duplicate(true)
		stream.links.append_array(composed.graph.get("visualConnections", []))
		stream.preload_distance = float(composed.graph.get("preloadDistance",320))
		stream.retain_distance = float(composed.graph.get("retainDistance",420))
		print("SURVEY_COMPOSED_WORLD source=",world_override," maps=",composed.maps.size())
	var override_path := OS.get_environment("ELORIA_SURVEY_MANIFEST")
	var override_key := ""
	if not override_path.is_empty():
		var override_data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(override_path))
		var registry: Dictionary = main.get("map_registry")
		var applied := _override_registry(registry, override_data, override_path, specs)
		if applied.has("error"):
			push_error(str(applied.error))
			quit(2)
			return
		override_key = str(applied.registryKey)
		print("SURVEY_OVERRIDE selected asset=", override_data.asset.id,
			" registry_key=", override_key, " manifest=", override_path)
	state.set("authenticated", true)
	main.get("login_panel").hide()
	main.get("creation_panel").hide()
	main.get("game_view").show()
	state.call("_on_packet", 5, PackedByteArray([180, 0]))
	for spec: Dictionary in specs:
		if state.get("current_map") != spec.map:
			# Survey viewpoints jump across the continent; they are not actor
			# movement packets continuing over a nearby border. Clear the prior
			# actor before world_loaded can interpret its old tile in a new map.
			state.set("actors", {})
			state.set("local_actor_id", -1)
			state.set("current_map", spec.map)
			main.call("_load_server_map")
			var loader: WorldLoader = main.get("world_loader")
			var deadline := Time.get_ticks_msec() + 180000
			while loader.world_root == null and Time.get_ticks_msec() < deadline:
				await process_frame
			if loader.world_root == null:
				push_error("Map failed to load: " + str(spec.map))
				quit(2)
				return
		var active_loader: WorldLoader = main.get("world_loader")
		if not override_key.is_empty() and str(MapRegistry.resolve(main.get("map_registry"), spec.map).get("registryKey", "")) == override_key:
			var actual := ProjectSettings.globalize_path(active_loader.manifest.source_path).replace("\\", "/").simplify_path()
			var expected := ProjectSettings.globalize_path(override_path).replace("\\", "/").simplify_path()
			if actual != expected:
				push_error("Candidate override was not loaded: expected=" + expected + " actual=" + actual)
				quit(2)
				return
			print("SURVEY_OVERRIDE loaded registry_key=", override_key, " manifest=", actual,
				" glb=", active_loader.manifest.glb_path())
		var adapter: CoordinateAdapter = main.get("adapter")
		var tile: Vector2i = adapter.godot_to_server(Vector3(float(spec.x), 0, float(spec.z)))
		var actors := {1: {"actor_id": 1, "x": tile.x, "y": tile.y,
			"rotation": 0, "actor_type": 0, "kind": 1, "name": "Traveller",
			"health": 100, "max_health": 100, "alive": true, "appearance": {}}}
		state.set("local_actor_id", 1)
		state.set("actors", actors)
		state.call("mark_all_actors_changed")
		main.call("_sync_world")
		var rig: Node3D = main.get("camera_rig")
		rig.set("yaw_degrees", float(spec.get("yaw", 0)))
		# The spec may ask for a lower view (a wall or a horn above a site); the rig accepts -80..-15.
		rig.set("pitch_degrees", clampf(float(spec.get("pitch", -60.0)), -80.0, -15.0))
		rig.set("distance", float(spec.get("distance", 26)))
		# Let camera interpolation and the HUD's one-second FPS window settle
		# after a large package load before taking a composition/performance view.
		for i in 120:
			await physics_frame
			await process_frame
		# A border capture must include the actual resident neighbor. Time-based
		# camera settling alone can finish before a cold background import.
		var stream: ExteriorRegionStream = main.get("exterior_stream")
		var candidates := stream._candidates(rig.get("focus"))
		var wanted := stream._wanted_neighbours(candidates)
		for candidate: Dictionary in candidates:
			if (wanted.has(str(candidate.map)) and float(candidate.distance) <= stream.preload_distance
					and (bool(candidate.seamless) or bool(candidate.visual_only))):
				var deadline := Time.get_ticks_msec() + 60000
				while not stream.residents.has(str(candidate.map)) and Time.get_ticks_msec() < deadline:
					await process_frame
				if not stream.residents.has(str(candidate.map)):
					push_error("Neighbor failed to preload for survey")
					quit(2)
					return
		var chunk_wait_ms := 90000
		if not OS.get_environment(CHUNK_WAIT_VARIABLE).is_empty():
			chunk_wait_ms = int(float(OS.get_environment(CHUNK_WAIT_VARIABLE)) * 1000.0)
		var chunk_deadline := Time.get_ticks_msec() + chunk_wait_ms
		while not _resident_chunks_ready(active_loader.world_root, stream) and Time.get_ticks_msec() < chunk_deadline:
			await process_frame
		if not _resident_chunks_ready(active_loader.world_root, stream):
			push_error("Selected geometry chunks failed to become ready for survey")
			quit(2)
			return
		# A cold neighbor import can finish after the initial settling period.
		# Let the HUD's one-second FPS window expire before a steady-view capture.
		await create_timer(1.1).timeout
		if spec.has("top"):
			var tiles := await _capture_top(spec)
			report.append({"id":spec.id,"map":spec.map,"tile":[tile.x,tile.y],"top":tiles,
				"manifest_source":active_loader.manifest.source_path,
				"chunkResidents":_chunk_report(active_loader.world_root, stream),
				"videoMemoryBytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
				"textureMemoryBytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED)})
			print("SURVEY saved ", spec.id, " tiles=", tiles.size())
			continue
		var actor: Node3D = main.get("actor_nodes").get(1)
		var times: Array = []
		for i in 30:
			var start := Time.get_ticks_usec()
			await process_frame
			times.append((Time.get_ticks_usec() - start) / 1000.0)
		var render_timing: Dictionary = {}
		if uncapped:
			render_timing = await _measure_render_time()
		RenderingServer.force_draw(false)
		root.get_texture().get_image().save_png(out.path_join(str(spec.id) + ".png"))
		report.append({"id":spec.id,"map":spec.map,"tile":[tile.x,tile.y],
			"render_ms":render_timing.get("render_ms", {}),
			"uncapped_frame_ms":render_timing.get("uncapped_frame_ms", -1.0),
			"manifest_source":active_loader.manifest.source_path,"glb_path":active_loader.manifest.glb_path(),
			"actor":[actor.position.x,actor.position.y,actor.position.z] if actor else [],
			"resident_maps":stream.residents.keys(), "preload_distance":stream.preload_distance,
			"camera":str(rig.call("camera_diagnostics")), "frame_ms":times,
			"chunkResidents":_chunk_report(active_loader.world_root, stream),
			"staticMemoryBytes":Performance.get_monitor(Performance.MEMORY_STATIC),
			"videoMemoryBytes":Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
			"textureMemoryBytes":Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED),
			"draw_calls":Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
			"primitives":Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
		print("SURVEY saved ", spec.id)
		if OS.get_environment(LIVE_TOGGLE_VARIABLE) == "1":
			(report.back() as Dictionary)["live_toggle"] = await _live_toggle(spec)
	var file := FileAccess.open(out.path_join("survey.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	main.call("_on_disconnect_pressed")
	main.get("exterior_stream").clear()
	while not main.get("exterior_stream").is_idle():
		await process_frame
	for i in 6:
		await process_frame
	main.queue_free()
	await process_frame
	quit()

## The orthographic overview tiles of a `top` spec (see the header). Returns
## one record per tile: file, centre (x, z), frame height and pixel size.
func _capture_top(spec: Dictionary) -> Array:
	var top: Dictionary = spec.top
	var viewport: SubViewport = main.get("main_viewport")
	var rig: Node3D = main.get("camera_rig")
	var rig_camera: Camera3D = rig.get("camera")
	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = float(top.get("size", 300.0))
	camera.near = 1.0
	camera.far = float(top.get("far", 1000.0))
	rig.get_parent().add_child(camera)
	if not bool(top.get("haze", true)):
		var environment := (main.get("world_environment") as WorldEnvironment).environment
		if environment != null:
			# Shallow: shares the Sky, so no second radiance map is allocated.
			var clear := environment.duplicate(false) as Environment
			clear.fog_enabled = false
			clear.volumetric_fog_enabled = false
			camera.environment = clear
	camera.make_current()
	var tiles: Array = []
	var centres: Array = top.get("tiles", [])
	for index in centres.size():
		var centre: Array = centres[index]
		camera.global_transform = Transform3D(Basis.looking_at(Vector3.DOWN, Vector3.FORWARD),
			Vector3(float(centre[0]), float(top.get("height", 400.0)), float(centre[1])))
		for i in 30:
			await process_frame
		RenderingServer.force_draw(false)
		var image := viewport.get_texture().get_image()
		var file := "%s_%02d.png" % [str(spec.id), index]
		image.save_png(out.path_join(file))
		tiles.append({"file": file, "x": float(centre[0]), "z": float(centre[1]), "size": camera.size,
			"pixels": [image.get_width(), image.get_height()]})
	rig_camera.make_current()
	camera.queue_free()
	return tiles

## Lifts every frame cap: Engine.max_fps (the player's fps_limit setting) and
## vsync. Called again before each measurement in case a map load or a
## settings refresh put a cap back.
func _lift_frame_cap() -> void:
	Engine.max_fps = 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)

## Switches the painted look off and back on in the running client and
## captures each (see LIVE_TOGGLE_VARIABLE). Returns what each switch cost.
func _live_toggle(spec: Dictionary) -> Dictionary:
	var result := {"look_before": LookProfile.enabled()}
	var had_settings := FileAccess.file_exists(SETTINGS_PATH)
	var saved_settings := FileAccess.get_file_as_bytes(SETTINGS_PATH) if had_settings \
		else PackedByteArray()
	for step: Array in [["off", false], ["on", true]]:
		var started := Time.get_ticks_usec()
		main.call("_on_client_setting_changed", "Graphics", "look", step[1])
		result[str(step[0]) + "_switch_ms"] = snappedf((Time.get_ticks_usec() - started) / 1000.0, 0.1)
		result[str(step[0]) + "_look"] = LookProfile.enabled()
		for i in 120:
			await physics_frame
			await process_frame
		await create_timer(1.1).timeout
		RenderingServer.force_draw(false)
		root.get_texture().get_image().save_png(out.path_join("%s_live_%s.png" % [spec.id, step[0]]))
		print("SURVEY saved ", spec.id, "_live_", step[0])
	if had_settings:
		var file := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
		file.store_buffer(saved_settings)
		file.close()
	else:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(SETTINGS_PATH))
	return result

## The renderer's measured time per viewport over UNCAPPED_FRAMES frames, as
## medians in milliseconds: {"render_ms": {<viewport>: {"gpu", "cpu"}, "total":
## {"gpu", "cpu"}}, "uncapped_frame_ms": <median wall time>}. "main" is the 3D
## world, "map" the minimap, "window" the root viewport's own 2D drawing (the
## HUD and the world's texture); "total" sums them frame by frame.
func _measure_render_time() -> Dictionary:
	_lift_frame_cap()
	var viewports := {"main": (main.get("main_viewport") as Viewport).get_viewport_rid(),
		"map": (main.get("map_viewport") as Viewport).get_viewport_rid(),
		"window": root.get_viewport_rid()}
	for rid: RID in viewports.values():
		RenderingServer.viewport_set_measure_render_time(rid, true)
	# The GPU timers report a frame or two late; let them fill first.
	for i in 8:
		await process_frame
	var samples := {}
	for key: String in viewports.keys() + ["total"]:
		samples[key] = {"gpu": [], "cpu": []}
	var wall: Array = []
	for i in UNCAPPED_FRAMES:
		var start := Time.get_ticks_usec()
		await process_frame
		wall.append((Time.get_ticks_usec() - start) / 1000.0)
		var gpu_total := 0.0
		var cpu_total := 0.0
		for key: String in viewports.keys():
			var gpu := RenderingServer.viewport_get_measured_render_time_gpu(viewports[key])
			var cpu := RenderingServer.viewport_get_measured_render_time_cpu(viewports[key])
			(samples[key].gpu as Array).append(gpu)
			(samples[key].cpu as Array).append(cpu)
			gpu_total += gpu
			cpu_total += cpu
		(samples.total.gpu as Array).append(gpu_total)
		(samples.total.cpu as Array).append(cpu_total)
	for rid: RID in viewports.values():
		RenderingServer.viewport_set_measure_render_time(rid, false)
	var medians := {}
	for key: String in samples.keys():
		medians[key] = {"gpu": snappedf(_median(samples[key].gpu), 0.001),
			"cpu": snappedf(_median(samples[key].cpu), 0.001)}
	return {"render_ms": medians, "uncapped_frame_ms": snappedf(_median(wall), 0.001)}

static func _median(values: Array) -> float:
	if values.is_empty():
		return -1.0
	var sorted := values.duplicate()
	sorted.sort()
	return float(sorted[sorted.size() / 2])

func _resident_chunks_ready(active: Node3D, stream: ExteriorRegionStream) -> bool:
	var roots: Array = [active]
	for resident: Dictionary in stream.residents.values():
		roots.append(resident.root)
	for imported: Node3D in roots:
		if not imported is ContinentChunkStream:
			continue
		var chunks := imported as ContinentChunkStream
		if not chunks.has_focus or chunks._thread != null or not chunks._retiring.is_empty():
			return false
		for entry: Dictionary in chunks.selection(chunks.focus,true):
			if float(entry.distance) <= chunks.preload_distance and not chunks.cells.has(str(entry.id)):
				return false
	return true

func _chunk_report(active: Node3D, stream: ExteriorRegionStream) -> Dictionary:
	var result: Dictionary = {}
	var roots: Array = [active]
	for resident: Dictionary in stream.residents.values():
		roots.append(resident.root)
	for imported: Node3D in roots:
		if imported is ContinentChunkStream:
			var chunks := imported as ContinentChunkStream
			result[chunks.territory.asset_id()] = {"cells":chunks.cells.keys(),
				"estimatedResidentBytes":chunks.resident_bytes,"maximumResidentBytes":chunks.maximum_resident_bytes,
				"preloadDistance":chunks.preload_distance,"focus":str(chunks.focus)}
	return result
