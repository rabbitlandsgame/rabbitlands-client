extends Node3D
## A bounded, analytic trail: identical at any frame rate and no full-length beam.
## UV falloff supplies soft edges in Compatibility, without requiring bloom.
const ENERGY_SHADER = preload("res://src/world/spell_energy.gdshader")
const SEGMENTS := 28
const AFTERGLOW := 0.24
var duration := 0.4
var start := Vector3.ZERO
var destination := Vector3.ZERO
var effect_id := 2
var power_level := 1
var tint := Color.WHITE
var _side := Vector3.RIGHT
var _up := Vector3.UP
var _path_distance := 0.0
var _path_spread := 0.0
var _path_arc := 0.0
var _tail_fraction := 0.58
var _mesh := ImmediateMesh.new()
var _native_mesh: ArrayMesh
var _mesh_node: MeshInstance3D
var _ribbon_material: ShaderMaterial
var _glow_material: ShaderMaterial
var _native_geometry: RefCounted
static var _power_materials: Dictionary = {}
static var _native_build_attempts := 0
static var _native_build_successes := 0
static var _native_build_fallbacks := 0

func _init() -> void:
	_initialize_native_presentation()
	if _native_geometry != null:
		_native_mesh = ArrayMesh.new()
	_set_power_materials(1)
	_mesh_node = MeshInstance3D.new()
	_mesh_node.name = "SpellEnergy"
	_mesh_node.mesh = _native_mesh if _native_geometry != null else _mesh
	_mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_mesh_node)

func _initialize_native_presentation() -> void:
	var mode := OS.get_environment("ELORIA_NATIVE_PRESENTATION").strip_edges().to_lower()
	if mode not in ["1", "flight", "both", "all"]:
		return
	if not ClassDB.class_exists(&"NativeSpellFlightGeometry"):
		var extension_path := "res://bin/native_crowd.gdextension"
		if not FileAccess.file_exists(extension_path):
			return
		GDExtensionManager.load_extension(extension_path)
	if not ClassDB.class_exists(&"NativeSpellFlightGeometry"):
		return
	_native_geometry = ClassDB.instantiate(&"NativeSpellFlightGeometry") as RefCounted
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

func _set_power_materials(power: int) -> void:
	if not _power_materials.has(power):
		_ribbon_material = ShaderMaterial.new()
		_ribbon_material.shader = ENERGY_SHADER
		_glow_material = ShaderMaterial.new()
		_glow_material.shader = ENERGY_SHADER
		_glow_material.set_shader_parameter("radial", true)
		# Vertex colors are packed into bytes. Brightness belongs in the shader
		# so high powers don't clip orange/green/violet into the same yellow.
		for material: ShaderMaterial in [_ribbon_material, _glow_material]:
			material.set_shader_parameter("intensity", SpellPresentation.power_intensity(power))
		_power_materials[power] = [_ribbon_material, _glow_material]
	_ribbon_material = _power_materials[power][0]
	_glow_material = _power_materials[power][1]

func configure(id: int, color: Color, from: Vector3, to: Vector3, power := 1) -> void:
	effect_id = id
	power_level = clampi(power, 1, 10)
	_set_power_materials(power_level)
	tint = color
	set_endpoints(from, to)
	duration = clampf(_path_distance / 13.0, 0.22, 0.62)

func set_endpoints(from: Vector3, to: Vector3) -> void:
	start = from
	destination = to
	var offset := to - from
	_path_distance = offset.length()
	_path_spread = minf(1.0, _path_distance / 1.5)
	_path_arc = minf(_path_distance * 0.055, 0.36)
	_tail_fraction = minf(0.58, 1.7 / maxf(0.1, _path_distance))
	var direction := offset.normalized()
	_side = direction.cross(Vector3.UP).normalized()
	if _side.length_squared() < 0.01:
		_side = Vector3.RIGHT
	_up = _side.cross(direction).normalized()

func point_at(progress: float, strand := 0) -> Vector3:
	var p := clampf(progress, 0.0, 1.0)
	var envelope := sin(p * PI)
	var offset := _up * envelope * _path_arc
	if effect_id in [0, 73]:
		offset += _side * sin(p * TAU * 1.7 + strand * 2.1) * envelope * 0.19 * _path_spread
	elif effect_id == 84:
		offset += _side * sin(p * TAU * 3.0) * envelope * 0.05
	elif effect_id == 85:
		offset += (_side * cos(p*TAU*4+strand*PI) + _up*sin(p*TAU*4+strand*PI))*envelope*0.15
	elif effect_id == 83:
		offset += _side * sin(p*TAU*5+strand*PI)*envelope*0.09
	elif effect_id == 1:
		offset += (_up * envelope * 0.18 + _side * sin(p * TAU + strand * PI) * envelope * 0.16) * _path_spread
	elif effect_id in [10, 86]:
		offset += (_side * cos(p * TAU * 2.0 + strand * 2.1)
			+ _up * sin(p * TAU * 2.0 + strand * 2.1)) * envelope * 0.16 * _path_spread
	else:
		offset += _side * sin(p * TAU * 2.5 + strand * PI) * envelope * 0.035
	return start.lerp(destination, p) + offset

func draw_at(time: float) -> void:
	_mesh.clear_surfaces()
	if _native_mesh != null:
		_native_mesh.clear_surfaces()
	if time >= duration + AFTERGLOW:
		return
	var camera := get_viewport().get_camera_3d()
	var view := camera.global_basis.z.normalized() if camera != null else Vector3(0.3, 0.5, 1).normalized()
	var right := camera.global_basis.x.normalized() if camera != null else Vector3.RIGHT
	var up := view.cross(right).normalized()
	if _native_geometry != null:
		_native_build_attempts += 1
		var magnitude := SpellPresentation.power_scale(power_level)
		var count := SpellPresentation.power_count(18, power_level)
		var built: Variant = _native_geometry.call("build", effect_id, tint, start,
			destination, _side, _up, _path_spread, _path_arc, _tail_fraction,
			duration, time, view, right, up, magnitude, count)
		if _native_output_valid(built, time):
			var native_arrays: Array = built
			if time >= 0.0:
				_commit_native_surface(native_arrays[0], native_arrays[1],
					native_arrays[2], _ribbon_material)
			_commit_native_surface(native_arrays[3], native_arrays[4],
				native_arrays[5], _glow_material)
			_native_build_successes += 1
			return
		_native_build_fallbacks += 1
		_native_geometry = null
		_mesh_node.mesh = _mesh
		_native_mesh = null
	var p := clampf(time / duration, 0.0, 1.0)
	var fade := 1.0 - smoothstep(duration, duration + AFTERGLOW, time)
	var magnitude := SpellPresentation.power_scale(power_level)
	if time >= 0.0:
		_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _ribbon_material)
		for strand: int in (3 if effect_id in [10, 86] else 2):
			# Each strand has its own finite tail; no stationary link spans the actors.
			var head := clampf((time - strand * 0.035) / duration, 0.0, 1.0)
			var tail := maxf(0.0, head - _tail_fraction)
			var previous := point_at(lerpf(tail, head, 0.0), strand)
			for i: int in SEGMENTS:
				var a := float(i) / SEGMENTS
				var b := float(i + 1) / SEGMENTS
				var color := tint.lerp(Color(1.0, 0.91, 0.66), a * 0.42 if effect_id == 2 else a * 0.16)
				color.a = pow(a, 0.7) * fade * (0.85 if strand == 0 else 0.42)
				var width := (0.13 if effect_id == 2 else 0.085) * (0.15 + a * 0.85) * magnitude
				var next := point_at(lerpf(tail, head, b), strand)
				_segment(previous, next, width, color, view)
				previous = next
		_mesh.surface_end()
	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES, _glow_material)
	var head_position := point_at(p)
	var size := (0.25 if effect_id == 2 else 0.19) * magnitude
	if time < 0.0:
		head_position = destination if effect_id in [10, 86] else start
		size *= 0.60 + 0.15 * sin(time * 24.0)
	_glow(head_position, size * 1.8, Color(tint, fade * 0.55), right, up)
	_glow(head_position, size, Color(tint, fade), right, up)
	_glow(head_position, size * 0.40, Color(1.0, 0.96, 0.83, fade), right, up)
	if time >= 0.0:
		var count := SpellPresentation.power_count(18, power_level)
		for i: int in count:
			var age := float(i) / count
			var sample := p - age * 0.42
			if sample <= 0.0:
				continue
			var angle := i * 2.399 + time * 4.0
			var drift := (_side * cos(angle) + _up * sin(angle)) * age * 0.38
			var point := point_at(sample, i % 2) + drift
			var color := tint.lerp(Color(1.0, 0.80, 0.32), 0.45 if effect_id == 2 else 0.0)
			color.a = (1.0 - age) * fade * 0.7
			_glow(point, (0.025 + float(i % 3) * 0.009) * magnitude, color, right, up)
	_mesh.surface_end()

func _native_output_valid(built: Variant, time: float) -> bool:
	if typeof(built) != TYPE_ARRAY:
		return false
	var arrays: Array = built
	if arrays.size() != 6:
		return false
	if (typeof(arrays[0]) != TYPE_PACKED_VECTOR3_ARRAY
			or typeof(arrays[1]) != TYPE_PACKED_COLOR_ARRAY
			or typeof(arrays[2]) != TYPE_PACKED_VECTOR2_ARRAY
			or typeof(arrays[3]) != TYPE_PACKED_VECTOR3_ARRAY
			or typeof(arrays[4]) != TYPE_PACKED_COLOR_ARRAY
			or typeof(arrays[5]) != TYPE_PACKED_VECTOR2_ARRAY):
		return false
	var ribbon_vertices: PackedVector3Array = arrays[0]
	var ribbon_colors: PackedColorArray = arrays[1]
	var ribbon_uvs: PackedVector2Array = arrays[2]
	var glow_vertices: PackedVector3Array = arrays[3]
	var glow_colors: PackedColorArray = arrays[4]
	var glow_uvs: PackedVector2Array = arrays[5]
	var expected_ribbon := (3 if effect_id in [10, 86] else 2) * SEGMENTS * 6 \
		if time >= 0.0 else 0
	return (ribbon_vertices.size() == expected_ribbon
		and ribbon_colors.size() == expected_ribbon
		and ribbon_uvs.size() == expected_ribbon
		and glow_vertices.size() >= 18
		and glow_vertices.size() % 6 == 0
		and glow_colors.size() == glow_vertices.size()
		and glow_uvs.size() == glow_vertices.size())

func _commit_native_surface(vertices: PackedVector3Array,
		colors: PackedColorArray, uvs: PackedVector2Array,
		material: Material) -> void:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_COLOR] = colors
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	_native_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_native_mesh.surface_set_material(_native_mesh.get_surface_count() - 1, material)

func _segment(a: Vector3, b: Vector3, width: float, color: Color, view: Vector3) -> void:
	var side := (b - a).cross(view).normalized() * width * 0.5
	_emit_quad(a-side, a+side, b+side, b-side, color)

func _glow(centre: Vector3, radius: float, color: Color, right: Vector3, up: Vector3) -> void:
	_emit_quad(centre-right*radius-up*radius, centre-right*radius+up*radius,
		centre+right*radius+up*radius, centre+right*radius-up*radius, color)

# Retain the old private helper signature for focused tests and debug callers.
# The hot path passes scalars directly to avoid allocating points/UV/index arrays.
func _quad(points: Array, color: Color) -> void:
	_emit_quad(points[0], points[1], points[2], points[3], color)

func _emit_quad(a: Vector3, b: Vector3, c: Vector3, d: Vector3, color: Color) -> void:
	_mesh.surface_set_color(color)
	_mesh.surface_set_uv(Vector2(0, 0))
	_mesh.surface_add_vertex(a)
	_mesh.surface_set_uv(Vector2(0, 1))
	_mesh.surface_add_vertex(b)
	_mesh.surface_set_uv(Vector2(1, 1))
	_mesh.surface_add_vertex(c)
	_mesh.surface_set_uv(Vector2(0, 0))
	_mesh.surface_add_vertex(a)
	_mesh.surface_set_uv(Vector2(1, 1))
	_mesh.surface_add_vertex(c)
	_mesh.surface_set_uv(Vector2(1, 0))
	_mesh.surface_add_vertex(d)
