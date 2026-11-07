extends "res://src/app/main.gd"
## UI probes exercise the real controls without starting map streaming or
## animation-library loading when their fixture authenticates AppState.

func _prepare_geometry_before_login() -> bool:
	return false

func _load_server_map() -> void:
	pass

func _prewarm_shared_animation_libraries() -> void:
	pass
