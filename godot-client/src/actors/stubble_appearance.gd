class_name StubbleAppearance
extends RefCounted

static var _textures: Dictionary = {}

static func apply(root: Node3D, appearance: Dictionary, config: Dictionary) -> void:
	if root == null:
		return
	var human := str(config.get("culture", "")) == "luminous" and str(config.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]
	var enabled := human and int(appearance.get("facial_hair", 0)) == 1
	var texture: Texture2D
	if enabled:
		var sex := str(config.get("gender", "female"))
		if not _textures.has(sex):
			_textures[sex] = load("res://data/actors/grooming/stubble_%s.png" % sex)
		texture = _textures[sex] as Texture2D
	var seen := {}
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := node as MeshInstance3D
		if mesh.mesh == null:
			continue
		for surface: int in mesh.mesh.get_surface_count():
			var material := mesh.get_active_material(surface) as ShaderMaterial
			if material == null or material.shader == null or not material.shader.code.contains("stubble_pigment.gdshaderinc") or seen.has(material.get_instance_id()):
				continue
			seen[material.get_instance_id()] = true
			material.set_shader_parameter("stubble_enabled", enabled)
			if enabled:
				material.set_shader_parameter("stubble_mask", texture)
				material.set_shader_parameter("stubble_color", AppearanceVariants.hair_color(int(appearance.get("hair", 0))))

static func clear() -> void:
	_textures.clear()
