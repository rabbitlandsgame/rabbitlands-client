extends "res://src/app/main.gd"
## Loaded after autoload registration, like the production main scene.
var picked_actor := -1
var picked_bag := -1
var picked_object: MapObject3D

func _pick_actor(_position: Vector2) -> int:
	return picked_actor

func _pick_ground_bag(_position: Vector2) -> int:
	return picked_bag

func _pick_map_object(_position: Vector2) -> MapObject3D:
	return picked_object
