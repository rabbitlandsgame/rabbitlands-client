extends "res://src/app/main.gd"

## Captures only the beyond-seam dispatch. Everything before this override is
## the production minimap/Tab-map handler, texture conversion, ray projection,
## and cartography polygon ownership decision.
var map_click_dispatches: Array[Dictionary] = []

func _map_click_beyond(camera: Camera3D, viewport_position: Vector2, run: bool,
		source: String, owner := "") -> void:
	var point_value: Variant = _map_click_point(camera, viewport_position)
	map_click_dispatches.append({
		"source": source,
		"owner": owner,
		"run": run,
		"point": point_value,
		"tile": adapter.godot_to_server(point_value as Vector3) if point_value is Vector3 else null})

func clear_map_click_dispatches() -> void:
	map_click_dispatches.clear()
