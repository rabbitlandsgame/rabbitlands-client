extends SceneTree

## A streamed seam must not replace a measured height with the map default,
## or cache a miss forever when the traveller stops on the arrival tile.
var failures := 0
var main: Control

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		push_error(message)
	else:
		print("PASS: ", message)

func settle() -> void:
	for _frame: int in range(4):
		await physics_frame
		await process_frame

func main_surface_connection_count(stream: ContinentChunkStream) -> int:
	var callback := Callable(main, "_on_chunk_surface_ready")
	var count := 0
	for connection: Dictionary in stream.cell_ready.get_connections():
		if connection.get("callable") == callback:
			count += 1
	return count

func cleanup_owned_main(state: Node) -> bool:
	# Intro cancellation must not issue a normal authenticated chat command.
	state.authenticated = false
	state.local_actor_id = -1
	state.selected_actor_id = -1
	state.current_map = ""
	state.actors = {}
	state.map_objects = {}
	state.combat_state = {}
	main.set_process(false)
	main.set_physics_process(false)
	main.set_process_input(false)
	main.set_process_unhandled_input(false)
	main.respawn_prewarm.discard()
	main._clear_world_presentation()
	# This fixture stopped exterior processing while it arranged the seam.
	# Re-enable its bounded drainer so the retained real chunk is released
	# before Main and its shared caches go away.
	main.exterior_stream.set_process(true)
	var deadline := Time.get_ticks_msec() + 30000
	var stable := 0
	while stable < 3:
		await physics_frame
		await process_frame
		var ready: bool = main.exterior_stream.is_idle() \
			and int(main.surface_work_snapshot().pending) == 0 \
			and not bool(main._actor_surface_snap_pending)
		stable = stable + 1 if ready else 0
		if Time.get_ticks_msec() >= deadline:
			expect(false, "owned terrain and surface follow-ups drain before test shutdown")
			# Preserve a busy owner for the strict runner to stop; never free
			# worker-backed content just to make an incomplete test exit.
			return false
	main.process_mode = Node.PROCESS_MODE_DISABLED
	main.queue_free()
	await settle()
	NativeAnimationImporter.clear()
	GlbSceneCache.clear()
	await settle()
	return true

func floor_at(position: Vector3, layer: int) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = layer
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(1.0, 1.0, 1.0)
	shape.shape = box
	body.add_child(shape)
	body.position = position - Vector3(0, 0.5, 0)
	return body

func run() -> void:
	main = load("res://src/app/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.set_process(false)
	root.get_node("Network").set_process(false)
	main.exterior_stream.set_process(false)
	var state: Node = root.get_node("AppState")
	state.current_map = "twinbrook"
	state.local_actor_id = 9001
	var manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/twinbrook/client/world.json")
	main.adapter = manifest.coordinate_adapter()
	var chunks := ContinentChunkStream.new()
	main.world_root.add_child(chunks)
	main.world_loader.world_root = chunks
	main._watch_chunk_surfaces()
	main._watch_chunk_surfaces()
	expect(main_surface_connection_count(chunks) == 1, "active terrain arrivals have exactly one Main callback")
	var terrain := WorldLoader.new()
	chunks.add_child(terrain)
	terrain.load_world("res://../eloria-assets/maps/continent-v2/twinbrook/client/chunks/07_12/world.json")
	await settle()
	var dto := {"actor_id": 9001, "x": 170, "y": 6, "rotation": 0,
		"name": "Traveller", "map": "twinbrook", "health": 40, "max_health": 40}
	state.actors = {9001: dto}
	var actor := ReplicatedActor3D.new()
	main.world_root.add_child(actor)
	actor.configure(dto, main.adapter, {}, {})
	main.actor_nodes[9001] = actor
	main._local_placement_logged = true
	main._place_actor_on_surface(actor, true)
	var previous: float = actor.server_target.y
	expect(previous > 168.0 and previous < 169.0, "the real Twinbrook tile [170, 6] grounds near 168 metres")
	actor.server_target = main.adapter.tile_center(170, 5)
	actor.server_target.y = previous
	actor.global_position = actor.server_target
	dto.y = 5
	main._place_actor_on_surface(actor)
	expect(is_equal_approx(actor.server_target.y, previous), "the missing seam cell at [170, 5] preserves the measured height")
	expect(not main._actor_surface_samples.has(9001), "a failed seam lookup is not cached")
	main._place_actor_on_surface(actor)
	expect(is_equal_approx(actor.server_target.y, previous), "repeated misses never drop the traveller to the map default")
	# The neighbour itself arrives, then its boundary cell arrives later.
	var neighbour := ContinentChunkStream.new()
	main.world_root.add_child(neighbour)
	var neighbour_manifest := WorldManifest.load_file("res://../eloria-assets/maps/continent-v2/warrenmead/client/world.json")
	var here: Array = manifest.data.continentGeography.translation
	var there: Array = neighbour_manifest.data.continentGeography.translation
	neighbour.position = Vector3(float(there[0]) - float(here[0]), float(there[1]) - float(here[1]), float(there[2]) - float(here[2]))
	main.exterior_stream.residents["warrenmead"] = {"root": neighbour, "manifest": neighbour_manifest}
	main.exterior_stream.residents_changed.emit()
	await settle()
	expect(neighbour.cell_ready.is_connected(main._on_chunk_surface_ready), "late neighbour cells are watched too")
	main._watch_chunk_surfaces()
	expect(main_surface_connection_count(neighbour) == 1, "watching the neighbour again keeps exactly one Main callback")
	var login_dto := dto.duplicate()
	login_dto.actor_id = 9002
	state.actors[9002] = login_dto
	var login_actor := ReplicatedActor3D.new()
	main.world_root.add_child(login_actor)
	login_actor.configure(login_dto, main.adapter, {}, {})
	main.actor_nodes[9002] = login_actor
	main._place_actor_on_surface(login_actor)
	expect(absf(login_actor.server_target.y - 121.62) < 0.01, "login at the boundary waits on the documented fallback")
	# Chunk IDs and extents follow the current authored partition. Locate the
	# actual neighbour cell beneath this exact world-space grounding ray.
	var local_ray := neighbour.to_local(actor.server_target)
	var covering: Array[Dictionary] = []
	var streaming: Dictionary = neighbour_manifest.data.get("streamingChunks", {}) as Dictionary
	for entry: Dictionary in streaming.get("chunks", []):
		var bounds: Dictionary = entry.get("bounds", {}) as Dictionary
		var lower: Array = bounds.get("min", []) as Array
		var upper: Array = bounds.get("max", []) as Array
		if lower.size() < 3 or upper.size() < 3:
			continue
		if local_ray.x >= float(lower[0]) and local_ray.x <= float(upper[0]) \
				and local_ray.z >= float(lower[2]) and local_ray.z <= float(upper[2]):
			covering.append(entry)
	expect(covering.size() == 1, "the current neighbour manifest names exactly one chunk beneath the seam ray")
	if covering.size() != 1:
		if await cleanup_owned_main(state):
			print("actor surface regrounding: %d failures" % failures)
			quit(1)
		return
	var preview_entry: Dictionary = covering[0].duplicate(true)
	var preview_id := str(preview_entry.get("id", ""))
	var relative_manifest := str(preview_entry.get("manifest", ""))
	expect(not preview_id.is_empty() and not relative_manifest.is_empty(),
		"the covering chunk has an authored ID and manifest reference")
	if preview_id.is_empty() or relative_manifest.is_empty():
		if await cleanup_owned_main(state):
			print("actor surface regrounding: %d failures" % failures)
			quit(1)
		return
	var preview_path := neighbour_manifest.source_path.get_base_dir().path_join(relative_manifest)
	var preview := WorldLoader.new()
	neighbour.add_child(preview)
	preview.load_world(preview_path)
	# Match a streamed resident: the imported root belongs directly to its
	# stream and is indexed with its actual authored entry before cell_ready.
	var preview_resident := preview.release_world()
	var preview_root := preview_resident.root as Node3D
	preview.queue_free()
	neighbour.add_child(preview_root)
	preview_resident.entry = preview_entry
	neighbour.cells[preview_id] = preview_resident
	ExteriorRegionStream._set_collision(preview_root, false, true, "", true)
	neighbour.cell_ready.emit(preview_id, preview_root)
	await settle()
	expect(actor.server_target.y > 168.8 and actor.server_target.y < 169.0, "a stationary traveller grounds on the real Warrenmead boundary cell")
	expect(is_equal_approx(login_actor.server_target.y, actor.server_target.y), "login on the same tile also recovers when that terrain arrives")
	# Its own navigation surface can arrive after a preview has grounded it.
	var active := floor_at(Vector3(actor.server_target.x, 169.0, actor.server_target.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	chunks.add_child(active)
	var active_local := chunks.to_local(actor.server_target)
	chunks.cells["active-boundary"] = {"root": active, "manifest": WorldManifest.new(),
		"entry": {"id": "active-boundary", "estimatedResidentBytes": 0,
			"bounds": {"min": [active_local.x - 0.5, 168, active_local.z - 0.5],
				"max": [active_local.x + 0.5, 170, active_local.z + 0.5]}}}
	chunks.cell_ready.emit("active-boundary", active)
	await settle()
	expect(absf(actor.server_target.y - 169.02) < 0.01, "active navigation takes precedence when it becomes available")
	expect(main._actor_surface_samples.has(9001), "successful active ground samples remain cached")
	# Another fresh actor still has the documented fallback when no ground exists.
	var fresh := ReplicatedActor3D.new()
	main.world_root.add_child(fresh)
	fresh.actor_id = 9003
	fresh.server_target = Vector3(1000, main.adapter.walking_height, 1000)
	main._place_actor_on_surface(fresh, true, 75.0)
	expect(absf(fresh.server_target.y - 75.02) < 0.01, "an actor with no measured height uses its own supplied fallback")
	if not await cleanup_owned_main(state):
		return
	print("actor surface regrounding: %d failures" % failures)
	quit(1 if failures > 0 else 0)
