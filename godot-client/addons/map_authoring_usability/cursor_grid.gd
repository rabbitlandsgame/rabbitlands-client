@tool
extends RefCounted
## The "smart grid": a small grid patch under the cursor that drapes over the
## terrain, fades with distance, and follows the ground height automatically.
##
## The mesh is an internal, ownerless child of the edited scene root, so it can
## never be packed into a saved scene or a snapshot.

const Probe := preload("res://addons/map_authoring_usability/terrain_probe.gd")
const NODE_NAME := "__MapAuthoringCursorGrid"
const LIFT := 0.06
const SAMPLES_PER_CELL := 2

var _mesh_instance: MeshInstance3D
var _mesh: ImmediateMesh
var _material: StandardMaterial3D
var _root: Node3D
var _last_key := ""


func show_at(root: Node3D, world_position: Vector3, step: float, radius_cells: int,
		color: Color = Color(0.92, 0.96, 1.0, 0.85), mark_snap_point: bool = false) -> void:
	# Only region terrain answers height queries cheaply enough to drape a grid on
	# every cursor move; the pilot's whole-mesh ray test would stall the editor.
	if root == null or step <= 0.0 or not world_position.is_finite() or \
			Probe.region_terrain(root) == null:
		hide()
		return
	_ensure(root)
	var inverse := root.global_transform.affine_inverse()
	var local: Vector3 = inverse * world_position
	var centre_x := roundf(local.x / step) * step
	var centre_z := roundf(local.z / step) * step
	var key := "%s|%.4f|%.4f|%.4f|%d|%d|%s|%s" % [root.get_instance_id(), centre_x, centre_z,
		step, radius_cells, _terrain_revision(root), color.to_html(), mark_snap_point]
	_mesh_instance.visible = true
	if key == _last_key:
		return
	_last_key = key
	_mesh.clear_surfaces()
	var radius := float(radius_cells) * step
	var sample_step := step / float(SAMPLES_PER_CELL)
	_mesh.surface_begin(Mesh.PRIMITIVE_LINES, _material)
	var line_count := radius_cells * 2 + 1
	for axis in 2:
		for line_index in line_count:
			var offset := (float(line_index) - float(radius_cells)) * step
			var previous: Variant = null
			var previous_alpha := 0.0
			var samples := radius_cells * 2 * SAMPLES_PER_CELL + 1
			for sample_index in samples:
				var along := -radius + float(sample_index) * sample_step
				var lx := centre_x + (offset if axis == 0 else along)
				var lz := centre_z + (along if axis == 0 else offset)
				var world := root.global_transform * Vector3(lx, 0.0, lz)
				var height := Probe.height_at(root, world)
				if is_nan(height):
					previous = null
					continue
				var point := Vector3(world.x, height + LIFT, world.z)
				var distance := Vector2(lx - centre_x, lz - centre_z).length()
				var alpha := clampf(1.0 - distance / radius, 0.0, 1.0)
				if previous is Vector3 and (alpha > 0.0 or previous_alpha > 0.0):
					_mesh.surface_set_color(Color(color, color.a * previous_alpha))
					_mesh.surface_add_vertex(_mesh_instance.global_transform.affine_inverse() *
						(previous as Vector3))
					_mesh.surface_set_color(Color(color, color.a * alpha))
					_mesh.surface_add_vertex(_mesh_instance.global_transform.affine_inverse() *
						point)
				previous = point
				previous_alpha = alpha
	# While snapping, a small cross marks the exact point the placement will use.
	var centre_world := root.global_transform * Vector3(centre_x, 0.0, centre_z)
	var centre_height := Probe.height_at(root, centre_world)
	if mark_snap_point and not is_nan(centre_height):
		var mark := Vector3(centre_world.x, centre_height + LIFT * 2.0, centre_world.z)
		var arm := step * 0.2
		for direction: Vector3 in [Vector3(arm, 0, 0), Vector3(0, 0, arm)]:
			_mesh.surface_set_color(Color(1.0, 0.85, 0.3, 0.95))
			_mesh.surface_add_vertex(_mesh_instance.global_transform.affine_inverse() *
				(mark - direction))
			_mesh.surface_set_color(Color(1.0, 0.85, 0.3, 0.95))
			_mesh.surface_add_vertex(_mesh_instance.global_transform.affine_inverse() *
				(mark + direction))
	_mesh.surface_end()


func hide() -> void:
	if is_instance_valid(_mesh_instance):
		_mesh_instance.visible = false


func release() -> void:
	if is_instance_valid(_mesh_instance):
		_mesh_instance.queue_free()
	_mesh_instance = null
	_root = null
	_last_key = ""


func node() -> MeshInstance3D:
	return _mesh_instance if is_instance_valid(_mesh_instance) else null


func _ensure(root: Node3D) -> void:
	if is_instance_valid(_mesh_instance) and _root == root and _mesh_instance.is_inside_tree():
		return
	release()
	_root = root
	_mesh = ImmediateMesh.new()
	_material = StandardMaterial3D.new()
	_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_material.vertex_color_use_as_albedo = true
	# Ground-region overlays sit a few centimetres above the terrain; like the
	# sculpt ring, the grid draws on top so those never swallow it.
	_material.no_depth_test = true
	_material.render_priority = 2
	_mesh_instance = MeshInstance3D.new()
	_mesh_instance.name = NODE_NAME
	_mesh_instance.mesh = _mesh
	_mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mesh_instance.top_level = true
	root.add_child(_mesh_instance, false, Node.INTERNAL_MODE_BACK)
	_mesh_instance.global_transform = Transform3D.IDENTITY


func _terrain_revision(root: Node3D) -> int:
	var terrain := Probe.region_terrain(root)
	return int(terrain.get("preview_revision")) if terrain != null else 0
