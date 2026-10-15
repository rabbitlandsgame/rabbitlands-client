extends SceneTree

const RegionMaterial := preload(
	"res://src/dev/map_authoring_pilot/style/ground_region_material.gd")

var _failures := 0


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_test_forced_zero_shader_and_preserved_pbr()
	_test_independent_parameters_and_shared_shader()
	_test_custom_material_fails_closed()
	print("map authoring ground region material: ",
		"PASS" if _failures == 0 else "FAIL (%d)" % _failures)
	quit(_failures)


func _test_forced_zero_shader_and_preserved_pbr() -> void:
	var surface := MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.SOIL)
	var source := surface.source_material as ORMMaterial3D
	var transform := Transform2D(-0.31, Vector2(8.0, -5.0)).affine_inverse()
	var region := RegionMaterial.create(surface, transform, Vector2(6.0, 3.0),
		RegionMaterial.ELLIPSE, 1.25, 0.72, 4)
	_expect(region != null and region != source,
		"zero rotation is forced through an independent region shader")
	_expect(region.get_shader_parameter("albedo_map") == source.albedo_texture and
		region.get_shader_parameter("normal_map") == source.normal_texture and
		region.get_shader_parameter("orm_map") == source.orm_texture and
		region.get_shader_parameter("albedo_tint") == source.albedo_color and
		region.get_shader_parameter("normal_strength") == source.normal_scale,
		"region conversion preserves albedo, normal, ORM, tint, and strength")
	_expect(is_zero_approx(float(region.get_shader_parameter(
		"texture_rotation_radians"))) and
		MapAuthoringTexturePresets._ORIENTED_PBR_SHADER.code.find("ALPHA =") < 0,
		"zero stays visually unrotated and the owned base shader stays opaque")
	_expect(region.shader.code.find("region_world_xz") >= 0 and
		region.shader.code.find("discard") >= 0 and
		region.shader.code.find("ALPHA = clamp") >= 0,
		"only the region variant contains the soft transparent footprint")
	var owned_crlf := MapAuthoringTexturePresets._ORIENTED_PBR_SHADER.code.replace(
		"\n", "\r\n")
	var crlf_region_code: String = RegionMaterial._region_code(owned_crlf)
	var crlf_shader := Shader.new()
	crlf_shader.code = owned_crlf
	var crlf_variant: Shader = RegionMaterial._region_shader(crlf_shader)
	var lf_shader := Shader.new()
	lf_shader.code = MapAuthoringTexturePresets._ORIENTED_PBR_SHADER.code
	var lf_variant: Shader = RegionMaterial._region_shader(lf_shader)
	_expect(not crlf_region_code.is_empty() and crlf_variant != null and
		crlf_variant == lf_variant and
		crlf_region_code.find("region_world_xz") >= 0 and
		crlf_region_code.find("ALPHA = clamp") >= 0,
		"CRLF owned source uses the production hooks and normalized LF shader cache")


func _test_independent_parameters_and_shared_shader() -> void:
	var surface := MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.SAND)
	surface.rotation_degrees = 37.0
	var first := RegionMaterial.create(surface, Transform2D.IDENTITY,
		Vector2(4.0, 2.0), RegionMaterial.RECTANGLE, 0.5, 0.8, 2)
	var second_transform := Transform2D(0.4, Vector2(-9.0, 3.0)).affine_inverse()
	var second := RegionMaterial.create(surface, second_transform,
		Vector2(9.0, 5.0), RegionMaterial.ELLIPSE, 2.0, 0.35, 7)
	_expect(first != second and first.shader == second.shader,
		"region materials are independent while identical base code is shared")
	_expect(first.get_shader_parameter("region_half_size") == Vector2(4.0, 2.0) and
		second.get_shader_parameter("region_half_size") == Vector2(9.0, 5.0) and
		is_equal_approx(float(second.get_shader_parameter("region_opacity")), 0.35) and
		second.render_priority == 7,
		"each region keeps its own size, opacity, and draw priority")
	_expect(is_equal_approx(rad_to_deg(float(first.get_shader_parameter(
		"texture_rotation_radians"))), 37.0),
		"surface texture rotation reaches the region PBR shader")
	var x_row: Vector3 = second.get_shader_parameter("region_world_to_local_x")
	var y_row: Vector3 = second.get_shader_parameter("region_world_to_local_y")
	var world_probe := Vector2(2.5, -4.0)
	var shader_local := Vector2(x_row.dot(Vector3(world_probe.x, world_probe.y, 1.0)),
		y_row.dot(Vector3(world_probe.x, world_probe.y, 1.0)))
	_expect(shader_local.is_equal_approx(second_transform * world_probe),
		"the two shader rows reproduce the authored world-to-local transform")


func _test_custom_material_fails_closed() -> void:
	var custom := ShaderMaterial.new()
	custom.shader = Shader.new()
	custom.shader.code = "shader_type spatial; void fragment(){ EMISSION=vec3(1.0); }"
	var surface := MapAuthoringSurface.from_material(custom)
	_expect(RegionMaterial.create(surface, Transform2D.IDENTITY, Vector2.ONE,
		RegionMaterial.ELLIPSE, 0.2, 1.0, 0) == null and
		surface.source_material is ShaderMaterial,
		"unknown custom shaders fail closed without replacing their source")
	var preset := MapAuthoringSurface.from_preset(MapAuthoringTexturePresets.GRASS)
	var singular := Transform2D(Vector2.ZERO, Vector2.ZERO, Vector2.ZERO)
	_expect(RegionMaterial.create(preset, singular, Vector2.ONE,
		RegionMaterial.ELLIPSE, 0.2, 1.0, 0) == null and
		RegionMaterial.create(preset, Transform2D.IDENTITY, Vector2(0.0, 2.0),
		RegionMaterial.RECTANGLE, 0.2, 1.0, 0) == null,
		"singular transforms and invalid footprint sizes fail closed")


func _expect(condition: bool, message: String) -> bool:
	if condition:
		print("PASS: ", message)
		return true
	_failures += 1
	push_error("FAIL: " + message)
	return false
