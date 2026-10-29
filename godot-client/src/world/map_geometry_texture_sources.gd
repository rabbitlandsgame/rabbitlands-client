extends RefCounted
const CreaturePayload := preload("res://src/actors/creature_payload.gd")
## Texture provenance for the offline geometry cooker. Ordinary play takes the
## disabled fast path; discovery owns WeakRefs and portable data, never pixels.
const Prepared := preload("res://src/world/prepared_content.gd")
const Vram := preload("res://src/world/vram_textures.gd")
const POLICY := "map-geometry-texture-sources-v1"
const MAX_IMAGE_BYTES := 268435456
static var _recording := false
static var _records: Dictionary = {}
static var _resolver: Callable
static var _notes := 0

static func set_recording(enabled: bool) -> void:
	if OS.get_thread_caller_id() != OS.get_main_thread_id():
		return
	if enabled != _recording:
		_records.clear()
		_notes = 0
	_recording = enabled

static func set_external_resolver(resolver: Callable) -> void:
	_resolver = resolver

static func is_recording() -> bool:
	return _recording

static func logical_source(path: String) -> String:
	var logical := Prepared.logical_source(path)
	return logical if _safe_logical(logical) else ""

static func source_path(logical: String) -> String:
	return Prepared.source_path(logical) if _safe_logical(logical) else ""

static func _safe_logical(path: String) -> bool:
	if path.is_empty() or "\\" in path or path.contains("::"):
		return false
	var relative := path.trim_prefix("user://") if path.begins_with("user://") else path
	if ":" in relative or relative.is_absolute_path() or ".." in relative.split("/"):
		return false
	return path.begins_with("godot-client/") or path.begins_with("eloria-assets/") \
		or (path.begins_with("user://") and not relative.is_empty())

static func digest_bytes(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func _format(texture: Texture2D) -> int:
	if texture is ImageTexture:
		return (texture as ImageTexture).get_format()
	var image := texture.get_image()
	return image.get_format() if image != null and not image.is_empty() else -1

static func _roles(value: Variant) -> Array[String]:
	var result: Array[String] = []
	if value is Dictionary:
		for role: Variant in value:
			if not result.has(str(role)): result.append(str(role))
	elif value is Array or value is PackedStringArray:
		for role: Variant in value:
			if not result.has(str(role)): result.append(str(role))
	result.sort()
	return result

static func _record(texture: Texture2D, origin: Dictionary) -> void:
	if texture == null or origin.is_empty(): return
	var identity := texture.get_instance_id()
	var previous: Dictionary = _records.get(identity, {})
	if not previous.is_empty() and (previous.reference as WeakRef).get_ref() == texture \
			and str(previous.origin.get("image_sha256", "")) == str(origin.get("image_sha256", "")):
		var combined: Array[String] = _roles(previous.origin.get("roles", []))
		for role: String in _roles(origin.get("roles", [])):
			if not combined.has(role): combined.append(role)
		combined.sort()
		origin["roles"] = combined
	origin["decoded_format"] = _format(texture)
	# Sidecar encodings are selected dynamically. They cannot establish the
	# glTF importer's normalization of an uncompressed source during a cook.
	if Vram.IMAGE_FORMATS.values().has(origin.decoded_format):
		origin["decoded_format"] = -1
	origin["width"] = texture.get_width()
	origin["height"] = texture.get_height()
	_records[identity] = {"reference": weakref(texture), "origin": origin}

static func note(state: GLTFState, glb_path: String) -> void:
	if not _recording: return
	if OS.get_thread_caller_id() != OS.get_main_thread_id() or state == null: return
	_notes += 1
	if _notes % 32 == 0:
		for identity: Variant in _records.keys():
			if (_records[identity].reference as WeakRef).get_ref() == null:
				_records.erase(identity)
	var file := logical_source(glb_path)
	if file.is_empty(): return
	var document: Dictionary = state.get_json()
	var descriptors: Array = document.get("images", [])
	var textures: Array[Texture2D] = state.get_images()
	var image_roles := Vram.image_roles(document)
	var origins: Dictionary = {}
	var container := PackedByteArray()
	for index: int in descriptors.size():
		if not descriptors[index] is Dictionary: continue
		var descriptor: Dictionary = descriptors[index]
		var uri := str(descriptor.get("uri", ""))
		var origin: Dictionary = {}
		if not uri.is_empty() and not uri.begins_with("data:"):
			if uri.is_absolute_path() or ":" in uri or "\\" in uri: continue
			var image_file := logical_source(glb_path.get_base_dir().path_join(uri.uri_file_decode()).simplify_path())
			if image_file.is_empty(): continue
			var sha := FileAccess.get_sha256(source_path(image_file))
			if sha.length() != 64: continue
			origin = {"kind": "external", "file": image_file, "file_sha256": sha,
				"image_sha256": sha, "mip_policy": "full" if file.begins_with("godot-client/assets/world/") else "map",
				"inputs": [{"path": image_file, "sha256": sha}]}
		else:
			if container.is_empty(): container = CreaturePayload.read_bytes(source_path(file))
			var extracted := embedded_bytes(container, index)
			if not bool(extracted.get("ok", false)): continue
			var sha := digest_bytes(container)
			origin = {"kind": "gltf_image", "file": file, "file_sha256": sha,
				"image_index": index, "image_sha256": digest_bytes(extracted.bytes),
				"mip_policy": "full" if file.begins_with("godot-client/assets/world/") else "map",
				"inputs": [{"path": file, "sha256": sha}]}
		origin["roles"] = _roles(image_roles.get(index, {}))
		origins[index] = origin
		if index < textures.size(): _record(textures[index], origin.duplicate(true))
	# A glTF importer can normalize a slot's texture (notably a normal map)
	# into another ImageTexture. Associate those actual material carriers too.
	var materials: Array = state.get_materials()
	var descriptions: Array = document.get("materials", [])
	var slots := {"albedo_texture": "pbrMetallicRoughness/baseColorTexture",
		"normal_texture": "normalTexture", "ao_texture": "occlusionTexture",
		"emission_texture": "emissiveTexture", "metallic_texture": "pbrMetallicRoughness/metallicRoughnessTexture",
		"roughness_texture": "pbrMetallicRoughness/metallicRoughnessTexture"}
	for index: int in mini(materials.size(), descriptions.size()):
		if not materials[index] is BaseMaterial3D or not descriptions[index] is Dictionary: continue
		for property: String in slots:
			var item: Variant = descriptions[index]
			for segment: String in str(slots[property]).split("/"):
				item = item.get(segment) if item is Dictionary else null
			if not item is Dictionary: continue
			var image_index := _texture_source(document, int(item.get("index", -1)))
			var actual := materials[index].get(property) as Texture2D
			if actual != null and origins.has(image_index):
				_record(actual, (origins[image_index] as Dictionary).duplicate(true))

static func _texture_source(document: Dictionary, index: int) -> int:
	var textures: Array = document.get("textures", [])
	if index < 0 or index >= textures.size() or not textures[index] is Dictionary: return -1
	var source := int(textures[index].get("source", -1))
	var extensions: Variant = textures[index].get("extensions", {})
	if extensions is Dictionary:
		for extension: Variant in extensions.values():
			if extension is Dictionary and extension.has("source"): source = int(extension.source)
	return source

static func lookup(texture: Texture2D) -> Dictionary:
	if texture == null or OS.get_thread_caller_id() != OS.get_main_thread_id(): return {}
	var identity := texture.get_instance_id()
	var known: Dictionary = _records.get(identity, {})
	if not known.is_empty():
		if (known.reference as WeakRef).get_ref() == texture:
			return (known.origin as Dictionary).duplicate(true)
		_records.erase(identity)
	if _resolver.is_valid():
		var resolved: Variant = _resolver.call(texture)
		if resolved is Dictionary:
			var file := logical_source(str(resolved.get("path", "")))
			var sha := str(resolved.get("sha", resolved.get("sha256", "")))
			if not file.is_empty() and sha.length() == 64 and FileAccess.get_sha256(source_path(file)) == sha:
				var origin := {"kind": "external", "file": file, "file_sha256": sha,
					"image_sha256": sha, "roles": _roles(resolved.get("roles", ["unclassified"])),
					"decoded_format": _format(texture), "width": texture.get_width(), "height": texture.get_height(),
					"mip_policy": "map", "inputs": [{"path": file, "sha256": sha}]}
				return origin
	var resource_path := texture.resource_path
	if resource_path.begins_with("res://") or texture is CompressedTexture2D or texture.has_method("get_load_path"):
		var imported := _imported_origin(texture, resource_path)
		if not imported.is_empty(): return imported
	if texture.get_width() * texture.get_height() <= 16:
		var image := texture.get_image()
		if image != null and not image.is_empty() and image.get_data().size() <= 64:
			return {"kind": "constant", "width": image.get_width(), "height": image.get_height(),
				"format": image.get_format(), "mips": image.get_mipmap_count(), "data": image.get_data().hex_encode(),
				"image_sha256": digest_bytes(image.get_data()), "decoded_format": image.get_format(),
				"roles": [], "mip_policy": "preserve", "inputs": []}
	return {}

static func _imported_origin(texture: Texture2D, resource_path: String) -> Dictionary:
	var file := logical_source(resource_path)
	var load_path := ""
	if texture.has_method("get_load_path"):
		load_path = str(texture.call("get_load_path"))
	if load_path.is_empty():
		for property: Dictionary in texture.get_property_list():
			if str(property.name) == "load_path":
				load_path = str(texture.get("load_path"))
				break
	var import_file := resource_path + ".import" if not file.is_empty() else ""
	if load_path.is_empty() and not import_file.is_empty() and FileAccess.file_exists(import_file):
		var config := ConfigFile.new()
		if config.load(import_file) == OK:
			load_path = str(config.get_value("remap", "path", ""))
			if load_path.is_empty():
				for key: String in config.get_section_keys("remap"):
					if key.begins_with("path."):
						var candidate := str(config.get_value("remap", key, ""))
						if FileAccess.file_exists(candidate):
							load_path = candidate
							break
	# An imported GLB's texture can have a PackedScene::subresource path but
	# still name its own portable CTEX product. Load that product directly;
	# never serialize the transient native subresource identifier.
	if file.is_empty():
		file = logical_source(load_path)
		if file.is_empty(): return {}
		resource_path = source_path(file)
	if not ResourceLoader.exists(resource_path, "Texture2D") and load_path.is_empty(): return {}
	var input_hashes := {}
	var raw_sha := FileAccess.get_sha256(resource_path) if FileAccess.file_exists(resource_path) else ""
	if raw_sha.length() == 64: input_hashes[file] = raw_sha
	var product := logical_source(load_path) if not load_path.is_empty() else ""
	var product_sha := FileAccess.get_sha256(source_path(product)) if not product.is_empty() else ""
	if not load_path.is_empty() and (product.is_empty() or product_sha.length() != 64): return {}
	if texture is CompressedTexture2D and product_sha.length() != 64: return {}
	if product_sha.length() == 64: input_hashes[product] = product_sha
	if not import_file.is_empty() and FileAccess.file_exists(import_file):
		var import_logical := logical_source(import_file)
		var import_sha := FileAccess.get_sha256(import_file)
		if not import_logical.is_empty() and import_sha.length() == 64:
			input_hashes[import_logical] = import_sha
	if input_hashes.is_empty() or (raw_sha.is_empty() and product_sha.is_empty()): return {}
	var paths: Array = input_hashes.keys()
	paths.sort()
	var inputs: Array = []
	for path: String in paths: inputs.append({"path": path, "sha256": input_hashes[path]})
	return {"kind": "imported", "file": file, "file_sha256": raw_sha,
		"load_path": product, "image_sha256": product_sha if not product_sha.is_empty() else raw_sha,
		"roles": [], "mip_policy": "preserve", "decoded_format": _format(texture),
		"width": texture.get_width(), "height": texture.get_height(), "inputs": inputs}

## Extract one encoded image without invoking the glTF mesh/material importer.
## Supports normal GLB BIN bufferViews and base64/percent-encoded data URIs.
static func embedded_bytes(container: PackedByteArray, image_index: int) -> Dictionary:
	if container.is_empty(): return {"ok": false, "error": "container_empty"}
	var document: Variant = null
	var binary := PackedByteArray()
	if container.size() >= 12 and container.slice(0, 4).get_string_from_ascii() == "glTF":
		if container.decode_u32(4) != 2 or container.decode_u32(8) != container.size():
			return {"ok": false, "error": "glb_header"}
		var offset := 12
		while offset + 8 <= container.size():
			var length := int(container.decode_u32(offset))
			var kind := int(container.decode_u32(offset + 4))
			offset += 8
			if length < 0 or offset + length > container.size(): return {"ok": false, "error": "glb_chunk"}
			if kind == 0x4e4f534a: document = JSON.parse_string(container.slice(offset, offset + length).get_string_from_utf8())
			elif kind == 0x004e4942 and binary.is_empty(): binary = container.slice(offset, offset + length)
			offset += length
	else:
		document = JSON.parse_string(container.get_string_from_utf8())
	if not document is Dictionary: return {"ok": false, "error": "gltf_json"}
	var images: Variant = document.get("images", [])
	if not images is Array or image_index < 0 or image_index >= images.size() or not images[image_index] is Dictionary:
		return {"ok": false, "error": "image_index"}
	var descriptor: Dictionary = images[image_index]
	var uri := str(descriptor.get("uri", ""))
	if uri.begins_with("data:"):
		var comma := uri.find(",")
		if comma < 0: return {"ok": false, "error": "data_uri"}
		var payload := uri.substr(comma + 1)
		var bytes: PackedByteArray
		if uri.substr(0, comma).ends_with(";base64"):
			if payload.length() > MAX_IMAGE_BYTES * 2: return {"ok": false, "error": "image_size"}
			for character: String in payload:
				if not character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n":
					return {"ok": false, "error": "data_base64"}
			bytes = Marshalls.base64_to_raw(payload)
		else:
			bytes = _percent_bytes(payload)
		if bytes.is_empty() or bytes.size() > MAX_IMAGE_BYTES: return {"ok": false, "error": "data_image"}
		return {"ok": true, "bytes": bytes}
	var views: Variant = document.get("bufferViews", [])
	var view_index := int(descriptor.get("bufferView", -1))
	if not views is Array or view_index < 0 or view_index >= views.size() or not views[view_index] is Dictionary:
		return {"ok": false, "error": "image_buffer_view"}
	var view: Dictionary = views[view_index]
	var offset := int(view.get("byteOffset", 0))
	var length := int(view.get("byteLength", 0))
	if int(view.get("buffer", -1)) != 0 or offset < 0 or length <= 0 or length > MAX_IMAGE_BYTES \
			or offset + length > binary.size(): return {"ok": false, "error": "image_buffer_range"}
	return {"ok": true, "bytes": binary.slice(offset, offset + length)}

static func _percent_bytes(value: String) -> PackedByteArray:
	var result := PackedByteArray()
	var index := 0
	while index < value.length():
		if value[index] == "%":
			if index + 2 >= value.length(): return PackedByteArray()
			var pair := value.substr(index + 1, 2)
			if not pair.is_valid_hex_number(false): return PackedByteArray()
			result.append(pair.hex_to_int())
			index += 3
		else:
			var character := value.unicode_at(index)
			if character > 127: return PackedByteArray()
			result.append(character)
			index += 1
	return result
