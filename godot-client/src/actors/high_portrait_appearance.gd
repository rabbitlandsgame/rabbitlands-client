class_name HighPortraitAppearance
extends RefCounted
## Optional Human portrait artwork. Low/Medium return before loading any High
## image or creating a derivative mesh. Geometry/skin/animations stay exact.
const HIGH := 2
const SHADER := preload("res://src/actors/high_portrait_appearance.gdshader")
const COMPACTOR := preload("res://src/actors/character_proportions.gd")
const LODS := preload("res://src/actors/wardrobe_shirt_fit.gd")
const META := &"rl_high_portrait"
const USER_META := &"rl_high_portrait_user"
const EXIT_META := &"rl_high_portrait_exit_hook"
const CACHE_LIMIT := 24
const PARTS := ["body", "eyes", "eyebrows", "scalp"]
static var _meshes: Dictionary = {}
static var _bundles: Dictionary = {}
static var _users: Dictionary = {}

static func apply(native_root: Node3D, skeleton: Skeleton3D,
		_appearance: Dictionary, model_config: Dictionary, level: int) -> void:
	if not is_instance_valid(native_root):
		return
	if level != HIGH or not _supported(model_config) or not is_instance_valid(skeleton):
		if native_root.has_meta(USER_META):
			release(native_root)
		return
	var sex := str(model_config.get("gender", ""))
	var bundle := _bundle(sex)
	if bundle.is_empty():
		release(native_root)
		return
	var head := skeleton.find_bone("Head")
	if head < 0:
		return
	_users[native_root.get_instance_id()] = weakref(native_root)
	native_root.set_meta(USER_META, sex)
	if not native_root.has_meta(EXIT_META):
		native_root.tree_exiting.connect(func() -> void: release(native_root), CONNECT_ONE_SHOT)
		native_root.set_meta(EXIT_META, true)
	var to_head := skeleton.get_bone_global_rest(head).affine_inverse() * _to_root(skeleton, native_root).affine_inverse()
	var projection: Dictionary = bundle.descriptor.projection
	for part: String in PARTS:
		var node := native_root.find_child(part, true, false) as MeshInstance3D
		if node == null or node.mesh == null:
			continue
		var previous: Dictionary = node.get_meta(META, {})
		var source := node.mesh
		var original_override := node.material_override
		var originals: Array[Material] = []
		if not previous.is_empty() and node.mesh == previous.result:
			source = previous.source
			original_override = previous.override
			originals.assign(previous.surfaces)
		else:
			for surface: int in source.get_surface_count():
				originals.append(node.get_surface_override_material(surface))
		var transform := to_head * _to_root(node, native_root)
		var key := "%d:%s" % [source.get_instance_id(), transform]
		var result := _meshes.get(key) as ArrayMesh
		if result == null:
			result = _project_mesh(source, transform, projection)
			if _meshes.size() >= CACHE_LIMIT:
				_meshes.erase(_meshes.keys()[0])
			_meshes[key] = result
		var active := original_override as ShaderMaterial
		if active == null and not originals.is_empty():
			active = originals[0] as ShaderMaterial
		if active == null:
			continue
		var material := ShaderMaterial.new()
		material.shader = SHADER
		var uniforms: Dictionary = {}
		for value: Dictionary in SHADER.get_shader_uniform_list():
			uniforms[str(value.name)] = true
		for value: Dictionary in active.shader.get_shader_uniform_list():
			var name := str(value.name)
			if uniforms.has(name):
				var data: Variant = active.get_shader_parameter(name)
				if data != null:
					material.set_shader_parameter(name, data)
		material.set_shader_parameter("portrait_paint", bundle.paint)
		material.set_shader_parameter("portrait_regions", bundle.regions)
		material.set_shader_parameter("portrait_normal", bundle.normal)
		node.material_override = material
		node.mesh = result
		node.set_meta(META, {"source": source, "result": result, "override": original_override,
			"surfaces": originals, "material": material})
	_prune_users()

static func restore(native_root: Node3D) -> void:
	if not is_instance_valid(native_root):
		return
	for part: String in PARTS:
		var node := native_root.find_child(part, true, false) as MeshInstance3D
		if node == null or not node.has_meta(META):
			continue
		var previous: Dictionary = node.get_meta(META)
		if node.mesh == previous.result:
			node.mesh = previous.source as Mesh
		if node.material_override == previous.material:
			node.material_override = previous.override as Material
		var surfaces: Array = previous.surfaces
		for surface: int in mini(surfaces.size(), node.mesh.get_surface_count()):
			if node.get_surface_override_material(surface) == previous.material:
				node.set_surface_override_material(surface, surfaces[surface] as Material)
		node.remove_meta(META)

static func release(native_root: Node3D) -> void:
	if is_instance_valid(native_root):
		restore(native_root)
		native_root.remove_meta(USER_META)
		_users.erase(native_root.get_instance_id())
	_prune_users()

static func clear() -> void:
	for reference: WeakRef in _users.values():
		var node := reference.get_ref() as Node3D
		if is_instance_valid(node):
			restore(node)
			node.remove_meta(USER_META)
	_users.clear()
	_bundles.clear()
	_meshes.clear()

static func cache_metrics() -> Dictionary:
	var bytes := 0
	for mesh: Mesh in _meshes.values():
		for surface: int in mesh.get_surface_count():
			for attribute: Variant in mesh.surface_get_arrays(surface):
				if attribute != null:
					bytes += attribute.to_byte_array().size()
	return {"mesh_entries": _meshes.size(), "texture_bundles": _bundles.size(), "high_users": _users.size(),
		"array_bytes": bytes, "compressed_texture_bytes": _bundles.size() * 4194384}

static func _bundle(sex: String) -> Dictionary:
	if _bundles.has(sex):
		return _bundles[sex]
	var path := "res://data/actors/portraits_high/%s.json" % sex
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if parsed is not Dictionary:
		return {}
	var descriptor := parsed as Dictionary
	var result: Dictionary = {"descriptor": descriptor}
	for name: String in ["paint", "regions", "normal"]:
		var texture := load(str(descriptor.textures[name])) as Texture2D
		if texture == null:
			return {}
		result[name] = texture
	_bundles[sex] = result
	return result

static func _prune_users() -> void:
	var needed: Dictionary = {}
	for id: int in _users.keys():
		var node := (_users[id] as WeakRef).get_ref() as Node3D
		if not is_instance_valid(node) or not node.has_meta(USER_META):
			_users.erase(id)
		else:
			needed[str(node.get_meta(USER_META))] = true
	for sex: String in _bundles.keys():
		if not needed.has(sex):
			_bundles.erase(sex)
	if _users.is_empty():
		_meshes.clear()

static func _supported(config: Dictionary) -> bool:
	return str(config.get("culture", "")) == "luminous" and str(config.get("bodyTemplate", "")) in ["luminous_male", "luminous_female"]

static func _project_mesh(source: Mesh, to_head: Transform3D, projection: Dictionary) -> ArrayMesh:
	var result := ArrayMesh.new()
	for blend: int in source.get_blend_shape_count():
		result.add_blend_shape(source.get_blend_shape_name(blend))
	if source is ArrayMesh:
		result.blend_shape_mode = (source as ArrayMesh).blend_shape_mode
	for surface: int in source.get_surface_count():
		var arrays := source.surface_get_arrays(surface)
		var blends := source.surface_get_blend_shape_arrays(surface)
		var lods := LODS._surface_lods(source, surface)
		COMPACTOR.compact(arrays, blends, lods)
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var uv := PackedVector2Array()
		var colors := PackedColorArray()
		uv.resize(points.size())
		colors.resize(points.size())
		for index: int in points.size():
			var p := to_head * points[index]
			uv[index] = Vector2((p.x - float(projection.x_min)) / (float(projection.x_max) - float(projection.x_min)),
				(float(projection.y_max) - p.y) / (float(projection.y_max) - float(projection.y_min)))
			var mask := smoothstep(-0.065, -0.030, p.y) * (1.0 - smoothstep(0.180, 0.202, p.y))
			mask *= 1.0 - smoothstep(0.067, 0.091, absf(p.x))
			mask *= smoothstep(-0.020, 0.014, p.z)
			colors[index] = Color(mask, 0, 0, 1)
		arrays[Mesh.ARRAY_TEX_UV2] = uv
		arrays[Mesh.ARRAY_COLOR] = colors
		result.add_surface_from_arrays(source.surface_get_primitive_type(surface), arrays, blends, lods,
			source.surface_get_format(surface) & Mesh.ARRAY_FLAG_USE_8_BONE_WEIGHTS)
		result.surface_set_material(surface, source.surface_get_material(surface))
		result.surface_set_name(surface, source.surface_get_name(surface))
	return result

static func _to_root(node: Node3D, root: Node3D) -> Transform3D:
	var result := Transform3D.IDENTITY
	var cursor: Node = node
	while cursor != root and cursor != null:
		if cursor is Node3D:
			result = (cursor as Node3D).transform * result
		cursor = cursor.get_parent()
	return result
