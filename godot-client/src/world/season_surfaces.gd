extends RefCounted
## Seasonal copies of outdoor scenery materials, independent of appearance mode.
## Original meshes, textures and cached map scenes remain the source of truth.

const META := &"rl_season_surface"
const SOURCE_META := &"rl_season_source"
const STAMP_META := &"rl_season_surfaces_generation"
const INCLUDE := "res://src/world/season_surface.gdshaderinc"
const STANDARD := "shader_type spatial;\nrender_mode %s;\n#define LOOK_STANDARD_RESTING\n" \
	+ "#include \"res://src/world/look/look_faded_standard.gdshaderinc\"\n"
enum Kind { NONE = -1, GROUND, LEAVES, EVERGREEN, SHRUB, ROOF }
const WARM_REGIONS := ["amethyst_barrens", "verdant_stair", "verdant_reach",
	"ssarathi_ruins", "manymouth_delta", "cinder_wastes", "sw_isle"]
const EVERGREEN_WORDS := ["pine", "fir", "spruce", "cedar", "cypress", "palm", "juniper"]
const TREE_WORDS := ["tree", "oak", "maple", "birch", "willow", "beech", "elm", "sapling"]

static var _season := -1
static var _materials: Dictionary = {} # Weak caches must not keep retired chunks alive.
static var _shaders: Dictionary = {}
static var _binds := 0

static func set_season(season: Dictionary) -> bool:
	var index := int(season.get("index", -1))
	if index < -1 or index > 3:
		index = -1
	if index == _season:
		return false
	_season = index
	for key: String in _materials.keys():
		var material: ShaderMaterial = (_materials[key] as WeakRef).get_ref() as ShaderMaterial
		if material == null:
			_materials.erase(key)
		else:
			material.set_shader_parameter(&"rl_season", float(index))
	return true

static func current_season() -> int:
	return _season

static func snow_cover(manifest: WorldManifest) -> float:
	if manifest == null or not DayNightBinder.drives(manifest):
		return 0.0
	var settings: Dictionary = (manifest.data.get("environment", {}) as Dictionary).get("seasons", {}) as Dictionary
	if settings.has("snowCover"):
		return clampf(float(settings.snowCover), 0.0, 1.0)
	var region := LookGround.region_of(manifest)
	if region in WARM_REGIONS:
		return 0.0
	return 0.45 if region in ["sunmane_steppe", "spindle_hill", "tollholm"] else 1.0

static func apply(root: Node, manifest: WorldManifest, force := false) -> int:
	if root == null or manifest == null or not DayNightBinder.drives(manifest) or _season < 0:
		return 0
	var generation := LookProfile.switch_generation()
	if not force and int(root.get_meta(STAMP_META, -1)) == generation:
		return 0
	_binds += 1
	if _binds % 32 == 0:
		for key: String in _materials.keys():
			if (_materials[key] as WeakRef).get_ref() == null:
				_materials.erase(key)
	var changed := 0
	var region := LookGround.region_of(manifest)
	var snow := snow_cover(manifest)
	var foliage := 0.0 if region in WARM_REGIONS else 1.0
	var nodes: Array[Node] = root.find_children("*", "MeshInstance3D", true, false)
	if root is MeshInstance3D:
		nodes.push_front(root)
	for node: Node in nodes:
		var mesh_node := node as MeshInstance3D
		if mesh_node.mesh == null:
			continue
		var label := _label(mesh_node, root)
		for surface: int in mesh_node.mesh.get_surface_count():
			var source: Material = mesh_node.get_active_material(surface)
			if source == null or source.has_meta(META):
				continue
			var kind := kind_of(label, source, region)
			if kind == Kind.NONE:
				continue
			var seasonal := material_for(source, kind, mesh_node.mesh, snow, foliage)
			if seasonal == null:
				continue
			if mesh_node.material_override != null:
				mesh_node.material_override = seasonal
			else:
				mesh_node.set_surface_override_material(surface, seasonal)
			# A hidden batch member needs the same seasonal surface when lifted
			# out for camera fading; the MultiMesh draws it the rest of the time.
			var batch: Variant = mesh_node.get_meta(LookFoliage.BATCH_META) \
				if mesh_node.has_meta(LookFoliage.BATCH_META) else null
			if batch is MultiMeshInstance3D and mesh_node.mesh.get_surface_count() == 1:
				var batch_source: Material = batch.material_override
				if batch_source == null:
					batch_source = source
				if not batch_source.has_meta(META):
					batch.material_override = material_for(batch_source, kind, mesh_node.mesh, snow, foliage)
			changed += 1
	root.set_meta(STAMP_META, generation)
	return changed

static func _label(node: Node, root: Node) -> String:
	var label := String(node.name)
	var parent := node.get_parent()
	# Imported kit meshes sometimes keep their species on the parent wrapper.
	for _level: int in range(2):
		if parent == null or parent == root:
			break
		label += " " + String(parent.name)
		parent = parent.get_parent()
	return label.to_lower()

static func kind_of(label: String, source: Material, region := "") -> Kind:
	label = label.to_lower()
	var original := source
	while original != null and original.has_meta(LookProfile.SOURCE_META):
		original = original.get_meta(LookProfile.SOURCE_META) as Material
	var name := original.resource_name.to_lower() if original != null else ""
	if label.contains("water_") or label.contains("scenery_water") or LookGround.water_named(name):
		return Kind.NONE
	if label.contains("terrain_") or label.contains("authoredground_") or label.contains("walk_") \
			or LookGround.is_kit_paving(label, region):
		return Kind.GROUND
	if label.contains("_wood") or name.begins_with("bark_"):
		return Kind.NONE
	if (label.contains("flower") or label.contains("blossom")) \
			and not label.contains("tree") and not label.contains("_canopy"):
		return Kind.NONE
	for word: String in EVERGREEN_WORDS:
		if label.contains(word):
			return Kind.EVERGREEN
	if name in LookProfile.CROWN_MATERIALS or label.contains("_canopy"):
		return Kind.LEAVES
	if label.contains("kit-"):
		for word: String in TREE_WORDS:
			if label.contains(word):
				return Kind.LEAVES
		for word: String in LookProfile.KIT_SHRUB_WORDS:
			if label.contains(word) and not label.contains("raft") and not label.contains("basket"):
				return Kind.SHRUB
	if label.contains("roof") and not label.contains("interior"):
		return Kind.ROOF
	return Kind.NONE

static func material_for(source: Material, kind: Kind, mesh: Mesh, snow: float,
		foliage := 1.0) -> ShaderMaterial:
	if source == null or mesh == null:
		return null
	if source.has_meta(META):
		return source as ShaderMaterial
	var key := "%d:%d:%d:%.2f:%.2f" % [source.get_instance_id(), mesh.get_instance_id(), kind, snow, foliage]
	if _materials.has(key):
		var cached := (_materials[key] as WeakRef).get_ref() as ShaderMaterial
		if cached != null:
			return cached
	var result: ShaderMaterial
	var native := source as BaseMaterial3D
	if native != null:
		if not LookFade.reproduces(native):
			return null
		var cull := "cull_disabled" if native.cull_mode == BaseMaterial3D.CULL_DISABLED else "cull_back"
		var base_shader := Shader.new()
		base_shader.code = STANDARD % cull
		result = ShaderMaterial.new()
		result.shader = _shader(base_shader, "standard:" + cull)
		LookFade.copy_standard_surface(native, result)
		result.set_shader_parameter(&"use_vertex_albedo", native.vertex_color_use_as_albedo)
		result.set_shader_parameter(&"vertex_albedo_srgb", native.vertex_color_is_srgb)
		result.set_shader_parameter(&"alpha_mode", 0 if native.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED \
			else 1 if native.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR else 2)
		result.set_shader_parameter(&"alpha_scissor_threshold", native.alpha_scissor_threshold)
		var faded := Shader.new()
		faded.code = (STANDARD % cull).replace("#define LOOK_STANDARD_RESTING", "")
		result.set_meta(LookFade.FADED_SHADER_META, _shader(faded, "standard_faded:" + cull))
	elif source is ShaderMaterial:
		var shader_source := source as ShaderMaterial
		if shader_source.shader == null:
			return null
		result = shader_source.duplicate() as ShaderMaterial
		result.shader = _shader(shader_source.shader)
		if source.has_meta(LookFade.FADED_SHADER_META):
			result.set_meta(LookFade.FADED_SHADER_META, _shader(source.get_meta(LookFade.FADED_SHADER_META) as Shader))
	else:
		return null
	if result.shader == null:
		return null
	result.resource_name = source.resource_name
	result.render_priority = source.render_priority
	result.next_pass = source.next_pass
	result.set_meta(META, true)
	result.set_meta(SOURCE_META, source)
	result.set_meta(LookProfile.SOURCE_META, source)
	var box := mesh.get_aabb()
	var original := source
	while original.has_meta(LookProfile.SOURCE_META):
		original = original.get_meta(LookProfile.SOURCE_META) as Material
	var whole_crown := original.resource_name.to_lower() in LookProfile.CROWN_MATERIALS
	result.set_shader_parameter(&"rl_season", float(_season))
	result.set_shader_parameter(&"rl_kind", int(kind))
	result.set_shader_parameter(&"rl_snow", snow)
	result.set_shader_parameter(&"rl_foliage", foliage)
	result.set_shader_parameter(&"rl_mixed_crown", not whole_crown)
	result.set_shader_parameter(&"rl_height", Vector2(box.position.y, maxf(box.size.y, 0.01)))
	result.set_shader_parameter(&"rl_seed", float(posmod(source.resource_name.hash(), 997)) / 997.0)
	_materials[key] = weakref(result)
	return result

static func _shader(source: Shader, cache_key := "") -> Shader:
	if source == null:
		return null
	var key := cache_key if not cache_key.is_empty() else str(source.get_instance_id())
	if _shaders.has(key):
		return _shaders[key] as Shader
	var code := _expand(source.code)
	var header_end := code.find(";", code.find("render_mode"))
	if header_end < 0:
		header_end = code.find(";")
	code = code.insert(header_end + 1, "\n" + FileAccess.get_file_as_string(INCLUDE) + "\n")
	code = _append_function(code, "vertex", "\nrl_position = VERTEX;\n" \
		+ "rl_up = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz).y;\n")
	code = _append_function(code, "fragment", "\nrl_apply(ALBEDO, ROUGHNESS, METALLIC);\n")
	if code.is_empty():
		push_warning("seasons: unsupported scenery shader left unchanged")
		return null
	var result := Shader.new()
	result.code = code
	_shaders[key] = result
	return result

static func _expand(code: String) -> String:
	var pattern := RegEx.create_from_string("(?m)^\\s*#include\\s+\"([^\"]+)\"")
	for _depth: int in range(12):
		var matches := pattern.search_all(code)
		if matches.is_empty():
			return code
		matches.reverse()
		for found: RegExMatch in matches:
			var body := FileAccess.get_file_as_string(found.get_string(1))
			code = code.substr(0, found.get_start()) + body + code.substr(found.get_end())
	return code

static func _append_function(code: String, function: String, body: String) -> String:
	var signature := RegEx.create_from_string("void\\s+" + function + "\\s*\\([^)]*\\)\\s*\\{").search(code)
	if signature == null:
		return code + "\nvoid " + function + "() {\n" + body + "}\n"
	# Ignore braces in comments while keeping offsets into the original code.
	var masked := code
	var comments := RegEx.create_from_string("(?s)/\\*.*?\\*/|//[^\\n]*").search_all(code)
	comments.reverse()
	for found: RegExMatch in comments:
		masked = masked.substr(0, found.get_start()) + " ".repeat(found.get_end() - found.get_start()) + masked.substr(found.get_end())
	var depth := 1
	for offset: int in range(signature.get_end(), code.length()):
		if masked[offset] == "{":
			depth += 1
		elif masked[offset] == "}":
			depth -= 1
			if depth == 0:
				return code.insert(offset, body)
	return ""
