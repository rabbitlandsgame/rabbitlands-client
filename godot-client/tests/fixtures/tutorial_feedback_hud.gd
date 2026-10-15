extends "res://src/app/main.gd"
## Keep the production grouping/suppression path, recording its rendered output.
var spawned: Array[Dictionary] = []

func _spawn_floating_feedback(feedback: Dictionary) -> void:
	spawned.append(feedback)
