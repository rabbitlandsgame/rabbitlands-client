extends RefCounted
const PAINT := preload("res://src/world/mineral_appearance.gdshader")
static func apply(model: Node3D, palette: Dictionary) -> void:
	for mesh: MeshInstance3D in model.find_children("*","MeshInstance3D",true,false):
		for surface in range(mesh.mesh.get_surface_count()):
			var original := mesh.get_active_material(surface) as StandardMaterial3D
			if original == null or original.albedo_texture == null: continue
			var material := ShaderMaterial.new()
			material.shader = PAINT
			material.set_shader_parameter("base_texture",original.albedo_texture)
			material.set_shader_parameter("stone_tint",Color.from_string(str(palette.stone),Color.GRAY))
			material.set_shader_parameter("mineral_tint",Color.from_string(str(palette.mineral),Color.WHITE))
			mesh.set_surface_override_material(surface,material)
