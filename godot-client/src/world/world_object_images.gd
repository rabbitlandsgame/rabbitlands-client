extends GLTFDocumentExtension
## World-object GLBs embed their images. Build mipmaps before their first GPU
## upload, avoiding the readback previously needed by GlbSceneCache afterwards.
##
## Sidecars: when the GLB's own directory carries a `vram/index.json` (written
## by tools/build_vram_textures.py --scenery-config, keyed by the sha256 of each
## embedded image's bytes) that lists an image, the renderer samples its format
## and the entry was encoded for every role this GLB samples the image in, the
## image is that pre-compressed sidecar (BC7 / BC5 / BC1 with its whole mip
## chain): no decode, no mips to build, a quarter or an eighth of the GPU
## memory. The checks are the map images' (vram_textures.gd decode_sidecar):
## any doubt decodes the embedded bytes as before, so a directory without an
## index behaves exactly as it always has. Nothing here touches the
## RenderingServer, so it is safe on a preloader's worker.
const VramTextures := preload("res://src/world/vram_textures.gd")
const ScenerySources := preload("res://src/world/scenery_image_sources.gd")
const MapImages := preload("res://src/world/map_image_extension.gd")
const Pool := preload("res://src/world/external_texture_pool.gd")
const VERIFIED_KEY := ScenerySources.VERIFIED_KEY
const EXTERNAL_ACTIVE := &"rl_world_external_images_active"
const LEGACY_PREPARED := &"rl_world_legacy_images_prepared"
const ENABLED := &"rabbitlands_world_object_images"
const PREPARED := &"rabbitlands_world_object_images_prepared"
## How many of this parse's images were uploaded from a sidecar.
const SIDECARS := &"rabbitlands_world_object_images_sidecars"
## sha256 of an embedded image's bytes -> {role: true} this document samples it
## in, built once per parse and only when a sidecar is on offer.
const ROLES := &"rabbitlands_world_object_images_roles"

func _import_preflight(state: GLTFState, _extensions: PackedStringArray) -> Error:
	var enabled: Variant = state.get_additional_data(ENABLED)
	if typeof(enabled) != TYPE_BOOL or not enabled:
		return ERR_SKIP
	state.set_additional_data(PREPARED, 0)
	state.set_additional_data(LEGACY_PREPARED, 0)
	state.set_additional_data(SIDECARS, 0)
	var verified: Variant = state.get_additional_data(VERIFIED_KEY)
	if not verified is Dictionary:
		verified = ScenerySources.verify_document(state.get_json(), state.get_base_path())
	if not bool(verified.get("ok", false)): return ERR_INVALID_DATA
	if bool(verified.get("tagged", false)):
		state.set_additional_data(VERIFIED_KEY, verified)
		state.set_additional_data(VramTextures.PLAN_KEY, {"resources": verified.resources,
			"policies": verified.policies, "mip_skip": 0, "eligible_only": true})
		var result := MapImages.new()._import_preflight(state, _extensions)
		if result != OK and result != ERR_SKIP: return result
		state.set_additional_data(EXTERNAL_ACTIVE, true)
	return OK

func _parse_image_data(state: GLTFState, bytes: PackedByteArray, _mime: String, image: Image) -> Error:
	if _mime.begins_with(MapImages.MIME_PREFIX):
		var result := MapImages.new()._parse_image_data(state, bytes, _mime, image)
		if not image.is_empty():
			state.set_additional_data(PREPARED, int(state.get_additional_data(PREPARED)) + 1)
		return result
	if _sidecar(state, bytes, image):
		state.set_additional_data(PREPARED, int(state.get_additional_data(PREPARED)) + 1)
		state.set_additional_data(LEGACY_PREPARED, int(state.get_additional_data(LEGACY_PREPARED)) + 1)
		state.set_additional_data(SIDECARS, int(state.get_additional_data(SIDECARS)) + 1)
		return OK
	var error := ERR_FILE_UNRECOGNIZED
	if bytes.size() >= 8 and bytes[0] == 0x89 and bytes[1] == 0x50 and bytes[2] == 0x4e:
		error = image.load_png_from_buffer(bytes)
	elif bytes.size() >= 3 and bytes[0] == 0xff and bytes[1] == 0xd8 and bytes[2] == 0xff:
		error = image.load_jpg_from_buffer(bytes)
	elif bytes.size() >= 12 and bytes.slice(0,4).get_string_from_ascii() == "RIFF" \
		and bytes.slice(8,12).get_string_from_ascii() == "WEBP":
		error = image.load_webp_from_buffer(bytes)
	if error == OK and not image.is_empty():
		if not image.has_mipmaps(): image.generate_mipmaps()
		state.set_additional_data(PREPARED, int(state.get_additional_data(PREPARED)) + 1)
		state.set_additional_data(LEGACY_PREPARED, int(state.get_additional_data(LEGACY_PREPARED)) + 1)
	# Empty images fall back to GLTFDocument's normal decoder.
	return OK

func _import_post_parse(state: GLTFState) -> Error:
	if not bool(state.get_additional_data(EXTERNAL_ACTIVE)): return OK
	var result := MapImages.new()._import_post_parse(state)
	if result != OK: return result
	var verified: Dictionary = state.get_additional_data(VERIFIED_KEY)
	var eligible := {}
	for descriptor: Dictionary in state.get_json().get("images", []):
		if bool(descriptor.get("extras", {}).get(ScenerySources.ELIGIBLE_EXTRA, false)):
			eligible[str(descriptor.uri)] = verified.resources[str(descriptor.uri)]
	# Every prepared/pooled image has DONE_KEY. share() must never read it back.
	Pool.share(state, eligible)
	var done: Variant = state.get_additional_data(VramTextures.DONE_KEY)
	state.set_additional_data(PREPARED, int(state.get_additional_data(LEGACY_PREPARED)) + (done.size() if done is Dictionary else 0))
	var stats: Variant = state.get_additional_data(VramTextures.STATS_KEY)
	if stats is Dictionary: state.set_additional_data(SIDECARS, int(stats.get("imagesSidecar", 0)))
	return OK

## Fills `image` from the sidecar of these bytes when one may stand for them.
static func _sidecar(state: GLTFState, bytes: PackedByteArray, image: Image) -> bool:
	if bytes.is_empty() or VramTextures.mode() == VramTextures.Mode.OFF:
		return false
	var directory := state.get_base_path()
	if directory.is_empty():
		return false
	# Read once per directory; most world-object folders have no index at all.
	var info := VramTextures.index_for_directory(directory)
	if str(info.status) != "ok" or int(info.entries) == 0:
		return false
	var sha := _sha256(bytes)
	var entry := VramTextures.sidecar_entry(sha, directory)
	if entry.is_empty():
		return false
	var roles: Dictionary = _roles(state).get(sha, {})
	# An image this document does not embed by bufferView (a URI image) or
	# samples in a role the encode was not made for decodes as before.
	if roles.is_empty() or not VramTextures.sidecar_fits(entry, roles):
		VramTextures.note_decoded_instead(sha)
		VramTextures._warn_once(sha, "vram_textures: an image of %s is sampled as %s, which sidecar %s was not encoded for; decoding it" % [
			directory, "+".join(PackedStringArray(roles.keys())), str(entry.file)])
		return false
	var loaded := VramTextures.decode_sidecar(entry)
	if loaded.image == null:
		VramTextures.note_decoded_instead(sha)
		VramTextures._warn_once(sha, "vram_textures: sidecar %s unusable (%s); decoding the embedded image" % [
			str(entry.file), str(loaded.reason)])
		return false
	image.copy_from(loaded.image)
	return true

static func _sha256(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()

## sha256 of each bufferView image -> the roles this document samples it in.
static func _roles(state: GLTFState) -> Dictionary:
	var known: Variant = state.get_additional_data(ROLES)
	if known is Dictionary:
		return known
	var result: Dictionary = {}
	var document := state.get_json()
	var by_index := VramTextures.image_roles(document)
	var images: Array = document.get("images", [])
	var views: Array = document.get("bufferViews", [])
	var buffers: Array = state.get_buffers()
	for index: int in images.size():
		var descriptor: Variant = images[index]
		if not descriptor is Dictionary or not (descriptor as Dictionary).has("bufferView"):
			continue
		var view_index := int((descriptor as Dictionary).bufferView)
		if view_index < 0 or view_index >= views.size() or not views[view_index] is Dictionary:
			continue
		var view: Dictionary = views[view_index]
		var buffer_index := int(view.get("buffer", 0))
		if buffer_index < 0 or buffer_index >= buffers.size():
			continue
		var buffer: PackedByteArray = buffers[buffer_index]
		var start := int(view.get("byteOffset", 0))
		var length := int(view.get("byteLength", 0))
		if start < 0 or length <= 0 or start + length > buffer.size():
			continue
		var sha := _sha256(buffer.slice(start, start + length))
		if not result.has(sha):
			result[sha] = {}
		(result[sha] as Dictionary).merge(by_index.get(index, {}))
	state.set_additional_data(ROLES, result)
	return result
