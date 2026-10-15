class_name ItemAtlas
extends RefCounted

## Eternal Lands draws a worn item as its own artwork mirrored across the
## vertical axis, with an orange exclamation mark in the lower-right corner.
## The mirror is the load-bearing half: a degraded item shares its picture with
## the fresh one it came from, so flipping is what tells them apart at a glance
## without a second piece of art for every item in the catalog. The mark is
## what stops a mirrored-but-symmetrical icon reading as unchanged.
const WORN_MARK_COLOUR := Color(0.98, 0.55, 0.11)
## Worn goods turn up on light and dark artwork alike, so the mark is outlined
## rather than trusted to contrast on its own.
const WORN_MARK_OUTLINE := Color(0.06, 0.04, 0.02, 0.92)

var _atlas_paths: Array[String] = []
var _textures: Dictionary = {}
var _aliases: Dictionary = {}
var _worn_icons: Dictionary = {}
## One AtlasTexture per resolved image id. Building one is tens of
## microseconds, and every inventory refresh asked for one per slot; the
## textures are never written to, so one instance serves every slot and
## every window that shows the same picture.
var _icons: Dictionary = {}
var _cell_size := Vector2(50.0, 50.0)
var _columns := 5
var _images_per_atlas := 25
var _image_count := -1
var _fallback_image_id := -1

func configure(config: Dictionary) -> void:
	_atlas_paths.clear()
	_textures.clear()
	_aliases.clear()
	_worn_icons.clear()
	_icons.clear()
	var cell_value: Variant = config.get("cellSize", [50, 50])
	if cell_value is Array:
		var values: Array = cell_value as Array
		if values.size() >= 2:
			_cell_size = Vector2(float(values[0]), float(values[1]))
	_columns = maxi(1, int(config.get("columns", 5)))
	_images_per_atlas = maxi(1, int(config.get("imagesPerAtlas", 25)))
	# The atlas set includes a declared painted range and a dedicated fallback.
	# Capacity alone would treat the remaining blank grid cells as real icons.
	_image_count = int(config.get("imageCount", -1))
	_fallback_image_id = int(config.get("fallbackImageId", -1))
	var aliases_value: Variant = config.get("aliases", {})
	if aliases_value is Dictionary:
		var aliases: Dictionary = aliases_value as Dictionary
		for source_value: Variant in aliases:
			_aliases[int(str(source_value))] = int(aliases.get(source_value, -1))
	var paths_value: Variant = config.get("atlases", [])
	if paths_value is Array:
		for raw_path: Variant in paths_value:
			_atlas_paths.append(str(raw_path))

func icon_for(image_id: int) -> Texture2D:
	if image_id < 0:
		return null
	var resolved_image_id: int = _resolved_image_id(image_id)
	if resolved_image_id < 0:
		return null
	var cached: Variant = _icons.get(resolved_image_id)
	if cached is AtlasTexture:
		return cached as AtlasTexture
	var atlas_index: int = floori(float(resolved_image_id) / float(_images_per_atlas))
	if atlas_index < 0 or atlas_index >= _atlas_paths.size():
		return null
	var texture: Texture2D = _texture_for(atlas_index)
	if texture == null:
		return null
	var local_id: int = resolved_image_id % _images_per_atlas
	var atlas_texture: AtlasTexture = AtlasTexture.new()
	atlas_texture.atlas = texture
	atlas_texture.region = Rect2(
		float(local_id % _columns) * _cell_size.x,
		float(floori(float(local_id) / float(_columns))) * _cell_size.y,
		_cell_size.x, _cell_size.y)
	_icons[resolved_image_id] = atlas_texture
	return atlas_texture

## The same item, drawn as worn: mirrored, with the orange mark. Baked into a
## texture rather than drawn as a flipped node with an overlay, because these
## end up in `ItemList.set_item_icon` and `Button.icon`, which take a texture
## and nothing else. Cached per image id - the work is per artwork, not per
## slot, and a full inventory would otherwise redo it on every refresh.
## The glyph the atlas set reserves for "there is no art for this". A summon
## produces no item, so the window that lists summons asks for this by name
## rather than inventing an icon of its own or drawing an empty square.
func placeholder_icon() -> Texture2D:
	return icon_for(_fallback_image_id)

func worn_icon_for(image_id: int) -> Texture2D:
	if _worn_icons.has(image_id):
		return _worn_icons[image_id] as Texture2D
	var image: Image = _region_image(image_id)
	if image == null:
		return null
	image.flip_x()
	_stamp_worn_mark(image)
	var texture: ImageTexture = ImageTexture.create_from_image(image)
	_worn_icons[image_id] = texture
	return texture

## The cell's own pixels, copied out of its atlas.
func _region_image(image_id: int) -> Image:
	var source: Dictionary = icon_source(image_id)
	if source.is_empty():
		return null
	var resource: Resource = load(str(source.path))
	if not resource is Texture2D:
		return null
	var whole: Image = (resource as Texture2D).get_image()
	if whole == null:
		return null
	var region: Rect2 = source.region as Rect2
	var copied: Image = whole.get_region(Rect2i(
		int(region.position.x), int(region.position.y),
		int(region.size.x), int(region.size.y)))
	# set_pixel needs a writable, unpacked format; atlases ship compressed.
	copied.convert(Image.FORMAT_RGBA8)
	return copied

## The mark's geometry for a cell of this size, so the drawing code and
## anything checking it read the same numbers instead of each keeping its own
## copy. Returns the stroke width and the bounding box, outline included.
static func worn_mark_metrics(width: int, height: int) -> Dictionary:
	var unit: int = maxi(1, roundi(float(mini(width, height)) / 16.0))
	var bar_height: int = unit * 3
	# Two units, not one: each shape carries a one-pixel outline, so a gap the
	# width of the stroke closed up and the mark read as a plain orange bar.
	var gap: int = unit * 2
	# Clear of the very bottom of the cell. A stack count is drawn over the
	# icon's bottom edge, right-aligned and up to seven digits wide, so a mark
	# flush with the corner sat underneath the number and neither could be
	# read. This keeps the mark in the lower-right, where Eternal Lands puts
	# it, while leaving the number the band it needs.
	var margin: int = unit * 3
	var left: int = width - margin - unit
	var top: int = height - margin - bar_height - gap - unit
	return {"unit": unit, "bar_height": bar_height, "gap": gap,
		"left": left, "top": top,
		"bounds": Rect2i(left - 1, top - 1, unit + 2,
			bar_height + gap + unit + 2)}

## An exclamation mark in the lower-right corner, drawn from rectangles so it
## renders identically at any atlas cell size and needs no font.
func _stamp_worn_mark(image: Image) -> void:
	var metrics: Dictionary = worn_mark_metrics(image.get_width(),
		image.get_height())
	var unit: int = int(metrics.unit)
	var bar_height: int = int(metrics.bar_height)
	var gap: int = int(metrics.gap)
	var left: int = int(metrics.left)
	var top: int = int(metrics.top)
	# Outline first, so the fill sits inside it rather than over it.
	_fill(image, left - 1, top - 1, unit + 2, bar_height + 2, WORN_MARK_OUTLINE)
	_fill(image, left - 1, top + bar_height + gap - 1, unit + 2, unit + 2,
		WORN_MARK_OUTLINE)
	_fill(image, left, top, unit, bar_height, WORN_MARK_COLOUR)
	_fill(image, left, top + bar_height + gap, unit, unit, WORN_MARK_COLOUR)

func _fill(image: Image, x: int, y: int, width: int, height: int,
		colour: Color) -> void:
	for offset_y: int in range(maxi(0, y), mini(image.get_height(), y + height)):
		for offset_x: int in range(maxi(0, x), mini(image.get_width(), x + width)):
			image.set_pixel(offset_x, offset_y, colour)

## The atlas file and the rectangle inside it for one item, or an empty
## dictionary. RichTextLabel's [img region=...] tag needs both as text, and it
## cannot be handed the AtlasTexture icon_for() builds.
func icon_source(image_id: int) -> Dictionary:
	if image_id < 0:
		return {}
	var resolved_image_id: int = _resolved_image_id(image_id)
	if resolved_image_id < 0:
		return {}
	var atlas_index: int = floori(float(resolved_image_id) / float(_images_per_atlas))
	if atlas_index < 0 or atlas_index >= _atlas_paths.size():
		return {}
	var local_id: int = resolved_image_id % _images_per_atlas
	return {"path": _atlas_paths[atlas_index], "region": Rect2(
		float(local_id % _columns) * _cell_size.x,
		float(floori(float(local_id) / float(_columns))) * _cell_size.y,
		_cell_size.x, _cell_size.y)}

func supports(image_id: int) -> bool:
	var capacity: int = _atlas_paths.size() * _images_per_atlas
	var painted: int = capacity if _image_count < 0 else mini(_image_count, capacity)
	return image_id >= 0 and image_id < painted

func uses_substitute(image_id: int) -> bool:
	return image_id >= 0 and (_aliases.has(image_id) or not supports(image_id))

func _resolved_image_id(image_id: int) -> int:
	if _aliases.has(image_id):
		return int(_aliases.get(image_id, -1))
	if supports(image_id):
		return image_id
	return _fallback_image_id

func _texture_for(atlas_index: int) -> Texture2D:
	if _textures.has(atlas_index):
		return _textures[atlas_index] as Texture2D
	var resource: Resource = load(_atlas_paths[atlas_index])
	if not resource is Texture2D:
		return null
	var texture: Texture2D = resource as Texture2D
	_textures[atlas_index] = texture
	return texture
