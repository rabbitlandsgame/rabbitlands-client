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
const MapMaterialPreparation := preload("res://src/world/map_material_preparation.gd")

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

static func _one_pixel_png() -> PackedByteArray:
	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color.WHITE)
	return image.save_png_to_buffer()

static func _padded(bytes: PackedByteArray, pad: int) -> PackedByteArray:
	var result := bytes.duplicate()
	while result.size() % 4 != 0:
		result.append(pad)
	return result

## A GLB holding only `document`'s materials, textures and samplers, every
## image one 1x1 PNG, no meshes, nodes or scenes.
static func materials_glb(document: Dictionary) -> PackedByteArray:
	var png := _one_pixel_png()
	var images: Array = []
	for _image: Variant in document.get("images", []) as Array:
		images.append({"bufferView": 0, "mimeType": "image/png"})
	var stripped := {"asset": document.get("asset", {"version": "2.0"}),
		"materials": document.get("materials", []), "textures": document.get("textures", []),
		"samplers": document.get("samplers", []), "images": images}
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
	var coloured_surfaces: Dictionary = {}
	var defaults: Dictionary = {}
	for mesh: Variant in document.get("meshes", []) as Array:
		if mesh is not Dictionary:
			continue
		for primitive: Variant in (mesh as Dictionary).get("primitives", []) as Array:
			if primitive is not Dictionary:
				continue
			var attributes: Variant = (primitive as Dictionary).get("attributes", {})
			var coloured := attributes is Dictionary and (attributes as Dictionary).has("COLOR_0")
			var index: Variant = (primitive as Dictionary).get("material")
			if (index is int or index is float) and int(index) >= 0 and int(index) < parsed.size():
				var material := parsed[int(index)] as BaseMaterial3D
				if material != null and coloured:
					material.vertex_color_use_as_albedo = true
					coloured_surfaces[material] = true
			elif not defaults.has(coloured):
				var fresh := StandardMaterial3D.new()
				fresh.vertex_color_use_as_albedo = coloured
				defaults[coloured] = fresh
				if coloured:
					coloured_surfaces[fresh] = true
	MapMaterialPreparation.prepare(state)
	var result: Array = []
	for value: Variant in parsed + defaults.values():
		var material := value as BaseMaterial3D
		if material == null:
			continue
		result.append(material)
		# WorldLoader._apply_material_passes, after generate_scene took the RID.
		var after := material.duplicate() as BaseMaterial3D
		var changed := false
		if after.texture_filter != MapMaterialPreparation.FILTER:
			after.texture_filter = MapMaterialPreparation.FILTER
			changed = true
		if coloured_surfaces.has(material) and after.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR \
				and not after.vertex_color_use_as_albedo:
			after.vertex_color_use_as_albedo = true
			changed = true
		if changed:
			result.append(after)
	return result

## Builds the shader of every key the GLB at `glb_path` binds and returns
## {"materials": [...] (hold them), "keys": distinct keys, "usec": int,
## "error": ""}. The compiles themselves land in the next draw.
static func warm(glb_path: String) -> Dictionary:
	var began := Time.get_ticks_usec()
	var document := read_json_chunk(glb_path)
	if document.is_empty():
		return {"materials": [], "keys": 0, "usec": Time.get_ticks_usec() - began, "error": "glb_unreadable"}
	var materials := materials_of(document)
	var keys: Dictionary = {}
	for material: BaseMaterial3D in materials:
		material.get_rid() # BaseMaterial3D builds (or shares) its key's shader here.
		keys[signature(material)] = true
	return {"materials": materials, "keys": keys.size(), "usec": Time.get_ticks_usec() - began, "error": ""}

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
