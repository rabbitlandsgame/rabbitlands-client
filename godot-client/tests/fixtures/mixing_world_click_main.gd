extends "res://src/app/main.gd"

## Deterministic ray hits; viewport dispatch and network requests stay real.
var clicked_actor := -1
var clicked_object: MapObject3D

func _pick_actor(_position: Vector2) -> int:
	return clicked_actor

func _pick_map_object(_position: Vector2) -> MapObject3D:
	return clicked_object
