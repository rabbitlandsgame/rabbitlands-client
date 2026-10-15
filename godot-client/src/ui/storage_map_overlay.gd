extends "res://src/ui/picture_marker_overlay.gd"
## Permanent storage locations on north-up Tab previews and continent pictures.
## Live maps continue to use the server's objects and normal map overlays.

const DotOverlayScript := preload("res://src/ui/minimap_marker_overlay.gd")
func _draw() -> void:
	for value: Variant in _marks:
		var point: Variant = mark_point(value as Dictionary)
		if not point is Vector2:
			continue
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS + DotOverlayScript.OUTLINE_WIDTH,
			DotOverlayScript.OUTLINE_COLOUR)
		draw_circle(point as Vector2, DotOverlayScript.BASE_RADIUS, MapObject3D.STORAGE_COLOUR)
