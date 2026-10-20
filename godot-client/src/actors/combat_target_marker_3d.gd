extends Node3D
## A combat cue independent of clicked selection and nameplate visibility.

const COLOUR := Color("ff755f")
const BORDER := Color.BLACK
const LAYER := 2
const SEGMENTS := 32
const Style := preload("res://src/actors/target_marker_style.gd")
var ring: MeshInstance3D
var pointer: Label3D
var _flat: ArrayMesh
var _size := Vector2.ZERO
var _draped_at := Vector3(NAN, NAN, NAN)
var _style := Style.defaults()

func _init() -> void:
	name = "CombatTargetMarker"
	ring = MeshInstance3D.new()
	ring.name = "Ring"
	ring.layers = LAYER
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ring.position.y = GroundDrape.CLEARANCE
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	ring.material_override = material
	add_child(ring)
	pointer = Label3D.new()
	pointer.name = "Pointer"
	pointer.text = "▼"
	pointer.font_size = 48
	pointer.pixel_size = 0.00075
	pointer.fixed_size = true
	pointer.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	pointer.no_depth_test = true
	pointer.modulate = COLOUR
	pointer.outline_modulate = BORDER
	pointer.outline_size = 6
	pointer.layers = preload("res://src/ui/world_label_style.gd").RENDER_LAYER
	add_child(pointer)
	hide()
	set_physics_process(false)

func configure(enabled: bool, footprint_metres: Vector2, head_height: float,
		appearance: Dictionary = {}) -> void:
	var next := Style.normalise(appearance)
	var changed := next != _style
	if changed:
		_style = next
		pointer.font_size = roundi(48.0 * _style.triangle_size / 100.0)
		pointer.outline_size = maxi(1, roundi(6.0 * _style.triangle_size / 100.0 * _style.triangle_thickness / 100.0))
		pointer.modulate = _style.triangle_color
	pointer.position.y = head_height + 0.75
	if enabled and not visible:
		invalidate_ground()
	if footprint_metres != _size or changed:
		_size = footprint_metres
		_flat = outline(footprint_metres, _style.circle_size / 100.0,
			_style.circle_thickness / 100.0, _style.circle_color)
		ring.mesh = _flat
		_draped_at = Vector3(NAN, NAN, NAN)
	visible = enabled
	set_physics_process(enabled)
	if enabled:
		_physics_process(0.0)

func invalidate_ground() -> void:
	_draped_at = Vector3(NAN, NAN, NAN)

func _physics_process(_delta: float) -> void:
	if not is_inside_tree() or not is_visible_in_tree():
		return
	# Terrain and the reserved box do not turn with the creature.
	global_rotation = Vector3.ZERO
	var here := global_position
	if _draped_at.is_finite() and here.distance_to(_draped_at) < 0.05:
		return
	var draped := GroundDrape.drape(ring, _flat)
	ring.mesh = _flat if draped == null else draped
	if draped != null:
		_draped_at = here

static func outline(size_metres: Vector2, size_scale := 1.0,
		thickness_scale := 1.0, colour := COLOUR) -> ArrayMesh:
	var radius := (size_metres * 0.5 + Vector2.ONE * 0.16) * size_scale
	# Keep an open centre even at the smallest size and thickest setting.
	thickness_scale = minf(thickness_scale, minf(radius.x, radius.y) * 0.9 / 0.145)
	var segments := maxi(SEGMENTS, ceili(TAU * maxf(radius.x, radius.y) / 0.5))
	var vertices := PackedVector3Array()
	var colours := PackedColorArray()
	var normals := PackedVector3Array()
	# Three adjoining bands keep the coral readable on pale and dark terrain.
	for band: int in 3:
		var inner: Vector2 = radius - Vector2.ONE * [0.145, 0.11, 0.0][band] * thickness_scale
		var outer: Vector2 = radius - Vector2.ONE * [0.11, 0.0, -0.035][band] * thickness_scale
		for i: int in segments:
			var a := TAU * float(i) / segments
			var b := TAU * float(i + 1) / segments
			var p := Vector3(cos(a) * inner.x, 0, sin(a) * inner.y)
			var q := Vector3(cos(a) * outer.x, 0, sin(a) * outer.y)
			var r := Vector3(cos(b) * outer.x, 0, sin(b) * outer.y)
			var s := Vector3(cos(b) * inner.x, 0, sin(b) * inner.y)
			for point: Vector3 in [p, q, r, p, r, s]:
				vertices.append(point)
				normals.append(Vector3.UP)
				colours.append(colour if band == 1 else BORDER)
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_COLOR] = colours
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh
