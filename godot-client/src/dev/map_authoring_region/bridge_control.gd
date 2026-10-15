@tool
class_name MapAuthoringRegionBridge
extends "res://src/dev/map_authoring_pilot/bridge_control.gd"

const DECK_THICKNESS := 0.22
const PIER_SIZE := 0.55
const DECK_TILE_METRES := 0.24

@export var bridge_id := ""
@export var replaces_route_id := ""
@export var collision_role := "walk_surface"
@export var metadata: Dictionary = {}

var _preview_signature: Array = []
var _preview_elapsed := 0.0


func _ready() -> void:
	super._ready()
	refresh_preview()


func sync_surface_bindings() -> void:
	super.sync_surface_bindings()
	if deck_surface != null:
		deck_surface.enable_region_uv_projection()
	if support_surface != null:
		support_surface.enable_region_uv_projection()


func _process(delta: float) -> void:
	super._process(delta)
	if not Engine.is_editor_hint():
		return
	_preview_elapsed += delta
	if _preview_elapsed < 0.18:
		return
	_preview_elapsed = 0.0
	if _current_preview_signature() != _preview_signature:
		refresh_preview()


func refresh_preview() -> void:
	_preview_signature = _current_preview_signature()
	var deck := _preview_mesh("Deck")
	var supports := _preview_mesh("Supports")
	var start := start_marker()
	var end := end_marker()
	var region := _region_root()
	if start == null or end == null or region == null:
		deck.mesh = null
		supports.mesh = null
		return
	var region_inverse := region.global_transform.affine_inverse()
	var bridge_relative := region_inverse * global_transform
	var start_region := region_inverse * start.global_position
	var end_region := region_inverse * end.global_position
	var delta_xz := Vector2(end_region.x - start_region.x,
		end_region.z - start_region.z)
	var length := delta_xz.length()
	if length <= 0.001:
		deck.mesh = null
		supports.mesh = null
		return
	var horizontal_scale := Vector2(bridge_relative.basis.x.x,
		bridge_relative.basis.x.z).length()
	var vertical_scale := bridge_relative.basis.y.length()
	var rendered_width := width * horizontal_scale
	var rendered_arch := arch * vertical_scale
	var rendered_clearance := water_clearance * vertical_scale
	var segment_count := maxi(1, ceili(length))
	var centers: Array[Vector3] = []
	var uniform_lift := 0.0
	for index in segment_count + 1:
		var amount := float(index) / float(segment_count)
		var center := start_region.lerp(end_region, amount)
		center.y += 4.0 * rendered_arch * amount * (1.0 - amount)
		centers.append(center)
		var water_y: Variant = _river_water_height_region(center, region)
		if water_y != null:
			uniform_lift = maxf(uniform_lift,
				float(water_y) + rendered_clearance - center.y)
	if uniform_lift > 0.0:
		for index in centers.size():
			var lifted: Vector3 = centers[index]
			lifted.y += uniform_lift
			centers[index] = lifted
	var direction := delta_xz / length
	var side := Vector3(-direction.y, 0.0, direction.x) * rendered_width * 0.5
	var region_to_bridge := bridge_relative.affine_inverse()
	deck.mesh = _deck_mesh(centers, side, length, rendered_width,
		region_to_bridge)
	deck.material_override = deck_surface.get_material(
		deck_texture_rotation_degrees) if deck_surface != null else \
		_default_material(Color(0.34, 0.18, 0.075))
	supports.mesh = _support_mesh(start_region, end_region, rendered_arch,
		uniform_lift, length, region, region_to_bridge)
	supports.material_override = support_surface.get_material() \
		if support_surface != null else _default_material(Color(0.32, 0.31, 0.29))


func _deck_mesh(centers: Array[Vector3], side: Vector3, length: float,
		rendered_width: float, region_to_bridge: Transform3D) -> ArrayMesh:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	for index in centers.size() - 1:
		var along0 := length * float(index) / float(centers.size() - 1)
		var along1 := length * float(index + 1) / float(centers.size() - 1)
		var left0 := region_to_bridge * (centers[index] + side)
		var right0 := region_to_bridge * (centers[index] - side)
		var left1 := region_to_bridge * (centers[index + 1] + side)
		var right1 := region_to_bridge * (centers[index + 1] - side)
		var down := region_to_bridge.basis * Vector3.DOWN * DECK_THICKNESS
		var bottom_left0 := left0 + down
		var bottom_right0 := right0 + down
		var bottom_left1 := left1 + down
		var bottom_right1 := right1 + down
		var u1 := rendered_width / DECK_TILE_METRES
		var v0 := along0 / DECK_TILE_METRES
		var v1 := along1 / DECK_TILE_METRES
		_append_quad(tool, left0, left1, right0, right1,
			Vector2(0.0, v0), Vector2(0.0, v1), Vector2(u1, v0), Vector2(u1, v1))
		_append_quad(tool, bottom_right0, bottom_right1, bottom_left0, bottom_left1,
			Vector2(0.0, v0), Vector2(0.0, v1), Vector2(u1, v0), Vector2(u1, v1))
		_append_quad(tool, right0, right1, bottom_right0, bottom_right1,
			Vector2(0.0, v0), Vector2(0.0, v1),
			Vector2(DECK_THICKNESS / DECK_TILE_METRES, v0),
			Vector2(DECK_THICKNESS / DECK_TILE_METRES, v1))
		_append_quad(tool, bottom_left0, bottom_left1, left0, left1,
			Vector2(0.0, v0), Vector2(0.0, v1),
			Vector2(DECK_THICKNESS / DECK_TILE_METRES, v0),
			Vector2(DECK_THICKNESS / DECK_TILE_METRES, v1))
	tool.generate_normals()
	return tool.commit()


func _support_mesh(start_region: Vector3, end_region: Vector3,
		rendered_arch: float, uniform_lift: float, length: float, region: Node3D,
		region_to_bridge: Transform3D) -> ArrayMesh:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	var support_sections := ceili(length / 5.0)
	var support_count := 0
	for section in range(1, support_sections):
		var amount := float(section) / float(support_sections)
		var center := start_region.lerp(end_region, amount)
		center.y += 4.0 * rendered_arch * amount * (1.0 - amount) + uniform_lift
		var terrain_y: Variant = _terrain_height_region(center, region)
		if terrain_y == null:
			continue
		var top := center.y - DECK_THICKNESS
		var bottom := float(terrain_y)
		if top - bottom <= 0.3:
			continue
		_append_box(tool, Vector3(center.x, (top + bottom) * 0.5, center.z),
			Vector3(PIER_SIZE, top - bottom, PIER_SIZE), region_to_bridge)
		support_count += 1
	if support_count == 0:
		return null
	tool.generate_normals()
	return tool.commit()


func _append_quad(tool: SurfaceTool, a: Vector3, b: Vector3, c: Vector3,
		d: Vector3, uv_a := Vector2.ZERO, uv_b := Vector2.ZERO,
		uv_c := Vector2.ZERO, uv_d := Vector2.ZERO) -> void:
	_append_vertex(tool, a, uv_a)
	_append_vertex(tool, b, uv_b)
	_append_vertex(tool, c, uv_c)
	_append_vertex(tool, c, uv_c)
	_append_vertex(tool, b, uv_b)
	_append_vertex(tool, d, uv_d)


func _append_box(tool: SurfaceTool, center: Vector3, size: Vector3,
		region_to_bridge: Transform3D) -> void:
	var half := size * 0.5
	var corners: Array[Vector3] = []
	for value in [
		Vector3(-half.x, -half.y, -half.z), Vector3(half.x, -half.y, -half.z),
		Vector3(-half.x, half.y, -half.z), Vector3(half.x, half.y, -half.z),
		Vector3(-half.x, -half.y, half.z), Vector3(half.x, -half.y, half.z),
		Vector3(-half.x, half.y, half.z), Vector3(half.x, half.y, half.z)]:
		corners.append(region_to_bridge * (center + value))
	_append_quad(tool, corners[2], corners[6], corners[3], corners[7])
	_append_quad(tool, corners[1], corners[5], corners[0], corners[4])
	_append_quad(tool, corners[0], corners[2], corners[1], corners[3])
	_append_quad(tool, corners[5], corners[7], corners[4], corners[6])
	_append_quad(tool, corners[4], corners[6], corners[0], corners[2])
	_append_quad(tool, corners[1], corners[3], corners[5], corners[7])


func _append_vertex(tool: SurfaceTool, vertex: Vector3, uv: Vector2) -> void:
	tool.set_uv(uv)
	tool.add_vertex(vertex)


func _preview_mesh(child_name: String) -> MeshInstance3D:
	var container := get_node_or_null("__BridgePreview") as Node3D
	if container == null:
		container = Node3D.new()
		container.name = "__BridgePreview"
		add_child(container)
	var mesh_instance := container.get_node_or_null(child_name) as MeshInstance3D
	if mesh_instance == null:
		mesh_instance = MeshInstance3D.new()
		mesh_instance.name = child_name
		container.add_child(mesh_instance)
	return mesh_instance


func _terrain_control() -> Node3D:
	var region := _region_root()
	return region.get_node_or_null("Terrain") as Node3D if region != null else null


func _region_root() -> Node3D:
	var container := get_parent()
	return container.get_parent() as Node3D if container != null else null


func _river_water_height_region(point: Vector3, region: Node3D) -> Variant:
	var terrain := _terrain_control()
	if terrain == null or not terrain.has_method("river_water_height_at_local"):
		return null
	var region_to_terrain: Transform3D = terrain.global_transform.affine_inverse() * \
		region.global_transform
	var terrain_point := region_to_terrain * point
	var water_y: Variant = terrain.river_water_height_at_local(terrain_point.x,
		terrain_point.z)
	if water_y == null:
		return null
	terrain_point.y = float(water_y)
	return (region.global_transform.affine_inverse() * terrain.global_transform * \
		terrain_point).y


func _terrain_height_region(point: Vector3, region: Node3D) -> Variant:
	var terrain := _terrain_control()
	if terrain == null or not terrain.has_method("height_at_local"):
		return null
	var region_to_terrain: Transform3D = terrain.global_transform.affine_inverse() * \
		region.global_transform
	var terrain_point := region_to_terrain * point
	var height: float = terrain.height_at_local(terrain_point.x, terrain_point.z)
	if is_nan(height):
		return null
	terrain_point.y = height
	return (region.global_transform.affine_inverse() * terrain.global_transform * \
		terrain_point).y


func _default_material(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	return material


func _current_preview_signature() -> Array:
	var terrain := _terrain_control()
	return [authored_signature(), int(terrain.get("preview_revision")) \
		if terrain != null else -1]


func _get_configuration_warnings() -> PackedStringArray:
	var warnings := PackedStringArray()
	if bridge_id.strip_edges().is_empty():
		warnings.append("Region bridges need a stable Bridge Id before export.")
	if start_marker() == null or end_marker() == null:
		warnings.append("Region bridges need Start and End Marker3D children.")
	elif start_marker().global_position.distance_to(end_marker().global_position) <= 0.001:
		warnings.append("Region bridge endpoints must be distinct.")
	return warnings
