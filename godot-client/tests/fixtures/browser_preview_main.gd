extends "res://src/app/main.gd"
var selected_ready := false
var admitted_dto := {}
func _browser_actor_ready(_id: int, dto: Dictionary) -> bool:
	admitted_dto = dto.duplicate(true)
	return selected_ready
