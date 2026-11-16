extends SceneTree
## Harvest node seating (map polish, owner-approved 2026-11-16): a node's model
## is seated on the walk surface under its footprint rather than standing level
## at its tile centre's height. A low model (a mushroom cap, a lotus pad) is
## tilted to the ground's plane and no part of its base hangs over a slope; a
## taller one (a bramble bush) stays upright, lowered onto the lowest ground
## under it. The node, its served tile and its pick stay where they were; a
## wall seam is not seated; a level node keeps its rest basis.

const REGISTRY := "res://data/world/objects.json"

var failures := 0

func _init() -> void:
	call_deferred("_run")

func _run() -> void:
	_check_seat_maths()
	var catalog: Dictionary = _json(REGISTRY)
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "serverOrigin": [0.0, 0.0]})
	# A walk surface rising 0.3 m per metre eastwards (+x), about the slope
	# of the hovering Mushroom and Lotus nodes the audit measured.
	var grade := 0.3
	var slope := _ground(grade, Vector3(10.5, 0.0, 10.5))
	await physics_frame
	await physics_frame
	var space := root.get_world_3d().direct_space_state
	for label: String in ["Mushroom", "Lotus"]:
		await _check_low_model(adapter, catalog, space, label, grade)
	await _check_upright_model(adapter, catalog, space, grade)
	await _check_level_and_wall(adapter, catalog, slope)
	print("harvest seating tests: ", "PASS" if failures == 0 else "FAIL (%d)" % failures)
	quit(failures)

# --- the seat, worked out from samples -----------------------------------------

func _check_seat_maths() -> void:
	# Level ground 5 cm under the node (set_surface_height lifts the node 5 cm).
	var level := _samples(func(_x: float, _z: float) -> float: return -0.05)
	var flat := MapObject3D.seat_for(level, 0.2)
	_expect(flat.slope == Vector2.ZERO and is_equal_approx(float(flat.offset), -0.05 - MapObject3D.SEAT_EMBED),
		"on level ground a model is let SEAT_EMBED into the ground, untilted: %s" % [flat])
	# A 0.3 grade: a low model is tilted to it and nothing floats.
	var sloped := _samples(func(x: float, z: float) -> float: return -0.05 + 0.3 * x - 0.1 * z)
	var low := MapObject3D.seat_for(sloped, 0.2)
	_expect((low.slope as Vector2).distance_to(Vector2(0.3, -0.1)) < 0.001 and float(low.floating) < 0.001
		and float(low.sunk) <= MapObject3D.SEAT_EMBED + 0.001,
		"a low model is tilted to the fitted plane and neither floats nor sinks: %s" % [low])
	# A taller model stays upright: the lowest sample touches, the uphill side is
	# rooted in the slope.
	var tall := MapObject3D.seat_for(sloped, 0.93)
	_expect(tall.slope == Vector2.ZERO and float(tall.floating) < 0.001 and float(tall.sunk) > 0.2
		and not bool(tall.low), "a taller model stays upright, lowered onto its lowest sample: %s" % [tall])
	# A steep bank: the tilt is clamped.
	var steep := MapObject3D.seat_for(_samples(func(x: float, _z: float) -> float: return 0.9 * x), 0.2)
	_expect(is_equal_approx(float(steep.tilt_degrees), MapObject3D.SEAT_MAX_TILT_DEGREES),
		"a low model's tilt is clamped at %.0f degrees: %.1f" % [MapObject3D.SEAT_MAX_TILT_DEGREES, steep.tilt_degrees])
	# The drop is clamped, so a seat can never bury a node.
	var cliff := MapObject3D.seat_for(_samples(func(x: float, _z: float) -> float: return 0.35 * x - 0.05,
		2.0), 1.6)
	_expect(is_equal_approx(float(cliff.offset), -MapObject3D.SEAT_UPRIGHT_MAX_DROP),
		"an upright model's drop is clamped at %.2f m: %.2f" % [MapObject3D.SEAT_UPRIGHT_MAX_DROP, cliff.offset])
	# A sample at the foot of a ledge is not ground the model stands on.
	var ledge := level.duplicate()
	ledge[3] = Vector3(ledge[3].x, -1.6, ledge[3].z)
	var edge := MapObject3D.seat_for(ledge, 0.2)
	_expect(int(edge.samples) == level.size() - 1 and is_equal_approx(float(edge.offset), -0.06),
		"a sample far below the rest (a ledge's foot) is ignored: %s" % [edge])
	# A hollow the plane cannot follow: a low model sinks at most its share of
	# its height into the rim and floats over the floor instead.
	var hollow := MapObject3D.seat_for(_samples(func(x: float, z: float) -> float: return -0.05 if x == 0.0 and z == 0.0 else 0.03), 0.2)
	_expect(is_equal_approx(float(hollow.sunk), maxf(MapObject3D.SEAT_LOW_MIN_SINK, 0.2 * MapObject3D.SEAT_LOW_SINK_SHARE))
		and float(hollow.floating) < 0.05, "a low cap in a hollow is not buried by its rim: %s" % [hollow])
	# Ground all above the node lifts the model, never more than SEAT_MAX_RAISE.
	var raised := MapObject3D.seat_for(_samples(func(_x: float, _z: float) -> float: return 0.3), 0.2)
	_expect(is_equal_approx(float(raised.offset), MapObject3D.SEAT_MAX_RAISE),
		"a model is lifted at most %.2f m: %s" % [MapObject3D.SEAT_MAX_RAISE, raised])
	_expect(MapObject3D.seat_for(PackedVector3Array([Vector3.ZERO, Vector3.ONE]), 0.2).is_empty(),
		"fewer than three samples seat nothing")

# --- a low model on a slope --------------------------------------------------------

func _check_low_model(adapter: CoordinateAdapter, catalog: Dictionary,
		space: PhysicsDirectSpaceState3D, label: String, grade: float) -> void:
	var node := _object(adapter, catalog, label, 5101)
	var model := node.get_node_or_null("Model") as Node3D
	_expect(model != null, "%s stands its model" % label)
	if model == null:
		return
	var centre: Variant = GroundDrape.surface_height(space, node.global_position.x, node.global_position.z)
	_expect(centre != null, "the slope is under %s" % label)
	if centre == null:
		return
	# As before this change: the node at its tile centre's height, the model
	# level on it.
	node.global_position.y = float(centre) + 0.05
	var before := _base_gaps(node, model, space)
	var tile := node.server_tile
	var position := node.global_position
	var pick := node.get_node("PickShape") as CollisionShape3D
	var pick_before := pick.global_position
	node.set_surface_height(float(centre))
	var after := _base_gaps(node, model, space)
	print("%s bounds %s; level base floats %.3f / sinks %.3f; seated floats %.3f / sinks %.3f; seat %s"
		% [label, MapObject3D.model_space_bounds(model), before.x, before.y, after.x, after.y, node.seat])
	_expect(before.x > 0.08, "%s's level base hung %.2f m over the slope before" % [label, before.x])
	_expect(after.x <= 0.03 and after.y <= 0.06,
		"%s's seated base neither floats nor sinks more than a few cm (%.3f / %.3f)" % [label, after.x, after.y])
	var up := model.global_transform.basis.y.normalized()
	var normal := Vector3(-grade, 1.0, 0.0).normalized()
	_expect(up.angle_to(normal) < deg_to_rad(2.0), "%s is tilted to the ground (%.1f degrees off)"
		% [label, rad_to_deg(up.angle_to(normal))])
	_expect(node.server_tile == tile and node.global_position.is_equal_approx(position),
		"%s's node and served tile do not move" % label)
	_expect(pick.global_position.distance_to(pick_before) <= MapObject3D.SEAT_LOW_MAX_DROP + 0.001
		and Vector2(pick.global_position.x, pick.global_position.z).is_equal_approx(
			Vector2(position.x, position.z)), "and its pick stays on the tile, with the model")
	var seated := model.transform
	node.set_surface_height(float(centre))
	_expect(model.transform.is_equal_approx(seated), "placing it again at the same height keeps the seat")
	node.free()

# --- an upright model on a slope -------------------------------------------------

func _check_upright_model(adapter: CoordinateAdapter, catalog: Dictionary,
		space: PhysicsDirectSpaceState3D, grade: float) -> void:
	var node := _object(adapter, catalog, "Bramble", 5102)
	var model := node.get_node_or_null("Model") as Node3D
	if not _expect(model != null and node.model_id == "bramble_bush_a", "a Bramble node stands its bush"):
		return
	var rest := model.transform.basis
	var centre: float = GroundDrape.surface_height(space, node.global_position.x, node.global_position.z)
	node.set_surface_height(centre)
	var after := _base_gaps(node, model, space)
	print("Bramble seat %s; base floats %.3f / sinks %.3f" % [node.seat, after.x, after.y])
	_expect(model.transform.basis.is_equal_approx(rest), "a bush stays upright on a %.1f grade" % grade)
	_expect(after.x <= 0.03, "and is lowered until no part of its base floats (%.3f)" % after.x)
	_expect(float(node.seat.offset) < -0.1 and float(node.seat.offset) >= -MapObject3D.SEAT_UPRIGHT_MAX_DROP,
		"by a clamped drop: %.2f m" % float(node.seat.offset))
	node.free()

# --- level ground, and a wall seam -----------------------------------------------

func _check_level_and_wall(adapter: CoordinateAdapter, catalog: Dictionary, slope: Node3D) -> void:
	slope.free()
	var level := _ground(0.0, Vector3(10.5, 2.0, 10.5))
	await physics_frame
	await physics_frame
	var node := _object(adapter, catalog, "Mushroom", 5103)
	var model := node.get_node("Model") as Node3D
	var rest := model.transform
	node.set_surface_height(2.0)
	_expect(model.transform.basis.is_equal_approx(rest.basis)
		and is_equal_approx(model.position.y, -0.05 - MapObject3D.SEAT_EMBED),
		"on level ground the model keeps its rest basis and is let into the ground: %s" % [node.seat])
	node.free()
	# A vein set into a rock face is placed by its own inset; it is not seated.
	var test_catalog: Dictionary = catalog.duplicate(true)
	var models: Dictionary = test_catalog.harvestables.models
	var seam: Dictionary = (models.get(str(test_catalog.harvestables.resources.get("Coal", "")), {}) as Dictionary).duplicate()
	seam["placement"] = "wall"
	models["test_coal_wall"] = seam
	test_catalog.harvestables["wallVariants"] = {"Coal": ["test_coal_wall"]}
	var wall := _object(adapter, test_catalog, "Coal", 5104,
		{"placement": "wall", "variant": 0.0, "yaw": 90.0, "inset": 0.8})
	var wall_model := wall.get_node("Model") as Node3D
	var wall_rest := wall_model.transform
	wall.set_surface_height(2.0)
	_expect(wall.is_wall_placed() and wall_model.transform.is_equal_approx(wall_rest) and wall.seat.is_empty(),
		"a wall seam keeps the place its inset gives it")
	wall.free()
	level.free()

# --- helpers ----------------------------------------------------------------------

## The most the model's base floats over the walk surface (x) and sinks into it
## (y), over a dense grid across its footprint.
func _base_gaps(node: MapObject3D, model: Node3D, space: PhysicsDirectSpaceState3D) -> Vector2:
	var bounds := MapObject3D.model_space_bounds(model)
	var floating := -INF
	var sunk := -INF
	for i: int in range(7):
		for j: int in range(7):
			var u := (float(i) / 6.0 - 0.5) * MapObject3D.SEAT_RIM_SHARE
			var v := (float(j) / 6.0 - 0.5) * MapObject3D.SEAT_RIM_SHARE
			# Inside the ellipse the samples cover: a round cap's corners are air.
			if u * u + v * v > 0.25 * MapObject3D.SEAT_RIM_SHARE * MapObject3D.SEAT_RIM_SHARE:
				continue
			var base := model.global_transform * Vector3(bounds.get_center().x + u * bounds.size.x,
				bounds.position.y, bounds.get_center().z + v * bounds.size.z)
			var ground: Variant = GroundDrape.surface_height(space, base.x, base.z)
			if ground == null:
				continue
			floating = maxf(floating, base.y - float(ground))
			sunk = maxf(sunk, float(ground) - base.y)
	return Vector2(floating, sunk)

## A walk surface on the navigation layer through `through`, rising `grade`
## metres per metre eastwards.
func _ground(grade: float, through: Vector3) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(200.0, 1.0, 200.0)
	shape.shape = box
	body.add_child(shape)
	root.add_child(body)
	var angle := atan(grade)
	body.global_transform = Transform3D(Basis(Vector3.BACK, angle), through) \
		* Transform3D(Basis.IDENTITY, Vector3(0.0, -0.5, 0.0))
	return body

## Ground samples at the node's footprint points: the centre and a 0.6 m ring.
func _samples(height: Callable, radius := 0.6) -> PackedVector3Array:
	var points := PackedVector3Array([Vector3(0.0, height.call(0.0, 0.0), 0.0)])
	for index: int in range(8):
		var angle := TAU * float(index) / 8.0
		var x := cos(angle) * radius
		var z := sin(angle) * radius
		points.append(Vector3(x, height.call(x, z), z))
	return points

func _object(adapter: CoordinateAdapter, catalog: Dictionary, label: String, object_id: int,
		presentation: Dictionary = {}) -> MapObject3D:
	var node := MapObject3D.new()
	node.configure({"object_id": object_id, "kind": EloriaProtocol.MAP_OBJECT_HARVEST,
		"x": 10, "y": 10, "label": label, "detail": ""}, adapter, catalog, false, presentation)
	root.add_child(node)
	return node

static func _json(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

func _expect(value: bool, label: String) -> bool:
	if not value:
		failures += 1
		push_error("FAIL: " + label)
	return value
