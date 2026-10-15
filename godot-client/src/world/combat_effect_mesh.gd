class_name CombatEffectMesh
extends RefCounted
## Thin, layered geometry stays legible in Compatibility without bloom.
static func material() -> StandardMaterial3D:
	var result := StandardMaterial3D.new()
	result.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	result.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	result.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	result.vertex_color_use_as_albedo = true
	result.cull_mode = BaseMaterial3D.CULL_DISABLED
	result.no_depth_test = false
	return result

static func line(mesh: ImmediateMesh, a: Vector3, b: Vector3, width: float,
		color: Color, normal := Vector3.UP) -> void:
	var side := (b - a).cross(normal).normalized() * width * 0.5
	if side.length_squared() < 0.0000001:
		side = Vector3.RIGHT * width * 0.5
	mesh.surface_set_color(color)
	var a_minus := a - side
	var a_plus := a + side
	var b_plus := b + side
	var b_minus := b - side
	mesh.surface_add_vertex(a_minus)
	mesh.surface_add_vertex(a_plus)
	mesh.surface_add_vertex(b_plus)
	mesh.surface_add_vertex(a_minus)
	mesh.surface_add_vertex(b_plus)
	mesh.surface_add_vertex(b_minus)

static func arc(mesh: ImmediateMesh, centre: Vector3, radius: float, width: float,
		color: Color, start := 0.0, sweep := TAU, basis := Basis.IDENTITY) -> void:
	var steps := maxi(3, ceili(absf(sweep) * 12.0))
	var angle := start + sweep * float(0) / steps
	var previous := centre + basis * Vector3(cos(angle), 0, sin(angle)) * radius
	for step: int in steps:
		angle = start + sweep * float(step + 1) / steps
		var next := centre + basis * Vector3(cos(angle), 0, sin(angle)) * radius
		line(mesh, previous, next, width, color, basis.y)
		previous = next

static func spark(mesh: ImmediateMesh, centre: Vector3, size: float, color: Color) -> void:
	mesh.surface_set_color(color)
	var up := centre + Vector3.UP * size
	var down := centre - Vector3.UP * size
	var right := Vector3.RIGHT * size * 0.38
	mesh.surface_add_vertex(up)
	mesh.surface_add_vertex(centre + right)
	mesh.surface_add_vertex(down)
	mesh.surface_add_vertex(up)
	mesh.surface_add_vertex(down)
	mesh.surface_add_vertex(centre - right)
	var forward := Vector3.FORWARD * size * 0.38
	mesh.surface_add_vertex(up)
	mesh.surface_add_vertex(centre + forward)
	mesh.surface_add_vertex(down)
	mesh.surface_add_vertex(up)
	mesh.surface_add_vertex(down)
	mesh.surface_add_vertex(centre - forward)
