extends RefCounted
## Rasterize world text at higher resolution, then draw it at its intended size.
## Small Label3D glyphs otherwise get enlarged by the viewport stretch and look
## heavier than the player's canvas labels, despite using the same typeface.
const RASTER_SCALE := 4

static func apply(label: Label3D, font_size: int, pixel_size: float,
		outline_size: int) -> void:
	label.font = ThemeDB.fallback_font
	label.font_size = font_size * RASTER_SCALE
	label.pixel_size = pixel_size / RASTER_SCALE
	label.outline_size = outline_size * RASTER_SCALE
	label.offset *= RASTER_SCALE
	label.width *= RASTER_SCALE
	label.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR
	label.shaded = false
	# The default outline priority (-1) puts it behind alpha-blended scenery,
	# even with depth testing disabled. Draw both passes after world effects,
	# keeping the outline behind the letters.
	label.outline_render_priority = 10
	label.render_priority = 11
