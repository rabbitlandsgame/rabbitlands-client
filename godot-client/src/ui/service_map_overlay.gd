extends "res://src/ui/picture_marker_overlay.gd"
## Permanent shop and tavern dots on region previews and the continent picture.

const DotOverlayScript := preload("res://src/ui/minimap_marker_overlay.gd")
const SHOP_COLOUR := Color("4fc67a")
const TAVERN_COLOUR := Color("ef795f")

static func dot_colour(mark: Dictionary) -> Color:
	return TAVERN_COLOUR if mark.get("category", "") == "tavern" else SHOP_COLOUR

func _draw() -> void:
	for value: Variant in _marks:
		var mark: Dictionary = value as Dictionary
		var point: Variant = mark_point(mark)
		if not point is Vector2:
			continue
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS + DotOverlayScript.OUTLINE_WIDTH,
			DotOverlayScript.OUTLINE_COLOUR)
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS, dot_colour(mark))
