extends GLTFDocumentExtension
## The one glTF image extension for actor documents: races, hair, equipment,
## held props, mounts, creatures and RL heads (2026-11 wave-2 schedule 1.1 #4).
## GlbSceneCache's actor-parse helper enables it on the GLTFState of every
## actor glTF, on the main thread and on the actor preparer's worker alike;
## any other document (maps, world objects, animation-library parses, the
## editor's importer) gets ERR_SKIP from `_import_preflight` before anything
## else, so none of the hooks below runs for it.
##
## URI role. 1,552 equipment glTFs name their textures by URI, and a package
## imports those textures (package_client.py IMPORTED_URI_TEXTURE_FOLDERS).
## GLTFDocument takes such a texture from ResourceLoader and then reads it back
## with get_image(): outside the editor a RenderingServer read, which stalls the
## GPU on the main thread and makes a worker wait for the main thread. Here the
## texture is taken from ResourceLoader exactly as GLTFDocument resolves and
## loads it, the image is pointed at a one-byte data URI with a private
## mimeType for the parse, `_parse_image_data` gives it a 1x1 placeholder, and
## `_import_post_parse` puts the loaded texture back in `state.images` and in
## every material slot that holds the placeholder, and the original URI back in
## the JSON. The materials end with the same texture resource as before, and no
## pixel is read back. A URI ResourceLoader cannot load is left alone, so
## GLTFDocument reads the file's bytes and decodes them as it always has. So
## is every URI of a document whose materials GLTFDocument converts from the
## textures' pixels (spec-gloss, PIXEL_READING_MATERIALS).
##
## Decode role. Embedded images (bufferView and data: URIs: races, hair,
## creatures, held props) are decoded here with GLTFDocument's own fallback
## (the declared PNG/JPEG type first, then PNG, then JPEG; each decoder only on
## bytes with its signature), with no mip chain: the same Image, byte for
## byte. Anything else is left to GLTFDocument. AT-C2 adds the actor VRAM
## sidecars inside this same `_parse_image_data` (its bufferView count skips
## the placeholders above, which are data: URIs); AW-04c adds the CPU-pixel
## capture for the wardrobe on this decode path. Mips on actors are an owner
## decision (AT-C6).
##
## ELORIA_ACTOR_IMAGES=legacy (HardwareTier.actor_images_mode) leaves every
## actor document to plain GLTFDocument, which is exactly the parse before this
## file existed; equipment with imported URI textures is then no longer safe to
## parse on a worker the main thread waits for (see GlbSceneCache "Threads").
##
## State: Godot 4.7.2 does not carry a registered GDScript extension's member
## fields into the import calls, so per-parse state lives in GLTFState
## additional data and process totals in statics behind a mutex. No instance
## fields. Registered once, on the main thread, by
## GltfQuantization.ensure_registered().

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")

## GLTFState flag: this document is an actor glTF (set by `enable`).
const ENABLED := &"rl_actor_document"
## image index -> [original uri, original mimeType or null], placeholdered images.
const URI_ORIGINALS := &"rl_actor_uri_originals"
## image index -> the Texture2D ResourceLoader returned for that image.
const URI_TEXTURES := &"rl_actor_uri_textures"
## Per-parse counters (see `stats`).
const STATS := &"rl_actor_image_stats"
const URI_MIME_PREFIX := "image/x-rl-actor-uri;"
const PLACEHOLDER_URI := "data:application/octet-stream;base64,AA=="
const LEGACY := "legacy"
## Material extensions GLTFDocument 4.7 builds from the textures' pixels while
## it parses (spec-gloss -> metal-rough reads get_image() of both textures).
const PIXEL_READING_MATERIALS: Array[String] = ["KHR_materials_pbrSpecularGlossiness"]
## The PNG file signature and the JPEG start-of-image marker.
const PNG_SIGNATURE: Array[int] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
const JPEG_SIGNATURE: Array[int] = [0xFF, 0xD8]

static var _mode := ""
static var _totals_mutex := Mutex.new()
static var _totals: Dictionary = {}


## Reads the switch once; GltfQuantization.ensure_registered() calls this on
## the main thread before any worker parse. Tests may pass a mode explicitly.
static func configure(mode := "") -> void:
	_mode = mode if not mode.is_empty() else HardwareTier.actor_images_mode()


static func mode() -> String:
	if _mode.is_empty():
		# Only main writes the switch: a worker that gets here before
		# registration reads the environment without caching it.
		if OS.get_thread_caller_id() != OS.get_main_thread_id():
			return HardwareTier.actor_images_mode()
		configure()
	return _mode


## False under ELORIA_ACTOR_IMAGES=legacy: actor documents parse as plain glTF.
static func active() -> bool:
	return mode() != LEGACY


## Marks `state` as an actor document before GLTFDocument parses it. Returns
## whether the extension will act on it. `path` is for AT-C2's sidecar lookup.
static func enable(state: GLTFState, _path := "") -> bool:
	if state == null or not active():
		return false
	state.set_additional_data(ENABLED, true)
	return true


static func is_enabled(state: GLTFState) -> bool:
	var enabled: Variant = state.get_additional_data(ENABLED) if state != null else null
	return typeof(enabled) == TYPE_BOOL and enabled


## This parse's counters: uriTextures (placeholdered, texture from
## ResourceLoader), uriLeft (URIs left to GLTFDocument), decoded,
## decodeFailed (left to GLTFDocument, which reports it). {} when not ours.
static func stats(state: GLTFState) -> Dictionary:
	var value: Variant = state.get_additional_data(STATS) if state != null else null
	return (value as Dictionary).duplicate() if value is Dictionary else {}


## Process totals of the same counters plus `documents`, for diagnostics.
static func totals() -> Dictionary:
	_totals_mutex.lock()
	var copy := _totals.duplicate()
	_totals_mutex.unlock()
	return copy


static func reset_totals() -> void:
	_totals_mutex.lock()
	_totals.clear()
	_totals_mutex.unlock()


## The path GLTFDocument 4.7 resolves a relative image URI to.
static func resolve_uri(base_path: String, uri: String) -> String:
	return base_path.path_join(uri.uri_file_decode()).replace("\\", "/").simplify_path()


## GLTFDocument's own decode of image bytes no extension claimed: the declared
## PNG or JPEG type first, then PNG, then JPEG. A decoder is tried only on bytes
## that carry its signature, which it needs to succeed anyway, and only once,
## so bytes in another format (WebP, KTX) log nothing here: `image` stays empty
## and GLTFDocument then tries and reports the image exactly as it does today.
static func decode(bytes: PackedByteArray, mime_type: String, image: Image) -> void:
	var png := _starts_with(bytes, PNG_SIGNATURE)
	var jpeg := _starts_with(bytes, JPEG_SIGNATURE)
	if mime_type == "image/png" and png:
		image.load_png_from_buffer(bytes)
	elif mime_type == "image/jpeg" and jpeg:
		image.load_jpg_from_buffer(bytes)
	if image.is_empty() and png and mime_type != "image/png":
		image.load_png_from_buffer(bytes)
	if image.is_empty() and jpeg and mime_type != "image/jpeg":
		image.load_jpg_from_buffer(bytes)


static func _starts_with(bytes: PackedByteArray, signature: Array[int]) -> bool:
	if bytes.size() < signature.size():
		return false
	for index: int in signature.size():
		if bytes[index] != signature[index]:
			return false
	return true


## GLTFDocument hands `images[i]` to the materials only in these modes; in the
## Basis mode it rebuilds textures from the source images, and the editor's
## extract mode writes files. A document with a material extension listed in
## PIXEL_READING_MATERIALS is converted from its textures' pixels during the
## parse, so a placeholder there would change the material. Placeholders are
## used only where they are inert.
static func _placeholders_allowed(state: GLTFState) -> bool:
	if Engine.is_editor_hint():
		return false
	var handling := state.get_handle_binary_image_mode()
	if handling != GLTFState.HANDLE_BINARY_IMAGE_MODE_EXTRACT_TEXTURES \
			and handling != GLTFState.HANDLE_BINARY_IMAGE_MODE_EMBED_AS_UNCOMPRESSED:
		return false
	var materials: Variant = state.get_json().get("materials", [])
	if materials is Array:
		for material: Variant in materials:
			var extensions: Variant = (material as Dictionary).get("extensions") if material is Dictionary else null
			if extensions is Dictionary:
				for name: String in PIXEL_READING_MATERIALS:
					if (extensions as Dictionary).has(name):
						return false
	return true


static func _count(state: GLTFState, key: String) -> void:
	var value: Variant = state.get_additional_data(STATS)
	if value is Dictionary:
		(value as Dictionary)[key] = int((value as Dictionary).get(key, 0)) + 1


func _import_preflight(state: GLTFState, _extensions: PackedStringArray) -> Error:
	var enabled: Variant = state.get_additional_data(ENABLED)
	if typeof(enabled) != TYPE_BOOL or not enabled:
		return ERR_SKIP
	var originals: Dictionary = {}
	var textures: Dictionary = {}
	var counters := {"uriTextures": 0, "uriLeft": 0, "decoded": 0, "decodeFailed": 0}
	var images: Variant = state.get_json().get("images", [])
	var base := state.get_base_path()
	if images is Array and _placeholders_allowed(state):
		for index: int in (images as Array).size():
			var descriptor: Variant = (images as Array)[index]
			if not descriptor is Dictionary or not (descriptor as Dictionary).has("uri"):
				continue
			var uri := str((descriptor as Dictionary).uri)
			if uri.begins_with("data:"):
				continue
			# GLTFDocument fails an empty base path itself; leave that to it.
			var path := resolve_uri(base, uri) if not base.is_empty() else ""
			var texture: Texture2D = null
			if not path.is_empty() and ResourceLoader.exists(path):
				texture = ResourceLoader.load(path, "Texture2D") as Texture2D
			if texture == null:
				counters.uriLeft += 1
				continue
			originals[index] = [(descriptor as Dictionary).get("uri"), (descriptor as Dictionary).get("mimeType")]
			textures[index] = texture
			(descriptor as Dictionary)["uri"] = PLACEHOLDER_URI
			(descriptor as Dictionary)["mimeType"] = URI_MIME_PREFIX + str(index)
			counters.uriTextures += 1
	state.set_additional_data(URI_ORIGINALS, originals)
	state.set_additional_data(URI_TEXTURES, textures)
	state.set_additional_data(STATS, counters)
	return OK


## GLTFDocument asks each active extension in turn and keeps the first
## non-empty image; an empty one with OK lets the next one (and finally
## GLTFDocument itself) try.
func _parse_image_data(state: GLTFState, image_data: PackedByteArray, mime_type: String,
		ret_image: Image) -> Error:
	if mime_type.begins_with(URI_MIME_PREFIX):
		ret_image.set_data(1, 1, false, Image.FORMAT_RGBA8, PackedByteArray([0, 0, 0, 0]))
		return OK
	decode(image_data, mime_type, ret_image)
	_count(state, "decodeFailed" if ret_image.is_empty() else "decoded")
	return OK


func _import_post_parse(state: GLTFState) -> Error:
	var originals: Variant = state.get_additional_data(URI_ORIGINALS)
	var textures: Variant = state.get_additional_data(URI_TEXTURES)
	if originals is Dictionary and textures is Dictionary and not (originals as Dictionary).is_empty():
		var descriptors: Array = state.get_json().get("images", [])
		var images := state.get_images()
		var swap: Dictionary = {}
		for index: int in originals:
			var original: Array = (originals as Dictionary)[index]
			var descriptor: Dictionary = descriptors[index]
			descriptor["uri"] = original[0]
			if original[1] == null:
				descriptor.erase("mimeType")
			else:
				descriptor["mimeType"] = original[1]
			var texture: Texture2D = (textures as Dictionary)[index]
			if index < images.size():
				if images[index] != null:
					swap[images[index]] = texture
				images[index] = texture
		state.set_images(images)
		for material: Material in state.get_materials():
			var base_material := material as BaseMaterial3D
			if base_material == null:
				continue
			for slot: int in BaseMaterial3D.TEXTURE_MAX:
				var current := base_material.get_texture(slot)
				if current != null and swap.has(current):
					base_material.set_texture(slot, swap[current])
	# The textures now live in state.images and the materials.
	state.set_additional_data(URI_TEXTURES, {})
	state.set_additional_data(URI_ORIGINALS, {})
	var counters: Variant = state.get_additional_data(STATS)
	if counters is Dictionary:
		_totals_mutex.lock()
		_totals["documents"] = int(_totals.get("documents", 0)) + 1
		for key: String in counters:
			_totals[key] = int(_totals.get(key, 0)) + int((counters as Dictionary)[key])
		_totals_mutex.unlock()
	return OK
