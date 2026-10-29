extends RefCounted
## Call-owned verification of ordinary scenery GLBs and their external bytes.
## No persistent stat/SHA acceptance cache: existing in-memory scenes own their
## immutable textures; every new disk/prepared acceptance verifies this closure.
const Vram := preload("res://src/world/vram_textures.gd")
const SCHEMA := "rabbitlands-scenery-images-v1"
const KEY := "rabbitlands_scenery_images"
const VERIFIED_KEY := &"rabbitlands_scenery_images_verified"
const ELIGIBLE_EXTRA := "rl_texture_sidecar_eligible"

static func digest(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()

static func _fail(error: String) -> Dictionary:
	return {"ok": false, "error": error, "tagged": true}

static func _plain_relative(value: Variant) -> bool:
	return value is String and not value.is_empty() and not value.is_absolute_path() \
		and not ":" in value and not "\\" in value and not "%" in value

static func _hex(value: Variant) -> bool:
	if not value is String or value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true

static func verify(path: String) -> Dictionary:
	var bytes := FileAccess.get_file_as_bytes(path)
	if bytes.size() < 20 or bytes.slice(0, 4).get_string_from_ascii() != "glTF" \
		or bytes.decode_u32(4) != 2 or bytes.decode_u32(8) != bytes.size() \
		or bytes.decode_u32(16) != 0x4e4f534a:
		return _fail("scenery_glb_header")
	var count := int(bytes.decode_u32(12))
	if count <= 0 or 20 + count > bytes.size(): return _fail("scenery_glb_json")
	var parsed: Variant = JSON.parse_string(bytes.slice(20, 20 + count).get_string_from_utf8())
	if not parsed is Dictionary: return _fail("scenery_glb_json")
	var result := verify_document(parsed, path.get_base_dir())
	if bool(result.ok):
		result["bytes"] = bytes
		result["source_sha256"] = digest(bytes)
	return result

static func verify_document(document: Dictionary, directory: String) -> Dictionary:
	var extras: Variant = document.get("extras", {})
	if not extras is Dictionary or not extras.has(KEY):
		return {"ok": true, "error": "", "tagged": false, "document": document,
			"resources": {}, "policies": {}, "closure_token": ""}
	var metadata: Variant = extras[KEY]
	if not metadata is Dictionary or metadata.get("schema") != SCHEMA or metadata.get("mipPolicy") != "full":
		return _fail("scenery_images_schema")
	var resources: Variant = metadata.get("resources")
	var policies: Variant = metadata.get("imagePolicies")
	if not resources is Dictionary or not policies is Dictionary: return _fail("scenery_images_resources")
	var errors := Vram.image_policy_errors({"externalResources": resources, "externalImagePolicies": policies}, directory)
	if not errors.is_empty(): return _fail("scenery_images_policy: " + "; ".join(errors))
	var base := Vram.runtime_absolute(directory)
	var world_root := Vram.runtime_absolute("res://assets/world")
	var assets_root := Vram.runtime_absolute("res://../eloria-assets")
	if not (base == world_root or base.begins_with(world_root + "/")): return _fail("scenery_images_source_scope")
	var used := {}
	for item: Variant in document.get("images", []):
		if not item is Dictionary or not _plain_relative(item.get("uri")) or item.has("bufferView"):
			return _fail("scenery_images_descriptor")
		var uri: String = item.uri
		var image_extras: Variant = item.get("extras")
		if not image_extras is Dictionary or not image_extras.get(ELIGIBLE_EXTRA) is bool \
			or not Vram.has_image_policy(item): return _fail("scenery_images_descriptor_policy")
		var policy := Vram.image_policy_directory(item, directory)
		if Vram.runtime_absolute(policy) != base: return _fail("scenery_images_original_directory")
		if not policies.get(uri) is Array or not policies[uri].has(image_extras[Vram.POLICY_DIRECTORY_EXTRA]):
			return _fail("scenery_images_undeclared_policy")
		for declared: String in policies[uri]:
			var declared_directory := Vram.image_policy_directory({"extras": {Vram.POLICY_DIRECTORY_EXTRA: declared}}, directory)
			if Vram.runtime_absolute(declared_directory) != base: return _fail("scenery_images_original_directory")
		if not _hex(resources.get(uri)): return _fail("scenery_images_source_digest")
		var source := base.path_join(uri).simplify_path()
		if not (source.begins_with(assets_root + "/maps/") or source.begins_with(assets_root + "/world/") \
			or source.begins_with(world_root + "/")):
			return _fail("scenery_images_resource_scope")
		used[uri] = source
	if used.size() != resources.size() or policies.size() != resources.size(): return _fail("scenery_images_resource_closure")
	var keys: Array = used.keys()
	keys.sort()
	var tokens: PackedStringArray = []
	for uri: String in keys:
		if FileAccess.get_sha256(used[uri]) != resources[uri]: return _fail("scenery_images_source_changed: " + uri)
		tokens.append(uri + "=" + str(resources[uri]))
	return {"ok": true, "error": "", "tagged": true, "document": document,
		"resources": resources, "policies": policies, "closure_token": digest("\n".join(tokens).to_utf8_buffer()),
		"hash_reads": used.size()}
