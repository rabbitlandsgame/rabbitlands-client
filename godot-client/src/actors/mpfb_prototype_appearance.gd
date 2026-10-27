class_name MpfbPrototypeAppearance
extends RefCounted
## Opt-in local prototype finish. MPFB skin/eye UVs are independent of the
## production Human portrait maps. The canonical rig/wardrobe remain; optional
## authored head/hair art is supplied by local study metadata.

const SHADER = preload("res://src/actors/mpfb_prototype_appearance.gdshader")
const HAIR_SHADER = preload("res://src/actors/mpfb_concept_hair.gdshader")
const PRESETS = preload("res://src/actors/human_portrait_presets.gd")
const FACE_FIELDS := ["jaw", "cheekbones", "nose", "face_length", "eye_size", "eye_tilt", "eye_spacing", "nose_width", "lip_fullness", "brow_depth"]
static var _materials: Dictionary = {}
static var _paint_textures: Dictionary = {}

static func _filtered_paint(source: Texture2D) -> Texture2D:
	if source == null: return null
	var key := source.get_instance_id()
	if _paint_textures.has(key): return _paint_textures[key]
	var image := source.get_image()
	if image == null: return source
	if image.has_mipmaps():
		_paint_textures[key] = source
		return source
	# Raw native GLB images do not pass through the editor's mipmap importer.
	# The narrow painted locks need a mip chain to remain stable at distance.
	image.generate_mipmaps()
	var filtered: Texture2D
	if source is ImageTexture:
		# Reinitialize the shared study texture in place instead of retaining a
		# second GPU allocation beside its unmipped source in the GLB cache.
		(source as ImageTexture).set_image(image)
		filtered = source
	else:
		filtered = ImageTexture.create_from_image(image)
	if _paint_textures.size() >= 8: _paint_textures.erase(_paint_textures.keys()[0])
	_paint_textures[key] = filtered
	return filtered

static func configure_art(model: Dictionary, metadata: Dictionary, directory: String) -> void:
	# Local study metadata can supply authored High hair without changing the
	# production registry or the canonical skeleton/equipment contract.
	var hair: Dictionary = metadata.get("concept_hair", {})
	if not hair.is_empty():
		var overrides := {}
		for key: String in hair.get("styles", {}):
			var entry: Dictionary = hair.styles[key].duplicate(true)
			entry.scene = directory.path_join(str(entry.scene))
			entry.skinned = false
			entry.concept = true
			entry.fit = {}
			overrides[key] = entry
		model.hairStyleOverrides = overrides
	model.conceptPortrait = bool(metadata.get("concept_portrait", false))
	model.headMasks = bool(metadata.get("head_masks", false))
	model.headLipBounds = metadata.get("head_lip_uv_bounds", [])
	if metadata.get("head_shape_center") is Dictionary:
		model.headShapeCenter = metadata.head_shape_center.duplicate()

static func supported(config: Dictionary) -> bool:
	return str(config.get("geometryProfile", "")) == "mpfb"

static func shape_appearance(appearance: Dictionary, config: Dictionary) -> Dictionary:
	# The study meshes already include their authored concept targets. Center
	# the matching preset on that shape rather than applying the sculpt twice.
	# Piecewise scaling retains both existing slider endpoints.
	var baseline: Dictionary = config.get("headShapeCenter", PRESETS.shape("Mira" if str(config.get("gender", "")) == "female" else "Rowan"))
	var result := appearance.duplicate()
	for field: String in FACE_FIELDS:
		var center := clampf(float(baseline.get(field, 50)), 1.0, 99.0)
		var value := clampf(float(appearance.get(field, 50)), 0.0, 100.0)
		result[field] = 50.0 * value / center if value <= center else 50.0 + 50.0 * (value - center) / (100.0 - center)
	return result

static func apply(root: Node3D, appearance: Dictionary, config: Dictionary = {}) -> void:
	for part: String in ["body", "eyes"]:
		var mesh := root.find_child(part, true, false) as MeshInstance3D
		if mesh == null or mesh.mesh == null: continue
		mesh.material_override = null
		for surface: int in mesh.mesh.get_surface_count():
			var source := mesh.mesh.surface_get_material(surface) as StandardMaterial3D
			if source == null: continue
			var skin := clampi(int(appearance.get("skin", 0)), 0, 9)
			var eyes := clampi(int(appearance.get("eyes", 0)), 0, 11)
			var concept := bool(config.get("conceptPortrait", false))
			var masks := bool(config.get("headMasks", false)) and part == "body" and surface == 0
			var stubble := masks and int(appearance.get("facial_hair", 0)) == 1
			var lip_box := Vector4.ZERO
			var lip_values: Variant = config.get("headLipBounds", [])
			if masks and lip_values is Array and lip_values.size() == 4:
				lip_box = Vector4(float(lip_values[0]), float(lip_values[1]), float(lip_values[2]), float(lip_values[3]))
			var groom := AppearanceVariants.hair_color(int(appearance.get("hair", 0))) if masks else Color(0.24, 0.10, 0.04)
			if masks and concept and AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))) == 4:
				groom = Color(0.46, 0.15, 0.065)
			var key := "%d:%s:%d:%d:%s:%s:%s:%s:%s" % [source.get_instance_id(), part, skin, eyes, concept, masks, stubble, groom.to_html(), lip_box]
			var material := _materials.get(key) as ShaderMaterial
			if material == null:
				if _materials.size() >= 128: _materials.erase(_materials.keys()[0])
				material = ShaderMaterial.new()
				material.shader = SHADER
				var texture := _filtered_paint(source.albedo_texture) if part == "eyes" or surface == 0 else source.albedo_texture
				material.set_shader_parameter("base_texture", texture)
				material.set_shader_parameter("base_color", source.albedo_color)
				material.set_shader_parameter("is_eye", part == "eyes")
				material.set_shader_parameter("iris_recolor_strength", 0.96 if concept else 0.78)
				material.set_shader_parameter("use_iris_uv_mask", concept)
				var iris_centers := Vector4(0.29280, 0.70102, 0.70606, 0.29541) if str(config.get("gender", "")) == "female" else Vector4(0.29109, 0.70878, 0.70675, 0.29674)
				material.set_shader_parameter("iris_uv_centers", iris_centers)
				material.set_shader_parameter("head_masks_enabled", masks)
				material.set_shader_parameter("stubble_enabled", stubble)
				material.set_shader_parameter("groom_color", groom)
				material.set_shader_parameter("lip_uv_bounds", lip_box)
				material.set_shader_parameter("skin_tint", AppearanceVariants.skin_tint(skin))
				var iris := AppearanceVariants.eye_color(eyes)
				if concept and eyes == 1: iris = Color(0.44, 0.43, 0.22)
				if concept and eyes == 2: iris = Color(0.34, 0.28, 0.20)
				material.set_shader_parameter("eye_tint", iris)
				_materials[key] = material
			mesh.set_surface_override_material(surface, material)
	apply_concept_hair(root, appearance, str(config.get("gender", "")) == "female")

static func apply_concept_hair(root: Node3D, appearance: Dictionary, female: bool) -> void:
	var baseline := PRESETS.shape("Mira" if female else "Rowan")
	var length := (float(appearance.get("hair_length", 50)) - float(baseline.hair_length)) / 50.0
	var volume := (float(appearance.get("hair_volume", 50)) - float(baseline.hair_volume)) / 50.0
	var tint := AppearanceVariants.hair_color(int(appearance.get("hair", 0)))
	if AppearanceVariants.hair_color_index(int(appearance.get("hair", 0))) == 4:
		tint = Color(0.46, 0.15, 0.065)
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var hair := node as MeshInstance3D
		if not hair.has_meta("rl_concept_hair") or hair.mesh == null: continue
		var projected := bool(hair.get_meta("rl_concept_hair_reference", false))
		var textured := bool(hair.get_meta("rl_concept_hair_texture", false))
		var source := hair.mesh.surface_get_material(0) as StandardMaterial3D
		var paint: Texture2D = _filtered_paint(source.albedo_texture) if source != null else null
		var key := "concept_hair:%s:%.4f:%.4f:%s:%s:%s:%d" % [tint.to_html(), length, volume, projected, female, textured, paint.get_instance_id() if paint != null else 0]
		var material := _materials.get(key) as ShaderMaterial
		if material == null:
			material = ShaderMaterial.new()
			material.shader = HAIR_SHADER
			material.set_shader_parameter("hair_color", tint)
			material.set_shader_parameter("use_reference_paint", projected)
			material.set_shader_parameter("use_reference_texture", textured and paint != null)
			material.set_shader_parameter("reference_paint", paint)
			material.set_shader_parameter("paint_reference_color", Color(0.46, 0.15, 0.065) if female else Color(0.24, 0.10, 0.04))
			material.set_shader_parameter("hair_length_delta", length)
			material.set_shader_parameter("hair_volume_delta", volume)
			if _materials.size() >= 128: _materials.erase(_materials.keys()[0])
			_materials[key] = material
		hair.material_override = material
