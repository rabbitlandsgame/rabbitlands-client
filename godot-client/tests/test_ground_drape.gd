extends SceneTree
## Ground markers follow the ground they mark.
##
## The client draws two markers flat on the terrain: the box under a selected
## actor and the ring under a harvest node. Both used to be one horizontal plane
## a fixed five centimetres over the single point the client had sampled, and
## the ground inside a tile is not flat: on Whitehorn Range it rises more than
## that clearance within half a metre under nine tiles in ten. So the uphill
## part of a marker sat inside the slope, the depth buffer dropped it, and which
## part survived changed with every step - the flicker under a running player.
##
## The ground here is a ridge steep enough to bury a flat marker, so the tests
## can watch a draped one clear it.

const CLEARANCE := 0.05
## Height of the ridge the markers are laid over, and how quickly it climbs.
const RIDGE_HEIGHT := 0.4
const RIDGE_PERIOD := 4.0

var _failures := 0
var _surface: StaticBody3D

func _init() -> void:
	call_deferred("_run")

## The test ridge's height at a point, which is also what the collision below
## is built from, so an expectation and the thing it measures cannot drift.
static func ridge_height(x: float, z: float) -> float:
	return RIDGE_HEIGHT * sin(TAU * x / RIDGE_PERIOD) * cos(TAU * z / RIDGE_PERIOD)

func _run() -> void:
	_surface = StaticBody3D.new()
	_surface.collision_layer = WorldLoader.NAVIGATION_SURFACE_LAYER
	_surface.collision_mask = 0
	var shape := CollisionShape3D.new()
	shape.shape = _ridge_shape()
	_surface.add_child(shape)
	root.add_child(_surface)
	for unused: int in range(4):
		await physics_frame
		await process_frame

	_a_flat_marker_sinks()
	_a_draped_marker_clears()
	_a_draped_marker_keeps_its_shape()
	_no_ground_leaves_the_marker_alone()
	await _an_actor_re_drapes_as_it_walks()
	_a_harvest_node_ring_clears()

	print("ground drape: ", "PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)

func _ridge_shape() -> ConcavePolygonShape3D:
	var faces := PackedVector3Array()
	var step := 0.25
	var extent := 4.0
	var count: int = int(extent * 2.0 / step)
	for row: int in count:
		for column: int in count:
			var x0: float = -extent + float(column) * step
			var z0: float = -extent + float(row) * step
			var x1: float = x0 + step
			var z1: float = z0 + step
			var a := Vector3(x0, ridge_height(x0, z0), z0)
			var b := Vector3(x1, ridge_height(x1, z0), z0)
			var c := Vector3(x1, ridge_height(x1, z1), z1)
			var d := Vector3(x0, ridge_height(x0, z1), z1)
			faces.append_array([a, b, c, a, c, d])
	var shape := ConcavePolygonShape3D.new()
	shape.set_faces(faces)
	return shape

## A marker built at one height, placed at the steepest part of the ridge.
func _marker(at: Vector2) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.mesh = ReplicatedActor3D.footprint_outline(1.0, 1.0)
	root.add_child(node)
	node.global_position = Vector3(at.x,
		ridge_height(at.x, at.y) + CLEARANCE, at.y)
	return node

## How far the lowest part of a marker sits under the ground beneath it.
func _deepest_burial(node: MeshInstance3D) -> float:
	var deepest := 0.0
	var arrays: Array = node.mesh.surface_get_arrays(0)
	for vertex: Vector3 in arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array:
		var point: Vector3 = node.global_transform * vertex
		deepest = maxf(deepest, ridge_height(point.x, point.z) - point.y)
	return deepest

func _a_flat_marker_sinks() -> void:
	# The steepest part of the ridge, which is what a marker has to survive.
	var node: MeshInstance3D = _marker(Vector2(0.0, 0.0))
	_expect(_deepest_burial(node) > CLEARANCE,
		"the flat marker this exists to fix does sink into the ridge (%.3f m)"
			% _deepest_burial(node))
	node.queue_free()

func _a_draped_marker_clears() -> void:
	for at: Vector2 in [Vector2(0.0, 0.0), Vector2(0.5, 0.5), Vector2(-1.0, 0.2)]:
		var node: MeshInstance3D = _marker(at)
		var draped: ArrayMesh = GroundDrape.drape(node, node.mesh)
		if not _expect(draped != null, "the ridge is ground a marker can be draped on"):
			node.queue_free()
			return
		node.mesh = draped
		_expect(_deepest_burial(node) <= 0.0,
			"at %v no part of the draped marker is under the ground" % at)
		# And it is lying on the ground rather than hovering over it.
		var highest := -100.0
		for vertex: Vector3 in (draped.surface_get_arrays(0)[
				Mesh.ARRAY_VERTEX] as PackedVector3Array):
			var point: Vector3 = node.global_transform * vertex
			highest = maxf(highest, point.y - ridge_height(point.x, point.z))
		_expect(highest < CLEARANCE * 2.0,
			"at %v it still reads as lying on the ground (%.3f m up)" % [at, highest])
		node.queue_free()

func _a_draped_marker_keeps_its_shape() -> void:
	var node: MeshInstance3D = _marker(Vector2(0.0, 0.0))
	var flat: ArrayMesh = node.mesh as ArrayMesh
	var draped: ArrayMesh = GroundDrape.drape(node, flat)
	if not _expect(draped != null, "a marker over ground drapes"):
		node.queue_free()
		return
	var before: PackedVector3Array = flat.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var after: PackedVector3Array = draped.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	if _expect(before.size() == after.size(),
			"draping moves the marker's vertices rather than rebuilding them"):
		var moved_sideways := 0.0
		for index: int in before.size():
			moved_sideways = maxf(moved_sideways,
				Vector2(before[index].x - after[index].x,
					before[index].z - after[index].z).length())
		_expect(moved_sideways < 0.0001,
			"the marker still covers the same ground it was built to cover")
	_expect(draped.get_aabb().size.y > 0.05,
		"and it is no longer one flat plane")
	node.queue_free()

func _no_ground_leaves_the_marker_alone() -> void:
	var node := MeshInstance3D.new()
	node.mesh = ReplicatedActor3D.footprint_outline(1.0, 1.0)
	root.add_child(node)
	node.global_position = Vector3(500.0, 0.0, 500.0)
	_expect(GroundDrape.drape(node, node.mesh) == null,
		"off the walk surface there is nothing to drape onto, and it says so")
	node.queue_free()

## The marker is laid down again as the actor walks, because the ground under
## it is different ground by the time the actor has crossed a tile.
func _an_actor_re_drapes_as_it_walks() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var actor := ReplicatedActor3D.new()
	root.add_child(actor)
	actor.configure({"actor_id": 7, "x": 0, "y": 0, "rotation": 0,
		"actor_type": 1, "kind": 1, "name": "Walker", "health": 10,
		"max_health": 10}, adapter, {}, {})
	actor.set_selected(true)
	var ring: MeshInstance3D = actor.get_node_or_null("SelectionRing") as MeshInstance3D
	if not _expect(ring != null, "the actor has a ground marker"):
		actor.queue_free()
		return
	var burials: Array[float] = []
	for step: int in 9:
		var x: float = -1.6 + float(step) * 0.4
		actor.global_position = Vector3(x, ridge_height(x, 0.0), 0.0)
		actor.call("_level_selection_ring")
		await physics_frame
		burials.append(_deepest_burial(ring))
	var deepest := 0.0
	for burial: float in burials:
		deepest = maxf(deepest, burial)
	_expect(deepest <= 0.0,
		"the marker clears the ground at every step of a walk (worst %.3f m)"
			% deepest)
	actor.queue_free()

## The ring under a harvest node is the other marker drawn flat on the ground,
## and on a slope most of it used to be inside the hill: what a player saw was
## a crescent that grew and shrank as they ran past.
func _a_harvest_node_ring_clears() -> void:
	var adapter := CoordinateAdapter.new({"metresPerTile": 1.0, "walkingHeight": 0.0})
	var node := MapObject3D.new()
	root.add_child(node)
	node.configure({"object_id": 3, "kind": 1, "x": 0, "y": 0,
		"label": "Snow Lily"}, adapter, {})
	var ring: MeshInstance3D = node.get_node_or_null("Ring") as MeshInstance3D
	if not _expect(ring != null and ring.visible,
			"an unmodelled harvest node falls back to its ring"):
		node.queue_free()
		return
	node.global_position = Vector3(0.0, 0.0, 0.0)
	var buried_flat: float = _deepest_burial(ring)
	node.set_surface_height(ridge_height(0.0, 0.0))
	var buried_draped: float = _deepest_burial(ring)
	_expect(buried_flat > 0.2,
		"the flat ring this exists to fix does sink into the ridge (%.3f m)"
			% buried_flat)
	# The ring is a torus, so its lower half lies inside the ground by design;
	# what matters is that no more of it than that does.
	_expect(buried_draped <= 0.05,
		"the draped ring lies on the ridge rather than in it (%.3f m under)"
			% buried_draped)
	node.queue_free()

func _expect(value: bool, label: String) -> bool:
	if not value:
		_failures += 1
		push_error("FAIL: " + label)
	return value
