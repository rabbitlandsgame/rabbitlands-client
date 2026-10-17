extends "res://src/app/main.gd"
## Observe movement dispatch without a network connection. All gesture handling,
## map projection, and marker placement use the production implementation.
var map_clicks: Array[Dictionary] = []

func _handle_map_gui_input(event: InputEvent, _control: TextureRect,
		_viewport: SubViewport, camera: Camera3D, source: String) -> void:
	if not _map_input_blocked() and event is InputEventMouseButton and event.pressed:
		var pixel: Variant = _texture_to_viewport_position(event.position, map_image, full_map_viewport.size)
		map_clicks.append({"run": event.shift_pressed, "source": source,
			"tile": _map_target_tile(camera, pixel) if pixel is Vector2 else null})
