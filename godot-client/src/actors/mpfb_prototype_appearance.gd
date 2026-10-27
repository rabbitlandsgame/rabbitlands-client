class_name MpfbPrototypeAppearance
extends RefCounted
## Opt-in local prototype finish. MPFB skin/eye UVs are independent of the
## production Human portrait maps; the existing rig, wardrobe and hair remain.

const SHADER = preload("res://src/actors/mpfb_prototype_appearance.gdshader")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const FACE_FIELDS := ["jaw", "cheekbones", "nose", "face_length", "eye_size", "eye_tilt", "eye_spacing", "nose_width", "lip_fullness", "brow_depth"]
static var _materials: Dictionary = {}

static func supported(config: Dictionary) -> bool:
	return str(config.get("geometryProfile", "")) == "mpfb"

static func shape_appearance(appearance: Dictionary, config: Dictionary) -> Dictionary:
	# The study meshes already include their authored concept targets. Center
	# the matching preset on that shape rather than applying the sculpt twice.
	# Piecewise scaling retains both existing slider endpoints.
	var baseline := PRESETS.shape("Mira" if str(config.get("gender", "")) == "female" else "Rowan")
	var result := appearance.duplicate()
	for field: String in FACE_FIELDS:
		var center := clampf(float(baseline.get(field, 50)), 1.0, 99.0)
		var value := clampf(float(appearance.get(field, 50)), 0.0, 100.0)
		result[field] = 50.0 * value / center if value <= center else 50.0 + 50.0 * (value - center) / (100.0 - center)
	return result

static func apply(root: Node3D, appearance: Dictionary) -> void:
	for part: String in ["body", "eyes"]:
		var mesh := root.find_child(part, true, false) as MeshInstance3D
		if mesh == null or mesh.mesh == null: continue
		mesh.material_override = null
		for surface: int in mesh.mesh.get_surface_count():
			var source := mesh.mesh.surface_get_material(surface) as StandardMaterial3D
			if source == null: continue
			var skin := clampi(int(appearance.get("skin", 0)), 0, 9)
			var eyes := clampi(int(appearance.get("eyes", 0)), 0, 7)
			var key := "%d:%s:%d:%d" % [source.get_instance_id(), part, skin, eyes]
			var material := _materials.get(key) as ShaderMaterial
			if material == null:
				if _materials.size() >= 128: _materials.erase(_materials.keys()[0])
				material = ShaderMaterial.new()
				material.shader = SHADER
				material.set_shader_parameter("base_texture", source.albedo_texture)
				material.set_shader_parameter("base_color", source.albedo_color)
				material.set_shader_parameter("is_eye", part == "eyes")
				material.set_shader_parameter("skin_tint", AppearanceVariants.skin_tint(skin))
				material.set_shader_parameter("eye_tint", AppearanceVariants.eye_color(eyes))
				_materials[key] = material
			mesh.set_surface_override_material(surface, material)
