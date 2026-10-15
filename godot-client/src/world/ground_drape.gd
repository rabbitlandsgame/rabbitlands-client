class_name GroundDrape
extends RefCounted
## Lays a flat ground marker over the ground it marks.
##
## Several markers are drawn as flat geometry a fixed few centimetres above the
## one point the client sampled underneath an actor or an object: the box under
## a selected actor, the ring under a harvest node. Ground is not flat over the
## metre such a marker covers - on Whitehorn Range the terrain rises more than
## five centimetres within half a metre under nine tiles in ten - so the uphill
## part of a marker ends up inside the slope and the depth buffer drops it.
## Which part survives changes with every step the actor takes and every degree
## the camera turns, so a marker that keeps losing and regaining a quarter of
## itself is what a player running across a region sees as flicker.
##
## Draping raises each vertex by the ground under that vertex, so a marker keeps
## its own shape and thickness and stands the same distance off the ground all
## the way round.

## How far a draped marker floats over the ground beneath it. Enough that the
## depth buffer can separate the two at the distance the isometric rig looks
## from, small enough that the marker still reads as lying on the ground.
const CLEARANCE := 0.05
## Ground samples this close together share a ray. A marker's mesh repeats the
## same corner across the triangles that meet there, and a centimetre is under
## the width of the outlines being draped, so this spends one query per corner
## without ever answering for ground a corner is not standing on.
const SAMPLE_QUANTUM := 0.01

## How far a ray that missed is moved before it is asked again. A heightfield
## is a grid of triangles and a marker's own vertices fall on round numbers, so
## a ray dropped exactly down a seam between two of them can pass between the
## pair and report no ground at all. A tenth of a millimetre is inside the
## width of that seam and outside nothing else.
const SEAM_NUDGE := 0.0001

## The walk surface's height under `x, z`, or null where there is none.
##
## The ray runs the full height of any authored region, and it hits only the
## navigation layer the loader hangs off the terrain: structural collision -
## gates, bridge sides, an interior's walls - is not ground a marker lies on.
static func surface_height(space: PhysicsDirectSpaceState3D, x: float,
		z: float) -> Variant:
	if space == null:
		return null
	var found: Variant = _cast(space, x, z)
	if found == null:
		found = _cast(space, x + SEAM_NUDGE, z + SEAM_NUDGE)
	return found

static func _cast(space: PhysicsDirectSpaceState3D, x: float,
		z: float) -> Variant:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(x, 400.0, z), Vector3(x, -100.0, z),
		WorldLoader.NAVIGATION_SURFACE_LAYER)
	var hit: Dictionary = space.intersect_ray(query)
	var position_value: Variant = hit.get("position")
	if position_value is not Vector3:
		return null
	return (position_value as Vector3).y

## `flat`'s geometry with every vertex lifted onto the ground under it, ready to
## hand back to `node`.
##
## The result stays in `node`'s local space and puts the marker's own zero plane
## `clearance` above the ground under each of its points, whatever height the
## caller gave the node, so a marker keeps sitting on the ground while the actor
## carrying it walks up a slope. Returns null when the ground cannot be sampled
## at all - off the edge of a map, or before the walk surface exists - so a
## caller can leave the flat mesh in place rather than drape over nothing.
static func drape(node: Node3D, flat: Mesh, clearance := CLEARANCE) -> ArrayMesh:
	if node == null or flat == null or not node.is_inside_tree():
		return null
	var world: World3D = node.get_world_3d()
	if world == null:
		return null
	var space: PhysicsDirectSpaceState3D = world.direct_space_state
	var origin: Vector3 = node.global_position
	var reference: Variant = surface_height(space, origin.x, origin.z)
	if reference == null:
		return null
	var origin_height: float = origin.y
	var to_world: Transform3D = node.global_transform
	var draped := ArrayMesh.new()
	var samples: Dictionary = {}
	for surface: int in flat.get_surface_count():
		var arrays: Array = flat.surface_get_arrays(surface)
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var lifted := PackedVector3Array()
		lifted.resize(vertices.size())
		for index: int in vertices.size():
			var vertex: Vector3 = vertices[index]
			var point: Vector3 = to_world * vertex
			var key := Vector2i(roundi(point.x / SAMPLE_QUANTUM),
				roundi(point.z / SAMPLE_QUANTUM))
			var height: Variant = samples.get(key)
			if height == null:
				height = surface_height(space, point.x, point.z)
				if height == null:
					height = reference
				samples[key] = height
			vertex.y += float(height) - origin_height + clearance
			lifted[index] = vertex
		# A marker built from one of Godot's primitives - the harvest node's
		# torus - answers for its arrays but not for the surface accessors an
		# ArrayMesh has, and every one of those primitives is triangles.
		var primitive: int = Mesh.PRIMITIVE_TRIANGLES
		var material: Material = null
		if flat is ArrayMesh:
			primitive = (flat as ArrayMesh).surface_get_primitive_type(surface)
			material = (flat as ArrayMesh).surface_get_material(surface)
		elif flat is PrimitiveMesh:
			material = (flat as PrimitiveMesh).material
		arrays[Mesh.ARRAY_VERTEX] = lifted
		draped.add_surface_from_arrays(primitive, arrays)
		draped.surface_set_material(surface, material)
	return draped
