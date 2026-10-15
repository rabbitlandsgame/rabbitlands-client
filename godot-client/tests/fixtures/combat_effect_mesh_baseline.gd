# FROZEN REFERENCE: do not optimize this test fixture.
# Source: res://src/world/combat_effect_mesh.gd at commit 4c42ab09f12844d5b9e370619c9be93b4f48033f.
# Normalized source-body SHA-256: 71628e85617c03a6949a74fe500ef29c0cd1860191f0f4fe83c740f33112d3a6.

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
	for point: Vector3 in [a-side, a+side, b+side, a-side, b+side, b-side]:
		mesh.surface_add_vertex(point)

static func arc(mesh: ImmediateMesh, centre: Vector3, radius: float, width: float,
		color: Color, start := 0.0, sweep := TAU, basis := Basis.IDENTITY) -> void:
	var steps := maxi(3, ceili(absf(sweep) * 12.0))
	for step: int in steps:
		var a := start + sweep * float(step) / steps
		var b := start + sweep * float(step + 1) / steps
		line(mesh, centre + basis * Vector3(cos(a), 0, sin(a)) * radius,
			centre + basis * Vector3(cos(b), 0, sin(b)) * radius,
			width, color, basis.y)

static func spark(mesh: ImmediateMesh, centre: Vector3, size: float, color: Color) -> void:
	mesh.surface_set_color(color)
	for axis: Vector3 in [Vector3.RIGHT, Vector3.FORWARD]:
		for point: Vector3 in [centre + Vector3.UP * size, centre + axis * size * 0.38,
			centre - Vector3.UP * size, centre + Vector3.UP * size,
			centre - Vector3.UP * size, centre - axis * size * 0.38]:
			mesh.surface_add_vertex(point)
