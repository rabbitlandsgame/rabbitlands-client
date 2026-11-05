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
## Embedded role (bufferView images: races, hair, creatures, held props,
## mounts). GLTFDocument hands `_parse_image_data` the bytes of one image at a
## time, in image order, without saying which image they are. The call is
## matched to the first bufferView image after the last one identified whose
## byteLength equals the bytes' size and whose bytes sample equal (the URI
## placeholders above carry their index in their mimeType and are never
## counted). An image GLTFDocument reads from a data: URI or a file comes
## before any later bufferView image, so a call that arrives while such an
## image is next is that image's, never a later bufferView image's even when
## their bytes are the same: it is decoded as below and moves the match past
## it (`_other_images`). For a matched image:
##   * sha = SHA-256 of the bytes, the only hash of the source.
##   * Sidecar: the GLB directory's `vram/index.json` (written offline by
##     tools/build_vram_textures.py --actor-dir, shipped by AT-C3) lists sha,
##     the renderer samples its format and the entry was encoded for every
##     role this document samples the image in (VramTextures.sidecar_fits): the
##     image is that sidecar, BC7 / BC5 / BC1 with its whole mip chain, checked
##     as the map sidecars are (VramTextures.decode_sidecar: file sha256,
##     header, size, DDS dimensions, format and mips against the index). Any
##     doubt decodes the bytes instead and warns once per sha.
##   * Otherwise the bytes are decoded as below, with no mip chain (the
##     fallback CPU chain is the owner's call, AT plan question 4; see
##     FALLBACK_MIPS).
##   * Pool: one texture per (sha, variant, mip skip) in this process, held
##     weakly, so GLBs that embed the same image (16 race bodies on two
##     atlases, 162 legacy hair GLBs on four images) share one upload. A live
##     pool entry turns the image into a 1x1 placeholder that
##     `_import_post_parse` replaces, in `state.images` and every material
##     slot, by the pooled texture.
##   * `_import_post_parse` first checks that every image it produced is where
##     it expects it (size and format); on any disagreement it publishes
##     nothing and keeps the parse's own textures (warned, counted
##     `checkFailed`). It then publishes each new texture, or adopts the one
##     another parse published first, and tags it with `rl_image_sha` and
##     `rl_image_variant` for its consumers (AT-C4).
## A directory without an index - every dev checkout that never staged
## sidecars, and every release until AT-C3's sidecars are release-enabled -
## gets exactly today's pixels: decoded, no mips, now shared by sha.
##
## Decode role (also data: URIs and loose files no bufferView matches): the
## declared PNG/JPEG type first, then PNG, then JPEG, each decoder only on
## bytes with its signature, with no mip chain: GLTFDocument's own fallback,
## the same Image byte for byte. Anything else is left to GLTFDocument.
## AW-04c adds the CPU-pixel capture for the wardrobe on this decode path.
##
## Discard (`enable(state, path, true)`, animation-library parses, AT-C4):
## every image GLTFDocument hands over (embedded, data: and loose files)
## becomes a 1x1 placeholder and nothing is recorded; URI textures are still
## taken from ResourceLoader as above.
##
## ELORIA_ACTOR_IMAGES (HardwareTier.actor_images_mode): legacy leaves every
## actor document to plain GLTFDocument, which is exactly the parse before this
## file existed; equipment with imported URI textures is then no longer safe to
## parse on a worker the main thread waits for (see GlbSceneCache "Threads").
## nomips keeps decoded images without a CPU mip chain whatever FALLBACK_MIPS
## says. ELORIA_VRAM_TEXTURES=0 turns the sidecars off (map and actor alike).
## ELORIA_ACTOR_VRAM_SELF_TEST=<dir> logs `self_test(dir)` at registration,
## for the package smoke launch (AT-C3).
##
## State: Godot 4.7.2 does not carry a registered GDScript extension's member
## fields into the import calls, so per-parse state lives in GLTFState
## additional data and process state in statics behind mutexes that are never
## held across a RenderingServer call. No instance fields. Registered once, on
## the main thread, by GltfQuantization.ensure_registered().

const HardwareTier := preload("res://src/runtime/hardware_tier.gd")
const VramTextures := preload("res://src/world/vram_textures.gd")
const GraphicsOptions := preload("res://src/world/graphics_options.gd")
const ResourceBytes := preload("res://src/runtime/resource_bytes.gd")

## GLTFState flag: this document is an actor glTF (set by `enable`).
const ENABLED := &"rl_actor_document"
## GLTFState flag: images become 1x1 placeholders (`enable` discard).
const DISCARD := &"rl_actor_discard"
## Whether placeholders, sidecars and pooled textures are inert in this parse
## (`_placeholders_allowed`, read once in preflight).
const ALLOWED := &"rl_actor_placeholders_allowed"
## image index -> [original uri, original mimeType or null], placeholdered images.
const URI_ORIGINALS := &"rl_actor_uri_originals"
## image index -> the Texture2D ResourceLoader returned for that image.
const URI_TEXTURES := &"rl_actor_uri_textures"
## Per-parse counters (see `stats`).
const STATS := &"rl_actor_image_stats"
## The document's bufferView images in image order: [image index, buffer,
## byteOffset, byteLength] each; empty where placeholders are not inert.
const EMBEDDED := &"rl_actor_embedded"
## The other images GLTFDocument reads bytes for, in image order (a
## PackedInt32Array of image indices: data: URIs with a payload, files
## ResourceLoader did not load; `_other_images`); empty where placeholders are
## not inert.
const OTHERS := &"rl_actor_others"
## The last image index a `_parse_image_data` call was identified as.
const CURSOR := &"rl_actor_cursor"
## image index -> {role: true} (VramTextures.image_roles), on first need.
const ROLES := &"rl_actor_roles"
## The GLB directory's sidecar index (VramTextures.index_for_directory), on first need.
const INDEX := &"rl_actor_index"
## image index -> what `_parse_image_data` produced for it: {sha, key, kind
## ("sidecar" | "decoded" | "pooled"), width, height, format, mipmaps,
## texture (pooled only)}.
const PRODUCED := &"rl_actor_produced"
const URI_MIME_PREFIX := "image/x-rl-actor-uri;"
const PLACEHOLDER_URI := "data:application/octet-stream;base64,AA=="
const LEGACY := "legacy"
const NOMIPS := "nomips"
## Texture metadata for consumers (AT-C4): the source image's sha256 and the
## pool key of the variant uploaded for it.
const META_SHA := &"rl_image_sha"
const META_VARIANT := &"rl_image_variant"
## Owner decision pending (AT plan question 4, the AT-C6 visual pack): decoded
## actor images (no sidecar, or a refused one) keep today's single level. True
## would give them a CPU mip chain (+33 % of their memory, less shimmer).
const FALLBACK_MIPS := false
## Bytes of a matched image compared directly; larger ones are compared at
## PROBES evenly spaced bytes plus their first and last EDGE bytes.
const FULL_COMPARE_BYTES := 4096
const PROBES := 64
const EDGE := 32
## Material extensions GLTFDocument 4.7 builds from the textures' pixels while
## it parses (spec-gloss -> metal-rough reads get_image() of both textures).
const PIXEL_READING_MATERIALS: Array[String] = ["KHR_materials_pbrSpecularGlossiness"]
## The PNG file signature and the JPEG start-of-image marker.
const PNG_SIGNATURE: Array[int] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
const JPEG_SIGNATURE: Array[int] = [0xFF, 0xD8]

static var _mode := ""
static var _fallback_mips := FALLBACK_MIPS
static var _totals_mutex := Mutex.new()
static var _totals: Dictionary = {}
## Pool: key -> WeakRef(ImageTexture), key -> its estimated GPU bytes.
static var _pool_mutex := Mutex.new()
static var _pool: Dictionary = {}
static var _pool_bytes: Dictionary = {}
static var _pool_hits := 0
static var _pool_publications := 0
static var _pool_adoptions := 0
## Shas already warned about, so a broken sidecar says so once.
static var _warned: Dictionary = {}


## Reads the switch once; GltfQuantization.ensure_registered() calls this on
## the main thread before any worker parse. Tests may pass a mode explicitly.
static func configure(mode := "") -> void:
	_mode = mode if not mode.is_empty() else HardwareTier.actor_images_mode()


## Main thread, once, at registration: reads the sidecar formats the renderer
## samples (a worker asking first would get none and decode) and logs the
## package self-test line when ELORIA_ACTOR_VRAM_SELF_TEST names a directory.
static func prime() -> void:
	VramTextures.usable_formats()
	var directory := HardwareTier.actor_vram_self_test_dir()
	if not directory.is_empty():
		print(self_test(directory))


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


## Whether decoded actor images get a CPU mip chain (FALLBACK_MIPS, never
## under nomips, never in the browser build, which publishes no sidecars).
static func fallback_mips() -> bool:
	return _fallback_mips and mode() != NOMIPS and not OS.has_feature("web")


## Tests and the AT-C6 measurement only: overrides FALLBACK_MIPS.
static func set_fallback_mips(enabled: bool) -> void:
	_fallback_mips = enabled


## Mip levels dropped from actor images. 0: Low and High hold the same actor
## textures until the owner decides AT-C5.
static func texture_skip() -> int:
	return 0


## Whether actor textures parsed from `directory` may carry a mip chain: its
## sidecar index lists images, or decoded images get FALLBACK_MIPS. Without
## either they are single-level, as before (GlbSceneCache's ledger).
static func may_have_mipmaps(directory: String) -> bool:
	if not active():
		return false
	if fallback_mips():
		return true
	if directory.is_empty() or VramTextures.mode() == VramTextures.Mode.OFF:
		return false
	var info := VramTextures.index_for_directory(directory)
	return str(info.status) == "ok" and int(info.entries) > 0


## Marks `state` as an actor document before GLTFDocument parses it. Returns
## whether the extension will act on it. With `discard` (a parse that only
## wants skeletons and animations) its images become 1x1 placeholders.
## The sidecars are looked up beside the document (state.get_base_path()).
static func enable(state: GLTFState, _path := "", discard := false) -> bool:
	if state == null or not active():
		return false
	state.set_additional_data(ENABLED, true)
	if discard:
		state.set_additional_data(DISCARD, true)
	return true


static func is_enabled(state: GLTFState) -> bool:
	var enabled: Variant = state.get_additional_data(ENABLED) if state != null else null
	return typeof(enabled) == TYPE_BOOL and enabled


## This parse's counters: uriTextures (placeholdered, texture from
## ResourceLoader), uriLeft (URIs left to GLTFDocument), decoded,
## decodeFailed (left to GLTFDocument, which reports it), sidecar (uploaded
## from a sidecar), pooled (a live pooled texture, nothing decoded),
## sidecarRejected (a sidecar file refused: decoded instead),
## sidecarRoleMismatch (indexed for other roles: decoded instead),
## sidecarUnsupported (a format this renderer cannot sample: decoded instead),
## unmatched (image bytes no bufferView image matched - data: URIs, loose
## files: decoded, not pooled),
## discarded, published, adopted, checkFailed, gpuBytes (estimated, the
## textures this parse uploaded). {} when not ours.
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


## `totals()` plus the pool: weak slots, live entries and their estimated GPU
## bytes, hits, publications and concurrent adoptions. No readback, file IO or
## strong reference (GlbSceneCache.retention_snapshot "actor_images").
static func retention_snapshot() -> Dictionary:
	var result := totals()
	_pool_mutex.lock()
	var live := 0
	var live_bytes := 0
	for key: String in _pool:
		var reference: WeakRef = _pool[key]
		if reference != null and reference.get_ref() != null:
			live += 1
			live_bytes += int(_pool_bytes.get(key, 0))
	result["pool"] = {"slots": _pool.size(), "live_entries": live, "bytes": live_bytes,
		"hits": _pool_hits, "publications": _pool_publications, "adoptions": _pool_adoptions}
	_pool_mutex.unlock()
	return result


## Tests: forgets the pool (live textures stay with their holders) and the
## warnings.
static func reset_pool() -> void:
	_pool_mutex.lock()
	_pool.clear()
	_pool_bytes.clear()
	_pool_hits = 0
	_pool_publications = 0
	_pool_adoptions = 0
	_warned.clear()
	_pool_mutex.unlock()


## The pool key of one image: its sha, the variant ("evt:<sidecar sha256>:
## <recipe>:<format>" for a sidecar, "decoded" or "decoded+cpu-mips"
## otherwise) and the mip skip.
static func pool_key(sha: String, entry: Dictionary = {}, skip := 0, mips := false) -> String:
	var variant := ("decoded+cpu-mips" if mips else "decoded") if entry.is_empty() else "evt:%s:%s:%s" % [
		str(entry.get("sha256", "")), str(entry.get("recipe", "")), str(entry.get("format", ""))]
	return "%s|%s|mip-skip=%d" % [sha, variant, skip]


## The live pooled texture of `key`, or null.
static func pooled(key: String) -> ImageTexture:
	_pool_mutex.lock()
	var reference: WeakRef = _pool.get(key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
	_pool_mutex.unlock()
	return shared


## Publishes `candidate` for `key` unless a live texture holds it already, in
## which case that one wins and is returned (the caller replaces its own).
static func _publish_or_adopt(key: String, candidate: ImageTexture, bytes: int) -> ImageTexture:
	_pool_mutex.lock()
	var reference: WeakRef = _pool.get(key)
	var shared: ImageTexture = reference.get_ref() as ImageTexture if reference != null else null
	if shared == null:
		_pool[key] = weakref(candidate)
		_pool_bytes[key] = bytes
		_pool_publications += 1
		shared = candidate
	else:
		_pool_adoptions += 1
	_pool_mutex.unlock()
	return shared


static func _note_pool_hit() -> void:
	_pool_mutex.lock()
	_pool_hits += 1
	_pool_mutex.unlock()


static func _warn_once(sha: String, message: String) -> void:
	_pool_mutex.lock()
	var fresh := not _warned.has(sha)
	_warned[sha] = true
	_pool_mutex.unlock()
	if fresh:
		push_warning(message)


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


static func sha256(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()


## GLTFDocument hands `images[i]` to the materials only in these modes; in the
## Basis mode it rebuilds textures from the source images, and the editor's
## extract mode writes files. A document with a material extension listed in
## PIXEL_READING_MATERIALS is converted from its textures' pixels during the
## parse, so a placeholder there would change the material. Placeholders are
## used only where they are inert, and so are sidecars and pooled textures.
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


static func _count(state: GLTFState, key: String, amount := 1) -> void:
	var value: Variant = state.get_additional_data(STATS)
	if value is Dictionary:
		(value as Dictionary)[key] = int((value as Dictionary).get(key, 0)) + amount


## The bufferView images of `document` (GLTFDocument reads an image with a
## `uri` from the URI, so those are not), in image order.
static func _embedded_images(document: Dictionary) -> Array:
	var out: Array = []
	var images: Variant = document.get("images", [])
	var views: Variant = document.get("bufferViews", [])
	if not images is Array or not views is Array:
		return out
	for index: int in (images as Array).size():
		var descriptor: Variant = (images as Array)[index]
		if not descriptor is Dictionary or (descriptor as Dictionary).has("uri") \
				or not typeof((descriptor as Dictionary).get("bufferView")) in [TYPE_INT, TYPE_FLOAT]:
			continue
		var view_index := int((descriptor as Dictionary).bufferView)
		if view_index < 0 or view_index >= (views as Array).size() or not (views as Array)[view_index] is Dictionary:
			continue
		var view: Dictionary = (views as Array)[view_index]
		out.append([index, int(view.get("buffer", 0)), int(view.get("byteOffset", 0)), int(view.get("byteLength", 0))])
	return out


## The images of `document` that are neither bufferView images nor URI
## placeholders but whose bytes GLTFDocument 4.7 reads and hands to
## `_parse_image_data`: a data: URI with a payload, and a URI ResourceLoader
## did not load whose file has bytes (GLTFDocument skips an empty or missing
## one without asking). In image order. Call after the URI rewrite.
static func _other_images(document: Dictionary, base: String) -> PackedInt32Array:
	var out := PackedInt32Array()
	var images: Variant = document.get("images", [])
	if not images is Array:
		return out
	for index: int in (images as Array).size():
		var descriptor: Variant = (images as Array)[index]
		if not descriptor is Dictionary or not (descriptor as Dictionary).has("uri"):
			continue
		if str((descriptor as Dictionary).get("mimeType", "")).begins_with(URI_MIME_PREFIX):
			continue
		var uri := str((descriptor as Dictionary).uri)
		if uri.begins_with("data:"):
			var comma := uri.find(",")
			if comma >= 0 and comma < uri.length() - 1:
				out.append(index)
			continue
		if base.is_empty():
			continue
		var path := resolve_uri(base, uri)
		if not FileAccess.file_exists(path):
			continue
		var file := FileAccess.open(path, FileAccess.READ)
		if file != null and file.get_length() > 0:
			out.append(index)
	return out


## The first image of OTHERS after `cursor`, or -1.
static func _next_other(state: GLTFState, cursor: int) -> int:
	var others: Variant = state.get_additional_data(OTHERS)
	if others is PackedInt32Array:
		for index: int in others:
			if index > cursor:
				return index
	return -1


## The image index of the bufferView image these bytes are, or -1: the first
## one after the last identified call whose length matches and whose bytes
## sample equal (`_same_bytes`), unless an image read from a data: URI or a
## file (OTHERS) comes before it. Calls arrive in image order (4.7.2), so the
## bytes are then that image's: the call matches nothing and the match moves
## past that image. A matched image is never matched again.
static func _match(state: GLTFState, bytes: PackedByteArray) -> int:
	var embedded: Variant = state.get_additional_data(EMBEDDED)
	if not embedded is Array or (embedded as Array).is_empty() or bytes.is_empty():
		return -1
	var cursor := _cursor(state)
	var next_other := _next_other(state, cursor)
	var buffers: Array = state.get_buffers()
	for candidate: Array in embedded:
		var index := int(candidate[0])
		if index <= cursor:
			continue
		if next_other >= 0 and index > next_other:
			break
		if int(candidate[3]) != bytes.size():
			continue
		var buffer_index := int(candidate[1])
		if buffer_index < 0 or buffer_index >= buffers.size():
			continue
		if _same_bytes(buffers[buffer_index], int(candidate[2]), bytes):
			state.set_additional_data(CURSOR, index)
			return index
	if next_other >= 0:
		state.set_additional_data(CURSOR, next_other)
	return -1


static func _cursor(state: GLTFState) -> int:
	var cursor: Variant = state.get_additional_data(CURSOR)
	return int(cursor) if typeof(cursor) in [TYPE_INT, TYPE_FLOAT] else -1


## Whether `buffer` holds `bytes` at `offset`: every byte of a small image,
## otherwise its first and last EDGE bytes and PROBES evenly spaced ones
## (compressed images of equal length that agree on all of those do not
## occur; the post-parse check still guards the result).
static func _same_bytes(buffer: PackedByteArray, offset: int, bytes: PackedByteArray) -> bool:
	var size := bytes.size()
	if offset < 0 or offset + size > buffer.size():
		return false
	if size <= FULL_COMPARE_BYTES:
		return buffer.slice(offset, offset + size) == bytes
	for index: int in EDGE:
		if buffer[offset + index] != bytes[index] or buffer[offset + size - 1 - index] != bytes[size - 1 - index]:
			return false
	for probe: int in PROBES:
		var at := EDGE + int((size - 2 * EDGE) * (probe + 0.5) / PROBES)
		if buffer[offset + at] != bytes[at]:
			return false
	return true


static func _directory_index(state: GLTFState) -> Dictionary:
	var known: Variant = state.get_additional_data(INDEX)
	if known is Dictionary:
		return known
	var directory := state.get_base_path()
	var info: Dictionary = {"status": "none", "entries": 0, "images": {}}
	if not directory.is_empty() and VramTextures.mode() != VramTextures.Mode.OFF:
		info = VramTextures.index_for_directory(directory)
	state.set_additional_data(INDEX, info)
	return info


static func _roles(state: GLTFState) -> Dictionary:
	var known: Variant = state.get_additional_data(ROLES)
	if known is Dictionary:
		return known
	var roles := VramTextures.image_roles(state.get_json())
	state.set_additional_data(ROLES, roles)
	return roles


## The index entry that may stand for image `index` (sha `sha`) here, or {}:
## listed beside the document, a format this renderer samples, encoded for
## every role this document samples the image in. A refusal is counted and
## warned once per sha; the caller decodes.
static func _sidecar(state: GLTFState, index: int, sha: String) -> Dictionary:
	var info := _directory_index(state)
	if str(info.get("status", "")) != "ok" or int(info.get("entries", 0)) == 0 \
			or not (info.images as Dictionary).has(sha):
		return {}
	var directory := state.get_base_path()
	var entry := VramTextures.sidecar_entry(sha, directory)
	if entry.is_empty():
		_count(state, "sidecarUnsupported")
		return {}
	var roles: Dictionary = _roles(state).get(index, {})
	if not VramTextures.sidecar_fits(entry, roles):
		_count(state, "sidecarRoleMismatch")
		VramTextures.note_decoded_instead(sha)
		_warn_once(sha, "actor_images: %s samples an image as %s, which sidecar %s was not encoded for; decoding it" % [
			directory, "+".join(PackedStringArray(roles.keys())), str(entry.file)])
		return {}
	return entry


static func _placeholder(image: Image) -> void:
	image.set_data(1, 1, false, Image.FORMAT_RGBA8, PackedByteArray([0, 0, 0, 0]))


static func _record(state: GLTFState, index: int, record: Dictionary) -> void:
	var produced: Variant = state.get_additional_data(PRODUCED)
	if produced is Dictionary:
		(produced as Dictionary)[index] = record


static func _image_record(sha: String, key: String, kind: String, image: Image) -> Dictionary:
	return {"sha": sha, "key": key, "kind": kind, "width": image.get_width(), "height": image.get_height(),
		"format": image.get_format(), "mipmaps": image.has_mipmaps()}


## Fills `image` for bufferView image `index`: a pooled placeholder, its
## sidecar, or its decode (left empty when that fails, for GLTFDocument).
static func _produce(state: GLTFState, index: int, bytes: PackedByteArray, mime_type: String, image: Image) -> void:
	var sha := sha256(bytes)
	var skip := texture_skip()
	var entry := _sidecar(state, index, sha)
	if not entry.is_empty():
		var key := pool_key(sha, entry, skip)
		var shared := pooled(key)
		if shared != null:
			_reuse(state, index, sha, key, shared, image)
			return
		var loaded := VramTextures.decode_sidecar(entry)
		if loaded.image != null:
			image.copy_from(GraphicsOptions.reduced_image(loaded.image, skip))
			_record(state, index, _image_record(sha, key, "sidecar", image))
			_count(state, "sidecar")
			return
		_count(state, "sidecarRejected")
		VramTextures.note_decoded_instead(sha)
		_warn_once(sha, "actor_images: sidecar %s unusable (%s); decoding the embedded image" % [
			str(entry.file), str(loaded.reason)])
	var mips := fallback_mips()
	var decoded_key := pool_key(sha, {}, skip, mips)
	var decoded_shared := pooled(decoded_key)
	if decoded_shared != null:
		_reuse(state, index, sha, decoded_key, decoded_shared, image)
		return
	decode(bytes, mime_type, image)
	if image.is_empty():
		_count(state, "decodeFailed")
		return
	if mips and not image.has_mipmaps():
		image.generate_mipmaps()
	if skip > 0:
		image.copy_from(GraphicsOptions.reduced_image(image, skip))
	_record(state, index, _image_record(sha, decoded_key, "decoded", image))
	_count(state, "decoded")


static func _reuse(state: GLTFState, index: int, sha: String, key: String, shared: ImageTexture, image: Image) -> void:
	_placeholder(image)
	var record := _image_record(sha, key, "pooled", image)
	record["texture"] = shared
	_record(state, index, record)
	_count(state, "pooled")
	_note_pool_hit()


## Whether `texture` is what `record` says this parse produced at its index.
static func _matches(texture: Texture2D, record: Dictionary) -> bool:
	var image_texture := texture as ImageTexture
	return image_texture != null and image_texture.get_width() == int(record.width) \
		and image_texture.get_height() == int(record.height) and image_texture.get_format() == int(record.format)


func _import_preflight(state: GLTFState, _extensions: PackedStringArray) -> Error:
	var enabled: Variant = state.get_additional_data(ENABLED)
	if typeof(enabled) != TYPE_BOOL or not enabled:
		return ERR_SKIP
	var originals: Dictionary = {}
	var textures: Dictionary = {}
	var counters := {"uriTextures": 0, "uriLeft": 0, "decoded": 0, "decodeFailed": 0, "sidecar": 0, "pooled": 0,
		"sidecarRejected": 0, "sidecarRoleMismatch": 0, "sidecarUnsupported": 0, "unmatched": 0,
		"discarded": 0, "published": 0, "adopted": 0, "checkFailed": 0, "gpuBytes": 0}
	var images: Variant = state.get_json().get("images", [])
	var base := state.get_base_path()
	var allowed := _placeholders_allowed(state)
	if images is Array and allowed:
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
	# After the URI rewrite: placeholders carry a uri, so they are never
	# counted among the bufferView images.
	state.set_additional_data(ALLOWED, allowed)
	state.set_additional_data(EMBEDDED, _embedded_images(state.get_json()) if allowed else [])
	state.set_additional_data(OTHERS, _other_images(state.get_json(), base) if allowed else PackedInt32Array())
	state.set_additional_data(CURSOR, -1)
	state.set_additional_data(PRODUCED, {})
	return OK


## GLTFDocument asks each active extension in turn and keeps the first
## non-empty image; an empty one with OK lets the next one (and finally
## GLTFDocument itself) try.
func _parse_image_data(state: GLTFState, image_data: PackedByteArray, mime_type: String,
		ret_image: Image) -> Error:
	if mime_type.begins_with(URI_MIME_PREFIX):
		_placeholder(ret_image)
		var at := mime_type.trim_prefix(URI_MIME_PREFIX)
		if at.is_valid_int() and int(at) > _cursor(state):
			state.set_additional_data(CURSOR, int(at))
		return OK
	var discard: Variant = state.get_additional_data(DISCARD)
	var allowed: Variant = state.get_additional_data(ALLOWED)
	if typeof(discard) == TYPE_BOOL and discard and typeof(allowed) == TYPE_BOOL and allowed:
		_placeholder(ret_image)
		_count(state, "discarded")
		return OK
	var index := _match(state, image_data)
	if index >= 0:
		_produce(state, index, image_data, mime_type, ret_image)
		return OK
	_count(state, "unmatched")
	decode(image_data, mime_type, ret_image)
	_count(state, "decodeFailed" if ret_image.is_empty() else "decoded")
	return OK


func _import_post_parse(state: GLTFState) -> Error:
	var images := state.get_images()
	var swap: Dictionary = {}
	# Whether `images` gained a texture (a URI texture can replace a null slot,
	# which `swap` does not record).
	var changed := false
	var originals: Variant = state.get_additional_data(URI_ORIGINALS)
	var textures: Variant = state.get_additional_data(URI_TEXTURES)
	if originals is Dictionary and textures is Dictionary and not (originals as Dictionary).is_empty():
		var descriptors: Array = state.get_json().get("images", [])
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
				changed = true
	var produced: Variant = state.get_additional_data(PRODUCED)
	if produced is Dictionary and not (produced as Dictionary).is_empty():
		_settle(state, images, produced as Dictionary, swap)
	if changed or not swap.is_empty():
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
	state.set_additional_data(PRODUCED, {})
	state.set_additional_data(EMBEDDED, [])
	state.set_additional_data(OTHERS, PackedInt32Array())
	var counters: Variant = state.get_additional_data(STATS)
	if counters is Dictionary:
		_totals_mutex.lock()
		_totals["documents"] = int(_totals.get("documents", 0)) + 1
		for key: String in counters:
			_totals[key] = int(_totals.get(key, 0)) + int((counters as Dictionary)[key])
		_totals_mutex.unlock()
	return OK


## The embedded role's post-parse (see the header): check, then swap pooled
## textures in and publish or adopt new ones, recording each swap in `swap`.
static func _settle(state: GLTFState, images: Array[Texture2D], produced: Dictionary, swap: Dictionary) -> void:
	var consistent := true
	for index: int in produced:
		if index >= images.size() or not _matches(images[index], produced[index]):
			consistent = false
	if not consistent:
		_count(state, "checkFailed")
		push_warning("actor_images: %s: a parsed image is not where its bytes were matched; publishing nothing" % [
			state.get_base_path().path_join(state.filename)])
	for index: int in produced:
		var record: Dictionary = produced[index]
		if index >= images.size() or not _matches(images[index], record):
			continue
		var current := images[index] as ImageTexture
		if record.kind == "pooled":
			swap[current] = record.texture
			images[index] = record.texture
			continue
		if not consistent:
			continue
		current.set_meta(META_SHA, record.sha)
		current.set_meta(META_VARIANT, record.key)
		var bytes := ResourceBytes.texture_bytes(current,
			ResourceBytes.MIPMAPS_FULL if bool(record.mipmaps) else ResourceBytes.MIPMAPS_NONE)
		var shared := _publish_or_adopt(str(record.key), current, bytes)
		if shared != current:
			swap[current] = shared
			images[index] = shared
			_count(state, "adopted")
		else:
			_count(state, "published")
			_count(state, "gpuBytes", bytes)


## Decodes the smallest sidecar of `directory`'s actor index (a path below
## res://, such as assets/actors/native/races, or absolute) and decompresses a
## copy, for the package smoke launch: the shipped binary reads what the tool
## wrote and can turn BC back into pixels (the wardrobe dye reads its atlas).
static func self_test(directory: String) -> String:
	var source := directory if directory.begins_with("res://") or directory.begins_with("user://") \
		or directory.is_absolute_path() else "res://" + directory.trim_prefix("/")
	var info := VramTextures.index_for_directory(source)
	if str(info.status) != "ok" or int(info.entries) == 0:
		return "actor_images self_test failed dir=%s index=%s" % [directory, str(info.status)]
	var smallest: Dictionary = {}
	for entry: Dictionary in (info.images as Dictionary).values():
		if smallest.is_empty() or int(entry.fileBytes) < int(smallest.fileBytes):
			smallest = entry
	var loaded := VramTextures.decode_sidecar(smallest)
	if loaded.image == null:
		return "actor_images self_test failed %s %s" % [str(smallest.file), str(loaded.reason)]
	var image: Image = loaded.image
	var copy := Image.new()
	copy.copy_from(image)
	var decompressed := copy.decompress() == OK and not copy.is_compressed() and not copy.is_empty()
	return "actor_images self_test ok entries=%d format=%s mips=%d decompress=%s" % [int(info.entries),
		str(smallest.format), image.get_mipmap_count(), "ok" if decompressed else "failed"]
