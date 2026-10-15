@tool
extends RefCounted
## Readable gameplay markers: a coloured pin per kind, a name label, a facing
## arrow for spawns and portals, and the footprint a harvestable or herd covers.
## Godot draws markers as identical grey crosses, which makes a territory with
## hundreds of them unreadable.
##
## Everything lives under one internal, ownerless node, so it is never saved or
## baked. It is rebuilt only when a marker's position, kind, label or extent
## changes.

const Markers := preload("res://addons/map_asset_palette/marker_library.gd")
const NODE_NAME := "__MapAuthoringMarkerOverlay"
const PIN_HEIGHT := 2.4
const RING_SEGMENTS := 20
const LABEL_RANGE := 140.0

var _root: Node3D
var _holder: Node3D
var _lines: MeshInstance3D
var _mesh: ImmediateMesh
var _labels: Node3D
var _signature := ""


func refresh(root: Node3D, show_labels: bool) -> void:
	if root == null or root.get_node_or_null(Markers.GAMEPLAY) == null:
		release()
		return
	var markers := Markers.markers(root)
	var signature := _signature_for(markers, show_labels)
	if _holder != null and is_instance_valid(_holder) and _root == root and \
			signature == _signature:
		return
	_ensure(root)
	_signature = signature
	_mesh.clear_surfaces()
	for child in _labels.get_children():
		_labels.remove_child(child)
		child.queue_free()
	if markers.is_empty():
		return
	var to_local := _holder.global_transform.affine_inverse()
	_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for marker_value in markers:
		var marker := marker_value as Node3D
		var kind := String(marker.get("kind"))
		var color := Markers.color_for(kind)
		var base := to_local * marker.global_position
		var top := base + Vector3.UP * PIN_HEIGHT
		_line(base, top, color)
		_diamond(top, 0.35, color)
		_ring(base + Vector3.UP * 0.05, 0.6, color)
		var extras: Dictionary = marker.get("extras")
		if kind == "harvestable" and extras.get("extent") is Array and \
				(extras.extent as Array).size() >= 2:
			_rectangle(base + Vector3.UP * 0.08, Vector2(float(extras.extent[0]),
				float(extras.extent[1])), Color(color, 0.8))
		if kind == "ambient_population" and extras.has("radius"):
			_ring(base + Vector3.UP * 0.08, float(extras.radius), Color(color, 0.8))
		if kind in ["spawn", "portal"]:
			var facing: Vector3 = marker.get("facing")
			var flat := Vector3(facing.x, 0.0, facing.z)
			if flat.length_squared() > 0.0001:
				var tip := base + Vector3.UP * 0.1 + flat.normalized() * 1.6
				_line(base + Vector3.UP * 0.1, tip, color)
				var side := flat.normalized().cross(Vector3.UP) * 0.35
				_line(tip, tip - flat.normalized() * 0.5 + side, color)
				_line(tip, tip - flat.normalized() * 0.5 - side, color)
		if show_labels:
			var label := Label3D.new()
			var text := String(marker.get("label"))
			label.text = text if not text.is_empty() else String(marker.get("record_id"))
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.pixel_size = 0.006
			label.font_size = 40
			label.outline_size = 10
			label.modulate = color.lightened(0.25)
			label.outline_modulate = Color(0.0, 0.0, 0.0, 0.85)
			label.visibility_range_end = LABEL_RANGE
			label.position = top + Vector3.UP * 0.55
			_labels.add_child(label)
	_mesh.surface_end()


func release() -> void:
	if _holder != null and is_instance_valid(_holder):
		if _holder.get_parent() != null:
			_holder.get_parent().remove_child(_holder)
		_holder.queue_free()
	_holder = null
	_root = null
	_signature = ""


func node() -> Node3D:
	return _holder if _holder != null and is_instance_valid(_holder) else null


func label_count() -> int:
	return _labels.get_child_count() if node() != null else 0


func _ensure(root: Node3D) -> void:
	if _holder != null and is_instance_valid(_holder) and _root == root and \
			_holder.is_inside_tree():
		return
	release()
	_root = root
	_holder = Node3D.new()
	_holder.name = NODE_NAME
	_holder.top_level = true
	_mesh = ImmediateMesh.new()
	_lines = MeshInstance3D.new()
	_lines.name = "Pins"
	_lines.mesh = _mesh
	_lines.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_lines.material_override = material
	_holder.add_child(_lines)
	_labels = Node3D.new()
	_labels.name = "Labels"
	_holder.add_child(_labels)
	root.add_child(_holder, false, Node.INTERNAL_MODE_BACK)
	_holder.global_transform = Transform3D.IDENTITY


func _signature_for(markers: Array[Node], show_labels: bool) -> String:
	var parts := PackedStringArray([str(show_labels)])
	for marker_value in markers:
		var marker := marker_value as Node3D
		var position := marker.global_position
		var extras: Dictionary = marker.get("extras")
		parts.append("%d|%.2f|%.2f|%.2f|%s|%s|%s|%s|%s|%s" % [marker.get_instance_id(),
			position.x, position.y, position.z, String(marker.get("kind")),
			String(marker.get("label")), String(marker.get("record_id")),
			str(extras.get("extent", "")), str(extras.get("radius", "")),
			str(marker.get("facing"))])
	return "\n".join(parts)


func _line(a: Vector3, b: Vector3, color: Color) -> void:
	_mesh.surface_set_color(color)
	_mesh.surface_add_vertex(a)
	_mesh.surface_set_color(color)
	_mesh.surface_add_vertex(b)


func _diamond(centre: Vector3, size: float, color: Color) -> void:
	var points := [centre + Vector3(size, 0, 0), centre + Vector3(0, size, 0),
		centre + Vector3(-size, 0, 0), centre + Vector3(0, -size, 0)]
	for index in points.size():
		_line(points[index], points[(index + 1) % points.size()], color)
	_line(centre + Vector3(0, 0, size), centre + Vector3(0, size, 0), color)
	_line(centre + Vector3(0, 0, -size), centre + Vector3(0, size, 0), color)


func _ring(centre: Vector3, radius: float, color: Color) -> void:
	if radius <= 0.0:
		return
	var previous := centre + Vector3(radius, 0.0, 0.0)
	for index in range(1, RING_SEGMENTS + 1):
		var angle := TAU * float(index) / float(RING_SEGMENTS)
		var next := centre + Vector3(cos(angle) * radius, 0.0, sin(angle) * radius)
		_line(previous, next, color)
		previous = next


func _rectangle(centre: Vector3, size: Vector2, color: Color) -> void:
	var half := size * 0.5
	var corners := [centre + Vector3(-half.x, 0, -half.y), centre + Vector3(half.x, 0, -half.y),
		centre + Vector3(half.x, 0, half.y), centre + Vector3(-half.x, 0, half.y)]
	for index in corners.size():
		_line(corners[index], corners[(index + 1) % corners.size()], color)
