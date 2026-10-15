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
var _mesh := ArrayMesh.new()
var _vertices := PackedVector3Array()
var _colors := PackedColorArray()
var _uvs := PackedVector2Array()
var _vertex_cursor := 0
var _ribbon_material: ShaderMaterial
var _glow_material: ShaderMaterial
static var _power_materials: Dictionary = {}

func _init() -> void:
	_set_power_materials(1)
	var node := MeshInstance3D.new()
	node.name = "SpellEnergy"
	node.mesh = _mesh
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)

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
	if time >= duration + AFTERGLOW:
		return
	var camera := get_viewport().get_camera_3d()
	var view := camera.global_basis.z.normalized() if camera != null else Vector3(0.3, 0.5, 1).normalized()
	var right := camera.global_basis.x.normalized() if camera != null else Vector3.RIGHT
	var up := view.cross(right).normalized()
	var p := clampf(time / duration, 0.0, 1.0)
	var fade := 1.0 - smoothstep(duration, duration + AFTERGLOW, time)
	var magnitude := SpellPresentation.power_scale(power_level)
	if time >= 0.0:
		var strands := 3 if effect_id in [10, 86] else 2
		_begin_surface(strands * SEGMENTS * 6)
		for strand: int in strands:
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
		_commit_surface(_ribbon_material)
	var count := SpellPresentation.power_count(18, power_level)
	var trail_quads := 0
	if time >= 0.0:
		for i: int in count:
			var age := float(i) / count
			if p - age * 0.42 > 0.0:
				trail_quads += 1
	_begin_surface((3 + trail_quads) * 6)
	var head_position := point_at(p)
	var size := (0.25 if effect_id == 2 else 0.19) * magnitude
	if time < 0.0:
		head_position = destination if effect_id in [10, 86] else start
		size *= 0.60 + 0.15 * sin(time * 24.0)
	_glow(head_position, size * 1.8, Color(tint, fade * 0.55), right, up)
	_glow(head_position, size, Color(tint, fade), right, up)
	_glow(head_position, size * 0.40, Color(1.0, 0.96, 0.83, fade), right, up)
	if time >= 0.0:
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
	_commit_surface(_glow_material)

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
	var at := _vertex_cursor
	_vertices[at] = a
	_vertices[at + 1] = b
	_vertices[at + 2] = c
	_vertices[at + 3] = a
	_vertices[at + 4] = c
	_vertices[at + 5] = d
	for offset: int in 6:
		_colors[at + offset] = color
	_uvs[at] = Vector2(0, 0)
	_uvs[at + 1] = Vector2(0, 1)
	_uvs[at + 2] = Vector2(1, 1)
	_uvs[at + 3] = Vector2(0, 0)
	_uvs[at + 4] = Vector2(1, 1)
	_uvs[at + 5] = Vector2(1, 0)
	_vertex_cursor += 6

func _begin_surface(vertex_count: int) -> void:
	_vertices.resize(vertex_count)
	_colors.resize(vertex_count)
	_uvs.resize(vertex_count)
	_vertex_cursor = 0

func _commit_surface(material: Material) -> void:
	assert(_vertex_cursor == _vertices.size())
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = _vertices
	arrays[Mesh.ARRAY_COLOR] = _colors
	arrays[Mesh.ARRAY_TEX_UV] = _uvs
	_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_mesh.surface_set_material(_mesh.get_surface_count() - 1, material)
