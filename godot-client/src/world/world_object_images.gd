extends GLTFDocumentExtension
## World-object GLBs embed their images. Build mipmaps before their first GPU
## upload, avoiding the readback previously needed by GlbSceneCache afterwards.
const ENABLED := &"rabbitlands_world_object_images"
const PREPARED := &"rabbitlands_world_object_images_prepared"

func _import_preflight(state: GLTFState, _extensions: PackedStringArray) -> Error:
	var enabled: Variant = state.get_additional_data(ENABLED)
	if typeof(enabled) != TYPE_BOOL or not enabled:
		return ERR_SKIP
	state.set_additional_data(PREPARED, 0)
	return OK

func _parse_image_data(state: GLTFState, bytes: PackedByteArray, _mime: String, image: Image) -> Error:
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
	# Empty images fall back to GLTFDocument's normal decoder.
	return OK
