extends RefCounted
## Device preferences shared by texture workers and the graphics window.
## Texture quality is fixed for a session: shared images and disk scene caches
## must never mix full and reduced textures after an in-game preference change.

const SETTINGS_PATH := "user://eloria_hud.cfg"
const RENDER_SCALES := [1.0, 0.75, 0.5]
const TEXTURE_QUALITIES := ["full", "half", "quarter"]
static var _texture_skip := -1
static var decorative_grass := true

static func render_scale(value: Variant) -> float:
	if value is float or value is int:
		for scale: float in RENDER_SCALES:
			if is_equal_approx(float(value), scale):
				return scale
	return 1.0

static func texture_quality(value: Variant) -> String:
	return str(value) if value is String and value in TEXTURE_QUALITIES else "full"

static func active_texture_skip() -> int:
	if _texture_skip < 0:
		var config := ConfigFile.new()
		config.load(SETTINGS_PATH)
		_texture_skip = TEXTURE_QUALITIES.find(texture_quality(
			config.get_value("graphics", "map_texture_quality", "full")))
	return _texture_skip

static func mip_skip(width: int, height: int, mipmaps: int, requested: int,
		block_aligned := false) -> int:
	var skip := clampi(requested, 0, mipmaps)
	# Keep block-compressed images aligned and small authored textures intact.
	while skip > 0 and ((width >> skip) < 4 or (height >> skip) < 4 \
			or (block_aligned and ((width >> skip) % 4 != 0 or (height >> skip) % 4 != 0))):
		skip -= 1
	return skip

## Slice existing levels, including BC textures, without decompressing,
## resizing, re-encoding, or altering an image another importer may share.
static func reduced_image(image: Image, requested := -1) -> Image:
	if image == null or image.is_empty():
		return image
	var skip := mip_skip(image.get_width(), image.get_height(), image.get_mipmap_count(),
		active_texture_skip() if requested < 0 else requested, image.is_compressed())
	if skip == 0:
		return image
	return Image.create_from_data(image.get_width() >> skip, image.get_height() >> skip,
		skip < image.get_mipmap_count(), image.get_format(),
		image.get_data().slice(image.get_mipmap_offset(skip)))
