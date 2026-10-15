extends SceneTree
## Loads both Sunmane cave interiors through the real WorldLoader and verifies
## that a player can stand, walk and be contained inside them: the floor grounds
## an actor everywhere the manifest says it should, every chamber has standing
## headroom, the roof and wall skirt stop a player-sized body from leaving the
## system, and the exit portal is reachable ground with clearance above it.

const INTERIORS := [
	"res://../eloria-assets/maps/nymara-regions/interiors/sunmane_wind_caves/world.json",
	"res://../eloria-assets/maps/nymara-regions/interiors/sunmane_crystal_hollow/world.json"]
const NAVIGATION_LAYER := 8
const WORLD_LAYER := 1
const STANDING_HEIGHT := 1.9

var _failures := 0
var _space: PhysicsDirectSpaceState3D

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	for manifest_path: String in INTERIORS:
		await _check(manifest_path)
	print("sunmane caves: ", "PASS" if _failures == 0 else "FAIL")
	quit(0 if _failures == 0 else 1)

func _check(manifest_path: String) -> void:
	var world_root := Node3D.new()
	root.add_child(world_root)
	var loader := WorldLoader.new()
	loader.name = "WorldLoader"
	world_root.add_child(loader)
	loader.load_world(ProjectSettings.globalize_path(manifest_path))
	var deadline := Time.get_ticks_msec() + 60000
	while loader.world_root == null and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _expect(loader.world_root != null, "interior imports: " + manifest_path):
		world_root.queue_free()
		return
	var name := str(loader.manifest.data["asset"]["name"])
	_expect(loader.manifest.errors.is_empty(),
		"%s manifest validates: %s" % [name, str(loader.manifest.errors)])
	for unused: int in range(6):
		await process_frame
	_space = world_root.get_world_3d().direct_space_state

	var navigation := 0
	var structural := 0
	for node: Node in loader.world_root.find_children("*", "StaticBody3D", true, false):
		var body := node as StaticBody3D
		if body.collision_layer == NAVIGATION_LAYER:
			navigation += 1
		elif body.collision_layer == WORLD_LAYER:
			structural += 1
	_expect(navigation >= 4, "%s: cavern floor bodies created: %d" % [name, navigation])
	_expect(structural == (loader.manifest.data["collision"]["nodeNames"] as Array).size(),
		"%s: every declared collision node produced a body (%d)" % [name, structural])

	_check_chambers(name, loader)
	_check_containment(name, loader)
	_check_portal(name, loader)
	world_root.queue_free()
	await process_frame

func _check_chambers(name: String, loader: WorldLoader) -> void:
	## Every chamber must be somewhere a player can stand and move about, so
	## each is sampled at its centre and on a ring inside it. Props legitimately
	## occupy part of a chamber - a brazier, a cart, a stalagmite - so the bar is
	## that most of each chamber is clear, not all of it.
	var clear_chambers := 0
	var chambers: Array = loader.manifest.data["chambers"]
	for chamber: Dictionary in chambers:
		var position: Array = chamber["position"]
		var radius := float(chamber["radius"])
		var samples: Array[Vector2] = [Vector2(float(position[0]), float(position[2]))]
		for step in range(12):
			var angle := TAU * float(step) / 12.0
			samples.append(Vector2(float(position[0]) + cos(angle) * radius * 0.55,
				float(position[2]) + sin(angle) * radius * 0.55))
		var grounded := 0
		var clear := 0
		for sample: Vector2 in samples:
			var floor_point: Variant = _ground(sample.x, sample.y)
			if floor_point == null:
				continue
			grounded += 1
			var head := (floor_point as Vector3) + Vector3(0.0, 0.15, 0.0)
			var query := PhysicsRayQueryParameters3D.create(head,
				head + Vector3(0.0, STANDING_HEIGHT, 0.0), WORLD_LAYER)
			if _space.intersect_ray(query).is_empty():
				clear += 1
		var expected := samples.size()
		if not _expect(grounded == expected,
				"%s: %s is floored throughout (%d/%d)"
				% [name, str(chamber["id"]), grounded, expected]):
			continue
		if float(clear) >= float(expected) * 0.75:
			clear_chambers += 1
		else:
			push_warning("%s: %s is obstructed: only %d of %d samples have "
				% [name, str(chamber["id"]), clear, expected]
				+ "standing headroom")
	_expect(clear_chambers == chambers.size(),
		"%s: every chamber is mostly clear standing room (%d/%d)"
		% [name, clear_chambers, chambers.size()])

	# The spawn points and light markers must at least be on the floor.
	var placed := 0
	var markers: Array = []
	for spawn: Dictionary in loader.manifest.data["spawnPoints"]:
		markers.append([spawn["position"], str(spawn["id"])])
	for marker: Dictionary in loader.manifest.data["lighting"]["markers"]:
		markers.append([marker["position"], str(marker["id"])])
	for entry: Array in markers:
		var position: Array = entry[0]
		if _ground(float(position[0]), float(position[2])) != null:
			placed += 1
		else:
			push_warning("%s: %s is not over the cavern floor" % [name, entry[1]])
	_expect(placed == markers.size(),
		"%s: every spawn and light marker sits over the floor (%d/%d)"
		% [name, placed, markers.size()])

func _check_containment(name: String, loader: WorldLoader) -> void:
	## A player must not be able to walk out of the system. From each chamber a
	## player-sized body is walked outward step by step in every direction, the
	## way the character controller moves: it drops to the floor at each step and
	## stops when the rock leaves it no room. Reaching the declared bounds means
	## the cavern has a hole in it.
	var body := CapsuleShape3D.new()
	body.radius = 0.4
	body.height = 1.7
	var bounds: Dictionary = loader.manifest.data["asset"]["bounds"]
	var edge: float = float((bounds["max"] as Array)[0]) - 1.0
	var escaped := 0
	var walks := 0
	for spawn: Dictionary in loader.manifest.data["spawnPoints"]:
		var position: Array = spawn["position"]
		for step in range(24):
			var angle := TAU * float(step) / 24.0
			var direction := Vector2(cos(angle), sin(angle))
			var here := Vector2(float(position[0]), float(position[2]))
			walks += 1
			var left := false
			for stride in range(240):
				var next := here + direction * 0.35
				var floor_point: Variant = _ground(next.x, next.y)
				if floor_point == null:
					break                      # no floor to step onto
				var stand := (floor_point as Vector3) + Vector3(0.0, 0.95, 0.0)
				var query := PhysicsShapeQueryParameters3D.new()
				query.shape = body
				query.collision_mask = WORLD_LAYER
				query.transform = Transform3D(Basis(), stand)
				if not _space.intersect_shape(query, 1).is_empty():
					break                      # the rock is in the way
				here = next
				if absf(here.x) > edge or absf(here.y) > edge:
					left = true
					break
			if left:
				escaped += 1
				push_warning("%s: a body walks out of the rock from %s heading %.0f deg"
					% [name, str(spawn["id"]), rad_to_deg(angle)])
	_expect(escaped == 0,
		"%s: the rock contains a walking player in every direction (%d of %d walks left)"
		% [name, escaped, walks])

func _check_portal(name: String, loader: WorldLoader) -> void:
	for portal: Dictionary in loader.manifest.data["portals"]:
		var position: Array = portal["position"]
		var point: Variant = _ground(float(position[0]), float(position[2]))
		if not _expect(point != null,
				"%s: portal ground: %s" % [name, str(portal["id"])]):
			continue
		var head := (point as Vector3) + Vector3(0.0, 0.15, 0.0)
		var query := PhysicsRayQueryParameters3D.create(head,
			head + Vector3(0.0, STANDING_HEIGHT, 0.0), WORLD_LAYER)
		_expect(_space.intersect_ray(query).is_empty(),
			"%s: portal has standing headroom: %s" % [name, str(portal["id"])])
		_expect(str(portal["destinationMap"]) != "",
			"%s: portal declares its destination map" % name)

func _ground(world_x: float, world_z: float) -> Variant:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(world_x, 200.0, world_z), Vector3(world_x, -100.0, world_z),
		NAVIGATION_LAYER)
	var hit := _space.intersect_ray(query)
	var position: Variant = hit.get("position")
	return position if position is Vector3 else null

func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
