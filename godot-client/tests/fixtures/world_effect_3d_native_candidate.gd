extends "res://tests/fixtures/world_effect_3d_967744_baseline.gd"
## Prototype wrapper for the coarse native detail-geometry boundary. Production
## selection stays untouched until exact parity and interface-inclusive timing
## are established against the frozen 967744 fixture.

static var _native_build_attempts := 0
static var _native_build_successes := 0
static var _native_build_fallbacks := 0

var _native_geometry: RefCounted
var _native_mesh := ArrayMesh.new()
var _details_node: MeshInstance3D


func configure(effect: int, origin: Vector3, target: Variant = null,
		power := 1) -> void:
	super.configure(effect, origin, target, power)
	_details_node = get_node("EffectRunes") as MeshInstance3D
	_initialize_native_geometry()
	if _native_geometry != null:
		_details_node.mesh = _native_mesh


func _initialize_native_geometry() -> void:
	if not ClassDB.class_exists(&"NativeWorldEffectGeometry"):
		return
	_native_geometry = ClassDB.instantiate(&"NativeWorldEffectGeometry") as RefCounted
	if _native_geometry != null and not _native_geometry.has_method(&"build"):
		_native_geometry = null


func native_presentation_active() -> bool:
	return _native_geometry != null


static func native_presentation_stats() -> Dictionary:
	return {
		"buildAttempts": _native_build_attempts,
		"buildSuccesses": _native_build_successes,
		"buildFallbacks": _native_build_fallbacks,
	}


func _draw_details(progress: float) -> void:
	if _native_geometry == null:
		super._draw_details(progress)
		return
	_native_build_attempts += 1
	var color := _palette()
	var size := SpellPresentation.power_scale(power_level)
	var radius := SpellPresentation.power_radius(power_level)
	color.a = sin(progress * PI) * 0.7
	var contact: Vector3 = flight.destination if flight != null else Vector3.ZERO
	var built: Variant = _native_geometry.call("build", effect_id, power_level,
		elapsed, progress, _impact, color, size, radius, area_radius,
		flight != null, contact)
	if _native_output_valid(built):
		_commit_native_surface(built as Array)
		_native_build_successes += 1
		return
	_native_build_fallbacks += 1
	_native_geometry = null
	_native_mesh.clear_surfaces()
	_details_node.mesh = _details
	super._draw_details(progress)


func _native_output_valid(built: Variant) -> bool:
	if typeof(built) != TYPE_ARRAY:
		return false
	var packed := built as Array
	if packed.size() != 2 \
			or typeof(packed[0]) != TYPE_PACKED_VECTOR3_ARRAY \
			or typeof(packed[1]) != TYPE_PACKED_COLOR_ARRAY:
		return false
	var vertices := packed[0] as PackedVector3Array
	var colors := packed[1] as PackedColorArray
	return not vertices.is_empty() and vertices.size() % 3 == 0 \
		and colors.size() == vertices.size()


func _commit_native_surface(packed: Array) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = packed[0]
	arrays[Mesh.ARRAY_COLOR] = packed[1]
	_native_mesh.clear_surfaces()
	_native_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_native_mesh.surface_set_material(0, _detail_material)
