@tool
extends RefCounted
## Fast, exact terrain queries for editor tools that run on every mouse motion.
##
## Region terrain answers through its effective height grid: a 2D cell walk along
## the ray tests the same two triangles per cell that the preview mesh and
## `MapAuthoringTerrainControl.intersect_local_segment` use, so hits agree with a
## click, but the cost follows the cells the ray crosses instead of the whole grid.
## Any other authoring root falls back to its own `authoring_ground_intersection`.

const TERRAIN_SCRIPT := preload("res://src/dev/map_authoring_region/terrain_control.gd")
const MAX_CELL_STEPS := 4096


static func region_terrain(root: Node) -> Node3D:
	if root == null:
		return null
	var terrain := root.get_node_or_null("Terrain")
	if terrain is Node3D and (terrain as Node).get_script() == TERRAIN_SCRIPT:
		return terrain as Node3D
	return null


static func ray_hit(root: Node3D, ray_origin: Vector3, ray_direction: Vector3,
		max_distance: float = 2048.0) -> Variant:
	if root == null or not ray_origin.is_finite() or not ray_direction.is_finite() or \
			ray_direction.length_squared() <= 0.000001:
		return null
	var terrain := region_terrain(root)
	if terrain == null:
		if root.has_method("authoring_ground_intersection"):
			return root.call("authoring_ground_intersection", ray_origin, ray_direction,
				max_distance)
		return null
	var inverse := terrain.global_transform.affine_inverse()
	var start: Vector3 = inverse * ray_origin
	var finish: Vector3 = inverse * (ray_origin + ray_direction.normalized() * max_distance)
	var hit: Variant = _walk_cells(terrain, start, finish)
	return terrain.global_transform * (hit as Vector3) if hit is Vector3 else null


## World height of the terrain under a world XZ position, or NAN outside it.
static func height_at(root: Node3D, world_position: Vector3) -> float:
	var terrain := region_terrain(root)
	if terrain != null:
		var local: Vector3 = terrain.global_transform.affine_inverse() * world_position
		if not _inside_grid(terrain, local.x, local.z):
			return NAN
		var height: float = terrain.call("height_at_local", local.x, local.z)
		if is_nan(height):
			return NAN
		return (terrain.global_transform * Vector3(local.x, height, local.z)).y
	var hit: Variant = ray_hit(root, Vector3(world_position.x, world_position.y + 4096.0,
		world_position.z), Vector3.DOWN, 8192.0)
	return (hit as Vector3).y if hit is Vector3 else NAN


## Upward surface normal from four nearby height samples.
static func normal_at(root: Node3D, world_position: Vector3, spacing: float = 0.75) -> Vector3:
	var east := height_at(root, world_position + Vector3(spacing, 0.0, 0.0))
	var west := height_at(root, world_position - Vector3(spacing, 0.0, 0.0))
	var south := height_at(root, world_position + Vector3(0.0, 0.0, spacing))
	var north := height_at(root, world_position - Vector3(0.0, 0.0, spacing))
	if is_nan(east) or is_nan(west) or is_nan(south) or is_nan(north):
		return Vector3.UP
	var normal := Vector3(west - east, 2.0 * spacing, north - south).normalized()
	return normal if normal.is_finite() and normal.y > 0.0 else Vector3.UP


## Territory-local metres and, when the root carries the region contract, the
## server tile using the snapshot conversion documented for regions.
static func describe_point(root: Node3D, world_position: Vector3) -> Dictionary:
	var local: Vector3 = root.global_transform.affine_inverse() * world_position
	var result := {"local": local, "has_tile": false}
	var metres_per_tile: Variant = root.get("metres_per_tile")
	var server_origin: Variant = root.get("server_origin")
	if (metres_per_tile is float or metres_per_tile is int) and float(metres_per_tile) > 0.0 \
			and server_origin is Vector2i:
		var origin := server_origin as Vector2i
		result.has_tile = true
		result.tile = Vector2i(
			floori(local.x / float(metres_per_tile) + float(origin.x)),
			floori(float(origin.y) - local.z / float(metres_per_tile)))
	return result


static func _inside_grid(terrain: Node3D, x: float, z: float) -> bool:
	var origin: Vector2 = terrain.get("origin")
	var cell: float = terrain.get("cell_metres")
	var grid: Vector2i = terrain.get("grid_size")
	return x >= origin.x and z >= origin.y and \
		x <= origin.x + float(grid.x - 1) * cell and z <= origin.y + float(grid.y - 1) * cell


static func _walk_cells(terrain: Node3D, start: Vector3, finish: Vector3) -> Variant:
	var origin: Vector2 = terrain.get("origin")
	var cell: float = terrain.get("cell_metres")
	var grid: Vector2i = terrain.get("grid_size")
	if cell <= 0.0 or grid.x < 2 or grid.y < 2:
		return null
	# Cell corners come from `height_at_local` on exact grid vertices, which returns
	# the stored effective heights without copying the whole grid.
	var extent := Vector2(float(grid.x - 1) * cell, float(grid.y - 1) * cell)
	var clipped := _clip_segment_xz(start, finish, origin, origin + extent)
	if clipped.is_empty():
		return null
	var a: Vector3 = clipped[0]
	var b: Vector3 = clipped[1]
	var fx := (a.x - origin.x) / cell
	var fz := (a.z - origin.y) / cell
	var cx := clampi(floori(fx), 0, grid.x - 2)
	var cz := clampi(floori(fz), 0, grid.y - 2)
	var dx := b.x - a.x
	var dz := b.z - a.z
	var step_x := 1 if dx > 0.0 else -1
	var step_z := 1 if dz > 0.0 else -1
	var t_delta_x := absf(cell / dx) if absf(dx) > 0.0000001 else INF
	var t_delta_z := absf(cell / dz) if absf(dz) > 0.0000001 else INF
	var next_x := origin.x + float(cx + (1 if step_x > 0 else 0)) * cell
	var next_z := origin.y + float(cz + (1 if step_z > 0 else 0)) * cell
	var t_max_x := (next_x - a.x) / dx if absf(dx) > 0.0000001 else INF
	var t_max_z := (next_z - a.z) / dz if absf(dz) > 0.0000001 else INF
	var t_enter := 0.0
	for _step in MAX_CELL_STEPS:
		var t_exit := minf(minf(t_max_x, t_max_z), 1.0)
		var hit: Variant = _cell_hit(terrain, cx, cz, origin, cell, a, b, t_enter, t_exit)
		if hit is Vector3:
			return hit
		if t_exit >= 1.0:
			return null
		if t_max_x < t_max_z:
			cx += step_x
			t_enter = t_max_x
			t_max_x += t_delta_x
		else:
			cz += step_z
			t_enter = t_max_z
			t_max_z += t_delta_z
		if cx < 0 or cz < 0 or cx > grid.x - 2 or cz > grid.y - 2:
			return null
	return null


static func _cell_hit(terrain: Node3D, cx: int, cz: int, origin: Vector2, cell: float,
		a: Vector3, b: Vector3, t_enter: float, t_exit: float) -> Variant:
	var x0 := origin.x + float(cx) * cell
	var z0 := origin.y + float(cz) * cell
	var h00: float = terrain.call("height_at_local", x0, z0)
	var h10: float = terrain.call("height_at_local", x0 + cell, z0)
	var h01: float = terrain.call("height_at_local", x0, z0 + cell)
	var h11: float = terrain.call("height_at_local", x0 + cell, z0 + cell)
	var low := minf(minf(h00, h10), minf(h01, h11))
	var high := maxf(maxf(h00, h10), maxf(h01, h11))
	var y_enter := lerpf(a.y, b.y, maxf(t_enter - 0.001, 0.0))
	var y_exit := lerpf(a.y, b.y, minf(t_exit + 0.001, 1.0))
	if minf(y_enter, y_exit) > high + 0.001 or maxf(y_enter, y_exit) < low - 0.001:
		return null
	var p00 := Vector3(x0, h00, z0)
	var p10 := Vector3(x0 + cell, h10, z0)
	var p01 := Vector3(x0, h01, z0 + cell)
	var p11 := Vector3(x0 + cell, h11, z0 + cell)
	var nearest: Variant = null
	var nearest_distance := INF
	for triangle: Array in [[p00, p01, p10], [p10, p01, p11]]:
		var hit: Variant = Geometry3D.segment_intersects_triangle(a, b, triangle[0],
			triangle[1], triangle[2])
		if hit is Vector3:
			var distance := a.distance_squared_to(hit as Vector3)
			if distance < nearest_distance:
				nearest_distance = distance
				nearest = hit
	return nearest


## Clips a 3D segment to an XZ rectangle and returns [start, end] or [].
static func _clip_segment_xz(start: Vector3, finish: Vector3, minimum: Vector2,
		maximum: Vector2) -> Array:
	var t0 := 0.0
	var t1 := 1.0
	var delta := finish - start
	for axis in [[start.x, delta.x, minimum.x, maximum.x],
			[start.z, delta.z, minimum.y, maximum.y]]:
		var p: float = axis[0]
		var d: float = axis[1]
		var low: float = axis[2]
		var high: float = axis[3]
		if absf(d) < 0.0000001:
			if p < low or p > high:
				return []
			continue
		var ta := (low - p) / d
		var tb := (high - p) / d
		t0 = maxf(t0, minf(ta, tb))
		t1 = minf(t1, maxf(ta, tb))
		if t0 > t1:
			return []
	return [start + delta * t0, start + delta * t1]
