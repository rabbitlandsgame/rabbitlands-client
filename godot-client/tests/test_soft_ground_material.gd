extends SceneTree

func _init() -> void:
	var loader := WorldLoader.new()
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.FORWARD])
	arrays[Mesh.ARRAY_COLOR] = PackedColorArray([Color(1,1,1,0), Color(1,1,1,.5), Color.WHITE])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var soft := StandardMaterial3D.new()
	soft.resource_name = "steppe_dust_soft_ground"
	soft.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mesh.surface_set_material(0,soft)
	var node := MeshInstance3D.new()
	node.mesh = mesh
	var count: int = loader._apply_material_passes([node])
	assert(count == 1)
	var replacement := mesh.surface_get_material(0) as ShaderMaterial
	assert(replacement != null)
	assert(replacement.shader.code.contains("discard;"))
	assert(not replacement.shader.code.contains("ALPHA ="))
	assert(replacement.get_shader_parameter("soil_roughness") == soft.roughness)
	var ordinary := StandardMaterial3D.new()
	ordinary.resource_name = "water_lake"
	ordinary.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mesh.surface_set_material(0,ordinary)
	loader._apply_material_passes([node])
	assert(ordinary.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA)
	assert(not ordinary.vertex_color_use_as_albedo)
	var continental := StandardMaterial3D.new()
	continental.resource_name = "continental_ground"
	mesh.surface_set_material(0,continental)
	loader.manifest = WorldManifest.new()
	loader.manifest.data = {"continentGeography":{"geometryMode":"continent-chunks-v1"}}
	loader._apply_material_passes([node])
	assert(continental.vertex_color_use_as_albedo)
	assert(continental.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED)
	node.free()
	loader.free()
	print("soft ground material: PASS")
	quit()
