extends "res://src/app/main.gd"
## Deterministic picking for test_range_lock.gd; dispatch stays in production.
var picked_actor := -1

func _pick_actor(_position: Vector2) -> int:
	return picked_actor

func _pick_ground_bag(_position: Vector2) -> int:
	return -1

func _pick_map_object(_position: Vector2) -> MapObject3D:
	return null

func _navigation_ray_position(_origin: Vector3, _direction: Vector3) -> Variant:
	return Vector3(10, 0, 20)
