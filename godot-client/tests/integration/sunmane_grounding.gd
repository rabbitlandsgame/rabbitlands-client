extends SceneTree
## Loads the Sunmane Steppe package through the real WorldLoader and verifies
## that the navigation-surface layer grounds an actor everywhere a player can
## legitimately stand, including the arrival datum and every portal approach.

const MANIFEST := "res://../eloria-assets/maps/nymara-regions/sunmane_steppe/world.json"
const NAVIGATION_LAYER := 8
const METRES_PER_TILE := 1.0
const SERVER_ORIGIN := Vector2(58.0, 58.0)

var _failures := 0
var _loader: WorldLoader
var _space: PhysicsDirectSpaceState3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	var world_root := Node3D.new()
	root.add_child(world_root)
	_loader = WorldLoader.new()
	_loader.name = "WorldLoader"
	world_root.add_child(_loader)
	_loader.load_world(ProjectSettings.globalize_path(MANIFEST))
	var deadline := Time.get_ticks_msec() + 60000
	while _loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	_expect(_loader.world_root != null, "world.glb imports through WorldLoader")
	if _loader.world_root == null:
		await _finish()
		return
	_expect(_loader.manifest.errors.is_empty(),
		"manifest validates: " + str(_loader.manifest.errors))
	for warning: String in _loader.manifest.warnings:
		print("WARN: ", warning)

	# Let the deferred physics bodies register before raycasting.
	for unused: int in range(6):
		await process_frame
	_space = world_root.get_world_3d().direct_space_state

	var surfaces := 0
	for node: Node in _loader.world_root.find_children("*", "StaticBody3D", true, false):
		var body := node as StaticBody3D
		if body.collision_layer == NAVIGATION_LAYER:
			surfaces += 1
	_expect(surfaces >= 64, "navigation-surface bodies created: %d" % surfaces)

	_probe_datum()
	_probe_portals()
	_probe_grid()
	await _finish()

func _server_to_world(tile_x: float, tile_y: float) -> Vector2:
	return Vector2((tile_x - SERVER_ORIGIN.x) * METRES_PER_TILE,
		-(tile_y - SERVER_ORIGIN.y) * METRES_PER_TILE)

func _ground(world_x: float, world_z: float) -> Variant:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(world_x, 400.0, world_z), Vector3(world_x, -100.0, world_z),
		NAVIGATION_LAYER)
	var hit := _space.intersect_ray(query)
	var position: Variant = hit.get("position")
	return position if position is Vector3 else null

func _probe_datum() -> void:
	var hit: Variant = _ground(0.0, 0.0)
	_expect(hit != null, "arrival datum (58,58) is grounded")
	if hit is Vector3:
		var y: float = (hit as Vector3).y
		print("datum ground height: %.3f" % y)
		_expect(y > 1.0 and y < 30.0, "datum ground height is inside the landform")

func _probe_portals() -> void:
	for entry: Array in [[6, 58, "west caravanserai"], [110, 58, "east caravanserai"],
			[58, 100, "north barrowfield"]]:
		var flat := _server_to_world(float(entry[0]), float(entry[1]))
		var hit: Variant = _ground(flat.x, flat.y)
		_expect(hit != null, "portal approach grounded: " + str(entry[2]))
		if hit is Vector3:
			print("%s -> godot (%.1f, %.3f, %.1f)" % [entry[2], flat.x,
				(hit as Vector3).y, flat.y])

func _probe_grid() -> void:
	var misses := 0
	var samples := 0
	var lowest := 1e9
	var highest := -1e9
	for tile_x: int in range(0, 209, 4):
		for tile_y: int in range(0, 209, 4):
			var world_x := -104.0 + float(tile_x)
			var world_z := -104.0 + float(tile_y)
			samples += 1
			var hit: Variant = _ground(world_x, world_z)
			if hit == null:
				misses += 1
				if misses <= 8:
					push_warning("grounding miss at (%.1f, %.1f)" % [world_x, world_z])
			else:
				var y: float = (hit as Vector3).y
				lowest = minf(lowest, y)
				highest = maxf(highest, y)
	print("grid samples=%d misses=%d ground range %.2f .. %.2f" % [
		samples, misses, lowest, highest])
	_expect(misses == 0, "every sampled column grounds on the navigation surface")

func _expect(condition: bool, message: String) -> void:
	if condition:
		print("PASS: ", message)
		return
	_failures += 1
	push_error("FAIL: " + message)

func _finish() -> void:
	print("sunmane grounding: ", "PASS" if _failures == 0 else "FAIL")
	# Sunmane streams the cells beyond the arrival's budget on a worker;
	# quitting under a live import crashes (or hangs) the process at exit
	# (ContinentChunkStream.drain_workers).
	await ContinentChunkStream.drain_workers(self)
	quit(_failures)
