extends SceneTree
## Low/Medium/other-race presentation parity capture for the RL High head work.
##
## Builds real actors headlessly through ReplicatedActor3D.configure (the same
## path world actors take), waits for the appearance pipeline, poses them at a
## fixed animation time and writes a canonical, deterministic JSON of every
## MeshInstance3D under each actor: node path, mesh content (surface arrays,
## blend-shape arrays and the renderer's packed buffers and LODs, hashed),
## material class, shader path and every set parameter value (never identities),
## visibility, shadows, LOD bias, layers, cull margin, instance uniforms and
## blend-shape weights, plus the skeleton pose. Meshes, materials, skins and
## textures are content-addressed in shared tables.
##
## Groups and what a later build must reproduce:
##   luminous_low / luminous_medium   Humans at Low/Medium: identical to develop.
##   luminous_from_high               Humans built at High, then switched to
##                                    Low/Medium in place: identical.
##   luminous_edited                  Built at Low/Medium, then edited in place
##                                    (appearance editor path): identical.
##   other_races_high                 Votary, Orun, Glasswarden and Greyhaven at
##                                    High: identical.
##   luminous_high_classic            Humans at High: identical only with the
##                                    dormant classic head (RL_HEADS=classic).
##   luminous_finish                  Humans at Low/Medium, every hairstyle and
##                                    saved finish, length and volume at and off
##                                    50, with hair_finish 0 or typed on the
##                                    finish's slider position: identical.
##   luminous_finish_classic          The same at High: identical only with
##                                    RL_HEADS=classic.
##
## Looks carry every PC/3 field (colour model spec revision 3: 53) as literals,
## so a build that does not know a field ignores it and a later build must draw
## the same thing: the V3 face and detail fields only ever change the RL head,
## colour fields equal to a palette entry's frozen value (Rule C) or guarded
## by a disagreeing palette byte, and a hair_finish typed on its saved
## finish's position or guarded, draw the palette path. A look with "sex" is
## captured only on bodies of that sex (frozen hair values are per sex).
##
## Usage (headless, after an import):
##   Godot --headless --path godot-client --script res://tests/integration/rl_high_parity_capture.gd
##       -- --out=<abs.json> [--groups=a,b] [--baseline=<abs.json>] [--limit=N]
##   Godot --headless --path godot-client --script res://tests/integration/rl_high_parity_capture.gd
##       -- --compare=<a.json>,<b.json> [--all-instances]
## With --baseline (or --compare), cases are compared by id: the visible
## instances must match exactly for every group except luminous_high_classic,
## which must match only when the capture ran with RL_HEADS=classic. Hidden
## instances are compared with --all-instances. Exit 0 = capture written and
## no required difference; 1 = differences or capture errors; 2 = bad usage.

const SCHEMA := 1
const PRESETS := preload("res://src/actors/human_portrait_presets.gd")
const QUALITY_NAMES := ["low", "medium", "high"]
const POSE_TIME := 0.4
const SETTLE_FRAMES := 3
const HASH_CHARS := 24
const ARRAY_NAMES := ["vertex", "normal", "tangent", "color", "tex_uv", "tex_uv2",
	"custom0", "custom1", "custom2", "custom3", "bones", "weights", "index"]
## Renderer-side surface fields hashed as they are packed for the GPU.
const RS_FIELDS := ["format", "primitive", "vertex_data", "attribute_data", "skin_data",
	"vertex_count", "index_data", "index_count", "aabb", "bone_aabbs",
	"blend_shape_data", "uv_scale"]
const SKIPPED_MATERIAL_PROPERTIES := ["resource_local_to_scene", "resource_path",
	"resource_name", "resource_scene_unique_id", "script", "next_pass", "render_priority"]
const OTHER_RACES := ["votary", "orun", "glasswarden", "greyhaven"]
const FROM_HIGH_LOOKS := ["default", "rowan", "mira", "tavi", "facial_hair_5", "bald",
	"closed_helmet", "band_111", "band_114", "v3_details", "colour_guarded"]
const EDITED_LOOKS := ["rowan", "mira", "extreme_100", "facial_hair_3", "band_111", "torso_armour",
	"v3_details", "colour_guarded", "typed_frozen_female", "typed_frozen_male"]
## Every PC/3 field and its wire maximum, literally (PC/1, PC/2, then V3: the
## 11 face offsets, 9 details ending with hair_finish, the 17 colour fields).
const ALL_FIELD_MAXIMA := {"facial_hair": 5, "jaw": 100, "cheekbones": 100, "nose": 100,
	"height": 100, "build": 100, "hair_detail": 2, "face_length": 100, "eye_size": 100,
	"eye_tilt": 100, "eye_spacing": 100, "nose_width": 100, "lip_fullness": 100,
	"brow_depth": 100, "hair_length": 100, "hair_volume": 100,
	"eyelid": 100, "brow_height": 100, "nose_length": 100, "nose_bridge": 100, "nose_tip": 100,
	"mouth_width": 100, "cupid_bow": 100, "cheek_fullness": 100, "chin_projection": 100,
	"chin_width": 100, "ear_size": 100, "brow_style": 13, "brow_thickness": 101, "freckles": 101,
	"liner": 101, "liner_wing": 101, "stubble": 101, "lip_tint": 12, "hair_module": 31,
	"hair_finish": 101, "skin_tone": 201, "skin_undertone": 201,
	"hair_hue": 240, "hair_sat": 101, "hair_light": 101, "eye_hue": 240, "eye_sat": 101, "eye_light": 101,
	"shirt_hue": 240, "shirt_sat": 101, "shirt_light": 101, "pants_hue": 240, "pants_sat": 101,
	"pants_light": 101, "boots_hue": 240, "boots_sat": 101, "boots_light": 101}
## hair_detail 0 Classic, 1 Tousled, 2 Swept -> hair_finish wire value on the
## finish's slider position (Classic 50, Tousled 75, Swept 25; wire = s + 1).
const FINISH_WIRE := [51, 76, 26]

var checks := 0
var failures := 0
var _models: Dictionary
var _equipment: Dictionary
var _animations: Dictionary = {}
var _mesh_table: Dictionary = {}
var _material_table: Dictionary = {}
var _skin_table: Dictionary = {}
var _texture_table: Dictionary = {}
var _texture_digest_by_id: Dictionary = {}
var _next_actor_id := 9300

func _init() -> void:
	call_deferred("run")

func expect(ok: bool, label: String) -> bool:
	checks += 1
	if not ok:
		failures += 1
		push_error(label)
	return ok

# ---------------------------------------------------------------- cases ----

## Named appearances shared by every model. Together they cover the default,
## the three editable presets, both extremes, every facial_hair value, every
## hair style (0-9), every hair_detail value, skin 0-9 and eye indices across
## the palettes, a closed helmet, the open bands 111/114, a show hood and
## torso armour.
static func looks() -> Dictionary:
	var all_min := {}
	var all_max := {}
	for field: String in ALL_FIELD_MAXIMA:
		all_min[field] = 0
		all_max[field] = ALL_FIELD_MAXIMA[field]
	var hair := func(style: int, colour: int) -> int: return AppearanceVariants.pack_hair(style, colour)
	# Typed frozen palette values (colour model spec revision 3, Appendix A):
	# skin golden tan 43, eyes emerald (104,87,63), luminous shirt crimson
	# (19,84,37), pants navy (180,56,25), boots walnut (38,37,27); chestnut hair
	# apparent on the reference path, per sex; Tousled typed on 75 (wire 76).
	var frozen := {"skin": 2, "skin_tone": 43, "skin_undertone": 0, "eyes": 1,
		"eye_hue": 104, "eye_sat": 87, "eye_light": 63, "shirt": 4, "shirt_hue": 19, "shirt_sat": 84,
		"shirt_light": 37, "pants": 6, "pants_hue": 180, "pants_sat": 56, "pants_light": 25,
		"boots": 0, "boots_hue": 38, "boots_sat": 37, "boots_light": 27, "hair_detail": 1,
		"hair_finish": 76, "hair": hair.call(1, 2)}
	return {
		"default": {"appearance": {}, "equipment": {}},
		"rowan": {"appearance": PRESETS.appearance("Rowan"), "equipment": {}},
		"mira": {"appearance": PRESETS.appearance("Mira"), "equipment": {}},
		"tavi": {"appearance": PRESETS.appearance("Tavi"), "equipment": {}},
		"extreme_0": {"appearance": all_min.merged({"hair": hair.call(2, 19), "skin": 9,
			"eyes": 11, "shirt": 11, "pants": 11, "boots": 11}), "equipment": {}},
		"extreme_100": {"appearance": all_max.merged({"hair": hair.call(4, 7), "skin": 6,
			"eyes": 5, "shirt": 3, "pants": 4, "boots": 5}), "equipment": {}},
		"facial_hair_1": {"appearance": {"facial_hair": 1, "hair": hair.call(5, 3), "skin": 2,
			"eyes": 3}, "equipment": {}},
		"facial_hair_2": {"appearance": {"facial_hair": 2, "hair": hair.call(6, 8), "skin": 3,
			"eyes": 4, "hair_detail": 1}, "equipment": {}},
		"facial_hair_3": {"appearance": {"facial_hair": 3, "hair": hair.call(7, 12), "skin": 4,
			"eyes": 6, "hair_detail": 2}, "equipment": {}},
		"facial_hair_4": {"appearance": {"facial_hair": 4, "hair": hair.call(8, 15), "skin": 5,
			"eyes": 7, "hair_length": 20, "hair_volume": 85}, "equipment": {}},
		"facial_hair_5": {"appearance": {"facial_hair": 5, "hair": hair.call(9, 18), "skin": 7,
			"eyes": 9, "hair_length": 90, "hair_volume": 15}, "equipment": {}},
		"bald": {"appearance": {"hair": hair.call(0, 2), "facial_hair": 4, "skin": 8, "eyes": 10},
			"equipment": {}},
		"legacy_hair_7": {"appearance": {"hair": 7, "skin": 1, "eyes": 8}, "equipment": {}},
		"closed_helmet": {"appearance": PRESETS.appearance("Rowan").merged({"facial_hair": 5}, true),
			"equipment": {3: 143}},
		"band_111": {"appearance": PRESETS.appearance("Mira"), "equipment": {3: 111}},
		"band_114": {"appearance": PRESETS.appearance("Tavi"), "equipment": {3: 114}},
		"hood_159": {"appearance": PRESETS.appearance("Rowan"), "equipment": {3: 159}},
		"torso_armour": {"appearance": {"facial_hair": 2, "hair": hair.call(2, 5), "skin": 3, "eyes": 2},
			"equipment": {5: 184, 4: 171, 6: 192, 0: 114, 1: 106}},
		# Non-neutral V3 face and detail fields (High-only) on a stubbled,
		# moustached Parted look with every hair module id in turn elsewhere.
		"v3_details": {"appearance": {"facial_hair": 2, "hair": hair.call(1, 4), "skin": 3, "eyes": 6,
			"eyelid": 0, "brow_height": 100, "nose_length": 7, "nose_bridge": 93, "nose_tip": 0,
			"mouth_width": 100, "cupid_bow": 12, "cheek_fullness": 88, "chin_projection": 0,
			"chin_width": 100, "ear_size": 100, "brow_style": 13, "brow_thickness": 1, "freckles": 101,
			"liner": 101, "liner_wing": 51, "stubble": 101, "lip_tint": 12, "hair_module": 3},
			"equipment": {}},
		"typed_frozen_female": {"sex": "female", "appearance": frozen.merged({"hair_hue": 36, "hair_sat": 79,
			"hair_light": 19}), "equipment": {}},
		"typed_frozen_male": {"sex": "male", "appearance": frozen.merged({"hair_hue": 36, "hair_sat": 79,
			"hair_light": 18}), "equipment": {}},
		# Custom values whose nearest palette entry disagrees with the saved
		# palette byte (an old client's edit): the palette wins (guard).
		"colour_guarded": {"appearance": {"skin": 3, "skin_tone": 10, "skin_undertone": 30,
			"hair": hair.call(5, 4), "hair_hue": 174, "hair_sat": 11, "hair_light": 40, "eyes": 0,
			"eye_hue": 104, "eye_sat": 87, "eye_light": 63, "shirt": 1, "shirt_hue": 192, "shirt_sat": 6,
			"shirt_light": 24, "pants": 2, "pants_hue": 61, "pants_sat": 70, "pants_light": 79,
			"boots": 3, "boots_hue": 19, "boots_sat": 84, "boots_light": 37, "hair_detail": 0,
			"hair_finish": 91}, "equipment": {}},
		# An undertone on an Eloria tone is ignored; a partly set triple is
		# palette (Rule A).
		"eloria_undertone": {"appearance": {"skin": 7, "skin_undertone": 30, "hair": hair.call(3, 9),
			"hair_hue": 50, "hair_sat": 0, "hair_light": 50, "eyes": 4, "eye_hue": 0, "eye_sat": 50,
			"eye_light": 50, "hair_detail": 2, "hair_finish": 26}, "equipment": {}},
	}

## R14: every hairstyle 1-9 and saved finish, length and volume at 50 and off
## it, with hair_finish 0 and typed on the finish's own slider position.
static func finish_looks() -> Dictionary:
	var result := {}
	for style: int in range(1, 10):
		for finish: int in 3:
			for shaped: bool in [false, true]:
				for typed: bool in [false, true]:
					var appearance := {"hair": AppearanceVariants.pack_hair(style, (style * 3 + finish) % 20),
						"hair_detail": finish, "skin": style % 6, "eyes": style % 12, "hair_finish": 0}
					if shaped:
						appearance.merge({"hair_length": 18 + style * 7, "hair_volume": 90 - style * 6}, true)
					if typed:
						appearance["hair_finish"] = FINISH_WIRE[finish]
					var name := "finish_s%d_f%d_%s_%s" % [style, finish, "shaped" if shaped else "50",
						"typed" if typed else "zero"]
					result[name] = {"appearance": appearance, "equipment": {}}
	return result

static func all_looks() -> Dictionary:
	return looks().merged(finish_looks())

## A look with "sex" belongs only on bodies of that sex.
static func _fits(look: Dictionary, model: String) -> bool:
	return not look.has("sex") or model.ends_with("_" + str(look["sex"]))

## Every case, in a fixed order: id, group, model slug, quality, build path, look.
static func cases() -> Array:
	var result: Array = []
	var all := looks()
	var names: Array = all.keys()
	var finishes: Array = finish_looks().keys()
	for quality: int in [0, 1]:
		for sex: String in ["male", "female"]:
			for look: String in names:
				_add_case(result, all, "luminous_" + QUALITY_NAMES[quality], "luminous_" + sex, quality, "direct", look)
	for quality: int in [0, 1]:
		for sex: String in ["male", "female"]:
			for look: String in FROM_HIGH_LOOKS:
				_add_case(result, all, "luminous_from_high", "luminous_" + sex, quality, "from_high", look)
			for look: String in EDITED_LOOKS:
				_add_case(result, all, "luminous_edited", "luminous_" + sex, quality, "edited", look)
	for race: String in OTHER_RACES:
		for sex: String in ["male", "female"]:
			for look: String in names:
				_add_case(result, all, "other_races_high", race + "_" + sex, 2, "direct", look)
	for sex: String in ["male", "female"]:
		for look: String in names:
			_add_case(result, all, "luminous_high_classic", "luminous_" + sex, 2, "direct", look)
	for quality: int in [0, 1]:
		for sex: String in ["male", "female"]:
			for look: String in finishes:
				_add_case(result, all, "luminous_finish", "luminous_" + sex, quality, "direct", look)
	for sex: String in ["male", "female"]:
		for look: String in finishes:
			_add_case(result, all, "luminous_finish_classic", "luminous_" + sex, 2, "direct", look)
	return result

## Appends a case when the look fits the model (a named helper, not a lambda
## called with string arguments, which tests/test_gdscript_references.py reads
## as string-named method calls).
static func _add_case(result: Array, all: Dictionary, group: String, model: String, quality: int, path: String, look: String) -> void:
	if _fits(all.get(look, {}) as Dictionary, model):
		result.append(_case(group, model, quality, path, look))

static func _case(group: String, model: String, quality: int, path: String, look: String) -> Dictionary:
	return {"id": "%s/%s/%s/%s/%s" % [group, model, QUALITY_NAMES[quality], path, look],
		"group": group, "model": model, "quality": quality, "path": path, "look": look}

# ------------------------------------------------------------- hashing ----

static func _sha(bytes: PackedByteArray) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	if not bytes.is_empty():
		context.update(bytes)
	return context.finish().hex_encode().substr(0, HASH_CHARS)

static func _hash_value(value: Variant) -> String:
	return _sha(var_to_bytes(value))

static func _digest(record: Variant) -> String:
	return _sha(JSON.stringify(record, "", true, true).to_utf8_buffer())

## A JSON-safe canonical value. Objects become content records (textures by
## path or pixels, other resources by class and path), never identities.
func _value(value: Variant) -> Variant:
	var kind := typeof(value)
	if kind in [TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_STRING]:
		return value
	if kind == TYPE_STRING_NAME:
		return str(value)
	if kind == TYPE_FLOAT:
		return value if is_finite(value) else var_to_str(value)
	if kind == TYPE_OBJECT:
		if value == null:
			return null
		if value is Texture:
			return {"texture": _texture_digest(value as Texture)}
		if value is Material:
			return {"material": _material_digest(value as Material)}
		if value is Resource:
			return {"class": (value as Resource).get_class(), "path": (value as Resource).resource_path}
		return {"class": (value as Object).get_class()}
	if kind == TYPE_ARRAY and _has_objects(value as Array):
		var items: Array = []
		for item: Variant in value as Array:
			items.append(_value(item))
		return items
	if kind == TYPE_ARRAY or kind == TYPE_DICTIONARY or (kind >= TYPE_PACKED_BYTE_ARRAY and kind <= TYPE_PACKED_VECTOR4_ARRAY):
		return {"sha": _hash_value(value), "size": value.size()}
	return var_to_str(value)

static func _has_objects(values: Array) -> bool:
	for item: Variant in values:
		if typeof(item) == TYPE_OBJECT:
			return true
	return false

func _texture_digest(texture: Texture) -> String:
	var key := texture.get_instance_id()
	if _texture_digest_by_id.has(key):
		return _texture_digest_by_id[key]
	var record := {"class": texture.get_class(), "path": texture.resource_path}
	if texture is Texture2D:
		var flat := texture as Texture2D
		record["size"] = [flat.get_width(), flat.get_height()]
		if texture.resource_path.is_empty() or not (texture is CompressedTexture2D):
			var image := flat.get_image()
			if image != null and not image.is_empty():
				record["image"] = {"sha": _sha(image.get_data()), "format": image.get_format(),
					"mipmaps": image.has_mipmaps(), "size": [image.get_width(), image.get_height()]}
	var digest := _digest(record)
	_texture_table[digest] = record
	_texture_digest_by_id[key] = digest
	return digest

func _material_digest(material: Material) -> String:
	if material == null:
		return ""
	var record := {"class": material.get_class(), "render_priority": material.render_priority,
		"next_pass": _material_digest(material.next_pass) if material.next_pass != null else ""}
	var parameters := {}
	if material is ShaderMaterial:
		var shader := (material as ShaderMaterial).shader
		if shader == null:
			record["shader"] = ""
		elif not shader.resource_path.is_empty() and not shader.resource_path.contains("::"):
			record["shader"] = shader.resource_path
		else:
			record["shader"] = "code:" + _sha(shader.code.to_utf8_buffer())
		if shader != null:
			# Unset uniforms (null) are left out: they draw the shader's own
			# default, so a uniform added with today's constant as its default
			# leaves every material that never sets it unchanged.
			for uniform: Dictionary in shader.get_shader_uniform_list():
				var name := str(uniform.get("name", ""))
				var value: Variant = (material as ShaderMaterial).get_shader_parameter(name)
				if value != null:
					parameters[name] = _value(value)
	else:
		for property: Dictionary in material.get_property_list():
			var name := str(property.name)
			if not (int(property.usage) & PROPERTY_USAGE_STORAGE) or name in SKIPPED_MATERIAL_PROPERTIES:
				continue
			parameters[name] = _value(material.get(name))
	record["parameters"] = parameters
	var digest := _digest(record)
	_material_table[digest] = record
	return digest

func _mesh_digest(mesh: Mesh) -> String:
	if mesh == null:
		return ""
	var record := {"class": mesh.get_class(), "surface_count": mesh.get_surface_count()}
	var shapes: Array = []
	if mesh is ArrayMesh:
		var array_mesh := mesh as ArrayMesh
		record["blend_shape_mode"] = array_mesh.blend_shape_mode
		record["custom_aabb"] = var_to_str(array_mesh.custom_aabb)
		for index: int in array_mesh.get_blend_shape_count():
			shapes.append(str(array_mesh.get_blend_shape_name(index)))
	record["blend_shapes"] = shapes
	var surfaces: Array = []
	for surface: int in mesh.get_surface_count():
		var arrays := mesh.surface_get_arrays(surface)
		var named := {}
		for index: int in mini(arrays.size(), ARRAY_NAMES.size()):
			if arrays[index] != null:
				named[ARRAY_NAMES[index]] = {"sha": _hash_value(arrays[index]), "size": arrays[index].size()}
		var entry := {"arrays": named,
			"blend_shape_arrays": _hash_value(mesh.surface_get_blend_shape_arrays(surface)),
			"material": _material_digest(mesh.surface_get_material(surface))}
		if mesh is ArrayMesh:
			entry["primitive"] = (mesh as ArrayMesh).surface_get_primitive_type(surface)
			entry["format"] = (mesh as ArrayMesh).surface_get_format(surface)
		var packed: Dictionary = RenderingServer.mesh_get_surface(mesh.get_rid(), surface)
		var renderer := {}
		for field: String in RS_FIELDS:
			if packed.has(field):
				renderer[field] = _hash_value(packed[field])
		var lods: Array = []
		for lod: Variant in packed.get("lods", []) as Array:
			if lod is Dictionary:
				lods.append({"edge_length": var_to_str((lod as Dictionary).get("edge_length", 0.0)),
					"index_data": _hash_value((lod as Dictionary).get("index_data", PackedByteArray()))})
		renderer["lods"] = lods
		entry["renderer"] = renderer
		surfaces.append(entry)
	record["surfaces"] = surfaces
	var digest := _digest(record)
	_mesh_table[digest] = record
	return digest

func _skin_digest(skin: Skin) -> String:
	if skin == null:
		return ""
	var binds: Array = []
	for index: int in skin.get_bind_count():
		binds.append([str(skin.get_bind_name(index)), skin.get_bind_bone(index),
			var_to_str(skin.get_bind_pose(index))])
	var record := {"bind_count": skin.get_bind_count(), "binds_sha": _hash_value(binds)}
	var digest := _digest(record)
	_skin_table[digest] = record
	return digest

## Node path from the actor with engine-generated names (@Class@<id>) replaced
## by their class and child index, which are stable between runs.
static func _stable_path(actor: Node, node: Node) -> String:
	var parts: Array[String] = []
	var current := node
	while current != null and current != actor:
		var name := str(current.name)
		if name.begins_with("@"):
			name = "@%s#%d" % [current.get_class(), current.get_index()]
		parts.push_front(name)
		current = current.get_parent()
	return "/".join(parts)

func _instance_record(actor: Node3D, instance: MeshInstance3D) -> Dictionary:
	var active: Array = []
	var overrides: Array = []
	var surface_count := instance.mesh.get_surface_count() if instance.mesh != null else 0
	for surface: int in surface_count:
		active.append(_material_digest(instance.get_active_material(surface)))
		overrides.append(_material_digest(instance.get_surface_override_material(surface)))
	var weights: Array = []
	if instance.mesh is ArrayMesh:
		for index: int in (instance.mesh as ArrayMesh).get_blend_shape_count():
			weights.append(var_to_str(instance.get_blend_shape_value(index)))
	var instance_parameters := {}
	for property: Dictionary in instance.get_property_list():
		var name := str(property.name)
		if name.begins_with("instance_shader_parameters/"):
			instance_parameters[name.trim_prefix("instance_shader_parameters/")] = _value(instance.get(name))
	return {
		"path": _stable_path(actor, instance),
		"class": instance.get_class(),
		"visible": instance.visible,
		"visible_in_tree": instance.is_visible_in_tree(),
		"mesh": _mesh_digest(instance.mesh),
		"active_materials": active,
		"surface_overrides": overrides,
		"material_override": _material_digest(instance.material_override),
		"material_overlay": _material_digest(instance.material_overlay),
		"skin": _skin_digest(instance.skin),
		"skeleton": str(instance.skeleton),
		"cast_shadow": instance.cast_shadow,
		"lod_bias": var_to_str(instance.lod_bias),
		"layers": instance.layers,
		"extra_cull_margin": var_to_str(instance.extra_cull_margin),
		"custom_aabb": var_to_str(instance.custom_aabb),
		"gi_mode": instance.gi_mode,
		"transparency": var_to_str(instance.transparency),
		"sorting_offset": var_to_str(instance.sorting_offset),
		"visibility_range": var_to_str(Vector4(instance.visibility_range_begin,
			instance.visibility_range_begin_margin, instance.visibility_range_end,
			instance.visibility_range_end_margin)),
		"transform": var_to_str(actor.global_transform.affine_inverse() * instance.global_transform),
		"blend_shape_weights_sha": _hash_value(weights),
		"blend_shape_weight_count": weights.size(),
		"instance_parameters": instance_parameters,
	}

func _skeleton_record(skeleton: Skeleton3D) -> Dictionary:
	if skeleton == null:
		return {}
	var local: Array = []
	var global: Array = []
	var names: Array = []
	for bone: int in skeleton.get_bone_count():
		names.append(str(skeleton.get_bone_name(bone)))
		local.append(var_to_str(skeleton.get_bone_pose(bone)))
		global.append(var_to_str(skeleton.get_bone_global_pose(bone)))
	return {"bone_count": skeleton.get_bone_count(), "names_sha": _hash_value(names),
		"pose_sha": _hash_value(local), "global_pose_sha": _hash_value(global)}

# ------------------------------------------------------------- capture ----

func _animation_config(model: Dictionary) -> Dictionary:
	var path := str(model.get("animationMap", "res://data/animations/luminous.json"))
	if not _animations.has(path):
		_animations[path] = JSON.parse_string(FileAccess.get_file_as_string(path))
	return _animations[path]

func _settle(frames: int = SETTLE_FRAMES) -> void:
	for _frame: int in frames:
		await process_frame

## Fixed pose: the idle clip without blending, at POSE_TIME, paused.
func _pose(actor: ReplicatedActor3D) -> String:
	var player := actor.animation_player
	if player == null:
		return ""
	var clip := str(actor.resolver.action_to_clip.get("idle", "")) if actor.resolver != null else ""
	if clip.is_empty() or not player.has_animation(clip):
		return ""
	# Manual callbacks: frames no longer advance the clip, as in
	# test_animated_head_culling's pose sampling.
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	player.stop()
	player.play(clip, 0.0)
	player.seek(POSE_TIME, true)
	player.advance(0.0)
	var skeleton := actor.get_skeleton()
	if skeleton != null:
		skeleton.force_update_all_bone_transforms()
	return clip

func _capture_case(spec: Dictionary, look: Dictionary) -> Dictionary:
	var model: Dictionary = _models[spec.model]
	var appearance: Dictionary = (look.appearance as Dictionary).duplicate(true)
	var equipment: Dictionary = (look.equipment as Dictionary).duplicate(true)
	var path := str(spec.path)
	var quality := int(spec.quality)
	# Pixel digests are per case: a runtime texture may be updated in place.
	_texture_digest_by_id.clear()
	var actor := ReplicatedActor3D.new()
	_next_actor_id += 1
	actor.apply_render_quality(2 if path == "from_high" else quality, false)
	root.add_child(actor)
	var dto := {"actor_id": _next_actor_id, "x": 0, "y": 0, "rotation": 0, "kind": 1, "name": "",
		"appearance": {} if path == "edited" else appearance,
		"equipment_visuals": {} if path == "edited" else equipment}
	var errors: Array = Array(actor.configure(dto, CoordinateAdapter.new({"walkingHeight": 0.0}),
		model, _animation_config(model), _equipment))
	actor.set_process(false)
	actor.set_physics_process(false)
	await _settle()
	if path == "from_high":
		actor.apply_render_quality(quality, false)
		await _settle()
	elif path == "edited":
		actor.apply_appearance_variants(appearance)
		actor.apply_equipment_visuals(equipment)
		await _settle()
	var clip := _pose(actor)
	await _settle(2)
	var instances: Array = []
	for node: Node in actor.find_children("*", "MeshInstance3D", true, false):
		instances.append(_instance_record(actor, node as MeshInstance3D))
	instances.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.path) < str(b.path))
	var paths := {}
	for record: Dictionary in instances:
		expect(not paths.has(record.path), "%s: unique stable path %s" % [spec.id, record.path])
		paths[record.path] = true
	var visible := instances.filter(func(r: Dictionary) -> bool: return bool(r.visible_in_tree))
	var native := actor.get_node_or_null("NativeModel") as Node3D
	var result := spec.duplicate()
	var equipment_keys := {}
	for slot: Variant in equipment:
		equipment_keys[str(slot)] = equipment[slot]
	result.merge({"appearance": appearance, "equipment": equipment_keys,
		"configure_errors": errors.map(func(e: Variant) -> String: return str(e)),
		"render_quality": actor.render_quality(), "pose_clip": clip, "pose_time": POSE_TIME,
		"native_model_transform": var_to_str(native.transform) if native != null else "",
		"skeleton": _skeleton_record(actor.get_skeleton()),
		"instance_count": instances.size(), "visible_count": visible.size(),
		"instances": instances}, true)
	result["visible_digest"] = _digest({"instances": visible, "skeleton": result.skeleton,
		"native": result.native_model_transform})
	result["case_digest"] = _digest({"instances": instances, "skeleton": result.skeleton,
		"native": result.native_model_transform})
	expect(errors.is_empty(), "%s configures: %s" % [spec.id, str(errors)])
	expect(actor.render_quality() == quality, "%s ends at %s" % [spec.id, QUALITY_NAMES[quality]])
	actor.free()
	await process_frame
	return result

# ------------------------------------------------------------- compare ----

static func _index(document: Dictionary) -> Dictionary:
	var result := {}
	for item: Variant in document.get("cases", []):
		result[str((item as Dictionary).id)] = item
	return result

static func _instances_by_path(case: Dictionary, all_instances: bool) -> Dictionary:
	var result := {}
	for item: Variant in case.get("instances", []):
		var record := item as Dictionary
		if all_instances or bool(record.visible_in_tree):
			result[str(record.path)] = record
	return result

static func _table_diff(kind: String, a: Dictionary, b: Dictionary, digest_a: String, digest_b: String) -> String:
	var left: Dictionary = (a.get(kind, {}) as Dictionary).get(digest_a, {})
	var right: Dictionary = (b.get(kind, {}) as Dictionary).get(digest_b, {})
	var keys := {}
	for key: Variant in left: keys[key] = true
	for key: Variant in right: keys[key] = true
	var changed: Array = []
	for key: Variant in keys:
		if JSON.stringify(left.get(key), "", true, true) != JSON.stringify(right.get(key), "", true, true):
			if key in ["parameters", "surfaces"] and left.get(key) is Dictionary and right.get(key) is Dictionary:
				for name: Variant in left[key]:
					if JSON.stringify(left[key].get(name)) != JSON.stringify((right[key] as Dictionary).get(name)):
						changed.append("%s.%s" % [key, name])
				for name: Variant in right[key]:
					if not (left[key] as Dictionary).has(name):
						changed.append("%s.%s(new)" % [key, name])
			elif key == "surfaces" and left.get(key) is Array and right.get(key) is Array:
				var ls: Array = left[key]
				var rs: Array = right[key]
				for s: int in mini(ls.size(), rs.size()):
					for field: Variant in ls[s]:
						if JSON.stringify(ls[s].get(field), "", true, true) != JSON.stringify((rs[s] as Dictionary).get(field), "", true, true):
							changed.append("surface%d.%s" % [s, field])
				if ls.size() != rs.size():
					changed.append("surface_count")
			else:
				changed.append(str(key))
	return ",".join(changed)

## Differences between two capture documents, by case id.
static func compare(a: Dictionary, b: Dictionary, all_instances: bool, limit_lines: int = 400) -> Dictionary:
	var left := _index(a)
	var right := _index(b)
	var classic := str((b.get("environment", {}) as Dictionary).get("RL_HEADS", "")).to_lower() == "classic"
	var lines: Array = []
	var required := 0
	var informational := 0
	var compared := 0
	var captured_groups: Array = b.get("groups", ["all"])
	for id: String in left:
		var case_a: Dictionary = left[id]
		if not captured_groups.has("all") and not captured_groups.has(str(case_a.group)):
			continue
		var must_match := not str(case_a.group).ends_with("_classic") or classic
		if not right.has(id):
			lines.append("MISSING %s" % id)
			if must_match: required += 1
			continue
		compared += 1
		var case_b: Dictionary = right[id]
		var key := "case_digest" if all_instances else "visible_digest"
		if case_a.get(key) == case_b.get(key):
			continue
		if must_match: required += 1
		else: informational += 1
		var tag := "DIFF" if must_match else "INFO"
		lines.append("%s %s" % [tag, id])
		if case_a.get("skeleton") != case_b.get("skeleton"):
			lines.append("  skeleton pose differs")
		if case_a.get("native_model_transform") != case_b.get("native_model_transform"):
			lines.append("  NativeModel transform differs")
		var ia := _instances_by_path(case_a, all_instances)
		var ib := _instances_by_path(case_b, all_instances)
		for path: String in ia:
			if not ib.has(path):
				lines.append("  - %s (only in first)" % path)
				continue
			var ra: Dictionary = ia[path]
			var rb: Dictionary = ib[path]
			for field: String in ra:
				if JSON.stringify(ra[field], "", true, true) == JSON.stringify(rb.get(field), "", true, true):
					continue
				var detail := ""
				if field == "mesh":
					detail = _table_diff("meshes", a, b, str(ra[field]), str(rb[field]))
				elif field in ["material_override", "material_overlay"]:
					detail = _table_diff("materials", a, b, str(ra[field]), str(rb[field]))
				elif field in ["active_materials", "surface_overrides"]:
					var parts: Array = []
					for s: int in mini((ra[field] as Array).size(), (rb[field] as Array).size()):
						if ra[field][s] != rb[field][s]:
							parts.append("s%d[%s]" % [s, _table_diff("materials", a, b, str(ra[field][s]), str(rb[field][s]))])
					detail = " ".join(parts)
				lines.append("  ~ %s %s %s" % [path, field, detail])
		for path: String in ib:
			if not ia.has(path):
				lines.append("  + %s (only in second)" % path)
	if lines.size() > limit_lines:
		var kept := lines.slice(0, limit_lines)
		kept.append("... %d more lines" % (lines.size() - limit_lines))
		lines = kept
	return {"compared": compared, "required_differences": required,
		"informational_differences": informational, "lines": lines, "classic_capture": classic}

static func _print_comparison(result: Dictionary) -> void:
	for line: String in result.lines:
		print(line)
	print("RL_HIGH_PARITY_COMPARE: %d cases compared, %d required differences, %d informational (classic capture: %s)"
		% [result.compared, result.required_differences, result.informational_differences, result.classic_capture])

static func _load(path: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}

# ----------------------------------------------------------------- run ----

static func _arguments() -> Dictionary:
	var result := {}
	for argument: String in OS.get_cmdline_user_args():
		if argument.begins_with("--"):
			var pair := argument.trim_prefix("--").split("=", true, 1)
			result[pair[0]] = pair[1] if pair.size() > 1 else "1"
	return result

func run() -> void:
	var arguments := _arguments()
	if arguments.has("compare"):
		var files := str(arguments.compare).split(",")
		if files.size() != 2:
			push_error("--compare needs two comma-separated capture files")
			quit(2)
			return
		var first := _load(files[0])
		var second := _load(files[1])
		if first.is_empty() or second.is_empty():
			push_error("cannot read both capture files")
			quit(2)
			return
		var comparison := compare(first, second, arguments.has("all-instances"))
		_print_comparison(comparison)
		quit(1 if comparison.required_differences else 0)
		return
	var output := str(arguments.get("out", ""))
	if output.is_empty():
		push_error("usage: -- --out=<abs.json> [--groups=a,b] [--baseline=<abs.json>] [--limit=N]")
		quit(2)
		return
	var wanted_groups := {}
	if arguments.has("groups"):
		for group: String in str(arguments.groups).split(",", false):
			wanted_groups[group] = true
	var limit := int(arguments.get("limit", "0"))
	_models = (JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/models.json")) as Dictionary).models
	_equipment = JSON.parse_string(FileAccess.get_file_as_string("res://data/actors/equipment.json"))
	var look_table := all_looks()
	var captured: Array = []
	var started := Time.get_ticks_msec()
	for spec: Dictionary in cases():
		if not wanted_groups.is_empty() and not wanted_groups.has(spec.group):
			continue
		if limit > 0 and captured.size() >= limit:
			break
		if not expect(_models.has(spec.model), "model %s exists" % spec.model):
			continue
		captured.append(await _capture_case(spec, look_table[spec.look]))
		if captured.size() % 25 == 0:
			print("RL_HIGH_PARITY: %d cases captured" % captured.size())
	var environment := {}
	for name: String in ["RL_HEADS", "RL_HEADWEAR_FIT", "ELORIA_LOOK_QUALITY", "ELORIA_LOOK"]:
		environment[name] = OS.get_environment(name)
	var document := {
		"schema": SCHEMA,
		"tool": "res://tests/integration/rl_high_parity_capture.gd",
		"godot": Engine.get_version_info().string,
		"renderer": RenderingServer.get_current_rendering_method(),
		"headless": DisplayServer.get_name() == "headless",
		"environment": environment,
		"look_quality": LookProfile.quality_name(LookProfile.quality()),
		"pose_time": POSE_TIME,
		"looks": look_table.keys(),
		"groups": wanted_groups.keys() if not wanted_groups.is_empty() else ["all"],
		"cases": captured,
		"meshes": _mesh_table,
		"materials": _material_table,
		"skins": _skin_table,
		"textures": _texture_table,
	}
	DirAccess.make_dir_recursive_absolute(output.get_base_dir())
	var file := FileAccess.open(output, FileAccess.WRITE)
	if not expect(file != null, "output %s opens" % output):
		quit(1)
		return
	file.store_string(JSON.stringify(document, " ", true, true) + "\n")
	file.close()
	var instance_total := 0
	var visible_total := 0
	for item: Dictionary in captured:
		instance_total += int(item.instance_count)
		visible_total += int(item.visible_count)
	print("RL_HIGH_PARITY: %d cases, %d instances (%d visible), %d meshes, %d materials, %d textures in %.1f s -> %s"
		% [captured.size(), instance_total, visible_total, _mesh_table.size(), _material_table.size(),
		_texture_table.size(), (Time.get_ticks_msec() - started) / 1000.0, output])
	var exit_code := 1 if failures else 0
	if arguments.has("baseline"):
		var baseline := _load(str(arguments.baseline))
		if not expect(not baseline.is_empty(), "baseline %s loads" % arguments.baseline):
			quit(1)
			return
		# Compare the written file (parsed numbers), exactly as --compare would.
		var comparison := compare(baseline, _load(output), arguments.has("all-instances"))
		_print_comparison(comparison)
		if comparison.required_differences:
			exit_code = 1
	print("RL_HIGH_PARITY_CHECKS: %d checks, %d failures" % [checks, failures])
	NativeAnimationImporter.clear()
	quit(exit_code)
