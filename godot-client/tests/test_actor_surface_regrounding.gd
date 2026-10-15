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
	expect(chunks.cell_ready.get_connections().size() == 1, "active terrain arrivals are watched once")
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
	expect(neighbour.cell_ready.get_connections().size() == 1, "watching the neighbour again does not duplicate callbacks")
	var login_dto := dto.duplicate()
	login_dto.actor_id = 9002
	state.actors[9002] = login_dto
	var login_actor := ReplicatedActor3D.new()
	main.world_root.add_child(login_actor)
	login_actor.configure(login_dto, main.adapter, {}, {})
	main.actor_nodes[9002] = login_actor
	main._place_actor_on_surface(login_actor)
	expect(absf(login_actor.server_target.y - 121.62) < 0.01, "login at the boundary waits on the documented fallback")
	var preview := WorldLoader.new()
	neighbour.add_child(preview)
	preview.load_world("res://../eloria-assets/maps/continent-v2/warrenmead/client/chunks/12_10/world.json")
	ExteriorRegionStream._set_collision(preview.world_root, false, true, "", true)
	neighbour.cell_ready.emit("12_10", preview.world_root)
	await settle()
	expect(actor.server_target.y > 168.8 and actor.server_target.y < 169.0, "a stationary traveller grounds on the real Warrenmead boundary cell")
	expect(is_equal_approx(login_actor.server_target.y, actor.server_target.y), "login on the same tile also recovers when that terrain arrives")
	# Its own navigation surface can arrive after a preview has grounded it.
	var active := floor_at(Vector3(actor.server_target.x, 169.0, actor.server_target.z), WorldLoader.NAVIGATION_SURFACE_LAYER)
	chunks.add_child(active)
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
	print("actor surface regrounding: %d failures" % failures)
	main.queue_free()
	await process_frame
	quit(1 if failures > 0 else 0)
