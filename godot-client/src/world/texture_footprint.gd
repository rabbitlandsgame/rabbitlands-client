extends RefCounted
## What a model's textures will hold on the GPU, read from the image headers
## alone (no decode): width x height x 4 bytes, plus a third for the mip chain.
##
## WorldPark's memory budget needs an interior's size before it builds it. The
## old guess (the GLB's size on disk x 3 + 32 MiB) said 34 MiB for Landfall
## Town, whose 818 KB shell GLB names 22 external images and whose 64 scenery
## GLBs embed 66.8 Mpx between them: 424 MiB measured once built (review,
## 2026-10-27). An image with a VRAM sidecar this client would upload for
## every role the GLB samples it in counts the sidecar's own `gpuBytes`
## (BC1/BC5/BC7 with its mips): a map image beside the GLB by its sha256 file
## name (vram_textures.gd), an embedded one by the sha256 of its bytes
## (world_object_images.gd: the town's scenery). Every other image counts as
## the RGBA8 the client decodes it to, so the estimate errs high, never low.
## Reads files only (no RenderingServer): safe on a worker thread, where it
## runs (WorldPark); VramTextures.usable_formats() must have been asked on the
## main thread first, or every sidecar counts as decoded.
const BYTES_PER_PIXEL := 4
## A full mip chain adds a third.
const MIP_NUMERATOR := 4
const MIP_DENOMINATOR := 3
## Header bytes read per image: a PNG or WebP states its size in the first 30,
## a JPEG in its frame header after any metadata.
const HEADER_BYTES := 65536

const VramTextures := preload("res://src/world/vram_textures.gd")

const GLB_MAGIC := 0x46546C67
const CHUNK_JSON := 0x4E4F534A

## Bytes a `width` x `height` RGBA texture with mipmaps holds.
static func texture_bytes(size: Vector2i) -> int:
	return maxi(0, size.x) * maxi(0, size.y) * BYTES_PER_PIXEL * MIP_NUMERATOR / MIP_DENOMINATOR

static func _be16(bytes: PackedByteArray, at: int) -> int:
	return (bytes[at] << 8) | bytes[at + 1]

static func _be32(bytes: PackedByteArray, at: int) -> int:
	return (bytes[at] << 24) | (bytes[at + 1] << 16) | (bytes[at + 2] << 8) | bytes[at + 3]

static func _le24(bytes: PackedByteArray, at: int) -> int:
	return bytes[at] | (bytes[at + 1] << 8) | (bytes[at + 2] << 16)

## An encoded image's pixel size from its header (PNG, JPEG, WebP), or
## Vector2i.ZERO when the bytes are none of those or are cut short.
static func header_size(bytes: PackedByteArray) -> Vector2i:
	var size := bytes.size()
	if size >= 24 and bytes[0] == 0x89 and bytes[1] == 0x50 and bytes[2] == 0x4E and bytes[3] == 0x47:
		return Vector2i(_be32(bytes, 16), _be32(bytes, 20))
	if size >= 30 and bytes.slice(0, 4).get_string_from_ascii() == "RIFF" \
			and bytes.slice(8, 12).get_string_from_ascii() == "WEBP":
		var chunk := bytes.slice(12, 16).get_string_from_ascii()
		if chunk == "VP8X":
			return Vector2i(_le24(bytes, 24) + 1, _le24(bytes, 27) + 1)
		if chunk == "VP8 " and bytes[23] == 0x9D and bytes[24] == 0x01 and bytes[25] == 0x2A:
			return Vector2i((bytes[26] | (bytes[27] << 8)) & 0x3FFF, (bytes[28] | (bytes[29] << 8)) & 0x3FFF)
		if chunk == "VP8L" and bytes[20] == 0x2F:
			var bits := bytes[21] | (bytes[22] << 8) | (bytes[23] << 16) | (bytes[24] << 24)
			return Vector2i((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
		return Vector2i.ZERO
	if size >= 4 and bytes[0] == 0xFF and bytes[1] == 0xD8:
		var at := 2
		while at + 9 < size:
			if bytes[at] != 0xFF:
				at += 1
				continue
			var marker := bytes[at + 1]
			if marker == 0xFF:
				at += 1
				continue
			# Start of frame (baseline, progressive, ...): not DHT C4, JPG C8, DAC CC.
			if marker >= 0xC0 and marker <= 0xCF and marker != 0xC4 and marker != 0xC8 and marker != 0xCC:
				return Vector2i(_be16(bytes, at + 7), _be16(bytes, at + 5))
			if marker == 0xD8 or marker == 0x01 or (marker >= 0xD0 and marker <= 0xD7):
				at += 2
				continue
			at += 2 + _be16(bytes, at + 2)
	return Vector2i.ZERO

## The texture bytes of every image a glTF binary names - embedded in its BIN
## chunk or beside it by URI - counting each distinct image once. `seen` (by
## absolute path or "<glb>#<index>") is shared across calls so an image two
## models name is counted once. 0 for a file that is not a readable GLB.
static func glb_texture_bytes(glb_path: String, seen: Dictionary = {}) -> int:
	var file := FileAccess.open(glb_path, FileAccess.READ)
	if file == null or file.get_length() < 20 or file.get_32() != GLB_MAGIC:
		return 0
	file.get_32()
	file.get_32()
	var json_length := file.get_32()
	if file.get_32() != CHUNK_JSON or json_length <= 0 or json_length > file.get_length():
		return 0
	var parsed: Variant = JSON.parse_string(file.get_buffer(json_length).get_string_from_utf8())
	if parsed is not Dictionary:
		return 0
	var document := parsed as Dictionary
	# The BIN chunk's data starts after its own 8-byte header.
	var binary_start := 20 + json_length + 8
	var views: Array = document.get("bufferViews", [])
	var total := 0
	var images: Array = document.get("images", [])
	# Embedded images have sidecars only where the GLB's folder has an index.
	var directory := glb_path.get_base_dir()
	var index_info := VramTextures.index_for_directory(directory)
	var indexed := str(index_info.status) == "ok" and int(index_info.entries) > 0
	var roles := VramTextures.image_roles(document)
	for index: int in images.size():
		var image: Variant = images[index]
		if image is not Dictionary:
			continue
		var header := PackedByteArray()
		var key := ""
		var uri := str((image as Dictionary).get("uri", ""))
		if not uri.is_empty():
			if uri.begins_with("data:"):
				continue
			key = glb_path.get_base_dir().path_join(uri.uri_decode()).simplify_path()
			if seen.has(key):
				continue
			# A content-addressed map image (<sha256>.<ext>) with a sidecar the
			# renderer takes is uploaded compressed, at the index's own size.
			var sha := key.get_file().get_basename()
			if sha.length() == 64 and sha.is_valid_hex_number():
				var sidecar := _usable_sidecar(sha, key.get_base_dir(), roles.get(index, {}))
				if sidecar > 0:
					seen[key] = true
					total += sidecar
					continue
			var source := FileAccess.open(key, FileAccess.READ)
			if source == null:
				continue
			header = source.get_buffer(mini(HEADER_BYTES, source.get_length()))
		else:
			var view_index: Variant = (image as Dictionary).get("bufferView")
			if (view_index is not int and view_index is not float) or int(view_index) >= views.size():
				continue
			var view: Dictionary = views[int(view_index)]
			key = "%s#%d" % [glb_path, index]
			if seen.has(key):
				continue
			file.seek(binary_start + int(view.get("byteOffset", 0)))
			var length := int(view.get("byteLength", 0))
			if indexed and length > 0:
				# The whole image, for the sha256 its sidecar is keyed by.
				header = file.get_buffer(length)
				var sidecar := _usable_sidecar(_sha256(header), directory, roles.get(index, {}))
				if sidecar > 0:
					seen[key] = true
					total += sidecar
					continue
			else:
				header = file.get_buffer(mini(HEADER_BYTES, length))
		seen[key] = true
		total += texture_bytes(header_size(header))
	return total

## The GPU bytes of `sha`'s sidecar in `directory` when this client would
## upload it for every role in `roles` (vram_textures.gd), else 0: as the
## loaders judge it, an image no material samples, or one sampled in a role
## its sidecar was not encoded for, is decoded.
static func _usable_sidecar(sha: String, directory: String, roles: Variant) -> int:
	var entry := VramTextures.sidecar_entry(sha, directory)
	if entry.is_empty() or int(entry.get("gpuBytes", 0)) <= 0:
		return 0
	if roles is not Dictionary or (roles as Dictionary).is_empty() \
			or not VramTextures.sidecar_fits(entry, roles as Dictionary):
		return 0
	return int(entry.gpuBytes)

static func _sha256(bytes: PackedByteArray) -> String:
	var hashing := HashingContext.new()
	hashing.start(HashingContext.HASH_SHA256)
	hashing.update(bytes)
	return hashing.finish().hex_encode()
