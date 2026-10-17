extends "res://src/app/main.gd"
## Loaded after autoload registration, like the production main scene.
var picked_actor := -1
var picked_bag := -1
var picked_object: MapObject3D
var actors_by_position: Dictionary = {}

func _pick_actor(position: Vector2) -> int:
	return int(actors_by_position.get(position, -1)) if not actors_by_position.is_empty() else picked_actor

func _pick_ground_bag(_position: Vector2) -> int:
	return picked_bag

func _pick_map_object(_position: Vector2) -> MapObject3D:
	return picked_object
