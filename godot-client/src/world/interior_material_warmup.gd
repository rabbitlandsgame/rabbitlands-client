extends RefCounted
## The shader variants an interior's shell needs, built on its parent map's
## arrival frame (behind the arrival curtain) instead of in the middle of the
## walk up to its door.
##
## Why (measured 2026-10-27, tests/integration/landfall_town_park.gd and a
## frame-split probe): a StandardMaterial3D whose feature set ("key") has no
## shader yet in the session gets one when its RID is first asked for, and the
## renderer then compiles it on the main thread at the next draw - about 70 ms
## per key with an empty shader cache and 15-30 ms from a warm one. A preload's
## worker asks for the Town shell's RIDs in GLTFDocument.generate_scene, so its
## four new keys (an emissive door quad, the door's light spill, an emissive
## blend, and a clamped decal sampler) cost one 103-123 ms frame cold and four
## 15-31 ms frames warm, 0.4-0.6 s into the preload, while the player walked.
## BaseMaterial3D shares one shader per key for as long as any material of the
## key lives, so building one material of each key here and holding it for the
## session makes every later build of the shell compile nothing.
##
## The materials are the shell GLB's own, parsed by GLTFDocument - so each key
## is exactly the import's, samplers included - from a copy of the GLB's JSON
## with its meshes and nodes dropped and every image replaced by one 1x1 PNG
## (a key depends on whether a slot has a texture, never on its pixels). The
## vertex-colour flag GLTFDocument sets while it parses meshes, and the
## loader's own material passes (MapMaterialPreparation before generate_scene,
## WorldLoader._apply_material_passes after it), are applied as the real load
## applies them; a pass that changes a material after its RID was taken keeps
## both keys, as the real load briefly does.
##
## The scenery's own shaders (final review 2026-10-27, finding 1). The preload
## also dresses the interior on the main thread (InteriorSceneryStepper): a
## placement with a `palette` is tinted by MineralAppearance's ShaderMaterial,
## and the styling gives a shell's Water_ and Shaft_ meshes the cenote water
## and daylight shaft shaders. Those are custom shaders, not BaseMaterial3D
## keys, so warming the shell builds none of them. Measured on the Town once
## its Hall of Eight Seats gained three lichen crusts and a tinted standing
## stone (`town-scenery.json`): the first tint material of a session cost
## 23.9 ms on the main thread inside a preload step, and with Godot's shader
## cache empty the preload had one 67-79 ms frame (landfall_town_park.gd
## failing its 50 ms check); with the tint shader drawn once when Landfall
## bound, the same runs' worst frames were 24.5 and 8.6 ms. So the warm-up
## also builds one ShaderMaterial of each such shader the interior's scenery
## config and shell imply (`scenery_shaders`), its samplers filled with the
## 1x1 picture, takes its RID and holds it for the session with the rest.
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")
const MineralAppearance := preload("res://src/world/mineral_appearance.gd")
const UndergroundScenery := preload("res://src/world/underground_scenery.gd")

const GLB_MAGIC := 0x46546C67
const CHUNK_JSON := 0x4E4F534A
const CHUNK_BIN := 0x004E4942

## The JSON chunk of the GLB at `path`, parsed, or {} (no file, not a GLB).
## Only the header and that chunk are read.
static func read_json_chunk(path: String) -> Dictionary:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() < 20:
		return {}
	if file.get_32() != GLB_MAGIC:
		return {}
	file.get_32() # version
	file.get_32() # total length
	var length := file.get_32()
	if file.get_32() != CHUNK_JSON or length <= 0 or length > file.get_length():
		return {}
	var parsed: Variant = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
	return parsed if parsed is Dictionary else {}

static func _one_pixel() -> Image:
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	return image

static func _one_pixel_png() -> PackedByteArray:
	return _one_pixel().save_png_to_buffer()

static func _padded(bytes: PackedByteArray, pad: int) -> PackedByteArray:
	var result := bytes.duplicate()
	while result.size() % 4 != 0:
		result.append(pad)
	return result

## A GLB holding only `document`'s materials, textures and samplers, every
## image one 1x1 PNG, no meshes, nodes or scenes. With `only` (material
## indices), just those materials and the textures, samplers and images they
## use, re-indexed: one material of a spread warm-up (`plan`).
static func materials_glb(document: Dictionary, only: Array = []) -> PackedByteArray:
	var png := _one_pixel_png()
	var materials: Array = document.get("materials", [])
	var textures: Array = document.get("textures", [])
	var samplers: Array = document.get("samplers", [])
	var image_count := (document.get("images", []) as Array).size()
	if not only.is_empty():
		var picked := _subset(document, only)
		materials = picked.materials
		textures = picked.textures
		samplers = picked.samplers
		image_count = int(picked.images)
	var images: Array = []
	for _image: int in image_count:
		images.append({"bufferView": 0, "mimeType": "image/png"})
	var stripped := {"asset": document.get("asset", {"version": "2.0"}),
		"materials": materials, "textures": textures, "samplers": samplers, "images": images}
	if document.has("extensionsUsed"):
		stripped["extensionsUsed"] = document.extensionsUsed
	if not images.is_empty():
		stripped["buffers"] = [{"byteLength": png.size()}]
		stripped["bufferViews"] = [{"buffer": 0, "byteOffset": 0, "byteLength": png.size()}]
	var json := _padded(JSON.stringify(stripped).to_utf8_buffer(), 0x20)
	var binary := _padded(png, 0) if not images.is_empty() else PackedByteArray()
	var stream := StreamPeerBuffer.new()
	stream.big_endian = false
	stream.put_u32(GLB_MAGIC)
	stream.put_u32(2)
	stream.put_u32(12 + 8 + json.size() + (8 + binary.size() if not binary.is_empty() else 0))
	stream.put_u32(json.size())
	stream.put_u32(CHUNK_JSON)
	stream.put_data(json)
	if not binary.is_empty():
		stream.put_u32(binary.size())
		stream.put_u32(CHUNK_BIN)
		stream.put_data(binary)
	return stream.data_array

## The materials at `only`, with the textures they name (every `*Texture`
## textureInfo, at any depth: the core slots and any extension's) and those
## textures' samplers, re-indexed in order of first use; "images" is how many
## images the kept textures name (each becomes the one 1x1 picture).
static func _subset(document: Dictionary, only: Array) -> Dictionary:
	var all_materials: Array = document.get("materials", [])
	var all_textures: Array = document.get("textures", [])
	var all_samplers: Array = document.get("samplers", [])
	var texture_map: Dictionary = {}
	var materials: Array = []
	for value: Variant in only:
		var index := int(value)
		if index < 0 or index >= all_materials.size():
			continue
		materials.append(_reindex_textures((all_materials[index] as Dictionary).duplicate(true), texture_map))
	var textures: Array = []
	textures.resize(texture_map.size())
	var sampler_map: Dictionary = {}
	var image_map: Dictionary = {}
	for old: int in texture_map:
		var texture: Dictionary = (all_textures[old] as Dictionary).duplicate(true) \
			if old >= 0 and old < all_textures.size() and all_textures[old] is Dictionary else {}
		if texture.has("sampler"):
			var sampler := int(texture.sampler)
			if not sampler_map.has(sampler):
				sampler_map[sampler] = sampler_map.size()
			texture["sampler"] = sampler_map[sampler]
		_reindex_sources(texture, image_map)
		textures[int(texture_map[old])] = texture
	var samplers: Array = []
	samplers.resize(sampler_map.size())
	for old: int in sampler_map:
		samplers[int(sampler_map[old])] = all_samplers[old] if old >= 0 and old < all_samplers.size() else {}
	return {"materials": materials, "textures": textures, "samplers": samplers, "images": image_map.size()}

## Rewrites every textureInfo `index` under a `*Texture` key in `value` to
## its compact index (`texture_map`: old -> new, grown on first use).
static func _reindex_textures(value: Variant, texture_map: Dictionary) -> Variant:
	if value is Dictionary:
		var row := value as Dictionary
		for key: Variant in row.keys():
			var child: Variant = row[key]
			if str(key).ends_with("Texture") and child is Dictionary and (child as Dictionary).has("index"):
				var old := int((child as Dictionary).index)
				if not texture_map.has(old):
					texture_map[old] = texture_map.size()
				(child as Dictionary)["index"] = texture_map[old]
			_reindex_textures(child, texture_map)
	elif value is Array:
		for child: Variant in value as Array:
			_reindex_textures(child, texture_map)
	return value

## Rewrites a texture's image `source` (its own and any extension's) to its
## compact index.
static func _reindex_sources(value: Variant, image_map: Dictionary) -> void:
	if value is Dictionary:
		var row := value as Dictionary
		for key: Variant in row.keys():
			if str(key) == "source" and (row[key] is int or row[key] is float):
				var old := int(row[key])
				if not image_map.has(old):
					image_map[old] = image_map.size()
				row[key] = image_map[old]
			else:
				_reindex_sources(row[key], image_map)

## As GLTFDocument._parse_meshes: the material indices a primitive with COLOR_0
## draws (their vertex colours turn on), and the vertex-colour flag of each
## default material a primitive without one gets ({true/false: true}).
static func _mesh_use(document: Dictionary) -> Dictionary:
	var coloured: Dictionary = {}
	var defaults: Dictionary = {}
	var count := (document.get("materials", []) as Array).size()
	for mesh: Variant in document.get("meshes", []) as Array:
		if mesh is not Dictionary:
			continue
		for primitive: Variant in (mesh as Dictionary).get("primitives", []) as Array:
			if primitive is not Dictionary:
				continue
			var attributes: Variant = (primitive as Dictionary).get("attributes", {})
			var has_colour := attributes is Dictionary and (attributes as Dictionary).has("COLOR_0")
			var index: Variant = (primitive as Dictionary).get("material")
			if (index is int or index is float) and int(index) >= 0 and int(index) < count:
				if has_colour:
					coloured[int(index)] = true
			elif not defaults.has(has_colour):
				defaults[has_colour] = true
	return {"coloured": coloured, "defaults": defaults}

## The materials a load of the GLB `document` binds, one per shader key it
## takes on the way (see the header). [] when the materials do not parse.
static func materials_of(document: Dictionary) -> Array:
	if (document.get("materials", []) as Array).is_empty() and (document.get("meshes", []) as Array).is_empty():
		return []
	var gltf := GLTFDocument.new()
	var state := GLTFState.new()
	if gltf.append_from_buffer(materials_glb(document), "", state) != OK:
		return []
	var parsed: Array = state.get_materials()
	# As GLTFDocument._parse_meshes: a primitive with COLOR_0 turns its
	# material's vertex colours on; one without a material gets a fresh one.
	var use := _mesh_use(document)
	var coloured_surfaces: Dictionary = {}
	for index: int in use.coloured:
		var material := parsed[index] as BaseMaterial3D if index < parsed.size() else null
		if material != null:
			material.vertex_color_use_as_albedo = true
			coloured_surfaces[material] = true
	var defaults: Array = []
	for flag: bool in use.defaults:
		var fresh := StandardMaterial3D.new()
		fresh.vertex_color_use_as_albedo = flag
		defaults.append(fresh)
		if flag:
			coloured_surfaces[fresh] = true
	MapMaterialPreparation.prepare(state)
	var result: Array = []
	for value: Variant in parsed + defaults:
		var material := value as BaseMaterial3D
		if material == null:
			continue
		result.append(material)
		var after := after_pass(material, coloured_surfaces.has(material))
		if after != null:
			result.append(after)
	return result

## The custom shaders (res:// paths) the dressing of an interior adds, from
## its scenery `config` (UndergroundScenery.config_for: placements, read
## only) and its shell GLB's JSON `document`: MineralAppearance's tint when a
## placement carries a `palette`, and the styling's cenote water and daylight
## shaft shaders for a shell with Water_ or Shaft_ nodes. None for an interior
## without a scenery config (nothing dresses it). Pure data: safe on a worker.
static func scenery_shaders(config: Dictionary, document: Dictionary = {}) -> PackedStringArray:
	var paths := PackedStringArray()
	if config.is_empty():
		return paths
	for placement: Variant in config.get("placements", []) as Array:
		if placement is Dictionary and (placement as Dictionary).get("palette") is Dictionary:
			paths.append(MineralAppearance.PAINT.resource_path)
			break
	var water := false
	var shaft := false
	for node: Variant in document.get("nodes", []) as Array:
		var name := str((node as Dictionary).get("name", "")) if node is Dictionary else ""
		water = water or name.begins_with("Water_")
		shaft = shaft or name.begins_with("Shaft_")
	if water:
		paths.append(UndergroundScenery.CENOTE_WATER.resource_path)
	if shaft:
		paths.append(UndergroundScenery.DAYLIGHT_SHAFT.resource_path)
	return paths

## A ShaderMaterial of the shader at `path`, as the dressing builds one: every
## sampler uniform given the 1x1 picture, its RID taken now (the shader is
## readied at this frame's material update). Null when `path` is no shader.
static func shader_material(path: String) -> ShaderMaterial:
	var shader := load(path) as Shader if ResourceLoader.exists(path) else null
	if shader == null:
		return null
	var material := ShaderMaterial.new()
	material.shader = shader
	var picture: ImageTexture = null
	for uniform: Dictionary in shader.get_shader_uniform_list():
		if int(uniform.get("type", TYPE_NIL)) == TYPE_OBJECT and str(uniform.get("hint_string", "")).contains("Texture"):
			if picture == null:
				picture = ImageTexture.create_from_image(_one_pixel())
			material.set_shader_parameter(str(uniform.name), picture)
	material.get_rid()
	return material

## WorldLoader._apply_material_passes on `material` after generate_scene took
## its RID: a copy with the loader's filter (and a coloured alpha-scissor
## material's vertex colours), or null when the passes change nothing.
static func after_pass(material: BaseMaterial3D, coloured: bool) -> BaseMaterial3D:
	var changed := material.texture_filter != MapMaterialPreparation.FILTER \
		or (coloured and material.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
			and not material.vertex_color_use_as_albedo)
	if not changed:
		return null
	var after := material.duplicate() as BaseMaterial3D
	after.texture_filter = MapMaterialPreparation.FILTER
	if coloured and after.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR:
		after.vertex_color_use_as_albedo = true
	return after

# --------------------------------------------------------------------------
# The warm-up spread over frames
# --------------------------------------------------------------------------
#
# Binding a parent with no curtain up - a walk over its border, where the map
# arrives as a seamless handoff (review 2026-10-27, finding 7) - must not
# spend `warm`'s 31-93 ms on one gameplay frame, nor hand the next draw every
# new key at once. `plan` does the file and JSON work on a worker and cuts
# the shell's materials into one small materials-only GLB each; `build_step`
# then builds one material a frame on the main thread and takes its RID at
# once, so a draw compiles at most one new key. A material is never left
# alive across a frame before its RID is taken: BaseMaterial3D would update
# every pending material's shader at the frame's flush, all keys together.

## A spread warm-up's steps, for a worker: {"steps": [{"glb", "coloured"} or
## {"default": true, "coloured"} or {"shader": path}], "error": "", "usec":
## int}; the scenery's shaders (`scenery_shaders` of `config`, which is only
## read) come last, one step each. Pure file and data work (no Resource is
## created), so it is safe off the main thread.
static func plan(glb_path: String, config: Dictionary = {}) -> Dictionary:
	var began := Time.get_ticks_usec()
	var document := read_json_chunk(glb_path)
	if document.is_empty():
		return {"steps": [], "error": "glb_unreadable", "usec": Time.get_ticks_usec() - began}
	var use := _mesh_use(document)
	var steps: Array = []
	for index: int in (document.get("materials", []) as Array).size():
		steps.append({"glb": materials_glb(document, [index]), "coloured": (use.coloured as Dictionary).has(index)})
	for flag: bool in use.defaults:
		steps.append({"default": true, "coloured": flag})
	for path: String in scenery_shaders(config, document):
		steps.append({"shader": path})
	return {"steps": steps, "error": "", "usec": Time.get_ticks_usec() - began}

## One planned step on the main thread: the material the shell's load (or,
## for a {"shader"} step, the scenery's dressing) binds for it, its RID taken
## now (its shader is built here and readied at this frame's material update).
## Null when the step's GLB does not parse or its shader does not load.
static func build_step(step: Dictionary) -> Material:
	if step.has("shader"):
		return shader_material(str(step.shader))
	var material: BaseMaterial3D = null
	if bool(step.get("default", false)):
		material = StandardMaterial3D.new()
		material.vertex_color_use_as_albedo = bool(step.get("coloured", false))
	else:
		var gltf := GLTFDocument.new()
		var state := GLTFState.new()
		if gltf.append_from_buffer(step.get("glb", PackedByteArray()) as PackedByteArray, "", state) != OK:
			return null
		var parsed: Array = state.get_materials()
		material = parsed[0] as BaseMaterial3D if not parsed.is_empty() else null
		if material == null:
			return null
		if bool(step.get("coloured", false)):
			material.vertex_color_use_as_albedo = true
		MapMaterialPreparation.prepare(state)
	material.get_rid()
	return material

## Builds the shader of every key the GLB at `glb_path` binds, and one
## material of each shader the dressing with scenery `config` adds
## (`scenery_shaders`), and returns {"materials": [...] (hold them), "keys":
## distinct BaseMaterial3D keys, "shaders": scenery shaders built, "usec":
## int, "error": ""}. The compiles themselves land in the next draw.
static func warm(glb_path: String, config: Dictionary = {}) -> Dictionary:
	var began := Time.get_ticks_usec()
	var document := read_json_chunk(glb_path)
	if document.is_empty():
		return {"materials": [], "keys": 0, "shaders": 0, "usec": Time.get_ticks_usec() - began,
			"error": "glb_unreadable"}
	var materials := materials_of(document)
	var keys: Dictionary = {}
	for material: BaseMaterial3D in materials:
		material.get_rid() # BaseMaterial3D builds (or shares) its key's shader here.
		keys[signature(material)] = true
	var shaders := 0
	for path: String in scenery_shaders(config, document):
		var tinted := shader_material(path)
		if tinted != null:
			materials.append(tinted)
			shaders += 1
	return {"materials": materials, "keys": keys.size(), "shaders": shaders,
		"usec": Time.get_ticks_usec() - began, "error": ""}

## A string equal for two BaseMaterial3Ds whose shader keys are equal (a
## superset of the key: every stored bool and int property - features, flags,
## modes, channels - and which texture slots are filled; colours and floats
## are uniforms, not key). Tests compare a load's materials with `warm`'s.
static func signature(material: BaseMaterial3D) -> String:
	var parts := PackedStringArray()
	for property: Dictionary in material.get_property_list():
		if (int(property.usage) & PROPERTY_USAGE_STORAGE) == 0:
			continue
		var name := str(property.name)
		var type := int(property.type)
		if type == TYPE_BOOL or type == TYPE_INT:
			if name == "render_priority" or name.begins_with("resource_"):
				continue
			parts.append("%s=%s" % [name, str(material.get(name))])
		elif type == TYPE_OBJECT and str(property.hint_string).contains("Texture"):
			parts.append("%s=%s" % [name, material.get(name) != null])
	return ";".join(parts)
